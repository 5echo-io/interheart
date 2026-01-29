/* interheart webui - app.js
   Migrated from legacy inline JS (v4.6-ish) to split static file.
*/
(function () {
  // ---- helpers ----
  const cfg = window.__INTERHEART__ || {};
  const POLL_SECONDS = Number(cfg.pollSeconds || 2);
  const LOG_LINES = Number(cfg.logLines || 200);

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function escapeHtml(s) {
    return String(s ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  // ---- toasts ----
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
    const x = $(".x", el);
    if (x) x.onclick = () => el.remove();
    toasts.appendChild(el);
    setTimeout(() => {
      if (el && el.parentNode) el.remove();
    }, 5200);
  }

  // ---- modal helpers ----
  function showModal(el) {
    if (!el) return;
    el.classList.add("show");
    el.setAttribute("aria-hidden", "false");
  }
  function hideModal(el) {
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

  async function apiPost(url, formData) {
    const res = await fetch(url, { method: "POST", body: formData });
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
  let rawLog = "";

  async function loadLogs() {
    try {
      const res = await fetch(`/logs?lines=${encodeURIComponent(String(LOG_LINES))}`, { cache: "no-store" });
      const data = await res.json();
      rawLog = data.text || "";
      if (logMeta) {
        logMeta.textContent =
          (data.source || "log") +
          " • " +
          (data.lines || 0) +
          " lines • " +
          (data.updated || "");
      }
      applyLogFilter();
      if (logBox) logBox.scrollTop = logBox.scrollHeight;
    } catch (e) {
      rawLog = "";
      if (logBox) logBox.textContent = "Failed to fetch logs: " + (e && e.message ? e.message : "unknown");
      if (logMeta) logMeta.textContent = "error";
    }
  }

  function applyLogFilter() {
    if (!logBox) return;
    const q = (logFilter?.value || "").trim().toLowerCase();
    if (!q) {
      logBox.textContent = rawLog || "(empty)";
      return;
    }
    const lines = (rawLog || "").split("\n").filter((l) => l.toLowerCase().includes(q));
    logBox.textContent = lines.join("\n") || "(no matches)";
  }

  if (openLogs) {
    openLogs.addEventListener("click", async () => {
      showModal(logModal);
      if (logFilter) logFilter.focus();
      await loadLogs();
    });
  }
  if (closeLogs) closeLogs.addEventListener("click", () => hideModal(logModal));
  if (reloadLogs) reloadLogs.addEventListener("click", async () => await loadLogs());
  if (copyLogs) {
    copyLogs.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(logBox?.textContent || "");
        toast("Copied", "Logs copied to clipboard");
      } catch (e) {
        // ignore
      }
    });
  }
  if (logFilter) logFilter.addEventListener("input", applyLogFilter);
  if (logModal) {
    logModal.addEventListener("click", (e) => {
      if (e.target === logModal) hideModal(logModal);
    });
  }

  // ---- Add modal ----
  const addModal = $("#addModal");
  const openAdd = $("#openAdd");
  const addCancel = $("#btnAddCancel");
  const addForm = $("#addForm");
  const btnAddSubmit = $("#btnAddSubmit");
  captureDefaultHtml(btnAddSubmit);

  if (openAdd) openAdd.addEventListener("click", () => showModal(addModal));
  if (addCancel) addCancel.addEventListener("click", () => hideModal(addModal));
  if (addModal) {
    addModal.addEventListener("click", (e) => {
      if (e.target === addModal) hideModal(addModal);
    });
  }

  if (addForm) {
    addForm.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (!btnAddSubmit) return;

      btnAddSubmit.disabled = true;
      btnAddSubmit.innerHTML = "Adding…";
      try {
        const fd = new FormData(addForm);
        const res = await fetch("/api/add", { method: "POST", body: fd });
        const data = await res.json();
        if (data.ok) {
          toast("Added", data.message || "Target added");
          hideModal(addModal);
          addForm.reset();
          await refreshState(true);
        } else {
          toast("Error", data.message || "Failed to add");
        }
      } catch (err) {
        toast("Error", err && err.message ? err.message : "Failed to add");
      } finally {
        btnAddSubmit.disabled = false;
        btnAddSubmit.innerHTML = btnAddSubmit.dataset.defaultHtml || "Add target";
      }
    });
  }

  // ---- Confirm remove modal ----
  const confirmModal = $("#confirmModal");
  const btnCloseConfirm = $("#btnCloseConfirm");
  const btnCancelRemove = $("#btnCancelRemove");
  const btnConfirmRemove = $("#btnConfirmRemove");
  const confirmName = $("#confirmName");
  let pendingRemoveName = null;

  function openConfirmRemove(name) {
    pendingRemoveName = name;
    if (confirmName) confirmName.textContent = name;
    showModal(confirmModal);
  }

  function closeConfirmRemove() {
    pendingRemoveName = null;
    hideModal(confirmModal);
  }

  if (btnCloseConfirm) btnCloseConfirm.addEventListener("click", closeConfirmRemove);
  if (btnCancelRemove) btnCancelRemove.addEventListener("click", closeConfirmRemove);
  if (confirmModal) {
    confirmModal.addEventListener("click", (e) => {
      if (e.target === confirmModal) closeConfirmRemove();
    });
  }

  async function removeTarget(name) {
    const fd = new FormData();
    fd.set("name", name);
    return await apiPost("/api/remove", fd);
  }

  if (btnConfirmRemove) {
    btnConfirmRemove.addEventListener("click", async () => {
      const name = pendingRemoveName;
      if (!name) return;

      btnConfirmRemove.disabled = true;
      btnConfirmRemove.textContent = "Removing…";
      try {
        const data = await removeTarget(name);
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
  }

  // ---- dropdown menus ----
  function closeAllMenus() {
    $$(".menu.show").forEach((m) => m.classList.remove("show"));
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

  // ---- Run summary modal + realtime polling ----
  const runModal = $("#runModal");
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

  if (btnCloseRun) btnCloseRun.addEventListener("click", () => hideModal(runModal));
  if (runModal) {
    runModal.addEventListener("click", (e) => {
      if (e.target === runModal) hideModal(runModal);
    });
  }

  function setBar(done, due) {
    if (!runBar) return;
    const pct =
      !due || due <= 0 ? 0 : Math.max(0, Math.min(100, Math.round((done / due) * 100)));
    runBar.style.width = pct + "%";
  }

  let runtimePoll = null;
  let statusPoll = null;
  let lastRuntimeUpdated = 0;

  async function fetchRuntime() {
    try {
      const res = await fetch("/runtime", { cache: "no-store" });
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  async function fetchRunStatus() {
    try {
      const res = await fetch("/api/run-status", { cache: "no-store" });
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  async function fetchRunResult() {
    try {
      const res = await fetch("/api/run-result", { cache: "no-store" });
      return await res.json();
    } catch (e) {
      return null;
    }
  }

  function highlightWorking(name) {
    $$('tr[data-name]').forEach((r) => {
      if (r.getAttribute("data-name") === name) r.classList.add("working");
      else r.classList.remove("working");
    });
  }

  function clearWorking() {
    $$('tr[data-name]').forEach((r) => r.classList.remove("working"));
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
    if (runtimePoll) {
      clearInterval(runtimePoll);
      runtimePoll = null;
    }
  }

  function stopStatusPoll() {
    if (statusPoll) {
      clearInterval(statusPoll);
      statusPoll = null;
    }
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
    if (runRaw) {
      runRaw.style.display = "none";
      runRaw.textContent = "";
    }
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
        if (runHintText) {
          runHintText.textContent =
            "Nothing was checked. If this keeps happening, verify permissions and systemd timer state.";
        }
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

  // ---- Run Now button ----
  const btnRunNow = $("#btnRunNow");
  captureDefaultHtml(btnRunNow);

  if (btnRunNow) {
    btnRunNow.addEventListener("click", async () => {
      btnRunNow.disabled = true;

      setRunModalInitial();
      showModal(runModal);

      startRuntimePoll();
      startStatusPoll();

      try {
        const res = await fetch("/api/run-now", { method: "POST" });
        const data = await res.json();

        if (!data.ok) {
          stopStatusPoll();
          stopRuntimePoll();
          clearWorking();
          if (runLive) runLive.style.display = "none";
          toast("Run failed", data.message || "Failed to start run");
          if (runRaw) {
            runRaw.textContent = data.message || "Failed to start run";
            runRaw.style.display = "block";
          }
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
        if (runRaw) {
          runRaw.textContent = e && e.message ? e.message : "Run failed";
          runRaw.style.display = "block";
        }
        if (runNowLine) runNowLine.textContent = "Failed";
      } finally {
        btnRunNow.disabled = false;
        await refreshState(true);
      }
    });
  }

  // ---- Inline interval editing ----
  async function setIntervalFor(name, seconds) {
    const fd = new FormData();
    fd.set("name", name);
    fd.set("seconds", String(seconds));
    return await apiPost("/api/set-target-interval", fd);
  }

  function attachIntervalHandlers() {
    $$('tr[data-name]').forEach((row) => {
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
        if (e.key === "Enter") {
          e.preventDefault();
          commit();
          input.blur();
        }
        if (e.key === "Escape") {
          input.value = input.getAttribute("data-interval") || "60";
          input.blur();
        }
      });
      input.addEventListener("blur", commit);
    });
  }

  // ---- Menu actions ----
  function attachMenuActions() {
    $$('tr[data-name]').forEach((row) => {
      const name = row.getAttribute("data-name");
      $$(".menu-item", row).forEach((btn) => {
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";

        btn.addEventListener("click", async () => {
          closeAllMenus();
          const action = btn.getAttribute("data-action");
          const fd = new FormData();
          fd.set("name", name);

          if (action === "remove") {
            openConfirmRemove(name);
            return;
          }

          try {
            let data;
            if (action === "test") {
              toast("Testing", `Running test for ${name}…`);
              data = await apiPost("/api/test", fd);
            } else {
              return;
            }
            toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
          } catch (e) {
            toast("Error", e && e.message ? e.message : "Failed");
          } finally {
            await refreshState(true);
          }
        });
      });
    });
  }

  // ---- Real-time refresh + row blink ----
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
    if (el.textContent !== newText) {
      el.textContent = newText;
      el.classList.remove("flash");
      void el.offsetWidth; // reflow to restart animation
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
      const res = await fetch("/state", { cache: "no-store" });
      const data = await res.json();

      const map = new Map();
      (data.targets || []).forEach((t) => map.set(t.name, t));

      $$('tr[data-name]').forEach((row) => {
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
    } catch (e) {
      // silent
    }
  }

  // ---- init ----
  attachIntervalHandlers();
  attachMenuActions();

  setInterval(() => refreshState(false), POLL_SECONDS * 1000);

  // ESC closes modals + menus
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;
    if (logModal?.classList.contains("show")) hideModal(logModal);
    if (addModal?.classList.contains("show")) hideModal(addModal);
    if (runModal?.classList.contains("show")) hideModal(runModal);
    if (confirmModal?.classList.contains("show")) hideModal(confirmModal);
    closeAllMenus();
  });
})();
