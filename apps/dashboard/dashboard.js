"use strict";

const endpoints = {
  health: "/health",
  authStatus: "/api/v1/auth/status",
  authLogin: "/api/v1/auth/login",
  authSession: "/api/v1/auth/session",
  authLogout: "/api/v1/auth/logout",
  people: "/api/v1/vision/people",
  objects: "/api/v1/vision/objects",
  model: "/api/v1/vision/model",
  performance: "/api/v1/vision/performance",
  benchmark: "/api/v1/system/benchmark",
  storage: "/api/v1/system/storage",
  retentionPreview: "/api/v1/system/retention-preview",
  retentionCleanupHistory:
    "/api/v1/system/retention-cleanup-history",
  evidenceIntegrity: "/api/v1/events/evidence-integrity",
  frame: "/api/v1/vision/frame",
  events: "/api/v1/events",
  eventSummary: "/api/v1/events/summary/recent",
  tools: "/api/v1/harness/tools",
  agentEvaluation: "/api/v1/harness/evaluations/latest",
  agent: "/api/v1/agent/tasks",
  agentJobs: "/api/v1/agent/jobs",
  agentSessions: "/api/v1/agent/sessions",
  agentMemories: "/api/v1/agent/memories",
  agentModelMode: "/api/v1/agent/model-mode",
  system: "/api/v1/system/status",
  camera: "/api/v1/camera/status",
  zones: "/api/v1/zones",
  zoneDefaults: "/api/v1/zones/defaults",
};

const eventLabels = {
  OBJECT_APPEARED: "物品出现",
  OBJECT_REMOVED: "物品移除",
  OBJECT_LEFT_BEHIND: "物品遗留",
  ZONE_ENTER: "进入区域",
  ZONE_EXIT: "离开区域",
  ZONE_DWELL: "长时间停留",
  CAMERA_OFFLINE: "摄像头离线",
  CAMERA_RECOVERED: "摄像头恢复",
};

const nodes = {
  authBackdrop: document.querySelector("#auth-backdrop"),
  authLoginForm: document.querySelector("#auth-login-form"),
  authUsername: document.querySelector("#auth-username"),
  authPassword: document.querySelector("#auth-password"),
  authLoginSubmit: document.querySelector("#auth-login-submit"),
  authError: document.querySelector("#auth-error"),
  authIdentity: document.querySelector("#auth-identity"),
  authCurrentUser: document.querySelector("#auth-current-user"),
  authLogout: document.querySelector("#auth-logout"),
  button: document.querySelector("#refresh-button"),
  dot: document.querySelector("#status-dot"),
  connection: document.querySelector("#connection-label"),
  notice: document.querySelector("#notice"),
  peopleCount: document.querySelector("#people-count"),
  peopleDetail: document.querySelector("#people-detail"),
  objectCount: document.querySelector("#object-count"),
  objectDetail: document.querySelector("#object-detail"),
  eventCount: document.querySelector("#event-count"),
  visionStatus: document.querySelector("#vision-status"),
  visionAge: document.querySelector("#vision-age"),
  objectList: document.querySelector("#object-list"),
  eventList: document.querySelector("#event-list"),
  eventSummary: document.querySelector("#event-summary"),
  eventTrend: document.querySelector("#event-trend"),
  cameraId: document.querySelector("#camera-id"),
  apiStatus: document.querySelector("#api-status"),
  databaseStatus: document.querySelector("#database-status"),
  agentModel: document.querySelector("#agent-model"),
  agentModelResilience: document.querySelector(
    "#agent-model-resilience"
  ),
  visionModelRuntime: document.querySelector(
    "#vision-model-runtime"
  ),
  visionPerformanceRuntime: document.querySelector(
    "#vision-performance-runtime"
  ),
  runtimeBenchmarkStatus: document.querySelector(
    "#runtime-benchmark-status"
  ),
  storageUsage: document.querySelector("#storage-usage"),
  retentionPreviewStatus: document.querySelector(
    "#retention-preview-status"
  ),
  retentionCleanupHistoryStatus: document.querySelector(
    "#retention-cleanup-history-status"
  ),
  evidenceIntegrityStatus: document.querySelector(
    "#evidence-integrity-status"
  ),
  mcpRuntimeStatus: document.querySelector("#mcp-runtime-status"),
  mcpToolsToggle: document.querySelector("#mcp-tools-toggle"),
  mcpToolsPanel: document.querySelector("#mcp-tools-panel"),
  mcpToolsSummary: document.querySelector("#mcp-tools-summary"),
  mcpToolsList: document.querySelector("#mcp-tools-list"),
  cameraRuntimeStatus: document.querySelector(
    "#camera-runtime-status"
  ),
  lastRefresh: document.querySelector("#last-refresh"),
  agentMode: document.querySelector("#agent-mode"),
  agentModelSwitchStatus: document.querySelector(
    "#agent-model-switch-status"
  ),
  agentModeOnline: document.querySelector("#agent-mode-online"),
  agentModeOffline: document.querySelector("#agent-mode-offline"),
  agentSessionStatus: document.querySelector(
    "#agent-session-status"
  ),
  agentSessionPrivacy: document.querySelector(
    "#agent-session-privacy"
  ),
  agentSessionClear: document.querySelector(
    "#agent-session-clear"
  ),
  agentLongTermStatus: document.querySelector(
    "#agent-long-term-status"
  ),
  agentLongTermList: document.querySelector(
    "#agent-long-term-list"
  ),
  agentLongTermRefresh: document.querySelector(
    "#agent-long-term-refresh"
  ),
  agentEvaluationStatus: document.querySelector(
    "#agent-evaluation-status"
  ),
  agentEvaluationBadge: document.querySelector(
    "#agent-evaluation-badge"
  ),
  agentEvaluationMeta: document.querySelector(
    "#agent-evaluation-meta"
  ),
  agentForm: document.querySelector("#agent-form"),
  agentMessage: document.querySelector("#agent-message"),
  messageCount: document.querySelector("#message-count"),
  agentSubmit: document.querySelector("#agent-submit"),
  agentJobCancel: document.querySelector("#agent-job-cancel"),
  agentResponse: document.querySelector("#agent-response"),
  agentTaskStatus: document.querySelector("#agent-task-status"),
  agentTaskMeta: document.querySelector("#agent-task-meta"),
  agentAnswer: document.querySelector("#agent-answer"),
  agentToolResults: document.querySelector("#agent-tool-results"),
  agentWorkbench: document.querySelector("#agent-workbench"),
  agentWorkbenchSummary: document.querySelector(
    "#agent-workbench-summary"
  ),
  agentRunTaskId: document.querySelector("#agent-run-task-id"),
  agentRunModel: document.querySelector("#agent-run-model"),
  agentRunSkill: document.querySelector("#agent-run-skill"),
  agentRunToolRoute: document.querySelector(
    "#agent-run-tool-route"
  ),
  agentRunModelResilience: document.querySelector(
    "#agent-run-model-resilience"
  ),
  agentRunSteps: document.querySelector("#agent-run-steps"),
  agentRunDuration: document.querySelector("#agent-run-duration"),
  agentRunBudget: document.querySelector("#agent-run-budget"),
  agentRunTimeline: document.querySelector("#agent-run-timeline"),
  agentConfirmation: document.querySelector("#agent-confirmation"),
  agentConfirmationRisk: document.querySelector(
    "#agent-confirmation-risk"
  ),
  agentConfirmationTool: document.querySelector(
    "#agent-confirmation-tool"
  ),
  agentConfirmationDescription: document.querySelector(
    "#agent-confirmation-description"
  ),
  agentConfirmationArguments: document.querySelector(
    "#agent-confirmation-arguments"
  ),
  agentConfirm: document.querySelector("#agent-confirm"),
  agentCancel: document.querySelector("#agent-cancel"),
  agentSnapshot: document.querySelector("#agent-snapshot"),
  agentSnapshotImage: document.querySelector(
    "#agent-snapshot-image"
  ),
  agentSnapshotMeta: document.querySelector(
    "#agent-snapshot-meta"
  ),
  agentSnapshotLink: document.querySelector(
    "#agent-snapshot-link"
  ),
  agentReport: document.querySelector("#agent-report"),
  agentReportMeta: document.querySelector("#agent-report-meta"),
  agentReportLink: document.querySelector("#agent-report-link"),
  liveFrame: document.querySelector("#live-frame"),
  liveFrameStatus: document.querySelector("#live-frame-status"),
  framePlaceholder: document.querySelector("#frame-placeholder"),
  frameCameraLabel: document.querySelector("#frame-camera-label"),
  frameFreshnessLabel: document.querySelector("#frame-freshness-label"),
  systemLoad: document.querySelector("#system-load"),
  systemMemory: document.querySelector("#system-memory"),
  systemTemperature: document.querySelector("#system-temperature"),
  systemDisk: document.querySelector("#system-disk"),
  systemUptime: document.querySelector("#system-uptime"),
  eventFilterForm: document.querySelector("#event-filter-form"),
  eventTypeFilter: document.querySelector("#event-type-filter"),
  eventStatusFilter: document.querySelector(
    "#event-status-filter"
  ),
  eventSeverityFilter: document.querySelector(
    "#event-severity-filter"
  ),
  eventObjectFilter: document.querySelector("#event-object-filter"),
  eventCameraFilter: document.querySelector("#event-camera-filter"),
  eventLimitFilter: document.querySelector("#event-limit-filter"),
  eventMinutesFilter: document.querySelector("#event-minutes-filter"),
  eventFilterReset: document.querySelector("#event-filter-reset"),
  eventResultCount: document.querySelector("#event-result-count"),
  eventLoadMore: document.querySelector("#event-load-more"),
  eventCollapse: document.querySelector("#event-collapse"),
  eventsPanel: document.querySelector(".events-panel"),
  eventDetailBackdrop: document.querySelector("#event-detail-backdrop"),
  eventDetailClose: document.querySelector("#event-detail-close"),
  eventDetailTitle: document.querySelector("#event-detail-title"),
  eventDetailFields: document.querySelector("#event-detail-fields"),
  eventEvidenceGrid: document.querySelector("#event-evidence-grid"),
  eventDetailJson: document.querySelector("#event-detail-json"),
  eventDispositionStatus: document.querySelector(
    "#event-disposition-status"
  ),
  eventEvidenceIntegrity: document.querySelector(
    "#event-evidence-integrity"
  ),
  eventAcknowledge: document.querySelector("#event-acknowledge"),
  zoneCanvas: document.querySelector("#zone-canvas"),
  zoneStatus: document.querySelector("#zone-status"),
  zoneRuntimeStatus: document.querySelector(
    "#zone-runtime-status"
  ),
  zoneLegend: document.querySelector("#zone-legend"),
  zoneDrawToggle: document.querySelector("#zone-draw-toggle"),
  zoneUndoPoint: document.querySelector("#zone-undo-point"),
  zoneClearDraft: document.querySelector("#zone-clear-draft"),
  zoneDraftCount: document.querySelector("#zone-draft-count"),
  zoneDraftJson: document.querySelector("#zone-draft-json"),
  zoneEditTarget: document.querySelector("#zone-edit-target"),
  zoneApplyDraft: document.querySelector("#zone-apply-draft"),
  zoneSnapBottom: document.querySelector("#zone-snap-bottom"),
  zoneRestoreDefault: document.querySelector(
    "#zone-restore-default"
  ),
  zoneDiscardChanges: document.querySelector(
    "#zone-discard-changes"
  ),
  zoneDirtyStatus: document.querySelector("#zone-dirty-status"),
  zoneAnchorGuidance: document.querySelector(
    "#zone-anchor-guidance"
  ),
  zoneSaveForm: document.querySelector("#zone-save-form"),
  zoneAdminToken: document.querySelector("#zone-admin-token"),
  zoneSaveConfirmation: document.querySelector(
    "#zone-save-confirmation"
  ),
  zoneSaveSubmit: document.querySelector("#zone-save-submit"),
  zoneSaveMode: document.querySelector("#zone-save-mode"),
  zoneSaveResult: document.querySelector("#zone-save-result"),
};

let lastEventDetailTrigger = null;
let currentEventDetail = null;
let configuredZones = [];
let factoryDefaultZones = [];
let draftZonePoints = [];
let zoneDrawingEnabled = false;
let zoneConfigVersion = null;
let zoneConfigDirty = false;
let zoneSaveEnabled = false;
let zoneVersionConflict = false;
let visionZoneRuntime = null;
let activeAgentTaskId = null;
let activeAgentToolName = null;
let liveFrameRequestPending = false;
let visionModelLoaded = false;
let eventNextCursor = null;
let loadedEventCount = 0;
let eventPagesExpanded = false;
let mcpToolsLoaded = false;
let modelSwitchPending = false;
let currentAgentModel = {};
let workbenchTaskId = null;
let activeAgentSessionId = null;
let activeAgentJobId = null;
let activeAgentEventSource = null;
let authCsrfToken = null;
let dashboardStarted = false;
let dashboardIntervals = [];
const agentSessionStorageKey = "edgesentinel-agent-session";
const zoneColors = ["#4fd1c5", "#a78bfa", "#f4b860", "#b7e36b"];

function authenticatedHeaders(extra = {}) {
  const headers = { ...extra };
  if (authCsrfToken) {
    headers["X-EdgeSentinel-CSRF"] = authCsrfToken;
  }
  return headers;
}

