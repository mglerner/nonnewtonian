"""M6: the WordPress-embeddable class view (framable, auto-resizing) and
the copy-paste snippet."""

from pathlib import Path

import pytest

from nonnewtonian import db as db_mod
from nonnewtonian.web import create_app
from nonnewtonian.web.views_manage import _embed_snippet

NOW = "2026-07-07T00:00:00+00:00"


@pytest.fixture
def app(tmp_path):
    db_path = tmp_path / "m6.db"
    conn = db_mod.init_db(db_path, now=NOW)
    conn.execute("INSERT INTO textbooks(slug,title,is_builtin,created_at) VALUES('bk','Book',1,?)", (NOW,))
    tid = conn.execute("SELECT id FROM textbooks WHERE slug='bk'").fetchone()[0]
    for ch in range(1, 4):
        conn.execute("INSERT INTO toc_rows(textbook_id,sort_order,chapter,topics) VALUES(?,?,?,?)", (tid, ch, ch, f"T{ch}"))
    conn.commit(); conn.close()
    app = create_app({"DB_PATH": str(db_path), "PHOTO_DIR": str(tmp_path / "p"),
                      "TESTING": True, "WTF_CSRF_ENABLED": False, "SITE_URL": "https://nonnewtonian.org"})
    app._db_path = str(db_path)
    return app


@pytest.fixture
def slug(app):
    c = app.test_client()
    c.post("/new", data={"name": "P121", "textbook_mode": "builtin", "textbook_slug": "bk"})
    return db_mod.connect(app._db_path).execute("SELECT slug FROM collections").fetchone()[0]


def test_embed_is_framable_and_chromeless(app, slug):
    r = app.test_client().get(f"/c/{slug}/embed")
    assert r.status_code == 200
    assert "frame-ancestors" in r.headers.get("Content-Security-Policy", "")
    assert r.headers.get("X-Frame-Options") is None  # NOT denied, unlike other pages
    assert b'class="embed"' in r.data           # header/footer hidden
    assert b"nnpEmbed" in r.data                 # height-reporting script present


def test_embed_reports_its_own_slug_for_height_targeting(app, slug):
    r = app.test_client().get(f"/c/{slug}/embed")
    assert slug.encode() in r.data


def test_snippet_has_origin_checked_resizer(app):
    with app.test_request_context():
        s = _embed_snippet("cls-1234")
    assert 'id="nnp-cls-1234"' in s
    assert "e.origin !== 'https://nonnewtonian.org'" in s   # origin guard
    assert 'd.nnpEmbed === "cls-1234"' in s                 # only this embed resizes this iframe
    assert "/c/cls-1234/embed" in s


def test_snippet_without_site_url_omits_origin_guard_but_still_resizes(tmp_path):
    app = create_app({"DB_PATH": str(tmp_path / "x.db"), "PHOTO_DIR": str(tmp_path / "p"),
                      "TESTING": True})  # no SITE_URL
    with app.test_request_context():
        s = _embed_snippet("cls-9")
    assert "e.origin" not in s
    assert "d.height" in s
