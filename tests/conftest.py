import json
import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from sphinx.testing.util import SphinxTestApp

pytest_plugins = ("sphinx.testing.fixtures",)


@pytest.fixture(scope="session")
def rootdir() -> Path:
    """Directory holding the ``test-<name>`` Sphinx projects used as test roots."""
    return Path(__file__).parent / "roots"


class GitProject:
    """A throwaway git repository holding a Sphinx project and a comments branch."""

    ENV = {
        "GIT_AUTHOR_NAME": "Test",
        "GIT_AUTHOR_EMAIL": "test@example.org",
        "GIT_COMMITTER_NAME": "Test",
        "GIT_COMMITTER_EMAIL": "test@example.org",
        "GIT_CONFIG_GLOBAL": os.devnull,
        "GIT_CONFIG_NOSYSTEM": "1",
    }

    def __init__(self, root: Path) -> None:
        self.root = root
        self.srcdir = root / "docs"
        self.srcdir.mkdir(parents=True)
        self._comments: dict[str, bytes] = {}
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str, stdin: bytes | None = None) -> str:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            input=stdin,
            capture_output=True,
            check=True,
            env={**os.environ, **self.ENV},
        )
        return result.stdout.decode().strip()

    def write(self, name: str, text: str) -> None:
        path = self.srcdir / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def commit(self, message: str = "Update docs") -> str:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def add_comment(
        self, data: dict[str, Any] | bytes, branch: str = "redline", name: str | None = None
    ) -> None:
        """Commit a comment file to ``branch`` without touching the working tree."""
        content = data if isinstance(data, bytes) else json.dumps(data).encode()
        if name is None:
            name = f"c{len(self._comments)}.json" if isinstance(data, bytes) else f"{data['id']}.json"
        self._comments[name] = content
        entries = "".join(
            f"100644 blob {self.git('hash-object', '-w', '--stdin', stdin=blob)}\t{file}\0"
            for file, blob in sorted(self._comments.items())
        )
        comments_tree = self.git("mktree", "-z", stdin=entries.encode())
        root_tree = self.git("mktree", stdin=f"040000 tree {comments_tree}\tcomments\n".encode())
        parent = subprocess.run(
            ["git", "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"],
            cwd=self.root, capture_output=True, text=True, check=False,
        ).stdout.strip()
        args = ["commit-tree", root_tree, "-m", "Add comment"] + (["-p", parent] if parent else [])
        self.git("update-ref", f"refs/heads/{branch}", self.git(*args))


@pytest.fixture
def git_project(tmp_path: Path) -> GitProject:
    """An empty git repository with a ``docs/`` Sphinx source directory."""
    return GitProject(tmp_path / "repo")


def comment(
    comment_id: str,
    quote: str,
    *,
    docname: str = "index",
    source: str | None = "docs/index.rst",
    lines: list[int] | None = None,
    commit: str | None = None,
    prefix: str = "",
    suffix: str = "",
    body: str = "A comment.",
    **extra: Any,
) -> dict[str, Any]:
    """Return the JSON content of a thread-starting comment file."""
    return {
        "version": 1,
        "id": comment_id,
        "thread": None,
        "author": "Reviewer",
        "auth": "guest",
        "created": "2026-09-30T10:00:00Z",
        "body": body,
        "status": None,
        "anchor": {
            "docname": docname,
            "source": source,
            "lines": lines,
            "commit": commit,
            "quote": quote,
            "prefix": prefix,
            "suffix": suffix,
        },
        **extra,
    }


@pytest.fixture
def build(make_app: Callable[..., SphinxTestApp]) -> Callable[..., SphinxTestApp]:
    """Build a Sphinx project directory and return the finished (cleaned up) app."""

    def run(srcdir: Path, buildername: str = "html", **confoverrides: Any) -> SphinxTestApp:
        app = make_app(
            buildername,
            srcdir=srcdir,
            confoverrides={"extensions": ["sphinx_redline"], **confoverrides},
        )
        app.build()
        # Undo the global docutils registrations, so a test can build again.
        app.cleanup()
        return app

    return run


def page_data(app: SphinxTestApp, page: str = "index") -> dict[str, Any]:
    """Extract the sphinx-redline data script from a built HTML page."""
    html = (app.outdir / f"{page}.html").read_text()
    start = html.index('id="redline-data"')
    start = html.index(">", start) + 1
    end = html.index("</script>", start)
    return json.loads(html[start:end])
