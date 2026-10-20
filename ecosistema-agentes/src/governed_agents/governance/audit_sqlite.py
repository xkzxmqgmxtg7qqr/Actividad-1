"""Auditoría persistente sobre SQLite.

Misma semántica que :class:`governed_agents.governance.audit.AuditLog`
(cadena de hashes SHA-256, denegación de manipulación), pero los eventos
sobreviven a reinicios del proceso. La integridad puede verificarse al
recargar: si alguien editó la base de datos a mano, la cadena se rompe.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterator

from governed_agents.governance.audit import AuditEvent, _GENESIS_HASH


class SqliteAuditLog:
    def __init__(self, path: str | Path = ":memory:") -> None:
        self._lock = threading.Lock()
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                sequence      INTEGER PRIMARY KEY,
                timestamp     REAL NOT NULL,
                event_type    TEXT NOT NULL,
                agent_id      TEXT NOT NULL,
                detail        TEXT NOT NULL,
                previous_hash TEXT NOT NULL,
                event_hash    TEXT NOT NULL
            )
            """
        )
        self._conn.commit()

    def record(self, event_type: str, agent_id: str, detail: dict[str, Any]) -> AuditEvent:
        with self._lock:
            row = self._conn.execute(
                "SELECT sequence, event_hash FROM audit_events ORDER BY sequence DESC LIMIT 1"
            ).fetchone()
            sequence = 0 if row is None else row[0] + 1
            previous_hash = _GENESIS_HASH if row is None else row[1]
            event = AuditEvent(
                sequence=sequence,
                timestamp=time.time(),
                event_type=event_type,
                agent_id=agent_id,
                detail=detail,
                previous_hash=previous_hash,
            )
            event = AuditEvent(
                sequence=event.sequence,
                timestamp=event.timestamp,
                event_type=event.event_type,
                agent_id=event.agent_id,
                detail=event.detail,
                previous_hash=event.previous_hash,
                event_hash=event.compute_hash(),
            )
            self._conn.execute(
                "INSERT INTO audit_events VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    event.sequence,
                    event.timestamp,
                    event.event_type,
                    event.agent_id,
                    json.dumps(event.detail, ensure_ascii=False),
                    event.previous_hash,
                    event.event_hash,
                ),
            )
            self._conn.commit()
            return event

    def _rows(self) -> Iterator[AuditEvent]:
        cursor = self._conn.execute(
            "SELECT sequence, timestamp, event_type, agent_id, detail, previous_hash, event_hash "
            "FROM audit_events ORDER BY sequence"
        )
        for seq, ts, etype, agent, detail, prev, ehash in cursor.fetchall():
            yield AuditEvent(
                sequence=seq,
                timestamp=ts,
                event_type=etype,
                agent_id=agent,
                detail=json.loads(detail),
                previous_hash=prev,
                event_hash=ehash,
            )

    def events(self, agent_id: str | None = None, event_type: str | None = None) -> Iterator[AuditEvent]:
        with self._lock:
            all_events = list(self._rows())
        for event in all_events:
            if agent_id is not None and event.agent_id != agent_id:
                continue
            if event_type is not None and event.event_type != event_type:
                continue
            yield event

    def verify_integrity(self) -> bool:
        previous_hash = _GENESIS_HASH
        for event in self.events():
            if event.previous_hash != previous_hash or event.compute_hash() != event.event_hash:
                return False
            previous_hash = event.event_hash
        return True

    def __len__(self) -> int:
        with self._lock:
            (count,) = self._conn.execute("SELECT COUNT(*) FROM audit_events").fetchone()
        return count

    def close(self) -> None:
        self._conn.close()
