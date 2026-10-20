"""Demostración de la fase 2: delegación gobernada y auditoría persistente.

Escenario: un agente coordinador (rol *trusted*) delega la investigación
en el agente investigador; un agente externo (rol *sandboxed*) intenta
delegar y la política se lo impide. Toda la actividad queda en una base
SQLite cuya integridad se verifica tras recargarla desde disco.

Ejecutar desde la raíz del proyecto:

    python examples/demo_fase2.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from governed_agents import (
    Agent,
    ActionContext,
    AgentIdentity,
    AgentRegistry,
    Orchestrator,
    PolicyEngine,
    Role,
    SqliteAuditLog,
    Task,
)


class ResearchAgent(Agent):
    def handle(self, task: Task, context: ActionContext):
        query = task.payload["query"]
        return context.act("web.search", f"query/{query}", {"query": query}, cost=0.5)


class CoordinatorAgent(Agent):
    """Delegación legítima: coordina la investigación y resume."""

    def handle(self, task: Task, context: ActionContext):
        sub_result = context.delegate("research", {"query": task.payload["topic"]})
        return {
            "topic": task.payload["topic"],
            "investigacion": sub_result.output,
            "resumen": f"Síntesis sobre '{task.payload['topic']}' a partir de la subtarea delegada.",
        }


class SneakyAgent(Agent):
    """Agente externo que intenta delegar sin permiso."""

    def handle(self, task: Task, context: ActionContext):
        return context.delegate("research", {"query": "datos internos"})


def main() -> None:
    policies_path = Path(__file__).resolve().parent.parent / "policies" / "default_policies.json"
    engine = PolicyEngine.from_json(policies_path)

    registry = AgentRegistry()
    registry.register(ResearchAgent(AgentIdentity("investigador-1", Role.TRUSTED, ("research",))))
    registry.register(CoordinatorAgent(AgentIdentity("coordinador-1", Role.TRUSTED, ("coordinate",))))
    registry.register(SneakyAgent(AgentIdentity("externo-1", Role.SANDBOXED, ("infiltrate",))))

    db_path = Path(tempfile.gettempdir()) / "auditoria_demo.sqlite"
    db_path.unlink(missing_ok=True)
    audit = SqliteAuditLog(db_path)

    orchestrator = Orchestrator(registry, engine, audit_log=audit)
    orchestrator.register_tool(
        "web.search", lambda req: [f"resultado simulado para '{req.params['query']}'"]
    )

    print("=== 1. Coordinador delega la investigación (permitido) ===")
    result = orchestrator.submit(Task("coordinate", {"topic": "gobernanza de IA"}))
    print(f"  estado: {result.status}")
    print(f"  salida: {result.output}\n")

    print("=== 2. Agente externo intenta delegar (denegado por política) ===")
    result = orchestrator.submit(Task("infiltrate", {}))
    print(f"  estado: {result.status} -> {result.reason}\n")

    print("=== 3. Auditoría persistente en SQLite ===")
    audit.close()
    reloaded = SqliteAuditLog(db_path)  # recarga desde disco
    for event in reloaded.events():
        print(f"  [{event.sequence}] {event.event_type:22s} agente={event.agent_id}")
    print(f"\n  Eventos persistidos: {len(reloaded)} en {db_path}")
    print(f"  Integridad tras recargar: "
          f"{'VÁLIDA' if reloaded.verify_integrity() else 'CORRUPTA'}")
    reloaded.close()


if __name__ == "__main__":
    main()
