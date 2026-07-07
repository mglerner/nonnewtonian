"""Acceptance tests over the 39 real scientist files, plus the specific
bug classes the 2026-07-07 audit found in the original parser."""

from nonnewtonian import entry_to_text, parse
from nonnewtonian.parser import unwrap_paragraphs


def test_all_39_files_parse(entries):
    assert len(entries) == 39
    for name, entry in entries.items():
        assert entry.name, name


def test_corpus_field_counts(entries):
    """Counts verified by hand against the corpus on 2026-07-07."""
    assert sum(1 for e in entries.values() if e.photos) == 38
    assert sum(1 for e in entries.values() if e.sources) == 36
    assert sum(len(e.placements_raw) for e in entries.values()) == 65


def test_ursula_franklin_has_no_photo(entries):
    assert entries["UrsulaFranklin.txt"].photos == []


def test_no_space_headers_parse(entries):
    """NergisMavalvala.txt uses '#Name' style headers throughout."""
    entry = entries["NergisMavalvala.txt"]
    assert entry.name == "Nergis Mavalvala"
    assert entry.description


def test_singular_contributor_header_aliased(entries):
    """EmmyNoether.txt is the one file using '# Contributor'."""
    assert entries["EmmyNoether.txt"].contributors


def test_repeated_textbook_headers_merge(entries):
    """HadiyahGreen.txt has three '# Textbook' headers (old format);
    the original code's accumulation bug dropped repeated prose blocks."""
    entry = entries["HadiyahGreen.txt"]
    assert entry.placements_raw  # merged, not lost
    assert any(flag.startswith("merged-repeated-header") for flag in entry.flags)


def test_out_of_order_sections(entries):
    """SubrahmanyanChandrasekhar.txt puts Photo before Description."""
    entry = entries["SubrahmanyanChandrasekhar.txt"]
    assert entry.photos and entry.description


def test_repeated_description_blocks_are_merged_not_last_wins():
    """The original pipeline rendered only the LAST repeated block —
    silent loss of student prose (makesyllabus.py:136-143)."""
    text = "# Name\nA Scientist\n# Description\nFirst block.\n# Description\nSecond block.\n"
    entry = parse(text)
    joined = " ".join(entry.description)
    assert "First block." in joined and "Second block." in joined


def test_unknown_headers_preserved_in_extras():
    text = "# Name\nA Scientist\n# Quotes\nSomething memorable.\n"
    entry = parse(text)
    assert entry.extras["Quotes"] == ["Something memorable."]


def test_paragraph_unwrap_and_soft_breaks():
    lines = ["First line  ", "second line.", "", "New paragraph."]
    assert unwrap_paragraphs(lines) == ["First line second line.", "New paragraph."]


def test_hyphen_split_url_rejoined():
    """Three corpus files hard-wrap URLs at a hyphen; joining with a
    space corrupts the link (audit: HadiyahGreen, Tomonaga, WarrenHenry)."""
    lines = ["https://example.org/pioneers-", "technology-article"]
    assert unwrap_paragraphs(lines) == ["https://example.org/pioneers-technology-article"]


def test_round_trip_all_39(entries):
    """The lossless-out guarantee: parse(entry_to_text(e)) == e."""
    for name, entry in entries.items():
        assert parse(entry_to_text(entry)) == entry, name


def test_round_trip_is_fixed_point(entries):
    for name, entry in entries.items():
        once = entry_to_text(entry)
        assert entry_to_text(parse(once)) == once, name
