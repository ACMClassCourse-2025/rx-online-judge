"use strict";
const $ = (id) => document.getElementById(id);
const state = {
  languages: [],
  catalog: null,
  selected: null,
  offset: 0,
  busy: false,
  detailKey: "",
  leaderboardKey: "",
  page: "submissions",
  aboutSection: "",
  runOrigin: "submissions",
  unauthorized: true,
  sessionReady: false,
  user: null,
  csrf: "",
  epoch: 0,
  revision: 0,
};
const escapeHTML = (value) =>
  String(value ?? "").replace(
    /[&<>"']/g,
    (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        c
      ],
  );
const label = (value) =>
  value === "ir"
    ? "LLVM IR"
    : String(value)
        .replaceAll("_", " ")
        .replace(/^./, (c) => c.toUpperCase());
const badge = (value) =>
  `<span class="badge ${escapeHTML(value)}">${escapeHTML(label(value))}</span>`;
const number = (n) => Number(n).toLocaleString();
const scoreText = (score) => Number(score).toFixed(6);
const date = (timestamp) =>
  new Date(timestamp * 1000).toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
const terminal = (status) => !["queued", "running"].includes(status);

function notice(message = "") {
  $("notice").textContent = message;
  $("notice").hidden = !message;
}
function showLogin() {
  if ($("account-dialog").open) $("account-dialog").close();
  if (!$("login-dialog").open) $("login-dialog").showModal();
}
function clearSession() {
  state.sessionReady = true;
  state.epoch++;
  state.user = null;
  state.csrf = "";
  state.unauthorized = true;
  state.selected = null;
  state.detailKey = "";
  state.offset = 0;
  state.runOrigin = "submissions";
  RunPage.reset();
  ManagePage.reset();
  if (state.page === "run") RunPage.error("Sign in to view this run.");
  renderSubmissions({ items: [], total: 0 });
  renderLeaderboard({ status: "signed_out", items: [] });
  $("access-button").textContent = "Sign in";
  $("submission-fields").disabled = true;
  $("submit-button").innerHTML =
    'Sign in to submit <span aria-hidden="true">→</span>';
  $("refresh").disabled = true;
  $("refresh-leaderboard").disabled = true;
  $("worker-status").textContent = "Sign in to connect";
  $("status-dot").classList.remove("ready");
  state.catalog = null;
  state.languages = [];
  $("language").innerHTML = '<option value="">Sign in to select</option>';
  $("language-help").textContent = "Dependency preparation ↗";
  $("language-help").href = "#about/dependencies";
  $("suite-help").textContent = "Each suite includes the stages before it.";
}
async function api(path, options = {}) {
  const response = await fetch(`/api${path}`, {
    ...options,
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
      ...(state.csrf ? { "X-CSRF-Token": state.csrf } : {}),
    },
  });
  const data = await response.json();
  if (response.status === 401 && path !== "/auth/login") {
    const hadSession = Boolean(state.user);
    clearSession();
    if (hadSession || path !== "/auth/me") showLogin();
  }
  if (!response.ok)
    throw Object.assign(
      new Error(
        typeof data.detail === "string"
          ? data.detail
          : "Check the form and try again.",
      ),
      { status: response.status },
    );
  return data;
}
function languageName(id) {
  return state.languages.find((l) => l.id === id)?.name || id;
}
function focusAboutSection() {
  const target =
    $("page-about").querySelector(`#about-${state.aboutSection || "title"}`) ||
    $("about-title");
  if (state.aboutSection)
    target.scrollIntoView({ block: "start", behavior: "instant" });
  else window.scrollTo({ top: 0, behavior: "instant" });
  target.focus({ preventScroll: true });
}
function route() {
  const run = location.hash.match(/^#run\/([a-zA-Z0-9_-]+)$/);
  const about = location.hash.match(/^#about(?:\/([a-z0-9-]+))?$/);
  const page = run
    ? "run"
    : location.hash === "#leaderboard"
      ? "leaderboard"
      : location.hash === "#manage"
        ? "manage"
        : about
          ? "about"
          : "submissions";
  const selected = run?.[1] || null;
  const aboutSection = about?.[1] || "";
  const changed =
    page !== state.page ||
    selected !== state.selected ||
    aboutSection !== state.aboutSection;
  if (selected !== state.selected) {
    state.selected = selected;
    state.detailKey = "";
    RunPage.reset();
  }
  state.page = page;
  state.aboutSection = aboutSection;
  for (const section of document.querySelectorAll(".page"))
    section.hidden = section.id !== `page-${state.page}`;
  for (const link of document.querySelectorAll(".nav-link")) {
    const active =
      link.dataset.page === (page === "run" ? state.runOrigin : page);
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  RunPage.activate(page === "run");
  ManagePage.activate();
  $("run-back").href = `#${state.runOrigin}`;
  $("run-back").innerHTML =
    `${state.runOrigin === "manage" ? "Back to manage" : "Back to menu"} <span aria-hidden="true">↗</span>`;
  if (page !== "run" || changed)
    document.title = `${page === "run" ? "Your run" : label(page)} · Rx Compiler Judge`;
  if (changed) {
    window.scrollTo({ top: 0, behavior: "instant" });
    if (page === "run") $("run-name").focus({ preventScroll: true });
    if (page === "about") focusAboutSection();
  }
  if (page === "run" && state.sessionReady && !state.user)
    RunPage.error("Sign in to view this run.");
  refresh();
}
function scoreTable(cases) {
  return `<div class="table-scroll" tabindex="0" role="region" aria-label="Optimization score breakdown"><table><thead><tr><th>TESTCASE</th><th>YOUR CYCLES</th><th>BASELINE CYCLES</th><th>RATIO ↓</th></tr></thead><tbody>${cases.map((c) => `<tr><td class="case-name">${escapeHTML(c.case_id)}</td><td>${number(c.cycles)}</td><td>${number(c.baseline_cycles)}</td><td>${scoreText(c.ratio)}</td></tr>`).join("")}</tbody></table></div>`;
}
function renderLeaderboard(data) {
  const key = JSON.stringify(data);
  if (key === state.leaderboardKey) return;
  state.leaderboardKey = key;
  const expanded = new Set(
    [...document.querySelectorAll("[data-score][aria-expanded=true]")].map(
      (el) => el.dataset.score,
    ),
  );
  $("leaderboard-count").textContent = number(data.items.length);
  $("leaderboard-empty").hidden = data.items.length > 0;
  const ready = data.status === "ready";
  const signedOut = data.status === "signed_out";
  $("baseline-info").textContent = signedOut
    ? "Sign in to see the Rust baseline."
    : ready
      ? `${data.baseline.compiler.split("\n")[0]} · ${data.baseline.cases.length} optimization tests`
      : data.status === "stale"
        ? "The test catalog has changed."
        : "An official Rust baseline is required for scoring.";
  $("leaderboard-empty-title").textContent = signedOut
    ? "A place for your personal best."
    : ready
      ? "First place is up for grabs."
      : data.status === "stale"
        ? "Baseline needs updating"
        : "Waiting for the baseline";
  $("leaderboard-empty-message").textContent = signedOut
    ? "Sign in to see the leaderboard."
    : ready
      ? "Pass the full optimization suite to earn a score."
      : "Scores appear once your administrator generates the Rust baseline.";
  $("leaderboard-body").innerHTML = data.items
    .map((row) => {
      const id = escapeHTML(row.submission_id);
      const open = expanded.has(row.submission_id);
      return `<tr class="${row.is_you ? "your-rank" : ""}"><td class="rank-number">${row.rank}</td><td><strong>${escapeHTML(row.username)}</strong>${row.is_you ? '<span class="you-label">YOU</span>' : ""}</td><td><button class="score-link" data-score="${id}" aria-expanded="${open}" aria-controls="score-${id}" title="Show testcase ratios">${scoreText(row.score)} <span>⌄</span></button></td><td>${row.can_view_submission ? `<button class="submission-link" data-id="${id}">${escapeHTML(row.submission_name)}</button>` : `<span>${escapeHTML(row.submission_name)}</span>`}</td><td>${escapeHTML(languageName(row.language))}</td><td>${date(row.finished_at)}</td></tr><tr id="score-${id}" class="score-breakdown" ${open ? "" : "hidden"}><td colspan="6"><div class="detail-body"><p class="field-help">${escapeHTML(row.username)} · ${row.cases.length} optimization tests · baseline ${escapeHTML(data.baseline.id.slice(0, 12))}</p>${scoreTable(row.cases)}</div></td></tr>`;
    })
    .join("");
}
function renderSubmissions(data) {
  $("submission-count").textContent = number(data.total);
  $("empty-state").hidden = data.items.length > 0;
  $("empty-title").textContent = "Hmm, nothing's here..";
  $("empty-message").textContent = state.user
    ? "Your first run starts with a Git repository."
    : "Sign in to start your first run.";
  $("pagination-info").textContent = data.total
    ? `${state.offset + 1}–${state.offset + data.items.length} of ${number(data.total)} submissions`
    : "No submissions yet";
  $("previous").disabled = state.offset === 0;
  $("next").disabled = state.offset + 10 >= data.total;
  $("submissions-body").innerHTML = data.items
    .map(
      (s) =>
        `<tr><td><button class="submission-link" data-id="${escapeHTML(s.id)}">${escapeHTML(s.name)}</button><span class="sub-meta">${escapeHTML(s.owner || "Legacy submission")} · ${date(s.created_at)}</span></td><td>${escapeHTML(languageName(s.language))}</td><td><button class="status-link" data-id="${escapeHTML(s.id)}" aria-label="Open ${escapeHTML(s.name)}: ${escapeHTML(label(s.status))}">${badge(s.status)}</button></td><td>${s.passed}<span class="sub-meta">/ ${s.total} tests</span></td></tr>`,
    )
    .join("");
}
function renderDetail(s) {
  $("run-error").hidden = true;
  const key = JSON.stringify(s);
  if (key === state.detailKey) return;
  state.detailKey = key;
  RunPage.update(s);
}
$("cancel-submission").onclick = async () => {
  const id = state.selected;
  if (!id) return;
  const epoch = state.epoch;
  $("cancel-submission").disabled = true;
  try {
    const result = await api(`/submissions/${id}/cancel`, { method: "POST" });
    if (epoch !== state.epoch) return;
    state.revision++;
    if (state.selected === id) renderDetail(result);
  } catch (e) {
    if (epoch === state.epoch && state.selected === id) {
      RunPage.error(e.message);
      $("cancel-submission").disabled = false;
    }
  }
};
async function refresh() {
  if (state.busy || state.unauthorized) return;
  if (state.page === "manage") ManagePage.load();
  state.busy = true;
  const epoch = state.epoch;
  const revision = state.revision;
  const selected = state.selected;
  try {
    const [submissions, health, detail, rankings] = await Promise.all([
      api(`/submissions?limit=10&offset=${state.offset}`),
      api("/health"),
      selected
        ? api(`/submissions/${selected}`).catch((e) => {
            if (state.selected === selected && state.page === "run")
              RunPage.error(e.message);
            return null;
          })
        : null,
      state.page === "leaderboard" ? api("/leaderboard") : null,
    ]);
    if (epoch !== state.epoch || revision !== state.revision || !state.user)
      return;
    renderSubmissions(submissions);
    if (rankings) renderLeaderboard(rankings);
    $("worker-status").textContent = health.workers.length
      ? `${health.workers.length} worker${health.workers.length === 1 ? "" : "s"} connected`
      : "Waiting for a worker";
    $("status-dot").classList.toggle("ready", health.workers.length > 0);
    if (detail && detail.id === state.selected) renderDetail(detail);
  } catch (e) {
    notice(e.message);
    $("worker-status").textContent = "Connection unavailable";
    $("status-dot").classList.remove("ready");
    if (state.page === "run")
      RunPage.error("Connection interrupted. Retrying automatically…");
  } finally {
    state.busy = false;
    // A route change during a poll must not leave the new run waiting on the old request.
    if (
      (state.selected !== selected || revision !== state.revision) &&
      !state.unauthorized
    )
      refresh();
  }
}
function renderMetrics(catalog) {
  for (const stage of ["semantic", "ir", "codegen", "optimization"])
    $(`metric-${stage}`).textContent = number(catalog.stages[stage] || 0);
  $("metric-total").textContent = number(catalog.total);
}
async function loadMetrics() {
  try {
    renderMetrics(await api("/catalog/summary"));
  } catch {
    if (state.catalog) return;
    for (const metric of document.querySelectorAll('[id^="metric-"]'))
      metric.textContent = "N/A";
  }
}
async function initialize() {
  try {
    const session = await api("/auth/me");
    state.user = session.user;
    state.sessionReady = true;
    state.csrf = session.csrf_token;
    state.unauthorized = false;
    $("access-button").textContent = state.user.username;
    $("account-name").textContent =
      `${state.user.username}${state.user.is_admin ? " · Administrator" : ""}`;
    const [languages, catalog] = await Promise.all([
      api("/languages"),
      api("/catalog"),
    ]);
    state.languages = languages;
    state.catalog = catalog;
    $("language").innerHTML = languages
      .map(
        (l) =>
          `<option value="${escapeHTML(l.id)}">${escapeHTML(l.name)}</option>`,
      )
      .join("");
    $("language").dispatchEvent(new Event("change"));
    $("suite").innerHTML = catalog.suites
      .map(
        (s) =>
          `<option value="${escapeHTML(s.id)}">${escapeHTML(label(s.id))} · ${number(s.total)} tests</option>`,
      )
      .join("");
    renderMetrics(catalog);
    $("suite").dispatchEvent(new Event("change"));
    $("submission-fields").disabled = false;
    $("submit-button").innerHTML =
      'Submit compiler <span aria-hidden="true">→</span>';
    $("refresh").disabled = false;
    $("refresh-leaderboard").disabled = false;
    notice();
    route();
    await refresh();
  } catch (e) {
    if (e.status !== 401) notice(e.message);
  }
}
$("submit-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!state.user) {
    showLogin();
    return;
  }
  $("submit-button").disabled = true;
  $("submit-button").textContent = "Submitting…";
  try {
    const result = await api("/submissions", {
      method: "POST",
      body: JSON.stringify(Object.fromEntries(new FormData(event.target))),
    });
    state.offset = 0;
    notice();
    openSubmission(result.id);
    renderDetail(result);
  } catch (e) {
    notice(e.message);
  } finally {
    $("submit-button").disabled = false;
    $("submit-button").innerHTML =
      `${state.user ? "Submit compiler" : "Sign in to submit"} <span aria-hidden="true">→</span>`;
  }
});
function openSubmission(id, origin = "submissions") {
  state.runOrigin = origin;
  location.hash = `#run/${encodeURIComponent(id)}`;
  route();
}
$("submissions-body").addEventListener("click", (event) => {
  const button = event.target.closest("[data-id]");
  if (button) openSubmission(button.dataset.id);
});
$("leaderboard-body").addEventListener("click", (event) => {
  const score = event.target.closest("[data-score]");
  if (score) {
    const expanded = score.getAttribute("aria-expanded") !== "true";
    score.setAttribute("aria-expanded", String(expanded));
    $(score.getAttribute("aria-controls")).hidden = !expanded;
  }
  const submission = event.target.closest("[data-id]");
  if (submission) openSubmission(submission.dataset.id);
});
$("refresh-leaderboard").onclick = () => {
  notice();
  refresh();
};
$("suite").onchange = () => {
  const suite = state.catalog?.suites.find((s) => s.id === $("suite").value);
  if (suite)
    $("suite-help").textContent =
      `${suite.includes.map(label).join(" → ")} · ${number(suite.total)} tests`;
};
$("language").onchange = () => {
  const language = state.languages.find((l) => l.id === $("language").value);
  $("language-help").textContent = language
    ? `${language.name} dependencies ↗`
    : "Dependency preparation ↗";
  $("language-help").href = ["cpp", "rust", "python", "java", "node"].includes(
    language?.id,
  )
    ? `#about/${language.id}`
    : "#about/dependencies";
};
$("refresh").onclick = () => {
  notice();
  refresh();
};
$("previous").onclick = () => {
  state.offset = Math.max(0, state.offset - 10);
  refresh();
};
$("next").onclick = () => {
  state.offset += 10;
  refresh();
};
$("access-button").onclick = () =>
  state.user ? $("account-dialog").showModal() : showLogin();
$("close-account").onclick = () => $("account-dialog").close();
$("close-login").onclick = () => $("login-dialog").close();
$("start-run").onclick = () => {
  if (!state.user) return showLogin();
  $("new-run").scrollIntoView({ block: "start" });
  $("submission-name").focus({ preventScroll: true });
};
$("login-form").onsubmit = async (event) => {
  event.preventDefault();
  $("login-button").disabled = true;
  $("login-error").hidden = true;
  try {
    await api("/auth/login", {
      method: "POST",
      body: JSON.stringify({
        username: $("username").value,
        password: $("password").value,
      }),
    });
    state.epoch++;
    $("password").value = "";
    $("login-dialog").close();
    await initialize();
  } catch (e) {
    $("login-error").textContent = e.message;
    $("login-error").hidden = false;
  } finally {
    $("login-button").disabled = false;
  }
};
$("logout-button").onclick = async () => {
  try {
    await api("/auth/logout", { method: "POST" });
    clearSession();
    showLogin();
  } catch (e) {
    notice(e.message);
  }
};
$("password-form").onsubmit = async (event) => {
  event.preventDefault();
  $("password-error").hidden = true;
  try {
    await api("/auth/password", {
      method: "POST",
      body: JSON.stringify({
        current_password: $("current-password").value,
        new_password: $("new-password").value,
      }),
    });
    event.target.reset();
    clearSession();
    showLogin();
    $("login-error").textContent = "Password changed. Sign in again.";
    $("login-error").hidden = false;
  } catch (e) {
    $("password-error").textContent = e.message;
    $("password-error").hidden = false;
  }
};
document.addEventListener("click", (event) => {
  const link = event.target.closest('a[href^="#about"]');
  if (
    state.page === "about" &&
    link?.getAttribute("href") === location.hash &&
    !event.ctrlKey && !event.metaKey && !event.shiftKey && !event.altKey
  ) {
    event.preventDefault();
    focusAboutSection();
  }
});
window.addEventListener("hashchange", route);
route();
loadMetrics();
initialize();
setInterval(() => {
  if (!document.hidden) refresh();
}, 2500);
