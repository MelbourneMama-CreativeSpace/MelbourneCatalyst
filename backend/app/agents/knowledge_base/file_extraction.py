"""Plain-text extraction for the business document uploader.

Dispatches on the uploaded filename's extension. Each extractor is
synchronous (both `pypdf` and `python-docx` are) — the caller is
responsible for running this off the event loop (`asyncio.to_thread`) for
large files.
"""

from __future__ import annotations

import io

from docx import Document as DocxDocument
from pypdf import PdfReader

_TEXT_EXTENSIONS = (".txt", ".md")


class UnsupportedFileTypeError(ValueError):
    def __init__(self, filename: str) -> None:
        super().__init__(f"Unsupported file type: {filename}")


def extract_text_from_upload(filename: str, content: bytes) -> str:
    """Extract plain text from uploaded file bytes. Raises
    `UnsupportedFileTypeError` for anything other than .pdf/.docx/.txt/.md."""
    lowered = filename.lower()
    if lowered.endswith(".pdf"):
        return _extract_pdf(content)
    if lowered.endswith(".docx"):
        return _extract_docx(content)
    if lowered.endswith(_TEXT_EXTENSIONS):
        return content.decode("utf-8", errors="replace")
    raise UnsupportedFileTypeError(filename)


def _extract_pdf(content: bytes) -> str:
    reader = PdfReader(io.BytesIO(content))
    return "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_docx(content: bytes) -> str:
    document = DocxDocument(io.BytesIO(content))
    return "\n\n".join(p.text for p in document.paragraphs if p.text.strip()).strip()
