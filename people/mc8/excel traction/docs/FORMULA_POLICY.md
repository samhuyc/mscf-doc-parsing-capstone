# Formula and cached-value policy

The parser loads each workbook twice with `openpyxl`:

1. `data_only=False` preserves formulas exactly as stored in the file.
2. `data_only=True` exposes the last result cached by the application that
   calculated and saved the workbook.

For a formula cell, `value` and `formula` contain the formula text (including
the leading `=`), while `cached_value` contains the unformatted cached result.
`cached_value_status` is `present` or `missing`. For every other cell,
`cached_value` is null and the status is `not_formula`.

This project never evaluates formulas in Python and never substitutes a guessed
result. A missing cache remains null. A stale cache cannot be detected reliably
from the workbook alone, so consumers must treat cached values as source data,
not as freshly calculated truth.

“Displayed value” means the raw cached value in this workstream. The parser
also retains `number_format`, but it does not render currency symbols,
parentheses, percentages, dates, decimal places, or colors. Rendering is a
consumer responsibility. This avoids locale-dependent text and keeps numeric
values machine-readable.

One limitation follows from the public `openpyxl` interface: a null value in a
`data_only=True` formula cell is treated as a missing cache. It is not possible
to distinguish that case from a legitimately calculated blank without reading
lower-level OOXML details, which are intentionally outside the parsing path.
