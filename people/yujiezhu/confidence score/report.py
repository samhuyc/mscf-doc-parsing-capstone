"""Write a readable pilot report from actual persisted run and scoring records."""
import argparse
from pathlib import Path

from prepare import ROOT, read_json, sha256, write_json


def percentage(value, already_percent=False):
    if value is None:
        return '—'
    return f'{value if already_percent else value * 100:.2f}%'


def main(run_name):
    folder = ROOT / 'results' / run_name
    report = read_json(folder / 'results.json')
    manifest = {r['local_id']: r for r in read_json(ROOT / 'manifest.json')}
    rows = report['documents']
    success = sum(r['parser_status'] == 'success' for r in rows)
    finished = all(r['parser_status'] in ('success', 'failed', 'timeout', 'empty', 'partial', 'interrupted') for r in rows)
    lines = ['# MinerU CPU subset pilot', '',
             f"Status: {'finished' if finished else 'in progress'}. MinerU parsed {success}/{len(rows)} complete documents.", '',
             'This experiment evaluates **MinerU 2.1.11 pipeline CPU + explicit-labels-tables-v1**, '
             'using the official metric functions on a selected subset. It is not a full benchmark '
             'submission, a score for MinerU alone, or a calibrated confidence model.', '',
             'The local extractor uses only explicit labels and HTML table headers. It omits '
             'unsupported or ambiguous fields, does not infer missing values, and supplies no '
             'page/box citations. Its incomplete schema coverage is a material limitation.', '',
             '## Documents and scores', '',
             '| ID | Pages | Parser | Extractor | Value F1 | Row precision | Row recall | Leaf accuracy | Parser seconds |',
             '| --- | ---: | --- | --- | ---: | ---: | ---: | ---: | ---: |']
    for row in rows:
        metrics = row['metrics'] or {}
        lines.append(f"| {row['local_id']} | {row['pages']} | {row['parser_status']} | {row['extraction_status']} | "
                     f"{percentage(metrics.get('extract_unified_value_f1'))} | "
                     f"{percentage(metrics.get('precision'))} | {percentage(metrics.get('recall'))} | "
                     f"{percentage(metrics.get('leaf_accuracy'), True)} | {row['parser_seconds'] or '—'} |")
    lines += ['', 'ExtractBench reports value F1; LongExtractionBench reports row precision/recall and '
              'leaf accuracy. Dashes indicate unavailable/inapplicable metrics.', '', '## Aggregate interpretation', '']
    for dataset, summary in report['summary'].items():
        means = summary['equal_document_mean']
        values = (f"value F1 {percentage(means.get('extract_unified_value_f1'))}" if dataset == 'extractbench'
                  else f"row precision {percentage(means.get('precision'))}, row recall {percentage(means.get('recall'))}, "
                       f"leaf accuracy {percentage(means.get('leaf_accuracy'), True)}")
        lines.append(f"- **{dataset}:** {summary['scored']}/{summary['selected']} scored; {values}. "
                     f"Schema-valid outputs: {summary['schema_valid']}/{summary['selected']}. "
                     f"{summary['averaging_rule']}.")
    lines += ['', 'A low extraction score can reflect an unsupported schema mapping even when the text is '
              'present in MinerU output. Inspect raw outputs before attributing errors to MinerU. '
              'Grounding scores are zero where applicable because this adapter supplies no citations.', '',
              '## Inspect the artifacts', '',
              '| ID and source task | Original PDF | MinerU Markdown | Predicted JSON |',
              '| --- | --- | --- | --- |']
    diagnostics = []
    for row in rows:
        record = manifest[row['local_id']]
        run_folder = ROOT / 'runs' / run_name / row['local_id']
        parser_path = run_folder / 'run.json'
        parser = read_json(parser_path) if parser_path.exists() else {}
        markdown = parser.get('markdown')
        md_link = f"[Markdown](../../{markdown})" if markdown else '—'
        prediction = f"[JSON](../../runs/{run_name}/{row['local_id']}/prediction.json)" if (run_folder / 'prediction.json').exists() else '—'
        lines.append(f"| {row['local_id']}: `{row['id']}` | [PDF](../../{record['files']['pdf']['path']}) | {md_link} | {prediction} |")
        if markdown:
            text = (ROOT / markdown).read_text()
            diagnostics.append({'local_id': row['local_id'], 'parsed_pages': parser['parsed_pages'],
                                'markdown_characters': len(text), 'html_tables': text.lower().count('<table'),
                                'interpretation': 'Output inventory, not correctness metrics'})
    write_json(folder / 'parser_inventory.json', diagnostics)
    lines += ['', '## Reproducibility and limitations', '',
              '- PDFs, schemas, and reference files are hashed in `manifest.json`; revisions are pinned in `pilot_config.json`.',
              '- Run metadata, logs, raw artifacts, predictions, and extraction evidence are retained in `runs/` locally.',
              '- Model/package versions and adapter source hash are recorded; the adapter was frozen before official scoring.',
              '- Hardware: Intel Core i5-8257U, 8 GB RAM. MinerU uses CPU, four threads, batches of four pages, '
              'tables enabled, formula recognition disabled, and `ch_lite` OCR.',
              '- The English-specific OCR configuration could not load its retired model files. '
              '`mineru_cpu_v1` is an unsuccessful setup attempt; this report uses the separately recorded rerun.',
              '- A 30-minute parser limit applies per document. Timing includes CLI startup; the smoke run warmed the model cache.',
              '- No model API or LLM was used. Nested arrays, contextual field interpretation, and implicit unit scaling are unsupported by the schema adapter.',
              '- Sampling was purposive and small. Scores do not establish a population ranking or a confidence probability.',
              '- LongExtractionBench leaf accuracy is conditional on matched rows and must be read with row recall and completion.', '',
              '[Detailed results](results.json) · [CSV](summary.csv) · [Parser inventory](parser_inventory.json) · '
              '[Source-page spot checks](../../spot_checks.md)', '']
    (folder / 'SUMMARY.md').write_text('\n'.join(lines))
    print(folder / 'SUMMARY.md')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run', default='mineru_cpu_v2')
    args = parser.parse_args()
    if Path(args.run).name != args.run:
        parser.error('Use a simple run name')
    main(args.run)
