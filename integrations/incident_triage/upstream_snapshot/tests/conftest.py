import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from triage.graph import build_graph  # noqa: E402


@pytest.fixture()
def app():
    return build_graph()
