"""Validation logic for document ingestion.

Provides validators for parent chunks, child chunks, and document content
to ensure data integrity before processing ingest requests.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Ingest size constraints
MAX_PARENTS_PER_INGEST = 25
MAX_TOKENS_PER_CHILD = 250
# 20 prompts × ~202 children each = ~4040 children (observed from prompts.pdf after
# PyMuPDF correctly detects all 20 headings). Set to 5000 for comfortable headroom
# with the full 25-prompt maximum.
MAX_CHILDREN_PER_INGEST = 5000


class IngestValidationError(Exception):
    """Raised when document ingestion validation fails."""

    def __init__(self, error: "ValidationError"):
        self.error = error
        super().__init__(error.message)


@dataclass(frozen=True)
class ValidationError:
    """Represents a single validation error.

    Attributes:
        code: Machine-readable error code (e.g., 'EMPTY_DOCUMENT', 'TOO_MANY_PARENTS')
        message: Human-readable error message
        detail: Additional context dict (error-specific fields)
    """

    code: str
    message: str
    detail: dict


def validate_document_empty(text: str) -> None:
    """Validate that document content is not empty.

    Raises:
        IngestValidationError: If text is empty or whitespace-only

    Args:
        text: Document text to validate
    """
    if not text or not text.strip():
        error = ValidationError(
            code="EMPTY_DOCUMENT",
            message="Document content cannot be empty",
            detail={},
        )
        raise IngestValidationError(error)


def validate_parents(spans: list) -> None:
    """Validate parent chunks (prompts) extracted from document.

    Ensures:
    - At least one parent chunk exists
    - Parent count does not exceed MAX_PARENTS_PER_INGEST
    - All parents have non-empty titles and content

    Raises:
        IngestValidationError: If validation fails

    Args:
        spans: List of PromptSpan objects from prompt_detector
    """
    if not spans:
        error = ValidationError(
            code="NO_PARENTS_FOUND",
            message="Document must contain at least one prompt (parent chunk)",
            detail={"required": 1, "found": 0},
        )
        raise IngestValidationError(error)

    if len(spans) > MAX_PARENTS_PER_INGEST:
        error = ValidationError(
            code="TOO_MANY_PARENTS",
            message=f"Document contains too many prompts (max {MAX_PARENTS_PER_INGEST})",
            detail={
                "max_allowed": MAX_PARENTS_PER_INGEST,
                "found": len(spans),
            },
        )
        raise IngestValidationError(error)

    # Validate each parent has content (handles both PromptSpan and Chunk objects)
    for i, parent in enumerate(spans):
        if not parent.title or not parent.title.strip():
            error = ValidationError(
                code="EMPTY_PARENT_TITLE",
                message=f"Parent prompt #{i + 1} has empty title",
                detail={"parent_index": i, "missing_field": "title"},
            )
            raise IngestValidationError(error)

        content = getattr(parent, 'content', None) or getattr(parent, 'full_text', None)
        if not content or not content.strip():
            error = ValidationError(
                code="EMPTY_PARENT_CONTENT",
                message=f"Parent prompt '{parent.title}' has empty content",
                detail={"parent_index": i, "parent_title": parent.title, "missing_field": "content"},
            )
            raise IngestValidationError(error)

    logger.info(f"Validated {len(spans)} parent chunks")


def validate_children(parents: list) -> None:
    """Validate child chunks generated from parent chunks.

    Ensures:
    - At least one child chunk exists across all parents
    - Total child count does not exceed MAX_CHILDREN_PER_INGEST
    - No individual child exceeds MAX_TOKENS_PER_CHILD tokens
    - All children have non-empty text

    Raises:
        IngestValidationError: If validation fails

    Args:
        parents: List of ParentChunk objects with children attribute
    """
    if not parents:
        error = ValidationError(
            code="NO_PARENTS_FOR_CHILDREN",
            message="Must have parent chunks before validating children",
            detail={},
        )
        raise IngestValidationError(error)

    # Collect all children and check total count
    all_children = []
    for parent in parents:
        if hasattr(parent, "children"):
            all_children.extend(parent.children)

    if not all_children:
        error = ValidationError(
            code="NO_CHILDREN_FOUND",
            message="No child chunks were generated from parent prompts",
            detail={"parents_count": len(parents)},
        )
        raise IngestValidationError(error)

    if len(all_children) > MAX_CHILDREN_PER_INGEST:
        error = ValidationError(
            code="TOO_MANY_CHILDREN",
            message=f"Too many child chunks (max {MAX_CHILDREN_PER_INGEST})",
            detail={
                "max_allowed": MAX_CHILDREN_PER_INGEST,
                "found": len(all_children),
            },
        )
        raise IngestValidationError(error)

    # Validate each child
    for i, child in enumerate(all_children):
        # Check for empty text
        if not hasattr(child, "text") or not child.text or not child.text.strip():
            error = ValidationError(
                code="EMPTY_CHILD_TEXT",
                message=f"Child chunk #{i} has empty text",
                detail={"child_index": i},
            )
            raise IngestValidationError(error)

        # Check token count if available
        if hasattr(child, "token_count") and child.token_count > MAX_TOKENS_PER_CHILD:
            parent_title = getattr(child, "parent_title", "unknown")
            error = ValidationError(
                code="CHILD_EXCEEDS_TOKEN_LIMIT",
                message=f"Child chunk exceeds {MAX_TOKENS_PER_CHILD} tokens",
                detail={
                    "child_index": i,
                    "parent_title": parent_title,
                    "token_count": child.token_count,
                    "max_allowed": MAX_TOKENS_PER_CHILD,
                },
            )
            raise IngestValidationError(error)

    logger.info(f"Validated {len(all_children)} child chunks from {len(parents)} parents")
