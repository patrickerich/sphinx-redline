# AGENTS.md

Guidance for AI coding agents working in this repository. Keep it short and
point into the docs rather than duplicating them.

## What sphinx-redline is

A Sphinx extension that lets readers highlight text in the built HTML and leave
review comments. Each comment is anchored to the RST/Markdown source file and
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
- Tests use pytest with Sphinx's own fixtures (`sphinx.testing.fixtures`); each
  test project lives in `tests/roots/test-<name>/`.

## Layout

| Path                   | Contents                                              |
| ---------------------- | ----------------------------------------------------- |
| `src/sphinx_redline/`  | The extension package (`__init__.setup` is the entry point) |
| `tests/`               | pytest suite; `tests/roots/test-*/` are Sphinx test projects |
| `docs/source/`         | This project's documentation, built with the extension enabled |
| `docs/build/`          | Build output (ignored by git)                         |
| `.github/workflows/`   | `docs.yml`: build docs on PRs, publish to GitHub Pages on `main` |
| `pyproject.toml`       | Package metadata and runtime dependencies             |
| `requirements.txt`     | Development environment: editable install plus pinned tools |
| `sourceme.sh`          | Creates and activates the project `.venv`             |
| `Makefile`             | `test`, `docs`, `docs-serve`, `docs-preview`, `docs-clean`, `docs-<builder>` |
