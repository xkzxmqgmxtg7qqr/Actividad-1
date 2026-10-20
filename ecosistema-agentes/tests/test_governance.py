"""Pruebas del marco de gobernanza (políticas, auditoría y límites)."""

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from governed_agents import (
    AgentIdentity,
    AuditLog,
    Effect,
    Policy,
    PolicyEngine,
    Role,
    UsageLimit,
    UsageLimiter,
)


IDENTITY = AgentIdentity("agente-prueba", Role.STANDARD, ("x",))


class TestPolicyEngine(unittest.TestCase):
    def test_default_deny(self):
        engine = PolicyEngine()
        decision = engine.evaluate(IDENTITY, "web.search", "query/x")
        self.assertFalse(decision.allowed)

    def test_explicit_allow(self):
        engine = PolicyEngine([
            Policy("p1", Effect.ALLOW, actions=("web.*",)),
        ])
        decision = engine.evaluate(IDENTITY, "web.search", "query/x")
        self.assertTrue(decision.allowed)
        self.assertEqual(decision.matched_policy, "p1")

    def test_deny_wins_over_allow(self):
        engine = PolicyEngine([
            Policy("allow-all", Effect.ALLOW),
            Policy("deny-prod", Effect.DENY, actions=("db.delete",), resources=("produccion/*",)),
        ])
        decision = engine.evaluate(IDENTITY, "db.delete", "produccion/usuarios")
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.matched_policy, "deny-prod")

    def test_role_filtering(self):
        engine = PolicyEngine([
            Policy("solo-trusted", Effect.ALLOW, roles=("trusted",), actions=("fs.write",)),
        ])
        standard = AgentIdentity("a", Role.STANDARD)
        trusted = AgentIdentity("b", Role.TRUSTED)
        self.assertFalse(engine.evaluate(standard, "fs.write", "reports/x").allowed)
        self.assertTrue(engine.evaluate(trusted, "fs.write", "reports/x").allowed)

    def test_requires_approval(self):
        engine = PolicyEngine([
            Policy("correo", Effect.ALLOW, actions=("email.send",), requires_approval=True),
        ])
        decision = engine.evaluate(IDENTITY, "email.send", "x@example.com")
        self.assertTrue(decision.allowed)
        self.assertTrue(decision.requires_approval)

    def test_load_from_json(self):
        path = Path(__file__).resolve().parent.parent / "policies" / "default_policies.json"
        engine = PolicyEngine.from_json(path)
        self.assertGreater(len(engine.policies), 0)
        sandbox = AgentIdentity("ext", Role.SANDBOXED)
        self.assertFalse(engine.evaluate(sandbox, "fs.write", "reports/x").allowed)
        self.assertTrue(engine.evaluate(sandbox, "web.search", "public/docs").allowed)


class TestAuditLog(unittest.TestCase):
    def test_chain_integrity(self):
        log = AuditLog()
        for i in range(5):
            log.record("evento", "agente", {"i": i})
        self.assertEqual(len(log), 5)
        self.assertTrue(log.verify_integrity())

    def test_tampering_detected(self):
        log = AuditLog()
        log.record("evento", "agente", {"i": 0})
        log.record("evento", "agente", {"i": 1})
        # Manipulación directa del registro interno.
        tampered = log._events[0].detail
        tampered["i"] = 999
        self.assertFalse(log.verify_integrity())

    def test_filtering(self):
        log = AuditLog()
        log.record("a", "agente-1", {})
        log.record("b", "agente-2", {})
        log.record("a", "agente-2", {})
        self.assertEqual(len(list(log.events(agent_id="agente-2"))), 2)
        self.assertEqual(len(list(log.events(event_type="a"))), 2)


class TestUsageLimiter(unittest.TestCase):
    def test_action_quota(self):
        limiter = UsageLimiter(UsageLimit(max_actions=2, max_cost=100.0))
        ok, _ = limiter.check("a")
        self.assertTrue(ok)
        limiter.consume("a")
        limiter.consume("a")
        ok, reason = limiter.check("a")
        self.assertFalse(ok)
        self.assertIn("Cuota", reason)

    def test_budget(self):
        limiter = UsageLimiter(UsageLimit(max_actions=100, max_cost=1.0))
        limiter.consume("a", cost=0.9)
        ok, reason = limiter.check("a", cost=0.2)
        self.assertFalse(ok)
        self.assertIn("Presupuesto", reason)

    def test_per_agent_limits(self):
        limiter = UsageLimiter(UsageLimit(max_actions=100))
        limiter.set_limit("restringido", UsageLimit(max_actions=1))
        limiter.consume("restringido")
        ok, _ = limiter.check("restringido")
        self.assertFalse(ok)
        ok, _ = limiter.check("normal")
        self.assertTrue(ok)


if __name__ == "__main__":
    unittest.main()
