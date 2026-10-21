import gc
import os
import re
import tempfile
import time
import traceback
from datetime import datetime
from difflib import SequenceMatcher

from bs4 import BeautifulSoup
from datasets import load_dataset
import pandas as pd
from PIL import Image, ImageOps, ImageEnhance, ImageFilter


DATASET_NAME = "nhhsag12/pubtabnet-with-html"
NUM_SAMPLES = 50
UPSCALE_FACTOR = 2.0
OUTPUT_CSV = "pubtabnet_mineru_teds_diagnostics.csv"
OUTPUT_TXT = "pubtabnet_mineru_teds_full_diagnostics.txt"
DEBUG_DIR = "pubtabnet_mineru_debug_teds"
SAVE_DEBUG_FILES = True


class DiagnosticLog:
    def __init__(self, path):
        self.file = open(path, "w", encoding="utf-8")

    def write(self, message=""):
        message = str(message)
        print(message)
        self.file.write(message + "\n")
        self.file.flush()

    def close(self):
        self.file.close()


LOG = None


def log(message=""):
    (LOG.write if LOG is not None else print)(message)


def markdown_to_html_table(markdown):
    """Extract a table from MinerU Markdown/HTML; convert pipe tables when needed."""
    if not markdown:
        return "<table></table>"

    # MinerU can emit HTML tables directly inside its Markdown output.
    soup = BeautifulSoup(markdown, "html.parser")
    table = soup.find("table")
    if table is not None:
        return str(table)

    table_lines = []
    inside_table = False
    for line in markdown.splitlines():
        stripped = line.strip()
        if "|" in stripped:
            inside_table = True
            table_lines.append(stripped)
        elif inside_table:
            break
    if not table_lines:
        return "<table></table>"

    rows = []
    for line in table_lines:
        cells = [x.strip() for x in line.strip("|").split("|")]
        if cells and all(re.fullmatch(r":?-+:?", cell) for cell in cells):
            continue
        rows.append(cells)
    if not rows:
        return "<table></table>"

    html = ["<table>"]
    for row_idx, cells in enumerate(rows):
        html.append("<tr>")
        for cell in cells:
            tag = "th" if row_idx == 0 else "td"
            html.append(f"<{tag}>{cell}</{tag}>")
        html.append("</tr>")
    html.append("</table>")
    return "".join(html)


def upscale_image(image, factor=UPSCALE_FACTOR):
    """Upscale using Lanczos; mild contrast/sharpness enhancement is intentionally omitted."""
    image = image.convert("RGB")
    if factor <= 1:
        return image.copy()
    new_size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def image_to_pdf_path(image):
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        pdf_path = f.name
    image.convert("RGB").save(pdf_path, format="PDF", resolution=72.0)
    return pdf_path


def save_debug_text(filename, label, content):
    if not SAVE_DEBUG_FILES:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    path = os.path.join(DEBUG_DIR, f"{safe_name}.{label}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")
    log(f"Saved debug text: {path}")


def predict_mineru(image, filename):
    """Run MinerU on an upscaled table image and return Markdown plus parsed table HTML."""
    from mineru.parser import parse

    image_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
            image_path = f.name
            image.convert("RGB").save(f, format="PNG")

        # MinerU's standard tier performs document/image understanding and table recognition.
        result = parse(image_path, tier="standard")
        markdown = result.markdown() if callable(getattr(result, "markdown", None)) else str(result)
        pred_html = markdown_to_html_table(markdown)
        save_debug_text(filename, "mineru_raw_markdown", markdown)
        save_debug_text(filename, "mineru_predicted_html", pred_html)
        return markdown, pred_html
    finally:
        if image_path:
            try:
                os.remove(image_path)
            except OSError:
                pass
        gc.collect()


def normalize_html(html):
    if html is None:
        return "<table></table>"
    return str(html).strip()


def table_soup(html):
    soup = BeautifulSoup(normalize_html(html), "html.parser")
    table = soup.find("table")
    if table is None:
        return BeautifulSoup("<table></table>", "html.parser").table
    return table


