"""Pruebas de la fase 2: auditoría SQLite, delegación gobernada y panel web."""

import sys
import tempfile
import threading
import unittest
import urllib.parse
import urllib.request
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
    SqliteAuditLog,
    Task,
)
from governed_agents.panel.server import create_panel_server


class TestSqliteAuditLog(unittest.TestCase):
    def test_record_and_integrity(self):
        log = SqliteAuditLog()  # en memoria
        for i in range(5):
            log.record("evento", "agente", {"i": i})
        self.assertEqual(len(log), 5)
        self.assertTrue(log.verify_integrity())
        log.close()

    def test_persistence_across_restarts(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite"
            log = SqliteAuditLog(path)
            log.record("a", "agente-1", {"x": 1})
            log.record("b", "agente-2", {"y": 2})
            log.close()

            reloaded = SqliteAuditLog(path)
            self.assertEqual(len(reloaded), 2)
            self.assertTrue(reloaded.verify_integrity())
            # La cadena continúa sobre los eventos previos.
            reloaded.record("c", "agente-1", {"z": 3})
            self.assertEqual(len(reloaded), 3)
            self.assertTrue(reloaded.verify_integrity())
            reloaded.close()

    def test_tampering_in_database_detected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "audit.sqlite"
            log = SqliteAuditLog(path)
            log.record("a", "agente-1", {"x": 1})
            log.record("b", "agente-1", {"x": 2})
            # Manipulación directa de la base de datos.
            log._conn.execute("UPDATE audit_events SET detail = '{\"x\": 999}' WHERE sequence = 0")
            log._conn.commit()
            self.assertFalse(log.verify_integrity())
            log.close()

    def test_filtering(self):
        log = SqliteAuditLog()
        log.record("a", "agente-1", {})
        log.record("b", "agente-2", {})
        log.record("a", "agente-2", {})
        self.assertEqual(len(list(log.events(agent_id="agente-2"))), 2)
        self.assertEqual(len(list(log.events(event_type="a"))), 2)
        log.close()


class WorkerAgent(Agent):
    def handle(self, task, context):
        return context.act("web.search", "query/x")


class DelegatingAgent(Agent):
    def handle(self, task, context):
        return context.delegate("work", {})


class RecursiveAgent(Agent):
    """Se delega a sí mismo indefinidamente."""

    def handle(self, task, context):
        return context.delegate("loop", {})


def build_delegation_orchestrator(extra_policies=(), **kwargs):
    registry = AgentRegistry()
    registry.register(WorkerAgent(AgentIdentity("obrero", Role.STANDARD, ("work",))))
    registry.register(DelegatingAgent(AgentIdentity("jefe", Role.TRUSTED, ("manage",))))
    registry.register(RecursiveAgent(AgentIdentity("bucle", Role.TRUSTED, ("loop",))))
    policies = [
        Policy("buscar", Effect.ALLOW, actions=("web.search",)),
        Policy("delegar", Effect.ALLOW, roles=("trusted",), actions=("agent.delegate",)),
        *extra_policies,
    ]
    return Orchestrator(registry, PolicyEngine(policies), **kwargs)


class TestDelegation(unittest.TestCase):
    def test_trusted_agent_can_delegate(self):
        orch = build_delegation_orchestrator()
        result = orch.submit(Task("manage", {}))
        self.assertEqual(result.status, "completed")
        # La salida es el TaskResult de la subtarea completada.
        self.assertEqual(result.output.status, "completed")
        self.assertEqual(len(list(orch.audit.events(event_type="task_delegated"))), 1)

    def test_delegation_denied_by_policy(self):
        registry = AgentRegistry()
        registry.register(WorkerAgent(AgentIdentity("obrero", Role.STANDARD, ("work",))))

        class StandardDelegator(DelegatingAgent):
            pass

        registry.register(StandardDelegator(AgentIdentity("aspirante", Role.STANDARD, ("manage",))))
        policies = [
            Policy("buscar", Effect.ALLOW, actions=("web.search",)),
            Policy("delegar", Effect.ALLOW, roles=("trusted",), actions=("agent.delegate",)),
        ]
        orch = Orchestrator(registry, PolicyEngine(policies))
        result = orch.submit(Task("manage", {}))
        self.assertEqual(result.status, "denied")
        self.assertEqual(len(list(orch.audit.events(event_type="delegation_denied"))), 1)

    def test_delegation_depth_limit(self):
        orch = build_delegation_orchestrator(max_delegation_depth=2)
        result = orch.submit(Task("loop", {}))
        # La delegación devuelve el TaskResult del subnivel: la denegación
        # queda en la subtarea más profunda, no se propaga hacia arriba.
        deepest = result.output.output
        self.assertEqual(deepest.status, "denied")
        self.assertIn("Profundidad máxima", deepest.reason)
        denials = list(orch.audit.events(event_type="delegation_denied"))
        self.assertEqual(len(denials), 1)
        self.assertIn("Profundidad máxima", denials[0].detail["reason"])

    def test_subtask_requested_by_records_delegator(self):
        orch = build_delegation_orchestrator()
        orch.submit(Task("manage", {}))
        submissions = list(orch.audit.events(event_type="task_submitted"))
        self.assertEqual(submissions[1].detail["requested_by"], "agent:jefe")
        self.assertEqual(submissions[1].detail["depth"], 1)


class TestPanelServer(unittest.TestCase):
    def setUp(self):
        policies = [
            Policy("correo", Effect.ALLOW, actions=("email.send",), requires_approval=True),
        ]

        class MailAgent(Agent):
            def handle(self, task, context):
                return context.act("email.send", "x@example.com")

        registry = AgentRegistry()
        registry.register(MailAgent(AgentIdentity("cartero", Role.STANDARD, ("mail",))))
        self.orch = Orchestrator(registry, PolicyEngine(policies))
        self.orch.submit(Task("mail", {}))

        self.server = create_panel_server(self.orch, port=0)  # puerto libre
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def _get(self, path="/"):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{path}") as response:
            return response.status, response.read().decode("utf-8")

    def test_panel_shows_pending_approval(self):
        status, body = self._get()
        self.assertEqual(status, 200)
        self.assertIn("Aprobaciones pendientes (1)", body)
        self.assertIn("email.send", body)
        self.assertIn("cadena íntegra", body)

    def test_approve_via_http(self):
        request_id = self.orch.approvals.pending()[0].request.request_id
        data = urllib.parse.urlencode(
            {"request_id": request_id, "approver": "ana"}
        ).encode("ascii")
        with urllib.request.urlopen(
            f"http://127.0.0.1:{self.port}/approve", data=data
        ) as response:
            self.assertEqual(response.status, 200)  # tras la redirección a /
        self.assertEqual(self.orch.approvals.pending(), [])
        self.assertEqual(
            len(list(self.orch.audit.events(event_type="action_approved_and_executed"))), 1
        )
        _, body = self._get()
        self.assertIn("Aprobaciones pendientes (0)", body)

    def test_unknown_request_returns_conflict(self):
        data = urllib.parse.urlencode(
            {"request_id": "no-existe", "approver": "ana"}
        ).encode("ascii")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/reject", data=data
        )
        try:
            urllib.request.urlopen(request)
            self.fail("Debería haber devuelto 409")
        except urllib.error.HTTPError as exc:
            self.assertEqual(exc.code, 409)


if __name__ == "__main__":
    unittest.main()
