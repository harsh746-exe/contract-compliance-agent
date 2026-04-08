"""Convenience registry facade for MCP discovery."""

from __future__ import annotations

from .bus import MCPBus


class MCPRegistry:
    """Thin discovery wrapper around the MCP bus."""

    def __init__(self, bus: MCPBus):
        self.bus = bus

    def list_agents(self):
        return self.bus.discover_agents()

    def find_agents(self, role: str):
        return self.bus.discover_agents(role=role)

    def find_tools(self, tool_name: str | None = None):
        return self.bus.discover_tools(tool_name=tool_name)
