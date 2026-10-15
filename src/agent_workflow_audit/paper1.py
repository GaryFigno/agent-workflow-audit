"""Explicit adapter for the frozen Paper 1 reduced records, not a live extractor."""

from .io import canonical, digest_bytes, read_json
from .schema import validate_dataset

VERSION_FIELDS = ("claim_sha256", "pack_input_digest", "owned_content_digest", "factory_code_digest",
                  "factory_release_id", "factory_release_manifest_sha256", "unreal_execution_stack_digest")


def _version(row):
    values = {field: row.get(field) for field in VERSION_FIELDS}
    return digest_bytes(canonical(values).encode("utf-8")) if all(values.values()) else None


def _state_id(poi, attempt, epoch):
    return f"{poi}:{attempt}:{epoch}"


def import_paper1(directory):
    def read(name):
        return read_json(directory / "data" / f"{name}.json")
    states, tickets, observations, archives, catalog = map(read, ("states", "tickets", "evidence_observations", "archives", "catalog"))
    stages = ["build", "validation", "idempotent_build", "traversal", "capture"]
    provenance = read_json(directory / "provenance.json")
    observed_at = provenance["archive_capture_finished_utc"]
    result = {"schema_version": "1.0", "metadata": {
        "dataset_id": "paper1-frozen-2026-10-15", "project_id": "Cinderage",
        "data_kind": "observational", "captured_at": observed_at,
        "execution_population": "Shared broker across projects; only linked attestations are scene-scoped",
        "observation_note": "Audit observations preserved from Paper 1; original evidence files are not rechecked",
        "source_manifest_sha256": digest_bytes((directory / "manifest.json").read_bytes()),
        "version_definition": "SHA-256 of all seven retained version fields; null if any field is absent"},
        "stages": stages, "tasks": [], "states": [], "executions": [], "attestations": [], "evidence": [], "decisions": [], "transitions": []}
    obsmap = {(e["poi_id"], e["attempt"], e["epoch"], e["step"]): e for e in observations}
    execution_bindings = {}
    for state in states:
        sid = _state_id(state["poi_id"], state["assignment_attempt"], state["assignment_epoch"])
        version = _version(state)
        result["states"].append({"state_id": sid, "task_id": state["poi_id"], "version_id": version,
                                 "attempt": state["assignment_attempt"], "revision": state["assignment_epoch"],
                                 "is_current": state["origin"] == "current", "origin": state["origin"],
                                 "gate": state["current_gate"], "status": state["status"]})
        for stage, attestation in state["attestations"].items():
            aid = f"{sid}:{stage}"
            result["attestations"].append({"attestation_id": aid, "state_id": sid, "stage": stage,
                                           "execution_id": attestation.get("broker_request_id"), "evidence_id": aid,
                                           "version_id": _version(attestation)})
            observation = obsmap.get((state["poi_id"], state["assignment_attempt"], state["assignment_epoch"], stage))
            evidence = {"evidence_id": aid, "version_id": _version(attestation), "path": None,
                        "expected_sha256": attestation.get("evidence_sha256")}
            if observation:
                status = "missing" if not observation["exists"] else ("match" if observation["hash_match"] else "mismatch")
                evidence["observation"] = {"status": status, "basis": "retained_observation",
                                           "observed_at": observed_at, "actual_sha256": observation.get("actual_sha256")}
            result["evidence"].append(evidence)
            request = attestation.get("broker_request_id")
            if request:
                execution_bindings[request] = {"task_id": state["poi_id"], "version_id": version, "stage": stage}
    for ticket in tickets:
        result["executions"].append({"execution_id": ticket["request_id"], "status": ticket["status"],
                                     "engine": ticket["app"], "resource_id": "shared-native-slot",
                                     **{key: ticket.get(key) for key in ("created_at", "accepted_at", "started_at", "finished_at")},
                                     **execution_bindings.get(ticket["request_id"], {})})
    by_attempt = {(s["task_id"], s["attempt"]): s["state_id"] for s in result["states"]}
    for archive in archives:
        source_id = _state_id(archive["poi_id"], archive["attempt"], archive["epoch"])
        result["transitions"].append({"transition_id": archive["sha256"], "task_id": archive["poi_id"],
                                      "from_state_id": source_id, "to_state_id": by_attempt.get((archive["poi_id"], archive["attempt"] + 1)),
                                      "category": archive["kind"], "occurred_at": None})
    for index, entry in enumerate(catalog):
        if entry.get("project") != "Cinderage":
            continue
        result["decisions"].append({"decision_id": f"catalog-{index}", "task_id": entry["poi_id"],
                                    "version_id": None, "decision": "recorded_fixed" if entry["fixed"] else "recorded_not_fixed",
                                    "scope": "Review catalog flag; exact scene bytes not recorded by this adapter",
                                    "reviewer_kind": "unknown", "decided_at": None})
    return validate_dataset(result)