function readAgentSessionId() {
  try {
    const sessionId = window.sessionStorage.getItem(
      agentSessionStorageKey
    );
    return /^sess_[0-9a-f]{32}$/.test(sessionId || "")
      ? sessionId
      : null;
  } catch (error) {
    return null;
  }
}

function persistAgentSessionId(sessionId) {
  activeAgentSessionId = /^sess_[0-9a-f]{32}$/.test(
    sessionId || ""
  )
    ? sessionId
    : null;
  try {
    if (activeAgentSessionId) {
      window.sessionStorage.setItem(
        agentSessionStorageKey,
        activeAgentSessionId
      );
    } else {
      window.sessionStorage.removeItem(agentSessionStorageKey);
    }
  } catch (error) {
    // The Agent still works if browser session storage is unavailable.
  }
}

function renderAgentMemory(memory, sessionId) {
  if (!sessionId || !memory) {
    nodes.agentSessionStatus.textContent =
      "尚未建立会话 · 首次提问时自动创建";
    nodes.agentSessionPrivacy.textContent =
      "最多保留12轮、7天后过期；不保存工具原始结果、图片、证据路径或凭据。";
    nodes.agentSessionClear.disabled = true;
    return;
  }
  persistAgentSessionId(sessionId);
  const turnCount = Number(memory.turn_count || 0);
  const maximum = Number(memory.max_turns || 12);
  nodes.agentSessionStatus.textContent =
    `${sessionId.slice(0, 13)}… · ${turnCount}/${maximum}轮 · ` +
    `到期 ${formatTimestamp(memory.expires_at)}`;
  nodes.agentSessionPrivacy.textContent =
    "仅保存用户问题和最终回答；工具原始结果、图片、证据路径和凭据均不写入会话记忆。";
  nodes.agentSessionClear.disabled = false;
}

async function restoreAgentSession() {
  const sessionId = readAgentSessionId();
  if (!sessionId) {
    renderAgentMemory(null, null);
    return;
  }
  activeAgentSessionId = sessionId;
  try {
    const memory = await getJson(
      `${endpoints.agentSessions}/${encodeURIComponent(sessionId)}`
    );
    renderAgentMemory(memory, sessionId);
  } catch (error) {
    persistAgentSessionId(null);
    renderAgentMemory(null, null);
  }
}

function renderLongTermMemory(payload) {
  const records = Array.isArray(payload.records)
    ? payload.records.slice(0, 20)
    : [];
  nodes.agentLongTermStatus.textContent =
    `${Number(payload.total_records || 0)}/100条 · ` +
    "本地持久化";
  nodes.agentLongTermList.replaceChildren();
  if (!records.length) {
    const empty = document.createElement("li");
    empty.className = "empty";
    empty.textContent = "尚无经过确认的长期事实或偏好";
    nodes.agentLongTermList.appendChild(empty);
    return;
  }
  records.forEach((record) => {
    const item = document.createElement("li");
    const heading = document.createElement("div");
    const key = document.createElement("strong");
    const badge = document.createElement("span");
    const value = document.createElement("p");
    const metadata = document.createElement("small");
    key.textContent = record.key || "未命名";
    badge.textContent = record.kind || "FACT";
    badge.className = "agent-long-term-kind";
    heading.append(key, badge);
    value.textContent = record.value || "";
    metadata.textContent =
      `${record.memory_id || "unknown"} · 修订${Number(record.revision || 1)} · ` +
      `${formatTimestamp(record.updated_at)}`;
    item.append(heading, value, metadata);
    nodes.agentLongTermList.appendChild(item);
  });
}

async function refreshLongTermMemory() {
  nodes.agentLongTermRefresh.disabled = true;
  try {
    const payload = await getJson(`${endpoints.agentMemories}?limit=20`);
    renderLongTermMemory(payload);
  } catch (error) {
    nodes.agentLongTermStatus.textContent =
      `读取失败：${error.message || "未知错误"}`;
  } finally {
    nodes.agentLongTermRefresh.disabled = false;
  }
}

