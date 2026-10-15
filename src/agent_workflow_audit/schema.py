"""Runtime validation for portable snapshot schema 1.0 (standard library only)."""

import math
import re
from datetime import datetime

from .io import AuditError, safe_relative

TABLE_IDS = {
    "tasks": "task_id", "executions": "execution_id", "states": "state_id", "attestations": "attestation_id",
    "evidence": "evidence_id", "decisions": "decision_id", "transitions": "transition_id",
}
KINDS = {"task": "tasks", "execution": "executions", "state": "states", "attestation": "attestations",
         "evidence": "evidence", "decision": "decisions", "transition": "transitions"}
FILE_STATUSES = ("match", "mismatch", "missing", "unreadable", "unknown")
TIME_FIELDS = ("created_at", "accepted_at", "started_at", "finished_at")
ACCOUNTING_FIELDS = ("input_tokens", "output_tokens", "cost_usd", "human_seconds")


def _string(row, key, required=False):
    value = row.get(key)
    if value is None and not required:
        return
    if not isinstance(value, str) or not value.strip():
        raise AuditError(f"{key} must be a nonempty string" + (" or null" if not required else ""))


def _timestamp(value, name, required=False):
    if value is None and not required:
        return
    if not isinstance(value, str):
        raise AuditError(f"{name} must be an ISO 8601 timestamp with timezone")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("timezone missing")
    except ValueError as error:
        raise AuditError(f"Invalid {name}: timezone-aware ISO 8601 required") from error


def _sha(value, name):
    if value is not None and (not isinstance(value, str) or not re.fullmatch(r"[a-f0-9]{64}", value)):
        raise AuditError(f"{name} must be a lowercase SHA-256 or null")


def validate_metadata(metadata, stages):
    if not isinstance(metadata, dict):
        raise AuditError("metadata must be an object")
    for key in ("dataset_id", "project_id"):
        _string(metadata, key, True)
    if metadata.get("data_kind") not in ("synthetic", "observational", "prospective"):
        raise AuditError("metadata.data_kind must be synthetic, observational, or prospective")
    _timestamp(metadata.get("captured_at"), "metadata.captured_at", True)
    if not isinstance(stages, list) or not stages or any(not isinstance(s, str) or not s.strip() for s in stages):
        raise AuditError("stages must be a nonempty list of stage names")
    if len(set(stages)) != len(stages):
        raise AuditError("Duplicate configured stages")


