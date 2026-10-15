"""Descriptive accounting; unknown observations never become measured zeros."""

from collections import Counter, defaultdict
from pathlib import Path
import math
import statistics

from . import __version__
from .io import AuditError, contained_path, file_digest, utc_now
from .schema import ACCOUNTING_FIELDS, FILE_STATUSES, validate_dataset


def distribution(values):
    values = sorted(values)
    count = len(values)
    if not count:
        return {"n": 0, "sum_s": None, "sum_h": None, "median_s": None,
                "p90_s": None, "p99_s": None, "top_decile_sum_share": None}
    total = sum(values)
    return {"n": count, "sum_s": total, "sum_h": total / 3600,
            "median_s": statistics.median(values),
            "p90_s": values[math.floor(.9 * (count - 1))],
            "p99_s": values[math.floor(.99 * (count - 1))],
            "top_decile_sum_share": sum(values[-math.ceil(count / 10):]) / total if total else None}


def resource_summary(rows):
    waits, leases, comparable = [], [], []
    for row in rows:
        wait = row["started_at"] - row["accepted_at"] if row.get("started_at") is not None and row.get("accepted_at") is not None else None
        lease = row["finished_at"] - row["started_at"] if row.get("finished_at") is not None and row.get("started_at") is not None else None
        if wait is not None:
            waits.append(wait)
        if lease is not None:
            leases.append(lease)
        if wait is not None and lease is not None:
            comparable.append(wait > lease)
    reported = {}
    for key in ACCOUNTING_FIELDS:
        known = [row[key] for row in rows if row.get(key) is not None]
        reported[key] = {"known_n": len(known), "unknown_n": len(rows) - len(known),
                         "known_sum": sum(known) if known else None}
    return {"requests": len(rows), "status_counts": dict(sorted(Counter(r["status"] for r in rows).items())),
            "waiting": distribution(waits), "lease": distribution(leases),
            "unknown_wait_n": len(rows) - len(waits), "unknown_lease_n": len(rows) - len(leases),
            "wait_exceeds_lease": sum(comparable), "wait_lease_comparable_n": len(comparable),
            "reported_accounting": reported}


def inspect_evidence(record, root=None):
    if root is None:
        observation = record.get("observation")
        return dict(observation) if observation else {"status": "unknown", "basis": "not_observed", "actual_sha256": None}
    result = {"status": "unknown", "basis": "live_verification", "observed_at": utc_now(), "actual_sha256": None}
    if record.get("path") is None:
        result["reason"] = "No relative evidence path is available"
        return result
    path = contained_path(root, record["path"])
    try:
        if not path.is_file():
            result["status"] = "missing"
        else:
            actual = file_digest(path)
            result["actual_sha256"] = actual
            expected = record.get("expected_sha256")
            result["status"] = "unknown" if expected is None else ("match" if expected == actual else "mismatch")
            if expected is None:
                result["reason"] = "File readable but no pre-existing expected hash"
    except OSError as error:
        result.update(status="unreadable", reason=type(error).__name__)
    return result


def _version_relation(state, related):
    if not state or not related or not state.get("version_id") or not related.get("version_id"):
        return "unknown"
    return "match" if state["version_id"] == related["version_id"] else "mismatch"


