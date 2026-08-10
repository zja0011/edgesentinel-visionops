"""Factory for the first allowlisted EdgeSentinel Harness tools."""

import os

from packages.api.evidence_service import EvidenceService
from packages.api.event_service import EventQueryService
from packages.evidence.integrity import EvidenceIntegrityService
from packages.events.summary import EventSummaryService
from packages.harness.audit import JsonlToolAuditRecorder
from packages.harness.benchmark_tools import RuntimeBenchmarkTools
from packages.harness.camera_tools import (
    CameraRestartTools,
    CameraSnapshotTools,
    CameraStatusTools,
)
from packages.harness.disaster_recovery import DisasterRecoveryStore
from packages.harness.event_tools import EventDispositionTools
from packages.harness.event_detail_tools import EventDetailTools
from packages.harness.inventory_tools import InventoryHistoryTools
from packages.harness.long_term_memory import LongTermMemoryStore
from packages.harness.model_tools import VisionModelTools
from packages.harness.policy import PolicyEngine, PolicyRule
from packages.harness.report_tools import DailyEventReportTools
from packages.harness.retention_tools import (
    RetentionCleanupHistoryTools,
    RetentionCleanupTools,
    RetentionPreviewTools,
)
from packages.harness.registry import ToolDefinition, ToolRegistry
from packages.harness.system_tools import SystemHealthTools
from packages.harness.storage_tools import StorageUsageTools
from packages.harness.vision_tools import VisionStateTools
from packages.harness.weather_tools import CurrentWeatherTools


EVENT_QUERY_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 20,
        },
        "event_type": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "object_class": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "description": (
                "Exact English detector class label stored in the "
                "database, for example bottle, cup, laptop, person, "
                "or cell phone. System lifecycle events use the "
                "pseudo-class camera. Never translate the class label."
            ),
        },
        "camera_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1440,
            "description": (
                "Optional Beijing-time lookback window in minutes. "
                "Omit it to query all persisted history."
            ),
        },
        "status": {
            "type": "string",
            "enum": ["OPEN", "ACKNOWLEDGED"],
            "description": (
                "Optional exact event disposition filter. OPEN means "
                "not yet acknowledged; ACKNOWLEDGED means handled."
            ),
        },
        "severity": {
            "type": "string",
            "enum": ["INFO", "MEDIUM", "HIGH", "CRITICAL"],
            "description": (
                "Optional exact event severity filter."
            ),
        },
        "cursor": {
            "type": "string",
            "minLength": 1,
            "maxLength": 2048,
            "description": (
                "Opaque signed cursor returned by the previous "
                "event.query page. Reuse the same filters."
            ),
        },
    },
    "additionalProperties": False,
}

WEATHER_CURRENT_SCHEMA = {
    "type": "object",
    "properties": {
        "location": {
            "type": "string",
            "minLength": 2,
            "maxLength": 80,
            "description": (
                "City or place name for the current weather lookup, "
                "for example Shenzhen, Beijing, or 上海. If the user "
                "did not state a location, omit this only when a "
                "server default is configured; otherwise ask the "
                "user which city they mean."
            ),
        },
    },
    "additionalProperties": False,
}

MEMORY_SEARCH_SCHEMA = {
    "type": "object",
    "properties": {
        "query": {
            "type": "string",
            "maxLength": 100,
            "description": (
                "Optional bounded text matched against confirmed "
                "memory keys and values. Omit it to list newest "
                "confirmed records."
            ),
        },
        "kind": {
            "type": "string",
            "enum": ["FACT", "PREFERENCE"],
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 20,
        },
    },
    "additionalProperties": False,
}

MEMORY_REMEMBER_SCHEMA = {
    "type": "object",
    "properties": {
        "kind": {
            "type": "string",
            "enum": ["FACT", "PREFERENCE"],
        },
        "key": {
            "type": "string",
            "minLength": 1,
            "maxLength": 80,
        },
        "value": {
            "type": "string",
            "minLength": 1,
            "maxLength": 500,
        },
    },
    "required": ["kind", "key", "value"],
    "additionalProperties": False,
}