def count_cells(html):
    return len(table_soup(html).find_all(["td", "th"]))


def extract_cell_text(html):
    table = table_soup(html)
    return " ".join(" ".join(cell.stripped_strings) for cell in table.find_all(["td", "th"]))


def edit_distance(a, b):
    """Levenshtein distance using a memory-efficient dynamic program."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(current[-1] + 1, previous[j] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def character_error_rate(pred_text, gt_text):
    pred = re.sub(r"\s+", " ", pred_text or "").strip()
    gt = re.sub(r"\s+", " ", gt_text or "").strip()
    if not gt:
        return 0.0 if not pred else 1.0
    return edit_distance(pred, gt) / len(gt)


# TEDS implementation: tree edit distance over table HTML.
# Install dependency with: pip install apted
class TableNode:
    def __init__(self, tag, children=None, content=""):
        self.tag = tag
        self.children = children or []
        self.content = content

    def get_children(self):
        return self.children


from apted import Config


class TEDSConfig(Config):
    def __init__(self, structure_only=False):
        super().__init__()
        self.structure_only = structure_only

    def rename(self, node1, node2):
        if node1.tag != node2.tag:
            return 1.0
        if node1.tag in ("td", "th") and not self.structure_only:
            a, b = node1.content, node2.content
            if not a and not b:
                return 0.0
            return edit_distance(a, b) / max(len(a), len(b), 1)
        return 0.0

    def children(self, node):
        return node.children

    def insert(self, node):
        return 1.0

    def delete(self, node):
        return 1.0


def html_to_tree(html, structure_only=False):
    table = table_soup(html)

    def build(element):
        children = [build(child) for child in element.find_all(recursive=False) if getattr(child, "name", None)]
        content = ""
        if element.name in ("td", "th") and not structure_only:
            content = re.sub(r"\s+", " ", element.get_text(" ", strip=True)).strip()
        return TableNode(element.name or "table", children, content)

    return build(table)


def teds_score(pred_html, gt_html, structure_only=False):
    from apted import APTED
    pred_tree = html_to_tree(pred_html, structure_only)
    gt_tree = html_to_tree(gt_html, structure_only)
    distance = APTED(pred_tree, gt_tree, TEDSConfig(structure_only=structure_only)).compute_edit_distance()
    node_count = max(count_tree_nodes(pred_tree), count_tree_nodes(gt_tree), 1)
    return max(0.0, 1.0 - distance / node_count)


def count_tree_nodes(node):
    return 1 + sum(count_tree_nodes(child) for child in node.children)


def diagnostic_summary(label, markdown, pred_html, gt_html):
    pred_cells, gt_cells = count_cells(pred_html), count_cells(gt_html)
    try:
        score = teds_score(pred_html, gt_html)
        struct_score = teds_score(pred_html, gt_html, structure_only=True)
    except Exception as exc:
        score = struct_score = float("nan")
        log(f"TEDS calculation failed: {type(exc).__name__}: {exc}")
    cer = character_error_rate(extract_cell_text(pred_html), extract_cell_text(gt_html))
    log(f"[{label}] Markdown character count: {len(markdown or '')}")
    log(f"[{label}] Predicted/GT cell counts: {pred_cells}/{gt_cells}")
    log(f"[{label}] TEDS: {score:.4f}")
    log(f"[{label}] TEDS-Struct: {struct_score:.4f}")
    log(f"[{label}] CER (cell text): {cer:.4f}")
    log(f"[{label}] Raw Markdown:\n{markdown!r}")
    log(f"[{label}] Predicted HTML:\n{pred_html}")
    return score, struct_score, cer


def run_benchmark(num_samples=NUM_SAMPLES):
    global LOG
    LOG = DiagnosticLog(OUTPUT_TXT)
    results, evaluated, skipped = [], 0, 0
    try:
        log("=" * 78)
        log("PubTabNet: MinerU OCR/Table Extraction Benchmark — TEDS + UPSCALING")
        log(f"Started: {datetime.now().isoformat(timespec='seconds')}")
        log(f"Dataset: {DATASET_NAME}")
        log(f"Target samples: {num_samples}; upscale factor: {UPSCALE_FACTOR}x")
        log("MinerU tier: standard")
        log(f"Full log: {os.path.abspath(OUTPUT_TXT)}")
        log("=" * 78)
        ds = load_dataset(DATASET_NAME, split="train", streaming=True)

        for sample in ds:
            if evaluated >= num_samples:
                break
            key, image, gt_html = sample.get("__key__"), sample.get("png"), sample.get("html")
            if key is None or not key.startswith("pubtabnet/train/") or image is None or gt_html is None or not isinstance(image, Image.Image):
                skipped += 1
                continue

            filename = key.split("/")[-1]
            if not filename.endswith(".png"):
                filename += ".png"
            original = image.convert("RGB")
            upscaled = upscale_image(original)
            gt_html = normalize_html(gt_html)
            log("\n" + "=" * 78)
            log(f"SAMPLE {evaluated + 1}/{num_samples}: {filename}")
            log(f"Original image size: {original.size}; upscaled size: {upscaled.size}")
            log(f"Ground-truth cells: {count_cells(gt_html)}")
            log(f"Ground-truth HTML:\n{gt_html}")

            row = {
                "filename": filename,
                "image_width": original.width,
                "image_height": original.height,
                "upscaled_width": upscaled.width,
                "upscaled_height": upscaled.height,
                "gt_cells": count_cells(gt_html),
            }
            started = time.perf_counter()
            try:
                log("\n--- MINERU: Upscaled image -> MinerU standard tier ---")
                markdown, pred_html = predict_mineru(upscaled, filename)
                elapsed = time.perf_counter() - started
                score, struct_score, cer = diagnostic_summary("MinerU", markdown, pred_html, gt_html)
                row.update({
                    "mineru_teds": score,
                    "mineru_teds_struct": struct_score,
                    "mineru_cer": cer,
                    "mineru_runtime_seconds": elapsed,
                    "mineru_predicted_cells": count_cells(pred_html),
                    "mineru_markdown_chars": len(markdown or ""),
                    "mineru_markdown": markdown or "",
                    "mineru_html": pred_html,
                })
            except Exception as exc:
                elapsed = time.perf_counter() - started
                error = f"{type(exc).__name__}: {exc}"
                log(f"MinerU FAILED: {error}\n{traceback.format_exc()}")
                row.update({
                    "mineru_teds": 0.0,
                    "mineru_teds_struct": 0.0,
                    "mineru_cer": 1.0,
                    "mineru_runtime_seconds": elapsed,
                    "mineru_predicted_cells": 0,
                    "mineru_markdown_chars": 0,
                    "mineru_error": error,
                })

            results.append(row)
            evaluated += 1
            original.close()
            upscaled.close()
            image.close()
            gc.collect()

        log("\n" + "=" * 78 + "\nFINAL RESULTS\n" + "=" * 78)
        log(f"Samples evaluated: {evaluated}; skipped: {skipped}")
        if results:
            df = pd.DataFrame(results)
            for metric in ("teds", "teds_struct", "cer", "runtime_seconds"):
                col = f"mineru_{metric}"
                if col in df:
                    log(f"Mean {col}: {df[col].mean():.4f}")
            df.to_csv(OUTPUT_CSV, index=False)
            log(f"CSV saved to: {os.path.abspath(OUTPUT_CSV)}")
        else:
            log("No samples evaluated. Check dataset keys/schema and split filtering.")
        log(f"Full diagnostics saved to: {os.path.abspath(OUTPUT_TXT)}")
        return pd.DataFrame(results)
    finally:
        LOG.close()
        LOG = None


if __name__ == "__main__":
    run_benchmark(NUM_SAMPLES)
