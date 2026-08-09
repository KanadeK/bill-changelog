"""Build deterministic wheel, sdist, portable pyz, demo bundle, and checksums."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.1.0"
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)
SOURCE_DATE_EPOCH = "1767225600"


def run(command: list[str], *, cwd: Path = ROOT, env: dict[str, str] | None = None) -> None:
    print("+ " + " ".join(command))
    subprocess.run(command, cwd=cwd, env=env, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def deterministic_zip(source: Path, target: Path) -> None:
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())


def build_portable_pyz(staging: Path, target: Path) -> None:
    import pypdf

    package_source = ROOT / "src" / "billchangelog"
    shutil.copytree(package_source, staging / "billchangelog")
    pypdf_source = Path(pypdf.__file__).resolve().parent
    shutil.copytree(
        pypdf_source,
        staging / "pypdf",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
    )
    (staging / "__main__.py").write_text(
        "from billchangelog.cli import main\nraise SystemExit(main())\n",
        encoding="utf-8",
        newline="\n",
    )
    deterministic_zip(staging, target)


def build_demo_bundle(staging: Path, target: Path) -> None:
    inputs = staging / "inputs"
    inputs.mkdir(parents=True)
    for name in (
        "acme-mobile-2026-01.txt",
        "acme-mobile-2026-02.txt",
        "acme-mobile-profile.json",
        "line-items.csv",
    ):
        shutil.copy2(ROOT / "examples" / name, inputs / name)
    report = staging / "report"
    run(
        [
            sys.executable,
            "-m",
            "billchangelog",
            "compare",
            str(inputs / "acme-mobile-2026-01.txt"),
            str(inputs / "acme-mobile-2026-02.txt"),
            "--profile",
            str(inputs / "acme-mobile-profile.json"),
            "--output",
            str(report),
        ]
    )
    (staging / "RUN.txt").write_text(
        "Bill Changelog fictional demo\n\n"
        "Compare again:\n"
        "  billchangelog compare inputs/acme-mobile-2026-01.txt "
        "inputs/acme-mobile-2026-02.txt --profile inputs/acme-mobile-profile.json "
        "--output my-report\n\n"
        "Verify the included report:\n"
        "  billchangelog verify report\n",
        encoding="utf-8",
        newline="\n",
    )
    deterministic_zip(staging, target)


def build_all(output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    environment = os.environ.copy()
    environment["SOURCE_DATE_EPOCH"] = SOURCE_DATE_EPOCH
    environment["PYTHONHASHSEED"] = "0"
    temp_root = ROOT / ".build-tmp"
    temp_root.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="release-", dir=temp_root) as temporary:
        work = Path(temporary)
        built = work / "built"
        run([sys.executable, "-m", "build", "--outdir", str(built)], env=environment)
        wheel = next(built.glob("*.whl"))
        sdist = next(built.glob("*.tar.gz"))
        destinations = [output / wheel.name, output / sdist.name]
        shutil.copy2(wheel, destinations[0])
        shutil.copy2(sdist, destinations[1])

        pyz = output / f"billchangelog-{VERSION}.pyz"
        build_portable_pyz(work / "pyz", pyz)
        destinations.append(pyz)

        demo = output / f"billchangelog-demo-{VERSION}.zip"
        demo_staging = work / "demo"
        demo_staging.mkdir()
        build_demo_bundle(demo_staging, demo)
        destinations.append(demo)

    checksum_path = output / "SHA256SUMS"
    checksum_path.write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sorted(destinations)),
        encoding="utf-8",
        newline="\n",
    )
    artifacts = [*destinations, checksum_path]
    summary = {
        "version": VERSION,
        "artifacts": [
            {"name": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in sorted(artifacts)
        ],
    }
    (output / "build-manifest.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "release-dist")
    args = parser.parse_args()
    summary = build_all(args.output.resolve())
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