MEMORY_FORGET_SCHEMA = {
    "type": "object",
    "properties": {
        "memory_id": {
            "type": "string",
            "minLength": 36,
            "maxLength": 36,
            "description": (
                "Exact immutable mem_ identifier returned by "
                "memory.search."
            ),
        },
    },
    "required": ["memory_id"],
    "additionalProperties": False,
}

EVENT_SUMMARY_SCHEMA = {
    "type": "object",
    "properties": {
        "minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1440,
            "default": 10,
            "description": (
                "Beijing-time lookback window in minutes."
            ),
        },
        "event_type": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "object_class": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "camera_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "recent_limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10,
            "default": 5,
        },
        "bucket_minutes": {
            "type": "integer",
            "enum": [15, 30, 60],
            "description": (
                "Optional Beijing-time trend bucket size. Omit it "
                "when no timeline is required."
            ),
        },
        "compare_previous": {
            "type": "boolean",
            "default": False,
            "description": (
                "Compare the selected window total with the "
                "immediately preceding equal-length window."
            ),
        },
        "comparison_offset_minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 10080,
            "description": (
                "Optional non-overlapping offset to an equal-length "
                "comparison window. Use 1440 for the same time "
                "yesterday or 10080 for the same time last week."
            ),
        },
        "include_reference_baselines": {
            "type": "boolean",
            "default": False,
            "description": (
                "Include a fixed bounded aggregate profile for the "
                "same time yesterday and the same time last week. "
                "No historical event details are returned."
            ),
        },
        "change_threshold_percent": {
            "type": "integer",
            "minimum": 1,
            "maximum": 500,
            "default": 25,
            "description": (
                "Minimum absolute percent change for the optional "
                "equal-period change assessment."
            ),
        },
        "change_threshold_events": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1000,
            "default": 10,
            "description": (
                "Minimum absolute event-count change for the "
                "optional equal-period change assessment."
            ),
        },
        "status": {
            "type": "string",
            "enum": ["OPEN", "ACKNOWLEDGED"],
            "description": (
                "Optional exact event disposition filter."
            ),
        },
        "severity": {
            "type": "string",
            "enum": ["INFO", "MEDIUM", "HIGH", "CRITICAL"],
            "description": (
                "Optional exact event severity filter."
            ),
        },
    },
    "additionalProperties": False,
}

EVIDENCE_VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 100,
            "default": 50,
            "description": (
                "Maximum number of newest events whose evidence "
                "references will be checked."
            ),
        },
        "minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1440,
            "description": (
                "Optional Beijing-time lookback window in minutes."
            ),
        },
    },
    "additionalProperties": False,
}

NO_ARGUMENTS_SCHEMA = {
    "type": "object",
    "properties": {},
    "additionalProperties": False,
}

RETENTION_CLEANUP_SCHEMA = {
    "type": "object",
    "properties": {
        "plan_id": {
            "type": "string",
            "minLength": 36,
            "maxLength": 36,
            "description": (
                "Exact ret_ plan identifier returned by the bounded "
                "retention preview."
            ),
        },
        "candidate_paths": {
            "type": "array",
            "minItems": 1,
            "maxItems": 100,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 512,
            },
            "description": (
                "Exact relative candidate paths returned by the "
                "same retention preview. No other paths are accepted."
            ),
        },
    },
    "required": ["plan_id", "candidate_paths"],
    "additionalProperties": False,
}

RETENTION_HISTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 10,
            "description": (
                "Maximum number of newest completed cleanup audit "
                "summaries to return."
            ),
        },
    },
    "additionalProperties": False,
}

ZONE_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "zone_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "description": (
                "Optional exact configured zone ID, for example "
                "left_zone or right_zone. Omit it to return every "
                "configured zone."
            ),
        },
    },
    "additionalProperties": False,
}

COUNT_OBJECTS_SCHEMA = {
    "type": "object",
    "properties": {
        "classes": {
            "type": "array",
            "minItems": 1,
            "maxItems": 20,
            "uniqueItems": True,
            "items": {
                "type": "string",
                "minLength": 1,
                "maxLength": 64,
            },
            "description": (
                "One to twenty exact English detector class labels "
                "to count in the latest frame."
            ),
        },
        "zone_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "description": (
                "Optional exact configured zone ID. When supplied, "
                "only detections currently assigned to that zone "
                "are counted."
            ),
        },
        "minimum_confidence": {
            "type": "number",
            "minimum": 0.0,
            "maximum": 1.0,
            "default": 0.0,
        },
    },
    "required": ["classes"],
    "additionalProperties": False,
}

