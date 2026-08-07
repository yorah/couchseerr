import json
import pathlib

import pytest

FIXTURE_DIR = pathlib.Path(__file__).parent / "fixtures" / "seerr"


@pytest.fixture
def fixture():
    def _load(name):
        return json.loads((FIXTURE_DIR / f"{name}.json").read_text())

    return _load
