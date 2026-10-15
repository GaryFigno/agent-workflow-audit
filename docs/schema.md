# Dataset schema 1.0

The runtime validator is authoritative. `schema/dataset.schema.json` describes
the interoperable structure; timestamp ordering and hash consistency are also
checked at runtime. Unknown extra properties are retained and ignored by the core
auditor, so do not put secrets or private prompts in data intended for publication.

All snapshots contain `schema_version: "1.0"`, `metadata`, a nonempty unique `stages`
array, and these arrays (empty arrays are valid):

| Array | Required fields | Selected optional fields |
| --- | --- | --- |
| tasks | task_id, enrolled_at | initial_version_id, requirements_sha256, task_type, condition, assigned_workflow, budget_seconds, budget_tokens, budget_usd, closed_at, outcome |
| executions | execution_id, status | task_id, version_id, stage, resource_id, execution_kind, engine, model, model_version, client_version, workflow_version, condition, created_at, accepted_at, started_at, finished_at, input_tokens, output_tokens, cost_usd, human_seconds |
| states | state_id, task_id, attempt, revision, is_current, origin | version_id, gate, status, condition |
| attestations | attestation_id, state_id, stage | execution_id, evidence_id, version_id |
| evidence | evidence_id | version_id, path, expected_sha256, observation |
| decisions | decision_id, task_id, decision | version_id, scope, reviewer_id, reviewer_kind, independent_reviewer, rubric_version, decided_at |
| transitions | transition_id, task_id, category | from_state_id, to_state_id, occurred_at |

`metadata` requires dataset_id, project_id, data_kind (synthetic / observational /
prospective), and captured_at. Protocol hash, environment versions, hardware
description, and inclusion notes can be included as explicit metadata.

Execution times are Unix seconds in UTC. ISO 8601 fields (enrollment, decisions,
observations, capture, transitions) require an explicit timezone. Null is unknown,
not zero. Zero is allowed only for a genuinely measured zero. A finish before a
start, negative cost, duplicate ID, NaN, or duplicate JSON key is rejected.

`version_id` should identify immutable artifact bytes or a manifest, not a mutable
branch name. A state can have multiple technical attestations. A run reused across
states retains one execution_id, so the combined resource account deduplicates it.
Multiple stages may reference a shared run; stage subtotals then are not additive.
Each task has at most one current state in a standalone snapshot. Separate revision
records can share an attempt number. Numbered attempt gaps stay unobserved.

Only configured technical stages enter evidence coverage and linked-stage accounting.
Other execution rows (e.g. model calls, review time) remain in the whole execution
population and per-resource summaries. Label resource_id and execution_kind to
avoid combining different kinds of occupancy without explanation.

An evidence path is relative to the explicit evidence root, uses forward slashes,
and cannot contain `..`, drive letters, or backslashes. Symlink escapes are refused.
An observation has status match / mismatch / missing / unreadable / unknown, basis
retained_observation / live_verification / synthetic, optional observed_at, and
actual_sha256. A match requires equal expected and actual hashes; a mismatch requires
different hashes. A readable file without an expected hash remains unknown.

A decision's reviewer_kind is human / agent / unknown. Role separation is not proof
of independence; record independent_reviewer truthfully. Binding only requires exact
task and version IDs; it does not validate the decision or its rubric. Missing scope
and missing version are visible findings. A historical-version decision may be valid
for that historical version and must not be relabeled as a current acceptance.

Broken foreign keys are retained as audit findings. Unmatched execution IDs do not
acquire zero duration. Missing evidence references are unknown, distinct from an
observed missing file. Rework categories are producer-defined, not model-error labels.

## Journal semantics

`awa record` accepts a full row of one table. A later event with the same record ID
replaces that row in the derived snapshot, preserving both events in history.
A new version should normally receive a new state_id. Retrying with the same event_id
and identical content is idempotent; reusing it with different content is rejected.
The collector stamps recorded_at itself. Row event times may differ: recorded_at is
collection time, not proof of when an external action happened.

When several states declare is_current=true for one task, journal export selects
the latest such state event and records projection_demoted_states in metadata.
The underlying event JSON is not rewritten. Direct dataset imports must resolve
multiple current states themselves. Version updates do not fabricate transition causes.

The SQLite API uses transactions for concurrent writers. It does not add database
triggers or signatures preventing the owner from changing the database externally.
Archive the exported event chain and externally retain the snapshot manifest hash.
