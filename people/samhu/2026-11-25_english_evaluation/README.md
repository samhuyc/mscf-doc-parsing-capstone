# English financial statement parsing evaluation

A frozen, preliminary comparison prepared for the Barclays capstone evaluation section.

| Start here | Use |
|---|---|
| [Presenter guide](Presenter_Guide.pdf) | Five pages for Eunice. Read the table and page examples on pages 2–3, use page 4 as the exhibit and page 5 for the speaking notes. |
| [Technical handoff for an assistant](AI_Handoff.md) | Upload this document to an assistant on its own. It contains the underlying numbers, definitions, attribution, commands and exact source paths. |
| [One-page results](Results_One_Page.pdf) | Landscape 16:9 PDF. It is the same exhibit as page 4 of the guide. |

Run `python3 reproduce.py` in this directory to check the numbers and prediction hashes with Python’s standard library. `python3 reproduce.py --json` also prints every matched ID and each cohort’s unrounded summary.

[Input manifest](evidence/inputs.csv) · [Per-input scores](evidence/observations.csv) · [Standardized outcomes](evidence/metric_outcomes.csv) · [Row-level filing checks](evidence/filing_checks.csv) · [Snapshot and model versions](evidence/release.json).

The original sources and additional replay commands are in the technical handoff. `freeze_evidence.py` is the exporter for the original run workspace. Shared outputs can be read, checked or re-scored directly from this folder.
