"""Build offline category reports and safely rendered page comparisons."""
import csv
import json
from html import escape as e

from benchmark import ROOT, PARSERS, read_json, read_jsonl, sha, table_html

NAMES = {'mineru_ocr': 'MinerU OCR', 'mineru_vlm': 'MinerU VLM', 'pymupdf4llm': 'PyMuPDF4LLM + Tesseract', 'pymupdf4llm_vlm': 'PyMuPDF4LLM + VLM'}
# Display groups do not alter scoring or denominators.
GROUPS = {
    'tables': dict(title='Table parsing', question='Did each value stay attached to the right row and column?',
                   kinds={'table'}, primary=['associated_value_accuracy', 'row_header_resolved'],
                   extra=['table_detected_by_row_labels', 'explicit_header_span_accuracy'],
                   scope='11 table references, 133 expected cells across six documents. Only two explicit merged-header assertions are labeled.',
                   example='CVS revenue is $98.9 under 2Q 2025 and $91.2 under 2Q 2024. Swapping the year headers retains both numbers but fails the correct-cell check.',
                   caution='Unmatched rows, missing headers and ambiguous cells count as failures. Some are export-format or strict-matcher limitations; a failed check does not always mean the value disappeared.'),
    'numbers': dict(title='Number retention', question='Did the expected numbers, signs and units survive?',
                    kinds={'table','visual_fact'}, primary=['selected_value_presence', 'negative_value_accuracy', 'visual_value_presence'],
                    extra=['display_form_accuracy', 'inline_currency_unit_accuracy', 'unit_evidence_retention',
                           'complete_matrix_numeric_recall', 'complete_matrix_numeric_precision'],
                    scope='128 numeric table expectations, including 18 negative values; five additional visual-card values. Five blank/dash cells are excluded from numeric presence.',
                    example='If 98.9 survives but moves under the wrong year, page-level number presence passes and table association fails. If (84.6) becomes 84.6, the negative-value check fails.',
                    caution='Finding a number anywhere on the page does not prove its meaning, row, year or unit. Sign and formatting checks use resolved table cells, so they also fail when a cell cannot be matched.'),
    'text': dict(title='Text & document organization', question='Did the words, notes and reading sequence survive?',
                 kinds={'text','footnote','reading_order','metadata','visual_fact'},
                 primary=['text_span_retention', 'footnote_text_retention', 'reading_order_accuracy'],
                 extra=['matched_span_character_error_rate', 'visual_label_value_sequence', 'metadata_evidence_retention'],
                 scope='Eight text spans, five footnotes, seven order pairs, eighteen metadata-evidence fields and five visual-card relationships.',
                 example='A footnote can retain every word yet become detached from its table. Text retention can pass in that case; correct footnote attachment is not automatically scored.',
                 caution='This small sample does not test the full reading order of all 140 pages. Visual sequence and metadata evidence are proxies; they do not establish semantic understanding.'),
}
# title, definition, interpretation/limitation
METRICS = {
'associated_value_accuracy': ('Correct value in the correct cell', 'Checks the expected amount and inline scale under the labeled row and full column-header path.', 'Higher is better. Missing or ambiguous matches fail. Inline currency is checked separately.'),
'row_header_resolved': ('Row and column can be identified', 'Checks whether the adapter finds exactly one cell for the labeled row and header path, before judging its value.', 'Higher is better. A gap between this and correct-cell accuracy means some located cells contain incorrect values.'),
'table_detected_by_row_labels': ('Reference table can be located', 'Chooses a unique table using exact normalized row-label matches, without looking at the expected values.', 'Higher is better. This is a matching diagnostic, not a general table-detector accuracy score.'),
'explicit_header_span_accuracy': ('Selected merged headers retained', 'Checks the two labeled EDF headers for their expected row and column spans.', 'Higher is better. Only two assertions on one document; not a broad merged-cell benchmark.'),
'selected_value_presence': ('Expected table number appears on the page', 'Looks for each signed numeric amount and inline scale anywhere on its labeled page, ignoring row and column.', 'Higher is better. Repeated facts can be satisfied by the same occurrence; currency symbols are checked separately. This does not verify association.'),
'negative_value_accuracy': ('Negative values correct in their cells', 'Checks the eighteen negative table expectations, including the amount and sign, in the correctly associated cell.', 'Higher is better. Parentheses and a minus sign are equivalent. Unresolved cells also fail, so failures are not necessarily lost minus signs.'),
'visual_value_presence': ('Visual-card number appears on the page', 'Looks for the five labeled slide-card amounts in the extracted page text.', 'Higher is better. Does not prove the number remains attached to its metric label.'),
'display_form_accuracy': ('Original cell formatting retained', 'Compares each resolved cell with its source display after case, Unicode and whitespace normalization.', 'Higher is better. Equivalent numeric displays such as (84.6) and -84.6 can differ here; this is presentation fidelity.'),
'inline_currency_unit_accuracy': ('Inline currency and unit retained', 'For labeled cells with an inline currency or suffix, checks those symbols in the resolved cell.', 'Higher is better. This checks symbols, not the numeric amount or a separate table-wide unit heading.'),
'unit_evidence_retention': ('Unit wording appears on the page', 'Looks for labeled unit phrases such as “In billions, except per share amounts”.', 'Higher is better. Presence alone cannot prove which numbers the unit applies to.'),
'complete_matrix_numeric_recall': ('Numbers recovered in complete reference matrices', 'Counts matching numeric occurrences in four fully labeled data matrices, divided by their 58 expected numeric occurrences.', 'Higher is better. Repeated values are counted; associations are ignored. Missing table/header matches reduce recall.'),
'complete_matrix_numeric_precision': ('Extracted matrix numbers match the reference', 'Within the four declared matrices, divides matching numeric occurrences by the extracted occurrences admitted by the table/header matcher.', 'Higher is better. A 100% score can coexist with missing values: always read with recall. Zero extracted values gives N/A. This is not document-wide hallucination precision.'),
'text_span_retention': ('Selected text passages retained', 'Looks for the eight labeled source strings after case, Unicode and whitespace normalization.', 'Higher is better. Exact wording is required; this does not judge paraphrase meaning or all document text.'),
'footnote_text_retention': ('Footnote wording retained', 'Looks for the five labeled footnote strings in the extracted page text.', 'Higher is better. Correct attachment to the referenced table or fact is not established.'),
'reading_order_accuracy': ('Selected text pairs in the right order', 'Checks that both anchors appear exactly once and the first comes before the second.', 'Higher is better. Missing or repeated anchors fail; seven pairs cannot establish full-document reading order.'),
'matched_span_character_error_rate': ('Character errors in selected text', 'Aligns each of thirteen text/footnote references to its best matching page-text span, then counts character edits relative to reference length.', 'Lower is better. This is a fuzzy-aligned diagnostic on selected spans, not whole-page OCR error.'),
'visual_label_value_sequence': ('Visual label and value follow the expected text sequence', 'Looks for the expected amount between its metric label and the next labeled card within a short text window.', 'Higher is better. Valid alternative reading orders can fail; textual proximity does not prove a visual relationship.'),
'metadata_evidence_retention': ('Document identity wording retained', 'Looks for source wording supporting issuer, period and document type: eighteen field-evidence checks.', 'Higher is better. Does not evaluate extracted metadata fields, since existing metadata contains manifest-supplied information.'),
}
UNSCORED = {
 'footnote_target_association': ('Footnote attachment', 'Labels store the target, but automatic scoring cannot establish the attachment.'),
 'visual_semantic_association': ('Visual meaning', 'Labels store metric–value relationships, but text order alone cannot verify their meaning.'),
 'metadata_field_accuracy': ('Independent metadata extraction', 'Existing metadata uses source-manifest fields, so scoring it as an independent extraction would be misleading.'),
}
CSS = """
:root{font-family:system-ui,sans-serif;color:#173033;background:#f5f7f6;font-size:15px}body{max-width:1200px;margin:auto;padding:30px}
h1{font-size:34px;letter-spacing:-1px;margin:26px 0 10px}h2{margin-top:30px}h3{margin:10px 0}h4{overflow-wrap:anywhere}p,li{line-height:1.6}
a{color:#006b68}.banner{border-left:4px solid #c27b22;background:#fff2d9;padding:14px 18px;margin:22px 0}.muted,small{color:#52666b}
small{display:block;font-size:12px;font-weight:400;margin-top:5px}.stats{display:flex;gap:30px;flex-wrap:wrap}.stats b{font-size:25px;display:block}
table{border-collapse:collapse;width:100%;font-size:14px;background:white}th,td{border:1px solid #d8e2df;padding:12px;text-align:left}th{background:#edf3f0}.scroll{overflow:auto}
details{margin:16px 0}summary{cursor:pointer;font-weight:600;padding:12px;background:#e5edeb;border-radius:5px}
.page{display:grid;grid-template-columns:minmax(280px,1fr) minmax(0,1fr);gap:22px;margin-top:20px}.source img{width:100%;border:1px solid #cad7d2}.source{align-self:start;position:sticky;top:16px}
article,.card{background:white;border:1px solid #d8e2df;padding:20px;margin:16px 0;border-radius:8px}.tag{font-size:12px;text-transform:uppercase;letter-spacing:.6px;color:#527268}
dt{font-size:12px;color:#52666b;margin-top:8px}dd{margin:3px 0;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;font-size:12px;background:#eef2f1;padding:12px}
nav,.links{display:flex;gap:18px;flex-wrap:wrap}nav{padding-bottom:18px;border-bottom:1px solid #d8e2df}nav a[aria-current]{font-weight:700;color:#173033;text-decoration:none}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}
@media(max-width:850px){body{padding:16px}.page,.cards{display:block}.source{position:static}h1{font-size:27px}}
"""


