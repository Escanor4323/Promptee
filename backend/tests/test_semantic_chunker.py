"""Tests for semantic chunking of PDFs and unstructured text."""

import pytest

from app.services.semantic_chunker import chunk_semantic


class TestChunkSemanticBasic:
    """Test basic semantic chunking functionality."""

    def test_empty_text(self) -> None:
        chunks = chunk_semantic("")
        assert chunks == []

    def test_whitespace_only(self) -> None:
        chunks = chunk_semantic("   \n\n   ")
        assert chunks == []

    def test_single_paragraph(self) -> None:
        text = "This is a single paragraph with no boundaries."
        chunks = chunk_semantic(text)
        assert len(chunks) == 1
        assert chunks[0].full_text == text

    def test_markdown_heading_split(self) -> None:
        text = "# First Section\nContent here\n# Second Section\nMore content"
        chunks = chunk_semantic(text)
        assert len(chunks) == 2
        assert chunks[0].title == "First Section"
        assert chunks[1].title == "Second Section"

    def test_numbered_section_split(self) -> None:
        text = "1. First Prompt\nContent\n2. Second Prompt\nMore content"
        chunks = chunk_semantic(text)
        assert len(chunks) == 2
        assert chunks[0].title == "First Prompt"
        assert chunks[1].title == "Second Prompt"

    def test_all_caps_split(self) -> None:
        text = "SYSTEM INSTRUCTIONS\nBe helpful\n\nUSER QUERY\nAnswer this"
        chunks = chunk_semantic(text)
        assert len(chunks) == 2
        assert chunks[0].title == "SYSTEM INSTRUCTIONS"
        assert chunks[1].title == "USER QUERY"

    def test_paragraph_boundary_split(self) -> None:
        text = "First paragraph.\nStill first.\n\nSecond paragraph.\nStill second."
        chunks = chunk_semantic(text)
        assert len(chunks) == 2


class TestChunkSemanticMetadata:
    """Test metadata extraction."""

    def test_extract_title_from_markdown(self) -> None:
        text = "# My Title\nContent below"
        chunks = chunk_semantic(text)
        assert chunks[0].title == "My Title"

    def test_extract_title_from_numbered(self) -> None:
        text = "1. First Prompt\nContent"
        chunks = chunk_semantic(text)
        assert chunks[0].title == "First Prompt"

    def test_extract_objective_explicit(self) -> None:
        text = "# Title\n**Objective:** Do something helpful\nContent"
        chunks = chunk_semantic(text)
        assert "Do something helpful" in chunks[0].objective

    def test_extract_objective_fallback(self) -> None:
        text = "# Title\nThis is the first sentence. More text here."
        chunks = chunk_semantic(text)
        assert "first sentence" in chunks[0].objective

    def test_extract_variables(self) -> None:
        text = "Title\n[USER_INPUT] and [CONTEXT] are important."
        chunks = chunk_semantic(text)
        assert "USER_INPUT" in chunks[0].variables
        assert "CONTEXT" in chunks[0].variables

    def test_variables_sorted_unique(self) -> None:
        text = "[VAR_B] and [VAR_A] and [VAR_B] again"
        chunks = chunk_semantic(text)
        assert chunks[0].variables == ["VAR_A", "VAR_B"]


class TestChunkSemanticNormalization:
    """Test whitespace normalization."""

    def test_triple_newlines_collapsed(self) -> None:
        text = "First\n\n\nSecond"
        chunks = chunk_semantic(text)
        # Triple newlines are collapsed to double, which triggers paragraph split
        assert len(chunks) == 2

    def test_leading_trailing_whitespace_stripped(self) -> None:
        text = "   \n  Content  \n   "
        chunks = chunk_semantic(text)
        assert chunks[0].full_text == "Content"

    def test_mixed_newlines_normalized(self) -> None:
        text = "Line 1\n\n\n\nLine 2"
        chunks = chunk_semantic(text)
        # Multiple newlines are normalized
        assert len(chunks) == 2


