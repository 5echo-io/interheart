/*
 * =============================================================================
 * Copyright (c) 2026 5echo.io
 * Project: interheart
 * Purpose: WebUI client-side logic.
 * Path: /webui/static/app.js
 * Created: 2026-02-01
 * Last modified: 2026-02-02
 * =============================================================================
 */

/*
 * =============================================================================
 * Copyright (c) 2026 5echo.io
 * Project: interheart
 * Purpose: WebUI client-side logic (table rendering, modals, discovery UI, API calls).
 * Path: /opt/interheart/webui/static/app.js
 * Created: 2026-02-01
 * Last modified: 2026-02-02
 * =============================================================================
 */

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

  // ---- Client debug reporting ----
  let _clientLogLast = 0;
  // Debug logging helper for agent instrumentation
  function debugLog(location, message, data, hypothesisId){
    try{
      const logData = {location, message, data, timestamp:Date.now(), sessionId:'debug-session', runId:'run1', hypothesisId:hypothesisId||'X'};
      console.log('[DEBUG]', location, message, data);
      try{
        reportClientLog('INFO', `[DEBUG] ${location}: ${message}`, logData);
      }catch(e2){
        console.error('reportClientLog failed:', e2);
      }
    }catch(e){
      console.error('debugLog error:', e, location, message);
    }
  }

  function reportClientLog(level, message, context){
    try{
      const now = Date.now();
      // basic throttle to avoid loops when the backend is down
      // BUT: don't throttle DEBUG logs - they're important for debugging
      const isDebug = String(message || '').includes('[DEBUG]');
      if (!isDebug && now - _clientLogLast < 600) return;
      _clientLogLast = now;
      const payload = {
        level: String(level || 'INFO').toUpperCase(),
        message: String(message || ''),
        context: context || {},
        path: location.pathname,
        href: location.href,
        ua: navigator.userAgent,
        ts: new Date().toISOString(),
      };
      if (navigator.sendBeacon){
        const blob = new Blob([JSON.stringify(payload)], {type:'application/json'});
        navigator.sendBeacon('/api/client-log', blob);
        return;
      }
      fetch('/api/client-log', {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload),
      }).catch(() => {});
    }catch(e){
      // ignore
    }
  }

  window.addEventListener('error', (ev) => {
    reportClientLog('ERROR', 'window.error', {
      message: ev?.message,
      source: ev?.filename,
      lineno: ev?.lineno,
      colno: ev?.colno,
    });
  });
  window.addEventListener('unhandledrejection', (ev) => {
    reportClientLog('ERROR', 'window.unhandledrejection', {
      reason: String(ev?.reason?.message || ev?.reason || ''),
    });
  });

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

  async function apiPostJson(url, obj){
    const payload = obj || {};
    try{
      const res = await fetch(url, {
        method: 'POST',
        headers: {'Content-Type':'application/json'},
        body: JSON.stringify(payload),
      });
      const ct = (res.headers.get('content-type') || '').toLowerCase();
      if (ct.includes('application/json')){
        const data = await res.json();
        if (!res.ok && data && data.ok !== true){
          data.ok = false;
          data.message = data.message || res.statusText || 'Request failed';
        }
        return data;
      }
      const txt = await res.text();
      return { ok: res.ok, message: txt ? String(txt).slice(0,240) : (res.statusText || 'Error') };
    }catch(e){
      reportClientLog('ERROR', 'apiPostJson exception', { url, error: String(e?.message || e) });
      return { ok:false, message: e?.message || 'Failed to fetch' };
    }
  }
  async function apiGet(url){
    try{
      const res = await fetch(url, {cache:"no-store"});
      const ct = (res.headers.get("content-type") || "").toLowerCase();
      if (ct.includes("application/json")){
        const data = await res.json();
        if (!res.ok){
          reportClientLog('WARN', 'apiGet non-ok response', { url, status: res.status, body: data });
          // Bubble up a readable error (this avoids "Failed to fetch" with no context)
          throw new Error(data?.message || res.statusText || "Request failed");
        }
        return data;
      }
      const txt = await res.text();
      if (!res.ok){
        reportClientLog('WARN', 'apiGet non-ok text response', { url, status: res.status, text: String(txt).slice(0,240) });
        throw new Error(res.statusText || "Request failed");
      }
      // Non-JSON but OK (rare) -> return wrapper
      return { ok: true, text: txt };
    }catch(e){
      reportClientLog('ERROR', 'apiGet exception', { url, error: String(e?.message || e) });
      throw e;
    }
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

  // ---- Changelog modal ----
  const changelogModal = $("#changelogModal");
  const openChangelog = $("#openChangelogFooter");
  const closeChangelog = $("#btnCloseChangelog");
  const changelogBox = $("#changelogBox");
  const changelogMeta = $("#changelogMeta");
  const openFullChangelog = $("#btnOpenFullChangelog");

  async function loadChangelog(){
    try{
      const data = await apiGet("/api/changelog");
      if (openFullChangelog && data.full_url){
        openFullChangelog.setAttribute("href", data.full_url);
      }
      const parts = [];
      if (data.current){
        parts.push(data.current);
      }
      if (data.unreleased){
        parts.push(data.unreleased);
      }
      const txt = parts.join("\n\n").trim() || "No changelog data available.";
      if (changelogBox) changelogBox.textContent = txt;
      if (changelogMeta){
        const v = data.current_version || "";
        changelogMeta.textContent = v ? `Current release: ${v}` : "Changelog";
      }
    }catch(e){
      if (changelogBox) changelogBox.textContent = "Failed to fetch changelog.";
      if (changelogMeta) changelogMeta.textContent = "error";
    }
  }

  openChangelog?.addEventListener("click", async (e) => {
    try{ e?.preventDefault?.(); }catch(_){ }
    show(changelogModal);
    await loadChangelog();
  });
  closeChangelog?.addEventListener("click", () => hide(changelogModal));
  changelogModal?.addEventListener("click", (e) => { if (e.target === changelogModal) hide(changelogModal); });

  // ---- Filter targets ----
  const filterInput = $("#filterInput");

  // ---- Sorting state (default: IP asc) ----
  // IMPORTANT: Don't cache #targetsTable here.
  // The script can load before the table exists; caching would keep it null,
  // and sorting would silently fail.
  // NOTE:
  // We default the *rendered* list to IP asc, but we don't want the first
  // user click on the IP header to immediately toggle to desc.
  // So we track a "first IP click" and keep asc on that click.
  let sortKey = "ip";
  let sortDir = "asc"; // asc|desc
  let ipFirstClickArmed = true;

  // If the backend state fetch hasn't populated lastTargets yet (or fails),
  // we still want sorting to work using the server-rendered table.
  function hydrateTargetsFromDOM(){
    const rows = $$("#targetsTable tbody tr[data-name]");
    return rows.map(row => {
      const name = String(row.getAttribute("data-name") || "").trim();
      const ip = String(row.getAttribute("data-ip") || "").trim();
      const status = String(row.getAttribute("data-status") || "").trim();
      const enabled = Number(row.getAttribute("data-enabled") || row.dataset.enabled || 0);
      const last_ping_epoch = Number(row.getAttribute("data-last-ping") || row.dataset.lastPing || 0);
      const last_response_epoch = Number(row.getAttribute("data-last-resp") || row.dataset.lastResp || 0);
      const intervalInput = row.querySelector(".interval-input");
      const interval = Number(intervalInput?.value || intervalInput?.getAttribute("data-interval") || 0);
      return {
        name,
        ip,
        status,
        enabled,
        interval,
        last_ping_epoch,
        last_response_epoch,
        // keep sortTargets happy
        last_ping_human: row.querySelector(".last-ping")?.textContent || "-",
        last_response_human: row.querySelector(".last-resp")?.textContent || "-",
      };
    }).filter(t => t.name || t.ip);
  }

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
    const tableEl = $("#targetsTable");
    if (!tableEl) return;
    $$("th.sortable", tableEl).forEach(th => {
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
    const tableEl = $("#targetsTable");
    if (!tableEl) return;
    // Use event delegation so sorting keeps working even if headers are
    // re-rendered or inner spans are clicked.
    if (tableEl.dataset.sortBound !== "1"){
      tableEl.dataset.sortBound = "1";
      tableEl.addEventListener("click", (e) => {
        const th = e.target?.closest?.("th.sortable");
        if (!th) return;

        // If state hasn't loaded yet, sort the server-rendered rows instead
        // of wiping the table by rendering an empty lastTargets array.
        if (!Array.isArray(lastTargets) || lastTargets.length === 0){
          lastTargets = hydrateTargetsFromDOM();
        }

        const key = th.dataset.sort || "name";
        if (sortKey === key){
          // Special rule: IP should default to ascending on first click.
          // Since we already default-sort by IP asc, the first click should NOT flip it.
          if (key === 'ip' && sortDir === 'asc' && ipFirstClickArmed){
            ipFirstClickArmed = false;
          } else {
            sortDir = (sortDir === "asc") ? "desc" : "asc";
            if (key === 'ip') ipFirstClickArmed = false;
          }
        } else {
          sortKey = key;
          sortDir = "asc";
          if (key === 'ip') ipFirstClickArmed = false;
        }
        updateSortIndicators();
        renderTargets(lastTargets);
      });
    }
    updateSortIndicators();
  }

  // Ultra-reliable sort trigger for header clicks.
  // Some environments/extensions can interfere with delegated click handlers.
  // The template also calls this directly via onclick on sortable headers.
  window.__IH_SORT = function(key){
    // If state hasn't loaded yet, sort the server-rendered rows instead
    // of wiping the table by rendering an empty lastTargets array.
    if (!Array.isArray(lastTargets) || lastTargets.length === 0){
      lastTargets = hydrateTargetsFromDOM();
    }

    const k = String(key || "name");
    if (sortKey === k){
      // Special rule: IP should default to ascending on first click.
      if (k === 'ip' && sortDir === 'asc' && ipFirstClickArmed){
        ipFirstClickArmed = false;
      } else {
        sortDir = (sortDir === "asc") ? "desc" : "asc";
        if (k === 'ip') ipFirstClickArmed = false;
      }
    } else {
      sortKey = k;
      sortDir = "asc";
      if (k === 'ip') ipFirstClickArmed = false;
    }
    updateSortIndicators();
    renderTargets(lastTargets);
  };

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

  // Subtle clear buttons for search/filter inputs
  document.querySelectorAll('[data-clear-for]').forEach(btn => {
    btn.addEventListener('click', () => {
      const id = btn.getAttribute('data-clear-for');
      if (!id) return;
      const inp = document.getElementById(id);
      if (!inp) return;
      inp.value = '';
      inp.dispatchEvent(new Event('input', { bubbles: true }));
      try{ toggleClearButtons(); }catch(_){ }
      inp.focus();
    });
  });
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
  const copyEndpointIcon = $("#copyEndpointIcon");
  const copyIpIcon = $("#copyIpIcon");

  const u24 = $("#u24");
  const u7 = $("#u7");
  const u30 = $("#u30");
  const u90 = $("#u90");
  const u24t = $("#u24t");
  const u7t = $("#u7t");
  const u30t = $("#u30t");
  const u90t = $("#u90t");

  
  async function copyText(text, label){
    const value = String(text || "").trim();
    if (!value || value === "-") return;
    try{
      await navigator.clipboard.writeText(value);
      toast("Copied", `${label} copied`);
    }catch(e){
      // fallback for older browsers
      const ta = document.createElement("textarea");
      ta.value = value;
      ta.style.position = "fixed";
      ta.style.left = "-9999px";
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      toast("Copied", `${label} copied`);
    }
  }

  function bindCopyable(el, label){
    if (!el) return;
    if (el.dataset.boundCopy === "1") return;
    el.dataset.boundCopy = "1";
    el.addEventListener("click", () => copyText(el.textContent, label));
    el.addEventListener("keydown", (e) => {
      if (e.key === "Enter" || e.key === " "){
        e.preventDefault();
        copyText(el.textContent, label);
      }
    });
  }

  bindCopyable(infoEndpoint, "Endpoint URL");
  bindCopyable(infoIp, "IP address");
  // Icons are just hints, but let them work too
  copyEndpointIcon?.addEventListener("click", (e) => { e.stopPropagation(); copyText(infoEndpoint?.textContent, "Endpoint URL"); });
  copyIpIcon?.addEventListener("click", (e) => { e.stopPropagation(); copyText(infoIp?.textContent, "IP address"); });

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

function renderSnapshotsInner(snaps){
  const arr = Array.isArray(snaps) ? snaps : [];
  return arr.slice(0,3).map(s => {
    const cls = (s && s.state) ? String(s.state) : "unknown";
    const title = (s && s.label) ? String(s.label) : cls;
    return `<span class="snap-dot ${cls}" title="${title}"></span>`;
  }).join("");
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
      // Minimal inline SVG icons (same style as the rest of the UI)
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
                <span class="status-flex">
                  <span class="status-text">${statusLabel(t.name, t.status, t.enabled, t.last_rtt_ms, t.last_response_epoch)}</span>
                  <span class="snapshots">${renderSnapshotsInner(t.snapshots)}</span>
                </span>
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
                  <button class="menu-item" data-action="test" type="button"><span class="mi-ic" aria-hidden="true">${ic.test}</span><span>Test</span></button>
                  <div class="menu-sep"></div>
                  <button class="menu-item" data-action="enable" type="button" style="display:${enabled ? 'none' : 'flex'}"><span class="mi-ic" aria-hidden="true">${ic.enable}</span><span>Enable</span></button>
                  <button class="menu-item" data-action="disable" type="button" style="display:${enabled ? 'flex' : 'none'}"><span class="mi-ic" aria-hidden="true">${ic.disable}</span><span>Disable</span></button>
                  <div class="menu-sep"></div>
                  <button class="menu-item" data-action="edit" type="button"><span class="mi-ic" aria-hidden="true">${ic.edit}</span><span>Edit</span></button>
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

  async function refreshTargets(){
    return await refreshState(true);
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
  // Details feed removed (it was unreliable and confusing)

  let runPoll = null;
  let runDueExpected = 0;
  let runFinishNotified = false;

  function setBar(done, due){
    const pct = (!due || due <= 0) ? 0 : Math.max(0, Math.min(100, Math.round((done / due) * 100)));
    runBar.style.width = pct + "%";
  }

  function setRunInitial(){
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

    // Update the top "what's happening" line from the output tail
    try{
      const lines = (outText || "").split("\n").filter(Boolean);
      const tail = lines.slice(-1);
      if (tail.length && runNowLine){
        runNowLine.textContent = tail[0];
      }
    }catch(_){ /* ignore */ }

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
    if (runFinishNotified) return;
    runFinishNotified = true;
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
    runFinishNotified = false;
    // Expected due count for progress (enabled targets).
    // NOTE: do not populate the "Checked" metric up-front; it should reflect actual work.
    try{
      runDueExpected = (lastTargets || []).filter(t => Number(t.enabled ?? 0) === 1 && String(t.status||"") !== "disabled").length;
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



  

  // ---- Network discovery (modal, nmap SSE) ----
  const discoverBtn = $("#btnDiscover");
  const discoverModal = $("#discoverModal");
  const btnCloseDiscover = $("#btnCloseDiscover");
  const btnDiscoverStart = $("#btnDiscoverStart");
  const btnDiscoverCancel = $("#btnDiscoverCancel");
  const btnDiscoverResume = $("#btnDiscoverResume");
  const btnDiscoverReset = $("#btnDiscoverReset");
  const btnDiscoverDebug = $("#btnDiscoverDebug");
  const discoverDebugCard = $("#discoverDebugCard");
  const discoverDebugOut = $("#discoverDebugOut");
  const btnDiscoverDebugClose = $("#btnDiscoverDebugClose");
  const btnDiscoverDebugCopy = $("#btnDiscoverDebugCopy");
  const discoverIface = $("#discoverIface");
  const discoverScope = $("#discoverScope");
  const discoverCustom = $("#discoverCustom");
  const discoverOnlyNew = $("#discoverOnlyNew");
  const discoverFilter = $("#discoverFilter");
  const discoverStopAfterToggle = $("#discoverStopAfterToggle");
  const discoverStopAfterCount = $("#discoverStopAfterCount");
  const discoverStopAfterWrap = $("#discoverStopAfterWrap");
  const discoverPercent = $("#discoverPercent");

  const discoverList = $("#discoverList");
  const discoverListEmpty = $("#discoverListEmpty");
  const discoverFound = $("#discoverFound");
  const discoverSubnets = $("#discoverSubnets");
  const discoverBar = $("#discoverBar");
  const discoverProgressBar = $("#discoverProgressBar");
  const discoverStatus = $("#discoverStatus");
  const discoverScanning = $("#discoverScanning");
  const discoverProgressWrap = $("#discoverProgressWrap");
  const discoverError = $("#discoverError");
  const discoverCountHint = $("#discoverCountHint");


  const discoverAddCard = $("#discoverAddCard");
  const discoverAddForm = $("#discoverAddForm");
  const discoverAddName = $("#discoverAddName");
  const discoverAddIp = $("#discoverAddIp");
  const discoverAddEndpoint = $("#discoverAddEndpoint");
  const discoverAddHint = $("#discoverAddHint");
  const btnDiscoverAddKeep = $("#btnDiscoverAddKeep");
  const btnDiscoverAddCancel = $("#btnDiscoverAddCancel");

  const discoverAddModal = $("#discoverAddModal");
  const discoverAddModalForm = $("#discoverAddModalForm");
  const discoverAddModalName = $("#discoverAddModalName");
  const discoverAddModalIp = $("#discoverAddModalIp");
  const discoverAddModalEndpoint = $("#discoverAddModalEndpoint");
  const discoverAddModalInterval = $("#discoverAddModalInterval");
  const btnDiscoverAddModalSubmit = $("#btnDiscoverAddModalSubmit");
  const btnDiscoverAddModalCancel = $("#btnDiscoverAddModalCancel");
  const btnCloseDiscoverAdd = $("#btnCloseDiscoverAdd");

  let discoverES = null;
  let discoverDevices = [];
  let discoverDeviceMap = new Map(); // key: ip
  let discoverSelected = null;
  let discoverRenderTimer = null;
  let discoverStartInFlight = false;
  let discoverGotSSE = false;
  let discoverLastEventId = 0;
  let discoverUiTick = null;
  let discoverUiDirty = false;
  let discoverLocalRunning = false;
  let discoverLocalPaused = false;
  let discoverPauseRetries = 0;
  let discoverPauseRetryTimer = null;
  let discoverResultsLastTs = 0;
  let discoverPauseGraceUntil = 0;
  let discoverResumeGraceUntil = 0;

  // Lightweight debug logger for Discovery.
  // Keeps last ~200 entries and renders them into the debug box.
  let discoverDebugLines = [];
  function discoverDbg(line, obj){
    try{
      const ts = new Date().toISOString().replace('T',' ').replace('Z','');
      let s = `[${ts}] ${String(line||'')}`;
      if (obj !== undefined){
        try{ s += "\n" + JSON.stringify(obj, null, 2); }catch(_){ }
      }
      discoverDebugLines.push(s);
      if (discoverDebugLines.length > 200) discoverDebugLines = discoverDebugLines.slice(-200);
      if (discoverDebugOut) discoverDebugOut.textContent = discoverDebugLines.length ? discoverDebugLines.join("\n\n") : '(no debug output yet)';
    }catch(_){ }
  }

  function openDiscoverDebug(){
    if (discoverDebugCard) discoverDebugCard.style.display = 'block';
  }

  function closeDiscoverDebug(){
    if (discoverDebugCard) discoverDebugCard.style.display = 'none';
  }

  function setDiscoverRunning(isRunning){
    if (discoverBar) {
      if (isRunning) discoverBar.classList.add('running');
      else discoverBar.classList.remove('running');
    }
    if (discoverProgressBar) {
      if (isRunning) discoverProgressBar.classList.add('is-running');
      else discoverProgressBar.classList.remove('is-running');
    }
  }


  async function resetDiscoveryBackend(){
    try{
      await fetch('/api/discover-reset', {method:'POST'});
    }catch(e){
      // best effort
      console.warn('discover reset failed', e);
    }
  }

  function scheduleDiscoverRender(){
    // Rate-limit UI updates to keep the server/UI smooth during large scans.
    if (discoverRenderTimer) return;
    discoverRenderTimer = setTimeout(() => {
      discoverRenderTimer = null;
      renderDiscoverList();

    }, 250);
  }

  async function openDiscover(){
    if (!discoverModal) return;
    // Load interface list on open
    try{ await loadDiscoverIfaces(); }catch(_){ }
    show(discoverModal);
    // Default: show only new devices
    try{ if (discoverOnlyNew) discoverOnlyNew.checked = true; }catch(_){ }

    // Sync UI with backend state, but do NOT attach/poll unless a scan is actually running.
    // This prevents the modal from looking like 'Discovery is active' when it is not.
    try{
      const st = await apiGet('/api/discover-status');
      // Update counters even when idle
      if (discoverSubnets && st && st.cidrs != null) discoverSubnets.textContent = String(st.cidrs);
      if (discoverFound && st && st.found != null) discoverFound.textContent = String(st.found);
      if (discoverStatus) discoverStatus.textContent = st.message || st.status || 'Idle';
      if (discoverScanning) discoverScanning.textContent = st.scanning || st.cidr || '-';

      const running = st && (st.status === 'running' || st.status === 'starting' || st.status === 'cancelling');
      if (running){
        connectDiscoveryStream();
        if (!discoverFallbackPoll){
          discoverFallbackPoll = setInterval(pollDiscoveryFallback, 1200);
        }
        // kick once
        pollDiscoveryFallback();
      }else{
        // Ensure we are not polling/streaming when idle
        try{ discoverES && discoverES.close && discoverES.close(); }catch(_){ }
        discoverES = null;
        if (discoverFallbackPoll){ clearInterval(discoverFallbackPoll); discoverFallbackPoll = null; }
      }
    }catch(_){ }
  }

  async function loadDiscoverIfaces(){
    if (!discoverIface) return;
    let res = null;
    try{
      res = await apiGet('/api/netifs');
    }catch(e){
      res = null;
    }

    const keep = String(discoverIface.value || 'auto');
    const items = Array.isArray(res?.interfaces) ? res.interfaces : [];
    const opts = [];
    opts.push({ value: 'auto', label: 'Interface: Auto' });
    items.forEach(it => {
      const name = String(it.name || '').trim();
      if (!name) return;
      const meta = String(it.meta || '').trim();
      const label = meta ? `${name} • ${meta}` : name;
      opts.push({ value: name, label });
    });

    discoverIface.innerHTML = opts.map(o => `<option value="${escapeHtml(o.value)}">${escapeHtml(o.label)}</option>`).join('');
    // restore selection if possible
    const exists = opts.some(o => o.value === keep);
    discoverIface.value = exists ? keep : 'auto';
  }
  function closeDiscover(){
    if (!discoverModal) return;
    hide(discoverModal);
  }

  discoverBtn?.addEventListener('click', openDiscover);
  btnCloseDiscover?.addEventListener('click', closeDiscover);
  discoverModal?.addEventListener('click', (e) => { if (e.target === discoverModal) closeDiscover(); });
  // "All results" button removed (the toggle is sufficient).

  function updateDiscoverScopeUI(){
    const v = String(discoverScope?.value || 'auto');
    if (discoverCustom){
      discoverCustom.style.display = (v === 'custom') ? 'inline-flex' : 'none';
    }
  }

  discoverScope?.addEventListener('change', updateDiscoverScopeUI);
  updateDiscoverScopeUI();

  function updateDiscoverStopAfterUI(){
    if (!discoverStopAfterToggle || !discoverStopAfterCount) return;
    const on = !!discoverStopAfterToggle.checked;

    // Keep layout stable (no line shifts) – reserve the space and just fade/hide the input.
    if (discoverStopAfterWrap){
      discoverStopAfterWrap.classList.toggle('is-off', !on);
    }
    discoverStopAfterCount.disabled = !on;
    discoverStopAfterCount.style.visibility = on ? 'visible' : 'hidden';
    discoverStopAfterCount.style.pointerEvents = on ? 'auto' : 'none';
  }
  discoverStopAfterToggle?.addEventListener('change', updateDiscoverStopAfterUI);
  updateDiscoverStopAfterUI();

  function suggestEndpoint(ip){
    if (!ip) return '';
    return `http://${ip}`;
  }

  function suggestName(dev){
    if (!dev) return '';
    const lbl = computeDeviceLabel(dev);
    // Prefer hostname, then IP
    return lbl.host || lbl.ip || '';
  }

  function computeDeviceLabel(dev){
    const ip = dev.ip || '';
    const host = dev.host || '';
    const vendor = dev.vendor || '';
    const mac = dev.mac || '';
    const parts = [];
    if (host) parts.push(host);
    if (vendor) parts.push(vendor);
    if (mac) parts.push(mac);
    return { ip, host, vendor, mac, meta: parts.join(' • ') };
  }

  function matchesFilter(dev, q){
    if (!q) return true;
    q = q.toLowerCase();
    const l = computeDeviceLabel(dev);
    return (l.ip||'').toLowerCase().includes(q) || (l.host||'').toLowerCase().includes(q) || (l.vendor||'').toLowerCase().includes(q) || (l.mac||'').toLowerCase().includes(q);
  }

  function renderDiscoverList(){
    if (!discoverList || !discoverListEmpty) return;
    const q = (discoverFilter?.value || '').trim();
    const onlyNew = !!discoverOnlyNew?.checked;

    // Use lastTargets (kept in sync with /state) to avoid ReferenceError in Discovery.
    const existingIps = new Set((lastTargets||[]).map(t => String(t.ip||'')).filter(Boolean));
    const targetMapByIp = new Map();
    (lastTargets||[]).forEach(t => {
      const ip = String(t.ip||'').trim();
      if (ip) targetMapByIp.set(ip, t);
    });

    discoverList.innerHTML = '';
    let shown = 0;

    // Always render a deduped view (keyed by IP)
    const list = Array.from(discoverDeviceMap.values());
    if (discoverFound) discoverFound.textContent = String(discoverDeviceMap.size);

    list.forEach(dev => {
      const ip = String(dev.ip||'');
      if (!ip) return;
      const already = !!dev.already_added || existingIps.has(ip);
      const addedNow = !!dev.added_now;
      if (onlyNew && (already || addedNow)) return;
      if (!matchesFilter(dev, q)) return;

      shown += 1;
      const el = document.createElement('div');
      el.className = 'scan-item' + (addedNow ? ' is-added' : '') + (already ? ' is-disabled' : '');
      el.dataset.ip = ip;

      const lbl = computeDeviceLabel(dev);
      const chipTxt = addedNow ? 'Added now' : (already ? 'Already added' : 'New');
      const chipCls = addedNow ? 'chip chip--muted' : (already ? 'chip' : 'chip chip--ok');
      
      // Get target name if already added
      const existingTarget = targetMapByIp.get(ip);
      const targetName = existingTarget ? String(existingTarget.name||'') : '';
      const displayName = targetName ? `${targetName} (${lbl.host || ip})` : (lbl.host || ip);
      const displayMeta = targetName ? `${escapeHtml(ip)}${lbl.meta ? ' • ' + escapeHtml(lbl.meta) : ''}` : `${escapeHtml(ip)}${lbl.meta ? ' • ' + escapeHtml(lbl.meta) : ''}`;

      el.innerHTML = `
        <div class="scan-item-left">
          <b>${escapeHtml(displayName)}</b>
          <div class="hint">${displayMeta}</div>
        </div>
        <div class="scan-item-right">
          <span class="${chipCls}">${chipTxt}</span>
        </div>
      `;

      discoverList.appendChild(el);
    });

    discoverListEmpty.style.display = shown ? 'none' : 'block';
    if (discoverCountHint) discoverCountHint.textContent = `${shown} shown`;
  }

  function isAlreadyAddedDevice(dev){
    if (!dev) return false;
    const ip = String(dev.ip||'').trim();
    if (!ip) return false;
    const existingIps = new Set((lastTargets||[]).map(t => String(t.ip||'')).filter(Boolean));
    return !!dev.already_added || existingIps.has(ip);
  }

  // Set up delegated click handler for scan items (only once)
  if (discoverList && !discoverList.dataset.bound){
    discoverList.dataset.bound = '1';
    discoverList.addEventListener('click', (e) => {
      // #region agent log
      console.log('[DEBUG] click handler called', e.target);
      debugLog('app.js:1933', 'click event on discoverList', {targetTag:e.target?.tagName,targetClass:e.target?.className,targetId:e.target?.id,discoverListExists:!!discoverList}, 'E');
      // #endregion
      const item = e.target?.closest?.('.scan-item');
      // #region agent log
      console.log('[DEBUG] closest scan-item:', item);
      debugLog('app.js:1937', 'scan-item closest check', {itemFound:!!item,itemIp:item?.dataset?.ip,itemClass:item?.className}, 'E');
      // #endregion
      if (!item) {
        // #region agent log
        debugLog('app.js:1941', 'no item found - returning early', {}, 'E');
        // #endregion
        return;
      }
      e.stopPropagation();
      e.preventDefault();
      const ip = String(item.dataset.ip || '').trim();        
      // #region agent log
      debugLog('app.js:1929', 'extracted IP from item', {ip,ipLength:ip.length}, 'E');
      // #endregion
      if (!ip) return;
      const dev = discoverDeviceMap.get(ip);
      // #region agent log
      debugLog('app.js:1932', 'device lookup from map', {ip,devFound:!!dev,devIp:dev?.ip,mapSize:discoverDeviceMap.size}, 'E');
      // #endregion
      if (!dev) return;
      const alreadyAdded = isAlreadyAddedDevice(dev);
      // #region agent log
      debugLog('app.js:1935', 'already added check', {ip,alreadyAdded}, 'E');
      // #endregion
      if (alreadyAdded){
        toast('Network discovery', 'Already added');
        return;
      }
      // #region agent log
      debugLog('app.js:1940', 'calling openDiscoverAddModal', {ip,devIp:dev?.ip}, 'E');
      // #endregion
      openDiscoverAddModal(dev);
    });
  }

  function toggleClearButtons(){
    document.querySelectorAll('.btn-clear[data-clear-for]').forEach(btn => {
      const id = btn.getAttribute('data-clear-for');
      const inp = id ? document.getElementById(id) : null;
      const has = !!(inp && String(inp.value||'').length);
      btn.classList.toggle('is-hidden', !has);
    });
  }

  discoverFilter?.addEventListener('input', () => { toggleClearButtons(); scheduleDiscoverRender(); });
  discoverOnlyNew?.addEventListener('change', () => scheduleDiscoverRender());
  discoverScope?.addEventListener('change', () => {
    const v = discoverScope.value || 'auto';
    if (discoverCustom) discoverCustom.style.display = (v === 'custom') ? 'inline-flex' : 'none';
  });

  function resetDiscoverUI(){
    discoverDevices = [];
    discoverDeviceMap = new Map();
    discoverSelected = null;
    discoverLocalRunning = false;
    discoverLocalPaused = false;
    discoverPauseGraceUntil = 0;
    discoverResumeGraceUntil = 0;
    discoverPauseRetries = 0;
    discoverResultsLastTs = 0;
    discoverGotSSE = false;
    discoverLastEventId = 0;
    try{ if (discoverES){ discoverES.close(); discoverES = null; } }catch(_){ }
    try{ if (discoverFallbackPoll){ clearInterval(discoverFallbackPoll); discoverFallbackPoll = null; } }catch(_){ }
    if (discoverPauseRetryTimer){ clearTimeout(discoverPauseRetryTimer); discoverPauseRetryTimer = null; }
    if (discoverAddCard) discoverAddCard.style.display = 'none';
    if (discoverError){ discoverError.style.display='none'; discoverError.textContent=''; }
    if (discoverBar) discoverBar.style.width = '0%';
    if (discoverStatus) discoverStatus.textContent = 'Idle';
    if (discoverScanning) discoverScanning.textContent = '-';
    if (discoverSubnets) discoverSubnets.textContent = '-';
    if (discoverFound) discoverFound.textContent = '0';
    try{ if (discoverOnlyNew) discoverOnlyNew.checked = true; }catch(_){ }
    if (btnDiscoverCancel) btnDiscoverCancel.style.display = 'none';
    if (btnDiscoverResume) btnDiscoverResume.style.display = 'none';
    if (btnDiscoverStart) btnDiscoverStart.style.display = 'inline-flex';
    if (btnDiscoverReset) btnDiscoverReset.style.display = 'none';
    if (discoverProgressWrap){
      discoverProgressWrap.style.opacity = '0';
      discoverProgressWrap.style.display = 'none';
    }
    renderDiscoverList();
  }

  async function startDiscovery(){
    try{
      if (discoverStartInFlight) { discoverDbg('Start ignored (already in flight)'); return; }
      discoverStartInFlight = true;
      resetDiscoverUI();
      discoverLocalRunning = true;
      discoverLocalPaused = false;
      discoverDbg('Start clicked', {
        iface: discoverIface?.value || 'auto',
        scope: discoverScope?.value || 'auto',
        profile: 'safe'
      });
      if (discoverStatus) discoverStatus.textContent = 'Starting…';
      if (discoverScanning) discoverScanning.textContent = '-';
      if (btnDiscoverStart) btnDiscoverStart.disabled = true;
      if (discoverProgressWrap){
        discoverProgressWrap.style.display = 'block';
        discoverProgressWrap.style.opacity = '1';
      }
      setDiscoverRunning(true);

    const scope = (discoverScope?.value || 'auto');
    const custom = (discoverCustom?.value || '').trim();
    const payload = {
      scope,
      custom,
      iface: discoverIface?.value || 'auto',
      profile: 'safe',
      // Keep server load down by default.
      cap: 256,
      stop_after: (discoverStopAfterToggle?.checked ? Number(discoverStopAfterCount?.value || 0) : 0),
    };

      let r = null;
      try{
        discoverDbg('POST /api/discover-start', payload);
        r = await apiPostJson('/api/discover-start', payload);
      }catch(e){
        r = { ok:false, message: e?.message || 'Failed to fetch' };
      }
      discoverDbg('Start response', r);

      if (!r || !r.ok){
        const msg = (r && r.message) ? String(r.message) : 'Failed to start';
        // If a discovery worker is already running, treat this as "running" and attach to progress.
        if (msg.toLowerCase().includes('already running')){
          if (discoverStatus) discoverStatus.textContent = 'Running…';
          if (discoverError){ discoverError.style.display='none'; discoverError.textContent=''; }
          if (btnDiscoverStart){ btnDiscoverStart.style.display='none'; btnDiscoverStart.disabled=false; }
          if (btnDiscoverCancel) btnDiscoverCancel.style.display='inline-flex';
          connectDiscoveryStream();
          if (!discoverFallbackPoll){
            discoverFallbackPoll = setInterval(pollDiscoveryFallback, 1200);
            pollDiscoveryFallback();
          }
          discoverStartInFlight = false;
          return;
        }
        if (discoverError){ discoverError.textContent = msg; discoverError.style.display='block'; }
        if (discoverStatus) discoverStatus.textContent = 'Error';
        if (btnDiscoverStart) btnDiscoverStart.disabled = false;
        discoverLocalRunning = false;
        // auto open debug box so the user can copy logs
        openDiscoverDebug();
        discoverStartInFlight = false;
        return;
      }

    if (discoverStatus) discoverStatus.textContent = 'Discovery started';
    if (btnDiscoverStart) btnDiscoverStart.style.display='none';
    if (btnDiscoverCancel) btnDiscoverCancel.style.display='inline-flex';

      connectDiscoveryStream();
      // Start fallback polling immediately (some proxies "hang" SSE without firing error).
      if (!discoverFallbackPoll){
        discoverFallbackPoll = setInterval(pollDiscoveryFallback, 1200);
        pollDiscoveryFallback();
      }
      discoverStartInFlight = false;
    }catch(err){
      discoverStartInFlight = false;
      discoverLocalRunning = false;
      // If anything throws before we update the UI, it can look like "Idle".
      try{
        discoverDbg('JS exception in startDiscovery', { message: String(err?.message || err), stack: String(err?.stack||'') });
        if (discoverError){ discoverError.textContent = 'Discovery failed (JS error). Use Debug to collect details.'; discoverError.style.display='block'; }
        if (discoverStatus) discoverStatus.textContent = 'Error';
        if (btnDiscoverStart) btnDiscoverStart.disabled = false;
        openDiscoverDebug();
      }catch(_){ }
    }
  }

  // Expose a stable global hook as a safety net.
  // This avoids situations where a browser/extension interferes with event binding.
  window.__ihStartDiscovery = startDiscovery;

  function applyPausedDiscoveryUI(){
    // discoverState was removed - UI state is managed via discoverLocalRunning/discoverLocalPaused
    discoverLocalRunning = false;
    discoverLocalPaused = true;
    discoverPauseRetries = 0;
    discoverPauseGraceUntil = Date.now() + 8000;
    if (btnDiscoverCancel) btnDiscoverCancel.style.display='none';
    if (btnDiscoverResume) btnDiscoverResume.style.display='inline-flex';
    if (btnDiscoverStart) btnDiscoverStart.style.display='none';
    if (btnDiscoverReset) btnDiscoverReset.style.display='inline-flex';
    if (discoverStatus) discoverStatus.textContent = 'Paused';
    if (discoverScanning) discoverScanning.textContent = '-';
    setDiscoverRunning(false);
    scheduleDiscoverRender();
  }

  function applyRunningDiscoveryUI(){
    // discoverState was removed - UI state is managed via discoverLocalRunning/discoverLocalPaused
    discoverLocalRunning = true;
    discoverLocalPaused = false;
    discoverPauseGraceUntil = 0;
    discoverResumeGraceUntil = Date.now() + 8000;
    if (btnDiscoverResume) btnDiscoverResume.style.display='none';
    if (btnDiscoverCancel) btnDiscoverCancel.style.display='inline-flex';
    if (btnDiscoverStart) btnDiscoverStart.style.display='none';
    if (btnDiscoverReset) btnDiscoverReset.style.display='none'; // Hide reset when running/resuming
    if (discoverStatus) discoverStatus.textContent = 'Running…';
    setDiscoverRunning(true);
    scheduleDiscoverRender();
  }

  async function pauseDiscovery(){
    // #region agent log
    debugLog('app.js:2149', 'pauseDiscovery START', {discoverLocalRunning,discoverLocalPaused,discoverPauseRetries}, 'A');
    // #endregion
    try{
      // Optimistic UI: show paused immediately
      try{
        applyPausedDiscoveryUI();
        // #region agent log
        debugLog('app.js:2155', 'applyPausedDiscoveryUI called', {}, 'A');
        // #endregion
      }catch(e_ui){
        // #region agent log
        console.error('applyPausedDiscoveryUI exception:', e_ui);
        debugLog('app.js:2157', 'applyPausedDiscoveryUI exception', {error:String(e_ui)}, 'A');
        // #endregion
      }
      // #region agent log
      debugLog('app.js:2161', 'calling apiPostJson pause', {}, 'A');
      // #endregion
      let r;
      try{
        r = await apiPostJson('/api/discover-pause', {}); 
      }catch(e_api){
        // #region agent log
        console.error('apiPostJson exception:', e_api);
        debugLog('app.js:2165', 'apiPostJson exception', {error:String(e_api),errorName:e_api?.name}, 'A');
        // #endregion
        throw e_api; // Re-throw to be caught by outer catch
      }
      // #region agent log
      debugLog('app.js:2169', 'pause API response', {ok:r?.ok,error:r?.error,status:r?.status,note:r?.note}, 'A');
      // #endregion
      // Always check status after API call, regardless of response
      let st = null;
      try{
        st = await apiGet('/api/discover-status');
        // #region agent log
        debugLog('app.js:2175', 'status check success', {status:st?.status}, 'A');
        // #endregion
      }catch(e){
        // #region agent log
        console.error('status check exception:', e);
        debugLog('app.js:2178', 'status check exception', {error:String(e),errorName:e?.name}, 'A');
        // #endregion
      }
      const stStatus = st ? String(st?.status || '').toLowerCase() : '';
      // #region agent log
      debugLog('app.js:2147', 'immediate status check', {stStatus,apiOk:r?.ok,apiError:r?.error}, 'A');
      // #endregion

      if (!r || !r.ok){
        const err = (r && r.error) ? String(r.error) : 'Pause failed';
        // #region agent log
        debugLog('app.js:2151', 'API returned !ok', {err,stStatus,willReturnEarly:['idle','','done','cancelled'].includes(stStatus)}, 'B');
        // #endregion
        // If nothing is running (idle/done), don't show a failure toast
        if (stStatus === 'idle' || stStatus === '' || stStatus === 'done' || stStatus === 'cancelled'){
          // #region agent log
          debugLog('app.js:2154', 'returning early - idle/done/cancelled', {stStatus}, 'B');
          // #endregion
          return;
        }
        // If status shows paused, treat as success
        if (stStatus === 'paused'){
          // #region agent log
          debugLog('app.js:2159', 'status is paused - treating as success', {stStatus}, 'B');
          // #endregion
          applyPausedDiscoveryUI();
          return;
        }
        // If the worker is already gone, treat this as "stopped" and just refresh.
        if (err.toLowerCase().includes('no worker') || err.toLowerCase().includes('worker not')){
          // #region agent log
          debugLog('app.js:2165', 'worker not found - handling', {err,discoverLocalRunning,discoverPauseRetries,willRetry:discoverLocalRunning && discoverPauseRetries < 3}, 'B');
          // #endregion
          if (discoverLocalRunning && discoverPauseRetries < 3){
            discoverPauseRetries += 1;
            if (discoverStatus) discoverStatus.textContent = 'Pausing…';
            if (discoverPauseRetryTimer) clearTimeout(discoverPauseRetryTimer);
            discoverPauseRetryTimer = setTimeout(() => pauseDiscovery(), 900);
            return;
          }
          discoverPauseRetries = 0;
          await pollDiscoveryFallback();
          return;
        }
        // Only show error if status check confirms it's not paused (after delay to allow status to update)
        // #region agent log
        debugLog('app.js:2177', 'scheduling delayed status check', {err,stStatus}, 'C');
        // #endregion
        setTimeout(async () => {
          try{
            const st2 = await apiGet('/api/discover-status'); 
            const finalStatus = String(st2?.status || '').toLowerCase();
            // #region agent log
            debugLog('app.js:2181', 'delayed status check result', {finalStatus,willShowToast:finalStatus !== 'paused' && finalStatus !== 'idle' && finalStatus !== 'done' && finalStatus !== 'cancelled',err}, 'C');
            // #endregion
            // Don't show error if status is paused, idle, done, or cancelled
            if (finalStatus !== 'paused' && finalStatus !== 'idle' && finalStatus !== 'done' && finalStatus !== 'cancelled'){
              // #region agent log
              debugLog('app.js:2185', 'SHOWING ERROR TOAST', {finalStatus,err}, 'C');
              // #endregion
              toast('Discovery', err);
            }
          }catch(e){
            // #region agent log
            debugLog('app.js:2189', 'delayed status check exception', {error:String(e)}, 'C');
            // #endregion
          }
        }, 600);
        return;
      }
      // If API says ok but status check shows not paused, check status again after short delay
      if (stStatus !== 'paused'){
        // #region agent log
        debugLog('app.js:2195', 'API ok but status not paused - scheduling recheck', {stStatus}, 'A');
        // #endregion
        setTimeout(async () => {
          try{
            const st2 = await apiGet('/api/discover-status'); 
            if (String(st2?.status || '').toLowerCase() === 'paused'){
              applyPausedDiscoveryUI();
            }
          }catch(_){ }
        }, 300);
      }
      // #region agent log
      debugLog('app.js:2203', 'pauseDiscovery SUCCESS path', {stStatus}, 'A');
      // #endregion
      applyPausedDiscoveryUI();
    }catch(e){
      // #region agent log
      console.error('pauseDiscovery EXCEPTION:', e);
      console.error('Exception details:', {name:e?.name, message:e?.message, stack:e?.stack});
      // Force immediate log without throttling
      try{
        const logData = {location:'app.js:2291', message:'pauseDiscovery EXCEPTION', data:{error:String(e),errorName:e?.name,errorMessage:e?.message,stack:String(e?.stack||'').substring(0,500)}, timestamp:Date.now(), sessionId:'debug-session', runId:'run1', hypothesisId:'D'};
        console.log('[DEBUG] EXCEPTION', logData);
        // Bypass throttle by using fetch directly
        fetch('/api/client-log', {
          method: 'POST',
          headers: {'Content-Type':'application/json'},
          body: JSON.stringify({
            level: 'INFO',
            message: `[DEBUG] app.js:2291: pauseDiscovery EXCEPTION`,
            context: logData,
            path: location.pathname,
            href: location.href,
            ts: new Date().toISOString(),
          }),
        }).catch(() => {});
      }catch(e_log){
        console.error('Failed to log exception:', e_log);
      }
      debugLog('app.js:2294', 'pauseDiscovery EXCEPTION (via debugLog)', {error:String(e),errorName:e?.name,errorMessage:e?.message}, 'D');
      // #endregion
      try{
        const st = await apiGet('/api/discover-status');      
        const stStatus = String(st?.status || '').toLowerCase();
        // #region agent log
        debugLog('app.js:2209', 'exception handler status check', {stStatus}, 'D');
        // #endregion
        if (stStatus === 'paused'){
          applyPausedDiscoveryUI();
          return;
        }
      }catch(e2){
        // #region agent log
        console.error('exception handler status check failed:', e2);
        debugLog('app.js:2214', 'exception handler status check failed', {error:String(e2),errorName:e2?.name}, 'D');
        // #endregion
      }
      setTimeout(async () => {
        try{
          const st2 = await apiGet('/api/discover-status');   
          const finalStatus = String(st2?.status || '').toLowerCase();
          // #region agent log
          debugLog('app.js:2219', 'exception delayed status check', {finalStatus,willShowToast:finalStatus !== 'paused' && finalStatus !== 'idle' && finalStatus !== 'done' && finalStatus !== 'cancelled'}, 'D');
          // #endregion
          // Don't show error if status is paused, idle, done, or cancelled
          if (finalStatus !== 'paused' && finalStatus !== 'idle' && finalStatus !== 'done' && finalStatus !== 'cancelled'){
            // #region agent log
            debugLog('app.js:2223', 'SHOWING ERROR TOAST from exception', {finalStatus}, 'D');
            // #endregion
            toast('Discovery', 'Pause failed');
          }
        }catch(e3){
          // #region agent log
          console.error('delayed status check exception:', e3);
          debugLog('app.js:2227', 'delayed status check exception in setTimeout', {error:String(e3)}, 'D');
          // #endregion
        }
      }, 600);
    }
  }

  async function resumeDiscovery(){
    try{
      // Optimistic UI: show running immediately
      applyRunningDiscoveryUI();
      const r = await apiPostJson('/api/discover-resume', {});
      // Always check status after API call, regardless of response
      let st = null;
      try{
        st = await apiGet('/api/discover-status');
      }catch(_){ }
      const stStatus = st ? String(st?.status || '').toLowerCase() : '';

      if (!r || !r.ok){
        const err = (r && r.error) ? String(r.error) : 'Resume failed';
        // If nothing is running (idle), don't show a failure toast
        if (stStatus === 'idle' || stStatus === ''){
          applyPausedDiscoveryUI();
          return;
        }
        // If status shows running/starting, treat as success 
        if (stStatus === 'running' || stStatus === 'starting'){
          applyRunningDiscoveryUI();
          return;
        }
        if (err.toLowerCase().includes('no worker')){
          await startDiscovery();
          return;
        }
        if (stStatus === 'paused'){
          applyPausedDiscoveryUI();
          return;
        }
        setTimeout(async () => {
          try{
            const st2 = await apiGet('/api/discover-status'); 
            if (String(st2?.status || '').toLowerCase() !== 'running' && String(st2?.status || '').toLowerCase() !== 'starting'){
              toast('Discovery', err);
            }
          }catch(_){ }
        }, 600);
        return;
      }
      // If API says ok but status check shows not running, check status again after short delay
      if (stStatus !== 'running' && stStatus !== 'starting'){
        setTimeout(async () => {
          try{
            const st2 = await apiGet('/api/discover-status'); 
            if (String(st2?.status || '').toLowerCase() === 'running' || String(st2?.status || '').toLowerCase() === 'starting'){
              applyRunningDiscoveryUI();
            }
          }catch(_){ }
        }, 300);
      }
      applyRunningDiscoveryUI();
    }catch(e){
      try{
        const st = await apiGet('/api/discover-status');      
        const stStatus = String(st?.status || '').toLowerCase();
        if (stStatus === 'running' || stStatus === 'starting'){
          applyRunningDiscoveryUI();
          return;
        }
        if (stStatus === 'paused'){
          applyPausedDiscoveryUI();
          return;
        }
      }catch(_){ }
      setTimeout(async () => {
        try{
          const st2 = await apiGet('/api/discover-status');   
          if (String(st2?.status || '').toLowerCase() !== 'running' && String(st2?.status || '').toLowerCase() !== 'starting'){
            toast('Discovery', 'Resume failed');
          }
        }catch(_){ }
      }, 600);
    }
  }

async function cancelDiscovery(){
    await apiPostJson('/api/discover-cancel', {});
    // Immediately stop local listeners/pollers so the UI doesn't look "stuck running".
    try{ if (discoverES){ discoverES.close(); discoverES = null; } }catch(_){ }
    try{ if (typeof discoverFallbackPoll !== 'undefined' && discoverFallbackPoll){ clearInterval(discoverFallbackPoll); discoverFallbackPoll = null; } }catch(_){ }
    try{ discoverGotSSE = false; }catch(_){ }
    discoverLocalRunning = false;
    discoverLocalPaused = false;
    if (discoverStatus) discoverStatus.textContent = 'Cancelling…';
    // Fetch a fresh state shortly after (backend may transition to idle quickly if the worker is already gone)
    setTimeout(() => { try{ pollDiscoveryFallback(); }catch(_){ } }, 400);
  }


  async function runDiscoveryDebug(){
    try{
      openDiscoverDebug();
      discoverDebugLines = [];
      discoverDbg('Running discovery diagnostics…');

      const payload = {
        scope: (discoverScope?.value || 'auto'),
        custom: (discoverCustom?.value || '').trim(),
        iface: discoverIface?.value || 'auto',
        profile: 'safe',
        cap: 256,
      };
      discoverDbg('POST /api/discover-debug', payload);
      const r = await apiPostJson('/api/discover-debug', payload);
      discoverDbg('Debug response', r);
      if (!r || !r.ok){
        toast('Discovery debug', (r && r.message) ? r.message : 'Failed');
      }
    }catch(err){
      discoverDbg('JS exception in debug', { message: String(err?.message || err), stack: String(err?.stack||'') });
    }
  }

  // Optional global hook for manual testing from the console.
  window.__ihDiscoveryDebug = runDiscoveryDebug;

  btnDiscoverStart?.addEventListener('click', startDiscovery);
  btnDiscoverCancel?.addEventListener('click', () => {
    pauseDiscovery();
  });

  btnDiscoverResume?.addEventListener('click', () => {
    resumeDiscovery();
  });

  btnDiscoverReset?.addEventListener('click', async () => {
    try {
      const r = await fetch('/api/discover-reset', { method: 'POST' });
      if (!r.ok) {
        console.warn('Reset API call failed, but continuing with local reset');
      }
    } catch (e) {
      // ignore; UI will still reset locally
      console.warn('Reset API call error:', e);
    }
    // Wait a bit for workers to be killed before resetting UI
    await new Promise(resolve => setTimeout(resolve, 300));
    resetDiscoverUI();
    // Ensure start button is enabled after reset
    if (btnDiscoverStart) {
      btnDiscoverStart.disabled = false;
      btnDiscoverStart.style.display = 'inline-flex';
    }
    discoverStartInFlight = false; // Reset the flag so start can work again
    // Force a status check to ensure backend state is synced
    try {
      await apiGet('/api/discover-status');
    } catch (_) {}
  });
  btnDiscoverDebug?.addEventListener('click', runDiscoveryDebug);
  btnDiscoverDebugClose?.addEventListener('click', closeDiscoverDebug);
  btnDiscoverDebugCopy?.addEventListener('click', async () => {
    try{
      const txt = discoverDebugOut ? (discoverDebugOut.textContent || '') : '';
      if (!txt.trim()) { discoverDbg('Copy: nothing to copy'); return; }
      if (navigator.clipboard && navigator.clipboard.writeText){
        await navigator.clipboard.writeText(txt);
      }else{
        const ta = document.createElement('textarea');
        ta.value = txt;
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        document.body.appendChild(ta);
        ta.focus(); ta.select();
        document.execCommand('copy');
        document.body.removeChild(ta);
      }
      discoverDbg('Copied debug output to clipboard');
    }catch(e){
      discoverDbg('Copy failed', { message: String(e?.message || e) });
      openDiscoverDebug();
    }
  });


  
  let discoverFallbackPoll = null;
  async function pollDiscoveryFallback(){
    try{
      const st = await apiGet('/api/discover-status');
      if (discoverSubnets && st && st.cidrs != null) discoverSubnets.textContent = String(st.cidrs);
      if (discoverFound && st && st.found != null) discoverFound.textContent = String(st.found);
      const stStatus = (st && st.status) ? String(st.status).toLowerCase() : '';
      const pauseGrace = discoverPauseGraceUntil && Date.now() < discoverPauseGraceUntil;
      const resumeGrace = discoverResumeGraceUntil && Date.now() < discoverResumeGraceUntil;
      if (discoverLocalPaused && (pauseGrace || stStatus === 'running' || stStatus === 'starting')){
        if (discoverStatus) discoverStatus.textContent = 'Paused';
        if (discoverScanning) discoverScanning.textContent = '-';
        setDiscoverRunning(false);
        if (btnDiscoverCancel) btnDiscoverCancel.style.display='none';
        if (btnDiscoverStart) btnDiscoverStart.style.display='none';
        if (btnDiscoverResume) btnDiscoverResume.style.display='inline-flex';
      } else if (resumeGrace && (stStatus === 'paused' || stStatus === '')){
        // During resume grace period, ignore paused status from backend
        if (discoverStatus) discoverStatus.textContent = 'Running…';
        if (discoverScanning) discoverScanning.textContent = st.scanning || st.cidr || '-';
      } else {
        if (discoverStatus) discoverStatus.textContent = st.message || st.status || 'Running…';
        if (discoverScanning) discoverScanning.textContent = st.scanning || st.cidr || '-';
      }
      if (discoverProgressWrap) {
        const show = !!(st && (st.status === 'running' || st.status === 'starting' || st.status === 'paused' || st.status === 'cancelling' || st.status === 'done'));
        discoverProgressWrap.style.display = show ? 'block' : 'none';
        discoverProgressWrap.style.opacity = show ? '1' : '0';
      }
      const isRunning = (!discoverLocalPaused) && (!!(st && (st.status === 'running' || st.status === 'starting')) || discoverLocalRunning);
      setDiscoverRunning(isRunning);
      if (discoverBar && st.progress){
        const cur = Number(st.progress.current||0); const tot = Number(st.progress.total||0);
        const pct = tot ? ((cur/tot)*100) : 0;
        const pctStr = tot
          ? (pct < 1 ? pct.toFixed(2) : pct < 10 ? pct.toFixed(1) : Math.round(pct).toString())
          : "0";
        const pctClamped = Math.min(100, Math.max(0, pct));
        discoverBar.style.width = `${pctClamped}%`;
        if (discoverProgressBar) discoverProgressBar.style.setProperty('--ih-pct', `${pctClamped}%`);
        if (discoverPercent) discoverPercent.textContent = `${pctStr}%`;
      }

      // Pull discovered devices when SSE is blocked or slow.
      if (!discoverGotSSE && (st.status === 'running' || st.status === 'starting' || st.status === 'paused')){
        const now = Date.now();
        if (!discoverResultsLastTs || (now - discoverResultsLastTs) > 1600){
          discoverResultsLastTs = now;
          try{
            const res = await apiGet('/api/discover-result');
            if (res && Array.isArray(res.found)){
              res.found.forEach(dev => {
                const ip = String(dev?.ip || '').trim();
                if (!ip) return;
                const prev = discoverDeviceMap.get(ip) || null;
                if (prev){
                  discoverDeviceMap.set(ip, Object.assign({}, prev, dev));
                } else {
                  discoverDeviceMap.set(ip, dev);
                }
              });
              discoverDevices = Array.from(discoverDeviceMap.values());
              if (discoverFound) discoverFound.textContent = String(discoverDeviceMap.size);
              scheduleDiscoverRender();
            }
          }catch(_){ }
        }
      }

      // Only show Debug when something looks wrong.
      if (btnDiscoverDebug) {
        const needsDebug = !!(st && ((st.status === 'error') || (st.error && st.error !== 'Cancelled')));
        btnDiscoverDebug.style.display = needsDebug ? 'inline-flex' : 'none';
      }
      if (st && (st.status === 'running' || st.status === 'starting' || st.status === 'cancelling')){
        if (discoverLocalPaused) return;
        if (btnDiscoverCancel) btnDiscoverCancel.style.display='inline-flex';
        if (btnDiscoverResume) btnDiscoverResume.style.display='none';
        if (btnDiscoverStart) btnDiscoverStart.style.display='none';
        if (discoverStatus && st.status === 'cancelling') discoverStatus.textContent = st.message || 'Cancelling…';
      }
      if (st && st.status === 'paused'){
        // Don't override if we're in a resume grace period
        if (!(discoverResumeGraceUntil && Date.now() < discoverResumeGraceUntil)){
          discoverLocalPaused = true;
          discoverPauseGraceUntil = Date.now() + 8000;
          if (btnDiscoverCancel) btnDiscoverCancel.style.display='none';
          if (btnDiscoverStart) btnDiscoverStart.style.display='none';
          if (btnDiscoverResume) btnDiscoverResume.style.display='inline-flex';
          setDiscoverRunning(false);
        }
      }
      if (st.status === 'done' || st.status === 'cancelled' || st.status === 'error'){
        discoverLocalRunning = false;
        discoverLocalPaused = false;
        discoverPauseGraceUntil = 0;
        discoverResumeGraceUntil = 0;
        if (discoverFallbackPoll){ clearInterval(discoverFallbackPoll); discoverFallbackPoll = null; }
        if (btnDiscoverCancel) btnDiscoverCancel.style.display='none';
        if (btnDiscoverResume) btnDiscoverResume.style.display='none';
        if (btnDiscoverStart){ btnDiscoverStart.style.display='inline-flex'; btnDiscoverStart.disabled=false; }
      }
    }catch(e){ /* ignore */ }
  }
function connectDiscoveryStream(){
    if (discoverES){ try{ discoverES.close(); }catch(e){} }
    discoverES = new EventSource('/api/discover-stream');

    discoverES.addEventListener('status', (ev) => {
      try{
        discoverGotSSE = true;
        const obj = JSON.parse(ev.data);
        const eid = Number(obj.id||0);
        if (eid && eid <= discoverLastEventId) return;
        if (eid) discoverLastEventId = eid;
        const st = obj.status || obj?.message || '';
        if (obj.cidrs != null && discoverSubnets) discoverSubnets.textContent = String(obj.cidrs);
        else if (obj.progress && obj.progress.total != null && discoverSubnets) discoverSubnets.textContent = String(obj.progress.total);
        if (obj.progress && discoverBar){
          const cur = Number(obj.progress.current||0); const tot = Number(obj.progress.total||0);
          const pct = tot ? ((cur/tot)*100) : 0;
          const pctClamped = Math.min(100, Math.max(0, pct));
          const pctStr = tot
            ? (pctClamped < 1 ? pctClamped.toFixed(2) : pctClamped < 10 ? pctClamped.toFixed(1) : Math.round(pctClamped).toString())
            : "0";
          discoverBar.style.width = `${pctClamped}%`;
          // Used by CSS shimmer/scanline effect.
          const pb = document.getElementById('discoverProgressBar');
          if (pb) pb.style.setProperty('--ih-pct', `${pctClamped}%`);
          if (discoverPercent) discoverPercent.textContent = `${pctStr}%`;
        }
        if (discoverStatus) discoverStatus.textContent = obj.message || st || 'Running…';
        try{
          if (obj.message && String(obj.message).startsWith('Scanning ')){
          }
        }catch(_){ }

        if (discoverScanning){
          const s = (obj.scanning || (obj.progress && obj.progress.cidr) || '')
          discoverScanning.textContent = s ? String(s) : '-';
        }
        if (obj.status){
          setDiscoverRunning(obj.status === 'running' || obj.status === 'starting');
        }
        if (obj.status === 'running' || obj.status === 'starting' || obj.status === 'cancelling'){
          discoverLocalRunning = true;
          if (btnDiscoverCancel) btnDiscoverCancel.style.display='inline-flex';
          if (btnDiscoverStart) btnDiscoverStart.style.display='none';
          if (btnDiscoverResume) btnDiscoverResume.style.display='none';
          if (discoverStatus && obj.status === 'cancelling') discoverStatus.textContent = obj.message || 'Cancelling…';
        }
        if (obj.status === 'paused'){
          discoverLocalRunning = false;
          if (btnDiscoverCancel) btnDiscoverCancel.style.display='none';
          if (btnDiscoverStart) btnDiscoverStart.style.display='none';
          if (btnDiscoverResume) btnDiscoverResume.style.display='inline-flex';
        }
        if (obj.status === 'done' || obj.status === 'cancelled' || obj.status === 'error'){
          discoverLocalRunning = false;
          if (btnDiscoverCancel) btnDiscoverCancel.style.display='none';
          if (btnDiscoverResume) btnDiscoverResume.style.display='none';
          if (btnDiscoverStart){ btnDiscoverStart.style.display='inline-flex'; btnDiscoverStart.disabled=false; }
        }
      }catch(e){}
    });

    discoverES.addEventListener('device', (ev) => {
      try{
        discoverGotSSE = true;
        const obj = JSON.parse(ev.data);
        const eid = Number(obj.id||0);
        if (eid && eid <= discoverLastEventId) return;
        if (eid) discoverLastEventId = eid;
        const dev = obj.device;
        if (!dev) return;
        const ip = String(dev.ip||'').trim();
        if (!ip) return;
        // Deduplicate: update existing record if we already saw this IP.
        const prev = discoverDeviceMap.get(ip) || null;
        if (prev){
          discoverDeviceMap.set(ip, Object.assign({}, prev, dev));
        } else {
          discoverDeviceMap.set(ip, dev);
        }

        try{
        }catch(_){ }
        // Keep array for any legacy callers, but render uses the map.
        discoverDevices = Array.from(discoverDeviceMap.values());
        if (discoverFound) discoverFound.textContent = String(discoverDeviceMap.size);
        scheduleDiscoverRender();
      }catch(e){}
    });

    discoverES.addEventListener('error', (ev) => {
      // Some proxies block SSE. Fall back to polling status so the user still sees progress.
      if (!discoverFallbackPoll){
        discoverFallbackPoll = setInterval(pollDiscoveryFallback, 1200);
        pollDiscoveryFallback();
      }
    });
  }

  btnDiscoverAddCancel?.addEventListener('click', () => {
    discoverSelected = null;
    if (discoverAddCard) discoverAddCard.style.display='none';
  });

  function openDiscoverAddModal(dev){
    // #region agent log
    debugLog('app.js:2593', 'openDiscoverAddModal START', {dev:!!dev,ip:dev?.ip}, 'F');
    // #endregion
    if (!dev) {
      // #region agent log
      debugLog('app.js:2595', 'openDiscoverAddModal - no dev', {}, 'F');
      // #endregion
      return;
    }
    const ip = String(dev.ip||'');
    if (!ip) {
      // #region agent log
      debugLog('app.js:2599', 'openDiscoverAddModal - no ip', {dev}, 'F');
      // #endregion
      return;
    }
    // Ensure modal element exists - try to find it if not already bound
    let modalEl = discoverAddModal;
    // #region agent log
    debugLog('app.js:2603', 'checking modal element', {discoverAddModalExists:!!discoverAddModal}, 'F');
    // #endregion
    if (!modalEl){
      modalEl = document.getElementById('discoverAddModal');  
      // #region agent log
      debugLog('app.js:2606', 'looked up modal by ID', {found:!!modalEl}, 'F');
      // #endregion
      if (!modalEl){
        console.error('discoverAddModal element not found');  
        toast('Error', 'Add modal not found');
        return;
      }
    }
    // Ensure form elements exist
    const nameEl = discoverAddModalName || document.getElementById('discoverAddModalName');
    const ipEl = discoverAddModalIp || document.getElementById('discoverAddModalIp');
    const endpointEl = discoverAddModalEndpoint || document.getElementById('discoverAddModalEndpoint');
    const intervalEl = discoverAddModalInterval || document.getElementById('discoverAddModalInterval');
    // #region agent log
    debugLog('app.js:2614', 'form elements check', {nameEl:!!nameEl,ipEl:!!ipEl,endpointEl:!!endpointEl,intervalEl:!!intervalEl,modalEl:!!modalEl}, 'F');
    // #endregion

    if (ipEl) {
      ipEl.value = ip;
      ipEl.classList.add('input--locked'); // Add locked styling
    }
    // Set name placeholder to IP, but leave value empty so user can type
    try{
      if (nameEl) {
        const suggestedName = suggestName(dev) || ip;
        nameEl.placeholder = suggestedName;
        nameEl.value = ''; // Empty so user can type, placeholder will show IP
        // If user clicks and starts typing, use their input; otherwise placeholder shows
      }
    }catch(e_name){
      // #region agent log
      console.error('suggestName error:', e_name);
      debugLog('app.js:2812', 'suggestName exception', {error:String(e_name)}, 'F');
      // #endregion
      if (nameEl) {
        nameEl.placeholder = ip || '';
        nameEl.value = '';
      }
    }
    // Don't prefill endpoint - user must provide it
    if (endpointEl) endpointEl.value = '';   
    if (intervalEl) intervalEl.value = '60';

    // #region agent log
    debugLog('app.js:2802', 'calling show() on modal', {modalEl:!!modalEl,hasShowClassBefore:modalEl?.classList?.contains('show')}, 'F');
    // #endregion
    try{
      show(modalEl);
    }catch(e_show){
      // #region agent log
      console.error('show() error:', e_show);
      debugLog('app.js:2804', 'show() exception', {error:String(e_show),modalEl:!!modalEl}, 'F');
      // #endregion
      throw e_show;
    }
    // #region agent log
    debugLog('app.js:2623', 'after show() call', {hasShowClass:modalEl?.classList?.contains('show'),ariaHidden:modalEl?.getAttribute('aria-hidden')}, 'F');
    // #endregion
    setTimeout(() => {
      try{ if (nameEl) nameEl.focus(); }catch(_){}    
    }, 100);
  }

  function closeDiscoverAddModal(){
    if (discoverAddModal) hide(discoverAddModal);
    // Remove locked styling when closing
    const ipEl = discoverAddModalIp || document.getElementById('discoverAddModalIp');
    if (ipEl) ipEl.classList.remove('input--locked');
  }

  btnCloseDiscoverAdd?.addEventListener('click', closeDiscoverAddModal);
  btnDiscoverAddModalCancel?.addEventListener('click', closeDiscoverAddModal);
  discoverAddModal?.addEventListener('click', (e) => { if (e.target === discoverAddModal) closeDiscoverAddModal(); });

  discoverAddModalForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    if (!discoverAddModalForm) return;
    const fd = new FormData(discoverAddModalForm);
    // If name is empty, use placeholder (which contains the suggested name/IP)
    const nameInput = discoverAddModalName;
    const nameValue = String(fd.get('name')||'').trim();
    if (!nameValue && nameInput && nameInput.placeholder){
      fd.set('name', nameInput.placeholder);
    }
    const endpoint = String(fd.get('endpoint')||'').trim();
    if (!endpointLooksValid(endpoint)){
      toast('Add target', 'Endpoint URL must be http:// or https://');
      discoverAddModalEndpoint?.focus();
      return;
    }
    const r = await apiPost('/api/add', fd);
    if (!r.ok){
      toast('Add target', r.message || 'Failed');
      return;
    }
    await refreshTargets();
    const ip = String(fd.get('ip')||'').trim();
    if (ip){
      const dev = discoverDeviceMap.get(ip);
      if (dev) dev.added_now = true;
    }
    renderDiscoverList();
    toast('Add target', 'Added');
    closeDiscoverAddModal();
  });

  function endpointLooksValid(u){
    try{
      const url = new URL(u);
      return url.protocol === 'http:' || url.protocol === 'https:';
    }catch(e){
      return false;
    }
  }

  async function submitDiscoverAdd(keepOpen){
    if (!discoverAddForm) return;
    const fd = new FormData(discoverAddForm);
    const endpoint = String(fd.get('endpoint')||'').trim();
    if (!endpointLooksValid(endpoint)){
      toast('Add target', 'Endpoint URL must be http:// or https://');
      discoverAddEndpoint?.focus();
      return;
    }
    const r = await apiPost('/api/add', fd);
    if (!r.ok){
      toast('Add target', r.message || 'Failed');
      return;
    }
    await refreshTargets();
    if (discoverSelected){
      discoverSelected.added_now = true;
    }
    renderDiscoverList();
    toast('Add target', 'Added');

    if (!keepOpen){
      discoverSelected = null;
      if (discoverAddCard) discoverAddCard.style.display='none';
    } else {
      discoverAddEndpoint.value = suggestEndpoint(discoverAddIp.value);
      discoverAddEndpoint.focus();
    }
  }

  discoverAddForm?.addEventListener('submit', async (e) => {
    e.preventDefault();
    await submitDiscoverAdd(false);
  });
  btnDiscoverAddKeep?.addEventListener('click', async () => {
    await submitDiscoverAdd(true);
  });



  // ---- INIT_BOOTSTRAP ----
  (async () => {
    try{
      // Ensure the table UI is fully interactive on first load (no need to click Run now).
      await refreshState(true);
    }catch(e){
      // If the first state fetch fails, still bind handlers for the server-rendered rows.
      try{ attachIntervalHandlers(); attachMenuActions(); attachBulkHandlers(); attachRowClickHandlers(); bindSortHeaders(); }catch(_){}
    }

    // periodic refresh
    let pollS = 2;
    try{
      const v = Number(document.body?.dataset?.pollSeconds || 2);
      if (Number.isFinite(v) && v > 0) pollS = v;
    }catch(e){}
    setInterval(() => { refreshState(false).catch(()=>{}); }, pollS*1000);
  })();
  // kick initial render if panel exists
  resetDiscoverUI();

  // ---- End network discovery ----


  // Ensure clear-buttons reflect current input state on load.
  try{ toggleClearButtons(); }catch(_){ }
})();
