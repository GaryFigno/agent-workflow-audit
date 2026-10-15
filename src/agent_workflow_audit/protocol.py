"""Local protocol freezing. A local freeze is not external preregistration."""

from .io import AuditError, canonical, digest_bytes, utc_now


def freeze_protocol(protocol):
    if not isinstance(protocol, dict) or protocol.get("status") != "draft":
        raise AuditError("Protocol must be a draft object")
    for key in ("protocol_id", "project_id", "design", "primary_unit", "enrollment_rule", "stopping_rule", "missing_data_policy"):
        if not isinstance(protocol.get(key), str) or not protocol[key].strip():
            raise AuditError(f"Complete protocol field before freezing: {key}")
    if protocol["design"] not in ("prospective_observational", "controlled_comparison"):
        raise AuditError("Choose prospective_observational or controlled_comparison")
    for key in ("stages", "primary_outcomes"):
        if not isinstance(protocol.get(key), list) or not protocol[key] or any(not isinstance(v, str) or not v.strip() for v in protocol[key]):
            raise AuditError(f"Complete protocol list before freezing: {key}")
    if len(set(protocol["stages"])) != len(protocol["stages"]):
        raise AuditError("Protocol stages must be unique")
    if protocol["design"] == "controlled_comparison":
        for key in ("conditions", "allocation_rule", "budget_rule", "independent_outcome_assessment"):
            if not protocol.get(key):
                raise AuditError(f"A controlled comparison requires: {key}")
    frozen = {**protocol, "status": "frozen_locally", "frozen_at": utc_now(),
              "preregistration": "Not registered externally by this tool"}
    return frozen, digest_bytes(canonical(frozen).encode("utf-8"))