def validate_record(table, row):
    if table not in TABLE_IDS or not isinstance(row, dict):
        raise AuditError("Unknown record table or non-object record")
    _string(row, TABLE_IDS[table], True)
    if table == "tasks":
        _timestamp(row.get("enrolled_at"), "enrolled_at", True)
        _timestamp(row.get("closed_at"), "closed_at")
        for key in ("task_type", "initial_version_id", "condition", "assigned_workflow", "outcome"):
            _string(row, key)
        _sha(row.get("requirements_sha256"), "requirements_sha256")
        for key in ("budget_seconds", "budget_tokens", "budget_usd"):
            value = row.get(key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise AuditError(f"{key} must be finite and nonnegative or null")
        if row.get("closed_at") and datetime.fromisoformat(row["closed_at"].replace("Z", "+00:00")) < datetime.fromisoformat(row["enrolled_at"].replace("Z", "+00:00")):
            raise AuditError("Task closure precedes enrollment")
    elif table == "executions":
        _string(row, "status", True)
        for key in ("task_id", "version_id", "stage", "resource_id", "execution_kind", "engine", "model", "model_version", "client_version", "workflow_version", "condition"):
            _string(row, key)
        for key in TIME_FIELDS + ACCOUNTING_FIELDS:
            value = row.get(key)
            if value is not None and (type(value) not in (int, float) or not math.isfinite(value) or value < 0):
                raise AuditError(f"{key} must be finite and nonnegative or null")
        for key in ("input_tokens", "output_tokens"):
            if row.get(key) is not None and type(row[key]) is not int:
                raise AuditError(f"{key} must be an integer or null")
        known = [row[k] for k in TIME_FIELDS if row.get(k) is not None]
        if known != sorted(known):
            raise AuditError("Execution timestamps are out of order")
    elif table == "states":
        _string(row, "task_id", True)
        _string(row, "version_id")
        _string(row, "origin", True)
        for key in ("attempt", "revision"):
            if type(row.get(key)) is not int or row[key] < (1 if key == "attempt" else 0):
                raise AuditError(f"Invalid state {key}")
        if type(row.get("is_current")) is not bool:
            raise AuditError("is_current must be a boolean")
        for key in ("gate", "status", "condition"):
            _string(row, key)
    elif table == "attestations":
        for key in ("state_id", "stage"):
            _string(row, key, True)
        for key in ("execution_id", "evidence_id", "version_id"):
            _string(row, key)
    elif table == "evidence":
        _string(row, "version_id")
        _sha(row.get("expected_sha256"), "expected_sha256")
        if row.get("path") is not None:
            safe_relative(row["path"])
        observation = row.get("observation")
        if observation is not None:
            if not isinstance(observation, dict) or observation.get("status") not in FILE_STATUSES:
                raise AuditError("Invalid evidence observation status")
            if observation.get("basis") not in ("retained_observation", "live_verification", "synthetic"):
                raise AuditError("Observation basis must identify retained, live, or synthetic evidence")
            _timestamp(observation.get("observed_at"), "observed_at")
            _sha(observation.get("actual_sha256"), "actual_sha256")
            expected, actual = row.get("expected_sha256"), observation.get("actual_sha256")
            if observation["status"] == "match" and (not expected or not actual or expected != actual):
                raise AuditError("A matching observation requires equal expected and actual hashes")
            if observation["status"] == "mismatch" and (not expected or not actual or expected == actual):
                raise AuditError("A mismatch requires two different hashes")
            if observation["status"] == "missing" and actual is not None:
                raise AuditError("A missing file cannot have a measured actual hash")
    elif table == "decisions":
        for key in ("task_id", "decision"):
            _string(row, key, True)
        for key in ("version_id", "scope", "reviewer_id", "rubric_version"):
            _string(row, key)
        if row.get("reviewer_kind", "unknown") not in ("human", "agent", "unknown"):
            raise AuditError("Invalid reviewer_kind")
        _timestamp(row.get("decided_at"), "decided_at")
        if row.get("independent_reviewer") is not None and type(row["independent_reviewer"]) is not bool:
            raise AuditError("independent_reviewer must be boolean or null")
    elif table == "transitions":
        for key in ("task_id", "category"):
            _string(row, key, True)
        for key in ("from_state_id", "to_state_id"):
            _string(row, key)
        _timestamp(row.get("occurred_at"), "occurred_at")


def validate_dataset(dataset):
    if not isinstance(dataset, dict) or dataset.get("schema_version") != "1.0":
        raise AuditError("Only dataset schema_version 1.0 is supported")
    validate_metadata(dataset.get("metadata"), dataset.get("stages"))
    for table, key in TABLE_IDS.items():
        rows = dataset.get(table)
        if not isinstance(rows, list):
            raise AuditError(f"{table} must be an array, including when empty")
        seen = set()
        for index, row in enumerate(rows):
            try:
                validate_record(table, row)
            except AuditError as error:
                raise AuditError(f"{table}[{index}]: {error}") from error
            if row[key] in seen:
                raise AuditError(f"Duplicate {table} identifier: {row[key]}")
            seen.add(row[key])
    current = [s["task_id"] for s in dataset["states"] if s["is_current"]]
    if len(current) != len(set(current)):
        raise AuditError("Multiple current states for a task; resolve the snapshot explicitly")
    # Broken foreign keys are audit findings, not silently discarded schema errors.
    return dataset
