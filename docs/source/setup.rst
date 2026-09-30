Setting up
==========

.. warning::

   sphinx-redline is an early alpha release. The comment file format and the
   settings below may still change.

Setting up commenting for a documentation project has four parts:

#. Install the extension and enable it in ``conf.py``.
#. Create a branch that holds the comments.
#. Choose how readers sign in.
#. Make the documentation build fetch the comments.

Install
-------

Install it from PyPI:

.. code-block:: bash

   pip install sphinx-redline

sphinx-redline needs Python 3.12 or newer and Sphinx 9.1 or newer. It works
with the HTML builders (``html`` and ``dirhtml``); other builders, such as
LaTeX for PDF output, are left untouched.

Then add it to ``conf.py``:

.. code-block:: python

   extensions = [
       # ...
       "sphinx_redline",
   ]

With only this, the extension shows existing comments but readers cannot add
new ones. The settings below turn on commenting.

Where comments are stored
-------------------------

Each comment is a small JSON file under ``comments/`` on a git branch,
``redline`` by default. The branch holds nothing else, so it starts empty.
Create it once:

.. code-block:: bash

   git switch --orphan redline
   git commit --allow-empty -m "Start the comments branch"
   git push origin redline
   git switch main

The branch can be in the documentation repository itself or in a separate
repository. **A separate repository is the safer choice when guests may
comment** (see `Guest passphrase`_ below): the token that saves comments then
cannot touch the documentation sources.

Settings
--------

.. list-table::
   :header-rows: 1
   :widths: 25 20 55

   * - Setting
     - Default
     - Meaning
   * - ``redline_forge``
     - ``None``
     - ``"github"`` or ``"gitlab"``. Where new comments are saved. ``None``
       makes the site read-only: existing comments are shown, but readers
       cannot add any.
   * - ``redline_repository``
     - ``None``
     - The repository holding the comments branch: ``"owner/repo"`` on
       GitHub, ``"group/project"`` (with any subgroups) on GitLab. Required
       when ``redline_forge`` is set.
   * - ``redline_branch``
     - ``"redline"``
     - The branch new comments are committed to.
   * - ``redline_forge_url``
     - ``None``
     - The forge's web address, for GitHub Enterprise or a self-hosted GitLab,
       for example ``"https://gitlab.example.com"``. Defaults to
       ``https://github.com`` or ``https://gitlab.com``.
   * - ``redline_guest_key``
     - ``None``
     - The encrypted token for guest sign-in; see `Guest passphrase`_.
   * - ``redline_gitlab_client_id``
     - ``None``
     - The application ID for "Sign in with GitLab"; see `Sign in with GitLab`_.
   * - ``redline_comments_ref``
     - ``"origin/redline"``
     - The git ref the *build* reads comments from. It must be available in
       the checkout the documentation is built from; see
       `Building with comments`_.
   * - ``redline_source_url``
     - ``None``
     - A link template to view the commented source, with the placeholders
       ``{commit}``, ``{path}``, ``{first}`` and ``{last}``. For GitHub:
       ``"https://github.com/owner/docs/blob/{commit}/{path}#L{first}-L{last}"``.

A complete example for a GitHub-hosted project with comments in a separate
repository:

.. code-block:: python

   import os

   redline_forge = "github"
   redline_repository = "owner/docs-comments"
   redline_guest_key = os.environ.get("REDLINE_GUEST_KEY")
   redline_comments_ref = "refs/redline/comments"
   redline_source_url = "https://github.com/owner/docs/blob/{commit}/{path}#L{first}-L{last}"

Signing in
----------

Saving a comment needs a token that may commit to the comments branch.
sphinx-redline offers two ways for readers to get one without running any
extra service. Both can be enabled at once.

Guest passphrase
^^^^^^^^^^^^^^^^

The site owner provides one token for all guests, encrypted with a
passphrase. Anyone who knows the passphrase can comment under a name of
their choice.

#. Create a token that can write to the comments repository and nothing
   else:

   GitHub
      A *fine-grained personal access token* (Settings → Developer settings →
      Fine-grained tokens) with access to **only the comments repository** and
      the permission **Contents: Read and write**.

   GitLab
      A *project access token* on the comments project, with the role
      **Developer** and the scope **api**.

#. Open the guest key tool, which is published with every site that uses
   sphinx-redline at ``_static/redline/keytool.html`` (for example
   `this site's key tool <_static/redline/keytool.html>`_). Enter the token
   and a passphrase and copy the resulting key. Nothing you enter there is
   sent anywhere.

