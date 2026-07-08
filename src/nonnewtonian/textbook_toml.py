"""Canonical built-in textbook definitions in TOML (prototype).

Today a built-in textbook is split across two files: an entry in
``data/textbooks/manifest.json`` (slug/title/author/edition/discipline +
aliases) and a separate ``<slug>.csv`` holding the table of contents. CSV is
the right INPUT format for a teacher pasting a real TOC out of a spreadsheet
(that path stays in ``toc.py``), but it is a poor SOURCE-OF-TRUTH format: the
quoting is fragile (see ``toc.repair_doubled_quotes``, which exists only to
undo a CSV export bug), it can't carry per-textbook metadata, and it doesn't
diff cleanly.

This module reads a single ``<slug>.toml`` per textbook that consolidates all
of it. ``seed_import`` loads these directly (one file per built-in textbook in
``data/textbooks/``), plus ``data/collection.toml`` for the collection-level
seed data (wanted scientists) that used to live in ``manifest.json``.

Format (see ``data/textbooks/knight-calc-3rd.toml``)::

    slug = "knight-calc-3rd"
    title = "Physics for Scientists and Engineers ..."
    author = "Randall D. Knight"
    edition = "3rd Edition"
    discipline = "physics"

    [[alias]]                 # free-text names that match a placement line
    text = "Knight, 3rd edition"
    ambiguous = true          # too generic to auto-match on its own

    [[chapter]]               # table of contents, in order
    number = 1
    topics = "Motion, Velocity, Acceleration"
    # section = 3             # optional; omit for a chapter-level row
"""
from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .toc import TocRow


class TextbookTomlError(ValueError):
    """A textbook .toml is missing a required field or has a bad TOC."""


@dataclass
class TextbookDef:
    slug: str
    title: str
    author: str | None
    edition: str | None
    discipline: str
    # Shaped exactly like the manifest so a caller can treat both the same:
    # aliases as {"alias": str, "ambiguous": 0|1}, toc as TocRow list.
    aliases: list[dict] = field(default_factory=list)
    toc: list[TocRow] = field(default_factory=list)


def load_textbook_toml(path: str | Path) -> TextbookDef:
    path = Path(path)
    data = tomllib.loads(path.read_text(encoding="utf-8"))

    for required in ("slug", "title"):
        if not data.get(required):
            raise TextbookTomlError(f"{path.name}: missing required '{required}'")

    aliases = []
    for i, alias in enumerate(data.get("alias", []), start=1):
        if not alias.get("text"):
            raise TextbookTomlError(f"{path.name}: alias #{i} has no 'text'")
        aliases.append({"alias": alias["text"], "ambiguous": int(bool(alias.get("ambiguous", False)))})

    toc: list[TocRow] = []
    previous_chapter = 0
    for i, row in enumerate(data.get("chapter", []), start=1):
        if "number" not in row:
            raise TextbookTomlError(f"{path.name}: TOC entry #{i} has no 'number'")
        if not isinstance(row["number"], int):
            raise TextbookTomlError(f"{path.name}: TOC entry #{i} 'number' must be an integer")
        if row["number"] < previous_chapter:
            raise TextbookTomlError(
                f"{path.name}: chapter {row['number']} comes after chapter "
                f"{previous_chapter}; chapters must not decrease."
            )
        previous_chapter = row["number"]
        section = row.get("section")
        if section is not None and not isinstance(section, int):
            raise TextbookTomlError(f"{path.name}: TOC entry #{i} 'section' must be an integer")
        toc.append(TocRow(chapter=row["number"], section=section, topics=row.get("topics", "")))

    return TextbookDef(
        slug=data["slug"],
        title=data["title"],
        author=data.get("author"),
        edition=data.get("edition"),
        discipline=data.get("discipline", "physics"),
        aliases=aliases,
        toc=toc,
    )


def load_collection_toml(path: str | Path) -> dict:
    """Collection-level seed data that isn't tied to one textbook. Returns
    ``{"wanted": [{"name","note","source"}...], "planned": [{"slug","note"}...]}``
    shaped like the old manifest so the importer consumes it unchanged.
    A missing file is fine (returns empty lists)."""
    path = Path(path)
    if not path.exists():
        return {"wanted": [], "planned": []}
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    wanted = [
        {"name": w["name"], "note": w.get("note"), "source": w.get("source")}
        for w in data.get("wanted_scientist", [])
    ]
    planned = [
        {"slug": p.get("slug"), "note": p.get("note")}
        for p in data.get("planned_textbook", [])
    ]
    return {"wanted": wanted, "planned": planned}
