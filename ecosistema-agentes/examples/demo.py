"""Demostración del ecosistema de agentes gobernados.

Escenario: un agente investigador busca información, un agente redactor
escribe un informe y un agente externo (sandbox) intenta una acción
prohibida. El envío del informe por correo exige aprobación humana.

Ejecutar desde la raíz del proyecto:

    python examples/demo.py
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
    AuditLog,
    Orchestrator,
    PolicyEngine,
    Role,
    Task,
    UsageLimit,
    UsageLimiter,
)
# ----------------------------------------------------------------------
# Agentes de ejemplo
# ----------------------------------------------------------------------
class ResearchAgent(Agent):
    def handle(self, task: Task, context: ActionContext):
        query = task.payload["query"]
        results = context.act("web.search", f"query/{query}", {"query": query}, cost=0.5)
        return {"query": query, "results": results}


class WriterAgent(Agent):
    def handle(self, task: Task, context: ActionContext):
        document = task.payload["document"]
        context.act("fs.write", f"reports/{document}", {"content": task.payload["content"]}, cost=0.2)
        # El envío por correo exige aprobación humana según las políticas.
        context.act("email.send", "direccion@example.com", {"attachment": document}, cost=0.1)
        return {"document": document, "sent": True}


class RogueAgent(Agent):
    """Agente externo que intenta borrar datos de producción."""

    def handle(self, task: Task, context: ActionContext):
        return context.act("db.delete", "produccion/usuarios", {}, cost=0.0)


# ----------------------------------------------------------------------
# Montaje del ecosistema
# ----------------------------------------------------------------------
def build_ecosystem() -> Orchestrator:
    policies_path = Path(__file__).resolve().parent.parent / "policies" / "default_policies.json"
    engine = PolicyEngine.from_json(policies_path)

    registry = AgentRegistry()
    registry.register(
        ResearchAgent(AgentIdentity("investigador-1", Role.TRUSTED, ("research",), owner="equipo-datos"))
    )
    registry.register(
        WriterAgent(AgentIdentity("redactor-1", Role.STANDARD, ("write_report",), owner="equipo-datos"))
    )
    registry.register(
        RogueAgent(AgentIdentity("externo-1", Role.SANDBOXED, ("cleanup",), owner="proveedor-externo"))
    )

    limiter = UsageLimiter(UsageLimit(max_actions=50, max_cost=5.0, window_seconds=3600))
    orchestrator = Orchestrator(registry, engine, AuditLog(), limiter)

    # Implementaciones simuladas de las herramientas.
    orchestrator.register_tool(
        "web.search",
        lambda req: [f"resultado simulado para '{req.params['query']}'"],
    )
    orchestrator.register_tool("fs.write", lambda req: f"escrito {req.resource}")
    orchestrator.register_tool("email.send", lambda req: f"correo enviado a {req.resource}")
    return orchestrator


def main() -> None:
    orchestrator = build_ecosystem()

    print("=== 1. Tarea de investigación (permitida) ===")
    result = orchestrator.submit(Task("research", {"query": "gobernanza de agentes de IA"}))
    print(f"  estado: {result.status}")
    print(f"  salida: {result.output}\n")

    print("=== 2. Informe con envío de correo (requiere aprobación humana) ===")
    result = orchestrator.submit(
        Task("write_report", {"document": "informe.md", "content": "Hallazgos..."})
    )
    print(f"  estado: {result.status} -> {result.reason}")
    pending = orchestrator.approvals.pending()[0]
    print(f"  pendiente: {pending.request.action} sobre {pending.request.resource}")
    output = orchestrator.approve(pending.request.request_id, "ana.supervisora", notes="Revisado OK")
    print(f"  tras aprobación humana: {output}\n")

    print("=== 3. Agente externo intenta borrar producción (denegado) ===")
    result = orchestrator.submit(Task("cleanup", {}))
    print(f"  estado: {result.status} -> {result.reason}\n")

    print("=== 4. Pista de auditoría ===")
    for event in orchestrator.audit.events():
        print(f"  [{event.sequence}] {event.event_type:28s} agente={event.agent_id}")
    print(f"\n  Integridad de la cadena de auditoría: "
          f"{'VÁLIDA' if orchestrator.audit.verify_integrity() else 'CORRUPTA'}")


if __name__ == "__main__":
    main()
