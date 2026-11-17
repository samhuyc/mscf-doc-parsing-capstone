# Native confidence on financial tables

**Working prototype; reliable accuracy prediction is not established.**

- Six models, **109 shared crops / 763 outputs**; a final test holds out 11 companies.
- Native token probabilities stay separate from fitted accuracy estimates. Wrong row/column associations lose credit.
- Two final-test scoring issues are flagged. All original results and human reviews are preserved.

[Open local panel](http://127.0.0.1:8768) · [Results](results/native_prototype/SUMMARY.md) · [Methods and commands](prototype/METHODS.md)

**Next:** audit the flagged references and header rules before expanding calibration. Do not use native confidence to auto-approve financial tables.
