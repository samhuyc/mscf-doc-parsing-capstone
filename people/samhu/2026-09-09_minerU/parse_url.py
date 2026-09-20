"""Download a public PDF and parse it locally with either MinerU backend."""
import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from pypdf import PdfReader

ROOT = Path(__file__).resolve().parent


def download(url, destination, max_bytes=100 * 1024 * 1024):
    if not url.startswith("https://"):
        raise ValueError("Only HTTPS source links are accepted")
    tmp = destination.with_suffix(".part")
    try:
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "MSCF-MinerU-Experiment/1.0"})
                with urllib.request.urlopen(req, timeout=60) as response, tmp.open("wb") as out:
                    size = 0
                    while chunk := response.read(1024 * 1024):
                        size += len(chunk)
                        if size > max_bytes:
                            raise ValueError("Download exceeded 100 MiB")
                        out.write(chunk)
                break
            except (OSError, TimeoutError):
                if attempt == 2:
                    raise
                time.sleep(2 ** attempt)
        if not tmp.read_bytes().startswith(b"%PDF-"):
            raise ValueError("Response is not a PDF (possibly an HTML error/login page)")
        PdfReader(tmp)  # Reject malformed files before replacing an existing source.
        tmp.replace(destination)
    finally:
        tmp.unlink(missing_ok=True)


def environment():
    env = os.environ.copy()
    for key, relative in {
        "HF_HOME": "cache/huggingface",
        "XDG_CACHE_HOME": "cache/xdg",
        "TORCH_HOME": "cache/torch",
        "MPLCONFIGDIR": "cache/matplotlib",
        "TMPDIR": "tmp",
        "MINERU_API_OUTPUT_ROOT": "tmp/api_outputs",
    }.items():
        path = Path(env.get(key, ROOT / relative))
        path.mkdir(parents=True, exist_ok=True)
        env[key] = str(path)
    config = ROOT / "cache/mineru.json"
    config.parent.mkdir(parents=True, exist_ok=True)
    if not config.exists():
        config.write_text(json.dumps({"config_version": "1.3.2", "model-source": "huggingface"}))
    env.update({
        "MINERU_TOOLS_CONFIG_JSON": str(config),
        "MINERU_MODEL_SOURCE": "huggingface",
        "MINERU_PROCESSING_WINDOW_SIZE": "4",
        "MINERU_API_MAX_CONCURRENT_REQUESTS": "1",
        "PYTORCH_ENABLE_MPS_FALLBACK": "1",
        "TOKENIZERS_PARALLELISM": "false",
    })
    return env


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url")
    parser.add_argument("--name", default="document")
    parser.add_argument("--backend", choices=["pipeline", "vlm-engine"], default="pipeline")
    parser.add_argument("--start-page", type=int, default=1, help="1-based physical PDF page")
    parser.add_argument("--end-page", type=int, help="1-based inclusive; default last page")
    parser.add_argument("--timeout", type=int, default=7200)
    args = parser.parse_args()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,60}", args.name):
        parser.error("Use 1-60 letters, digits, underscores or hyphens for --name")
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    run = ROOT / "outputs" / f"{args.name}_{stamp}"
    run.mkdir(parents=True)
    meta_path = run / "run.json"
    meta = {"url": args.url, "backend": args.backend, "started_at_utc": stamp, "status": "started"}
    meta_path.write_text(json.dumps(meta, indent=2))
    started = time.perf_counter()
    try:
        pdf = run / f"{args.name}.pdf"
        download(args.url, pdf)
        reader = PdfReader(pdf)
        end = args.end_page if args.end_page is not None else len(reader.pages)
        if not 1 <= args.start_page <= end <= len(reader.pages):
            raise ValueError(f"Page range must be within 1..{len(reader.pages)}")
        meta.update({"pdf_sha256": hashlib.sha256(pdf.read_bytes()).hexdigest(), "pdf_pages": len(reader.pages), "selected_source_pages": list(range(args.start_page, end + 1))})
        cmd = [str(Path(sys.executable).parent / "mineru"), "-p", str(pdf), "-o", str(run / "parsed"),
               "-b", args.backend, "-m", "auto", "-s", str(args.start_page - 1), "-e", str(end - 1),
               "-f", "false", "-t", "true"]
        if args.backend == "vlm-engine":
            cmd += ["--image-analysis", "false"]
        meta["command"] = cmd
        with (run / "mineru.log").open("w") as log:
            proc = subprocess.Popen(cmd, cwd=ROOT, env=environment(), stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            try:
                code = proc.wait(timeout=args.timeout)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait()
                raise TimeoutError("Parsing exceeded timeout; local process group stopped")
        meta["return_code"] = code
        markdown = list((run / "parsed").rglob("*.md"))
        middle = list((run / "parsed").rglob("*_middle.json"))
        if code or not markdown or not middle:
            raise RuntimeError("MinerU failed or did not emit expected outputs; see mineru.log")
        parsed_pages = sum(len(json.loads(p.read_text())["pdf_info"]) for p in middle)
        if parsed_pages != end - args.start_page + 1:
            raise RuntimeError(f"Expected {end - args.start_page + 1} parsed pages, got {parsed_pages}")
        meta.update({"status": "success", "parsed_pages": parsed_pages, "markdown": [str(p.relative_to(run)) for p in markdown]})
        print("Markdown:", *markdown, sep="\n")
    except Exception as exc:
        meta.update({"status": "failed", "error": str(exc)})
        raise
    finally:
        meta["elapsed_seconds"] = round(time.perf_counter() - started, 3)
        meta_path.write_text(json.dumps(meta, indent=2) + "\n")
        print(f"Run record: {meta_path}")


if __name__ == "__main__":
    main()
