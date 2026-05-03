"""Semantic chunking for PDFs and unstructured text.

Splits text intelligently on logical prompt boundaries:
- Markdown headings (# ## ### etc)
- Numbered sections (1. 2. 1.1 1.2.3 etc)
- ALL CAPS heading lines
- Paragraph boundaries (double newlines)

Preserves complete paragraphs and never splits mid-sentence.
"""

import re
from dataclasses import dataclass

# Reuse patterns from existing chunker
OBJECTIVE_PATTERN = re.compile(r"(?:\*\*)?Objective:?\s*\*?\*?\s*(.+?)(?:\n|$)", re.IGNORECASE | re.MULTILINE)
VARIABLE_PATTERN = re.compile(r"\[([A-Z_][A-Z0-9_]*)\]")


@dataclass(frozen=True)
class Chunk:
    """Immutable chunk of text with extracted metadata."""
    title: str
    objective: str
    full_text: str
    variables: list[str]


def _extract_objective(text: str) -> str:
    """Extract objective from text, or return first sentence."""
    match = OBJECTIVE_PATTERN.search(text)
    if match:
        obj = match.group(1).strip()
        if len(obj) <= 200:
            return obj
    # Fallback: first sentence
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line and len(line) > 10:
            # Try to find a sentence boundary
            if "." in line:
                return line.split(".")[0] + "."
            return line[:200] if len(line) > 200 else line
    return "Untitled"


def _extract_title(text: str) -> str:
    """Extract title from text (first non-empty line, strip heading markers)."""
    lines = text.strip().split("\n")
    for line in lines:
        line = line.strip()
        if line:
            # Remove markdown heading markers
            line = re.sub(r"^#+\s+", "", line)
            # Remove numbered section markers (1. 1.2 etc)
            line = re.sub(r"^\d+(\.\d+)*\.\s+", "", line)
            # Remove ALL CAPS marker if line is all uppercase
            if len(line) > 3 and line.isupper():
                return line
            return line[:256] if len(line) > 256 else line
    return "Untitled"


def _extract_variables(text: str) -> list[str]:
    """Extract [VARIABLE_NAME] tokens from text."""
    return sorted(set(VARIABLE_PATTERN.findall(text)))


def chunk_semantic(text: str) -> list[Chunk]:
    """Chunk text intelligently on semantic boundaries.

    Priority order for boundary detection:
    1. Markdown headings (# ## ### etc)
    2. Numbered sections (1. 2. 1.1 etc)
    3. ALL CAPS heading lines
    4. Paragraph boundaries (double newlines)
    5. If no boundaries found, return as single chunk

    Returns:
        List of Chunk objects. Never returns empty list; if text is empty,
        returns empty list. If text is non-empty, returns at least one chunk.
    """
    if not text or not text.strip():
        return []

    # Normalize: strip, collapse triple+ newlines to double
    text = text.strip()
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")

    # Try primary boundary: markdown headings + numbered sections + ALL CAPS
    # This regex matches lines that start with heading/section markers
    primary_pattern = re.compile(
        r"(?=^(?:#{1,6}\s+\S|### \d+\.\s+|\d+(?:\.\d+)*\.\s+\S|[A-Z][A-Z0-9 \-]{3,}$))",
        re.MULTILINE
    )
    parts = primary_pattern.split(text)
    parts = [p.strip() for p in parts if p.strip()]

    # If primary split yielded multiple parts, use them
    if len(parts) > 1:
        chunks = []
        for part in parts:
            if part:
                chunks.append(Chunk(
                    title=_extract_title(part),
                    objective=_extract_objective(part),
                    full_text=part,
                    variables=_extract_variables(part),
                ))
        return chunks

    # Fallback: try paragraph boundary (double newline)
    para_parts = text.split("\n\n")
    para_parts = [p.strip() for p in para_parts if p.strip()]

    if len(para_parts) > 1:
        chunks = []
        for part in para_parts:
            if part:
                chunks.append(Chunk(
                    title=_extract_title(part),
                    objective=_extract_objective(part),
                    full_text=part,
                    variables=_extract_variables(part),
                ))
        return chunks

    # No boundaries found: return entire text as single chunk
    return [Chunk(
        title=_extract_title(text),
        objective=_extract_objective(text),
        full_text=text,
        variables=_extract_variables(text),
    )]
