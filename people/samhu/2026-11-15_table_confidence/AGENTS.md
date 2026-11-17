# Working rules

- Keep replies and README extremely concise. Put reproducibility details in `prototype/` and linked methods.
- Canonical checkout is local under `/Users/hu/ML Capstone repo/`; never run weights from Desktop/iCloud.
- Preserve human reviews. Assistant checks are not human approvals.
- Raw native probability is not correctness probability. Keep fitted estimates separate.
- Hold out whole issuers. Freeze calibration before inspecting fresh-test outputs. Never silently drop failed/missing cases.
- Keep one heavy recognizer running at a time. Model files stay below 4 GB; runtime memory may exceed this.
- Score wrong row/column associations as errors. Audit representation differences against source crops.
- Read `prototype/progress.json` and `prototype/protocol.json` before resuming. No automatic publication.

# Current checkpoint

- Read `results/native_prototype/SUMMARY.md` first; full evidence is in `findings.json`.
- Current operational entry: `prototype/predict_crop.py` / `score_round2.py`. Results panel: port 8768; original editable review: 8766.
- Round-one files are immutable. `metric_v2/` is disclosed post-inspection sensitivity; `round2/` contains the later sealed test.
- All 109 crops have now been inspected or evaluated. None can be called a new untouched test in future work.
- Two final-test measurement issues remain flagged, not silently corrected. Native confidence did not establish reliable quality prediction.
- Future improvements need audited references and a new independent test. Do not optimize against the existing final test and still call it held out.
