import unittest

from packages.harness.tool_router import (
    ToolRouteError,
    ToolSchemaRouter,
)


def schema(name, description="", confirmation=False):
    return {
        "name": name,
        "description": description,
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
        "annotations": {
            "riskLevel": "L1" if confirmation else "L0",
            "requiresConfirmation": confirmation,
        },
    }


CATALOG = [
    schema("camera.capture_snapshot", confirmation=True),
    schema("camera.get_status", "camera supervisor device health"),
    schema("camera.restart", confirmation=True),
    schema("event.get_detail", "exact event detail"),
    schema("event.query", "query recent structured events"),
    schema("event.summarize", "summarize event trends"),
    schema("inventory.compare_state", "compare inventory counts"),
    schema("memory.forget", confirmation=True),
    schema("memory.search", "search confirmed memory"),
    schema("system.cleanup_retained_data", confirmation=True),
    schema("system.preview_data_retention", "preview retention"),
    schema("vision.get_people_count", "confirmed people count"),
    schema("vision.get_zone_status", "current zone occupancy"),
    schema("weather.get_current", "current weather forecast"),
]


class ToolSchemaRouterTests(unittest.TestCase):
    def setUp(self):
        self.router = ToolSchemaRouter(max_tools=6)

    def test_routes_common_chinese_paraphrase_to_one_tool(self):
        route = self.router.route(
            "摄像头里面现在站着几位？", CATALOG
        )
        self.assertEqual(
            route["selected_tools"],
            ["vision.get_people_count"],
        )
        self.assertEqual(route["mode"], "DETERMINISTIC")
        self.assertGreater(route["schema_reduction_percent"], 80)

    def test_generic_instruction_words_do_not_add_event_query(self):
        catalog = list(CATALOG)
        catalog[4] = schema(
            "event.query",
            (
                "Query recent structured vision events. "
                "object_class must use an exact label such as "
                "bottle or camera."
            ),
        )

        route = self.router.route(
            (
                "Use the tool to confirm how many people are "
                "currently in the camera view."
            ),
            catalog,
        )

        self.assertEqual(
            route["selected_tools"],
            ["vision.get_people_count"],
        )

    def test_routes_weather_without_vision_catalog(self):
        route = self.router.route("武汉今天天气怎么样？", CATALOG)
        self.assertEqual(
            route["selected_tools"], ["weather.get_current"]
        )

    def test_general_question_exposes_no_tools(self):
        route = self.router.route("今天星期几？", CATALOG)
        self.assertEqual(route["mode"], "NO_MATCH")
        self.assertEqual(route["selected_tools"], [])
        self.assertFalse(route["fallback_used"])

    def test_sensitive_tool_requires_explicit_action_phrase(self):
        status_route = self.router.route("camera status", CATALOG)
        self.assertIn(
            "camera.get_status", status_route["selected_tools"]
        )
        self.assertNotIn(
            "camera.restart", status_route["selected_tools"]
        )
        restart_route = self.router.route(
            "please restart camera", CATALOG
        )
        self.assertIn(
            "camera.restart", restart_route["selected_tools"]
        )

    def test_routes_dependencies_inside_same_bound(self):
        memory_route = self.router.route(
            "请忘记这条记忆", CATALOG
        )
        self.assertEqual(
            memory_route["selected_tools"],
            ["memory.forget", "memory.search"],
        )
        cleanup_route = self.router.route(
            "执行数据清理", CATALOG
        )
        self.assertEqual(
            cleanup_route["selected_tools"],
            [
                "system.cleanup_retained_data",
                "system.preview_data_retention",
            ],
        )

    def test_skill_required_tools_are_pinned_exactly(self):
        route = self.router.route(
            "anything",
            CATALOG,
            required_tools=("event.query", "event.get_detail"),
        )
        self.assertEqual(route["mode"], "SKILL_PINNED")
        self.assertEqual(
            route["selected_tools"],
            ["event.get_detail", "event.query"],
        )

    def test_prior_context_hint_supports_short_follow_up(self):
        route = self.router.route(
            "what about now?",
            CATALOG,
            context_hints=("How many people are in the camera?",),
        )
        self.assertIn(
            "vision.get_people_count", route["selected_tools"]
        )

    def test_rejects_tampered_or_oversized_route(self):
        route = self.router.route("recent events", CATALOG)
        route["selected_tools"] = ["system.shell"]
        with self.assertRaises(ToolRouteError):
            self.router.validate_route(route, CATALOG)
        with self.assertRaises(ValueError):
            ToolSchemaRouter(max_tools=9)

    def test_select_schemas_returns_only_routed_tools(self):
        route = self.router.route("event trend", CATALOG)
        selected = self.router.select_schemas(route, CATALOG)
        self.assertEqual(
            [item["name"] for item in selected],
            ["event.summarize"],
        )


if __name__ == "__main__":
    unittest.main()
