"""Pruebas de la fase 3: políticas condicionales y cerebros LLM gobernados."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from governed_agents import (
    Agent,
    AgentIdentity,
    AgentRegistry,
    Condition,
    Effect,
    Orchestrator,
    Policy,
    PolicyEngine,
    Role,
    Task,
)
from governed_agents.llm.providers import (
    MockLlmProvider,
    OpenAiCompatibleProvider,
    create_llm_tool,
)

IDENTITY = AgentIdentity("agente", Role.STANDARD)


class TestCondition(unittest.TestCase):
    def test_operators(self):
        cases = [
            (Condition("x", "eq", 5), {"x": 5}, True),
            (Condition("x", "eq", 5), {"x": 6}, False),
            (Condition("x", "ne", 5), {"x": 6}, True),
            (Condition("x", "in", [1, 2]), {"x": 2}, True),
            (Condition("x", "in", [1, 2]), {"x": 3}, False),
            (Condition("x", "not_in", [1, 2]), {"x": 3}, True),
            (Condition("x", "lte", 500), {"x": 500}, True),
            (Condition("x", "lte", 500), {"x": 501}, False),
            (Condition("x", "gt", 500), {"x": 501}, True),
            (Condition("x", "matches", "*@example.com"), {"x": "ana@example.com"}, True),
            (Condition("x", "matches", "*@example.com"), {"x": "ana@otro.com"}, False),
        ]
        for condition, params, expected in cases:
            with self.subTest(condition=condition, params=params):
                self.assertEqual(condition.holds(params), expected)

    def test_missing_param_fails(self):
        self.assertFalse(Condition("x", "eq", 1).holds({}))

    def test_incomparable_types_fail_safely(self):
        self.assertFalse(Condition("x", "lte", 5).holds({"x": "texto"}))


class TestConditionalPolicies(unittest.TestCase):
    def setUp(self):
        self.engine = PolicyEngine([
            Policy(
                "pagos-pequenos", Effect.ALLOW, actions=("pay.transfer",),
                conditions=(Condition("amount", "lte", 500),),
            ),
            Policy(
                "deny-destinatario-vetado", Effect.DENY, actions=("pay.transfer",),
                conditions=(Condition("recipient", "eq", "vetado-sa"),),
            ),
        ])

    def test_allow_when_condition_holds(self):
        decision = self.engine.evaluate(IDENTITY, "pay.transfer", "cuentas/x", {"amount": 300})
        self.assertTrue(decision.allowed)

    def test_default_deny_when_condition_fails(self):
        decision = self.engine.evaluate(IDENTITY, "pay.transfer", "cuentas/x", {"amount": 900})
        self.assertFalse(decision.allowed)

    def test_conditional_deny_wins(self):
        decision = self.engine.evaluate(
            IDENTITY, "pay.transfer", "cuentas/x",
            {"amount": 100, "recipient": "vetado-sa"},
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.matched_policy, "deny-destinatario-vetado")

    def test_conditions_from_json(self):
        data = [{
            "policy_id": "p", "effect": "allow", "actions": ["pay.transfer"],
            "conditions": [{"param": "amount", "op": "lte", "value": 500}],
        }]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "policies.json"
            path.write_text(json.dumps(data), encoding="utf-8")
            engine = PolicyEngine.from_json(path)
        self.assertTrue(engine.evaluate(IDENTITY, "pay.transfer", "x", {"amount": 400}).allowed)
        self.assertFalse(engine.evaluate(IDENTITY, "pay.transfer", "x", {"amount": 600}).allowed)


class PayingAgent(Agent):
    def handle(self, task, context):
        return context.act("pay.transfer", "cuentas/empresa", dict(task.payload))


class TestOrchestratorWithConditions(unittest.TestCase):
    def setUp(self):
        registry = AgentRegistry()
        registry.register(PayingAgent(AgentIdentity("pagos", Role.STANDARD, ("pay",))))
        self.orch = Orchestrator(registry, PolicyEngine([
            Policy(
                "pequenos", Effect.ALLOW, actions=("pay.transfer",),
                conditions=(Condition("amount", "lte", 500),),
            ),
            Policy(
                "grandes", Effect.ALLOW, actions=("pay.transfer",),
                requires_approval=True,
                conditions=(Condition("amount", "gt", 500),),
            ),
        ]))

    def test_small_transfer_executes(self):
        result = self.orch.submit(Task("pay", {"amount": 100}))
        self.assertEqual(result.status, "completed")

    def test_large_transfer_needs_approval(self):
        result = self.orch.submit(Task("pay", {"amount": 5000}))
        self.assertEqual(result.status, "pending_approval")

    def test_missing_param_is_denied(self):
        result = self.orch.submit(Task("pay", {}))
        self.assertEqual(result.status, "denied")


class LlmAgent(Agent):
    def handle(self, task, context):
        return context.act(
            "llm.generate", "model/analista-v1", {"prompt": task.payload["prompt"]}, cost=0.3
        )


class TestGovernedLlm(unittest.TestCase):
    def test_mock_provider_canned_and_default(self):
        provider = MockLlmProvider(canned={"hola": "¡Hola! Encantado."})
        self.assertEqual(provider.complete("m", "di hola por favor").text, "¡Hola! Encantado.")
        default = provider.complete("m", "otra cosa")
        self.assertIn("respuesta simulada", default.text)
        self.assertGreater(default.prompt_tokens, 0)

    def _build(self, role):
        registry = AgentRegistry()
        registry.register(LlmAgent(AgentIdentity("ia", role, ("think",))))
        orch = Orchestrator(registry, PolicyEngine([
            Policy("llm", Effect.ALLOW, roles=("trusted",),
                   actions=("llm.generate",), resources=("model/*",)),
        ]))
        orch.register_tool("llm.generate", create_llm_tool(MockLlmProvider()))
        return orch

    def test_trusted_agent_uses_llm(self):
        orch = self._build(Role.TRUSTED)
        result = orch.submit(Task("think", {"prompt": "analiza esto"}))
        self.assertEqual(result.status, "completed")
        self.assertIn("respuesta simulada", result.output["text"])
        self.assertEqual(len(list(orch.audit.events(event_type="action_executed"))), 1)

    def test_sandboxed_agent_denied_llm(self):
        orch = self._build(Role.SANDBOXED)
        result = orch.submit(Task("think", {"prompt": "analiza esto"}))
        self.assertEqual(result.status, "denied")


class TestOpenAiCompatibleProvider(unittest.TestCase):
    def test_build_request(self):
        provider = OpenAiCompatibleProvider(
            base_url="https://llm.example.com/v1/", api_key="clave-secreta"
        )
        request = provider.build_request("modelo-x", "hola", temperature=0.2)
        self.assertEqual(request.full_url, "https://llm.example.com/v1/chat/completions")
        self.assertEqual(request.get_header("Authorization"), "Bearer clave-secreta")
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual(payload["model"], "modelo-x")
        self.assertEqual(payload["messages"], [{"role": "user", "content": "hola"}])
        self.assertEqual(payload["temperature"], 0.2)

    def test_missing_api_key_raises(self):
        provider = OpenAiCompatibleProvider(api_key_env="CLAVE_QUE_NO_EXISTE")
        with self.assertRaises(RuntimeError):
            provider.build_request("m", "hola")


if __name__ == "__main__":
    unittest.main()
