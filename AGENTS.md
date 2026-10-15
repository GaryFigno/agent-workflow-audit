# Working on Agent Workflow Audit

This repository is an offline research tool. Read README.md and docs/schema.md
before changing the data contract. Use `python -m unittest discover -s tests -v`
and `python tools/check_release.py` for changes to core behavior.

Preserve the frozen analysis files in studies/paper1 and their pinned hashes.
New behavior belongs in the generic package or a versioned adapter. Rechecking
the original case requires its separate local replication data.

Keep synthetic fixtures, retrospective observations, and prospective study data
distinct. Unknown timestamps, costs and absent evidence must not become zeros.
Deduplicate execution IDs in combined accounts and expose shared references.

The distributed Slowlife profile is an unfrozen plan. Do not invent its engine,
task population, conditions, authors, experimental outcomes or public DOI.
Actual project execution uses the project's existing tools and instructions;
this package observes records and does not replace the engine/resource broker.

The reusable workflow is documented in .agents/skills/agent-workflow-audit/SKILL.md.