TRACK_HISTORY_SCHEMA = {
    "type": "object",
    "properties": {
        "track_id": {
            "type": "integer",
            "minimum": 1,
            "maximum": 2147483647,
        },
        "object_class": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 10,
        },
    },
    "additionalProperties": False,
}

INVENTORY_STATE_SCHEMA = {
    "type": "object",
    "properties": {
        "object_class": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "description": (
                "Optional exact configured English detector class "
                "label, for example bottle, cup, laptop, or backpack. "
                "Omit it to return every configured inventory class, "
                "including classes whose stable count is zero."
            ),
        },
    },
    "additionalProperties": False,
}

INVENTORY_COMPARE_SCHEMA = {
    "type": "object",
    "properties": {
        "expected_counts": {
            "type": "object",
            "minProperties": 1,
            "maxProperties": 20,
            "additionalProperties": {
                "type": "integer",
                "minimum": 0,
                "maximum": 100,
            },
            "description": (
                "Expected stable counts keyed by exact configured "
                "English detector class labels. Only these classes "
                "are compared."
            ),
        },
    },
    "required": ["expected_counts"],
    "additionalProperties": False,
}

REMOVED_ITEMS_SCHEMA = {
    "type": "object",
    "properties": {
        "minutes": {
            "type": "integer",
            "minimum": 1,
            "maximum": 1440,
            "default": 10,
            "description": (
                "Look back this many minutes from current Beijing "
                "time. The maximum window is 24 hours."
            ),
        },
        "object_class": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
            "description": (
                "Optional exact English detector class label, for "
                "example bottle, cup, laptop, or backpack."
            ),
        },
        "camera_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 50,
            "default": 20,
        },
    },
    "additionalProperties": False,
}

REPORT_GENERATE_SCHEMA = {
    "type": "object",
    "properties": {
        "date": {
            "type": "string",
            "minLength": 10,
            "maxLength": 10,
            "description": (
                "Optional Beijing calendar date in YYYY-MM-DD format. "
                "Omit it to generate today's report."
            ),
        },
        "camera_id": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
        "object_class": {
            "type": "string",
            "minLength": 1,
            "maxLength": 64,
        },
    },
    "additionalProperties": False,
}

EVENT_ID_SCHEMA = {
    "type": "object",
    "properties": {
        "event_id": {
            "type": "string",
            "minLength": 36,
            "maxLength": 36,
            "description": (
                "Exact immutable EdgeSentinel event ID, formatted as "
                "evt_ followed by 32 hexadecimal characters."
            ),
        },
    },
    "required": ["event_id"],
    "additionalProperties": False,
}

RECOVERY_STATUS_SCHEMA = {
    "type": "object",
    "properties": {
        "limit": {
            "type": "integer",
            "minimum": 1,
            "maximum": 20,
            "default": 10,
        },
    },
    "additionalProperties": False,
}

RECOVERY_PREVIEW_SCHEMA = {
    "type": "object",
    "properties": {
        "backup_id": {
            "type": "string",
            "minLength": 35,
            "maxLength": 35,
            "description": (
                "Exact local disaster-recovery backup identifier, "
                "formatted as dr_ followed by 32 hexadecimal characters."
            ),
        },
    },
    "required": ["backup_id"],
    "additionalProperties": False,
}

