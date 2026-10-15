from concurrent.futures import ThreadPoolExecutor
import contextlib
import copy
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from agent_workflow_audit.cli import main
from agent_workflow_audit.io import AuditError, file_digest, make_manifest, read_json
from agent_workflow_audit.journal import initialize, append_event, export_journal, verify_exported_events
from agent_workflow_audit.protocol import freeze_protocol
from agent_workflow_audit.snapshot import freeze_snapshot, verify_snapshot

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/minimal"


class RecordingTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="awa-test-")
        self.folder = Path(self.temporary.name)
        self.dataset = read_json(EXAMPLE / "dataset.json")
        self.journal = self.folder / "events.sqlite"
        initialize(self.journal, self.dataset["metadata"], self.dataset["stages"])

    def tearDown(self):
        self.temporary.cleanup()

    def test_idempotent_retry_and_conflicting_retry(self):
        row = self.dataset["executions"][0]
        first = append_event(self.journal, "execution", row, "stable-id")
        repeated = append_event(self.journal, "execution", row, "stable-id")
        self.assertEqual(first["sequence"], repeated["sequence"])
        self.assertTrue(repeated["idempotent"])
        with self.assertRaises(AuditError):
            append_event(self.journal, "execution", {**row, "status": "FAILED"}, "stable-id")

    def test_concurrent_writers_preserve_all_events(self):
        def record(index):
            return append_event(self.journal, "execution", {"execution_id": f"run-{index}", "status": "DONE"}, f"event-{index}")
        with ThreadPoolExecutor(max_workers=4) as executor:
            results = list(executor.map(record, range(12)))
        dataset, events, _ = export_journal(self.journal)
        self.assertEqual(len(dataset["executions"]), 12)
        self.assertEqual(len({r["sequence"] for r in results}), 12)
        self.assertEqual(verify_exported_events(dataset, events)["events_verified"], 12)

    def test_updates_preserve_history_but_latest_row_drives_snapshot(self):
        row = self.dataset["executions"][0]
        append_event(self.journal, "execution", {**row, "finished_at": None, "status": "RUNNING"}, "start")
        append_event(self.journal, "execution", row, "finish")
        dataset, events, _ = export_journal(self.journal)
        self.assertEqual(len(dataset["executions"]), 1)
        self.assertEqual(len(events), 2)
        self.assertIsNone(events[0]["record"]["finished_at"])
        self.assertEqual(dataset["executions"][0]["status"], "DONE")

    def test_current_state_projection_preserves_original_event_bytes(self):
        for index, row in enumerate(self.dataset["states"]):
            append_event(self.journal, "state", {**row, "is_current": True}, f"state-{index}")
        dataset, events, _ = export_journal(self.journal)
        self.assertEqual(sum(s["is_current"] for s in dataset["states"]), 1)
        self.assertTrue(events[0]["record"]["is_current"])
        self.assertEqual(verify_exported_events(dataset, events)["events_verified"], 2)

    def test_mutated_journal_is_detected(self):
        append_event(self.journal, "execution", self.dataset["executions"][0], "first")
        with contextlib.closing(sqlite3.connect(self.journal)) as database, database:
            database.execute("UPDATE events SET record_json='{}' WHERE sequence=1")
        with self.assertRaises(AuditError):
            export_journal(self.journal)

    def test_existing_journal_is_never_overwritten(self):
        before = file_digest(self.journal)
        with self.assertRaises(FileExistsError):
            initialize(self.journal, self.dataset["metadata"], self.dataset["stages"])
        self.assertEqual(before, file_digest(self.journal))

    def test_snapshot_preserves_bytes_and_detects_mutation(self):
        target = self.folder / "snapshot"
        receipt = freeze_snapshot(self.dataset, target, EXAMPLE / "evidence")
        verify_snapshot(target, receipt["manifest_sha256"])
        (target / "evidence/build.txt").write_text("modified", encoding="utf-8")
        with self.assertRaises(AuditError):
            verify_snapshot(target)

    def test_snapshot_refuses_extra_unmanifested_files(self):
        target = self.folder / "snapshot"
        freeze_snapshot(self.dataset, target)
        (target / "extra.txt").write_text("extra", encoding="utf-8")
        with self.assertRaises(AuditError):
            verify_snapshot(target)

    def test_external_manifest_hash_detects_rewritten_manifest(self):
        target = self.folder / "snapshot"
        receipt = freeze_snapshot(self.dataset, target)
        report = read_json(target / "report.json")
        report["altered"] = True
        (target / "report.json").write_text(json.dumps(report), encoding="utf-8")
        (target / "manifest.json").write_text(json.dumps(make_manifest(target)), encoding="utf-8")
        with self.assertRaises(AuditError):
            verify_snapshot(target, receipt["manifest_sha256"])

    def test_invalid_protocol_shape_and_manifest_fail_clearly(self):
        with self.assertRaises(AuditError):
            initialize(self.folder / "bad.sqlite", self.dataset["metadata"], self.dataset["stages"], [])
        target = self.folder / "bad-packet"
        target.mkdir()
        (target / "manifest.json").write_text("[]", encoding="utf-8")
        with self.assertRaises(AuditError):
            verify_snapshot(target)

    def test_frozen_journal_contains_a_verified_event_history(self):
        append_event(self.journal, "task", self.dataset["tasks"][0], "enroll")
        dataset, events, protocol = export_journal(self.journal)
        receipt = freeze_snapshot(dataset, self.folder / "snapshot", events=events, protocol=protocol)
        self.assertEqual(receipt["events_verified"], 1)

    def test_draft_slowlife_protocol_cannot_start_prospective_collection(self):
        draft = read_json(ROOT / "profiles/slowlife.protocol.draft.json")
        with self.assertRaises(AuditError):
            freeze_protocol(draft)
        with self.assertRaises(AuditError):
            initialize(self.folder / "study.sqlite", {**self.dataset["metadata"], "data_kind": "prospective"}, self.dataset["stages"], draft)

    def test_completed_protocol_freezes_and_matches_project(self):
        protocol = read_json(ROOT / "profiles/slowlife.protocol.draft.json")
        protocol.update(project_id="demo", stages=self.dataset["stages"], enrollment_rule="All three prespecified fixture tasks", stopping_rule="After all three tasks or the fixed 30-minute fixture budget")
        frozen, digest = freeze_protocol(protocol)
        self.assertEqual(len(digest), 64)
        initialize(self.folder / "study.sqlite", {**self.dataset["metadata"], "data_kind": "prospective"}, self.dataset["stages"], frozen)
        exported, _, saved = export_journal(self.folder / "study.sqlite")
        self.assertEqual(exported["metadata"]["protocol_sha256"], digest)
        self.assertEqual(saved, frozen)

    def test_comparison_protocol_requires_comparator_details(self):
        protocol = read_json(ROOT / "profiles/slowlife.protocol.draft.json")
        protocol.update(stages=["check"], enrollment_rule="All fixture tasks", stopping_rule="One fixture batch", design="controlled_comparison")
        with self.assertRaises(AuditError):
            freeze_protocol(protocol)

    def test_cli_reports_input_errors_and_gap_exit_status(self):
        error_stream = io.StringIO()
        with contextlib.redirect_stderr(error_stream):
            status = main(["validate", str(self.folder / "missing.json")])
        self.assertEqual(status, 2)
        self.assertIn("awa:", error_stream.getvalue())
        with contextlib.redirect_stdout(io.StringIO()):
            status = main(["audit", str(EXAMPLE / "dataset.json"), "--out", str(self.folder / "report"), "--fail-on-gaps"])
        self.assertEqual(status, 3)


if __name__ == "__main__":
    unittest.main()
