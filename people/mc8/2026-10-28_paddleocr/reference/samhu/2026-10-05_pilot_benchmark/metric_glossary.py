"""Metric definitions with actual, unmodified reference-label JSON examples."""
import json
from html import escape


CVS_TABLE = 'cvs_2025q2.p6.quarter_results'
EDF_TABLE = 'edf_2024.p3.segment_statement'
TEXT = 'cvs_2025q2.p1.title'
FOOTNOTE = 'cvs_2025q2.p12.prescription_note'
VISUAL = 'rolls_royce_2026h1_presentation.p5.card_operating_profit'
METADATA = 'cvs_2025q2.p1.metadata_issuer'

# Each metric points to the same authoritative record used by the scorer.
# Reusing a table label makes the distinction between its checks explicit.
EXAMPLES = {
    'associated_value_accuracy': (CVS_TABLE, 'Read rows[0].values[0] under columns[0].header_path: Total Revenues → 2Q 2025 → $98.9. Moving 98.9 to the 2024 column fails; dropping only the dollar sign does not fail this amount check.'),
    'row_header_resolved': (CVS_TABLE, 'The scorer must find exactly one cell at Total Revenues → 2Q 2025. A located cell containing 91.2 passes this structural check but fails correct-value accuracy.'),
    'table_detected_by_row_labels': (CVS_TABLE, 'rows[].label supplies the table-matching evidence. The unique table with the most matching row labels is selected; rows[].values is not used to choose it.'),
    'explicit_header_span_accuracy': (EDF_TABLE, 'header_spans requires Electricity supply and Gas supply each to span two columns. Omitted rowspan means one row. Correct header words without the required span fail.'),
    'selected_value_presence': (CVS_TABLE, 'Each numeric entry in rows[].values is sought anywhere on this page. Finding 98.9 under the wrong year still passes presence. Currency is ignored, but sign and inline suffix are retained.'),
    'negative_value_accuracy': (EDF_TABLE, 'rows[1].values[2] is (84.6), under EBITDA → Gas supply → Domestic. -84.6 passes; 84.6 or an unresolved cell fails.'),
    'visual_value_presence': (VISUAL, 'value is £2.5bn. Finding 2.5bn anywhere on page 5 passes this amount-presence check, even without the currency symbol or its Operating profit label.'),
    'display_form_accuracy': (EDF_TABLE, 'For the expected (84.6), an extracted -84.6 is numerically correct but fails display-form accuracy. Comparison normalizes case, Unicode and whitespace, not equivalent numeric notation.'),
    'inline_currency_unit_accuracy': (CVS_TABLE, 'For rows[0].values[0] = $98.9, an extracted 98.9 fails because $ is missing. This diagnostic checks currency and suffix in the resolved cell, not the numeric amount.'),
    'unit_evidence_retention': (CVS_TABLE, 'unit_evidence[0] supplies the exact phrase to find: In billions, except per share amounts. Presence does not prove which values the phrase qualifies.'),
    'complete_matrix_numeric_recall': (CVS_TABLE, 'coverage = complete_data_matrix enables this check. All ten numeric occurrences in this full label are expected. If eight match, recall is 8/10 = 80%; their row associations are ignored.'),
    'complete_matrix_numeric_precision': (CVS_TABLE, 'The same complete matrix supplies the expected numeric multiset. If the matcher admits eight extracted occurrences and all eight match, precision is 8/8 = 100%, even though recall is only 8/10. No admitted numbers gives N/A precision.'),
    'text_span_retention': (TEXT, 'text is the expected phrase: Earnings Conference Call. It must occur after case, Unicode and whitespace normalization; paraphrasing does not count.'),
    'footnote_text_retention': (FOOTNOTE, 'text supplies the footnote wording, including punctuation. marker and target document the source relationship but are not tested by this retention check. A missing final period can fail.'),
    'reading_order_accuracy': ('cvs_2025q2.p6.order_title_table', 'before and after are text anchors. Consolidated Results must occur once and precede the single occurrence of Total Revenues. Missing or repeated anchors fail.'),
    'matched_span_character_error_rate': (TEXT, 'text supplies the reference for fuzzy span alignment. Earnings Conference Call has 24 normalized characters: one substitution in an otherwise matching span gives 1/24 ≈ 4.2% CER. Insertions and deletions also count. Footnote labels generate this metric too.'),
    'visual_label_value_sequence': (VISUAL, 'The scorer looks for value between label and next_label: Operating profit → £2.5bn → Operating margin. The default window is 120 characters when max_chars is absent. Unlike amount presence, this check includes the currency symbol.'),
    'metadata_evidence_retention': (METADATA, 'evidence_text = CVS Health must survive in the page text. field and value describe the intended metadata; the check does not test whether an independent issuer field was extracted.'),
    'footnote_target_association': (FOOTNOTE, 'target stores the intended relationship. The scorer records N/A because retaining the note wording does not establish correct attachment to its target.'),
    'visual_semantic_association': (VISUAL, 'label and value describe the source relationship. The scorer records N/A: textual presence or sequence does not independently establish that the visual card was understood.'),
    'metadata_field_accuracy': (METADATA, 'field = issuer and value = CVS Health show the expected structured field. The scorer records N/A because existing metadata is supplied from the source manifest, not independently predicted.'),
}


def glossary_html(labels, metrics, unscored, names=None):
    """Put explanations and complete source-label examples before report results."""
    by_id = {label['id']: label for label in labels}
    names = list(names) if names is not None else list(metrics) + list(unscored)
    pieces = ['<section class="metric-glossary card" id="metric-glossary" aria-labelledby="glossary-title">',
              '<h2 id="glossary-title">Metric glossary &amp; label JSON examples</h2>',
              '<p>A <b>label</b> records the expected source content; a <b>metric</b> tests one aspect of the extracted output. One label can generate several checks. Every entry below includes its definition, how its fields are used, and a complete real JSON record from <a href="../labels.jsonl">labels.jsonl</a>.</p>',
              '<p>Most scores are passed / applicable checks; higher is better. Character error rate is lower-is-better. Precision and recall count numeric occurrences. Missing or ambiguous matches fail applicable checks; N/A means not measured. These selected draft references are not independently verified gold.</p>',
              '<p><a href="#evaluation-content">Skip glossary and continue to results ↓</a> · Expand any metric to see its JSON example.</p>']
    for index, name in enumerate(names):
        label_id, example = EXAMPLES[name]
        if name in metrics:
            title, definition, interpretation = metrics[name]
        else:
            title, definition = unscored[name]
            interpretation = 'Not automatically scored — N/A.'
        label_json = json.dumps(by_id[label_id], ensure_ascii=False, indent=2)
        pieces.append(
            f'<details class="metric-example" id="metric-{escape(name)}"' + (' open' if index == 0 else '') + '>'
            f'<summary>{escape(title)}</summary><p><code>{escape(name)}</code></p>'
            f'<p>{escape(definition)}</p><p class="muted">{escape(interpretation)}</p>'
            f'<p><b>How this label is checked:</b> {escape(example)}</p>'
            '<p><b>Actual label record (JSON)</b> — shared across metrics where applicable; values follow the order of columns.</p>'
            f'<pre><code class="language-json">{escape(label_json)}</code></pre></details>')
    pieces.append('</section><div id="evaluation-content"></div>')
    return ''.join(pieces)
