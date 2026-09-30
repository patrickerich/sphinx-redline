"""The comment file format and the store that reads comments from git."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sphinx.util import logging

from sphinx_redline.git import GitError

if TYPE_CHECKING:
    from sphinx_redline.git import GitRepository

logger = logging.getLogger(__name__)


class CommentFormatError(ValueError):
    """Raised when a comment file does not follow the expected format."""


class _Fields:
    """Typed access to the fields of one decoded JSON object."""

    def __init__(self, data: Any, what: str) -> None:
        """Wrap a decoded JSON value that must be an object.

        Args:
            data: The decoded JSON value.
            what: Name used in error messages.
        """
        if not isinstance(data, dict):
            raise CommentFormatError(f"{what} must be a JSON object")
        self._data = data
        self._what = what

    def text(self, key: str, *, optional: bool = False, empty: bool = False) -> str | None:
        """Return a string field; ``optional`` allows it to be missing or null."""
        value = self._data.get(key)
        if value is None and optional:
            return None
        if not isinstance(value, str) or (not value and not empty):
            raise CommentFormatError(f"{self._what}: '{key}' must be a non-empty string")
        return value

    def lines(self, key: str) -> tuple[int, int] | None:
        """Return an optional ``[first, last]`` line range field."""
        value = self._data.get(key)
        if value is None:
            return None
        if (
            not isinstance(value, list)
            or len(value) != 2
            or not all(isinstance(v, int) and not isinstance(v, bool) and v > 0 for v in value)
            or value[0] > value[1]
        ):
            raise CommentFormatError(f"{self._what}: '{key}' must be [first, last] line numbers")
        return value[0], value[1]

    def child(self, key: str) -> _Fields | None:
        """Return an optional nested object field."""
        value = self._data.get(key)
        return None if value is None else _Fields(value, f"{self._what}.{key}")


@dataclass(frozen=True)
class Anchor:
    """Where a comment thread was made: the page, the source and the quoted text."""

    docname: str
    quote: str
    prefix: str
    suffix: str
    source: str | None
    lines: tuple[int, int] | None
    commit: str | None

    @classmethod
    def from_fields(cls, fields: _Fields) -> Anchor:
        """Build an anchor from the ``anchor`` object of a comment file."""
        return cls(
            docname=fields.text("docname"),
            quote=fields.text("quote"),
            prefix=fields.text("prefix", optional=True, empty=True) or "",
            suffix=fields.text("suffix", optional=True, empty=True) or "",
            source=fields.text("source", optional=True),
            lines=fields.lines("lines"),
            commit=fields.text("commit", optional=True),
        )


@dataclass(frozen=True)
class Comment:
    """One comment file: a thread's first comment, or a reply to it."""

    FORMAT_VERSION = 1
    STATUSES = ("open", "resolved")
    ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

    id: str
    thread: str | None
    author: str
    auth: str | None
    created: str
    body: str
    status: str | None
    anchor: Anchor | None

    @classmethod
    def from_json(cls, data: Any) -> Comment:
        """Validate and decode one comment file.

        Args:
            data: The decoded JSON content of the file.

        Returns:
            The comment.

        Raises:
            CommentFormatError: If the content does not follow the format.
        """
        fields = _Fields(data, "comment")
        if data.get("version") != cls.FORMAT_VERSION:
            raise CommentFormatError(f"unsupported comment format version {data.get('version')!r}")
        comment_id = fields.text("id")
        thread = fields.text("thread", optional=True)
        for value in (comment_id, thread):
            if value is not None and not cls.ID_PATTERN.match(value):
                raise CommentFormatError(f"invalid comment id {value!r}")
        status = fields.text("status", optional=True)
        if status is not None and status not in cls.STATUSES:
            raise CommentFormatError(f"invalid status {status!r}")
        anchor_fields = fields.child("anchor")
        anchor = None if anchor_fields is None else Anchor.from_fields(anchor_fields)
        if thread is None and anchor is None:
            raise CommentFormatError("a comment that starts a thread needs an 'anchor'")
        return cls(
            id=comment_id,
            thread=thread,
            author=fields.text("author"),
            auth=fields.text("auth", optional=True),
            created=fields.text("created"),
            body=fields.text("body"),
            status=status,
            anchor=anchor,
        )

    def to_page_json(self) -> dict[str, Any]:
        """Return the fields the browser needs to display this comment."""
        return {
            "id": self.id,
            "author": self.author,
            "auth": self.auth,
            "created": self.created,
            "body": self.body,
            "status": self.status,
        }


