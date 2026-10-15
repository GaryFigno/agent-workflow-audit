# Synthetic example

All records and evidence bytes here are invented fixtures for testing the tool.
They are not production observations and are not experiment data.

The expected combined technical account contains two matched execution IDs and
one unmatched ID. `run-1` is referenced three times but contributes only 30 lease
seconds. It is shared across current and historical states. `run-2` was canceled
before starting and has unknown lease duration, not a measured zero.

The example includes matching, missing and mismatching files; a historical-version
decision; an unresolved decision; and missing configured technical stages.
