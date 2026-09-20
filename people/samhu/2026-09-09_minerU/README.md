# MinerU experiment — September 9, 2026 meeting

PDF-to-Markdown comparison prepared for the September 9 meeting; original runs
completed on September 8, 2026. Two MinerU backends were tested on a scanned UK
annual report and a text-based US quarterly filing.

## Finding

The vision-language model (VLM) backend worked better for financial tables in
these documents, preserving row labels and amounts that the OCR/layout backend
sometimes merged or misread. Both backends produced Markdown for both complete
PDFs. This small experiment does not establish accuracy on other documents.
See the [unaltered table excerpts](example.md) for one comparison.

## How the model was used

- **`pipeline`:** local layout detection, OCR and table extraction, using embedded
  PDF text where available.
- **`vlm-engine`:** a local vision-language model,
  `opendatalab/MinerU2.5-Pro-2605-1.2B`. Its weights were downloaded from Hugging
  Face and inference ran on an Apple M1 Pro (16 GB memory) through MLX.

Hugging Face was the model download source. No Hugging Face hosted inference,
OpenAI API, paid inference service or API key was used. MinerU's CLI starts a
temporary local API server to coordinate parsing; that server runs on the same
machine. The VLM reads page images as part of MinerU extraction; it was not an
extra chatbot pass to rewrite the OCR output. Formula recognition and VLM
image descriptions were disabled; table extraction was enabled.

## Use

Run these commands from this experiment folder. The tested setup was macOS on
Apple silicon, Python 3.12 and MinerU 3.4.5.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Parse a public HTTPS PDF with the local VLM:

```bash
python parse_url.py \
  'https://find-and-update.company-information.service.gov.uk/company/01415057/filing-history/MzA4MTc5NTUwNGFkaXF6a2N4/document?format=pdf&download=0' \
  --name uk --backend vlm-engine
```

Use `--backend pipeline` to run the OCR/layout version. Replace the URL and name
to parse another PDF. For a short run, add `--start-page 8 --end-page 8`;
page numbers are 1-based physical PDF pages and the end is inclusive. Without
page arguments, the whole document is processed. Run the two backends sequentially.

The first run downloads model weights and needs internet access and several GB
of disk space. Models are cached for reuse. Other operating systems were not
tested; the non-macOS VLM setup may require a supported GPU/inference engine.
For CPU OCR/layout parsing, prefix the command with `MINERU_DEVICE_MODE=cpu`.

Each run creates `outputs/<name>_<timestamp>/` containing the downloaded PDF,
MinerU results under `parsed/`, `mineru.log` and a `run.json` record of the source,
hash, selected pages and result. The command prints the Markdown path after
checking page coverage. Keep generated Markdown beside its images; tables use
embedded HTML. Generated outputs, model caches and environments are ignored by Git.

## Documents tested

| Document | Full PDF | Sample physical pages |
|---|---:|---|
| [Lamray Holdings Limited, 2012 annual report](https://find-and-update.company-information.service.gov.uk/company/01415057/filing-history/MzA4MTc5NTUwNGFkaXF6a2N4/document?format=pdf&download=0) — scanned | 23 pages | 4, 8, 9, 16 |
| [Apple Inc., quarter ended June 27, 2026, Form 10-Q](https://d18rn0p25nwr6d.cloudfront.net/CIK-0000320193/e0dac020-713e-47ce-809a-f58dd78dfa91.pdf) — text-based | 32 pages | 4, 6, 10, 24 |

The saved comparison comes from the four-page UK sample. The usage example
processes the full PDF unless a page range is specified.
