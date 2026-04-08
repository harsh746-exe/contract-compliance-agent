"""Base class for autonomous MCP agents."""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from ..llm import get_provider
from ..mcp.bus import MCPBus
from ..mcp.protocol import AgentCard, MCPMessage, MessageType, ToolSchema
from ..skills.registry import SkillRegistry

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """Common MCP-aware agent behavior."""

    def __init__(self, agent_id: str, role: str, description: str, bus: MCPBus, skill_registry: SkillRegistry):
        self.agent_id = agent_id
        self.role = role
        self.description = description
        self.bus = bus
        self.skills = skill_registry
        self.llm = get_provider()
        self.state: dict[str, Any] = {
            "status": "idle",
            "current_task": None,
            "history": [],
        }

        bus.register_agent(
            AgentCard(
                agent_id=agent_id,
                role=role,
                description=description,
                tools=self._declare_tools(),
            ),
            self.handle_message,
        )

    @abstractmethod
    def _declare_tools(self) -> list[ToolSchema]:
        """Declare the MCP tools the agent exposes."""

    @abstractmethod
    async def execute_goal(self, goal: dict) -> dict:
        """Autonomously complete the provided goal."""

    async def handle_message(self, message: MCPMessage) -> MCPMessage:
        if message.type == MessageType.GOAL:
            self.state["status"] = "busy"
            self.state["current_task"] = message.payload
            try:
                result = await self.execute_goal(message.payload)
                self.state["status"] = "idle"
                self.state["history"].append({"goal": message.payload, "result": "success"})
                return MCPMessage(
                    type=MessageType.RESULT,
                    sender=self.agent_id,
                    recipient=message.sender,
                    payload=result,
                    correlation_id=message.id,
                )
            except Exception as exc:
                logger.exception("Agent %s failed", self.agent_id)
                self.state["status"] = "error"
                return MCPMessage(
                    type=MessageType.ERROR,
                    sender=self.agent_id,
                    recipient=message.sender,
                    payload={"error": str(exc), "goal": message.payload},
                    correlation_id=message.id,
                )

        if message.type == MessageType.TOOL_CALL:
            tool_name = message.payload.get("tool")
            tool_args = message.payload.get("args", {})
            try:
                result = await self.skills.invoke(tool_name, **tool_args)
                return MCPMessage(
                    type=MessageType.TOOL_RESULT,
                    sender=self.agent_id,
                    recipient=message.sender,
                    payload={"tool": tool_name, "result": result},
                    correlation_id=message.id,
                )
            except Exception as exc:
                return MCPMessage(
                    type=MessageType.ERROR,
                    sender=self.agent_id,
                    recipient=message.sender,
                    payload={"tool": tool_name, "error": str(exc)},
                    correlation_id=message.id,
                )

        return MCPMessage(
            type=MessageType.ERROR,
            sender=self.agent_id,
            recipient=message.sender,
            payload={"error": f"Unhandled message type: {message.type.value}"},
            correlation_id=message.id,
        )

    async def use_skill(self, skill_name: str, **kwargs):
        call = self.bus.record_event(
            MessageType.TOOL_CALL,
            sender=self.agent_id,
            recipient=f"skill:{skill_name}",
            payload={"tool": skill_name, "args": kwargs},
        )
        try:
            result = await self.skills.invoke(skill_name, **kwargs)
            self.bus.record_event(
                MessageType.TOOL_RESULT,
                sender=f"skill:{skill_name}",
                recipient=self.agent_id,
                payload={"tool": skill_name, "result": result},
                correlation_id=call.id,
            )
            return result
        except Exception as exc:
            self.bus.record_event(
                MessageType.ERROR,
                sender=f"skill:{skill_name}",
                recipient=self.agent_id,
                payload={"tool": skill_name, "error": str(exc)},
                correlation_id=call.id,
            )
            raise

    async def ask_agent(self, recipient_id: str, goal: dict) -> MCPMessage | None:
        message = MCPMessage(
            type=MessageType.GOAL,
            sender=self.agent_id,
            recipient=recipient_id,
            payload=goal,
        )
        return await self.bus.send(message)

    def report_status(self, status_msg: str):
        logger.info("%s", status_msg)
        self.bus.record_event(
            MessageType.STATUS,
            sender=self.agent_id,
            recipient="broadcast",
            payload={"status": status_msg, "agent_state": self.state["status"]},
        )
