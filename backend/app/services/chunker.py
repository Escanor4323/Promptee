"""Schema-Aware Structural Chunking for markdown prompt templates.

Slices markdown documents precisely at template boundaries (### N. Title)
using Regex positive lookaheads, guaranteeing exactly one prompt per chunk.
"""

import re
from dataclasses import dataclass

BOUNDARY_PATTERN = re.compile(r"(?=^### \d+\. )", re.MULTILINE)
VARIABLE_PATTERN = re.compile(r"\[([A-Z][A-Z0-9_]*)\]")
OBJECTIVE_PATTERN = re.compile(r"\*\*Objective:\*\*\s*(.+?)(?:\n|$)", re.IGNORECASE)
FALLBACK_OBJECTIVE_PATTERN = re.compile(r"Objective:\s*(.+?)(?:\n|$)", re.IGNORECASE)


@dataclass(frozen=True)
class Chunk:
    title: str
    objective: str
    full_text: str
    variables: list[str]


def _extract_title(chunk_text: str) -> str:
    first_line = chunk_text.strip().split("\n", 1)[0]
    return re.sub(r"^###\s*\d+\.\s*", "", first_line).strip()


def _extract_objective(chunk_text: str) -> str:
    match = OBJECTIVE_PATTERN.search(chunk_text)
    if match:
        return match.group(1).strip()
    match = FALLBACK_OBJECTIVE_PATTERN.search(chunk_text)
    if match:
        return match.group(1).strip()
    return ""


def _extract_variables(chunk_text: str) -> list[str]:
    matches = VARIABLE_PATTERN.findall(chunk_text)
    return list(dict.fromkeys(matches))


def chunk_markdown(text: str) -> list[Chunk]:
    """Split a markdown document into chunks at template boundaries.

    Each chunk contains exactly one prompt template, from its ### header
    to the next boundary or end of document.
    """
    if not text or not text.strip():
        return []

    parts = BOUNDARY_PATTERN.split(text.strip())
    parts = [p.strip() for p in parts if p.strip()]

    chunks: list[Chunk] = []
    for part in parts:
        title = _extract_title(part)
        objective = _extract_objective(part)
        variables = _extract_variables(part)
        chunks.append(Chunk(
            title=title,
            objective=objective,
            full_text=part,
            variables=variables,
        ))

    return chunks


def chunk_file(file_path: str) -> list[Chunk]:
    """Read a markdown file and return its chunks."""
    with open(file_path, encoding="utf-8") as f:
        return chunk_markdown(f.read())


def chunk_file_auto(file_path: str) -> list[Chunk]:
    """Chunk a file using the appropriate strategy based on file extension.

    Routes by extension:
    - .md, .markdown → schema-aware markdown chunker (existing behavior)
    - .pdf → PDF extraction + CascadingDetector (prompt-boundary aware)
    - .txt and others → CascadingDetector

    The CascadingDetector (ADR-006) anchors on Objective: markers and
    strict heading patterns, so it never splits on numbered list items
    inside a prompt body — preventing the over-splitting that caused
    TOO_MANY_PARENTS errors on dense prompt PDFs.

    Args:
        file_path: Path to the file.

    Returns:
        List of Chunk objects (one per detected parent prompt).

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    import pathlib

    path = pathlib.Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".md", ".markdown"):
        return chunk_file(file_path)

    if suffix == ".pdf":
        from app.services import pdf_parser
        text = pdf_parser.extract_text(file_path)
    else:
        with open(file_path, encoding="utf-8") as f:
            text = f.read()

    # #region agent log f0c062
    import logging as _log, re as _re
    _logger = _log.getLogger(__name__)
    _all_obj = list(_re.finditer(r"objective", text, _re.IGNORECASE))
    _line_start_obj = list(_re.finditer(r"^[ \t]*(?:\*\*)?objective\s*:", text, _re.IGNORECASE | _re.MULTILINE))
    _logger.info("[f0c062] total 'objective' occurrences=%d, line-start matches=%d", len(_all_obj), len(_line_start_obj))
    # Log first 500 chars around each non-line-start occurrence
    _line_start_positions = {m.start() for m in _line_start_obj}
    for _m in _all_obj[:25]:
        if _m.start() not in _line_start_positions:
            _ctx_start = max(0, _m.start() - 80)
            _ctx_end = min(len(text), _m.end() + 80)
            _logger.info("[f0c062] MISSED objective at pos %d ctx=%r", _m.start(), text[_ctx_start:_ctx_end])
    # #endregion agent log f0c062

    from app.services.prompt_detector import CascadingDetector
    detector = CascadingDetector()
    spans = detector.detect_prompts(text)

    return [
        Chunk(
            title=span.title,
            objective=span.objective or "",
            full_text=span.content,
            variables=_extract_variables(span.content),
        )
        for span in spans
    ]
