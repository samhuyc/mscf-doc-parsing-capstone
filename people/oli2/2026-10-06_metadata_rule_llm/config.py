"""Experiment configuration. No evaluation data belongs in this module."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[2]
BASELINE = ROOT.parent / '2026-09-29_metadata_extraction'
SOURCE = REPO / 'people/samhu/2026-09-29_sponsor_samples/results'
PARSERS = ('pymupdf4llm', 'mineru_ocr', 'mineru_vlm')
VERSION = '1.0.2'
MODEL = 'gpt-4.1-mini-2025-04-14'
PROMPT_VERSION = '1.0.1'
SETTINGS = {'temperature': 0, 'max_output_tokens': 6000}
