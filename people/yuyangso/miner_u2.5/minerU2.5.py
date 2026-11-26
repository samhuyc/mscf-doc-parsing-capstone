import gc
import os
import re
import tempfile
import time
import traceback
from datetime import datetime

from bs4 import BeautifulSoup
from datasets import load_dataset
import pandas as pd
from PIL import Image


DATASET_NAME = "nhhsag12/pubtabnet-with-html"
NUM_SAMPLES = 50
UPSCALE_FACTOR = 2.0
OUTPUT_CSV = "pubtabnet_mineru_2_5_teds_diagnostics.csv"
OUTPUT_TXT = "pubtabnet_mineru_2_5_teds_full_diagnostics.txt"
DEBUG_DIR = "pubtabnet_mineru_2_5_debug_teds"
SAVE_DEBUG_FILES = True

SAVE_MINERU_OUTPUTS = True

MINERU_DEBUG_ROOT = "mineru_2_5_full_outputs"

SAVE_MIDDLE_JSON = True
SAVE_MODEL_JSON = True
SAVE_CONTENT_LIST_JSON = True


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
    """
    Extract all HTML tables from MinerU Markdown.
    Preserve rowspan, colspan and other HTML attributes.
    Fall back to pipe-table conversion when necessary.
    """
    if not markdown or not markdown.strip():
        return "<table></table>"

    soup = BeautifulSoup(markdown, "html.parser")
    tables = soup.find_all("table")

    if tables:
        return (
            "<html><body>"
            + "".join(str(table) for table in tables)
            + "</body></html>"
        )

    # Fallback: Markdown pipe tables
    table_lines = []

    for line in markdown.splitlines():
        stripped = line.strip()

        if "|" in stripped:
            table_lines.append(stripped)

    if not table_lines:
        return "<table></table>"

    rows = []

    for line in table_lines:
        cells = [
            cell.strip()
            for cell in line.strip("|").split("|")
        ]

        # Remove Markdown separator rows
        if all(
            re.fullmatch(r":?-+:?", cell)
            for cell in cells
        ):
            continue

        rows.append(cells)

    if not rows:
        return "<table></table>"

    html = ["<table>"]

    for row in rows:
        html.append("<tr>")

        for cell in row:
            html.append(
                f"<td>{cell}</td>"
            )

        html.append("</tr>")

    html.append("</table>")

    return "".join(html)


def upscale_image(image, factor=UPSCALE_FACTOR):
    """Upscale using Lanczos resampling."""
    image = image.convert("RGB")
    if factor <= 1:
        return image.copy()
    new_size = (max(1, round(image.width * factor)), max(1, round(image.height * factor)))
    return image.resize(new_size, Image.Resampling.LANCZOS)


def save_debug_text(filename, label, content):
    if not SAVE_DEBUG_FILES:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    safe_name = re.sub(r"[^A-Za-z0-9_.-]", "_", filename)
    path = os.path.join(DEBUG_DIR, f"{safe_name}.{label}.txt")
    with open(path, "w", encoding="utf-8") as f:
        f.write(content or "")
    log(f"Saved debug text: {path}")





