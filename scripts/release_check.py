"""Fast metadata and repository-state checks used before tagging a release."""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

from secret_scan import scan

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    ".github/workflows/ci.yml",
    ".github/workflows/release.yml",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "LICENSE",
    "README.md",
    "SECURITY.md",
    "docs/architecture.md",
    "docs/formats.md",
    "docs/repair.md",
    "docs/research.md",
    "examples/acme-mobile-2026-01.txt",
    "examples/acme-mobile-2026-02.txt",
    "pyproject.toml",
    "uv.lock",
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


def git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", f"safe.directory={ROOT.as_posix()}", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )


def run_checks(strict: bool) -> list[Check]:
    checks: list[Check] = []
    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    checks.append(
        Check(
            "required-files",
            "PASS" if not missing else "FAIL",
            "all required files present" if not missing else "missing: " + ", ".join(missing),
        )
    )
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    init = (ROOT / "src/billchangelog/__init__.py").read_text(encoding="utf-8")
    checks.append(
        Check(
            "version",
            "PASS" if 'version = "0.1.0"' in pyproject and '"0.1.0"' in init else "FAIL",
            "pyproject and source fallback use 0.1.0",
        )
    )
    secret_findings = scan(ROOT)
    checks.append(
        Check(
            "secrets",
            "PASS" if not secret_findings else "FAIL",
            "no credential patterns" if not secret_findings else "; ".join(secret_findings),
        )
    )
    status = git("status", "--porcelain")
    clean = status.returncode == 0 and not status.stdout.strip()
    state_status = "PASS" if clean else ("FAIL" if strict else "WARN")
    checks.append(Check("git-clean", state_status, "clean" if clean else status.stdout.strip()))

    head = git("rev-parse", "--verify", "HEAD")
    if head.returncode == 0:
        authors = git("shortlog", "-sne", "HEAD")
        contributors = [line for line in authors.stdout.splitlines() if line.strip()]
        author_ok = len(contributors) == 1 and "KanadeK" in contributors[0]
        checks.append(
            Check(
                "author-history",
                "PASS" if author_ok else "FAIL",
                " | ".join(contributors) if contributors else "no contributors found",
            )
        )
        log = git("log", "--format=%B", "HEAD")
        checks.append(
            Check(
                "co-authors",
                "PASS" if "Co-authored-by:" not in log.stdout else "FAIL",
                "no Co-authored-by trailers"
                if "Co-authored-by:" not in log.stdout
                else "trailer found",
            )
        )
    else:
        status_value = "FAIL" if strict else "WARN"
        checks.append(Check("author-history", status_value, "repository has no commit yet"))
        checks.append(Check("co-authors", status_value, "repository has no commit yet"))
    return checks


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    checks = run_checks(args.strict)
    if args.json:
        print(
            json.dumps(
                {
                    "ok": all(item.status != "FAIL" for item in checks),
                    "checks": [asdict(item) for item in checks],
                },
                indent=2,
            )
        )
    else:
        for item in checks:
            print(f"[{item.status}] {item.name}: {item.detail}")
    return 0 if all(item.status != "FAIL" for item in checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
