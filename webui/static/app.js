/* webui/static/app.js
 * Interheart WebUI - vanilla JS
 * Assumes these IDs exist in index.html:
 * btnAdd, btnRefresh, btnSaveTarget, btnConfirmRemove
 * tbodyTargets, hintLine
 * modalEdit, modalRemove, modalInfo
 * fName, fIP, fEndpoint, fInterval
 * modalEditTitle, editModeHint
 * removeName
 * infoGrid
 * toast, toastInner
 */

(() => {
  // --- tiny helpers ---
  const $ = (id) => document.getElementById(id);

  const state = {
    targets: [],
    editMode: "add", // add | edit
    currentName: null, // for edit/remove/info
  };

  function showToast(text, kind = "ok") {
    const el = $("toast");
    const inner = $("toastInner");
    if (!el || !inner) return;

    inner.textContent = String(text || "");
    el.dataset.kind = kind;
    el.classList.add("toast--show");

    window.clearTimeout(showToast._t);
    showToast._t = window.setTimeout(() => el.classList.remove("toast--show"), 2600);
  }

  function openModal(id) {
    const m = $(id);
    if (!m) return;
    m.setAttribute("aria-hidden", "false");
    m.classList.add("modal--open");
  }

  function closeModal(id) {
    const m = $(id);
    if (!m) return;
    m.setAttribute("aria-hidden", "true");
    m.classList.remove("modal--open");
  }

  async function api(url, options = {}) {
    const res = await fetch(url, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok || data.ok === false) {
      const msg = data?.error || `Request failed (${res.status})`;
      throw new Error(msg);
    }
    return data;
  }

  function cssId(s) {
    return String(s).replace(/[^a-zA-Z0-9_-]/g, "_");
  }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function escapeAttr(s) {
    return escapeHtml(s).replaceAll('"', "&quot;");
  }

  function intervalText(t) {
    const v = Number(t?.interval || 0);
    if (!v) return "—";
    return `${v}s`;
  }

  function statusBadge(t) {
    const s = String(t?.last_status || "unknown").toLowerCase();
    const label =
      s === "up" ? "Up" :
      s === "down" ? "Down" :
      s === "degraded" ? "Degraded" :
      s === "paused" ? "Paused" :
      "Unknown";

    const cls =
      s === "up" ? "badge badge--up" :
      s === "down" ? "badge badge--down" :
      s === "degraded" ? "badge badge--warn" :
      "badge";

    return `<span class="${cls}">${label}</span>`;
  }

  function render() {
    const tbody = $("tbodyTargets");
    const hint = $("hintLine");
    if (!tbody || !hint) return;

    const items = state.targets || [];
    if (!items.length) {
      tbody.innerHTML = `<tr><td colspan="6" class="td-muted">No targets yet.</td></tr>`;
      hint.textContent = "0 targets";
      return;
    }

    hint.textContent = `${items.length} target${items.length === 1 ? "" : "s"} loaded`;

    tbody.innerHTML = items.map((t) => {
      const enabled = !!t.enabled;

      return `
        <tr>
          <td>
            <label class="switch">
              <input type="checkbox" ${enabled ? "checked" : ""} data-toggle="${escapeAttr(t.name)}">
              <span class="switch__ui"></span>
            </label>
          </td>
          <td class="td-strong">${escapeHtml(t.name)}</td>
          <td class="td-mono">${escapeHtml(t.ip || "—")}</td>
          <td class="td-mono col-interval">${intervalText(t)}</td>
          <td>${statusBadge(t)}</td>
          <td style="text-align:right;">
            <div class="dropdown">
              <button class="btn btn--ghost btn--sm" data-dd="${escapeAttr(t.name)}">Actions ▾</button>
              <div class="dropdown__menu" id="dd-${cssId(t.name)}">
                <button class="dropdown__item" data-action="info" data-name="${escapeAttr(t.name)}">Information</button>
                <button class="dropdown__item" data-action="edit" data-name="${escapeAttr(t.name)}">Edit</button>
                <div class="dropdown__sep"></div>
                <button class="dropdown__item dropdown__item--danger" data-action="remove" data-name="${escapeAttr(t.name)}">Remove</button>
              </div>
            </div>
          </td>
        </tr>
      `;
    }).join("");
  }

  async function loadTargets() {
    const hint = $("hintLine");
    if (hint) hint.textContent = "Loading…";
    const out = await api("/api/targets");
    state.targets = out.data || [];
    render();
  }

  function resetEditForm() {
    const fName = $("fName");
    const fIP = $("fIP");
    const fEndpoint = $("fEndpoint");
    const fInterval = $("fInterval");

    if (fName) fName.value = "";
    if (fIP) fIP.value = "";
    if (fEndpoint) fEndpoint.value = "";
    if (fInterval && fInterval.defaultValue) fInterval.value = fInterval.defaultValue;
  }

  function setEditMode(mode, target) {
    state.editMode = mode;

    const title = $("modalEditTitle");
    const hint = $("editModeHint");
    const fName = $("fName");
    const fIP = $("fIP");
    const fEndpoint = $("fEndpoint");
    const fInterval = $("fInterval");

    if (mode === "add") {
      state.currentName = null;
      if (title) title.textContent = "Add target";
      if (hint) hint.textContent = "Creates a new target.";
      resetEditForm();
      return;
    }

    // edit
    state.currentName = target?.name || null;
    if (title) title.textContent = "Edit target";
    if (hint) hint.textContent = "Edits the existing target (name/IP/endpoint/interval).";

    if (fName) fName.value = target?.name || "";
    if (fIP) fIP.value = target?.ip || "";
    if (fEndpoint) fEndpoint.value = target?.endpoint || "";
    if (fInterval) fInterval.value = String(target?.interval ?? (fInterval.defaultValue || "60"));
  }

  async function saveTarget() {
    const payload = {
      name: ($("fName")?.value || "").trim(),
      ip: ($("fIP")?.value || "").trim(),
      endpoint: ($("fEndpoint")?.value || "").trim(),
      interval: Number(($("fInterval")?.value || "0")),
    };

    if (state.editMode === "add") {
      await api("/api/targets", { method: "POST", body: JSON.stringify(payload) });
      showToast("Target created", "ok");
      closeModal("modalEdit");
      await loadTargets();
      return;
    }

    await api(`/api/targets/${encodeURIComponent(state.currentName)}`, {
      method: "PATCH",
      body: JSON.stringify(payload),
    });

    showToast("Target updated", "ok");
    closeModal("modalEdit");
    await loadTargets();
  }

  function openRemove(name) {
    state.currentName = name;
    const el = $("removeName");
    if (el) el.textContent = name;
    openModal("modalRemove");
  }

  async function confirmRemove() {
    const name = state.currentName;
    await api(`/api/targets/${encodeURIComponent(name)}`, { method: "DELETE" });
    showToast("Target removed", "ok");
    closeModal("modalRemove");
    await loadTargets();
  }

  function openInfo(target) {
    state.currentName = target?.name || null;

    const lines = [
      ["Name", target?.name],
      ["IP", target?.ip || "—"],
      ["Endpoint URL", target?.endpoint || "—"],
      ["Interval", intervalText(target)],
      ["Enabled", target?.enabled ? "Yes" : "No"],
      ["Last status", (target?.last_status || "unknown")],
      ["Last ping (epoch)", target?.last_ping ?? "—"],
      ["Last response (epoch)", target?.last_response ?? "—"],
      ["Last latency (ms)", target?.last_latency_ms ?? "—"],
      ["Next due (epoch)", target?.next_due_at ?? "—"],
      ["Created", target?.created_at ?? "—"],
      ["Updated", target?.updated_at ?? "—"],
    ];

    const grid = $("infoGrid");
    if (grid) {
      grid.innerHTML = lines.map(([k, v]) => `
        <div class="infoRow">
          <div class="infoKey">${escapeHtml(k)}</div>
          <div class="infoVal">${escapeHtml(v)}</div>
        </div>
      `).join("");
    }

    openModal("modalInfo");
  }

  function closeAllDropdowns() {
    document.querySelectorAll(".dropdown__menu--open")
      .forEach((m) => m.classList.remove("dropdown__menu--open"));
  }

  function init() {
    // Close modals via data-close
    document.addEventListener("click", (e) => {
      const t = e.target;
      const closeId = t?.getAttribute?.("data-close");
      if (closeId) closeModal(closeId);
    });

    // Dropdown + actions
    document.addEventListener("click", (e) => {
      const t = e.target;

      // Toggle dropdown
      const ddName = t?.getAttribute?.("data-dd");
      if (ddName) {
        const id = `dd-${cssId(ddName)}`;
        const menu = document.getElementById(id);
        if (!menu) return;

        const open = menu.classList.contains("dropdown__menu--open");
        closeAllDropdowns();
        if (!open) menu.classList.add("dropdown__menu--open");

        e.stopPropagation();
        return;
      }

      // Action click
      const action = t?.getAttribute?.("data-action");
      const name = t?.getAttribute?.("data-name");
      if (action && name) {
        closeAllDropdowns();

        const target = (state.targets || []).find((x) => x.name === name);
        if (!target) return;

        if (action === "remove") openRemove(name);
        if (action === "info") openInfo(target);
        if (action === "edit") {
          setEditMode("edit", target);
          openModal("modalEdit");
        }
        return;
      }

      // click outside closes dropdowns
      closeAllDropdowns();
    });

    // Toggle enable
    document.addEventListener("change", async (e) => {
      const t = e.target;
      const name = t?.getAttribute?.("data-toggle");
      if (!name) return;

      const enabled = !!t.checked;
      try {
        await api(`/api/targets/${encodeURIComponent(name)}`, {
          method: "PATCH",
          body: JSON.stringify({ enabled }),
        });
        showToast(enabled ? "Enabled" : "Disabled", "ok");
        await loadTargets();
      } catch (err) {
        showToast(err?.message || "Failed", "err");
        // revert UI
        t.checked = !enabled;
      }
    });

    // Buttons
    $("btnRefresh")?.addEventListener("click", () => loadTargets().catch((e) => showToast(e.message, "err")));
    $("btnAdd")?.addEventListener("click", () => {
      setEditMode("add", null);
      openModal("modalEdit");
    });
    $("btnSaveTarget")?.addEventListener("click", () => saveTarget().catch((e) => showToast(e.message, "err")));
    $("btnConfirmRemove")?.addEventListener("click", () => confirmRemove().catch((e) => showToast(e.message, "err")));

    // Initial
    loadTargets().catch((e) => showToast(e.message, "err"));
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
