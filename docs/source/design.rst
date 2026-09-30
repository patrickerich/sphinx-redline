How it works
============

This page explains how sphinx-redline works. :doc:`setup` covers how to use
it.

sphinx-redline has three parts:

Build step
   The Sphinx extension records, for every paragraph, list item and similar
   block in the HTML output, the source file and line it came from and a
   stable identifier. Sphinx and MyST already know the source location of most
   blocks, but only per block, and not always precisely.

Browser script
   Lets a reader select text, write a comment, reply to a thread and resolve
   it. Commented text is highlighted, and a side panel lists the threads.

Storage
   Comments are plain JSON files kept on a git branch, rather than in a
   database. Every comment and every reply is its own file, so two people
   commenting at the same time never edit the same file. (If their commits
   collide, the browser simply tries again.)

Anchoring comments to the source
--------------------------------

Each comment stores:

-  the git commit of the documentation it was made on,
-  the source file and line range,
-  the exact highlighted text plus a little context before and after it.

On every build the extension re-anchors each comment:

#. If the source file changed since that commit, ``git diff`` tells where the
   commented lines moved.
#. The highlighted text is looked up exactly: first in the block now at
   those lines, then in other blocks from the same file, then anywhere on the
   page. When the text occurs more than once, the words around it decide.
#. If the commented lines were edited, a close match in the lines that
   replaced them is accepted too.
#. A comment that cannot be placed is marked *outdated*. It stays visible
   in the comment panel, like an outdated review comment on a pull request.

Re-anchoring runs in the build, which has the full git history. This is the
main advantage of keeping comments in git instead of in the rendered pages.

Sphinx has a related mechanism (``sphinx.versioning``) that gives paragraphs
stable identifiers by comparing them with the previous build. It only works
when the previous build is still on disk, so it does nothing in a clean CI
build; sphinx-redline stores its own anchors instead.

Saving comments and signing in
------------------------------

A static web page cannot write to git on its own: something has to hold a
credential that is allowed to commit. sphinx-redline is designed to get that
credential without running an extra service, and to work with both GitHub and
GitLab (including self-hosted GitLab). There are two sign-in modes, plus a
third that is not implemented:

Guest passphrase
   The site owner creates a separate account with a token that can only write
   to the comments. At build time the token is placed in the page, encrypted
   with a passphrase the owner chooses. A guest enters the passphrase and a
   display name; the browser decrypts the token and saves the comment.

   This keeps out drive-by spam and works the same on GitHub and GitLab.
   Guests are not verified, though, and anyone who knows the passphrase can
   extract the token. The token must therefore be limited to the comments,
   and the passphrase must be long, because the encrypted token is public.

Sign in with GitLab
   The reader signs in on GitLab's own login page (OAuth with PKCE) and
   comments under their real name. GitLab's API accepts this directly from a
   web page, so no extra service is needed.

Sign in with GitHub
   Not implemented. GitHub's login endpoint does not accept requests from a
   web page, so this mode would need a small login relay: a service.

sphinx-redline never asks for a GitHub or GitLab password on the documentation
page. GitHub's API no longer accepts account passwords at all; GitLab's
password login is disabled for accounts with two-factor authentication; and a
documentation page asking for forge passwords would train readers to fall for
phishing.

New comments and the build
---------------------------

The build places comments, so a new comment becomes part of the published
page with the next documentation build. Until then the browser that saved it
shows it anyway, marked "saved, not yet built". A small workflow on the
comments branch can start that build whenever a comment arrives; see
:doc:`setup`.

Comment files
-------------

A thread's first comment carries the anchor; replies point to the thread and
may change its status (the last status set wins):

.. code-block:: json

   {
     "version": 1,
     "id": "20260930T101500Z-1a2b3c4d",
     "thread": null,
     "author": "Ann",
     "auth": "guest",
     "created": "2026-09-30T10:15:00Z",
     "body": "Should this be \"must\"?",
     "status": null,
     "anchor": {
       "docname": "setup",
       "source": "docs/source/setup.rst",
       "lines": [42, 44],
       "commit": "3b35f7c…",
       "quote": "should be",
       "prefix": "the token ",
       "suffix": " limited to the comments"
     }
   }

A reply has ``"thread"`` set to the first comment's ``id``, ``"anchor":
null``, and optionally ``"status": "resolved"`` or ``"open"``.

Limits
------

-  HTML output only. Comments on PDF output are a separate, much harder
   problem and are not planned yet.
-  A comment stays on the page (``docname``) it was made on. If a page is
   renamed, its comments are no longer shown.
-  Markdown sources (MyST) should work, since the extension only uses the
   source positions Sphinx records, but have not been tested yet.