def page_start(title, active, verified, total):
    links = [('workspace','Review labels'),('index','Overview'),('comparison','Page comparisons'),('outputs','Full parsed results'),('tables','Tables'),('numbers','Numbers'),('text','Text & organization'),('labels','Source & labels')]
    nav = ''.join(f'<a href="{key}.html"' + (' aria-current="page"' if key == active else '') + '>' + e(name) + '</a>' for key,name in links)
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>' + e(title) + ' · sponsor pilot</title><style>' + CSS + '</style></head><body><nav>' + nav + '</nav><main>'
            '<h1>' + e(title) + '</h1><div class="banner"><b>' + str(verified) + ' / ' + str(total) + ' relevant label records human-verified in the saved benchmark.</b> '
            'This counts reference labels, not tables or parser checks. Browser decisions enter this count after export/import. '
            '<a href="workspace.html">Review labels here</a>. Performance results include drafts and remain preliminary.</div>')


def page_end():
    return '<footer><p class="muted">Report generation uses saved outputs · no hosted model calls · <a href="../README.md">Method</a> · <a href="../results/preliminary.json">Full results and provenance</a></p></footer></main></body></html>'


def score_cell(metric):
    if not metric or metric['value'] is None:
        return '<td class="muted">N/A</td>'
    if 'reference_chars' in metric:
        count = f"{metric['character_errors']} / {metric['reference_chars']} characters"
    elif 'denominator' in metric:
        count = f"{metric['numerator']} / {metric['denominator']} values"
    else:
        count = f"{metric['passed']} / {metric['total']} checks"
    return f'<td><b>{metric["value"]:.1%}</b><small>{count}</small></td>'


