"""Tests for PDF parsing service."""

import tempfile
from pathlib import Path

import pytest

from app.services.pdf_parser import extract_text, is_pdf


class TestIsPdf:
    """Test PDF detection by extension and magic bytes."""

    def test_is_pdf_valid_extension(self, tmp_path):
        """Valid .pdf file with PDF magic bytes."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\n%example")
        assert is_pdf(str(pdf_file)) is True

    def test_is_pdf_wrong_extension(self, tmp_path):
        """File with PDF content but wrong extension."""
        txt_file = tmp_path / "test.txt"
        txt_file.write_bytes(b"%PDF-1.4\n%example")
        assert is_pdf(str(txt_file)) is False

    def test_is_pdf_wrong_magic_bytes(self, tmp_path):
        """File with .pdf extension but wrong magic bytes."""
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"Not a PDF\n%example")
        assert is_pdf(str(pdf_file)) is False

    def test_is_pdf_nonexistent_file(self):
        """Nonexistent file returns False."""
        assert is_pdf("/nonexistent/file.pdf") is False


class TestExtractText:
    """Test PDF text extraction."""

    def test_extract_text_nonexistent_file(self):
        """Raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            extract_text("/nonexistent/file.pdf")

    def test_extract_text_invalid_file(self, tmp_path):
        """Raises ValueError for invalid PDF."""
        invalid_file = tmp_path / "invalid.pdf"
        invalid_file.write_bytes(b"Not a real PDF")
        with pytest.raises(ValueError):
            extract_text(str(invalid_file))

    def test_extract_text_requires_pypdf(self, monkeypatch):
        """ImportError if pypdf is not available."""
        import builtins
        original_import = builtins.__import__

        def mock_import(name, *args, **kwargs):
            if name == "pypdf":
                raise ImportError("pypdf not installed")
            return original_import(name, *args, **kwargs)

        monkeypatch.setattr("builtins.__import__", mock_import)
        with pytest.raises(ImportError, match="pypdf"):
            extract_text("/some/file.pdf")
