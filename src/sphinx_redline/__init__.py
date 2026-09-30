"""sphinx-redline: inline review comments anchored to the documentation source."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sphinx_redline.extension import RedlineExtension

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata

__all__ = ["RedlineExtension", "setup"]


def setup(app: Sphinx) -> ExtensionMetadata:
    """Sphinx entry point; Sphinx requires this to be a module-level function.

    Args:
        app: The Sphinx application loading the extension.

    Returns:
        The extension metadata Sphinx expects from ``setup()``.
    """
    return RedlineExtension(app).register()
