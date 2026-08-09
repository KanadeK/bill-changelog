from __future__ import annotations

import json
from pathlib import Path

from billchangelog.diff import compare_statements
from billchangelog.extract import capture_path
from billchangelog.manifest import verify_bundle
from billchangelog.profile import load_profile
from billchangelog.report import write_report_bundle


def test_report_bundle_redacts_and_verifies(
    example_before: Path, example_after: Path, example_profile: Path, tmp_path: Path
) -> None:
    profile = load_profile(example_profile)
    comparison = compare_statements(
        capture_path(example_before, profile), capture_path(example_after, profile), profile
    )
    artifacts = write_report_bundle(comparison, tmp_path / "report")
    assert len(artifacts) == 5
    assert verify_bundle(tmp_path / "report") == []
    report_text = (tmp_path / "report" / "report.json").read_text(encoding="utf-8")
    assert "88310492" not in report_text
    assert "••••0492" in report_text
    payload = json.loads(report_text)
    assert payload["summary"]["annualized_delta"] == "276.00"
    support = (tmp_path / "report" / "support.md").read_text(encoding="utf-8")
    assert "not a finding of fraud" in support
    assert "Suggested question" in support


def test_manifest_detects_tampering(
    example_before: Path, example_after: Path, example_profile: Path, tmp_path: Path
) -> None:
    profile = load_profile(example_profile)
    comparison = compare_statements(
        capture_path(example_before, profile), capture_path(example_after, profile), profile
    )
    bundle = tmp_path / "report"
    write_report_bundle(comparison, bundle)
    (bundle / "support.md").write_text("tampered", encoding="utf-8")
    assert verify_bundle(bundle) == ["hash mismatch: support.md", "size mismatch: support.md"]


def test_html_escapes_untrusted_labels(
    example_before: Path, example_after: Path, example_profile: Path, tmp_path: Path
) -> None:
    malicious = tmp_path / "malicious.txt"
    malicious.write_text(
        "Provider: Demo\nStatement date: 2026-03-15\n<script>alert(1)</script> | $4.00\nTotal due | $4.00\n",
        encoding="utf-8",
    )
    profile = load_profile(example_profile)
    comparison = compare_statements(
        capture_path(example_after, profile), capture_path(malicious, profile), profile
    )
    bundle = tmp_path / "escaped"
    write_report_bundle(comparison, bundle)
    html_text = (bundle / "report.html").read_text(encoding="utf-8")
    assert "<script>alert(1)</script>" not in html_text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_text


def test_existing_bundle_requires_force(
    example_before: Path, example_after: Path, example_profile: Path, tmp_path: Path
) -> None:
    profile = load_profile(example_profile)
    comparison = compare_statements(
        capture_path(example_before, profile), capture_path(example_after, profile), profile
    )
    bundle = tmp_path / "report"
    write_report_bundle(comparison, bundle)
    try:
        write_report_bundle(comparison, bundle)
    except FileExistsError as exc:
        assert "--force" in str(exc)
    else:
        raise AssertionError("expected FileExistsError")
    write_report_bundle(comparison, bundle, force=True)