def metric_table(aggregate, names):
    rows = ['<div class="scroll"><table><thead><tr><th>Metric</th>' + ''.join(f'<th>{NAMES[p]}</th>' for p in PARSERS) + '</tr></thead><tbody>']
    for name in names:
        title = METRICS[name][0]
        if name == 'matched_span_character_error_rate':
            title += ' (lower is better)'
        rows.append('<tr><th>' + e(title) + '</th>' + ''.join(score_cell(aggregate[p].get(name)) for p in PARSERS) + '</tr>')
    return ''.join(rows) + '</tbody></table></div>'


def label_card(label):
    if label['kind'] == 'table':
        body = table_html(label) + '<p>Scope: ' + e(label['coverage']) + '. Unit evidence: ' + e('; '.join(label.get('unit_evidence', []))) + '</p>'
        if label.get('context'):
            body += '<p>' + e(str(label['context'])) + '</p>'
    else:
        fields = ('text', 'before', 'after', 'label', 'value', 'next_label', 'field', 'evidence_text', 'target')
        body = '<dl>' + ''.join('<dt>' + e(k.replace('_', ' ')) + '</dt><dd>' + e(str(label[k])) + '</dd>' for k in fields if k in label) + '</dl>'
    return ('<article><div class="tag">' + e(label['kind']) + ' · ' + e(label['importance']) + ' · ' + e(label['review_status']) + '</div>'
            '<h4>' + e(label['id']) + '</h4><p class="muted">Source region: ' + e(label['evidence']['region']) + '</p>'
            '<div class="scroll">' + body + '</div></article>')


def metric_card(result, metric):
    title, definition, interpretation = METRICS[metric]
    return ('<article><h3>' + e(title) + '</h3><p>' + e(definition) + '</p>'
            + metric_table(result['aggregate'], [metric]) + '<p class="muted">' + e(interpretation) + '</p></article>')


