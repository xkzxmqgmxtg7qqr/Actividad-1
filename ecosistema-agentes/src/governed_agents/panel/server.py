"""Panel web de gobernanza (solo biblioteca estándar).

Muestra la cola de aprobaciones pendientes con botones para aprobar o
rechazar, y la pista de auditoría con su estado de integridad. Pensado
para el humano en el circuito.

Uso::

    from governed_agents.panel.server import create_panel_server
    server = create_panel_server(orchestrator, port=8765)
    server.serve_forever()  # o en un hilo
"""

from __future__ import annotations

import html
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

from governed_agents.orchestration.orchestrator import Orchestrator

_STYLE = """
body { font-family: Arial, Helvetica, sans-serif; background: #f8fafc; color: #1f2937;
       max-width: 1000px; margin: 0 auto; padding: 24px; }
h1 { color: #004b8d; } h2 { color: #0f172a; margin-top: 32px; }
table { border-collapse: collapse; width: 100%; background: white;
        box-shadow: 0 4px 10px rgba(15,23,42,.06); }
th, td { border: 1px solid #e5e7eb; padding: 8px 10px; text-align: left; font-size: 14px; }
th { background: #eff6ff; }
.badge { padding: 2px 8px; border-radius: 10px; font-size: 12px; }
.ok { background: #ecfdf5; color: #065f46; } .bad { background: #fef2f2; color: #991b1b; }
form { display: inline; } input[type=text] { width: 110px; }
button { border: 0; border-radius: 8px; padding: 6px 12px; cursor: pointer; }
.aprobar { background: #065f46; color: white; } .rechazar { background: #991b1b; color: white; }
.vacio { color: #6b7280; font-style: italic; }
"""


def _render(orchestrator: Orchestrator) -> str:
    pending = orchestrator.approvals.pending()
    rows = []
    for item in pending:
        rid = html.escape(item.request.request_id)
        rows.append(
            f"<tr><td><code>{rid}</code></td>"
            f"<td>{html.escape(item.request.agent_id)}</td>"
            f"<td>{html.escape(item.request.action)}</td>"
            f"<td>{html.escape(item.request.resource)}</td>"
            f"<td>{item.cost}</td>"
            f"<td>"
            f"<form method='post' action='/approve'>"
            f"<input type='hidden' name='request_id' value='{rid}'>"
            f"<input type='text' name='approver' placeholder='su nombre' required> "
            f"<button class='aprobar'>Aprobar</button></form> "
            f"<form method='post' action='/reject'>"
            f"<input type='hidden' name='request_id' value='{rid}'>"
            f"<input type='text' name='approver' placeholder='su nombre' required> "
            f"<button class='rechazar'>Rechazar</button></form>"
            f"</td></tr>"
        )
    approvals_html = (
        f"<table><tr><th>Solicitud</th><th>Agente</th><th>Acción</th><th>Recurso</th>"
        f"<th>Coste</th><th>Decisión</th></tr>{''.join(rows)}</table>"
        if rows
        else "<p class='vacio'>No hay acciones pendientes de aprobación.</p>"
    )

    audit_rows = []
    for event in orchestrator.audit.events():
        audit_rows.append(
            f"<tr><td>{event.sequence}</td>"
            f"<td>{html.escape(event.event_type)}</td>"
            f"<td>{html.escape(event.agent_id)}</td>"
            f"<td><code>{html.escape(str(event.detail))}</code></td></tr>"
        )
    integrity_ok = orchestrator.audit.verify_integrity()
    integrity = (
        "<span class='badge ok'>cadena íntegra</span>"
        if integrity_ok
        else "<span class='badge bad'>cadena corrupta</span>"
    )

    return f"""<!DOCTYPE html>
<html lang="es"><head><meta charset="utf-8">
<title>Panel de gobernanza</title><style>{_STYLE}</style></head>
<body>
<h1>Panel de gobernanza del ecosistema de agentes</h1>
<h2>Aprobaciones pendientes ({len(pending)})</h2>
{approvals_html}
<h2>Pista de auditoría ({len(orchestrator.audit)} eventos) — {integrity}</h2>
<table><tr><th>#</th><th>Evento</th><th>Agente</th><th>Detalle</th></tr>
{''.join(reversed(audit_rows))}</table>
</body></html>"""


class _PanelHandler(BaseHTTPRequestHandler):
    server: "PanelServer"

    def _send_html(self, body: str, status: int = 200) -> None:
        payload = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _redirect_home(self) -> None:
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802 (API de http.server)
        if self.path != "/":
            self._send_html("<h1>404</h1>", status=404)
            return
        self._send_html(_render(self.server.orchestrator))

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        form = parse_qs(self.rfile.read(length).decode("utf-8"))
        request_id = form.get("request_id", [""])[0]
        approver = form.get("approver", ["anónimo"])[0]
        orchestrator = self.server.orchestrator
        try:
            if self.path == "/approve":
                orchestrator.approve(request_id, approver)
            elif self.path == "/reject":
                orchestrator.reject(request_id, approver)
            else:
                self._send_html("<h1>404</h1>", status=404)
                return
        except KeyError:
            self._send_html("<h1>Solicitud no encontrada o ya resuelta</h1>", status=409)
            return
        self._redirect_home()

    def log_message(self, format: str, *args) -> None:  # silenciar logs en consola
        pass


class PanelServer(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], orchestrator: Orchestrator) -> None:
        super().__init__(address, _PanelHandler)
        self.orchestrator = orchestrator


def create_panel_server(
    orchestrator: Orchestrator, host: str = "127.0.0.1", port: int = 8765
) -> PanelServer:
    return PanelServer((host, port), orchestrator)
