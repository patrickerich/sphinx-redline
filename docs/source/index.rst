sphinx-redline
==============

.. warning::

   **Work in progress — not usable yet.** The extension currently only loads
   into Sphinx; it does not add any commenting features. Do not use it for real
   documentation projects yet. The :doc:`roadmap` shows what is done and what
   comes next.

sphinx-redline is a Sphinx extension for review comments on documentation, in
the spirit of comments in a word processor:

-  Readers highlight text in the built HTML pages and leave a comment on it.
-  Each comment is anchored to the RST or Markdown **source** file and line it
   was made on, not just to the rendered page.
-  When the source changes, comments follow their text. A comment whose text
   can no longer be found is shown as *outdated*, never silently dropped.
-  Comments are stored as files in git and saved through the git forge's API
   (GitHub or GitLab), so no extra service has to be run.

Existing tools such as Hypothesis or giscus let readers comment on a rendered
page, but they anchor comments to the HTML output only. Comments are orphaned
when the text changes and nothing links them back to the source that has to be
edited. :doc:`design` explains how sphinx-redline approaches this.

sphinx-redline is licensed under the Apache License 2.0. It is provided "as
is", without warranty of any kind; use it at your own risk.

.. toctree::
   :maxdepth: 2

   design
   roadmap
