/* interheart webui (legacy UX migrated) */
(function () {
  "use strict";

  const CFG = window.APP_CONFIG || {};
  const ICONS = window.ICONS || {};

  const POLL_SECONDS = Number(CFG.poll_seconds || 2);
  const LOG_LINES = Number(CFG.log_lines || 200);

  // ---------- helpers ----------
  function $(sel, root = document) { return root.querySelector(sel); }
  function $all(sel, root = document) { return Array.from(root.querySelectorAll(sel)); }

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function ico(name) {
    // returns HTML string for <span class="ico">...</span>
    const svg = ICONS[name] || "";
    return `<span class="ico">${svg}</span>`;
  }

  function show(el) {
    if (!el) return;
    el.classList.add("show");
    el.setAttribute("aria-hidden", "false");
  }
  function hide(el) {
    if (!el) return;
    el.classList.remove("show");
    el.setAttribute("aria-hidden", "true");
  }

  function captureDefaultHtml(btn) {
    if (!btn) return;
    if (!btn.dataset.defaultHtml || btn.dataset.defaultHtml === "") {
      btn.dataset.defaultHtml = btn.innerHTML;
    }
  }

  async function fetchJson(url, opts) {
    const res = await fetch(url, Object.assign({ cache: "no-store" }, opts || {}));
    let data = null;
    try { data = await res.json(); } catch (_) {}
    if (!res.ok) {
      const msg = (data && (data.message || data.error)) ? (data.message || data.error) : `HTTP ${res.status}`;
      throw new Error(msg);
    }
    return data;
  }

  async function postForm(url, formData) {
    return await fetchJson(url, { method: "POST", body: formData });
  }

  // ---------- toasts ----------
  const toasts = $("#toasts");

  function toast(title, msg) {
    if (!toasts) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `
      <div>
        <b>${escapeHtml(title)}</b>
        <p>${escapeHtml(msg || "")}</p>
      </div>
      <button class="x" aria-label="Close">×</button>
    `;
    $(".x", el).onclick = () => el.remove();
    toasts.appendChild(el);
    setTimeout(() => { if (el && el.parentNode) el.remove(); }, 5200);
  }

  // ---------- modals ----------
  const logModal = $("#logModal");
  const runModal = $("#runModal");
  const addModal = $("#addModal");
  const confirmModal = $("#confirmModal");

  function closeAllModals() {
    [logModal, runModal, addModal, confirmModal].forEach(hide);
  }

  // ---------- logs modal ----------
  const openLogsBtn = $("#openLogs");
  const closeLogsBtn = $("#btnCloseLogs");
  const reloadLogsBtn = $("#btnReloadLogs");
  const copyLogsBtn = $("#btnCopyLogs");
  const logBox = $("#logBox");
  const logMeta = $("#logMeta");
  const logFilter = $("#logFilter");
  const logLinesLbl = $("#logLinesLbl");

  let rawLog = "";

  async function loadLogs() {
    if (!logBox) return;
    try {
      const data = await fetchJson(`/logs?lines=${encodeURIComponent(String(LOG_LINES))}`);
      rawLog = data.text || "";
      if (logMeta) {
        logMeta.textContent = `${data.source || "log"} • ${(data.lines || 0)} lines • ${(data.updated || "")}`;
      }
      applyLogFilter();
      logBox.scrollTop = logBox.scrollHeight;
    } catch (e) {
      rawLog = "";
      logBox.textContent = "Failed to fetch logs: " + (e && e.message ? e.message : "unknown");
      if (logMeta) logMeta.textContent = "error";
    }
  }

  function applyLogFilter() {
    if (!logBox) return;
    const q = String(logFilter?.value || "").trim().toLowerCase();
    if (!q) {
      logBox.textContent = rawLog || "(empty)";
      return;
    }
    const lines = (rawLog || "").split("\n").filter((l) => l.toLowerCase().includes(q));
    logBox.textContent = lines.join("\n") || "(no matches)";
  }

  if (logLinesLbl) logLinesLbl.textContent = String(LOG_LINES);

  openLogsBtn?.addEventListener("click", async () => {
    show(logModal);
    logFilter?.focus();
    await loadLogs();
  });
  closeLogsBtn?.addEventListener("click", () => hide(logModal));
  reloadLogsBtn?.addEventListener("click", async () => await loadLogs());
  copyLogsBtn?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(logBox?.textContent || "");
      toast("Copied", "Logs copied to clipboard");
    } catch (_) {}
  });
  logFilter?.addEventListener("input", applyLogFilter);
  logModal?.addEventListener("click", (e) => { if (e.target === logModal) hide(logModal); });

  // ---------- add modal ----------
  const openAddBtn = $("#openAdd");
  const addCancelBtn = $("#btnAddCancel");
  const addForm = $("#addForm");
  const btnAddSubmit = $("#btnAddSubmit");

  captureDefaultHtml(btnAddSubmit);

  openAddBtn?.addEventListener("click", () => show(addModal));
  addCancelBtn?.addEventListener("click", () => hide(addModal));
  addModal?.addEventListener("click", (e) => { if (e.target === addModal) hide(addModal); });

  addForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    if (!btnAddSubmit) return;

    btnAddSubmit.disabled = true;
    btnAddSubmit.innerHTML = "Adding…";
    try {
      const fd = new FormData(addForm);
      const data = await postForm("/api/add", fd);
      if (data.ok) {
        toast("Added", data.message || "Target added");
        hide(addModal);
        addForm.reset();
        await refreshState(true);
      } else {
        toast("Error", data.message || "Failed to add");
      }
    } catch (err) {
      toast("Error", err && err.message ? err.message : "Failed to add");
    } finally {
      btnAddSubmit.disabled = false;
      btnAddSubmit.innerHTML = btnAddSubmit.dataset.defaultHtml || (ico("plus") + " Add target");
    }
  });

  // ---------- confirm remove modal ----------
  const btnCloseConfirm = $("#btnCloseConfirm");
  const btnCancelRemove = $("#btnCancelRemove");
  const btnConfirmRemove = $("#btnConfirmRemove");
  const confirmNameEl = $("#confirmName");
  let pendingRemoveName = null;

  function openConfirmRemove(name) {
    pendingRemoveName = name;
    if (confirmNameEl) confirmNameEl.textContent = name;
    show(confirmModal);
  }

  function closeConfirmRemove() {
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
    try {
      const fd = new FormData();
      fd.set("name", name);
      const data = await postForm("/api/remove", fd);
      toast(data.ok ? "Removed" : "Error", data.message || (data.ok ? "Done" : "Failed"));
      closeConfirmRemove();
    } catch (e) {
      toast("Error", e && e.message ? e.message : "Failed");
    } finally {
      btnConfirmRemove.disabled = false;
      btnConfirmRemove.textContent = "Remove";
      await refreshState(true);
    }
  });

  // ---------- dropdown actions ----------
  function closeAllMenus() {
    $all(".menu.show").forEach((m) => m.classList.remove("show"));
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".menu-btn");
    if (btn) {
      const menu = btn.closest(".menu");
      const isOpen = menu.classList.contains("show");
      closeAllMenus();
      if (!isOpen) menu.classList.add("show");
      return;
    }
    if (!e.target.closest(".menu")) closeAllMenus();
  });

  function attachMenuActions() {
    $all('tr[data-name]').forEach((row) => {
      const name = row.getAttribute("data-name");
      $all(".menu-item", row).forEach((btn) => {
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";
        btn.addEventListener("click", async () => {
          closeAllMenus();
          const action = btn.getAttribute("data-action");
          if (action === "remove") {
            openConfirmRemove(name);
            return;
          }

          const fd = new FormData();
          fd.set("name", name);

          try {
            if (action === "test") {
              toast("Testing", `Running test for ${name}…`);
              const data = await postForm("/api/test", fd);
              toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
            }
          } catch (e) {
            toast("Error", e && e.message ? e.message : "Failed");
          } finally {
            await refreshState(true);
          }
        });
      });
    });
  }

  // ---------- inline interval editing ----------
  async function setIntervalFor(name, seconds) {
    const fd = new FormData();
    fd.set("name", name);
    fd.set("seconds", String(seconds));
    return await postForm("/api/set-target-interval", fd);
  }

  function attachIntervalHandlers() {
    $all('tr[data-name]').forEach((row) => {
      const name = row.getAttribute("data-name");
      const input = $(".interval-input", row);
      if (!input || input.dataset.bound === "1") return;
      input.dataset.bound = "1";

      const commit = async () => {
        const v = String(input.value || "").trim();
        const n = parseInt(v, 10);
        if (!Number.isFinite(n) || n < 10 || n > 86400) {
          toast("Invalid interval", "Use 10–86400 seconds");
          input.value = input.getAttribute("data-interval") || "60";
          return;
        }
        if (String(n) === String(input.getAttribute("data-interval"))) return;

        input.disabled = true;
        try {
          const r = await setIntervalFor(name, n);
          if (r.ok) {
            toast("Updated", r.message || `Interval set to ${n}s`);
            input.setAttribute("data-interval", String(n));
          } else {
            toast("Error", r.message || "Failed to set interval");
            input.value = input.getAttribute("data-interval") || "60";
          }
        } catch (e) {
          toast("Error", e && e.message ? e.message : "Failed to set interval");
          input.value = input.getAttribute("data-interval") || "60";
        } finally {
          input.disabled = false;
        }
      };

      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") { e.preventDefault(); commit(); input.blur(); }
        if (e.key === "Escape") { input.value = input.getAttribute("data-interval") || "60"; input.blur(); }
      });
      input.addEventListener("blur", commit);
    });
  }

  // ---------- run summary modal ----------
  const btnRunNow = $("#btnRunNow");
  const btnCloseRun = $("#btnCloseRun");

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
  const runRaw = $("#runRaw");
  const runHintBox = $("#runHintBox");
  const runHintText = $("#runHintText");

  captureDefaultHtml(btnRunNow);

  btnCloseRun?.addEventListener("click", () => hide(runModal));
  runModal?.addEventListener("click", (e) => { if (e.target === runModal) hide(runModal); });

  function setBar(done, due) {
    const pct = (!due || due <= 0) ? 0 : Math.max(0, Math.min(100, Math.round((done / due) * 100)));
    if (runBar) runBar.style.width = pct + "%";
  }

  let runtimePoll = null;
  let statusPoll = null;
  let lastRuntimeUpdated = 0;

  function highlightWorking(name) {
    $all('tr[data-name]').forEach((r) => {
      if (r.getAttribute("data-name") === name) r.classList.add("working");
      else r.classList.remove("working");
    });
  }

  function clearWorking() {
    $all('tr[data-name]').forEach((r) => r.classList.remove("working"));
  }

  async function fetchRuntime() {
    try { return await fetchJson("/runtime"); } catch (_) { return null; }
  }
  async function fetchRunStatus() {
    try { return await fetchJson("/api/run-status"); } catch (_) { return null; }
  }
  async function fetchRunResult() {
    try { return await fetchJson("/api/run-result"); } catch (_) { return null; }
  }

  function startRuntimePoll() {
    stopRuntimePoll();
    lastRuntimeUpdated = 0;
    runtimePoll = setInterval(async () => {
      const rt = await fetchRuntime();
      if (!rt) return;

      const upd = Number(rt.updated || 0);
      if (upd && upd === lastRuntimeUpdated) return;
      if (upd) lastRuntimeUpdated = upd;

      if (rt.status === "running") {
        if (runLive) runLive.style.display = "inline-flex";
        if (runLiveText) runLiveText.textContent = "Running…";

        const cur = String(rt.current || "").trim();
        if (cur) {
          highlightWorking(cur);
          if (runNowLine) runNowLine.textContent = "Now checking: " + cur;
        } else {
          if (runNowLine) runNowLine.textContent = "Running…";
        }

        const done = Number(rt.done || 0);
        const due = Number(rt.due || 0);
        if (runDoneLine) runDoneLine.textContent = `done: ${done} / ${due}`;
        setBar(done, due);
      }
    }, 250);
  }

  function startStatusPoll() {
    stopStatusPoll();
    statusPoll = setInterval(async () => {
      const st = await fetchRunStatus();
      if (!st) return;

      if (st.running) {
        if (runTitleMeta) runTitleMeta.textContent = "running…";
        if (runLive) runLive.style.display = "inline-flex";
      } else if (st.finished) {
        stopStatusPoll();
        stopRuntimePoll();
        clearWorking();
        if (runLive) runLive.style.display = "none";
        const result = await fetchRunResult();
        if (result) applyRunResult(result);
      }
    }, 300);
  }

  function stopRuntimePoll() {
    if (runtimePoll) { clearInterval(runtimePoll); runtimePoll = null; }
  }
  function stopStatusPoll() {
    if (statusPoll) { clearInterval(statusPoll); statusPoll = null; }
  }

  function setRunModalInitial() {
    if (runTitleMeta) runTitleMeta.textContent = "running…";
    if (runLive) runLive.style.display = "inline-flex";
    if (runLiveText) runLiveText.textContent = "Running…";

    if (mTotal) mTotal.textContent = "-";
    if (mDue) mDue.textContent = "-";
    if (mSkipped) mSkipped.textContent = "-";
    if (mOk) mOk.textContent = "-";
    if (mFail) mFail.textContent = "-";
    if (mSent) mSent.textContent = "-";
    if (mCurlFail) mCurlFail.textContent = "-";

    if (runNowLine) runNowLine.textContent = "Starting…";
    if (runDoneLine) runDoneLine.textContent = "done: 0 / 0";

    if (runRaw) { runRaw.style.display = "none"; runRaw.textContent = ""; }
    if (runHintBox) runHintBox.style.display = "none";

    setBar(0, 0);
  }

  function applyRunResult(data) {
    const ts = new Date().toLocaleString();
    if (runTitleMeta) runTitleMeta.textContent = ts;

    const summary = data.summary || null;

    if (summary) {
      if (mTotal) mTotal.textContent = String(summary.total ?? "-");
      if (mDue) mDue.textContent = String(summary.due ?? "-");
      if (mSkipped) mSkipped.textContent = String(summary.skipped ?? "-");
      if (mOk) mOk.textContent = String(summary.ping_ok ?? "-");
      if (mFail) mFail.textContent = String(summary.ping_fail ?? "-");
      if (mSent) mSent.textContent = String(summary.sent ?? "-");
      if (mCurlFail) mCurlFail.textContent = String(summary.curl_fail ?? "-");

      const due = Number(summary.due || 0);
      setBar(due, due);

      if (runNowLine) runNowLine.textContent = data.ok ? "Completed" : "Failed";
      if (runDoneLine) runDoneLine.textContent = `done: ${due} / ${due}`;

      if (due === 0 && Number(summary.total || 0) > 0) {
        if (runHintBox) runHintBox.style.display = "block";
        if (runHintText) runHintText.textContent =
          "Nothing was checked. If this keeps happening, verify permissions and systemd timer state.";
      }
    } else {
      if (runRaw) {
        runRaw.textContent = data.message || "-";
        runRaw.style.display = "block";
      }
      if (runNowLine) runNowLine.textContent = data.ok ? "Completed" : "Failed";
    }

    toast(data.ok ? "Run completed" : "Run failed", data.ok ? "Done" : (data.message || "Error"));
  }

  btnRunNow?.addEventListener("click", async () => {
    btnRunNow.disabled = true;

    setRunModalInitial();
    show(runModal);

    startRuntimePoll();
    startStatusPoll();

    try {
      const data = await fetchJson("/api/run-now", { method: "POST" });
      if (!data.ok) {
        stopStatusPoll();
        stopRuntimePoll();
        clearWorking();
        if (runLive) runLive.style.display = "none";
        toast("Run failed", data.message || "Failed to start run");
        if (runRaw) { runRaw.textContent = data.message || "Failed to start run"; runRaw.style.display = "block"; }
        if (runNowLine) runNowLine.textContent = "Failed";
      } else {
        if (runNowLine) runNowLine.textContent = "Started…";
      }
    } catch (e) {
      stopStatusPoll();
      stopRuntimePoll();
      clearWorking();
      if (runLive) runLive.style.display = "none";
      toast("Run failed", e && e.message ? e.message : "Error");
      if (runRaw) { runRaw.textContent = e && e.message ? e.message : "Run failed"; runRaw.style.display = "block"; }
      if (runNowLine) runNowLine.textContent = "Failed";
    } finally {
      btnRunNow.disabled = false;
      await refreshState(true);
    }
  });

  // ---------- real-time refresh + row blink ----------
  function setStatusChip(row, status) {
    const chip = $(".status-chip", row);
    const text = $(".status-text", row);
    if (!chip || !text) return;

    chip.classList.remove("status-up", "status-down", "status-unknown");
    if (status === "up") chip.classList.add("status-up");
    else if (status === "down") chip.classList.add("status-down");
    else chip.classList.add("status-unknown");

    text.textContent = String(status || "unknown").toUpperCase();
  }

  function flashIfChanged(el, newText) {
    if (!el) return false;
    const txt = String(newText ?? "-");
    if (el.textContent !== txt) {
      el.textContent = txt;
      el.classList.remove("flash");
      void el.offsetWidth; // reflow
      el.classList.add("flash");
      return true;
    }
    return false;
  }

  function blinkRow(row, ok) {
    if (!row) return;
    row.classList.remove("blink-ok", "blink-bad");
    void row.offsetWidth;
    row.classList.add(ok ? "blink-ok" : "blink-bad");
    setTimeout(() => row.classList.remove("blink-ok", "blink-bad"), 1000);
  }

  async function refreshState(force = false) {
    try {
      const data = await fetchJson("/state");
      const map = new Map();
      (data.targets || []).forEach((t) => map.set(t.name, t));

      $all('tr[data-name]').forEach((row) => {
        const name = row.getAttribute("data-name");
        const t = map.get(name);
        if (!t) return;

        setStatusChip(row, t.status);

        const prevPing = parseInt(row.getAttribute("data-last-ping") || "0", 10);
        const newPing = parseInt(String(t.last_ping_epoch || 0), 10);

        if (newPing && newPing !== prevPing) {
          row.setAttribute("data-last-ping", String(newPing));
          blinkRow(row, t.status === "up");
        }

        flashIfChanged($(".last-ping", row), t.last_ping_human || "-");
        flashIfChanged($(".last-resp", row), t.last_response_human || "-");

        const iv = $(".interval-input", row);
        if (iv && force) {
          iv.value = String(t.interval || 60);
          iv.setAttribute("data-interval", String(t.interval || 60));
        }

        const ep = $(".endpoint", row);
        if (ep) ep.textContent = t.endpoint_masked || "-";
      });

      attachIntervalHandlers();
      attachMenuActions();
    } catch (_) {
      // silent on purpose
    }
  }

  // init bindings
  attachIntervalHandlers();
  attachMenuActions();

  setInterval(() => refreshState(false), Math.max(1, POLL_SECONDS) * 1000);

  // ESC closes modals + menus
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (logModal?.classList.contains("show")) hide(logModal);
      if (addModal?.classList.contains("show")) hide(addModal);
      if (runModal?.classList.contains("show")) hide(runModal);
      if (confirmModal?.classList.contains("show")) hide(confirmModal);
      closeAllMenus();
    }
  });

})();
