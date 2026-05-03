"""PDF parsing service using pypdf for text extraction."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def is_pdf(file_path: str) -> bool:
    """Check if a file is a PDF by extension and magic bytes."""
    path = Path(file_path)
    if path.suffix.lower() != ".pdf":
        return False
    try:
        with open(file_path, "rb") as f:
            magic = f.read(4)
            return magic == b"%PDF"
    except (IOError, OSError):
        return False


def extract_text(file_path: str) -> str:
    """Extract text from a PDF file.

    Reads all pages, joins them with double newlines to preserve paragraph
    structure, and normalizes whitespace.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text as a single string.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a valid PDF.
    """
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError("pypdf is required for PDF parsing. Install with: pip install pypdf")

    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    if not is_pdf(file_path):
        raise ValueError(f"File is not a valid PDF: {file_path}")

    try:
        reader = PdfReader(file_path)
    except Exception as exc:
        raise ValueError(f"Failed to read PDF {file_path}: {exc}") from exc

    pages = []
    for page_num, page in enumerate(reader.pages):
        try:
            text = page.extract_text()
            if text:
                pages.append(text)
        except Exception as exc:
            logger.warning("Failed to extract text from page %d of %s: %s", page_num, file_path, exc)

    # Join pages with double newlines to preserve paragraph structure
    full_text = "\n\n".join(pages)

    # Normalize whitespace: collapse 3+ newlines to 2, strip trailing spaces per line
    lines = full_text.split("\n")
    normalized_lines = [line.rstrip() for line in lines]
    normalized_text = "\n".join(normalized_lines)

    # Collapse runs of 3+ newlines
    while "\n\n\n" in normalized_text:
        normalized_text = normalized_text.replace("\n\n\n", "\n\n")

    return normalized_text.strip()
