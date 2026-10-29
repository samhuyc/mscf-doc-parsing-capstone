"""Run the installed Marker parser on the FinTabNet image pilot."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def image_to_pdf(image: Path, pdf: Path) -> None:
    from PIL import Image

    with Image.open(image) as source:
        source.convert("RGB").save(pdf, "PDF", resolution=150.0)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pilot-dir", type=Path, default=Path("data/fintabnet_otsl_pilot"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/marker_fintabnet"))
    parser.add_argument("--count", type=int, default=None)
    args = parser.parse_args()

    manifest_path = args.pilot_dir / "manifest.jsonl"
    records = [json.loads(line) for line in manifest_path.read_text().splitlines() if line.strip()]
    if args.count is not None:
        records = records[: args.count]
    args.output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="fintabnet-marker-") as temporary:
        temp_dir = Path(temporary)
        for index, record in enumerate(records):
            sample_id = record["sample_id"]
            pdf_path = temp_dir / f"{sample_id}.pdf"
            sample_output = args.output_dir / sample_id
            sample_output.mkdir(exist_ok=True)
            image_to_pdf(Path(record["image_path"]), pdf_path)
            command = ["marker_single", str(pdf_path), str(sample_output), "--max_pages", "1"]
            print(f"[{index + 1}/{len(records)}] {sample_id}", flush=True)
            subprocess.run(command, check=True)

    print(f"Marker output written to {args.output_dir}")


if __name__ == "__main__":
    main()
