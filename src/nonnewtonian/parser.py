"""Parse and round-trip the NonNewtonian scientist text-file format.

The format is the one used by mglerner/IntroductoryPhysics since 2016::

    # Name
    Margaret Murnane
    # Textbook
    Knight, ..., Chapter 32, section 2
    # Description
    Words words words...

    More words after a blank line.
    # Sources
    https://en.wikipedia.org/wiki/Margaret_Murnane
    # Photo
    https://example.edu/murnane.jpg

Real files vary (audited 2026-07-07 across the 39-file corpus), and this
parser must accept all of it without silently dropping anything:

- headers appear as ``# Name`` and ``#Name``, any case, with trailing
  markdown soft-break spaces;
- one file uses singular ``# Contributor`` (aliased to Contributors);
- the same header may repeat within a file (old format); repeated blocks
  are MERGED, never last-wins (the original pipeline lost data here);
- blocks appear in any order and any block except Name may be missing;
- body text is hard-wrapped at ~72 columns with blank lines separating
  real paragraphs, so prose blocks are unwrapped into paragraphs;
- unknown headers are preserved verbatim in ``Entry.extras``.

``parse(entry_to_text(e)) == e`` holds for every entry: ``entry_to_text``
emits the canonical form and parsing is a fixed point on it.  This is the
lossless-out guarantee — an entry can always leave the system as a plain
text file in the original format.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# Headers with dedicated Entry fields.  Everything else lands in extras.
_KNOWN = {"name", "textbook", "description", "sources", "photo", "contributors"}
_ALIASES = {
    "contributor": "contributors",  # EmmyNoether.txt uses the singular
    "photos": "photo",
    "source": "sources",
    "textbooks": "textbook",
}
# Line-per-item blocks; the rest are prose and get paragraph-unwrapped.
_LINE_BLOCKS = {"name", "textbook", "photo", "contributors"}

_CANONICAL_TITLES = {
    "name": "Name",
    "textbook": "Textbook",
    "description": "Description",
    "sources": "Sources",
    "photo": "Photo",
    "contributors": "Contributors",
}
# Canonical emit order (matches the original ExampleScientist.txt).
_EMIT_ORDER = ["name", "textbook", "description", "sources", "photo", "contributors"]


class ParseError(ValueError):
    """Raised when a file cannot be parsed as a scientist entry at all."""


@dataclass
class Entry:
    """One scientist entry in canonical form.

    ``flags`` records parse events worth human review (merged repeated
    headers, extra lines under Name, ...).  It is deliberately excluded
    from equality so the round-trip guarantee compares content only:
    the canonical text has no repeated headers, so re-parsing it cannot
    reproduce the original file's flags.
    """

    name: str
    placements_raw: list[str] = field(default_factory=list)
    description: list[str] = field(default_factory=list)  # paragraphs
    sources: list[str] = field(default_factory=list)  # paragraphs
    photos: list[str] = field(default_factory=list)  # one URL/line each
    contributors: list[str] = field(default_factory=list)
    extras: dict[str, list[str]] = field(default_factory=dict)  # header -> paragraphs
    flags: list[str] = field(default_factory=list, compare=False)


def _normalize_header(raw_header: str) -> tuple[str, str]:
    """Return (canonical_key, display_title) for a ``#``-prefixed line."""
    title = raw_header.lstrip("#").strip()
    key = title.casefold()
    key = _ALIASES.get(key, key)
    if key in _KNOWN:
        return key, _CANONICAL_TITLES[key]
    return key, title


def iter_blocks(text: str):
    """Yield (raw_header_line, [body lines]) in file order.

    Lines before the first header are yielded under a None header so
    callers can decide what to do with stray preamble text.
    """
    header = None
    body: list[str] = []
    for line in text.split("\n"):
        if line.startswith("#"):
            if header is not None or body:
                yield header, body
            header, body = line, []
        else:
            body.append(line)
    if header is not None or body:
        yield header, body


def _join_wrapped(pieces: list[str]) -> str:
    """Join stripped lines of one paragraph with spaces — except when a
    line broke inside a URL: three files in the corpus hard-wrap URLs at
    a hyphen (``...pioneers-`` / ``technology-...``), and joining those
    with a space corrupts the link.  If the accumulating text ends in a
    URL token that ends with ``-``, the next line continues it directly.
    """
    text = ""
    for piece in pieces:
        if not text:
            text = piece
            continue
        last_token = text.rsplit(None, 1)[-1]
        if "://" in last_token and last_token.endswith("-"):
            text += piece
        else:
            text += " " + piece
    return text


