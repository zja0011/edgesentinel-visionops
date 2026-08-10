"""Deterministic bounded tool-schema routing before model calls."""

import json
import re


ROUTE_MODES = (
    "DETERMINISTIC",
    "SKILL_PINNED",
    "NO_MATCH",
)

TOKEN_PATTERN = re.compile(r"[a-z0-9_]+", re.IGNORECASE)
MEANINGLESS_TOKENS = frozenset(
    (
        "a",
        "all",
        "and",
        "by",
        "current",
        "data",
        "exact",
        "for",
        "from",
        "get",
        "in",
        "is",
        "latest",
        "local",
        "of",
        "one",
        "only",
        "or",
        "read",
        "recent",
        "return",
        "status",
        "the",
        "this",
        "to",
        "tool",
        "up",
        "use",
        "with",
    )
)


TOOL_ALIASES = {
    "recovery.create_backup": (
        "create disaster recovery backup", "create recovery backup",
        "backup edgesentinel", "\u521b\u5efa\u707e\u96be\u6062\u590d\u5907\u4efd",
        "\u521b\u5efa\u6062\u590d\u5907\u4efd", "\u5907\u4efdedgesentinel",
    ),
    "recovery.get_status": (
        "recovery backup status", "list recovery backups",
        "disaster recovery status", "\u707e\u96be\u6062\u590d\u72b6\u6001",
        "\u67e5\u770b\u6062\u590d\u5907\u4efd", "\u5907\u4efd\u72b6\u6001",
    ),
    "recovery.preview_restore": (
        "preview disaster recovery", "preview restore",
        "verify recovery backup", "\u9884\u89c8\u707e\u96be\u6062\u590d",
        "\u6062\u590d\u9884\u89c8", "\u6821\u9a8c\u6062\u590d\u5907\u4efd",
    ),
    "camera.capture_snapshot": (
        "capture snapshot", "take snapshot", "take a photo",
        "take photo", "camera snapshot", "拍摄快照", "拍快照",
        "快照", "拍照", "截图", "保存当前画面",
    ),
    "camera.get_status": (
        "camera status", "camera health", "camera online",
        "camera offline", "camera available", "摄像头状态",
        "摄像头正常", "摄像头离线", "摄像头在线",
    ),
    "camera.restart": (
        "restart camera", "restart inference", "camera restart",
        "重启摄像头", "重启推理", "恢复摄像头",
    ),
    "report.generate": (
        "generate report", "daily report", "event report",
        "生成报告", "今日报告", "日报", "事件报告",
    ),
    "evidence.verify_recent": (
        "evidence integrity", "verify recent evidence",
        "check evidence", "证据完整性", "检查事件证据",
        "验证最近证据",
    ),
    "evidence.verify_event": (
        "verify event evidence", "exact event evidence",
        "验证事件证据", "核验事件证据", "这个事件的证据",
    ),
    "event.acknowledge": (
        "acknowledge event", "mark event acknowledged",
        "确认事件", "确认告警", "标记已处理", "标记已读",
    ),
    "event.get_detail": (
        "event detail", "event details", "exact event",
        "事件详情", "事件明细", "这个事件",
    ),
    "event.query": (
        "query events", "recent events", "latest events",
        "bottle events", "person events", "camera events",
        "查询事件", "最近事件", "历史事件", "瓶子事件",
        "人员事件", "摄像头事件", "发生了什么",
    ),
    "event.summarize": (
        "event summary", "summarize events", "event trend",
        "event comparison", "event baseline", "event change",
        "事件汇总", "事件摘要", "事件趋势", "事件对比",
        "事件基线", "事件变化", "同比", "环比",
    ),
    "inventory.compare_state": (
        "compare inventory", "inventory check", "expected count",
        "核对库存", "库存对比", "期望库存", "缺少几件",
    ),
    "inventory.get_current_state": (
        "inventory state", "current inventory", "stable inventory",
        "库存状态", "当前库存", "稳定库存",
    ),
    "inventory.get_removed_items": (
        "removed items", "items removed", "missing items",
        "what was removed", "移走的物品", "移除了什么",
        "拿走了什么", "最近移走", "物品移除",
    ),
    "memory.search": (
        "search memory", "what do you remember", "remember about",
        "查询记忆", "搜索记忆", "你记得什么", "我的偏好",
        "长期记忆",
    ),
    "memory.remember": (
        "remember this", "remember that", "save my preference",
        "记住这个", "请记住", "记住我的", "保存偏好",
        "长期记住",
    ),
    "memory.forget": (
        "forget memory", "delete memory", "forget this",
        "忘掉记忆", "删除记忆", "请忘记", "清除记忆",
    ),
    "system.get_health": (
        "jetson health", "system health", "jetson status",
        "system status", "cpu temperature", "memory usage",
        "jetson状态", "系统健康", "系统状态", "设备温度",
        "内存使用", "负载情况",
    ),
    "system.get_retention_cleanup_history": (
        "cleanup history", "retention history", "cleanup audit",
        "清理历史", "清理审计", "保留策略历史",
    ),
    "system.get_runtime_benchmark": (
        "runtime benchmark", "benchmark result", "continuous benchmark",
        "运行基准", "基准测试", "连续运行基准",
    ),
    "system.cleanup_retained_data": (
        "delete old logs", "clean old logs", "run retention cleanup",
        "删除旧日志", "清理旧日志", "执行数据清理",
        "执行保留清理",
    ),
    "system.preview_data_retention": (
        "preview cleanup", "retention preview", "preview old logs",
        "清理预览", "预览旧日志", "预览数据清理",
    ),
    "system.get_storage_usage": (
        "storage usage", "disk usage", "project size",
        "data usage", "存储占用", "磁盘占用", "数据占用",
        "项目大小",
    ),
    "vision.get_model_info": (
        "vision model", "model info", "tensorrt engine",
        "model integrity", "视觉模型", "模型版本", "engine完整性",
        "模型完整性",
    ),
    "vision.get_performance": (
        "vision performance", "processing fps", "pipeline latency",
        "p95 latency", "视觉性能", "处理帧率", "推理帧率",
        "处理延迟", "p95延迟",
    ),
    "weather.get_current": (
        "weather", "temperature outside", "current temperature",
        "forecast", "天气", "气温", "室外温度", "下雨",
        "降雨", "风速",
    ),
    "vision.count_objects": (
        "count objects", "object count", "how many bottles",
        "how many objects", "bottle count", "目标计数",
        "物体计数", "几个瓶子", "多少瓶子", "瓶子数量", "画面有几",
    ),
    "vision.get_current_objects": (
        "current objects", "what objects", "objects in view",
        "what is visible", "当前物品", "有哪些物品",
        "画面里有什么", "看到什么物品",
    ),
    "vision.get_track_history": (
        "track history", "person track", "object track",
        "movement direction", "轨迹历史", "人员轨迹", "目标轨迹",
        "移动方向",
    ),
    "vision.get_people_count": (
        "people count", "person count", "how many people",
        "people in view", "people in camera", "几个人", "多少人",
        "几位", "人员数量", "当前人员",
    ),
    "vision.get_zone_status": (
        "zone status", "zone occupancy", "people in left zone",
        "people in right zone", "区域状态", "区域人数",
        "左侧区域", "右侧区域", "区域占用",
    ),
}


