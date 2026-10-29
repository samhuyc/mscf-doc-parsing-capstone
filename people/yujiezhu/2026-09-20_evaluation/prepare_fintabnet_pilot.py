"""Prepare a small, deterministic FinTabNet test manifest.

This script does not download the benchmark or run a parser. It validates the
official FinTabNet JSONL layout and writes selected annotation records so a
parser adapter can consume a fixed pilot sample.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


EXPECTED_PREFIX = "FinTabNet_1.0.0"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_records(path: Path) -> list[dict]:
    records = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON at {path}:{line_number}: {exc}") from exc
            required = {"filename", "html", "split"}
            missing = required.difference(record)
            if missing:
                raise ValueError(f"Missing {sorted(missing)} at {path}:{line_number}")
            records.append(record)
    return records


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_dir", type=Path, help="FinTabNet root containing pdf/ and JSONL files")
    parser.add_argument("--count", type=int, default=25, help="Number of test records to include")
    parser.add_argument("--output", type=Path, default=Path("data/fintabnet_test_manifest.jsonl"))
    args = parser.parse_args()

    if args.count < 1:
        parser.error("--count must be at least 1")

    data_dir = args.data_dir.expanduser().resolve()
    annotation_path = data_dir / f"{EXPECTED_PREFIX}_cell_test.jsonl"
    detection_path = data_dir / f"{EXPECTED_PREFIX}_table_test.jsonl"
    pdf_dir = data_dir / "pdf"

    missing = [str(path) for path in (annotation_path, detection_path, pdf_dir) if not path.exists()]
    if missing:
        raise SystemExit(
            "FinTabNet layout is incomplete. Missing:\n  " + "\n  ".join(missing)
        )

    records = load_records(annotation_path)
    selected = records[: args.count]
    if len(selected) < args.count:
        raise SystemExit(f"Requested {args.count} records, but only found {len(selected)}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as handle:
        for index, record in enumerate(selected):
            filename = record["filename"]
            pdf_path = pdf_dir / filename
            handle.write(
                json.dumps(
                    {
                        "sample_id": f"fintabnet-test-{index:04d}",
                        "split": record["split"],
                        "filename": filename,
                        "pdf_path": str(pdf_path),
                        "pdf_exists": pdf_path.exists(),
                        "pdf_sha256": sha256_file(pdf_path) if pdf_path.is_file() else None,
                        "table_id": record.get("table_id"),
                        "reference": record,
                    },
                    ensure_ascii=True,
                )
                + "\n"
            )

    print(f"Wrote {len(selected)} records to {args.output}")
    print(f"Annotation SHA-256: {sha256_file(annotation_path)}")
    print(f"PDFs found: {sum((pdf_dir / record['filename']).is_file() for record in selected)}/{len(selected)}")


if __name__ == "__main__":
    main()
