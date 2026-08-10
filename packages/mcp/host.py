"""Read-only MCP Host boundary for EdgeSentinel."""

import json

from packages.mcp.client import McpClientError


class EdgeSentinelMcpHost(object):
    def __init__(
        self,
        client,
        allowed_open_world_tools=None,
    ):
        self.client = client
        self.allowed_open_world_tools = set(
            allowed_open_world_tools
            if allowed_open_world_tools is not None
            else ("weather.get_current",)
        )
        self.tools = {}
        self.resources = {}
        self.prompts = {}
        self.discovered = False

    def discover(self):
        tools = self.client.list_tools()
        resources = self.client.list_resources()
        prompts = self.client.list_prompts()
        self.tools = {}
        for schema in tools:
            name = schema.get("name")
            annotations = schema.get("annotations") or {}
            if (
                not isinstance(name, str)
                or not name
                or not annotations.get("readOnlyHint")
                or annotations.get("destructiveHint")
                or not annotations.get("idempotentHint")
            ):
                raise McpClientError(
                    "UNSAFE_DISCOVERY",
                    "MCP tool discovery contains an unsafe schema",
                )
            self.tools[name] = schema
        self.resources = {
            resource["uri"]: resource
            for resource in resources
            if (
                isinstance(resource, dict)
                and isinstance(resource.get("uri"), str)
                and resource["uri"].startswith("edgesentinel://")
            )
        }
        if len(self.resources) != len(resources):
            raise McpClientError(
                "UNSAFE_DISCOVERY",
                "MCP resources contain an untrusted URI",
            )
        self.prompts = {
            prompt["name"]: prompt
            for prompt in prompts
            if (
                isinstance(prompt, dict)
                and isinstance(prompt.get("name"), str)
                and prompt.get("name")
            )
        }
        if len(self.prompts) != len(prompts):
            raise McpClientError(
                "UNSAFE_DISCOVERY",
                "MCP prompt discovery is invalid",
            )
        self.discovered = True
        return {
            "tool_count": len(self.tools),
            "resource_count": len(self.resources),
            "prompt_count": len(self.prompts),
        }

    def call_tool(self, name, arguments=None):
        self._require_discovered()
        if name not in self.tools:
            raise McpClientError(
                "HOST_POLICY_DENIED",
                "tool was not discovered as L0 read-only",
                {"name": str(name)},
            )
        annotations = self.tools[name].get("annotations") or {}
        if (
            annotations.get("openWorldHint")
            and name not in self.allowed_open_world_tools
        ):
            raise McpClientError(
                "HOST_POLICY_DENIED",
                "open-world tool is not allowlisted by the host",
                {"name": str(name)},
            )
        result = self.client.call_tool(name, arguments or {})
        if result.get("isError"):
            error = (
                result.get("structuredContent") or {}
            ).get("error") or {}
            raise McpClientError(
                error.get("code", "TOOL_FAILED"),
                error.get("message", "MCP tool failed"),
            )
        structured = result.get("structuredContent")
        if not isinstance(structured, dict):
            raise McpClientError(
                "INVALID_TOOL_RESULT",
                "MCP tool result is not structured",
            )
        return structured

    def read_resource(self, uri):
        self._require_discovered()
        if uri not in self.resources:
            raise McpClientError(
                "HOST_POLICY_DENIED",
                "resource URI was not discovered",
                {"uri": str(uri)[:256]},
            )
        result = self.client.read_resource(uri)
        contents = result.get("contents") or []
        if len(contents) != 1:
            raise McpClientError(
                "INVALID_RESOURCE_RESULT",
                "MCP resource must return one content item",
            )
        content = contents[0]
        if (
            content.get("uri") != uri
            or content.get("mimeType") != "application/json"
            or not isinstance(content.get("text"), str)
        ):
            raise McpClientError(
                "INVALID_RESOURCE_RESULT",
                "MCP resource content is invalid",
            )
        try:
            payload = json.loads(content["text"])
        except ValueError:
            raise McpClientError(
                "INVALID_RESOURCE_RESULT",
                "MCP resource is not valid JSON",
            )
        if not isinstance(payload, dict):
            raise McpClientError(
                "INVALID_RESOURCE_RESULT",
                "MCP resource JSON must be an object",
            )
        return payload

    def get_prompt(self, name, arguments=None):
        self._require_discovered()
        if name not in self.prompts:
            raise McpClientError(
                "HOST_POLICY_DENIED",
                "prompt was not discovered",
                {"name": str(name)},
            )
        result = self.client.get_prompt(name, arguments or {})
        messages = result.get("messages")
        if not isinstance(messages, list) or not messages:
            raise McpClientError(
                "INVALID_PROMPT_RESULT",
                "MCP prompt has no messages",
            )
        for message in messages:
            content = message.get("content") or {}
            if (
                message.get("role") not in ("user", "assistant")
                or content.get("type") != "text"
                or not isinstance(content.get("text"), str)
            ):
                raise McpClientError(
                    "INVALID_PROMPT_RESULT",
                    "MCP prompt message is invalid",
                )
        return result

    def _require_discovered(self):
        if not self.discovered:
            raise McpClientError(
                "HOST_STATE",
                "MCP Host discovery has not completed",
            )
