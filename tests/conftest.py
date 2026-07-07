from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SCIENTISTS = FIXTURES / "scientists"


@pytest.fixture(scope="session")
def scientist_paths() -> list[Path]:
    paths = sorted(SCIENTISTS.glob("*.txt"))
    assert len(paths) == 39, "the acceptance corpus is the 39 real files"
    return paths


@pytest.fixture(scope="session")
def entries(scientist_paths):
    from nonnewtonian import parse_file

    return {path.name: parse_file(path) for path in scientist_paths}
