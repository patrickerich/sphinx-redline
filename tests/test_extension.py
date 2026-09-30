from importlib.metadata import version

import pytest
from sphinx.testing.util import SphinxTestApp


@pytest.mark.sphinx("html", testroot="basic")
def test_extension_loads_and_builds(app: SphinxTestApp) -> None:
    app.build()

    assert "sphinx_redline" in app.extensions
    assert app.extensions["sphinx_redline"].version == version("sphinx-redline")
    assert not app.warning.getvalue()
    assert (app.outdir / "index.html").is_file()
