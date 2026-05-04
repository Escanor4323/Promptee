"""PDF parsing service using PyMuPDF for layout-aware text extraction.

Detects headings by comparing font sizes against the median body text size.
Text blocks with font size >= HEADING_SIZE_RATIO * median are prefixed with
a Markdown '## ' heading marker, enabling the ObjectiveAnchoredDetector to
use its heading-based splitting path.

Falls back to pypdf plain-text extraction if fitz is unavailable or layout
analysis fails.
"""

import logging
import statistics
from pathlib import Path

logger = logging.getLogger(__name__)

# A span is treated as a heading if its font size is this multiple above median.
# For typical PDFs where headings are ~1.2x body size (e.g. 13pt heading / 11pt body),
# a ratio of 1.15 catches these while excluding body text.
HEADING_SIZE_RATIO = 1.15

# Maximum word count for a block to be classified as a heading (not body text).
HEADING_MAX_WORDS = 20

# Fraction of page height used to skip running headers/footers.
HEADER_FOOTER_MARGIN = 0.05


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


def _extract_with_fitz(file_path: str) -> str | None:
    """Extract layout-aware Markdown text using PyMuPDF (fitz).

    Returns None if fitz is unavailable or extraction fails.
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.debug("PyMuPDF not available; falling back to pypdf")
        return None

    try:
        doc = fitz.open(file_path)
    except Exception as exc:
        logger.warning("fitz failed to open %s: %s", file_path, exc)
        return None

    # --- Pass 1: collect all font sizes to compute median ---
    all_sizes: list[float] = []
    # Store structured page data so we don't re-parse in pass 2.
    pages_data: list[list[dict]] = []

    for page in doc:
        page_height = page.rect.height
        top_margin = page_height * HEADER_FOOTER_MARGIN
        bottom_margin = page_height * (1 - HEADER_FOOTER_MARGIN)
        page_blocks: list[dict] = []

        try:
            raw = page.get_text("dict")
        except Exception as exc:
            logger.warning("get_text('dict') failed on page: %s", exc)
            pages_data.append(page_blocks)
            continue

        for block in raw.get("blocks", []):
            if block.get("type") != 0:  # 0 = text block
                continue
            by0 = block["bbox"][1]
            # Skip running headers/footers.
            if by0 < top_margin or by0 > bottom_margin:
                continue

            spans_data: list[dict] = []
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span.get("text", "").strip()
                    size = float(span.get("size", 0))
                    if text and size > 0:
                        spans_data.append({"text": text, "size": size})
                        all_sizes.append(size)

            if spans_data:
                page_blocks.append({"spans": spans_data, "bbox": block["bbox"]})

        pages_data.append(page_blocks)

    doc.close()

    if not all_sizes:
        return None

    median_size = statistics.median(all_sizes)
    heading_threshold = median_size * HEADING_SIZE_RATIO

    # --- Pass 2: build Markdown output ---
    output_blocks: list[str] = []

    for page_blocks in pages_data:
        for block in page_blocks:
            spans = block["spans"]
            max_size = max(s["size"] for s in spans)
            block_text = " ".join(s["text"] for s in spans).strip()

            if not block_text:
                continue

            word_count = len(block_text.split())
            is_heading = (
                max_size >= heading_threshold
                and word_count <= HEADING_MAX_WORDS
            )

            if is_heading:
                output_blocks.append(f"## {block_text}")
            else:
                output_blocks.append(block_text)

    if not output_blocks:
        return None

    # If no heading was produced, signal fallback to pypdf.
    has_headings = any(b.startswith("## ") for b in output_blocks)
    if not has_headings:
        logger.debug("fitz extraction found no headings; falling back to pypdf")
        return None

    raw_text = "\n\n".join(output_blocks)
    return _normalize(raw_text)


def _extract_with_pypdf(file_path: str) -> str:
    """Plain-text extraction via pypdf (fallback)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        raise ImportError(
            "Neither PyMuPDF nor pypdf is available. "
            "Install with: pip install PyMuPDF pypdf"
        )

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
            logger.warning(
                "Failed to extract text from page %d of %s: %s",
                page_num, file_path, exc,
            )

    return _normalize("\n\n".join(pages))


def _normalize(text: str) -> str:
    """Normalize whitespace: strip trailing spaces and collapse 3+ newlines."""
    lines = text.split("\n")
    normalized = "\n".join(line.rstrip() for line in lines)
    while "\n\n\n" in normalized:
        normalized = normalized.replace("\n\n\n", "\n\n")
    return normalized.strip()


def extract_text(file_path: str) -> str:
    """Extract text from a PDF file with layout-aware heading detection.

    Attempts PyMuPDF-based extraction first (produces Markdown headings).
    Falls back to pypdf plain-text extraction if fitz is unavailable or if no
    headings are detected in the layout pass.

    Args:
        file_path: Path to the PDF file.

    Returns:
        Extracted text as a single string, with '## ' Markdown headings where
        visual titles were detected.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If the file is not a valid PDF.
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"PDF file not found: {file_path}")

    if not is_pdf(file_path):
        raise ValueError(f"File is not a valid PDF: {file_path}")

    result = _extract_with_fitz(file_path)
    if result is not None:
        logger.debug("PDF extracted with PyMuPDF (layout-aware): %s", file_path)
        return result

    logger.debug("Falling back to pypdf for: %s", file_path)
    return _extract_with_pypdf(file_path)
