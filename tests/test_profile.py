from decimal import Decimal

import pytest

from billchangelog.profile import load_profile, profile_from_dict


def test_generic_profile_classifies_common_charges() -> None:
    profile = load_profile()
    assert profile.classify("Monthly unlimited plan", Decimal("70")) == "recurring"
    assert profile.classify("Autopay discount", Decimal("-5")) == "discount"
    assert profile.classify("Network access fee", Decimal("3")) == "fee"
    assert profile.classify("State tax", Decimal("2")) == "tax"
    assert profile.cadence_for("Monthly unlimited plan", "recurring") == "monthly"


def test_custom_alias_and_threshold(example_profile) -> None:  # type: ignore[no-untyped-def]
    profile = load_profile(example_profile)
    assert profile.normalize("Unlimited 5G Plan Plus") == "unlimited 5g plan"
    assert profile.name == "acme-mobile-demo"


def test_profile_validation() -> None:
    with pytest.raises(ValueError, match="between 0 and 1"):
        profile_from_dict({"match_threshold": 2})
    with pytest.raises(ValueError, match="category_patterns"):
        profile_from_dict({"category_patterns": []})
