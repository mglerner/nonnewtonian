"""Photo fetching, validation, normalization, and content-hash storage.

Replaces the original pipeline's photo handling, whose audited failure
modes were: a shared ``test.jpg`` temp file, no timeout, no status
check (404 HTML pages saved as "images"), every photo re-downloaded on
every run, and hotlinked display URLs of which roughly half have rotted.

Here: a URL is fetched once, validated by magic bytes, re-encoded by
Pillow (which also defuses decompression bombs and exotic payloads), and
stored under a content-hash filename.  Display and slide generation only
ever touch the local file.

SSRF posture (per the plan's adversarial review): ``validate_url``
rejects non-http(s) schemes and any hostname resolving to a private,
loopback, link-local, or otherwise non-global address; ``fetch_photo``
follows redirects manually and re-validates every hop, and reads the
body as a capped stream.  Residual TOCTOU (DNS rebinding between the
resolve-check and the connect) is NOT fully closed here — pinning the
connection to the vetted IP is wired up in the web app (M4), where the
plan's SSRF verify step gates it.  Flagged, not hidden.
"""

from __future__ import annotations

import hashlib
import io
import ipaddress
import socket
import warnings
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image

# A generous ceiling for legitimate portraits; a hard error beyond it.
Image.MAX_IMAGE_PIXELS = 30_000_000
warnings.simplefilter("error", Image.DecompressionBombWarning)

MAX_BYTES = 8 * 1024 * 1024
FETCH_TIMEOUT = 5.0
MAX_REDIRECTS = 5

_MAGIC = {
    b"\xff\xd8\xff": "jpg",
    b"\x89PNG\r\n\x1a\n": "png",
    b"GIF87a": "gif",
    b"GIF89a": "gif",
    b"RIFF": "webp",  # checked more precisely below
}


class PhotoError(ValueError):
    """A photo URL or payload was rejected; message says why, plainly."""


@dataclass
class StoredPhoto:
    path: Path
    original_url: str | None
    content_type: str
    width: int
    height: int
    sha256: str


def validate_url(url: str, *, resolver=socket.getaddrinfo) -> None:
    """Reject URLs this server must never fetch.  Raises PhotoError."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise PhotoError(f"Only http/https photo links work (got {parsed.scheme!r}).")
    if not parsed.hostname:
        raise PhotoError("That link has no host name.")
    try:
        infos = resolver(parsed.hostname, parsed.port or 0)
    except socket.gaierror:
        raise PhotoError(f"Could not look up {parsed.hostname!r}.") from None
    if not infos:
        raise PhotoError(f"Could not look up {parsed.hostname!r}.")
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise PhotoError(
                "That link points at a private or internal address, "
                "which this site will not fetch."
            )


def sniff_image_type(data: bytes) -> str:
    """Return an extension for known image magic bytes, else raise."""
    for magic, ext in _MAGIC.items():
        if data.startswith(magic):
            if ext == "webp" and data[8:12] != b"WEBP":
                continue
            return ext
    raise PhotoError(
        "That link did not return an image file (it may be an error page "
        "or a web page around the image — link directly to the image)."
    )


def normalize_image(data: bytes) -> tuple[bytes, str, int, int]:
    """Re-encode through Pillow: validates the file deeply, strips exotic
    payloads/metadata, converts to slide-safe JPEG (or PNG when there is
    transparency).  Returns (bytes, extension, width, height)."""
    sniff_image_type(data)
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            has_alpha = image.mode in ("RGBA", "LA", "P") and (
                image.mode != "P" or "transparency" in image.info
            )
            buffer = io.BytesIO()
            if has_alpha:
                image.convert("RGBA").save(buffer, format="PNG")
                ext = "png"
            else:
                image.convert("RGB").save(buffer, format="JPEG", quality=90)
                ext = "jpg"
            return buffer.getvalue(), ext, image.width, image.height
    except PhotoError:
        raise
    except Image.DecompressionBombWarning:
        raise PhotoError("That image is implausibly large.") from None
    except Exception as exc:  # Pillow raises many types on bad files
        raise PhotoError(f"Could not read that image file ({exc}).") from None


def store_bytes(data: bytes, dest_dir: Path, *, original_url: str | None = None) -> StoredPhoto:
    """Normalize and write image bytes under a content-hash filename."""
    normalized, ext, width, height = normalize_image(data)
    digest = hashlib.sha256(normalized).hexdigest()
    subdir = Path(dest_dir) / digest[:2]
    subdir.mkdir(parents=True, exist_ok=True)
    path = subdir / f"{digest}.{ext}"
    if not path.exists():
        path.write_bytes(normalized)
    return StoredPhoto(
        path=path,
        original_url=original_url,
        content_type=f"image/{'jpeg' if ext == 'jpg' else ext}",
        width=width,
        height=height,
        sha256=digest,
    )


def fetch_photo(url: str, dest_dir: Path, *, session: requests.Session | None = None,
                resolver=socket.getaddrinfo) -> StoredPhoto:
    """Fetch, validate, normalize, and store one remote photo."""
    session = session or requests.Session()
    current = url
    for _ in range(MAX_REDIRECTS + 1):
        validate_url(current, resolver=resolver)
        response = session.get(
            current, stream=True, timeout=FETCH_TIMEOUT, allow_redirects=False
        )
        if response.is_redirect or response.is_permanent_redirect:
            location = response.headers.get("Location")
            if not location:
                raise PhotoError("The link redirected without a destination.")
            current = requests.compat.urljoin(current, location)
            continue
        if response.status_code != 200:
            raise PhotoError(
                f"The link returned HTTP {response.status_code} instead of an image."
            )
        data = b""
        for chunk in response.iter_content(chunk_size=65536):
            data += chunk
            if len(data) > MAX_BYTES:
                raise PhotoError(
                    f"That image is larger than {MAX_BYTES // (1024 * 1024)} MB."
                )
        return store_bytes(data, dest_dir, original_url=url)
    raise PhotoError("Too many redirects.")


def extract_pptx_images(pptx_path) -> list[tuple[bytes, str]]:
    """Pull embedded images out of a .pptx (a zip) — the only surviving
    copies of photos whose source URLs have rotted.  Returns
    [(bytes, extension), ...] in archive order."""
    import zipfile

    images: list[tuple[bytes, str]] = []
    with zipfile.ZipFile(pptx_path) as archive:
        for name in sorted(archive.namelist()):
            if name.startswith("ppt/media/"):
                ext = name.rsplit(".", 1)[-1].lower()
                if ext in {"jpg", "jpeg", "png", "gif", "webp"}:
                    images.append((archive.read(name), "jpg" if ext == "jpeg" else ext))
    return images
