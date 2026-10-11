import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agentic_intent_gate.runtime import EXTERNAL_PAYLOAD_REVISION

from safeops.domain.handoff import valid_arguments


class StoreConflict(Exception):
    pass


class StoreIdentityMismatch(Exception):
    pass


def binding_identity(binding):
    return json.dumps(vars(binding), sort_keys=True, separators=(",", ":"))


class HandoffStore:
    """Business records only. Core Action claiming and receipts stay in the runtime."""

    def __init__(self, path, binding, store_id):
        self.path, self.binding, self.store_id = Path(path).resolve(), binding, store_id

    @classmethod
    def provision(cls, path, binding, store_id):
        Path(path).touch(exist_ok=False)
        store = cls(path, binding, store_id)
        with closing(sqlite3.connect(path)) as db:
            db.executescript("""
                PRAGMA journal_mode=WAL;
                PRAGMA synchronous=FULL;
                PRAGMA user_version=1;
                CREATE TABLE identity (
                    singleton INTEGER PRIMARY KEY CHECK(singleton=1),
                    store_id TEXT NOT NULL, binding_identity TEXT NOT NULL
                ) STRICT;
                CREATE TABLE handoffs (
                    effect_key TEXT PRIMARY KEY NOT NULL,
                    payload_digest TEXT NOT NULL,
                    store_id TEXT NOT NULL,
                    binding_identity TEXT NOT NULL,
                    incident_id TEXT NOT NULL,
                    summary TEXT NOT NULL,
                    handoff_note TEXT NOT NULL,
                    receipt_reference TEXT UNIQUE NOT NULL,
                    created_at TEXT NOT NULL
                ) STRICT;
                CREATE TABLE policy_evidence (
                    event_id TEXT PRIMARY KEY NOT NULL,
                    operation TEXT NOT NULL, status TEXT NOT NULL,
                    reason TEXT NOT NULL, effect_key TEXT,
                    mode TEXT NOT NULL CHECK(mode='MOCK'), created_at TEXT NOT NULL
                ) STRICT;
            """)
            db.execute("INSERT INTO identity VALUES (1,?,?)", (store_id, binding_identity(binding)))
            db.commit()
        return store

    def _connect(self):
        db = sqlite3.connect(self.path.as_uri() + "?mode=rw", uri=True, timeout=1)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA synchronous=FULL")
        return db

    def _check_identity(self, db):
        rows = db.execute(
            "SELECT store_id,binding_identity FROM identity WHERE singleton=1"
        ).fetchall()
        if db.execute("PRAGMA user_version").fetchone()[0] != 1 or [tuple(row) for row in rows] != [
            (self.store_id, binding_identity(self.binding))
        ]:
            raise StoreIdentityMismatch(
                "Business store identity does not match trusted configuration"
            )

    def validate(self):
        with closing(self._connect()) as db:
            self._check_identity(db)
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise StoreIdentityMismatch("Business store failed integrity check")
            expected = {
                "effect_key",
                "payload_digest",
                "store_id",
                "binding_identity",
                "incident_id",
                "summary",
                "handoff_note",
                "receipt_reference",
                "created_at",
            }
            columns = {row[1] for row in db.execute("PRAGMA table_info(handoffs)")}
            if columns != expected:
                raise StoreIdentityMismatch("Unsupported business schema; no automatic migration")

    def persist(self, spec, effect_key, context, *, lose_ack=False):
        if (
            not self.binding.matches(spec)
            or spec.identity_revision != EXTERNAL_PAYLOAD_REVISION
            or not valid_arguments(dict(spec.arguments))
        ):
            raise StoreIdentityMismatch("Effect specification does not match trusted store binding")
        with closing(self._connect()) as db:
            try:
                db.execute("BEGIN IMMEDIATE")
                self._check_identity(db)
                existing = db.execute(
                    "SELECT * FROM handoffs WHERE effect_key=?", (effect_key,)
                ).fetchone()
                args, digest = dict(spec.arguments), spec.payload_digest()
                if existing:
                    if existing["payload_digest"] != digest:
                        raise StoreConflict("Same effect key has a different payload")
                    if (
                        existing["store_id"] != self.store_id
                        or existing["binding_identity"] != binding_identity(self.binding)
                        or any(existing[key] != value for key, value in args.items())
                    ):
                        raise StoreIdentityMismatch("Stored effect does not match its digest")
                    return existing["receipt_reference"]
                if context.expired():
                    raise TimeoutError("Attempt expired before commit")
                receipt = str(uuid4())
                db.execute(
                    "INSERT INTO handoffs VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        effect_key,
                        digest,
                        self.store_id,
                        binding_identity(self.binding),
                        args["incident_id"],
                        args["summary"],
                        args["handoff_note"],
                        receipt,
                        datetime.now(UTC).isoformat(),
                    ),
                )
                if context.expired():
                    raise TimeoutError("Attempt expired before commit")
                db.commit()
                if lose_ack:
                    raise sqlite3.OperationalError("Injected post-commit acknowledgement loss")
                if context.expired():
                    raise TimeoutError("Attempt expired after commit")
                return receipt
            finally:
                if db.in_transaction:
                    db.rollback()

    def records(self):
        with closing(self._connect()) as db:
            self._check_identity(db)
            return [
                dict(row) for row in db.execute("SELECT * FROM handoffs ORDER BY created_at DESC")
            ]

    def record_policy(self, operation, decision, *, effect_key=None):
        with closing(self._connect()) as db:
            self._check_identity(db)
            db.execute(
                "INSERT INTO policy_evidence VALUES (?,?,?,?,?,?,?)",
                (
                    str(uuid4()),
                    operation,
                    decision.status.value,
                    decision.reason,
                    effect_key,
                    "MOCK",
                    datetime.now(UTC).isoformat(),
                ),
            )
            db.commit()

    def policy_evidence(self):
        with closing(self._connect()) as db:
            self._check_identity(db)
            return [
                dict(row) for row in db.execute("SELECT * FROM policy_evidence ORDER BY created_at")
            ]
