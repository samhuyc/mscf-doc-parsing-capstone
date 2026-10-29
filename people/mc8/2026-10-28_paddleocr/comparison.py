"""Baseline parity without changing Sam's scoring or returned metric values."""
import math


def metric_parity(actual,expected):
    """Counts/pooled scores exact; only float-summed document means allow roundoff.

    Python 3.12 changed sum(float) to a more accurate algorithm. The Intel
    Paddle environment uses Python 3.10. This tolerates representational noise
    in equal_document_mean only, never different numerators or denominators.
    """
    if actual.keys()!=expected.keys():
        return False
    for name,reference in expected.items():
        value=actual[name]
        if value.keys()!=reference.keys():
            return False
        for key,wanted in reference.items():
            got=value[key]
            if key=='equal_document_mean' and isinstance(wanted,float) and isinstance(got,float):
                if not math.isclose(got,wanted,rel_tol=0,abs_tol=1e-14):
                    return False
            elif got!=wanted:
                return False
    return True


def baseline_parity(result,baseline,parsers):
    checks={p:metric_parity(result['aggregate'][p],baseline['aggregate'][p]) for p in parsers}
    expected_docs=[d for d in baseline['documents'] if d['parser'] in parsers]
    actual_docs=[d for d in result['documents'] if d['parser'] in parsers]
    if actual_docs!=expected_docs:
        raise AssertionError('Per-document historical metrics changed')
    if not all(checks.values()):
        raise AssertionError('Historical metric counts or scores changed: '+str(checks))
    return checks