def audit_dataset(dataset, evidence_root=None):
    validate_dataset(dataset)
    if evidence_root is not None and not Path(evidence_root).is_dir():
        raise AuditError("The evidence root must be an existing directory")
    states = {s["state_id"]: s for s in dataset["states"]}
    executions = {r["execution_id"]: r for r in dataset["executions"]}
    evidence = {e["evidence_id"]: e for e in dataset["evidence"]}
    observations = {key: inspect_evidence(record, evidence_root) for key, record in evidence.items()}
    technical = [a for a in dataset["attestations"] if a["stage"] in dataset["stages"]]
    detail = []
    cohorts = defaultdict(list)
    steps = defaultdict(set)
    cohort_ids = defaultdict(set)
    stage_ids = defaultdict(set)
    for item in technical:
        state = states.get(item["state_id"])
        cohort = "unresolved_state" if state is None else ("current" if state["is_current"] else "historical")
        execution = executions.get(item.get("execution_id"))
        file_record = evidence.get(item.get("evidence_id"))
        file_result = observations.get(item.get("evidence_id"), {"status": "unknown", "basis": "missing_evidence_reference"})
        row = {"attestation_id": item["attestation_id"], "state_id": item["state_id"],
               "stage": item["stage"], "cohort": cohort, "file_status": file_result["status"],
               "observation_basis": file_result["basis"], "execution_joined": execution is not None,
               "execution_status": execution.get("status") if execution else None,
               "execution_version": _version_relation(state, execution),
               "evidence_version": _version_relation(state, file_record),
               "attestation_version": _version_relation(state, item),
               "execution_task_mismatch": bool(state and execution and execution.get("task_id") and execution["task_id"] != state["task_id"])}
        detail.append(row)
        cohorts[cohort].append(row)
        steps[item["state_id"]].add(item["stage"])
        if item.get("execution_id"):
            cohort_ids[cohort].add(item["execution_id"])
            stage_ids[item["stage"]].add(item["execution_id"])
    coverage = {}
    for name in ("current", "historical", "unresolved_state", "all"):
        rows = detail if name == "all" else cohorts[name]
        joint = {status: {"joined": 0, "unmatched": 0} for status in FILE_STATUSES}
        for row in rows:
            joint[row["file_status"]]["joined" if row["execution_joined"] else "unmatched"] += 1
        coverage[name] = {"attestations": len(rows), "joint": joint,
                          "both_file_match_and_execution_join": joint["match"]["joined"],
                          "joint_coverage": joint["match"]["joined"] / len(rows) if rows else None}

    def summarize_ids(ids):
        return {"distinct_referenced": len(ids), "unmatched": len(ids - executions.keys()),
                **resource_summary([executions[key] for key in sorted(ids) if key in executions])}

    current_ids, historical_ids = cohort_ids["current"], cohort_ids["historical"]
    all_ids = set().union(*cohort_ids.values()) if cohort_ids else set()
    resources = {"all_recorded_executions": resource_summary(dataset["executions"]),
                 "linked_technical": summarize_ids(all_ids),
                 "current": summarize_ids(current_ids), "historical": summarize_ids(historical_ids),
                 "current_only": summarize_ids(current_ids - historical_ids),
                 "historical_only": summarize_ids(historical_ids - current_ids),
                 "shared_current_historical": summarize_ids(current_ids & historical_ids),
                 "unresolved_state_only": summarize_ids(cohort_ids["unresolved_state"] - current_ids - historical_ids),
                 "by_stage": {stage: summarize_ids(stage_ids[stage]) for stage in dataset["stages"]},
                 "stage_subtotals_may_overlap": len(set().union(*stage_ids.values())) < sum(map(len, stage_ids.values())) if stage_ids else False}
    resources["by_resource"] = {resource: resource_summary([row for row in dataset["executions"] if (row.get("resource_id") or "unrecorded") == resource])
                                for resource in sorted({row.get("resource_id") or "unrecorded" for row in dataset["executions"]})}
    decisions = []
    for decision in dataset["decisions"]:
        candidates = [s for s in dataset["states"] if s["task_id"] == decision["task_id"]]
        matched = [s for s in candidates if decision.get("version_id") and s.get("version_id") == decision["version_id"]]
        binding = "current_version" if any(s["is_current"] for s in matched) else ("historical_version" if matched else "unresolved")
        decisions.append({"decision_id": decision["decision_id"], "decision": decision["decision"],
                          "binding": binding, "scope_recorded": bool(decision.get("scope")),
                          "reviewer_kind": decision.get("reviewer_kind", "unknown"),
                          "matched_state_ids": [s["state_id"] for s in matched]})
    histories = []
    for task in sorted({s["task_id"] for s in dataset["states"]}):
        rows = [s for s in dataset["states"] if s["task_id"] == task]
        attempts = {s["attempt"] for s in rows}
        end = max(attempts)
        histories.append({"task_id": task, "observed_attempts": sorted(attempts),
                          "missing_numbered_positions": [n for n in range(1, end + 1) if n not in attempts],
                          "current_state_ids": [s["state_id"] for s in rows if s["is_current"]]})
    broken_transitions = [t["transition_id"] for t in dataset["transitions"]
                          if any(t.get(k) and t[k] not in states for k in ("from_state_id", "to_state_id"))]
    findings = {"file_not_verified": sum(r["file_status"] != "match" for r in detail),
                "execution_not_joined": sum(not r["execution_joined"] for r in detail),
                "version_mismatches": sum(any(r[k] == "mismatch" for k in ("execution_version", "evidence_version", "attestation_version")) for r in detail),
                "execution_task_mismatches": sum(r["execution_task_mismatch"] for r in detail),
                "unresolved_state_references": len(cohorts["unresolved_state"]),
                "unresolved_decision_versions": sum(d["binding"] == "unresolved" for d in decisions),
                "decisions_without_scope": sum(not d["scope_recorded"] for d in decisions),
                "broken_transition_references": len(broken_transitions)}
    return {"report_version": "1.0", "tool_version": __version__, "metadata": dataset["metadata"],
            "stages": dataset["stages"], "verification_mode": "live_files" if evidence_root is not None else "retained_observations_only",
            "units": {table: len(dataset[table]) for table in ("tasks", "states", "executions", "attestations", "evidence", "decisions", "transitions")},
            "enrollment": {"recorded_tasks": len(dataset["tasks"]),
                           "tasks_with_closure": sum(bool(t.get("closed_at")) for t in dataset["tasks"]),
                           "state_tasks_without_enrollment": sorted({s["task_id"] for s in dataset["states"]} - {t["task_id"] for t in dataset["tasks"]})},
            "coverage": coverage, "resources": resources, "findings": findings,
            "stage_presence": [{"state_id": key, "complete": set(dataset["stages"]).issubset(steps[key]),
                                "missing_stages": [s for s in dataset["stages"] if s not in steps[key]]} for key in states],
            "evidence_audit": detail, "evidence_observations": observations,
            "decisions": decisions, "histories": histories,
            "transition_categories": dict(sorted(Counter(t["category"] for t in dataset["transitions"]).items())),
            "broken_transition_ids": broken_transitions,
            "limits": ["File matching and execution linkage are not proof of execution correctness or accepted quality.",
                       "Stage completeness means recorded stage presence, not successful independent tests.",
                       "Lease time is resource occupancy; summed waiting can overlap and is not lost labor.",
                       "Current and historical resource groups may overlap; use exclusive groups for additive accounting.",
                       "Null costs and durations remain unknown; sums include only observed values.",
                       "Numbered gaps are unobserved positions, not inferred failures.",
                       "An unresolved decision is a missing version association, not proof the decision was wrong."]}
