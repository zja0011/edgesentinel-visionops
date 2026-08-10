"""Deterministic offline model substitute for Agent Loop testing."""

import re


class ToolCall(object):
    def __init__(self, name, arguments=None, call_id=None):
        self.name = str(name)
        self.arguments = dict(arguments or {})
        self.call_id = (
            str(call_id) if call_id is not None else None
        )

    def to_dict(self):
        payload = {
            "name": self.name,
            "arguments": self.arguments,
        }
        if self.call_id is not None:
            payload["call_id"] = self.call_id
        return payload


class ModelResponse(object):
    def __init__(
        self,
        content="",
        tool_calls=None,
        usage=None,
        runtime=None,
    ):
        self.content = str(content)
        self.tool_calls = list(tool_calls or [])
        self.usage = (
            dict(usage) if isinstance(usage, dict) else None
        )
        self.runtime = (
            dict(runtime) if isinstance(runtime, dict) else None
        )

    def to_dict(self):
        payload = {
            "content": self.content,
            "tool_calls": [
                tool_call.to_dict()
                for tool_call in self.tool_calls
            ],
        }
        if self.usage is not None:
            payload["usage"] = dict(self.usage)
        if self.runtime is not None:
            payload["runtime"] = dict(self.runtime)
        return payload


class OfflineMockModel(object):
    """Route a few demo intents without any network or real LLM."""

    name = "offline-rule-mock"

    def generate(
        self,
        context,
        tool_schemas=None,
        conversation=None,
    ):
        message = context.get("user_message", "").lower()
        results = context.get("recent_tool_results") or []
        active_skill = context.get("active_skill") or {}
        if (
            not results
            and active_skill.get("name")
            == "vision.investigate_removed_item"
        ):
            arguments = {
                "event_type": "OBJECT_REMOVED",
                "limit": 5,
            }
            if (
                "bottle" in message
                or "\u74f6\u5b50" in message
            ):
                arguments["object_class"] = "bottle"
            return ModelResponse(
                tool_calls=[
                    ToolCall("event.query", arguments)
                ]
            )
        cleanup_requested = self._contains_any(
            message,
            (
                "执行旧日志清理",
                "清理已预览旧日志",
                "确认清理旧日志",
                "execute retention cleanup",
                "clean the previewed old logs",
            ),
        )
        if results:
            latest = results[-1]
            if (
                self._memory_forget_requested(message)
                and latest.get("status") == "SUCCEEDED"
                and latest.get("tool_name") == "memory.search"
            ):
                records = list(
                    (latest.get("result") or {}).get("records")
                    or []
                )
                if len(records) == 1:
                    return ModelResponse(
                        tool_calls=[
                            ToolCall(
                                "memory.forget",
                                {
                                    "memory_id": records[0].get(
                                        "memory_id"
                                    )
                                },
                            )
                        ]
                    )
            if (
                cleanup_requested
                and latest.get("status") == "SUCCEEDED"
                and latest.get("tool_name")
                == "system.preview_data_retention"
            ):
                payload = latest.get("result") or {}
                candidates = list(
                    payload.get("candidate_files") or []
                )
                if not candidates:
                    return ModelResponse(
                        content=(
                            "当前没有符合固定保留规则的旧日志，"
                            "未执行删除。"
                        )
                    )
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            "system.cleanup_retained_data",
                            {
                                "plan_id": payload.get(
                                    "plan_id"
                                ),
                                "candidate_paths": [
                                    item.get("path")
                                    for item in candidates
                                ],
                            },
                        )
                    ]
                )
            return self._answer_from_result(results[-1])

        if "system.shell" in message or "shell" in message:
            return ModelResponse(
                tool_calls=[ToolCall("system.shell", {})]
            )
        backup_id = re.search(r"\bdr_[0-9a-f]{32}\b", message)
        if self._contains_any(
            message,
            (
                "preview disaster recovery",
                "preview restore",
                "verify recovery backup",
                "\u9884\u89c8\u707e\u96be\u6062\u590d",
                "\u6062\u590d\u9884\u89c8",
                "\u6821\u9a8c\u6062\u590d\u5907\u4efd",
            ),
        ):
            if backup_id is None:
                return ModelResponse(
                    tool_calls=[
                        ToolCall("recovery.get_status", {"limit": 5})
                    ]
                )
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "recovery.preview_restore",
                        {"backup_id": backup_id.group(0)},
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "create disaster recovery backup",
                "create recovery backup",
                "backup edgesentinel",
                "\u521b\u5efa\u707e\u96be\u6062\u590d\u5907\u4efd",
                "\u521b\u5efa\u6062\u590d\u5907\u4efd",
                "\u5907\u4efdedgesentinel",
            ),
        ):
            return ModelResponse(
                tool_calls=[ToolCall("recovery.create_backup", {})]
            )
        if self._contains_any(
            message,
            (
                "recovery backup status",
                "list recovery backups",
                "disaster recovery status",
                "\u707e\u96be\u6062\u590d\u72b6\u6001",
                "\u67e5\u770b\u6062\u590d\u5907\u4efd",
                "\u5907\u4efd\u72b6\u6001",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("recovery.get_status", {"limit": 5})
                ]
            )
        memory_id = re.search(r"\bmem_[0-9a-f]{32}\b", message)
        if self._memory_forget_requested(message):
            if memory_id is not None:
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            "memory.forget",
                            {"memory_id": memory_id.group(0)},
                        )
                    ]
                )
            query = self._extract_memory_query(message)
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "memory.search",
                        {"query": query, "limit": 5}
                        if query
                        else {"limit": 5},
                    )
                ]
            )
        memory_record = self._extract_memory_record(message)
        if memory_record is not None:
            return ModelResponse(
                tool_calls=[
                    ToolCall("memory.remember", memory_record)
                ]
            )
        if self._memory_search_requested(message):
            query = self._extract_memory_query(message)
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "memory.search",
                        {"query": query, "limit": 5}
                        if query
                        else {"limit": 5},
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "snapshot",
                "capture",
                "\u5feb\u7167",
                "\u622a\u56fe",
                "\u4fdd\u5b58\u753b\u9762",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("camera.capture_snapshot", {})
                ]
            )
        if self._contains_any(
            message,
            (
                "restart camera",
                "restart vision",
                "restart inference",
                "\u91cd\u542f\u6444\u50cf\u5934",
                "\u91cd\u542f\u89c6\u89c9",
                "\u91cd\u542f\u63a8\u7406",
            ),
        ):
            return ModelResponse(
                tool_calls=[ToolCall("camera.restart", {})]
            )
        if self._contains_any(
            message,
            (
                "model version",
                "model info",
                "tensorrt engine",
                "\u6a21\u578b\u7248\u672c",
                "\u89c6\u89c9\u6a21\u578b",
                "\u63a8\u7406\u6a21\u578b",
                "\u5f15\u64ce\u5b8c\u6574\u6027",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("vision.get_model_info", {})
                ]
            )
        if self._contains_any(
            message,
            (
                "vision performance",
                "processing fps",
                "inference latency",
                "latency p95",
                "\u89c6\u89c9\u6027\u80fd",
                "\u5904\u7406\u5e27\u7387",
                "\u63a8\u7406\u5ef6\u8fdf",
                "\u5ef6\u8fdfp95",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("vision.get_performance", {})
                ]
            )
        if self._contains_any(
            message,
            (
                "runtime benchmark",
                "stability benchmark",
                "latest benchmark",
                "\u8fd0\u884c\u57fa\u51c6",
                "\u7a33\u5b9a\u6027\u57fa\u51c6",
                "\u8fde\u7eed\u8fd0\u884c\u57fa\u51c6",
                "\u6700\u8fd1\u57fa\u51c6",
                "\u57fa\u51c6\u62a5\u544a",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "system.get_runtime_benchmark",
                        {},
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "摄像头状态",
                "摄像头正常",
                "摄像头在线",
                "摄像头工作",
                "camera status",
                "camera healthy",
                "camera online",
            ),
        ):
            return ModelResponse(
                tool_calls=[ToolCall("camera.get_status", {})]
            )
        if self._contains_any(
            message,
            (
                "天气",
                "气温",
                "weather",
                "outside temperature",
            ),
        ):
            weather_location = self._extract_weather_location(
                message
            )
            weather_arguments = {}
            if weather_location:
                weather_arguments["location"] = weather_location
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "weather.get_current",
                        weather_arguments,
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "\u6e05\u7406\u5ba1\u8ba1",
                "\u6e05\u7406\u5386\u53f2",
                "\u6e05\u7406\u8bb0\u5f55",
                "\u65e7\u65e5\u5fd7\u6e05\u7406\u8bb0\u5f55",
                "retention cleanup history",
                "retention cleanup audit",
                "cleanup audit history",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "system.get_retention_cleanup_history",
                        {"limit": 10},
                    )
                ]
            )
        if cleanup_requested:
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "system.preview_data_retention",
                        {},
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "清理预览",
                "可清理多少",
                "旧数据清理",
                "保留策略",
                "retention preview",
                "cleanup preview",
                "old data can be cleaned",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "system.preview_data_retention",
                        {},
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "项目数据占用",
                "证据占用",
                "存储占用",
                "数据目录大小",
                "project data usage",
                "project data storage",
                "storage usage",
                "evidence usage",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("system.get_storage_usage", {})
                ]
            )
        if self._contains_any(
            message,
            (
                "设备状态",
                "运行状态",
                "系统健康",
                "温度",
                "内存",
                "磁盘",
                "负载",
                "system health",
                "temperature",
                "memory",
                "disk usage",
            ),
        ):
            return ModelResponse(
                tool_calls=[ToolCall("system.get_health", {})]
            )
        if self._contains_any(
            message,
            (
                "\u8bc1\u636e\u5b8c\u6574\u6027",
                "\u8bc1\u636e\u6587\u4ef6\u68c0\u67e5",
                "\u68c0\u67e5\u4e8b\u4ef6\u8bc1\u636e",
                "evidence integrity",
                "verify event evidence",
                "check evidence files",
            ),
        ):
            exact_event = re.search(
                r"\bevt_[0-9a-f]{32}\b",
                message,
            )
            if exact_event:
                return ModelResponse(
                    tool_calls=[
                        ToolCall(
                            "evidence.verify_event",
                            {
                                "event_id": (
                                    exact_event.group(0)
                                )
                            },
                        )
                    ]
                )
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "evidence.verify_recent",
                        {"limit": 50},
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "报告",
                "日报",
                "生成摘要",
                "generate report",
                "daily report",
            ),
        ):
            return ModelResponse(
                tool_calls=[ToolCall("report.generate", {})]
            )
        if self._contains_any(
            message,
            (
                "确认处理事件",
                "标记事件已处理",
                "acknowledge event",
            ),
        ):
            event_id = re.search(
                r"\bevt_[0-9a-f]{32}\b",
                message,
            )
            if event_id is None:
                return ModelResponse(
                    content="请提供需要确认处理的完整事件ID。"
                )
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "event.acknowledge",
                        {"event_id": event_id.group(0)},
                    )
                ]
            )
        event_id = re.search(
            r"\bevt_[0-9a-f]{32}\b",
            message,
        )
        if event_id is not None and self._contains_any(
            message,
            (
                "事件",
                "详情",
                "查看",
                "event",
                "detail",
                "show",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "event.get_detail",
                        {"event_id": event_id.group(0)},
                    )
                ]
            )
        track_history_requested = self._contains_any(
            message,
            (
                "轨迹",
                "移动路线",
                "运动路线",
                "track history",
                "trajectory",
                "movement path",
            ),
        )
        if track_history_requested:
            track_match = re.search(
                r"(?:track(?:_id)?|轨迹)\s*[#:=]?\s*(\d+)",
                message,
            )
            track_object_class = self._extract_inventory_class(
                message
            )
            if track_object_class is None and self._contains_any(
                message,
                ("person", "人员", "行人"),
            ):
                track_object_class = "person"
            arguments = {}
            if track_match is not None:
                arguments["track_id"] = int(track_match.group(1))
            if track_object_class is not None:
                arguments["object_class"] = track_object_class
            if not arguments:
                return ModelResponse(
                    content=(
                        "请提供要查询的track ID或目标类别，"
                        "例如：查询track 7的轨迹。"
                    )
                )
            arguments["limit"] = 10
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "vision.get_track_history",
                        arguments,
                    )
                ]
            )
        object_count_class = self._extract_inventory_class(message)
        inventory_comparison_requested = (
            self._contains_any(
                message,
                (
                    "对比",
                    "比较",
                    "核对",
                    "compare",
                    "comparison",
                ),
            )
            and self._contains_any(
                message,
                ("库存", "inventory"),
            )
        )
        if (
            object_count_class
            and not inventory_comparison_requested
            and self._contains_any(
                message,
                (
                    "多少个",
                    "有几个",
                    "几个",
                    "数量",
                    "数一下",
                    "how many",
                    "count",
                ),
            )
        ):
            arguments = {"classes": [object_count_class]}
            confidence_match = re.search(
                (
                    r"(?:confidence|置信度)\s*"
                    r"(?:>=|=|至少|at\s+least)?\s*"
                    r"(0(?:\.\d+)?|1(?:\.0+)?)"
                ),
                message,
            )
            if confidence_match is not None:
                arguments["minimum_confidence"] = float(
                    confidence_match.group(1)
                )
            if self._contains_any(
                message,
                ("left_zone", "left zone", "左侧", "左边", "左区"),
            ):
                arguments["zone_id"] = "left_zone"
            elif self._contains_any(
                message,
                (
                    "right_zone",
                    "right zone",
                    "右侧",
                    "右边",
                    "右区",
                ),
            ):
                arguments["zone_id"] = "right_zone"
            return ModelResponse(
                tool_calls=[
                    ToolCall("vision.count_objects", arguments)
                ]
            )
        if inventory_comparison_requested:
            object_class = self._extract_inventory_class(message)
            count_match = re.search(
                (
                    r"(?:期望|应该有|应有)\s*(\d{1,3})"
                    r"|(?:expected(?:\s+count)?(?:\s+is)?"
                    r"|expect)\s*(?:=|:)?\s*(\d{1,3})"
                ),
                message,
            )
            if object_class is None or count_match is None:
                return ModelResponse(
                    content=(
                        "请提供要核对的物品类别和期望数量，"
                        "例如：对比瓶子库存，期望2个。"
                    )
                )
            expected_count = next(
                int(value)
                for value in count_match.groups()
                if value is not None
            )
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "inventory.compare_state",
                        {
                            "expected_counts": {
                                object_class: expected_count
                            }
                        },
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "移走",
                "拿走",
                "移除",
                "被取走",
                "removed",
                "taken away",
            ),
        ) and (
            re.search(
                r"\d{1,4}\s*(?:分钟|minutes?|mins?)",
                message,
            )
            is not None
            or self._contains_any(
                message,
                (
                    "哪些物品",
                    "什么物品",
                    "移除记录",
                    "移走记录",
                    "removed items",
                    "removal history",
                    "inventory",
                ),
            )
        ):
            arguments = {"minutes": 10, "limit": 20}
            minute_match = re.search(
                r"(\d{1,4})\s*(?:分钟|minutes?|mins?)",
                message,
            )
            if minute_match is not None:
                arguments["minutes"] = int(
                    minute_match.group(1)
                )
            if self._contains_any(
                message,
                (
                    "\u672a\u5904\u7406",
                    "\u5f85\u5904\u7406",
                    "open events",
                    "open info events",
                    "unacknowledged",
                ),
            ):
                arguments["status"] = "OPEN"
            elif self._contains_any(
                message,
                (
                    "\u5df2\u5904\u7406",
                    "acknowledged events",
                    "handled events",
                ),
            ):
                arguments["status"] = "ACKNOWLEDGED"
            object_class = self._extract_inventory_class(message)
            if object_class:
                arguments["object_class"] = object_class
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "inventory.get_removed_items",
                        arguments,
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "库存",
                "清点",
                "稳定数量",
                "可见数量",
                "inventory",
                "stable count",
                "visible count",
            ),
        ):
            arguments = {}
            object_class = self._extract_inventory_class(message)
            if object_class:
                arguments["object_class"] = object_class
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        "inventory.get_current_state",
                        arguments,
                    )
                ]
            )
        if self._contains_any(
            message,
            (
                "区域",
                "分区",
                "zone",
                "left_zone",
                "right_zone",
            ),
        ) and not self._contains_any(
            message,
            (
                "事件",
                "进入",
                "离开",
                "停留",
                "event",
                "dwell",
            ),
        ):
            arguments = {}
            if self._contains_any(
                message,
                ("left_zone", "left zone", "左侧", "左边", "左区"),
            ):
                arguments["zone_id"] = "left_zone"
            elif self._contains_any(
                message,
                (
                    "right_zone",
                    "right zone",
                    "右侧",
                    "右边",
                    "右区",
                ),
            ):
                arguments["zone_id"] = "right_zone"
            return ModelResponse(
                tool_calls=[
                    ToolCall("vision.get_zone_status", arguments)
                ]
            )
        if self._contains_any(
            message,
            (
                "几个人",
                "多少人",
                "几位",
                "多少位",
                "人数",
                "people",
            ),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("vision.get_people_count", {})
                ]
            )
        if self._contains_any(
            message,
            ("当前物品", "有什么物品", "哪些物品", "objects"),
        ):
            return ModelResponse(
                tool_calls=[
                    ToolCall("vision.get_current_objects", {})
                ]
            )
        if self._contains_any(
            message,
            (
                "发生了什么",
                "事件汇总",
                "事件概览",
                "what happened",
                "event summary",
                "summary of",
                "summarize",
                "summarize events",
                "\u4e8b\u4ef6\u8d8b\u52bf",
                "\u8d8b\u52bf",
                "event trend",
                "events trend",
                "\u4e8b\u4ef6\u5bf9\u6bd4",
                "\u4e8b\u4ef6\u6bd4\u8f83",
                "compare events",
                "event comparison",
                "\u4e8b\u4ef6\u53d8\u5316\u662f\u5426\u5f02\u5e38",
                "\u4e8b\u4ef6\u53d8\u5316\u8bc4\u4f30",
                "event change assessment",
                "event volume changed significantly",
                "\u6628\u5929\u540c\u4e00\u65f6\u6bb5",
                "\u6628\u65e5\u540c\u671f",
                "\u4e0a\u5468\u540c\u4e00\u65f6\u6bb5",
                "same time yesterday",
                "same period yesterday",
                "same time last week",
            ),
        ):
            trend_intent = self._contains_any(
                message,
                (
                    "\u4e8b\u4ef6\u8d8b\u52bf",
                    "\u8d8b\u52bf",
                    "event trend",
                    "events trend",
                    "as a trend",
                ),
            )
            compare_intent = self._contains_any(
                message,
                (
                    "\u4e8b\u4ef6\u5bf9\u6bd4",
                    "\u4e8b\u4ef6\u6bd4\u8f83",
                    "\u4e0e\u524d\u4e00\u65f6\u6bb5\u5bf9\u6bd4",
                    "compare events",
                    "event comparison",
                    "compare with the previous",
                ),
            )
            assessment_intent = self._contains_any(
                message,
                (
                    "\u4e8b\u4ef6\u53d8\u5316\u662f\u5426\u5f02\u5e38",
                    "\u4e8b\u4ef6\u53d8\u5316\u8bc4\u4f30",
                    "event change assessment",
                    "event volume changed significantly",
                ),
            )
            aligned_yesterday_intent = self._contains_any(
                message,
                (
                    "\u6628\u5929\u540c\u4e00\u65f6\u6bb5",
                    "\u6628\u65e5\u540c\u671f",
                    "same time yesterday",
                    "same period yesterday",
                ),
            )
            aligned_week_intent = self._contains_any(
                message,
                (
                    "\u4e0a\u5468\u540c\u4e00\u65f6\u6bb5",
                    "same time last week",
                ),
            )
            aligned_intent = (
                aligned_yesterday_intent
                or aligned_week_intent
            )
            reference_baseline_intent = (
                aligned_yesterday_intent
                and aligned_week_intent
            )
            compare_intent = (
                compare_intent
                or assessment_intent
                or aligned_intent
            )
            arguments = {
                "minutes": (
                    60
                    if aligned_intent
                    else (
                        1440
                        if trend_intent or compare_intent
                        else 10
                    )
                ),
                "recent_limit": 5,
            }
            if trend_intent:
                arguments["bucket_minutes"] = 60
            if compare_intent and not reference_baseline_intent:
                arguments["compare_previous"] = True
            if reference_baseline_intent:
                arguments["include_reference_baselines"] = True
            if assessment_intent:
                arguments["change_threshold_percent"] = 25
                arguments["change_threshold_events"] = 10
            if (
                aligned_yesterday_intent
                and not reference_baseline_intent
            ):
                arguments["comparison_offset_minutes"] = 1440
            elif (
                aligned_week_intent
                and not reference_baseline_intent
            ):
                arguments["comparison_offset_minutes"] = 10080
            minute_match = re.search(
                r"(\d{1,4})\s*(?:\u5206\u949f|minutes?|mins?)",
                message,
                re.IGNORECASE,
            )
            if minute_match is not None:
                arguments["minutes"] = int(
                    minute_match.group(1)
                )
            if self._contains_any(
                message,
                (
                    "\u672a\u5904\u7406",
                    "\u5f85\u5904\u7406",
                    "open events",
                    "open info events",
                    "unacknowledged",
                ),
            ):
                arguments["status"] = "OPEN"
            elif self._contains_any(
                message,
                (
                    "\u5df2\u5904\u7406",
                    "acknowledged events",
                    "handled events",
                ),
            ):
                arguments["status"] = "ACKNOWLEDGED"
            severity = self._event_severity(message)
            if severity is not None:
                arguments["severity"] = severity
            if "瓶" in message or "bottle" in message:
                arguments["object_class"] = "bottle"
            elif "人" in message or "person" in message:
                arguments["object_class"] = "person"
            return ModelResponse(
                tool_calls=[
                    ToolCall("event.summarize", arguments)
                ]
            )
        if self._contains_any(
            message,
            (
                "事件",
                "拿走",
                "移除",
                "最近",
                "离线",
                "断线",
                "恢复",
                "故障",
                "停留",
                "逗留",
                "event",
                "offline",
                "recovered",
                "dwell",
            ),
        ):
            arguments = {"limit": 5}
            minute_match = re.search(
                r"(\d{1,4})\s*(?:\u5206\u949f|minutes?|mins?)",
                message,
                re.IGNORECASE,
            )
            if minute_match is not None:
                arguments["minutes"] = int(
                    minute_match.group(1)
                )
            if self._contains_any(
                message,
                (
                    "\u672a\u5904\u7406",
                    "\u5f85\u5904\u7406",
                    "open events",
                    "open info events",
                    "unacknowledged",
                ),
            ):
                arguments["status"] = "OPEN"
            elif self._contains_any(
                message,
                (
                    "\u5df2\u5904\u7406",
                    "acknowledged events",
                    "handled events",
                ),
            ):
                arguments["status"] = "ACKNOWLEDGED"
            severity = self._event_severity(message)
            if severity is not None:
                arguments["severity"] = severity
            if "瓶" in message or "bottle" in message:
                arguments["object_class"] = "bottle"
            elif self._contains_any(
                message,
                ("停留", "逗留", "dwell"),
            ):
                arguments["object_class"] = "person"
                arguments["event_type"] = "ZONE_DWELL"
            elif "摄像头" in message or "camera" in message:
                arguments["object_class"] = "camera"
                offline_intent = self._contains_any(
                    message,
                    ("离线", "断线", "故障", "offline"),
                )
                recovered_intent = self._contains_any(
                    message,
                    ("恢复", "recovered"),
                )
                if offline_intent and not recovered_intent:
                    arguments["event_type"] = "CAMERA_OFFLINE"
                elif recovered_intent and not offline_intent:
                    arguments["event_type"] = "CAMERA_RECOVERED"
            return ModelResponse(
                tool_calls=[ToolCall("event.query", arguments)]
            )
        return ModelResponse(
            content=(
                "离线 Mock Model 目前支持人数、当前物品、"
                "历史事件和 Jetson 设备健康查询。"
            )
        )

    def _answer_from_result(self, tool_result):
        if tool_result.get("status") != "SUCCEEDED":
            if tool_result.get("tool_name") == "weather.get_current":
                return ModelResponse(
                    content=(
                        "天气查询未完成。请提供具体城市（例如“深圳天气"
                        "怎样”），并确认 Jetson 可以访问天气服务。"
                    )
                )
            error_code = tool_result.get("error_code") or "UNKNOWN"
            return ModelResponse(
                content=(
                    "请求的工具被安全策略或工具运行时拒绝"
                    "（{0}），未执行任何系统操作。"
                ).format(error_code)
            )

        tool_name = tool_result.get("tool_name")
        payload = tool_result.get("result") or {}
        if tool_name == "camera.capture_snapshot":
            return ModelResponse(
                content=(
                    "\u5df2\u786e\u8ba4\u5e76\u4fdd\u5b58\u5f53\u524d"
                    "\u6807\u6ce8\u753b\u9762\uff1a{0}"
                ).format(
                    payload.get("evidence_path")
                    or "\u672a\u77e5\u8def\u5f84"
                )
            )
        if tool_name == "recovery.create_backup":
            return ModelResponse(
                content=(
                    "\u5df2\u786e\u8ba4\u5e76\u521b\u5efa\u672c\u5730\u707e\u96be\u6062\u590d\u5907\u4efd"
                    "{0}\uff1a{1}\u4e2a\u6587\u4ef6\uff0c{2}\u5b57\u8282\uff0cSQLite\u4e00\u81f4\u6027={3}\u3002"
                ).format(
                    payload.get("backup_id"),
                    payload.get("file_count"),
                    payload.get("bytes"),
                    payload.get("sqlite_consistent"),
                )
            )
        if tool_name == "recovery.get_status":
            backups = list(payload.get("backups") or [])
            if not backups:
                return ModelResponse(
                    content="\u5f53\u524d\u6ca1\u6709\u53ef\u7528\u7684\u707e\u96be\u6062\u590d\u5907\u4efd\u3002"
                )
            latest = backups[0]
            return ModelResponse(
                content=(
                    "\u5df2\u9a8c\u8bc1{0}\u4e2a\u707e\u96be\u6062\u590d\u5907\u4efd\uff1b\u6700\u65b0\u5907\u4efd"
                    "{1}\uff0c{2}\u4e2a\u6587\u4ef6\uff0c{3}\u5b57\u8282\u3002"
                ).format(
                    payload.get("backup_count"),
                    latest.get("backup_id"),
                    latest.get("file_count"),
                    latest.get("bytes"),
                )
            )
        if tool_name == "recovery.preview_restore":
            return ModelResponse(
                content=(
                    "\u6062\u590d\u9884\u89c8{0}\uff1a\u5c06\u8986\u76d6\u6216\u521b\u5efa{1}\u4e2a\u6587\u4ef6\uff0c"
                    "{2}\u4e2a\u6587\u4ef6\u4e0d\u53d8\uff1b\u672a\u6267\u884c\u6062\u590d\u3002"
                ).format(
                    payload.get("backup_id"),
                    payload.get("changed_file_count"),
                    payload.get("unchanged_file_count"),
                )
            )
        if tool_name == "memory.remember":
            return ModelResponse(
                content=(
                    "已确认长期记忆：{0}={1}（{2}，修订{3}）。"
                ).format(
                    payload.get("key"),
                    payload.get("value"),
                    payload.get("kind"),
                    payload.get("revision"),
                )
            )
        if tool_name == "memory.forget":
            return ModelResponse(
                content=(
                    "已确认删除长期记忆：{0}（{1}）。"
                ).format(
                    payload.get("key"),
                    payload.get("memory_id"),
                )
            )
        if tool_name == "memory.search":
            records = list(payload.get("records") or [])
            if not records:
                return ModelResponse(content="没有找到匹配的长期记忆。")
            return ModelResponse(
                content="已确认的长期记忆：{0}".format(
                    "；".join(
                        "{0}={1}（{2}，修订{3}）".format(
                            record.get("key"),
                            record.get("value"),
                            record.get("kind"),
                            record.get("revision"),
                        )
                        for record in records[:5]
                    )
                )
            )
        if tool_name == "vision.get_model_info":
            artifact = payload.get("artifact") or {}
            verification = payload.get("verification") or {}
            return ModelResponse(
                content=(
                    "\u5f53\u524d\u89c6\u89c9\u6a21\u578b\uff1a{0}"
                    "\uff0c\u540e\u7aef{1}\uff0c\u7cbe\u5ea6{2}"
                    "\uff0c\u6e05\u5355ID {3}\uff0cEngine\u5b8c\u6574"
                    "\u6027{4}\u3002"
                ).format(
                    payload.get("network") or "unknown",
                    payload.get("backend") or "unknown",
                    artifact.get("precision") or "UNKNOWN",
                    payload.get("manifest_id") or "unknown",
                    verification.get("status") or "UNKNOWN",
                )
            )
        if tool_name == "vision.get_performance":
            latency = payload.get("pipeline_latency_ms") or {}
            targets = payload.get("targets") or {}
            return ModelResponse(
                content=(
                    "\u5f53\u524d\u89c6\u89c9\u6027\u80fd\uff1a"
                    "{0} FPS\uff0c\u5e73\u5747\u5904\u7406\u5ef6\u8fdf"
                    "{1} ms\uff0cP95\u5ef6\u8fdf{2} ms\uff0c"
                    "\u72b6\u6001{3}\uff0cNano\u6027\u80fd\u76ee\u6807"
                    "\u5168\u90e8\u8fbe\u6807={4}\u3002"
                ).format(
                    payload.get("processing_fps"),
                    latency.get("average"),
                    latency.get("p95"),
                    payload.get("status"),
                    targets.get("all_met"),
                )
            )
        if tool_name == "system.get_runtime_benchmark":
            performance = payload.get("performance") or {}
            resources = payload.get("resources") or {}
            camera = payload.get("camera") or {}
            return ModelResponse(
                content=(
                    "\u6700\u8fd1\u8fde\u7eed\u8fd0\u884c\u57fa\u51c6"
                    "\uff1a{0}\uff0c\u65f6\u957f{1}\u79d2\uff0c"
                    "\u91c7\u6837{2}/{3}\uff0cAPI\u6210\u529f\u7387"
                    "{4}%\uff0c\u89c6\u89c9\u65b0\u9c9c\u7387{5}%"
                    "\uff0c\u6700\u4f4eFPS {6}\uff0c\u6700\u5927P95 "
                    "{7} ms\uff0c\u5cf0\u503c\u5185\u5b58{8} GiB"
                    "\uff0c\u6700\u9ad8\u6e29\u5ea6{9}\u00b0C\uff0c"
                    "\u6444\u50cf\u5934\u91cd\u542f\u589e\u91cf{10}"
                    "\u3002"
                ).format(
                    payload.get("status"),
                    payload.get("actual_duration_seconds"),
                    payload.get("sample_count"),
                    payload.get("expected_sample_count"),
                    payload.get("api_success_percent"),
                    payload.get("vision_fresh_percent"),
                    performance.get("minimum_fps"),
                    performance.get("maximum_observed_p95_ms"),
                    resources.get("peak_memory_used_gib"),
                    resources.get(
                        "maximum_temperature_celsius"
                    ),
                    camera.get("restart_count_delta"),
                )
            )
        if tool_name == "camera.get_status":
            vision = payload.get("vision") or {}
            if payload.get("healthy"):
                return ModelResponse(
                    content=(
                        "摄像头运行正常：状态{0}，设备可用，"
                        "推理进程正在运行，视觉帧{1}，"
                        "累计自动恢复{2}次。"
                    ).format(
                        payload.get("status"),
                        vision.get("frame_id"),
                        payload.get("restart_count", 0),
                    )
                )
            return ModelResponse(
                content=(
                    "摄像头当前不健康：状态{0}，设备可用={1}，"
                    "推理进程运行={2}，状态过期={3}。"
                ).format(
                    payload.get("status"),
                    payload.get("device_available"),
                    payload.get("worker_running"),
                    payload.get("state_stale"),
                )
            )
        if tool_name == "camera.restart":
            return ModelResponse(
                content=(
                    "\u6444\u50cf\u5934\u63a8\u7406\u5df2\u53d7\u63a7"
                    "\u91cd\u542f\uff1ageneration {0}\u2192{1}\uff0c"
                    "\u89c6\u89c9\u5e27{2}\uff0c\u6062\u590d\u7528\u65f6"
                    "{3}\u79d2\u3002API\u3001Docker\u548cJetson"
                    "\u672a\u91cd\u542f\u3002"
                ).format(
                    payload.get("before_generation"),
                    payload.get("after_generation"),
                    payload.get("vision_frame_id"),
                    payload.get("recovery_seconds"),
                )
            )
        if tool_name == "report.generate":
            return ModelResponse(
                content=(
                    "已确认并生成{0}的本地事件报告，共{1}条事件：{2}"
                ).format(
                    payload.get("date") or "指定日期",
                    payload.get("event_count", 0),
                    payload.get("report_path") or "未知路径",
                )
            )
        if tool_name == "event.acknowledge":
            if payload.get("already_acknowledged"):
                return ModelResponse(
                    content=(
                        "事件 {0} 此前已经确认处理，无需重复修改。"
                    ).format(payload.get("event_id"))
                )
            return ModelResponse(
                content=(
                    "已确认事件 {0} 为已处理，处理时间：{1}。"
                ).format(
                    payload.get("event_id"),
                    payload.get("acknowledged_at"),
                )
            )
        if tool_name == "system.get_health":
            checks = payload.get("checks") or {}
            memory = checks.get("memory") or {}
            disk = checks.get("disk") or {}
            temperature = checks.get("temperature") or {}
            load = checks.get("load") or {}
            return ModelResponse(
                content=(
                    "Jetson 运行状态：{0}。1分钟负载{1}，"
                    "内存使用{2}%，项目磁盘使用{3}%，"
                    "最高温度{4}°C。"
                ).format(
                    payload.get("status") or "UNKNOWN",
                    load.get("one_minute", "不可用"),
                    memory.get("used_percent", "不可用"),
                    disk.get("used_percent", "不可用"),
                    temperature.get(
                        "max_celsius",
                        "不可用",
                    ),
                )
            )
        if tool_name == "system.get_storage_usage":
            totals = payload.get("totals") or {}
            categories = payload.get("categories") or []
            largest = sorted(
                categories,
                key=lambda item: int(item.get("bytes") or 0),
                reverse=True,
            )[:3]
            category_text = "、".join(
                "{0} {1}字节".format(
                    item.get("name"),
                    item.get("bytes", 0),
                )
                for item in largest
                if int(item.get("bytes") or 0) > 0
            )
            return ModelResponse(
                content=(
                    "项目data目录共{0}个文件、{1}字节"
                    "{2}；扫描状态{3}。"
                ).format(
                    totals.get("file_count", 0),
                    totals.get("bytes", 0),
                    (
                        "，占用最多：" + category_text
                        if category_text
                        else ""
                    ),
                    payload.get("status") or "UNKNOWN",
                )
            )
        if tool_name == "system.preview_data_retention":
            candidates = payload.get("candidates") or {}
            return ModelResponse(
                content=(
                    "安全清理预览：{0}个旧文件、{1}字节"
                    "符合固定保留规则；当前仅预览，未删除"
                    "任何文件。扫描状态{2}。"
                ).format(
                    candidates.get("file_count", 0),
                    candidates.get("bytes", 0),
                    payload.get("status") or "UNKNOWN",
                )
            )
        if tool_name == "system.cleanup_retained_data":
            return ModelResponse(
                content=(
                    "已确认完成旧日志清理：删除{0}个文件、"
                    "释放{1}字节，失败{2}个；审计记录：{3}。"
                ).format(
                    payload.get("deleted_file_count", 0),
                    payload.get("deleted_bytes", 0),
                    payload.get("failed_file_count", 0),
                    payload.get("audit_path")
                    or "未知路径",
                )
            )
        if (
            tool_name
            == "system.get_retention_cleanup_history"
        ):
            totals = payload.get("totals") or {}
            records = payload.get("records") or []
            if not records:
                return ModelResponse(
                    content=(
                        "\u5c1a\u65e0\u5df2\u6267\u884c\u7684"
                        "\u65e7\u65e5\u5fd7\u6e05\u7406\u8bb0\u5f55\uff1b"
                        "\u67e5\u8be2\u4e3a\u53ea\u8bfb\uff0c"
                        "\u672a\u5220\u9664\u4efb\u4f55\u6587\u4ef6\u3002"
                    )
                )
            latest = records[0]
            return ModelResponse(
                content=(
                    "\u6e05\u7406\u5ba1\u8ba1\u5171{0}\u6b21\uff1a"
                    "\u7d2f\u8ba1\u5220\u9664{1}\u4e2a\u6587\u4ef6\u3001"
                    "\u91ca\u653e{2}\u5b57\u8282\uff0c\u5931\u8d25{3}"
                    "\u4e2a\uff1b\u6700\u8fd1\u4e00\u6b21{4}\uff0c"
                    "\u72b6\u6001{5}\u3002"
                ).format(
                    payload.get("record_count", 0),
                    totals.get("deleted_file_count", 0),
                    totals.get("deleted_bytes", 0),
                    totals.get("failed_file_count", 0),
                    latest.get("timestamp") or "unknown",
                    latest.get("status") or "UNKNOWN",
                )
            )
        if tool_name == "evidence.verify_event":
            event = payload.get("event") or {}
            evidence = payload.get("evidence") or []
            statuses = "\uff1b".join(
                "{0}={1}".format(
                    item.get("kind") or "unknown",
                    item.get("status") or "UNKNOWN",
                )
                for item in evidence
            )
            if not statuses:
                statuses = "\u65e0\u8bc1\u636e\u5f15\u7528"
            return ModelResponse(
                content=(
                    "\u4e8b\u4ef6{0}\u8bc1\u636e\u6821\u9a8c\uff1a"
                    "\u72b6\u6001{1}\uff0c\u5f15\u7528{2}\u4e2a\u3001"
                    "\u6709\u6548{3}\u4e2a\u3001\u95ee\u9898{4}"
                    "\u4e2a\uff1b{5}\u3002"
                ).format(
                    event.get("event_id") or "unknown",
                    payload.get("status") or "UNKNOWN",
                    payload.get("referenced_evidence_count", 0),
                    payload.get("valid_evidence_count", 0),
                    payload.get("issue_count", 0),
                    statuses,
                )
            )
        if tool_name == "evidence.verify_recent":
            return ModelResponse(
                content=(
                    "\u8fd1\u671f\u4e8b\u4ef6\u8bc1\u636e\u5b8c\u6574"
                    "\u6027\uff1a\u72b6\u6001{0}\uff0c\u68c0\u67e5"
                    "{1}\u6761\u4e8b\u4ef6\u3001{2}\u4e2a\u8bc1\u636e"
                    "\u5f15\u7528\uff0c\u6709\u6548{3}\u4e2a\uff0c"
                    "\u95ee\u9898{4}\u4e2a\u3002"
                ).format(
                    payload.get("status") or "UNKNOWN",
                    payload.get("checked_event_count", 0),
                    payload.get("referenced_evidence_count", 0),
                    payload.get("valid_evidence_count", 0),
                    payload.get("issue_count", 0),
                )
            )
        if tool_name == "event.query":
            events = payload.get("events") or []
            window = payload.get("window") or {}
            filters = payload.get("filters") or {}
            window_prefix = (
                "\u6700\u8fd1{0}\u5206\u949f".format(
                    window.get("minutes")
                )
                if window.get("minutes") is not None
                else ""
            )
            if not events:
                return ModelResponse(
                    content=(
                        "{0}\u6ca1\u6709\u67e5\u5230"
                        "\u7b26\u5408\u6761\u4ef6\u7684"
                        "\u5386\u53f2\u4e8b\u4ef6\u3002"
                    ).format(
                        window_prefix
                        + "\uff1a"
                        if window_prefix
                        else ""
                    )
                )
            descriptions = [
                "{0} {1} {2}".format(
                    event.get("timestamp") or "未知时间",
                    event.get("event_type") or "UNKNOWN",
                    event.get("object_class") or "unknown",
                )
                for event in events
            ]
            return ModelResponse(
                content="{0}{1}{2}查到{3}条事件：{4}".format(
                    (
                        window_prefix + "\uff1a"
                        if window_prefix
                        else ""
                    ),
                    (
                        "\u5f85\u5904\u7406"
                        if filters.get("status") == "OPEN"
                        else (
                            "\u5df2\u5904\u7406"
                            if filters.get("status")
                            == "ACKNOWLEDGED"
                            else ""
                        )
                    ),
                    (
                        "{0}\u7ea7\u522b".format(
                            filters.get("severity")
                        )
                        if filters.get("severity")
                        else ""
                    ),
                    len(events),
                    "\uff1b".join(descriptions),
                )
            )
        if tool_name == "event.summarize":
            total = int(payload.get("total_events") or 0)
            window = payload.get("window") or {}
            minutes = window.get("minutes", 10)
            reference_baselines = (
                payload.get("reference_baselines") or {}
            )
            if (
                total == 0
                and not payload.get("comparison")
                and not reference_baselines
            ):
                return ModelResponse(
                    content=(
                        "最近{0}分钟没有符合条件的事件。"
                    ).format(minutes)
                )
            event_types = (
                payload.get("counts", {}).get(
                    "by_event_type",
                    [],
                )
                or []
            )
            type_text = "、".join(
                "{0}×{1}".format(
                    item.get("name") or "UNKNOWN",
                    item.get("count") or 0,
                )
                for item in event_types[:5]
            )
            timeline = payload.get("timeline") or {}
            buckets = timeline.get("buckets") or []
            peak = (
                max(
                    buckets,
                    key=lambda item: int(
                        item.get("count") or 0
                    ),
                )
                if buckets
                else None
            )
            comparison = payload.get("comparison") or {}
            comparison_text = ""
            if comparison:
                largest_change = (
                    comparison.get(
                        "largest_event_type_change"
                    )
                    or {}
                )
                contributor_text = ""
                if largest_change:
                    contributor_text = (
                        "\uff0c\u4e3b\u8981\u53d8\u5316\u6765\u81ea"
                        "{0}{1}{2}\u6761"
                    ).format(
                        largest_change.get("name") or "UNKNOWN",
                        (
                            "\u589e\u52a0"
                            if largest_change.get(
                                "absolute_change",
                                0,
                            )
                            > 0
                            else (
                                "\u51cf\u5c11"
                                if largest_change.get(
                                    "absolute_change",
                                    0,
                                )
                                < 0
                                else "\u53d8\u5316"
                            )
                        ),
                        abs(
                            int(
                                largest_change.get(
                                    "absolute_change",
                                    0,
                                )
                            )
                        ),
                    )
                assessment = comparison.get("assessment") or {}
                assessment_text = ""
                if assessment:
                    assessment_text = (
                        "\uff0c\u53d8\u5316\u8bc4\u4f30{0}"
                        "\uff08{1}\uff09"
                    ).format(
                        assessment.get("status") or "UNKNOWN",
                        (
                            "\u5df2\u8d85\u8fc7\u9608\u503c"
                            if assessment.get(
                                "threshold_exceeded"
                            )
                            else "\u672a\u8d85\u8fc7\u9608\u503c"
                        ),
                    )
                significant_event_types = (
                    (
                        comparison.get(
                            "significant_contributors"
                        )
                        or {}
                    ).get("by_event_type")
                    or []
                )
                significant_text = (
                    "\uff0c\u5206\u7ec4\u663e\u8457\u53d8\u5316"
                    "{0}\u9879{1}"
                ).format(
                    len(significant_event_types),
                    (
                        "\uff0c\u9996\u9879{0}".format(
                            significant_event_types[0].get(
                                "name"
                            )
                            or "UNKNOWN"
                        )
                        if significant_event_types
                        else ""
                    ),
                )
                event_type_structure = (
                    (
                        comparison.get("structural_change")
                        or {}
                    ).get("by_event_type")
                    or {}
                )
                structural_text = ""
                if event_type_structure:
                    structural_text = (
                        "\uff0c\u7c7b\u578b\u53d8\u5316\u62b5\u6d88"
                        "{0}\u6761\uff08{1}\uff09"
                    ).format(
                        event_type_structure.get(
                            "offsetting_events",
                            0,
                        ),
                        event_type_structure.get("status")
                        or "UNKNOWN",
                    )
                previous_window = (
                    comparison.get("previous_window") or {}
                )
                alignment_text = ""
                if previous_window.get("offset_minutes"):
                    alignment_text = (
                        "\uff0c\u5bf9\u6bd4\u504f\u79fb{0}\u5206\u949f"
                        "\uff08{1}\uff09"
                    ).format(
                        previous_window.get("offset_minutes"),
                        previous_window.get("alignment")
                        or "UNKNOWN",
                    )
                comparison_text = (
                    "\uff1b\u8f83\u524d\u4e00\u65f6\u6bb5{0}{1}"
                    "\u6761{2}{3}{4}{5}{6}"
                ).format(
                    (
                        "\u589e\u52a0"
                        if comparison.get("absolute_change", 0) > 0
                        else (
                            "\u51cf\u5c11"
                            if comparison.get(
                                "absolute_change",
                                0,
                            )
                            < 0
                            else "\u53d8\u5316"
                        )
                    ),
                    abs(
                        int(
                            comparison.get(
                                "absolute_change",
                                0,
                            )
                        )
                    ),
                    contributor_text,
                    assessment_text,
                    significant_text,
                    structural_text,
                    alignment_text,
                )
            if reference_baselines:
                baseline_rows = (
                    reference_baselines.get("baselines") or []
                )
                change_from_average = float(
                    reference_baselines.get(
                        "change_from_average",
                        0,
                    )
                )
                comparison_text += (
                    "\uff1b\u5386\u53f2\u53cc\u57fa\u7ebf\u5747\u503c"
                    "{0}\u6761\uff0c\u5f53\u524d\u8f83\u5747\u503c"
                    "{1}{2}\u6761\uff08{3}\uff09\uff0c\u57fa\u7ebf"
                    "{4}\u4e2a\uff0c\u8bc4\u4f30{5}\uff0c"
                    "\u4e00\u81f4\u6027{6}"
                ).format(
                    reference_baselines.get(
                        "baseline_average_total",
                        0,
                    ),
                    (
                        "\u589e\u52a0"
                        if change_from_average > 0
                        else (
                            "\u51cf\u5c11"
                            if change_from_average < 0
                            else "\u53d8\u5316"
                        )
                    ),
                    abs(change_from_average),
                    reference_baselines.get("direction")
                    or "UNKNOWN",
                    len(baseline_rows),
                    (
                        (
                            reference_baselines.get(
                                "assessment"
                            )
                            or {}
                        ).get("status")
                        or "UNKNOWN"
                    ),
                    (
                        (
                            reference_baselines.get(
                                "consistency"
                            )
                            or {}
                        ).get("status")
                        or "UNKNOWN"
                    ),
                )
            return ModelResponse(
                content=(
                    "最近{0}分钟共发生{1}条事件"
                    "{2}{3}{4}。"
                ).format(
                    minutes,
                    total,
                    (
                        "：" + type_text
                        if type_text
                        else ""
                    ),
                    (
                        "；峰值时段{0}，{1}条".format(
                            peak.get("start"),
                            peak.get("count"),
                        )
                        if peak is not None
                        else ""
                    ),
                    comparison_text,
                )
            )
        if tool_name == "event.get_detail":
            details = payload.get("details") or {}
            detail_text = "，".join(
                "{0}={1}".format(key, details[key])
                for key in sorted(details)
            )
            evidence_urls = payload.get("evidence_urls") or {}
            return ModelResponse(
                content=(
                    "事件{0}：{1}，时间{2}，目标{3}，区域{4}，"
                    "严重级别{5}，处理状态{6}{7}；证据{8}。"
                ).format(
                    payload.get("event_id"),
                    payload.get("event_type"),
                    payload.get("timestamp"),
                    payload.get("object_class"),
                    payload.get("zone_name")
                    or payload.get("zone_id"),
                    payload.get("severity"),
                    payload.get("disposition_status"),
                    (
                        "，详情" + detail_text
                        if detail_text
                        else ""
                    ),
                    (
                        "可用"
                        if evidence_urls
                        else "不可用"
                    ),
                )
            )
        if tool_name == "vision.get_people_count":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能把其中的人数当作"
                        "当前现场人数。"
                    )
                )
            return ModelResponse(
                content="当前检测到{0}人。".format(
                    payload.get("current_people", 0)
                )
            )
        if tool_name == "weather.get_current":
            location = payload.get("location") or {}
            current = payload.get("current") or {}
            place = "，".join(
                str(value)
                for value in (
                    location.get("name"),
                    location.get("admin1"),
                    location.get("country"),
                )
                if value
            )
            return ModelResponse(
                content=(
                    "{0}当前天气：{1}，气温{2}°C，体感{3}°C，"
                    "湿度{4}%，降水{5}毫米，风速{6}公里/小时。"
                ).format(
                    place or "所选城市",
                    current.get("condition") or "unknown",
                    current.get("temperature_c"),
                    current.get("apparent_temperature_c"),
                    current.get("relative_humidity_percent"),
                    current.get("precipitation_mm"),
                    current.get("wind_speed_kmh"),
                )
            )
        if tool_name == "vision.get_current_objects":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能把其中的物品当作"
                        "当前现场物品。"
                    )
                )
            objects = payload.get("objects") or []
            if not objects:
                return ModelResponse(
                    content="当前没有检测到稳定物品。"
                )
            return ModelResponse(
                content="当前稳定物品：{0}。".format(
                    "，".join(
                        "{0}×{1}".format(
                            item.get("class_name"),
                            item.get("count"),
                        )
                        for item in objects
                    )
                )
            )
        if tool_name == "vision.count_objects":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能把即时检测数量"
                        "当作当前画面计数。"
                    )
                )
            counts = payload.get("counts") or []
            zone_text = (
                "，区域{0}".format(payload.get("selected_zone_id"))
                if payload.get("selected_zone_id")
                else ""
            )
            return ModelResponse(
                content=(
                    "当前帧目标计数（最低置信度{0}{1}）：{2}，"
                    "合计{3}个。"
                ).format(
                    payload.get("minimum_confidence", 0.0),
                    zone_text,
                    "，".join(
                        "{0}×{1}".format(
                            item.get("class_name"),
                            item.get("count", 0),
                        )
                        for item in counts
                    ),
                    payload.get("total_count", 0),
                )
            )
        if tool_name == "vision.get_track_history":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能把轨迹摘要当作"
                        "当前目标轨迹。"
                    )
                )
            tracks = payload.get("tracks") or []
            if not tracks:
                return ModelResponse(
                    content="当前保留轨迹中没有匹配目标。"
                )
            summaries = []
            for track in tracks:
                zones = track.get("current_zone_ids") or []
                zone_text = (
                    "，当前区域{0}".format(",".join(zones))
                    if zones
                    else ""
                )
                summaries.append(
                    "track {0}（{1}）：{2}，位移{3}，"
                    "{4}次观察{5}".format(
                        track.get("track_id"),
                        track.get("class_name"),
                        track.get("movement"),
                        track.get("displacement"),
                        track.get("observation_count"),
                        zone_text,
                    )
                )
            return ModelResponse(
                content="当前轨迹摘要：{0}。".format(
                    "；".join(summaries)
                )
            )
        if tool_name == "inventory.get_current_state":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能把其中的库存数量"
                        "当作当前现场库存。"
                    )
                )
            items = payload.get("items") or []
            selected = payload.get("selected_object_class")
            if selected and items:
                item = items[0]
                track_ids = item.get("active_track_ids") or []
                track_text = (
                    "，稳定轨迹ID为{0}".format(
                        "、".join(str(value) for value in track_ids)
                    )
                    if track_ids
                    else "，当前没有稳定轨迹ID"
                )
                return ModelResponse(
                    content=(
                        "{0}：稳定库存{1}，当前可见{2}{3}。"
                    ).format(
                        item.get("class_name"),
                        item.get("current_count", 0),
                        item.get("visible_count", 0),
                        track_text,
                    )
                )
            nonzero_items = [
                item
                for item in items
                if int(item.get("current_count") or 0) > 0
            ]
            if not nonzero_items:
                return ModelResponse(
                    content=(
                        "当前所有已配置库存类别的稳定数量均为0。"
                    )
                )
            return ModelResponse(
                content="当前稳定库存：{0}。".format(
                    "，".join(
                        "{0}×{1}（可见{2}）".format(
                            item.get("class_name"),
                            item.get("current_count", 0),
                            item.get("visible_count", 0),
                        )
                        for item in nonzero_items
                    )
                )
            )
        if tool_name == "inventory.compare_state":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能用它核对当前库存。"
                    )
                )
            comparisons = payload.get("comparisons") or []
            if payload.get("matches"):
                return ModelResponse(
                    content="库存核对一致：{0}。".format(
                        "，".join(
                            "{0}期望{1}、当前{2}".format(
                                item.get("class_name"),
                                item.get("expected_count", 0),
                                item.get("current_count", 0),
                            )
                            for item in comparisons
                        )
                    )
                )
            descriptions = []
            for item in comparisons:
                if item.get("matches"):
                    continue
                difference = (
                    "缺少{0}".format(item.get("missing_count"))
                    if int(item.get("missing_count") or 0) > 0
                    else "多出{0}".format(item.get("extra_count"))
                )
                descriptions.append(
                    "{0}期望{1}、当前{2}，{3}".format(
                        item.get("class_name"),
                        item.get("expected_count", 0),
                        item.get("current_count", 0),
                        difference,
                    )
                )
            return ModelResponse(
                content="库存核对不一致：{0}。".format(
                    "；".join(descriptions)
                )
            )
        if tool_name == "inventory.get_removed_items":
            removals = payload.get("removals") or []
            window_minutes = payload.get("window_minutes", 10)
            if not removals:
                return ModelResponse(
                    content=(
                        "最近{0}分钟没有查到已确认的物品移除事件。"
                    ).format(window_minutes)
                )
            descriptions = [
                "{0}移走{1}个{2}".format(
                    item.get("timestamp") or "未知时间",
                    item.get("removed_units", 1),
                    item.get("object_class") or "unknown",
                )
                for item in removals
            ]
            return ModelResponse(
                content=(
                    "最近{0}分钟查到{1}条物品移除事件，共移走"
                    "{2}件：{3}。"
                ).format(
                    window_minutes,
                    len(removals),
                    payload.get("total_removed_units", 0),
                    "；".join(descriptions),
                )
            )
        if tool_name == "vision.get_zone_status":
            if payload.get("stale"):
                return ModelResponse(
                    content=(
                        "视觉状态已经过期，不能把区域计数当作"
                        "当前现场状态。"
                    )
                )
            zones = payload.get("zones") or []
            if not zones:
                return ModelResponse(
                    content="当前没有可用的区域统计。"
                )
            return ModelResponse(
                content="当前区域状态：{0}。".format(
                    "；".join(
                        "{0}（{1}）计数{2}".format(
                            zone.get("name"),
                            zone.get("zone_id"),
                            zone.get("current_count", 0),
                        )
                        for zone in zones
                    )
                )
            )
        return ModelResponse(content="工具调用已经完成。")

    @staticmethod
    def _contains_any(message, keywords):
        return any(keyword in message for keyword in keywords)

    @staticmethod
    def _extract_memory_record(message):
        english = re.search(
            r"\b(?:please\s+)?remember(?:\s+that)?\s+"
            r"(?:my\s+)?(.{1,80}?)\s+(?:is|=)\s+(.{1,500})$",
            message,
        )
        if english:
            key = english.group(1).strip(" .?!")
            value = english.group(2).strip(" .?!")
        else:
            chinese = re.search(
                r"(?:请)?记住(?:我的)?(.{1,80}?)(?:是|为|=)"
                r"(.{1,500})$",
                message,
            )
            if chinese is None:
                return None
            key = chinese.group(1).strip(" ，,。！？?!")
            value = chinese.group(2).strip(" ，,。！？?!")
        if not key or not value:
            return None
        preference_words = (
            "prefer",
            "preferred",
            "preference",
            "偏好",
            "喜欢",
            "习惯",
        )
        return {
            "kind": (
                "PREFERENCE"
                if any(word in key for word in preference_words)
                else "FACT"
            ),
            "key": key,
            "value": value,
        }

    @classmethod
    def _memory_forget_requested(cls, message):
        return cls._contains_any(
            message,
            (
                "forget memory",
                "forget my",
                "delete memory",
                "remove memory",
                "忘记",
                "删除记忆",
                "清除记忆",
            ),
        )

    @classmethod
    def _memory_search_requested(cls, message):
        return cls._contains_any(
            message,
            (
                "what do you remember",
                "what did i tell you",
                "long-term memory",
                "remember about me",
                "记得什么",
                "长期记忆",
                "我告诉过你",
                "我的偏好",
            ),
        )

    @staticmethod
    def _extract_memory_query(message):
        value = message
        for phrase in (
            "what do you remember about",
            "what did i tell you about",
            "remember about me",
            "forget memory",
            "forget my",
            "delete memory",
            "remove memory",
            "请忘记",
            "忘记我的",
            "忘记",
            "删除记忆",
            "清除记忆",
            "你记得",
            "关于我的",
            "我的",
            "吗",
        ):
            value = value.replace(phrase, " ")
        value = " ".join(value.strip(" ，,。！？?!").split())
        return value[:100] if value else None

    @staticmethod
    def _extract_weather_location(message):
        english = re.search(
            r"\bweather\s+(?:in|for)\s+(.{2,40})",
            message,
        )
        if english:
            return english.group(1).strip(" .?!")

        marker_positions = [
            position
            for position in (
                message.find("天气"),
                message.find("气温"),
            )
            if position >= 0
        ]
        if not marker_positions:
            return None
        prefix = message[: min(marker_positions)]
        for phrase in (
            "请问",
            "请帮我",
            "帮我",
            "查询",
            "查一下",
            "看看",
            "告诉我",
        ):
            prefix = prefix.replace(phrase, "")
        prefix = prefix.strip(" ，,。！？?!")
        for suffix in ("今天", "现在", "当前", "当地", "的"):
            if prefix.endswith(suffix):
                prefix = prefix[: -len(suffix)].strip()
        if (
            2 <= len(prefix) <= 40
            and not any(
                word in prefix
                for word in (
                    "今天",
                    "明天",
                    "现在",
                    "当前",
                    "这里",
                    "本地",
                )
            )
        ):
            return prefix
        return None

    @staticmethod
    def _event_severity(message):
        checks = (
            (
                "CRITICAL",
                (
                    "critical events",
                    "critical severity",
                    "\u4e25\u91cd\u7ea7\u522b",
                    "\u5371\u6025\u7ea7\u522b",
                ),
            ),
            (
                "HIGH",
                (
                    "high severity",
                    "high events",
                    "\u9ad8\u4e25\u91cd\u7ea7\u522b",
                    "\u9ad8\u7ea7\u522b\u4e8b\u4ef6",
                ),
            ),
            (
                "MEDIUM",
                (
                    "medium severity",
                    "medium events",
                    "\u4e2d\u7b49\u4e25\u91cd\u7ea7\u522b",
                    "\u4e2d\u7b49\u7ea7\u522b\u4e8b\u4ef6",
                ),
            ),
            (
                "INFO",
                (
                    "info events",
                    "info severity",
                    "\u4fe1\u606f\u7ea7\u522b",
                    "\u4fe1\u606f\u7ea7\u4e8b\u4ef6",
                ),
            ),
        )
        for severity, keywords in checks:
            if any(keyword in message for keyword in keywords):
                return severity
        return None

    @staticmethod
    def _extract_inventory_class(message):
        aliases = (
            ("cell phone", ("cell phone", "手机")),
            ("traffic light", ("traffic light", "交通灯")),
            ("dining table", ("dining table", "餐桌")),
            ("potted plant", ("potted plant", "盆栽")),
            ("bottle", ("bottle", "瓶子", "瓶")),
            ("cup", ("cup", "杯子")),
            ("laptop", ("laptop", "笔记本电脑", "笔记本")),
            ("backpack", ("backpack", "背包")),
            ("book", ("book", "书")),
            ("chair", ("chair", "椅子")),
            ("tv", ("television", "电视", "tv")),
        )
        for class_name, keywords in aliases:
            if any(keyword in message for keyword in keywords):
                return class_name
        return None
