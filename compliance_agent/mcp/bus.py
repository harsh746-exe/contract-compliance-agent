"""In-process MCP message bus."""

from __future__ import annotations

from dataclasses import asdict, is_dataclass
import logging
from collections import defaultdict
from typing import Awaitable, Callable, Optional

from .protocol import AgentCard, MCPMessage, MessageType

logger = logging.getLogger(__name__)

MessageHandler = Callable[[MCPMessage], Awaitable[Optional[MCPMessage]]]


class MCPBus:
    """Simple in-process message bus with audit logging."""

    def __init__(self):
        self._agents: dict[str, AgentCard] = {}
        self._handlers: dict[str, MessageHandler] = {}
        self._message_log: list[MCPMessage] = []
        self._subscribers: dict[MessageType, list[Callable[[MCPMessage], None]]] = defaultdict(list)

    def register_agent(self, card: AgentCard, handler: MessageHandler):
        """Register an agent card and its async message handler."""
        self._agents[card.agent_id] = card
        self._handlers[card.agent_id] = handler
        self.record_event(
            MessageType.SPAWN,
            sender="bus",
            recipient=card.agent_id,
            payload={
                "agent_id": card.agent_id,
                "role": card.role,
                "description": card.description,
                "tools": [tool.name for tool in card.tools],
            },
        )
        logger.info("Agent registered: %s (%s)", card.agent_id, card.role)

    def unregister_agent(self, agent_id: str, reason: str = "unregistered"):
        """Unregister an agent and record a termination event."""
        card = self._agents.pop(agent_id, None)
        self._handlers.pop(agent_id, None)
        self.record_event(
            MessageType.TERMINATE,
            sender="bus",
            recipient=agent_id,
            payload={
                "agent_id": agent_id,
                "role": getattr(card, "role", None),
                "reason": reason,
            },
        )
        logger.info("Agent unregistered: %s", agent_id)

    def discover_agents(self, role: str | None = None) -> list[AgentCard]:
        """Return registered agent cards, optionally filtered by role."""
        if role:
            return [agent for agent in self._agents.values() if agent.role == role]
        return list(self._agents.values())

    def discover_tools(self, tool_name: str | None = None) -> list[tuple[str, object]]:
        """Return available tools across agents, optionally filtered by name."""
        results = []
        for agent_id, card in self._agents.items():
            for tool in card.tools:
                if tool_name is None or tool.name == tool_name:
                    results.append((agent_id, tool))
        return results

    async def send(self, message: MCPMessage) -> MCPMessage | None:
        """Dispatch a message to its recipient and return any response."""
        self._append_message(message)

        handler = self._handlers.get(message.recipient)
        if handler is None:
            logger.error("No handler for agent %s", message.recipient)
            response = MCPMessage(
                type=MessageType.ERROR,
                sender="bus",
                recipient=message.sender,
                payload={"error": f"Agent {message.recipient} not found"},
                correlation_id=message.id,
            )
            self._append_message(response)
            return response

        response = await handler(message)
        if response:
            self._append_message(response)
        return response

    def subscribe(self, message_type: MessageType, callback: Callable[[MCPMessage], None]):
        """Subscribe a callback to receive bus messages of one type."""
        self._subscribers[message_type].append(callback)

    def record_event(
        self,
        message_type: MessageType,
        sender: str,
        recipient: str,
        payload: dict | None = None,
        correlation_id: str | None = None,
    ) -> MCPMessage:
        """Record a synthetic bus event and append it to the audit log."""
        message = MCPMessage(
            type=message_type,
            sender=sender,
            recipient=recipient,
            payload=payload or {},
            correlation_id=correlation_id,
        )
        self._append_message(message)
        return message

    def _append_message(self, message: MCPMessage) -> None:
        self._message_log.append(message)
        for callback in self._subscribers.get(message.type, []):
            callback(message)

    def get_audit_log(self) -> list[dict]:
        """Return a serializable list of recorded messages for audit output."""
        return [
            {
                "id": message.id,
                "type": message.type.value,
                "sender": message.sender,
                "recipient": message.recipient,
                "timestamp": message.timestamp,
                "payload": self._serialize_payload(message.payload),
                "payload_keys": list(message.payload.keys()),
                "correlation_id": message.correlation_id,
            }
            for message in self._message_log
        ]

    def _serialize_payload(self, payload):
        if is_dataclass(payload):
            return asdict(payload)
        if isinstance(payload, dict):
            return {key: self._serialize_payload(value) for key, value in payload.items()}
        if isinstance(payload, list):
            return [self._serialize_payload(item) for item in payload]
        return payload