def source_review(labels, documents, checks, allowed=None, kinds=None):
    pieces = []
    for doc in documents:
        selected = [x for x in labels if x['document'] == doc['id'] and (kinds is None or x['kind'] in kinds)]
        if not selected:
            continue
        pages = sorted({x['page'] for x in selected})
        pieces.append('<h3>' + e(doc['title']) + '</h3><p>' + str(doc['pages']) + ' PDF pages · <a href="' + e(doc['url']) + '">Original public PDF</a></p>')
        for page in pages:
            page_labels = [x for x in selected if x['page'] == page]
            asset = e(doc['id']) + '_' + str(page) + '.png'
            pieces.append(f'<details id="{e(doc["id"])}-p{page}"><summary>PDF page {page} · {len(page_labels)} label records</summary><div class="page">'
                          f'<div class="source"><a href="assets/{asset}"><img loading="lazy" src="assets/{asset}" alt="Original PDF page {page}"></a></div><div>')
            pieces.extend(label_card(x) for x in page_labels)
            if allowed is not None:
                failures = [r for r in checks if r['document'] == doc['id'] and r['page'] == page and r.get('passed') is False and r['metric'] in allowed]
                pieces.append('<details><summary>Failed checks in this category (' + str(len(failures)) + ')</summary>')
                for parser in PARSERS:
                    failed = [r for r in failures if r['parser'] == parser]
                    pieces.append('<h4>' + NAMES[parser] + '</h4>')
                    if not failed:
                        pieces.append('<p>No failed binary checks in this category.</p>')
                    for record in failed:
                        detail = record.get('detail')
                        pieces.append('<details><summary>' + e(METRICS[record['metric']][0] + ' · ' + record['label_id']) + '</summary><pre>' + e(str(detail) if detail is not None else 'Expected labeled text, value or relationship was not found by this check.') + '</pre></details>')
                pieces.append('</details>')
            pieces.append('</div></div></details>')
    return ''.join(pieces)


