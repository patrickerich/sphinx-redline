// Unit tests for the browser script's DOM-free logic. Run by tests/test_js.py.
const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");

const R = require(path.join(__dirname, "../../src/sphinx_redline/static/redline/redline.js"));

const GITHUB = {
  kind: "github",
  url: "https://github.com",
  apiUrl: "https://api.github.com",
  repository: "owner/comments",
  branch: "redline",
};
const GITLAB = {
  kind: "gitlab",
  url: "https://gitlab.example.com",
  apiUrl: "https://gitlab.example.com/api/v4",
  repository: "group/sub/project",
  branch: "redline",
  gitlabClientId: "client-123",
};

function recordingFetch(status = 201, payload = {}) {
  const calls = [];
  const fetch = async (url, init) => {
    calls.push({ url, init });
    return { ok: status < 400, status, statusText: "x", json: async () => payload };
  };
  return { calls, fetch };
}

test("guest key round-trips and rejects a wrong passphrase", async () => {
  const key = await R.GuestKey.encrypt("ghp_secret", "correct horse battery staple", 1000);
  assert.match(key, /^rl1\.1000\.[\w-]+\.[\w-]+\.[\w-]+$/);
  assert.equal(await R.GuestKey.decrypt(key, "correct horse battery staple"), "ghp_secret");
  await assert.rejects(R.GuestKey.decrypt(key, "wrong"), /Wrong passphrase/);
  await assert.rejects(R.GuestKey.decrypt("rl2.1.a.b.c", "x"), /not in a supported format/);
});

test("PKCE challenge matches RFC 7636 appendix B", async () => {
  const challenge = await R.GitLabOAuth.challenge("dBjftJeZ4CVP-mB92K27uhbUJU1p1r_wW1gFWFOEjXk");
  assert.equal(challenge, "E9Melhoa2OwvFrEMTJguCHaoeK1t8URWbuGJSstw-cM");
});

test("GitHub files are created with the contents API", async () => {
  const { calls, fetch } = recordingFetch();
  const forge = R.Forge.create(GITHUB, "tok", fetch);
  await forge.createFile("comments/a b.json", "{\"x\": \"é\"}\n", "Add comment");
  assert.equal(calls.length, 1);
  const { url, init } = calls[0];
  assert.equal(url, "https://api.github.com/repos/owner/comments/contents/comments/a%20b.json");
  assert.equal(init.method, "PUT");
  assert.equal(init.headers.Authorization, "Bearer tok");
  const body = JSON.parse(init.body);
  assert.equal(body.branch, "redline");
  assert.equal(body.message, "Add comment");
  assert.equal(Buffer.from(body.content, "base64").toString("utf8"), "{\"x\": \"é\"}\n");
});

test("GitLab files are created with the repository files API", async () => {
  const { calls, fetch } = recordingFetch();
  const forge = R.Forge.create(GITLAB, "glpat", fetch);
  await forge.createFile("comments/id.json", "text", "Add comment");
  const { url, init } = calls[0];
  assert.equal(
    url,
    "https://gitlab.example.com/api/v4/projects/group%2Fsub%2Fproject/repository/files/comments%2Fid.json"
  );
  assert.equal(init.method, "POST");
  assert.deepEqual(JSON.parse(init.body), {
    branch: "redline",
    content: "text",
    commit_message: "Add comment",
  });
});

test("forge errors explain the likely cause", async () => {
  const { fetch } = recordingFetch(404, { message: "Branch not found" });
  const forge = R.Forge.create(GITHUB, "tok", fetch);
  await assert.rejects(forge.createFile("comments/x.json", "", "m"), (error) => {
    assert.equal(error.status, 404);
    assert.match(error.message, /owner\/comments \(branch "redline"\)/);
    assert.match(error.message, /Branch not found/);
    return true;
  });
});

test("comment factory builds valid ids and files", () => {
  const now = new Date("2026-09-30T10:15:00.123Z");
  const anchor = { docname: "index", quote: "q", prefix: "", suffix: "" };
  const thread = R.CommentFactory.thread(anchor, "Ann", "guest", "Hello", now);
  assert.match(thread.id, /^20260930T101500Z-[0-9a-f]{8}$/);
  assert.equal(thread.created, "2026-09-30T10:15:00Z");
  assert.equal(R.CommentFactory.path(thread), `comments/${thread.id}.json`);
  const reply = R.CommentFactory.reply(thread.id, "Bob", "guest", "Done", "resolved", now);
  assert.equal(reply.thread, thread.id);
  assert.equal(reply.anchor, null);
  assert.equal(R.CommentFactory.commitMessage(reply), `Add comment ${reply.id} on thread ${thread.id}`);
});

test("GitLab sign-in builds a PKCE authorize URL and exchanges the code", async () => {
  const values = {};
  const store = {
    get: (k) => values[k] ?? null,
    set: (k, v) => (values[k] = v),
    remove: (k) => delete values[k],
  };
  const page = { href: "https://docs.example.com/guide/page.html#part" };
  const oauth = new R.GitLabOAuth(GITLAB, store, page, null);
  const authorize = new URL(await oauth.authorizeUrl("../"));
  assert.equal(authorize.origin + authorize.pathname, "https://gitlab.example.com/oauth/authorize");
  const params = authorize.searchParams;
  assert.equal(params.get("redirect_uri"), "https://docs.example.com/");
  assert.equal(params.get("code_challenge_method"), "S256");
  assert.equal(params.get("scope"), "api");
  const pending = values[R.GitLabOAuth.STATE_KEY];
  assert.equal(params.get("code_challenge"), await R.GitLabOAuth.challenge(pending.verifier));

  const { calls, fetch } = recordingFetch(200, { access_token: "oauth-token" });
  const back = { href: `https://docs.example.com/?code=abc&state=${params.get("state")}` };
  const result = await new R.GitLabOAuth(GITLAB, store, back, fetch).complete();
  assert.deepEqual(result, { token: "oauth-token", returnUrl: page.href });
  const body = new URLSearchParams(calls[0].init.body);
  assert.equal(calls[0].url, "https://gitlab.example.com/oauth/token");
  assert.equal(body.get("code_verifier"), pending.verifier);
  assert.equal(body.get("redirect_uri"), "https://docs.example.com/");
  assert.equal(values[R.GitLabOAuth.STATE_KEY], undefined);

  // A second visit to the redirect URL, or a forged state, does nothing.
  assert.equal(await new R.GitLabOAuth(GITLAB, store, back, fetch).complete(), null);
});

test("a conflicting save is retried, other errors are not", async () => {
  R.Forge.RETRY_DELAY_MS = 1;
  const statuses = [409, 201];
  const calls = [];
  const fetch = async (url, init) => {
    calls.push(url);
    const status = statuses.shift();
    return { ok: status < 400, status, statusText: "x", json: async () => ({ message: "conflict" }) };
  };
  await R.Forge.create(GITHUB, "tok", fetch).createFile("comments/x.json", "", "m");
  assert.equal(calls.length, 2);

  const always = (status) => async () => ({ ok: false, status, statusText: "x", json: async () => ({}) });
  let count = 0;
  const counting = (status) => async (...args) => (count++, always(status)(...args));
  await assert.rejects(R.Forge.create(GITHUB, "tok", counting(409)).createFile("c", "", "m"));
  assert.equal(count, R.Forge.ATTEMPTS);
  count = 0;
  await assert.rejects(R.Forge.create(GITHUB, "tok", counting(422)).createFile("c", "", "m"));
  assert.equal(count, 1);
});
