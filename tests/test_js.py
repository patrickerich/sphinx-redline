import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sphinx_redline.blocks import TextNormalizer
from sphinx_redline.comments import Comment

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "src/sphinx_redline/static/redline/redline.js"
NODE = shutil.which("node")

pytestmark = pytest.mark.skipif(NODE is None, reason="Node.js is not installed")


def run_node(code: str) -> str:
    result = subprocess.run(
        [NODE, "-e", f"const R = require({json.dumps(str(SCRIPT))});\n{code}"],
        capture_output=True, text=True, check=True,
    )
    return result.stdout


def test_node_unit_tests() -> None:
    result = subprocess.run(
        [NODE, "--test", str(ROOT / "tests/js")], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_normalisation_matches_python() -> None:
    samples = ["  a \n\t b  ", "x y", "line one\nline two\r\n", "", "   "]
    output = run_node(
        f"console.log(JSON.stringify({json.dumps(samples)}.map(R.TextNormalizer.normalize)))"
    )
    assert json.loads(output) == [TextNormalizer.normalize(s) for s in samples]


def test_browser_comments_are_valid_for_the_build() -> None:
    output = run_node(
        """
        const anchor = {docname: "index", source: "docs/index.rst", lines: [3, 4],
                        commit: "abc", quote: "q", prefix: "p", suffix: "s"};
        const thread = R.CommentFactory.thread(anchor, "Ann", "guest", "Hi\\nthere");
        const reply = R.CommentFactory.reply(thread.id, "Bob", "gitlab:bob", "Ok", "resolved");
        console.log(JSON.stringify([thread, reply].map(R.CommentFactory.serialize)));
        """
    )
    thread, reply = (Comment.from_json(json.loads(text)) for text in json.loads(output))
    assert thread.anchor is not None and thread.anchor.lines == (3, 4)
    assert reply.thread == thread.id and reply.status == "resolved"
