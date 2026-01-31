(function(){
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  // ---- Toasts ----
  const toasts = $("#toasts");
  function escapeHtml(s){
    return String(s ?? "")
      .replaceAll("&","&amp;").replaceAll("<","&lt;").replaceAll(">","&gt;")
      .replaceAll('"',"&quot;").replaceAll("'","&#039;");
  }
  function toast(title, msg){
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `
      <div>
        <b>${escapeHtml(title)}</b>
        <p>${escapeHtml(msg || "")}</p>
      </div>
      <button class="x" aria-label="Close">×</button>
    `;
    el.querySelector(".x").onclick = () => el.remove();
    toasts.appendChild(el);
    setTimeout(() => { if (el && el.parentNode) el.remove(); }, 5200);
  }

  // ---- Modals ----
  function show(el){ el.classList.add("show"); el.setAttribute("aria-hidden","false"); }
  function hide(el){ el.classList.remove("show"); el.setAttribute("aria-hidden","true"); }

  // ---- API helpers ----
  async function apiPost(url, fd){
    const res = await fetch(url, {method:"POST", body: fd});
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    let data = null;
    if (ct.includes("application/json")){
      data = await res.json();
    } else {
      const txt = await res.text();
      // avoid blowing up the UI when the server returns HTML on error
      data = { ok: res.ok, message: txt ? String(txt).slice(0,240) : (res.statusText || "Error") };
    }
    if (!res.ok && data && data.ok !== true){
      // Normalize common fetch failures
      data.ok = false;
      data.message = data.message || res.statusText || "Request failed";
    }
    return data;
  }
  async function apiGet(url){
    const res = await fetch(url, {cache:"no-store"});
    const ct = (res.headers.get("content-type") || "").toLowerCase();
    if (ct.includes("application/json")){
      const data = await res.json();
      if (!res.ok){
        // Bubble up a readable error (this avoids "Failed to fetch" with no context)
        throw new Error(data?.message || res.statusText || "Request failed");
      }
      return data;
    }
    const txt = await res.text();
    if (!res.ok){
      throw new Error(res.statusText || "Request failed");
    }
    // Non-JSON but OK (rare) -> return wrapper
    return { ok: true, text: txt };
  }

  // ---- Logs modal ----
  const logModal = $("#logModal");
  const openLogs = $("#openLogsFooter") || $("#openLogs");
  const closeLogs = $("#btnCloseLogs");
  const reloadLogs = $("#btnReloadLogs");
  const copyLogs = $("#btnCopyLogs");
  const logBox = $("#logBox");
  const logMeta = $("#logMeta");
  const logFilter = $("#logFilter");
  const logChips = $("#logChips");
  const logDlMenu = $("#logDlMenu");
  const logLinesLbl = $("#logLinesLbl");
  let rawLog = "";
  let lastTargets = [];
  let logLevel = "all"; // all|info|warn|error

  async function loadLogs(){
    const lines = logLinesLbl ? Number(logLinesLbl.textContent || "200") : 200;
    try{
      const data = await apiGet(`/logs?lines=${encodeURIComponent(lines)}`);
      rawLog = data.text || "";
      logMeta.textContent = `${data.source || "log"} • ${(data.lines || 0)} lines • ${(data.updated || "")}`;
      applyLogFilter();
      logBox.scrollTop = logBox.scrollHeight;
    }catch(e){
      rawLog = "";
      logBox.textContent = "Failed to fetch logs";
      logMeta.textContent = "error";
    }
  }

  function applyLogFilter(){
    const q = (logFilter.value || "").trim().toLowerCase();
    const all = (rawLog || "").split("\n");
    const levelFiltered = all.filter(l => {
      if (logLevel === "all") return true;
      const ll = l.toLowerCase();
      if (logLevel === "error") return (ll.includes("error") || ll.includes("failed"));
      if (logLevel === "warn") return (ll.includes("warn") || ll.includes("warning"));
      if (logLevel === "info") return !(ll.includes("error") || ll.includes("failed") || ll.includes("warn") || ll.includes("warning"));
      return true;
    });
    const lines = !q ? levelFiltered : levelFiltered.filter(l => l.toLowerCase().includes(q));

    if (!lines.length){
      logBox.textContent = q ? "(no matches)" : "(empty)";
      return;
    }

    const esc = (s) => String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
    const html = lines.map(l => {
      const ll = l.toLowerCase();
      let cls = "level-info";
      if (ll.includes("error") || ll.includes("failed")) cls = "level-error";
      else if (ll.includes("warn") || ll.includes("warning")) cls = "level-warn";
      return `<div class="log-line ${cls}">${esc(l)}</div>`;
    }).join("");
    logBox.innerHTML = html;
  }

  function setActiveChip(){
    $$(".chip-btn", logChips).forEach(b => {
      const on = (b.dataset.level || "all") === logLevel;
      b.classList.toggle("is-active", on);
    });
  }

  logChips?.addEventListener("click", (e) => {
    const btn = e.target?.closest?.(".chip-btn");
    if (!btn) return;
    logLevel = btn.dataset.level || "all";
    setActiveChip();
    applyLogFilter();
  });

  openLogs?.addEventListener("click", async () => { show(logModal); logFilter?.focus(); await loadLogs(); });
  closeLogs?.addEventListener("click", () => hide(logModal));
  reloadLogs?.addEventListener("click", async () => await loadLogs());
  copyLogs?.addEventListener("click", async () => {
    try{ await navigator.clipboard.writeText(logBox.textContent || ""); toast("Copied", "Logs copied to clipboard"); }catch(e){}
  });

  function downloadLogs(fmt){
    const lines = logLinesLbl ? Number(logLinesLbl.textContent || "200") : 200;
    const q = (logFilter?.value || "").trim();
    const lvl = logLevel;
    const url = `/api/logs-export?fmt=${encodeURIComponent(fmt)}&lines=${encodeURIComponent(lines)}&q=${encodeURIComponent(q)}&level=${encodeURIComponent(lvl)}`;
    window.open(url, "_blank");
  }
  // Download dropdown
  logDlMenu?.querySelectorAll("[data-dlfmt]").forEach(b => {
    if (b.dataset.bound === "1") return;
    b.dataset.bound = "1";
    b.addEventListener("click", () => {
      closeAllMenus();
      downloadLogs(b.getAttribute("data-dlfmt") || "csv");
    });
  });
  logFilter?.addEventListener("input", applyLogFilter);
  logModal?.addEventListener("click", (e) => { if (e.target === logModal) hide(logModal); });

  // ---- Filter targets ----
  const filterInput = $("#filterInput");
  const table = $("#targetsTable");
  // ---- Sorting state (default: IP asc) ----
  let sortKey = "ip";
  let sortDir = "asc"; // asc|desc

  function ipKey(ip){
    try{
      const p = String(ip||"0.0.0.0").split(".").map(x => Number(x));
      if (p.length !== 4 || p.some(n => Number.isNaN(n))) return [999,999,999,999];
      return p;
    }catch(e){
      return [999,999,999,999];
    }
  }

  function numKey(v){
    const n = Number(v);
    return Number.isFinite(n) ? n : -1;
  }

  function sortTargets(list){
    const arr = Array.from(list || []);
    const dir = (sortDir === "desc") ? -1 : 1;

    const cmp = (a,b) => {
      const ak = (sortKey || "");
      if (ak === "ip"){
        const ka = ipKey(a.ip);
        const kb = ipKey(b.ip);
        for (let i=0;i<4;i++){
          if (ka[i] !== kb[i]) return (ka[i] - kb[i]) * dir;
        }
        return String(a.name||"").localeCompare(String(b.name||"")) * dir;
      }
      if (ak === "interval"){
        return (numKey(a.interval) - numKey(b.interval)) * dir;
      }
      if (ak === "last_ping"){
        return (numKey(a.last_ping_epoch) - numKey(b.last_ping_epoch)) * dir;
      }
      if (ak === "last_resp"){
        return (numKey(a.last_response_epoch) - numKey(b.last_response_epoch)) * dir;
      }
      if (ak === "status"){
        return String(a.status||"").localeCompare(String(b.status||"")) * dir;
      }
      // name
      return String(a.name||"").localeCompare(String(b.name||"")) * dir;
    };

    arr.sort(cmp);
    return arr;
  }

  function updateSortIndicators(){
    $$("th.sortable", table).forEach(th => {
      const key = th.dataset.sort || "";
      const ind = th.querySelector(".sort-ind");
      th.classList.toggle("is-sorted", key === sortKey);
      if (!ind) return;
      if (key === sortKey){
        ind.textContent = (sortDir === "asc") ? "▲" : "▼";
      } else {
        ind.textContent = "";
      }
    });
  }

  function bindSortHeaders(){
    $$("th.sortable", table).forEach(th => {
      if (th.dataset.bound === "1") return;
      th.dataset.bound = "1";
      th.addEventListener("click", () => {
        const key = th.dataset.sort || "name";
        if (sortKey === key){
          sortDir = (sortDir === "asc") ? "desc" : "asc";
        } else {
          sortKey = key;
          sortDir = (key === "name" || key === "status") ? "asc" : "asc";
        }
        updateSortIndicators();
        renderTargets(lastTargets);
      });
    });
    updateSortIndicators();
  }

  function applyTargetFilter(){
    renderTargets(lastTargets);
  }
  filterInput?.addEventListener("input", applyTargetFilter);

  // ---- Add modal ----
  const addModal = $("#addModal");
  const openAdd = $("#openAdd");
  const addCancel = $("#btnAddCancel");
  const addForm = $("#addForm");
  const btnAddSubmit = $("#btnAddSubmit");
  const addName = addForm?.querySelector('input[name="name"]');
  const addIp = addForm?.querySelector('input[name="ip"]');

  let nameSuggestTimer = null;
  async function suggestNameForIp(ip, targetInput){
    const clean = String(ip||"").trim();
    if (!clean) return;
    try{
      const data = await apiGet(`/api/name-suggest?ip=${encodeURIComponent(clean)}`);
      if (!data.ok) return;
      const s = String(data.name || "").trim();
      if (!s) return;
      // Only auto-fill if empty or still matching a previous suggestion
      if (targetInput && (!targetInput.value || targetInput.dataset.autofill === "1")){
        targetInput.value = s;
        targetInput.dataset.autofill = "1";
      }
    }catch(e){}
  }

  function bindSmartAssist(ipInput, nameInput){
    if (!ipInput || !nameInput) return;
    nameInput.addEventListener("input", () => {
      // user touched it -> stop auto overwriting
      nameInput.dataset.autofill = "0";
    });
    ipInput.addEventListener("input", () => {
      if (nameSuggestTimer) clearTimeout(nameSuggestTimer);
      nameSuggestTimer = setTimeout(() => suggestNameForIp(ipInput.value, nameInput), 400);
    });
    ipInput.addEventListener("blur", () => suggestNameForIp(ipInput.value, nameInput));
  }

  bindSmartAssist(addIp, addName);

  openAdd?.addEventListener("click", () => show(addModal));
  addCancel?.addEventListener("click", () => hide(addModal));
  addModal?.addEventListener("click", (e) => { if (e.target === addModal) hide(addModal); });

  addForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    btnAddSubmit.disabled = true;
    btnAddSubmit.textContent = "Adding…";
    try{
      const fd = new FormData(addForm);
      const data = await apiPost("/api/add", fd);
      if (data.ok){
        const n = fd.get("name");
        if (n) markForcedStarting(n);
        toast("Added", data.message || "Target added");
        hide(addModal);
        addForm.reset();
        await refreshState(true);
      } else {
        toast("Error", data.message || "Failed to add");
      }
    }catch(err){
      toast("Error", err?.message || "Failed to add");
    }finally{
      btnAddSubmit.disabled = false;
      btnAddSubmit.textContent = "Add target";
    }
  });

  // ---- Confirm delete modal ----
