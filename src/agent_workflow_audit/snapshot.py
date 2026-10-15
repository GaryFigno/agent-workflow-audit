"""Freeze exact inputs, optional evidence bytes, and a verifiable file manifest."""

from pathlib import Path
import shutil

from .audit import audit_dataset
from .io import AuditError, canonical, contained_path, file_digest, make_manifest, parse_json, read_json, verify_manifest, write_json
from .journal import verify_exported_events
from .report import render_html
from .schema import validate_dataset


def freeze_snapshot(dataset, directory, evidence_root=None, events=None, protocol=None):
    validate_dataset(dataset)
    report = audit_dataset(dataset, evidence_root)
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "dataset.json", dataset)
    if evidence_root is not None:
        for evidence in dataset["evidence"]:
            observation = report["evidence_observations"][evidence["evidence_id"]]
            if evidence.get("path") is None or observation.get("actual_sha256") is None:
                continue
            source = contained_path(evidence_root, evidence["path"])
            target = contained_path(directory / "evidence", evidence["path"])
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copyfile(source, target)
            if file_digest(target) != observation["actual_sha256"]:
                raise AuditError("Evidence changed during snapshot capture; output is incomplete")
    if events is not None:
        verify_exported_events(dataset, events)
        with (directory / "events.jsonl").open("x", encoding="utf-8", newline="\n") as stream:
            for event in events:
                stream.write(canonical(event) + "\n")
    if protocol is not None:
        write_json(directory / "protocol.json", protocol)
    report["input_sha256"] = file_digest(directory / "dataset.json")
    write_json(directory / "report.json", report)
    (directory / "report.html").write_text(render_html(report), encoding="utf-8")
    write_json(directory / "manifest.json", make_manifest(directory))
    return verify_snapshot(directory)


def verify_snapshot(directory, expected_manifest_sha256=None):
    directory = Path(directory)
    result = verify_manifest(directory, expected_manifest_sha256)
    dataset = validate_dataset(read_json(directory / "dataset.json"))
    events_path = directory / "events.jsonl"
    if events_path.is_file():
        events = [parse_json(line) for line in events_path.read_text(encoding="utf-8").splitlines() if line]
        result.update(verify_exported_events(dataset, events))
    report_path = directory / "report.json"
    if report_path.is_file() and read_json(report_path).get("input_sha256") != file_digest(directory / "dataset.json"):
        raise AuditError("Report is bound to a different input dataset")
    return result
