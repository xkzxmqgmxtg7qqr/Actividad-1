"""Tipos de mensajes que circulan por el ecosistema."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}"


@dataclass
class Task:
    """Unidad de trabajo que un agente debe resolver."""

    capability: str
    payload: dict[str, Any]
    requested_by: str = "user"
    task_id: str = field(default_factory=lambda: _new_id("task"))


@dataclass
class TaskResult:
    """Resultado de la ejecución de una tarea."""

    task_id: str
    agent_id: str
    status: str  # "completed" | "denied" | "pending_approval" | "failed"
    output: Any = None
    reason: str | None = None


@dataclass
class ActionRequest:
    """Acción concreta que un agente solicita ejecutar.

    Los agentes nunca actúan directamente sobre recursos: declaran la
    acción y el orquestador la autoriza (o no) contra las políticas.
    """

    agent_id: str
    action: str  # p.ej. "web.search", "fs.write", "email.send"
    resource: str  # recurso afectado, p.ej. "reports/informe.md"
    params: dict[str, Any] = field(default_factory=dict)
    request_id: str = field(default_factory=lambda: _new_id("act"))
