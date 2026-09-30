"""Marking commentable blocks in a doctree and recording where they came from."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from docutils import nodes
from sphinx import addnodes

if TYPE_CHECKING:
    from sphinx_redline.git import GitRepository


class TextNormalizer:
    """Whitespace normalisation shared by the build and the browser script.

    Offsets into block text are exchanged between both sides, so both must
    collapse every run of whitespace to one space and strip both ends.
    """

    _WHITESPACE = re.compile(r"\s+")

    @classmethod
    def normalize(cls, text: str) -> str:
        """Collapse whitespace runs to single spaces and strip the ends.

        Args:
            text: Any text.

        Returns:
            The normalised text.
        """
        return cls._WHITESPACE.sub(" ", text).strip()


@dataclass(frozen=True)
class Block:
    """One commentable block of a page, as written to the HTML."""

    id: str
    source: str | None
    lines: tuple[int, int] | None
    text: str

    def to_page_json(self) -> dict[str, object]:
        """Return the fields the browser needs to anchor new comments."""
        return {"source": self.source, "lines": None if self.lines is None else list(self.lines)}


class BlockCollector:
    """Finds the commentable blocks of a resolved doctree and marks them.

    Each block gets two CSS classes: ``redline-block`` and ``redline-b<N>``,
    where ``<N>`` numbers the blocks of the page. Classes rather than ids are
    used because docutils writes extra ids of a node as separate empty
    elements, which the browser could not attach a highlight to.
    """

    BLOCK_TYPES: tuple[type[nodes.Element], ...] = (
        nodes.paragraph,
        nodes.title,
        nodes.literal_block,
        nodes.doctest_block,
        nodes.term,
        nodes.line,
        nodes.caption,
        nodes.rubric,
    )
    BLOCK_CLASS = "redline-block"
    ID_CLASS_PREFIX = "redline-b"

    def __init__(self, repo: GitRepository | None, srcdir: Path) -> None:
        """Configure how source paths are reported.

        Args:
            repo: The git repository, used to make source paths relative to
                its root. ``None`` if the docs are not in git.
            srcdir: The Sphinx source directory; paths are relative to it
                when there is no repository.
        """
        self._repo = repo
        self._srcdir = srcdir

    def collect(self, doctree: nodes.document) -> list[Block]:
        """Mark the commentable blocks of a doctree and describe them.

        Args:
            doctree: A resolved doctree about to be written as HTML. It is
                modified in place.

        Returns:
            The blocks in document order.
        """
        blocks = []
        for node in doctree.findall(self._is_block):
            block_id = f"b{len(blocks)}"
            node["classes"] += [self.BLOCK_CLASS, f"{self.ID_CLASS_PREFIX}{len(blocks)}"]
            blocks.append(
                Block(
                    id=block_id,
                    source=self._source_path(node.source),
                    lines=self._line_range(node),
                    text=TextNormalizer.normalize(node.astext()),
                )
            )
        return blocks

    def _is_block(self, node: nodes.Node) -> bool:
        return (
            isinstance(node, self.BLOCK_TYPES)
            # Toctree entries: navigation, not content.
            and not isinstance(node, addnodes.compact_paragraph)
            and node.line is not None
            and bool(node.astext().strip())
        )

    def _source_path(self, source: str | None) -> str | None:
        if not source:
            return None
        path = Path(source)
        if not path.is_file():
            # e.g. "module.py:docstring of f" from autodoc: no plain file to point at.
            return None
        if self._repo is not None:
            return self._repo.relative_path(path)
        try:
            return path.resolve().relative_to(self._srcdir.resolve()).as_posix()
        except ValueError:
            return None

    @staticmethod
    def _line_range(node: nodes.Element) -> tuple[int, int]:
        first = node.line
        count = max(1, node.rawsource.count("\n") + 1) if node.rawsource else 1
        if isinstance(node, nodes.title) and first > 1:
            # docutils reports a section title at its underline.
            return first - 1, first
        return first, first + count - 1
