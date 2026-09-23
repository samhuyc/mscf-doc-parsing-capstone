import gc
import multiprocessing as mp
import os
import re
import tempfile

from bs4 import BeautifulSoup
from datasets import load_dataset
import pandas as pd
from PIL import Image


# =====================================================================
# CONFIG
# =====================================================================

DATASET_NAME = "nhhsag12/pubtabnet-with-html"

NUM_SAMPLES = 50

TIMEOUT_SECONDS = 15

OUTPUT_CSV = "pubtabnet_benchmark_results.csv"


# =====================================================================
# 1. Markdown -> HTML
# =====================================================================

def markdown_to_html_table(markdown):
    """
    Convert the first markdown table found in the PyMuPDF4LLM
    output into simple HTML.
    """

    lines = markdown.splitlines()

    table_lines = []
    inside_table = False

    for line in lines:

        stripped = line.strip()

        if "|" in stripped:

            inside_table = True
            table_lines.append(stripped)

        elif inside_table:

            break

    if not table_lines:
        return "<table></table>"

    # -------------------------------------------------------------
    # Remove markdown separator rows
    # -------------------------------------------------------------

    cleaned = []

    for line in table_lines:

        cells = [
            x.strip()
            for x in line.strip("|").split("|")
        ]

        if all(
            re.fullmatch(r":?-+:?", cell)
            for cell in cells
        ):
            continue

        cleaned.append(cells)

    if not cleaned:
        return "<table></table>"

    # -------------------------------------------------------------
    # Build HTML
    # -------------------------------------------------------------

    html = ["<table>"]

    for row_idx, cells in enumerate(cleaned):

        html.append("<tr>")

        for cell in cells:

            tag = "th" if row_idx == 0 else "td"

            html.append(
                f"<{tag}>{cell}</{tag}>"
            )

        html.append("</tr>")

    html.append("</table>")

    return "".join(html)


# =====================================================================
# 2. PyMuPDF4LLM subprocess worker
# =====================================================================

def _pymupdf4llm_worker(pdf_path, conn):

    try:

        import pymupdf4llm

        markdown = pymupdf4llm.to_markdown(
            pdf_path
        )

        html = markdown_to_html_table(
            markdown
        )

        conn.send(html)

    except Exception as e:

        print(
            f"[PyMuPDF4LLM worker error] "
            f"{type(e).__name__}: {e}"
        )

        try:
            conn.send("<table></table>")
        except Exception:
            pass

    finally:

        conn.close()


# =====================================================================
# 3. Safe PyMuPDF4LLM prediction
# =====================================================================

def predict_pymupdf4llm_safe(image):

    pdf_path = None
    parent_conn = None
    child_conn = None
    process = None

    try:

        # -------------------------------------------------------------
        # Create temporary PDF
        # -------------------------------------------------------------

        with tempfile.NamedTemporaryFile(
            suffix=".pdf",
            delete=False
        ) as f:

            pdf_path = f.name

            image.convert("RGB").save(
                f,
                format="PDF"
            )

        # -------------------------------------------------------------
        # Spawn fresh process
        # -------------------------------------------------------------

        ctx = mp.get_context("spawn")

        parent_conn, child_conn = ctx.Pipe(
            duplex=False
        )

        process = ctx.Process(
            target=_pymupdf4llm_worker,
            args=(
                pdf_path,
                child_conn
            )
        )

        process.start()

        child_conn.close()
        child_conn = None

        # -------------------------------------------------------------
        # Wait
        # -------------------------------------------------------------

        process.join(
            timeout=TIMEOUT_SECONDS
        )

        # -------------------------------------------------------------
        # Timeout
        # -------------------------------------------------------------

        if process.is_alive():

            print(
                "    PyMuPDF4LLM timeout -> "
                "terminating worker"
            )

            process.terminate()

            process.join(timeout=3)

            if process.is_alive():

                print(
                    "    terminate failed -> "
                    "killing worker"
                )

                process.kill()
                process.join()

            return "<table></table>"

        # -------------------------------------------------------------
        # Process completed
        # -------------------------------------------------------------

        if parent_conn.poll():

            result = parent_conn.recv()

            if result:
                return result

        return "<table></table>"

    except Exception as e:

        print(
            f"    [Parent error] "
            f"{type(e).__name__}: {e}"
        )

        return "<table></table>"

    finally:

        # -------------------------------------------------------------
        # Make sure worker is dead
        # -------------------------------------------------------------

        if process is not None:

            if process.is_alive():

                process.terminate()
                process.join(timeout=1)

            if process.is_alive():

                process.kill()
                process.join()

        # -------------------------------------------------------------
        # Close pipes
        # -------------------------------------------------------------

        if child_conn is not None:

            try:
                child_conn.close()
            except Exception:
                pass

        if parent_conn is not None:

            try:
                parent_conn.close()
            except Exception:
                pass

        # -------------------------------------------------------------
        # Remove temporary PDF
        # -------------------------------------------------------------

        if pdf_path is not None:

            try:
                os.remove(pdf_path)
            except Exception:
                pass

        gc.collect()


