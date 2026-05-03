"""Tests for schema-aware structural chunking."""

import pytest

from app.services.chunker import Chunk, chunk_markdown


SAMPLE_MD = """\
### 1. Code Review Assistant
**Objective:** Review code for quality issues
You are a [ROLE] reviewing [LANGUAGE] code for bugs and style violations.

### 2. Bug Fix Helper
**Objective:** Help fix bugs efficiently
You are a [ROLE] fixing bugs in [FRAMEWORK] applications. Focus on root causes.

### 3. Test Writer
Objective: Write comprehensive tests
Write unit tests for [LANGUAGE] using [FRAMEWORK]. Cover edge cases.
"""


def test_split_markdown_at_boundaries() -> None:
    chunks = chunk_markdown(SAMPLE_MD)
    assert len(chunks) == 3
    assert chunks[0].title == "Code Review Assistant"
    assert chunks[1].title == "Bug Fix Helper"
    assert chunks[2].title == "Test Writer"


def test_extract_variables() -> None:
    chunks = chunk_markdown(SAMPLE_MD)
    assert "[ROLE]" in chunks[0].full_text
    assert chunks[0].variables == ["ROLE", "LANGUAGE"]
    assert chunks[1].variables == ["ROLE", "FRAMEWORK"]


def test_extract_objective() -> None:
    chunks = chunk_markdown(SAMPLE_MD)
    assert "Review code for quality issues" in chunks[0].objective
    assert "Help fix bugs efficiently" in chunks[1].objective


def test_single_chunk_document() -> None:
    text = "### 1. Only Prompt\n**Objective:** Do something\nYou are helpful."
    chunks = chunk_markdown(text)
    assert len(chunks) == 1
    assert chunks[0].title == "Only Prompt"


def test_empty_document() -> None:
    chunks = chunk_markdown("")
    assert len(chunks) == 0


def test_chunk_is_frozen() -> None:
    chunks = chunk_markdown("### 1. Test\nObjective: test\nBody")
    chunk = chunks[0]
    assert isinstance(chunk, Chunk)
    with pytest.raises(AttributeError):
        chunk.title = "modified"
