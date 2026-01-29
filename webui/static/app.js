/* Interheart WebUI (static) - v4.8.0 split
   - Dropdown Actions: Remove, Information, Edit
   - Remove modal: kun Cancel + Remove (reversert rekkefølge)
   - Penere checkbox: switch
   - Interval kolonne smalere
   - Latency + endpoint fjernet fra tabell -> flyttet til Information modal
*/

(function () {
  const API_BASE = "/api";

  // ---------- helpers ----------
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function clampStr(s, max = 120) {
    if (s == null) return "";
    const str = String(s);
    if (str.length <= max) return str;
    return str.slice(0, max - 1) + "…";
  }

  function safe(v, fallback = "-") {
    if (v === null || v === undefined || v === "") return fallback;
    return String(v);
  }

  function msToHuman(ms) {
    const n = Number(ms);
    if (!Number.isFinite(n)) return "-";
    if (n < 1000) return `${Math.round(n)} ms`;
    const s = n / 1000;
    if (s < 60) return `${s.toFixed(2)} s`;
    const m = Math.floor(s / 60);
    const rem = (s % 60).toFixed(0).padStart(2, "0");
    return `${m}m ${rem}s`;
  }

  // ---------- toast ----------
  let toastTimer = null;
  function toast(msg, kind = "ok") {
    const el = $("#toast");
    if (!el) return;
    el.dataset.kind = kind;
    $("#toastText").textContent = msg;
    el.classList.add("toast--show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("toast--show"), 2200);
  }

  // ---------- state ----------
  const state = {
    targets: [],
    filterEnabled: false,
    lastUpdated: null,
  };

  // ---------- fetch ----------
  async function apiGet(path) {
    const res = await fetch(API_BASE + path, { headers: { "Accept": "application/json" } });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`GET ${path} -> ${res.status} ${txt}`);
    }
    return res.json();
  }

  async function apiPost(path, body) {
    const res = await fetch(API_BASE + path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "Accept": "application/json" },
      body: JSON.stringify(body || {}),
    });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`POST ${path} -> ${res.status} ${txt}`);
    }
    return res.json().catch(() => ({}));
  }

  async function apiDelete(path) {
    const res = await fetch(API_BASE + path, { method: "DELETE" });
    if (!res.ok) {
      const txt = await res.text().catch(() => "");
      throw new Error(`DELETE ${path} -> ${res.status} ${txt}`);
    }
    return res.json().catch(() => ({}));
  }

  // ---------- render ----------
  function render() {
    renderHeader();
    renderTable();
  }

  function renderHeader() {
    const count = state.targets.length;
    const up = state.targets.filter(t => t.status === "up").length;
    const down = state.targets.filter(t => t.status === "down").length;
    const badge = $("#statusBadge");

    if (badge) {
      badge.classList.remove("badge--up", "badge--down", "badge--warn");
      if (down > 0) badge.classList.add("badge--down");
      else if (up === count && count > 0) badge.classList.add("badge--up");
      else badge.classList.add("badge--warn");

      $("#statusBadgeText").textContent = `${up} up • ${down} down • ${count} targets`;
    }

    const updated = $("#lastUpdated");
    if (updated) {
      updated.textContent = state.lastUpdated
        ? `Updated: ${new Date(state.lastUpdated).toLocaleString()}`
        : "Updated: -";
    }

    const sw = $("#enabledSwitch");
    if (sw) sw.checked = !!state.filterEnabled;
  }

  function getVisibleTargets() {
    const q = ($("#searchInput")?.value || "").trim().toLowerCase();
    let items = state.targets.slice();

    if (state.filterEnabled) {
      items = items.filter(t => !!t.enabled);
    }
    if (q) {
      items = items.filter(t => {
        const hay = [
          t.name, t.id, t.group, t.ip, t.interval,
          t.endpoint, t.url
        ].map(x => (x || "").toString().toLowerCase()).join(" ");
        return hay.includes(q);
      });
    }

    return items;
  }

  function renderTable() {
    const tbody = $("#targetsBody");
    if (!tbody) return;

    const items = getVisibleTargets();
    tbody.innerHTML = "";

    if (!items.length) {
      const tr = document.createElement("tr");
      tr.innerHTML = `<td class="td-muted" colspan="7" style="padding:16px 14px;">No targets found.</td>`;
      tbody.appendChild(tr);
      return;
    }

    for (const t of items) {
      const tr = document.createElement("tr");

      const statusClass =
        t.status === "up" ? "badge badge--up" :
        t.status === "down" ? "badge badge--down" :
        "badge badge--warn";

      tr.innerHTML = `
        <td>
          <div class="row">
            <span class="${statusClass}">${safe((t.status || "unknown").toUpperCase())}</span>
          </div>
        </td>
        <td>
          <div class="td-strong">${safe(t.name, "Unnamed")}</div>
          <div class="td-muted">${safe(t.group, "")}</div>
        </td>
        <td class="td-mono">${safe(t.ip)}</td>
        <td class="td-mono col-interval">${safe(t.interval)}</td>
        <td>
          <label class="switch" title="Enabled">
            <input type="checkbox" data-action="toggleEnabled" data-id="${safe(t.id)}" ${t.enabled ? "checked" : ""}/>
            <span class="switch__ui"></span>
          </label>
        </td>
        <td class="td-muted">${safe(t.last_check || t.lastCheck || "")}</td>
        <td style="text-align:right;">
          ${renderActionsDropdown(t)}
        </td>
      `;

      tbody.appendChild(tr);
    }

    // bind switch toggles
    $$(`input[data-action="toggleEnabled"]`, tbody).forEach(inp => {
      inp.addEventListener("change", async (e) => {
        const id = e.target.getAttribute("data-id");
        const enabled = !!e.target.checked;
        try {
          await apiPost(`/targets/${encodeURIComponent(id)}/enabled`, { enabled });
          toast(enabled ? "Enabled" : "Disabled", "ok");
          await refresh();
        } catch (err) {
          toast("Could not update enabled state", "err");
          console.error(err);
          await refresh();
        }
      });
    });

    // dropdown wiring
    $$(`.dropdown`, tbody).forEach(dd => wireDropdown(dd));
  }

  function renderActionsDropdown(t) {
    const id = safe(t.id);
    return `
      <div class="dropdown" data-id="${id}">
        <button class="btn btn--sm btn--ghost" data-dd-open type="button">Actions ▾</button>
        <div class="dropdown__menu" data-dd-menu>
          <button class="dropdown__item" type="button" data-dd-action="info">Information</button>
          <button class="dropdown__item" type="button" data-dd-action="edit">Edit</button>
          <div class="dropdown__sep"></div>
          <button class="dropdown__item dropdown__item--danger" type="button" data-dd-action="remove">Remove</button>
        </div>
      </div>
    `;
  }

  function wireDropdown(root) {
    const btn = $(`[data-dd-open]`, root);
    const menu = $(`[data-dd-menu]`, root);

    function close() {
      menu.classList.remove("dropdown__menu--open");
    }
    function toggle() {
      // close others
      $$(`.dropdown__menu--open`).forEach(m => m !== menu && m.classList.remove("dropdown__menu--open"));
      menu.classList.toggle("dropdown__menu--open");
    }

    btn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      toggle();
    });

    menu.addEventListener("click", async (e) => {
      const el = e.target.closest("[data-dd-action]");
      if (!el) return;
      const action = el.getAttribute("data-dd-action");
      const id = root.getAttribute("data-id");
      close();

      const target = state.targets.find(x => String(x.id) === String(id));
      if (!target) return;

      if (action === "remove") openRemoveModal(target);
      if (action === "info") openInfoModal(target);
      if (action === "edit") openEditModal(target);
    });

    // click outside closes
    document.addEventListener("click", (e) => {
      if (!root.contains(e.target)) close();
    });
  }

  // ---------- modals ----------
  function openModal(id) {
    const el = $(id);
    if (!el) return;
    el.classList.add("modal--open");
  }

  function closeModal(id) {
    const el = $(id);
    if (!el) return;
    el.classList.remove("modal--open");
  }

  // Remove modal: ingen "Close". Bare Cancel + Remove, og rekkefølge: Remove først, så Cancel.
  function openRemoveModal(t) {
    $("#removeTargetName").textContent = safe(t.name, "Unnamed");
    $("#removeTargetId").textContent = safe(t.id);

    const removeBtn = $("#btnConfirmRemove");
    removeBtn.onclick = async () => {
      try {
        await apiDelete(`/targets/${encodeURIComponent(t.id)}`);
        toast("Target removed", "ok");
        closeModal("#modalRemove");
        await refresh();
      } catch (err) {
        toast("Could not remove target", "err");
        console.error(err);
      }
    };

    openModal("#modalRemove");
  }

  function openInfoModal(t) {
    $("#infoName").textContent = safe(t.name, "Unnamed");
    $("#infoId").textContent = safe(t.id);
    $("#infoGroup").textContent = safe(t.group);
    $("#infoIP").textContent = safe(t.ip);
    $("#infoInterval").textContent = safe(t.interval);

    // Flyttet hit:
    $("#infoEndpoint").textContent = safe(t.endpoint || t.url || "");
    $("#infoLatency").textContent = msToHuman(t.latency_ms || t.latency || t.last_latency_ms);

    $("#infoLastCheck").textContent = safe(t.last_check || t.lastCheck || "");
    $("#infoStatus").textContent = safe(t.status || "unknown");

    openModal("#modalInfo");
  }

  function openEditModal(t) {
    // prefill
    $("#editId").value = safe(t.id, "");
    $("#editName").value = safe(t.name, "");
    $("#editGroup").value = safe(t.group, "");
    $("#editIP").value = safe(t.ip, "");
    $("#editInterval").value = safe(t.interval, "");
    $("#editEndpoint").value = safe(t.endpoint || t.url || "", "");

    $("#btnSaveEdit").onclick = async () => {
      const payload = {
        name: $("#editName").value.trim(),
        group: $("#editGroup").value.trim(),
        ip: $("#editIP").value.trim(),
        interval: $("#editInterval").value.trim(),
        endpoint: $("#editEndpoint").value.trim(),
      };

      try {
        await apiPost(`/targets/${encodeURIComponent(t.id)}`, payload);
        toast("Target updated", "ok");
        closeModal("#modalEdit");
        await refresh();
      } catch (err) {
        toast("Could not update target", "err");
        console.error(err);
      }
    };

    openModal("#modalEdit");
  }

  // modal close wiring
  function wireModalBasics(modalSel) {
    const modal = $(modalSel);
    if (!modal) return;

    const backdrop = $(`.modal__backdrop`, modal);
    const closeBtns = $$(`[data-modal-close]`, modal);

    backdrop?.addEventListener("click", () => closeModal(modalSel));
    closeBtns.forEach(b => b.addEventListener("click", () => closeModal(modalSel)));
  }

  // ---------- refresh ----------
  async function refresh() {
    try {
      const data = await apiGet("/targets");
      state.targets = Array.isArray(data) ? data : (data.targets || []);
      state.lastUpdated = Date.now();
      render();
    } catch (err) {
      console.error(err);
      toast("Could not load targets", "err");
    }
  }

  async function toggleFilterEnabled(v) {
    state.filterEnabled = !!v;
    renderTable();
  }

  // ---------- init ----------
  function init() {
    // wire header UI
    $("#btnRefresh")?.addEventListener("click", refresh);
    $("#searchInput")?.addEventListener("input", renderTable);
    $("#enabledSwitch")?.addEventListener("change", (e) => toggleFilterEnabled(e.target.checked));

    // modals
    wireModalBasics("#modalRemove");
    wireModalBasics("#modalInfo");
    wireModalBasics("#modalEdit");

    // Remove modal buttons
    $("#btnCancelRemove")?.addEventListener("click", () => closeModal("#modalRemove"));

    // Info modal
    $("#btnCloseInfo")?.addEventListener("click", () => closeModal("#modalInfo"));

    // Edit modal
    $("#btnCancelEdit")?.addEventListener("click", () => closeModal("#modalEdit"));

    refresh();
    setInterval(refresh, 10_000);
  }

  document.addEventListener("DOMContentLoaded", init);
})();
