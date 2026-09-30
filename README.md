# Comments branch

This branch holds the review comments on the
[sphinx-redline documentation](https://patrickerich.github.io/sphinx-redline/):
one JSON file per comment under `comments/`, written by the comment panel on
the published pages. It shares no history with `main`.

`.github/workflows/rebuild-docs.yml` starts the documentation build on `main`
whenever a comment is pushed here, so new comments are published within a
few minutes.
