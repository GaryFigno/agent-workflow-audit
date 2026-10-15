import copy
from pathlib import Path
import tempfile
import unittest

from agent_workflow_audit.audit import audit_dataset, distribution
from agent_workflow_audit.io import AuditError, read_json, parse_json
from agent_workflow_audit.schema import validate_dataset

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "examples/minimal"


class AuditTests(unittest.TestCase):
    def setUp(self):
        self.data = read_json(EXAMPLE / "dataset.json")

    def test_repeated_execution_is_counted_once_and_overlap_is_explicit(self):
        report = audit_dataset(self.data)
        resources = report["resources"]
        self.assertEqual(resources["linked_technical"]["lease"]["sum_s"], 30)
        self.assertEqual(resources["linked_technical"]["unmatched"], 1)
        self.assertEqual(resources["shared_current_historical"]["requests"], 1)
        self.assertEqual(resources["current_only"]["lease"]["sum_s"], None)
        self.assertEqual(resources["current_only"]["unknown_lease_n"], 1)

    def test_live_file_checks_distinguish_match_missing_and_drift(self):
        report = audit_dataset(self.data, EXAMPLE / "evidence")
        joint = report["coverage"]["all"]["joint"]
        self.assertEqual(joint["match"]["joined"], 2)
        self.assertEqual(joint["missing"]["unmatched"], 1)
        self.assertEqual(joint["mismatch"]["joined"], 1)
        self.assertEqual(report["verification_mode"], "live_files")

    def test_unknown_duration_and_measured_zero_remain_distinct(self):
        self.data["executions"][0]["finished_at"] = self.data["executions"][0]["started_at"]
        report = audit_dataset(self.data)
        summary = report["resources"]["linked_technical"]
        self.assertEqual(summary["lease"]["sum_s"], 0)
        self.assertEqual(summary["lease"]["n"], 1)
        self.assertEqual(summary["unknown_lease_n"], 1)
        self.assertIsNone(summary["reported_accounting"]["cost_usd"]["known_sum"])

    def test_costs_deduplicate_and_report_unknown_coverage(self):
        self.data["executions"][0]["cost_usd"] = 0
        self.data["executions"][0]["input_tokens"] = 12
        summary = audit_dataset(self.data)["resources"]["linked_technical"]["reported_accounting"]
        self.assertEqual(summary["input_tokens"]["known_sum"], 12)
        self.assertEqual(summary["cost_usd"], {"known_n": 1, "unknown_n": 1, "known_sum": 0})

    def test_historical_acceptance_is_not_current_acceptance(self):
        rows = audit_dataset(self.data)["decisions"]
        self.assertEqual(rows[0]["binding"], "historical_version")
        self.assertEqual(rows[1]["binding"], "unresolved")
        self.assertFalse(rows[1]["scope_recorded"])

    def test_version_mismatch_is_observed_not_silently_joined(self):
        report = audit_dataset(self.data)
        self.assertEqual(report["findings"]["version_mismatches"], 1)

    def test_missing_evidence_reference_is_unknown_not_missing_file(self):
        self.data["attestations"][0]["evidence_id"] = "not-recorded"
        report = audit_dataset(self.data)
        self.assertEqual(report["evidence_audit"][0]["file_status"], "unknown")

    def test_orphan_state_is_retained(self):
        self.data["attestations"][0]["state_id"] = "unavailable"
        report = audit_dataset(self.data)
        self.assertEqual(report["coverage"]["unresolved_state"]["attestations"], 1)

    def test_duplicate_execution_identifiers_are_rejected(self):
        self.data["executions"].append(copy.deepcopy(self.data["executions"][0]))
        with self.assertRaises(AuditError):
            validate_dataset(self.data)

    def test_bad_times_and_nonfinite_values_are_rejected(self):
        for key, value in [("finished_at", 1), ("cost_usd", -1), ("input_tokens", 1.5), ("started_at", float("nan"))]:
            with self.subTest(key=key):
                dataset = copy.deepcopy(self.data)
                dataset["executions"][0][key] = value
                with self.assertRaises(AuditError):
                    validate_dataset(dataset)

    def test_duplicate_json_keys_and_nan_are_rejected(self):
        for text in ['{"a":1,"a":2}', '{"a":NaN}']:
            with self.assertRaises(AuditError):
                parse_json(text)

    def test_multiple_current_states_are_rejected_on_direct_import(self):
        self.data["states"][0]["is_current"] = True
        with self.assertRaises(AuditError):
            validate_dataset(self.data)

    def test_paths_cannot_escape_the_explicit_root(self):
        for name in ("../secret", "C:/secret", "/secret", "folder\\secret", "./secret"):
            with self.subTest(name=name):
                dataset = copy.deepcopy(self.data)
                dataset["evidence"][0]["path"] = name
                with self.assertRaises(AuditError):
                    audit_dataset(dataset, EXAMPLE / "evidence")

    def test_symlink_escape_is_rejected_when_host_supports_symlinks(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            root = folder / "root"
            root.mkdir()
            outside = folder / "outside.txt"
            outside.write_text("outside", encoding="utf-8")
            try:
                (root / "link.txt").symlink_to(outside)
            except OSError:
                self.skipTest("Host does not permit unprivileged symlink creation")
            self.data["evidence"][0]["path"] = "link.txt"
            with self.assertRaises(AuditError):
                audit_dataset(self.data, root)

    def test_readable_file_without_expected_hash_is_unverified(self):
        self.data["evidence"][0]["expected_sha256"] = None
        self.data["evidence"][0]["observation"] = None
        result = audit_dataset(self.data, EXAMPLE / "evidence")
        self.assertEqual(result["evidence_observations"]["file-1"]["status"], "unknown")

    def test_false_matching_observation_is_rejected(self):
        self.data["evidence"][0]["observation"]["actual_sha256"] = "f" * 64
        with self.assertRaises(AuditError):
            validate_dataset(self.data)

    def test_arbitrary_stage_names_and_numbered_gaps(self):
        self.data["stages"] = ["custom-check"]
        self.data["attestations"][0]["stage"] = "custom-check"
        self.data["states"][1]["attempt"] = 4
        result = audit_dataset(self.data)
        self.assertEqual(result["coverage"]["all"]["attestations"], 1)
        self.assertEqual(result["histories"][0]["missing_numbered_positions"], [2, 3])

    def test_p90_and_empty_distribution_use_documented_definitions(self):
        self.assertEqual(distribution([10, 20, 30, 40])["p90_s"], 30)
        self.assertIsNone(distribution([])["sum_s"])

    def test_stage_subtotals_flag_shared_runs(self):
        self.data["attestations"][1]["execution_id"] = "run-1"
        result = audit_dataset(self.data)
        self.assertTrue(result["resources"]["stage_subtotals_may_overlap"])
        self.assertEqual(result["resources"]["linked_technical"]["lease"]["sum_s"], 30)


if __name__ == "__main__":
    unittest.main()
