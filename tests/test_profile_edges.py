from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from billchangelog.profile import load_profile, profile_from_dict


def test_profile_matching_helpers() -> None:
    profile = load_profile()
    assert profile.classify("mystery", Decimal("-1")) == "discount"
    assert profile.classify("mystery", Decimal("1")) == "other"
    assert profile.cadence_for("One-time activation", "one_time") == "one_time"
    assert profile.cadence_for("Meter reading", "usage") == "unknown"
    assert profile.should_ignore("Previous balance")
    assert profile.is_total("Total due")


def test_profile_invalid_custom_shapes(tmp_path: Path) -> None:
    custom = tmp_path / "profile.json"
    custom.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="root must be"):
        load_profile(custom)
    with pytest.raises(ValueError, match="aliases"):
        profile_from_dict({"aliases": []})