const confirmModal = $("#confirmModal");
const btnCancelRemove = $("#btnCancelRemove");
const btnConfirmRemove = $("#btnConfirmRemove");
const confirmName = $("#confirmName");
let pendingRemoveNames = null; // string[] or null
let confirmCountdown = null;

function clearConfirmCountdown(){
  if (confirmCountdown){
    clearInterval(confirmCountdown);
    confirmCountdown = null;
  }
}

function openConfirmRemove(names){
  const arr = Array.isArray(names) ? names.filter(Boolean) : [String(names||"")].filter(Boolean);
  pendingRemoveNames = arr.length ? arr : null;
  if (!pendingRemoveNames) return;

  if (pendingRemoveNames.length === 1){
    confirmName.textContent = pendingRemoveNames[0];
  } else {
    const preview = pendingRemoveNames.slice(0, 4).join(", ");
    confirmName.textContent = `${pendingRemoveNames.length} targets: ${preview}${pendingRemoveNames.length > 4 ? "…" : ""}`;
  }

  clearConfirmCountdown();
  let sec = 3;
  btnConfirmRemove.disabled = true;
  btnConfirmRemove.classList.add("is-disabled");
  btnConfirmRemove.textContent = `Delete (${sec})`;

  confirmCountdown = setInterval(() => {
    sec -= 1;
    if (sec <= 0){
      clearConfirmCountdown();
      btnConfirmRemove.disabled = false;
      btnConfirmRemove.classList.remove("is-disabled");
      btnConfirmRemove.textContent = "Delete";
    } else {
      btnConfirmRemove.textContent = `Delete (${sec})`;
    }
  }, 1000);

  show(confirmModal);
}

function closeConfirmRemove(){
  pendingRemoveNames = null;
  clearConfirmCountdown();
  hide(confirmModal);
}

btnCancelRemove?.addEventListener("click", closeConfirmRemove);
confirmModal?.addEventListener("click", (e) => { if (e.target === confirmModal) closeConfirmRemove(); });

btnConfirmRemove?.addEventListener("click", async () => {
  clearConfirmCountdown();
  const names = pendingRemoveNames;
  if (!names || !names.length) return;

  btnConfirmRemove.disabled = true;
  btnConfirmRemove.classList.add("is-disabled");
  btnConfirmRemove.textContent = "Deleting…";

  try{
    if (names.length === 1){
      const fd = new FormData();
      fd.set("name", names[0]);
      const data = await apiPost("/api/remove", fd);
      toast(data.ok ? "Deleted" : "Error", data.message || (data.ok ? "Deleted" : "Failed"));
    } else {
      const data = await postJson("/api/bulk-remove", {names});
      toast(data.ok ? "Deleted" : "Error", data.message || (data.ok ? "Deleted" : "Failed"));
    }
  }catch(e){
    toast("Error", e?.message || "Failed");
  }finally{
    btnConfirmRemove.textContent = "Delete";
    btnConfirmRemove.disabled = false;
    btnConfirmRemove.classList.remove("is-disabled");
    closeConfirmRemove();
    clearBulkSelection();
    await refreshState(true);
  }
});
// ---- Info modal ----

  const infoModal = $("#infoModal");
  const btnCloseInfo = $("#btnCloseInfo");
  const infoTitle = $("#infoTitle");
  const infoName = $("#infoName");
  const infoIp = $("#infoIp");
  const infoEnabled = $("#infoEnabled");
  const infoInterval = $("#infoInterval");
  const infoEndpoint = $("#infoEndpoint");
  const infoStatus = $("#infoStatus");
  const infoLastPing = $("#infoLastPing");
  const infoLastResp = $("#infoLastResp");
  const infoLatency = $("#infoLatency");
  const btnCopyEndpoint = $("#btnCopyEndpoint");

  const u24 = $("#u24");
  const u7 = $("#u7");
  const u30 = $("#u30");
  const u90 = $("#u90");
  const u24t = $("#u24t");
  const u7t = $("#u7t");
  const u30t = $("#u30t");
  const u90t = $("#u90t");

  
  btnCopyEndpoint?.addEventListener("click", async () => {
    const url = (infoEndpoint && infoEndpoint.textContent) ? String(infoEndpoint.textContent).trim() : "";
    if (!url || url === "-") return;
    try{
      await navigator.clipboard.writeText(url);
      toast("Copied", "Endpoint URL copied");
    }catch(e){
      const ta = document.createElement("textarea");
      ta.value = url;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      toast("Copied", "Endpoint URL copied");
    }
  });

