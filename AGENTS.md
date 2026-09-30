# AGENTS.md

Guidance for AI coding agents working in this repository. Keep it short and
point into the docs rather than duplicating them.

## What sphinx-redline is

A Sphinx extension that lets readers highlight text in the built HTML and leave
review comments (experimental). Each comment is anchored to the RST/Markdown source file and
line, and follows its text as the source changes between builds. Comments are
stored as files in git; saving them from the browser goes through the git
forge's API (GitHub or GitLab), so no extra service is needed.

## Environment

```bash
source ./sourceme.sh   # create/activate .venv, install requirements.txt (incl. `-e .`)
make test              # pytest suite
make docs              # Sphinx build with -W --keep-going
```

The Makefile always runs Python through `.venv/bin/python`, so the pinned
versions in `requirements.txt` are used even if another venv is active.

## Python conventions

- Object-oriented: put behaviour in classes with clear responsibilities. The
  only module-level functions are those an external API requires, such as the
  `setup(app)` entry point Sphinx calls, and they delegate straight to a class.
- Python 3.12+ (Sphinx 9.1 requires it), PEP 8, 100-column lines, type hints on
  every signature, docstrings with arguments and return values.
- No SPDX license headers in source files; `LICENSE` (Apache-2.0) covers the repo.
- Tests use pytest with Sphinx's own fixtures (`sphinx.testing.fixtures`). Static
  test projects live in `tests/roots/test-<name>/`; projects that need git
  history are built with the `GitProject` fixture.

## Workflow

`main` is protected by a ruleset: changes go through a pull request, and the
checks `pytest (3.12)`, `pytest (3.13)` and `build` (docs) must pass on a
branch that is up to date with `main`. Work on a branch, open a PR with
`gh pr create`, and merge once CI is green. The `redline` branch (comments)
only blocks force-pushes and deletion: the browser commits to it directly.

## How it fits together

- Build side (Python, `src/sphinx_redline/`): `blocks.py` marks commentable
  blocks, `comments.py` reads and validates comment files from a git ref,
  `git.py` wraps read-only git calls and diff line mapping, `anchoring.py`
  places threads, `extension.py` wires Sphinx events and writes a JSON data
  script into every HTML page.
- Browser side: `static/redline/redline.js` (one classic script, also loaded
  by Node for tests), `redline.css`, and `keytool.html` for guest keys.
- The comment file format is defined twice, by `comments.Comment` and by
  `CommentFactory` in `redline.js`; `tests/test_js.py` checks they agree.
- The build must never emit a Sphinx warning for normal conditions (missing
  ref, malformed comment, not a git checkout): log at info level instead.
  Only invalid `conf.py` settings are warnings.
- Comment text is untrusted: render it with `textContent` only.

## Tests

- `tests/test_*.py`: pytest, with `tests/conftest.py` providing a throwaway
  git repository (`GitProject`) and a `build` fixture.
- `tests/js/*.test.js`: Node unit tests for `redline.js`, run from pytest.
- `tests/test_e2e.py` + `tests/e2e/drive.js`: the whole UI in a headless
  Chromium-family browser via the DevTools protocol, forge requests
  intercepted. Skipped if no browser is found; set `REDLINE_BROWSER` to pick
  one. GitHub's Ubuntu runners have Chrome, so it runs in CI.

## Layout

| Path                   | Contents                                              |
| ---------------------- | ----------------------------------------------------- |
| `src/sphinx_redline/`  | The extension package (`__init__.setup` is the entry point) |
| `tests/`               | pytest suite, Node unit tests (`js/`) and the browser test (`e2e/`) |
| `docs/source/`         | This project's documentation, built with the extension enabled |
| `docs/build/`          | Build output (ignored by git)                         |
| `.github/workflows/`   | `test.yml`: pytest on Python 3.12 and 3.13; `docs.yml`: build docs on PRs, publish to GitHub Pages on `main` |
| `pyproject.toml`       | Package metadata and runtime dependencies             |
| `requirements.txt`     | Development environment: editable install plus pinned tools |
| `sourceme.sh`          | Creates and activates the project `.venv`             |
| `Makefile`             | `test`, `docs`, `docs-serve`, `docs-preview`, `docs-clean`, `docs-<builder>` |
