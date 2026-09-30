/*
 * sphinx-redline browser script.
 *
 * A classic script rather than an ES module, so it also works for docs opened
 * from file://. In the browser it exposes window.Redline and starts itself;
 * under Node (tests, keytool) it exports the same classes instead.
 *
 * All comment text is inserted with textContent, never innerHTML: comments
 * are written by readers and must not be able to inject markup.
 */
(function (root, factory) {
  "use strict";
  const api = factory(root);
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  } else {
    root.Redline = api;
    api.RedlineApp.autostart(root.document);
  }
})(typeof window !== "undefined" ? window : globalThis, function (root) {
  "use strict";

  const CONTEXT_LENGTH = 32;
  const UI_CLASS = "redline-ui";

  /** Whitespace normalisation; must match blocks.TextNormalizer in Python. */
  class TextNormalizer {
    static normalize(text) {
      return text.replace(/\s+/g, " ").trim();
    }
  }

  /** Byte, base64 and random helpers shared by the crypto and forge code. */
  class Bytes {
    static fromText(text) {
      return new TextEncoder().encode(text);
    }

    static toText(bytes) {
      return new TextDecoder().decode(bytes);
    }

    static toBase64(bytes) {
      let binary = "";
      for (const byte of new Uint8Array(bytes)) {
        binary += String.fromCharCode(byte);
      }
      return btoa(binary);
    }

    static toBase64Url(bytes) {
      return Bytes.toBase64(bytes).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
    }

    static fromBase64Url(text) {
      const base64 = text.replace(/-/g, "+").replace(/_/g, "/");
      const binary = atob(base64 + "=".repeat((4 - (base64.length % 4)) % 4));
      return Uint8Array.from(binary, (c) => c.charCodeAt(0));
    }

    static random(length) {
      return root.crypto.getRandomValues(new Uint8Array(length));
    }

    static randomHex(length) {
      return Array.from(Bytes.random(length), (b) => b.toString(16).padStart(2, "0")).join("");
    }
  }

  /**
   * The guest key: a forge token encrypted with a passphrase.
   *
   * Format: "rl1.<iterations>.<salt>.<iv>.<ciphertext>", base64url parts.
   * The key is derived with PBKDF2-SHA-256 and the token encrypted with
   * AES-256-GCM, both from WebCrypto, so no crypto library is needed.
   */
  class GuestKey {
    static PREFIX = "rl1";
    static ITERATIONS = 600000;

    static async _deriveKey(passphrase, salt, iterations) {
      const subtle = root.crypto.subtle;
      const material = await subtle.importKey("raw", Bytes.fromText(passphrase), "PBKDF2", false, [
        "deriveKey",
      ]);
      return subtle.deriveKey(
        { name: "PBKDF2", hash: "SHA-256", salt, iterations },
        material,
        { name: "AES-GCM", length: 256 },
        false,
        ["encrypt", "decrypt"]
      );
    }

    static async encrypt(token, passphrase, iterations = GuestKey.ITERATIONS) {
      const salt = Bytes.random(16);
      const iv = Bytes.random(12);
      const key = await GuestKey._deriveKey(passphrase, salt, iterations);
      const ciphertext = await root.crypto.subtle.encrypt(
        { name: "AES-GCM", iv },
        key,
        Bytes.fromText(token)
      );
      return [
        GuestKey.PREFIX,
        String(iterations),
        Bytes.toBase64Url(salt),
        Bytes.toBase64Url(iv),
        Bytes.toBase64Url(ciphertext),
      ].join(".");
    }

    static async decrypt(guestKey, passphrase) {
      const parts = guestKey.trim().split(".");
      const iterations = Number(parts[1]);
      if (parts.length !== 5 || parts[0] !== GuestKey.PREFIX || !Number.isInteger(iterations)) {
        throw new Error("The site's guest key is not in a supported format.");
      }
      const [salt, iv, ciphertext] = parts.slice(2).map(Bytes.fromBase64Url);
      const key = await GuestKey._deriveKey(passphrase, salt, iterations);
      try {
        const plain = await root.crypto.subtle.decrypt({ name: "AES-GCM", iv }, key, ciphertext);
        return Bytes.toText(plain);
      } catch (error) {
        throw new Error("Wrong passphrase.");
      }
    }
  }

  /** A failed forge API request, with a message meant for the reader. */
  class ForgeError extends Error {
    constructor(status, message) {
      super(message);
      this.status = status;
    }
  }

  /** Common request handling for the GitHub and GitLab APIs. */
  class Forge {
    constructor(settings, token, fetchImpl) {
      this.settings = settings;
      this.token = token;
      this._fetch = fetchImpl || root.fetch.bind(root);
    }

    static create(settings, token, fetchImpl) {
      const Kind = settings.kind === "gitlab" ? GitLabForge : GitHubForge;
      return new Kind(settings, token, fetchImpl);
    }

    async _request(method, url, body) {
      const init = { method, headers: { ...this._headers() } };
      if (body !== undefined) {
        init.headers["Content-Type"] = "application/json";
        init.body = JSON.stringify(body);
      }
      let response;
      try {
        response = await this._fetch(url, init);
      } catch (error) {
        throw new ForgeError(0, `Could not reach ${this.settings.url}: ${error.message}`);
      }
      if (!response.ok) {
        let detail = "";
        try {
          const data = await response.json();
          detail = data.message || data.error_description || data.error || "";
          if (typeof detail !== "string") {
            detail = JSON.stringify(detail);
          }
        } catch (error) {
          detail = response.statusText;
        }
        throw new ForgeError(response.status, this._explain(response.status, detail));
      }
      return response.status === 204 ? null : response.json();
    }

    _explain(status, detail) {
      const target = `${this.settings.repository} (branch "${this.settings.branch}")`;
      if (status === 401) {
        return "The sign-in has expired or its token is no longer valid. Please sign in again.";
      }
      if (status === 403 || status === 404) {
        return `Not allowed to save to ${target}. The token may lack write access, or the branch may not exist. (${status}: ${detail})`;
      }
      return `Saving failed (${status}: ${detail}).`;
    }
  }

  class GitHubForge extends Forge {
    _headers() {
      return {
        Authorization: `Bearer ${this.token}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
      };
    }

    createFile(path, text, message) {
      const [owner, repo] = this.settings.repository.split("/");
      const encodedPath = path.split("/").map(encodeURIComponent).join("/");
      const url =
        `${this.settings.apiUrl}/repos/${encodeURIComponent(owner)}/${encodeURIComponent(repo)}` +
        `/contents/${encodedPath}`;
      return this._request("PUT", url, {
        message,
        content: Bytes.toBase64(Bytes.fromText(text)),
        branch: this.settings.branch,
      });
    }
  }

  class GitLabForge extends Forge {
    _headers() {
      return { Authorization: `Bearer ${this.token}` };
    }

    createFile(path, text, message) {
      const url =
        `${this.settings.apiUrl}/projects/${encodeURIComponent(this.settings.repository)}` +
        `/repository/files/${encodeURIComponent(path)}`;
      return this._request("POST", url, {
        branch: this.settings.branch,
        content: text,
        commit_message: message,
      });
    }

    currentUser() {
      return this._request("GET", `${this.settings.apiUrl}/user`);
    }
  }

  /** Builds comment files in the format read by comments.Comment in Python. */
  class CommentFactory {
    static FORMAT_VERSION = 1;

    static timestamp(now) {
      return now.toISOString().replace(/\.\d+Z$/, "Z");
    }

    static newId(now) {
      const stamp = CommentFactory.timestamp(now).replace(/[-:]/g, "");
      return `${stamp}-${Bytes.randomHex(4)}`;
    }

    static thread(anchor, author, auth, body, now = new Date()) {
      return {
        version: CommentFactory.FORMAT_VERSION,
        id: CommentFactory.newId(now),
        thread: null,
        author,
        auth,
        created: CommentFactory.timestamp(now),
        body,
        status: null,
        anchor,
      };
    }

    static reply(threadId, author, auth, body, status, now = new Date()) {
      return {
        version: CommentFactory.FORMAT_VERSION,
        id: CommentFactory.newId(now),
        thread: threadId,
        author,
        auth,
        created: CommentFactory.timestamp(now),
        body,
        status,
        anchor: null,
      };
    }

    static path(comment) {
      return `comments/${comment.id}.json`;
    }

    static serialize(comment) {
      return JSON.stringify(comment, null, 2) + "\n";
    }

    static commitMessage(comment) {
      const docname = comment.anchor ? comment.anchor.docname : `thread ${comment.thread}`;
      return `Add comment ${comment.id} on ${docname}`;
    }
  }

  /** sessionStorage/localStorage access that tolerates blocked storage. */
  class Store {
    constructor(storage) {
      this._storage = storage;
    }

    static session() {
      try {
        return new Store(root.sessionStorage);
      } catch (error) {
        return new Store(null);
      }
    }

    static local() {
      try {
        return new Store(root.localStorage);
      } catch (error) {
        return new Store(null);
      }
    }

    get(key) {
      try {
        const value = this._storage && this._storage.getItem(key);
        return value ? JSON.parse(value) : null;
      } catch (error) {
        return null;
      }
    }

    set(key, value) {
      try {
        if (this._storage) {
          this._storage.setItem(key, JSON.stringify(value));
        }
      } catch (error) {
        // Storage full or blocked: the value is only a convenience.
      }
    }

    remove(key) {
      try {
        if (this._storage) {
          this._storage.removeItem(key);
        }
      } catch (error) {
        // Nothing to clean up.
      }
    }
  }

  /**
   * "Sign in with GitLab": OAuth 2 authorization code flow with PKCE, done
   * entirely in the browser. GitLab's token endpoint accepts cross-origin
   * requests, so no server is needed. The redirect URI is the site root,
   * which must be registered in the GitLab OAuth application.
   */
  class GitLabOAuth {
    static STATE_KEY = "redline-oauth";

    constructor(settings, store, location, fetchImpl) {
      this.settings = settings;
      this._store = store;
      this._location = location;
      this._fetch = fetchImpl || root.fetch.bind(root);
    }

    static async challenge(verifier) {
      const digest = await root.crypto.subtle.digest("SHA-256", Bytes.fromText(verifier));
      return Bytes.toBase64Url(digest);
    }

    redirectUri(contentRoot) {
      const url = new URL(contentRoot || "./", this._location.href);
      url.search = "";
      url.hash = "";
      return url.href;
    }

    async authorizeUrl(contentRoot) {
      const verifier = Bytes.toBase64Url(Bytes.random(48));
      const state = Bytes.toBase64Url(Bytes.random(16));
      const redirectUri = this.redirectUri(contentRoot);
      this._store.set(GitLabOAuth.STATE_KEY, {
        verifier,
        state,
        redirectUri,
        returnUrl: this._location.href,
      });
      const params = new URLSearchParams({
        client_id: this.settings.gitlabClientId,
        redirect_uri: redirectUri,
        response_type: "code",
        state,
        scope: "api",
        code_challenge: await GitLabOAuth.challenge(verifier),
        code_challenge_method: "S256",
      });
      return `${this.settings.url}/oauth/authorize?${params}`;
    }

    /** Finish a sign-in if the current URL is the OAuth redirect; else null. */
    async complete() {
      const url = new URL(this._location.href);
      const code = url.searchParams.get("code");
      const pending = this._store.get(GitLabOAuth.STATE_KEY);
      if (!code || !pending || url.searchParams.get("state") !== pending.state) {
        return null;
      }
      this._store.remove(GitLabOAuth.STATE_KEY);
      const response = await this._fetch(`${this.settings.url}/oauth/token`, {
        method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded" },
        body: new URLSearchParams({
          client_id: this.settings.gitlabClientId,
          code,
          grant_type: "authorization_code",
          redirect_uri: pending.redirectUri,
          code_verifier: pending.verifier,
        }),
      });
      if (!response.ok) {
        throw new ForgeError(response.status, "GitLab sign-in failed. Please try again.");
      }
      const data = await response.json();
      return { token: data.access_token, returnUrl: pending.returnUrl };
    }
  }

  /**
   * The text of one block element, normalised like the build does, with the
   * DOM position of every character. Text in headerlinks, code line numbers,
   * footnote brackets, buttons and our own UI is skipped, since the build's
   * node.astext() does not contain it.
   */
  class TextIndex {
    static EXCLUDE = `.headerlink, .linenos, .fn-bracket, button, .copybtn, .${UI_CLASS}`;

    constructor(element) {
      this.element = element;
      this.positions = [];
      const chars = [];
      const doc = element.ownerDocument;
      const walker = doc.createTreeWalker(element, root.NodeFilter.SHOW_TEXT, {
        acceptNode: (node) => (this._excluded(node) ? 2 : 1), // FILTER_REJECT : FILTER_ACCEPT
      });
      let pendingSpace = null;
      for (let node = walker.nextNode(); node; node = walker.nextNode()) {
        const value = node.nodeValue;
        for (let i = 0; i < value.length; i++) {
          if (/\s/.test(value[i])) {
            if (chars.length && !pendingSpace) {
              pendingSpace = [node, i];
            }
            continue;
          }
          if (pendingSpace) {
            chars.push(" ");
            this.positions.push(pendingSpace);
            pendingSpace = null;
          }
          chars.push(value[i]);
          this.positions.push([node, i]);
        }
      }
      this.text = chars.join("");
    }

    _excluded(node) {
      const parent = node.parentElement;
      const excluded = parent && parent.closest(TextIndex.EXCLUDE);
      return Boolean(excluded && this.element.contains(excluded));
    }

    /** DOM range covering normalised text [start, end), or null. */
    rangeFor(start, end) {
      if (!(start >= 0 && start < end && end <= this.positions.length)) {
        return null;
      }
      const range = this.element.ownerDocument.createRange();
      const [startNode, startOffset] = this.positions[start];
      const [endNode, endOffset] = this.positions[end - 1];
      range.setStart(startNode, startOffset);
      range.setEnd(endNode, endOffset + 1);
      return range;
    }

    /** Number of normalised characters before a DOM boundary point. */
    offsetOf(container, offset) {
      const point = this.element.ownerDocument.createRange();
      point.setStart(container, offset);
      let low = 0;
      let high = this.positions.length;
      while (low < high) {
        const mid = (low + high) >> 1;
        const [node, index] = this.positions[mid];
        if (point.comparePoint(node, index) < 0) {
          low = mid + 1;
        } else {
          high = mid;
        }
      }
      return low;
    }

    /** Find `quote` near `hint`: the occurrence whose start is closest. */
    find(quote, hint) {
      let best = -1;
      for (let at = this.text.indexOf(quote); at !== -1; at = this.text.indexOf(quote, at + 1)) {
        if (best === -1 || Math.abs(at - hint) < Math.abs(best - hint)) {
          best = at;
        }
      }
      return best;
    }
  }

  /** Wraps DOM ranges in <mark> elements linked to a thread. */
  class Highlighter {
    static wrap(range, threadId, resolved) {
      const doc = range.startContainer.ownerDocument;
      const container = range.commonAncestorContainer;
      const textNodes = [];
      if (container.nodeType === 3) {
        textNodes.push(container);
      } else {
        const walker = doc.createTreeWalker(container, root.NodeFilter.SHOW_TEXT);
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if (range.intersectsNode(node)) {
            textNodes.push(node);
          }
        }
      }
      const marks = [];
      for (const node of textNodes) {
        const start = node === range.startContainer ? range.startOffset : 0;
        const end = node === range.endContainer ? range.endOffset : node.nodeValue.length;
        if (start >= end || !node.nodeValue.slice(start, end).trim()) {
          continue;
        }
        if (end < node.nodeValue.length) {
          node.splitText(end);
        }
        const target = start > 0 ? node.splitText(start) : node;
        const mark = doc.createElement("mark");
        mark.className = resolved ? "redline-mark redline-resolved" : "redline-mark";
        mark.dataset.thread = threadId;
        target.parentNode.insertBefore(mark, target);
        mark.appendChild(target);
        marks.push(mark);
      }
      return marks;
    }
  }

  /** Small DOM builder: el("p", {className: "x"}, "text", child). */
  function el(tag, props, ...children) {
    const node = root.document.createElement(tag);
    Object.assign(node, props || {});
    for (const child of children) {
      if (child !== null && child !== undefined && child !== false) {
        node.append(child);
      }
    }
    return node;
  }

  /**
   * The page's comments: renders highlights and the comment panel, and
   * handles signing in, new comments, replies and resolving.
   */
  class RedlineApp {
    static SESSION_KEY = "redline-session";
    static PENDING_KEY = "redline-pending";
    static NAME_KEY = "redline-name";

    constructor(doc, data) {
      this.doc = doc;
      this.data = data;
      this.forge = data.forge;
      this.session = Store.session();
      this.local = Store.local();
      this.threads = [];
      this.draftAnchor = null;
      this.busy = false;
    }

    static autostart(doc) {
      if (!doc) {
        return;
      }
      const start = () => {
        const script = doc.getElementById("redline-data");
        if (!script) {
          return;
        }
        const app = new RedlineApp(doc, JSON.parse(script.textContent));
        root.Redline.app = app;
        app.start();
      };
      if (doc.readyState === "loading") {
        doc.addEventListener("DOMContentLoaded", start);
      } else {
        start();
      }
    }

    get _sessionKey() {
      return this.forge ? `${RedlineApp.SESSION_KEY}:${this.forge.url}/${this.forge.repository}` : "";
    }

    get _pendingKey() {
      // Per site and page: several sites can share one origin (and one tab).
      const site = new URL(this._contentRoot(), this.doc.defaultView.location.href).href;
      const target = this.forge ? `${this.forge.repository}@${this.forge.branch}` : "";
      return `${RedlineApp.PENDING_KEY}:${site}:${target}:${this.data.docname}`;
    }

    get user() {
      return this.forge ? this.session.get(this._sessionKey) : null;
    }

    start() {
      this.threads = this._mergePending(this.data.threads);
      this._buildChrome();
      this._placeAll();
      this.render();
      this.doc.addEventListener("mouseup", () => setTimeout(() => this._onSelection(), 0));
      this.doc.addEventListener("keyup", (event) => {
        if (event.shiftKey || event.key === "Shift") {
          this._onSelection();
        }
      });
      this.doc.addEventListener("click", (event) => this._onClick(event));
      this._completeOAuth();
    }

    // ----- data -------------------------------------------------------------

    _mergePending(threads) {
      const pending = this.session.get(this._pendingKey) || { threads: [], replies: [] };
      const known = new Set();
      for (const thread of threads) {
        for (const comment of thread.comments) {
          known.add(comment.id);
        }
      }
      pending.threads = pending.threads.filter((t) => !known.has(t.id));
      pending.replies = pending.replies.filter((r) => !known.has(r.comment.id));
      this.session.set(this._pendingKey, pending);
      const merged = threads.map((t) => ({ ...t, comments: [...t.comments] }));
      for (const thread of pending.threads) {
        merged.push({ ...thread, pending: true });
      }
      for (const reply of pending.replies) {
        const thread = merged.find((t) => t.id === reply.thread);
        if (thread) {
          this._applyReply(thread, reply.comment);
        }
      }
      return merged;
    }

    _remember(kind, entry) {
      const pending = this.session.get(this._pendingKey) || { threads: [], replies: [] };
      pending[kind].push(entry);
      this.session.set(this._pendingKey, pending);
    }

    _applyReply(thread, comment) {
      thread.comments.push({ ...comment, pending: true });
      if (comment.status) {
        thread.status = comment.status;
      }
    }

    // ----- placing highlights -----------------------------------------------

    _block(blockId) {
      return blockId ? this.doc.querySelector(`.redline-b${blockId.slice(1)}`) : null;
    }

    _placeAll() {
      for (const mark of this.doc.querySelectorAll("mark.redline-mark")) {
        mark.replaceWith(...mark.childNodes);
      }
      this.doc.body.normalize();
      for (const thread of this.threads) {
        thread.located = this._place(thread);
      }
    }

    _place(thread) {
      const placement = thread.placement;
      if (placement.state !== "anchored") {
        return false;
      }
      const block = this._block(placement.block);
      if (!block) {
        return false;
      }
      const index = new TextIndex(block);
      let start = placement.start;
      if (index.text.slice(start, placement.end) !== placement.quote) {
        start = index.find(placement.quote, placement.start);
      }
      const range = start === -1 ? null : index.rangeFor(start, start + placement.quote.length);
      if (!range) {
        return false;
      }
      thread.marks = Highlighter.wrap(range, thread.id, thread.status === "resolved");
      return thread.marks.length > 0;
    }

    // ----- selection → new comment ------------------------------------------

    _selectionAnchor() {
      const selection = this.doc.getSelection();
      if (!selection || selection.isCollapsed || selection.rangeCount === 0) {
        return null;
      }
      const range = selection.getRangeAt(0);
      const startElement =
        range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
      const block = startElement && startElement.closest(".redline-block");
      if (!block || startElement.closest(`.${UI_CLASS}`)) {
        return null;
      }
      const blockId = Array.from(block.classList)
        .map((name) => /^redline-b(\d+)$/.exec(name))
        .find(Boolean);
      const info = blockId && this.data.blocks[`b${blockId[1]}`];
      if (!info) {
        return null;
      }
      const index = new TextIndex(block);
      let start = index.offsetOf(range.startContainer, range.startOffset);
      let end = block.contains(range.endContainer)
        ? index.offsetOf(range.endContainer, range.endOffset)
        : index.text.length;
      while (start < end && index.text[start] === " ") start++;
      while (end > start && index.text[end - 1] === " ") end--;
      if (start >= end) {
        return null;
      }
      return {
        block: `b${blockId[1]}`,
        start,
        end,
        anchor: {
          docname: this.data.docname,
          source: info.source,
          lines: info.lines,
          commit: this.data.commit,
          quote: index.text.slice(start, end),
          prefix: index.text.slice(Math.max(0, start - CONTEXT_LENGTH), start),
          suffix: index.text.slice(end, end + CONTEXT_LENGTH),
        },
        rect: range.getBoundingClientRect(),
      };
    }

    _onSelection() {
      const selected = this._selectionAnchor();
      this.selected = selected;
      if (!selected || !this.forge) {
        this.addButton.hidden = true;
        return;
      }
      const view = this.doc.defaultView;
      this.addButton.hidden = false;
      this.addButton.style.top = `${selected.rect.bottom + view.scrollY + 6}px`;
      this.addButton.style.left = `${Math.max(8, selected.rect.left + view.scrollX)}px`;
    }

    startDraft() {
      if (!this.selected) {
        return;
      }
      this.draftAnchor = this.selected;
      this.addButton.hidden = true;
      this._setStatus("");
      this.open();
      this.render();
      const field = this.panel.querySelector(".redline-draft textarea, .redline-auth input");
      if (field) {
        field.focus();
      }
    }

    // ----- saving -----------------------------------------------------------

    async _save(comment) {
      const user = this.user;
      const forge = Forge.create(this.forge, user.token);
      await forge.createFile(
        CommentFactory.path(comment),
        CommentFactory.serialize(comment),
        CommentFactory.commitMessage(comment)
      );
    }

    /**
     * Run an async action with a busy guard. On success the panel is
     * re-rendered and the returned message shown; on failure only the error
     * is shown, so whatever the reader typed stays in the forms.
     */
    async _run(action) {
      if (this.busy) {
        return;
      }
      this.busy = true;
      this._setStatus("Working…");
      try {
        const message = await action();
        this.busy = false;
        this._setStatus(message || "");
        this.render();
      } catch (error) {
        this.busy = false;
        if (error.status === 401) {
          this.session.remove(this._sessionKey);
          this.render();
        }
        this._setStatus(error.message, true);
      }
    }

    _setStatus(text, isError) {
      this.status.textContent = text;
      this.status.className = `redline-status${isError ? " redline-error" : ""}`;
      this.status.hidden = !text;
      this.status.setAttribute("role", isError ? "alert" : "status");
    }

    submitThread(body) {
      return this._run(async () => {
        const draft = this.draftAnchor;
        const user = this.user;
        const comment = CommentFactory.thread(draft.anchor, user.author, user.auth, body);
        await this._save(comment);
        const thread = {
          id: comment.id,
          status: "open",
          quote: draft.anchor.quote,
          source: draft.anchor.source,
          lines: draft.anchor.lines,
          commit: draft.anchor.commit,
          placement: {
            state: "anchored",
            block: draft.block,
            start: draft.start,
            end: draft.end,
            quote: draft.anchor.quote,
          },
          comments: [comment],
        };
        this._remember("threads", thread);
        this.threads.push({ ...thread, pending: true });
        this.draftAnchor = null;
        this._placeAll();
        return "Comment saved. Everyone sees it after the next documentation build.";
      });
    }

    submitReply(thread, body, status) {
      return this._run(async () => {
        const user = this.user;
        const comment = CommentFactory.reply(thread.id, user.author, user.auth, body, status);
        await this._save(comment);
        this._remember("replies", { thread: thread.id, comment });
        this._applyReply(thread, comment);
        this._placeAll();
        return "Saved. Everyone sees it after the next documentation build.";
      });
    }

    // ----- signing in -------------------------------------------------------

    signInGuest(name, passphrase) {
      return this._run(async () => {
        const token = await GuestKey.decrypt(this.forge.guestKey, passphrase);
        this.local.set(RedlineApp.NAME_KEY, name);
        this.session.set(this._sessionKey, { mode: "guest", token, author: name, auth: "guest" });
        return `Signed in as ${name} (guest).`;
      });
    }

    async signInGitLab() {
      const oauth = new GitLabOAuth(this.forge, this.session, this.doc.defaultView.location);
      this.doc.defaultView.location.assign(await oauth.authorizeUrl(this._contentRoot()));
    }

    _contentRoot() {
      return this.doc.documentElement.dataset.content_root || "./";
    }

    _completeOAuth() {
      if (!this.forge || this.forge.kind !== "gitlab" || !this.forge.gitlabClientId) {
        return;
      }
      const view = this.doc.defaultView;
      const oauth = new GitLabOAuth(this.forge, this.session, view.location);
      this._run(async () => {
        const result = await oauth.complete();
        if (!result) {
          return;
        }
        const forge = Forge.create(this.forge, result.token);
        const profile = await forge.currentUser();
        this.session.set(this._sessionKey, {
          mode: "gitlab",
          token: result.token,
          author: profile.name || profile.username,
          auth: `gitlab:${profile.username}`,
        });
        view.location.replace(result.returnUrl);
      });
    }

    signOut() {
      this.session.remove(this._sessionKey);
      this._setStatus("");
      this.render();
    }

    // ----- UI -----------------------------------------------------------------

    _buildChrome() {
      this.toggle = el("button", { type: "button", className: `${UI_CLASS} redline-toggle` });
      this.toggle.addEventListener("click", () => (this.panel.hidden ? this.open() : this.close()));
      this.addButton = el("button", {
        type: "button",
        className: `${UI_CLASS} redline-add`,
        hidden: true,
        textContent: "Comment",
      });
      // mousedown: act before the click clears the selection.
      this.addButton.addEventListener("mousedown", (event) => {
        event.preventDefault();
        this.startDraft();
      });
      this.status = el("p", { className: "redline-status", hidden: true });
      this.content = el("div", { className: "redline-content" });
      this.panel = el(
        "aside",
        { className: `${UI_CLASS} redline-panel`, hidden: true, ariaLabel: "Comments" },
        el(
          "header",
          { className: "redline-header" },
          el("strong", {}, "Comments"),
          this._button("Close", () => this.close(), "redline-close")
        ),
        this.status,
        this.content
      );
      this.doc.body.append(this.toggle, this.addButton, this.panel);
    }

    open() {
      this.panel.hidden = false;
      this.doc.body.classList.add("redline-open");
    }

    close() {
      this.panel.hidden = true;
      this.doc.body.classList.remove("redline-open");
    }

    _onClick(event) {
      const mark = event.target.closest && event.target.closest("mark.redline-mark");
      if (mark) {
        this.focusThread(mark.dataset.thread);
      }
    }

    focusThread(threadId) {
      this.open();
      const card = this.panel.querySelector(`[data-thread="${CSS.escape(threadId)}"]`);
      if (card) {
        card.scrollIntoView({ block: "nearest" });
        card.classList.add("redline-flash");
        setTimeout(() => card.classList.remove("redline-flash"), 1200);
      }
    }

    render() {
      const open = this.threads.filter((t) => t.status !== "resolved").length;
      this.toggle.textContent = open ? `Comments (${open})` : "Comments";
      const located = this.threads.filter((t) => t.located);
      const outdated = this.threads.filter((t) => !t.located);
      this.content.replaceChildren(
        this._authView(),
        this.draftAnchor ? this._draftView() : null,
        located.length || outdated.length || this.draftAnchor
          ? null
          : el("p", {
              className: "redline-empty",
              textContent: this.forge
                ? "No comments on this page yet. Select text to add one."
                : "No comments on this page.",
            }),
        ...located.map((t) => this._threadView(t)),
        outdated.length ? el("h3", { textContent: "Outdated" }) : null,
        outdated.length
          ? el("p", {
              className: "redline-hint",
              textContent: "The text these comments were made on has changed or moved.",
            })
          : null,
        ...outdated.map((t) => this._threadView(t))
      );
    }

    _button(label, onClick, className) {
      const button = el("button", { type: "button", textContent: label, className: className || "" });
      button.addEventListener("click", onClick);
      return button;
    }

    _authView() {
      const box = el("div", { className: "redline-auth" });
      if (!this.forge) {
        box.append(el("p", { textContent: "Commenting is not enabled on this site." }));
        return box;
      }
      const user = this.user;
      if (user) {
        box.append(
          el(
            "p",
            {},
            `Signed in as ${user.author}${user.mode === "guest" ? " (guest)" : ""}. `,
            this._button("Sign out", () => this.signOut(), "redline-link")
          )
        );
        return box;
      }
      if (this.forge.guestKey) {
        const name = el("input", {
          type: "text",
          required: true,
          placeholder: "Your name",
          value: this.local.get(RedlineApp.NAME_KEY) || "",
          autocomplete: "name",
        });
        const passphrase = el("input", {
          type: "password",
          required: true,
          placeholder: "Guest passphrase",
          autocomplete: "current-password",
        });
        const submit = el("button", { type: "submit", textContent: "Sign in as guest" });
        const form = el("form", { className: "redline-guest" }, name, passphrase, submit);
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          this.signInGuest(name.value.trim(), passphrase.value);
        });
        box.append(form);
      }
      if (this.forge.kind === "gitlab" && this.forge.gitlabClientId) {
        box.append(this._button("Sign in with GitLab", () => this.signInGitLab(), "redline-oauth"));
      }
      if (!box.childElementCount) {
        box.append(
          el("p", { textContent: "No sign-in method is configured for this site, so comments are read-only." })
        );
      }
      return box;
    }

    _draftView() {
      const quote = el("blockquote", { className: "redline-quote", textContent: this.draftAnchor.anchor.quote });
      const box = el("div", { className: "redline-draft" }, el("h3", { textContent: "New comment" }), quote);
      if (!this.user) {
        box.append(el("p", { className: "redline-hint", textContent: "Sign in above to comment." }));
      } else {
        const text = el("textarea", { rows: 4, required: true, placeholder: "Your comment" });
        const submit = el("button", { type: "submit", textContent: "Save comment" });
        const form = el("form", {}, text, submit, this._button("Cancel", () => this._cancelDraft()));
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          if (text.value.trim()) {
            this.submitThread(text.value.trim());
          }
        });
        box.append(form);
      }
      return box;
    }

    _cancelDraft() {
      this.draftAnchor = null;
      this.render();
    }

    _sourceLink(thread) {
      const template = this.data.sourceUrl;
      const placement = thread.placement;
      let source = thread.source;
      let lines = thread.lines;
      let commit = thread.commit;
      if (thread.located && placement.block && this.data.blocks[placement.block]) {
        ({ source, lines } = this.data.blocks[placement.block]);
        commit = this.data.commit;
      }
      if (!template || !source || !lines || !commit) {
        return null;
      }
      const href = template
        .replace("{commit}", encodeURIComponent(commit))
        .replace("{path}", source.split("/").map(encodeURIComponent).join("/"))
        .replace("{first}", String(Number(lines[0])))
        .replace("{last}", String(Number(lines[1])));
      const label = `${source}:${lines[0]}${lines[1] !== lines[0] ? `-${lines[1]}` : ""}`;
      return el("a", { href, textContent: label, target: "_blank", rel: "noopener" });
    }

    _threadView(thread) {
      const resolved = thread.status === "resolved";
      const card = el("article", {
        className: `redline-thread${resolved ? " redline-thread-resolved" : ""}`,
      });
      card.dataset.thread = thread.id;
      const quote = el("blockquote", { className: "redline-quote", textContent: thread.quote });
      if (thread.located) {
        quote.addEventListener("click", () => {
          thread.marks[0].scrollIntoView({ block: "center", behavior: "smooth" });
        });
      }
      const status = resolved ? "Resolved" : "Open";
      const meta = el(
        "div",
        { className: "redline-meta" },
        `${status}${thread.pending ? " · saved, not yet built" : ""}`,
        this._sourceLink(thread) ? " · " : null,
        this._sourceLink(thread)
      );
      const list = el(
        "ol",
        { className: "redline-comments" },
        ...thread.comments.map((c) =>
          el(
            "li",
            {},
            el("span", { className: "redline-author", textContent: c.author }),
            " ",
            el("time", { dateTime: c.created, textContent: c.created.slice(0, 10) }),
            c.status ? el("em", { textContent: ` — marked ${c.status}` }) : null,
            el("p", { className: "redline-body", textContent: c.body })
          )
        )
      );
      card.append(quote, meta, list);
      if (this.user) {
        const text = el("textarea", { rows: 2, placeholder: "Reply" });
        const reply = el("button", { type: "submit", textContent: "Reply" });
        const toggle = this._button(resolved ? "Reopen" : "Resolve", () => {
          const body = text.value.trim() || (resolved ? "Reopened." : "Resolved.");
          this.submitReply(thread, body, resolved ? "open" : "resolved");
        });
        const form = el("form", { className: "redline-reply" }, text, reply, toggle);
        form.addEventListener("submit", (event) => {
          event.preventDefault();
          if (text.value.trim()) {
            this.submitReply(thread, text.value.trim(), null);
          }
        });
        card.append(form);
      }
      return card;
    }
  }

  return {
    TextNormalizer,
    Bytes,
    GuestKey,
    Forge,
    ForgeError,
    GitHubForge,
    GitLabForge,
    CommentFactory,
    GitLabOAuth,
    Store,
    TextIndex,
    Highlighter,
    RedlineApp,
  };
});
