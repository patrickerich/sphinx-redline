// Drives a headless Chromium-family browser over the DevTools protocol to
// exercise the comment UI end to end. Requests to the GitHub API are
// intercepted and answered locally, so nothing is written anywhere.
//
// Usage: node [--experimental-websocket] drive.js <browser> <page-url> <passphrase>
// Prints a JSON object with the observations; tests/test_e2e.py asserts on it.
const { spawn } = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");

const [browserPath, pageUrl, passphrase] = process.argv.slice(2);

class Browser {
  static async launch(executable) {
    const profile = fs.mkdtempSync(path.join(os.tmpdir(), "redline-e2e-"));
    const proc = spawn(executable, [
      "--headless=new", "--remote-debugging-port=0", `--user-data-dir=${profile}`,
      "--no-first-run", "--no-default-browser-check", "--disable-gpu",
      // CI runners restrict the user namespaces Chromium's sandbox needs; the
      // test only loads a local page, so running without it is harmless.
      "--no-sandbox", "about:blank",
    ]);
    const endpoint = await new Promise((resolve, reject) => {
      let buffer = "";
      proc.stderr.on("data", (chunk) => {
        buffer += chunk;
        const match = /DevTools listening on (ws:\/\/\S+)/.exec(buffer);
        if (match) resolve(match[1]);
      });
      proc.on("exit", (code) => reject(new Error(`browser exited (${code}): ${buffer}`)));
    });
    const port = new URL(endpoint).port;
    const target = await (await fetch(`http://127.0.0.1:${port}/json/new?about:blank`, { method: "PUT" })).json();
    const page = new Page(target.webSocketDebuggerUrl);
    await page.ready;
    return { proc, page, profile };
  }
}

class Page {
  constructor(url) {
    this.socket = new WebSocket(url);
    this.nextId = 1;
    this.pending = new Map();
    this.listeners = [];
    this.ready = new Promise((resolve) => this.socket.addEventListener("open", resolve));
    this.socket.addEventListener("message", (event) => {
      const message = JSON.parse(event.data);
      if (message.id && this.pending.has(message.id)) {
        const { resolve, reject } = this.pending.get(message.id);
        this.pending.delete(message.id);
        message.error ? reject(new Error(message.error.message)) : resolve(message.result);
      } else if (message.method) {
        for (const listener of this.listeners) listener(message);
      }
    });
  }

  send(method, params = {}) {
    const id = this.nextId++;
    this.socket.send(JSON.stringify({ id, method, params }));
    return new Promise((resolve, reject) => this.pending.set(id, { resolve, reject }));
  }

  on(method, handler) {
    this.listeners.push((message) => message.method === method && handler(message.params));
  }

  async eval(expression) {
    const result = await this.send("Runtime.evaluate", {
      expression, awaitPromise: true, returnByValue: true,
    });
    if (result.exceptionDetails) {
      throw new Error(`${expression}\n${JSON.stringify(result.exceptionDetails)}`);
    }
    return result.result.value;
  }

  async waitFor(expression, timeout = 10000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
      if (await this.eval(expression)) return true;
      await new Promise((r) => setTimeout(r, 100));
    }
    throw new Error(`timed out waiting for: ${expression}`);
  }

  async load(url) {
    const loaded = new Promise((resolve) => this.on("Page.loadEventFired", resolve));
    await this.send("Page.navigate", { url });
    await loaded;
    await this.waitFor("Boolean(window.Redline && window.Redline.app)");
  }
}

// Select `text` inside the block with class `blockClass`, like a mouse drag would.
const selectText = (blockClass, text) => `(() => {
  const block = document.querySelector(".${blockClass}");
  const index = new Redline.TextIndex(block);
  const start = index.text.indexOf(${JSON.stringify(text)});
  const range = index.rangeFor(start, start + ${JSON.stringify(text)}.length);
  const selection = document.getSelection();
  selection.removeAllRanges();
  selection.addRange(range);
  document.dispatchEvent(new MouseEvent("mouseup", { bubbles: true }));
  return start;
})()`;