btnCloseInfo?.addEventListener("click", () => hide(infoModal));
  infoModal?.addEventListener("click", (e) => { if (e.target === infoModal) hide(infoModal); });

  function setUptimeRow(barEl, textEl, stat){
    if (!barEl || !textEl) return;
    if (!stat || !stat.series || !stat.series.length){
      barEl.innerHTML = "";
      textEl.textContent = "-";
      return;
    }

    const pct = Number(stat.pct ?? 0);
    textEl.textContent = `${Math.max(0, Math.min(100, pct))}%` + ((stat.avg_rtt_ms === null || stat.avg_rtt_ms === undefined) ? "" : ` • avg ${stat.avg_rtt_ms}ms`);

    const series = stat.series;
    barEl.innerHTML = series.map(s => {
      const cls = (s === "up") ? "tick up" : (s === "hb" ? "tick hb" : "tick down");
      return `<span class="${cls}"></span>`;
    }).join("");
  }

  function drawSparkline(container, points){
  if (!container) return;
  const w = 120, h = 22, pad = 2;
  const pts = (points||[]).map(p => Math.max(0, Math.min(100, Number(p)||0)));
  if (!pts.length){
    container.innerHTML = "";
    return;
  }
  const xStep = (w - pad*2) / Math.max(1, (pts.length - 1));
  const toY = (v) => pad + (h - pad*2) * (1 - (v/100));
  const d = pts.map((v,i)=>`${pad + i*xStep},${toY(v).toFixed(2)}`).join(" ");
  container.innerHTML = `
    <svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" role="img" aria-label="Uptime trend">
      <polyline class="grid" fill="none" stroke="rgba(255,255,255,.25)" stroke-width="1" points="0,${h-1} ${w},${h-1}"></polyline>
      <polyline fill="none" stroke="rgba(255,255,255,.70)" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" points="${d}"></polyline>
      <circle cx="${pad + (pts.length-1)*xStep}" cy="${toY(pts[pts.length-1]).toFixed(2)}" r="1.8" fill="rgba(255,255,255,.85)"></circle>
    </svg>
  `;
}

async function openInfo(name){
    infoTitle.textContent = name;
    show(infoModal);

    // Reset
    [infoName,infoIp,infoEnabled,infoInterval,infoEndpoint,infoStatus,infoLastPing,infoLastResp,infoLatency].forEach(el => { if (el) el.textContent = "-"; });
    [u24,u7,u30,u90].forEach(el => { if (el) el.style.width = "0%"; });
    [u24t,u7t,u30t,u90t].forEach(el => { if (el) el.textContent = "-"; });

    const data = await apiGet(`/api/info?name=${encodeURIComponent(name)}`);
    if (!data || !data.ok){
      toast("Error", data?.message || "Failed to load target information");
      return;
    }

    infoName.textContent = data.name || name;
    infoIp.textContent = data.ip || "-";
    infoEnabled.textContent = (data.enabled ? "Yes" : "No");
    infoInterval.textContent = String(data.interval ?? "-");
    infoEndpoint.textContent = data.endpoint || "-";

    const cur = data.current || {};
    infoStatus.textContent = (cur.status || "unknown").toUpperCase();
    infoLastPing.textContent = cur.last_ping_human || "-";
    infoLastResp.textContent = cur.last_response_human || "-";
    infoLatency.textContent = (cur.last_rtt_ms === undefined || cur.last_rtt_ms === null || Number(cur.last_rtt_ms) < 0) ? "-" : `${cur.last_rtt_ms} ms`;

    const up = data.uptime || {};
    setUptimeRow(u24, u24t, up["24h"]);
    setUptimeRow(u7, u7t, up["7d"]);
    setUptimeRow(u30, u30t, up["30d"]);
    setUptimeRow(u90, u90t, up["90d"]);
  }

  // ---- Edit modal ----
  const editModal = $("#editModal");
  const btnEditCancel = $("#btnEditCancel");
  const btnEditEnable = $("#btnEditEnable");
  const btnEditDisable = $("#btnEditDisable");
  const editForm = $("#editForm");
  const editTitle = $("#editTitle");
  const editOldName = $("#editOldName");
  const editName = $("#editName");
  const editIp = $("#editIp");
  const editInterval = $("#editInterval");
  const editEndpoint = $("#editEndpoint");
  const editEnabled = $("#editEnabled");
  const btnEditSubmit = $("#btnEditSubmit");

  // Smart assist for edit form (does not overwrite if user edits name)
  bindSmartAssist(editIp, editName);

  function closeEdit(){ hide(editModal); }

  btnEditCancel?.addEventListener("click", closeEdit);
  editModal?.addEventListener("click", (e) => { if (e.target === editModal) closeEdit(); });

  async function openEdit(name){
    editTitle.textContent = name;
    show(editModal);

    // Best effort: pull current values using /state map + /api/get raw
    const row = $(`tr[data-name="${CSS.escape(name)}"]`);
    const ip = row ? (row.getAttribute("data-ip") || "") : "";

    editOldName.value = name;
    editName.value = name;
    editIp.value = ip;
    editInterval.value = row ? (row.querySelector(".interval-input")?.getAttribute("data-interval") || "60") : "60";

    // Pull current values via /api/info (clean fields)
    const data = await apiGet(`/api/info?name=${encodeURIComponent(name)}`);
    if (data && data.ok){
      editEndpoint.value = data.endpoint || "";
      editEnabled.value = data.enabled ? "1" : "0";
    } else {
      editEndpoint.value = "";
      editEnabled.value = "1";
    }

    // Toggle Enable/Disable buttons
    const isEnabled = editEnabled.value === "1";
    if (btnEditEnable) btnEditEnable.style.display = isEnabled ? "none" : "inline-flex";
    if (btnEditDisable) btnEditDisable.style.display = isEnabled ? "inline-flex" : "none";
  }

  async function setEnabledFromEdit(enabled){
    const name = editOldName.value;
    if (!name) return;
    const fd = new FormData();
    fd.set("name", name);
    try{
      const data = await apiPost(enabled ? "/api/enable" : "/api/disable", fd);
      if (data.ok && enabled) markForcedStarting(name);
      toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
      editEnabled.value = enabled ? "1" : "0";
      if (btnEditEnable) btnEditEnable.style.display = enabled ? "none" : "inline-flex";
      if (btnEditDisable) btnEditDisable.style.display = enabled ? "inline-flex" : "none";
      await refreshState(true);
    }catch(e){
      toast("Error", e?.message || "Failed");
    }
  }

  btnEditEnable?.addEventListener("click", () => setEnabledFromEdit(true));
  btnEditDisable?.addEventListener("click", () => setEnabledFromEdit(false));

  editForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    btnEditSubmit.disabled = true;
    btnEditSubmit.textContent = "Saving…";
    try{
      const fd = new FormData(editForm);
      const data = await apiPost("/api/edit", fd);
      toast(data.ok ? "Saved" : "Error", data.message || (data.ok ? "Done" : "Failed"));
      if (data.ok) hide(editModal);
    }catch(err){
      toast("Error", err?.message || "Failed");
    }finally{
      btnEditSubmit.disabled = false;
      btnEditSubmit.textContent = "Save";
      await refreshState(true);
    }
  });

  // ---- Dropdown menus ----
  function closeAllMenus(){
    $$(".menu.show").forEach(m => m.classList.remove("show"));
  }
  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".menu-btn");
    if (btn){
      const menu = btn.closest(".menu");
      const isOpen = menu.classList.contains("show");
      closeAllMenus();
      if (!isOpen) menu.classList.add("show");
      return;
    }
    if (!e.target.closest(".menu")) closeAllMenus();
  });

  // ---- Inline interval editing ----
  async function setIntervalFor(name, seconds){
    const fd = new FormData();
    fd.set("name", name);
    fd.set("seconds", String(seconds));
    return await apiPost("/api/set-target-interval", fd);
  }

  function attachIntervalHandlers(){
    $$("tr[data-name]").forEach(row => {
      const name = row.getAttribute("data-name");
      const input = row.querySelector(".interval-input");
      if (!input || input.dataset.bound === "1") return;
      input.dataset.bound = "1";

      const commit = async () => {
        const v = String(input.value || "").trim();
        const n = parseInt(v, 10);
        if (!Number.isFinite(n) || n < 10 || n > 86400){
          toast("Invalid interval", "Use 10–86400 seconds");
          input.value = input.getAttribute("data-interval") || "60";
          return;
        }
        if (String(n) === String(input.getAttribute("data-interval"))){
          return;
        }

        input.disabled = true;
        try{
          const r = await setIntervalFor(name, n);
          if (r.ok){
            toast("Updated", r.message || `Interval set to ${n}s`);
            input.setAttribute("data-interval", String(n));
          }else{
            toast("Error", r.message || "Failed to set interval");
            input.value = input.getAttribute("data-interval") || "60";
          }
        }catch(e){
          toast("Error", e?.message || "Failed to set interval");
          input.value = input.getAttribute("data-interval") || "60";
        }finally{
          input.disabled = false;
        }
      };

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter"){ e.preventDefault(); commit(); input.blur(); }
        if (e.key === "Escape"){ input.value = input.getAttribute("data-interval") || "60"; input.blur(); }
      });
      input.addEventListener("blur", commit);
    });
  }

  // ---- Menu actions ----
  

    const forcedStarting = new Map(); // name -> until (ms)