# =====================================================================
# 4. Native PyMuPDF OCR + table detection
# =====================================================================

def predict_pymupdf_native(image):

    import pymupdf

    ocr_doc = None

    try:

        # -------------------------------------------------------------
        # Convert PIL image -> PyMuPDF Pixmap
        # -------------------------------------------------------------

        image = image.convert("RGB")

        # Save image temporarily so PyMuPDF can open it.
        #
        # This is preferable to constructing a fake PDF with PIL,
        # because we want PyMuPDF's own OCR pipeline.
        # -------------------------------------------------------------

        with tempfile.NamedTemporaryFile(
            suffix=".png",
            delete=False
        ) as f:

            png_path = f.name

            image.save(
                f,
                format="PNG"
            )

        try:

            # ---------------------------------------------------------
            # Open image using PyMuPDF
            # ---------------------------------------------------------

            img_doc = pymupdf.open(
                png_path
            )

            try:

                pix = img_doc[0].get_pixmap(
                    colorspace=pymupdf.csRGB,
                    alpha=False
                )

            finally:

                img_doc.close()

            # ---------------------------------------------------------
            # OCR the image using PyMuPDF / Tesseract
            #
            # This creates a one-page PDF containing:
            #
            #   original image
            #        +
            #   hidden OCR text layer
            #
            # find_tables(strategy="text") can then use the
            # OCR text positions to infer table structure.
            # ---------------------------------------------------------

            ocr_bytes = pix.pdfocr_tobytes(
                language="eng"
            )

        finally:

            try:
                os.remove(png_path)
            except Exception:
                pass

        # -------------------------------------------------------------
        # Open OCR-generated PDF
        # -------------------------------------------------------------

        ocr_doc = pymupdf.open(
            stream=ocr_bytes,
            filetype="pdf"
        )

        page = ocr_doc[0]

        # -------------------------------------------------------------
        # Diagnostic: OCR word count
        # -------------------------------------------------------------

        words = page.get_text(
            "words"
        )

        print(
            f"    OCR words: {len(words)}"
        )

        # -------------------------------------------------------------
        # IMPORTANT:
        #
        # The original PNG has no PDF vector lines.
        #
        # Therefore:
        #
        #     strategy="lines"
        #
        # is inappropriate here.
        #
        # We use:
        #
        #     strategy="text"
        #
        # which uses text positions to infer rows/columns.
        # -------------------------------------------------------------

        tables = page.find_tables(
            strategy="text"
        )

        print(
            f"    Tables detected: "
            f"{len(tables.tables)}"
        )

        if len(tables.tables) == 0:

            return "<table></table>"

        # -------------------------------------------------------------
        # Extract ALL detected tables
        # -------------------------------------------------------------

        html_tables = []

        for table_idx, table in enumerate(
            tables.tables
        ):

            print(
                f"    Table {table_idx}: "
                f"{table.row_count} rows x "
                f"{table.col_count} columns"
            )

            try:

                html = table.to_html()

                if html:
                    html_tables.append(
                        html
                    )

            except Exception as e:

                print(
                    f"    [Table extraction error] "
                    f"{type(e).__name__}: {e}"
                )

        # -------------------------------------------------------------
        # Combine all tables
        # -------------------------------------------------------------

        if not html_tables:

            return "<table></table>"

        return "\n".join(
            html_tables
        )

    except Exception as e:

        print(
            f"    [Native PyMuPDF error] "
            f"{type(e).__name__}: {e}"
        )

        return "<table></table>"

    finally:

        if ocr_doc is not None:

            try:
                ocr_doc.close()
            except Exception:
                pass

        gc.collect()