async function clearAgentSession() {
  if (!activeAgentSessionId) {
    return;
  }
  if (!window.confirm(
    "确定清空当前短期会话吗？工具结果和事件数据不会被删除。"
  )) {
    return;
  }
  nodes.agentSessionClear.disabled = true;
  try {
    const response = await fetch(
      `${endpoints.agentSessions}/${encodeURIComponent(activeAgentSessionId)}/clear`,
      {
        method: "POST",
        headers: authenticatedHeaders({
          Accept: "application/json",
          "Content-Type": "application/json; charset=utf-8",
        }),
        body: JSON.stringify({
          confirmation: "CLEAR_AGENT_SESSION",
        }),
      }
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    persistAgentSessionId(null);
    renderAgentMemory(null, null);
    nodes.agentResponse.classList.add("hidden");
    nodes.agentMessage.value = "";
    updateMessageCount();
  } catch (error) {
    nodes.agentSessionStatus.textContent =
      `会话清空失败：${error.message || "未知错误"}`;
    nodes.agentSessionClear.disabled = false;
  }
}

async function ensureAgentSession() {
  if (activeAgentSessionId) {
    return activeAgentSessionId;
  }
  const response = await fetch(endpoints.agentSessions, {
    method: "POST",
    headers: authenticatedHeaders({ Accept: "application/json" }),
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.detail || `HTTP ${response.status}`);
  }
  renderAgentMemory(payload, payload.session_id);
  return payload.session_id;
}

async function getJson(path) {
  const response = await fetch(path, {
    headers: { Accept: "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    if (response.status === 401) {
      showAuthenticationRequired();
    }
    throw new Error(`${path} returned HTTP ${response.status}`);
  }
  return response.json();
}

function showAuthenticationRequired(message = "请登录后继续。") {
  authCsrfToken = null;
  nodes.authIdentity.classList.add("hidden");
  nodes.authBackdrop.classList.remove("hidden");
  nodes.authError.textContent = message;
  nodes.authPassword.value = "";
  nodes.authUsername.focus();
}

function applyAuthenticatedSession(session) {
  authCsrfToken = session.csrf_token || null;
  nodes.authCurrentUser.textContent =
    `${session.username || "operator"} · ${session.role || "viewer"}`;
  nodes.authIdentity.classList.remove("hidden");
  nodes.authBackdrop.classList.add("hidden");
  nodes.authError.textContent = "";
}

async function submitAuthentication(event) {
  event.preventDefault();
  nodes.authLoginSubmit.disabled = true;
  nodes.authError.textContent = "正在验证…";
  try {
    const response = await fetch(endpoints.authLogin, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
      },
      body: JSON.stringify({
        username: nodes.authUsername.value,
        password: nodes.authPassword.value,
      }),
      cache: "no-store",
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    nodes.authPassword.value = "";
    applyAuthenticatedSession(payload);
    startDashboard();
  } catch (error) {
    showAuthenticationRequired(
      `登录失败：${error.message || "凭据无效"}`
    );
  } finally {
    nodes.authLoginSubmit.disabled = false;
  }
}

async function logoutAuthentication() {
  nodes.authLogout.disabled = true;
  try {
    await fetch(endpoints.authLogout, {
      method: "POST",
      headers: authenticatedHeaders({ Accept: "application/json" }),
      cache: "no-store",
    });
  } finally {
    dashboardIntervals.forEach((timer) => window.clearInterval(timer));
    dashboardIntervals = [];
    dashboardStarted = false;
    nodes.authLogout.disabled = false;
    showAuthenticationRequired("已安全退出。")
  }
}

function startDashboard() {
  if (dashboardStarted) {
    return;
  }
  dashboardStarted = true;
  refreshDashboard();
  refreshAgentEvaluation();
  restoreAgentSession();
  refreshLongTermMemory();
  refreshLiveFrame();
  updateZoneDraft();
  dashboardIntervals = [
    window.setInterval(refreshDashboard, 5000),
    window.setInterval(refreshAgentEvaluation, 30000),
    window.setInterval(refreshLongTermMemory, 30000),
    window.setInterval(refreshLiveFrame, 500),
  ];
}

async function initializeAuthentication() {
  try {
    const statusResponse = await fetch(endpoints.authStatus, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    const status = await statusResponse.json();
    if (!statusResponse.ok || (status.enabled && !status.ready)) {
      showAuthenticationRequired(
        "认证已启用但 root 凭据尚未正确配置。"
      );
      nodes.authLoginSubmit.disabled = true;
      return;
    }
    const response = await fetch(endpoints.authSession, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (response.status === 401) {
      showAuthenticationRequired();
      return;
    }
    const session = await response.json();
    if (!response.ok) {
      throw new Error(session.detail || `HTTP ${response.status}`);
    }
    applyAuthenticatedSession(session);
    startDashboard();
  } catch (error) {
    showAuthenticationRequired(
      `认证服务不可用：${error.message || "未知错误"}`
    );
  }
}

function renderAgentEvaluation(report) {
  const summary = report.summary || {};
  const metrics = report.metrics || {};
  const dataset = report.dataset || {};
  const toolSelection = metrics.tool_selection_accuracy || {};
  const argumentAccuracy = metrics.argument_accuracy || {};
  const violations = Number(
    metrics.unexpected_policy_violations || 0
  );
  nodes.agentEvaluationBadge.textContent = report.status || "UNKNOWN";
  nodes.agentEvaluationBadge.className =
    `agent-evaluation-badge ${String(report.status || "fail").toLowerCase()}`;
  nodes.agentEvaluationStatus.textContent =
    `${Number(summary.passed_cases || 0)}/${Number(summary.total_cases || 0)} ` +
    `通过 · 工具路由 ${Math.round(Number(toolSelection.rate || 0) * 100)}% ` +
    `· 参数 ${Math.round(Number(argumentAccuracy.rate || 0) * 100)}%`;
  nodes.agentEvaluationMeta.textContent =
    `${dataset.dataset_id || "unknown"}@${dataset.version || "unknown"} ` +
    `· ${String(dataset.sha256 || "").slice(0, 12)}… ` +
    `· 策略违规 ${violations} · 隔离离线评测`;
}

async function refreshAgentEvaluation() {
  try {
    renderAgentEvaluation(
      await getJson(endpoints.agentEvaluation)
    );
  } catch (error) {
    nodes.agentEvaluationBadge.textContent = "NO REPORT";
    nodes.agentEvaluationBadge.className =
      "agent-evaluation-badge pending";
    nodes.agentEvaluationStatus.textContent = "尚未运行评测";
    nodes.agentEvaluationMeta.textContent =
      "在容器中运行 scripts/run_agent_evaluation_test.sh 生成只读基线报告。";
  }
}

function isMcpTool(schema) {
  const annotations = schema.annotations || {};
  return Boolean(
    annotations.readOnlyHint &&
    annotations.riskLevel === "L0" &&
    annotations.autoExecute &&
    !annotations.requiresConfirmation
  );
}

function renderMcpCatalog(payload) {
  const tools = (Array.isArray(payload.tools) ? payload.tools : [])
    .filter(isMcpTool);
  nodes.mcpToolsList.replaceChildren();
  nodes.mcpToolsSummary.textContent =
    `${tools.length} 个只读 MCP 工具 · 点击名称查看参数 Schema`;
  nodes.mcpRuntimeStatus.textContent =
    `按需启动 · ${tools.length}工具 · 5资源 · 3提示`;

  tools.forEach((tool) => {
    const details = document.createElement("details");
    details.className = "mcp-tool";
    const summary = document.createElement("summary");
    const name = document.createElement("code");
    name.textContent = tool.name;
    const badges = document.createElement("span");
    const annotations = tool.annotations || {};
    badges.textContent = annotations.openWorldHint
      ? "L0 · 只读 · 外部网络"
      : "L0 · 只读 · 本地";
    summary.append(name, badges);

    const description = document.createElement("p");
    description.textContent = tool.description || "没有工具说明";
    const schema = document.createElement("pre");
    schema.textContent = JSON.stringify(
      tool.inputSchema || {},
      null,
      2
    );
    details.append(summary, description, schema);
    nodes.mcpToolsList.append(details);
  });
  mcpToolsLoaded = true;
}

async function toggleMcpCatalog() {
  const opening = nodes.mcpToolsPanel.classList.contains("hidden");
  if (!opening) {
    nodes.mcpToolsPanel.classList.add("hidden");
    nodes.mcpToolsToggle.textContent = "查看 MCP 工具";
    return;
  }

  nodes.mcpToolsPanel.classList.remove("hidden");
  nodes.mcpToolsPanel.classList.remove("error");
  nodes.mcpToolsToggle.textContent = "隐藏 MCP 工具";
  if (mcpToolsLoaded) {
    return;
  }
  nodes.mcpToolsToggle.disabled = true;
  nodes.mcpToolsSummary.textContent = "正在读取 MCP 工具目录…";
  try {
    renderMcpCatalog(await getJson(endpoints.tools));
  } catch (error) {
    nodes.mcpToolsSummary.textContent =
      "MCP 工具目录读取失败，请稍后重试。";
    nodes.mcpToolsPanel.classList.add("error");
  } finally {
    nodes.mcpToolsToggle.disabled = false;
  }
}

function setConnection(online) {
  nodes.dot.classList.toggle("online", online);
  nodes.dot.classList.toggle("offline", !online);
  nodes.connection.textContent = online ? "API 在线" : "API 连接失败";
}

function renderHealth(health) {
  nodes.eventCount.textContent = String(health.database.event_count);
  nodes.apiStatus.textContent = health.status === "ok" ? "正常" : "降级";
  nodes.databaseStatus.textContent =
    health.database.status === "ok" ? "正常" : "不可用";
  const model = health.agent_model || {};
  nodes.agentModel.textContent =
    model.mode === "remote"
      ? `${model.provider} · ${model.model}`
      : "本地离线规则";
  nodes.agentMode.textContent =
    model.mode === "remote"
      ? `远程 · ${model.provider}`
      : "离线规则模型";
  renderAgentModelResilience(model);
  renderAgentModelSwitch(model);
}

function renderAgentModelResilience(model) {
  const resilience = (model || {}).resilience || {};
  if (!resilience.enabled) {
    nodes.agentModelResilience.textContent = "仅离线 · 无外部依赖";
  } else {
    const circuit = resilience.circuit_state || "UNKNOWN";
    const fallbackCount = Number(resilience.fallback_count || 0);
    nodes.agentModelResilience.textContent =
      `${circuit} · 最多${Number(resilience.retry_max_attempts || 1)}次 · ` +
      `离线降级${fallbackCount}次`;
  }
}

function renderAgentModelSwitch(model) {
  currentAgentModel = model || {};
  const available = Array.isArray(model.available_modes)
    ? model.available_modes
    : [];
  const onlineAvailable = available.includes("remote");
  const activeOnline = model.mode === "remote";
  const locked =
    modelSwitchPending ||
    Boolean(activeAgentTaskId) ||
    nodes.agentMessage.disabled;

  nodes.agentModeOnline.classList.toggle("active", activeOnline);
  nodes.agentModeOffline.classList.toggle("active", !activeOnline);
  nodes.agentModeOnline.disabled = locked || !onlineAvailable;
  nodes.agentModeOffline.disabled = locked;

  if (!model.runtime_switchable) {
    nodes.agentModelSwitchStatus.textContent =
      "当前服务不支持运行时切换";
  } else if (!onlineAvailable) {
    nodes.agentModelSwitchStatus.textContent =
      "未配置在线凭据，仅可使用离线规则";
  } else {
    const bootLabel =
      model.boot_mode === "remote" ? "在线" : "离线";
    nodes.agentModelSwitchStatus.textContent =
      `${activeOnline ? "当前在线" : "当前离线"} · ` +
      `重启后默认${bootLabel}`;
  }
}

async function switchAgentModel(mode) {
  const targetLabel =
    mode === "online" ? "在线 DeepSeek" : "离线规则";
  if (
    activeAgentTaskId ||
    !window.confirm(
      `确认把 Agent 回答模型切换为“${targetLabel}”吗？`
    )
  ) {
    return;
  }
  modelSwitchPending = true;
  let switchError = null;
  renderAgentModelSwitch(currentAgentModel);
  nodes.agentModelSwitchStatus.textContent =
    `正在切换到${targetLabel}…`;
  try {
    const response = await fetch(endpoints.agentModelMode, {
      method: "PUT",
      headers: authenticatedHeaders({
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
      }),
      body: JSON.stringify({
        mode,
        confirmation: "SWITCH_AGENT_MODEL",
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    renderAgentModelSwitch(payload);
    renderAgentModelResilience(payload);
    nodes.agentModel.textContent =
      payload.mode === "remote"
        ? `${payload.provider} · ${payload.model}`
        : "本地离线规则";
    nodes.agentMode.textContent =
      payload.mode === "remote"
        ? `远程 · ${payload.provider}`
        : "离线规则模型";
  } catch (error) {
    switchError = error;
  } finally {
    modelSwitchPending = false;
    renderAgentModelSwitch(currentAgentModel);
    if (switchError) {
      nodes.agentModelSwitchStatus.textContent =
        `切换失败：${switchError.message || "未知错误"}`;
    }
  }
}

function renderCameraStatus(camera) {
  const labels = {
    STARTING: "正在启动",
    RUNNING: "正常",
    CAMERA_OFFLINE: "摄像头离线",
    WAITING_FOR_CAMERA: "等待摄像头",
    RESTARTING: "正在重启推理",
    VISION_STALLED: "画面中断，正在恢复",
    STOPPED: "已停止",
  };
  const label = labels[camera.status] || camera.status;
  nodes.cameraRuntimeStatus.textContent =
    camera.status === "RUNNING"
      ? `${label} · 第${camera.generation}代`
      : `${label} · 已重试${camera.restart_count}次`;
}

function renderVisionModel(model) {
  const artifact = model.artifact || {};
  const verification = model.verification || {};
  const precision = artifact.precision || "UNKNOWN";
  const integrity = verification.status || "UNKNOWN";
  nodes.visionModelRuntime.textContent =
    `${model.network || "unknown"} · ${precision} · ${integrity}`;
}

function renderVisionPerformance(performance) {
  const latency = performance.pipeline_latency_ms || {};
  nodes.visionPerformanceRuntime.textContent =
    `${Number(performance.processing_fps || 0).toFixed(1)} FPS · ` +
    `P95 ${Number(latency.p95 || 0).toFixed(1)} ms · ` +
    `${performance.status || "UNKNOWN"}`;
}

function renderRuntimeBenchmark(benchmark) {
  const performance = benchmark.performance || {};
  nodes.runtimeBenchmarkStatus.textContent =
    `${benchmark.status || "UNKNOWN"} · ` +
    `${Number(performance.minimum_fps || 0).toFixed(1)} FPS · ` +
    `P95 ${Number(
      performance.maximum_observed_p95_ms || 0
    ).toFixed(1)} ms`;
}

function renderStorageUsage(storage) {
  const totals = storage.totals || {};
  nodes.storageUsage.textContent =
    `${formatBytes(Number(totals.bytes || 0))} · ` +
    `${Number(totals.file_count || 0)}个文件`;
}

function renderRetentionPreview(preview) {
  const candidates = preview.candidates || {};
  nodes.retentionPreviewStatus.textContent =
    `${formatBytes(Number(candidates.bytes || 0))} · ` +
    `${Number(candidates.file_count || 0)}个旧文件 · 仅预览`;
}

function renderRetentionCleanupHistory(history) {
  const totals = history.totals || {};
  if (Number(history.record_count || 0) === 0) {
    nodes.retentionCleanupHistoryStatus.textContent =
      "尚无已执行清理";
    return;
  }
  nodes.retentionCleanupHistoryStatus.textContent =
    `${Number(history.record_count || 0)}次 · ` +
    `${Number(totals.deleted_file_count || 0)}个文件 · ` +
    `${formatBytes(Number(totals.deleted_bytes || 0))}`;
}

function renderEvidenceIntegrity(integrity) {
  nodes.evidenceIntegrityStatus.textContent =
    `${integrity.status || "UNKNOWN"} · ` +
    `${Number(integrity.valid_evidence_count || 0)}/` +
    `${Number(integrity.referenced_evidence_count || 0)}有效 · ` +
    `${Number(integrity.issue_count || 0)}个问题`;
}

function renderPeople(people) {
  nodes.peopleCount.textContent = String(people.current_people);
  nodes.peopleDetail.textContent =
    `可见 ${people.visible_people} · frame ${people.frame_id}`;
  renderFreshness(people);
  nodes.cameraId.textContent = people.camera_id;
  nodes.frameCameraLabel.textContent = people.camera_id.toUpperCase();
  visionZoneRuntime = people.zone_config || null;
  updateZoneRuntimeStatus();
}

function renderFreshness(payload) {
  const age = Number(payload.age_seconds);
  nodes.visionStatus.textContent = payload.stale ? "数据陈旧" : "实时";
  nodes.visionAge.textContent = `状态年龄 ${age.toFixed(1)} 秒`;
  nodes.frameFreshnessLabel.textContent = payload.stale
    ? `STALE · ${age.toFixed(1)}s`
    : `LIVE · ${age.toFixed(1)}s`;
}

function renderObjects(payload) {
  nodes.objectCount.textContent = String(payload.total_current);
  nodes.objectDetail.textContent =
    `${payload.objects.length} 个稳定类别`;
  nodes.objectList.replaceChildren();
  if (payload.objects.length === 0) {
    appendEmpty(nodes.objectList, "当前没有稳定物品");
    return;
  }
  payload.objects.forEach((object) => {
    const item = document.createElement("div");
    item.className = "object-item";
    const name = document.createElement("span");
    name.textContent = object.class_name;
    const count = document.createElement("strong");
    count.textContent = String(object.count);
    item.append(name, count);
    nodes.objectList.append(item);
  });
}

function renderZones(payload) {
  const incomingZones = Array.isArray(payload.zones)
    ? payload.zones
    : [];
  const incomingVersion = String(payload.config_version || "");
  zoneSaveEnabled = payload.save_enabled === true;
  if (!zoneConfigDirty || zoneConfigVersion === null) {
    configuredZones = JSON.parse(JSON.stringify(incomingZones));
    zoneConfigVersion = incomingVersion;
    zoneVersionConflict = false;
  } else if (incomingVersion !== zoneConfigVersion) {
    zoneVersionConflict = true;
    setZoneSaveResult(
      "服务器上的区域配置已变化。请放弃本地修改并重新绘制。",
      "error"
    );
  }
  nodes.zoneStatus.textContent = zoneConfigDirty
    ? `已加载 ${configuredZones.length} 个区域 · 有未保存修改`
    : `已加载 ${configuredZones.length} 个区域`;
  nodes.zoneSaveMode.textContent = zoneSaveEnabled
    ? "保存功能已启用"
    : "保存功能未启用";
  nodes.zoneSaveMode.classList.toggle(
    "enabled",
    zoneSaveEnabled
  );
  nodes.zoneLegend.replaceChildren();
  configuredZones.forEach((zone, index) => {
    const item = document.createElement("span");
    item.className = "zone-legend-item";
    const color = document.createElement("span");
    color.className = "zone-color";
    color.style.setProperty(
      "--zone-color",
      zoneColors[index % zoneColors.length]
    );
    const label = document.createElement("span");
    label.textContent =
      `${zone.name} · ${zone.target_classes.join(", ") || "all"}`;
    item.append(color, label);
    nodes.zoneLegend.append(item);
  });
  renderZoneTargetOptions();
  updateZoneControls();
  updateZoneRuntimeStatus();
  drawZoneCanvas();
}

function updateZoneRuntimeStatus() {
  nodes.zoneRuntimeStatus.classList.remove(
    "synced",
    "pending",
    "degraded"
  );
  if (!visionZoneRuntime || !visionZoneRuntime.enabled) {
    nodes.zoneRuntimeStatus.textContent =
      "视觉任务尚未提供区域版本";
    return;
  }
  if (visionZoneRuntime.status === "degraded") {
    nodes.zoneRuntimeStatus.classList.add("degraded");
    nodes.zoneRuntimeStatus.textContent =
      "热加载失败，推理继续使用上一有效版本";
    return;
  }
  if (!zoneConfigVersion) {
    nodes.zoneRuntimeStatus.textContent =
      "正在比对推理区域版本…";
    return;
  }
  const shortVersion = String(
    visionZoneRuntime.version || ""
  ).slice(0, 12);
  if (visionZoneRuntime.version === zoneConfigVersion) {
    nodes.zoneRuntimeStatus.classList.add("synced");
    nodes.zoneRuntimeStatus.textContent =
      `推理配置已同步 · ${shortVersion}`;
    return;
  }
  nodes.zoneRuntimeStatus.classList.add("pending");
  nodes.zoneRuntimeStatus.textContent =
    `等待视觉任务热加载 · 当前 ${shortVersion}`;
}

function renderZoneTargetOptions() {
  const previous = nodes.zoneEditTarget.value;
  nodes.zoneEditTarget.replaceChildren();
  configuredZones.forEach((zone) => {
    const option = document.createElement("option");
    option.value = zone.id;
    option.textContent = `${zone.name} (${zone.id})`;
    nodes.zoneEditTarget.append(option);
  });
  if (configuredZones.some((zone) => zone.id === previous)) {
    nodes.zoneEditTarget.value = previous;
  }
  nodes.zoneEditTarget.disabled = configuredZones.length === 0;
}

function renderDefaultZones(payload) {
  factoryDefaultZones = Array.isArray(payload.zones)
    ? JSON.parse(JSON.stringify(payload.zones))
    : [];
  updateZoneControls();
}

function drawZoneCanvas() {
  const canvas = nodes.zoneCanvas;
  const context = canvas.getContext("2d");
  context.clearRect(0, 0, canvas.width, canvas.height);
  configuredZones.forEach((zone, index) => {
    drawPolygon(
      context,
      zone.polygon,
      zoneColors[index % zoneColors.length],
      false,
      zone.name
    );
  });
  if (draftZonePoints.length > 0) {
    drawPolygon(
      context,
      draftZonePoints,
      "#ffcf70",
      true,
      "DRAFT"
    );
  }
}

function drawPolygon(context, points, color, draft, label) {
  if (!Array.isArray(points) || points.length === 0) {
    return;
  }
  const width = context.canvas.width;
  const height = context.canvas.height;
  context.save();
  context.beginPath();
  points.forEach((point, index) => {
    const x = Number(point[0]) * width;
    const y = Number(point[1]) * height;
    if (index === 0) {
      context.moveTo(x, y);
    } else {
      context.lineTo(x, y);
    }
  });
  if (points.length >= 3) {
    context.closePath();
    context.globalAlpha = draft ? 0.16 : 0.1;
    context.fillStyle = color;
    context.fill();
  }
  context.globalAlpha = 0.95;
  context.strokeStyle = color;
  context.lineWidth = draft ? 3 : 2;
  context.setLineDash(draft ? [8, 6] : []);
  context.stroke();
  context.setLineDash([]);
  points.forEach((point) => {
    context.beginPath();
    context.arc(
      Number(point[0]) * width,
      Number(point[1]) * height,
      draft ? 5 : 3,
      0,
      Math.PI * 2
    );
    context.fillStyle = color;
    context.fill();
  });
  context.font = "bold 13px sans-serif";
  context.fillStyle = color;
  context.fillText(
    label,
    Number(points[0][0]) * width + 7,
    Math.max(16, Number(points[0][1]) * height + 16)
  );
  context.restore();
}

function updateZoneDraft() {
  nodes.zoneDraftCount.textContent =
    `草稿点数：${draftZonePoints.length}`;
  nodes.zoneUndoPoint.disabled = draftZonePoints.length === 0;
  nodes.zoneClearDraft.disabled = draftZonePoints.length === 0;
  nodes.zoneDraftJson.textContent =
    draftZonePoints.length === 0
      ? "点击“开始绘制”，然后在画面中依次点击多边形顶点。"
      : JSON.stringify(
          {
            coordinate_space: "normalized",
            polygon: draftZonePoints,
            valid_polygon: draftZonePoints.length >= 3,
          },
          null,
          2
        );
  updateZoneControls();
  drawZoneCanvas();
}

function toggleZoneDrawing() {
  setZoneDrawing(!zoneDrawingEnabled);
}

function setZoneDrawing(enabled) {
  zoneDrawingEnabled = enabled;
  nodes.zoneCanvas.classList.toggle(
    "drawing",
    zoneDrawingEnabled
  );
  nodes.zoneDrawToggle.classList.toggle(
    "active",
    zoneDrawingEnabled
  );
  nodes.zoneDrawToggle.textContent = zoneDrawingEnabled
    ? "结束绘制"
    : "开始绘制";
}

function addDraftPoint(event) {
  if (!zoneDrawingEnabled) {
    return;
  }
  const bounds = nodes.zoneCanvas.getBoundingClientRect();
  const x = Math.max(
    0,
    Math.min(1, (event.clientX - bounds.left) / bounds.width)
  );
  const y = Math.max(
    0,
    Math.min(1, (event.clientY - bounds.top) / bounds.height)
  );
  draftZonePoints.push([
    Number(x.toFixed(3)),
    Number(y.toFixed(3)),
  ]);
  updateZoneDraft();
}

function updateZoneControls() {
  const selectedZone = configuredZones.find(
    (zone) => zone.id === nodes.zoneEditTarget.value
  );
  const matchingDefault = factoryDefaultZones.some(
    (zone) => selectedZone && zone.id === selectedZone.id
  );
  const anchorSafe = isDraftAnchorSafe(selectedZone);
  nodes.zoneApplyDraft.disabled =
    draftZonePoints.length < 3
    || !selectedZone
    || !anchorSafe;
  nodes.zoneSnapBottom.disabled =
    draftZonePoints.length < 3
    || !selectedZone
    || selectedZone.anchor !== "bottom_center"
    || maximumPolygonY(draftZonePoints) >= 0.999;
  nodes.zoneRestoreDefault.disabled = !matchingDefault;
  nodes.zoneDiscardChanges.disabled = !zoneConfigDirty;
  nodes.zoneDirtyStatus.textContent = zoneConfigDirty
    ? "存在未保存修改"
    : "没有未保存修改";
  nodes.zoneDirtyStatus.classList.toggle(
    "dirty",
    zoneConfigDirty
  );
  const tokenReady = nodes.zoneAdminToken.value.length >= 16;
  const confirmationReady =
    nodes.zoneSaveConfirmation.value === "SAVE_ZONE_CONFIG";
  nodes.zoneSaveSubmit.disabled =
    !zoneSaveEnabled
    || !zoneConfigDirty
    || zoneVersionConflict
    || !tokenReady
    || !confirmationReady;
  updateAnchorGuidance(selectedZone);
}

function maximumPolygonY(points) {
  if (!Array.isArray(points) || points.length === 0) {
    return 0;
  }
  return Math.max(...points.map((point) => Number(point[1])));
}

function isDraftAnchorSafe(selectedZone) {
  if (
    !selectedZone
    || selectedZone.anchor !== "bottom_center"
    || draftZonePoints.length < 3
  ) {
    return true;
  }
  return maximumPolygonY(draftZonePoints) >= 0.98;
}

function updateAnchorGuidance(selectedZone) {
  nodes.zoneAnchorGuidance.classList.remove("warning", "ready");
  if (!selectedZone) {
    nodes.zoneAnchorGuidance.textContent = "请选择一个区域。";
    return;
  }
  if (selectedZone.anchor !== "bottom_center") {
    nodes.zoneAnchorGuidance.textContent =
      "所选区域使用目标中心点判断，不要求底边到达 y=1.0。";
    return;
  }
  if (draftZonePoints.length < 3) {
    nodes.zoneAnchorGuidance.textContent =
      "所选人员区域使用脚底中心判断；建议让底边到达 y=1.0。";
    return;
  }
  const maximumY = maximumPolygonY(draftZonePoints);
  if (maximumY < 0.98) {
    nodes.zoneAnchorGuidance.classList.add("warning");
    nodes.zoneAnchorGuidance.textContent =
      `脚底锚点警告：草稿最下方只有 y=${maximumY.toFixed(3)}。`
      + " 请继续画到底部，或点击“底边吸附到 y=1.0”。";
    return;
  }
  nodes.zoneAnchorGuidance.classList.add("ready");
  nodes.zoneAnchorGuidance.textContent =
    `脚底锚点检查通过：草稿最下方 y=${maximumY.toFixed(3)}。`;
}

function snapDraftBottom() {
  if (draftZonePoints.length < 3) {
    return;
  }
  const maximumY = maximumPolygonY(draftZonePoints);
  const threshold = Math.max(0, maximumY - 0.08);
  draftZonePoints = draftZonePoints.map((point) => [
    Number(point[0]),
    Number(point[1]) >= threshold ? 1.0 : Number(point[1]),
  ]);
  setZoneSaveResult(
    "草稿底边已吸附到 y=1.0；请检查形状后再应用。",
    ""
  );
  updateZoneDraft();
}

function restoreSelectedZoneDefault() {
  const selectedId = nodes.zoneEditTarget.value;
  const defaultZone = factoryDefaultZones.find(
    (zone) => zone.id === selectedId
  );
  const currentIndex = configuredZones.findIndex(
    (zone) => zone.id === selectedId
  );
  if (!defaultZone || currentIndex < 0) {
    setZoneSaveResult("所选区域没有可用的默认值。", "error");
    return;
  }
  configuredZones[currentIndex] = JSON.parse(
    JSON.stringify(defaultZone)
  );
  zoneConfigDirty = true;
  draftZonePoints = [];
  setZoneDrawing(false);
  setZoneSaveResult(
    `${defaultZone.name} 已恢复为默认值，尚未写入 Jetson。`,
    ""
  );
  renderZoneTargetOptions();
  updateZoneDraft();
}

function applyDraftToSelectedZone() {
  if (draftZonePoints.length < 3) {
    setZoneSaveResult("多边形至少需要3个点。", "error");
    return;
  }
  const selectedId = nodes.zoneEditTarget.value;
  const zone = configuredZones.find(
    (candidate) => candidate.id === selectedId
  );
  if (!zone) {
    setZoneSaveResult("请选择一个现有区域。", "error");
    return;
  }
  zone.polygon = draftZonePoints.map((point) => [
    Number(point[0]),
    Number(point[1]),
  ]);
  zoneConfigDirty = true;
  draftZonePoints = [];
  setZoneDrawing(false);
  setZoneSaveResult(
    `草稿已应用到 ${zone.name}，尚未写入 Jetson。`,
    ""
  );
  renderZoneTargetOptions();
  updateZoneDraft();
}

async function discardZoneChanges() {
  zoneConfigDirty = false;
  zoneConfigVersion = null;
  zoneVersionConflict = false;
  draftZonePoints = [];
  setZoneDrawing(false);
  try {
    renderZones(await getJson(endpoints.zones));
    setZoneSaveResult("已放弃本地修改并重新读取配置。", "");
  } catch (error) {
    setZoneSaveResult("重新读取区域配置失败。", "error");
  }
  updateZoneDraft();
}

async function saveZoneConfiguration(event) {
  event.preventDefault();
  updateZoneControls();
  if (nodes.zoneSaveSubmit.disabled) {
    return;
  }
  const token = nodes.zoneAdminToken.value;
  nodes.zoneSaveSubmit.disabled = true;
  setZoneSaveResult("正在验证、备份并保存区域配置…", "");
  try {
    const response = await fetch(endpoints.zones, {
      method: "PUT",
      headers: authenticatedHeaders({
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "X-EdgeSentinel-Config-Token": token,
      }),
      body: JSON.stringify({
        expected_version: zoneConfigVersion,
        confirmation: nodes.zoneSaveConfirmation.value,
        coordinate_space: "normalized",
        zones: configuredZones,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail || `HTTP ${response.status}`;
      if (response.status === 409) {
        zoneVersionConflict = true;
      }
      throw new Error(String(detail));
    }
    zoneConfigDirty = false;
    zoneConfigVersion = null;
    zoneVersionConflict = false;
    nodes.zoneSaveConfirmation.value = "";
    renderZones(payload);
    setZoneSaveResult(
      `保存成功，旧配置已备份到 ${payload.backup_path}。`
      + " 视觉任务将在约30帧内自动加载，无需重启。",
      "success"
    );
  } catch (error) {
    setZoneSaveResult(
      `保存失败：${error.message || "未知错误"}`,
      "error"
    );
  } finally {
    nodes.zoneAdminToken.value = "";
    updateZoneControls();
  }
}

function setZoneSaveResult(message, status) {
  nodes.zoneSaveResult.textContent = message;
  nodes.zoneSaveResult.classList.toggle(
    "success",
    status === "success"
  );
  nodes.zoneSaveResult.classList.toggle(
    "error",
    status === "error"
  );
}

function renderSystem(payload) {
  const load = payload.load_average;
  const memory = payload.memory;
  const disk = payload.disk;
  const temperature = payload.temperature || {};

  nodes.systemLoad.textContent = load
    ? `${load.one_minute.toFixed(2)} / ${load.cpu_count}核`
    : "不可用";
  nodes.systemMemory.textContent = memory
    ? `${memory.used_percent.toFixed(1)}% · ${formatBytes(memory.available_bytes)} 可用`
    : "不可用";
  nodes.systemTemperature.textContent =
    temperature.max_celsius !== null &&
    temperature.max_celsius !== undefined
      ? `${temperature.max_celsius.toFixed(1)} °C`
      : "传感器不可用";
  nodes.systemDisk.textContent = disk
    ? `${disk.used_percent.toFixed(1)}% · ${formatBytes(disk.available_bytes)} 可用`
    : "不可用";
  nodes.systemUptime.textContent =
    payload.uptime_seconds !== null
      ? formatDuration(payload.uptime_seconds)
      : "不可用";
}

function formatBytes(value) {
  const bytes = Number(value);
  if (!Number.isFinite(bytes) || bytes < 0) {
    return "—";
  }
  const units = ["B", "KB", "MB", "GB", "TB"];
  let amount = bytes;
  let unit = 0;
  while (amount >= 1024 && unit < units.length - 1) {
    amount /= 1024;
    unit += 1;
  }
  const digits = unit >= 3 ? 1 : 0;
  return `${amount.toFixed(digits)} ${units[unit]}`;
}

function formatDuration(seconds) {
  const totalMinutes = Math.floor(Number(seconds) / 60);
  const days = Math.floor(totalMinutes / 1440);
  const hours = Math.floor((totalMinutes % 1440) / 60);
  const minutes = totalMinutes % 60;
  return days > 0
    ? `${days}天 ${hours}小时`
    : `${hours}小时 ${minutes}分钟`;
}

function renderEvents(payload, append = false) {
  if (!append) {
    nodes.eventList.replaceChildren();
    loadedEventCount = 0;
    eventPagesExpanded = false;
  } else {
    eventPagesExpanded = true;
  }
  eventNextCursor = payload.pagination?.next_cursor || null;
  nodes.eventLoadMore.classList.toggle(
    "hidden",
    !payload.pagination?.has_more
  );
  nodes.eventLoadMore.disabled = false;
  nodes.eventLoadMore.textContent = "加载更早事件";
  nodes.eventCollapse.disabled = false;
  nodes.eventCollapse.textContent = "收起并回到最新事件";
  nodes.eventCollapse.classList.toggle(
    "hidden",
    !eventPagesExpanded
  );
  loadedEventCount += payload.events.length;
  nodes.eventResultCount.textContent =
    `${loadedEventCount} 条已加载 · 可确认处理`;
  if (loadedEventCount === 0) {
    appendEmpty(nodes.eventList, "数据库中还没有事件");
    return;
  }
  payload.events.forEach((event) => {
    const item = document.createElement("article");
    item.className = "event-item";

    const titleWrap = document.createElement("div");
    const title = document.createElement("div");
    title.className = "event-name";
    title.textContent = eventLabels[event.event_type] || event.event_type;
    const meta = document.createElement("div");
    meta.className = "event-meta";
    meta.textContent =
      `${event.object_class || "person"} · ${event.zone_name || event.zone_id}`;
    const disposition = document.createElement("span");
    disposition.className =
      `event-disposition-badge ${String(event.status || "OPEN").toLowerCase()}`;
    disposition.textContent =
      event.status === "ACKNOWLEDGED" ? "已处理" : "待处理";
    titleWrap.append(title, meta, disposition);

    const severity = document.createElement("span");
    severity.className =
      `severity ${String(event.severity).toLowerCase()}`;
    severity.textContent = event.severity;

    const time = document.createElement("time");
    time.className = "event-time";
    time.dateTime = event.timestamp;
    time.textContent = formatBeijingTime(event.timestamp);

    const action = document.createElement("div");
    action.className = "event-actions";
    const primary =
      event.evidence_urls && event.evidence_urls.primary;
    if (primary) {
      const link = document.createElement("a");
      link.className = "evidence-link";
      link.href = primary;
      link.target = "_blank";
      link.rel = "noreferrer";
      link.textContent = "查看证据";
      action.append(link);
    } else {
      const noEvidence = document.createElement("span");
      noEvidence.className = "event-meta";
      noEvidence.textContent = "无截图";
      action.append(noEvidence);
    }

    const detailButton = document.createElement("button");
    detailButton.className = "event-detail-button";
    detailButton.type = "button";
    detailButton.textContent = "详情";
    detailButton.addEventListener("click", () => {
      lastEventDetailTrigger = detailButton;
      openEventDetail(event.event_id);
    });
    action.append(detailButton);

    item.append(titleWrap, severity, time, action);
    nodes.eventList.append(item);
  });
}

function renderEventSummary(payload) {
  const groups = payload.counts?.by_event_type || [];
  const groupText = groups
    .slice(0, 4)
    .map((item) => `${eventLabels[item.name] || item.name} ${item.count}`)
    .join(" · ");
  const status = payload.filters?.status;
  const statusText =
    status === "OPEN"
      ? "待处理"
      : status === "ACKNOWLEDGED"
        ? "已处理"
        : "全部状态";
  const severity = payload.filters?.severity;
  const severityText = severity || "全部级别";
  const comparison = payload.comparison;
  const largestChange = comparison?.largest_event_type_change;
  const changeAssessment = comparison?.assessment;
  const changeAssessmentText = changeAssessment
    ? changeAssessment.threshold_exceeded
      ? ` · 变化超阈值(${changeAssessment.status})`
      : ` · 变化未超阈值(${changeAssessment.status})`
    : "";
  const significantTypeCount = Number(
    comparison?.significant_event_type_count || 0
  );
  const significantContributorText = comparison
    ? ` · 显著类型变化${significantTypeCount}项`
    : "";
  const eventTypeStructure =
    comparison?.structural_change?.by_event_type;
  const structuralChangeText = eventTypeStructure
    ? ` · 类型抵消${eventTypeStructure.offsetting_events}条` +
      `(${eventTypeStructure.status})`
    : "";
  const comparisonOffset =
    comparison?.previous_window?.offset_minutes;
  const comparisonAlignmentText = comparisonOffset
    ? ` · 基线偏移${comparisonOffset}分钟`
    : "";
  const referenceBaselines = payload.reference_baselines;
  const referenceBaselineText = referenceBaselines
    ? ` · 历史双基线均值${
        referenceBaselines.baseline_average_total
      }条 · 当前较均值${
        referenceBaselines.change_from_average >= 0
          ? "增加"
          : "减少"
      }${Math.abs(referenceBaselines.change_from_average)}条`
      + ` · 基线评估${
        referenceBaselines.assessment?.status || "UNKNOWN"
      } · 一致性${
        referenceBaselines.consistency?.status || "UNKNOWN"
      }`
    : "";
  const contributorText = largestChange
    ? ` · 主要变化${
        eventLabels[largestChange.name] || largestChange.name
      }${
        largestChange.absolute_change > 0
          ? "增加"
          : largestChange.absolute_change < 0
            ? "减少"
            : "持平"
      }${Math.abs(largestChange.absolute_change)}条`
    : "";
  const comparisonText = comparison
    ? comparison.direction === "INCREASE"
      ? ` · 较前期增加${comparison.absolute_change}条`
      : comparison.direction === "DECREASE"
        ? ` · 较前期减少${Math.abs(comparison.absolute_change)}条`
        : " · 与前期持平"
    : "";
  nodes.eventSummary.textContent =
    `最近${payload.window.minutes}分钟 · ${statusText} · ` +
    `${severityText} · ` +
    `共${payload.total_events}条` +
    (groupText ? ` · ${groupText}` : "") +
    comparisonText +
    contributorText +
    changeAssessmentText +
    significantContributorText +
    structuralChangeText +
    comparisonAlignmentText +
    referenceBaselineText;
  nodes.eventTrend.replaceChildren();
  const buckets = (payload.timeline?.buckets || []).slice(-12);
  if (buckets.length === 0) {
    return;
  }
  const maximum = Math.max(
    1,
    ...buckets.map((bucket) => bucket.count)
  );
  buckets.forEach((bucket) => {
    const item = document.createElement("div");
    item.className = "event-trend-item";
    item.title = `${formatBeijingTime(bucket.start)} · ${bucket.count}条`;
    const bar = document.createElement("span");
    bar.className = "event-trend-bar";
    bar.style.height =
      `${Math.max(4, (bucket.count / maximum) * 100)}%`;
    const label = document.createElement("time");
    label.textContent = new Date(bucket.start).toLocaleTimeString(
      "zh-CN",
      {
        timeZone: "Asia/Shanghai",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }
    );
    item.append(bar, label);
    nodes.eventTrend.append(item);
  });
}

function buildEventUrl(cursor = null) {
  const parameters = new URLSearchParams();
  parameters.set("limit", nodes.eventLimitFilter.value || "6");
  const eventType = nodes.eventTypeFilter.value.trim();
  const status = nodes.eventStatusFilter.value.trim();
  const severity = nodes.eventSeverityFilter.value.trim();
  const objectClass = nodes.eventObjectFilter.value.trim();
  const cameraId = nodes.eventCameraFilter.value.trim();
  const minutes = nodes.eventMinutesFilter.value.trim();
  if (eventType) {
    parameters.set("type", eventType);
  }
  if (status) {
    parameters.set("status", status);
  }
  if (severity) {
    parameters.set("severity", severity);
  }
  if (objectClass) {
    parameters.set("object_class", objectClass);
  }
  if (cameraId) {
    parameters.set("camera_id", cameraId);
  }
  if (minutes) {
    parameters.set("minutes", minutes);
  }
  if (cursor) {
    parameters.set("cursor", cursor);
  }
  return `${endpoints.events}?${parameters.toString()}`;
}

function buildEventSummaryUrl() {
  const parameters = new URLSearchParams();
  parameters.set(
    "minutes",
    nodes.eventMinutesFilter.value || "1440"
  );
  parameters.set("recent_limit", "5");
  parameters.set("bucket_minutes", "60");
  parameters.set("compare_previous", "true");
  const eventType = nodes.eventTypeFilter.value.trim();
  const status = nodes.eventStatusFilter.value.trim();
  const severity = nodes.eventSeverityFilter.value.trim();
  const objectClass = nodes.eventObjectFilter.value.trim();
  const cameraId = nodes.eventCameraFilter.value.trim();
  if (eventType) {
    parameters.set("type", eventType);
  }
  if (status) {
    parameters.set("status", status);
  }
  if (severity) {
    parameters.set("severity", severity);
  }
  if (objectClass) {
    parameters.set("object_class", objectClass);
  }
  if (cameraId) {
    parameters.set("camera_id", cameraId);
  }
  return `${endpoints.eventSummary}?${parameters.toString()}`;
}

async function openEventDetail(eventId) {
  currentEventDetail = null;
  nodes.eventDetailBackdrop.classList.remove("hidden");
  document.body.classList.add("modal-open");
  nodes.eventDetailTitle.textContent = "正在读取事件…";
  nodes.eventDetailFields.replaceChildren();
  nodes.eventEvidenceGrid.replaceChildren();
  nodes.eventDetailJson.textContent = "";
  nodes.eventDispositionStatus.textContent = "等待读取";
  nodes.eventEvidenceIntegrity.textContent = "等待校验";
  nodes.eventAcknowledge.disabled = true;
  nodes.eventDetailClose.focus();
  try {
    const event = await getJson(
      `${endpoints.events}/${encodeURIComponent(eventId)}`
    );
    renderEventDetail(event);
    try {
      const integrity = await getJson(
        `${endpoints.events}/${encodeURIComponent(eventId)}` +
        "/evidence-integrity"
      );
      renderEventEvidenceIntegrity(integrity);
    } catch (integrityError) {
      nodes.eventEvidenceIntegrity.textContent = "校验不可用";
    }
  } catch (error) {
    nodes.eventDetailTitle.textContent = "事件详情读取失败";
    nodes.eventDetailJson.textContent = String(
      error.message || "未知错误"
    );
  }
}

function renderEventEvidenceIntegrity(integrity) {
  const evidence = integrity.evidence || [];
  const details = evidence
    .map((item) => `${item.kind}=${item.status}`)
    .join(" · ");
  nodes.eventEvidenceIntegrity.textContent =
    `${integrity.status} · ` +
    `${Number(integrity.valid_evidence_count || 0)}/` +
    `${Number(integrity.referenced_evidence_count || 0)}有效` +
    (details ? ` · ${details}` : " · 无证据引用");
}

function renderEventDetail(event) {
  currentEventDetail = event;
  nodes.eventDetailTitle.textContent =
    eventLabels[event.event_type] || event.event_type;
  const fields = [
    ["事件ID", event.event_id],
    ["北京时间", event.timestamp],
    ["严重级别", event.severity],
    ["摄像头", event.camera_id],
    ["区域", event.zone_name || event.zone_id],
    ["目标类别", event.object_class || "person"],
    ["匿名 Track ID", event.track_id ?? "无"],
    [
      "处置状态",
      event.status === "ACKNOWLEDGED" ? "已处理" : "待处理",
    ],
    ["处理时间", event.acknowledged_at || "尚未处理"],
  ];
  nodes.eventDetailFields.replaceChildren();
  fields.forEach(([name, value]) => {
    const wrapper = document.createElement("div");
    const term = document.createElement("dt");
    const detail = document.createElement("dd");
    term.textContent = name;
    detail.textContent = String(value);
    wrapper.append(term, detail);
    nodes.eventDetailFields.append(wrapper);
  });

  nodes.eventEvidenceGrid.replaceChildren();
  const evidenceUrls = event.evidence_urls || {};
  ["primary", "before", "after"].forEach((kind) => {
    if (evidenceUrls[kind]) {
      appendEvidence(kind, evidenceUrls[kind]);
    }
  });
  if (nodes.eventEvidenceGrid.children.length === 0) {
    appendEmpty(nodes.eventEvidenceGrid, "该事件没有可用证据图片");
  }
  nodes.eventDetailJson.textContent = JSON.stringify(
    event.details || {},
    null,
    2
  );
  const acknowledged = event.status === "ACKNOWLEDGED";
  nodes.eventDispositionStatus.textContent = acknowledged
    ? `已处理 · ${event.acknowledged_at || "时间未知"}`
    : "待处理 · 尚未修改事件记录";
  nodes.eventAcknowledge.disabled = acknowledged;
  nodes.eventAcknowledge.textContent = acknowledged
    ? "该事件已经处理"
    : "通过 Agent 确认已处理";
}

function appendEvidence(kind, url) {
  const labels = {
    primary: "主要证据",
    before: "变化前",
    after: "变化后",
  };
  const link = document.createElement("a");
  link.className = "event-evidence";
  link.href = url;
  link.target = "_blank";
  link.rel = "noreferrer";
  const image = document.createElement("img");
  image.src = url;
  image.alt = `${labels[kind]}图片`;
  image.loading = "lazy";
  const label = document.createElement("span");
  label.textContent = labels[kind];
  link.append(image, label);
  nodes.eventEvidenceGrid.append(link);
}

function closeEventDetail() {
  nodes.eventDetailBackdrop.classList.add("hidden");
  document.body.classList.remove("modal-open");
  if (lastEventDetailTrigger) {
    lastEventDetailTrigger.focus();
  }
}

async function requestEventAcknowledgement() {
  if (
    !currentEventDetail ||
    currentEventDetail.status === "ACKNOWLEDGED"
  ) {
    return;
  }
  const eventId = currentEventDetail.event_id;
  closeEventDetail();
  nodes.agentMessage.value = `确认处理事件 ${eventId}`;
  updateMessageCount();
  document.querySelector(".agent-panel").scrollIntoView({
    behavior: "smooth",
    block: "start",
  });
  await runAgentTask(nodes.agentMessage.value);
}

function appendEmpty(parent, message) {
  const empty = document.createElement("p");
  empty.className = "empty";
  empty.textContent = message;
  parent.append(empty);
}

function formatBeijingTime(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "Asia/Shanghai",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(date);
}

function formatTimestamp(value) {
  if (typeof value !== "string" || !value.trim()) {
    return "时间未知";
  }
  return formatBeijingTime(value);
}

function showNotice(messages) {
  const visible = messages.length > 0;
  nodes.notice.classList.toggle("hidden", !visible);
  nodes.notice.textContent = messages.join("；");
}

async function refreshDashboard() {
  nodes.button.disabled = true;
  const results = await Promise.allSettled([
    getJson(endpoints.health),
    getJson(endpoints.people),
    getJson(endpoints.objects),
    getJson(buildEventUrl()),
    getJson(endpoints.system),
    getJson(endpoints.camera),
    getJson(endpoints.zones),
    getJson(endpoints.zoneDefaults),
    visionModelLoaded
      ? Promise.resolve(null)
      : getJson(endpoints.model),
    getJson(endpoints.performance),
    getJson(endpoints.benchmark),
    getJson(buildEventSummaryUrl()),
    getJson(endpoints.storage),
    getJson(endpoints.retentionPreview),
    getJson(endpoints.retentionCleanupHistory),
    getJson(endpoints.evidenceIntegrity),
  ]);
  const errors = [];

  if (results[0].status === "fulfilled") {
    renderHealth(results[0].value);
    setConnection(true);
  } else {
    setConnection(false);
    errors.push("API 健康信息读取失败");
  }

  if (results[1].status === "fulfilled") {
    renderPeople(results[1].value);
    if (results[1].value.stale) {
      errors.push("视觉任务当前未运行，页面显示最后一次保存状态");
    }
  } else {
    errors.push("没有可用的人员状态");
  }

  if (results[2].status === "fulfilled") {
    renderObjects(results[2].value);
  } else {
    nodes.objectList.replaceChildren();
    appendEmpty(nodes.objectList, "没有可用的物品状态");
    errors.push("没有可用的物品状态");
  }

  if (results[3].status === "fulfilled") {
    if (!eventPagesExpanded) {
      renderEvents(results[3].value);
    }
  } else {
    nodes.eventList.replaceChildren();
    nodes.eventLoadMore.classList.add("hidden");
    appendEmpty(nodes.eventList, "事件数据库读取失败");
    errors.push("事件记录读取失败");
  }

  if (results[4].status === "fulfilled") {
    renderSystem(results[4].value);
    if (results[4].value.status !== "ok") {
      errors.push("部分设备运行指标不可用");
    }
  } else {
    errors.push("设备运行状态读取失败");
  }

  if (results[5].status === "fulfilled") {
    renderCameraStatus(results[5].value);
    if (
      results[5].value.status !== "RUNNING" ||
      results[5].value.state_stale
    ) {
      errors.push("摄像头推理正在自动恢复");
    }
  } else {
    nodes.cameraRuntimeStatus.textContent = "状态不可用";
    errors.push("摄像头监督状态读取失败");
  }

  if (results[6].status === "fulfilled") {
    renderZones(results[6].value);
  } else {
    nodes.zoneStatus.textContent = "区域配置读取失败";
    errors.push("区域配置读取失败");
  }

  if (results[7].status === "fulfilled") {
    renderDefaultZones(results[7].value);
  } else {
    factoryDefaultZones = [];
    updateZoneControls();
    errors.push("默认区域配置读取失败");
  }

  if (
    results[8].status === "fulfilled" &&
    results[8].value !== null
  ) {
    renderVisionModel(results[8].value);
    visionModelLoaded = true;
    if (results[8].value.verification.status !== "MATCH") {
      errors.push("视觉模型Engine完整性校验未通过");
    }
  } else if (results[8].status === "rejected") {
    nodes.visionModelRuntime.textContent = "模型清单不可用";
    errors.push("视觉模型清单读取失败");
  }

  if (results[9].status === "fulfilled") {
    renderVisionPerformance(results[9].value);
    if (results[9].value.stale) {
      errors.push("视觉性能数据已陈旧");
    }
  } else {
    nodes.visionPerformanceRuntime.textContent = "性能数据不可用";
    errors.push("视觉性能数据读取失败");
  }

  if (results[10].status === "fulfilled") {
    renderRuntimeBenchmark(results[10].value);
    if (results[10].value.status !== "PASS") {
      errors.push("最近连续运行基准未通过");
    }
  } else {
    nodes.runtimeBenchmarkStatus.textContent = "尚无基准报告";
  }

  if (results[11].status === "fulfilled") {
    renderEventSummary(results[11].value);
  } else {
    nodes.eventSummary.textContent = "最近事件汇总不可用";
    errors.push("最近事件汇总读取失败");
  }

  if (results[12].status === "fulfilled") {
    renderStorageUsage(results[12].value);
    if (results[12].value.status !== "COMPLETE") {
      errors.push("项目数据占用清单不完整");
    }
  } else {
    nodes.storageUsage.textContent = "数据占用不可用";
    errors.push("项目数据占用读取失败");
  }

  if (results[13].status === "fulfilled") {
    renderRetentionPreview(results[13].value);
    if (results[13].value.status !== "COMPLETE") {
      errors.push("旧数据清理预览不完整");
    }
  } else {
    nodes.retentionPreviewStatus.textContent = "清理预览不可用";
    errors.push("旧数据清理预览读取失败");
  }

  if (results[14].status === "fulfilled") {
    renderRetentionCleanupHistory(results[14].value);
    if (results[14].value.status !== "COMPLETE") {
      errors.push("旧日志清理审计读取不完整");
    }
  } else {
    nodes.retentionCleanupHistoryStatus.textContent =
      "清理审计不可用";
    errors.push("旧日志清理审计读取失败");
  }

  if (results[15].status === "fulfilled") {
    renderEvidenceIntegrity(results[15].value);
    if (results[15].value.status !== "PASS") {
      errors.push("部分近期事件证据不可用");
    }
  } else {
    nodes.evidenceIntegrityStatus.textContent =
      "证据完整性不可用";
    errors.push("近期事件证据完整性读取失败");
  }

  showNotice(errors);
  nodes.lastRefresh.textContent = new Date().toLocaleTimeString(
    "zh-CN",
    { hour12: false }
  );
  nodes.button.disabled = false;
}

async function submitAgentTask(event) {
  event.preventDefault();
  const message = nodes.agentMessage.value.trim();
  if (!message) {
    nodes.agentMessage.focus();
    return;
  }

  await runAgentTask(message);
}

async function runAgentTask(message) {
  setAgentLoading(true);
  try {
    const sessionId = await ensureAgentSession();
    const response = await fetch(endpoints.agentJobs, {
      method: "POST",
      headers: authenticatedHeaders({
        Accept: "application/json",
        "Content-Type": "application/json; charset=utf-8",
        "Idempotency-Key": createAgentIdempotencyKey(),
      }),
      body: JSON.stringify({
        message,
        session_id: sessionId,
      }),
    });
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail || `HTTP ${response.status}`;
      throw new Error(String(detail));
    }
    activeAgentJobId = payload.job_id;
    renderAgentJobProgress(payload);
    await waitForAgentJob(payload);
  } catch (error) {
    renderAgentError(error);
  } finally {
    activeAgentJobId = null;
    if (activeAgentEventSource) {
      activeAgentEventSource.close();
      activeAgentEventSource = null;
    }
    setAgentLoading(false);
  }
}

function createAgentIdempotencyKey() {
  return `dashboard-${Date.now()}-${Math.random()
    .toString(16)
    .slice(2, 14)}`;
}

function renderAgentJobProgress(job) {
  const execution = job.execution || {};
  const limits = execution.limits || {};
  const usage = execution.usage || {};
  nodes.agentResponse.classList.remove("hidden", "error");
  nodes.agentTaskStatus.textContent = `JOB ${job.status}`;
  nodes.agentTaskMeta.textContent =
    `${job.job_id.slice(0, 13)}… · sequence ${job.sequence} · ` +
    `${Number(usage.model_calls || 0)}/${Number(limits.max_model_calls || 5)} model · ` +
    `${Number(usage.tool_calls || 0)}/${Number(limits.max_tool_calls || 8)} tool · ` +
    `${Number(usage.total_tokens || 0)}/${Number(limits.max_total_tokens || 0)} token`;
  nodes.agentAnswer.textContent =
    job.cancel_pending
      ? "已提交协作取消请求；当前调用返回后，Agent 会在下一安全点停止。"
      : job.status === "QUEUED"
      ? "任务已进入有界队列，等待单个安全 Worker 执行。"
      : job.status === "RUNNING"
        ? `Agent 正在运行；总时限 ${Number(limits.max_wall_seconds || 60)} 秒，状态通过 SSE 实时推送。`
        : `Job 已结束：${job.status}`;
  nodes.agentToolResults.replaceChildren();
  appendToolResult(
    `queue · ${job.status}`,
    job.status === "FAILED" ? "failed" : "pending"
  );
  const canCancel = Boolean(job.safe_cancel);
  nodes.agentJobCancel.classList.toggle("hidden", !canCancel);
  nodes.agentJobCancel.disabled = !canCancel;
  nodes.agentJobCancel.textContent =
    job.status === "RUNNING" ? "请求安全停止" : "取消排队";
  nodes.agentWorkbench.classList.add("hidden");
}

async function completeAgentJob(job) {
  renderAgentJobProgress(job);
  if (job.status === "COMPLETED" && job.task_id) {
    const task = await getJson(
      `${endpoints.agent}/${encodeURIComponent(job.task_id)}`
    );
    renderAgentTask(task);
    return;
  }
  if (job.status === "CANCELLED" && job.task_id) {
    const task = await getJson(
      `${endpoints.agent}/${encodeURIComponent(job.task_id)}`
    );
    renderAgentTask(task);
    return;
  }
  if (job.status === "CANCELLED") {
    nodes.agentTaskStatus.textContent = "JOB CANCELLED";
    nodes.agentAnswer.textContent =
      "排队任务已安全取消，Agent Loop 和任何工具都没有执行。";
    return;
  }
  if (job.status === "FAILED" && job.task_id) {
    const task = await getJson(
      `${endpoints.agent}/${encodeURIComponent(job.task_id)}`
    );
    renderAgentTask(task);
    return;
  }
  throw new Error(
    `Agent Job ${job.status}: ${job.error_code || "unknown"}`
  );
}

function waitForAgentJob(initialJob) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const finish = async (job) => {
      if (settled) {
        return;
      }
      if (!["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"]
        .includes(job.status)) {
        renderAgentJobProgress(job);
        return;
      }
      settled = true;
      if (activeAgentEventSource) {
        activeAgentEventSource.close();
        activeAgentEventSource = null;
      }
      try {
        await completeAgentJob(job);
        resolve();
      } catch (error) {
        reject(error);
      }
    };

    if (typeof window.EventSource !== "function") {
      pollAgentJob(initialJob.job_id, finish, reject);
      return;
    }
    const source = new EventSource(
      `${endpoints.agentJobs}/${encodeURIComponent(initialJob.job_id)}/events?after=-1`
    );
    activeAgentEventSource = source;
    source.addEventListener("status", (event) => {
      try {
        finish(JSON.parse(event.data));
      } catch (error) {
        settled = true;
        source.close();
        reject(error);
      }
    });
    source.onerror = () => {
      if (settled) {
        return;
      }
      source.close();
      activeAgentEventSource = null;
      pollAgentJob(initialJob.job_id, finish, reject);
    };
  });
}

async function pollAgentJob(jobId, finish, reject) {
  try {
    while (activeAgentJobId === jobId) {
      const job = await getJson(
        `${endpoints.agentJobs}/${encodeURIComponent(jobId)}`
      );
      await finish(job);
      if (["COMPLETED", "FAILED", "CANCELLED", "INTERRUPTED"]
        .includes(job.status)) {
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 750));
    }
  } catch (error) {
    reject(error);
  }
}

async function cancelQueuedAgentJob() {
  if (!activeAgentJobId) {
    return;
  }
  nodes.agentJobCancel.disabled = true;
  try {
    const response = await fetch(
      `${endpoints.agentJobs}/${encodeURIComponent(activeAgentJobId)}/cancel`,
      {
        method: "POST",
        headers: authenticatedHeaders({
          Accept: "application/json",
          "Content-Type": "application/json; charset=utf-8",
        }),
        body: JSON.stringify({ cancel: true }),
      }
    );
    const payload = await response.json();
    if (!response.ok) {
      throw new Error(payload.detail || `HTTP ${response.status}`);
    }
    renderAgentJobProgress(payload);
  } catch (error) {
    nodes.agentTaskMeta.textContent =
      `无法取消：${error.message || "任务已开始"}`;
  }
}

function setAgentLoading(loading) {
  nodes.agentSubmit.disabled = loading;
  nodes.agentMessage.disabled = loading;
  nodes.agentSubmit.textContent = loading ? "正在分析…" : "发送问题";
  if (!loading) {
    nodes.agentJobCancel.classList.add("hidden");
    nodes.agentJobCancel.disabled = true;
  }
  renderAgentModelSwitch(currentAgentModel);
  if (loading) {
    activeAgentTaskId = null;
    activeAgentToolName = null;
    nodes.agentConfirmation.classList.add("hidden");
    hideAgentSnapshot();
    hideAgentReport();
    nodes.agentResponse.classList.remove("hidden", "error");
    nodes.agentTaskStatus.textContent = "AGENT RUNNING";
    nodes.agentTaskMeta.textContent = "工具调用将经过安全策略";
    nodes.agentAnswer.textContent = "正在等待回答…";
    nodes.agentToolResults.replaceChildren();
    nodes.agentWorkbench.classList.add("hidden");
    nodes.agentRunTimeline.replaceChildren();
  }
}

function getAgentStepCount(task) {
  const value = task.steps ?? task.step;
  const count = Number(value);
  return Number.isFinite(count) && count >= 0
    ? Math.floor(count)
    : 0;
}

function formatAgentStepCount(task) {
  const count = getAgentStepCount(task);
  return `${count} ${count === 1 ? "step" : "steps"}`;
}

function renderAgentTask(task) {
  if (task.session_id && task.memory) {
    renderAgentMemory(task.memory, task.session_id);
  }
  nodes.agentResponse.classList.remove("hidden", "error");
  nodes.agentTaskStatus.textContent = `TASK ${task.status}`;
  nodes.agentTaskMeta.textContent =
    `${task.model || "unknown"} · ${formatAgentStepCount(task)}`;
  nodes.agentAnswer.textContent = task.answer || "Agent 没有返回文字回答。";
  if (!task.answer && task.error) {
    nodes.agentAnswer.textContent =
      `任务停止：${task.error.code || "UNKNOWN"}` +
      (task.error.stage ? ` · ${task.error.stage}` : "");
  }
  nodes.agentToolResults.replaceChildren();
  renderAgentConfirmation(task);
  renderAgentSnapshot(task);
  renderAgentReport(task);
  renderAgentWorkbench(task);
  const toolResults = Array.isArray(task.tool_results)
    ? task.tool_results
    : [];
  if (toolResults.length === 0) {
    appendToolResult(
      task.status === "AWAITING_CONFIRMATION"
        ? "工具尚未执行 · 等待确认"
        : "未调用工具",
      task.status === "AWAITING_CONFIRMATION"
        ? "pending"
        : "succeeded"
    );
    return;
  }
  toolResults.forEach((result) => {
    appendToolResult(
      `${result.tool_name} · ${result.status}`,
      String(result.status).toLowerCase()
    );
  });
}

function formatAgentDuration(startedAt, completedAt) {
  if (!startedAt || !completedAt) {
    return "运行中";
  }
  const durationMs =
    new Date(completedAt).getTime() - new Date(startedAt).getTime();
  if (!Number.isFinite(durationMs) || durationMs < 0) {
    return "不可用";
  }
  return durationMs < 1000
    ? `${durationMs} ms`
    : `${(durationMs / 1000).toFixed(3)} s`;
}

function traceRecordLabel(record) {
  const labels = {
    SKILL_SELECTED: "Skill 选择",
    SKILL_POLICY_DENIED: "Skill 策略拒绝",
    HOOK_RESULT: "Hook 执行",
    MODEL_DECISION: "模型决策",
    MODEL_USAGE: "模型用量",
    MODEL_RESILIENCE: "模型韧性",
    TOOL_ROUTE: "工具路由",
    TOOL_ROUTE_DENIED: "路由拒绝",
    TOOL_RESULT: "工具结果",
    CONFIRMATION_REQUIRED: "等待确认",
    CONFIRMATION_GRANTED: "确认通过",
    CONFIRMATION_CANCELLED: "操作取消",
    TASK_RESUMED: "任务恢复",
    TASK_PAUSED: "任务暂停",
    TASK_RESULT: "任务结束",
    SESSION_MEMORY: "会话记忆",
    EXECUTION_STOPPED: "执行停止",
  };
  return labels[record.record_type] || record.record_type || "运行记录";
}

function traceRecordDescription(record) {
  if (record.record_type === "SKILL_SELECTED") {
    return `${record.skill_name || "unknown"}@${
      record.skill_version || "unknown"
    } · ${String(record.skill_sha256 || "").slice(0, 12)}…`;
  }
  if (record.record_type === "SKILL_POLICY_DENIED") {
    return `${record.tool_name || "unknown"} · ${
      record.error_code || "SKILL_TOOL_NOT_ALLOWED"
    }`;
  }
  if (record.record_type === "HOOK_RESULT") {
    const timeout = Number.isFinite(record.timeout_ms)
      ? ` · timeout ${record.timeout_ms} ms`
      : "";
    return `${record.hook_point || "unknown"} · ${
      record.hook_name || "unknown"
    } · ${record.decision || record.status || "UNKNOWN"} · ${
      record.failure_policy || "UNKNOWN"
    }${timeout}`;
  }
  if (record.record_type === "MODEL_DECISION") {
    const calls = Array.isArray(record.tool_calls)
      ? record.tool_calls
      : [];
    return calls.length > 0
      ? `模型请求 ${calls.length} 个工具`
      : "模型生成最终回答";
  }
  if (record.record_type === "MODEL_USAGE") {
    const reported = record.usage_reported === true;
    const cost = record.cost_estimate_available
      ? ` · $${Number(record.estimated_cost_usd || 0).toFixed(6)} est.`
      : " · cost n/a";
    return reported
      ? `${Number(record.total_tokens || 0)} token · cumulative ${Number(record.cumulative_total_tokens || 0)}${cost}`
      : `provider usage unavailable${cost}`;
  }
  if (record.record_type === "MODEL_RESILIENCE") {
    const fallback = record.fallback_used
      ? ` · fallback ${record.fallback_reason || "UNKNOWN"}`
      : "";
    return `${record.requested_mode || "unknown"} → ${record.served_mode || "unknown"} · ${Number(record.remote_attempts || 0)} attempt · ${Number(record.retry_count || 0)} retry · ${record.circuit_state || "UNKNOWN"}${fallback}`;
  }
  if (record.record_type === "TOOL_ROUTE") {
    const selected = Array.isArray(record.selected_tools)
      ? record.selected_tools.join(", ")
      : "";
    return `${record.route_mode || "UNKNOWN"} · ${Number(record.selected_count || 0)}/${Number(record.catalog_tools || 0)} tools · schema -${Number(record.schema_reduction_percent || 0).toFixed(1)}%${selected ? ` · ${selected}` : ""}`;
  }
  if (record.record_type === "TOOL_ROUTE_DENIED") {
    return `${record.tool_name || "unknown"} · ${record.error_code || "TOOL_ROUTE_NOT_ALLOWED"}`;
  }
  if (record.record_type === "TOOL_RESULT") {
    const risk = record.tool_policy?.riskLevel || "risk unknown";
    const latency = Number.isFinite(record.latency_ms)
      ? ` · ${record.latency_ms.toFixed(3)} ms`
      : "";
    return `${record.tool_name || "unknown"} · ${risk} · ${record.status || "UNKNOWN"}${latency}`;
  }
  if (
    record.record_type === "CONFIRMATION_REQUIRED" ||
    record.record_type === "CONFIRMATION_GRANTED" ||
    record.record_type === "CONFIRMATION_CANCELLED"
  ) {
    return `${record.tool_name || "unknown"} · ${record.risk || "风险未知"}`;
  }
  if (record.record_type === "TASK_RESULT") {
    return `状态 ${record.status || "UNKNOWN"} · ${record.steps || 0} step`;
  }
  if (record.record_type === "SESSION_MEMORY") {
    return `${record.memory_action || "UPDATED"} · ` +
      `${record.prior_turn_count || 0} → ${record.turn_count || 0}轮 · ` +
      `最多${record.max_turns || 12}轮/${record.retention_days || 7}天`;
  }
  if (record.record_type === "EXECUTION_STOPPED") {
    return `${record.error_code || "STOPPED"} · ${record.stage || "safe_point"}`;
  }
  return record.status || "Harness 生命周期记录";
}

function appendTraceRecord(record) {
  const item = document.createElement("article");
  item.className = "agent-run-step";
  const marker = document.createElement("span");
  marker.className = "agent-run-marker";
  const content = document.createElement("div");
  const heading = document.createElement("div");
  heading.className = "agent-run-step-heading";
  const title = document.createElement("strong");
  title.textContent = traceRecordLabel(record);
  const meta = document.createElement("span");
  const step = Number.isInteger(record.step)
    ? `step ${record.step}`
    : "task";
  meta.textContent = `${step} · ${formatTimestamp(record.timestamp)}`;
  heading.append(title, meta);
  const description = document.createElement("p");
  description.textContent = traceRecordDescription(record);
  content.append(heading, description);

  const toolCalls = Array.isArray(record.tool_calls)
    ? record.tool_calls
    : [];
  toolCalls.forEach((toolCall) => {
    const call = document.createElement("details");
    call.className = "agent-run-tool-call";
    const summary = document.createElement("summary");
    const policy = toolCall.policy || {};
    const exposure = policy.openWorldHint ? "外部网络" : "本地";
    summary.textContent =
      `${toolCall.name || "unknown tool"} · ${policy.riskLevel || "risk unknown"} · ${exposure}`;
    const argumentsView = document.createElement("pre");
    argumentsView.textContent = JSON.stringify(
      toolCall.arguments || {},
      null,
      2
    );
    call.append(summary, argumentsView);
    content.append(call);
  });
  item.append(marker, content);
  nodes.agentRunTimeline.append(item);
}

async function renderAgentWorkbench(task) {
  if (!task.task_id) {
    return;
  }
  const taskId = task.task_id;
  workbenchTaskId = taskId;
  nodes.agentWorkbench.classList.remove("hidden");
  nodes.agentWorkbench.open = true;
  nodes.agentWorkbenchSummary.textContent =
    `${task.status} · ${formatAgentStepCount(task)}`;
  nodes.agentRunTaskId.textContent = taskId;
  nodes.agentRunModel.textContent = task.model || "unknown";
  nodes.agentRunSkill.textContent = task.skill
    ? `${task.skill.name}@${task.skill.version}`
    : "未触发";
  const toolRoute = task.tool_route || {};
  nodes.agentRunToolRoute.textContent = toolRoute.schema_version
    ? `${toolRoute.mode} · ${Number(toolRoute.selected_count || 0)}/${Number(toolRoute.catalog_tools || 0)} · -${Number(toolRoute.schema_reduction_percent || 0).toFixed(1)}%`
    : "未记录";
  const modelResilience = task.model_resilience || {};
  nodes.agentRunModelResilience.textContent =
    modelResilience.schema_version
      ? `${modelResilience.last_requested_mode || "unknown"} → ${modelResilience.last_served_mode || "unknown"} · ${Number(modelResilience.retry_count || 0)} retry · ${Number(modelResilience.fallback_count || 0)} fallback · ${modelResilience.circuit_state || "UNKNOWN"}`
      : "未记录";
  nodes.agentRunSteps.textContent = `${getAgentStepCount(task)}`;
  nodes.agentRunDuration.textContent = formatAgentDuration(
    task.started_at,
    task.completed_at
  );
  const execution = task.execution || {};
  const limits = execution.limits || {};
  const usage = execution.usage || {};
  const costEstimate = execution.cost_estimate || {};
  const costLabel = costEstimate.available
    ? `$${Number(costEstimate.estimated_cost_usd || 0).toFixed(6)} est.`
    : "cost n/a";
  nodes.agentRunBudget.textContent = execution.schema_version
    ? `${Number(usage.model_calls || 0)}/${Number(limits.max_model_calls || 0)}M · ` +
      `${Number(usage.tool_calls || 0)}/${Number(limits.max_tool_calls || 0)}T · ` +
      `${Number(usage.external_tool_calls || 0)}/${Number(limits.max_external_tool_calls || 0)}E · ` +
      `${Number(usage.total_tokens || 0)}/${Number(limits.max_total_tokens || 0)} tok · ` +
      `${costLabel} · ` +
      `${Number(usage.elapsed_seconds || 0).toFixed(3)}s`
    : "未记录";
  nodes.agentRunTimeline.replaceChildren();
  appendEmpty(nodes.agentRunTimeline, "正在读取脱敏 Trace…");
  try {
    const trace = await getJson(
      `${endpoints.agent}/${encodeURIComponent(taskId)}/trace?limit=100`
    );
    if (workbenchTaskId !== taskId) {
      return;
    }
    nodes.agentRunTimeline.replaceChildren();
    if (!Array.isArray(trace.records) || trace.records.length === 0) {
      appendEmpty(nodes.agentRunTimeline, "当前任务还没有 Trace 记录");
      return;
    }
    trace.records.forEach(appendTraceRecord);
    if (trace.truncated) {
      appendEmpty(
        nodes.agentRunTimeline,
        "Trace 已按安全上限截断，仅显示最近记录"
      );
    }
  } catch (error) {
    if (workbenchTaskId !== taskId) {
      return;
    }
    nodes.agentRunTimeline.replaceChildren();
    appendEmpty(nodes.agentRunTimeline, "任务 Trace 暂时不可用");
  }
}

function renderAgentSnapshot(task) {
  if (
    task.status !== "COMPLETED" ||
    typeof task.snapshot_url !== "string" ||
    !task.snapshot_url.startsWith("/api/v1/agent/tasks/")
  ) {
    hideAgentSnapshot();
    return;
  }
  const toolResults = Array.isArray(task.tool_results)
    ? task.tool_results
    : [];
  const snapshotTool = toolResults.find(
    (result) =>
      result.tool_name === "camera.capture_snapshot" &&
      result.status === "SUCCEEDED"
  );
  const snapshot = snapshotTool ? snapshotTool.result || {} : {};
  nodes.agentSnapshotImage.src = task.snapshot_url;
  nodes.agentSnapshotLink.href = task.snapshot_url;
  nodes.agentSnapshotMeta.textContent =
    `${Number(snapshot.bytes || 0).toLocaleString("zh-CN")} bytes · ` +
    `SHA-256 ${String(snapshot.sha256 || "unknown").slice(0, 12)}…`;
  nodes.agentSnapshot.classList.remove("hidden");
}

function hideAgentSnapshot() {
  nodes.agentSnapshot.classList.add("hidden");
  nodes.agentSnapshotImage.removeAttribute("src");
  nodes.agentSnapshotLink.removeAttribute("href");
  nodes.agentSnapshotMeta.textContent = "";
}

function renderAgentReport(task) {
  if (
    task.status !== "COMPLETED" ||
    typeof task.report_url !== "string" ||
    !task.report_url.startsWith("/api/v1/agent/tasks/")
  ) {
    hideAgentReport();
    return;
  }
  const toolResults = Array.isArray(task.tool_results)
    ? task.tool_results
    : [];
  const reportTool = toolResults.find(
    (result) =>
      result.tool_name === "report.generate" &&
      result.status === "SUCCEEDED"
  );
  const report = reportTool ? reportTool.result || {} : {};
  nodes.agentReportLink.href = task.report_url;
  nodes.agentReportMeta.textContent =
    `${report.date || "未知日期"} · ` +
    `${Number(report.event_count || 0)} 条事件 · ` +
    `${Number(report.bytes || 0).toLocaleString("zh-CN")} bytes · ` +
    `SHA-256 ${String(report.sha256 || "unknown").slice(0, 12)}…`;
  nodes.agentReport.classList.remove("hidden");
}

function hideAgentReport() {
  nodes.agentReport.classList.add("hidden");
  nodes.agentReportLink.removeAttribute("href");
  nodes.agentReportMeta.textContent = "";
}

function renderAgentConfirmation(task) {
  const pending = task.pending_confirmation;
  if (
    task.status !== "AWAITING_CONFIRMATION" ||
    !pending ||
    typeof pending.tool_name !== "string"
  ) {
    activeAgentTaskId = null;
    activeAgentToolName = null;
    nodes.agentConfirmation.classList.add("hidden");
    renderAgentModelSwitch(currentAgentModel);
    return;
  }
  activeAgentTaskId = task.task_id;
  activeAgentToolName = pending.tool_name;
  nodes.agentAnswer.textContent =
    "Agent 尚未执行该动作。请核对工具、风险和参数后选择确认或取消。";
  nodes.agentConfirmationRisk.textContent = pending.risk || "L1";
  nodes.agentConfirmationTool.textContent = pending.tool_name;
  nodes.agentConfirmationDescription.textContent =
    pending.tool_name === "camera.capture_snapshot"
      ? "将在 Jetson 本地保存一张当前标注画面，不会发送到外部。"
      : pending.tool_name === "camera.restart"
        ? "将短暂中断并受控重启摄像头推理工作进程；API、Docker 和 Jetson 不会重启。"
      : pending.tool_name === "report.generate"
        ? "将在 Jetson 本地生成一份 Markdown 事件报告，不会发送到外部。"
        : pending.tool_name === "system.cleanup_retained_data"
          ? "将永久删除参数中列出的旧日志。执行前会重新校验固定策略、计划ID和文件指纹，并写入审计记录；证据和事件数据库不会进入计划。"
        : pending.tool_name === "recovery.create_backup"
          ? "将在 Jetson 本地创建一份有界灾难恢复备份并校验 SQLite 一致性与文件 SHA-256。DeepSeek、登录和 TLS 凭据不会进入备份；此操作不会执行恢复。"
        : pending.tool_name === "memory.remember"
          ? "将在 Jetson 本地创建或更新一项长期事实/偏好；请核对键和值。凭据、证据路径、图片和工具原始结果禁止写入。"
        : pending.tool_name === "memory.forget"
          ? "将从 Jetson 本地长期记忆中删除这一条精确记录，不会清除短期会话或事件数据。"
        : pending.tool_name === "event.acknowledge"
          ? "只会把指定事件标记为已处理；不会删除事件或证据。"
          : "该动作需要你的明确确认后才能执行。";
  nodes.agentConfirmationArguments.textContent = JSON.stringify(
    pending.arguments || {},
    null,
    2
  );
  nodes.agentConfirmation.classList.remove("hidden");
  setAgentActionLoading(false);
  renderAgentModelSwitch(currentAgentModel);
}

async function resolveAgentConfirmation(action) {
  if (!activeAgentTaskId) {
    return;
  }
  const taskId = activeAgentTaskId;
  const toolName = activeAgentToolName;
  const isConfirmation = action === "confirm";
  const body = isConfirmation
    ? { confirmation: "CONFIRM_TOOL_EXECUTION" }
    : { cancel: true };
  setAgentActionLoading(true);
  try {
    const response = await fetch(
      `${endpoints.agent}/${encodeURIComponent(taskId)}/${action}`,
      {
        method: "POST",
        headers: authenticatedHeaders({
          Accept: "application/json",
          "Content-Type": "application/json; charset=utf-8",
        }),
        body: JSON.stringify(body),
      }
    );
    const payload = await response.json();
    if (!response.ok) {
      const detail = payload.detail || `HTTP ${response.status}`;
      throw new Error(String(detail));
    }
    renderAgentTask(payload);
    if (
      isConfirmation &&
      (toolName === "memory.remember" || toolName === "memory.forget") &&
      payload.status === "COMPLETED"
    ) {
      await refreshLongTermMemory();
    }
    if (
      isConfirmation &&
      toolName === "event.acknowledge" &&
      payload.status === "COMPLETED"
    ) {
      await refresh();
    }
    if (
      isConfirmation &&
      toolName === "system.cleanup_retained_data" &&
      payload.status === "COMPLETED"
    ) {
      await refresh();
    }
  } catch (error) {
    nodes.agentResponse.classList.add("error");
    nodes.agentTaskStatus.textContent = "ACTION FAILED";
    nodes.agentAnswer.textContent =
      `任务操作失败：${error.message || "未知错误"}`;
    setAgentActionLoading(false);
  }
}

function setAgentActionLoading(loading) {
  nodes.agentConfirm.disabled = loading;
  nodes.agentCancel.disabled = loading;
  nodes.agentConfirm.textContent = loading
    ? "正在处理…"
    : activeAgentToolName === "report.generate"
      ? "确认生成并保存报告"
    : activeAgentToolName === "system.cleanup_retained_data"
      ? "确认永久删除已预览旧日志"
    : activeAgentToolName === "recovery.create_backup"
      ? "确认创建本地恢复备份"
      : activeAgentToolName === "memory.remember"
        ? "确认写入长期记忆"
      : activeAgentToolName === "memory.forget"
        ? "确认删除长期记忆"
      : activeAgentToolName === "event.acknowledge"
        ? "确认标记为已处理"
        : "确认拍摄并保存";
}

function renderAgentError(error) {
  activeAgentTaskId = null;
  activeAgentToolName = null;
  nodes.agentConfirmation.classList.add("hidden");
  hideAgentSnapshot();
  hideAgentReport();
  nodes.agentResponse.classList.remove("hidden");
  nodes.agentResponse.classList.add("error");
  nodes.agentTaskStatus.textContent = "REQUEST FAILED";
  nodes.agentTaskMeta.textContent = "";
  nodes.agentAnswer.textContent =
    `Agent 请求失败：${error.message || "未知错误"}`;
  nodes.agentToolResults.replaceChildren();
}

function appendToolResult(text, status) {
  const item = document.createElement("span");
  item.className = `tool-result ${status}`;
  item.textContent = text;
  nodes.agentToolResults.append(item);
}

function updateMessageCount() {
  nodes.messageCount.textContent =
    `${nodes.agentMessage.value.length} / 1000`;
}

function refreshLiveFrame() {
  if (
    document.visibilityState === "hidden"
    || liveFrameRequestPending
  ) {
    return;
  }
  liveFrameRequestPending = true;
  const candidate = new Image();
  const source = `${endpoints.frame}?t=${Date.now()}`;
  candidate.decoding = "async";
  candidate.onload = () => {
    liveFrameRequestPending = false;
    nodes.liveFrame.src = source;
    nodes.framePlaceholder.classList.add("hidden");
    nodes.liveFrameStatus.classList.add("streaming");
    nodes.liveFrameStatus.textContent = "画面持续更新";
  };
  candidate.onerror = () => {
    liveFrameRequestPending = false;
    nodes.liveFrameStatus.classList.remove("streaming");
    nodes.liveFrameStatus.textContent = "等待推理画面";
    if (!nodes.liveFrame.getAttribute("src")) {
      nodes.framePlaceholder.classList.remove("hidden");
    }
  };
  candidate.src = source;
}

async function applyEventFilters(event) {
  event.preventDefault();
  eventPagesExpanded = false;
  try {
    const payload = await getJson(buildEventUrl());
    renderEvents(payload);
  } catch (error) {
    nodes.eventList.replaceChildren();
    nodes.eventLoadMore.classList.add("hidden");
    nodes.eventCollapse.classList.add("hidden");
    appendEmpty(nodes.eventList, "筛选后的事件读取失败");
  }
}

async function loadMoreEvents() {
  if (!eventNextCursor) {
    return;
  }
  nodes.eventLoadMore.disabled = true;
  nodes.eventLoadMore.textContent = "正在加载…";
  try {
    const payload = await getJson(
      buildEventUrl(eventNextCursor)
    );
    renderEvents(payload, true);
  } catch (error) {
    nodes.eventLoadMore.disabled = false;
    nodes.eventLoadMore.textContent = "加载失败，点击重试";
  }
}

async function collapseEvents() {
  nodes.eventCollapse.disabled = true;
  nodes.eventLoadMore.disabled = true;
  nodes.eventCollapse.textContent = "正在返回最新事件…";
  try {
    eventPagesExpanded = false;
    eventNextCursor = null;
    const payload = await getJson(buildEventUrl());
    renderEvents(payload);
    nodes.eventsPanel.scrollIntoView({
      behavior: "smooth",
      block: "start",
    });
  } catch (error) {
    eventPagesExpanded = true;
    nodes.eventCollapse.disabled = false;
    nodes.eventLoadMore.disabled = false;
    nodes.eventCollapse.textContent = "返回失败，点击重试";
  }
}

nodes.button.addEventListener("click", () => {
  visionModelLoaded = false;
  eventPagesExpanded = false;
  nodes.eventCollapse.classList.add("hidden");
  refreshDashboard();
});
nodes.authLoginForm.addEventListener("submit", submitAuthentication);
nodes.authLogout.addEventListener("click", logoutAuthentication);
nodes.mcpToolsToggle.addEventListener("click", toggleMcpCatalog);
nodes.zoneDrawToggle.addEventListener("click", toggleZoneDrawing);
nodes.zoneCanvas.addEventListener("click", addDraftPoint);
nodes.zoneUndoPoint.addEventListener("click", () => {
  draftZonePoints.pop();
  updateZoneDraft();
});
nodes.zoneClearDraft.addEventListener("click", () => {
  draftZonePoints = [];
  updateZoneDraft();
});
nodes.zoneApplyDraft.addEventListener(
  "click",
  applyDraftToSelectedZone
);
nodes.zoneSnapBottom.addEventListener("click", snapDraftBottom);
nodes.zoneRestoreDefault.addEventListener(
  "click",
  restoreSelectedZoneDefault
);
nodes.zoneDiscardChanges.addEventListener(
  "click",
  discardZoneChanges
);
nodes.zoneSaveForm.addEventListener(
  "submit",
  saveZoneConfiguration
);
nodes.zoneAdminToken.addEventListener(
  "input",
  updateZoneControls
);
nodes.zoneSaveConfirmation.addEventListener(
  "input",
  updateZoneControls
);
nodes.zoneEditTarget.addEventListener(
  "change",
  updateZoneControls
);
nodes.eventFilterForm.addEventListener("submit", applyEventFilters);
nodes.eventLoadMore.addEventListener("click", loadMoreEvents);
nodes.eventCollapse.addEventListener("click", collapseEvents);
nodes.eventFilterReset.addEventListener("click", () => {
  nodes.eventFilterForm.reset();
  nodes.eventFilterForm.dispatchEvent(
    new Event("submit", { cancelable: true })
  );
});
nodes.eventDetailClose.addEventListener("click", closeEventDetail);
nodes.eventAcknowledge.addEventListener(
  "click",
  requestEventAcknowledgement
);
nodes.eventDetailBackdrop.addEventListener("click", (event) => {
  if (event.target === nodes.eventDetailBackdrop) {
    closeEventDetail();
  }
});
document.addEventListener("keydown", (event) => {
  if (
    event.key === "Escape" &&
    !nodes.eventDetailBackdrop.classList.contains("hidden")
  ) {
    closeEventDetail();
  }
});
nodes.agentForm.addEventListener("submit", submitAgentTask);
nodes.agentModeOnline.addEventListener("click", () => {
  switchAgentModel("online");
});
nodes.agentModeOffline.addEventListener("click", () => {
  switchAgentModel("offline");
});
nodes.agentMessage.addEventListener("input", updateMessageCount);
nodes.agentConfirm.addEventListener("click", () => {
  resolveAgentConfirmation("confirm");
});
nodes.agentCancel.addEventListener("click", () => {
  resolveAgentConfirmation("cancel");
});
nodes.agentSessionClear.addEventListener("click", clearAgentSession);
nodes.agentLongTermRefresh.addEventListener(
  "click",
  refreshLongTermMemory
);
nodes.agentJobCancel.addEventListener("click", cancelQueuedAgentJob);
document.querySelectorAll(".prompt-chip").forEach((button) => {
  button.addEventListener("click", () => {
    nodes.agentMessage.value = button.dataset.prompt || "";
    updateMessageCount();
    nodes.agentMessage.focus();
  });
});
initializeAuthentication();
