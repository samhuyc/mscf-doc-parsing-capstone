#!/usr/bin/env python3
"""Download and verify the pinned official TAT-QA development split."""

from __future__ import annotations

import argparse
import hashlib
import shutil
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
COMMIT = "644770eb2a66dddc24b92303bd2acbad84cd2b9f"
EXPECTED_SHA256 = "8da095a819af6db3c14877c6df2d4d29960e41d1a63dd1fa853507bd2a616af5"
URL = (
    "https://raw.githubusercontent.com/NExTplusplus/TAT-QA/"
    f"{COMMIT}/dataset_raw/tatqa_dataset_dev.json"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--destination",
        type=Path,
        default=ROOT / "data" / "tatqa" / "raw" / "tatqa_dataset_dev.json",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    destination = args.destination
    if destination.exists() and not args.force:
        actual = sha256(destination)
        if actual == EXPECTED_SHA256:
            print(f"Already present and verified: {destination}")
            return
        raise RuntimeError(
            f"Refusing to replace {destination}: SHA-256 is {actual}, expected {EXPECTED_SHA256}. "
            "Use --force to replace it."
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")
    try:
        with urllib.request.urlopen(URL) as response, partial.open("wb") as target:
            shutil.copyfileobj(response, target)
        actual = sha256(partial)
        if actual != EXPECTED_SHA256:
            raise RuntimeError(f"Downloaded SHA-256 is {actual}, expected {EXPECTED_SHA256}")
        partial.replace(destination)
    finally:
        partial.unlink(missing_ok=True)
    print(f"Downloaded and verified: {destination}")


if __name__ == "__main__":
    main()
