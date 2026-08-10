"""Local Model Context Protocol adapter for EdgeSentinel."""

from packages.mcp.client import McpClientError, McpStdioClient
from packages.mcp.host import EdgeSentinelMcpHost
from packages.mcp.prompts import EdgeSentinelPrompts
from packages.mcp.resources import EdgeSentinelResources
from packages.mcp.server import EdgeSentinelMcpServer, StdioTransport

__all__ = [
    "EdgeSentinelMcpServer",
    "EdgeSentinelMcpHost",
    "EdgeSentinelPrompts",
    "EdgeSentinelResources",
    "McpClientError",
    "McpStdioClient",
    "StdioTransport",
]
