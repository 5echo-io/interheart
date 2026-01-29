(() => {
  "use strict";

  // ---------------------------
  // Helpers
  // ---------------------------
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

  function showModal(el) {
    if (!el) return;
    el.setAttribute("aria-hidden", "false");
  }

  function hideModal(el) {
    if (!el) return;
    el.setAttribute("aria-hidden", "true");
  }

  function isModalOpen(el) {
    return el && el.getAttribute("aria-hidden") === "false";
  }

  function captureDefaultHtml(btn) {
    if (!btn) return;
    if (!btn.dataset.defaultHtml) btn.dataset.defaultHtml = btn.innerHTML;
  }

  function sleep(ms) {
    return new Promise((r) => setTimeout(r, ms));
  }

  // ---------------------------
  // Toasts
  // ---------------------------
  const toasts = $("#toasts");
  function toast(title, msg) {
    if (!toasts) return;

    const el = document.createElement("div");
    el.className = "toast";
    el.innerHTML = `
      <div>
        <b>${escapeHtml(title)}</b>
        <div style="color: var(--muted); font-size: 12px; margin-top: 3px;">
          ${escapeHtml(msg || "")}
        </div>
      </div>
    `;
    toasts.appendChild(el);
    setTimeout(() => {
      if (el && el.parentNode) el.remove();
    }, 4500);
  }

  // ---------------------------
  // API helpers
  // ---------------------------
  async function getJson(url) {
    const res = await fetch(url, { cache: "no-store" });
    return await res.json();
  }

  async function postForm(url, formData) {
    const res = await fetch(url, { method: "POST", body: formData });
    return await res.json();
  }

  // ---------------------------
  // Logs modal
  // ---------------------------
  const logModal = $("#logModal");
  const openLogs = $("#openLogs");
  const btnCloseLogs = $("#btnCloseLogs");
  const btnReloadLogs = $("#btnReloadLogs");
  const btnCopyLogs = $("#btnCopyLogs");
  const logFilter = $("#logFilter");
  const logBox = $("#logBox");
  const logMeta = $("#logMeta");

  let rawLog = "";

  function applyLogFilter() {
    if (!logBox) return;
    const q = (logFilter?.value || "").trim().toLowerCase();
    if (!q) {
      logBox.textContent = rawLog || "(empty)";
      return;
    }
    const lines = (rawLog || "")
      .split("\n")
      .filter((l) => l.toLowerCase().includes(q));
    logBox.textContent = lines.join("\n") || "(no matches)";
  }

  async function loadLogs() {
    if (!logBox) return;
    try {
      // index.html kan sette data-lines på logModal eller logBox – hvis ikke, bruk 200
      const lines =
        Number(logModal?.dataset?.lines || logBox?.dataset?.lines || 200) || 200;

      const data = await getJson(`/logs?lines=${encodeURIComponent(lines)}`);
      rawLog = data.text || "";
      if (logMeta) {
        logMeta.textContent =
          `${data.source || "logs"} • ` +
          `${data.lines || 0} lines • ` +
          `${data.updated || ""}`;
      }
      applyLogFilter();
      logBox.scrollTop = logBox.scrollHeight;
    } catch (e) {
      rawLog = "";
      logBox.textContent =
        "Failed to fetch logs: " + (e?.message ? e.message : "unknown");
      if (logMeta) logMeta.textContent = "error";
    }
  }

  if (openLogs && logModal) {
    openLogs.addEventListener("click", async () => {
      showModal(logModal);
      await sleep(10);
      logFilter?.focus();
      await loadLogs();
    });
  }
  btnCloseLogs?.addEventListener("click", () => hideModal(logModal));
  btnReloadLogs?.addEventListener("click", loadLogs);
  btnCopyLogs?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(logBox?.textContent || "");
      toast("Copied", "Logs copied to clipboard");
    } catch {
      toast("Copy failed", "Browser blocked clipboard");
    }
  });
  logFilter?.addEventListener("input", applyLogFilter);
  logModal?.addEventListener("click", (e) => {
    if (e.target === logModal) hideModal(logModal);
  });

  // ---------------------------
  // Add modal
  // ---------------------------
  const addModal = $("#addModal");
  const openAdd = $("#openAdd");
  const btnAddCancel = $("#btnAddCancel");
  const addForm = $("#addForm");
  const btnAddSubmit = $("#btnAddSubmit");

  captureDefaultHtml(btnAddSubmit);

  openAdd?.addEventListener("click", () => showModal(addModal));
  btnAddCancel?.addEventListener("click", () => hideModal(addModal));
  addModal?.addEventListener("click", (e) => {
    if (e.target === addModal) hideModal(addModal);
  });

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
        addForm.reset();
        hideModal(addModal);
        await refreshState(true);
      } else {
        toast("Error", data.message || "Failed to add");
      }
    } catch (err) {
      toast("Error", err?.message || "Failed to add");
    } finally {
      btnAddSubmit.disabled = false;
      btnAddSubmit.innerHTML = btnAddSubmit.dataset.defaultHtml || "Add";
    }
  });

  // ---------------------------
  // Confirm remove modal
  // ---------------------------
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

  btnCloseConfirm?.addEventListener("click", closeConfirmRemove);
  btnCancelRemove?.addEventListener("click", closeConfirmRemove);
  confirmModal?.addEventListener("click", (e) => {
    if (e.target === confirmModal) closeConfirmRemove();
  });

  btnConfirmRemove?.addEventListener("click", async () => {
    const name = pendingRemoveName;
    if (!name || !btnConfirmRemove) return;

    btnConfirmRemove.disabled = true;
    btnConfirmRemove.textContent = "Removing…";

    try {
      const fd = new FormData();
      fd.set("name", name);
      const data = await postForm("/api/remove", fd);

      toast(data.ok ? "Removed" : "Error", data.message || (data.ok ? "Done" : "Failed"));
      closeConfirmRemove();
      await refreshState(true);
    } catch (e) {
      toast("Error", e?.message || "Failed");
    } finally {
      btnConfirmRemove.disabled = false;
      btnConfirmRemove.textContent = "Remove";
    }
  });

  // ---------------------------
  // Menu dropdown
  // ---------------------------
  function closeAllMenus() {
    $$(".menu").forEach((m) => {
      const dd = $(".menu-dd", m);
      dd?.classList.remove("open");
    });
  }

  document.addEventListener("click", (e) => {
    const btn = e.target.closest(".menu-btn");
    if (btn) {
      const menu = btn.closest(".menu");
      const dd = menu ? $(".menu-dd", menu) : null;
      const isOpen = dd?.classList.contains("open");

      closeAllMenus();
      if (!isOpen) dd?.classList.add("open");
      return;
    }

    if (!e.target.closest(".menu")) closeAllMenus();
  });

  // ---------------------------
  // Interval editing
  // ---------------------------
  async function setIntervalFor(name, seconds) {
    const fd = new FormData();
    fd.set("name", name);
    fd.set("seconds", String(seconds));
    return await postForm("/api/set-target-interval", fd);
  }

  function bindIntervalInputs(force = false) {
    $$('tr[data-name]').forEach((row) => {
      const name = row.getAttribute("data-name");
      const input = $(".interval-input", row);
      if (!input) return;

      if (force) {
        input.dataset.bound = "0";
      }
      if (input.dataset.bound === "1") return;
      input.dataset.bound = "1";

      const commit = async () => {
        const v = String(input.value || "").trim();
        const n = parseInt(v, 10);

        const fallback = input.getAttribute("data-interval") || "60";

        if (!Number.isFinite(n) || n < 10 || n > 86400) {
          toast("Invalid interval", "Use 10–86400 seconds");
          input.value = fallback;
          return;
        }

        if (String(n) === String(fallback)) return;

        input.disabled = true;
        try {
          const r = await setIntervalFor(name, n);
          if (r.ok) {
            toast("Updated", r.message || `Interval set to ${n}s`);
            input.setAttribute("data-interval", String(n));
          } else {
            toast("Error", r.message || "Failed to set interval");
            input.value = fallback;
          }
        } catch (e) {
          toast("Error", e?.message || "Failed to set interval");
          input.value = fallback;
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

  // ---------------------------
  // Row updates
  // ---------------------------
  function setStatusChip(row, status) {
    const chip = $(".status-chip", row);
    const text = $(".status-text", row);
    if (!chip || !text) return;

    chip.classList.remove("status-up", "status-down", "status-unknown");
    if (status === "up") chip.classList.add("status-up");
    else if (status === "down") chip.classList.add("status-down");
    else chip.classList.add("status-unknown");

    text.textContent = (status || "unknown").toUpperCase();
  }

  function flashIfChanged(el, newText) {
    if (!el) return;
    if (el.textContent !== newText) {
      el.textContent = newText;
      // enkel "flash" uten CSS-klasse avhengighet
      el.style.transition = "background .35s ease";
      el.style.background = "rgba(255,255,255,0.10)";
      setTimeout(() => (el.style.background = "transparent"), 260);
    }
  }

  // ---------------------------
  // Menu actions (test/remove)
  // ---------------------------
  async function apiTest(name) {
    const fd = new FormData();
    fd.set("name", name);
    return await postForm("/api/test", fd);
  }

  function bindMenuActions(force = false) {
    $$('tr[data-name]').forEach((row) => {
      const name = row.getAttribute("data-name");
      $$(".menu-item", row).forEach((btn) => {
        if (force) btn.dataset.bound = "0";
        if (btn.dataset.bound === "1") return;
        btn.dataset.bound = "1";

        btn.addEventListener("click", async () => {
          closeAllMenus();
          const action = btn.getAttribute("data-action");

          if (action === "remove") {
            openConfirmRemove(name);
            return;
          }

          if (action === "test") {
            toast("Testing", `Running test for ${name}…`);
            try {
              const data = await apiTest(name);
              toast(data.ok ? "OK" : "Error", data.message || (data.ok ? "Done" : "Failed"));
            } catch (e) {
              toast("Error", e?.message || "Failed");
            } finally {
              await refreshState(true);
            }
          }
        });
      });
    });
  }

  // ---------------------------
  // Run summary modal
  // ---------------------------
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
  const runRaw = $("#runRaw");
  const runHintBox = $("#runHintBox");
  const runHintText = $("#runHintText");

  btnCloseRun?.addEventListener("click", () => hideModal(runModal));
  runModal?.addEventListener("click", (e) => {
    if (e.target === runModal) hideModal(runModal);
  });

  captureDefaultHtml(btnRunNow);

  function setBar(done, due) {
    if (!runBar) return;
    const d = Number(due || 0);
    const dn = Number(done || 0);
    const pct = !d ? 0 : Math.max(0, Math.min(100, Math.round((dn / d) * 100)));
    runBar.style.width = pct + "%";
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
    if (runLive) runLive.style.display = "none";

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

      if (due === 0 && Number(summary.total || 0) > 0 && runHintBox && runHintText) {
        runHintBox.style.display = "block";
        runHintText.textContent =
          "Nothing was checked. If this keeps happening, verify timer state and permissions.";
      }
    } else {
      if (runRaw) {
        runRaw.style.display = "block";
        runRaw.textContent = data.message || "-";
      }
      if (runNowLine) runNowLine.textContent = data.ok ? "Completed" : "Failed";
    }

    toast(data.ok ? "Run completed" : "Run failed", data.ok ? "Done" : (data.message || "Error"));
  }

  let runtimePoll = null;
  let statusPoll = null;
  let lastRuntimeUpdated = 0;

  async function fetchRuntime() {
    try {
      return await getJson("/runtime");
    } catch {
      return null;
    }
  }

  async function fetchRunStatus() {
    try {
      return await getJson("/api/run-status");
    } catch {
      return null;
    }
  }

  async function fetchRunResult() {
    try {
      return await getJson("/api/run-result");
    } catch {
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
        const result = await fetchRunResult();
        if (result) applyRunResult(result);
      }
    }, 320);
  }

  function stopRuntimePoll() {
    if (runtimePoll) clearInterval(runtimePoll);
    runtimePoll = null;
  }

  function stopStatusPoll() {
    if (statusPoll) clearInterval(statusPoll);
    statusPoll = null;
  }

  btnRunNow?.addEventListener("click", async () => {
    if (!btnRunNow) return;

    btnRunNow.disabled = true;
    setRunModalInitial();
    showModal(runModal);

    startRuntimePoll();
    startStatusPoll();

    try {
      const data = await postForm("/api/run-now", new FormData());
      if (!data.ok) {
        stopStatusPoll();
        stopRuntimePoll();
        clearWorking();
        if (runLive) runLive.style.display = "none";

        toast("Run failed", data.message || "Failed to start run");
        if (runRaw) {
          runRaw.style.display = "block";
          runRaw.textContent = data.message || "Failed to start run";
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

      toast("Run failed", e?.message || "Error");
      if (runRaw) {
        runRaw.style.display = "block";
        runRaw.textContent = e?.message || "Run failed";
      }
      if (runNowLine) runNowLine.textContent = "Failed";
    } finally {
      btnRunNow.disabled = false;
      btnRunNow.innerHTML = btnRunNow.dataset.defaultHtml || btnRunNow.innerHTML;
      await refreshState(true);
    }
  });

  // ---------------------------
  // Live state refresh
  // ---------------------------
  async function refreshState(force = false) {
    try {
      const data = await getJson("/state");
      const map = new Map();
      (data.targets || []).forEach((t) => map.set(t.name, t));

      $$('tr[data-name]').forEach((row) => {
        const name = row.getAttribute("data-name");
        const t = map.get(name);
        if (!t) return;

        setStatusChip(row, t.status);

        flashIfChanged($(".last-ping", row), t.last_ping_human || "-");
        flashIfChanged($(".last-resp", row), t.last_response_human || "-");

        const ep = $(".endpoint", row);
        if (ep) ep.textContent = t.endpoint_masked || "-";

        const iv = $(".interval-input", row);
        if (iv && force) {
          iv.value = String(t.interval || 60);
          iv.setAttribute("data-interval", String(t.interval || 60));
        }
      });

      // re-bind
      bindIntervalInputs(false);
      bindMenuActions(false);
    } catch {
      // silent
    }
  }

  // ---------------------------
  // Global key handling
  // ---------------------------
  document.addEventListener("keydown", (e) => {
    if (e.key !== "Escape") return;

    if (isModalOpen(logModal)) hideModal(logModal);
    if (isModalOpen(addModal)) hideModal(addModal);
    if (isModalOpen(runModal)) hideModal(runModal);
    if (isModalOpen(confirmModal)) hideModal(confirmModal);
    closeAllMenus();
  });

  // ---------------------------
  // Init
  // ---------------------------
  bindIntervalInputs(true);
  bindMenuActions(true);
  refreshState(true);

  // Poll state every N seconds (index.html kan sette data-poll på <body>)
  const pollSeconds = Number(document.body?.dataset?.pollSeconds || 2) || 2;
  setInterval(() => refreshState(false), pollSeconds * 1000);
})();
