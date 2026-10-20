"""Motor de políticas: decide si una acción está permitida.

Modelo declarativo inspirado en IAM:

- Cada :class:`Policy` tiene un efecto (ALLOW / DENY), y filtra por roles,
  acciones y recursos mediante patrones glob (``fnmatch``).
- La evaluación es **denegación por defecto**: si ninguna política permite
  la acción, se deniega.
- Un DENY explícito siempre gana sobre cualquier ALLOW.
- Una política ALLOW puede exigir aprobación humana (``requires_approval``).

Las políticas pueden definirse en código o cargarse desde JSON, lo que
permite versionarlas y revisarlas igual que el código.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from fnmatch import fnmatch
from pathlib import Path
from typing import Any

from governed_agents.governance.identity import AgentIdentity, Role


class Effect(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class Policy:
    policy_id: str
    effect: Effect
    roles: tuple[str, ...] = ("*",)      # roles a los que aplica
    actions: tuple[str, ...] = ("*",)    # patrones de acción, p.ej. "web.*"
    resources: tuple[str, ...] = ("*",)  # patrones de recurso
    requires_approval: bool = False
    description: str = ""

    def matches(self, role: Role, action: str, resource: str) -> bool:
        return (
            any(fnmatch(role.value, p) for p in self.roles)
            and any(fnmatch(action, p) for p in self.actions)
            and any(fnmatch(resource, p) for p in self.resources)
        )


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_approval: bool = False
    reason: str = ""
    matched_policy: str | None = None


class PolicyEngine:
    def __init__(self, policies: list[Policy] | None = None) -> None:
        self._policies: list[Policy] = list(policies or [])

    def add_policy(self, policy: Policy) -> None:
        self._policies.append(policy)

    @property
    def policies(self) -> tuple[Policy, ...]:
        return tuple(self._policies)

    def evaluate(self, identity: AgentIdentity, action: str, resource: str) -> Decision:
        matched = [p for p in self._policies if p.matches(identity.role, action, resource)]

        for policy in matched:
            if policy.effect is Effect.DENY:
                return Decision(
                    allowed=False,
                    reason=f"Denegado explícitamente por la política '{policy.policy_id}'",
                    matched_policy=policy.policy_id,
                )

        allows = [p for p in matched if p.effect is Effect.ALLOW]
        if not allows:
            return Decision(
                allowed=False,
                reason="Ninguna política permite esta acción (denegación por defecto)",
            )

        # Criterio conservador: si cualquier ALLOW aplicable exige aprobación
        # humana, la acción queda sujeta a aprobación.
        decisive = next((p for p in allows if p.requires_approval), allows[0])
        return Decision(
            allowed=True,
            requires_approval=decisive.requires_approval,
            reason=f"Permitido por la política '{decisive.policy_id}'",
            matched_policy=decisive.policy_id,
        )

    # ------------------------------------------------------------------
    # Carga / volcado en JSON
    # ------------------------------------------------------------------
    @classmethod
    def from_json(cls, path: str | Path) -> "PolicyEngine":
        raw: list[dict[str, Any]] = json.loads(Path(path).read_text(encoding="utf-8"))
        policies = [
            Policy(
                policy_id=item["policy_id"],
                effect=Effect(item["effect"]),
                roles=tuple(item.get("roles", ["*"])),
                actions=tuple(item.get("actions", ["*"])),
                resources=tuple(item.get("resources", ["*"])),
                requires_approval=item.get("requires_approval", False),
                description=item.get("description", ""),
            )
            for item in raw
        ]
        return cls(policies)
