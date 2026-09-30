Try it on your fork
===================

The quickest way to try sphinx-redline is on your own fork of its
repository: the documentation you are reading is already set up for it, so
you only need a token, a passphrase and a few clicks in GitHub. Everything
happens in your fork; nothing is sent to the upstream repository.

You need a GitHub account. Allow about fifteen minutes.

.. note::

   For simplicity, this tutorial keeps the comments in the fork itself. The
   guest token can therefore also push to your fork's other branches, which
   is fine for a throwaway fork but not for real documentation; see
   :doc:`setup` for the safer setup with a separate comments repository.

1. Fork the repository
----------------------

Open https://github.com/patrickerich/sphinx-redline and click
:guilabel:`Fork`. **Uncheck** :guilabel:`Copy the main branch only`, so the
fork also gets the ``redline`` branch with the example comments and the
workflow that rebuilds the documentation when a comment arrives.

If you forked with only the main branch, create an empty comments branch
instead:

.. code-block:: bash

   git clone https://github.com/<you>/sphinx-redline
   cd sphinx-redline
   git switch --orphan redline
   git commit --allow-empty -m "Start the comments branch"
   git push origin redline

(Without the rebuild workflow you then start the documentation build by hand
after commenting; see step 6.)

2. Turn on Actions and Pages
----------------------------

GitHub disables workflows in new forks.

#. In your fork, open the :guilabel:`Actions` tab and confirm that you want
   to enable workflows.
#. Open :guilabel:`Settings` → :guilabel:`Pages` and set
   :guilabel:`Source` to :guilabel:`GitHub Actions`.

3. Create a token for the comments
----------------------------------

Open GitHub's `fine-grained token page
<https://github.com/settings/personal-access-tokens/new>`_ and create a
token with:

-  :guilabel:`Repository access`: :guilabel:`Only select repositories`, and
   select your fork only.
-  :guilabel:`Permissions` → :guilabel:`Contents`: :guilabel:`Read and write`.
-  An expiration date that suits you.

Copy the token (it starts with ``github_pat_``).

4. Create the guest key
-----------------------

Open the `guest key tool <_static/redline/keytool.html>`_ (it runs entirely
in your browser; the token is not sent anywhere). Paste the token, click
:guilabel:`Generate` for a passphrase, and click
:guilabel:`Create guest key`. Keep the passphrase: you need it to comment.

In your fork, open :guilabel:`Settings` → :guilabel:`Secrets and variables`
→ :guilabel:`Actions` → :guilabel:`Variables` and add a repository variable
named ``REDLINE_GUEST_KEY`` with the key as its value.

5. Build the documentation
--------------------------

Open :guilabel:`Actions` → :guilabel:`docs` → :guilabel:`Run workflow`. When
it has finished, your copy of this documentation is published at
``https://<you>.github.io/sphinx-redline/``.

6. Add a comment
----------------

#. Open ``https://<you>.github.io/sphinx-redline/example.html``.
#. Select a few words in a paragraph and click the :guilabel:`Comment` button
   that appears below them.
#. In the comment panel, enter your name and the passphrase and click
   :guilabel:`Sign in as guest`.
#. Write the comment and click :guilabel:`Save comment`.

The comment is committed to your ``redline`` branch as
``comments/<id>.json``; have a look at the branch on GitHub. You see it on
the page straight away, marked "saved, not yet built". The commit starts a
new documentation build (see the :guilabel:`Actions` tab); when that is done,
the comment is part of the published page for everyone. If your fork has no
rebuild workflow, run the :guilabel:`docs` workflow again by hand.

Reply to the thread, or resolve it, the same way.

7. Change the text and watch the comment follow
-----------------------------------------------

Edit ``docs/source/example.rst`` on your fork's ``main`` branch, for example
by adding a paragraph above the one you commented on, and commit. After the
documentation build, the comment is still on its text. Then reword or delete
the commented sentence: the comment moves to the :guilabel:`Outdated` list
in the panel instead of disappearing.

Cleaning up
-----------

Delete the token on GitHub's token page when you are done, and delete the
fork if you no longer need it.