# =====================================================================
# 5. Normalize HTML
# =====================================================================

def normalize_html(html):

    if html is None:
        return "<table></table>"

    if not isinstance(
        html,
        str
    ):

        html = str(html)

    return html.strip()


# =====================================================================
# 6. Node-count similarity
# =====================================================================

def calculate_node_similarity(
    pred_html,
    gt_html
):

    pred_html = normalize_html(
        pred_html
    )

    gt_html = normalize_html(
        gt_html
    )

    pred_soup = BeautifulSoup(
        pred_html,
        "html.parser"
    )

    gt_soup = BeautifulSoup(
        gt_html,
        "html.parser"
    )

    pred_nodes = len(
        pred_soup.find_all(
            ["td", "th"]
        )
    )

    gt_nodes = len(
        gt_soup.find_all(
            ["td", "th"]
        )
    )

    # Both empty.
    if pred_nodes == 0 and gt_nodes == 0:
        return 1.0

    # Only one is empty.
    if pred_nodes == 0 or gt_nodes == 0:
        return 0.0

    return (
        min(
            pred_nodes,
            gt_nodes
        )
        /
        max(
            pred_nodes,
            gt_nodes
        )
    )


# =====================================================================
# 7. Count nodes
# =====================================================================

def count_nodes(html):

    soup = BeautifulSoup(
        normalize_html(html),
        "html.parser"
    )

    return len(
        soup.find_all(
            ["td", "th"]
        )
    )


# =====================================================================
# 8. Main benchmark
# =====================================================================

