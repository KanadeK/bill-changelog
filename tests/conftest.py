from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


@pytest.fixture
def example_before(project_root: Path) -> Path:
    return project_root / "examples" / "acme-mobile-2026-01.txt"


@pytest.fixture
def example_after(project_root: Path) -> Path:
    return project_root / "examples" / "acme-mobile-2026-02.txt"


@pytest.fixture
def example_profile(project_root: Path) -> Path:
    return project_root / "examples" / "acme-mobile-profile.json"
