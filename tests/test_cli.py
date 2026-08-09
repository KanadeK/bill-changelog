from __future__ import annotations

from pathlib import Path

from billchangelog.cli import main


def test_capture_compare_and_verify_cli(
    example_before: Path,
    example_after: Path,
    example_profile: Path,
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "before.json"
    assert (
        main(
            ["capture", str(example_before), "-o", str(snapshot), "--profile", str(example_profile)]
        )
        == 0
    )
    bundle = tmp_path / "report"
    assert (
        main(
            [
                "compare",
                str(snapshot),
                str(example_after),
                "-o",
                str(bundle),
                "--profile",
                str(example_profile),
            ]
        )
        == 0
    )
    assert main(["verify", str(bundle)]) == 0
    assert main(["verify", str(tmp_path / "missing")]) == 2


def test_fail_on_and_demo(
    tmp_path: Path, example_before: Path, example_after: Path, example_profile: Path
) -> None:
    bundle = tmp_path / "strict"
    assert (
        main(
            [
                "compare",
                str(example_before),
                str(example_after),
                "-o",
                str(bundle),
                "--profile",
                str(example_profile),
                "--fail-on",
                "high",
            ]
        )
        == 1
    )
    demo = tmp_path / "demo"
    assert main(["demo", "-o", str(demo)]) == 0
    assert (demo / "report.html").is_file()


def test_cli_force_doctor_sensitive_and_errors(
    example_before: Path,
    example_after: Path,
    example_profile: Path,
    tmp_path: Path,
) -> None:
    snapshot = tmp_path / "capture.json"
    command = [
        "capture",
        str(example_before),
        "-o",
        str(snapshot),
        "--profile",
        str(example_profile),
    ]
    assert main(command) == 0
    assert main(command) == 2
    assert main([*command, "--force"]) == 0

    sensitive = tmp_path / "sensitive"
    assert (
        main(
            [
                "compare",
                str(example_before),
                str(example_after),
                "-o",
                str(sensitive),
                "--profile",
                str(example_profile),
                "--include-sensitive-evidence",
                "--fail-on",
                "any",
            ]
        )
        == 1
    )
    assert "88310492" in (sensitive / "report.json").read_text(encoding="utf-8")
    (sensitive / "support.md").write_text("tamper", encoding="utf-8")
    assert main(["verify", str(sensitive)]) == 2
    assert main(["doctor"]) == 0
    assert main(["capture", str(tmp_path / "missing.txt"), "-o", str(tmp_path / "x")]) == 2
