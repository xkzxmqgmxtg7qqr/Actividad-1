"""Identidad y roles de los agentes.

Cada agente del ecosistema tiene una identidad verificable: un id único,
un rol que determina qué políticas le aplican y la lista de capacidades
que declara ofrecer. Un agente no registrado no puede recibir tareas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    """Roles con niveles de confianza decrecientes."""

    SUPERVISOR = "supervisor"   # puede aprobar acciones de otros agentes
    TRUSTED = "trusted"         # agente interno verificado
    STANDARD = "standard"       # agente normal
    SANDBOXED = "sandboxed"     # agente externo o en evaluación


@dataclass(frozen=True)
class AgentIdentity:
    agent_id: str
    role: Role
    capabilities: tuple[str, ...] = field(default_factory=tuple)
    owner: str = "unknown"

    def has_capability(self, capability: str) -> bool:
        return capability in self.capabilities
