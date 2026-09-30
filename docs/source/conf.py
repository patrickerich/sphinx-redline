"""Sphinx configuration for the sphinx-redline documentation.

Build with `make docs`; `make docs-serve` to view, `make docs-preview` to
edit with live reload.
"""

import os

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

# Comments live on the `redline` branch of this repository. In GitHub Actions,
# GITHUB_REPOSITORY names the repository being built, so a fork saves comments
# to itself without editing this file. The guest key comes from the
# REDLINE_GUEST_KEY Actions variable; without it the site is read-only.
_repository = os.environ.get("GITHUB_REPOSITORY", "patrickerich/sphinx-redline")
redline_forge = "github"
redline_repository = _repository
redline_guest_key = os.environ.get("REDLINE_GUEST_KEY") or None
redline_source_url = f"https://github.com/{_repository}/blob/{{commit}}/{{path}}#L{{first}}-L{{last}}"
