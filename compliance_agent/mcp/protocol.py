"""Protocol objects for in-process MCP communication."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
import uuid


class MessageType(Enum):
    GOAL = "goal"
    RESULT = "result"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STATUS = "status"
    ERROR = "error"
    SPAWN = "spawn"
    TERMINATE = "terminate"


@dataclass
class MCPMessage:
    """Structured message passed over the in-process MCP bus."""

    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    type: MessageType = MessageType.STATUS
    sender: str = ""
    recipient: str = ""
    payload: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    correlation_id: Optional[str] = None


@dataclass
class ToolSchema:
    """Public MCP tool contract exposed by an agent."""

    name: str
    description: str
    input_schema: dict
    output_schema: dict
    version: str = "1.0"


@dataclass
class AgentCard:
    """Agent discovery payload."""

    agent_id: str
    role: str
    description: str
    tools: list[ToolSchema] = field(default_factory=list)
    status: str = "idle"