def predict_mineru_2_5(image, filename):
    """
    MinerU 2.5.3 OCR pipeline.

    Preserves:
      - Markdown
      - middle.json
      - model.json
      - content_list.json
      - Original MinerU output directory
    """
    import shutil
    import json
    from pathlib import Path
    from mineru.cli.common import do_parse

    work_dir = tempfile.mkdtemp(prefix="mineru_2_5_")

    safe_filename = re.sub(
        r"[^A-Za-z0-9_.-]", "_", filename
    )

    pdf_filename = (
        os.path.splitext(safe_filename)[0] + ".pdf"
    )

    input_dir = os.path.join(work_dir, "input")
    output_dir = os.path.join(work_dir, "output")

    os.makedirs(input_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    pdf_path = os.path.join(input_dir, pdf_filename)

    try:
        image.convert("RGB").save(
            pdf_path,
            format="PDF",
            resolution=72.0
        )

        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()

        log(f"MinerU input: {pdf_path}")

        do_parse(
            output_dir=output_dir,
            pdf_file_names=[pdf_filename],
            pdf_bytes_list=[pdf_bytes],
            p_lang_list=["en"],
            backend="pipeline",
            parse_method="ocr",
            formula_enable=False,
            table_enable=True,
            f_draw_layout_bbox=False,
            f_draw_span_bbox=False,
            f_dump_md=True,
            f_dump_middle_json=True,
            f_dump_model_output=True,
            f_dump_orig_pdf=False,
            f_dump_content_list=True,
        )

        output_root = Path(output_dir)

        markdown_files = list(
            output_root.rglob("*.md")
        )

        if not markdown_files:
            raise RuntimeError(
                "MinerU produced no Markdown output."
            )

        expected_stem = Path(pdf_filename).stem

        matching = [
            p for p in markdown_files
            if p.stem == expected_stem
        ]

        selected_md = (
            matching[0] if matching
            else markdown_files[0]
        )

        markdown = selected_md.read_text(
            encoding="utf-8"
        )

        ocr_dir = selected_md.parent

        # Locate MinerU JSON outputs.
        json_files = list(ocr_dir.glob("*.json"))

        log("\nMinerU generated files:")

        for path in json_files:
            log(f"  {path.name}")

        # Preserve complete output.
        if SAVE_MINERU_OUTPUTS:
            os.makedirs(
                MINERU_DEBUG_ROOT,
                exist_ok=True
            )

            preserved_dir = os.path.join(
                MINERU_DEBUG_ROOT,
                Path(filename).stem
            )

            if os.path.exists(preserved_dir):
                shutil.rmtree(preserved_dir)

            shutil.copytree(
                output_root,
                preserved_dir
            )

            log(
                f"Preserved MinerU output: "
                f"{preserved_dir}"
            )

        # Load individual JSON files for diagnostics.
        json_diagnostics = {}

        for path in json_files:
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)

                json_diagnostics[path.name] = data

                log(
                    f"Loaded {path.name}: "
                    f"{type(data).__name__}"
                )

            except Exception as exc:
                log(
                    f"Could not load {path.name}: "
                    f"{exc}"
                )

        # Extract Markdown table.
        pred_html = markdown_to_html_table(markdown)

        save_debug_text(
            filename,
            "mineru_2_5_raw_markdown",
            markdown
        )

        save_debug_text(
            filename,
            "mineru_2_5_predicted_html",
            pred_html
        )

        return markdown, pred_html, json_diagnostics

    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
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



from collections import deque
from lxml import etree, html
from apted import APTED, Config


class TableNode:
    """PubTabNet-compatible HTML table tree."""

    def __init__(
        self,
        tag,
        colspan=None,
        rowspan=None,
        content=None,
        children=None,
    ):
        self.tag = tag
        self.colspan = colspan
        self.rowspan = rowspan
        self.content = content
        self.children = list(children or [])

    def get_children(self):
        return self.children


class PubTabNetTEDSConfig(Config):
    """Edit costs from the original IBM PubTabNet implementation."""

    @staticmethod
    def normalized_distance(a, b):
        if not a and not b:
            return 0.0

        return edit_distance(a, b) / max(len(a), len(b), 1)

    def __init__(self, structure_only=False):
        super().__init__()
        self.structure_only = structure_only

    def rename(self, node1, node2):

        # Different HTML tags.
        if node1.tag != node2.tag:
            return 1.0

        # Compare cell spans.
        if (
            node1.colspan != node2.colspan
            or node1.rowspan != node2.rowspan
        ):
            return 1.0

        # Compare cell text.
        if node1.tag == "td" and not self.structure_only:
            return self.normalized_distance(
                node1.content or [],
                node2.content or [],
            )

        return 0.0

    def children(self, node):
        return node.children

    def insert(self, node):
        return 1.0

    def delete(self, node):
        return 1.0


def pubtabnet_tokenize(node, tokens):
    """
    Reproduce the tokenization used by IBM PubTabNet.

    Cell content includes nested HTML tags and text.
    """

    tokens.append(f"<{node.tag}>")

    if node.text is not None:
        tokens.extend(list(node.text))

    for child in node:
        pubtabnet_tokenize(child, tokens)

    if node.tag != "unk":
        tokens.append(f"</{node.tag}>")

    if node.tag != "td" and node.tail is not None:
        tokens.extend(list(node.tail))


def parse_pubtabnet_html(table_html):
    """
    Parse HTML and locate the first table.
    """

    if not table_html or not str(table_html).strip():
        return None

    try:
        parser = html.HTMLParser(
            remove_comments=True,
            encoding="utf-8",
        )

        root = html.fromstring(
            str(table_html),
            parser=parser,
        )

        # Official PubTabNet expects body/table.
        tables = root.xpath(
            ".//body/table | .//table"
        )

        if not tables and root.tag == "table":
            tables = [root]

        return tables[0] if tables else None

    except Exception:
        return None


def html_to_tree_pubtabnet(element, structure_only=False):
    """
    Convert HTML into the official PubTabNet tree representation.
    """

    if element.tag == "td":

        if structure_only:
            content = []
        else:
            tokens = []
            pubtabnet_tokenize(element, tokens)
            content = tokens[1:-1].copy()

        return TableNode(
            tag="td",
            colspan=int(element.attrib.get("colspan", "1")),
            rowspan=int(element.attrib.get("rowspan", "1")),
            content=content,
        )

    children = [
        html_to_tree_pubtabnet(child, structure_only)
        for child in element
        if isinstance(child.tag, str)
    ]

    return TableNode(
        tag=element.tag,
        children=children,
    )


