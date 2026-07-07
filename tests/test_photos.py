"""Photo pipeline: URL validation (SSRF posture), magic-byte sniffing,
Pillow normalization, content-hash storage, and pptx image recovery."""

import io

import pytest
from PIL import Image

from nonnewtonian.photos import (
    PhotoError,
    extract_pptx_images,
    normalize_image,
    sniff_image_type,
    store_bytes,
    validate_url,
)

from conftest import FIXTURES


def _fake_resolver(mapping):
    def resolver(host, port):
        if host not in mapping:
            import socket

            raise socket.gaierror(host)
        return [(2, 1, 6, "", (mapping[host], port or 80))]

    return resolver


def _jpeg_bytes(width=40, height=60, color=(200, 30, 30)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (width, height), color).save(buffer, format="JPEG")
    return buffer.getvalue()


class TestValidateUrl:
    def test_rejects_non_http_schemes(self):
        for url in ["file:///etc/passwd", "gopher://x/", "ftp://x/a.jpg"]:
            with pytest.raises(PhotoError, match="http"):
                validate_url(url, resolver=_fake_resolver({}))

    def test_rejects_private_loopback_linklocal_metadata(self):
        cases = {
            "internal.example": "10.1.2.3",
            "loop.example": "127.0.0.1",
            "metadata.example": "169.254.169.254",
            "lan.example": "192.168.1.10",
        }
        for host, ip in cases.items():
            with pytest.raises(PhotoError, match="private or internal"):
                validate_url(
                    f"http://{host}/x.jpg", resolver=_fake_resolver({host: ip})
                )

    def test_accepts_global_addresses(self):
        validate_url(
            "https://photos.example/x.jpg",
            resolver=_fake_resolver({"photos.example": "93.184.216.34"}),
        )

    def test_rejects_unresolvable_host(self):
        with pytest.raises(PhotoError, match="look up"):
            validate_url("https://nope.example/x.jpg", resolver=_fake_resolver({}))


class TestImageHandling:
    def test_sniff_rejects_html_error_pages(self):
        """The original pipeline saved 404 HTML pages as test.jpg."""
        with pytest.raises(PhotoError, match="not return an image"):
            sniff_image_type(b"<!DOCTYPE html><html>404</html>")

    def test_normalize_reencodes_jpeg(self):
        data, ext, width, height = normalize_image(_jpeg_bytes())
        assert ext == "jpg" and (width, height) == (40, 60)
        Image.open(io.BytesIO(data))  # round-trips through Pillow

    def test_normalize_converts_transparent_png_to_png(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (10, 10), (0, 0, 0, 0)).save(buffer, format="PNG")
        _, ext, _, _ = normalize_image(buffer.getvalue())
        assert ext == "png"

    def test_decompression_bomb_rejected(self):
        # A tiny file that decodes to an enormous bitmap.
        buffer = io.BytesIO()
        Image.MAX_IMAGE_PIXELS = None  # allow *creating* it in the test
        try:
            Image.new("1", (40000, 40000)).save(buffer, format="PNG")
        finally:
            Image.MAX_IMAGE_PIXELS = 30_000_000
        with pytest.raises(PhotoError):
            normalize_image(buffer.getvalue())

    def test_store_bytes_content_hash_layout(self, tmp_path):
        stored = store_bytes(_jpeg_bytes(), tmp_path, original_url="http://x/a.jpg")
        assert stored.path.exists()
        assert stored.path.parent.name == stored.sha256[:2]
        assert stored.path.name == f"{stored.sha256}.jpg"
        # Idempotent: same bytes, same path, no duplicate files.
        again = store_bytes(_jpeg_bytes(), tmp_path)
        assert again.path == stored.path
        assert sum(1 for _ in tmp_path.rglob("*.jpg")) == 1


class TestPptxRecovery:
    def test_extracts_images_from_real_decks(self):
        """The existing decks are the only surviving copies of rotted
        photos; Chien-Shiung Wu's deck has two embedded photos."""
        wu = extract_pptx_images(FIXTURES / "Chien-Shiung Wu.pptx")
        assert len(wu) == 2
        for data, ext in wu:
            sniff_image_type(data)  # each is a real image
        noether = extract_pptx_images(FIXTURES / "Emmy Noether.pptx")
        assert len(noether) >= 1
