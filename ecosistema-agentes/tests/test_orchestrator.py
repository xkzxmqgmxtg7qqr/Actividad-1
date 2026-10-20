"""Pruebas de integración del orquestador y el ciclo de vida de tareas."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from governed_agents import (
    Agent,
    AgentIdentity,
    AgentRegistry,
    Effect,
    Orchestrator,
    Policy,
    PolicyEngine,
    Role,
    Task,
    UsageLimit,
    UsageLimiter,
)
from governed_agents.orchestration.orchestrator import NotAuthorizedToApprove, UnknownCapability


class EchoAgent(Agent):
    """Agente mínimo: ejecuta la acción indicada en el payload de la tarea."""

    def handle(self, task, context):
        return context.act(
            task.payload["action"],
            task.payload["resource"],
            cost=task.payload.get("cost", 0.0),
        )


def build(policies, limiter=None):
    registry = AgentRegistry()
    registry.register(EchoAgent(AgentIdentity("eco-1", Role.STANDARD, ("echo",))))
    return Orchestrator(registry, PolicyEngine(policies), limiter=limiter)


class TestOrchestrator(unittest.TestCase):
    def test_allowed_action_completes(self):
        orch = build([Policy("allow", Effect.ALLOW, actions=("web.search",))])
        result = orch.submit(Task("echo", {"action": "web.search", "resource": "query/x"}))
        self.assertEqual(result.status, "completed")
        self.assertEqual(
            [e.event_type for e in orch.audit.events()],
            ["task_submitted", "action_executed", "task_completed"],
        )

    def test_denied_action(self):
        orch = build([])
        result = orch.submit(Task("echo", {"action": "db.delete", "resource": "produccion/x"}))
        self.assertEqual(result.status, "denied")
        self.assertIn("denegación por defecto", result.reason)
        self.assertEqual(len(list(orch.audit.events(event_type="action_denied"))), 1)

    def test_unknown_capability(self):
        orch = build([])
        with self.assertRaises(UnknownCapability):
            orch.submit(Task("no-existe", {}))

    def test_approval_flow(self):
        orch = build([Policy("correo", Effect.ALLOW, actions=("email.send",), requires_approval=True)])
        result = orch.submit(Task("echo", {"action": "email.send", "resource": "x@example.com"}))
        self.assertEqual(result.status, "pending_approval")
        pending = orch.approvals.pending()
        self.assertEqual(len(pending), 1)

        output = orch.approve(pending[0].request.request_id, "humano.revisor")
        self.assertEqual(output["action"], "email.send")
        self.assertEqual(orch.approvals.pending(), [])
        self.assertEqual(
            len(list(orch.audit.events(event_type="action_approved_and_executed"))), 1
        )

    def test_rejection_flow(self):
        orch = build([Policy("correo", Effect.ALLOW, actions=("email.send",), requires_approval=True)])
        orch.submit(Task("echo", {"action": "email.send", "resource": "x@example.com"}))
        pending = orch.approvals.pending()[0]
        orch.reject(pending.request.request_id, "humano.revisor", notes="No procede")
        self.assertEqual(pending.status, "rejected")
        with self.assertRaises(KeyError):
            orch.approve(pending.request.request_id, "otro.humano")

    def test_supervisor_agent_can_approve_but_standard_cannot(self):
        orch = build([Policy("correo", Effect.ALLOW, actions=("email.send",), requires_approval=True)])
        orch.submit(Task("echo", {"action": "email.send", "resource": "x@example.com"}))
        request_id = orch.approvals.pending()[0].request.request_id

        standard = AgentIdentity("otro", Role.STANDARD)
        with self.assertRaises(NotAuthorizedToApprove):
            orch.approve(request_id, standard)

        supervisor = AgentIdentity("jefe", Role.SUPERVISOR)
        output = orch.approve(request_id, supervisor)
        self.assertIsNotNone(output)

    def test_usage_limit_blocks_action(self):
        limiter = UsageLimiter(UsageLimit(max_actions=1, max_cost=100.0))
        orch = build([Policy("allow", Effect.ALLOW, actions=("web.search",))], limiter=limiter)
        task = Task("echo", {"action": "web.search", "resource": "query/x"})
        self.assertEqual(orch.submit(task).status, "completed")
        result = orch.submit(Task("echo", {"action": "web.search", "resource": "query/y"}))
        self.assertEqual(result.status, "denied")
        self.assertIn("Cuota", result.reason)

    def test_registered_tool_is_used(self):
        orch = build([Policy("allow", Effect.ALLOW, actions=("web.search",))])
        orch.register_tool("web.*", lambda req: "resultado-real")
        result = orch.submit(Task("echo", {"action": "web.search", "resource": "query/x"}))
        self.assertEqual(result.output, "resultado-real")

    def test_agent_failure_is_audited(self):
        class FailingAgent(Agent):
            def handle(self, task, context):
                raise ValueError("fallo interno")

        registry = AgentRegistry()
        registry.register(FailingAgent(AgentIdentity("fragil", Role.STANDARD, ("fail",))))
        orch = Orchestrator(registry, PolicyEngine([]))
        result = orch.submit(Task("fail", {}))
        self.assertEqual(result.status, "failed")
        self.assertEqual(len(list(orch.audit.events(event_type="task_failed"))), 1)


if __name__ == "__main__":
    unittest.main()
