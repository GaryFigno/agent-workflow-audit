"""Recompute the frozen case and cross-check the generic auditor without engines."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import subprocess
import sys
import tempfile

from agent_workflow_audit.audit import audit_dataset
from agent_workflow_audit.io import AuditError, contained_path, read_json, write_json
from agent_workflow_audit.paper1 import import_paper1
from agent_workflow_audit.report import write_report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    study = Path(__file__).resolve().parents[1] / "studies/paper1"
    manifest = read_json(study / "reference_hashes.json")
    for entry in manifest["files"]:
        source = contained_path(args.source, entry["path"])
        if not source.is_file() or hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise AuditError(f"The supplied case is not the pinned Paper 1 data: {entry['path']}")
    with tempfile.TemporaryDirectory(prefix="awa-paper1-") as temporary:
        output = Path(temporary)
        commands = [
            [sys.executable, str(study / "analyze.py"), "--data", str(args.source / "data"), "--out", str(output)],
            [sys.executable, str(study / "extended_analysis.py"), "--data", str(args.source / "data"), "--out", str(output / "extended_results.json")],
        ]
        for command in commands:
            subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
        for name in ("results.json", "poi_histories.json", "extended_results.json"):
            if read_json(output / name) != read_json(args.source / "expected_results" / name):
                raise AuditError(f"Frozen numerical output differs: {name}")
        original = read_json(output / "results.json")
        extra = read_json(output / "extended_results.json")
    dataset = import_paper1(args.source)
    report = audit_dataset(dataset)
    historical = report["coverage"]["historical"]
    actual_joint = [[historical["joint"][status][column] for column in ("joined", "unmatched")]
                    for status in ("match", "missing")]
    if actual_joint != extra["historical_technical_joint"]["counts"]:
        raise AuditError("Generic historical evidence matrix differs")
    for group, old_group in (("linked_technical", "all"), ("current", "current")):
        actual = report["resources"][group]
        expected = original["chain_resource"][old_group]
        if actual["distinct_referenced"] != expected["distinct_referenced_tickets"] or actual["unmatched"] != expected["unmatched"]:
            raise AuditError(f"Generic resource IDs differ: {group}")
        for new_key, old_key in (("lease", "lease"), ("waiting", "wait")):
            if not math.isclose(actual[new_key]["sum_h"], expected[old_key]["sum_h"], rel_tol=1e-12):
                raise AuditError(f"Generic resource duration differs: {group}/{new_key}")
    if report["coverage"]["current"]["joint_coverage"] != 1.0:
        raise AuditError("Generic current technical coverage differs")
    if report["resources"]["historical"]["distinct_referenced"] != 1876:
        raise AuditError("Generic historical resource population differs")
    write_report(report, args.out)
    write_json(args.out / "normalized-dataset.json", dataset)
    receipt = {"pinned_files_verified": len(manifest["files"]), "frozen_numerical_outputs_reproduced": 3,
               "generic_historical_joint": actual_joint, "current_technical_coverage": 1.0,
               "linked_lease_hours": report["resources"]["linked_technical"]["lease"]["sum_h"],
               "historical_lease_hours": report["resources"]["historical"]["lease"]["sum_h"],
               "generic_and_frozen_results_agree": True,
               "original_file_checks_rerun": False}
    write_json(args.out / "verification.json", receipt)
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (AuditError, OSError, subprocess.CalledProcessError) as error:
        raise SystemExit(str(error))
