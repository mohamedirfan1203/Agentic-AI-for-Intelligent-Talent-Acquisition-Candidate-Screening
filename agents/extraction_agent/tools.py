"""
Extraction Agent Tools
======================
File-parsing utilities (PDF, DOCX, TXT) with clean milestone logging.
"""

import io
import json
import logging
import os
import time
from datetime import datetime
from typing import Tuple

import fitz  # PyMuPDF
import docx  # python-docx

logger = logging.getLogger("agents.extraction_agent.tools")

INTERMEDIATE_DIR = "intermediate_data"


def _ts() -> str:
    """Current timestamp string for inline log messages."""
    return datetime.now().strftime("%H:%M:%S")


def _ensure_intermediate_dir() -> None:
    if not os.path.exists(INTERMEDIATE_DIR):
        os.makedirs(INTERMEDIATE_DIR)


def _save_intermediate_json(data: dict, original_filename: str, doc_type: str) -> str | None:
    _ensure_intermediate_dir()
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = os.path.basename(original_filename).replace(".", "_")
        out_filename = f"{doc_type}_{safe_name}_{timestamp}.json"
        out_path = os.path.join(INTERMEDIATE_DIR, out_filename)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return out_path
    except Exception as exc:
        logger.error(f"[{_ts()}] Failed to save intermediate JSON: {exc}")
        return None


def extract_text_from_file(file_content: bytes, filename: str) -> Tuple[str, float]:
    """Parse raw bytes → plain text. Returns (text, latency_seconds)."""
    ext = os.path.splitext(filename.lower())[1]
    t0 = time.perf_counter()
    raw_text = ""

    logger.info(f"[{_ts()}] 📄 Parsing file: {filename} ({len(file_content):,} bytes)")

    if ext == ".pdf":
        try:
            doc = fitz.open(stream=file_content, filetype="pdf")
            raw_text = "".join([page.get_text() for page in doc]).strip()
        except Exception as exc:
            logger.error(f"[{_ts()}] PyMuPDF error: {exc}")

    elif ext == ".docx":
        try:
            doc = docx.Document(io.BytesIO(file_content))
            raw_text = "\n".join(p.text for p in doc.paragraphs if p.text.strip()).strip()
        except Exception as exc:
            logger.error(f"[{_ts()}] python-docx error: {exc}")

    elif ext == ".txt":
        try:
            raw_text = file_content.decode("utf-8").strip()
        except UnicodeDecodeError:
            raw_text = file_content.decode("latin-1").strip()

    else:
        logger.warning(f"[{_ts()}] Unsupported format: {ext}")

    latency = time.perf_counter() - t0
    logger.info(f"[{_ts()}] ✅ Text extracted — {len(raw_text):,} chars in {latency:.2f}s")
    return raw_text, latency


def save_extraction_result(data: dict, original_filename: str, doc_type: str) -> str | None:
    path = _save_intermediate_json(data, original_filename, doc_type)
    if path:
        logger.info(f"[{_ts()}] 💾 Saved intermediate JSON → {path}")
    return path
