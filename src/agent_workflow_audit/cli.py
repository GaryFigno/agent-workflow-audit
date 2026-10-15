"""Public command-line interface."""

import argparse
import json
from pathlib import Path
import sqlite3
import sys

from . import __version__
from .audit import audit_dataset
from .io import AuditError, file_digest, read_json, utc_now, write_json
from .journal import append_event, export_journal, initialize
from .paper1 import import_paper1
from .protocol import freeze_protocol
from .report import write_report
from .schema import KINDS, validate_dataset
from .snapshot import freeze_snapshot, verify_snapshot


def parser():
    root = argparse.ArgumentParser(description="Offline workflow evidence and resource audits. No engine or model is called.")
    root.add_argument("--version", action="version", version=__version__)
    commands = root.add_subparsers(dest="command", required=True)
    validate = commands.add_parser("validate", help="Validate a schema 1.0 dataset")
    validate.add_argument("dataset", type=Path)
    audit = commands.add_parser("audit", help="Write JSON and HTML audit reports")
    audit.add_argument("dataset", type=Path)
    audit.add_argument("--out", type=Path, required=True, help="A new report directory")
    audit.add_argument("--evidence-root", type=Path, help="Explicitly recheck evidence under this directory")
    audit.add_argument("--fail-on-gaps", action="store_true", help="Exit 3 if any recorded gap exists")
    init = commands.add_parser("init", help="Create a new event journal without overwriting")
    init.add_argument("--journal", type=Path, required=True)
    init.add_argument("--project", required=True)
    init.add_argument("--dataset-id", required=True)
    init.add_argument("--kind", choices=("synthetic", "observational", "prospective"), required=True)
    init.add_argument("--stages", nargs="+", required=True)
    init.add_argument("--protocol", type=Path)
    record = commands.add_parser("record", help="Append a record; repeat the same event ID for idempotent retry")
    record.add_argument("--journal", type=Path, required=True)
    record.add_argument("--kind", choices=tuple(KINDS), required=True)
    record.add_argument("--file", type=Path, required=True)
    record.add_argument("--event-id")
    export = commands.add_parser("export", help="Freeze a consistent journal snapshot, history, and report")
    export.add_argument("--journal", type=Path, required=True)
    export.add_argument("--out", type=Path, required=True)
    export.add_argument("--evidence-root", type=Path)
    freeze = commands.add_parser("freeze", help="Freeze a portable dataset and optional evidence bytes")
    freeze.add_argument("dataset", type=Path)
    freeze.add_argument("--out", type=Path, required=True)
    freeze.add_argument("--evidence-root", type=Path)
    verify = commands.add_parser("verify", help="Verify a frozen packet and any included journal chain")
    verify.add_argument("directory", type=Path)
    verify.add_argument("--manifest-sha256", help="Previously retained external manifest hash")
    protocol = commands.add_parser("freeze-protocol", help="Freeze a completed local protocol before recording")
    protocol.add_argument("input", type=Path)
    protocol.add_argument("--out", type=Path, required=True)
    paper = commands.add_parser("import-paper1", help="Convert the existing reduced Paper 1 replication data")
    paper.add_argument("--source", type=Path, required=True, help="Path to the original replication directory")
    paper.add_argument("--out", type=Path, required=True, help="New dataset JSON file")
    return root


def run(args):
    if args.command == "validate":
        dataset = validate_dataset(read_json(args.dataset))
        return {"valid": True, "data_kind": dataset["metadata"]["data_kind"]}, 0
    if args.command == "audit":
        report = audit_dataset(read_json(args.dataset), args.evidence_root)
        report["input_sha256"] = file_digest(args.dataset)
        write_report(report, args.out)
        code = 3 if args.fail_on_gaps and any(report["findings"].values()) else 0
        return {"report": str(args.out / "report.html"), "findings": report["findings"]}, code
    if args.command == "init":
        protocol = read_json(args.protocol) if args.protocol else None
        metadata = {"project_id": args.project, "dataset_id": args.dataset_id, "data_kind": args.kind, "captured_at": utc_now()}
        return initialize(args.journal, metadata, args.stages, protocol), 0
    if args.command == "record":
        return append_event(args.journal, args.kind, read_json(args.file), args.event_id), 0
    if args.command == "export":
        dataset, events, protocol = export_journal(args.journal)
        return freeze_snapshot(dataset, args.out, args.evidence_root, events, protocol), 0
    if args.command == "freeze":
        return freeze_snapshot(read_json(args.dataset), args.out, args.evidence_root), 0
    if args.command == "verify":
        return verify_snapshot(args.directory, args.manifest_sha256), 0
    if args.command == "freeze-protocol":
        protocol, digest = freeze_protocol(read_json(args.input))
        write_json(args.out, protocol)
        return {"protocol": str(args.out), "canonical_sha256": digest, "status": protocol["status"]}, 0
    if args.command == "import-paper1":
        dataset = import_paper1(args.source)
        write_json(args.out, dataset)
        return {"dataset": str(args.out), "data_kind": dataset["metadata"]["data_kind"]}, 0
    raise AuditError("Unknown command")


def main(argv=None):
    try:
        result, code = run(parser().parse_args(argv))
        print(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False))
        return code
    except (AuditError, OSError, sqlite3.Error) as error:
        print(f"awa: {error}", file=sys.stderr)
        return 2
