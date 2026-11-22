"""Shared summaries of scored rows; no model imports or execution."""
from collections import Counter
import statistics
from common import config


def summarize_engines(pairs, include_forecasts=False, engines=None):
    summary={}
    for engine in engines if engines is not None else config()['engines']:
        rows=[r for r in pairs if r['engine']==engine];valid=[r for r in rows if r['fact_f1'] is not None]
        recall=[r['financial_value_recall'] for r in rows if r['financial_value_recall'] is not None]
        summary[engine]=dict(planned=len(rows),statuses=dict(Counter(r['inference_status'] for r in rows)),
                            eligible_financial_tables=len(valid),fact_f1=statistics.mean(r['fact_f1'] for r in valid) if valid else None,
                            financial_value_recall=statistics.mean(recall) if recall else None,
                            flagged_measurements=sum(bool(r['measurement_flags']) for r in rows))
        forecasts=[r for r in valid if 'expected_f1' in r]
        if include_forecasts and forecasts:
            from calibration_round2 import metrics
            summary[engine]['forecast']=metrics([dict(table_id=r['table_id'],issuer=r['issuer'],truth=r['fact_f1'],
                prediction=r['expected_f1'],baseline=r['baseline'],selected_feature=r['selected_feature'],review=r['review']) for r in forecasts])
    return summary
