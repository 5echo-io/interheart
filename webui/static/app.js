(() => {
  "use strict";

  // ---------- helpers ----------
  const $ = (sel, root=document) => root.querySelector(sel);
  const $$ = (sel, root=document) => Array.from(root.querySelectorAll(sel));

  const state = {
    targets: [],
    filter: "",
    menusOpenFor: null,
    pendingRemove: null,
    infoTarget: null,
    editTarget: null,
    run: {
      runtimePoll: null,
      statusPoll: null,
      lastRuntimeUpdated: 0
    }
  };

  function escapeHtml(s){
    return String(s ?? "")
      .replaceAll("&","&amp;")
      .replaceAll("<","&lt;")
      .replaceAll(">","&gt;")
      .replaceAll('"',"&quot;")
      .replaceAll("'","&#039;");
  }

  // ---------- toast ----------
  let toastTimer = null;
  function toast(kind, msg){
    const el = $("#toast");
    const inner = $("#toastInner");
    if (!el || !inner) return;

    el.dataset.kind = kind || "ok";
    inner.textContent = msg || "";
    el.classList.add("toast--show");

    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("toast--show"), 2600);
  }

  // ---------- modal ----------
  function openModal(id){
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.add("modal--open");
    document.body.style.overflow = "hidden";
  }
  function closeModal(id){
    const m = document.getElementById(id);
    if (!m) return;
    m.classList.remove("modal--open");
    document.body.style.overflow = "";
  }
  function closeAllModals(){
    $$(".modal.modal--open").forEach(m => m.classList.remove("modal--open"));
    document.body.style.overflow = "";
  }

  // close on backdrop click
  function bindModalBackdrop(id){
    const m = document.getElementById(id);
    if (!m) return;
    const backdrop = $(".modal__backdrop", m);
    if (!backdrop) return;
    backdrop.addEventListener("click", () => closeModal(id));
  }

  // ---------- API ----------
  async function apiGet(url){
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }
  async function apiPost(url, formObj){
    const fd = new FormData();
    Object.entries(formObj || {}).forEach(([k,v]) => fd.set(k, String(v)));
    const res = await fetch(url, { method: "POST", body: fd });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }

  // ---------- rendering ----------
  function statusBadgeClass(st){
    if (st === "up") return "badge badge--up";
    if (st === "down") return "badge badge--down";
    return "badge badge--warn";
  }

  function rowHtml(t){
    // Endpoint skal IKKE være kolonne i tabell lenger.
    // "Information" modal viser endpoint + extra.
    const enabled = Number(t.enabled ?? 1) === 1;

    return `
      <tr data-name="${escapeHtml(t.name)}">
        <td class="td-mono td-strong">${escapeHtml(t.name)}</td>
        <td class="td-mono">${escapeHtml(t.ip || "-")}</td>

        <td>
          <span class="${statusBadgeClass(t.status)}">
            <span class="dot"></span>
            <span class="status-text">${escapeHtml((t.status || "unknown").toUpperCase())}</span>
          </span>
        </td>

        <td class="col-interval">
          <div class="intervalWrap">
            <input class="input intervalInput" type="number" min="10" max="86400" step="1"
                   value="${escapeHtml(String(t.interval ?? 60))}"
                   data-interval="${escapeHtml(String(t.interval ?? 60))}"
                   data-name="${escapeHtml(t.name)}" />
            <span class="intervalSuffix">s</span>
          </div>
        </td>

        <td class="td-mono"><span class="last-ping">${escapeHtml(t.last_ping_human || "-")}</span></td>
        <td class="td-mono"><span class="last-resp">${escapeHtml(t.last_response_human || "-")}</span></td>

        <td style="text-align:right;">
          <div class="dropdown" data-dd="${escapeHtml(t.name)}">
            <button class="iconbtn" type="button" data-ddbtn="${escapeHtml(t.name)}" aria-label="Actions">⋯</button>
            <div class="dropdown__menu" data-ddmenu="${escapeHtml(t.name)}" role="menu">
              <button class="dropdown__item" data-action="info" data-name="${escapeHtml(t.name)}">Information</button>
              <button class="dropdown__item" data-action="edit" data-name="${escapeHtml(t.name)}">Edit</button>
              <div class="dropdown__sep"></div>
              <button class="dropdown__item" data-action="${enabled ? "disable" : "enable"}" data-name="${escapeHtml(t.name)}">
                ${enabled ? "Disable" : "Enable"}
              </button>
              <button class="dropdown__item" data-action="test" data-name="${escapeHtml(t.name)}">Test</button>
              <button class="dropdown__item dropdown__item--danger" data-action="remove" data-name="${escapeHtml(t.name)}">Remove</button>
            </div>
          </div>
        </td>
      </tr>
    `;
  }

  function applyFilter(list){
    const q = (state.filter || "").trim().toLowerCase();
    if (!q) return list;
    return list.filter(t => {
      const blob = [
        t.name, t.ip, t.status,
        t.last_ping_human, t.last_response_human,
      ].join(" ").toLowerCase();
      return blob.includes(q);
    });
  }

  function render(){
    const tbody = $("#targetsBody");
    if (!tbody) return;

    const filtered = applyFilter(state.targets);
    tbody.innerHTML = filtered.map(rowHtml).join("");

    bindIntervalInputs();
    bindDropdowns();

    $("#filterCount").textContent = String(filtered.length);
    $("#totalCount").textContent = String(state.targets.length);
  }

  // ---------- fetch state ----------
  async function refreshState(){
    try{
      const data = await apiGet("/state");
      state.targets = data.targets || [];
      render();
    }catch(e){
      // silent
    }
  }

  // ---------- interval editing ----------
  function bindIntervalInputs(){
    $$(".intervalInput").forEach(inp => {
      if (inp.dataset.bound === "1") return;
      inp.dataset.bound = "1";

      const name = inp.dataset.name;

      const commit = async () => {
        const raw = String(inp.value || "").trim();
        const n = parseInt(raw, 10);
        const prev = parseInt(inp.dataset.interval || "60", 10);

        if (!Number.isFinite(n) || n < 10 || n > 86400){
          toast("err", "Invalid interval (10–86400s)");
          inp.value = String(prev);
          return;
        }
        if (n === prev) return;

        inp.disabled = true;
        try{
          const r = await apiPost("/api/set-target-interval", { name, seconds: n });
          if (r.ok){
            inp.dataset.interval = String(n);
            toast("ok", r.message || `Interval set to ${n}s`);
            await refreshState();
          }else{
            inp.value = String(prev);
            toast("err", r.message || "Failed to set interval");
          }
        }catch(err){
          inp.value = String(prev);
          toast("err", err?.message || "Failed to set interval");
        }finally{
          inp.disabled = false;
        }
      };

      inp.addEventListener("keydown", (e) => {
        if (e.key === "Enter"){ e.preventDefault(); commit(); inp.blur(); }
        if (e.key === "Escape"){ inp.value = inp.dataset.interval || "60"; inp.blur(); }
      });
      inp.addEventListener("blur", commit);
    });
  }

  // ---------- dropdown ----------
  function closeAllDropdowns(){
    $$(".dropdown__menu").forEach(m => m.classList.remove("dropdown__menu--open"));
    state.menusOpenFor = null;
  }

  function bindDropdowns(){
    // open/close
    $$(".iconbtn[data-ddbtn]").forEach(btn => {
      if (btn.dataset.bound === "1") return;
      btn.dataset.bound = "1";

      btn.addEventListener("click", (e) => {
        e.stopPropagation();
        const name = btn.dataset.ddbtn;
        const menu = document.querySelector(`.dropdown__menu[data-ddmenu="${CSS.escape(name)}"]`);
        if (!menu) return;

        const open = menu.classList.contains("dropdown__menu--open");
        closeAllDropdowns();
        if (!open){
          menu.classList.add("dropdown__menu--open");
          state.menusOpenFor = name;
        }
      });
    });

    // menu actions
    $$(".dropdown__item[data-action]").forEach(item => {
      if (item.dataset.bound === "1") return;
      item.dataset.bound = "1";

      item.addEventListener("click", async (e) => {
        e.stopPropagation();
        closeAllDropdowns();

        const action = item.dataset.action;
        const name = item.dataset.name;

        try{
          if (action === "remove"){
            openConfirmRemove(name);
            return;
          }

          if (action === "info"){
            openInformation(name);
            return;
          }

          if (action === "edit"){
            openEdit(name);
            return;
          }

          if (action === "test"){
            toast("ok", `Testing ${name}…`);
            const r = await apiPost("/api/test", { name });
            toast(r.ok ? "ok" : "err", r.message || (r.ok ? "OK" : "Failed"));
            await refreshState();
            return;
          }

          if (action === "disable"){
            toast("ok", `Disabling ${name}…`);
            const r = await apiPost("/api/disable", { name });
            toast(r.ok ? "ok" : "err", r.message || (r.ok ? "Disabled" : "Failed"));
            await refreshState();
            return;
          }

          if (action === "enable"){
            toast("ok", `Enabling ${name}…`);
            const r = await apiPost("/api/enable", { name });
            toast(r.ok ? "ok" : "err", r.message || (r.ok ? "Enabled" : "Failed"));
            await refreshState();
            return;
          }

        }catch(err){
          toast("err", err?.message || "Action failed");
        }
      });
    });
  }

  document.addEventListener("click", () => closeAllDropdowns());

  // ---------- filtering ----------
  function bindFilter(){
    const inp = $("#filterInput");
    if (!inp) return;

    inp.addEventListener("input", () => {
      state.filter = inp.value || "";
      render();
    });
  }

  // ---------- logs ----------
  let rawLogs = "";
  function bindLogs(){
    bindModalBackdrop("logsModal");

    const btnOpen = $("#btnOpenLogs");
    const btnClose = $("#btnCloseLogs");
    const btnReload = $("#btnReloadLogs");
    const btnCopy = $("#btnCopyLogs");
    const box = $("#logsBox");
    const meta = $("#logsMeta");
    const filter = $("#logsFilter");
    const linesLbl = $("#logsLinesLbl");

    if (!btnOpen || !btnClose || !btnReload || !btnCopy || !box || !meta || !filter || !linesLbl) return;

    async function loadLogs(){
      const lines = parseInt(linesLbl.textContent || "200", 10) || 200;
      try{
        const data = await apiGet(`/logs?lines=${lines}`);
        rawLogs = data.text || "";
        meta.textContent = `${data.source || "logs"} • ${data.lines || 0} lines • ${data.updated || ""}`;
        applyFilterLogs();
        box.scrollTop = box.scrollHeight;
      }catch(e){
        rawLogs = "";
        box.textContent = `Failed to fetch logs: ${e?.message || "unknown"}`;
        meta.textContent = "error";
      }
    }

    function applyFilterLogs(){
      const q = (filter.value || "").trim().toLowerCase();
      if (!q){
        box.textContent = rawLogs || "(empty)";
        return;
      }
      const lines = (rawLogs || "").split("\n").filter(l => l.toLowerCase().includes(q));
      box.textContent = lines.join("\n") || "(no matches)";
    }

    btnOpen.addEventListener("click", async () => {
      openModal("logsModal");
      filter.focus();
      await loadLogs();
    });
    btnClose.addEventListener("click", () => closeModal("logsModal"));
    btnReload.addEventListener("click", async () => await loadLogs());
    btnCopy.addEventListener("click", async () => {
      try{
        await navigator.clipboard.writeText(box.textContent || "");
        toast("ok", "Logs copied");
      }catch(_){}
    });
    filter.addEventListener("input", applyFilterLogs);
  }

  // ---------- add target ----------
  function bindAdd(){
    bindModalBackdrop("addModal");

    const btnOpen = $("#btnOpenAdd");
    const btnCancel = $("#btnAddCancel");
    const form = $("#addForm");
    const btnSubmit = $("#btnAddSubmit");

    if (!btnOpen || !btnCancel || !form || !btnSubmit) return;

    btnOpen.addEventListener("click", () => openModal("addModal"));
    btnCancel.addEventListener("click", () => closeModal("addModal"));

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      btnSubmit.disabled = true;
      const prev = btnSubmit.textContent;
      btnSubmit.textContent = "Adding…";

      try{
        const fd = new FormData(form);
        const payload = {
          name: fd.get("name") || "",
          ip: fd.get("ip") || "",
          endpoint: fd.get("endpoint") || "",
          interval: fd.get("interval") || "60"
        };
        const r = await apiPost("/api/add", payload);
        if (r.ok){
          toast("ok", r.message || "Target added");
          form.reset();
          closeModal("addModal");
          await refreshState();
        }else{
          toast("err", r.message || "Failed to add");
        }
      }catch(err){
        toast("err", err?.message || "Failed to add");
      }finally{
        btnSubmit.disabled = false;
        btnSubmit.textContent = prev;
      }
    });
  }

  // ---------- remove confirm ----------
  function bindConfirmRemove(){
    bindModalBackdrop("removeModal");

    const btnCancel = $("#btnRemoveCancel");
    const btnConfirm = $("#btnRemoveConfirm");
    const nameEl = $("#removeName");

    if (!btnCancel || !btnConfirm || !nameEl) return;

    btnCancel.addEventListener("click", () => {
      state.pendingRemove = null;
      closeModal("removeModal");
    });

    btnConfirm.addEventListener("click", async () => {
      const name = state.pendingRemove;
      if (!name) return;

      btnConfirm.disabled = true;
      const prev = btnConfirm.textContent;
      btnConfirm.textContent = "Removing…";

      try{
        const r = await apiPost("/api/remove", { name });
        toast(r.ok ? "ok" : "err", r.message || (r.ok ? "Removed" : "Failed"));
        closeModal("removeModal");
        state.pendingRemove = null;
        await refreshState();
      }catch(err){
        toast("err", err?.message || "Failed");
      }finally{
        btnConfirm.disabled = false;
        btnConfirm.textContent = prev;
      }
    });

    function openConfirmRemove(name){
      state.pendingRemove = name;
      nameEl.textContent = name;
      openModal("removeModal");
    }

    // expose
    window.__interheartOpenRemove = openConfirmRemove;
  }

  function openConfirmRemove(name){
    if (typeof window.__interheartOpenRemove === "function") window.__interheartOpenRemove(name);
  }

  // ---------- information modal ----------
  function bindInformation(){
    bindModalBackdrop("infoModal");
    const btnClose = $("#btnInfoClose");
    if (btnClose) btnClose.addEventListener("click", () => closeModal("infoModal"));
  }

  function openInformation(name){
    const t = state.targets.find(x => x.name === name);
    if (!t){
      toast("err", "Target not found");
      return;
    }

    $("#infoName").textContent = t.name || "-";
    $("#infoIp").textContent = t.ip || "-";
    $("#infoStatus").textContent = (t.status || "unknown").toUpperCase();
    $("#infoInterval").textContent = String(t.interval ?? "-");
    $("#infoLastPing").textContent = t.last_ping_human || "-";
    $("#infoLastResp").textContent = t.last_response_human || "-";

    // endpoint + extra (backend bør sende disse)
    $("#infoEndpoint").textContent = t.endpoint || t.endpoint_masked || "-";
    $("#infoLatency").textContent = (t.last_rtt_ms ?? t.latency_ms ?? "-") + "";
    $("#infoEnabled").textContent = (Number(t.enabled ?? 1) === 1) ? "YES" : "NO";

    openModal("infoModal");
  }

  // ---------- edit modal ----------
  function bindEdit(){
    bindModalBackdrop("editModal");

    const btnCancel = $("#btnEditCancel");
    const form = $("#editForm");
    const btnSave = $("#btnEditSave");

    if (btnCancel) btnCancel.addEventListener("click", () => closeModal("editModal"));
    if (!form || !btnSave) return;

    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      btnSave.disabled = true;
      const prev = btnSave.textContent;
      btnSave.textContent = "Saving…";

      try{
        const fd = new FormData(form);
        const payload = {
          old_name: fd.get("old_name") || "",
          new_name: fd.get("new_name") || "",
          ip: fd.get("ip") || "",
          endpoint: fd.get("endpoint") || "",
          interval: fd.get("interval") || "60",
          enabled: fd.get("enabled") || "1"
        };
        const r = await apiPost("/api/edit", payload);
        toast(r.ok ? "ok" : "err", r.message || (r.ok ? "Updated" : "Failed"));
        if (r.ok){
          closeModal("editModal");
          await refreshState();
        }
      }catch(err){
        toast("err", err?.message || "Failed to save");
      }finally{
        btnSave.disabled = false;
        btnSave.textContent = prev;
      }
    });
  }

  function openEdit(name){
    const t = state.targets.find(x => x.name === name);
    if (!t){
      toast("err", "Target not found");
      return;
    }

    // fyll form
    $("#editOldName").value = t.name || "";
    $("#editNewName").value = t.name || "";
    $("#editIp").value = t.ip || "";
    $("#editEndpoint").value = t.endpoint || "";
    $("#editInterval").value = String(t.interval ?? 60);
    $("#editEnabled").value = String(Number(t.enabled ?? 1));

    openModal("editModal");
  }

  // ---------- Run now (realtime) ----------
  function bindRunNow(){
    bindModalBackdrop("runModal");

    const btn = $("#btnRunNow");
    const btnClose = $("#btnRunClose");

    if (btnClose) btnClose.addEventListener("click", () => closeModal("runModal"));
    if (!btn) return;

    const runLive = $("#runLive");
    const runLiveText = $("#runLiveText");
    const runTitleMeta = $("#runTitleMeta");

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
    const runRaw = $("#runRaw");
    const runHintBox = $("#runHintBox");
    const runHintText = $("#runHintText");

    function setBar(done, due){
      const d = Number(done || 0);
      const du = Number(due || 0);
      const pct = (!du || du <= 0) ? 0 : Math.max(0, Math.min(100, Math.round((d / du) * 100)));
      runBar.style.width = pct + "%";
    }

    function clearWorking(){
      $$("tr[data-name]").forEach(r => r.classList.remove("working"));
    }
    function highlightWorking(name){
      $$("tr[data-name]").forEach(r => {
        if (r.getAttribute("data-name") === name) r.classList.add("working");
        else r.classList.remove("working");
      });
    }

    function setRunModalInitial(){
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
      runRaw.style.display = "none";
      runHintBox.style.display = "none";
      setBar(0, 0);
    }

    function applyRunResult(data){
      const ts = new Date().toLocaleString();
      runTitleMeta.textContent = ts;

      const summary = data.summary || null;

      if (summary){
        mTotal.textContent = String(summary.total ?? "-");
        mDue.textContent = String(summary.due ?? "-");
        mSkipped.textContent = String(summary.skipped ?? "-");
        mOk.textContent = String(summary.ping_ok ?? "-");
        mFail.textContent = String(summary.ping_fail ?? "-");
        mSent.textContent = String(summary.sent ?? "-");
        mCurlFail.textContent = String(summary.curl_fail ?? "-");

        const due = Number(summary.due || 0);
        setBar(due, due);
        runNowLine.textContent = data.ok ? "Completed" : "Failed";
        runDoneLine.textContent = `done: ${due} / ${due}`;

        if (due === 0 && Number(summary.total || 0) > 0){
          runHintBox.style.display = "block";
          runHintText.textContent = "Nothing was checked. Verify timer permissions and runtime state.";
        }
      }else{
        runRaw.textContent = data.message || "-";
        runRaw.style.display = "block";
        runNowLine.textContent = data.ok ? "Completed" : "Failed";
      }

      toast(data.ok ? "ok" : "err", data.ok ? "Run completed" : (data.message || "Run failed"));
    }

    async function fetchRuntime(){
      try{
        return await apiGet("/runtime");
      }catch(_){
        return null;
      }
    }
    async function fetchRunStatus(){
      try{
        return await apiGet("/api/run-status");
      }catch(_){
        return null;
      }
    }
    async function fetchRunResult(){
      try{
        return await apiGet("/api/run-result");
      }catch(_){
        return null;
      }
    }

    function stopRuntimePoll(){
      if (state.run.runtimePoll){
        clearInterval(state.run.runtimePoll);
        state.run.runtimePoll = null;
      }
    }
    function stopStatusPoll(){
      if (state.run.statusPoll){
        clearInterval(state.run.statusPoll);
        state.run.statusPoll = null;
      }
    }

    function startRuntimePoll(){
      stopRuntimePoll();
      state.run.lastRuntimeUpdated = 0;

      state.run.runtimePoll = setInterval(async () => {
        const rt = await fetchRuntime();
        if (!rt) return;

        const upd = Number(rt.updated || 0);
        if (upd && upd === state.run.lastRuntimeUpdated) return;
        if (upd) state.run.lastRuntimeUpdated = upd;

        if (rt.status === "running"){
          runLive.style.display = "inline-flex";
          runLiveText.textContent = "Running…";

          const cur = String(rt.current || "").trim();
          if (cur){
            highlightWorking(cur);
            runNowLine.textContent = "Now checking: " + cur;
          }else{
            runNowLine.textContent = "Running…";
          }

          const done = Number(rt.done || 0);
          const due = Number(rt.due || 0);
          runDoneLine.textContent = `done: ${done} / ${due}`;
          setBar(done, due);
        }
      }, 250);
    }

    function startStatusPoll(){
      stopStatusPoll();
      state.run.statusPoll = setInterval(async () => {
        const st = await fetchRunStatus();
        if (!st) return;

        if (st.running){
          runTitleMeta.textContent = "running…";
          runLive.style.display = "inline-flex";
          return;
        }

        if (st.finished){
          stopStatusPoll();
          stopRuntimePoll();
          clearWorking();
          runLive.style.display = "none";
          const result = await fetchRunResult();
          if (result) applyRunResult(result);
        }
      }, 300);
    }

    btn.addEventListener("click", async () => {
      btn.disabled = true;
      setRunModalInitial();
      openModal("runModal");

      startRuntimePoll();
      startStatusPoll();

      try{
        const r = await apiPost("/api/run-now", {});
        if (!r.ok){
          stopStatusPoll();
          stopRuntimePoll();
          clearWorking();
          runLive.style.display = "none";
          runRaw.textContent = r.message || "Failed to start run";
          runRaw.style.display = "block";
          runNowLine.textContent = "Failed";
          toast("err", r.message || "Run failed");
        }else{
          runNowLine.textContent = "Started…";
        }
      }catch(err){
        stopStatusPoll();
        stopRuntimePoll();
        clearWorking();
        runLive.style.display = "none";
        runRaw.textContent = err?.message || "Run failed";
        runRaw.style.display = "block";
        runNowLine.textContent = "Failed";
        toast("err", err?.message || "Run failed");
      }finally{
        btn.disabled = false;
        await refreshState();
      }
    });
  }

  // ---------- init ----------
  function init(){
    bindFilter();
    bindLogs();
    bindAdd();
    bindConfirmRemove();
    bindInformation();
    bindEdit();
    bindRunNow();

    // esc closes
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape"){
        closeAllDropdowns();
        closeAllModals();
      }
    });

    refreshState();
    setInterval(refreshState, 2000);
  }

  // expose remove open helper
  window.openConfirmRemove = openConfirmRemove;

  init();

})();
