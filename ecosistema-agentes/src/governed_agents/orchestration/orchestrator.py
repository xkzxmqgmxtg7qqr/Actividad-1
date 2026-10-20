"""Orquestador: el punto donde la gobernanza se hace efectiva.

Flujo de una tarea:

1. Se busca en el registro un agente con la capacidad requerida.
2. El agente la resuelve a través de un :class:`ActionContext`.
3. Cada acción solicitada pasa por: motor de políticas -> límites de uso
   -> (aprobación humana si procede) -> ejecución del *tool* -> auditoría.

Nada de lo anterior es opcional ni accesible directamente al agente.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from governed_agents.core.agent import (
    ActionContext,
    ActionDenied,
    ActionPendingApproval,
    Agent,
)
from governed_agents.core.message import ActionRequest, Task, TaskResult
from governed_agents.governance.audit import AuditLog
from governed_agents.governance.identity import AgentIdentity, Role
from governed_agents.governance.limits import UsageLimiter
from governed_agents.governance.policy import PolicyEngine
from governed_agents.orchestration.registry import AgentRegistry

ToolExecutor = Callable[[ActionRequest], Any]


@dataclass
class PendingApproval:
    request: ActionRequest
    cost: float
    status: str = "pending"  # "pending" | "approved" | "rejected"
    resolved_by: str | None = None
    result: Any = None
    notes: str = ""


class ApprovalQueue:
    """Cola de acciones a la espera de decisión humana o de un supervisor."""

    def __init__(self) -> None:
        self._items: dict[str, PendingApproval] = {}

    def enqueue(self, request: ActionRequest, cost: float) -> PendingApproval:
        item = PendingApproval(request=request, cost=cost)
        self._items[request.request_id] = item
        return item

    def get(self, request_id: str) -> PendingApproval | None:
        return self._items.get(request_id)

    def pending(self) -> list[PendingApproval]:
        return [i for i in self._items.values() if i.status == "pending"]


class UnknownCapability(Exception):
    pass


class NotAuthorizedToApprove(Exception):
    pass


class Orchestrator:
    def __init__(
        self,
        registry: AgentRegistry,
        policy_engine: PolicyEngine,
        audit_log: AuditLog | None = None,
        limiter: UsageLimiter | None = None,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine
        self.audit = audit_log or AuditLog()
        self.limiter = limiter or UsageLimiter()
        self.approvals = ApprovalQueue()
        self._tools: dict[str, ToolExecutor] = {}

    # ------------------------------------------------------------------
    # Herramientas (implementaciones reales de las acciones)
    # ------------------------------------------------------------------
    def register_tool(self, action_pattern: str, executor: ToolExecutor) -> None:
        self._tools[action_pattern] = executor

    def _execute_tool(self, request: ActionRequest) -> Any:
        from fnmatch import fnmatch

        for pattern, executor in self._tools.items():
            if fnmatch(request.action, pattern):
                return executor(request)
        # Sin implementación registrada: se devuelve un eco (útil en demos/tests).
        return {"action": request.action, "resource": request.resource, "params": request.params}

    # ------------------------------------------------------------------
    # Autorización de acciones (corazón de la gobernanza)
    # ------------------------------------------------------------------
    def _authorize_and_execute(self, agent: Agent, request: ActionRequest, cost: float) -> Any:
        decision = self.policy_engine.evaluate(agent.identity, request.action, request.resource)
        if not decision.allowed:
            self.audit.record(
                "action_denied",
                agent.agent_id,
                {"request_id": request.request_id, "action": request.action,
                 "resource": request.resource, "reason": decision.reason},
            )
            raise ActionDenied(request, decision.reason)

        ok, limit_reason = self.limiter.check(agent.agent_id, cost)
        if not ok:
            self.audit.record(
                "action_denied",
                agent.agent_id,
                {"request_id": request.request_id, "action": request.action,
                 "resource": request.resource, "reason": limit_reason},
            )
            raise ActionDenied(request, limit_reason)

        if decision.requires_approval:
            self.approvals.enqueue(request, cost)
            self.audit.record(
                "action_pending_approval",
                agent.agent_id,
                {"request_id": request.request_id, "action": request.action,
                 "resource": request.resource, "policy": decision.matched_policy},
            )
            raise ActionPendingApproval(request)

        self.limiter.consume(agent.agent_id, cost)
        result = self._execute_tool(request)
        self.audit.record(
            "action_executed",
            agent.agent_id,
            {"request_id": request.request_id, "action": request.action,
             "resource": request.resource, "policy": decision.matched_policy, "cost": cost},
        )
        return result

    # ------------------------------------------------------------------
    # Ciclo de vida de tareas
    # ------------------------------------------------------------------
    def submit(self, task: Task) -> TaskResult:
        candidates = self.registry.find_by_capability(task.capability)
        if not candidates:
            raise UnknownCapability(task.capability)
        agent = candidates[0]

        self.audit.record(
            "task_submitted",
            agent.agent_id,
            {"task_id": task.task_id, "capability": task.capability,
             "requested_by": task.requested_by},
        )

        context = ActionContext(
            agent.agent_id,
            lambda request, cost: self._authorize_and_execute(agent, request, cost),
        )
        try:
            output = agent.handle(task, context)
        except ActionDenied as exc:
            return TaskResult(task.task_id, agent.agent_id, "denied", reason=exc.reason)
        except ActionPendingApproval as exc:
            return TaskResult(
                task.task_id, agent.agent_id, "pending_approval",
                reason=f"Esperando aprobación de '{exc.request.request_id}'",
                output={"request_id": exc.request.request_id},
            )
        except Exception as exc:  # fallo del propio agente
            self.audit.record(
                "task_failed", agent.agent_id,
                {"task_id": task.task_id, "error": repr(exc)},
            )
            return TaskResult(task.task_id, agent.agent_id, "failed", reason=repr(exc))

        self.audit.record(
            "task_completed", agent.agent_id, {"task_id": task.task_id},
        )
        return TaskResult(task.task_id, agent.agent_id, "completed", output=output)

    # ------------------------------------------------------------------
    # Aprobación humana / de supervisor
    # ------------------------------------------------------------------
    def approve(self, request_id: str, approver: AgentIdentity | str, notes: str = "") -> Any:
        """Aprueba y ejecuta una acción pendiente.

        ``approver`` puede ser un humano (cadena con su nombre) o la
        identidad de un agente con rol SUPERVISOR.
        """
        if isinstance(approver, AgentIdentity):
            if approver.role is not Role.SUPERVISOR:
                raise NotAuthorizedToApprove(
                    f"El agente '{approver.agent_id}' no tiene rol supervisor"
                )
            approver_name = f"agent:{approver.agent_id}"
        else:
            approver_name = f"human:{approver}"

        item = self.approvals.get(request_id)
        if item is None or item.status != "pending":
            raise KeyError(f"No hay aprobación pendiente con id '{request_id}'")

        self.limiter.consume(item.request.agent_id, item.cost)
        result = self._execute_tool(item.request)
        item.status = "approved"
        item.resolved_by = approver_name
        item.result = result
        item.notes = notes
        self.audit.record(
            "action_approved_and_executed",
            item.request.agent_id,
            {"request_id": request_id, "action": item.request.action,
             "resource": item.request.resource, "approved_by": approver_name, "notes": notes},
        )
        return result

    def reject(self, request_id: str, approver: str, notes: str = "") -> None:
        item = self.approvals.get(request_id)
        if item is None or item.status != "pending":
            raise KeyError(f"No hay aprobación pendiente con id '{request_id}'")
        item.status = "rejected"
        item.resolved_by = f"human:{approver}"
        item.notes = notes
        self.audit.record(
            "action_rejected",
            item.request.agent_id,
            {"request_id": request_id, "action": item.request.action,
             "resource": item.request.resource, "rejected_by": approver, "notes": notes},
        )
