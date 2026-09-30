# sphinx-redline

> **Work in progress — not usable yet.** The extension currently only loads
> into Sphinx; it does not add any commenting features. See the
> [roadmap](https://patrickerich.github.io/sphinx-redline/roadmap.html) for progress.

A Sphinx extension for Word-style review comments on your documentation.
Readers highlight text in the built HTML and leave a comment; each comment is
anchored to the RST/Markdown source file and line and follows its text as the
source changes. Comments are stored as files in git and saved through your git
forge (GitHub or GitLab), so no extra service is needed.

Documentation: <https://patrickerich.github.io/sphinx-redline/>

## Quick start (development)

```bash
source ./sourceme.sh   # creates .venv (python3.13 by default) and installs requirements.txt
make test              # run the test suite
make docs              # build docs/source into docs/build/html (warnings are errors)
make docs-preview      # live-reload authoring server on http://localhost:8000
make help              # all targets
```

Use another interpreter (3.12 or newer) with `PYTHON=python3.12 source ./sourceme.sh`. This only
takes effect when `.venv` does not exist yet; delete it to switch.

## License

[Apache License 2.0](LICENSE). The software is provided "as is", without
warranty of any kind; use it at your own risk. See sections 7 (Disclaimer of
Warranty) and 8 (Limitation of Liability) of the license.
