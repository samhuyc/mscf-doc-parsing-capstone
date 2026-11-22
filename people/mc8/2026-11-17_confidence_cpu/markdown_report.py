"""Render saved summaries as Markdown without running inference or scoring."""
import argparse
from datetime import datetime
import os
from pathlib import Path
from zoneinfo import ZoneInfo

from common import HERE, read, write


ENGINE_NAMES = {
    'tesseract': 'Tesseract', 'paddle': 'PP-OCRv5', 'mineru': 'MinerU (text)',
    'paddle_vl': 'PaddleOCR-VL-1.6', 'glm': 'GLM-OCR',
    'monkey': 'MonkeyOCR-pro-1.2B', 'mineru_table': 'MinerU (table)',
}


def number(value):
    return 'N/A' if value is None else f'{value:.4f}'


def percent(value):
    return 'N/A' if value is None else f'{100*value:.2f}%'


def interval(value):
    return 'N/A' if value is None else '[' + ', '.join(number(v) for v in value) + ']'


def table(headers, rows):
    return ['| ' + ' | '.join(headers) + ' |',
            '| ' + ' | '.join('---' for _ in headers) + ' |',
            *['| ' + ' | '.join(str(v) for v in row) + ' |' for row in rows]]


def engine_table(engines):
    lines = ['| Configuration | Scored tables | Success | Failed | Missing | Eligible F1 tables | Fact F1 | Number recall | Flagged |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for engine, row in engines.items():
        statuses = row.get('statuses', {})
        values = [ENGINE_NAMES.get(engine, engine), str(row['planned']),
                  str(statuses.get('success', 0)), str(statuses.get('failed', 0)),
                  str(statuses.get('missing', 0)), str(row['eligible_financial_tables']),
                  number(row['fact_f1']), percent(row['financial_value_recall']),
                  str(row['flagged_measurements'])]
        lines.append('| ' + ' | '.join(values) + ' |')
    return lines


def forecast_table(engines, details=None):
    if details is not None:
        return detailed_forecasts(details)
    rows = [(engine, row['forecast']) for engine, row in engines.items() if 'forecast' in row]
    if not rows:
        return []
    lines = ['## Held-out forecast quality', '',
             'These metrics use held-out test rows only. Forecasts estimate expected fact F1.', '',
             '| Configuration | Test rows | Issuers | MAE | Baseline MAE | MSE | Baseline MSE | MSE gain |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for engine, row in rows:
        values = [ENGINE_NAMES.get(engine, engine), str(row.get('n', 0)),
                  str(row.get('issuers', 0)), number(row.get('mae')),
                  number(row.get('baseline_mae')), number(row.get('mse')),
                  number(row.get('baseline_mse')), number(row.get('mse_gain'))]
        lines.append('| ' + ' | '.join(values) + ' |')
    return lines


def detailed_forecasts(details):
    from report_details import STRUCTURED
    rows = [(engine, r['prediction']) for engine, r in details['engines'].items()
            if engine in STRUCTURED]
    lines = ['## Held-out forecast quality', '',
             'Pending means calibration and held-out forecasts are not available for this prefix. '
             'Calibration freezes after all 1,600 development tables. No fit is performed to fill this report. '
             'Text-only configurations have no expected-F1 forecast.', '']
    lines += table(['Configuration', 'Test rows', 'Issuers', 'MAE', 'Baseline MAE', 'MSE',
                    'Baseline MSE', 'MSE gain', 'MSE gain 95% issuer CI', 'Selected feature (rows)'],
                   [[ENGINE_NAMES.get(e, e), p['n'], p['issuers'], number(p['mae']),
                     number(p['baseline_mae']), number(p['mse']), number(p['baseline_mse']),
                     number(p['mse_gain']), interval(p.get('mse_gain_issuer_bootstrap_95')),
                     ', '.join(f'{k} ({n})' for k, n in p['selection_counts'].items())]
                    if p else [ENGINE_NAMES.get(e, e), 0, 0, *(['Pending']*6), 'Pending']
                    for e, p in rows])
    lines += ['', 'MAE uses the 0–1 F1 scale; multiply by 100 for percentage points. '
              'Positive MSE gain means lower error than the development-mean baseline. '
              'These metrics use held-out test rows only.', '',
              '## Review policy on held-out forecasts', '',
              'The review cutoff is learned from development confidence. Errors mean F1 < 0.95; '
              'kept accuracy is mean F1. No acceptance threshold is selected from the current report prefix.', '']
    lines += table(['Configuration', 'Reviewed / total', 'Errors', 'Caught', 'Error capture',
                    'Kept', 'Kept coverage', 'Kept mean F1', 'All mean F1'],
                   [[ENGINE_NAMES.get(e, e), f"{p['triage']['reviewed']} / {p['triage']['total']}",
                     p['triage']['errors'], p['triage']['caught'], percent(p['triage']['error_capture']),
                     p['training_threshold_triage']['kept'], percent(p['training_threshold_triage']['coverage']),
                     number(p['training_threshold_triage']['kept_mean_accuracy']),
                     number(p['training_threshold_triage']['all_mean_accuracy'])]
                    if p else [ENGINE_NAMES.get(e, e), *(['Pending']*8)] for e, p in rows])
    return lines


def detail_tables(details):
    counts = details['counts']
    lines = ['## Cohort in this report', '',
             *table(['Metric', 'Count'], [[label, counts[key] if counts[key] is not None else 'N/A']
                 for label, key in [('Unique crops', 'unique_crops'), ('Scored outputs', 'outputs'),
                    ('Crops with financial reference facts', 'financial_crops'),
                    ('Crops without financial reference facts', 'no_financial_facts'),
                    ('Source reports', 'source_reports'), ('Issuers', 'issuers'),
                    ('Issuers with financial facts', 'financial_issuers'),
                    ('Held-out test crops', 'final_test_crops'), ('Held-out test issuers', 'final_test_issuers'),
                    ('Configurations', 'configurations'), ('Models', 'models')]]), '',
             'Source reports count distinct manifest document names. These are cropped table images. '
             'MinerU text/table share one model.', '',
             '## Additional accuracy, confidence and runtime metrics', '',
             *table(['Configuration', 'GriTS content F1', 'GriTS tables', 'Number recall tables',
                     'Native numeric coverage', 'Mean native numeric', 'Native range',
                     'Median recognition (s)', 'Timed outputs', 'Truncated'],
                    [[ENGINE_NAMES.get(e, e), number(r['mean_grits']), r['grits_tables'],
                      r['number_recall_tables'], f"{r['numeric_coverage']} / {r['n']}",
                      number(r['mean_native_numeric']), interval(r['native_range']),
                      number(r['median_recognition_seconds']), r['timed_outputs'], r['truncated']]
                     for e, r in details['engines'].items()]), '',
             'GriTS measures cell-content similarity and is averaged over its available saved scores. '
             'Its denominator can differ from financial fact F1. Native numeric coverage counts '
             'non-null native numeric confidence, including valid zero values; confidence is not correctness probability. '
             'Recognition times use saved per-output seconds within this prefix, including first-output setup, '
             'and exclude separate scoring/calibration. Sam’s pasted runtime medians instead pool all his cohorts.', '',
             '## Financial F1 outcome counts', '',
             *table(['Configuration', 'Eligible F1 tables', 'F1 < 0.95', 'Exact F1 tables'],
                    [[ENGINE_NAMES.get(e, e), r['eligible_f1_tables'], r['errors_below_95'], r['exact_tables']]
                     for e, r in details['engines'].items() if r['eligible_f1_tables']]), '',
             'Exact means F1 ≥ 1 − 1e−9 under the saved scorer; it does not certify the whole table.', '']
    for split in ('development', 'test'):
        rows = [(e, r['ranking_by_split'][split]) for e, r in details['engines'].items()
                if split in r['ranking_by_split']]
        if not rows:
            continue
        lines += [f'## Native numeric confidence ranking — {split}', '',
                  'Within-model association between native numeric confidence and financial fact F1. '
                  + ('These are descriptive development results, not held-out validation. '
                     if split == 'development' else 'These use held-out test rows only. ')
                  + 'Sam’s ranking definitions and 1,000 issuer-bootstrap resamples are reused. '
                  'Only rows with both confidence and F1 enter this table; missing confidence is excluded here, '
                  'while the accuracy table retains all eligible F1 rows. No confidence feature is selected here.', '',
                  *table(['Configuration', 'Rows', 'Issuers', 'Mean F1', 'Mean native', 'Native range',
                          'Spearman', 'Spearman 95% issuer CI', 'Error AUC (F1 < 0.95)',
                          'F1 < 0.95', 'Exact F1 tables'],
                         [[ENGINE_NAMES.get(e, e), r['n'], r.get('issuers', 0),
                           number(r.get('mean_accuracy')), number(r.get('mean_native')),
                           interval(r.get('native_range')), number(r.get('spearman')),
                           interval(r.get('spearman_issuer_bootstrap_95')),
                           number(r.get('error_auc_below_95')), r.get('errors_below_95', 0),
                           r.get('exact_tables', 0)] for e, r in rows]), '',
                  'Error AUC treats lower confidence as an error signal. N/A includes undefined correlation '
                  '(constant data), one-class AUC, or insufficient issuer clusters for a confidence interval.', '']
    lines += ['## Measurement flags and audit status', '',
              'References are public benchmark annotations; independent human audit is pending. '
              'Flagged cases remain included. This report does not claim Sam’s audit passes for these new outputs.', '']
    if details['measurement_flags']:
        lines += table(['Table', 'Saved measurement flags'],
                       [[tid, '; '.join(flags)] for tid, flags in details['measurement_flags'].items()])
    else:
        lines += ['No saved measurement flags in this prefix.']
    lines += ['', 'Post-inspection exclusion sensitivity: not computed; the original scoring denominator is retained.', '']
    return lines


def render_summary(summary, details=None):
    cumulative = 'completed_batches' in summary
    title = 'Cumulative confidence experiment results' if cumulative else f'{summary["split"].capitalize()} results'
    lines = ['# ' + title, '']
    if cumulative:
        lines += [f'**Tables completed:** {summary["completed_tables"]:,} / {summary["total_tables"]:,}  ',
                  f'**Batches completed:** {summary["completed_batches"]} / {summary["total_batches"]}  ',
                  f'**Scored outputs:** {summary["scored_outputs"]:,}', '']
    else:
        lines += [f'**Tables scored:** {summary["scored_tables"]:,} / {summary["total_split_tables"]:,}', '']
    if summary.get('updated_utc'):
        updated = datetime.fromisoformat(summary['updated_utc']).astimezone(ZoneInfo('America/New_York'))
        lines += ['Updated: ' + updated.strftime('%Y-%m-%d %H:%M:%S %Z') + ' (America/New_York).', '']
    lines += ['## Accuracy by configuration', '', *engine_table(summary['engines']), '',
              'Fact F1 measures associated financial facts on a 0–1 scale. Number recall measures the share '
              'of reference numbers recovered. Higher values are better for both. Text-only configurations '
              'have no fact F1; N/A is not zero.', '']
    for split, detail in summary.get('splits', {}).items():
        lines += [f'## {split.capitalize()}', '',
                  f'Tables scored: {detail["scored_tables"]:,} / {detail["total_split_tables"]:,}.', '',
                  *engine_table(detail['engines']), '']
    if details is not None:
        lines += detail_tables(details)
    forecasts = forecast_table(summary['engines'], details)
    if forecasts:
        lines += [*forecasts, '']
    lines += ['## Interpretation', '',
              '- Results include the scored prefix only; tables that have not run are excluded.',
              '- Failed or missing outputs within that prefix remain in the scoring denominator.',
              '- Development scores are descriptive. Held-out test results are reported separately.',
              '- Calibration freezes after all 1,600 development tables, before test inference.',
              '- Native confidence features are saved in the per-table `pairs.json` files.',
              '- Expected F1 and native confidence are not the probability that an entire table is correct.',
              '- References are public labels; human audit is pending. Flagged measurements stay visible.', '',
              'The matching JSON summary retains the original precision and forecast details. '
              'Additional metrics and source-score hashes are in the companion `*-metrics.json` file.', '']
    return '\n'.join(lines)


def write_markdown(path, summary):
    path = Path(path)
    run = path.parent.parent if path.parent.name in ('batch-results', 'development', 'test') else path.parent
    from report_details import collect_details
    details = collect_details(run, summary)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temp.write_text(render_summary(summary, details), encoding='utf-8')
    temp.replace(path)
    if details is not None:
        write(path.with_name(path.stem+'-metrics.json'), details)


def regenerate_reports(run):
    """Add Markdown alongside existing summaries, preserving every JSON file."""
    run = Path(run)
    sources = [run/'summary.json', run/'development/summary.json', run/'test/summary.json']
    sources += sorted(p for p in (run/'batch-results').glob('batch-*.json')
                      if p.stem.removeprefix('batch-').isdigit())
    written = []
    for source in sources:
        if source.exists():
            target = source.with_suffix('.md')
            write_markdown(target, read(source))
            written.append(target)
    return written


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run-dir', type=Path, default=HERE/'runs/cpu_v1')
    args = p.parse_args()
    for path in regenerate_reports(args.run_dir.resolve()):
        print('Saved', path)


if __name__ == '__main__':
    main()
