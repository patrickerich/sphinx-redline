from pathlib import Path

import pytest

pytest_plugins = ("sphinx.testing.fixtures",)


@pytest.fixture(scope="session")
def rootdir() -> Path:
    """Directory holding the ``test-<name>`` Sphinx projects used as test roots."""
    return Path(__file__).parent / "roots"
