"""Tests for prompt boundary detection: CascadingDetector and strategy classes.

All tests are synchronous — no asyncio required.
"""

import pytest

from app.services.prompt_detector import (
    CascadingDetector,
    ObjectiveAnchoredDetector,
    TitlePatternDetector,
    WholeDocumentDetector,
)


# ---------------------------------------------------------------------------
# ObjectiveAnchoredDetector — markdown (heading) mode
# ---------------------------------------------------------------------------


def test_objective_anchored_markdown_returns_spans():
    """Sections with '# Heading' + 'Objective:' produce one span each."""
    text = (
        "# Prompt One\n\nObjective: Be helpful.\n\nSome body.\n\n"
        "# Prompt Two\n\nObjective: Write tests.\n\nMore body.\n"
    )
    detector = ObjectiveAnchoredDetector()
    spans = detector.detect(text)

    assert len(spans) == 2
    assert spans[0].title == "Prompt One"
    assert spans[0].objective == "Be helpful."
    assert spans[1].title == "Prompt Two"
    assert spans[1].objective == "Write tests."


def test_objective_anchored_markdown_no_objective_section_ignored():
    """Sections without 'Objective:' are silently skipped."""
    text = (
        "# Section Without Objective\n\nJust prose, no goal.\n\n"
        "# Section With Objective\n\nObjective: Accomplish this.\n\nBody.\n"
    )
    detector = ObjectiveAnchoredDetector()
    spans = detector.detect(text)

    assert len(spans) == 1
    assert spans[0].title == "Section With Objective"


# ---------------------------------------------------------------------------
# ObjectiveAnchoredDetector — raw text (no headings) mode
# ---------------------------------------------------------------------------


def test_objective_anchored_raw_text_detects_by_objective_anchors():
    """Without # headings, split on standalone 'Objective:' lines."""
    text = (
        "First Prompt\n\n"
        "Objective: Do something useful.\n\n"
        "This is the body of the first prompt.\n\n"
        "Second Prompt\n\n"
        "Objective: Do something else.\n\n"
        "This is the body of the second prompt.\n"
    )
    detector = ObjectiveAnchoredDetector()
    spans = detector.detect(text)

    assert len(spans) == 2
    assert spans[0].objective == "Do something useful."
    assert spans[1].objective == "Do something else."


def test_numbered_list_inline_objective_does_not_split_spans():
    """'1. Step Objective: …' (inline, not line-start) must not create a new span.

    _OBJ_LINE_RE requires Objective: at the very start of a line (after optional
    whitespace only), so an embedded 'Objective:' inside a list item is ignored.
    """
    # No # headings — raw-text mode where _OBJ_LINE_RE guards the split.
    text = (
        "My Prompt Title\n\n"
        "Objective: The real goal.\n\n"
        "Instructions:\n\n"
        "1. Start by planning. Objective: not a separate prompt.\n"
        "2. Execute the plan.\n"
    )
    detector = ObjectiveAnchoredDetector()
    spans = detector.detect(text)

    assert len(spans) == 1
    assert "real goal" in (spans[0].objective or "")


# ---------------------------------------------------------------------------
# TitlePatternDetector
# ---------------------------------------------------------------------------


def test_title_pattern_detector_splits_on_headings():
    """## headings each become a separate PromptSpan."""
    text = (
        "## Alpha\n\nBody of alpha.\n\n"
        "## Beta\n\nBody of beta.\n\n"
        "## Gamma\n\nBody of gamma.\n"
    )
    detector = TitlePatternDetector()
    spans = detector.detect(text)

    assert len(spans) == 3
    titles = {s.title for s in spans}
    assert titles == {"Alpha", "Beta", "Gamma"}


def test_title_pattern_detector_empty_section_skipped():
    """A heading with no body content produces no span."""
    text = "## Empty\n\n## HasContent\n\nSome text here.\n"
    detector = TitlePatternDetector()
    spans = detector.detect(text)

    assert len(spans) == 1
    assert spans[0].title == "HasContent"


# ---------------------------------------------------------------------------
# WholeDocumentDetector
# ---------------------------------------------------------------------------


def test_whole_document_detector_returns_single_span():
    text = "No headings here.\nJust plain prose across two lines."
    detector = WholeDocumentDetector()
    spans = detector.detect(text)

    assert len(spans) == 1
    assert spans[0].content == text


def test_whole_document_detector_empty_input_returns_empty():
    assert WholeDocumentDetector().detect("") == []
    assert WholeDocumentDetector().detect("   ") == []


# ---------------------------------------------------------------------------
# CascadingDetector
# ---------------------------------------------------------------------------


def test_cascading_falls_through_to_whole_document():
    """Text with no Objective: and no headings uses WholeDocumentDetector."""
    text = "Just a sentence. No objective. No headings."
    detector = CascadingDetector()
    spans = detector.detect_prompts(text)

    assert len(spans) == 1
    assert spans[0].content == text


def test_cascading_empty_input_returns_empty_list():
    detector = CascadingDetector()
    assert detector.detect_prompts("") == []
    assert detector.detect_prompts("   \n\t  \n") == []


def test_cascading_26_sections_all_returned():
    """The detector itself imposes no upper limit — 26 spans come back intact.

    Validation of the 25-prompt cap lives in IngestValidationError, not here.
    """
    sections = [
        f"## Prompt {i + 1}\n\nObjective: Do task {i + 1}.\n\nBody text.\n"
        for i in range(26)
    ]
    text = "\n".join(sections)
    detector = CascadingDetector()
    spans = detector.detect_prompts(text)

    assert len(spans) == 26


def test_cascading_pdf_style_five_sections():
    """Simulates prompts.pdf: 5 sections separated by standalone Objective: lines."""
    sections = [
        f"Prompt Title {i + 1}\n\nObjective: Accomplish goal {i + 1}.\n\nInstructions here.\n"
        for i in range(5)
    ]
    text = "\n\n".join(sections)
    detector = CascadingDetector()
    spans = detector.detect_prompts(text)

    assert len(spans) == 5
    for idx, span in enumerate(spans):
        assert span.objective is not None
        assert f"goal {idx + 1}" in span.objective
