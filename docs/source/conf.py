"""Sphinx configuration for the sphinx-redline documentation.

Build with `make docs`; `make docs-serve` to view, `make docs-preview` to
edit with live reload.
"""

project = "sphinx-redline"
author = "sphinx-redline contributors"
copyright = "sphinx-redline contributors"

extensions = [
    "sphinx_copybutton",
    # The extension this repository develops; its own docs are the first test site.
    "sphinx_redline",
]

html_theme = "furo"
html_title = "sphinx-redline"
html_static_path = []
