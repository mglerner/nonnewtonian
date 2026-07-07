"""TOC validation: the Knight CSV loads verbatim; the corrupted M&I CSV
is rejected loudly and loads 23 chapters after repair."""

import pytest

from nonnewtonian import TocError, load_toc, load_toc_file, repair_doubled_quotes

from conftest import FIXTURES


def test_knight_csv_loads_42_chapters():
    rows = load_toc_file(FIXTURES / "Knight3rdEdition.csv")
    assert [row.chapter for row in rows] == list(range(1, 43))
    assert all(row.section is None for row in rows)  # 100% blank, audited
    assert rows[2].topics == "Vectors"


def test_broken_mandi_csv_is_rejected_readably():
    """The original file's doubled quotes fold 23 chapters into 13
    records; the old pipeline would have published that silently."""
    text = (FIXTURES / "MandI4thEdition.csv").read_text()
    with pytest.raises(TocError) as excinfo:
        load_toc(text)
    # The message is for teachers, not tracebacks.
    assert "line break" in str(excinfo.value) or "quoting" in str(excinfo.value)


def test_repaired_mandi_csv_loads_23_chapters():
    text = (FIXTURES / "MandI4thEdition.csv").read_text()
    rows = load_toc(repair_doubled_quotes(text))
    assert [row.chapter for row in rows] == list(range(1, 24))
    assert rows[0].topics == "Interactions and Motion"
    assert rows[1].topics == "The Momentum Principle"  # the swallowed chapter


def test_wrong_header_rejected():
    with pytest.raises(TocError, match="Chapter,Section,Topics"):
        load_toc("Ch,Sec,Top\n1,,Stuff\n")


def test_non_numeric_chapter_rejected():
    with pytest.raises(TocError, match="whole number"):
        load_toc('Chapter,Section,Topics\none,,"Motion"\n')


def test_decreasing_chapters_rejected():
    with pytest.raises(TocError, match="must not decrease"):
        load_toc('Chapter,Section,Topics\n2,,"B"\n1,,"A"\n')


def test_blank_lines_skipped():
    rows = load_toc('Chapter,Section,Topics\n1,,"A"\n\n2,,"B"\n')
    assert len(rows) == 2


def test_sections_load_when_present():
    rows = load_toc('Chapter,Section,Topics\n1,1,"A"\n1,2,"B"\n')
    assert [row.section for row in rows] == [1, 2]
