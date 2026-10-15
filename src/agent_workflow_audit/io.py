"""Strict JSON, safe relative evidence paths, and exclusive output writes."""

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath


class AuditError(ValueError):
    """An actionable input or integrity error."""


def utc_now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


def digest_bytes(value):
    return hashlib.sha256(value).hexdigest()


def file_digest(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AuditError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def parse_json(text):
    def reject(value):
        raise AuditError(f"Non-finite JSON number: {value}")
    try:
        return json.loads(text, object_pairs_hook=_unique_object, parse_constant=reject)
    except json.JSONDecodeError as error:
        raise AuditError(f"Invalid JSON at line {error.lineno}, column {error.colno}: {error.msg}") from error


def read_json(path):
    try:
        return parse_json(Path(path).read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError as error:
        raise AuditError("JSON input must be UTF-8") from error


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")


def safe_relative(value):
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise AuditError("Evidence paths must be nonempty, relative POSIX paths")
    parts = PurePosixPath(value).parts
    if value.startswith("/") or PureWindowsPath(value).is_absolute() or ".." in parts:
        raise AuditError(f"Path escapes the evidence root: {value}")
    if any(part in ("", ".") for part in value.split("/")):
        raise AuditError(f"Noncanonical relative path: {value}")
    return value


def contained_path(root, relative):
    root = Path(root).resolve()
    target = (root / safe_relative(relative)).resolve()
    if not target.is_relative_to(root):
        raise AuditError(f"Resolved path escapes the evidence root: {relative}")
    return target


def make_manifest(directory, exclude=("manifest.json",)):
    directory = Path(directory)
    files = []
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise AuditError("Snapshots may not contain symbolic links")
        if path.is_file() and path.relative_to(directory).as_posix() not in exclude:
            files.append({"path": path.relative_to(directory).as_posix(),
                          "bytes": path.stat().st_size, "sha256": file_digest(path)})
    return {"manifest_version": 1, "files": files}


def verify_manifest(directory, expected_manifest_sha256=None):
    directory = Path(directory)
    manifest_path = directory / "manifest.json"
    if expected_manifest_sha256 and file_digest(manifest_path) != expected_manifest_sha256:
        raise AuditError("Manifest does not match the externally retained SHA-256")
    manifest = read_json(manifest_path)
    if not isinstance(manifest, dict) or manifest.get("manifest_version") != 1 or not isinstance(manifest.get("files"), list):
        raise AuditError("Invalid snapshot manifest; expected manifest_version 1 and a files array")
    names = set()
    for entry in manifest["files"]:
        if not isinstance(entry, dict) or not all(key in entry for key in ("path", "bytes", "sha256")):
            raise AuditError("Malformed manifest entry")
        if type(entry["bytes"]) is not int or entry["bytes"] < 0 or not isinstance(entry["sha256"], str):
            raise AuditError("Invalid manifest size or digest")
        name = safe_relative(entry["path"])
        if name in names or name == "manifest.json":
            raise AuditError(f"Duplicate or self-referencing manifest path: {name}")
        names.add(name)
        path = contained_path(directory, name)
        if not path.is_file() or path.stat().st_size != entry["bytes"] or file_digest(path) != entry["sha256"]:
            raise AuditError(f"Manifest mismatch: {name}")
    actual = {p.relative_to(directory).as_posix() for p in directory.rglob("*") if p.is_file()}
    if actual != names | {"manifest.json"}:
        raise AuditError("Snapshot contains unmanifested files or omits manifested files")
    return {"files_verified": len(names), "manifest_sha256": file_digest(manifest_path)}
