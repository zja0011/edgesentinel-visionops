"""Minimal UTF-8 MCP stdio server backed by the Harness registry."""

import json
import sys

from packages.harness.registry import ToolInvocationError
from packages.mcp.prompts import McpPromptError
from packages.mcp.resources import McpResourceError


class McpProtocolError(RuntimeError):
    def __init__(self, code, message, data=None):
        super(McpProtocolError, self).__init__(message)
        self.code = int(code)
        self.message = str(message)
        self.data = data


class EdgeSentinelMcpServer(object):
    SERVER_NAME = "edgesentinel-visionops"
    SERVER_VERSION = "1.0.0"
    PREFERRED_PROTOCOL_VERSION = "2025-11-25"
    SUPPORTED_PROTOCOL_VERSIONS = (
        "2025-11-25",
        "2025-06-18",
        "2025-03-26",
    )

    def __init__(
        self,
        registry,
        resource_provider=None,
        prompt_provider=None,
    ):
        self.registry = registry
        self.resource_provider = resource_provider
        self.prompt_provider = prompt_provider
        self.initialized = False
        self.client_ready = False
        self.protocol_version = None
        self._all_schemas = {
            schema["name"]: schema
            for schema in registry.schemas()
        }
        self._read_only_schemas = {
            name: schema
            for name, schema in self._all_schemas.items()
            if self._is_mcp_callable(schema)
        }

    @property
    def tool_count(self):
        return len(self._read_only_schemas)

    def handle_message(self, message):
        if not isinstance(message, dict):
            return self._error_response(
                None,
                -32600,
                "Invalid Request",
            )
        request_id = message.get("id")
        is_notification = "id" not in message
        try:
            if message.get("jsonrpc") != "2.0":
                raise McpProtocolError(
                    -32600,
                    "Invalid Request",
                )
            method = message.get("method")
            if not isinstance(method, str) or not method:
                raise McpProtocolError(
                    -32600,
                    "Invalid Request",
                )
            if method == "initialize":
                if is_notification:
                    return None
                result = self._initialize(message.get("params"))
            elif method == "notifications/initialized":
                if not self.initialized:
                    return None
                self.client_ready = True
                return None
            elif method == "notifications/cancelled":
                return None
            elif method == "ping":
                self._require_request(request_id)
                result = {}
            elif method == "tools/list":
                self._require_ready()
                self._require_request(request_id)
                result = self._list_tools(message.get("params"))
            elif method == "tools/call":
                self._require_ready()
                self._require_request(request_id)
                result = self._call_tool(message.get("params"))
            elif method == "resources/list":
                self._require_ready()
                self._require_request(request_id)
                result = self._list_resources(
                    message.get("params")
                )
            elif method == "resources/read":
                self._require_ready()
                self._require_request(request_id)
                result = self._read_resource(
                    message.get("params")
                )
            elif method == "prompts/list":
                self._require_ready()
                self._require_request(request_id)
                result = self._list_prompts(
                    message.get("params")
                )
            elif method == "prompts/get":
                self._require_ready()
                self._require_request(request_id)
                result = self._get_prompt(
                    message.get("params")
                )
            else:
                if is_notification:
                    return None
                raise McpProtocolError(
                    -32601,
                    "Method not found",
                )
            return {
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            }
        except McpProtocolError as error:
            if is_notification:
                return None
            return self._error_response(
                request_id,
                error.code,
                error.message,
                error.data,
            )

    def _initialize(self, params):
        if self.initialized:
            raise McpProtocolError(
                -32600,
                "Server is already initialized",
            )
        if not isinstance(params, dict):
            raise McpProtocolError(
                -32602,
                "Invalid initialize parameters",
            )
        requested = params.get("protocolVersion")
        if not isinstance(requested, str) or not requested:
            raise McpProtocolError(
                -32602,
                "protocolVersion is required",
            )
        client_info = params.get("clientInfo")
        capabilities = params.get("capabilities")
        if (
            not isinstance(client_info, dict)
            or not isinstance(capabilities, dict)
        ):
            raise McpProtocolError(
                -32602,
                "clientInfo and capabilities are required",
            )
        self.protocol_version = (
            requested
            if requested in self.SUPPORTED_PROTOCOL_VERSIONS
            else self.PREFERRED_PROTOCOL_VERSION
        )
        self.initialized = True
        server_capabilities = {
            "tools": {
                "listChanged": False,
            }
        }
        if self.resource_provider is not None:
            server_capabilities["resources"] = {
                "subscribe": False,
                "listChanged": False,
            }
        if self.prompt_provider is not None:
            server_capabilities["prompts"] = {
                "listChanged": False,
            }
        return {
            "protocolVersion": self.protocol_version,
            "capabilities": server_capabilities,
            "serverInfo": {
                "name": self.SERVER_NAME,
                "version": self.SERVER_VERSION,
            },
            "instructions": (
                "This local server exposes bounded EdgeSentinel "
                "resources, user-controlled prompt templates, and "
                "only L0 read-only tools. State-changing L1/L2 "
                "actions must use the confirmation-gated Agent API "
                "or Dashboard."
            ),
        }

    def _list_tools(self, params):
        if params is not None and not isinstance(params, dict):
            raise McpProtocolError(
                -32602,
                "Invalid tools/list parameters",
            )
        if isinstance(params, dict) and params.get("cursor"):
            raise McpProtocolError(
                -32602,
                "Pagination cursor is not supported",
            )
        return {
            "tools": [
                self._mcp_schema(self._read_only_schemas[name])
                for name in sorted(self._read_only_schemas)
            ]
        }

    def _call_tool(self, params):
        if not isinstance(params, dict):
            raise McpProtocolError(
                -32602,
                "Invalid tools/call parameters",
            )
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise McpProtocolError(
                -32602,
                "Tool name is required",
            )
        if not isinstance(arguments, dict):
            raise McpProtocolError(
                -32602,
                "Tool arguments must be an object",
            )
        if name not in self._all_schemas:
            try:
                self.registry.invoke(name, arguments)
            except ToolInvocationError:
                pass
            raise McpProtocolError(
                -32601,
                "Tool not found",
            )
        try:
            response = self.registry.invoke(name, arguments)
        except ToolInvocationError as error:
            failure = {
                "code": error.code,
                "message": error.message,
            }
            return {
                "content": [
                    {
                        "type": "text",
                        "text": self._compact_json(failure),
                    }
                ],
                "structuredContent": {"error": failure},
                "isError": True,
            }
        result = response.get("result") or {}
        return {
            "content": [
                {
                    "type": "text",
                    "text": self._compact_json(result),
                }
            ],
            "structuredContent": result,
            "isError": False,
            "_meta": {
                "io.edgesentinel/callId": response.get("call_id"),
            },
        }

    def _list_resources(self, params):
        if self.resource_provider is None:
            raise McpProtocolError(
                -32601,
                "Method not found",
            )
        self._validate_list_params(params, "resources/list")
        return {
            "resources": (
                self.resource_provider.list_resources()
            )
        }

    def _read_resource(self, params):
        if self.resource_provider is None:
            raise McpProtocolError(
                -32601,
                "Method not found",
            )
        if not isinstance(params, dict):
            raise McpProtocolError(
                -32602,
                "Invalid resources/read parameters",
            )
        uri = params.get("uri")
        if not isinstance(uri, str) or not uri:
            raise McpProtocolError(
                -32602,
                "Resource URI is required",
            )
        try:
            payload = self.resource_provider.read(uri)
        except McpResourceError as error:
            raise McpProtocolError(
                -32002 if error.not_found else -32603,
                (
                    "Resource not found"
                    if error.not_found
                    else "Internal error"
                ),
                {
                    "uri": uri,
                    "reason": str(error),
                },
            )
        return {
            "contents": [
                {
                    "uri": uri,
                    "mimeType": "application/json",
                    "text": self._compact_json(payload),
                }
            ]
        }

    def _list_prompts(self, params):
        if self.prompt_provider is None:
            raise McpProtocolError(
                -32601,
                "Method not found",
            )
        self._validate_list_params(params, "prompts/list")
        return {
            "prompts": self.prompt_provider.list_prompts()
        }

    def _get_prompt(self, params):
        if self.prompt_provider is None:
            raise McpProtocolError(
                -32601,
                "Method not found",
            )
        if not isinstance(params, dict):
            raise McpProtocolError(
                -32602,
                "Invalid prompts/get parameters",
            )
        name = params.get("name")
        arguments = params.get("arguments", {})
        if not isinstance(name, str) or not name:
            raise McpProtocolError(
                -32602,
                "Prompt name is required",
            )
        try:
            return self.prompt_provider.get(name, arguments)
        except McpPromptError as error:
            raise McpProtocolError(
                -32602,
                "Invalid prompt parameters",
                {
                    "name": name,
                    "reason": str(error),
                },
            )

    @staticmethod
    def _validate_list_params(params, method):
        if params is not None and not isinstance(params, dict):
            raise McpProtocolError(
                -32602,
                "Invalid {0} parameters".format(method),
            )
        if isinstance(params, dict) and params.get("cursor"):
            raise McpProtocolError(
                -32602,
                "Pagination cursor is not supported",
            )

    def _require_ready(self):
        if not self.initialized or not self.client_ready:
            raise McpProtocolError(
                -32002,
                "Server is not initialized",
            )

    @staticmethod
    def _require_request(request_id):
        if request_id is None or isinstance(request_id, bool):
            raise McpProtocolError(
                -32600,
                "A request ID is required",
            )
        if not isinstance(request_id, (str, int, float)):
            raise McpProtocolError(
                -32600,
                "Request ID is invalid",
            )

    @staticmethod
    def _is_mcp_callable(schema):
        annotations = schema.get("annotations") or {}
        return bool(
            annotations.get("readOnlyHint")
            and annotations.get("riskLevel") == "L0"
            and annotations.get("autoExecute")
            and not annotations.get("requiresConfirmation")
        )

    @staticmethod
    def _mcp_schema(schema):
        source_annotations = schema.get("annotations") or {}
        return {
            "name": schema["name"],
            "description": schema.get("description", ""),
            "inputSchema": schema["inputSchema"],
            "annotations": {
                "readOnlyHint": True,
                "destructiveHint": False,
                "idempotentHint": True,
                "openWorldHint": bool(
                    source_annotations.get("openWorldHint", False)
                ),
            },
        }

    @staticmethod
    def _compact_json(payload):
        return json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _error_response(request_id, code, message, data=None):
        error = {
            "code": int(code),
            "message": str(message),
        }
        if data is not None:
            error["data"] = data
        return {
            "jsonrpc": "2.0",
            "id": request_id,
            "error": error,
        }


