"""Portable JSON and escaped standalone HTML reports."""

import html
from pathlib import Path

from .io import write_json


def _display(value):
    if value is None:
        return "Unknown / not measured"
    if isinstance(value, float):
        return f"{value:,.4f}"
    return str(value)


def _table(headers, rows):
    head = "".join(f"<th>{html.escape(str(h))}</th>" for h in headers)
    body = "".join("<tr>" + "".join(f"<td>{html.escape(_display(v))}</td>" for v in row) + "</tr>" for row in rows)
    return f"<table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>"


def render_html(report):
    meta = report["metadata"]
    coverage_rows = [(name, cell["attestations"], cell["joint"]["match"]["joined"],
                      cell["joint_coverage"] * 100 if cell["joint_coverage"] is not None else None)
                     for name, cell in report["coverage"].items()]
    resources = report["resources"]
    names = ("linked_technical", "current_only", "historical_only", "shared_current_historical", "unresolved_state_only")
    resource_rows = [(name, resources[name]["requests"], resources[name]["unmatched"],
                      resources[name]["lease"]["sum_h"], resources[name]["unknown_lease_n"],
                      resources[name]["waiting"]["p90_s"]) for name in names]
    evidence_rows = [(row["attestation_id"], row["cohort"], row["stage"], row["file_status"],
                      row["execution_joined"], row["execution_version"])
                     for row in report["evidence_audit"]]
    decisions = [(row["decision_id"], row["decision"], row["binding"], row["scope_recorded"], row["reviewer_kind"])
                 for row in report["decisions"]]
    limits = "".join(f"<li>{html.escape(value)}</li>" for value in report["limits"])
    return """<!doctype html><html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Agent Workflow Audit</title><style>
body{font:16px/1.5 system-ui,sans-serif;color:#17324a;background:#f4f7fa;margin:0}
main{max-width:1200px;margin:auto;padding:32px}h1{font-size:30px}h2{margin-top:34px}
table{border-collapse:collapse;width:100%;background:white;font-size:14px;margin:12px 0}
th,td{padding:10px 12px;border-bottom:1px solid #d6e0e8;text-align:left;overflow-wrap:anywhere}
th{background:#e6eef5}aside{padding:16px;background:#fff1cc;border-left:4px solid #bb8020}
.scroll{overflow:auto}code{overflow-wrap:anywhere}details{margin-top:24px}
</style><main>""" + f"""
<h1>Agent Workflow Audit</h1>
<p><b>{html.escape(meta['project_id'])}</b> · Dataset {html.escape(meta['dataset_id'])}
 · Tool {html.escape(report['tool_version'])}</p>
<aside>Data kind: <strong>{html.escape(meta['data_kind'])}</strong>.
 Verification mode: <strong>{html.escape(report['verification_mode'])}</strong>.
 This report describes records; it does not certify product quality or productivity.</aside>
<p>Snapshot time: {html.escape(meta['captured_at'])}. Zero records mean no observations supplied.</p>
<h2>Evidence coverage</h2>
{_table(('Cohort','Technical references','File matches + execution joins','Joint coverage (%)'), coverage_rows)}
<h2>Resource accounting</h2>
<p>The exclusive current / historical / shared / unresolved rows partition the referenced executions.
 Missing execution IDs and missing durations remain separate. Hours are lease occupancy.</p>
{_table(('Group','Joined requests','Unmatched IDs','Known lease hours','Unknown lease durations','Wait P90 (s)'), resource_rows)}
<h2>Recorded gaps</h2>{_table(('Finding','Count'), report['findings'].items())}
<h2>Interpretation</h2><ul>{limits}</ul>
<details><summary>All technical evidence references ({len(evidence_rows)})</summary><div class="scroll">
{_table(('Attestation','Cohort','Stage','File check','Execution joined','Execution version'), evidence_rows)}</div></details>
<details><summary>Decision bindings ({len(decisions)})</summary><div class="scroll">
{_table(('Decision ID','Recorded decision','Version binding','Scope recorded','Reviewer kind'), decisions)}</div></details>
</main></html>"""


def write_report(report, directory):
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=False)
    write_json(directory / "report.json", report)
    (directory / "report.html").write_text(render_html(report), encoding="utf-8")