async function main() {
  const { proc, page, profile } = await Browser.launch(browserPath);
  const requests = [];
  const out = {};
  try {
    await page.send("Page.enable");
    await page.send("Runtime.enable");
    page.on("Runtime.exceptionThrown", (p) => (out.exceptions = [...(out.exceptions || []), p.exceptionDetails]));
    await page.send("Fetch.enable", { patterns: [{ urlPattern: "https://api.github.com/*" }] });
    page.on("Fetch.requestPaused", async ({ requestId, request }) => {
      if (request.method !== "OPTIONS") requests.push({ url: request.url, method: request.method, body: request.postData });
      await page.send("Fetch.fulfillRequest", {
        requestId,
        responseCode: request.method === "OPTIONS" ? 204 : 201,
        responseHeaders: [
          { name: "Content-Type", value: "application/json" },
          { name: "Access-Control-Allow-Origin", value: "*" },
          { name: "Access-Control-Allow-Methods", value: "PUT, GET, POST" },
          { name: "Access-Control-Allow-Headers", value: "Authorization, Content-Type, Accept, X-GitHub-Api-Version" },
        ],
        body: Buffer.from("{}").toString("base64"),
      });
    });

    await page.load(pageUrl);
    out.initial = await page.eval(`({
      marks: Array.from(document.querySelectorAll("mark.redline-mark")).map(m => [m.dataset.thread, m.textContent]),
      toggle: document.querySelector(".redline-toggle").textContent,
      outdated: Array.from(document.querySelectorAll(".redline-thread")).filter(c => !Redline.app.threads.find(t => t.id === c.dataset.thread).located).map(c => c.dataset.thread),
      bodyHtml: document.querySelector('.redline-thread[data-thread="t1"] .redline-body').innerHTML,
      sourceLink: document.querySelector('.redline-thread[data-thread="t1"] .redline-meta a')?.href ?? null,
    })`);

    // Clicking a highlight opens the panel on its thread.
    await page.eval(`document.querySelector('mark[data-thread="t1"]').click()`);
    out.panelOpenedByMark = await page.eval(`!document.querySelector(".redline-panel").hidden`);

    // New comment on a selection, signing in as a guest first.
    await page.eval(selectText("redline-b1", "some words"));
    out.addButtonShown = await page.eval(`!document.querySelector(".redline-add").hidden`);
    await page.eval(`document.querySelector(".redline-add").dispatchEvent(new MouseEvent("mousedown", {bubbles: true}))`);
    await page.eval(`(() => {
      const form = document.querySelector(".redline-guest");
      form.querySelector('input[type="password"]').value = "wrong";
      form.querySelector('input[type="text"]').value = "Erin";
      form.requestSubmit();
    })()`);
    await page.waitFor(`document.querySelector(".redline-status.redline-error")?.textContent.includes("Wrong passphrase")`);
    out.passphraseKeptAfterError = await page.eval(`document.querySelector('.redline-guest input[type="password"]').value`);
    await page.eval(`(() => {
      const form = document.querySelector(".redline-guest");
      form.querySelector('input[type="password"]').value = ${JSON.stringify(passphrase)};
      form.requestSubmit();
    })()`);
    await page.waitFor(`Boolean(document.querySelector(".redline-draft textarea"))`);
    await page.eval(`(() => {
      const form = document.querySelector(".redline-draft form");
      form.querySelector("textarea").value = "Please rephrase <b>this</b>.";
      form.requestSubmit();
    })()`);
    await page.waitFor(`document.querySelector(".redline-status")?.textContent.includes("Comment saved")`);
    out.afterSave = await page.eval(`({
      marks: document.querySelectorAll("mark.redline-mark").length,
      pendingLabel: Array.from(document.querySelectorAll(".redline-meta")).some(m => m.textContent.includes("not yet built")),
    })`);

    // Resolve an existing thread.
    await page.eval(`Array.from(document.querySelectorAll('.redline-thread[data-thread="t1"] button')).find(b => b.textContent === "Resolve").click()`);
    await page.waitFor(`document.querySelector('.redline-thread[data-thread="t1"]').classList.contains("redline-thread-resolved")`);

    // After a reload the unsaved-to-build comments are still shown.
    await page.load(pageUrl);
    out.afterReload = await page.eval(`({
      threads: Redline.app.threads.map(t => [t.id, t.status, Boolean(t.pending), t.located]),
      signedIn: Redline.app.user?.author ?? null,
    })`);

    // The keytool page creates a key that decrypts back to the token.
    const loaded = new Promise((resolve) => page.on("Page.loadEventFired", resolve));
    await page.send("Page.navigate", { url: new URL("_static/redline/keytool.html", pageUrl).href });
    await loaded;
    await page.eval(`(() => {
      document.getElementById("token").value = "github_pat_example";
      document.getElementById("generate").click();
      document.getElementById("create").requestSubmit();
    })()`);
    await page.waitFor(`!document.getElementById("result").hidden`, 30000);
    out.keytool = await page.eval(`Redline.GuestKey.decrypt(
      document.getElementById("key").value, document.getElementById("passphrase").value)`);
  } catch (error) {
    out.error = String(error.stack || error);
    out.debug = await page.eval(`({
      status: document.querySelector(".redline-status")?.textContent,
      marks: Array.from(document.querySelectorAll("mark.redline-mark")).map(m => [m.dataset.thread, m.textContent]),
      buttons: Array.from(document.querySelectorAll('.redline-thread[data-thread="t1"] button')).map(b => b.textContent),
    })`).catch((e) => String(e));
  } finally {
    out.requests = requests;
    await new Promise((resolve) => {
      proc.on("exit", resolve);
      proc.kill();
    });
    try {
      // Helper processes may still write to the profile briefly after exit.
      fs.rmSync(profile, { recursive: true, force: true, maxRetries: 10, retryDelay: 200 });
    } catch (error) {
      // Best effort: it is a temporary directory.
    }
  }
  console.log(JSON.stringify(out));
  process.exit(0);
}

if (require.main === module) {
  main();
}

module.exports = { Browser, Page };