function markForcedStarting(name){
  if(!name) return;
  forcedStarting.set(String(name), Date.now() + 10*60*1000);
}

function clearForcedStarting(name){
  if(!name) return;
  forcedStarting.delete(String(name));
}

function statusClass(name, status, enabled, lastRttMs, lastRespEpoch){
  const nm = String(name||"");
  let st = String(status||"unknown").toLowerCase();
  const isEnabled = Number(enabled||0) === 1;

  const hbFail = isEnabled && st === "down" && Number(lastRttMs||-1) >= 0 && Number(lastRespEpoch||0) > 0;
  const hasForced = forcedStarting.has(nm);

  if (!isEnabled) return "status-disabled";

  // Right after enabling, the DB may still report last_status='disabled'
  // until the first run updates it. Treat that as STARTING to avoid
  // flipping the UI back to DISABLED.
  if (st === "disabled") st = "starting";

  if (st === "up")  { clearForcedStarting(nm); return "status-up"; }
  if (hbFail)       { clearForcedStarting(nm); return "status-hb"; }
  if (st === "down"){ clearForcedStarting(nm); return "status-down"; }

  if (st === "starting") return "status-starting";
  if (hasForced) return "status-starting";

  return "status-unknown";
}

function statusLabel(name, status, enabled, lastRttMs, lastRespEpoch){
  const nm = String(name||"");
  let st = String(status||"unknown").toLowerCase();
  const isEnabled = Number(enabled||0) === 1;

  const hbFail = isEnabled && st === "down" && Number(lastRttMs||-1) >= 0 && Number(lastRespEpoch||0) > 0;
  const hasForced = forcedStarting.has(nm);

  if (!isEnabled) return "DISABLED";

  if (st === "disabled") st = "starting";
  if (st === "up") return "OK";
  if (st === "starting") return "STARTING..";
  if (hasForced) return "STARTING..";
  if (hbFail) return "HEARTBEAT FAILED";
  if (st === "down") return "NOT RESPONDING";
  return st.toUpperCase();
}

function renderSnapshots(snaps){
    const arr = Array.isArray(snaps) ? snaps : [];
    const out = arr.slice(0,3).map(s => {
      const cls = (s && s.state) ? String(s.state) : "unknown";
      const title = (s && s.label) ? String(s.label) : cls;
      return `<span class="snap-dot ${cls}" title="${title}"></span>`;
    }).join("");
    return `<span class="snapshots">${out}</span>`;
  }


  function setActionVisibility(row, enabled){
    const btnEnable = row.querySelector('.menu-item[data-action="enable"]');
    const btnDisable = row.querySelector('.menu-item[data-action="disable"]');
    if (btnEnable) btnEnable.style.display = enabled ? "none" : "flex";
    if (btnDisable) btnDisable.style.display = enabled ? "flex" : "none";
  }

  function buildRow(t){
    const enabled = Number(t.enabled ?? 0) === 1;
    const ic = {
      info: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M12 16v-4"/><path d="M12 8h.01"/></svg>`,
      edit: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>`,
      enable: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6 9 17l-5-5"/></svg>`,
      disable: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="M4.9 4.9l14.2 14.2"/></svg>`,
      test: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/></svg>`,
      remove: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v6"/><path d="M14 11v6"/></svg>`
    };
    return `<tr data-name="${t.name}" data-ip="${t.ip}" data-status="${t.status}" data-enabled="${enabled?1:0}"
              data-last-ping="${t.last_ping_epoch||0}" data-last-resp="${t.last_response_epoch||0}" data-last-rtt="${t.last_rtt_ms ?? -1}">
            <td class="name-cell">
              <div class="name-cell-inner">
                <span class="gutter" aria-hidden="true">
                  <input class="row-check" type="checkbox" aria-label="Select row">
                  <span class="gutter-flash" aria-hidden="true"></span>
                </span>
                <code class="name-code" title="${t.name}">${t.name}</code>
              </div>
            </td>
            <td><code>${t.ip}</code></td>
            <td>
              <span class="chip status-chip ${statusClass(t.name, t.status, t.enabled, t.last_rtt_ms, t.last_response_epoch)}">
                <span class="dot"></span>
                <span class="status-text">${statusLabel(t.name, t.status, t.enabled, t.last_rtt_ms, t.last_response_epoch)}</span>${renderSnapshots(t.snapshots)}
              </span>
            </td>
            <td>
              <div class="interval-wrap">
                <input class="interval-input" data-interval="${t.interval}" value="${t.interval}" inputmode="numeric" />
                <span class="interval-suffix">s</span>
              </div>
            </td>
            <td><code class="last-ping">${t.last_ping_human||"-"}</code></td>
            <td><code class="last-resp">${t.last_response_human||"-"}</code></td>
            <td style="text-align:right;">
              <div class="menu">
                <button class="btn btn-ghost btn-mini menu-btn" type="button" aria-label="Actions">⋯</button>
                <div class="menu-dd" role="menu">
                  <button class="menu-item" data-action="info" type="button"><span class="mi-ic" aria-hidden="true">${ic.info}</span><span>Information</span></button>
                  <button class="menu-item" data-action="edit" type="button"><span class="mi-ic" aria-hidden="true">${ic.edit}</span><span>Edit</span></button>
                  <div class="menu-sep"></div>
                  <button class="menu-item" data-action="enable" type="button" style="display:${enabled ? 'none' : 'flex'}"><span class="mi-ic" aria-hidden="true">${ic.enable}</span><span>Enable</span></button>
                  <button class="menu-item" data-action="disable" type="button" style="display:${enabled ? 'flex' : 'none'}"><span class="mi-ic" aria-hidden="true">${ic.disable}</span><span>Disable</span></button>
                  <div class="menu-sep"></div>
                  <button class="menu-item" data-action="test" type="button"><span class="mi-ic" aria-hidden="true">${ic.test}</span><span>Test</span></button>
                  <button class="menu-item danger" data-action="remove" type="button"><span class="mi-ic" aria-hidden="true">${ic.remove}</span><span>Delete</span></button>
                </div>
              </div>
            </td>
          </tr>`;
  }

  function renderTargets(list){
  const tbody = $("#targetsTable tbody");
  if (!tbody) return;

  // Preserve selection across re-renders
  const preSelected = new Set();
  $$("tr[data-name] .row-check").forEach(cb => {
    if (cb.checked){
      const row = cb.closest("tr");
      if (row) preSelected.add(row.getAttribute("data-name"));
    }
  });

  const q = (filterInput?.value || "").trim().toLowerCase();
  const filtered = (list || []).filter(t => {
    if (!q) return true;
    const name = String(t.name||"").toLowerCase();
    const ip = String(t.ip||"").toLowerCase();
    const st = String(t.status||"").toLowerCase();
    return name.includes(q) || ip.includes(q) || st.includes(q);
  });

  const sorted = sortTargets(filtered);
  tbody.innerHTML = sorted.map(buildRow).join("");
  attachIntervalHandlers();
  attachMenuActions();
  attachBulkHandlers();
  attachRowClickHandlers();
  // Restore selection
  $$("tr[data-name]").forEach(row => {
    const name = row.getAttribute("data-name");
    const cb = row.querySelector(".row-check");
    if (cb && preSelected.has(name)){
      cb.checked = true;
      row.classList.add("is-selected");
    }
  });
  // keep visibility consistent
  $$("tr[data-name]").forEach(row => {
    const enabled = String(row.dataset.enabled||"0")==="1";
    setActionVisibility(row, enabled);
  });
  }

