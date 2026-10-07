# Mapping to the existing PDF benchmark JSON

The earlier PDF benchmark emits one object per TAT-QA context:

| PDF field | Excel analogue | Decision |
| --- | --- | --- |
| `parser` | `parser.name` plus library metadata | Retained and expanded. |
| `context_uid` | `source.sha256` and `source.filename` | Workbooks have no TAT-QA context ID. |
| `raw` | Full `workbook.sheets[].cells[]` representation | Cell records are the loss-minimizing source representation. |
| `text` | No canonical equivalent yet | Flattening a workbook would discard sheet and coordinate structure. |
| `tables` | `workbook.sheets[].tables[]` | Tables are sheet-scoped and refer back to canonical cell coordinates. |

The Excel schema does not force nested workbooks into the PDF experiment's
flat payload. The stable bridge is:

- parser identity at the envelope level;
- source identity and provenance;
- tables as detected views over a loss-minimizing source representation; and
- every extracted value traceable to a source location (`sheet` plus cell
  `coordinate`).

A future shared benchmark can wrap both formats in a common document envelope,
but renaming fields in the completed PDF experiment is unnecessary for this
v1. The Excel `table.range` and `cell_coordinates` fields provide the same
audit role as the PDF table matrices while retaining stronger provenance.