def run_benchmark(
    num_samples=NUM_SAMPLES
):

    print("=" * 70)
    print("PubTabNet HTML Benchmark")
    print("=" * 70)

    print(
        f"Dataset: {DATASET_NAME}"
    )

    print(
        f"Target samples: {num_samples}"
    )

    print()

    # -------------------------------------------------------------
    # Load dataset
    # -------------------------------------------------------------

    print("Loading dataset...")

    ds = load_dataset(
        DATASET_NAME,
        split="train",
        streaming=True
    )

    print("Dataset loaded.")
    print()

    # -------------------------------------------------------------
    # Results
    # -------------------------------------------------------------

    results = []

    evaluated = 0
    skipped = 0

    # -------------------------------------------------------------
    # Stream samples
    # -------------------------------------------------------------

    for sample in ds:

        if evaluated >= num_samples:
            break

        # ---------------------------------------------------------
        # Key
        # ---------------------------------------------------------

        key = sample.get(
            "__key__"
        )

        if key is None:

            skipped += 1
            continue

        if not key.startswith(
            "pubtabnet/train/"
        ):

            skipped += 1
            continue

        # ---------------------------------------------------------
        # Image
        # ---------------------------------------------------------

        image = sample.get("png")

        if image is None:

            print(
                f"Skipping {key}: no PNG"
            )

            skipped += 1
            continue

        # ---------------------------------------------------------
        # Ground truth HTML
        # ---------------------------------------------------------

        gt_html = sample.get("html")

        if gt_html is None:

            print(
                f"Skipping {key}: "
                f"no HTML ground truth"
            )

            skipped += 1
            continue

        # ---------------------------------------------------------
        # Validate image
        # ---------------------------------------------------------

        if not isinstance(
            image,
            Image.Image
        ):

            print(
                f"Skipping {key}: "
                f"unexpected image type "
                f"{type(image)}"
            )

            skipped += 1
            continue

        image = image.convert("RGB")

        # ---------------------------------------------------------
        # Filename
        # ---------------------------------------------------------

        filename = key.split("/")[-1]

        if not filename.endswith(".png"):
            filename += ".png"

        print()
        print("-" * 70)

        print(
            f"[{evaluated + 1}/{num_samples}] "
            f"{filename}"
        )

        print(
            f"Image size: {image.size}"
        )

        # ---------------------------------------------------------
        # Ground truth
        # ---------------------------------------------------------

        gt_html = normalize_html(
            gt_html
        )

        gt_nodes = count_nodes(
            gt_html
        )

        print(
            f"GT nodes: {gt_nodes}"
        )

        # =========================================================
        # PyMuPDF4LLM
        # =========================================================

        print(
            "Running PyMuPDF4LLM..."
        )

        pymupdf4llm_html = (
            predict_pymupdf4llm_safe(
                image
            )
        )

        pymupdf4llm_nodes = (
            count_nodes(
                pymupdf4llm_html
            )
        )

        pymupdf4llm_score = (
            calculate_node_similarity(
                pymupdf4llm_html,
                gt_html
            )
        )

        print(
            f"PyMuPDF4LLM nodes: "
            f"{pymupdf4llm_nodes}"
        )

        print(
            f"PyMuPDF4LLM score: "
            f"{pymupdf4llm_score:.4f}"
        )

        # =========================================================
        # Native PyMuPDF
        # =========================================================

        print(
            "Running native PyMuPDF..."
        )

        pymupdf_html = (
            predict_pymupdf_native(
                image
            )
        )

        pymupdf_nodes = (
            count_nodes(
                pymupdf_html
            )
        )

        pymupdf_score = (
            calculate_node_similarity(
                pymupdf_html,
                gt_html
            )
        )

        print(
            f"Native PyMuPDF nodes: "
            f"{pymupdf_nodes}"
        )

        print(
            f"Native PyMuPDF score: "
            f"{pymupdf_score:.4f}"
        )

        # ---------------------------------------------------------
        # Save result
        # ---------------------------------------------------------

        results.append({

            "filename": filename,

            "gt_nodes": gt_nodes,

            "pymupdf4llm_nodes":
                pymupdf4llm_nodes,

            "pymupdf_nodes":
                pymupdf_nodes,

            "pymupdf4llm_score":
                pymupdf4llm_score,

            "pymupdf_score":
                pymupdf_score,
        })

        evaluated += 1

        # ---------------------------------------------------------
        # Cleanup
        # ---------------------------------------------------------

        image.close()

        gc.collect()

    # =================================================================
    # Final results
    # =================================================================

    print()
    print("=" * 70)
    print("FINAL RESULTS")
    print("=" * 70)

    if len(results) == 0:

        print(
            "No samples were successfully evaluated."
        )

        print(
            f"Skipped: {skipped}"
        )

        return pd.DataFrame()

    df = pd.DataFrame(
        results
    )

    print()

    print(
        df.to_string(
            index=False
        )
    )

    print()

    print("-" * 70)

    print(
        f"Samples evaluated: "
        f"{len(df)}"
    )

    print(
        f"Samples skipped: "
        f"{skipped}"
    )

    print()

    print(
        "Mean PyMuPDF4LLM score: "
        f"{df['pymupdf4llm_score'].mean():.4f}"
    )

    print(
        "Mean native PyMuPDF score: "
        f"{df['pymupdf_score'].mean():.4f}"
    )

    print()

    # -------------------------------------------------------------
    # Save CSV
    # -------------------------------------------------------------

    df.to_csv(
        OUTPUT_CSV,
        index=False
    )

    print(
        f"Results saved to: "
        f"{OUTPUT_CSV}"
    )

    return df


# =====================================================================
# 9. Main
# =====================================================================

if __name__ == "__main__":

    # -------------------------------------------------------------
    # macOS:
    #
    # multiprocessing must be protected by __main__.
    # -------------------------------------------------------------

    mp.set_start_method(
        "spawn",
        force=True
    )

    df = run_benchmark(
        num_samples=NUM_SAMPLES
    )
