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
    analyticsStartDate: null,
    analyticsEndDate: null,
    analyticsGranularity: "monthly",
    analyticsActivePreset: "all",
    analyticsData: null,
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

    // Analytics View
    kpiRevenueValue: $("kpiRevenueValue"),
    kpiRevenueSub: $("kpiRevenueSub"),
    kpiRevenuePeriodLabel: $("kpiRevenuePeriodLabel"),
    kpiOrdersValue: $("kpiOrdersValue"),
    kpiOrdersSub: $("kpiOrdersSub"),
    kpiCustomersValue: $("kpiCustomersValue"),
    kpiCustomersSub: $("kpiCustomersSub"),
    kpiInventoryValue: $("kpiInventoryValue"),
    kpiInventorySub: $("kpiInventorySub"),
    analyticsSyncPill: $("analyticsSyncPill"),
    btnRefreshAnalytics: $("btnRefreshAnalytics"),
    filterPresetBtns: $$(".filter-preset-btn"),
    analyticsStartDate: $("analyticsStartDate"),
    analyticsEndDate: $("analyticsEndDate"),
    btnApplyDateFilter: $("btnApplyDateFilter"),
    btnResetDateFilter: $("btnResetDateFilter"),
    granularityBtns: $$(".granularity-btn"),
    revenueTrendChartContainer: $("revenueTrendChartContainer"),
    trendChartSubtitle: $("trendChartSubtitle"),
    trendChartViewport: $("trendChartViewport"),
    chartTooltip: $("chartTooltip"),
    analyticsCategoryList: $("analyticsCategoryList"),
    analyticsTopProductsTbody: $("analyticsTopProductsTbody"),
    invHealthScoreVal: $("invHealthScoreVal"),
    invTotalSkusVal: $("invTotalSkusVal"),
    invCriticalAlertsVal: $("invCriticalAlertsVal"),
    warehouseCardsGrid: $("warehouseCardsGrid"),
    analyticsRestockTbody: $("analyticsRestockTbody"),

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

    // If switching to analytics, load fresh metrics
    if (viewName === "analytics") {
      loadDashboardAnalytics(false);
    }

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
  // Live Business Analytics (BigQuery Marts)
  // ===========================================================================

  let analyticsLoading = false;

  function formatInrShort(val) {
    const num = Number(val) || 0;
    const abs = Math.abs(num);
    if (abs >= 10000000) return `₹${(num / 10000000).toFixed(1)} Cr`;
    if (abs >= 100000) return `₹${(num / 100000).toFixed(1)} L`;
    if (abs >= 1000) return `₹${(num / 1000).toFixed(0)} K`;
    return `₹${num.toFixed(0)}`;
  }

  async function loadDashboardAnalytics(forceRefresh = false) {
    if (analyticsLoading) return;
    analyticsLoading = true;

    if (dom.analyticsSyncPill) {
      dom.analyticsSyncPill.innerHTML = `<span>⏳</span> Syncing BigQuery...`;
    }

    try {
      const params = new URLSearchParams();
      if (state.analyticsStartDate) params.append("start_date", state.analyticsStartDate);
      if (state.analyticsEndDate) params.append("end_date", state.analyticsEndDate);
      if (state.analyticsGranularity) params.append("granularity", state.analyticsGranularity);
      if (forceRefresh) params.append("refresh", "true");

      const qs = params.toString();
      const url = `${API_BASE_URL}/analytics/dashboard${qs ? `?${qs}` : ""}`;

      const response = await fetch(url, {
        method: "GET",
        headers: { "Accept": "application/json" },
      });

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}));
        throw new Error(errorData.detail || `Analytics API returned HTTP ${response.status}`);
      }

      const data = await response.json();
      state.analyticsData = data;
      renderAnalyticsDashboard(data);

      if (forceRefresh) {
        showToast("Fetched fresh metrics from BigQuery warehouse");
      }
    } catch (err) {
      console.warn("Failed to fetch dashboard analytics:", err);
      if (dom.analyticsSyncPill) {
        dom.analyticsSyncPill.innerHTML = `<span>⚠</span> BigQuery Connection Error`;
      }
      showToast(`Analytics Error: ${err.message}`, false);
    } finally {
      analyticsLoading = false;
    }
  }

  function renderAnalyticsDashboard(data) {
    if (!data || !data.summary) return;

    const s = data.summary;

    // 1. Update KPI Cards
    if (dom.kpiRevenueValue) dom.kpiRevenueValue.textContent = s.total_net_revenue_formatted;
    if (dom.kpiRevenueSub) {
      dom.kpiRevenueSub.innerHTML = `<span class="trend-indicator up">Total Profit: ${s.total_profit_formatted}</span> (${s.profit_margin_percentage}% margin)`;
    }
    if (dom.kpiRevenuePeriodLabel) {
      const presetLabels = {
        all: "All Time",
        fy2026: "FY 2026 YTD",
        fy2025: "FY 2025",
        last90: "Last 90 Days",
        last30: "Last 30 Days",
      };
      if (state.analyticsActivePreset && presetLabels[state.analyticsActivePreset]) {
        dom.kpiRevenuePeriodLabel.textContent = presetLabels[state.analyticsActivePreset];
      } else if (state.analyticsStartDate || state.analyticsEndDate) {
        dom.kpiRevenuePeriodLabel.textContent = `${state.analyticsStartDate || "Start"} → ${state.analyticsEndDate || "End"}`;
      } else {
        dom.kpiRevenuePeriodLabel.textContent = "All Time";
      }
    }

    if (dom.kpiOrdersValue) dom.kpiOrdersValue.textContent = Number(s.total_orders).toLocaleString("en-IN");
    if (dom.kpiOrdersSub) {
      const deliveredPercent = s.total_orders > 0 ? Math.round((s.delivered_orders / s.total_orders) * 100) : 100;
      dom.kpiOrdersSub.innerHTML = `<span class="trend-indicator up">${Number(s.delivered_orders).toLocaleString("en-IN")} delivered</span> (${deliveredPercent}% recorded)`;
    }

    if (dom.kpiCustomersValue) dom.kpiCustomersValue.textContent = Number(s.total_customers).toLocaleString("en-IN");
    if (dom.kpiCustomersSub) {
      dom.kpiCustomersSub.textContent = "Active ordering customers across regions";
    }

    if (dom.kpiInventoryValue) dom.kpiInventoryValue.textContent = `${s.total_products} SKUs`;
    if (dom.kpiInventorySub) {
      dom.kpiInventorySub.innerHTML = `<span class="trend-indicator down">${s.restock_alerts_count} alerts</span> below reorder level`;
    }

    // 2. Render Revenue Trends SVG Chart
    renderRevenueTrendChart(data.revenue_trends, data.date_filter?.granularity || state.analyticsGranularity);

    // 3. Render Category Profitability Progress Bars
    renderCategoryComparison(data.category_profitability);

    // 4. Render Top 10 Products Leaderboard Table
    renderTopProductsLeaderboard(data.top_products);

    // 5. Render Warehouse Inventory Risk Cards & Restock Priority Queue
    renderWarehouseInventoryRisk(data.inventory_risk, data.restock_queue);

    // 6. Update Sync Pill
    if (dom.analyticsSyncPill) {
      const isCached = data.cache && data.cache.cached;
      dom.analyticsSyncPill.innerHTML = `<span>◈</span> Source: dbt Marts (${isCached ? "Cached BigQuery" : "Live BigQuery"})`;
    }
  }

  function renderRevenueTrendChart(trends, granularity) {
    if (!dom.revenueTrendChartContainer) return;

    if (!Array.isArray(trends) || trends.length === 0) {
      dom.revenueTrendChartContainer.innerHTML = `
        <div style="color: var(--text-muted); font-size: 13px; text-align: center; padding: 40px;">
          No revenue or sales telemetry recorded for the selected date range.
        </div>
      `;
      return;
    }

    if (dom.trendChartSubtitle) {
      const granLabel = granularity === "daily" ? "Daily" : "Monthly";
      dom.trendChartSubtitle.textContent = `Model: fct_daily_sales · ${granLabel} aggregation (${trends.length} periods) · Chronological warehouse telemetry`;
    }

    const W = 960;
    const H = 250;
    const padLeft = 70;
    const padRight = 30;
    const padTop = 20;
    const padBottom = 35;
    const plotW = W - padLeft - padRight;
    const plotH = H - padTop - padBottom;

    const maxRev = Math.max(...trends.map((t) => Number(t.net_revenue) || 0), 1000);
    const yMax = Math.ceil(maxRev * 1.15);

    const getX = (i) => padLeft + (i / Math.max(trends.length - 1, 1)) * plotW;
    const getY = (val) => padTop + plotH - ((Number(val) || 0) / yMax) * plotH;

    // Y Gridlines (4 horizontal lines)
    let gridLinesSvg = "";
    const yTicks = 4;
    for (let t = 0; t <= yTicks; t++) {
      const tickVal = (yMax / yTicks) * t;
      const yPos = getY(tickVal);
      gridLinesSvg += `
        <line x1="${padLeft}" y1="${yPos}" x2="${W - padRight}" y2="${yPos}" stroke="#1e2636" stroke-width="1" stroke-dasharray="3 3"/>
        <text x="${padLeft - 10}" y="${yPos + 4}" fill="#64748b" font-size="10" font-family="JetBrains Mono, monospace" text-anchor="end">${formatInrShort(tickVal)}</text>
      `;
    }

    // Build Paths
    const revPoints = trends.map((d, i) => `${getX(i).toFixed(1)},${getY(d.net_revenue).toFixed(1)}`);
    const profitPoints = trends.map((d, i) => `${getX(i).toFixed(1)},${getY(d.total_profit).toFixed(1)}`);

    const areaD = `M ${getX(0).toFixed(1)},${(padTop + plotH).toFixed(1)} L ${revPoints.join(" L ")} L ${getX(trends.length - 1).toFixed(1)},${(padTop + plotH).toFixed(1)} Z`;
    const revLineD = `M ${revPoints.join(" L ")}`;
    const profitLineD = `M ${profitPoints.join(" L ")}`;

    // X Axis Labels (sample spaced intervals)
    let xLabelsSvg = "";
    const labelStep = Math.max(1, Math.ceil(trends.length / 8));
    trends.forEach((d, i) => {
      if (i % labelStep === 0 || i === trends.length - 1) {
        const xPos = getX(i);
        xLabelsSvg += `
          <text x="${xPos}" y="${H - 12}" fill="#94a3b8" font-size="10" font-family="JetBrains Mono, monospace" text-anchor="middle">${d.period_label}</text>
        `;
      }
    });

    // Data Circles for Revenue
    let circlesSvg = "";
    if (trends.length <= 40) {
      trends.forEach((d, i) => {
        circlesSvg += `
          <circle cx="${getX(i).toFixed(1)}" cy="${getY(d.net_revenue).toFixed(1)}" r="3" fill="#090b10" stroke="#bef264" stroke-width="2"/>
        `;
      });
    }

    const svgContent = `
      <svg class="trend-chart-svg" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none">
        <defs>
          <linearGradient id="revAreaGradient" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="#bef264" stop-opacity="0.32" />
            <stop offset="100%" stop-color="#bef264" stop-opacity="0.0" />
          </linearGradient>
        </defs>

        <!-- Y Grid & Labels -->
        ${gridLinesSvg}

        <!-- Area Fill -->
        <path d="${areaD}" fill="url(#revAreaGradient)"/>

        <!-- Profit Line (Blue Dashed) -->
        <path d="${profitLineD}" fill="none" stroke="#38bdf8" stroke-width="1.8" stroke-dasharray="4 3" stroke-linecap="round" stroke-linejoin="round"/>

        <!-- Net Revenue Line (Lime Solid) -->
        <path d="${revLineD}" fill="none" stroke="#bef264" stroke-width="2.6" stroke-linecap="round" stroke-linejoin="round"/>

        <!-- Data Circles -->
        ${circlesSvg}

        <!-- Guide Line (Interactive) -->
        <line id="trendChartGuideLine" x1="0" y1="${padTop}" x2="0" y2="${padTop + plotH}" stroke="rgba(255,255,255,0.25)" stroke-width="1" stroke-dasharray="2 2" style="display: none;"/>

        <!-- X Axis Labels -->
        ${xLabelsSvg}
      </svg>
    `;

    dom.revenueTrendChartContainer.innerHTML = svgContent;

    // Attach Hover Tooltip Interactions
    const svgEl = dom.revenueTrendChartContainer.querySelector("svg");
    const guideLine = dom.revenueTrendChartContainer.querySelector("#trendChartGuideLine");
    const tooltip = dom.chartTooltip;

    if (!svgEl || !tooltip || !guideLine) return;

    svgEl.addEventListener("mousemove", (e) => {
      const rect = svgEl.getBoundingClientRect();
      const mouseX = e.clientX - rect.left;
      const svgScaleX = W / rect.width;
      const svgX = mouseX * svgScaleX;

      let closestIdx = 0;
      let minDiff = Infinity;
      trends.forEach((_, i) => {
        const diff = Math.abs(getX(i) - svgX);
        if (diff < minDiff) {
          minDiff = diff;
          closestIdx = i;
        }
      });

      const item = trends[closestIdx];
      const targetSvgX = getX(closestIdx);
      const targetSvgY = getY(item.net_revenue);

      // Position guideline
      guideLine.setAttribute("x1", targetSvgX);
      guideLine.setAttribute("x2", targetSvgX);
      guideLine.style.display = "block";

      // Position and populate tooltip
      const screenX = (targetSvgX / W) * rect.width;
      const screenY = (targetSvgY / H) * rect.height;

      tooltip.innerHTML = `
        <div class="tt-title">${item.period_label}</div>
        <div class="tt-row"><span class="label">Net Revenue:</span><span class="val revenue">${item.net_revenue_formatted}</span></div>
        <div class="tt-row"><span class="label">Total Profit:</span><span class="val profit">${item.total_profit_formatted}</span></div>
        <div class="tt-row"><span class="label">Margin:</span><span class="val">${item.profit_margin_percentage}%</span></div>
        <div class="tt-row"><span class="label">Orders / Units:</span><span class="val">${Number(item.total_orders).toLocaleString("en-IN")} / ${Number(item.units_sold).toLocaleString("en-IN")}</span></div>
      `;

      tooltip.style.left = `${screenX + 12}px`;
      tooltip.style.top = `${screenY + 16}px`;
      tooltip.style.display = "block";
    });

    svgEl.addEventListener("mouseleave", () => {
      guideLine.style.display = "none";
      tooltip.style.display = "none";
    });
  }

  function renderCategoryComparison(categories) {
    if (!dom.analyticsCategoryList) return;
    dom.analyticsCategoryList.innerHTML = "";

    if (!Array.isArray(categories) || categories.length === 0) {
      dom.analyticsCategoryList.innerHTML = `<div style="color: var(--text-muted); font-size: 12px; padding: 12px;">No category sales data for this period.</div>`;
      return;
    }

    const maxRev = Math.max(...categories.map((c) => Number(c.net_revenue) || 0), 1);

    categories.forEach((cat) => {
      const item = document.createElement("div");
      item.className = "cat-bar-item";

      const fillWidth = Math.max(10, Math.round((Number(cat.net_revenue) / maxRev) * 100));
      const orderCountText = cat.total_orders > 0 ? ` · ${Number(cat.total_orders).toLocaleString("en-IN")} orders` : "";

      item.innerHTML = `
        <div class="cat-bar-labels">
          <span class="cat-name">${cat.product_category}</span>
          <span class="cat-metrics">${cat.net_revenue_formatted} · ${cat.profit_margin_percentage}% margin${orderCountText}</span>
        </div>
        <div class="cat-progress-track">
          <div class="cat-progress-fill" style="width: ${fillWidth}%;"></div>
        </div>
      `;
      dom.analyticsCategoryList.appendChild(item);
    });
  }

  function renderTopProductsLeaderboard(topProducts) {
    if (!dom.analyticsTopProductsTbody) return;
    dom.analyticsTopProductsTbody.innerHTML = "";

    if (!Array.isArray(topProducts) || topProducts.length === 0) {
      dom.analyticsTopProductsTbody.innerHTML = `
        <tr><td colspan="6" style="text-align: center; color: var(--text-muted); padding: 20px;">No product records found for this period.</td></tr>
      `;
      return;
    }

    topProducts.forEach((p, idx) => {
      const tr = document.createElement("tr");
      const rankNum = idx + 1;

      tr.innerHTML = `
        <td class="rank"><span class="rank-badge">${rankNum}</span></td>
        <td>
          <div class="prod-meta-name">
            <span class="prod-title">${p.product_name}</span>
            <span class="prod-category">${p.product_category}</span>
          </div>
        </td>
        <td class="num">${Number(p.units_sold).toLocaleString("en-IN")}</td>
        <td class="num" style="color: var(--text-primary); font-weight: 600;">${p.total_revenue_formatted}</td>
        <td class="num" style="color: #38bdf8;">${p.total_profit_formatted}</td>
        <td class="num"><span class="margin-pill">${p.profit_margin_percentage}%</span></td>
      `;
      dom.analyticsTopProductsTbody.appendChild(tr);
    });
  }

  function renderWarehouseInventoryRisk(invRisk, restockQueue) {
    // 1. Overall Health Score
    if (invRisk) {
      if (dom.invHealthScoreVal) dom.invHealthScoreVal.textContent = `${invRisk.health_score_percentage}%`;
      if (dom.invTotalSkusVal) dom.invTotalSkusVal.textContent = invRisk.total_skus;
      if (dom.invCriticalAlertsVal) dom.invCriticalAlertsVal.textContent = invRisk.critical_alerts_count;

      // 2. Warehouse Cards Grid
      if (dom.warehouseCardsGrid && Array.isArray(invRisk.warehouse_breakdown)) {
        dom.warehouseCardsGrid.innerHTML = "";
        invRisk.warehouse_breakdown.forEach((w) => {
          const card = document.createElement("div");
          card.className = "warehouse-card";

          let badgeClass = "normal";
          if (w.health_status === "High Risk") badgeClass = "high";
          else if (w.health_status === "Moderate Risk") badgeClass = "moderate";

          card.innerHTML = `
            <div class="wh-card-header">
              <span class="wh-name">${w.warehouse} Hub</span>
              <span class="wh-badge ${badgeClass}">${w.health_status}</span>
            </div>
            <div class="wh-stats-grid">
              <div class="wh-stat-item">
                <span class="lbl">SKUs Monitored</span>
                <span class="val">${w.total_skus}</span>
              </div>
              <div class="wh-stat-item">
                <span class="lbl">Total Units</span>
                <span class="val">${Number(w.total_units).toLocaleString("en-IN")}</span>
              </div>
              <div class="wh-stat-item">
                <span class="lbl">Restock Alerts</span>
                <span class="val ${w.restock_alerts > 0 ? "alert" : ""}">${w.restock_alerts}</span>
              </div>
              <div class="wh-stat-item">
                <span class="lbl">In-Stock SKUs</span>
                <span class="val">${w.in_stock_count}</span>
              </div>
            </div>
          `;
          dom.warehouseCardsGrid.appendChild(card);
        });
      }
    }

    // 3. Restock Priority Queue Table
    if (dom.analyticsRestockTbody && Array.isArray(restockQueue)) {
      dom.analyticsRestockTbody.innerHTML = "";

      if (restockQueue.length === 0) {
        dom.analyticsRestockTbody.innerHTML = `
          <tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 18px;">All inventory levels are currently above reorder thresholds.</td></tr>
        `;
      } else {
        restockQueue.forEach((item) => {
          const tr = document.createElement("tr");
          const isCritical = Number(item.stock_difference) <= -8;
          const statusClass = isCritical ? "urgent" : "urgent";
          const statusLabel = isCritical ? "Critical" : "Low Stock";

          tr.innerHTML = `
            <td>${item.product_name}</td>
            <td>${item.product_category}</td>
            <td>${item.warehouse}</td>
            <td class="num urgent">${item.stock_quantity}</td>
            <td class="num">${item.reorder_level}</td>
            <td class="num urgent">${item.stock_difference}</td>
            <td><span class="${statusClass}">${statusLabel}</span></td>
          `;
          dom.analyticsRestockTbody.appendChild(tr);
        });
      }
    }
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

    // Refresh Analytics Button
    if (dom.btnRefreshAnalytics) {
      dom.btnRefreshAnalytics.addEventListener("click", (e) => {
        e.preventDefault();
        loadDashboardAnalytics(true);
      });
    }

    // Date Range Presets
    dom.filterPresetBtns.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const preset = btn.dataset.preset;
        state.analyticsActivePreset = preset;

        dom.filterPresetBtns.forEach((b) => b.classList.toggle("active", b === btn));

        if (preset === "all") {
          state.analyticsStartDate = null;
          state.analyticsEndDate = null;
          if (dom.analyticsStartDate) dom.analyticsStartDate.value = "";
          if (dom.analyticsEndDate) dom.analyticsEndDate.value = "";
        } else if (preset === "fy2026") {
          state.analyticsStartDate = "2026-01-01";
          state.analyticsEndDate = "2026-10-31";
          if (dom.analyticsStartDate) dom.analyticsStartDate.value = "2026-01-01";
          if (dom.analyticsEndDate) dom.analyticsEndDate.value = "2026-10-31";
        } else if (preset === "fy2025") {
          state.analyticsStartDate = "2025-01-01";
          state.analyticsEndDate = "2025-12-31";
          if (dom.analyticsStartDate) dom.analyticsStartDate.value = "2025-01-01";
          if (dom.analyticsEndDate) dom.analyticsEndDate.value = "2025-12-31";
        } else if (preset === "last90") {
          state.analyticsStartDate = "2026-08-02";
          state.analyticsEndDate = "2026-10-31";
          if (dom.analyticsStartDate) dom.analyticsStartDate.value = "2026-08-02";
          if (dom.analyticsEndDate) dom.analyticsEndDate.value = "2026-10-31";
        } else if (preset === "last30") {
          state.analyticsStartDate = "2026-10-01";
          state.analyticsEndDate = "2026-10-31";
          if (dom.analyticsStartDate) dom.analyticsStartDate.value = "2026-10-01";
          if (dom.analyticsEndDate) dom.analyticsEndDate.value = "2026-10-31";
        }

        loadDashboardAnalytics(false);
      });
    });

    // Custom Date Range Apply Button
    if (dom.btnApplyDateFilter) {
      dom.btnApplyDateFilter.addEventListener("click", (e) => {
        e.preventDefault();
        const startVal = dom.analyticsStartDate ? dom.analyticsStartDate.value.trim() : "";
        const endVal = dom.analyticsEndDate ? dom.analyticsEndDate.value.trim() : "";

        if (startVal && endVal && startVal > endVal) {
          showToast("Start date cannot be after end date", false);
          return;
        }

        state.analyticsStartDate = startVal || null;
        state.analyticsEndDate = endVal || null;
        state.analyticsActivePreset = null;
        dom.filterPresetBtns.forEach((b) => b.classList.remove("active"));

        loadDashboardAnalytics(false);
      });
    }

    // Custom Date Range Reset Button
    if (dom.btnResetDateFilter) {
      dom.btnResetDateFilter.addEventListener("click", (e) => {
        e.preventDefault();
        state.analyticsStartDate = null;
        state.analyticsEndDate = null;
        state.analyticsActivePreset = "all";
        if (dom.analyticsStartDate) dom.analyticsStartDate.value = "";
        if (dom.analyticsEndDate) dom.analyticsEndDate.value = "";
        dom.filterPresetBtns.forEach((b) => b.classList.toggle("active", b.dataset.preset === "all"));

        loadDashboardAnalytics(false);
      });
    }

    // Granularity Toggle Buttons (Monthly / Daily)
    dom.granularityBtns.forEach((btn) => {
      btn.addEventListener("click", (e) => {
        e.preventDefault();
        const gran = btn.dataset.granularity;
        if (!gran || gran === state.analyticsGranularity) return;

        state.analyticsGranularity = gran;
        dom.granularityBtns.forEach((b) => b.classList.toggle("active", b === btn));

        loadDashboardAnalytics(false);
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

    // Preload dashboard analytics in background
    loadDashboardAnalytics(false);
  }

  // Initialize once DOM is ready
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();

