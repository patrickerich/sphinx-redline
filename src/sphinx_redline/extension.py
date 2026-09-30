"""Registration of sphinx-redline with a Sphinx application."""

from __future__ import annotations

from importlib.metadata import version
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx.application import Sphinx
    from sphinx.util.typing import ExtensionMetadata


class RedlineExtension:
    """Owns everything sphinx-redline registers with one Sphinx application."""

    def __init__(self, app: Sphinx) -> None:
        """Bind the extension to a Sphinx application.

        Args:
            app: The Sphinx application to register with.
        """
        self._app = app

    def register(self) -> ExtensionMetadata:
        """Register config values, event handlers and assets with Sphinx.

        Returns:
            The extension metadata Sphinx expects from ``setup()``.
        """
        return {
            "version": version("sphinx-redline"),
            "parallel_read_safe": True,
            "parallel_write_safe": True,
        }
