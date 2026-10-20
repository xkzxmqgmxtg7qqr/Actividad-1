"""Límites de uso por agente (cuotas y presupuesto).

Complementa al motor de políticas: una acción puede estar permitida por
política pero bloquearse si el agente agotó su cuota de acciones o su
presupuesto en la ventana de tiempo configurada.
"""

from __future__ import annotations

import time
from dataclasses import dataclass


@dataclass
class UsageLimit:
    max_actions: int = 100          # acciones por ventana
    max_cost: float = 10.0          # coste acumulado por ventana (unidades arbitrarias)
    window_seconds: float = 3600.0


class UsageLimiter:
    def __init__(self, default_limit: UsageLimit | None = None) -> None:
        self._default = default_limit or UsageLimit()
        self._limits: dict[str, UsageLimit] = {}
        self._usage: dict[str, list[tuple[float, float]]] = {}  # agent -> [(ts, cost)]

    def set_limit(self, agent_id: str, limit: UsageLimit) -> None:
        self._limits[agent_id] = limit

    def _prune(self, agent_id: str, now: float, window: float) -> list[tuple[float, float]]:
        entries = [e for e in self._usage.get(agent_id, []) if now - e[0] <= window]
        self._usage[agent_id] = entries
        return entries

    def check(self, agent_id: str, cost: float = 0.0) -> tuple[bool, str]:
        """Comprueba si el agente puede ejecutar una acción más con ese coste."""
        limit = self._limits.get(agent_id, self._default)
        now = time.time()
        entries = self._prune(agent_id, now, limit.window_seconds)
        if len(entries) + 1 > limit.max_actions:
            return False, f"Cuota de acciones agotada ({limit.max_actions} por ventana)"
        accumulated = sum(c for _, c in entries)
        if accumulated + cost > limit.max_cost:
            return False, f"Presupuesto agotado ({limit.max_cost} por ventana)"
        return True, ""

    def consume(self, agent_id: str, cost: float = 0.0) -> None:
        self._usage.setdefault(agent_id, []).append((time.time(), cost))
