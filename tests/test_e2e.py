"""End-to-end test of the comment UI in a headless Chromium-family browser.

Skipped when no such browser (or Node.js) is found. Set REDLINE_BROWSER to
the browser executable to choose one explicitly.
"""

import base64
import json
import os
import shutil
import subprocess
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import GitProject, comment

ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "src/sphinx_redline/static/redline/redline.js"
BROWSER_NAMES = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "brave")
BROWSER_PATHS = ("/opt/brave.com/brave/brave",)
PASSPHRASE = "test passphrase for the e2e run"


def find_browser() -> str | None:
    if os.environ.get("REDLINE_BROWSER"):
        return os.environ["REDLINE_BROWSER"]
    for name in BROWSER_NAMES:
        if path := shutil.which(name):
            return path
    return next((p for p in BROWSER_PATHS if Path(p).is_file()), None)


BROWSER = find_browser()
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(
    BROWSER is None or NODE is None, reason="needs Node.js and a Chromium-family browser"
)

INDEX = """\
Review Me
=========

First paragraph with some words to comment on.

Second paragraph that stays the same.

Removed paragraph that a comment was made on.
"""


def guest_key(token: str) -> str:
    code = (
        f"require({json.dumps(str(SCRIPT))}).GuestKey"
        f".encrypt({json.dumps(token)}, {json.dumps(PASSPHRASE)}, 1000).then(console.log)"
    )
    return subprocess.run([NODE, "-e", code], capture_output=True, text=True, check=True).stdout.strip()


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: object) -> None:
        pass


@pytest.fixture
def served_site(git_project: GitProject, build):
    git_project.write("conf.py", "")
    git_project.write("index.rst", INDEX)
    commit = git_project.commit()
    git_project.add_comment(
        comment("t1", "Second paragraph", lines=[6, 6], commit=commit,
                body="<img src=x onerror=alert(1)> looks fine")
    )
    git_project.add_comment(comment("t2", "Removed paragraph", lines=[8, 8], commit=commit))
    git_project.write("index.rst", INDEX.replace("Removed paragraph that a comment was made on.\n", ""))
    git_project.commit()

    app = build(
        git_project.srcdir,
        html_theme="furo",
        extensions=["sphinx_redline", "sphinx_copybutton"],
        redline_comments_ref="redline",
        redline_forge="github",
        redline_repository="owner/comments",
        redline_guest_key=guest_key("ghp_test_token"),
        redline_source_url="https://github.com/owner/docs/blob/{commit}/{path}#L{first}-L{last}",
    )
    assert not app.warning.getvalue()
    handler = partial(QuietHandler, directory=str(app.outdir))
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/index.html", git_project
    server.shutdown()


def node_websocket_flags() -> list[str]:
    """Node 22+ has a global WebSocket; Node 20 needs a flag for it."""
    check = subprocess.run([NODE, "-e", "process.exit(typeof WebSocket === 'function' ? 0 : 1)"])
    return [] if check.returncode == 0 else ["--experimental-websocket"]


def test_comment_ui_end_to_end(served_site) -> None:
    url, project = served_site
    result = subprocess.run(
        [NODE, *node_websocket_flags(), str(ROOT / "tests/e2e/drive.js"), BROWSER, url, PASSPHRASE],
        capture_output=True, text=True, timeout=120, check=False,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    print(json.dumps(out, indent=1))  # shown by pytest when an assertion fails
    assert "error" not in out, out["error"]
    assert "exceptions" not in out, out["exceptions"]

    initial = out["initial"]
    assert initial["marks"] == [["t1", "Second paragraph"]]
    assert initial["toggle"] == "Comments (2)"
    assert initial["outdated"] == ["t2"]
    assert "&lt;img" in initial["bodyHtml"]
    # Skipped parts of the panel must not show up as the text "null".
    assert "null" not in initial.pop("panelText")
    assert "null" not in out["afterSave"].pop("panelText")
    head = project.git("rev-parse", "HEAD")
    assert initial["sourceLink"] == f"https://github.com/owner/docs/blob/{head}/docs/index.rst#L6-L6"
    assert out["panelOpenedByMark"] and out["addButtonShown"]
    assert out["passphraseKeptAfterError"] == "wrong"
    assert out["afterSave"] == {"marks": 2, "pendingLabel": True}

    new_thread, resolve = out["requests"]
    assert new_thread["method"] == "PUT"
    assert new_thread["url"].startswith("https://api.github.com/repos/owner/comments/contents/comments/")
    body = json.loads(new_thread["body"])
    assert body["branch"] == "redline"
    saved = json.loads(base64.b64decode(body["content"]))
    assert saved["author"] == "Erin" and saved["auth"] == "guest"
    assert saved["body"] == "Please rephrase <b>this</b>."
    assert saved["anchor"] == {
        "docname": "index",
        "source": "docs/index.rst",
        "lines": [4, 4],
        "commit": head,
        "quote": "some words",
        "prefix": "First paragraph with ",
        "suffix": " to comment on.",
    }
    resolved = json.loads(base64.b64decode(json.loads(resolve["body"])["content"]))
    assert (resolved["thread"], resolved["status"]) == ("t1", "resolved")

    threads = {t[0]: t[1:] for t in out["afterReload"]["threads"]}
    assert threads["t1"] == ["resolved", False, True]
    assert threads[saved["id"]] == ["open", True, True]
    assert out["afterReload"]["signedIn"] == "Erin"
    assert out["keytool"] == "github_pat_example"