def unwrap_paragraphs(lines: list[str]) -> list[str]:
    """Join hard-wrapped lines into paragraphs; blank lines separate them.

    Trailing whitespace (including markdown two-space soft breaks) is
    stripped per line before joining.
    """
    paragraphs: list[str] = []
    current: list[str] = []
    for line in lines:
        stripped = line.strip()
        if stripped:
            current.append(stripped)
        elif current:
            paragraphs.append(_join_wrapped(current))
            current = []
    if current:
        paragraphs.append(_join_wrapped(current))
    return paragraphs


def _nonempty_lines(lines: list[str]) -> list[str]:
    return [line.strip() for line in lines if line.strip()]


def parse(text: str) -> Entry:
    """Parse one scientist file's text into an Entry.

    Never drops content: repeated blocks merge, unknown headers go to
    extras, and anything surprising adds a flag instead of vanishing.
    """
    blocks: dict[str, list[str]] = {}
    display_titles: dict[str, str] = {}
    flags: list[str] = []

    for raw_header, body in iter_blocks(text):
        if raw_header is None:
            if _nonempty_lines(body):
                blocks.setdefault("_preamble", []).extend(body)
                flags.append("text-before-first-header")
            continue
        key, title = _normalize_header(raw_header)
        display_titles.setdefault(key, title)
        if key in blocks:
            # Old-format files repeat headers (sometimes with empty
            # bodies); merging is silent data loss territory in the
            # original pipeline, so any repeat is flagged for review.
            flags.append(f"merged-repeated-header:{title}")
            # Blank separator keeps paragraph boundaries between merged blocks.
            blocks[key].append("")
        blocks.setdefault(key, []).extend(body)

    name_lines = _nonempty_lines(blocks.pop("name", []))
    if not name_lines:
        raise ParseError(
            "no '# Name' block found; headers present: "
            + ", ".join(sorted(display_titles.values()))
        )
    if len(name_lines) > 1:
        flags.append("extra-lines-under-name")
    name = name_lines[0]

    entry = Entry(
        name=name,
        placements_raw=_nonempty_lines(blocks.pop("textbook", [])),
        description=unwrap_paragraphs(blocks.pop("description", [])),
        sources=unwrap_paragraphs(blocks.pop("sources", [])),
        photos=_nonempty_lines(blocks.pop("photo", [])),
        contributors=_nonempty_lines(blocks.pop("contributors", [])),
        flags=flags,
    )
    # Extra name lines are preserved, not dropped.
    if len(name_lines) > 1:
        entry.extras["Name notes"] = name_lines[1:]
    preamble = blocks.pop("_preamble", None)
    if preamble:
        entry.extras["Preamble"] = unwrap_paragraphs(preamble)
    for key, body in blocks.items():
        content = unwrap_paragraphs(body)
        if content:
            entry.extras[display_titles[key]] = content
    return entry


def parse_file(path) -> Entry:
    """Parse a scientist file from disk (UTF-8, NFC-normalized)."""
    import unicodedata

    with open(path, encoding="utf-8") as handle:
        return parse(unicodedata.normalize("NFC", handle.read()))


def entry_to_text(entry: Entry) -> str:
    """Emit the canonical plain-text form of an entry.

    ``parse(entry_to_text(e)) == e`` for all entries (flags excluded).
    """
    chunks: list[str] = []

    def block(title: str, paragraphs: list[str]) -> None:
        if paragraphs:
            chunks.append(f"# {title}\n" + "\n\n".join(paragraphs))

    block("Name", [entry.name])
    block("Textbook", ["\n".join(entry.placements_raw)] if entry.placements_raw else [])
    block("Description", entry.description)
    block("Sources", entry.sources)
    block("Photo", ["\n".join(entry.photos)] if entry.photos else [])
    block("Contributors", ["\n".join(entry.contributors)] if entry.contributors else [])
    for title, paragraphs in entry.extras.items():
        block(title, paragraphs)
    return "\n\n".join(chunks) + "\n"
