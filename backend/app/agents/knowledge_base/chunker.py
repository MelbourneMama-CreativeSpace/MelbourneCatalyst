"""Text chunking — thin wrapper over LangChain's RecursiveCharacterTextSplitter.

Using only `langchain-text-splitters` (not the full LangChain runtime),
which is a small utility library with a hardened, well-tested splitter.
Rebuilding this ourselves would just reproduce its edge cases.
"""

from __future__ import annotations

from langchain_text_splitters import RecursiveCharacterTextSplitter

# 1000 chars / 100 overlap are the widely-used defaults for retrieval over
# medium-length web text; small enough for voyage-3-lite's 32k context to
# fit many at once, big enough to hold a meaningful passage.
_DEFAULT_CHUNK_SIZE = 1000
_DEFAULT_CHUNK_OVERLAP = 100


def chunk_text(
    text: str,
    *,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split `text` into overlapping chunks. Returns an empty list on empty input."""
    if not text or not text.strip():
        return []
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
    )
    return splitter.split_text(text)
