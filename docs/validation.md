# Local validation of v0.1.0

Validated on Windows with Python 3.12.14 on 2026-10-15. The source archive was
extracted into a new directory, built into a wheel, and installed offline in a new
virtual environment. The tests imported the installed wheel, not the working source.

| Check | Observed result |
| --- | --- |
| Unit suite | 34 run: 33 passed, 0 failures, 0 errors, 1 skipped |
| Platform skip | This Windows host did not permit unprivileged symbolic-link creation |
| CLI entry point and version | Passed |
| Synthetic audit, evidence snapshot and external manifest-hash verification | Passed |
| Journal creation, recording, idempotent retry, export and event-chain verification | Passed |
| Unfinished Slowlife study protocol | Rejected, as intended |
| Paper 1 pinned input/source files | 20 hashes matched |
| Paper 1 frozen numerical outputs | All three reproduced exactly |
| Generic historical evidence matrix | `[[1120, 638], [114, 4]]`, agrees with the frozen calculation |
| Generic linked technical lease hours | 56.27231424212456 |
| Generic historical lease hours | 35.34355492658085 |
| Synthetic JSON Schema and CFF 1.2 citation metadata | Validated |
| Portable agent skill | Validated |

The real-data cross-check read the separately supplied reduced replication data.
It did not run the game or recheck production evidence files. Those data are not
included in the source repository. Aggregate verification results are not new study
observations.

The source scan checks for obvious credentials, private local paths and excluded
artifact types; it is a bounded packaging check. The GitHub workflow is configured
for Ubuntu/Windows and Python 3.11/3.12, but remote jobs have not run. Large-scale
production throughput and actual Slowlife integration remain unmeasured. This release
contains no Slowlife observations.

To repeat the public checks, follow [the release instructions](releasing.md).
