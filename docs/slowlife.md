# Slowlife handoff: prospective records, then analysis

Status: **planned; no Slowlife production run or experimental observation has been
collected by this release**. The engine, actual stage names, allocation and task list
are intentionally not guessed. The demo project is unrelated synthetic test data.

## Before the first included task

Complete `profiles/slowlife.protocol.draft.json` with the actual stages, task
enrollment rule, primary outcomes, and stopping rule. Choose task-level inclusion
before examining outcomes; include failures, canceled requests, retries and unfinished
tasks. Freeze the starting artifact manifest and record model/client/tool/engine
versions, hardware/resource policy, and any treatment condition.

The initial plan is prospective observational: evaluate whether recording and audit
work across another project. It does not establish productivity improvement.
For a controlled comparison, additionally fix conditions, allocation, comparable
budgets and independent outcome assessment. Queue interference, project difficulty,
operator and hardware must be considered. Do not treat 10,000 correlated tool calls
as 10,000 independent development tasks.

The shared host/operator means a Slowlife replication is a cross-project transfer,
not automatically independent organizational replication. Preserve that distinction.

## Freeze the local protocol

After replacing null planning fields with the actual decisions:

```console
awa freeze-protocol profiles/slowlife.protocol.draft.json --out local-data/slowlife-protocol-v1.json
```

This records a local freeze timestamp and hash; it does not register a study with a
third-party preregistration service. For changes after collection starts, create a
new protocol version and journal/dataset ID, preserve the earlier files, and record
the amendment reason. Do not edit a frozen protocol to make it appear prospective.

Initialize a fresh journal with the **same actual stage names** as the frozen protocol:

```console
awa init --journal local-data/slowlife-v1.sqlite --project Slowlife --dataset-id slowlife-v1 --kind prospective --stages <actual-stage-names> --protocol local-data/slowlife-protocol-v1.json
```

The angle-bracket argument is an instruction to supply real stage names, not a
literal command. The unfrozen draft deliberately fails freeze-protocol until filled.

## Instrument the producer

Call the stable Python API at real workflow boundaries or invoke `awa record` with
one record file. Do not execute production commands from this audit library.

```python
from agent_workflow_audit.journal import append_event

# real_record is the producer's observed task/execution/state/etc. row.
# Persist a stable event_id with the producer action and reuse it on retry.
receipt = append_event(journal_path, "execution", real_record, event_id=stable_event_id)
```

Record these boundaries:

1. **Enrollment:** task_id, initial version, requirements hash, condition and budget.
2. **Request lifecycle:** accepted/start/finish timestamps, result, resource and versions;
   append updated rows with the same execution_id. Preserve cancellation before start.
3. **Artifact revision:** new state_id/version_id; preserve the old state and the reason
   for transition (technical failure, visual revision, release change, or another defined cause).
4. **Evidence:** immutable relative file reference and expected hash; record when and how
   it was verified. Files should be retained with the run, not overwritten by later reports.
5. **Decision:** exact task and version, scope, rubric, decision, reviewer type and actual
   independence. Automated self-review is not an independent human outcome.
6. **Costs:** collect reported model tokens/charges and measured human time separately;
   leave missing quantities null. Avoid counting the same charge on multiple execution rows.

The audit layer does not bypass the project's engine/resource broker. Scheduling and
game execution remain with the existing project tools and their instructions.

## Freeze and verify each analysis cut

```console
awa export --journal local-data/slowlife-v1.sqlite --evidence-root <run-evidence-directory> --out snapshots/slowlife-cut-001
awa verify snapshots/slowlife-cut-001 --manifest-sha256 <externally-saved-manifest-hash>
```

Retain the exported events, dataset, evidence bytes, protocol, and manifest. New cuts
use new directories. Audit only explicit input snapshots; do not combine synthetic
examples, the retrospective Cinderage case, and Slowlife observations into one sample.

## Initial analysis targets

- Both-file-and-execution coverage, with separate missing/unknown/mismatch categories.
- Presence of acceptance scope and exact artifact-version binding.
- Current-exclusive, historical-exclusive and shared resource occupancy; unmatched IDs.
- Coverage of model-cost and human-time measurements, not just their known sums.
- Transition counts by reason and task, retaining unobserved attempt positions.
- Task closure and incomplete enrollment, as specified before analysis.

These are measurement outcomes. Actual product quality needs its own task-appropriate
assessment, and causal efficiency claims need a suitable comparison design.
