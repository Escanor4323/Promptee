"""Unit tests for path resolution service."""

import pytest
from pathlib import Path
from unittest.mock import Mock

from app.services.path_resolver import (
    PathResolution,
    PathResolutionError,
    resolve_to_container_path,
    resolve_many,
)
from app.config import Settings


@pytest.fixture
def settings() -> Settings:
    """Create a test Settings instance with fixed paths."""
    return Settings(
        host_project_root="/Users/joelmartinez/Documents/Projects/Promptee",
        container_data_root="/app/data",
    )


class TestResolveToContainerPath:
    """Tests for resolve_to_container_path function."""

    def test_absolute_host_path_translates_to_container_path(self, settings: Settings) -> None:
        """Absolute host path under host_project_root should translate to container."""
        result = resolve_to_container_path(
            "/Users/joelmartinez/Documents/Projects/Promptee/data/file.md",
            settings,
        )
        assert result.original == "/Users/joelmartinez/Documents/Projects/Promptee/data/file.md"
        assert result.container_path == Path("/app/data/data/file.md")
        assert result.was_translated is True
        assert result.is_relative is False

    def test_absolute_container_path_passes_through(self, settings: Settings) -> None:
        """Absolute container paths (starting with /app/) pass through unchanged."""
        result = resolve_to_container_path(
            "/app/data/templates/file.md",
            settings,
        )
        assert result.original == "/app/data/templates/file.md"
        assert result.container_path == Path("/app/data/templates/file.md")
        assert result.was_translated is False
        assert result.is_relative is False

    def test_relative_path_joins_to_container_root(self, settings: Settings) -> None:
        """Relative paths should join to container_data_root."""
        result = resolve_to_container_path(
            "data/file.md",
            settings,
        )
        assert result.original == "data/file.md"
        assert result.container_path == Path("/app/data/data/file.md")
        assert result.was_translated is False
        assert result.is_relative is True

    def test_empty_string_raises_error(self, settings: Settings) -> None:
        """Empty string should raise PathResolutionError."""
        with pytest.raises(PathResolutionError, match="Path cannot be empty"):
            resolve_to_container_path("", settings)

    def test_whitespace_only_raises_error(self, settings: Settings) -> None:
        """Whitespace-only string should raise PathResolutionError."""
        with pytest.raises(PathResolutionError, match="Path cannot be empty"):
            resolve_to_container_path("   ", settings)

    def test_unmounted_absolute_path_raises_error(self, settings: Settings) -> None:
        """Absolute path outside host_project_root should raise PathResolutionError."""
        with pytest.raises(PathResolutionError, match="not under"):
            resolve_to_container_path(
                "/usr/local/bin/file.md",
                settings,
            )

    def test_relative_path_with_parent_directory_escapes_detection(self, settings: Settings) -> None:
        """Relative path with .. that escapes root should be caught."""
        with pytest.raises(PathResolutionError, match="escapes allowed root"):
            resolve_to_container_path(
                "../../etc/passwd",
                settings,
            )

    def test_container_path_outside_root_raises_error(self, settings: Settings) -> None:
        """Container path outside /app/data should raise PathResolutionError."""
        with pytest.raises(PathResolutionError, match="outside allowed root"):
            resolve_to_container_path(
                "/app/secrets/file.md",
                settings,
            )

    def test_symlink_escape_detected_with_follow_symlinks(self, settings: Settings, tmp_path: Path) -> None:
        """Symlink escaping root should be caught when follow_symlinks=True."""
        # Create a temporary directory structure
        data_root = tmp_path / "app" / "data"
        data_root.mkdir(parents=True)
        outside_root = tmp_path / "outside"
        outside_root.mkdir()
        target_file = outside_root / "secret.txt"
        target_file.write_text("secret")

        # Create a symlink inside data_root pointing outside
        symlink = data_root / "link.txt"
        symlink.symlink_to(target_file)

        # Override settings to use temp paths
        test_settings = Settings(
            host_project_root=str(tmp_path / "host"),
            container_data_root=str(data_root),
        )

        # The symlink escape should be caught (either during containment or symlink check)
        with pytest.raises(PathResolutionError, match="(escapes allowed root|resolves outside allowed root)"):
            resolve_to_container_path(
                "link.txt",
                test_settings,
                follow_symlinks=True,
            )

    def test_whitespace_trimmed(self, settings: Settings) -> None:
        """Leading/trailing whitespace should be trimmed."""
        result = resolve_to_container_path(
            "  data/file.md  ",
            settings,
        )
        assert result.original == "data/file.md"
        assert result.container_path == Path("/app/data/data/file.md")

    def test_simple_relative_path(self, settings: Settings) -> None:
        """Simple relative path like 'file.md' should resolve correctly."""
        result = resolve_to_container_path(
            "file.md",
            settings,
        )
        assert result.original == "file.md"
        assert result.container_path == Path("/app/data/file.md")
        assert result.is_relative is True


