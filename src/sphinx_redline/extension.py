"""Registration of sphinx-redline with a Sphinx application."""

from __future__ import annotations

import json
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse

from sphinx.util import logging

from sphinx_redline.anchoring import CommentAnchorer
from sphinx_redline.blocks import BlockCollector
from sphinx_redline.comments import CommentStore
from sphinx_redline.git import GitRepository

if TYPE_CHECKING:
    from docutils import nodes
    from sphinx.application import Sphinx
    from sphinx.config import Config
    from sphinx.environment import BuildEnvironment
    from sphinx.util.typing import ExtensionMetadata

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ForgeSettings:
    """Where the browser saves new comments: a repository branch on a forge."""

    DEFAULT_URLS = {"github": "https://github.com", "gitlab": "https://gitlab.com"}

    kind: str
    url: str
    api_url: str
    repository: str
    branch: str
    guest_key: str | None
    gitlab_client_id: str | None

    @classmethod
    def from_config(cls, config: Config) -> ForgeSettings | None:
        """Read the forge settings from ``conf.py``.

        Args:
            config: The Sphinx configuration.

        Returns:
            The settings, or ``None`` if commenting is not configured or the
            configuration is invalid (which is reported as a warning).
        """
        kind = config.redline_forge
        if kind is None:
            return None
        if kind not in cls.DEFAULT_URLS:
            logger.warning("sphinx-redline: redline_forge must be 'github' or 'gitlab', not %r", kind)
            return None
        if not config.redline_repository:
            logger.warning("sphinx-redline: redline_forge is set but redline_repository is not")
            return None
        url = (config.redline_forge_url or cls.DEFAULT_URLS[kind]).rstrip("/")
        if kind == "github":
            api_url = "https://api.github.com" if urlparse(url).hostname == "github.com" else f"{url}/api/v3"
        else:
            api_url = f"{url}/api/v4"
        return cls(
            kind=kind,
            url=url,
            api_url=api_url,
            repository=config.redline_repository,
            branch=config.redline_branch,
            guest_key=config.redline_guest_key or None,
            gitlab_client_id=config.redline_gitlab_client_id or None,
        )

    def to_page_json(self) -> dict[str, Any]:
        """Return the settings the browser script needs."""
        return {
            "kind": self.kind,
            "url": self.url,
            "apiUrl": self.api_url,
            "repository": self.repository,
            "branch": self.branch,
            "guestKey": self.guest_key,
            "gitlabClientId": self.gitlab_client_id,
        }


class RedlineExtension:
    """Owns everything sphinx-redline registers with one Sphinx application."""

    STATIC_DIR = Path(__file__).parent / "static"
    HTML_BUILDERS = ("html", "dirhtml")
    DATA_SCRIPT_ID = "redline-data"
    PAGE_FORMAT_VERSION = 1

    def __init__(self, app: Sphinx) -> None:
        """Bind the extension to a Sphinx application.

        Args:
            app: The Sphinx application to register with.
        """
        self._app = app
        self._repo: GitRepository | None = None
        self._store = CommentStore.empty()
        self._forge: ForgeSettings | None = None
        self._head: str | None = None
        self._pages: dict[str, dict[str, Any]] = {}

    def register(self) -> ExtensionMetadata:
        """Register config values, event handlers and assets with Sphinx.

        Returns:
            The extension metadata Sphinx expects from ``setup()``.
        """
        app = self._app
        app.add_config_value("redline_comments_ref", "origin/redline", "html", str)
        app.add_config_value("redline_forge", None, "html", (str, type(None)))
        app.add_config_value("redline_forge_url", None, "html", (str, type(None)))
        app.add_config_value("redline_repository", None, "html", (str, type(None)))
        app.add_config_value("redline_branch", "redline", "html", str)
        app.add_config_value("redline_guest_key", None, "html", (str, type(None)))
        app.add_config_value("redline_gitlab_client_id", None, "html", (str, type(None)))
        app.add_config_value("redline_source_url", None, "html", (str, type(None)))

        app.connect("config-inited", self._on_config_inited)
        app.connect("builder-inited", self._on_builder_inited)
        app.connect("env-get-outdated", self._on_env_get_outdated)
        app.connect("doctree-resolved", self._on_doctree_resolved)
        app.connect("html-page-context", self._on_html_page_context)
        return {
            "version": version("sphinx-redline"),
            "parallel_read_safe": True,
            "parallel_write_safe": True,
        }

    def _is_active(self) -> bool:
        return self._app.builder is not None and self._app.builder.name in self.HTML_BUILDERS

    def _on_config_inited(self, app: Sphinx, config: Config) -> None:
        config.html_static_path.append(str(self.STATIC_DIR))

    def _on_builder_inited(self, app: Sphinx) -> None:
        if not self._is_active():
            return
        app.add_css_file("redline/redline.css")
        app.add_js_file("redline/redline.js")
        self._repo = GitRepository.discover(Path(app.srcdir))
        self._head = None if self._repo is None else self._repo.head()
        self._store = CommentStore.load(self._repo, app.config.redline_comments_ref)
        self._forge = ForgeSettings.from_config(app.config)

    def _on_env_get_outdated(
        self,
        app: Sphinx,
        env: BuildEnvironment,
        added: set[str],
        changed: set[str],
        removed: set[str],
    ) -> list[str]:
        """Re-build pages whose comments changed although their source did not."""
        if not self._is_active():
            return []
        previous: dict[str, str] = getattr(env, "redline_comment_digests", {})
        current = self._store.digests()
        env.redline_comment_digests = current  # type: ignore[attr-defined]
        return sorted(
            docname
            for docname in previous.keys() | current.keys()
            if previous.get(docname) != current.get(docname)
            and docname in env.found_docs
            and docname not in added | changed
        )

    def _on_doctree_resolved(self, app: Sphinx, doctree: nodes.document, docname: str) -> None:
        if not self._is_active():
            return
        blocks = BlockCollector(self._repo, Path(app.srcdir)).collect(doctree)
        anchorer = CommentAnchorer(self._repo)
        threads = []
        for thread in self._store.threads_for(docname):
            placement = anchorer.place(thread.anchor, blocks)
            anchor = thread.anchor
            threads.append(
                {
                    "id": thread.root.id,
                    "status": thread.status,
                    "quote": anchor.quote,
                    "source": anchor.source,
                    "lines": None if anchor.lines is None else list(anchor.lines),
                    "commit": anchor.commit,
                    "placement": placement.to_page_json(),
                    "comments": [c.to_page_json() for c in thread.comments()],
                }
            )
        self._pages[docname] = {
            "version": self.PAGE_FORMAT_VERSION,
            "docname": docname,
            "commit": self._head,
            "sourceUrl": app.config.redline_source_url,
            "forge": None if self._forge is None else self._forge.to_page_json(),
            "blocks": {b.id: b.to_page_json() for b in blocks},
            "threads": threads,
        }

    def _on_html_page_context(
        self,
        app: Sphinx,
        pagename: str,
        templatename: str,
        context: dict[str, Any],
        doctree: nodes.document | None,
    ) -> None:
        page = self._pages.pop(pagename, None) if doctree is not None else None
        if page is None:
            return
        # Added during html-page-context, the script only goes into this page.
        app.add_js_file(
            None,
            body=self._script_json(page),
            type="application/json",
            id=self.DATA_SCRIPT_ID,
        )

    @staticmethod
    def _script_json(data: dict[str, Any]) -> str:
        """Serialise data for an inline ``<script>`` without letting it close the tag."""
        text = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
        return text.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
