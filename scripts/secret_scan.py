"""Small deterministic secret scan for source and release gates."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_DIRS = {
    ".git",
    ".mypy_cache",
    ".pytest-tmp",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "build",
    "dist",
    "examples/generated",
    "release-dist",
}
PATTERNS = {
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\bgh[opusr]_[A-Za-z0-9]{20,}\b"),
    "OpenAI-style key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "AWS access key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "Slack token": re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{20,}\b"),
}


def source_files(root: Path = ROOT) -> list[Path]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if not path.is_file() or path.stat().st_size > 2_000_000:
            continue
        relative = path.relative_to(root).as_posix()
        if any(relative == item or relative.startswith(f"{item}/") for item in EXCLUDED_DIRS):
            continue
        files.append(path)
    return sorted(files)


def scan(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in source_files(root):
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        relative = path.relative_to(root).as_posix()
        for line_number, line in enumerate(text.splitlines(), 1):
            for name, pattern in PATTERNS.items():
                if pattern.search(line):
                    findings.append(f"{relative}:{line_number}: possible {name}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description="Scan repository text for credential patterns")
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    findings = scan(args.root.resolve())
    if findings:
        print("Secret scan failed:")
        for finding in findings:
            print(f"  - {finding}")
        return 1
    print(f"Secret scan passed ({len(source_files(args.root.resolve()))} files checked)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
