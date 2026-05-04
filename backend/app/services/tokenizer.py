"""Token counting using tiktoken for LLM-friendly text chunking.

Provides a lazy-loaded tiktoken encoder for counting and manipulating tokens.
Uses the cl100k_base encoding (GPT-4/3.5 compatible).
"""

import logging
from typing import Protocol

logger = logging.getLogger(__name__)

_encoder = None


class TokenCounter(Protocol):
    """Abstract interface for token counting and encoding operations."""

    def count(self, text: str) -> int:
        """Count tokens in the given text."""
        ...

    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs."""
        ...

    def decode(self, tokens: list[int]) -> str:
        """Decode token IDs back to text."""
        ...


def get_encoder() -> TokenCounter:
    """Lazy-load the tiktoken encoder (singleton).

    Returns the cl100k_base encoder compatible with GPT-4/3.5 models.
    Loaded on first call only to avoid startup overhead.

    Returns:
        Tiktoken encoder instance
    """
    global _encoder
    if _encoder is None:
        import tiktoken

        logger.info("Loading tiktoken encoder: cl100k_base")
        _encoder = tiktoken.get_encoding("cl100k_base")
    return _encoder


class TiktokenCounter:
    """Token counter using tiktoken cl100k_base encoding.

    Provides methods for counting tokens, encoding text to tokens,
    and decoding tokens back to text.
    """

    def count(self, text: str) -> int:
        """Count tokens in the given text.

        Args:
            text: Text to tokenize

        Returns:
            Number of tokens in the text
        """
        encoder = get_encoder()
        tokens = encoder.encode(text)
        return len(tokens)

    def encode(self, text: str) -> list[int]:
        """Encode text to token IDs.

        Args:
            text: Text to encode

        Returns:
            List of token IDs
        """
        encoder = get_encoder()
        return encoder.encode(text)

    def decode(self, tokens: list[int]) -> str:
        """Decode token IDs back to text.

        Args:
            tokens: List of token IDs

        Returns:
            Decoded text
        """
        encoder = get_encoder()
        return encoder.decode(tokens)
