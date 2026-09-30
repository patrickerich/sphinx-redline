from pathlib import Path

from conftest import GitProject, comment, page_data

INDEX = """\
Title Here
==========

First paragraph with some words.

.. note::

   A note that mentions words too.

::

   code line
"""


def setup_project(project: GitProject) -> str:
    project.write("conf.py", "")
    project.write("index.rst", INDEX)
    return project.commit()


def test_blocks_are_marked_with_source_lines(git_project: GitProject, build) -> None:
    setup_project(git_project)
    app = build(git_project.srcdir)
    assert not app.warning.getvalue()

    html = (app.outdir / "index.html").read_text()
    assert 'class="redline-block redline-b1"' in html
    data = page_data(app)
    assert data["commit"] == git_project.git("rev-parse", "HEAD")
    assert data["forge"] is None
    assert data["blocks"]["b0"] == {"source": "docs/index.rst", "lines": [1, 2]}
    assert data["blocks"]["b1"] == {"source": "docs/index.rst", "lines": [4, 4]}
    assert len(data["blocks"]) == 4


def test_comments_are_placed_and_follow_edits(git_project: GitProject, build) -> None:
    commit = setup_project(git_project)
    git_project.add_comment(
        comment("t1", "some words", lines=[4, 4], commit=commit, prefix="paragraph with ")
    )
    git_project.add_comment(comment("t2", "gone text", lines=[8, 8], commit=commit))
    # Insert lines above the commented paragraph and reword the note.
    git_project.write(
        "index.rst",
        INDEX.replace("==========\n", "==========\n\nIntro.\n\nMore intro.\n").replace(
            "mentions words too", "says something else"
        ),
    )
    git_project.commit()

    app = build(git_project.srcdir, redline_comments_ref="redline")
    assert not app.warning.getvalue()
    threads = {t["id"]: t for t in page_data(app)["threads"]}
    moved = threads["t1"]["placement"]
    assert moved["state"] == "anchored"
    assert moved["quote"] == "some words"
    assert page_data(app)["blocks"][moved["block"]]["lines"] == [8, 8]
    assert threads["t2"]["placement"]["state"] == "outdated"


def test_comment_text_cannot_break_out_of_the_script(git_project: GitProject, build) -> None:
    setup_project(git_project)
    git_project.add_comment(comment("t1", "some words", body="</script><script>alert(1)</script>"))
    app = build(git_project.srcdir, redline_comments_ref="redline")
    html = (app.outdir / "index.html").read_text()
    assert "<script>alert(1)" not in html
    assert page_data(app)["threads"][0]["comments"][0]["body"] == "</script><script>alert(1)</script>"


def test_problems_do_not_warn(git_project: GitProject, build) -> None:
    setup_project(git_project)
    git_project.add_comment(b"not json")
    git_project.add_comment({**comment("t1", "x"), "version": 99})
    app = build(git_project.srcdir, redline_comments_ref="redline")
    assert not app.warning.getvalue()
    assert page_data(app)["threads"] == []

    app = build(git_project.srcdir, redline_comments_ref="no-such-ref")
    assert not app.warning.getvalue()


def test_outside_git_and_other_builders(tmp_path: Path, build) -> None:
    srcdir = tmp_path / "plain"
    srcdir.mkdir()
    (srcdir / "conf.py").write_text("")
    (srcdir / "index.rst").write_text(INDEX)
    app = build(srcdir)
    assert not app.warning.getvalue()
    assert page_data(app)["blocks"]["b1"]["source"] == "index.rst"

    for builder in ("latex", "text"):
        app = build(srcdir, builder)
        assert not app.warning.getvalue(), builder


def test_forge_settings(git_project: GitProject, build) -> None:
    setup_project(git_project)
    app = build(
        git_project.srcdir,
        redline_forge="gitlab",
        redline_forge_url="https://gitlab.example.com/",
        redline_repository="group/docs-comments",
    )
    forge = page_data(app)["forge"]
    assert forge["apiUrl"] == "https://gitlab.example.com/api/v4"
    assert forge["repository"] == "group/docs-comments"
    assert forge["branch"] == "redline"

    app = build(git_project.srcdir, redline_forge="github")
    assert "redline_repository is not" in app.warning.getvalue()


def test_new_comment_rebuilds_unchanged_page(git_project: GitProject, build) -> None:
    setup_project(git_project)
    app = build(git_project.srcdir, redline_comments_ref="redline")
    assert page_data(app)["threads"] == []
    git_project.add_comment(comment("t1", "some words"))
    app = build(git_project.srcdir, redline_comments_ref="redline")
    assert [t["id"] for t in page_data(app)["threads"]] == ["t1"]
