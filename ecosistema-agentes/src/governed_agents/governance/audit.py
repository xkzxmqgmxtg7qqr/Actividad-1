"""Registro de auditoría inmutable con encadenamiento de hashes.

Cada evento incluye el hash SHA-256 del evento anterior, de modo que
cualquier alteración retroactiva del registro rompe la cadena y puede
detectarse con :meth:`AuditLog.verify_integrity`.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Iterator


@dataclass(frozen=True)
class AuditEvent:
    sequence: int
    timestamp: float
    event_type: str  # "task_submitted", "action_allowed", "action_denied", ...
    agent_id: str
    detail: dict[str, Any]
    previous_hash: str
    event_hash: str = field(default="", compare=False)

    def compute_hash(self) -> str:
        body = {
            "sequence": self.sequence,
            "timestamp": self.timestamp,
            "event_type": self.event_type,
            "agent_id": self.agent_id,
            "detail": self.detail,
            "previous_hash": self.previous_hash,
        }
        serialized = json.dumps(body, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


_GENESIS_HASH = "0" * 64


class AuditLog:
    def __init__(self) -> None:
        self._events: list[AuditEvent] = []

    def record(self, event_type: str, agent_id: str, detail: dict[str, Any]) -> AuditEvent:
        previous_hash = self._events[-1].event_hash if self._events else _GENESIS_HASH
        event = AuditEvent(
            sequence=len(self._events),
            timestamp=time.time(),
            event_type=event_type,
            agent_id=agent_id,
            detail=detail,
            previous_hash=previous_hash,
        )
        event = AuditEvent(**{**asdict(event), "event_hash": event.compute_hash()})
        self._events.append(event)
        return event

    def events(self, agent_id: str | None = None, event_type: str | None = None) -> Iterator[AuditEvent]:
        for event in self._events:
            if agent_id is not None and event.agent_id != agent_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            yield event

    def verify_integrity(self) -> bool:
        previous_hash = _GENESIS_HASH
        for event in self._events:
            if event.previous_hash != previous_hash or event.compute_hash() != event.event_hash:
                return False
            previous_hash = event.event_hash
        return True

    def __len__(self) -> int:
        return len(self._events)
