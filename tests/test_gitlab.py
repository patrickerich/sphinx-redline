"""End-to-end test against a real GitLab: both sign-in modes, saving, and the build.

Needs a local GitLab started with ``tests/gitlab/gitlab.sh up`` (settings in
``.gitlab-test.env``, or the file named by ``REDLINE_GITLAB_ENV``), plus
Node.js and a Chromium-family browser. Skipped otherwise, so it never runs
in CI.
"""

import base64
import json
import os
import subprocess
import threading
import urllib.parse
import urllib.request
from functools import partial
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from conftest import GitProject, page_data
from test_e2e import BROWSER, NODE, PASSPHRASE, QuietHandler, guest_key, node_websocket_flags

ROOT = Path(__file__).parent.parent
ENV_FILE = Path(os.environ.get("REDLINE_GITLAB_ENV", ROOT / ".gitlab-test.env"))


def load_settings() -> dict[str, str] | None:
    if not ENV_FILE.is_file():
        return None
    settings = dict(
        line.split("=", 1) for line in ENV_FILE.read_text().splitlines() if "=" in line
    )
    try:
        urllib.request.urlopen(f"{settings['REDLINE_GITLAB_URL']}/users/sign_in", timeout=5)
    except OSError:
        return None
    return settings


SETTINGS = load_settings()
pytestmark = pytest.mark.skipif(
    SETTINGS is None or BROWSER is None or NODE is None,
    reason="needs a local GitLab (tests/gitlab/gitlab.sh up), Node.js and a browser",
)

INDEX = """\
GitLab Test
===========

First paragraph with some words to comment on.

Second paragraph that stays the same.
"""


def gitlab_api(path: str) -> object:
    request = urllib.request.Request(
        f"{SETTINGS['REDLINE_GITLAB_URL']}/api/v4{path}",
        headers={"PRIVATE-TOKEN": SETTINGS["REDLINE_GITLAB_ROOT_TOKEN"]},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def read_comment(comment_id: str) -> dict:
    project = urllib.parse.quote(SETTINGS["REDLINE_GITLAB_PROJECT"], safe="")
    path = urllib.parse.quote(f"comments/{comment_id}.json", safe="")
    data = gitlab_api(f"/projects/{project}/repository/files/{path}?ref=redline")
    return json.loads(base64.b64decode(data["content"]))


def build_site(project: GitProject, build, **extra):
    return build(
        project.srcdir,
        redline_forge="gitlab",
        redline_forge_url=SETTINGS["REDLINE_GITLAB_URL"],
        redline_repository=SETTINGS["REDLINE_GITLAB_PROJECT"],
        redline_guest_key=guest_key(SETTINGS["REDLINE_GITLAB_PROJECT_TOKEN"]),
        redline_gitlab_client_id=SETTINGS["REDLINE_GITLAB_CLIENT_ID"],
        **extra,
    )


def test_gitlab_end_to_end(git_project: GitProject, build) -> None:
    git_project.write("conf.py", "")
    git_project.write("index.rst", INDEX)
    git_project.commit()
    app = build_site(git_project, build)
    assert not app.warning.getvalue()

    # The OAuth application's redirect URI is this exact address.
    port = int(SETTINGS["REDLINE_GITLAB_SITE_PORT"])
    server = ThreadingHTTPServer(
        ("127.0.0.1", port), partial(QuietHandler, directory=str(app.outdir))
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        result = subprocess.run(
            [
                NODE, *node_websocket_flags(), str(ROOT / "tests/gitlab/drive.js"), BROWSER,
                f"http://127.0.0.1:{port}/index.html", PASSPHRASE,
                SETTINGS["REDLINE_GITLAB_USER"], SETTINGS["REDLINE_GITLAB_PASSWORD"],
            ],
            capture_output=True, text=True, timeout=300, check=False,
        )
    finally:
        server.shutdown()
        server.server_close()
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout)
    print(json.dumps(out, indent=1))  # shown by pytest when an assertion fails
    assert "error" not in out, out["error"]
    assert out["gitlabUser"] == "Reviewer / gitlab:reviewer"

    guest = read_comment(out["guestId"])
    assert (guest["author"], guest["auth"]) == ("Guest Gina", "guest")
    assert guest["anchor"]["quote"] == "some words"
    signed_in = read_comment(out["gitlabId"])
    assert (signed_in["author"], signed_in["auth"]) == ("Reviewer", "gitlab:reviewer")
    assert signed_in["anchor"]["quote"] == "stays the same"

    # Close the loop: fetch the comments from GitLab and build with them.
    url = urllib.parse.urlsplit(SETTINGS["REDLINE_GITLAB_URL"])
    remote = (
        f"{url.scheme}://oauth2:{SETTINGS['REDLINE_GITLAB_ROOT_TOKEN']}@{url.netloc}"
        f"/{SETTINGS['REDLINE_GITLAB_PROJECT']}.git"
    )
    git_project.git("fetch", "-q", remote, "redline:refs/redline/comments")
    app = build_site(git_project, build, redline_comments_ref="refs/redline/comments")
    assert not app.warning.getvalue()
    threads = {t["id"]: t for t in page_data(app)["threads"]}
    for comment_id in (out["guestId"], out["gitlabId"]):
        assert threads[comment_id]["placement"]["state"] == "anchored"