def main():
    labels = read_jsonl(ROOT/'labels.jsonl')
    documents = read_json(ROOT/'documents.json')
    coverage = read_json(ROOT/'coverage.json')
    result = read_json(ROOT/'results/preliminary.json')
    assert result['label_sha256'] == sha(ROOT/'labels.jsonl'), 'Rescore after editing labels'
    assert result['scorer_sha256'] == sha(ROOT/'benchmark.py'), 'Rescore after editing scorer'
    checks = read_jsonl(ROOT/'results/preliminary_checks.jsonl')
    verified = sum(x['review_status'] in {'human_verified', 'adjudicated'} for x in labels)
    out = ROOT/'review'
    out.mkdir(exist_ok=True)
    review_data = dict(label_sha256=sha(ROOT/'labels.jsonl'), labels=[dict(
        id=x['id'], document=x['document'], page=x['page'], kind=x['kind'],
        source_sha256=x['source_sha256'], review_status=x['review_status'],
        decision=x.get('review_decision'), reviewer=x.get('reviewer'), reviewed_at=x.get('reviewed_at'),
        html=label_card(x)) for x in labels])
    workspace = (ROOT/'review_workspace.html').read_text().replace('/* SHARED_CSS */', CSS)
    workspace = workspace.replace('/* REVIEW_DATA */', json.dumps(review_data,ensure_ascii=False).replace('<','\\u003c'))
    (out/'workspace.html').write_text(workspace)
    mapped = [m for group in GROUPS.values() for m in group['primary'] + group['extra']]
    assert len(mapped) == len(set(mapped)), 'Metric assigned to multiple review categories'
    assert set(mapped) | set(UNSCORED) == set(result['aggregate'][PARSERS[0]]), 'Unexplained metric in report'
    intro = page_start('Choose one evaluation question', 'index', verified, len(labels))
    intro += '<section class="card"><h2>October 6 addition: four pipelines</h2><p><a href="comparison.html">Compare the same source page across all four pipelines</a> · <a href="outputs.html">Find every full parsed document</a> · <a href="../results/SUMMARY.md">Concise result summary</a></p><p>PyMuPDF4LLM now has a local MinerU VLM OCR backend. The original three outputs and 54 labels are unchanged. Automatic OCR means native-text pages may not invoke either OCR engine.</p></section>'
    intro += '<p><a href="../MEETING.md">Wednesday meeting walkthrough</a>. This is a working preliminary pilot; independent teammate review is optional follow-up, not a prerequisite for exploring the results.</p><details><summary>Optional teammate review</summary><p><a href="workspace.html">Review labels →</a> Compare drafts with original pages, approve or flag corrections, then export decisions. A shared label only needs review once.</p></details><p>Each performance review focuses on one aspect of parsing. Definitions appear beside the results.</p><div class="cards">'
    for key, group in GROUPS.items():
        intro += '<section class="card"><h2><a href="' + key + '.html">' + e(group['title']) + '</a></h2><p>' + e(group['question']) + '</p><small>' + str(len(group['primary'])) + ' main checks; supporting details are collapsed.</small></section>'
    intro += '</div><h2>What has been labeled?</h2><div class="stats">'
    for count, description in [(coverage['documents'],'source PDFs'),(str(coverage['annotated_pages'])+' / '+str(coverage['source_pages']),'pages with selected labels'),(coverage['labels'],'label records'),(coverage['table_facts'],'expected table cells')]:
        intro += '<div><b>' + str(count) + '</b>' + description + '</div>'
    intro += '</div><p><a href="labels.html">Review original source pages beside the labels →</a></p><p>Label review has no parser scores. Confirm source values and relationships first, then inspect the category reviews.</p>'
    intro += '<h2>How to read these reviews</h2><ul><li>Counts are passed checks / applicable checks, not a percentage of the entire document.</li><li>The same number may pass retention and fail table association; these answer different questions.</li><li>Missing or ambiguous matches fail applicable checks. N/A means not measured, not zero performance.</li><li>There is no combined score. Small, selected samples do not establish overall parser quality.</li></ul>'
    (out/'index.html').write_text(intro + page_end())
    for key, group in GROUPS.items():
        relevant = [x for x in labels if x['kind'] in group['kinds']]
        approved = sum(x['review_status'] in {'human_verified','adjudicated'} for x in relevant)
        pieces = [page_start(group['title'], key, approved, len(relevant)), '<p><a href="workspace.html#' + key + '">Review this category’s labels →</a> Labels overlap across categories; approving a table reference also supports number checks.</p>', '<h2>' + e(group['question']) + '</h2><p>' + e(group['scope']) + '</p>',
                  '<div class="card"><b>Example</b><p>' + e(group['example']) + '</p></div>', '<p><b>Interpretation:</b> ' + e(group['caution']) + '</p>']
        pieces.extend(metric_card(result,m) for m in group['primary'])
        pieces.append('<details><summary>Supporting diagnostics — definitions and results</summary>')
        pieces.extend(metric_card(result,m) for m in group['extra'])
        pieces.append('</details>')
        if key == 'text':
            pieces.append('<details><summary>Relationships recorded but not automatically scored</summary>')
            for title, explanation in UNSCORED.values():
                pieces.append('<p><b>' + e(title) + ' — N/A.</b> ' + e(explanation) + '</p>')
            pieces.append('</details>')
        pieces.append('<details><summary>Breakdown by source document — main checks only</summary>')
        for doc in documents:
            perdoc = {p: next(d['metrics'] for d in result['documents'] if d['document'] == doc['id'] and d['parser'] == p) for p in PARSERS}
            pieces.append('<h3>' + e(doc['title']) + '</h3>' + metric_table(perdoc,group['primary']))
        pieces.append('</details><details><summary>Review source labels and failures in this category</summary><p>Original pages and relevant label records appear below. Failed checks are filtered to this category; full reference tables retain their source context.</p>')
        pieces.append(source_review(labels,documents,checks,set(group['primary']+group['extra']),group['kinds']))
        pieces.append('</details>' + page_end())
        (out/(key+'.html')).write_text(''.join(pieces))
    source = page_start('Original documents & draft labels', 'labels', verified, len(labels))
    source += '<p>Review the reference independently of parser performance. Confirm transcription, signs, units, header paths, source region and relationships.</p>'
    source += '<p class="links"><a href="../labels.jsonl">Editable labels</a><a href="review_checklist.csv">Review checklist</a></p>'
    source += '<p><a href="workspace.html">Use the interactive review workspace to record decisions.</a> This page is a read-only source gallery. The CSV is only an optional working checklist.</p>'
    source += source_review(labels, documents, checks) + page_end()
    (out/'labels.html').write_text(source)
    with (out/'review_checklist.csv').open('w', newline='') as handle:
        fields = ['id','document','page','kind','importance','review_status','reviewer','reviewed_at','correction_notes']
        writer = csv.DictWriter(handle, fieldnames=fields, lineterminator='\n')
        writer.writeheader()
        writer.writerows({k: x.get(k, '') for k in fields} for x in labels)
    from review_addition import build
    build()
    print(f'Review: {out / "index.html"}')


if __name__ == '__main__':
    main()
