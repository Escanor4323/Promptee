"""Recursive child chunking for prompt templates using token-aware splitting.

Splits parent chunks into smaller, overlapping child chunks using a recursive
descent algorithm through sentence boundaries, with token-aware sizing and overlap.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from app.services.tokenizer import TokenCounter, TiktokenCounter

logger = logging.getLogger(__name__)

# Default separators for recursive descent, ordered by priority
DEFAULT_SEPARATORS = (
    "\n\n",      # Double newline (paragraph break)
    "\n",        # Single newline
    ". ",        # Sentence boundary
    " ",         # Word boundary
    "",          # Character fallback
)


@dataclass(frozen=True)
class ChildChunk:
    """Represents a child chunk (dense embedding unit).

    Attributes:
        text: The chunk content
        chunk_index: Sequential index within parent (0-based)
        token_count: Number of tokens in this chunk
        char_start: Starting character offset in parent text
        char_end: Ending character offset in parent text
        parent_title: Title of the parent prompt
    """

    text: str
    chunk_index: int
    token_count: int
    char_start: int
    char_end: int
    parent_title: str


def split_children(
    text: str,
    *,
    parent_title: str,
    max_tokens: int = 250,
    overlap_tokens: int = 50,
    separators: tuple[str, ...] = DEFAULT_SEPARATORS,
    tokenizer: Optional[TokenCounter] = None,
) -> tuple[ChildChunk, ...]:
    """Split text into token-bounded child chunks with overlap.

    Algorithm:
    ----------
    1. Use provided tokenizer (or create default TiktokenCounter)
    2. Recursively descend through separators to find split boundaries
    3. Greedily pack chunks up to max_tokens size
    4. Maintain overlap_tokens between consecutive chunks
    5. Return frozen tuple of ChildChunk objects with metadata

    The recursive descent approach:
    - Tries each separator in order (paragraph, sentence, word, char)
    - Finds the rightmost separator that keeps chunk <= max_tokens
    - Falls back to next separator if split point not found
    - Ensures no single word exceeds max_tokens

    Overlap strategy:
    - End of chunk N overlaps with start of chunk N+1
    - Helps maintain semantic continuity across boundaries
    - Last chunk may have fewer overlap tokens if near end

    Args:
        text: Parent text to split (usually from PromptSpan.content)
        parent_title: Title of parent prompt (metadata)
        max_tokens: Maximum tokens per child chunk (default 250)
        overlap_tokens: Tokens to overlap between chunks (default 50)
        separators: Tuple of separators to try in order (DEFAULT_SEPARATORS used if omitted)
        tokenizer: Optional TokenCounter instance (TiktokenCounter used if None)

    Returns:
        Frozen tuple of ChildChunk objects, each with:
        - text: chunk content
        - chunk_index: position in sequence
        - token_count: token count of this chunk
        - char_start: character offset from parent start
        - char_end: character offset from parent end
        - parent_title: reference to parent title

    Raises:
        ValueError: If text is empty or parent_title is empty
    """
    if not text or not text.strip():
        raise ValueError("Text cannot be empty")
    if not parent_title or not parent_title.strip():
        raise ValueError("parent_title cannot be empty")

    if tokenizer is None:
        tokenizer = TiktokenCounter()

    chunks: list[ChildChunk] = []
    char_offset = 0

    while char_offset < len(text):
        # Extract candidate text starting from current offset
        remaining = text[char_offset:]
        remaining_tokens = tokenizer.count(remaining)

        # If remaining text fits in one chunk, add it and finish
        if remaining_tokens <= max_tokens:
            chunk_text = remaining
            token_count = remaining_tokens
            chunk_end = len(text)
        else:
            # Need to split: find the right boundary using recursive descent
            chunk_text = _find_split_point(
                remaining,
                max_tokens,
                separators,
                tokenizer,
            )
            token_count = tokenizer.count(chunk_text)
            chunk_end = char_offset + len(chunk_text)

        # Create ChildChunk with metadata
        child = ChildChunk(
            text=chunk_text,
            chunk_index=len(chunks),
            token_count=token_count,
            char_start=char_offset,
            char_end=chunk_end,
            parent_title=parent_title,
        )
        chunks.append(child)

        # Move offset forward, accounting for overlap
        # overlap_tokens translates to approximate character count
        # rough heuristic: 1 token ~ 4 characters
        overlap_chars = overlap_tokens * 4
        char_offset = max(char_offset + len(chunk_text) - overlap_chars, char_offset + 1)

        # Prevent infinite loop if chunk is very small
        if len(chunk_text) == 0:
            logger.warning(f"Empty chunk produced for parent '{parent_title}', breaking")
            break

    logger.info(f"Split parent '{parent_title}' into {len(chunks)} child chunks")
    return tuple(chunks)


def _find_split_point(
    text: str,
    max_tokens: int,
    separators: tuple[str, ...],
    tokenizer: TokenCounter,
) -> str:
    """Recursively find the best split point using separators.

    Tries each separator in order. For each separator, finds the rightmost
    occurrence that keeps the left side <= max_tokens. Falls back to next
    separator if no valid split found.

    Args:
        text: Text to split
        max_tokens: Maximum tokens for the chunk
        separators: Tuple of separators to try in priority order
        tokenizer: TokenCounter instance for token counting

    Returns:
        Text of the chunk (may be less than max_tokens due to split point)
    """
    for i, sep in enumerate(separators):
        if sep == "":
            # Last resort: return first max_tokens of text by character
            # This is a safety valve and should rarely happen
            tokens = tokenizer.encode(text)
            if len(tokens) <= max_tokens:
                return text
            # Decode only first max_tokens
            truncated_tokens = tokens[:max_tokens]
            return tokenizer.decode(truncated_tokens)

        # Find all occurrences of this separator
        if sep not in text:
            continue

        # Try to find rightmost separator where left side fits in max_tokens
        parts = text.split(sep)
        accumulated = ""

        for j, part in enumerate(parts[:-1]):
            candidate = accumulated + part + sep
            candidate_tokens = tokenizer.count(candidate)

            if candidate_tokens > max_tokens:
                # Current candidate is too large
                if accumulated:
                    # Return what we accumulated so far
                    return accumulated.rstrip()
                else:
                    # First part itself is too large, try next separator
                    break
            else:
                # This candidate fits, keep going
                accumulated = candidate

        # If we accumulated something with this separator, return it
        if accumulated:
            return accumulated.rstrip()

    # Fallback: should not reach here if separators include ""
    logger.warning(f"No split point found in text of {len(text)} chars, returning first 1000 chars")
    return text[:1000]
