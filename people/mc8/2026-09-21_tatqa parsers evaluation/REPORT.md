# PyMuPDF4LLM vs PyMuPDF on TAT-QA

## Result

Both parsers completed all 278 English TAT-QA development contexts. On this
controlled benchmark, plain PyMuPDF was more accurate on text and tables and
about 4.1 times faster than PyMuPDF4LLM.

| Parser | Completed | Text accuracy | Reading order | Table cell F1 | Table shape | Exact table | Extractive answer retention | Arithmetic operand retention | Mean sec/context |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| PyMuPDF4LLM 0.2.9 | 278/278 | 96.860% | 98.629% | 92.899% | 43.885% | 3.597% | 97.277% | 92.589% | 0.892 |
| PyMuPDF 1.28.2 | 278/278 | 99.361% | 99.662% | 99.680% | 94.964% | 93.885% | 99.455% | 92.589% | 0.217 |

Lower is better only for word error rate (not shown above): PyMuPDF4LLM was
3.140%, while PyMuPDF was 0.639%. All other quality metrics are higher-is-better.
The machine-readable values are in `results/metrics_by_parser.csv`.

## Interpretation

PyMuPDF's direct text extraction was the better fit for these digitally created,
single-column financial contexts. Its table finder nearly reproduced the
rendered tables exactly: 99.680% cell F1 and 93.885% exact table match.

PyMuPDF4LLM retained most content but its Markdown-oriented layout processing
occasionally reordered fragments and normalized empty or merged table headers.
That explains why its answer evidence remained strong (97.277%) while exact
table structure was much lower (3.597%). The low exact-table score should not
be read as near-total table failure; its cell recall was 97.252% and cell F1 was
92.899%.

Arithmetic operand retention tied at 92.589%. This metric checks whether each
number in the official arithmetic derivation remains available in extracted
content. It does not attempt the arithmetic or score the final QA answer.

## Benchmark composition

- 278 hybrid contexts rendered to 298 PDF pages
- 1,356 paragraphs and 8,773 non-empty table cells
- 1,668 questions: 701 span, 217 multi-span, 718 arithmetic, and 32 count
- 918 extractive questions used for answer-retention scoring
- 1,889 arithmetic derivation operands used for operand-retention scoring
- all content is English and comes from the official TAT-QA development split

## Metric definitions

- **Text accuracy:** `max(0, 1 - WER)`, where WER is micro-aggregated token
  Levenshtein distance divided by the number of reference tokens.
- **Reading order:** order-preserving token matches from sequence matching,
  divided by reference tokens.
- **Table cell precision/recall/F1:** multiset matching of normalized non-empty
  cells. The parser receives no credit for duplicated or invented cells.
- **Table shape:** fraction of contexts with a detected table having the same
  row and maximum-column count as the reference.
- **Exact table:** fraction whose normalized two-dimensional cell matrix exactly
  matches the TAT-QA reference.
- **Extractive answer retention:** fraction of span and multi-span questions for
  which every annotated answer span occurs in parser output.
- **Arithmetic operand retention:** fraction of normalized numeric operands from
  official arithmetic derivations found in parser output.
- **Runtime:** wall-clock parser time only; rendering and evaluation are
  excluded. Means were 0.892 seconds for PyMuPDF4LLM and 0.217 seconds for
  PyMuPDF; medians were 0.649 and 0.167 seconds, respectively.

Normalization is case-insensitive, collapses whitespace, applies Unicode NFKC
normalization (including ligatures), and retains financially meaningful symbols
and punctuation. Per-context values and run status are retained in
`results/metrics_by_context.csv`.

## Scope and caveat

TAT-QA distributes tables, paragraphs, questions, answers, and derivations as
JSON, not the original report PDFs. The PDFs in this experiment are deterministic
renderings of those official contexts. The experiment therefore isolates text,
reading-order, and table reconstruction behavior on clean digital documents.
It does not test OCR or visual noise.

These are not official TAT-QA QA scores. An official QA evaluation would require
a model that consumes the parser output and predicts answer plus scale. This
benchmark instead measures whether the evidence needed by such a model survives
parsing.

## Runtime environment

- Intel macOS host
- PyMuPDF 1.28.2
- PyMuPDF4LLM 0.2.9
- 278/278 successful contexts for both parsers
- PyMuPDF4LLM total parser time: 247.91 seconds
- PyMuPDF total parser time: 60.23 seconds
