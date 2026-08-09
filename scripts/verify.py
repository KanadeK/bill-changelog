"""One-command local acceptance gate with deterministic packaging checks."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(
    name: str,
    command: list[str],
    *,
    cwd: Path = ROOT,
    env: dict[str, str] | None = None,
) -> None:
    print(f"\n== {name} ==")
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=cwd, check=True, env=env)


def file_hashes(directory: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    for path in sorted(directory.iterdir()):
        if path.is_file():
            result[path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def venv_python(directory: Path) -> Path:
    return directory / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-audit", action="store_true", help="skip dependency advisory lookup")
    args = parser.parse_args()
    run("Ruff lint", [sys.executable, "-m", "ruff", "check", "."])
    run("Ruff format", [sys.executable, "-m", "ruff", "format", "--check", "."])
    run("Mypy", [sys.executable, "-m", "mypy", "src", "scripts"])
    run(
        "Tests and coverage",
        [
            sys.executable,
            "-m",
            "pytest",
            "--cov=billchangelog",
            "--cov-report=term-missing",
            "--cov-fail-under=90",
        ],
    )
    run("Secret scan", [sys.executable, "scripts/secret_scan.py"])
    if not args.skip_audit:
        audit_env = os.environ.copy()
        # pip-api decodes `pip --version` as UTF-8. Force the child interpreter
        # to emit UTF-8 so Windows user/profile paths are audited reliably.
        audit_env["PYTHONUTF8"] = "1"
        run(
            "Dependency audit",
            [sys.executable, "-m", "pip_audit", "--skip-editable"],
            env=audit_env,
        )

    temp_root = ROOT / ".verify-tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gate-", dir=temp_root) as temporary:
        work = Path(temporary)
        first = work / "first"
        second = work / "second"
        run(
            "Package release (run 1)",
            [sys.executable, "scripts/package_release.py", "--output", str(first)],
        )
        time.sleep(2.1)
        run(
            "Package release (run 2)",
            [sys.executable, "scripts/package_release.py", "--output", str(second)],
        )
        first_hashes = file_hashes(first)
        second_hashes = file_hashes(second)
        if first_hashes != second_hashes:
            differing = sorted(set(first_hashes) | set(second_hashes))
            raise RuntimeError("release artifacts are not deterministic: " + ", ".join(differing))
        print("[PASS] release artifacts are byte-identical across separated builds")

        pyz = first / "billchangelog-0.1.0.pyz"
        run("Portable archive version", [sys.executable, str(pyz), "--version"])
        demo_output = work / "pyz-demo"
        run("Portable archive demo", [sys.executable, str(pyz), "demo", "-o", str(demo_output)])
        run("Portable archive verify", [sys.executable, str(pyz), "verify", str(demo_output)])

        wheel = next(first.glob("*.whl"))
        smoke = work / "smoke-venv"
        run("Create clean smoke venv", [sys.executable, "-m", "venv", str(smoke)])
        smoke_python = venv_python(smoke)
        run(
            "Install wheel without dependency reuse",
            [str(smoke_python), "-m", "pip", "install", "--no-deps", str(wheel)],
        )
        run("Wheel import smoke", [str(smoke_python), "-m", "billchangelog", "--version"])

        release_output = ROOT / "release-dist"
        release_output.mkdir(exist_ok=True)
        for existing in release_output.iterdir():
            if existing.is_file():
                existing.unlink()
        for artifact in first.iterdir():
            if artifact.is_file():
                shutil.copy2(artifact, release_output / artifact.name)
    print("\nALL ACCEPTANCE CHECKS PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
