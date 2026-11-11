"""Inventory additional local labels without silently promoting them to training truth."""
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from model_pipeline import ROOT, digest, number, write

PEOPLE=ROOT.parents[2]
FIN=PEOPLE/'yujiezhu/2026-09-20_evaluation'
SPONSOR=PEOPLE/'samhu/2026-10-05_pilot_benchmark'
sys.path.insert(0,str(FIN))
from score_fintabnet_pilot import reference_table, parse_tables


def key(value):
    return re.sub(r'\s+','',value).casefold()


def numeric(value):
    n=number(value)
    return (n[0],n[2]) if n is not None else None


def main():
    labels=[json.loads(line) for line in (SPONSOR/'labels.jsonl').read_text().splitlines()]
    tables=[r for r in labels if r['kind']=='table']
    manifest=FIN/'data/fintabnet_otsl_pilot/manifest.jsonl'
    references=[json.loads(line) for line in manifest.read_text().splitlines()]
    per_table=[]; candidates=[]
    for i,ref in enumerate(references):
        path=next((FIN/'content/fintabnet_pilot/mineru_output').glob(f'fintabnet-{i:04}/**/*.md'))
        parsed=parse_tables(path.read_text())
        if not parsed:
            per_table.append(dict(index=i,filename=ref['filename'],status='no_parsed_table',candidate_pairs=0))
            continue
        gold,pred=defaultdict(list),defaultdict(list)
        for row in reference_table(ref):
            if row and re.search('[a-zA-Z]',row[0]):
                gold[key(row[0])].append(row)
        for row in parsed[0]:
            if row and re.search('[a-zA-Z]',row[0]):
                pred[key(row[0])].append(row)
        pairs=0
        for label,rows in pred.items():
            originals=gold.get(label,[])
            if len(originals)!=len(rows):
                continue
            for row,original in zip(rows,originals):
                p=[v for v in row[1:] if numeric(v) is not None]
                g=[v for v in original[1:] if numeric(v) is not None]
                if len(p)!=len(g):
                    continue
                for col,(actual,expected) in enumerate(zip(p,g)):
                    pairs+=1
                    if numeric(actual)!=numeric(expected):
                        candidates.append(dict(table_index=i,filename=ref['filename'],row=row[0],numeric_ordinal=col,
                                               extracted=actual,reference=expected,independently_verified=False,
                                               source_image=str(FIN/f'data/fintabnet_otsl_pilot/images/{i:04}.jpg'),
                                               source_image_sha256=digest(FIN/f'data/fintabnet_otsl_pilot/images/{i:04}.jpg'),
                                               note=('Source image shows the comparison values in the Vertical row; this is an association discrepancy, not established numeric transcription failure.' if i==19 else
                                                     'Assistant source-image inspection supports comma-to-decimal transcription discrepancy. Independent verification still pending.')))
        per_table.append(dict(index=i,filename=ref['filename'],status='candidate_alignment_only',candidate_pairs=pairs,
                              parser_output_sha256=digest(path)))
    result=dict(
        sponsor=dict(label_records=len(labels),table_records=len(tables),
                     reference_cells=sum(len(row['values']) for t in tables for row in t['rows']),
                     independently_verified_records=sum(r.get('review_status') in ('human_verified','adjudicated') for r in labels),
                     labels_sha256=digest(SPONSOR/'labels.jsonl'),
                     note='These draft references overlap the demo and are not 133 additional independent observations.'),
        fintabnet=dict(tables=len(references),companies=sorted({r['filename'].split('.')[0] for r in references}),
                       report_years=sorted({r['filename'].split('.')[1] for r in references}),
                       candidate_pairs=sum(r['candidate_pairs'] for r in per_table),
                       mismatch_candidates=candidates,table_inventory=per_table,manifest_sha256=digest(manifest),
                       note='Candidate pairing uses exact normalized row labels and numeric-order matching only when counts agree. It is not trusted spatial/cell alignment and is not admitted to model training. All tables are HAL, a different input/configuration domain from the sponsor PDFs. Matching candidate values do not prove numeric accuracy or correct association.'),
        training_data_added=0,
        next_action='Review source-linked candidates and labels, obtain additional representative documents with actual numeric errors, and freeze document-family splits before fitting.')
    (ROOT/'model_results').mkdir(exist_ok=True)
    write(ROOT/'model_results/additional_data_audit.json',result)
    print(json.dumps(dict(sponsor=result['sponsor'],fintabnet_candidate_pairs=result['fintabnet']['candidate_pairs'],
                         mismatch_candidates=len(candidates),training_data_added=0),indent=2))


if __name__=='__main__':
    main()
