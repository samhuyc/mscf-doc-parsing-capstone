"""Summarize the public earlier stages without inventing unavailable scores."""
import csv
import json
from common import ROOT, REFERENCE, PARSER


def main():
    early=ROOT/'early/source_manifest.json'
    if early.is_file():
        sources=json.loads(early.read_text())
        lines=['# Original two-PDF trial: PaddleOCR output','','Same URLs and complete physical page counts as Sam’s September 9 trial. No quantitative gold evaluation was supplied for this stage.']
        excerpts=['# Documented sample pages, unchanged PaddleOCR predictions']
        for source in sources:
            work=ROOT/'early/results'/source['id']/PARSER
            if not (work/'pages.json').is_file():
                lines.append(f'\n{source["id"]}: no completed export.')
                continue
            pages=json.loads((work/'pages.json').read_text())['pages']
            record=json.loads((work/'run.json').read_text())
            lines.append(f'\n- {source["title"]}: {len(pages)} pages, {record["nonempty_pages"]} with text, {record["elapsed_seconds"]:.1f}s. [Full output](results/{source["id"]}/{PARSER}/document.md).')
            for number in source['sample_pages']:
                prefix=f'results/{source["id"]}/{PARSER}/images/'
                markdown=pages[number-1]['markdown'].replace('](images/',']('+prefix).replace('src="images/','src="'+prefix)
                excerpts+=['',f'## {source["title"]} · physical PDF page {number}','',markdown]
        (ROOT/'early/REPORT.md').write_text('\n'.join(lines)+'\n')
        (ROOT/'early/example.md').write_text('\n'.join(excerpts)+'\n')
    baseline=REFERENCE/'2026-09-20_evaluation/results'
    lines=['# September dataset pilot: same fixed samples','','Sam’s custom page-macro diagnostics, not official leaderboard scores. Higher is better for all metrics in this stage. FinCriticalED remains unavailable without an approved download.']
    rows=[]
    for dataset in ['omni','fin']:
        path=ROOT/'benchmarks/results'/f'{dataset}_paddleocr.json'
        if not path.is_file():
            continue
        actual=json.loads(path.read_text())
        key=next(iter(actual['summary']))
        group={name:json.loads((baseline/f'{dataset}_{backend}.json').read_text())['summary'][key]
               for name,backend in [('MinerU OCR','pipeline'),('MinerU VLM','vlm')]}
        group['PaddleOCR PP-StructureV3']=actual['summary'][key]
        lines+=['',f'## {key}','','| Metric | MinerU OCR | MinerU VLM | PaddleOCR PP-StructureV3 |','|---|---:|---:|---:|']
        for metric in group['PaddleOCR PP-StructureV3']['metrics']:
            values=[g['metrics'][metric]['mean'] for g in group.values()]
            lines.append('| '+metric+' | '+' | '.join(f'{v:.4f}' if v is not None else 'N/A' for v in values)+' |')
            rows.extend(dict(dataset=key,parser=name,metric=metric,**data['metrics'][metric]) for name,data in group.items())
        lines+=['',f'PaddleOCR produced {group["PaddleOCR PP-StructureV3"]["successful"]}/{group["PaddleOCR PP-StructureV3"]["pages"]} successful page exports. Failures remain in the denominator.']
    (ROOT/'benchmarks/REPORT.md').write_text('\n'.join(lines)+'\n')
    if rows:
        with (ROOT/'benchmarks/results/comparison.csv').open('w',newline='') as out:
            writer=csv.DictWriter(out,fieldnames=['dataset','parser','metric','mean','scored_pages'])
            writer.writeheader();writer.writerows(rows)


if __name__=='__main__':
    main()