def count_html_nodes(element):
    """
    PubTabNet denominator: number of descendant HTML nodes,
    excluding the root table element.
    """

    return len(element.xpath(".//*"))


def teds_score(pred_html, gt_html, structure_only=False):
    """
    Original PubTabNet TEDS / TEDS-Struct.

    TEDS:
        Evaluates table structure and cell content.

    TEDS-Struct:
        Evaluates table structure, including cell spans,
        while ignoring cell content.
    """

    if not pred_html or not gt_html:
        return 0.0

    pred_element = parse_pubtabnet_html(pred_html)
    gt_element = parse_pubtabnet_html(gt_html)

    # Missing or invalid table predictions receive zero.
    if pred_element is None or gt_element is None:
        return 0.0

    pred_nodes = count_html_nodes(pred_element)
    gt_nodes = count_html_nodes(gt_element)

    denominator = max(pred_nodes, gt_nodes)

    if denominator == 0:
        return 0.0

    pred_tree = html_to_tree_pubtabnet(
        pred_element,
        structure_only,
    )

    gt_tree = html_to_tree_pubtabnet(
        gt_element,
        structure_only,
    )

    distance = APTED(
        pred_tree,
        gt_tree,
        PubTabNetTEDSConfig(
            structure_only=structure_only
        ),
    ).compute_edit_distance()

    return max(
        0.0,
        1.0 - float(distance) / denominator,
    )



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
    if pred_cells == 0:
        log("WARNING: ZERO TABLE CELLS PREDICTED")

    if pred_cells != gt_cells:
        log(
            f"WARNING: CELL COUNT MISMATCH: "
            f"{pred_cells} vs {gt_cells}"
        )

    log(
        f"Cell count difference: "
        f"{abs(pred_cells - gt_cells)}"
    )
    return score, struct_score, cer


def run_benchmark(num_samples=NUM_SAMPLES):
    global LOG
    LOG = DiagnosticLog(OUTPUT_TXT)
    results, evaluated, skipped = [], 0, 0
    try:
        log("=" * 78)
        log("PubTabNet: MinerU 2.5 Benchmark — TEDS + OCR + Upscaling")
        log(f"Started: {datetime.now().isoformat(timespec='seconds')}")
        log(f"Dataset: {DATASET_NAME}")
        log(f"Target samples: {num_samples}; upscale factor: {UPSCALE_FACTOR}x")
        log("Engine: MinerU 2.5 (DocLayout-YOLO + SLANet-Plus + OCR)")
        log(f"Full log: {os.path.abspath(OUTPUT_TXT)}")
        log("=" * 78)
        try:
            from mineru.cli.common import do_parse
            log("MinerU 2.5.3 API imports OK")
            log(f"MinerU parsing function: {do_parse.__name__}")
        except Exception as exc:
            raise RuntimeError(
                "MinerU 2.5.3 API is unavailable. "
                f"Original error: {type(exc).__name__}: {exc}"
            ) from exc
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
                log("\n--- MINERU 2.5: Upscaled image -> DocLayout + OCR Pipeline ---")
                markdown, pred_html, json_diagnostics = predict_mineru_2_5(upscaled, filename)
                elapsed = time.perf_counter() - started
                score, struct_score, cer = diagnostic_summary("MinerU-2.5", markdown, pred_html, gt_html)
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
                log(f"MinerU 2.5 FAILED: {error}\n{traceback.format_exc()}")
                row.update({
                    # NaN keeps infrastructure/API failures out of metric means.
                    "mineru_teds": float("nan"),
                    "mineru_teds_struct": float("nan"),
                    "mineru_cer": float("nan"),
                    "mineru_runtime_seconds": elapsed,
                    "mineru_predicted_cells": 0,
                    "mineru_markdown_chars": 0,
                    "mineru_error": error,
                })

            results.append(row)
            evaluated += 1
            original.close()
            upscaled.close()
            try:
                image.close()
            except Exception:
                pass
            gc.collect()

        log("\n" + "=" * 78 + "\nFINAL RESULTS (MINERU 2.5)\n" + "=" * 78)
        log(f"Samples evaluated: {evaluated}; skipped: {skipped}")
        if results:
            df = pd.DataFrame(results)
            successful = df["mineru_error"].isna() if "mineru_error" in df.columns else pd.Series(True, index=df.index)
            log(f"Successful inference samples: {int(successful.sum())}/{len(df)}")
            log(f"Failed inference samples: {int((~successful).sum())}/{len(df)}")
            for metric in ("teds", "teds_struct", "cer", "runtime_seconds"):
                col = f"mineru_{metric}"
                if col in df:
                    log(f"Mean {col} (successful samples where applicable): {df.loc[successful, col].mean():.4f}")
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

