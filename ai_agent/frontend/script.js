/**
 * DataPulse AI — Frontend Application Controller
 * Premium Enterprise Analytics Interface
 */

(() => {
  "use strict";

  // Configuration
  const API_BASE_URL = "http://127.0.0.1:8001";
  const DEFAULT_TIMEOUT_MS = 45000; // 45 seconds timeout
  const HISTORY_STORAGE_KEY = "datapulse_history_v1";

  // Application State
  const state = {
    isBusy: false,
    activeRequestId: 0,
    activeAbortController: null,
    backendOnline: false,
    activeView: "assistant",
    queryHistory: [],
    toastTimer: null,
  };

  // Safe DOM Elements Helper
  const $ = (id) => document.getElementById(id);
  const $$ = (selector) => document.querySelectorAll(selector);

  // Cached DOM Elements
  const dom = {
    // Nav & Shell
    newAnalysisBtn: $("newAnalysisBtn"),
    navItems: $$(".nav-item-btn"),
    viewPanels: $$(".view-panel"),
    breadcrumbSection: $("breadcrumbSection"),
    breadcrumbPage: $("breadcrumbPage"),
    topbarPageTitle: $("topbarPageTitle"),
    topbarConnectionBadge: $("topbarConnectionBadge"),
    topbarConnectionText: $("topbarConnectionText"),
    btnRefreshHealth: $("btnRefreshHealth"),
    sidebarPulsePill: $("sidebarPulsePill"),
    sidebarStatusText: $("sidebarStatusText"),
    historyCounterBadge: $("historyCounterBadge"),

    // Assistant View
    viewAssistant: $("viewAssistant"),
    chatViewport: $("chatViewport"),
    welcomeExperience: $("welcomeExperience"),
    conversationStream: $("conversationStream"),
    loadingContainer: $("loadingContainer"),
    loadingStatusText: $("loadingStatusText"),
    btnCancelQuery: $("btnCancelQuery"),
    queryInput: $("queryInput"),
    btnSendQuery: $("btnSendQuery"),
    suggestionCards: $$(".suggestion-card"),

    // History View
    historyListContainer: $("historyListContainer"),
    btnClearHistory: $("btnClearHistory"),

    // Toast
    toastNotice: $("toastNotice"),
    toastMessage: $("toastMessage"),
    toastIcon: $("toastIcon"),
  };

  // ===========================================================================
  // Toast Notifications
  // ===========================================================================

  function showToast(message, isSuccess = true) {
    if (!dom.toastNotice) return;
    dom.toastMessage.textContent = message;
    dom.toastIcon.textContent = isSuccess ? "✓" : "!";
    dom.toastNotice.classList.add("show");

    clearTimeout(state.toastTimer);
    state.toastTimer = setTimeout(() => {
      dom.toastNotice.classList.remove("show");
    }, 2800);
  }

  // ===========================================================================
  // View Routing (Single-Page App)
  // ===========================================================================

  const VIEW_TITLES = {
    assistant: { section: "INTELLIGENCE", page: "AI ASSISTANT", title: "AI Analytics Assistant" },
    analytics: { section: "ANALYTICS", page: "BUSINESS MARTS", title: "Business Performance & Metrics" },
    warehouse: { section: "INFRASTRUCTURE", page: "DATA WAREHOUSE", title: "BigQuery Marts & Catalog" },
    history: { section: "MONITORING", page: "QUERY HISTORY", title: "Session Query Audit Log" },
  };

  function switchView(viewName) {
    if (!VIEW_TITLES[viewName]) return;
    state.activeView = viewName;

    // Update Nav buttons
    dom.navItems.forEach((btn) => {
      const targetView = btn.dataset.view;
      if (targetView === viewName) {
        btn.classList.add("active");
      } else {
        btn.classList.remove("active");
      }
    });

    // Update Panels
    dom.viewPanels.forEach((panel) => {
      if (panel.id === `view${viewName.charAt(0).toUpperCase() + viewName.slice(1)}`) {
        panel.classList.add("active");
      } else {
        panel.classList.remove("active");
      }
    });

    // Update Topbar
    const meta = VIEW_TITLES[viewName];
    if (dom.breadcrumbSection) dom.breadcrumbSection.textContent = meta.section;
    if (dom.breadcrumbPage) dom.breadcrumbPage.textContent = meta.page;
    if (dom.topbarPageTitle) dom.topbarPageTitle.textContent = meta.title;

    // If switching to history, re-render
    if (viewName === "history") {
      renderHistoryView();
    }
  }

  // ===========================================================================
  // Backend Health Check
  // ===========================================================================

  async function checkBackendHealth() {
    if (dom.sidebarPulsePill) {
      dom.sidebarPulsePill.className = "status-pulse-pill checking";
      dom.sidebarStatusText.textContent = "Checking...";
    }

    try {
      const startTime = performance.now();
      const response = await fetch(`${API_BASE_URL}/health`, {
        method: "GET",
        cache: "no-store",
      });
      const latency = Math.round(performance.now() - startTime);

      if (response.ok) {
        state.backendOnline = true;
        setConnectionUI(true, `Online (${latency}ms)`);
      } else {
        state.backendOnline = false;
        setConnectionUI(false, `HTTP ${response.status}`);
      }
    } catch {
      state.backendOnline = false;
      setConnectionUI(false, "API Offline");
    }
  }

  function setConnectionUI(isOnline, labelText) {
    if (dom.topbarConnectionBadge) {
      dom.topbarConnectionBadge.className = `topbar-badge ${isOnline ? "live" : "offline"}`;
      dom.topbarConnectionText.textContent = isOnline ? `Backend ${labelText}` : labelText;
    }

    if (dom.sidebarPulsePill) {
      dom.sidebarPulsePill.className = `status-pulse-pill ${isOnline ? "online" : "offline"}`;
      dom.sidebarStatusText.textContent = isOnline ? "Connected" : "Disconnected";
    }
  }

  // ===========================================================================
  // UI State & Textarea Autosize
  // ===========================================================================

  function setBusyState(busy, statusMessage = "Analysing your question and querying the warehouse...") {
    state.isBusy = busy;

    if (dom.btnSendQuery) {
      dom.btnSendQuery.disabled = busy;
    }

    if (dom.loadingContainer) {
      if (busy) {
        dom.loadingStatusText.textContent = statusMessage;
        dom.loadingContainer.style.display = "flex";
      } else {
        dom.loadingContainer.style.display = "none";
      }
    }

    dom.suggestionCards.forEach((card) => {
      card.disabled = busy;
      card.style.opacity = busy ? "0.6" : "1";
      card.style.pointerEvents = busy ? "none" : "auto";
    });
  }

  function autosizeTextarea() {
    if (!dom.queryInput) return;
    dom.queryInput.style.height = "auto";
    dom.queryInput.style.height = `${Math.min(dom.queryInput.scrollHeight, 180)}px`;
  }

  function scrollToBottom() {
    if (!dom.chatViewport) return;
    dom.chatViewport.scrollTo({
      top: dom.chatViewport.scrollHeight,
      behavior: "smooth",
    });
  }

  // ===========================================================================
  // Message & Results Rendering
  // ===========================================================================

  function renderUserMessage(questionText) {
    // Hide welcome on first message
    if (dom.welcomeExperience) {
      dom.welcomeExperience.style.display = "none";
    }

    const entry = document.createElement("div");
    entry.className = "message-entry user-entry";

    const header = document.createElement("div");
    header.className = "message-header-row";

    const tag = document.createElement("span");
    tag.className = "message-avatar-tag";
    tag.textContent = "YOU";

    const time = document.createElement("span");
    time.className = "message-timestamp";
    time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    header.append(tag, time);

    const bubble = document.createElement("div");
    bubble.className = "user-query-bubble";
    bubble.textContent = questionText;

    entry.append(header, bubble);
    dom.conversationStream.appendChild(entry);
    scrollToBottom();
  }

  function renderAIResponse(data, elapsedMs) {
    const entry = document.createElement("div");
    entry.className = "message-entry ai-entry";

    const header = document.createElement("div");
    header.className = "message-header-row";

    const tag = document.createElement("span");
    tag.className = "message-avatar-tag";
    tag.textContent = "DATAPULSE AI";

    const time = document.createElement("span");
    time.className = "message-timestamp";
    time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    header.append(tag, time);

    const container = document.createElement("div");
    container.className = "ai-response-container";

    // Meta Bar
    const metaBar = document.createElement("div");
    metaBar.className = "ai-meta-bar";

    const badgesWrap = document.createElement("div");
    badgesWrap.className = "ai-meta-badges";

    const statusPill = document.createElement("span");
    statusPill.className = "meta-pill success";
    statusPill.innerHTML = "<span>●</span> BigQuery Success";

    const rowsCount = Array.isArray(data.results) ? data.results.length : (data.row_count || 0);
    const rowsPill = document.createElement("span");
    rowsPill.className = "meta-pill rows";
    rowsPill.textContent = `${rowsCount} ${rowsCount === 1 ? "row" : "rows"} returned`;

    badgesWrap.append(statusPill, rowsPill);

    if (elapsedMs) {
      const timePill = document.createElement("span");
      timePill.className = "meta-pill time";
      timePill.textContent = `${(elapsedMs / 1000).toFixed(2)}s`;
      metaBar.append(badgesWrap, timePill);
    } else {
      metaBar.append(badgesWrap);
    }

    container.appendChild(metaBar);

    // Natural Narrative
    const narrative = document.createElement("div");
    narrative.className = "response-narrative";
    narrative.textContent = rowsCount > 0
      ? "Here are the query results retrieved from your connected BigQuery warehouse:"
      : "The query executed successfully, but returned zero matching records from the warehouse.";
    container.appendChild(narrative);

    // SQL Accordion
    if (data.sql && typeof data.sql === "string") {
      const sqlAccordion = createSqlAccordion(data.sql);
      container.appendChild(sqlAccordion);
    }

    // Results Table
    if (Array.isArray(data.results) && data.results.length > 0) {
      const tableSection = createResultsTableSection(data.results);
      container.appendChild(tableSection);
    }

    entry.append(header, container);
    dom.conversationStream.appendChild(entry);
    scrollToBottom();
  }

  function renderAIError(errorMessage, statusCode, rawDetail) {
    const entry = document.createElement("div");
    entry.className = "message-entry ai-entry";

    const header = document.createElement("div");
    header.className = "message-header-row";

    const tag = document.createElement("span");
    tag.className = "message-avatar-tag";
    tag.textContent = "DATAPULSE AI";

    const time = document.createElement("span");
    time.className = "message-timestamp";
    time.textContent = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });

    header.append(tag, time);

    const errorContainer = document.createElement("div");
    errorContainer.className = "ai-error-container";

    const errorHeader = document.createElement("div");
    errorHeader.className = "error-header-row";
    errorHeader.innerHTML = `<span>⚠</span><span>Query Execution Notice · Status ${statusCode || "Client Error"}</span>`;

    const errorText = document.createElement("div");
    errorText.className = "error-narrative";
    errorText.textContent = errorMessage;

    errorContainer.append(errorHeader, errorText);

    if (rawDetail && typeof rawDetail === "string" && rawDetail !== errorMessage) {
      const detailsBox = document.createElement("div");
      detailsBox.className = "error-details-box";
      detailsBox.textContent = rawDetail;
      errorContainer.appendChild(detailsBox);
    }

    entry.append(header, errorContainer);
    dom.conversationStream.appendChild(entry);
    scrollToBottom();
  }

  // ===========================================================================
  // SQL Accordion & Table Components
  // ===========================================================================

  function createSqlAccordion(sqlText) {
    const details = document.createElement("details");
    details.className = "sql-accordion";

    const summary = document.createElement("summary");
    summary.className = "sql-summary";
    summary.innerHTML = `
      <div class="sql-summary-label">
        <span class="sql-tag">SQL</span>
        <span>View Generated BigQuery Query</span>
      </div>
      <span style="font-size: 11px; color: var(--text-muted);">Expand ▾</span>
    `;

    const body = document.createElement("div");
    body.className = "sql-content-body";

    const pre = document.createElement("pre");
    pre.className = "sql-code-block";
    pre.textContent = sqlText;

    const copyBtn = document.createElement("button");
    copyBtn.type = "button";
    copyBtn.className = "btn-copy-sql";
    copyBtn.innerHTML = `<span>📋</span><span>Copy SQL</span>`;
    copyBtn.addEventListener("click", async (e) => {
      e.preventDefault();
      e.stopPropagation();
      try {
        await navigator.clipboard.writeText(sqlText);
        copyBtn.innerHTML = `<span>✓</span><span>Copied!</span>`;
        showToast("SQL copied to clipboard");
        setTimeout(() => {
          copyBtn.innerHTML = `<span>📋</span><span>Copy SQL</span>`;
        }, 2000);
      } catch {
        showToast("Clipboard write permission unavailable", false);
      }
    });

    body.append(pre, copyBtn);
    details.append(summary, body);

    return details;
  }

  function formatCellValue(val) {
    if (val === null || val === undefined) return "—";
    if (typeof val === "number") {
      return val.toLocaleString("en-IN", { maximumFractionDigits: 2 });
    }
    if (typeof val === "boolean") return val ? "True" : "False";
    if (typeof val === "object") return JSON.stringify(val);
    return String(val);
  }

  function isNumericColumn(rows, colName) {
    const sample = rows.slice(0, 10);
    return sample.some((r) => typeof r[colName] === "number");
  }

  function createResultsTableSection(records) {
    const section = document.createElement("div");
    section.className = "results-table-section";

    const columns = Object.keys(records[0] || {});

    // Table Toolbar
    const toolbar = document.createElement("div");
    toolbar.className = "table-toolbar";

    const stats = document.createElement("div");
    stats.className = "table-stats";
    stats.textContent = `Displaying ${records.length} records`;

    const searchInput = document.createElement("input");
    searchInput.type = "text";
    searchInput.className = "table-search-input";
    searchInput.placeholder = "Filter table rows...";
    searchInput.setAttribute("aria-label", "Search results table");

    toolbar.append(stats, searchInput);

    // Table Wrapper
    const wrapper = document.createElement("div");
    wrapper.className = "results-table-wrapper";

    const table = document.createElement("table");
    table.className = "results-table";

    // Header
    const thead = document.createElement("thead");
    const headerRow = document.createElement("tr");

    columns.forEach((col) => {
      const th = document.createElement("th");
      th.className = "sortable";
      th.textContent = col.replace(/_/g, " ").toUpperCase();
      th.title = "Click to sort";
      th.dataset.column = col;
      th.dataset.direction = "asc";
      headerRow.appendChild(th);
    });
    thead.appendChild(headerRow);

    // Body
    const tbody = document.createElement("tbody");

    function renderRows(filteredRecords) {
      tbody.innerHTML = "";
      if (filteredRecords.length === 0) {
        const emptyRow = document.createElement("tr");
        const emptyTd = document.createElement("td");
        emptyTd.colSpan = columns.length;
        emptyTd.style.textAlign = "center";
        emptyTd.style.color = "var(--text-muted)";
        emptyTd.style.padding = "20px";
        emptyTd.textContent = "No matching records found.";
        emptyRow.appendChild(emptyTd);
        tbody.appendChild(emptyRow);
        return;
      }

      filteredRecords.forEach((rowObj) => {
        const tr = document.createElement("tr");
        columns.forEach((col) => {
          const td = document.createElement("td");
          const val = rowObj[col];
          if (typeof val === "number") {
            td.className = "numeric";
          }
          td.textContent = formatCellValue(val);
          tr.appendChild(td);
        });
        tbody.appendChild(tr);
      });
    }

    let currentRecords = [...records];
    renderRows(currentRecords);

    // Search filter listener
    searchInput.addEventListener("input", () => {
      const query = searchInput.value.toLowerCase().trim();
      if (!query) {
        currentRecords = [...records];
      } else {
        currentRecords = records.filter((r) =>
          Object.values(r).some((v) => String(v).toLowerCase().includes(query))
        );
      }
      renderRows(currentRecords);
      stats.textContent = `Displaying ${currentRecords.length} of ${records.length} records`;
    });

    // Column sorting listener
    headerRow.addEventListener("click", (e) => {
      const th = e.target.closest("th");
      if (!th) return;
      const col = th.dataset.column;
      const dir = th.dataset.direction === "asc" ? "desc" : "asc";
      th.dataset.direction = dir;

      currentRecords.sort((a, b) => {
        const valA = a[col];
        const valB = b[col];
        if (valA === valB) return 0;
        if (valA === null || valA === undefined) return 1;
        if (valB === null || valB === undefined) return -1;
        if (typeof valA === "number" && typeof valB === "number") {
          return dir === "asc" ? valA - valB : valB - valA;
        }
        return dir === "asc"
          ? String(valA).localeCompare(String(valB))
          : String(valB).localeCompare(String(valA));
      });

      renderRows(currentRecords);
    });

    table.append(thead, tbody);
    wrapper.appendChild(table);
    section.append(toolbar, wrapper);

    return section;
  }

  // ===========================================================================
  // API Query Pipeline
  // ===========================================================================

  async function executeAskQuery(questionText, isFromSuggestion = false) {
    const trimmedQuestion = String(questionText || "").trim();

    if (!trimmedQuestion) {
      if (dom.queryInput) dom.queryInput.focus();
      return;
    }

    if (state.isBusy) {
      showToast("A warehouse query is already in progress.", false);
      return;
    }

    // Capture the current textarea draft
    const inputDraft = dom.queryInput ? dom.queryInput.value : "";

    // Track Request Sequence & AbortController
    const currentRequestId = ++state.activeRequestId;
    const controller = new AbortController();
    state.activeAbortController = controller;

    // Timeout safety
    const timeoutTimer = setTimeout(() => {
      controller.abort();
    }, DEFAULT_TIMEOUT_MS);

    // Switch view to assistant if called from analytics
    if (state.activeView !== "assistant") {
      switchView("assistant");
    }

    // Render user message bubble
    renderUserMessage(trimmedQuestion);

    // Set UI to busy
    setBusyState(true, "Analysing question and querying BigQuery warehouse...");

    const startTime = performance.now();

    try {
      const response = await fetch(`${API_BASE_URL}/ask`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ question: trimmedQuestion }),
        signal: controller.signal,
      });

      const responseText = await response.text();
      let responseData = {};

      try {
        responseData = responseText ? JSON.parse(responseText) : {};
      } catch {
        throw new Error(`The backend returned an unparseable response (HTTP ${response.status}).`);
      }

      // Stale response guard: Ignore if newer request was initiated
      if (currentRequestId !== state.activeRequestId) {
        return;
      }

      const elapsedMs = Math.round(performance.now() - startTime);

      if (!response.ok) {
        // Parse error message accurately
        let displayError = "The request could not be processed by the warehouse.";
        let rawDetail = "";

        if (Array.isArray(responseData.detail)) {
          // FastAPI / Pydantic validation error array
          displayError = responseData.detail.map((err) => `${err.msg || "Invalid field"} (${err.loc ? err.loc.join(".") : ""})`).join("; ");
          rawDetail = JSON.stringify(responseData.detail, null, 2);
        } else if (typeof responseData.detail === "string") {
          displayError = responseData.detail;
          rawDetail = responseData.detail;
        }

        renderAIError(displayError, response.status, rawDetail);
        saveHistoryEntry({
          question: trimmedQuestion,
          status: "ERROR",
          sql: "",
          rows: 0,
          timestamp: new Date().toISOString(),
        });
        return;
      }

      // Success HTTP 200
      renderAIResponse(responseData, elapsedMs);

      // Save to History
      saveHistoryEntry({
        question: trimmedQuestion,
        status: responseData.status ? responseData.status.toUpperCase() : "SUCCESS",
        sql: responseData.sql || "",
        rows: Array.isArray(responseData.results) ? responseData.results.length : (responseData.row_count || 0),
        timestamp: new Date().toISOString(),
      });

      // Clear input ONLY upon success if the input matched what was submitted
      if (!isFromSuggestion && dom.queryInput && dom.queryInput.value === inputDraft) {
        dom.queryInput.value = "";
        autosizeTextarea();
      }
    } catch (err) {
      // Stale response guard
      if (currentRequestId !== state.activeRequestId) {
        return;
      }

      if (err.name === "AbortError") {
        renderAIError("The query request timed out or was cancelled by user.", 408, "Operation cancelled before completion.");
      } else if (err instanceof TypeError) {
        renderAIError(
          `Unable to reach DataPulse AI backend at ${API_BASE_URL}. Ensure FastAPI is running on port 8001.`,
          0,
          err.message
        );
      } else {
        renderAIError(err.message || "An unexpected error occurred.", 500, err.stack || "");
      }
    } finally {
      clearTimeout(timeoutTimer);

      // GUARANTEED CLEANUP: Only clear if this was the latest active request
      if (currentRequestId === state.activeRequestId) {
        state.activeAbortController = null;
        setBusyState(false);
        if (dom.queryInput) {
          dom.queryInput.focus();
        }
      }
    }
  }

  // ===========================================================================
  // Session Query History Persistence
  // ===========================================================================

  function loadHistory() {
    try {
      const raw = localStorage.getItem(HISTORY_STORAGE_KEY);
      if (raw) {
        state.queryHistory = JSON.parse(raw);
      } else {
        state.queryHistory = [];
      }
    } catch {
      state.queryHistory = [];
    }
    updateHistoryBadge();
  }

  function saveHistoryEntry(entry) {
    state.queryHistory.unshift(entry);
    if (state.queryHistory.length > 50) {
      state.queryHistory = state.queryHistory.slice(0, 50);
    }
    try {
      localStorage.setItem(HISTORY_STORAGE_KEY, JSON.stringify(state.queryHistory));
    } catch {
      // Storage full or private mode
    }
    updateHistoryBadge();
  }

  function updateHistoryBadge() {
    if (dom.historyCounterBadge) {
      dom.historyCounterBadge.textContent = state.queryHistory.length;
    }
  }

  function renderHistoryView() {
    if (!dom.historyListContainer) return;
    dom.historyListContainer.innerHTML = "";

    if (state.queryHistory.length === 0) {
      const empty = document.createElement("div");
      empty.className = "empty-state-card";
      empty.innerHTML = `
        <div class="empty-icon">⏱</div>
        <div class="empty-title">No Queries Recorded Yet</div>
        <div class="empty-desc">
          Questions you submit in the AI Assistant will appear here with execution metrics and generated SQL.
        </div>
      `;
      dom.historyListContainer.appendChild(empty);
      return;
    }

    state.queryHistory.forEach((item) => {
      const card = document.createElement("div");
      card.className = "history-item-card";

      const top = document.createElement("div");
      top.className = "history-item-top";

      const q = document.createElement("div");
      q.className = "history-question";
      q.textContent = item.question;

      const actions = document.createElement("div");
      actions.className = "history-actions";

      const rerunBtn = document.createElement("button");
      rerunBtn.type = "button";
      rerunBtn.className = "btn-history-rerun";
      rerunBtn.innerHTML = `<span>↻</span><span>Rerun</span>`;
      rerunBtn.addEventListener("click", () => {
        executeAskQuery(item.question, false);
      });

      actions.appendChild(rerunBtn);
      top.append(q, actions);
      card.appendChild(top);

      if (item.sql) {
        const sqlPre = document.createElement("pre");
        sqlPre.className = "history-sql-preview";
        sqlPre.textContent = item.sql;
        card.appendChild(sqlPre);
      }

      const meta = document.createElement("div");
      meta.className = "history-meta-row";

      const timeFormatted = new Date(item.timestamp).toLocaleString();
      meta.innerHTML = `
        <span><strong>Status:</strong> ${item.status || "SUCCESS"}</span>
        <span>·</span>
        <span><strong>Rows:</strong> ${item.rows}</span>
        <span>·</span>
        <span>${timeFormatted}</span>
      `;

      card.appendChild(meta);
      dom.historyListContainer.appendChild(card);
    });
  }

  // ===========================================================================
  // Reset Action ("New Analysis")
  // ===========================================================================

  function handleNewAnalysis() {
    // Abort active controller if any
    if (state.activeAbortController) {
      state.activeAbortController.abort();
      state.activeAbortController = null;
    }

    // Invalidate request sequence
    state.activeRequestId++;

    // Reset UI
    setBusyState(false);

    if (dom.conversationStream) {
      dom.conversationStream.replaceChildren();
    }

    if (dom.welcomeExperience) {
      dom.welcomeExperience.style.display = "flex";
    }

    if (dom.chatViewport) {
      dom.chatViewport.scrollTo({ top: 0, behavior: "smooth" });
    }

    // Switch to Assistant view
    switchView("assistant");

    // Clear textarea
    if (dom.queryInput) {
      dom.queryInput.value = "";
      autosizeTextarea();
      dom.queryInput.focus();
    }

    showToast("Started new analysis session");
  }

  // ===========================================================================
  // Event Bindings & Idempotent Initialization
  // ===========================================================================

  function bindEvents() {
    // Navigation items
    dom.navItems.forEach((btn) => {
      btn.addEventListener("click", () => {
        const view = btn.dataset.view;
        if (view) switchView(view);
      });
    });

    // New Analysis button
    if (dom.newAnalysisBtn) {
      dom.newAnalysisBtn.addEventListener("click", (e) => {
        e.preventDefault();
        handleNewAnalysis();
      });
    }

    // Refresh Health button
    if (dom.btnRefreshHealth) {
      dom.btnRefreshHealth.addEventListener("click", (e) => {
        e.preventDefault();
        checkBackendHealth();
        showToast("Checking backend connection...");
      });
    }

    // Send button click
    if (dom.btnSendQuery) {
      dom.btnSendQuery.addEventListener("click", (e) => {
        e.preventDefault();
        if (dom.queryInput) {
          executeAskQuery(dom.queryInput.value, false);
        }
      });
    }

    // Textarea input & keyboard shortcuts
    if (dom.queryInput) {
      dom.queryInput.addEventListener("input", autosizeTextarea);

      dom.queryInput.addEventListener("keydown", (e) => {
        // Enter sends unless Shift is pressed
        if (e.key === "Enter" && !e.shiftKey) {
          e.preventDefault();
          executeAskQuery(dom.queryInput.value, false);
        }
      });
    }

    // Suggested Questions (Event Delegation on card clicks)
    dom.suggestionCards.forEach((card) => {
      card.addEventListener("click", (e) => {
        e.preventDefault();
        const exactQuestion = card.dataset.question;
        if (exactQuestion) {
          executeAskQuery(exactQuestion, true);
        }
      });
    });

    // "Ask AI" buttons on Analytics Page
    $$(".btn-ask-widget").forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const q = btn.dataset.quickQuestion;
        if (q) {
          executeAskQuery(q, true);
        }
      });
    });

    // Cancel Query button
    if (dom.btnCancelQuery) {
      dom.btnCancelQuery.addEventListener("click", (e) => {
        e.preventDefault();
        if (state.activeAbortController) {
          state.activeAbortController.abort();
          state.activeAbortController = null;
        }
        setBusyState(false);
        showToast("Query cancelled", false);
      });
    }

    // Clear History button
    if (dom.btnClearHistory) {
      dom.btnClearHistory.addEventListener("click", (e) => {
        e.preventDefault();
        state.queryHistory = [];
        try {
          localStorage.removeItem(HISTORY_STORAGE_KEY);
        } catch {
          // Ignore
        }
        updateHistoryBadge();
        renderHistoryView();
        showToast("Query history cleared");
      });
    }
  }

  // ===========================================================================
  // App Bootstrapping
  // ===========================================================================

  function init() {
    loadHistory();
    bindEvents();
    checkBackendHealth();

    // Health poll every 20 seconds
    setInterval(checkBackendHealth, 20000);

    // Initial textarea focus
    if (dom.queryInput) {
      dom.queryInput.focus();
    }
  }

  // Initialize once DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

