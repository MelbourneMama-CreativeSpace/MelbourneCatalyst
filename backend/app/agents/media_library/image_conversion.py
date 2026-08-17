"""HEIC/HEIF -> JPEG conversion at upload time.

HEIC (Apple's default photo format on iPhones since iOS 11) has no native
decoder in any major browser — Chrome, Firefox, and Safari-on-non-Apple
all render a broken-image icon for it, confirmed live (a real chat
attachment showed exactly this). It's also not accepted by Meta's photo-
post APIs: confirmed against Instagram's real `INSTAGRAM_CREATE_MEDIA_
CONTAINER` schema, which spells out "Supported formats: JPG, PNG (WebP
not supported)" — Facebook's `FACEBOOK_CREATE_PHOTO_POST` has the same
real-world constraint. Converting once here, at upload, means every
downstream consumer (a chat thumbnail, a Content Studio preview, an
Instagram/Facebook publish) just works, instead of failing later in
however many separate places happen to render or forward the file.

`pillow-heif` registers a HEIC/HEIF codec with Pillow (`Image.open` can't
decode it on its own — HEIC's HEVC-based codec isn't in Pillow core).
Verified live on this exact platform: a prebuilt wheel, no system-level
libheif compilation needed.
"""

from __future__ import annotations

import io

import pillow_heif
from PIL import Image

pillow_heif.register_heif_opener()

_HEIC_CONTENT_TYPES = {"image/heic", "image/heif"}
_HEIC_EXTENSIONS = (".heic", ".heif")


def is_heic(filename: str, content_type: str) -> bool:
    return content_type in _HEIC_CONTENT_TYPES or filename.lower().endswith(_HEIC_EXTENSIONS)


def convert_heic_to_jpeg(content: bytes) -> bytes:
    """Decodes HEIC/HEIF bytes and re-encodes as JPEG. Raises on a
    genuinely corrupt/unreadable file — the caller decides how to
    surface that (this never silently drops the upload)."""
    image = Image.open(io.BytesIO(content))
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=90)
    return buffer.getvalue()


def heic_safe_filename(filename: str) -> str:
    """Swaps a .heic/.heif extension for .jpg — the stored filename
    should match what the bytes actually are now, not what the user's
    phone originally called it."""
    for ext in _HEIC_EXTENSIONS:
        if filename.lower().endswith(ext):
            return filename[: -len(ext)] + ".jpg"
    return filename