DEFAULT_POLICY_RULES = {
    "recovery.create_backup": PolicyRule(
        risk="L1",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "recovery.get_status": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "recovery.preview_restore": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "evidence.verify_event": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "evidence.verify_recent": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "event.query": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "event.summarize": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "event.get_detail": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "inventory.get_current_state": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "inventory.compare_state": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "inventory.get_removed_items": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "memory.search": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "memory.remember": PolicyRule(
        risk="L1",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "memory.forget": PolicyRule(
        risk="L1",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "vision.get_current_objects": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "vision.count_objects": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "vision.get_track_history": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "vision.get_people_count": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "vision.get_zone_status": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "vision.get_model_info": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "vision.get_performance": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "camera.capture_snapshot": PolicyRule(
        risk="L1",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "camera.get_status": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "camera.restart": PolicyRule(
        risk="L2",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "report.generate": PolicyRule(
        risk="L1",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "event.acknowledge": PolicyRule(
        risk="L1",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "system.get_health": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "system.get_runtime_benchmark": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "system.get_retention_cleanup_history": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "system.preview_data_retention": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "system.cleanup_retained_data": PolicyRule(
        risk="L2",
        enabled=True,
        auto_execute=False,
        require_confirmation=True,
    ),
    "system.get_storage_usage": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
    "weather.get_current": PolicyRule(
        risk="L0",
        enabled=True,
        auto_execute=True,
    ),
}


def build_default_registry(
    project_dir,
    database_path,
    audit_path=None,
    state_path=None,
    state_max_age_seconds=5.0,
    camera_state_path=None,
    camera_state_max_age_seconds=10.0,
    camera_control_path=None,
    camera_restart_timeout_seconds=90.0,
    model_manifest_path=None,
    model_root="/jetson-inference/data/networks",
    weather_default_location=None,
    weather_opener=None,
    long_term_memory_store=None,
):
    project_dir = os.path.abspath(project_dir)
    audit_path = audit_path or os.path.join(
        project_dir,
        "data",
        "harness",
        "tool-calls.jsonl",
    )
    event_service = EventQueryService(database_path)
    event_summary_service = EventSummaryService(database_path)
    evidence_integrity_service = EvidenceIntegrityService(
        project_dir,
        database_path,
    )
    evidence_service = EvidenceService(project_dir)
    state_path = state_path or os.path.join(
        project_dir,
        "data",
        "state",
        "current-vision.json",
    )
    vision_tools = VisionStateTools(
        state_path,
        max_age_seconds=state_max_age_seconds,
    )
    camera_tools = CameraSnapshotTools(
        project_dir,
        state_path=state_path,
        max_age_seconds=state_max_age_seconds,
    )
    camera_status_tools = CameraStatusTools(
        project_dir,
        supervisor_state_path=camera_state_path,
        max_state_age_seconds=camera_state_max_age_seconds,
    )
    camera_restart_tools = CameraRestartTools(
        project_dir,
        supervisor_state_path=camera_state_path,
        control_path=camera_control_path,
        max_state_age_seconds=camera_state_max_age_seconds,
        timeout_seconds=camera_restart_timeout_seconds,
    )
    report_tools = DailyEventReportTools(
        project_dir,
        database_path,
    )
    event_tools = EventDispositionTools(database_path)
    event_detail_tools = EventDetailTools(
        project_dir,
        database_path,
    )
    inventory_history_tools = InventoryHistoryTools(
        project_dir,
        database_path,
    )
    system_tools = SystemHealthTools(project_dir)
    benchmark_tools = RuntimeBenchmarkTools(project_dir)
    storage_tools = StorageUsageTools(project_dir)
    retention_tools = RetentionPreviewTools(project_dir)
    retention_cleanup_tools = RetentionCleanupTools(project_dir)
    retention_history_tools = RetentionCleanupHistoryTools(
        project_dir
    )
    model_tools = VisionModelTools(
        model_manifest_path
        or os.path.join(
            project_dir,
            "data",
            "state",
            "current-model.json",
        ),
        model_root,
    )
    weather_tools = CurrentWeatherTools(
        default_location=weather_default_location,
        opener=weather_opener,
    )
    memory_store = long_term_memory_store or LongTermMemoryStore(
        os.path.join(
            project_dir,
            "data",
            "harness",
            "long-term-memory",
        ),
        max_records=100,
    )
    recovery_store = DisasterRecoveryStore(project_dir)
    registry = ToolRegistry(
        JsonlToolAuditRecorder(audit_path),
        policy_engine=PolicyEngine(DEFAULT_POLICY_RULES),
    )

    def query_events(arguments):
        payload = event_service.list_events(
            limit=arguments.get("limit", 20),
            event_type=arguments.get("event_type"),
            object_class=arguments.get("object_class"),
            camera_id=arguments.get("camera_id"),
            minutes=arguments.get("minutes"),
            status=arguments.get("status"),
            severity=arguments.get("severity"),
            cursor=arguments.get("cursor"),
        )
        payload["events"] = [
            evidence_service.add_urls(event)
            for event in payload["events"]
        ]
        return payload

    registry.register(
        ToolDefinition(
            name="recovery.create_backup",
            description=(
                "Create one bounded consistent local disaster-recovery "
                "backup of zone configuration, SQLite events, evidence, "
                "reports, benchmarks, and confirmed long-term memory. "
                "Runtime state and all root-owned model, authentication, "
                "and TLS credentials are excluded. This L1 write requires "
                "explicit confirmation."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=recovery_store.create_backup,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="recovery.get_status",
            description=(
                "List bounded verified local disaster-recovery backup "
                "metadata and manifest hashes. Every returned backup has "
                "a valid manifest and payload inventory. No paths, file "
                "contents, or credentials are returned. This is read-only."
            ),
            input_schema=RECOVERY_STATUS_SCHEMA,
            handler=recovery_store.get_status,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="recovery.preview_restore",
            description=(
                "Verify one exact disaster-recovery manifest and every "
                "payload SHA-256, then produce a bounded restore plan "
                "without writing project data. Actual restore is not an "
                "online Agent capability and requires host maintenance "
                "mode. This tool is read-only."
            ),
            input_schema=RECOVERY_PREVIEW_SCHEMA,
            handler=recovery_store.preview_restore,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="camera.capture_snapshot",
            description=(
                "Archive the latest fresh annotated camera JPEG under "
                "the local evidence directory. This creates one file "
                "and requires explicit user confirmation."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=camera_tools.capture_snapshot,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="camera.get_status",
            description=(
                "Return the current bounded camera supervisor status, "
                "device availability, worker state, generation, "
                "restart count, and vision freshness. This is read-only "
                "and never restarts or reconfigures the camera."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=camera_status_tools.get_status,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="camera.restart",
            description=(
                "Perform one controlled restart of only the supervised "
                "camera inference worker. The API, container, and "
                "Jetson remain running. This disruptive L2 action "
                "requires explicit user confirmation."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=camera_restart_tools.restart,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="report.generate",
            description=(
                "Generate one deterministic local Markdown report for "
                "a Beijing calendar date from SQLite events. The file "
                "stays under data/reports and requires explicit user "
                "confirmation."
            ),
            input_schema=REPORT_GENERATE_SCHEMA,
            handler=report_tools.generate,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="evidence.verify_recent",
            description=(
                "Verify evidence referenced by a bounded set of "
                "recent events. Checks trusted location, regular-file "
                "type, JPEG extension, and JPEG start/end signatures. "
                "Returns only aggregate counts and bounded issue codes, "
                "never evidence paths. This is read-only."
            ),
            input_schema=EVIDENCE_VERIFY_SCHEMA,
            handler=evidence_integrity_service.verify_recent,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="evidence.verify_event",
            description=(
                "Verify all evidence references for one exact event. "
                "Returns per-kind status, bounded byte size, SHA-256, "
                "and safe HTTP URL for valid JPEG evidence without "
                "returning stored or absolute paths. This is read-only."
            ),
            input_schema=EVENT_ID_SCHEMA,
            handler=evidence_integrity_service.verify_event,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="event.acknowledge",
            description=(
                "Mark one exact existing event as acknowledged in the "
                "local SQLite database. This does not delete the event "
                "or evidence and requires explicit user confirmation."
            ),
            input_schema=EVENT_ID_SCHEMA,
            handler=event_tools.acknowledge,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="event.get_detail",
            description=(
                "Return one exact existing structured event by its "
                "immutable event_id, including disposition and bounded "
                "evidence links. This is read-only and never changes "
                "the event or evidence."
            ),
            input_schema=EVENT_ID_SCHEMA,
            handler=event_detail_tools.get_detail,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="event.query",
            description=(
                "Query recent structured vision events from the local "
                "read-only SQLite event database. object_class must "
                "use the exact English label such as bottle, or camera "
                "for camera lifecycle events. Results include the "
                "acknowledgement status. An optional bounded minutes "
                "lookback filters by Beijing time."
            ),
            input_schema=EVENT_QUERY_SCHEMA,
            handler=query_events,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="event.summarize",
            description=(
                "Summarize a bounded recent Beijing-time event "
                "window by event type, severity, object class, and "
                "zone, with at most ten recent event headers. An "
                "optional equal-period comparison includes bounded "
                "group change contributors, threshold signals, and "
                "structural cancellation metrics. This is read-only "
                "and excludes evidence and event details."
            ),
            input_schema=EVENT_SUMMARY_SCHEMA,
            handler=lambda arguments: event_summary_service.summarize(
                minutes=arguments.get("minutes", 10),
                event_type=arguments.get("event_type"),
                object_class=arguments.get("object_class"),
                camera_id=arguments.get("camera_id"),
                status=arguments.get("status"),
                severity=arguments.get("severity"),
                bucket_minutes=arguments.get("bucket_minutes"),
                compare_previous=arguments.get(
                    "compare_previous",
                    False,
                ),
                comparison_offset_minutes=arguments.get(
                    "comparison_offset_minutes"
                ),
                include_reference_baselines=arguments.get(
                    "include_reference_baselines",
                    False,
                ),
                change_threshold_percent=arguments.get(
                    "change_threshold_percent",
                    25,
                ),
                change_threshold_events=arguments.get(
                    "change_threshold_events",
                    10,
                ),
                recent_limit=arguments.get("recent_limit", 5),
            ),
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="inventory.compare_state",
            description=(
                "Compare current debounced stable inventory counts "
                "with user-provided expected counts for up to twenty "
                "exact configured classes. Return matching, missing, "
                "and extra counts without saving or changing a "
                "baseline. This is read-only."
            ),
            input_schema=INVENTORY_COMPARE_SCHEMA,
            handler=vision_tools.compare_inventory_state,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="inventory.get_current_state",
            description=(
                "Return the complete stable inventory state or one "
                "exact configured object class from the latest atomic "
                "vision state. Results include stable counts, visible "
                "counts, bounded track IDs, and freshness metadata. "
                "This is read-only and never changes inventory."
            ),
            input_schema=INVENTORY_STATE_SCHEMA,
            handler=vision_tools.get_inventory_state,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="inventory.get_removed_items",
            description=(
                "Return confirmed OBJECT_REMOVED inventory events "
                "from a bounded recent Beijing-time window, optionally "
                "filtered by exact object class and camera. Results "
                "include aggregate removed units and safe evidence "
                "URLs. This is read-only."
            ),
            input_schema=REMOVED_ITEMS_SCHEMA,
            handler=inventory_history_tools.get_removed_items,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory.search",
            description=(
                "Search or list bounded user-confirmed long-term "
                "facts and preferences. This is read-only and "
                "returns provenance and revisions; it never reads "
                "session transcripts, images, evidence, or raw tool "
                "results."
            ),
            input_schema=MEMORY_SEARCH_SCHEMA,
            handler=memory_store.search,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory.remember",
            description=(
                "Create or update one bounded long-term FACT or "
                "PREFERENCE from the user's explicit request. This "
                "persists local data and requires confirmation. "
                "Never store credentials, evidence paths, images, "
                "or raw tool results."
            ),
            input_schema=MEMORY_REMEMBER_SCHEMA,
            handler=memory_store.remember,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="memory.forget",
            description=(
                "Delete one exact confirmed long-term memory record "
                "by mem_ identifier. This changes persistent local "
                "data and requires explicit confirmation. Use "
                "memory.search first when the identifier is unknown."
            ),
            input_schema=MEMORY_FORGET_SCHEMA,
            handler=memory_store.forget,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="system.get_health",
            description=(
                "Return a deterministic read-only Jetson health "
                "summary for load, memory, project disk, temperature, "
                "and uptime. This never runs shell commands or changes "
                "the device."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=system_tools.get_health,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="system.get_retention_cleanup_history",
            description=(
                "Return bounded aggregate history from the local "
                "retention cleanup audit. Results include completion "
                "status, counts, bytes, failures, and timestamps but "
                "never candidate paths, deleted paths, or absolute "
                "paths. This is read-only and never deletes data."
            ),
            input_schema=RETENTION_HISTORY_SCHEMA,
            handler=retention_history_tools.get_history,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="system.get_runtime_benchmark",
            description=(
                "Return a bounded integrity-checked summary of the "
                "newest persisted local runtime benchmark. Results "
                "include duration, sample success, frame progress, "
                "FPS, P95 latency, memory, temperature, camera "
                "stability, and report SHA-256 without raw samples or "
                "absolute paths. This is read-only."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=benchmark_tools.get_latest,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="system.cleanup_retained_data",
            description=(
                "Delete only the exact old log candidates from a "
                "previous bounded retention preview. The complete "
                "plan ID and every approved relative path are "
                "revalidated immediately before deletion. Evidence, "
                "events, reports, benchmarks, state, and runtime "
                "control files are never eligible. This L2 operation "
                "requires explicit confirmation and writes PREPARED "
                "and final append-only audit records."
            ),
            input_schema=RETENTION_CLEANUP_SCHEMA,
            handler=retention_cleanup_tools.cleanup,
            read_only=False,
        )
    )
    registry.register(
        ToolDefinition(
            name="system.preview_data_retention",
            description=(
                "Preview old files eligible under the fixed local "
                "retention policy. Only logs, Harness audit files, "
                "and edgesentinel-*.log runtime logs are considered. "
                "Evidence, events, reports, benchmarks, state, and "
                "live control files are protected. This dry run is "
                "bounded, skips symlinks, omits absolute paths, and "
                "never deletes or moves files."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=retention_tools.preview,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="system.get_storage_usage",
            description=(
                "Return a bounded read-only inventory of files and "
                "bytes under the fixed project data directory, "
                "grouped by evidence, events, logs, Harness audit, "
                "reports, benchmarks, runtime, state, and other. "
                "Symlinks are skipped and absolute paths are omitted."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=storage_tools.get_usage,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.get_model_info",
            description=(
                "Return the active vision model provenance and verify "
                "the TensorRT engine SHA-256 against the startup "
                "manifest. Results include only a model-root-relative "
                "artifact path, size, precision, L4T release, and "
                "integrity status. This is read-only and never loads, "
                "rebuilds, replaces, or modifies the model."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=model_tools.get_model_info,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.get_performance",
            description=(
                "Return bounded rolling live-vision processing FPS and "
                "pipeline latency statistics, including P50, P95, and "
                "fixed Nano acceptance targets. This is read-only, "
                "uses at most 120 in-memory samples, and never changes "
                "the camera or inference configuration."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=vision_tools.get_performance,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="weather.get_current",
            description=(
                "Look up bounded current weather for one city or "
                "place using the fixed Open-Meteo HTTPS geocoding "
                "and forecast APIs. This makes external network "
                "requests but is read-only, returns no raw provider "
                "response, and never accesses arbitrary URLs. If no "
                "location is stated and no default is configured, "
                "ask the user for a city before calling."
            ),
            input_schema=WEATHER_CURRENT_SCHEMA,
            handler=weather_tools.get_current,
            read_only=True,
            open_world=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.count_objects",
            description=(
                "Count one to twenty exact detector classes in the "
                "latest atomic frame, optionally applying a configured "
                "zone and minimum confidence. Return only aggregate "
                "counts and freshness; never expose detections or "
                "bounding boxes. This is read-only."
            ),
            input_schema=COUNT_OBJECTS_SCHEMA,
            handler=vision_tools.count_objects,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.get_current_objects",
            description=(
                "Return stable object counts from the latest atomic "
                "vision state, including freshness metadata."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=vision_tools.get_current_objects,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.get_track_history",
            description=(
                "Return bounded recent normalized center-point history "
                "for one exact current track ID or detector class. "
                "Results include movement, displacement, visibility, "
                "and current zone IDs, but never bounding boxes or "
                "full detections. This is read-only."
            ),
            input_schema=TRACK_HISTORY_SCHEMA,
            handler=vision_tools.get_track_history,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.get_people_count",
            description=(
                "Return the confirmed people count from the latest "
                "atomic vision state, including freshness metadata."
            ),
            input_schema=NO_ARGUMENTS_SCHEMA,
            handler=vision_tools.get_people_count,
            read_only=True,
        )
    )
    registry.register(
        ToolDefinition(
            name="vision.get_zone_status",
            description=(
                "Return bounded current occupancy for all configured "
                "vision zones or one exact zone_id from the latest "
                "atomic state, including freshness metadata."
            ),
            input_schema=ZONE_STATUS_SCHEMA,
            handler=vision_tools.get_zone_status,
            read_only=True,
        )
    )
    return registry