ROUTE_DEPENDENCIES = {
    "recovery.preview_restore": ("recovery.get_status",),
    "memory.forget": ("memory.search",),
    "event.acknowledge": ("event.get_detail",),
    "system.cleanup_retained_data": (
        "system.preview_data_retention",
    ),
}


class ToolRouteError(ValueError):
    pass


class ToolSchemaRouter(object):
    """Select a small, auditable schema set without model calls."""

    def __init__(self, max_tools=6):
        max_tools = int(max_tools)
        if max_tools < 1 or max_tools > 8:
            raise ValueError("max_tools must be between 1 and 8")
        self.max_tools = max_tools

    def route(
        self,
        user_message,
        tool_schemas,
        required_tools=None,
        context_hints=None,
    ):
        schemas = self._validated_schemas(tool_schemas)
        by_name = {
            schema["name"]: schema for schema in schemas
        }
        required = tuple(required_tools or ())
        if required:
            if len(required) > self.max_tools:
                raise ToolRouteError(
                    "required tools exceed route limit"
                )
            missing = [name for name in required if name not in by_name]
            if missing:
                raise ToolRouteError("required tool is unavailable")
            selected_names = sorted(set(required))
            mode = "SKILL_PINNED"
        else:
            routing_text = self._routing_text(
                user_message, context_hints
            )
            scores = []
            for name, schema in by_name.items():
                score = self._score(name, schema, routing_text)
                if score > 0:
                    scores.append((score, name))
            scores.sort(key=lambda item: (-item[0], item[1]))
            selected_names = [
                name for score, name in scores[: self.max_tools]
            ]
            selected_names = self._add_dependencies(
                selected_names, by_name
            )
            mode = (
                "DETERMINISTIC" if selected_names else "NO_MATCH"
            )
        selected = [by_name[name] for name in selected_names]
        before_bytes = self._schema_bytes(schemas)
        after_bytes = self._schema_bytes(selected)
        reduction = (
            round(
                100.0 * (before_bytes - after_bytes) / before_bytes,
                1,
            )
            if before_bytes
            else 0.0
        )
        return {
            "schema_version": "1.0",
            "mode": mode,
            "catalog_tools": len(schemas),
            "selected_tools": selected_names,
            "selected_count": len(selected_names),
            "max_tools": self.max_tools,
            "schema_bytes_before": before_bytes,
            "schema_bytes_after": after_bytes,
            "schema_reduction_percent": reduction,
            "fallback_used": False,
        }

    def validate_route(self, route, tool_schemas):
        if not isinstance(route, dict) or set(route) != {
            "schema_version",
            "mode",
            "catalog_tools",
            "selected_tools",
            "selected_count",
            "max_tools",
            "schema_bytes_before",
            "schema_bytes_after",
            "schema_reduction_percent",
            "fallback_used",
        }:
            raise ToolRouteError("tool route fields are invalid")
        schemas = self._validated_schemas(tool_schemas)
        available = set(schema["name"] for schema in schemas)
        selected = route.get("selected_tools")
        if (
            route.get("schema_version") != "1.0"
            or route.get("mode") not in ROUTE_MODES
            or not isinstance(selected, list)
            or len(selected) > self.max_tools
            or len(selected) != len(set(selected))
            or any(name not in available for name in selected)
            or route.get("catalog_tools") != len(schemas)
            or route.get("selected_count") != len(selected)
            or route.get("max_tools") != self.max_tools
            or route.get("fallback_used") is not False
        ):
            raise ToolRouteError("tool route is invalid")
        for field in (
            "schema_bytes_before",
            "schema_bytes_after",
            "schema_reduction_percent",
        ):
            value = route.get(field)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or value < 0
            ):
                raise ToolRouteError("tool route metrics are invalid")
        schemas_by_name = {
            schema["name"]: schema for schema in schemas
        }
        expected_selected = [
            schemas_by_name[name] for name in selected
        ]
        if (
            route["schema_bytes_before"]
            != self._schema_bytes(schemas)
            or route["schema_bytes_after"]
            != self._schema_bytes(expected_selected)
        ):
            raise ToolRouteError("tool route schema metrics changed")
        return dict(route)

    def select_schemas(self, route, tool_schemas):
        route = self.validate_route(route, tool_schemas)
        selected = set(route["selected_tools"])
        return [
            schema
            for schema in tool_schemas
            if schema.get("name") in selected
        ]

    def _add_dependencies(self, selected_names, by_name):
        result = list(selected_names)
        for name in list(result):
            for dependency in ROUTE_DEPENDENCIES.get(name, ()):
                if dependency in by_name and dependency not in result:
                    if len(result) >= self.max_tools:
                        break
                    result.append(dependency)
        return result

    @classmethod
    def _score(cls, name, schema, routing_text):
        exact_name = name.lower()
        if exact_name in routing_text:
            return 10000 + len(exact_name)
        aliases = TOOL_ALIASES.get(name, ())
        alias_score = max(
            [
                1000 + len(alias) * 4
                for alias in aliases
                if alias.lower() in routing_text
            ]
            or [0]
        )
        annotations = schema.get("annotations") or {}
        if annotations.get("requiresConfirmation"):
            return alias_score
        message_tokens = set(TOKEN_PATTERN.findall(routing_text))
        candidate_text = "{0} {1}".format(
            name.replace(".", " ").replace("_", " "),
            schema.get("description") or "",
        ).lower()
        candidate_tokens = set(TOKEN_PATTERN.findall(candidate_text))
        overlap = (
            message_tokens & candidate_tokens
        ) - MEANINGLESS_TOKENS
        lexical_score = 0
        if len(overlap) >= 2:
            lexical_score = 100 + len(overlap) * 10
        elif overlap & {
            "benchmark",
            "evidence",
            "inventory",
            "memory",
            "people",
            "performance",
            "retention",
            "snapshot",
            "storage",
            "track",
            "weather",
            "zone",
        }:
            lexical_score = 90
        return max(alias_score, lexical_score)

    @staticmethod
    def _routing_text(user_message, context_hints):
        parts = [str(user_message or "").strip().lower()]
        for hint in list(context_hints or [])[-2:]:
            text = str(hint or "").strip().lower()
            if text:
                parts.append(text[:1000])
        return "\n".join(parts)[:3000]

    @staticmethod
    def _validated_schemas(tool_schemas):
        schemas = list(tool_schemas or [])
        if len(schemas) > 128:
            raise ToolRouteError("tool catalog exceeds limit")
        names = set()
        for schema in schemas:
            if not isinstance(schema, dict):
                raise ToolRouteError("tool schema is invalid")
            name = schema.get("name")
            if not isinstance(name, str) or not name or name in names:
                raise ToolRouteError("tool schema name is invalid")
            names.add(name)
        return schemas

    @staticmethod
    def _schema_bytes(schemas):
        return len(
            json.dumps(
                list(schemas),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        )
