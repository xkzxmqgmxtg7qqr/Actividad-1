"""Ecosistema de agentes gobernados.

Framework ligero (solo biblioteca estándar) para orquestar agentes de IA
bajo un marco de gobernanza: identidad, políticas, auditoría, límites de
uso y aprobación humana.
"""

from governed_agents.core.agent import Agent, ActionContext
from governed_agents.core.message import Task, TaskResult, ActionRequest
from governed_agents.governance.identity import AgentIdentity, Role
from governed_agents.governance.policy import Policy, PolicyEngine, Decision, Effect
from governed_agents.governance.audit import AuditLog, AuditEvent
from governed_agents.governance.audit_sqlite import SqliteAuditLog
from governed_agents.governance.limits import UsageLimiter, UsageLimit
from governed_agents.orchestration.registry import AgentRegistry
from governed_agents.orchestration.orchestrator import Orchestrator, ApprovalQueue

__all__ = [
    "Agent",
    "ActionContext",
    "Task",
    "TaskResult",
    "ActionRequest",
    "AgentIdentity",
    "Role",
    "Policy",
    "PolicyEngine",
    "Decision",
    "Effect",
    "AuditLog",
    "AuditEvent",
    "SqliteAuditLog",
    "UsageLimiter",
    "UsageLimit",
    "AgentRegistry",
    "Orchestrator",
    "ApprovalQueue",
]