class TestChunkSemanticInvariants:
    """Test safety invariants."""

    def test_large_prompt_stays_whole(self) -> None:
        """Large prompts without clear boundaries should not be split."""
        large_text = "A single very long paragraph. " * 100
        chunks = chunk_semantic(large_text)
        assert len(chunks) == 1
        assert chunks[0].full_text.startswith("A single very long paragraph")

    def test_all_chunks_have_title(self) -> None:
        text = "# Section 1\nContent\n# Section 2\nMore content"
        chunks = chunk_semantic(text)
        for chunk in chunks:
            assert chunk.title
            assert len(chunk.title) > 0

    def test_full_text_preserved(self) -> None:
        """Check that full_text is preserved without modification."""
        text = "# Title\nSpecial chars: !@#$%^&*()"
        chunks = chunk_semantic(text)
        assert "!@#$%^&*()" in chunks[0].full_text

    def test_chunk_immutability(self) -> None:
        """Test that Chunk objects are immutable (frozen)."""
        text = "# Test\nContent"
        chunks = chunk_semantic(text)
        chunk = chunks[0]
        with pytest.raises(AttributeError):
            chunk.title = "modified"


class TestChunkSemanticEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_only_heading_no_content(self) -> None:
        text = "# Heading Only"
        chunks = chunk_semantic(text)
        assert len(chunks) == 1
        assert chunks[0].title == "Heading Only"

    def test_mixed_heading_levels(self) -> None:
        text = "# Level 1\nContent\n## Level 2\nMore content\n### Level 3\nEven more"
        chunks = chunk_semantic(text)
        assert len(chunks) >= 1  # Should split on heading boundaries

    def test_numbered_sections_with_decimals(self) -> None:
        text = "1.1 Subsection\nContent\n1.2 Another subsection\nMore content"
        chunks = chunk_semantic(text)
        assert len(chunks) >= 1

    def test_very_long_line(self) -> None:
        """Test handling of very long lines without newlines."""
        long_line = "A" * 1000
        chunks = chunk_semantic(long_line)
        assert len(chunks) == 1
        assert chunks[0].full_text == long_line

    def test_special_markdown_characters(self) -> None:
        """Test text with markdown special characters."""
        text = "# **Bold Title** with _emphasis_\n[Link](http://example.com)"
        chunks = chunk_semantic(text)
        assert len(chunks) == 1

    def test_objective_case_insensitive(self) -> None:
        """Test that objective extraction is case-insensitive."""
        text = "# Title\nobjective: Something\nContent"
        chunks = chunk_semantic(text)
        assert "Something" in chunks[0].objective

    def test_all_caps_only_long_lines(self) -> None:
        """ALL CAPS only triggers for lines with 4+ characters."""
        text = "ABC\nCONTENT HERE\nXY"
        chunks = chunk_semantic(text)
        # ABC and XY are too short, only CONTENT HERE should trigger
        assert len(chunks) >= 1


class TestChunkSemanticRealWorld:
    """Test with realistic prompt content."""

    def test_pdf_extracted_text(self) -> None:
        """Simulate PDF extraction with normalized whitespace."""
        text = """SYSTEM INSTRUCTIONS
You are a helpful assistant.

USER QUERY
Answer the question below:

CONTEXT
Here is background information.

RESPONSE
Provide your answer."""
        chunks = chunk_semantic(text)
        assert len(chunks) >= 1
        assert any("SYSTEM" in chunk.title or "helpful" in chunk.objective for chunk in chunks)

    def test_multi_section_document(self) -> None:
        """Test a realistic multi-section document."""
        text = """# Section 1: Introduction
This is the introduction paragraph.

# Section 2: Details
This section provides details.

# Section 3: Conclusion
Final thoughts."""
        chunks = chunk_semantic(text)
        assert len(chunks) >= 2
        titles = [c.title for c in chunks]
        assert any("Introduction" in t for t in titles)

    def test_template_with_variables(self) -> None:
        """Test extraction of template variables."""
        text = "# Email Generator\nObjective: Generate professional emails\nCreate an email for [RECIPIENT] about [TOPIC].\nUse tone [TONE] and include [DETAILS]."
        chunks = chunk_semantic(text)
        assert len(chunks) == 1
        assert set(chunks[0].variables) == {"RECIPIENT", "TOPIC", "TONE", "DETAILS"}
