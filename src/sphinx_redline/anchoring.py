"""Placing comment threads on the blocks of the current build."""

from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from sphinx_redline.blocks import Block
    from sphinx_redline.comments import Anchor
    from sphinx_redline.git import GitRepository


@dataclass(frozen=True)
class Placement:
    """Where a thread is shown in the current build.

    ``state`` is ``anchored`` when the commented text was found (``start``
    and ``end`` are offsets into the normalised block text), or ``outdated``
    when it was not. An outdated thread keeps a best-guess ``block`` so it
    can still be shown near where it was made, or ``None`` if there is none.
    """

    state: str
    block: str | None
    start: int | None = None
    end: int | None = None
    quote: str | None = None

    def to_page_json(self) -> dict[str, object]:
        """Return the placement fields for the page data."""
        return {
            "state": self.state,
            "block": self.block,
            "start": self.start,
            "end": self.end,
            "quote": self.quote,
        }


@dataclass(frozen=True)
class _Match:
    block: Block
    start: int
    end: int
    score: float


class CommentAnchorer:
    """Finds the text a comment was made on in the current version of a page.

    The steps, in order:

    #. Map the comment's source lines from the commit it was made on to the
       working tree with ``git diff``, following renames.
    #. Look for the quoted text in the block now at those lines, then in the
       other blocks from the same source file, then anywhere on the page.
       Several occurrences are told apart by the text around the quote.
    #. If there is no exact match, accept a close match, but only in the
       block now at those lines: elsewhere a short quote would too easily
       match unrelated text.
    #. Otherwise the thread is outdated.
    """

    FUZZY_THRESHOLD = 0.8
    CONTEXT_LENGTH = 32

    def __init__(self, repo: GitRepository | None) -> None:
        """Bind to the repository used for line mapping.

        Args:
            repo: The git repository, or ``None`` if the docs are not in git.
        """
        self._repo = repo

    def place(self, anchor: Anchor, blocks: list[Block]) -> Placement:
        """Place one thread on the blocks of its page.

        Args:
            anchor: The anchor recorded when the thread was made.
            blocks: The blocks of the page in the current build.

        Returns:
            Where to show the thread.
        """
        source, lines = self._map_source(anchor)
        expected = [b for b in blocks if self._overlaps(b, source, lines)]
        same_source = [b for b in blocks if source and b.source == source and b not in expected]
        same_source.sort(key=lambda b: self._distance(b, lines))
        others = [b for b in blocks if b not in expected and b not in same_source]

        for tier in (expected, same_source, others):
            match = self._best(self._exact_matches(anchor, tier))
            if match is not None:
                return self._anchored(match)
        match = self._best(self._fuzzy_matches(anchor, expected))
        if match is not None:
            return self._anchored(match)

        nearest = (expected or same_source or [None])[0]
        return Placement(state="outdated", block=None if nearest is None else nearest.id)

    def _map_source(self, anchor: Anchor) -> tuple[str | None, tuple[int, int] | None]:
        if anchor.source is None or anchor.lines is None:
            return anchor.source, None
        if self._repo is None or anchor.commit is None:
            return anchor.source, anchor.lines
        diff = self._repo.diff(anchor.commit)
        if diff is None:
            # Commit not available (e.g. shallow clone): trust the recorded lines.
            return anchor.source, anchor.lines
        file_diff = diff.file(anchor.source)
        if file_diff is None:
            return anchor.source, anchor.lines
        return file_diff.new_path, file_diff.map_range(*anchor.lines)

    @staticmethod
    def _overlaps(block: Block, source: str | None, lines: tuple[int, int] | None) -> bool:
        if source is None or lines is None or block.source != source or block.lines is None:
            return False
        return block.lines[0] <= lines[1] and lines[0] <= block.lines[1]

    @staticmethod
    def _distance(block: Block, lines: tuple[int, int] | None) -> int:
        if lines is None or block.lines is None:
            return 0
        return abs(block.lines[0] - lines[0])

    def _exact_matches(self, anchor: Anchor, blocks: list[Block]) -> list[_Match]:
        matches = []
        for block in blocks:
            start = block.text.find(anchor.quote)
            while start != -1:
                end = start + len(anchor.quote)
                matches.append(_Match(block, start, end, self._context_score(anchor, block, start, end)))
                start = block.text.find(anchor.quote, start + 1)
        return matches

    def _fuzzy_matches(self, anchor: Anchor, blocks: list[Block]) -> list[_Match]:
        quote = anchor.quote
        slack = max(4, len(quote) // 4)
        matches = []
        for block in blocks:
            longest = SequenceMatcher(None, block.text, quote, autojunk=False).find_longest_match()
            if longest.size < min(4, len(quote)):
                continue
            window_start = max(0, longest.a - longest.b - slack)
            window_end = min(len(block.text), longest.a + (len(quote) - longest.b) + slack)
            window = block.text[window_start:window_end]
            parts = [
                m for m in SequenceMatcher(None, window, quote, autojunk=False).get_matching_blocks()
                if m.size
            ]
            start = window_start + parts[0].a
            end = window_start + parts[-1].a + parts[-1].size
            matched = sum(m.size for m in parts)
            ratio = 2 * matched / ((end - start) + len(quote))
            if ratio >= self.FUZZY_THRESHOLD:
                matches.append(_Match(block, start, end, ratio))
        return matches

    def _context_score(self, anchor: Anchor, block: Block, start: int, end: int) -> float:
        before = block.text[max(0, start - self.CONTEXT_LENGTH):start]
        after = block.text[end:end + self.CONTEXT_LENGTH]
        return float(
            self._common_suffix(before, anchor.prefix) + self._common_prefix(after, anchor.suffix)
        )

    @staticmethod
    def _common_prefix(a: str, b: str) -> int:
        count = 0
        for x, y in zip(a, b, strict=False):
            if x != y:
                break
            count += 1
        return count

    @classmethod
    def _common_suffix(cls, a: str, b: str) -> int:
        return cls._common_prefix(a[::-1], b[::-1])

    @staticmethod
    def _best(matches: list[_Match]) -> _Match | None:
        # max() keeps the first of equal scores, i.e. document order.
        return max(matches, key=lambda m: m.score, default=None)

    @staticmethod
    def _anchored(match: _Match) -> Placement:
        return Placement(
            state="anchored",
            block=match.block.id,
            start=match.start,
            end=match.end,
            quote=match.block.text[match.start:match.end],
        )
