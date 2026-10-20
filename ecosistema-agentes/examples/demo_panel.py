"""Lanza el panel web de gobernanza con datos de ejemplo.

Monta el ecosistema de la demo principal, genera actividad (incluida una
acción pendiente de aprobación humana) y sirve el panel en
http://127.0.0.1:8765 para aprobarla o rechazarla desde el navegador.

Ejecutar desde la raíz del proyecto:

    python examples/demo_panel.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from demo import build_ecosystem  # reutiliza el montaje de la demo principal
from governed_agents import Task
from governed_agents.panel.server import create_panel_server


def main() -> None:
    orchestrator = build_ecosystem()
    orchestrator.submit(Task("research", {"query": "gobernanza de agentes de IA"}))
    orchestrator.submit(Task("write_report", {"document": "informe.md", "content": "Hallazgos..."}))
    orchestrator.submit(Task("cleanup", {}))

    server = create_panel_server(orchestrator, port=8765)
    print("Panel de gobernanza en http://127.0.0.1:8765 (Ctrl+C para salir)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
