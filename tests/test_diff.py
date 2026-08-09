from dataclasses import replace
from decimal import Decimal
from pathlib import Path

import pytest

from billchangelog.diff import compare_statements
from billchangelog.extract import capture_path
from billchangelog.models import Evidence, LineItem, Statement
from billchangelog.profile import load_profile


def test_demo_diff_is_explainable(
    example_before: Path, example_after: Path, example_profile: Path
) -> None:
    profile = load_profile(example_profile)
    comparison = compare_statements(
        capture_path(example_before, profile), capture_path(example_after, profile), profile
    )
    assert len(comparison.changes) == 4
    assert comparison.total_delta == Decimal("23.35")
    assert comparison.monthly_delta == Decimal("23.00")
    assert comparison.annualized_delta == Decimal("276.00")
    changes = {change.label: change for change in comparison.changes}
    assert changes["Unlimited 5G Plan Plus"].kind == "modified"
    assert changes["Unlimited 5G Plan Plus"].delta == Decimal("10.00")
    assert changes["Autopay discount"].kind == "removed"
    assert changes["Autopay discount"].severity == "high"
    assert changes["Network access fee"].kind == "added"


def test_currency_mismatch_is_rejected(example_before: Path) -> None:
    profile = load_profile()
    before = capture_path(example_before, profile)
    after = Statement(**{**before.__dict__, "currency": "EUR"})
    with pytest.raises(ValueError, match="currency mismatch"):
        compare_statements(before, after, profile)


def test_fuzzy_match_warning_near_threshold() -> None:
    profile = replace(load_profile(), match_threshold=0.6)
    old = _statement(_item("Fiber access plan", "45"), "old")
    new = _statement(_item("Fiber access package", "46"), "new")
    comparison = compare_statements(old, new, profile)
    assert comparison.changes[0].kind == "modified"
    assert comparison.warnings


def test_no_change_and_cost_decrease_fallback_totals() -> None:
    profile = load_profile()
    item = _item("Monthly plan", "20")
    before = _statement(item, "old")
    identical = _statement(item, "new")
    no_change = compare_statements(before, identical, profile)
    assert no_change.changes == ()
    assert no_change.total_delta == Decimal("0.00")

    cheaper = _statement(_item("Monthly plan", "8"), "cheap")
    comparison = compare_statements(before, cheaper, profile)
    assert comparison.changes[0].impact == "cost_decrease"
    assert comparison.changes[0].severity == "high"


def _item(label: str, amount: str) -> LineItem:
    profile = load_profile()
    value = Decimal(amount)
    category = profile.classify(label, value)
    return LineItem(
        label=label,
        normalized_label=profile.normalize(label),
        amount=value,
        category=category,
        cadence="monthly",
        evidence=Evidence("fixture", "line 1", f"{label} ${amount}"),
    )


def _statement(item: LineItem, name: str) -> Statement:
    return Statement(
        provider="Fixture",
        statement_date="2026-01-01",
        period_start=None,
        period_end=None,
        due_date=None,
        currency="USD",
        account_hint=None,
        total=item.amount,
        items=(item,),
        source_name=f"{name}.txt",
        source_sha256=name * 32,
        extractor="test",
    )
