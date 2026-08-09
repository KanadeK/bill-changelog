"""Tamper-evident bundle manifests."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from billchangelog import __version__
from billchangelog.models import Comparison


def sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_manifest(
    output_dir: Path, artifacts: list[Path], comparison: Comparison
) -> dict[str, Any]:
    report_path = output_dir / "report.json"
    comparison_id = sha256_path(report_path)[:20]
    return {
        "schema_version": 1,
        "tool": {"name": "billchangelog", "version": __version__},
        "comparison_id": comparison_id,
        "inputs": [
            {"name": comparison.before.source_name, "sha256": comparison.before.source_sha256},
            {"name": comparison.after.source_name, "sha256": comparison.after.source_sha256},
        ],
        "artifacts": [
            {
                "name": artifact.relative_to(output_dir).as_posix(),
                "sha256": sha256_path(artifact),
                "bytes": artifact.stat().st_size,
            }
            for artifact in sorted(artifacts)
        ],
    }


def verify_bundle(bundle_dir: Path) -> list[str]:
    manifest_path = bundle_dir / "manifest.json"
    if not manifest_path.is_file():
        return ["manifest.json is missing"]
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return [f"manifest.json is invalid: {exc}"]
    errors: list[str] = []
    artifacts = manifest.get("artifacts", [])
    if not isinstance(artifacts, list) or not artifacts:
        return ["manifest has no artifacts"]
    root = bundle_dir.resolve()
    for entry in artifacts:
        if not isinstance(entry, dict) or not isinstance(entry.get("name"), str):
            errors.append("manifest contains an invalid artifact entry")
            continue
        candidate = (root / entry["name"]).resolve()
        try:
            candidate.relative_to(root)
        except ValueError:
            errors.append(f"artifact escapes bundle directory: {entry['name']}")
            continue
        if not candidate.is_file():
            errors.append(f"artifact is missing: {entry['name']}")
            continue
        actual = sha256_path(candidate)
        if actual != entry.get("sha256"):
            errors.append(f"hash mismatch: {entry['name']}")
        if candidate.stat().st_size != entry.get("bytes"):
            errors.append(f"size mismatch: {entry['name']}")
    return errors
