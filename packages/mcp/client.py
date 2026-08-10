"""Bounded synchronous MCP stdio client for local EdgeSentinel hosts."""

import json
import queue
import subprocess
import threading


class McpClientError(RuntimeError):
    def __init__(self, code, message, data=None):
        super(McpClientError, self).__init__(message)
        self.code = code
        self.message = str(message)
        self.data = data


class McpStdioClient(object):
    MAX_MESSAGE_BYTES = 1024 * 1024
    MAX_STDERR_BYTES = 64 * 1024

    def __init__(
        self,
        command,
        cwd=None,
        timeout_seconds=10.0,
        protocol_version="2025-11-25",
        client_name="edgesentinel-mcp-host",
    ):
        if not isinstance(command, (list, tuple)) or not command:
            raise ValueError("command must be a non-empty argv list")
        self.command = [str(value) for value in command]
        self.cwd = cwd
        self.timeout_seconds = float(timeout_seconds)
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        self.requested_protocol_version = str(protocol_version)
        self.client_name = str(client_name)
        self.process = None
        self.initialized = False
        self.protocol_version = None
        self.server_info = None
        self.capabilities = None
        self._next_request_id = 1
        self._responses = queue.Queue()
        self._reader_thread = None
        self._stderr_thread = None
        self._stderr_chunks = []
        self._stderr_size = 0
        self._write_lock = threading.Lock()

    def start(self):
        if self.process is not None:
            raise McpClientError(
                "CLIENT_STATE",
                "MCP client is already started",
            )
        self.process = subprocess.Popen(
            self.command,
            cwd=self.cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,
        )
        self._reader_thread = threading.Thread(
            target=self._read_stdout,
            name="edgesentinel-mcp-stdout",
        )
        self._reader_thread.daemon = True
        self._reader_thread.start()
        self._stderr_thread = threading.Thread(
            target=self._read_stderr,
            name="edgesentinel-mcp-stderr",
        )
        self._stderr_thread.daemon = True
        self._stderr_thread.start()
        try:
            initialized = self._request(
                "initialize",
                {
                    "protocolVersion": (
                        self.requested_protocol_version
                    ),
                    "capabilities": {},
                    "clientInfo": {
                        "name": self.client_name,
                        "version": "1.0.0",
                    },
                },
            )
            protocol_version = initialized.get(
                "protocolVersion"
            )
            server_info = initialized.get("serverInfo")
            capabilities = initialized.get("capabilities")
            if (
                not isinstance(protocol_version, str)
                or not isinstance(server_info, dict)
                or not isinstance(capabilities, dict)
            ):
                raise McpClientError(
                    "INVALID_INITIALIZE",
                    "MCP initialize response is invalid",
                )
            self.protocol_version = protocol_version
            self.server_info = dict(server_info)
            self.capabilities = dict(capabilities)
            self._notify("notifications/initialized")
            self.initialized = True
            return {
                "protocolVersion": self.protocol_version,
                "serverInfo": dict(self.server_info),
                "capabilities": dict(self.capabilities),
            }
        except Exception:
            self.close()
            raise

    def ping(self):
        self._require_initialized()
        return self._request("ping", {})

    def list_tools(self):
        self._require_capability("tools")
        return self._request("tools/list", {}).get("tools") or []

    def call_tool(self, name, arguments=None):
        self._require_capability("tools")
        return self._request(
            "tools/call",
            {
                "name": str(name),
                "arguments": arguments or {},
            },
        )

    def list_resources(self):
        self._require_capability("resources")
        return (
            self._request("resources/list", {}).get("resources")
            or []
        )

    def read_resource(self, uri):
        self._require_capability("resources")
        return self._request(
            "resources/read",
            {"uri": str(uri)},
        )

    def list_prompts(self):
        self._require_capability("prompts")
        return (
            self._request("prompts/list", {}).get("prompts")
            or []
        )

    def get_prompt(self, name, arguments=None):
        self._require_capability("prompts")
        return self._request(
            "prompts/get",
            {
                "name": str(name),
                "arguments": arguments or {},
            },
        )

    def close(self):
        process = self.process
        if process is None:
            return
        try:
            if process.stdin is not None:
                process.stdin.close()
        except OSError:
            pass
        try:
            process.wait(timeout=self.timeout_seconds)
        except subprocess.TimeoutExpired:
            process.terminate()
            try:
                process.wait(timeout=2.0)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=2.0)
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=1.0)
        if self._stderr_thread is not None:
            self._stderr_thread.join(timeout=1.0)
        for stream in (process.stdout, process.stderr):
            try:
                if stream is not None:
                    stream.close()
            except OSError:
                pass
        self.process = None
        self.initialized = False

    @property
    def stderr_text(self):
        return b"".join(self._stderr_chunks).decode(
            "utf-8",
            "replace",
        )

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.close()
        return False

    def _request(self, method, params):
        if self.process is None:
            raise McpClientError(
                "CLIENT_STATE",
                "MCP client is not started",
            )
        request_id = self._next_request_id
        self._next_request_id += 1
        self._write(
            {
                "jsonrpc": "2.0",
                "id": request_id,
                "method": str(method),
                "params": params,
            }
        )
        try:
            response = self._responses.get(
                timeout=self.timeout_seconds
            )
        except queue.Empty:
            raise McpClientError(
                "TIMEOUT",
                "MCP request timed out",
                {"method": str(method)},
            )
        if isinstance(response, McpClientError):
            raise response
        if response.get("id") != request_id:
            raise McpClientError(
                "RESPONSE_ID_MISMATCH",
                "MCP response ID does not match request",
            )
        if "error" in response:
            error = response.get("error") or {}
            raise McpClientError(
                error.get("code", "SERVER_ERROR"),
                error.get("message", "MCP server error"),
                error.get("data"),
            )
        result = response.get("result")
        if not isinstance(result, dict):
            raise McpClientError(
                "INVALID_RESPONSE",
                "MCP result must be an object",
            )
        return result

    def _notify(self, method, params=None):
        payload = {
            "jsonrpc": "2.0",
            "method": str(method),
        }
        if params is not None:
            payload["params"] = params
        self._write(payload)

    def _write(self, message):
        encoded = (
            json.dumps(
                message,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            + "\n"
        ).encode("utf-8")
        if len(encoded) > self.MAX_MESSAGE_BYTES:
            raise McpClientError(
                "MESSAGE_TOO_LARGE",
                "MCP request is too large",
            )
        process = self.process
        if (
            process is None
            or process.stdin is None
            or process.poll() is not None
        ):
            raise McpClientError(
                "SERVER_EXITED",
                "MCP server is not running",
            )
        try:
            with self._write_lock:
                process.stdin.write(encoded)
                process.stdin.flush()
        except (OSError, ValueError):
            raise McpClientError(
                "SERVER_EXITED",
                "MCP server closed its input",
            )

    def _read_stdout(self):
        while self.process is not None:
            raw = self.process.stdout.readline(
                self.MAX_MESSAGE_BYTES + 1
            )
            if not raw:
                break
            if len(raw) > self.MAX_MESSAGE_BYTES:
                self._responses.put(
                    McpClientError(
                        "MESSAGE_TOO_LARGE",
                        "MCP response is too large",
                    )
                )
                break
            try:
                response = json.loads(raw.decode("utf-8"))
            except (UnicodeDecodeError, ValueError):
                self._responses.put(
                    McpClientError(
                        "INVALID_RESPONSE",
                        "MCP response is not valid UTF-8 JSON",
                    )
                )
                break
            if not isinstance(response, dict):
                self._responses.put(
                    McpClientError(
                        "INVALID_RESPONSE",
                        "MCP response must be an object",
                    )
                )
                break
            self._responses.put(response)

    def _read_stderr(self):
        while self.process is not None:
            raw = self.process.stderr.read(4096)
            if not raw:
                break
            remaining = (
                self.MAX_STDERR_BYTES - self._stderr_size
            )
            if remaining > 0:
                chunk = raw[:remaining]
                self._stderr_chunks.append(chunk)
                self._stderr_size += len(chunk)

    def _require_initialized(self):
        if not self.initialized:
            raise McpClientError(
                "CLIENT_STATE",
                "MCP client is not initialized",
            )

    def _require_capability(self, name):
        self._require_initialized()
        if name not in (self.capabilities or {}):
            raise McpClientError(
                "CAPABILITY_UNAVAILABLE",
                "MCP capability is unavailable: {0}".format(name),
            )
