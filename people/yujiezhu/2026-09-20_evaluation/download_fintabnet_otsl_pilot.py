"""Download a small FinTabNet_OTSL test pilot from Hugging Face."""

from __future__ import annotations

import argparse
import hashlib
import json
import ssl
import urllib.parse
import urllib.request
from pathlib import Path


DATASET = "docling-project/FinTabNet_OTSL"
API = "https://datasets-server.huggingface.co/rows"
SSL_CONTEXT = ssl.create_default_context(cafile="/etc/ssl/cert.pem")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch_rows(count: int) -> list[dict]:
    query = urllib.parse.urlencode(
        {"dataset": DATASET, "config": "default", "split": "test", "offset": 0, "length": count}
    )
    with urllib.request.urlopen(f"{API}?{query}", context=SSL_CONTEXT) as response:
        payload = json.load(response)
    return [item["row"] for item in payload["rows"]]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=25)
    parser.add_argument("--output-dir", type=Path, default=Path("data/fintabnet_otsl_pilot"))
    args = parser.parse_args()
    if args.count < 1:
        parser.error("--count must be at least 1")

    args.output_dir.mkdir(parents=True, exist_ok=True)
    image_dir = args.output_dir / "images"
    image_dir.mkdir(exist_ok=True)
    rows = fetch_rows(args.count)[: args.count]
    manifest_path = args.output_dir / "manifest.jsonl"

    with manifest_path.open("w", encoding="utf-8") as manifest:
        for index, row in enumerate(rows):
            image_path = image_dir / f"{index:04d}.jpg"
            request = urllib.request.Request(row["image"]["src"])
            with urllib.request.urlopen(request, context=SSL_CONTEXT) as response:
                image_path.write_bytes(response.read())
            record = {
                "sample_id": f"fintabnet-otsl-test-{index:04d}",
                "dataset": DATASET,
                "split": row["split"],
                "filename": row["filename"],
                "imgid": row["imgid"],
                "image_path": str(image_path),
                "image_sha256": sha256(image_path),
                "html": row["html"],
                "html_restored": row["html_restored"],
                "cells": row["cells"],
                "rows": row["rows"],
                "cols": row["cols"],
            }
            manifest.write(json.dumps(record, ensure_ascii=True) + "\n")

    print(f"Downloaded {len(rows)} test samples to {args.output_dir}")
    print(f"Manifest: {manifest_path}")


if __name__ == "__main__":
    main()
