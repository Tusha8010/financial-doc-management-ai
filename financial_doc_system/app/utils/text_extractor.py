"""
utils/text_extractor.py
Extract plain text from PDF and text files.
Tries pdfplumber first (better for structured PDFs), falls back to PyMuPDF.
"""

import io
from pathlib import Path
from typing import Optional

from loguru import logger


def extract_text_from_pdf_pdfplumber(file_path: str) -> str:
    """
    Extract text using pdfplumber — better for structured/tabular PDFs.
    Returns concatenated text from all pages.
    """
    try:
        import pdfplumber
        full_text = []
        with pdfplumber.open(file_path) as pdf:
            for i, page in enumerate(pdf.pages):
                page_text = page.extract_text()
                if page_text:
                    full_text.append(f"[Page {i + 1}]\n{page_text}")
        return "\n\n".join(full_text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed: {e}")
        return ""


def extract_text_from_pdf_pymupdf(file_path: str) -> str:
    """
    Extract text using PyMuPDF — faster and handles more edge cases.
    Used as fallback when pdfplumber yields empty/short output.
    """
    try:
        import fitz  # PyMuPDF
        full_text = []
        with fitz.open(file_path) as doc:
            for i, page in enumerate(doc):
                page_text = page.get_text("text")
                if page_text.strip():
                    full_text.append(f"[Page {i + 1}]\n{page_text}")
        return "\n\n".join(full_text)
    except Exception as e:
        logger.warning(f"PyMuPDF extraction failed: {e}")
        return ""


def extract_text(file_path: str, mime_type: Optional[str] = None) -> str:
    """
    Main entry point for text extraction.

    Strategy:
      1. If plain text file → read directly.
      2. If PDF → try pdfplumber, fall back to PyMuPDF.

    Args:
        file_path: Path to the uploaded file.
        mime_type: MIME type hint (e.g., 'application/pdf').

    Returns:
        Extracted plain text string. Empty string on failure.
    """
    path = Path(file_path)

    if not path.exists():
        logger.error(f"File not found: {file_path}")
        return ""

    suffix = path.suffix.lower()

    # Plain text files
    if suffix in {".txt", ".md", ".csv"} or (mime_type and "text/" in mime_type):
        try:
            return path.read_text(encoding="utf-8", errors="replace")
        except Exception as e:
            logger.error(f"Failed to read text file {file_path}: {e}")
            return ""

    # PDF files
    if suffix == ".pdf" or (mime_type and "pdf" in mime_type):
        logger.info(f"Extracting text from PDF: {file_path}")
        text = extract_text_from_pdf_pdfplumber(file_path)

        # Fallback: if pdfplumber got less than 100 chars, try PyMuPDF
        if len(text.strip()) < 100:
            logger.info("pdfplumber output too short, trying PyMuPDF fallback")
            text = extract_text_from_pdf_pymupdf(file_path)

        char_count = len(text)
        logger.info(f"Extracted {char_count} characters from {path.name}")
        return text

    logger.warning(f"Unsupported file type: {suffix}")
    return ""


def get_page_count(file_path: str) -> int:
    """Return the number of pages in a PDF (0 for non-PDFs)."""
    try:
        import pdfplumber
        with pdfplumber.open(file_path) as pdf:
            return len(pdf.pages)
    except Exception:
        return 0
