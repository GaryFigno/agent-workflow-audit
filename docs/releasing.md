# GitHub release preparation

Repository: [https://github.com/GaryFigno/agent-workflow-audit](https://github.com/GaryFigno/agent-workflow-audit). GitHub releases distribute the reviewed source and wheel; no package-index upload or DOI is implied.

## Contents and attribution

MIT applies to the code, documentation and synthetic examples. The software author is Wang Jiayi. The separate manuscript retains its own copyright and is not covered by the software MIT license. Do not describe a GitHub manuscript copy as peer-reviewed journal publication or invent a DOI.

The existing private replication data remain in a separate local package. The source
repository includes the original calculation source and pinned input hashes, but no
production evidence bytes, game assets, original conversations, or local credentials.
New study-data/ and local-data/ directories are ignored by Git. Sharing a frozen
study dataset is a separate release with explicit data terms and a new manifest.

## Local acceptance checks

The observed v0.1.0 checks and their limits are recorded in [validation.md](validation.md).

```console
python -m pip install .
python -m unittest discover -s tests -v
python tools/check_release.py
python tools/verify_paper1.py --source <private-replication-directory> --out reports/paper1-release-check
python -m pip wheel . --no-deps --wheel-dir dist
```

Use a new report directory for each run. The last study check requires the separately
supplied frozen data. It is intentionally not part of a public CI job.

## Publishing later

Use the existing repository and the maintainer's real Git identity for subsequent changes. Create a release for the version reviewed
against the paper, and attach the wheel/source archive and their SHA-256 values.
Do not move a paper's release tag to a different commit after publication.

The included GitHub workflow runs unit tests and the synthetic demo on Windows and Ubuntu with Python 3.11 and 3.12. Consult the repository's Actions page for the actual remote result; local validation does not imply a remote pass.

`CITATION.cff` supplies software citation metadata. For archival citation, configure
Zenodo for the actual public repository and archive the selected release. Add a DOI
only after it exists. The ordinary GitHub branch remains the evolving development
version, while the paper cites the archived version.

References: [GitHub citation files](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/about-citation-files),
[GitHub/Zenodo archival](https://docs.github.com/en/repositories/archiving-a-github-repository/referencing-and-citing-content),
[repository licensing](https://docs.github.com/en/repositories/managing-your-repositorys-settings-and-features/customizing-your-repository/licensing-a-repository).
