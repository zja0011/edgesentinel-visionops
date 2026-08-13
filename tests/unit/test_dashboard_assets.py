import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)
DASHBOARD_DIR = os.path.join(PROJECT_DIR, "apps", "dashboard")


def read_asset(name):
    with open(
        os.path.join(DASHBOARD_DIR, name),
        "r",
        encoding="utf-8",
    ) as asset_file:
        return asset_file.read()


class DashboardAssetTests(unittest.TestCase):
    def test_html_contains_accessible_agent_form(self):
        html = read_asset("index.html")

        self.assertIn('id="agent-form"', html)
        self.assertIn('id="auth-login-form"', html)
        self.assertIn('id="auth-username"', html)
        self.assertIn('id="auth-password"', html)
        self.assertIn('id="auth-logout"', html)
        self.assertIn('id="agent-mode-online"', html)
        self.assertIn('id="agent-mode-offline"', html)
        self.assertIn('id="weather-prompt"', html)
        self.assertIn('id="live-frame"', html)
        self.assertIn('id="event-filter-form"', html)
        self.assertIn('id="event-status-filter"', html)
        self.assertIn('id="event-severity-filter"', html)
        self.assertIn('id="event-load-more"', html)
        self.assertIn('id="event-collapse"', html)
        self.assertIn('id="event-minutes-filter"', html)
        self.assertIn('id="event-summary"', html)
        self.assertIn('id="event-trend"', html)
        self.assertIn('value="1440"', html)
        self.assertIn('id="event-acknowledge"', html)
        self.assertIn('id="event-disposition-status"', html)
        self.assertIn('id="event-evidence-integrity"', html)
        self.assertIn('role="dialog"', html)
        self.assertIn('id="zone-canvas"', html)
        self.assertIn('id="zone-draw-toggle"', html)
        self.assertIn('id="zone-edit-target"', html)
        self.assertIn('id="zone-save-form"', html)
        self.assertIn('id="zone-admin-token"', html)
        self.assertIn('id="zone-snap-bottom"', html)
        self.assertIn('id="zone-restore-default"', html)
        self.assertIn('id="zone-anchor-guidance"', html)
        self.assertIn('id="zone-runtime-status"', html)
        self.assertIn('id="agent-confirmation"', html)
        self.assertIn('id="agent-confirm"', html)
        self.assertIn('id="agent-cancel"', html)
        self.assertIn('id="agent-snapshot"', html)
        self.assertIn('id="agent-snapshot-image"', html)
        self.assertIn('id="agent-snapshot-link"', html)
        self.assertIn('id="agent-workbench"', html)
        self.assertIn('id="agent-evaluation-baseline"', html)
        self.assertIn('id="agent-evaluation-badge"', html)
        self.assertIn('id="agent-long-term-memory"', html)
        self.assertIn('id="agent-long-term-list"', html)
        self.assertIn('id="agent-long-term-refresh"', html)
        self.assertIn('id="memory-remember-prompt"', html)
        self.assertIn('id="memory-search-prompt"', html)
        self.assertIn('id="agent-run-task-id"', html)
        self.assertIn('id="agent-run-skill"', html)
        self.assertIn('id="agent-run-tool-route"', html)
        self.assertIn('id="agent-model-resilience"', html)
        self.assertIn(
            'id="agent-run-model-resilience"', html
        )
        self.assertIn('id="agent-run-timeline"', html)
        self.assertIn('id="agent-run-budget"', html)
        self.assertIn("HARNESS RUN", html)
        self.assertIn('id="agent-report"', html)
        self.assertIn('id="agent-report-meta"', html)
        self.assertIn('id="agent-report-link"', html)
        self.assertIn("生成今日报告", html)
        self.assertIn("检查 Jetson 状态", html)
        self.assertIn("Jetson运行状态是否正常？", html)
        self.assertIn('id="system-health-prompt"', html)
        self.assertIn("左侧区域人数", html)
        self.assertIn("左侧区域现在有几个人？", html)
        self.assertIn('id="zone-status-prompt"', html)
        self.assertIn('id="inventory-status-prompt"', html)
        self.assertIn("瓶子当前稳定库存是多少？", html)
        self.assertIn('id="object-count-prompt"', html)
        self.assertIn("当前画面有几个瓶子？", html)
        self.assertIn('id="track-history-prompt"', html)
        self.assertIn("查询当前人员轨迹", html)
        self.assertIn('id="removed-items-prompt"', html)
        self.assertIn("最近10分钟移走了哪些瓶子？", html)
        self.assertIn('id="inventory-compare-prompt"', html)
        self.assertIn("对比瓶子库存，期望2个。", html)
        self.assertIn("检查摄像头状态", html)
        self.assertIn("摄像头状态正常吗？", html)
        self.assertIn('id="camera-status-prompt"', html)
        self.assertIn('id="model-info-prompt"', html)
        self.assertIn(
            "当前视觉模型版本和Engine完整性是什么？",
            html,
        )
        self.assertIn('id="vision-model-runtime"', html)
        self.assertIn('id="vision-performance-runtime"', html)
        self.assertIn('id="vision-performance-prompt"', html)
        self.assertIn('id="runtime-benchmark-status"', html)
        self.assertIn('id="runtime-benchmark-prompt"', html)
        self.assertIn('id="storage-usage"', html)
        self.assertIn('id="storage-usage-prompt"', html)
        self.assertIn(
            'id="retention-preview-status"',
            html,
        )
        self.assertIn(
            'id="retention-preview-prompt"',
            html,
        )
        self.assertIn(
            'id="retention-cleanup-prompt"',
            html,
        )
        self.assertIn(
            'id="retention-cleanup-history-status"',
            html,
        )
        self.assertIn(
            'id="retention-cleanup-history-prompt"',
            html,
        )
        self.assertIn(
            'id="evidence-integrity-status"',
            html,
        )
        self.assertIn(
            'id="evidence-integrity-prompt"',
            html,
        )
        self.assertIn(
            "当前视觉性能、处理帧率和P95延迟是多少？",
            html,
        )
        self.assertIn('id="camera-restart-prompt"', html)
        self.assertIn('id="camera-runtime-status"', html)
        self.assertIn('id="mcp-runtime-status"', html)
        self.assertIn('id="mcp-tools-toggle"', html)
        self.assertIn('id="mcp-tools-panel"', html)
        self.assertIn('id="mcp-tools-list"', html)
        self.assertIn("25工具 · 5资源 · 3提示", html)
        self.assertIn('id="recovery-status-prompt"', html)
        self.assertIn('id="recovery-create-prompt"', html)
        self.assertIn('value="CAMERA_OFFLINE"', html)
        self.assertIn('value="CAMERA_RECOVERED"', html)
        self.assertIn('value="ZONE_DWELL"', html)
        self.assertIn("拍摄当前快照", html)
        self.assertIn('type="password"', html)
        self.assertIn("SAVE_ZONE_CONFIG", html)
        self.assertIn('for="agent-message"', html)
        self.assertIn('maxlength="1000"', html)
        self.assertIn('aria-live="polite"', html)
        self.assertNotIn("https://", html)
        self.assertNotIn("http://", html)

    def test_javascript_uses_agent_api_without_html_injection(self):
        javascript = read_asset("dashboard.js")
        self.assertEqual(
            javascript.count("function formatTimestamp(value)"),
            1,
        )
        self.assertIn("formatTimestamp(record.timestamp)", javascript)
        self.assertIn("function getAgentStepCount(task)", javascript)
        self.assertIn("task.steps ?? task.step", javascript)
        self.assertIn("formatAgentStepCount(task)", javascript)
        self.assertNotIn("${task.steps} step", javascript)
        self.assertIn("recovery.create_backup", javascript)
        self.assertIn("确认创建本地恢复备份", javascript)

        self.assertIn('agent: "/api/v1/agent/tasks"', javascript)
        self.assertIn('authLogin: "/api/v1/auth/login"', javascript)
        self.assertIn("authenticatedHeaders", javascript)
        self.assertIn("initializeAuthentication", javascript)
        self.assertIn('"X-EdgeSentinel-CSRF"', javascript)
        self.assertIn('agentJobs: "/api/v1/agent/jobs"', javascript)
        self.assertIn(
            'agentMemories: "/api/v1/agent/memories"',
            javascript,
        )
        self.assertIn("refreshLongTermMemory", javascript)
        self.assertIn("memory.remember", javascript)
        self.assertIn("memory.forget", javascript)
        self.assertIn(
            'tools: "/api/v1/harness/tools"',
            javascript,
        )
        self.assertIn("isMcpTool", javascript)
        self.assertIn("renderMcpCatalog", javascript)
        self.assertIn("toggleMcpCatalog", javascript)
        self.assertIn("collapseEvents", javascript)
        self.assertIn("scrollIntoView", javascript)
        self.assertIn("renderAgentWorkbench", javascript)
        self.assertIn("renderAgentEvaluation", javascript)
        self.assertIn(
            'agentEvaluation: "/api/v1/harness/evaluations/latest"',
            javascript,
        )
        self.assertIn("appendTraceRecord", javascript)
        self.assertIn("EXECUTION_STOPPED", javascript)
        self.assertIn("请求安全停止", javascript)
        self.assertIn("max_external_tool_calls", javascript)
        self.assertIn("MODEL_USAGE", javascript)
        self.assertIn("MODEL_RESILIENCE", javascript)
        self.assertIn("fallback_reason", javascript)
        self.assertIn("circuit_state", javascript)
        self.assertIn("agentRunModelResilience", javascript)
        self.assertIn("TOOL_ROUTE", javascript)
        self.assertIn("TOOL_ROUTE_DENIED", javascript)
        self.assertIn("schema_reduction_percent", javascript)
        self.assertIn("agentRunToolRoute", javascript)
        self.assertIn("max_total_tokens", javascript)
        self.assertIn("estimated_cost_usd", javascript)
        self.assertIn("cost n/a", javascript)
        self.assertIn("agentRunSkill", javascript)
        self.assertIn("SKILL_SELECTED", javascript)
        self.assertIn("HOOK_RESULT", javascript)
        self.assertIn("hook_point", javascript)
        self.assertIn("/trace?limit=100", javascript)
        self.assertIn(
            'agentModelMode: "/api/v1/agent/model-mode"',
            javascript,
        )
        self.assertIn("SWITCH_AGENT_MODEL", javascript)
        self.assertIn("switchAgentModel", javascript)
        self.assertIn('frame: "/api/v1/vision/frame"', javascript)
        self.assertIn('system: "/api/v1/system/status"', javascript)
        self.assertIn('camera: "/api/v1/camera/status"', javascript)
        self.assertIn('model: "/api/v1/vision/model"', javascript)
        self.assertIn(
            'performance: "/api/v1/vision/performance"',
            javascript,
        )
        self.assertIn(
            'benchmark: "/api/v1/system/benchmark"',
            javascript,
        )
        self.assertIn(
            'storage: "/api/v1/system/storage"',
            javascript,
        )
        self.assertIn(
            (
                'retentionPreview: '
                '"/api/v1/system/retention-preview"'
            ),
            javascript,
        )
        self.assertIn(
            (
                '"/api/v1/system/'
                'retention-cleanup-history"'
            ),
            javascript,
        )
        self.assertIn(
            (
                'evidenceIntegrity: '
                '"/api/v1/events/evidence-integrity"'
            ),
            javascript,
        )
        self.assertIn("refreshLiveFrame", javascript)
        self.assertIn("liveFrameRequestPending", javascript)
        self.assertIn(
            "window.setInterval(refreshLiveFrame, 500)",
            javascript,
        )
        self.assertIn("renderSystem", javascript)
        self.assertIn("renderCameraStatus", javascript)
        self.assertIn("renderVisionModel", javascript)
        self.assertIn("renderVisionPerformance", javascript)
        self.assertIn("renderRuntimeBenchmark", javascript)
        self.assertIn("renderStorageUsage", javascript)
        self.assertIn("renderRetentionPreview", javascript)
        self.assertIn(
            "renderRetentionCleanupHistory",
            javascript,
        )
        self.assertIn("renderEvidenceIntegrity", javascript)
        self.assertIn("visionModelLoaded", javascript)
        self.assertIn(
            'pending.tool_name === "camera.restart"',
            javascript,
        )
        self.assertIn('CAMERA_OFFLINE: "摄像头离线"', javascript)
        self.assertIn(
            'CAMERA_RECOVERED: "摄像头恢复"',
            javascript,
        )
        self.assertIn('ZONE_DWELL: "长时间停留"', javascript)
        self.assertIn("buildEventUrl", javascript)
        self.assertIn("eventMinutesFilter", javascript)
        self.assertIn("eventStatusFilter", javascript)
        self.assertIn(
            'parameters.set("status", status)',
            javascript,
        )
        self.assertIn(
            'eventSummary: "/api/v1/events/summary/recent"',
            javascript,
        )
        self.assertIn("renderEventSummary", javascript)
        self.assertIn("event.track_id", javascript)
        self.assertIn("buildEventSummaryUrl", javascript)
        self.assertIn('parameters.set("minutes", minutes)', javascript)
        self.assertIn(
            "comparison?.largest_event_type_change",
            javascript,
        )
        self.assertIn("主要变化", javascript)
        self.assertIn(
            "comparison?.assessment",
            javascript,
        )
        self.assertIn(
            "changeAssessment.threshold_exceeded",
            javascript,
        )
        self.assertIn(
            "comparison?.significant_event_type_count",
            javascript,
        )
        self.assertIn("significantContributorText", javascript)
        self.assertIn(
            "comparison?.structural_change?.by_event_type",
            javascript,
        )
        self.assertIn("structuralChangeText", javascript)
        self.assertIn(
            "comparison?.previous_window?.offset_minutes",
            javascript,
        )
        self.assertIn("comparisonAlignmentText", javascript)
        self.assertIn(
            "payload.reference_baselines",
            javascript,
        )
        self.assertIn("referenceBaselineText", javascript)
        self.assertIn(
            "referenceBaselines.assessment?.status",
            javascript,
        )
        self.assertIn(
            "referenceBaselines.consistency?.status",
            javascript,
        )
        self.assertIn("openEventDetail", javascript)
        self.assertIn(
            '"/evidence-integrity"',
            javascript,
        )
        self.assertIn(
            "renderEventEvidenceIntegrity",
            javascript,
        )
        self.assertIn('zones: "/api/v1/zones"', javascript)
        self.assertIn(
            'zoneDefaults: "/api/v1/zones/defaults"',
            javascript,
        )
        self.assertIn("drawZoneCanvas", javascript)
        self.assertIn("addDraftPoint", javascript)
        self.assertIn("snapDraftBottom", javascript)
        self.assertIn("restoreSelectedZoneDefault", javascript)
        self.assertIn("isDraftAnchorSafe", javascript)
        self.assertIn("updateZoneRuntimeStatus", javascript)
        self.assertIn("无需重启", javascript)
        self.assertIn("applyDraftToSelectedZone", javascript)
        self.assertIn("saveZoneConfiguration", javascript)
        self.assertIn(
            '"X-EdgeSentinel-Config-Token": token',
            javascript,
        )
        self.assertIn("submitAgentTask", javascript)
        self.assertIn("new EventSource", javascript)
        self.assertIn("Idempotency-Key", javascript)
        self.assertIn("cancelQueuedAgentJob", javascript)
        self.assertIn("activeAgentSessionId", javascript)
        self.assertIn("ensureAgentSession", javascript)
        self.assertIn("session_id: sessionId", javascript)
        self.assertIn("resolveAgentConfirmation", javascript)
        self.assertIn(
            'confirmation: "CONFIRM_TOOL_EXECUTION"',
            javascript,
        )
        self.assertIn('resolveAgentConfirmation("confirm")', javascript)
        self.assertIn('resolveAgentConfirmation("cancel")', javascript)
        self.assertIn("renderAgentSnapshot", javascript)
        self.assertIn("task.snapshot_url", javascript)
        self.assertIn("renderAgentReport", javascript)
        self.assertIn("task.report_url", javascript)
        self.assertIn('pending.tool_name === "report.generate"', javascript)
        self.assertIn(
            (
                'pending.tool_name === '
                '"system.cleanup_retained_data"'
            ),
            javascript,
        )
        self.assertIn(
            'pending.tool_name === "event.acknowledge"',
            javascript,
        )
        self.assertIn("requestEventAcknowledgement", javascript)
        self.assertIn("确认处理事件", javascript)
        self.assertNotIn("innerHTML", javascript)
        self.assertNotIn("insertAdjacentHTML", javascript)
        self.assertNotIn("localStorage", javascript)
        self.assertIn("window.sessionStorage", javascript)
        self.assertIn("CLEAR_AGENT_SESSION", javascript)

    def test_styles_include_agent_and_mobile_layout(self):
        css = read_asset("dashboard.css")

        self.assertIn(".agent-panel", css)
        self.assertIn(".agent-response", css)
        self.assertIn(".agent-confirmation", css)
        self.assertIn(".agent-job-cancel", css)
        self.assertIn(".agent-evaluation-baseline", css)
        self.assertIn(".risk-badge", css)
        self.assertIn(".agent-snapshot", css)
        self.assertIn(".agent-report", css)
        self.assertIn(".event-disposition", css)
        self.assertIn(".event-disposition-badge", css)
        self.assertIn(".event-summary", css)
        self.assertIn("@media (max-width: 580px)", css)


if __name__ == "__main__":
    unittest.main()
