import os
import unittest


PROJECT_DIR = os.path.abspath(
    os.path.join(os.path.dirname(__file__), os.pardir, os.pardir)
)


def read_script(name):
    with open(
        os.path.join(PROJECT_DIR, "scripts", name),
        "r",
        encoding="utf-8",
    ) as script_file:
        return script_file.read()


class HostRuntimeScriptTests(unittest.TestCase):
    def test_host_launcher_uses_a_managed_detached_container(self):
        script = read_script("host_edgesentinel.sh")

        self.assertIn("--label \"$MANAGED_LABEL=true\"", script)
        self.assertIn("--init", script)
        self.assertIn("--network host", script)
        self.assertIn("--device /dev/video0", script)
        self.assertIn("sleep infinity", script)
        self.assertIn("[ -f /.dockerenv ]", script)
        self.assertNotIn("--rm", script)
        self.assertNotIn("--restart", script)
        self.assertIn("prepare_model_file", script)
        self.assertIn(
            'sudo cp /proc/device-tree/model "$MODEL_FILE"',
            script,
        )
        self.assertIn('sudo rm -f -- "$MODEL_FILE/model"', script)
        self.assertIn('sudo rmdir -- "$MODEL_FILE"', script)
        self.assertNotIn('rm -rf', script)
        self.assertLess(
            script.index("prepare_model_file", script.index("ensure_container()")),
            script.index(
                'docker_cmd start "$CONTAINER_NAME"',
                script.index("ensure_container()"),
            ),
        )

    def test_host_launcher_does_not_put_the_token_in_docker_arguments(self):
        script = read_script("host_edgesentinel.sh")

        self.assertIn("start --token-stdin", script)
        self.assertIn("start --read-only", script)
        self.assertIn("unset ADMIN_TOKEN", script)
        self.assertNotIn("EDGESENTINEL_CONFIG_TOKEN=", script)
        self.assertNotIn("--env", script)

    def test_host_launcher_refuses_unmanaged_name_collision(self):
        script = read_script("host_edgesentinel.sh")

        self.assertIn("validate_managed_container", script)
        self.assertIn("Refusing to modify or replace it.", script)
        self.assertNotIn("docker rm", script)

    def test_acceptance_checks_docker_secret_and_runtime_health(self):
        script = read_script("check_host_container.sh")

        self.assertIn("EDGESENTINEL_CONFIG_TOKEN=", script)
        self.assertIn("check_service_manager.sh", script)
        self.assertIn("Restart policy: $restart_policy", script)
        self.assertIn("Host Container smoke test passed.", script)

    def test_live_launcher_supervises_camera_worker_restarts(self):
        script = read_script("run_dashboard_live.sh")

        self.assertIn("apps.vision_supervisor", script)
        self.assertIn("vision-supervisor.json", script)
        self.assertIn("--device /dev/video0", script)
        self.assertIn("--retry-seconds 3", script)
        self.assertIn("--startup-timeout-seconds 120", script)
        self.assertIn(
            "--control-input data/runtime/vision-control.json",
            script,
        )
        self.assertIn('--event-output "$EVENT_LOG"', script)
        self.assertIn('--event-db "$EVENT_DB"', script)
        self.assertIn("--camera-id camera_01", script)
        self.assertIn("--zone-dwell-seconds 20", script)
        self.assertIn("apps.vision_probe", script)
        self.assertLess(
            script.index("apps.vision_supervisor"),
            script.index("apps.vision_probe"),
        )

    def test_camera_recovery_checks_linked_lifecycle_events(self):
        script = read_script("check_camera_recovery.ps1")

        self.assertIn("CAMERA_OFFLINE events added", script)
        self.assertIn("CAMERA_RECOVERED events added", script)
        self.assertIn("offline_event_id", script)
        self.assertIn("outage_duration_seconds", script)
        self.assertIn("Invoke-Utf8AgentTask", script)
        self.assertIn("Agent camera event count", script)

    def test_dwell_acceptance_checks_event_evidence_and_agent(self):
        script = read_script("check_zone_dwell.ps1")

        self.assertIn("type=ZONE_DWELL", script)
        self.assertIn("dwell_seconds_threshold", script)
        self.assertIn("observed_dwell_seconds", script)
        self.assertIn("Evidence bytes", script)
        self.assertIn("Agent dwell event count", script)
        self.assertIn("ZONE_DWELL smoke test passed.", script)

    def test_mcp_acceptance_uses_local_stdio_transport(self):
        script = read_script("run_mcp_server_test.sh")

        self.assertIn("apps.mcp_smoke_test", script)
        self.assertIn("mcp-tools-", script)
        self.assertIn("mcp-result-", script)

    def test_mcp_host_acceptance_is_local_and_bounded(self):
        script = read_script("run_mcp_host_test.sh")
        self.assertIn("apps.mcp_host_smoke_test", script)
        self.assertIn("mcp-host-tools-", script)
        self.assertIn("mcp-host-result-", script)
        self.assertIn("--timeout-seconds 10", script)
        self.assertNotIn("curl", script)

    def test_model_manifest_acceptance_is_read_only(self):
        script = read_script("run_model_manifest_test.sh")
        self.assertIn("apps.model_manifest_smoke_test", script)
        self.assertIn("current-model.json", script)
        self.assertIn("/jetson-inference/data/networks", script)
        self.assertIn("model-tools-", script)
        self.assertIn("model-result-", script)
        self.assertNotIn("trtexec", script)
        self.assertIn("%Y%m%dT%H%M%S+0800", script)
        self.assertNotIn("curl", script)

    def test_report_dashboard_checks_confirmation_and_integrity(self):
        script = read_script("check_report_dashboard.ps1")

        self.assertIn("report.generate", script)
        self.assertIn("AWAITING_CONFIRMATION", script)
        self.assertIn("Cancelled report: HTTP", script)
        self.assertIn("X-EdgeSentinel-Report-SHA256", script)
        self.assertIn("Duplicate confirmation", script)
        self.assertIn(
            "[int]$ReportResult.event_count -lt 0",
            script,
        )
        self.assertNotIn(
            "[int]$ReportResult.event_count -lt 1",
            script,
        )
        self.assertIn(
            "Agent Report Dashboard smoke test passed.",
            script,
        )

    def test_event_acknowledgement_dashboard_checks_safe_transition(self):
        script = read_script(
            "check_event_acknowledgement_dashboard.ps1"
        )

        self.assertIn("event.acknowledge", script)
        self.assertIn("AWAITING_CONFIRMATION", script)
        self.assertIn("Status after cancellation", script)
        self.assertIn("ACKNOWLEDGED", script)
        self.assertIn("Evidence retained", script)
        self.assertIn("Duplicate confirmation", script)
        self.assertIn("[switch]$AssetsOnly", script)
        self.assertIn(
            "/dashboard/assets/dashboard.js",
            script,
        )
        self.assertIn(
            "/dashboard/assets/dashboard.css",
            script,
        )
        self.assertNotIn(
            "$BaseUrl/dashboard/dashboard.js",
            script,
        )
        self.assertIn(
            "Event Acknowledgement Dashboard smoke test passed.",
            script,
        )

    def test_system_health_agent_checks_read_only_metrics(self):
        script = read_script("check_system_health_agent.ps1")

        self.assertIn("system.get_health", script)
        self.assertIn("riskLevel", script)
        self.assertIn("requiresConfirmation", script)
        self.assertIn("/api/v1/system/status", script)
        self.assertIn("MemoryDifference", script)
        self.assertIn("Read only", script)
        self.assertIn('id="system-health-prompt"', script)
        self.assertIn(
            "System Health Agent smoke test passed.",
            script,
        )

    def test_model_info_agent_checks_integrity_without_paths(self):
        script = read_script("check_model_info_agent.ps1")

        self.assertIn("vision.get_model_info", script)
        self.assertIn("/api/v1/vision/model", script)
        self.assertIn("MATCH", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn("unknown model fields", script)
        self.assertIn('id="model-info-prompt"', script)
        self.assertIn(
            "Vision Model Agent smoke test passed.",
            script,
        )

    def test_vision_performance_agent_checks_fixed_targets(self):
        script = read_script(
            "check_vision_performance_agent.ps1"
        )

        self.assertIn("vision.get_performance", script)
        self.assertIn("/api/v1/vision/performance", script)
        self.assertIn("MEETS_TARGET", script)
        self.assertIn("processing_fps", script)
        self.assertIn("pipeline_latency_ms.p95", script)
        self.assertIn('id="vision-performance-prompt"', script)
        self.assertIn(
            "Vision Performance Agent smoke test passed.",
            script,
        )

    def test_runtime_benchmark_agent_checks_safe_report(self):
        script = read_script(
            "check_runtime_benchmark_agent.ps1"
        )

        self.assertIn(
            "system.get_runtime_benchmark",
            script,
        )
        self.assertIn("/api/v1/system/benchmark", script)
        self.assertIn("report_sha256", script)
        self.assertIn("samples_included", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn('id="runtime-benchmark-prompt"', script)
        self.assertIn(
            "Runtime Benchmark Agent smoke test passed.",
            script,
        )

    def test_storage_usage_agent_checks_bounded_read_only_scan(self):
        script = read_script(
            "check_storage_usage_agent.ps1"
        )

        self.assertIn("system.get_storage_usage", script)
        self.assertIn("/api/v1/system/storage", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn("skipped_symlinks", script)
        self.assertIn("truncated", script)
        self.assertIn('id="storage-usage-prompt"', script)
        self.assertIn(
            "Storage Usage Agent smoke test passed.",
            script,
        )

    def test_retention_preview_agent_never_deletes(self):
        script = read_script(
            "check_retention_preview_agent.ps1"
        )

        self.assertIn(
            "system.preview_data_retention",
            script,
        )
        self.assertIn(
            "/api/v1/system/retention-preview",
            script,
        )
        self.assertIn("PREVIEW_ONLY", script)
        self.assertIn("delete_performed", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn("data/evidence", script)
        self.assertIn(
            'id="retention-preview-prompt"',
            script,
        )
        self.assertIn(
            "Data Retention Preview smoke test passed.",
            script,
        )

    def test_retention_cleanup_dashboard_defaults_to_cancel(self):
        script = read_script(
            "check_retention_cleanup_dashboard.ps1"
        )

        self.assertIn(
            "system.cleanup_retained_data",
            script,
        )
        self.assertIn("riskLevel -ne \"L2\"", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn("ExpectedStatus 422", script)
        self.assertIn("/cancel", script)
        self.assertIn("Cleanup tool calls", script)
        self.assertIn("Delete performed", script)
        self.assertIn(
            'id="retention-cleanup-prompt"',
            script,
        )
        self.assertIn(
            "Retention Cleanup Dashboard smoke test passed.",
            script,
        )

    def test_retention_cleanup_history_is_read_only_and_path_free(self):
        script = read_script(
            "check_retention_cleanup_history_agent.ps1"
        )

        self.assertIn(
            "system.get_retention_cleanup_history",
            script,
        )
        self.assertIn(
            "/api/v1/system/retention-cleanup-history",
            script,
        )
        self.assertIn("paths_included", script)
        self.assertIn("Cleanup tool calls", script)
        self.assertIn("Candidate files unchanged", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            'id="retention-cleanup-history-prompt"',
            script,
        )
        self.assertIn(
            "Retention Cleanup History smoke test passed.",
            script,
        )

    def test_evidence_integrity_agent_is_read_only_and_path_free(self):
        script = read_script(
            "check_evidence_integrity_agent.ps1"
        )

        self.assertIn("evidence.verify_recent", script)
        self.assertIn(
            "/api/v1/events/evidence-integrity",
            script,
        )
        self.assertIn("jpeg_signature_checked", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn("Write tool calls", script)
        self.assertIn(
            'id="evidence-integrity-prompt"',
            script,
        )
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Evidence Integrity Agent smoke test passed.",
            script,
        )

    def test_exact_event_evidence_rehashes_downloaded_jpeg(self):
        script = read_script(
            "check_event_evidence_agent.ps1"
        )

        self.assertIn("evidence.verify_event", script)
        self.assertIn(
            "/evidence-integrity",
            script,
        )
        self.assertIn("Get-Sha256", script)
        self.assertIn("Downloaded SHA-256 match", script)
        self.assertIn("absolute_paths_included", script)
        self.assertIn("Event disposition unchanged", script)
        self.assertIn(
            'id="event-evidence-integrity"',
            script,
        )
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Exact Event Evidence smoke test passed.",
            script,
        )

    def test_event_disposition_filter_is_read_only(self):
        script = read_script(
            "check_event_disposition_filter_agent.ps1"
        )

        self.assertIn("status=OPEN", script)
        self.assertIn("ACKNOWLEDGED", script)
        self.assertIn("ExpectedStatus 422", script)
        self.assertIn("event.query", script)
        self.assertIn("event.summarize", script)
        self.assertIn("Write tool calls", script)
        self.assertIn('id="event-status-filter"', script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Disposition Filter smoke test passed.",
            script,
        )

    def test_event_severity_filter_is_read_only(self):
        script = read_script(
            "check_event_severity_filter_agent.ps1"
        )

        self.assertIn("severity=UNKNOWN", script)
        self.assertIn("status=OPEN&severity=INFO", script)
        self.assertIn("ExpectedStatus 422", script)
        self.assertIn("event.query", script)
        self.assertIn("event.summarize", script)
        self.assertIn("Write tool calls", script)
        self.assertIn('id="event-severity-filter"', script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Severity Filter smoke test passed.",
            script,
        )

    def test_event_cursor_pagination_is_read_only(self):
        script = read_script(
            "check_event_cursor_pagination_agent.ps1"
        )

        self.assertIn("next_cursor", script)
        self.assertIn("Tampered cursor rejected", script)
        self.assertIn("Changed filters rejected", script)
        self.assertIn("Assert-NoOverlap", script)
        self.assertIn("Write tool calls", script)
        self.assertIn('id="event-load-more"', script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Cursor Pagination smoke test passed.",
            script,
        )

    def test_event_trend_is_read_only(self):
        script = read_script("check_event_trend_agent.ps1")

        self.assertIn("bucket_minutes=20", script)
        self.assertIn("bucket_minutes=60", script)
        self.assertIn("Assert-Trend", script)
        self.assertIn("Peak bucket count", script)
        self.assertIn("Write tool calls", script)
        self.assertIn('id="event-trend"', script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Trend smoke test passed.",
            script,
        )

    def test_event_period_comparison_is_read_only(self):
        script = read_script(
            "check_event_period_comparison_agent.ps1"
        )

        self.assertIn("compare_previous=maybe", script)
        self.assertIn("compare_previous=true", script)
        self.assertIn("Assert-Comparison", script)
        self.assertIn("Previous window minutes", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Period Comparison smoke test passed.",
            script,
        )

    def test_event_change_contributors_are_read_only(self):
        script = read_script(
            "check_event_change_contributors_agent.ps1"
        )

        self.assertIn("Assert-Contributors", script)
        self.assertIn("largest_event_type_change", script)
        self.assertIn(
            "const contributorText = largestChange",
            script,
        )
        self.assertIn("Contributor groups bounded", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Change Contributors smoke test passed.",
            script,
        )

    def test_event_change_assessment_is_read_only(self):
        script = read_script(
            "check_event_change_assessment_agent.ps1"
        )

        self.assertIn("Assert-Assessment", script)
        self.assertIn("change_threshold_percent=0", script)
        self.assertIn("Threshold exceeded", script)
        self.assertIn(
            "changeAssessment\\.threshold_exceeded",
            script,
        )
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Change Assessment smoke test passed.",
            script,
        )

    def test_event_group_change_signals_are_read_only(self):
        script = read_script(
            "check_event_group_change_signals_agent.ps1"
        )

        self.assertIn("Assert-GroupSignals", script)
        self.assertIn("significant_contributors", script)
        self.assertIn("All signals satisfy thresholds", script)
        self.assertIn("Signals retained in contributors", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Group Change Signals smoke test passed.",
            script,
        )

    def test_event_change_cancellation_is_read_only(self):
        script = read_script(
            "check_event_change_cancellation_agent.ps1"
        )

        self.assertIn("Assert-StructuralChange", script)
        self.assertIn("Gross absolute change", script)
        self.assertIn("Offsetting events", script)
        self.assertIn("Truncation safety verified", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Change Cancellation smoke test passed.",
            script,
        )

    def test_event_aligned_baseline_is_read_only(self):
        script = read_script(
            "check_event_aligned_baseline_agent.ps1"
        )

        self.assertIn("Assert-AlignedBaseline", script)
        self.assertIn("comparison_offset_minutes=59", script)
        self.assertIn("comparison.current_total", script)
        self.assertIn("comparison.previous_total", script)
        self.assertNotIn("current_total_events", script)
        self.assertNotIn("previous_total_events", script)
        self.assertIn(
            "[string]$AgentPrevious.since_timestamp",
            script,
        )
        self.assertIn(
            "[string]$AgentPrevious.until_timestamp",
            script,
        )
        self.assertIn("Non-overlapping windows", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Aligned Baseline smoke test passed.",
            script,
        )

    def test_event_reference_baselines_are_read_only(self):
        script = read_script(
            "check_event_reference_baselines_agent.ps1"
        )

        self.assertIn("Assert-ReferenceBaselines", script)
        self.assertIn("SAME_TIME_YESTERDAY", script)
        self.assertIn("SAME_TIME_LAST_WEEK", script)
        self.assertIn("Bounded baseline count", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Reference Baselines smoke test passed.",
            script,
        )

    def test_event_reference_assessment_is_read_only(self):
        script = read_script(
            "check_event_reference_assessment_agent.ps1"
        )

        self.assertIn("Assert-ReferenceAssessment", script)
        self.assertIn("NO_HISTORICAL_ACTIVITY", script)
        self.assertIn("NEW_ACTIVITY", script)
        self.assertIn("ABOVE_HISTORICAL_AVERAGE", script)
        self.assertIn("BELOW_HISTORICAL_AVERAGE", script)
        self.assertIn("MATCHES_HISTORICAL_AVERAGE", script)
        self.assertIn("Zero-baseline division safe", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Reference Assessment smoke test passed.",
            script,
        )

    def test_event_reference_consistency_is_read_only(self):
        script = read_script(
            "check_event_reference_consistency_agent.ps1"
        )

        self.assertIn("Assert-ReferenceConsistency", script)
        self.assertIn("NO_HISTORICAL_ACTIVITY", script)
        self.assertIn("STABLE", script)
        self.assertIn("VARIABLE", script)
        self.assertIn("Maximum stable spread percent", script)
        self.assertIn("Reliable for average", script)
        self.assertIn("Bounded baseline count", script)
        self.assertIn("Write tool calls", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn(
            "Event Reference Consistency smoke test passed.",
            script,
        )

    def test_agent_model_switch_requires_confirmation_and_restores_mode(self):
        script = read_script(
            "check_agent_model_switch_dashboard.ps1"
        )

        self.assertIn("SWITCH_AGENT_MODEL", script)
        self.assertIn("Invalid confirmation: HTTP 422", script)
        self.assertIn("vision.get_people_count", script)
        self.assertIn("finally", script)
        self.assertIn(
            "Agent Model Switch smoke test passed.",
            script,
        )

    def test_weather_agent_uses_bounded_read_only_tool(self):
        script = read_script("check_weather_agent.ps1")

        self.assertIn("weather.get_current", script)
        self.assertIn("open-meteo", script)
        self.assertIn("External request", script)
        self.assertIn("Read only", script)
        self.assertNotIn("CONFIRM_TOOL_EXECUTION", script)
        self.assertIn("Weather Agent smoke test passed.", script)

    def test_mcp_catalog_dashboard_exposes_only_read_only_tools(self):
        script = read_script("check_mcp_catalog_dashboard.ps1")

        self.assertIn("/api/v1/harness/tools", script)
        self.assertIn("readOnlyHint", script)
        self.assertIn("riskLevel", script)
        self.assertIn("requiresConfirmation", script)
        self.assertIn("weather.get_current", script)
        self.assertIn("openWorldHint", script)
        self.assertIn('id="event-collapse"', script)
        self.assertIn(
            "MCP Catalog Dashboard smoke test passed.",
            script,
        )

    def test_agent_workbench_uses_bounded_sanitized_trace(self):
        script = read_script(
            "check_agent_workbench_dashboard.ps1"
        )

        self.assertIn("/trace?limit=100", script)
        self.assertIn("MODEL_DECISION", script)
        self.assertIn("TOOL_RESULT", script)
        self.assertIn("TASK_RESULT", script)
        self.assertIn("model_content_exposed", script)
        self.assertIn("raw_trace_exposed", script)
        self.assertIn("Get-HttpStatusCode", script)
        self.assertIn("InnerException", script)
        self.assertIn('id="agent-workbench"', script)
        self.assertIn(
            "Agent Harness Workbench smoke test passed.",
            script,
        )

    def test_agent_skills_are_versioned_pinned_and_policy_bounded(self):
        script = read_script(
            "check_agent_skill_dashboard.ps1"
        )

        self.assertIn("/api/v1/harness/skills", script)
        self.assertIn(
            "vision.investigate_removed_item",
            script,
        )
        self.assertIn("instructions_sha256", script)
        self.assertIn("SKILL_SELECTED", script)
        self.assertIn("allowed_risks", script)
        self.assertIn('id="agent-run-skill"', script)
        self.assertIn(
            "Agent Skills smoke test passed.",
            script,
        )

    def test_agent_hooks_are_bounded_audited_and_visible(self):
        script = read_script(
            "check_agent_hooks_dashboard.ps1"
        )

        self.assertIn("/api/v1/harness/hooks", script)
        self.assertIn("before_model", script)
        self.assertIn("after_model", script)
        self.assertIn("before_tool", script)
        self.assertIn("after_tool", script)
        self.assertIn("on_checkpoint", script)
        self.assertIn("on_task_complete", script)
        self.assertIn("FAIL_CLOSED", script)
        self.assertIn("HOOK_RESULT", script)
        self.assertIn("Get-HttpStatusCode", script)
        self.assertIn("/api/v1/harness/hooks/audit", script)
        self.assertIn(
            "Agent Hooks smoke test passed.",
            script,
        )

    def test_agent_session_memory_is_bounded_private_and_clearable(self):
        script = read_script(
            "check_agent_session_memory_dashboard.ps1"
        )

        self.assertIn("session_id", script)
        self.assertIn("max_turns", script)
        self.assertIn("retention_days", script)
        self.assertIn("raw_tool_results_stored", script)
        self.assertIn("evidence_paths_stored", script)
        self.assertIn("SESSION_MEMORY", script)
        self.assertIn("Terminal checkpoint history", script)
        self.assertIn("CLEAR_AGENT_SESSION", script)
        self.assertIn("Invalid clear phrase: HTTP 422", script)
        self.assertIn('id="agent-session-memory"', script)
        self.assertIn(
            "Agent Session Memory smoke test passed.",
            script,
        )

    def test_agent_job_stream_is_bounded_idempotent_and_cancelable(self):
        script = read_script(
            "check_agent_job_stream_dashboard.ps1"
        )

        self.assertIn("/api/v1/agent/jobs", script)
        self.assertIn("/events?after=-1", script)
        self.assertIn("Idempotency-Key", script)
        self.assertIn("Changed request conflict: HTTP 409", script)
        self.assertIn("Queued cancellation: CANCELLED", script)
        self.assertIn("Request body persisted", script)
        self.assertIn('id="agent-job-cancel"', script)
        self.assertIn(
            "Agent Job Stream smoke test passed.",
            script,
        )

    def test_agent_evaluation_is_versioned_isolated_and_visible(self):
        runner = read_script("run_agent_evaluation_test.sh")
        dashboard = read_script(
            "check_agent_evaluation_dashboard.ps1"
        )

        self.assertIn("apps.run_agent_evaluation", runner)
        self.assertIn("agent-routing-v1.json", runner)
        self.assertIn("data/evaluations", runner)
        self.assertIn(
            "/api/v1/harness/evaluations/latest", dashboard
        )
        self.assertIn("offline-deterministic", dashboard)
        self.assertIn("external_requests", dashboard)
        self.assertIn("device_tools_executed", dashboard)
        self.assertIn("unexpected_policy_violations", dashboard)
        self.assertIn('id=\"agent-evaluation-baseline\"', dashboard)
        self.assertIn(
            "Agent Evaluation Dashboard smoke test passed.",
            dashboard,
        )

    def test_agent_execution_control_is_bounded_and_cooperative(self):
        local = read_script(
            "run_agent_execution_control_test.sh"
        )
        dashboard = read_script(
            "check_agent_execution_budget_dashboard.ps1"
        )

        self.assertIn("test_execution_control", local)
        self.assertIn("test_agent_execution_control", local)
        self.assertIn("test_task_queue", local)
        self.assertIn("Running cancellation: cooperative", local)
        self.assertIn("Force termination used: False", local)
        self.assertIn("EXECUTION_STOPPED", local)
        self.assertIn("max_wall_seconds", dashboard)
        self.assertIn("max_model_calls", dashboard)
        self.assertIn("max_tool_calls", dashboard)
        self.assertIn("max_external_tool_calls", dashboard)
        self.assertIn('id=\"agent-run-budget\"', dashboard)
        self.assertIn(
            "Agent Execution Budget Dashboard smoke test passed.",
            dashboard,
        )

    def test_agent_token_governance_is_bounded_and_observable(self):
        local = read_script(
            "run_agent_token_governance_test.sh"
        )
        dashboard = read_script(
            "check_agent_token_governance_dashboard.ps1"
        )

        self.assertIn("test_model_gateway", local)
        self.assertIn("MODEL_TOKEN_BUDGET_EXCEEDED", local)
        self.assertIn("MODEL_COST_BUDGET_EXCEEDED", local)
        self.assertIn("never fabricated", local)
        self.assertIn("max_total_tokens", dashboard)
        self.assertIn("model_usage_reports", dashboard)
        self.assertIn("MODEL_USAGE", dashboard)
        self.assertIn("estimated_cost_usd", dashboard)
        self.assertIn("model_content_exposed", dashboard)
        self.assertIn(
            "Agent Token Governance Dashboard smoke test passed.",
            dashboard,
        )

    def test_agent_tool_routing_is_bounded_and_observable(self):
        local = read_script("run_agent_tool_routing_test.sh")
        dashboard = read_script(
            "check_agent_tool_routing_dashboard.ps1"
        )

        self.assertIn("test_tool_router", local)
        self.assertIn("test_agent_tool_routing", local)
        self.assertIn("Maximum visible tools: 6", local)
        self.assertIn("Catalog fallback: disabled", local)
        self.assertIn("TOOL_ROUTE_NOT_ALLOWED", local)
        self.assertIn("MaximumPromptTokens", dashboard)
        self.assertIn("NO_MATCH", dashboard)
        self.assertIn("vision.get_people_count", dashboard)
        self.assertIn("schema_reduction_percent", dashboard)
        self.assertIn("TOOL_ROUTE_DENIED", dashboard)
        self.assertIn("model_content_exposed", dashboard)
        self.assertIn(
            "Agent Tool Routing Dashboard smoke test passed.",
            dashboard,
        )

    def test_agent_model_resilience_is_bounded_and_observable(self):
        local = read_script(
            "run_agent_model_resilience_test.sh"
        )
        dashboard = read_script(
            "check_agent_model_resilience_dashboard.ps1"
        )

        self.assertIn("test_model_runtime", local)
        self.assertIn("test_agent_model_resilience", local)
        self.assertIn("Retry maximum attempts: 2", local)
        self.assertIn("Half-open probes: one", local)
        self.assertIn("Tool calls replayed by retry: False", local)
        self.assertIn("retry_max_attempts", dashboard)
        self.assertIn("failure_threshold", dashboard)
        self.assertIn("offline_fallback_enabled", dashboard)
        self.assertIn("MODEL_RESILIENCE", dashboard)
        self.assertIn("model_content_exposed", dashboard)
        self.assertIn(
            "Agent Model Resilience Dashboard smoke test passed.",
            dashboard,
        )


if __name__ == "__main__":
    unittest.main()
