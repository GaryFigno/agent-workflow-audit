# Agent Workflow Audit

[中文说明](README.zh-CN.md)

Offline evidence and resource auditing for agent-assisted engineering workflows.
Version 0.1.0 is a research tool, validated locally on Windows with Python 3.12;
cross-platform CI is configured for Windows/Ubuntu and Python 3.11/3.12.

The tool joins task versions, technical attestations, evidence observations,
execution records, and acceptance decisions. It separates missing records from
measured zeros and counts each execution once in the combined resource account.
Stages and transition categories belong to the input workflow, not a game engine.

## Quick start

Python 3.11 or newer. No runtime dependencies, API keys, game engine, or network calls.
Run these commands from the extracted repository root:

```console
python -m pip install .
awa validate examples/minimal/dataset.json
awa audit examples/minimal/dataset.json --evidence-root examples/minimal/evidence --out reports/demo
```

Open `reports/demo/report.html`. The supplied example is explicitly **synthetic**:
it intentionally contains missing evidence, a hash mismatch, a missing execution,
and an unbound decision. Findings are expected. It is not Slowlife experiment data.
Installing from source may fetch setuptools; an included release wheel can instead
be installed offline with `python -m pip install --no-index <wheel-path>`.

## Preserve a run

```console
awa freeze examples/minimal/dataset.json --evidence-root examples/minimal/evidence --out snapshots/demo
awa verify snapshots/demo
```

Keep the returned manifest SHA-256 outside the snapshot. Supply it with
`awa verify snapshots/demo --manifest-sha256 <saved-hash>` when checking later.
Each output directory must be new. The tool does not overwrite prior snapshots.

## Record future work

The journal stores every submitted record event in SQLite, including updates to
the same execution. Stable event IDs make retrying an identical submission safe.
Export materializes the latest record per ID while preserving all events.

```console
awa init --journal local-data/demo.sqlite --project demo --dataset-id demo-journal --kind synthetic --stages build check capture
awa record --journal local-data/demo.sqlite --kind task --file examples/minimal/records/task.json --event-id demo-enrollment-1
awa record --journal local-data/demo.sqlite --kind state --file examples/minimal/records/state.json --event-id demo-state-1
awa record --journal local-data/demo.sqlite --kind execution --file examples/minimal/records/execution.json --event-id demo-execution-1
awa export --journal local-data/demo.sqlite --out snapshots/demo-journal
```

Partial snapshots report missingness. Collection must include failures, cancellations,
and abandoned attempts according to the study's enrollment rule. File checks use a
saved observation by default; `--evidence-root` requests a new file verification.

## Repository contents

| Location | Purpose |
| --- | --- |
| `src/agent_workflow_audit/` | Generic validator, auditor, journal, snapshot tools, and Paper 1 adapter |
| `examples/minimal/` | Synthetic cross-platform example with expected findings |
| `profiles/slowlife.protocol.draft.json` | Unfrozen plan for a future Slowlife study; contains no observations |
| `docs/slowlife.md` | Recording and experiment handoff for the next project |
| `docs/schema.md`, `schema/` | Input contract and machine-readable shape |
| `studies/paper1/` | Frozen analysis source and source hashes; private data are supplied separately |
| `.agents/skills/agent-workflow-audit/` | Portable agent guidance for reuse |

## Paper 1

Wang Jiayi (Independent Researcher, China), *Evidence Retention and Resource Accounting in Multiagent Game Development: A Retrospective Study of a Shared Engine Workflow*. [Manuscript reading copy](https://github.com/GaryFigno/agent-workflow-audit/releases/download/v0.1.0/paper1-jss-manuscript.pdf). Prepared for Journal of Systems and Software; not peer reviewed or accepted by the journal.

The manuscript retains its own copyright; the software's MIT license does not apply to the manuscript or private study data.

The original paper concerns a retrospective Cinderage case. Its historical records
are not mixed with prospective Slowlife observations. With the separately supplied
original replication directory available locally:

```console
python tools/verify_paper1.py --source <replication-directory> --out reports/paper1
```

This checks pinned bytes, recomputes the three original numerical results, and tests
the generic auditor against the original evidence matrix and resource totals.
The adapter reads reduced records only; it neither opens the production project nor
re-runs its original evidence checks. See [the study note](studies/paper1/README.md).

## Meaning of a result

- File integrity, execution linkage, version agreement, and acceptance scope are separate checks.
- A matching file does not prove a correct execution. A successful execution does not prove product acceptance.
- The configured technical chain reports presence of stages, not independent correctness.
- A lease is recorded resource occupancy. Summed waiting can overlap and is not lost labor.
- The combined account deduplicates executions. Current/historical and stage subtotals may overlap; exclusive groups are supplied.
- Token, USD, and human-time fields report only supplied measurements, alongside unknown counts.
- Journal hash chains and manifests are integrity aids, not authenticated third-party evidence.
- The tool does not launch engines, schedule agents, publish data, or run an experiment automatically.

## Development and distribution

```console
python -m unittest discover -s tests -v
python tools/check_release.py
python -m pip wheel . --no-deps --wheel-dir dist
```

Code, documentation, and synthetic examples are MIT licensed. Private production
data and third-party assets are not included in this repository or covered by this
software license. See [release instructions](docs/releasing.md) for GitHub and citation setup.