function attachMenuActions(){
    $$("tr[data-name]").forEach(row => {
      const name = row.getAttribute("data-name");
      row.querySelectorAll(".menu-item").forEach(btn => {
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";
        btn.addEventListener("click", async () => {
          closeAllMenus();
          const action = btn.getAttribute("data-action");
          const fd = new FormData();
          fd.set("name", name);

          if (action === "remove"){
            openConfirmRemove(name);
            return;
          }
          if (action === "info"){
            await openInfo(name);
            return;
          }
          if (action === "edit"){
            await openEdit(name);
            return;
          }

          try{
            let data;
            if (action === "test"){
              toast("Testing", `Running test for ${name}…`);
              data = await apiPost("/api/test", fd);

              const msg = (data.message || "").trim();
              let title = "Test results";
              let body = "";

              if (msg.startsWith("OK:")){
                body = `Success. ${name} responded.`;
              } else if (msg.startsWith("WARN:")){
                body = `Ping OK, but heartbeat failed for ${name}.`;
              } else if (msg.startsWith("FAIL:")){
                body = `Failed. No response from ${name}.`;
              } else if (!data.ok){
                body = msg || `Failed. No response from ${name}.`;
              } else {
                body = msg || `Success. ${name} responded.`;
              }

              toast(title, body);
            } else if (action === "enable"){
              data = await apiPost("/api/enable", fd);
              toast(data.ok ? "Updated" : "Error", data.message || (data.ok ? "Enabled" : "Failed"));
              if (data.ok){
                markForcedStarting(name);
                // optimistic starting state + immediate verification ping
                row.setAttribute("data-enabled","1");
                row.setAttribute("data-status","starting");
                const stEl = row.querySelector(".status-text");
                const chip = row.querySelector(".status-chip");
                if (stEl) stEl.textContent = "STARTING..";
                if (chip){ chip.classList.remove("status-up","status-down","status-hb","status-unknown","status-starting","status-disabled"); chip.classList.add("status-starting"); }
                // fire test in background (don't block UI)
                apiPost("/api/test", fd).then(()=>refreshState(true)).catch(()=>{});
              }
            } else if (action === "disable"){
              data = await apiPost("/api/disable", fd);
              toast(data.ok ? "Updated" : "Error", data.message || (data.ok ? "Disabled" : "Failed"));
            } else {
              return;
            }

          }catch(e){
            toast("Error", e?.message || "Failed");
          }finally{
            await refreshState(true);
          }
        });
      });
    });
  }

  // ---- Bulk actions ----
  const bulkBar = $("#bulkBar");
  const bulkCount = $("#bulkCount");
  const bulkEnable = $("#bulkEnable");
  const bulkDisable = $("#bulkDisable");
  const bulkTest = $("#bulkTest");
  const bulkRemove = $("#bulkRemove");
  const bulkClear = $("#bulkClear");

  function getSelectedNames(){
    const names = [];
    $$('tr[data-name]').forEach(row => {
      const cb = row.querySelector('.row-check');
      if (cb && cb.checked){
        names.push(row.getAttribute('data-name'));
      }
    });
    return names;
  }

  function updateBulkBar(){
    const names = getSelectedNames();
    const n = names.length;
    if (!bulkBar || !bulkCount) return;
    if (n === 0){
      bulkBar.classList.add("is-hidden");
      return;
    }
    bulkCount.textContent = `${n} selected`;
    // animate in
    bulkBar.classList.remove("is-hidden");
  }

  function clearBulkSelection(){
    $$('tr[data-name]').forEach(row => {
      const cb = row.querySelector('.row-check');
      if (cb) cb.checked = false;
      row.classList.remove('is-selected');
    });
    updateBulkBar();
  }

  async function postJson(url, obj){
    const res = await fetch(url, {method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(obj)});
    return await res.json();
  }

  async function bulkAction(action){
    const names = getSelectedNames();
    if (!names.length) return;
    const label = action.replace(/\b\w/g, c => c.toUpperCase());
    toast("Bulk", `${label} ${names.length} targets…`);
    try{
      const data = await postJson(`/api/bulk-${action}`, {names});
      if (data.ok && action === "enable") { names.forEach(n => markForcedStarting(n)); }
      toast(data.ok ? "Done" : "Error", data.message || (data.ok ? "Completed" : "Failed"));
    }catch(e){
      toast("Error", e?.message || "Failed");
    }finally{
      clearBulkSelection();
      await refreshState(true);
    }
  }

  function attachBulkHandlers(){
    $$('tr[data-name] .row-check').forEach(cb => {
      if (cb.dataset.bound === "1") return;
      cb.dataset.bound = "1";
      cb.addEventListener('change', () => {
        const row = cb.closest('tr');
        if (row) row.classList.toggle('is-selected', !!cb.checked);
        updateBulkBar();
      });
    });
    updateBulkBar();
  }

  bulkClear?.addEventListener('click', clearBulkSelection);
  bulkEnable?.addEventListener('click', () => bulkAction('enable'));
  bulkDisable?.addEventListener('click', () => bulkAction('disable'));
  bulkTest?.addEventListener('click', () => bulkAction('test'));
  bulkRemove?.addEventListener('click', () => { const names = getSelectedNames(); if(names.length) openConfirmRemove(names); });


