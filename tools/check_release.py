"""Check the source release for accidental study data and obvious local secrets.

This bounded check is not a complete sensitive-data classifier. Review actual
new data before any future data release; this repository contains synthetic data.
"""

import hashlib
import json
from pathlib import Path
import re

from agent_workflow_audit.io import read_json
from agent_workflow_audit.schema import validate_dataset

ROOT = Path(__file__).resolve().parents[1]
IGNORED = {".git", "__pycache__", ".venv", "build", "dist", "reports", "snapshots", "local-data", "study-data", "runs", "release_artifacts"}
PATTERNS = {
    "Windows user profile": re.compile(r"[A-Za-z]:[/\\]+Users[/\\]+[A-Za-z0-9_]", re.I),
    "Private production path": re.compile(r"[A-Za-z]:[/\\]+Cinderage", re.I),
    "Private key": re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY-----"),
    "GitHub credential": re.compile(r"(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})"),
    "API credential": re.compile(r"\bsk-[A-Za-z0-9_-]{24,}\b"),
}


def release_files():
    for path in sorted(ROOT.rglob("*")):
        relative = path.relative_to(ROOT)
        if any(part in IGNORED or part.endswith(".egg-info") for part in relative.parts):
            continue
        if path.is_file():
            yield path


def main():
    failures = []
    files = list(release_files())
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        if path.suffix.lower() in (".sqlite", ".db", ".uasset", ".umap", ".glb", ".blend") or path.name == ".env":
            failures.append(f"Production/local artifact in release: {name}")
        if path.suffix.lower() in (".py", ".md", ".json", ".yml", ".toml", ".cff", ".txt") or path.name in ("LICENSE", ".gitignore", ".gitattributes"):
            content = path.read_text(encoding="utf-8")
            for label, pattern in PATTERNS.items():
                if pattern.search(content):
                    failures.append(f"{label}: {name}")
    dataset = validate_dataset(read_json(ROOT / "examples/minimal/dataset.json"))
    if dataset["metadata"]["data_kind"] != "synthetic":
        failures.append("Public demo must be labeled synthetic")
    profile = read_json(ROOT / "profiles/slowlife.protocol.draft.json")
    if profile["status"] != "draft":
        failures.append("The distributed Slowlife profile must remain an unfrozen plan")
    hashes = read_json(ROOT / "studies/paper1/reference_hashes.json")
    expected = {entry["path"]: entry["sha256"] for entry in hashes["files"]}
    for name in ("analyze.py", "extended_analysis.py"):
        if hashlib.sha256((ROOT / "studies/paper1" / name).read_bytes()).hexdigest() != expected[name]:
            failures.append(f"Frozen Paper 1 source changed: {name}")
    if failures:
        raise SystemExit("\n".join(failures))
    print(json.dumps({"release_files_checked": len(files), "obvious_private_path_or_credential_matches": 0,
                      "demo_data_kind": "synthetic", "slowlife_protocol": "draft", "frozen_analysis_unchanged": True}))


if __name__ == "__main__":
    main()
