"""Tests for HEIC/HEIF -> JPEG conversion at upload time.

Full byte-level decoding is `pillow-heif`'s own well-established job (not
re-verified here — confirmed separately that `register_heif_opener()`
registers `.heic` with Pillow on this exact platform, a prebuilt wheel,
no system libheif compilation needed); this file exercises this app's
own logic layered on top of it.
"""

from __future__ import annotations

import io

import pytest
from PIL import Image

from app.agents.media_library import image_conversion


def test_is_heic_matches_by_content_type():
    assert image_conversion.is_heic("photo.jpg", "image/heic") is True
    assert image_conversion.is_heic("photo.jpg", "image/heif") is True


def test_is_heic_matches_by_extension_even_with_generic_content_type():
    # Confirmed real-world case: an iPhone upload can arrive with a
    # generic "application/octet-stream" content-type, extension is the
    # only reliable signal in that case.
    assert image_conversion.is_heic("IMG_1762.HEIC", "application/octet-stream") is True
    assert image_conversion.is_heic("IMG_1762.heic", "application/octet-stream") is True


def test_is_heic_false_for_ordinary_images():
    assert image_conversion.is_heic("photo.jpg", "image/jpeg") is False
    assert image_conversion.is_heic("photo.png", "image/png") is False


def test_heic_safe_filename_swaps_extension():
    assert image_conversion.heic_safe_filename("IMG_1762.HEIC") == "IMG_1762.jpg"
    assert image_conversion.heic_safe_filename("photo.heif") == "photo.jpg"


def test_heic_safe_filename_leaves_other_extensions_alone():
    assert image_conversion.heic_safe_filename("photo.png") == "photo.png"


def test_convert_heic_to_jpeg_produces_a_real_decodable_jpeg():
    """Exercises this function's own logic (decode, convert to RGB,
    re-encode as JPEG) without depending on generating a real HEIC
    fixture in this environment. `Image.open` auto-detects format from
    content rather than the function name — feeding it real, plain PNG
    bytes here proves the surrounding convert/save logic is correct;
    decoding actual HEIC bytes is pillow-heif's own job (verified
    separately: its opener registers `.heic` with Pillow on this exact
    platform), not re-tested here."""
    source = Image.new("RGB", (64, 48), color=(200, 50, 50))
    source_bytes = io.BytesIO()
    source.save(source_bytes, format="PNG")

    jpeg_bytes = image_conversion.convert_heic_to_jpeg(source_bytes.getvalue())

    result = Image.open(io.BytesIO(jpeg_bytes))
    assert result.format == "JPEG"
    assert result.size == (64, 48)


def test_convert_heic_to_jpeg_raises_on_unreadable_bytes():
    with pytest.raises(Exception):
        image_conversion.convert_heic_to_jpeg(b"not a real image at all")