#. Set the key as ``redline_guest_key``, typically from an environment
   variable set by CI. The key is published in every page, so it may be
   stored as a plain CI variable rather than a secret.

#. Give the passphrase to the people who should be able to comment.

.. important::

   Everyone who knows the passphrase can extract the token from the page and
   use it directly. That is why the token must be limited to the comments:

   -  On GitHub, a fine-grained token cannot be limited to one branch. If the
      comments branch is in the documentation repository itself, the token
      can also push to your other branches. Either use a separate comments
      repository, or protect the default branch with a ruleset that has an
      empty bypass list: rulesets apply to the repository owner, and so to
      the owner's tokens, unless the owner is on that list. A second ruleset
      that blocks force pushes and deletion of the comments branch keeps a
      token holder from erasing comments, while still allowing new ones.
      This repository uses the second approach.
   -  On GitLab, the default branch is protected against Developer pushes by
      default, so a project token with the Developer role can only push to
      unprotected branches such as the comments branch.

   The encrypted key is public, so a short passphrase could be guessed
   offline. The key tool enforces at least 16 characters; its
   :guilabel:`Generate` button creates a random one. To revoke guest access,
   delete the token and publish a new key with a new passphrase.

Sign in with GitLab
^^^^^^^^^^^^^^^^^^^

Readers who have an account on the GitLab instance sign in on GitLab's own
login page, and their comments carry their GitLab name.

.. note::

   This mode, and guest mode on GitLab, are tested against a local GitLab CE
   (version 19.4), but not yet on gitlab.com or in production use. Please
   report how it works for you.

#. In GitLab, create an OAuth application (User settings → Applications, or
   for a group: Group settings → Applications):

   -  **Redirect URI**: the root address of your documentation site, for
      example ``https://docs.example.com/``. Every page sends readers back
      there after signing in.
   -  **Confidential**: unchecked. A browser cannot keep a secret; sign-in
      uses PKCE instead.
   -  **Scopes**: ``api``. GitLab has no narrower scope that allows creating
      files through the API.

#. Set ``redline_gitlab_client_id`` to the application ID.

Readers need at least the Developer role on the comments project to save
comments. The ``api`` scope gives the page a token with the reader's full
API access for about two hours; it is kept in the browser tab's session
storage and never sent anywhere except to GitLab.

"Sign in with GitHub" is not offered: GitHub's login endpoint does not allow
requests from a web page, so it would need a server of its own.

Building with comments
----------------------

The build reads comments from the git ref in ``redline_comments_ref`` and
uses the git history to follow comments to their current place. In CI that
means:

-  check out the full history (``fetch-depth: 0`` with
   ``actions/checkout``), and
-  fetch the comments branch before building.

For comments in the documentation repository itself:

.. code-block:: yaml

   - uses: actions/checkout@v6
     with:
       fetch-depth: 0
   - name: Fetch comments
     run: git fetch --no-tags origin redline:refs/remotes/origin/redline || true

For comments in a separate repository, fetch from there and set
``redline_comments_ref = "refs/redline/comments"``:

.. code-block:: yaml

   - name: Fetch comments
     run: git fetch --no-tags https://github.com/owner/docs-comments.git redline:refs/redline/comments || true

Nothing is fetched automatically: a local build shows the comments of
whatever ``origin/redline`` your last ``git fetch`` got.

New comments appear for everyone after the next build. The author sees their
own new comments right away, marked "saved, not yet built". To rebuild the
documentation whenever a comment arrives, add a workflow **on the comments
branch** that starts the documentation workflow:

.. code-block:: yaml

   # .github/workflows/rebuild-docs.yml on the redline branch
   name: rebuild-docs
   on:
     push:
       branches: [redline]
   permissions:
     actions: write
   jobs:
     dispatch:
       runs-on: ubuntu-latest
       timeout-minutes: 5
       steps:
         - run: gh workflow run docs.yml --repo "$GITHUB_REPOSITORY" --ref main
           env:
             GH_TOKEN: ${{ github.token }}

The documentation workflow needs a ``workflow_dispatch`` trigger for this.
For a separate comments repository, a scheduled documentation build (for
example hourly) is the simplest alternative.

If a comment file is malformed, or the comments ref is missing, the build
logs it and carries on without failing, so ``-W`` builds are not affected.
