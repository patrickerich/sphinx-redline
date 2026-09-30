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
-  "Sign in with GitLab" (OAuth with PKCE).
-  Both GitLab sign-in modes tested end to end against a local GitLab CE.
-  A live example comment and the :doc:`fork_tutorial`.
-  Markdown sources (MyST), covered by tests.
-  First alpha release, 0.1.0, on PyPI.

Next
----

-  Try both GitLab sign-in modes on gitlab.com and in real use.
-  Keep comments when a page is renamed.

Not planned for now
-------------------

-  "Sign in with GitHub": it needs a small login relay, which is a service.
-  Comments on PDF output.
