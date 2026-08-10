"""Validated user-controlled MCP prompts for EdgeSentinel."""

import re

from packages.vision.schemas import beijing_timestamp


class McpPromptError(RuntimeError):
    pass


class EdgeSentinelPrompts(object):
    PROMPT_DEFINITIONS = (
        {
            "name": "current_scene_summary",
            "title": "Summarize the current scene",
            "description": (
                "Summarize current people, objects, and occupied "
                "zones while reporting state freshness."
            ),
        },
        {
            "name": "recent_event_review",
            "title": "Review recent events",
            "description": (
                "Review a bounded number of recent events, optionally "
                "for one detector class."
            ),
            "arguments": [
                {
                    "name": "object_class",
                    "description": (
                        "Optional detector class such as bottle"
                    ),
                    "required": False,
                },
                {
                    "name": "limit",
                    "description": "Number of events from 1 to 20",
                    "required": False,
                },
            ],
        },
        {
            "name": "inventory_check",
            "title": "Compare expected inventory",
            "description": (
                "Compare one configured inventory class with an "
                "expected count."
            ),
            "arguments": [
                {
                    "name": "object_class",
                    "description": (
                        "Configured detector class such as bottle"
                    ),
                    "required": True,
                },
                {
                    "name": "expected_count",
                    "description": "Expected count from 0 to 100",
                    "required": True,
                },
            ],
        },
    )

    CLASS_PATTERN = re.compile(
        r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,63}$"
    )

    def __init__(self, audit_recorder=None):
        self.audit_recorder = audit_recorder
        self._definitions = {
            definition["name"]: definition
            for definition in self.PROMPT_DEFINITIONS
        }

    def list_prompts(self):
        return [
            dict(definition)
            for definition in self.PROMPT_DEFINITIONS
        ]

    def get(self, name, arguments=None):
        if not isinstance(name, str) or not name:
            raise McpPromptError("prompt name is required")
        definition = self._definitions.get(name)
        if definition is None:
            self._audit(name, "FAILED", "PROMPT_NOT_FOUND")
            raise McpPromptError("prompt not found")
        arguments = arguments or {}
        if not isinstance(arguments, dict):
            raise McpPromptError(
                "prompt arguments must be an object"
            )
        expected = {
            argument["name"]: argument
            for argument in definition.get("arguments", [])
        }
        if set(arguments) - set(expected):
            self._audit(
                name,
                "FAILED",
                "UNEXPECTED_ARGUMENT",
            )
            raise McpPromptError("unexpected prompt argument")
        for key, value in arguments.items():
            if not isinstance(value, str):
                raise McpPromptError(
                    "prompt arguments must be strings"
                )
        for key, argument in expected.items():
            if argument.get("required") and not arguments.get(key):
                self._audit(
                    name,
                    "FAILED",
                    "MISSING_ARGUMENT",
                )
                raise McpPromptError(
                    "required prompt argument is missing"
                )
        try:
            text = self._render(name, arguments)
        except (TypeError, ValueError):
            self._audit(name, "FAILED", "INVALID_ARGUMENT")
            raise McpPromptError("prompt argument is invalid")
        self._audit(name, "SUCCEEDED", None)
        return {
            "description": definition["description"],
            "messages": [
                {
                    "role": "user",
                    "content": {
                        "type": "text",
                        "text": text,
                    },
                }
            ],
        }

    def _render(self, name, arguments):
        if name == "current_scene_summary":
            return (
                "请总结 EdgeSentinel 当前画面。只调用 L0 只读工具 "
                "vision.get_people_count、vision.get_current_objects 和 "
                "vision.get_zone_status。明确说明数据是否 stale；若状态陈旧或"
                "不可用，不要把历史状态描述成实时事实。不要执行任何写操作。"
            )
        if name == "recent_event_review":
            object_class = arguments.get("object_class")
            if object_class:
                object_class = self._validate_class(object_class)
            limit = self._bounded_integer(
                arguments.get("limit", "5"),
                1,
                20,
            )
            scope = (
                "目标类别 {0}".format(object_class)
                if object_class
                else "全部目标类别"
            )
            return (
                "请使用 L0 只读工具 event.query 检索{0}最近{1}条"
                "结构化事件，按时间倒序概括类型、时间、区域和严重级别。"
                "只根据工具结果回答，不推测未记录的因果关系，不执行任何"
                "写操作。".format(scope, limit)
            )
        object_class = self._validate_class(
            arguments["object_class"]
        )
        expected_count = self._bounded_integer(
            arguments["expected_count"],
            0,
            100,
        )
        return (
            "请使用 L0 只读工具 inventory.compare_state 核对 {0}，"
            "期望数量为 {1}。报告当前稳定数量、缺少数、额外数及是否"
            "一致；若视觉状态 stale，必须明确提示。不要执行任何写操作。"
            .format(object_class, expected_count)
        )

    @classmethod
    def _validate_class(cls, value):
        value = str(value).strip()
        if not cls.CLASS_PATTERN.match(value):
            raise ValueError("invalid detector class")
        return value

    @staticmethod
    def _bounded_integer(value, minimum, maximum):
        if not isinstance(value, str) or not value.isdigit():
            raise ValueError("integer argument is invalid")
        number = int(value)
        if number < minimum or number > maximum:
            raise ValueError("integer argument is out of range")
        return number

    def _audit(self, name, status, error_code):
        if self.audit_recorder is None:
            return
        record = {
            "schema_version": "1.0",
            "record_type": "mcp_prompt_get",
            "timestamp": beijing_timestamp(),
            "prompt_name": str(name)[:128],
            "status": status,
            "user_controlled": True,
        }
        if error_code:
            record["error"] = {"code": error_code}
        self.audit_recorder.append(record)
