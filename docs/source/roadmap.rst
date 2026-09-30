Roadmap
=======

sphinx-redline is experimental. The order below may change as the work
progresses.

Done
----

-  Package, test and documentation scaffold.
-  Source anchors: the build marks every commentable block of the HTML and
   records its source file and lines.
-  Comments stored as files on a git branch, read by the build.
-  Re-anchoring comments when the source changes, and marking comments whose
   text is gone as outdated.
-  Browser UI: highlights, comment panel, new comments, replies, resolving.
-  Guest passphrase sign-in and saving comments to GitHub and GitLab.
-  "Sign in with GitLab" (OAuth with PKCE), with unit tests.
-  A live example comment and the :doc:`fork_tutorial`.

Next
----

-  Try "Sign in with GitLab" and guest mode against a real GitLab instance.
-  Test with Markdown sources (MyST).
-  Keep comments when a page is renamed.
-  A first release on PyPI.

Not planned for now
-------------------

-  "Sign in with GitHub": it needs a small login relay, which is a service.
-  Comments on PDF output.
