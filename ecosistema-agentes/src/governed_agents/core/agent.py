"""Contrato base de un agente gobernado.

Principio central del ecosistema: los agentes **no ejecutan acciones
directamente**. Reciben un :class:`ActionContext` desde el orquestador y
toda acción sobre recursos (buscar, escribir, enviar...) pasa por él, de
modo que la gobernanza es imposible de eludir desde el código del agente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from governed_agents.core.message import ActionRequest, Task
from governed_agents.governance.identity import AgentIdentity


class ActionDenied(Exception):
    """La acción fue rechazada por la gobernanza."""

    def __init__(self, request: ActionRequest, reason: str) -> None:
        super().__init__(f"Acción '{request.action}' sobre '{request.resource}' denegada: {reason}")
        self.request = request
        self.reason = reason


class ActionPendingApproval(Exception):
    """La acción quedó encolada a la espera de aprobación humana."""

    def __init__(self, request: ActionRequest) -> None:
        super().__init__(
            f"Acción '{request.action}' sobre '{request.resource}' pendiente de aprobación humana"
        )
        self.request = request


class ActionContext:
    """Puerta de acceso del agente al mundo exterior, mediada por gobernanza."""

    def __init__(
        self,
        agent_id: str,
        authorize: Callable[[ActionRequest, float], Any],
    ) -> None:
        self._agent_id = agent_id
        self._authorize = authorize

    def act(self, action: str, resource: str, params: dict[str, Any] | None = None, cost: float = 0.0) -> Any:
        """Solicita ejecutar una acción. Lanza ActionDenied / ActionPendingApproval."""
        request = ActionRequest(
            agent_id=self._agent_id,
            action=action,
            resource=resource,
            params=params or {},
        )
        return self._authorize(request, cost)


class Agent(ABC):
    """Clase base para todos los agentes del ecosistema."""

    def __init__(self, identity: AgentIdentity) -> None:
        self.identity = identity

    @property
    def agent_id(self) -> str:
        return self.identity.agent_id

    @abstractmethod
    def handle(self, task: Task, context: ActionContext) -> Any:
        """Resuelve la tarea usando exclusivamente ``context`` para actuar."""
