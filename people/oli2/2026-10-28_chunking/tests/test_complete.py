"""Early budget validation without loading source exports or writing results."""
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from complete import build


class BuildBudgetTests(unittest.TestCase):
    def test_nonpositive_budgets_fail_before_loading_inputs(self):
        for name in ('max_tokens', 'context_budget'):
            for value in (0, -1):
                with self.subTest(name=name, value=value), tempfile.TemporaryDirectory() as temp:
                    output = Path(temp) / 'results'
                    with patch('complete.load_document', side_effect=AssertionError('inputs loaded')) as load:
                        with self.assertRaisesRegex(ValueError, f'{name} must be positive'):
                            build(output, **{name: value})
                        load.assert_not_called()
                    self.assertFalse(output.exists())

    def test_positive_budgets_reach_existing_input_validation(self):
        # Do not introduce a new minimum: later stages retain their own checks.
        for budgets in ({}, {'max_tokens': 1}, {'context_budget': 128}):
            with self.subTest(budgets=budgets), tempfile.TemporaryDirectory() as temp:
                output = Path(temp) / 'results'
                with patch('complete.load_document', side_effect=RuntimeError('input validation reached')):
                    with self.assertRaisesRegex(RuntimeError, 'input validation reached'):
                        build(output, **budgets)
                self.assertFalse(output.exists())


if __name__ == '__main__':
    unittest.main()
