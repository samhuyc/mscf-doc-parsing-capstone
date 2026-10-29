# FinTabNet evaluation

## Does FinTabNet have its own dataset?

Yes. **FinTabNet is a standalone financial table dataset and benchmark**, not only an evaluation script or model. It was introduced for table structure recognition from financial reports. The dataset provides financial table images together with structured annotations that describe table cells and their relationships. Use the dataset's own train/validation/test split rather than mixing it with PubTables-1M or an unrelated PDF collection.

There are two names to keep separate:

- **FinTabNet**: the original financial table benchmark.
- **FinTabNet.c**: Microsoft's canonicalized version used by the Table Transformer project. The canonicalization aligns the table representation with the project's training and evaluation format. Microsoft's financial structure-recognition model is listed as trained on FinTabNet.c.

The dataset is therefore suitable for testing a parser's table structure output, but it is not automatically a complete end-to-end PDF parsing benchmark. A table-structure run normally evaluates table images and annotations. If we want to test PDF ingestion, we need to pair the benchmark annotations with the corresponding source documents or explicitly report that the experiment starts from rendered table/page images.

## What to test

For the first pilot, evaluate table structure recognition on a small held-out sample:

1. Select a fixed number of test examples from the official FinTabNet or FinTabNet.c test split.
2. Record the dataset source, revision, split, sample IDs, and local file hashes.
3. Run the parser without using the gold annotations as input.
4. Convert the parser output to a consistent table representation, preferably HTML or a cell grid with row/column spans.
5. Score both structure and content. Keep missing tables and malformed outputs in the denominator.
6. Save per-example results and manually inspect failures involving merged cells, blank cells, multi-level headers, and financial numbers.

Suggested primary metrics:

- **GriTS-topology** for cell/grid structure.
- **GriTS-location** when predicted cell bounding boxes are available.
- **GriTS-content** when cell text is available.
- Numeric exact-match or normalized numeric F1 as a supplementary financial-value check.

Do not compare these scores directly with a published leaderboard unless the preprocessing, dataset variant, split, output format, and metric implementation match exactly.

## Dataset and access notes

Do not commit the downloaded dataset or model weights. Store local copies under the repository's ignored data area, for example:

```text
data/raw/FinTabNet/
data/raw/FinTabNet.c/
```

Before downloading, record:

```text
source_url:
dataset_variant:
dataset_revision_or_commit:
split:
license_or_access_terms:
local_archive_sha256:
```

The repository currently has no FinTabNet files. This folder contains documentation only until the team agrees on the exact source and variant.

## Recommended next step

Use **FinTabNet.c** if the goal is to reproduce Microsoft's Table Transformer financial model evaluation. Use the original FinTabNet only if the experiment specifically needs the original benchmark representation. First download or obtain the approved dataset, verify its license and split files, then add a small manifest and a preparation script before running the parser.

The pilot preparation script is now available as [prepare_fintabnet_pilot.py](prepare_fintabnet_pilot.py). After obtaining the official source layout, run:

```bash
python prepare_fintabnet_pilot.py /path/to/FinTabNet --count 25 \
	--output data/fintabnet_test_manifest.jsonl
```

The script reads the test cell annotations, checks for the paired table annotations and `pdf/` directory, selects the first fixed records, and records local PDF hashes when the PDFs are present. It does not download data or run a parser yet. The next implementation step is an adapter for the parser being tested that consumes this manifest and emits one structured table result per sample.

For a small table-image pilot, [download_fintabnet_otsl_pilot.py](download_fintabnet_otsl_pilot.py) downloads directly from the public `docling-project/FinTabNet_OTSL` test split. This mirror contains the original HTML ground truth plus table images:

```bash
python3 download_fintabnet_otsl_pilot.py --count 25
```

The default output is `data/fintabnet_otsl_pilot/`, which is intentionally local pilot data and should not be committed. This tests table structure recognition from table images; it is not a native-PDF extraction test.

## Sources

- [Microsoft Table Transformer repository](https://github.com/microsoft/table-transformer) - identifies FinTabNet.c as a training dataset and provides the related preprocessing/evaluation code.
- [Aligning benchmark datasets for table structure recognition](https://arxiv.org/abs/2303.00716) - describes canonicalization and alignment of FinTabNet with other table benchmarks.
- [FinTabNet paper search and citation should be recorded here once the team's approved download/source is selected.] 
