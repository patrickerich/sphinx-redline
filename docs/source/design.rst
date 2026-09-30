How it works
============

.. note::

   This page describes the planned design. Most of it is not implemented yet;
   see the :doc:`roadmap`.

sphinx-redline has three parts:

Build step
   The Sphinx extension records, for every paragraph, list item and similar
   block in the HTML output, the source file and line it came from and a
   stable identifier. Sphinx and MyST already know the source location of most
   blocks, but only per block, and not always precisely.

Browser script
   Lets a reader select text, write a comment, reply to a thread and resolve
   it. Existing comments are shown next to the text they belong to.

Storage
   Comments are plain files (one per thread) kept in git, next to the
   documentation they comment on, rather than in a database.

Anchoring comments to the source
--------------------------------

Each comment stores:

-  the git commit of the documentation it was made on,
-  the source file and line range,
-  the exact highlighted text plus a little context before and after it.

On every build the extension re-anchors each comment:

#. If the source file changed since that commit, ``git diff`` tells where the
   commented lines moved.
#. Within the matching block, the highlighted text is looked up again: first
   exactly, then by closest match.
#. A comment that cannot be placed with confidence is marked *outdated*. It
   stays visible, like an outdated review comment on a pull request.

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
GitLab (including self-hosted GitLab). Three sign-in modes are planned:

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
   The same for GitHub. GitHub's login endpoint does not accept requests from
   a web page, so this mode needs a small login relay and is optional.

sphinx-redline never asks for a GitHub or GitLab password on the documentation
page. GitHub's API no longer accepts account passwords at all; GitLab's
password login is disabled for accounts with two-factor authentication; and a
documentation page asking for forge passwords would train readers to fall for
phishing.

Scope
-----

The first versions target HTML output only. Comments on PDF output are a
separate, much harder problem and are not planned yet.
