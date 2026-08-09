"""Command-line interface for capture, comparison, verification, and demos."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from collections.abc import Sequence
from contextlib import ExitStack
from importlib.resources import as_file, files
from pathlib import Path

from billchangelog import __version__
from billchangelog.diff import compare_statements
from billchangelog.extract import CaptureOverrides, ExtractionError, capture_path
from billchangelog.manifest import verify_bundle
from billchangelog.models import Comparison
from billchangelog.profile import load_profile
from billchangelog.report import write_report_bundle


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="billchangelog",
        description="Local-first, evidence-linked diffs for recurring bills.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    capture = subparsers.add_parser(
        "capture", help="extract one bill into a reviewable JSON snapshot"
    )
    capture.add_argument("input", type=Path)
    capture.add_argument("--output", "-o", type=Path, required=True)
    capture.add_argument("--profile", type=Path)
    _add_capture_overrides(capture)
    capture.add_argument("--force", action="store_true", help="replace the named output file")
    capture.set_defaults(handler=_handle_capture)

    compare = subparsers.add_parser("compare", help="compare two bills or captured snapshots")
    compare.add_argument("before", type=Path)
    compare.add_argument("after", type=Path)
    compare.add_argument("--output", "-o", type=Path, required=True)
    compare.add_argument("--profile", type=Path)
    compare.add_argument(
        "--fail-on",
        choices=("never", "any", "medium", "high"),
        default="never",
        help="return exit code 1 when changes meet this severity threshold",
    )
    compare.add_argument(
        "--include-sensitive-evidence",
        action="store_true",
        help="do not mask likely account, phone, and email identifiers in reports",
    )
    compare.add_argument("--force", action="store_true", help="replace known report artifacts")
    compare.set_defaults(handler=_handle_compare)

    verify = subparsers.add_parser("verify", help="verify every artifact hash in a report bundle")
    verify.add_argument("bundle", type=Path)
    verify.set_defaults(handler=_handle_verify)

    demo = subparsers.add_parser("demo", help="run the bundled fictional two-month example")
    demo.add_argument("--output", "-o", type=Path, default=Path("billchangelog-demo"))
    demo.add_argument("--force", action="store_true", help="replace known demo/report artifacts")
    demo.set_defaults(handler=_handle_demo)

    doctor = subparsers.add_parser(
        "doctor", help="check the installation and bundled demo pipeline"
    )
    doctor.set_defaults(handler=_handle_doctor)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return int(args.handler(args))
    except (ExtractionError, FileExistsError, OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


def _add_capture_overrides(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider")
    parser.add_argument("--statement-date")
    parser.add_argument("--due-date")
    parser.add_argument("--period-start")
    parser.add_argument("--period-end")
    parser.add_argument("--account-hint")
    parser.add_argument("--currency")


def _handle_capture(args: argparse.Namespace) -> int:
    output: Path = args.output
    if output.exists() and not args.force:
        raise FileExistsError(f"output exists: {output}; pass --force to replace it")
    profile = load_profile(args.profile)
    statement = capture_path(args.input, profile, _overrides(args))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(statement.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(f"Captured {len(statement.items)} line item(s) from {statement.source_name} -> {output}")
    for warning in statement.warnings:
        print(f"WARNING: {warning}", file=sys.stderr)
    return 0


def _handle_compare(args: argparse.Namespace) -> int:
    profile = load_profile(args.profile)
    before = capture_path(args.before, profile)
    after = capture_path(args.after, profile)
    comparison = compare_statements(before, after, profile)
    artifacts = write_report_bundle(
        comparison,
        args.output,
        include_sensitive_evidence=args.include_sensitive_evidence,
        force=args.force,
    )
    print(_summary_line(comparison))
    print("Artifacts:")
    for artifact in artifacts:
        print(f"  {artifact}")
    return 1 if _should_fail(comparison, args.fail_on) else 0


def _handle_verify(args: argparse.Namespace) -> int:
    errors = verify_bundle(args.bundle)
    if errors:
        print("Bundle verification failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 2
    print(f"Verified all artifacts in {args.bundle}")
    return 0


def _handle_demo(args: argparse.Namespace) -> int:
    with ExitStack() as stack:
        before = stack.enter_context(
            as_file(files("billchangelog.data").joinpath("demo-before.txt"))
        )
        after = stack.enter_context(as_file(files("billchangelog.data").joinpath("demo-after.txt")))
        profile_path = stack.enter_context(
            as_file(files("billchangelog.data").joinpath("demo-profile.json"))
        )
        profile = load_profile(profile_path)
        comparison = compare_statements(
            capture_path(before, profile), capture_path(after, profile), profile
        )
    artifacts = write_report_bundle(comparison, args.output, force=args.force)
    print(_summary_line(comparison))
    print(f"Demo report: {args.output / 'report.html'}")
    print(f'Verification: billchangelog verify "{args.output}"')
    if not artifacts:
        raise RuntimeError("demo produced no artifacts")
    return 0


def _handle_doctor(args: argparse.Namespace) -> int:
    del args
    checks: list[tuple[str, bool, str]] = []
    try:
        import pypdf

        checks.append(("PDF extractor", True, f"pypdf {pypdf.__version__}"))
    except ImportError:
        checks.append(("PDF extractor", False, "pypdf is missing"))
    with tempfile.TemporaryDirectory(prefix="billchangelog-doctor-") as temporary:
        output = Path(temporary) / "report"
        namespace = argparse.Namespace(output=output, force=False)
        try:
            _handle_demo(namespace)
            errors = verify_bundle(output)
            checks.append(("Bundled demo", not errors, "; ".join(errors) if errors else "verified"))
        except (OSError, ValueError) as exc:
            checks.append(("Bundled demo", False, str(exc)))
    for name, ok, detail in checks:
        print(f"[{'PASS' if ok else 'FAIL'}] {name}: {detail}")
    return 0 if all(ok for _, ok, _ in checks) else 2


def _overrides(args: argparse.Namespace) -> CaptureOverrides:
    return CaptureOverrides(
        provider=args.provider,
        statement_date=args.statement_date,
        due_date=args.due_date,
        period_start=args.period_start,
        period_end=args.period_end,
        account_hint=args.account_hint,
        currency=args.currency,
    )


def _should_fail(comparison: Comparison, threshold: str) -> bool:
    if threshold == "never":
        return False
    ranks = {"low": 1, "medium": 2, "high": 3}
    minimum = 1 if threshold == "any" else ranks[threshold]
    changes = comparison.changes
    return any(ranks[change.severity] >= minimum for change in changes)


def _summary_line(comparison: Comparison) -> str:
    changes = comparison.changes
    total_delta = comparison.total_delta
    monthly_delta = comparison.monthly_delta
    annualized_delta = comparison.annualized_delta
    currency = comparison.after.currency
    high_count = sum(change.severity == "high" for change in changes)
    return (
        f"{len(changes)} change(s), {high_count} high; total {currency} {total_delta:+.2f}; "
        f"monthly {currency} {monthly_delta:+.2f}; annualized {currency} {annualized_delta:+.2f}"
    )


if __name__ == "__main__":
    raise SystemExit(main())
