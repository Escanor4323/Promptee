"""Path resolution service for translating host paths to container paths.

Handles path normalization and validation when running in containerized environments,
ensuring safe access to mounted volumes.
"""

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from fastapi import Depends

from app.config import get_settings, Settings

logger = logging.getLogger(__name__)


class PathResolutionError(Exception):
    """Raised when a path cannot be safely resolved to a container path."""

    pass


@dataclass(frozen=True)
class PathResolution:
    """Result of resolving a path from host to container.

    Attributes:
        original: The original path string provided by the client.
        container_path: The resolved container path as a Path object.
        was_translated: Whether the path was translated (host->container) or passed through.
        is_relative: Whether the original path was relative.
    """

    original: str
    container_path: Path
    was_translated: bool
    is_relative: bool


def resolve_to_container_path(
    original_path: str,
    settings: Settings,
    follow_symlinks: bool = False,
) -> PathResolution:
    """Resolve a path from host filesystem to container filesystem.

    Translation rules:
    1. Empty string raises PathResolutionError
    2. Absolute container paths (starting with /app/) pass through unchanged
    3. Absolute host paths are rewritten using host_project_root mapping
    4. Relative paths are joined to container_data_root
    5. Paths containing ".." are validated to prevent escaping the root
    6. Symlink targets are checked for containment when follow_symlinks=True

    Args:
        original_path: Path string from client (may be absolute host or relative)
        settings: Settings object containing path configuration
        follow_symlinks: If True, resolve symlinks and check containment

    Returns:
        PathResolution with resolved container path and metadata

    Raises:
        PathResolutionError: If path is empty, unmounted, or escapes allowed root
    """
    if not original_path or not original_path.strip():
        raise PathResolutionError("Path cannot be empty")

    original_path = original_path.strip()
    container_root = Path(settings.container_data_root)
    host_root = Path(settings.host_project_root)

    # Rule 2: Absolute container paths pass through
    if original_path.startswith("/app/"):
        resolved = Path(original_path)
        # Validate containment: ensure resolved path is under /app/data
        try:
            resolved.relative_to(container_root)
        except ValueError:
            raise PathResolutionError(
                f"Container path {original_path} is outside allowed root {container_root}"
            )
        return PathResolution(
            original=original_path,
            container_path=resolved,
            was_translated=False,
            is_relative=False,
        )

    # Rule 3: Absolute host paths (not /app/) are rewritten
    if original_path.startswith("/"):
        host_path = Path(original_path)
        # Check if path is under host_project_root
        try:
            host_path.relative_to(host_root)
        except ValueError:
            raise PathResolutionError(
                f"Absolute path {original_path} is not under {host_root}"
            )
        # Translate: /Users/joelmartinez/Documents/Projects/Promptee/data/file.md
        # becomes /app/data/file.md
        relative_from_host = host_path.relative_to(host_root)
        container_path = container_root / relative_from_host
        return PathResolution(
            original=original_path,
            container_path=container_path,
            was_translated=True,
            is_relative=False,
        )

    # Rule 4: Relative paths join to container root
    container_path = (container_root / original_path).resolve()

    # Rule 5: Validate no ".." escapes
    try:
        container_path.relative_to(container_root)
    except ValueError:
        raise PathResolutionError(
            f"Relative path {original_path} escapes allowed root {container_root}"
        )

    # Rule 6: If symlink following, resolve and recheck
    if follow_symlinks and container_path.is_symlink():
        try:
            target = container_path.resolve()
            target.relative_to(container_root)
        except ValueError:
            raise PathResolutionError(
                f"Symlink {original_path} resolves outside allowed root {container_root}"
            )

    return PathResolution(
        original=original_path,
        container_path=container_path,
        was_translated=False,
        is_relative=True,
    )


def resolve_many(
    paths: list[str],
    settings: Settings,
    follow_symlinks: bool = False,
) -> list[PathResolution]:
    """Batch resolve multiple paths.

    Fails fast on first error.

    Args:
        paths: List of path strings to resolve
        settings: Settings object containing path configuration
        follow_symlinks: If True, resolve symlinks and check containment

    Returns:
        List of PathResolution objects

    Raises:
        PathResolutionError: On first unresolvable path
    """
    results: list[PathResolution] = []
    for path in paths:
        results.append(resolve_to_container_path(path, settings, follow_symlinks))
    return results


def get_path_resolver(
    settings: Settings = Depends(get_settings),
) -> Callable[[str], PathResolution]:
    """FastAPI dependency that returns a closure for path resolution.

    Creates a bound resolver function using the current settings.

    Args:
        settings: Injected Settings object

    Returns:
        Callable that resolves a single path string to PathResolution
    """

    def resolver(path: str) -> PathResolution:
        return resolve_to_container_path(path, settings, follow_symlinks=False)

    return resolver
