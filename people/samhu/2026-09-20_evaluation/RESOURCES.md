# Resources and compatibility review — 2026-09-20

Scope follows `Parsing_Barclays_CMU.pdf` and `project_roadmap.pdf` in the project master folder. The mentor-provided paper is **MultiFinBen**; “FINN” is not used here as an additional dataset name. This inventory distinguishes documentation review from actual execution.

## Datasets and evaluation inspirations

| Resource | Existing labels / relevance | Decision and evidence |
|---|---|---|
| [MultiFinBen paper](https://arxiv.org/html/2506.14028v3), [EnglishOCR dataset](https://huggingface.co/datasets/TheFinAI/MultiFinBen-EnglishOCR) | Financial OCR page images with aligned text/HTML; released English split has 7,961 rows | Surveyed, not run. Useful expansion source, but inspect image/label alignment before treating all references as expert-verified gold. The dataset card identifies matching issues. |
| [FinCriticalED dataset](https://huggingface.co/datasets/TheFinAI/FinCriticalED), [paper](https://arxiv.org/abs/2511.14998), [evaluation code](https://github.com/The-FinAI/FinCriticalED) | Financial page images and expert critical-field markup: numbers, dates, units, reporting entities, concepts | Downloaded and run. Current CSV has 848 images; 859 annotation files include pages absent from that CSV. Join by ID, never file count or row position. Source HTML uses layout tables, so use critical spans/context here and explicit OmniDocBench table gold for structure. |
| [OmniDocBench dataset](https://huggingface.co/datasets/opendatalab/OmniDocBench), [code](https://github.com/opendatalab/OmniDocBench) | Page images plus layout, reading order, text and HTML table labels | Downloaded annotations and ran an 8-page coverage sample. The pinned release has 1,651 page images and no native PDFs. `research_report` is mostly Chinese and is not a reliable financial-only filter; visual inspection found an electronics datasheet among the English entries. |
| [FinCriticalED evaluation implementation](https://github.com/The-FinAI/FinCriticalED) | Finance-aware factual evaluation and context-sensitive comparison | Inspiration for prioritizing critical fields. Its semantic/LLM judging is not reproduced by the deterministic span/context diagnostics here. |
| [OmniDocBench table metrics](https://github.com/opendatalab/OmniDocBench/blob/f133a71e9e91c3621c7ce8994200a7b394a06eb3/src/metrics/table_metric.py) | Table tree similarity and structural evaluation | Inspiration for separate structure/content scores. This prototype uses its own smaller tree representation and matching; it does not report official TEDS or official OmniDocBench aggregate results. |

Pinned data revisions: OmniDocBench `aa1ee96d106dbe53d0ae59474d75c6e6d9b53fec`; FinCriticalED `2ac95f3dc2f0b55caf35f3d942bb5d32945f7c3e`. The tracked `pilot_selection.json` and `fin_selection.json` record selected IDs and checksums. A post-run visual check found malformed rendering in FinCriticalED image 367; screen image/label usability before a larger evaluation. Keep gated data local and follow each dataset's access/license terms when sharing artifacts.

## Can models meet Markdown + HTML tables?

“Feasible” means the documented input/output path can feed an adapter. It does not mean every model reliably preserves merged cells, or that all integrations are implemented. Only the two MinerU backends and PyMuPDF were executed; other rows are documentation review.

| Model / tool | Practical path to the common format | Status / qualification |
|---|---|---|
| [OpenAI vision models](https://developers.openai.com/api/docs/guides/images-vision) | Send a page image and request Markdown prose + HTML tables; import text response | Feasible by prompting; quality and adherence untested here. No API calls made. |
| [Anthropic Claude](https://platform.claude.com/docs/en/build-with-claude/pdf-support) | PDF/image input with the same transcription contract | Feasible by prompting; quality and adherence untested here. No API calls made. |
| [MinerU](https://opendatalab.github.io/MinerU/reference/output_files/) | Native Markdown, HTML tables and structured intermediate JSON | **Executed:** MinerU 3.4.5 pipeline and `vlm-engine`. Retain native artifacts and convert deterministically. |
| [Docling](https://github.com/docling-project/docling) | Structured document exports to Markdown/HTML/JSON | Feasible via document/table exporters; export settings and table spans must be checked in an integration test. |
| [PaddleOCR-VL](https://www.paddleocr.ai/main/en/version3.x/pipeline_usage/PaddleOCR-VL.html) | Pipeline provides Markdown export and HTML table export | Feasible through exports; use trained pipeline behavior, not an arbitrary schema prompt. |
| [DeepSeek-OCR-2](https://github.com/deepseek-ai/DeepSeek-OCR-2) | Document-to-Markdown prompt with grounding output | Feasible text/container path; retain grounding and verify table serialization. Arbitrary HTML-schema adherence untested. |
| [Marker](https://github.com/datalab-to/marker) | Markdown/HTML/JSON/chunk outputs; table conversion available | Feasible native export route; raw JSON also carries useful structural metadata. |
| [PyMuPDF4LLM](https://pymupdf.readthedocs.io/en/latest/pymupdf4llm/api.html) | Markdown/pipe-table output, page chunks and configurable OCR | Pipe tables convert to HTML. Conversion cannot recover merged cells absent in the source output. Not the same as the plain PyMuPDF control. |
| [pdfplumber](https://github.com/jsvine/pdfplumber) | Serialize extracted text and table cell arrays | Feasible deterministic adapter; built-in extraction is not OCR. Do not infer merged cells from missing entries. |
| [GLM-OCR](https://huggingface.co/zai-org/GLM-OCR), [pipeline](https://github.com/zai-org/GLM-OCR) | Task-specific text/table recognition plus pipeline export | Feasible via documented pipeline; avoid assuming this small model supports every generalist prompt. Table schema needs an integration test. |
| [NVIDIA Nemotron Parse v1.1](https://huggingface.co/nvidia/NVIDIA-Nemotron-Parse-v1.1) | Default text is Markdown, tables are LaTeX, with location/type markers | **Partial:** text can enter the harness; LaTeX-to-HTML table adapter is not implemented. Currently flagged, not silently flattened. |
| [Gemma 4 vision](https://ai.google.dev/gemma/docs/capabilities/vision) | Image OCR/transcription via prompting | Plausible generalist route documented for vision; output adherence and exact variant need a pilot. |
| [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-ocr.html) | Native text extraction; separate Tesseract-based OCR possible | **Executed without OCR:** native PDF smoke test and image-PDF negative control. Mentor baseline name/configuration remains to be confirmed. |

## Later workflow choices

Keep native page/block IDs, bounding boxes, headings and table spans when a parser provides them. Evaluate chunking as a later transformation: page chunks, heading-based chunks and table-preserving chunks should all point back to source pages. Test hierarchy/retrieval/template filling using existing suitable labels before claiming that a parser can reliably populate free-cash-flow fields across a whole filing. Neither OCR accuracy nor a valid HTML table alone establishes that downstream capability.
