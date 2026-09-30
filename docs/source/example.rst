Example page
============

This page is here to be commented on. Highlighted text has a comment
thread: click it to open the thread in the comment panel. The
:guilabel:`Comments` button in the bottom right corner opens the panel too,
including threads whose text has since changed.

The upstream copy of this site has no sign-in configured, so its comment
panel is read-only. To add comments yourself, follow :doc:`fork_tutorial`:
on your own fork, you choose the passphrase.

A paragraph to review
---------------------

Redlining is the practice of marking up a document for review: striking out
text, suggesting new wording and writing notes in the margin. Reviewers of
word processor documents take it for granted. Documentation written as
reStructuredText or Markdown and built with Sphinx usually has no such
thing, because the published pages are generated from plain text files.

With sphinx-redline, a reader selects some text on a page and writes a
comment. The comment is saved as a file in git, next to the documentation it
refers to, and records the source file and line numbers the text came from.
When the documentation is built again, every comment is placed on its text,
even if lines were added or removed above it.

Some code
---------

Comments work on code blocks too:

.. code-block:: python

   def greet(name: str) -> str:
       return f"Hello, {name}!"
