"""Full-page diagnostic against source PDF text layers, never OCR consensus.

Unreviewed weak references: reading order, hidden text and serialization affect CER.
Scanned pages without text are explicitly excluded, never treated as empty truth.
"""
import argparse
from pathlib import Path

import pymupdf
from rapidfuzz.distance import Levenshtein

from core import ROOT, SPONSOR, read, sha, sources, write
from evaluate import norm, association


def page_metrics(reference, prediction):
    expected, actual = norm(reference), norm(prediction)
    if not expected:
        raise ValueError('An empty text layer is not ground truth')
    errors = Levenshtein.distance(expected, actual)
    return {'reference_characters': len(expected), 'output_characters': len(actual),
            'edit_errors': errors, 'cer': errors/len(expected),
            'character_accuracy_proxy': max(0, 1-errors/len(expected)),
            'length_ratio': len(actual)/len(expected)}


def build_references(output):
    refs, excluded = [], []
    for source in sources():
        path = SPONSOR/'inputs'/(source['id']+'.pdf')
        if sha(path) != source['sha256']:
            raise ValueError('Source PDF changed')
        with pymupdf.open(path) as pdf:
            for i, page in enumerate(pdf):
                text = page.get_text('text', sort=True)
                row = {'document':source['id'], 'page':i+1, 'source_sha256':source['sha256'],
                       'reference_kind':'embedded_pdf_text_unreviewed',
                       'human_verified':False}
                if norm(text):
                    refs.append({**row, 'text':text})
                else:
                    excluded.append({**row, 'reason':'No embedded PDF text; requires transcription'})
    write(output/'page_references.json', {'references':refs, 'excluded':excluded,
        'extraction':'PyMuPDF get_text(text, sort=True); all nonempty source pages',
        'pymupdf_version':pymupdf.__version__,
        'limitations':'Unreviewed PDF text layers, not gold ground truth. Sorting can differ from reading order.'})
    return refs, excluded


def evaluate_pages(runs, output):
    all_refs, excluded = build_references(output)
    # The deadline run may be partial. Compare identical available pages across
    # engines, without filling missing scores from the previous instrumentation.
    refs=[ref for ref in all_refs if all(
        (run/ref['document']/f'page_{ref["page"]:03}.json').exists() and
        read(run/ref['document']/f'page_{ref["page"]:03}.json')['status']=='success'
        for run in runs)]
    rows, summaries = [], {}
    for run in runs:
        engine = read(run/'settings.json')['engine']
        document_confidence={d['document']:d['confidence'] for d in read(run/'documents.json')}
        for ref in refs:
            page = read(run/ref['document']/f'page_{ref["page"]:03}.json')
            if page['source_sha256'] != ref['source_sha256']:
                raise ValueError('Reference/output PDF mismatch')
            prediction = page.get('text','') if page['status']=='success' else ''
            rows.append({'engine':engine, 'document':ref['document'], 'page':ref['page'],
                         'status':page['status'], 'truncated':page.get('truncated',False),
                         'confidence':page.get('confidence',{}),
                         **page_metrics(ref['text'],prediction)})
        engine_rows = [r for r in rows if r['engine']==engine]
        metric_names=('mean','character_weighted_mean','geometric_mean','p10','fraction_below_0_90')
        def correlations(items):
            return {m:association([r['confidence'].get(m) for r in items],
                                  [r['character_accuracy_proxy'] for r in items]) for m in metric_names}
        docs=[]
        for doc in dict.fromkeys(r['document'] for r in refs):
            items=[r for r in engine_rows if r['document']==doc]
            if len(items)!=sum(r['document']==doc for r in all_refs):
                continue  # A partial document is not an end-to-end document score.
            n=sum(r['reference_characters'] for r in items)
            docs.append({'document':doc, 'pages':len(items),
                         'confidence':document_confidence[doc],
                         'reference_characters':n,
                         'cer':sum(r['edit_errors'] for r in items)/n,
                         'character_accuracy_proxy':max(0,1-sum(r['edit_errors'] for r in items)/n),
                         'within_document_page_correlations':correlations(items)})
        summaries[engine]={'pages':len(engine_rows), 'documents':docs,
                           'document_correlations':correlations(docs),
                           'page_correlations':correlations(engine_rows),
                           'micro_cer':sum(r['edit_errors'] for r in engine_rows)/sum(r['reference_characters'] for r in engine_rows)}
    result={'reference_pages':len(all_refs), 'evaluated_reference_pages':len(refs),
            'unrun_reference_pages':len(all_refs)-len(refs),'excluded_pages':len(excluded),
            'reference_documents':len({r['document'] for r in refs}),
            'reference_characters':sum(len(norm(r['text'])) for r in refs),
            'rows':rows, 'engines':summaries,
            'accuracy_definition':'max(0, 1 - full-page normalized character edit distance / reference length)',
            'limitations':['Unreviewed embedded text is a weak reference, not verified ground truth.',
                           'Full-page comparison penalizes omissions and repetition, but also reading-order and markup differences.',
                           'Available pages cluster within documents and issuers; they are not independent documents.',
                           'The partial rerun prioritizes existing references and an observed failure; this is a diagnostic sample, not a random or held-out benchmark.',
                           'Scanned documents lack text layers and are absent from this comparison.',
                           'No calibrated correctness probabilities or held-out generalization claims.']}
    write(output/'page_evaluation.json',result)
    print({k:result[k] for k in ('reference_pages','excluded_pages','reference_documents','reference_characters')})
    for name, engine in summaries.items():
        print(name,{m:stats['spearman'] for m,stats in engine['page_correlations'].items()})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runs',nargs='+',type=Path)
    parser.add_argument('--output',type=Path,default=ROOT/'results/v2')
    args=parser.parse_args()
    evaluate_pages(args.runs,args.output)
