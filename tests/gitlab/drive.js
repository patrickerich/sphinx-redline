// Drives both GitLab sign-in modes against a local GitLab (tests/gitlab/gitlab.sh):
// guest passphrase, then "Sign in with GitLab" through GitLab's real login and
// authorization pages. Saves one comment with each and prints their ids as JSON.
//
// Usage: node [--experimental-websocket] drive.js <browser> <page-url> <passphrase> <user> <password>
const path = require("node:path");
const fs = require("node:fs");
const { Browser } = require(path.join(__dirname, "../e2e/drive.js"));

const [browserPath, pageUrl, passphrase, user, password] = process.argv.slice(2);

// Poll an expression, tolerating the page navigating away mid-evaluation.
async function waitFor(page, expression, timeout = 30000) {
  const end = Date.now() + timeout;
  let last = null;
  while (Date.now() < end) {
    try {
      if (await page.eval(expression)) return;
    } catch (error) {
      last = error;
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error(`timed out waiting for: ${expression}${last ? ` (${last.message})` : ""}`);
}

const selectAndOpenDraft = (text) => `(() => {
  const block = Array.from(document.querySelectorAll(".redline-block"))
    .find((b) => b.textContent.includes(${JSON.stringify(text)}));
  const index = new Redline.TextIndex(block);
  const start = index.text.indexOf(${JSON.stringify(text)});
  const selection = document.getSelection();
  selection.removeAllRanges();
  selection.addRange(index.rangeFor(start, start + ${JSON.stringify(text)}.length));
  document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  return new Promise((resolve) => setTimeout(() => {
    document.querySelector(".redline-add").dispatchEvent(new MouseEvent("mousedown", { bubbles: true }));
    resolve(true);
  }, 50));
})()`;

const saveDraft = (body) => `(() => {
  const form = document.querySelector(".redline-draft form");
  form.querySelector("textarea").value = ${JSON.stringify(body)};
  form.requestSubmit();
})()`;

const SAVED = `/Comment saved/.test(document.querySelector(".redline-status")?.textContent || "")`;
const STATUS = `document.querySelector(".redline-status")?.textContent`;

async function main() {
  const { proc, page, profile } = await Browser.launch(browserPath);
  const out = {};
  try {
    await page.send("Page.enable");
    await page.load(pageUrl);

    // 1. Guest passphrase.
    await page.eval(selectAndOpenDraft("some words"));
    await page.eval(`(() => {
      const form = document.querySelector(".redline-guest");
      form.querySelector('input[type="text"]').value = "Guest Gina";
      form.querySelector('input[type="password"]').value = ${JSON.stringify(passphrase)};
      form.requestSubmit();
    })()`);
    await waitFor(page, `Boolean(document.querySelector(".redline-draft textarea"))`);
    await page.eval(saveDraft("Guest comment on a local GitLab."));
    await waitFor(page, `${SAVED} || /fail|Not allowed|reach/i.test(${STATUS} || "")`);
    out.guestStatus = await page.eval(STATUS);
    out.guestId = await page.eval(`Redline.app.threads.find((t) => t.pending)?.id ?? null`);

    // 2. Sign out, then sign in with GitLab.
    await page.eval(`Array.from(document.querySelectorAll(".redline-auth button")).find((b) => b.textContent === "Sign out").click()`);
    await page.eval(`Array.from(document.querySelectorAll(".redline-auth button")).find((b) => b.textContent === "Sign in with GitLab").click()`);
    await waitFor(page, `Boolean(document.querySelector("#user_login"))`);
    // GitLab's form ignores values set from script; type them instead.
    for (const [id, value] of [["user_login", user], ["user_password", password]]) {
      await page.eval(`document.getElementById("${id}").focus()`);
      await page.send("Input.insertText", { text: value });
    }
    await page.eval(`document.querySelector('[data-testid="sign-in-button"]').click()`);
    // First sign-in shows GitLab's consent page; afterwards it redirects straight back.
    await waitFor(page, `location.port !== "${new URL(pageUrl).port}"
      ? Array.from(document.querySelectorAll("button, input[type=submit]")).some((b) => /Authorize/.test(b.textContent || b.value))
      : Boolean(window.Redline && Redline.app)`);
    out.consentShown = await page.eval(`location.port !== "${new URL(pageUrl).port}"`);
    if (out.consentShown) {
      await page.eval(`Array.from(document.querySelectorAll("button, input[type=submit]")).find((b) => /^\\s*Authorize/.test(b.textContent || b.value)).click()`);
    }
    await waitFor(page, `location.href === ${JSON.stringify(pageUrl)} && window.Redline?.app?.user?.mode === "gitlab"`);
    out.gitlabUser = await page.eval(`Redline.app.user.author + " / " + Redline.app.user.auth`);

    await page.eval(selectAndOpenDraft("stays the same"));
    await page.eval(saveDraft("Signed-in comment on a local GitLab."));
    await waitFor(page, `${SAVED} || /fail|Not allowed|reach/i.test(${STATUS} || "")`);
    out.gitlabStatus = await page.eval(STATUS);
    out.gitlabId = await page.eval(`Redline.app.threads.filter((t) => t.pending).map((t) => t.id).find((id) => id !== ${JSON.stringify(out.guestId)}) ?? null`);
  } catch (error) {
    out.error = String(error.stack || error);
    out.url = await page.eval("location.href").catch(() => null);
    out.text = await page.eval("document.body.innerText.slice(0, 1500)").catch(() => null);
  } finally {
    await new Promise((resolve) => {
      proc.on("exit", resolve);
      proc.kill();
    });
    try {
      fs.rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
    } catch (error) {
      // Best effort: it is a temporary directory.
    }
  }
  console.log(JSON.stringify(out));
  process.exit(0);
}

main();
