# Frozen Paper 1 analysis

These two analysis programs are byte-identical to the JSS-format manuscript's local
replication package prepared on 15 October 2026. Their Cinderage-specific fields and
assertions intentionally remain frozen. They are separate from the generic package.
`reference_hashes.json` pins the complete original replication inputs and programs.

The original data are not included in this Git source package. Supply the existing
private replication directory to `tools/verify_paper1.py`. It validates all pinned
hashes, runs these frozen programs with explicit input/output paths, compares all
three expected JSON results, and checks the normalized generic audit independently.
It does not execute the private production extractor.

The generic adapter keeps observations as retained observations, does not fabricate
original evidence paths, and does not infer a catalog decision's version from a POI
or capture-path text. Consequently, generic decision binding is deliberately stricter
than the manuscript's separate, explicitly weaker catalog path-association analysis.
No new empirical measurements are implied by the conversion.

The code license does not grant a license to the separately held production data.
The original manuscript and its frozen numerical results remain unchanged.
