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
  unauthorized: true,
  user: null,
  csrf: "",
  epoch: 0,
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
  state.epoch++;
  state.user = null;
  state.csrf = "";
  state.unauthorized = true;
  state.selected = null;
  state.detailKey = "";
  state.offset = 0;
  $("detail").hidden = true;
  $("detail").innerHTML = "";
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
  $("language-help").textContent = "";
  $("git-hosts").textContent = "Use a public HTTPS repository.";
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
function route() {
  state.page = location.hash === "#leaderboard" ? "leaderboard" : "submissions";
  for (const section of document.querySelectorAll(".page"))
    section.hidden = section.id !== `page-${state.page}`;
  for (const link of document.querySelectorAll(".nav-link")) {
    const active = link.dataset.page === state.page;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  }
  document.title = `${label(state.page)} · Rx Compiler Judge`;
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
      return `<tr class="${row.is_you ? "your-rank" : ""}"><td class="rank-number">${row.rank}</td><td><strong>${escapeHTML(row.username)}</strong>${row.is_you ? '<span class="you-label">YOU</span>' : ""}</td><td><button class="score-link" data-score="${id}" aria-expanded="${open}" aria-controls="score-${id}" title="Show testcase ratios">${scoreText(row.score)} <span>⌄</span></button></td><td>${row.can_view_submission ? `<button class="submission-link" data-id="${id}">${escapeHTML(row.submission_name)}</button>` : `<span>${escapeHTML(row.submission_name)}</span>`}</td><td>${escapeHTML(languageName(row.language))}</td><td>${date(row.finished_at)}</td></tr><tr id="score-${id}" class="score-breakdown" ${open ? "" : "hidden"}><td colspan="6"><div class="detail-body"><p class="field-help">${escapeHTML(row.username)} · Geometric mean of ${row.cases.length} testcase ratios · baseline ${escapeHTML(data.baseline.id.slice(0, 12))}</p>${scoreTable(row.cases)}</div></td></tr>`;
    })
    .join("");
}
function renderSubmissions(data) {
  $("submission-count").textContent = number(data.total);
  $("empty-state").hidden = data.items.length > 0;
  $("empty-title").textContent = "Hello, compiler.";
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
        `<tr><td><button class="submission-link" data-id="${escapeHTML(s.id)}">${escapeHTML(s.name)}</button><span class="sub-meta">${escapeHTML(s.owner || "Legacy submission")} · ${date(s.created_at)}</span></td><td>${escapeHTML(languageName(s.language))}</td><td>${badge(s.status)}</td><td>${s.passed}<span class="sub-meta">/ ${s.total} tests</span></td></tr>`,
    )
    .join("");
}
function renderDetail(s) {
  const key = JSON.stringify(s);
  if (key === state.detailKey) return;
  state.detailKey = key;
  $("detail").hidden = false;
  const failures = s.results.filter((r) => r.verdict !== "accepted");
  $("detail").innerHTML =
    `<div class="panel-heading"><div><div class="eyebrow">SUBMISSION / ${escapeHTML(s.id.slice(0, 8))}</div><h2>${escapeHTML(s.name)}</h2></div><div class="detail-heading-actions">${badge(s.status)}${!terminal(s.status) ? `<button id="cancel-submission" class="button ghost small" ${s.cancel_requested ? "disabled" : ""}>${s.cancel_requested ? "Cancelling…" : "Cancel run"}</button>` : ""}<button id="close-detail" class="icon-button" aria-label="Close submission details">×</button></div></div>
    <div class="detail-body"><p class="source-info">${escapeHTML(s.repository_url || "Legacy archive submission")}<br>Ref: <code>${escapeHTML(s.git_ref || "—")}</code> · Commit: <code>${escapeHTML(s.commit_sha || "Waiting for Git fetch")}</code></p><div class="detail-summary"><span><strong>${s.passed} / ${s.total}</strong> passed</span><span><strong>${s.completed}</strong> completed</span><span><strong>${number(s.cycles)}</strong> optimization cycles</span><span>${escapeHTML(label(s.stage))} · ${escapeHTML(languageName(s.language))}</span></div>${s.optimization_score ? `<div class="optimization-score"><strong>${scoreText(s.optimization_score.score)}</strong><span>Optimization score · lower is better</span><a href="#leaderboard">View leaderboard ↗</a></div>` : ""}<progress class="detail-progress" value="${s.completed}" max="${s.total}" aria-label="Completed testcases"></progress>
    ${s.message ? `<p>${escapeHTML(s.message)}</p>` : ""}${!s.results.length ? `<p class="field-help">${s.status === "queued" ? "Waiting for a worker to claim this submission." : s.status === "running" ? "Fetching the repository, building the compiler, and preparing the suite…" : "No testcase results were produced."}</p>` : `<div class="table-scroll" tabindex="0" role="region" aria-label="Testcase results"><table><thead><tr><th>TESTCASE</th><th>STAGE</th><th>VERDICT</th><th>ELAPSED</th><th>CYCLES</th></tr></thead><tbody>${s.results.map((r) => `<tr><td class="case-name">${escapeHTML(r.case_id)}</td><td>${escapeHTML(label(r.stage))}</td><td>${badge(r.verdict)}</td><td>${(r.duration_ms / 1000).toFixed(2)}s</td><td>${r.stage === "optimization" && r.verdict === "accepted" ? number(r.cycles) : "—"}</td></tr>`).join("")}</tbody></table></div>`}
    ${s.optimization_score ? `<details><summary>Optimization score · testcase ratios</summary>${scoreTable(s.optimization_score.cases)}</details>` : ""}
    <details ${s.status === "build_error" ? "open" : ""}><summary>Build diagnostics</summary><pre tabindex="0" role="region" aria-label="Build diagnostics output">${escapeHTML(s.build_log || "No build output.")}</pre></details>
    ${failures.map((r) => `<details><summary>${escapeHTML(r.case_id)} · ${escapeHTML(label(r.verdict))}</summary><p>${escapeHTML(r.message)}</p><pre tabindex="0" role="region" aria-label="Testcase diagnostics output">${escapeHTML(r.log || "No compiler or simulator diagnostics.")}</pre></details>`).join("")}
    <details><summary>Result JSON · all runs and diagnostics</summary><pre tabindex="0" role="region" aria-label="Result JSON output">${escapeHTML(JSON.stringify(s, null, 2))}</pre></details></div>`;
  $("close-detail").onclick = () => {
    state.selected = null;
    state.detailKey = "";
    $("detail").hidden = true;
  };
  if ($("cancel-submission"))
    $("cancel-submission").onclick = async () => {
      try {
        renderDetail(
          await api(`/submissions/${s.id}/cancel`, { method: "POST" }),
        );
      } catch (e) {
        notice(e.message);
      }
    };
}
async function refresh() {
  if (state.busy || state.unauthorized) return;
  state.busy = true;
  const epoch = state.epoch;
  try {
    const [submissions, health, detail, rankings] = await Promise.all([
      api(`/submissions?limit=10&offset=${state.offset}`),
      api("/health"),
      state.selected ? api(`/submissions/${state.selected}`) : null,
      state.page === "leaderboard" ? api("/leaderboard") : null,
    ]);
    if (epoch !== state.epoch || !state.user) return;
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
  } finally {
    state.busy = false;
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
    $("git-hosts").textContent =
      `Public repositories only: ${catalog.git_hosts.join(", ")}`;
    $("submission-fields").disabled = false;
    $("submit-button").innerHTML =
      'Submit compiler <span aria-hidden="true">→</span>';
    $("refresh").disabled = false;
    $("refresh-leaderboard").disabled = false;
    notice();
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
    state.selected = result.id;
    state.detailKey = "";
    state.offset = 0;
    notice();
    renderDetail(result);
    await refresh();
  } catch (e) {
    notice(e.message);
  } finally {
    $("submit-button").disabled = false;
    $("submit-button").innerHTML =
      `${state.user ? "Submit compiler" : "Sign in to submit"} <span aria-hidden="true">→</span>`;
  }
});
async function openSubmission(id) {
  state.selected = id;
  state.detailKey = "";
  try {
    const result = await api(`/submissions/${state.selected}`);
    if (result.id === state.selected) {
      location.hash = "#submissions";
      route();
      renderDetail(result);
      $("detail").scrollIntoView({ block: "start" });
    }
  } catch (e) {
    notice(e.message);
  }
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
  $("language-help").textContent =
    state.languages.find((l) => l.id === $("language").value)?.description ||
    "";
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
window.addEventListener("hashchange", route);
route();
loadMetrics();
initialize();
setInterval(() => {
  if (!document.hidden) refresh();
}, 2500);
