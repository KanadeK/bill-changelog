"""Deterministic, explainable line-item matching and change scoring."""

from __future__ import annotations

from decimal import Decimal
from difflib import SequenceMatcher

from billchangelog.models import Change, Comparison, LineItem, Statement
from billchangelog.profile import Profile

ZERO = Decimal("0.00")
TWELVE = Decimal("12")


def compare_statements(before: Statement, after: Statement, profile: Profile) -> Comparison:
    if before.currency != after.currency:
        raise ValueError(
            f"currency mismatch: before is {before.currency}, after is {after.currency}; "
            "convert or capture both statements with one currency"
        )
    matches, before_unmatched, after_unmatched = _match_items(before.items, after.items, profile)
    changes: list[Change] = []
    for before_index, after_index, score in matches:
        old = before.items[before_index]
        new = after.items[after_index]
        fields: list[str] = []
        if old.normalized_label != new.normalized_label:
            fields.append("label")
        if old.amount != new.amount:
            fields.append("amount")
        if old.category != new.category:
            fields.append("category")
        if old.cadence != new.cadence:
            fields.append("cadence")
        if not fields:
            continue
        delta = new.amount - old.amount
        annualized = delta * TWELVE if _is_monthly(old, new) else None
        changes.append(
            Change(
                kind="modified",
                before=old,
                after=new,
                fields_changed=tuple(fields),
                delta=delta,
                annualized_delta=annualized,
                match_score=score,
                severity=_severity(old, new, delta, annualized, profile),
                impact=_impact(delta),
            )
        )
    for index in before_unmatched:
        old = before.items[index]
        delta = -old.amount
        annualized = delta * TWELVE if old.cadence == "monthly" else None
        changes.append(
            Change(
                kind="removed",
                before=old,
                after=None,
                fields_changed=("presence",),
                delta=delta,
                annualized_delta=annualized,
                match_score=None,
                severity=_severity(old, None, delta, annualized, profile),
                impact=_impact(delta),
            )
        )
    for index in after_unmatched:
        new = after.items[index]
        delta = new.amount
        annualized = delta * TWELVE if new.cadence == "monthly" else None
        changes.append(
            Change(
                kind="added",
                before=None,
                after=new,
                fields_changed=("presence",),
                delta=delta,
                annualized_delta=annualized,
                match_score=None,
                severity=_severity(None, new, delta, annualized, profile),
                impact=_impact(delta),
            )
        )
    changes.sort(key=_change_sort_key)
    before_total = before.total if before.total is not None else _sum_items(before.items)
    after_total = after.total if after.total is not None else _sum_items(after.items)
    monthly_delta = sum(
        (change.delta for change in changes if change.annualized_delta is not None),
        start=ZERO,
    )
    warnings = [*before.warnings, *after.warnings]
    low_confidence = [
        change.label
        for change in changes
        if change.match_score is not None
        and change.match_score < max(profile.match_threshold + 0.1, 0.85)
    ]
    if low_confidence:
        warnings.append(
            "review fuzzy matches near the configured threshold: " + ", ".join(low_confidence)
        )
    return Comparison(
        before=before,
        after=after,
        changes=tuple(changes),
        total_delta=after_total - before_total,
        monthly_delta=monthly_delta,
        annualized_delta=monthly_delta * TWELVE,
        warnings=tuple(dict.fromkeys(warnings)),
    )


def _match_items(
    before: tuple[LineItem, ...],
    after: tuple[LineItem, ...],
    profile: Profile,
) -> tuple[list[tuple[int, int, float]], list[int], list[int]]:
    unmatched_before = set(range(len(before)))
    unmatched_after = set(range(len(after)))
    matches: list[tuple[int, int, float]] = []

    candidates: list[tuple[float, int, int]] = []
    for old_index, old in enumerate(before):
        for new_index, new in enumerate(after):
            score = _match_score(old, new)
            if score >= profile.match_threshold:
                candidates.append((score, old_index, new_index))
    candidates.sort(
        key=lambda candidate: (
            -candidate[0],
            abs(before[candidate[1]].amount - after[candidate[2]].amount),
            before[candidate[1]].normalized_label,
            after[candidate[2]].normalized_label,
        )
    )
    for score, old_index, new_index in candidates:
        if old_index not in unmatched_before or new_index not in unmatched_after:
            continue
        matches.append((old_index, new_index, score))
        unmatched_before.remove(old_index)
        unmatched_after.remove(new_index)
    return matches, sorted(unmatched_before), sorted(unmatched_after)


def _match_score(old: LineItem, new: LineItem) -> float:
    if old.normalized_label == new.normalized_label:
        return 1.0
    old_tokens = set(old.normalized_label.split())
    new_tokens = set(new.normalized_label.split())
    union = old_tokens | new_tokens
    jaccard = len(old_tokens & new_tokens) / len(union) if union else 0.0
    sequence = SequenceMatcher(None, old.normalized_label, new.normalized_label).ratio()
    score = (sequence * 0.65) + (jaccard * 0.35)
    if old.category == new.category:
        score = min(1.0, score + 0.04)
    return score


def _severity(
    old: LineItem | None,
    new: LineItem | None,
    delta: Decimal,
    annualized: Decimal | None,
    profile: Profile,
) -> str:
    if old is not None and old.category == "discount" and new is None:
        return "high"
    if old is not None and new is not None and old.category == "discount" and delta > 0:
        return "high" if abs(delta) >= profile.high_monthly_delta else "medium"
    if annualized is not None and abs(annualized) >= profile.high_annual_delta:
        return "high"
    if abs(delta) >= profile.high_monthly_delta and _is_monthly(old, new):
        return "high"
    if delta != ZERO or old is None or new is None:
        return "medium"
    return "low"


def _is_monthly(old: LineItem | None, new: LineItem | None) -> bool:
    return (old is not None and old.cadence == "monthly") or (
        new is not None and new.cadence == "monthly"
    )


def _sum_items(items: tuple[LineItem, ...]) -> Decimal:
    return sum((item.amount for item in items), start=ZERO)


def _impact(delta: Decimal) -> str:
    if delta > ZERO:
        return "cost_increase"
    if delta < ZERO:
        return "cost_decrease"
    return "neutral"


def _change_sort_key(change: Change) -> tuple[int, Decimal, str]:
    severity_rank = {"high": 0, "medium": 1, "low": 2}
    return severity_rank[change.severity], -abs(change.delta), change.label.casefold()
