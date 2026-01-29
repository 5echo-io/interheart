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
    return await res.json();
  }
  async function apiGet(url){
    const res = await fetch(url, {cache:"no-store"});
    return await res.json();
  }

  // ---- Logs modal ----
  const logModal = $("#logModal");
  const openLogs = $("#openLogs");
  const closeLogs = $("#btnCloseLogs");
  const reloadLogs = $("#btnReloadLogs");
  const copyLogs = $("#btnCopyLogs");
  const logBox = $("#logBox");
  const logMeta = $("#logMeta");
  const logFilter = $("#logFilter");
  const logLinesLbl = $("#logLinesLbl");
  let rawLog = "";

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
    if (!q){
      logBox.textContent = rawLog || "(empty)";
      return;
    }
    const lines = (rawLog || "").split("\n").filter(l => l.toLowerCase().includes(q));
    logBox.textContent = lines.join("\n") || "(no matches)";
  }

  openLogs?.addEventListener("click", async () => { show(logModal); logFilter?.focus(); await loadLogs(); });
  closeLogs?.addEventListener("click", () => hide(logModal));
  reloadLogs?.addEventListener("click", async () => await loadLogs());
  copyLogs?.addEventListener("click", async () => {
    try{ await navigator.clipboard.writeText(logBox.textContent || ""); toast("Copied", "Logs copied to clipboard"); }catch(e){}
  });
  logFilter?.addEventListener("input", applyLogFilter);
  logModal?.addEventListener("click", (e) => { if (e.target === logModal) hide(logModal); });

  // ---- Filter targets ----
  const filterInput = $("#filterInput");
  const table = $("#targetsTable");
  function applyTargetFilter(){
    const q = (filterInput?.value || "").trim().toLowerCase();
    $$("tbody tr[data-name]", table).forEach(row => {
      const name = (row.getAttribute("data-name") || "").toLowerCase();
      const ip = (row.getAttribute("data-ip") || "").toLowerCase();
      const status = (row.getAttribute("data-status") || "").toLowerCase();
      const ok = !q || name.includes(q) || ip.includes(q) || status.includes(q);
      row.style.display = ok ? "" : "none";
    });
  }
  filterInput?.addEventListener("input", applyTargetFilter);

  // ---- Add modal ----
  const addModal = $("#addModal");
  const openAdd = $("#openAdd");
  const addCancel = $("#btnAddCancel");
  const addForm = $("#addForm");
  const btnAddSubmit = $("#btnAddSubmit");

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

  // ---- Confirm remove modal ----
  const confirmModal = $("#confirmModal");
  const btnCloseConfirm = $("#btnCloseConfirm");
  const btnCancelRemove = $("#btnCancelRemove");
  const btnConfirmRemove = $("#btnConfirmRemove");
  const confirmName = $("#confirmName");
  let pendingRemoveName = null;

  function openConfirmRemove(name){
    pendingRemoveName = name;
    confirmName.textContent = name;
    show(confirmModal);
  }
  function closeConfirmRemove(){
    pendingRemoveName = null;
    hide(confirmModal);
  }

  btnCloseConfirm?.addEventListener("click", closeConfirmRemove);
  btnCancelRemove?.addEventListener("click", closeConfirmRemove);
  confirmModal?.addEventListener("click", (e) => { if (e.target === confirmModal) closeConfirmRemove(); });

  btnConfirmRemove?.addEventListener("click", async () => {
    const name = pendingRemoveName;
    if (!name) return;
    btnConfirmRemove.disabled = true;
    btnConfirmRemove.textContent = "Removing…";
    try{
      const fd = new FormData();
      fd.set("name", name);
      const data = await apiPost("/api/remove", fd);
      toast(data.ok ? "Removed" : "Error", data.message || (data.ok ? "Done" : "Failed"));
      closeConfirmRemove();
    }catch(e){
      toast("Error", e?.message || "Failed");
    }finally{
      btnConfirmRemove.disabled = false;
      btnConfirmRemove.textContent = "Remove";
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

  const u24 = $("#u24");
  const u7 = $("#u7");
  const u30 = $("#u30");
  const u90 = $("#u90");
  const u24t = $("#u24t");
  const u7t = $("#u7t");
  const u30t = $("#u30t");
  const u90t = $("#u90t");

  btnCloseInfo?.addEventListener("click", () => hide(infoModal));
  infoModal?.addEventListener("click", (e) => { if (e.target === infoModal) hide(infoModal); });

  function setUptimeRow(barEl, textEl, stat){
    if (!barEl || !textEl) return;
    if (!stat){
      barEl.style.width = "0%";
      textEl.textContent = "-";
      return;
    }
    const pct = Number(stat.pct ?? 0);
    barEl.style.width = `${Math.max(0, Math.min(100, pct))}%`;
    const s = `${pct}% (${stat.up}/${stat.samples})`;
    const rtt = (stat.avg_rtt_ms === null || stat.avg_rtt_ms === undefined) ? "" : ` • avg ${stat.avg_rtt_ms}ms`;
    textEl.textContent = s + rtt;
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
            } else if (action === "enable"){
              data = await apiPost("/api/enable", fd);
            } else if (action === "disable"){
              data = await apiPost("/api/disable", fd);
            } else {
              return;
            }
            toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
          }catch(e){
            toast("Error", e?.message || "Failed");
          }finally{
            await refreshState(true);
          }
        });
      });
    });
  }

  // ---- Real-time-ish refresh + row blink ----
  function setStatusChip(row, status){
    const chip = row.querySelector(".status-chip");
    const text = row.querySelector(".status-text");
    if (!chip || !text) return;

    chip.classList.remove("status-up","status-down","status-unknown");
    if (status === "up") chip.classList.add("status-up");
    else if (status === "down") chip.classList.add("status-down");
    else chip.classList.add("status-unknown");

    text.textContent = (status || "unknown").toUpperCase();
    row.setAttribute("data-status", status || "unknown");
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
      const map = new Map();
      (data.targets || []).forEach(t => map.set(t.name, t));

      function setActionVisibility(row, enabled){
        // Dropdown Enable/Disable
        const btnEnable = row.querySelector('.menu-item[data-action="enable"]');
        const btnDisable = row.querySelector('.menu-item[data-action="disable"]');
        if (btnEnable) btnEnable.style.display = enabled ? "none" : "block";
        if (btnDisable) btnDisable.style.display = enabled ? "block" : "none";
      }

      $$("tr[data-name]").forEach(row => {
        const name = row.getAttribute("data-name");
        const t = map.get(name);
        if (!t) return;

        setStatusChip(row, t.status);

        // Track enabled + keep Actions menu consistent
        const enabled = Number(t.enabled ?? 0) === 1 && String(t.status || "") !== "disabled";
        row.setAttribute("data-enabled", enabled ? "1" : "0");
        setActionVisibility(row, enabled);

        // Blink row for 1s when a new ping happens
        const prevPing = Number(row.getAttribute("data-last-ping") || "0");
        const nextPing = Number(t.last_ping_epoch || 0);
        if (nextPing && nextPing !== prevPing){
          row.setAttribute("data-last-ping", String(nextPing));
          row.classList.remove("flash-up","flash-down");
          row.classList.add((t.status === "up") ? "flash-up" : "flash-down");
          setTimeout(() => row.classList.remove("flash-up","flash-down"), 1000);
        }
        const nextResp = Number(t.last_response_epoch || 0);
        row.setAttribute("data-last-resp", String(nextResp));

        flashIfChanged(row.querySelector(".last-ping"), t.last_ping_human || "-");
        flashIfChanged(row.querySelector(".last-resp"), t.last_response_human || "-");

        const iv = row.querySelector(".interval-input");
        if (iv && force){
          iv.value = String(t.interval || 60);
          iv.setAttribute("data-interval", String(t.interval || 60));
        }
      });

      applyTargetFilter();
      attachIntervalHandlers();
      attachMenuActions();
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

  let runPoll = null;

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
    try{
      const out = await apiGet("/api/run-output?lines=220");
      if (out && out.ok){
        outText = out.text || "";
        summary = out.summary || null;
      }
    }catch(e){ /* ignore */ }

    // Progress: count completed target lines (`run: <name> ...`)
    const done = (outText.match(/^run:\s+/gm) || []).length;

    // If summary exists (usually at end), prefer it
    const due = summary ? Number(summary.due || 0) : Math.max(done, 0);
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
      runNowLine.textContent = "Running…";
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

  // init
  attachIntervalHandlers();
  attachMenuActions();
  applyTargetFilter();
  // Ensure Enable/Disable visibility + row datasets are synced immediately
  refreshState(true);
  setInterval(() => refreshState(false), 2000);

  // ESC closes modals
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape"){
      if (logModal?.classList.contains("show")) hide(logModal);
      if (addModal?.classList.contains("show")) hide(addModal);
      if (runModal?.classList.contains("show")) hide(runModal);
      if (confirmModal?.classList.contains("show")) hide(confirmModal);
      if (infoModal?.classList.contains("show")) hide(infoModal);
      if (editModal?.classList.contains("show")) hide(editModal);
      closeAllMenus();
    }
  });

})();
