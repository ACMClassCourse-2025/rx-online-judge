"use strict";
const ManagePage = (() => {
  const el = (id) => document.getElementById(id);
  const pageSize = 20;
  let offset = 0;
  let filters = {};
  let rows = [];
  let request = 0;
  let rendered = "";
  let voidRun = null;
  let voidBusy = false;
  let actionError = "";
  const pending = new Set();

  function error(message = "") {
    el("manage-error").textContent = message;
    el("manage-error").hidden = !message;
  }
  function activate() {
    const admin = Boolean(state.user?.is_admin);
    el("manage-nav").hidden = !admin;
    el("manage-tools").hidden = !admin;
    el("manage-access").hidden = admin;
    el("manage-access").textContent = state.user
      ? "Administrator access is required to manage runs."
      : "Sign in as an administrator to manage runs.";
    const languages =
      '<option value="">All languages</option>' +
      state.languages
        .map(
          (l) =>
            `<option value="${escapeHTML(l.id)}">${escapeHTML(l.name)}</option>`,
        )
        .join("");
    if (el("manage-language").innerHTML !== languages) {
      const selected = el("manage-language").value;
      el("manage-language").innerHTML = languages;
      el("manage-language").value = selected;
    }
    if (state.page === "manage" && admin) load();
  }
  function reset() {
    request++;
    offset = 0;
    filters = {};
    rows = [];
    rendered = "";
    pending.clear();
    actionError = "";
    voidRun = null;
    el("void-dialog").close();
    el("manage-search").reset();
    el("manage-body").replaceChildren();
    el("manage-count").textContent = "0";
    el("manage-pagination").textContent = "";
    error();
    activate();
  }
  function render(data) {
    rows = data.items;
    el("manage-count").textContent = number(data.total);
    el("manage-empty").hidden = rows.length > 0;
    el("manage-pagination").textContent = data.total
      ? `${offset + 1}–${offset + rows.length} of ${number(data.total)} runs`
      : "No matching runs";
    el("manage-previous").disabled = offset === 0;
    el("manage-next").disabled = offset + pageSize >= data.total;
    const key = JSON.stringify([rows, [...pending]]);
    if (key === rendered) return;
    rendered = key;
    el("manage-body").innerHTML = rows
      .map((s) => {
        const id = escapeHTML(s.id);
        const busy = pending.has(s.id);
        return `<tr data-run="${id}">
        <td><a class="submission-link" href="#run/${id}" data-inspect="${id}">${escapeHTML(s.name)}</a>
          <span class="sub-meta">${escapeHTML(s.id.slice(0, 12))} · ${date(s.created_at)}</span>
          <span class="sub-meta manage-repo" title="${escapeHTML(s.repository_url)}">${escapeHTML(s.repository_url)}</span></td>
        <td>${escapeHTML(s.owner || "Legacy submission")}</td>
        <td>${escapeHTML(label(s.suite || s.stage))}<span class="sub-meta">${escapeHTML(languageName(s.language))}</span></td>
        <td>${badge(s.status)}${s.cancel_requested && !terminal(s.status) ? '<span class="sub-meta">Cancelling…</span>' : ""}${s.status_before_void ? `<span class="sub-meta">Was ${escapeHTML(label(s.status_before_void))}</span>` : ""}</td>
        <td>${number(s.passed)}<span class="sub-meta">/ ${number(s.total)} tests</span></td>
        <td><div class="manage-actions">
          <a class="button ghost small" href="#run/${id}" data-inspect="${id}" aria-label="Inspect ${escapeHTML(s.name)}">Inspect</a>
          ${!terminal(s.status) ? `<button class="button ghost small" data-cancel="${id}" ${busy || s.cancel_requested ? "disabled" : ""}>Cancel</button>` : ""}
          ${s.status !== "voided" ? `<button class="button ghost small" data-void="${id}" ${busy ? "disabled" : ""}>Void</button>` : ""}
        </div></td></tr>`;
      })
      .join("");
  }
  async function load() {
    if (!state.user?.is_admin || state.page !== "manage") return;
    const current = ++request;
    const epoch = state.epoch;
    el("manage-tools").setAttribute("aria-busy", "true");
    try {
      const query = new URLSearchParams({
        ...filters,
        limit: pageSize,
        offset,
      });
      const data = await api(`/admin/submissions?${query}`);
      if (current !== request || epoch !== state.epoch || !state.user?.is_admin)
        return;
      if (offset && offset >= data.total) {
        offset = Math.max(
          0,
          Math.floor((data.total - 1) / pageSize) * pageSize,
        );
        return load();
      }
      render(data);
      error(actionError);
    } catch (e) {
      if (current === request && epoch === state.epoch) error(e.message);
    } finally {
      if (current === request)
        el("manage-tools").setAttribute("aria-busy", "false");
    }
  }
  function confirmVoid(s) {
    if (!state.user?.is_admin || s.status === "voided" || voidBusy) return;
    voidRun = { id: s.id, epoch: state.epoch };
    el("void-run-name").textContent =
      `${s.name} · ${s.owner || "Legacy submission"} · ${s.id}`;
    el("void-error").hidden = true;
    el("void-confirm").disabled = false;
    el("void-confirm").textContent = "Void run";
    el("void-dialog").showModal();
  }
  async function cancel(id, button) {
    if (pending.has(id)) return;
    const epoch = state.epoch;
    actionError = "";
    error();
    pending.add(id);
    request++;
    button.disabled = true;
    try {
      await api(`/submissions/${id}/cancel`, { method: "POST" });
      if (epoch === state.epoch) state.revision++;
    } catch (e) {
      if (epoch === state.epoch) {
        actionError = e.message;
        error(actionError);
      }
    } finally {
      if (epoch === state.epoch) {
        pending.delete(id);
        button.disabled = false;
        await load();
      }
    }
  }
  el("manage-search").onsubmit = (event) => {
    event.preventDefault();
    actionError = "";
    filters = Object.fromEntries(new FormData(event.target));
    offset = 0;
    load();
  };
  el("manage-search").onreset = () => {
    actionError = "";
    filters = {};
    offset = 0;
    load();
  };
  el("manage-refresh").onclick = () => {
    actionError = "";
    load();
  };
  el("manage-previous").onclick = () => {
    offset = Math.max(0, offset - pageSize);
    load();
  };
  el("manage-next").onclick = () => {
    offset += pageSize;
    load();
  };
  el("manage-body").onclick = (event) => {
    const inspect = event.target.closest("[data-inspect]");
    if (inspect && !event.ctrlKey && !event.metaKey && !event.shiftKey) {
      event.preventDefault();
      openSubmission(inspect.dataset.inspect, "manage");
    }
    const cancelButton = event.target.closest("[data-cancel]");
    if (cancelButton) cancel(cancelButton.dataset.cancel, cancelButton);
    const voidButton = event.target.closest("[data-void]");
    const s = rows.find((s) => s.id === voidButton?.dataset.void);
    if (s) confirmVoid(s);
  };
  el("void-close").onclick = () => el("void-dialog").close();
  el("void-dialog").addEventListener("cancel", (event) => {
    if (voidBusy) event.preventDefault();
  });
  el("void-form").onsubmit = async (event) => {
    event.preventDefault();
    if (!voidRun || voidBusy || !state.user?.is_admin) return;
    const { id, epoch } = voidRun;
    voidBusy = true;
    pending.add(id);
    request++;
    el("void-confirm").disabled = true;
    el("void-close").disabled = true;
    el("void-confirm").textContent = "Voiding…";
    try {
      const result = await api(`/admin/submissions/${id}/void`, {
        method: "POST",
      });
      if (epoch !== state.epoch) return;
      state.revision++;
      if (state.selected === id) renderDetail(result);
      el("void-dialog").close();
      await load();
      refresh();
    } catch (e) {
      if (epoch !== state.epoch) return;
      el("void-error").textContent = e.message;
      el("void-error").hidden = false;
    } finally {
      pending.delete(id);
      voidBusy = false;
      el("void-confirm").disabled = false;
      el("void-close").disabled = false;
      el("void-confirm").textContent = "Void run";
    }
  };
  return { activate, reset, load, confirmVoid };
})();
