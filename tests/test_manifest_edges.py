from __future__ import annotations

import json
from pathlib import Path

from billchangelog.manifest import verify_bundle


def test_manifest_missing_invalid_and_empty(tmp_path: Path) -> None:
    assert verify_bundle(tmp_path) == ["manifest.json is missing"]
    (tmp_path / "manifest.json").write_text("{", encoding="utf-8")
    assert "is invalid" in verify_bundle(tmp_path)[0]
    (tmp_path / "manifest.json").write_text('{"artifacts": []}', encoding="utf-8")
    assert verify_bundle(tmp_path) == ["manifest has no artifacts"]


def test_manifest_rejects_invalid_missing_and_escape_entries(tmp_path: Path) -> None:
    manifest = {
        "artifacts": [
            "bad",
            {"name": "missing.txt", "sha256": "x", "bytes": 1},
            {"name": "../escape.txt", "sha256": "x", "bytes": 1},
        ]
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    errors = verify_bundle(tmp_path)
    assert "manifest contains an invalid artifact entry" in errors
    assert "artifact is missing: missing.txt" in errors
    assert "artifact escapes bundle directory: ../escape.txt" in errors
