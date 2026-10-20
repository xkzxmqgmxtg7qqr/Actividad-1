"""Demostración de la fase 3: cerebros LLM gobernados y políticas condicionales.

Escenario A — LLM gobernado: un agente analista (rol *trusted*) usa un
modelo de lenguaje a través del circuito de gobernanza; un agente externo
(rol *sandboxed*) intenta usarlo y la política se lo impide.

Escenario B — condiciones sobre parámetros: un agente de pagos puede
transferir hasta 500 a destinatarios autorizados; por encima de 500 exige
aprobación humana, y a destinatarios no autorizados se deniega.

Ejecutar desde la raíz del proyecto:

    python examples/demo_fase3.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from governed_agents import (
    Agent,
    ActionContext,
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
from governed_agents.llm.providers import MockLlmProvider, create_llm_tool


class AnalystAgent(Agent):
    """Usa un LLM para analizar un tema. El modelo es una acción gobernada."""

    def handle(self, task: Task, context: ActionContext):
        topic = task.payload["topic"]
        response = context.act(
            "llm.generate",
            "model/analista-v1",
            {"prompt": f"Analiza brevemente el tema: {topic}"},
            cost=0.3,
        )
        return {"topic": topic, "analisis": response["text"], "modelo": response["model"]}


class SneakyLlmAgent(Agent):
    """Agente externo que intenta usar el LLM sin permiso."""

    def handle(self, task: Task, context: ActionContext):
        return context.act("llm.generate", "model/analista-v1", {"prompt": "datos internos"})


class PaymentsAgent(Agent):
    """Ejecuta la transferencia que indique la tarea."""

    def handle(self, task: Task, context: ActionContext):
        return context.act(
            "pay.transfer",
            "cuentas/empresa",
            {"recipient": task.payload["recipient"], "amount": task.payload["amount"]},
            cost=0.0,
        )


AUTORIZADOS = ["proveedor-a", "proveedor-b"]

POLICIES = [
    # LLM: solo agentes de confianza.
    Policy("llm-interno", Effect.ALLOW, roles=("trusted", "supervisor"),
           actions=("llm.generate",), resources=("model/*",)),
    # Pagos pequeños a destinatarios autorizados: directos.
    Policy(
        "pagos-pequenos", Effect.ALLOW, actions=("pay.transfer",),
        conditions=(
            Condition("recipient", "in", AUTORIZADOS),
            Condition("amount", "lte", 500),
        ),
    ),
    # Pagos grandes a destinatarios autorizados: con aprobación humana.
    Policy(
        "pagos-grandes", Effect.ALLOW, actions=("pay.transfer",),
        requires_approval=True,
        conditions=(
            Condition("recipient", "in", AUTORIZADOS),
            Condition("amount", "gt", 500),
        ),
    ),
]


def main() -> None:
    registry = AgentRegistry()
    registry.register(AnalystAgent(AgentIdentity("analista-1", Role.TRUSTED, ("analyze",))))
    registry.register(SneakyLlmAgent(AgentIdentity("externo-1", Role.SANDBOXED, ("infiltrate",))))
    registry.register(PaymentsAgent(AgentIdentity("pagos-1", Role.STANDARD, ("pay",))))

    orchestrator = Orchestrator(registry, PolicyEngine(POLICIES))
    orchestrator.register_tool("llm.generate", create_llm_tool(MockLlmProvider()))
    orchestrator.register_tool(
        "pay.transfer",
        lambda req: f"transferidos {req.params['amount']} a {req.params['recipient']}",
    )

    print("=== A1. Analista usa el LLM (permitido y auditado) ===")
    result = orchestrator.submit(Task("analyze", {"topic": "riesgos de agentes autónomos"}))
    print(f"  estado: {result.status}")
    print(f"  análisis: {result.output['analisis']}\n")

    print("=== A2. Agente externo intenta usar el LLM (denegado) ===")
    result = orchestrator.submit(Task("infiltrate", {}))
    print(f"  estado: {result.status} -> {result.reason}\n")

    print("=== B1. Transferencia de 300 a proveedor autorizado (directa) ===")
    result = orchestrator.submit(Task("pay", {"recipient": "proveedor-a", "amount": 300}))
    print(f"  estado: {result.status} -> {result.output}\n")

    print("=== B2. Transferencia de 1200 (requiere aprobación humana) ===")
    result = orchestrator.submit(Task("pay", {"recipient": "proveedor-a", "amount": 1200}))
    print(f"  estado: {result.status}")
    pending = orchestrator.approvals.pending()[0]
    output = orchestrator.approve(pending.request.request_id, "tesorera.maria")
    print(f"  tras aprobación: {output}\n")

    print("=== B3. Transferencia a destinatario NO autorizado (denegada) ===")
    result = orchestrator.submit(Task("pay", {"recipient": "desconocido-sa", "amount": 100}))
    print(f"  estado: {result.status} -> {result.reason}\n")

    print("=== Auditoría ===")
    for event in orchestrator.audit.events():
        print(f"  [{event.sequence}] {event.event_type:28s} agente={event.agent_id}")
    print(f"\n  Integridad: {'VÁLIDA' if orchestrator.audit.verify_integrity() else 'CORRUPTA'}")


if __name__ == "__main__":
    main()
