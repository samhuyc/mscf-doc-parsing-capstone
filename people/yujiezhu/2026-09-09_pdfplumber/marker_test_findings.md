# Marker PDF Test Findings

## Test Setup

- **Document:** Apple Inc. Q3 2026 Form 10-Q
- **Input:** `data/10Q.pdf`
- **Command:** `marker_single data/10Q.pdf output/marker`
- **Operating system:** macOS
- **Python:** 3.9

## Result

Marker did not complete the conversion and produced no Markdown output.

The first run downloaded and loaded the Surya detection, layout, reading-order, and Texify models successfully. It then failed while opening the PDF through the `pdftext` dependency:

```text
TypeError: Invalid input type 'PdfDocument'
```

## Troubleshooting Attempted

The environment was tested with these dependency versions:

- `marker-pdf 0.2.6`
- `pdftext 0.3.10`
- `pypdfium2 4.30.0`
- `surya-ocr 0.4.5`

The error remained after changing `pypdfium2` from version 5.x to the Marker-compatible 4.x range and after trying the older allowed `pdftext` release.

## Interpretation

This is an environment or package-compatibility failure, not evidence that Marker cannot parse the Apple 10-Q. Marker loaded its models, but its PDF text extraction dependency received an already-open `PdfDocument` where it expected a path or bytes input.

A fair comparison should either:

1. Run Marker in the project’s recommended isolated environment or Docker image, or
2. Report Marker as unavailable in this local Python 3.9 environment and compare the successful `pdfplumber` results separately.

## Comparison Note

`pdfplumber` completed the same document successfully: 32 pages processed, 30 tables detected, and Markdown/JSON outputs generated. Marker has no comparable output from this local test, so accuracy and table quality should not be scored until the compatibility issue is resolved.
