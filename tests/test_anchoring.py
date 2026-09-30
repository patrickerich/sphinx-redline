from sphinx_redline.anchoring import CommentAnchorer
from sphinx_redline.blocks import Block
from sphinx_redline.comments import Anchor


def anchor(quote: str, *, lines=(1, 1), prefix: str = "", suffix: str = "") -> Anchor:
    return Anchor("index", quote, prefix, suffix, "docs/index.rst", lines, None)


BLOCKS = [
    Block("b0", "docs/index.rst", (1, 2), "Title"),
    Block("b1", "docs/index.rst", (4, 5), "The cat sat on the mat. The cat left."),
    Block("b2", "docs/other.rst", (1, 1), "Unrelated text about a dog."),
]


def test_exact_match_in_expected_block() -> None:
    placement = CommentAnchorer(None).place(anchor("sat on", lines=(4, 5)), BLOCKS)
    assert (placement.state, placement.block, placement.start, placement.end) == ("anchored", "b1", 8, 14)


def test_context_picks_the_right_occurrence() -> None:
    placement = CommentAnchorer(None).place(anchor("The cat", lines=(4, 5), prefix="mat. "), BLOCKS)
    assert (placement.block, placement.start) == ("b1", 24)


def test_moved_text_is_found_in_other_blocks() -> None:
    placement = CommentAnchorer(None).place(anchor("about a dog", lines=(4, 5)), BLOCKS)
    assert (placement.state, placement.block) == ("anchored", "b2")


def test_slightly_edited_text_is_a_fuzzy_match() -> None:
    placement = CommentAnchorer(None).place(anchor("The cat sat on a mat", lines=(4, 5)), BLOCKS)
    assert placement.state == "anchored"
    assert placement.quote == "The cat sat on the mat"


def test_missing_text_is_outdated_near_its_lines() -> None:
    placement = CommentAnchorer(None).place(anchor("completely different words", lines=(4, 4)), BLOCKS)
    assert (placement.state, placement.block, placement.start) == ("outdated", "b1", None)