// ---- Real-time-ish refresh + row blink ----
  function setStatusChip(row, t){
  const chip = row.querySelector(".status-chip");
  const text = row.querySelector(".status-text");
  if (!chip || !text) return;

  const enabled = Number(t?.enabled ?? 0) === 1;
  const lastRtt = Number(t?.last_rtt_ms ?? -1);
  const lastResp = Number(t?.last_response_epoch ?? 0);
  let st = String(t?.status || "unknown").toLowerCase();

  // Same logic as statusLabel/statusClass: treat last_status='disabled' as STARTING
  // when the target is enabled, until the first run updates it.
  if (enabled && st === "disabled") st = "starting";

  const hbFail = enabled && st === "down" && lastRtt >= 0 && lastResp > 0;

  chip.classList.remove("status-up","status-down","status-unknown","status-hb","status-starting","status-disabled");

  if (!enabled){
    chip.classList.add("status-disabled");
    text.textContent = "DISABLED";
  }else if (st === "up"){
    chip.classList.add("status-up");
    text.textContent = "OK";
  }else if (st === "starting"){
    chip.classList.add("status-starting");
    text.textContent = "STARTING..";
  }else if (hbFail){
    chip.classList.add("status-hb");
    text.textContent = "HEARTBEAT FAILED";
  }else if (st === "down"){
    chip.classList.add("status-down");
    text.textContent = "NOT RESPONDING";
  }else{
    chip.classList.add("status-unknown");
    text.textContent = st.toUpperCase();
  }

  row.setAttribute("data-status", st);
  row.setAttribute("data-enabled", enabled ? "1" : "0");
}


  function flashIfChanged(el, newText){
    if (!el) return false;
    if (el.textContent !== newText){
      el.textContent = newText;
      return true;
    }
    return false;
  }

  async function refreshState(force=false){
    try{
      const data = await apiGet("/state");
      const incoming = Array.isArray(data.targets) ? data.targets : [];
      const backendOk = (data && data.ok !== false);
      if (!backendOk && incoming.length === 0 && Array.isArray(lastTargets) && lastTargets.length > 0){
        // keep current state
        return;
      }
      lastTargets = incoming;

      // Only re-render the table if structure changed (add/remove) or if forced.
      const namesNow = new Set((incoming||[]).map(t => String(t.name||"")));
      const namesRendered = new Set($$("tr[data-name]").map(tr => String(tr.getAttribute("data-name")||"")));
      let structureChanged = (namesNow.size !== namesRendered.size);
      if (!structureChanged){
        for (const n of namesNow){ if (!namesRendered.has(n)){ structureChanged = true; break; } }
      }
      if (force || structureChanged){
        renderTargets(lastTargets);
        bindSortHeaders();
      }
      const map = new Map();
      (incoming || []).forEach(t => map.set(t.name, t));

      $$("tr[data-name]").forEach(row => {
        const name = row.getAttribute("data-name");
        const t = map.get(name);
        if (!t) return;

        setStatusChip(row, t);
        setActionVisibility(row, Number(t.enabled ?? 0) === 1);

        // Blink row for 1s when a new ping happens (keep row blink),
        // but keep the gutter icon visible a bit longer.
        const prevPing = Number(row.getAttribute("data-last-ping") || "0");
        const nextPing = Number(t.last_ping_epoch || 0);
        if (nextPing && nextPing !== prevPing){
          row.setAttribute("data-last-ping", String(nextPing));

          // 1s row blink
          row.classList.remove("flash-up","flash-down");
          row.classList.add((t.status === "up") ? "flash-up" : "flash-down");
          if (row._flashTimer) clearTimeout(row._flashTimer);
          row._flashTimer = setTimeout(() => row.classList.remove("flash-up","flash-down"), 1000);

          // 5s icon flash (independent of row class)
          const gf = row.querySelector('.gutter-flash');
          if (gf){
            gf.classList.remove('icon-up','icon-down');
            gf.classList.add((t.status === "up") ? 'icon-up' : 'icon-down');
            if (gf._iconTimer) clearTimeout(gf._iconTimer);
            gf._iconTimer = setTimeout(() => gf.classList.remove('icon-up','icon-down'), 5000);
          }
        }
        const nextResp = Number(t.last_response_epoch || 0);
        row.setAttribute("data-last-resp", String(nextResp));
        row.setAttribute("data-last-rtt", String(t.last_rtt_ms ?? -1));

        flashIfChanged(row.querySelector(".last-ping"), t.last_ping_human || "-");
        flashIfChanged(row.querySelector(".last-resp"), t.last_response_human || "-");

        const iv = row.querySelector(".interval-input");
        if (iv && force){
          iv.value = String(t.interval || 60);
          iv.setAttribute("data-interval", String(t.interval || 60));
        }
      });

      // Avoid re-rendering every poll: keep menus/checkboxes stable.
      // Filter/sort actions explicitly call renderTargets().
      attachIntervalHandlers();
      attachMenuActions();
      attachBulkHandlers();
      attachRowClickHandlers();
  attachRowClickHandlers();
    }catch(e){
      // silent
    }
  }

  // ---- Run now modal ----
  const runModal = $("#runModal");
  const btnCloseRun = $("#btnCloseRun");
  const btnRunNow = $("#btnRunNow");

  const runTitleMeta = $("#runTitleMeta");
  const runLive = $("#runLive");
  const runLiveText = $("#runLiveText");

  const mTotal = $("#mTotal");
  const mDue = $("#mDue");
  const mSkipped = $("#mSkipped");
  const mOk = $("#mOk");
  const mFail = $("#mFail");
  const mSent = $("#mSent");
  const mCurlFail = $("#mCurlFail");
  const runBar = $("#runBar");
  const runNowLine = $("#runNowLine");
  const runDoneLine = $("#runDoneLine");
  const runFeedWrap = $("#runFeedWrap");
  const runFeed = $("#runFeed");
  const btnRunDetails = $("#btnRunDetails");
  let runShowDetails = false;

  let runPoll = null;
  let runDueExpected = 0;

  function setBar(done, due){
    const pct = (!due || due <= 0) ? 0 : Math.max(0, Math.min(100, Math.round((done / due) * 100)));
    runBar.style.width = pct + "%";
  }

  function setRunInitial(){
    runShowDetails = false;
    if (runFeedWrap) runFeedWrap.style.display = "none";
    if (btnRunDetails) btnRunDetails.textContent = "Show details";
    runTitleMeta.textContent = "running…";
    runLive.style.display = "inline-flex";
    runLiveText.textContent = "Running…";

    mTotal.textContent = "-";
    mDue.textContent = "-";
    mSkipped.textContent = "-";
    mOk.textContent = "-";
    mFail.textContent = "-";
    mSent.textContent = "-";
    mCurlFail.textContent = "-";
    runNowLine.textContent = "Starting…";
    runDoneLine.textContent = "done: 0 / 0";
    setBar(0, 0);
  }