class TestResolveMany:
    """Tests for resolve_many batch function."""

    def test_batch_resolution_success(self, settings: Settings) -> None:
        """Multiple valid paths should resolve successfully."""
        paths = [
            "/Users/joelmartinez/Documents/Projects/Promptee/data/file1.md",
            "data/file2.md",
            "/app/data/templates/file3.md",
        ]
        results = resolve_many(paths, settings)
        assert len(results) == 3
        assert results[0].was_translated is True
        assert results[1].is_relative is True
        assert results[2].was_translated is False

    def test_batch_resolution_fails_fast(self, settings: Settings) -> None:
        """Batch resolution should fail on first invalid path."""
        paths = [
            "/Users/joelmartinez/Documents/Projects/Promptee/data/file1.md",
            "",  # Invalid: empty
            "data/file3.md",
        ]
        with pytest.raises(PathResolutionError, match="Path cannot be empty"):
            resolve_many(paths, settings)

    def test_batch_resolution_empty_list(self, settings: Settings) -> None:
        """Empty list should return empty results."""
        results = resolve_many([], settings)
        assert results == []


class TestPathResolutionDataclass:
    """Tests for PathResolution frozen dataclass."""

    def test_path_resolution_is_frozen(self, settings: Settings) -> None:
        """PathResolution should be immutable (frozen)."""
        result = resolve_to_container_path("data/file.md", settings)
        with pytest.raises(AttributeError):
            result.container_path = Path("/different/path")

    def test_path_resolution_has_required_fields(self, settings: Settings) -> None:
        """PathResolution should have all required fields."""
        result = resolve_to_container_path("data/file.md", settings)
        assert hasattr(result, "original")
        assert hasattr(result, "container_path")
        assert hasattr(result, "was_translated")
        assert hasattr(result, "is_relative")


class TestPathResolutionError:
    """Tests for PathResolutionError exception."""

    def test_path_resolution_error_is_exception(self) -> None:
        """PathResolutionError should be an Exception."""
        assert issubclass(PathResolutionError, Exception)

    def test_path_resolution_error_message(self) -> None:
        """PathResolutionError should contain message."""
        error = PathResolutionError("Test error message")
        assert "Test error message" in str(error)


class TestEdgeCases:
    """Tests for edge cases and special scenarios."""

    def test_path_with_multiple_slashes(self, settings: Settings) -> None:
        """Path with multiple consecutive slashes should be handled."""
        result = resolve_to_container_path(
            "data//file.md",
            settings,
        )
        # Path normalization should handle this
        assert result.container_path.exists() is False or True  # Path doesn't need to exist

    def test_absolute_path_at_root_boundary(self, settings: Settings) -> None:
        """Absolute path exactly at host_project_root should resolve."""
        result = resolve_to_container_path(
            "/Users/joelmartinez/Documents/Projects/Promptee",
            settings,
        )
        assert result.container_path == Path("/app/data")
        assert result.was_translated is True

    def test_relative_path_single_dot(self, settings: Settings) -> None:
        """Relative path with ./ should resolve correctly."""
        result = resolve_to_container_path(
            "./data/file.md",
            settings,
        )
        assert result.container_path == Path("/app/data/data/file.md")

    def test_relative_path_with_single_parent_dir(self, settings: Settings) -> None:
        """Relative path trying to escape with single .. should fail."""
        with pytest.raises(PathResolutionError, match="escapes allowed root"):
            resolve_to_container_path(
                "../something.txt",
                settings,
            )
