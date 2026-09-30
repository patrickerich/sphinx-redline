import pytest

from conftest import comment
from sphinx_redline.comments import Comment, CommentFormatError, CommentStore


def test_valid_comment_round_trips() -> None:
    parsed = Comment.from_json(comment("c1", "quoted", lines=[3, 4], commit="abc1234"))
    assert parsed.anchor is not None
    assert parsed.anchor.lines == (3, 4)
    assert parsed.to_page_json()["author"] == "Reviewer"


@pytest.mark.parametrize(
    "change",
    [
        {"version": 2},
        {"id": "../escape"},
        {"body": ""},
        {"status": "deleted"},
        {"anchor": None},
        {"author": 5},
        {"id": "abc\n"},
    ],
)
def test_invalid_comment_is_rejected(change: dict) -> None:
    with pytest.raises(CommentFormatError):
        Comment.from_json({**comment("c1", "quoted"), **change})


def test_invalid_line_range_is_rejected() -> None:
    with pytest.raises(CommentFormatError):
        Comment.from_json(comment("c1", "quoted", lines=[5, 2]))


def test_thread_status_follows_last_reply() -> None:
    root = comment("root", "quoted")
    reply = {**root, "id": "r1", "thread": "root", "anchor": None, "status": "resolved",
             "created": "2026-09-30T11:00:00Z"}
    reopen = {**reply, "id": "r2", "status": "open", "created": "2026-09-30T12:00:00Z"}
    store = CommentStore(CommentStore._build_threads([Comment.from_json(c) for c in (reopen, root, reply)]), None)
    (thread,) = store.threads_for("index")
    assert [c.id for c in thread.replies] == ["r1", "r2"]
    assert thread.status == "open"


@pytest.mark.parametrize(
    "anchor_change",
    [
        {"lines": [1, 10**12]},
        {"lines": [1, 20_000]},
        {"commit": "\u0000"},
        {"commit": "--output=/tmp/x"},
        {"quote": "x" * 5001},
        {"prefix": "x" * 201},
    ],
)
def test_untrusted_anchor_values_are_bounded(anchor_change: dict) -> None:
    data = comment("c1", "quoted")
    data["anchor"].update(anchor_change)
    with pytest.raises(CommentFormatError):
        Comment.from_json(data)