btnRunDetails?.addEventListener("click", () => {
  runShowDetails = !runShowDetails;
  if (runFeedWrap) runFeedWrap.style.display = runShowDetails ? "block" : "none";
  if (btnRunDetails) btnRunDetails.textContent = runShowDetails ? "Hide details" : "Show details";
});


  async function pollRun(){
    // Use output tail only for progress counting (no live output UI)
    let outText = "";
    let summary = null;
    let outResp = null;
    try{
      outResp = await apiGet("/api/run-output?lines=220");
      if (outResp && outResp.ok){
        outText = outResp.text || "";
        summary = outResp.summary || null;
      }
    }catch(e){ /* ignore */ }

    // Live feed (last lines)
    if (runFeed && runFeedWrap){
      const lines = (outText || "").split("\n").filter(Boolean);
      const tail = lines.slice(-12);
      if (tail.length){
        if (runShowDetails){
          runFeedWrap.style.display = "block";
          runFeed.innerHTML = tail.map(l => `<div class=\"log-line\">${escapeHtml(l)}</div>`).join("");
        }
        runNowLine.textContent = tail[tail.length-1];
      }
      if (!runShowDetails){
        runFeedWrap.style.display = "none";
      }
    }

    // Progress: count completed targets (server-side)
    const done = Number(outResp?.done ?? 0);

    // If summary exists (usually at end), prefer it
    const due = summary ? Number(summary.due || 0) : Math.max(runDueExpected || 0, done || 0);
    if (summary){
      mTotal.textContent = String(summary.total ?? "-");
      mDue.textContent = String(summary.due ?? "-");
      mSkipped.textContent = String(summary.skipped ?? "-");
      mOk.textContent = String(summary.ping_ok ?? "-");
      mFail.textContent = String(summary.ping_fail ?? "-");
      mSent.textContent = String(summary.sent ?? "-");
      mCurlFail.textContent = String(summary.curl_fail ?? "-");
    }
    setBar(done, due);
    runDoneLine.textContent = `done: ${done} / ${due}`;

    const st = await apiGet("/api/run-status");
    if (st && st.running){
      runTitleMeta.textContent = "running…";
      runLive.style.display = "inline-flex";
      runLiveText.textContent = "Running…";
      await refreshState(false);
      return;
    }

    // finished
    clearInterval(runPoll);
    runPoll = null;
    runLive.style.display = "none";

    const res = await apiGet("/api/run-result");
    runTitleMeta.textContent = new Date().toLocaleString();
    toast(res.ok ? "Run completed" : "Run failed", res.ok ? "Done" : (res.message || "Error"));
    runNowLine.textContent = res.ok ? "Completed" : "Failed";
    await refreshState(true);
  }

  btnCloseRun?.addEventListener("click", () => hide(runModal));
  runModal?.addEventListener("click", (e) => { if (e.target === runModal) hide(runModal); });

  btnRunNow?.addEventListener("click", async () => {
    btnRunNow.disabled = true;
    setRunInitial();
    show(runModal);
    // Expected due count for progress (enabled targets)
    try{
      runDueExpected = (lastTargets || []).filter(t => Number(t.enabled ?? 0) === 1 && String(t.status||"") !== "disabled").length;
      mDue.textContent = String(runDueExpected || 0);
    }catch(e){ runDueExpected = 0; }

    try{
      const data = await apiPost("/api/run-now", new FormData());
      if (!data.ok){
        toast("Run failed", data.message || "Failed to start run");
        runNowLine.textContent = "Failed";
        runLive.style.display = "none";
      } else {
        // poll frequently while running
        if (runPoll) clearInterval(runPoll);
        runPoll = setInterval(pollRun, 600);
        await pollRun();
      }
    }catch(e){
      toast("Run failed", e?.message || "Error");
      runNowLine.textContent = "Failed";
      runLive.style.display = "none";
    }finally{
      btnRunNow.disabled = false;
    }
  });



  // ---- Network scan ----
  const btnSearchNetwork = $("#btnSearchNetwork");
  const scanModal = $("#scanModal");
  const btnCloseScan = $("#btnCloseScan");
  const scanOutput = $("#scanOutput");
  const scanBar = $("#scanBar");
  const scanStatusLine = $("#scanStatusLine");
  const scanError = $("#scanError");
  const scanSubnets = $("#scanSubnets");
  const scanFoundCount = $("#scanFoundCount");
  const scanNewCount = $("#scanNewCount");
  const scanList = $("#scanList");
  const scanListEmpty = $("#scanListEmpty");
  const scanLive = $("#scanLive");
  const scanTitleMeta = $("#scanTitleMeta");
  const btnScanNow = $("#btnScanNow");
  const btnAbortScan = $("#btnAbortScan");
  const scanScope = $("#scanScope");
  const scanSpeed = $("#scanSpeed");
  const scanCustomWrap = $("#scanCustomWrap");
  const scanCustom = $("#scanCustom");

  const scanAddModal = $("#scanAddModal");
  const scanAddForm = $("#scanAddForm");
  const scanAddName = $("#scanAddName");
  const scanAddIp = $("#scanAddIp");
  const scanAddEndpoint = $("#scanAddEndpoint");
  const scanAddTitle = $("#scanAddTitle");
  const btnScanAddCancel = $("#btnScanAddCancel");

  bindSmartAssist(scanAddIp, scanAddName);

  function updateScanScopeUI(){
    const v = scanScope?.value || "local";
    if (scanCustomWrap) scanCustomWrap.style.display = (v === "local+custom") ? "block" : "none";
  }
  scanScope?.addEventListener("change", updateScanScopeUI);
  updateScanScopeUI();

  let scanPoll = null;
  let scanFound = [];
  let scanSelected = null;
  let scanAddedIps = new Set();

  function suggestName(dev){
    const host = (dev?.host || "").trim();
    if (host) return host;
    const vendor = (dev?.vendor || "").trim();
    if (vendor) return `${vendor} ${dev.ip}`;
    return String(dev?.ip || "");
  }

  function renderScanList(){
    if (!scanList || !scanListEmpty) return;
    scanList.innerHTML = "";
    if (!scanFound.length){
      scanListEmpty.style.display = "block";
      return;
    }
    scanListEmpty.style.display = "none";
    const existingIps = new Set((lastTargets||[]).map(t => String(t.ip||"")));
    const existingMacs = new Set((lastTargets||[]).map(t => String(t.mac||"").toLowerCase()).filter(Boolean));
    scanFound.forEach(dev => {
      const host = dev.host || dev.ip;
      const vendor = dev.vendor ? `<span class="muted">${escapeHtml(dev.vendor)}</span>` : "";
      const dtype = dev.type ? `<span class="badge">${escapeHtml(dev.type)}</span>` : "";
      const conf = (dev.confidence !== undefined && dev.confidence !== null) ? `<span class="conf">${dev.confidence}%</span>` : "";

      const ip = String(dev.ip||"");
      const mac = String(dev.mac||"").toLowerCase();
      const isExisting = existingIps.has(ip) || (mac && existingMacs.has(mac));
      const isAdded = scanAddedIps.has(ip);
      const statusBadge = isAdded ? `<span class="badge badge-ok">Added</span>` : (isExisting ? `<span class="badge badge-muted">Already added</span>` : "");
      const canAdd = !isExisting && !isAdded;

      const el = document.createElement("div");
      el.className = "scan-item" + (canAdd ? "" : " is-disabled");
      el.innerHTML = `
        <div class="meta">
          <div class="meta-top"><b>${escapeHtml(host)}</b>${dtype}${conf}${statusBadge}</div>
          <div class="meta-sub"><span>${escapeHtml(dev.ip)}</span>${dev.mac ? `<span class="muted">${escapeHtml(dev.mac)}</span>` : ""}${vendor}</div>
        </div>
        <button class="btn btn-primary btn-mini" type="button" ${canAdd ? "" : "disabled"}>${isAdded ? "Added" : (isExisting ? "Added" : "Add")}</button>
      `;

      const openAdd = () => {
        scanSelected = dev;
        scanAddTitle.textContent = dev.ip;
        scanAddName.value = suggestName(dev);
        scanAddIp.value = dev.ip;
        scanAddEndpoint.value = "";
        show(scanAddModal);
        scanAddEndpoint.focus();
      };

      el.addEventListener("click", (e) => {
        // Only allow opening when it makes sense.
        if (!canAdd) return;
        // Ignore button bubbling (handled below)
        if (e?.target?.closest && e.target.closest("button")) return;
        openAdd();
      });

      el.querySelector("button").addEventListener("click", () => {
        if (!canAdd) return;
        openAdd();
      });
      scanList.appendChild(el);
    });
  }

  async function refreshScan(){
    try{
      if (scanError){ scanError.style.display = "none"; scanError.textContent = ""; }
      const out = await apiGet(`/api/scan-output?lines=260`);
      const meta = out.meta || {};
      scanTitleMeta.textContent = meta.cidrs?.length ? `(${meta.cidrs.length} subnets)` : "";
      scanSubnets.textContent = meta.cidrs?.length ? String(meta.cidrs.length) : "-";
      scanOutput.textContent = out.text || "";
      scanOutput.scrollTop = scanOutput.scrollHeight;

      // Simple progress estimate: subnets started vs total
      const txt = String(out.text||"");
      const started = (txt.match(/^scan:\s+/gm) || []).length;
      const total = (meta.cidrs||[]).length || 0;
      const pct = total ? Math.min(100, Math.round((started/total)*100)) : 0;
      scanBar.style.width = `${pct}%`;
      const currentIp = meta.current_ip ? String(meta.current_ip) : "";
      const errTxt = (meta.error || "").trim();
      scanStatusLine.textContent = total ? `Scanning ${Math.min(started+1,total)} / ${total}${currentIp ? " • " + currentIp : ""}` : (errTxt || "Scanning…");
      if (errTxt && scanError){
        scanError.textContent = errTxt;
        scanError.style.display = "block";
      }

      const st = await apiGet(`/api/scan-status`);
      if (st.running){
        scanLive.style.display = "flex";
        if (btnAbortScan) btnAbortScan.style.display = "inline-flex";
        if (btnScanNow) btnScanNow.style.display = "none";
        btnSearchNetwork?.classList.add("is-running");
        return;
      }
      scanLive.style.display = "none";
      if (btnAbortScan) btnAbortScan.style.display = "none";
      if (btnScanNow) btnScanNow.style.display = "inline-flex";
      if (btnScanNow) btnScanNow.textContent = st.finished ? "Search again" : "Start search";
      btnSearchNetwork?.classList.remove("is-running");

      // finished -> get results
      const res = await apiGet(`/api/scan-result`);
      scanFound = res.found || [];
      scanFoundCount.textContent = String(scanFound.length);

      const existingIps = new Set((lastTargets||[]).map(t => String(t.ip||"")));
      const existingMacs = new Set((lastTargets||[]).map(t => String(t.mac||"").toLowerCase()).filter(Boolean));
      const newCount = (scanFound||[]).filter(d => {
        const ip = String(d?.ip||"");
        const mac = String(d?.mac||"").toLowerCase();
        return ip && !existingIps.has(ip) && !(mac && existingMacs.has(mac)) && !scanAddedIps.has(ip);
      }).length;
      scanNewCount.textContent = String(newCount);
      renderScanList();

      // Keep polling if modal is open; otherwise stop.
      if (!scanModal?.classList.contains("show")){
        if (scanPoll){ clearInterval(scanPoll); scanPoll = null; }
      }
    }catch(e){
      scanStatusLine.textContent = e?.message || "Scan failed";
      if (scanError){
        scanError.textContent = e?.message || "Scan failed";
        scanError.style.display = "block";
      }
      toast("Search network", e?.message || "Failed to fetch");
      scanLive.style.display = "none";
      if (scanPoll){ clearInterval(scanPoll); scanPoll = null; }
    }
  }

  function resetScanUi(){
    scanFound = [];
    scanAddedIps = new Set();
    scanBar.style.width = "0%";
    scanFoundCount.textContent = "-";
    scanNewCount.textContent = "-";
    scanSubnets.textContent = "-";
    scanStatusLine.textContent = "-";
    if (scanError){ scanError.style.display = "none"; scanError.textContent = ""; }
    scanListEmpty.style.display = "block";
    scanList.innerHTML = "";
  }

  async function startScan(force=false){
    const fd = new FormData();
    fd.set("scope", scanScope?.value || "local");
    fd.set("speed", scanSpeed?.value || "normal");
    fd.set("custom", (scanCustom?.value || "").trim());
    if (force) fd.set("force", "1");
    const started = await apiPost("/api/scan-start", fd);
    if (!started.ok){
      toast("Search network", started.message || "Failed to start scan");
      return false;
    }
    return true;
  }

  btnSearchNetwork?.addEventListener("click", async () => {
    show(scanModal);
    // Show current status/results and keep polling while the modal is open.
    if (scanPoll) clearInterval(scanPoll);
    scanPoll = setInterval(refreshScan, 800);
    await refreshScan();
  });

  btnAbortScan?.addEventListener("click", async () => {
    try{
      const r = await apiPost("/api/scan-cancel", new FormData());
      toast(r.ok ? "Scan" : "Scan", r.ok ? "Cancelled" : (r.message || "Failed"));
    }catch(e){ toast("Scan", "Failed"); }
  });

  btnScanNow?.addEventListener("click", async () => {
    resetScanUi();
    scanOutput.textContent = "Starting search…";
    scanLive.style.display = "flex";
    const cur = await apiGet(`/api/scan-status`);
    const ok = await startScan(!!cur.finished);
    if (!ok){
      scanLive.style.display = "none";
      return;
    }
    toast("Search network", "Search started");
    if (scanPoll) clearInterval(scanPoll);
    scanPoll = setInterval(refreshScan, 800);
    await refreshScan();
  });

  // Closing the modal should not stop the scan. We'll stop polling to save cycles,
  // but keep a "running" indicator on the button.
  btnCloseScan?.addEventListener("click", () => {
    hide(scanModal);
    if (scanPoll){ clearInterval(scanPoll); scanPoll = null; }
  });
  btnScanAddCancel?.addEventListener("click", () => hide(scanAddModal));
  scanAddForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    try{
      const fd = new FormData(scanAddForm);
      const data = await apiPost("/api/add", fd);
      if (!data.ok){
        toast("Add target", data.message || "Failed");
        return;
      }
      toast("Add target", "Added");
      hide(scanAddModal);
      if (scanSelected){
        scanAddedIps.add(String(scanSelected.ip||""));
        renderScanList();
        scanSelected = null;
      }
      await refreshState(true);
      // Update counters in the scan modal (if it is open)
      if (scanModal?.classList.contains("show")) await refreshScan();
    }catch(err){
      toast("Add target", err?.message || "Failed");
    }
  });

  // init
  // Start with the server-rendered targets to avoid a flash of empty rows
  // before the first /state poll completes.
  try{
    const seeded = window.__INITIAL_TARGETS__;
    if (Array.isArray(seeded) && seeded.length){
      lastTargets = seeded;
      renderTargets(lastTargets);
    } else {
      // If nothing was seeded, do not wipe the DOM table here.
      // We'll populate it as soon as /state returns.
    }
  }catch(e){}

  bindSortHeaders();
  // Ensure Enable/Disable visibility + row datasets are synced immediately
  refreshState(true);
  setInterval(() => refreshState(false), 2000);

  // Keyboard UX: Esc closes sidepanel/modals, Enter toggles sidepanel on focused/selected row
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape"){
      // Close Information modal first
      if (infoModal && infoModal.classList.contains("show")){
        hide(infoModal);
        e.preventDefault();
        return;
      }
      // Close the top-most open modal
      const openModal = Array.from(document.querySelectorAll(".modal.show")).pop();
      if (openModal){
        hide(openModal);
        e.preventDefault();
        return;
      }
      // Finally close menus
      closeAllMenus();
      return;
    }

    if (e.key === "Enter"){
      const tag = (e.target && e.target.tagName) ? e.target.tagName.toLowerCase() : "";
      if (tag === "input" || tag === "textarea" || tag === "select" || e.target.isContentEditable) return;

      const openModal = Array.from(document.querySelectorAll(".modal.show")).filter(m => m && m.id !== "infoModal").pop();
      if (openModal) return;

      const row = document.querySelector("tr.is-focused") || document.querySelector("tr.is-selected");
      if (!row) return;
      const name = row.getAttribute("data-name");
      if (!name) return;

      if (infoModal && infoModal.classList.contains("show") && infoTitle && infoTitle.textContent === name){
        hide(infoModal);
      } else {
        openInfo(name);
      }

      e.preventDefault();
    }
  });

})();