"""The per-textbook TOML files are the source of truth for built-in
textbooks. These lock the format and the parsed contents so an accidental
edit (a dropped chapter, a broken alias) fails loudly."""
import pathlib

import pytest

from nonnewtonian.textbook_toml import (
    TextbookTomlError,
    load_collection_toml,
    load_textbook_toml,
)

DATA = pathlib.Path(__file__).resolve().parents[1] / "data" / "textbooks"


def test_every_builtin_textbook_toml_loads_and_is_ordered():
    tomls = sorted(DATA.glob("*.toml"))
    assert {p.stem for p in tomls} == {"knight-calc-3rd", "knight-college-2nd", "mandi-4th"}
    for p in tomls:
        tb = load_textbook_toml(p)
        assert tb.slug == p.stem
        assert tb.title and tb.discipline == "physics"
        assert tb.toc, "TOC must not be empty"
        chapters = [r.chapter for r in tb.toc]
        assert chapters == sorted(chapters), f"{p.name} chapters out of order"


def test_knight_calc_3rd_exact_contents():
    tb = load_textbook_toml(DATA / "knight-calc-3rd.toml")
    assert tb.title.startswith("Physics for Scientists and Engineers")
    assert tb.author == "Randall D. Knight"
    assert tb.edition == "3rd Edition"
    assert len(tb.toc) == 42
    assert tb.toc[0].chapter == 1 and tb.toc[0].topics == "Motion, Velocity, Acceleration"
    # the "3rd edition" shorthand alias is marked ambiguous
    ambiguous = {a["alias"]: a["ambiguous"] for a in tb.aliases}
    assert ambiguous["Knight, 3rd edition"] == 1


def test_collection_toml_has_the_six_wanted_scientists():
    col = load_collection_toml(DATA.parent / "collection.toml")
    assert len(col["wanted"]) == 6
    assert all(w["name"] for w in col["wanted"])


def test_missing_required_field_is_a_clear_error(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text('title = "no slug here"\n', encoding="utf-8")
    with pytest.raises(TextbookTomlError, match="missing required 'slug'"):
        load_textbook_toml(bad)


def test_decreasing_chapters_rejected(tmp_path):
    bad = tmp_path / "bad.toml"
    bad.write_text(
        'slug = "x"\ntitle = "X"\n'
        "[[chapter]]\nnumber = 5\ntopics = \"a\"\n"
        "[[chapter]]\nnumber = 2\ntopics = \"b\"\n",
        encoding="utf-8",
    )
    with pytest.raises(TextbookTomlError, match="must not decrease"):
        load_textbook_toml(bad)
