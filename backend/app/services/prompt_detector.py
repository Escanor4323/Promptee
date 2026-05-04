"""Deterministic prompt boundary detection service.

This module implements a CascadingDetector strategy to isolate discrete prompts
from a Markdown document, avoiding naive text-splitting issues.
"""

import logging
import re
from dataclasses import dataclass
from typing import List, Optional

logger = logging.getLogger(__name__)


@dataclass
class PromptSpan:
    """Represents an isolated, unfragmented prompt."""
    title: str
    objective: Optional[str]
    content: str


class DetectorStrategy:
    """Base class for prompt boundary detection strategies."""

    def detect(self, markdown_text: str) -> List[PromptSpan]:
        raise NotImplementedError


class ObjectiveAnchoredDetector(DetectorStrategy):
    """Detects prompts by anchoring on 'Objective:' markers.

    Two modes:
    - Markdown mode: when the text has # headings, splits by heading and keeps
      sections that contain an Objective: line.
    - Raw text mode: for pypdf-style output with no # markers, splits directly
      on Objective: lines and walks backward to reconstruct prompt titles.

    Neither mode splits on numbered list items (1., 2.) — the key distinction
    from semantic_chunker.
    """

    # Matches an "Objective:" line regardless of leading whitespace, optional
    # bold markers, or whether the objective text follows on the same line.
    _OBJ_LINE_RE = re.compile(
        r"(^[ \t]*(?:\*\*)?Objective\s*:\*?\*?\s*.*$)", re.IGNORECASE | re.MULTILINE
    )
    _HEADING_RE = re.compile(r"^#+\s+\S", re.MULTILINE)

    def detect(self, text: str) -> List[PromptSpan]:
        if self._HEADING_RE.search(text):
            spans = self._detect_by_headings(text)
            if spans:
                return spans
        return self._detect_by_objectives(text)

    def _detect_by_headings(self, text: str) -> List[PromptSpan]:
        """Split by # headings; keep only sections that contain Objective:."""
        spans = []
        parts = re.split(r"^(#+\s+.*)$", text, flags=re.MULTILINE)
        current_title = "Untitled Prompt"
        i = 1 if len(parts) > 1 and parts[1].startswith("#") else 0
        while i < len(parts):
            if parts[i].startswith("#"):
                current_title = parts[i].lstrip("#").strip()
                i += 1
                content = parts[i].strip() if i < len(parts) else ""
                i += 1
            else:
                content = parts[i].strip()
                i += 1
            if not content:
                continue
            if "Objective:" in content or "**Objective:**" in content:
                obj_match = re.search(
                    r"\*?\*?Objective:\*?\*?\s*(.*?)(?=\n|$)", content, re.IGNORECASE
                )
                objective = obj_match.group(1).strip() if obj_match else None
                spans.append(PromptSpan(
                    title=current_title,
                    objective=objective,
                    content=f"# {current_title}\n\n{content}",
                ))
        return spans

    def _detect_by_objectives(self, text: str) -> List[PromptSpan]:
        """For raw PDF text (no # markers): split on Objective: anchors.

        Splits the document at every Objective: line. For each resulting
        segment the title is the last non-empty paragraph BEFORE that
        Objective: (which is the first paragraph of the previous body block
        or the document preamble). The section content runs from the title
        through the Objective: line to the end of the segment body (i.e.
        just before the next prompt's title paragraph).
        """
        parts = self._OBJ_LINE_RE.split(text)
        # After split with a capturing group:
        #   parts = [pre, OBJ_LINE, body, OBJ_LINE, body, ...]
        if len(parts) < 3:
            return []

        spans = []
        prev_preamble = parts[0]

        i = 1  # index of the first Objective: line
        while i < len(parts) - 1:
            obj_line = parts[i].strip()
            body = parts[i + 1]

            title = self._last_paragraph_title(prev_preamble)

            # The body runs until the next prompt's title paragraph.
            # If there is a following Objective:, the last paragraph of body
            # is that next title — strip it off and carry it forward.
            has_next = (i + 2) < len(parts)
            if has_next:
                body_paras = [p.strip() for p in body.split("\n\n") if p.strip()]
                prompt_body = "\n\n".join(body_paras[:-1]) if len(body_paras) > 1 else ""
                prev_preamble = body_paras[-1] if body_paras else ""
            else:
                prompt_body = body.strip()
                prev_preamble = ""

            obj_text = re.sub(
                r"^[ \t]*(?:\*\*)?Objective\s*:\*?\*?\s*", "", obj_line, flags=re.IGNORECASE
            ).strip()

            full_content = "\n\n".join(filter(None, [title, obj_line, prompt_body]))

            if title and full_content:
                spans.append(PromptSpan(
                    title=title,
                    objective=obj_text or None,
                    content=full_content,
                ))

            i += 2

        return spans

    @staticmethod
    def _last_paragraph_title(text: str) -> str:
        """Return a title string from the last non-empty paragraph of text."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        if not paragraphs:
            return "Untitled Prompt"
        last = paragraphs[-1]
        first_line = last.split("\n")[0].strip()
        # Strip markdown heading markers and leading numbering (not inner list items)
        first_line = re.sub(r"^#+\s*", "", first_line)
        first_line = re.sub(r"^\d+\.\s+", "", first_line)
        return first_line.strip() or "Untitled Prompt"


class TitlePatternDetector(DetectorStrategy):
    """Fallback detector using Markdown headings."""

    def detect(self, markdown_text: str) -> List[PromptSpan]:
        spans = []
        parts = re.split(r"^(#+\s+.*)$", markdown_text, flags=re.MULTILINE)

        i = 1 if len(parts) > 1 and parts[1].startswith("#") else 0

        while i < len(parts):
            if parts[i].startswith("#"):
                current_title = parts[i].lstrip("#").strip()
                i += 1
                if i < len(parts):
                    content = parts[i].strip()
                    i += 1
                else:
                    content = ""

                if content:
                    full_content = f"# {current_title}\n\n{content}"
                    spans.append(
                        PromptSpan(title=current_title, objective=None, content=full_content)
                    )
            else:
                i += 1

        return spans


class WholeDocumentDetector(DetectorStrategy):
    """Last resort detector that treats the entire document as one prompt."""

    def detect(self, markdown_text: str) -> List[PromptSpan]:
        if not markdown_text.strip():
            return []

        # Try to extract a title from the first line
        lines = markdown_text.strip().split("\n")
        title = lines[0].lstrip("#").strip() if lines else "Untitled Document"

        return [PromptSpan(title=title, objective=None, content=markdown_text)]


class CascadingDetector:
    """Runs multiple detection strategies in priority order."""

    def __init__(self):
        self.strategies = [
            ObjectiveAnchoredDetector(),
            TitlePatternDetector(),
            WholeDocumentDetector(),
        ]

    def detect_prompts(self, markdown_text: str) -> List[PromptSpan]:
        if not markdown_text.strip():
            return []

        for strategy in self.strategies:
            spans = strategy.detect(markdown_text)
            if spans:
                logger.info(f"{strategy.__class__.__name__} found {len(spans)} prompts.")
                return spans

        return []
