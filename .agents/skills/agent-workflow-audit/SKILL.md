---
name: agent-workflow-audit
description: Use the Agent Workflow Audit package to record engineering task events, freeze evidence snapshots, audit version and execution links, or prepare Slowlife prospective study data. Use for research recording and audit, not for launching engines or producing synthetic experimental outcomes.
---

# Agent Workflow Audit

Locate the repository containing this skill and read its `README.md`. The installed
CLI is `awa`, with equivalent `python -m agent_workflow_audit` commands.

- For imported records, read `docs/schema.md`; validate before auditing.
- For Slowlife collection, read `docs/slowlife.md`. The bundled protocol is a draft.
  Fill actual study decisions before `awa freeze-protocol`; a local freeze is not
  external preregistration. Preserve amendments as new versions.
- Record actual task enrollment before work, then real lifecycle events with
  `append_event` or `awa record`. Stable event IDs support idempotent retries.
- Export to a new snapshot directory and retain the returned manifest hash outside
  it. `awa verify --manifest-sha256` checks against that external anchor.
- Use `--evidence-root` for an explicit live file check; without it, the auditor
  only evaluates retained observations. Do not describe the latter as a replay.
- Keep synthetic examples, Paper 1 observations and new Slowlife records separate.
  Report missing values and non-additive resource subtotals with their definitions.

Core validation: `python -m unittest discover -s tests -v` and
`python tools/check_release.py`. The optional real-data cross-check is
`python tools/verify_paper1.py --source <replication-directory> --out <new-directory>`.
Do not modify the pinned case analysis to make a changed result appear identical.

An existing output path is intentionally refused: choose a new run/cut directory.
Schema errors return exit 2; `audit --fail-on-gaps` returns 3 for observed gaps.
A journal or manifest mismatch requires investigation and recovery from preserved
sources, not silently rewriting the anchor. These hashes do not authenticate the
operator or certify product quality.
