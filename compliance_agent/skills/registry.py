"""Central skill registry."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

logger = logging.getLogger(__name__)


@dataclass
class Skill:
    """One registered capability."""

    name: str
    description: str
    handler: Callable[..., Awaitable[Any]]
    input_schema: dict
    output_schema: dict
    version: str = "1.0"
    tags: list[str] = field(default_factory=list)
    llm_tier: str = "standard"


class SkillRegistry:
    """Lookup and invocation for skills."""

    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def register(self, skill: Skill):
        """Register a skill definition for later lookup and invocation."""
        self._skills[skill.name] = skill
        logger.info("Skill registered: %s v%s", skill.name, skill.version)

    def get(self, name: str) -> Skill | None:
        """Return one skill by name if it has been registered."""
        return self._skills.get(name)

    def search(self, tags: list[str] | None = None, keyword: str | None = None) -> list[Skill]:
        """Search skills by tags and/or keyword."""
        results = list(self._skills.values())
        if tags:
            results = [skill for skill in results if any(tag in skill.tags for tag in tags)]
        if keyword:
            lowered = keyword.lower()
            results = [
                skill
                for skill in results
                if lowered in skill.name.lower() or lowered in skill.description.lower()
            ]
        return results

    def list_all(self) -> list[str]:
        """List the names of all registered skills."""
        return list(self._skills.keys())

    async def invoke(self, name: str, **kwargs) -> Any:
        """Invoke a registered skill asynchronously with keyword arguments."""
        skill = self._skills.get(name)
        if not skill:
            raise KeyError(f"Skill '{name}' not found in registry. Available: {self.list_all()}")
        return await skill.handler(**kwargs)
