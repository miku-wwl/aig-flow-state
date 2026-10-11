"""Sanitized consumer evidence, separate from the unchanged Phase 1 schemas."""

import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4


class LiveAudit:
    def __init__(self, path):
        self.path = Path(path).resolve()
        with closing(self.connect()) as db:
            if db.execute("PRAGMA user_version").fetchone()[0] != 1:
                raise ValueError("Unsupported live audit schema")

    @classmethod
    def provision(cls, path):
        Path(path).touch(exist_ok=False)
        with closing(sqlite3.connect(path)) as db:
            db.execute("PRAGMA user_version=1")
            db.execute("CREATE TABLE events (event_id TEXT PRIMARY KEY, data TEXT NOT NULL) STRICT")
            db.commit()
        return cls(path)

    def connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=1)
        db.execute("PRAGMA synchronous=FULL")
        return db

    def record(
        self,
        classification,
        *,
        action_id=None,
        effect_key=None,
        plan_id=None,
        receipt_reference=None,
        operation="create_incident_handoff",
        diagnostics=None,
    ):
        # No payloads, tokens, exception messages, secrets or unfiltered provider metadata.
        value = {
            "event_id": str(uuid4()),
            "mode": "LIVE",
            "status": classification,
            "operation": operation,
            "action_id": action_id,
            "effect_key": effect_key,
            "plan_id": plan_id,
            "receipt_reference": receipt_reference,
            "created_at": datetime.now(UTC).isoformat(),
        }
        if diagnostics is not None:
            value["diagnostics"] = diagnostics
        with closing(self.connect()) as db:
            db.execute("INSERT INTO events VALUES (?,?)", (value["event_id"], json.dumps(value)))
            db.commit()
        return value

    def events(self):
        with closing(self.connect()) as db:
            return [
                json.loads(row[0]) for row in db.execute("SELECT data FROM events ORDER BY rowid")
            ]