class StdioTransport(object):
    MAX_MESSAGE_BYTES = 1024 * 1024

    def __init__(
        self,
        server,
        input_stream=None,
        output_stream=None,
    ):
        self.server = server
        self.input_stream = input_stream or getattr(
            sys.stdin,
            "buffer",
            sys.stdin,
        )
        self.output_stream = output_stream or getattr(
            sys.stdout,
            "buffer",
            sys.stdout,
        )

    def run(self):
        while True:
            line = self.input_stream.readline(
                self.MAX_MESSAGE_BYTES + 1
            )
            if not line:
                break
            if isinstance(line, str):
                raw = line.encode("utf-8")
            else:
                raw = line
            if len(raw) > self.MAX_MESSAGE_BYTES:
                response = EdgeSentinelMcpServer._error_response(
                    None,
                    -32600,
                    "Message is too large",
                )
            else:
                try:
                    message = json.loads(raw.decode("utf-8"))
                except (UnicodeDecodeError, ValueError):
                    response = (
                        EdgeSentinelMcpServer._error_response(
                            None,
                            -32700,
                            "Parse error",
                        )
                    )
                else:
                    if isinstance(message, list):
                        response = (
                            EdgeSentinelMcpServer._error_response(
                                None,
                                -32600,
                                "JSON-RPC batches are not supported",
                            )
                        )
                    else:
                        response = self.server.handle_message(
                            message
                        )
            if response is not None:
                self._write(response)
        return 0

    def _write(self, response):
        encoded = (
            json.dumps(
                response,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        try:
            self.output_stream.write(encoded)
        except TypeError:
            self.output_stream.write(encoded.decode("utf-8"))
        self.output_stream.flush()