@dataclass
class Thread:
    """A first comment with its anchor, plus its replies in creation order."""

    root: Comment
    replies: list[Comment] = field(default_factory=list)

    @property
    def anchor(self) -> Anchor:
        """The anchor of the first comment."""
        assert self.root.anchor is not None  # guaranteed by Comment.from_json
        return self.root.anchor

    @property
    def status(self) -> str:
        """``open`` or ``resolved``: the last status set in the thread wins."""
        status = "open"
        for comment in [self.root, *self.replies]:
            if comment.status is not None:
                status = comment.status
        return status

    def comments(self) -> list[Comment]:
        """The first comment followed by all replies."""
        return [self.root, *self.replies]


class CommentStore:
    """All comment threads, read from a git revision and grouped by page."""

    DIRECTORY = "comments"

    def __init__(self, threads: list[Thread], revision: str | None) -> None:
        """Hold already loaded threads.

        Args:
            threads: The comment threads.
            revision: The commit id they were read from, if any.
        """
        self.revision = revision
        self._by_docname: dict[str, list[Thread]] = {}
        for thread in threads:
            self._by_docname.setdefault(thread.anchor.docname, []).append(thread)

    @classmethod
    def empty(cls) -> CommentStore:
        """Return a store without comments."""
        return cls([], None)

    @classmethod
    def load(cls, repo: GitRepository | None, ref: str) -> CommentStore:
        """Read all comment files from ``comments/`` of a git ref.

        Problems are logged at info level rather than as warnings: a missing
        comments branch is the normal state of a fresh project, and a single
        malformed file must not break a ``-W`` documentation build.

        Args:
            repo: The repository, or ``None`` when the docs are not in git.
            ref: The ref holding the comments, e.g. ``origin/redline``.

        Returns:
            The store; empty if the ref does not exist.
        """
        if repo is None:
            logger.info("sphinx-redline: not a git checkout; no comments loaded")
            return cls.empty()
        revision = repo.resolve(ref)
        if revision is None:
            logger.info("sphinx-redline: comments ref %r not found; no comments loaded", ref)
            return cls.empty()
        try:
            files = repo.read_directory(revision, cls.DIRECTORY)
        except GitError as error:
            logger.info("sphinx-redline: cannot read comments from %r: %s", ref, error)
            return cls.empty()
        comments = []
        for path, content in sorted(files.items()):
            if not path.endswith(".json"):
                continue
            try:
                comments.append(Comment.from_json(json.loads(content)))
            except (ValueError, UnicodeDecodeError) as error:
                logger.info("sphinx-redline: skipping %s: %s", path, error)
        logger.info("sphinx-redline: loaded %d comments from %s", len(comments), ref)
        return cls(cls._build_threads(comments), revision)

    @staticmethod
    def _build_threads(comments: list[Comment]) -> list[Thread]:
        threads = {c.id: Thread(root=c) for c in comments if c.thread is None}
        for comment in sorted(comments, key=lambda c: (c.created, c.id)):
            if comment.thread is None:
                continue
            thread = threads.get(comment.thread)
            if thread is None:
                logger.info("sphinx-redline: reply %s has no thread %s", comment.id, comment.thread)
                continue
            thread.replies.append(comment)
        return sorted(threads.values(), key=lambda t: (t.root.created, t.root.id))

    def threads_for(self, docname: str) -> list[Thread]:
        """Return the threads made on one page.

        Args:
            docname: The Sphinx document name.

        Returns:
            The threads, oldest first.
        """
        return self._by_docname.get(docname, [])

    def digests(self) -> dict[str, str]:
        """Return a hash of each page's comments, to detect which pages changed."""
        digests = {}
        for docname, threads in self._by_docname.items():
            payload = json.dumps(
                [[c.to_page_json() for c in t.comments()] for t in threads]
                + [[t.anchor.__dict__ for t in threads]],
                sort_keys=True,
                default=list,
            )
            digests[docname] = hashlib.sha256(payload.encode()).hexdigest()
        return digests
