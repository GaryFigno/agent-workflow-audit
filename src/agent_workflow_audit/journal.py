"""Transactional append-only event interface with a verifiable hash chain.

The chain detects changes relative to a retained tip. It is not a signature,
independent timestamp, or guarantee against an operator rewriting the whole DB.
"""

from pathlib import Path
import copy
from contextlib import closing
import sqlite3
import uuid

from . import __version__
from .io import AuditError, canonical, digest_bytes, parse_json, utc_now
from .schema import KINDS, TABLE_IDS, validate_dataset, validate_metadata, validate_record


def _connect(path):
    path = Path(path).resolve()
    if not path.is_file():
        raise AuditError("Journal does not exist; run init first")
    connection = sqlite3.connect(path.as_uri() + "?mode=rw", uri=True, timeout=10)
    connection.row_factory = sqlite3.Row
    return connection


def initialize(path, metadata, stages, protocol=None):
    validate_metadata(metadata, stages)
    if protocol is not None and not isinstance(protocol, dict):
        raise AuditError("Protocol must be a JSON object")
    if metadata["data_kind"] == "prospective" and (not protocol or protocol.get("status") != "frozen_locally"):
        raise AuditError("Prospective collection requires a locally frozen protocol")
    if protocol and (protocol.get("project_id") != metadata["project_id"] or protocol.get("stages") != stages):
        raise AuditError("Journal project and stages must match the protocol")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally initializing over an existing study.
    with path.open("xb"):
        pass
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.executescript("""
            CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE events (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                event_id TEXT NOT NULL UNIQUE,
                recorded_at TEXT NOT NULL,
                kind TEXT NOT NULL,
                record_json TEXT NOT NULL,
                previous_sha256 TEXT NOT NULL,
                event_sha256 TEXT NOT NULL
            );
        """)
        settings = {"metadata": metadata, "stages": stages, "protocol": protocol,
                    "journal_version": 1, "tool_version": __version__}
        connection.executemany("INSERT INTO settings VALUES (?, ?)", [(k, canonical(v)) for k, v in settings.items()])
    return {"journal": str(path), "events": 0, "data_kind": metadata["data_kind"]}


def _settings(connection):
    return {row["key"]: parse_json(row["value"]) for row in connection.execute("SELECT key, value FROM settings")}


def _genesis(settings):
    return digest_bytes(canonical(settings).encode("utf-8"))


def _event_hash(event_id, recorded_at, kind, record, previous):
    return digest_bytes(canonical({"event_id": event_id, "recorded_at": recorded_at, "kind": kind,
                                   "record": record, "previous_sha256": previous}).encode("utf-8"))


def _verified_rows(connection, settings):
    previous = _genesis(settings)
    rows = list(connection.execute("SELECT * FROM events ORDER BY sequence"))
    for number, row in enumerate(rows, 1):
        record = parse_json(row["record_json"])
        expected = _event_hash(row["event_id"], row["recorded_at"], row["kind"], record, previous)
        if row["sequence"] != number or row["previous_sha256"] != previous or row["event_sha256"] != expected:
            raise AuditError(f"Journal integrity failure at sequence {number}")
        if row["kind"] not in KINDS:
            raise AuditError(f"Unknown journal kind at sequence {number}")
        validate_record(KINDS[row["kind"]], record)
        previous = row["event_sha256"]
    return rows, previous


def append_event(path, kind, record, event_id=None):
    if kind not in KINDS:
        raise AuditError(f"Unsupported event kind: {kind}")
    validate_record(KINDS[kind], record)
    event_id = event_id or str(uuid.uuid4())
    if not isinstance(event_id, str) or not event_id.strip():
        raise AuditError("event_id must be nonempty")
    with closing(_connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        settings = _settings(connection)
        rows, tip = _verified_rows(connection, settings)
        existing = connection.execute("SELECT * FROM events WHERE event_id=?", (event_id,)).fetchone()
        if existing:
            if existing["kind"] != kind or parse_json(existing["record_json"]) != record:
                raise AuditError("An event_id cannot be reused for different content")
            return {"event_id": event_id, "sequence": existing["sequence"], "idempotent": True, "event_sha256": existing["event_sha256"]}
        recorded_at = utc_now()
        event_hash = _event_hash(event_id, recorded_at, kind, record, tip)
        connection.execute("INSERT INTO events(event_id, recorded_at, kind, record_json, previous_sha256, event_sha256) VALUES (?, ?, ?, ?, ?, ?)",
                           (event_id, recorded_at, kind, canonical(record), tip, event_hash))
        return {"event_id": event_id, "sequence": len(rows) + 1, "idempotent": False, "event_sha256": event_hash}


def export_journal(path):
    with closing(_connect(path)) as connection, connection:
        # One read transaction: metadata and all event rows belong to the same snapshot.
        connection.execute("BEGIN")
        settings = _settings(connection)
        rows, tip = _verified_rows(connection, settings)
    tables = {name: {} for name in TABLE_IDS}
    events = []
    current_order = {}
    for row in rows:
        record = parse_json(row["record_json"])
        table = KINDS[row["kind"]]
        tables[table][record[TABLE_IDS[table]]] = copy.deepcopy(record)
        if table == "states":
            current_order[record["state_id"]] = row["sequence"]
        events.append({"sequence": row["sequence"], "event_id": row["event_id"], "recorded_at": row["recorded_at"],
                       "kind": row["kind"], "record": record, "previous_sha256": row["previous_sha256"], "event_sha256": row["event_sha256"]})
    candidates = {}
    for state in tables["states"].values():
        if state["is_current"]:
            task = state["task_id"]
            if task not in candidates or current_order[state["state_id"]] > current_order[candidates[task]]:
                candidates[task] = state["state_id"]
    demoted = []
    for state in tables["states"].values():
        if state["is_current"] and candidates[state["task_id"]] != state["state_id"]:
            state["is_current"] = False
            demoted.append(state["state_id"])
    metadata = {**settings["metadata"], "captured_at": utc_now(), "journal_tip_sha256": tip,
                "journal_genesis_sha256": _genesis(settings),
                "journal_event_count": len(rows), "projection": "latest record per ID; latest declared current state per task",
                "projection_demoted_states": demoted}
    protocol = settings["protocol"]
    if protocol is not None:
        metadata["protocol_sha256"] = digest_bytes(canonical(protocol).encode("utf-8"))
        metadata["protocol_status"] = protocol.get("status", "unspecified")
    dataset = {"schema_version": "1.0", "metadata": metadata, "stages": settings["stages"],
               **{table: list(records.values()) for table, records in tables.items()}}
    validate_dataset(dataset)
    return dataset, events, protocol


def verify_exported_events(dataset, events):
    metadata = dataset["metadata"]
    previous = metadata.get("journal_genesis_sha256")
    if not previous or len(events) != metadata.get("journal_event_count"):
        raise AuditError("Exported journal event count or genesis is inconsistent")
    ids = set()
    for number, event in enumerate(events, 1):
        expected = _event_hash(event["event_id"], event["recorded_at"], event["kind"], event["record"], previous)
        if event["sequence"] != number or event["previous_sha256"] != previous or event["event_sha256"] != expected:
            raise AuditError(f"Exported event integrity failure at sequence {number}")
        if event["event_id"] in ids:
            raise AuditError("Duplicate exported event identifier")
        ids.add(event["event_id"])
        previous = expected
    if previous != metadata.get("journal_tip_sha256"):
        raise AuditError("Exported journal tip is inconsistent")
    return {"events_verified": len(events), "tip_sha256": previous}
