"""Typed domain models and stable JSON serialization."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

SCHEMA_VERSION = 1
CATEGORIES = {"recurring", "usage", "fee", "tax", "discount", "one_time", "other"}
CADENCES = {"monthly", "one_time", "unknown"}


def decimal_text(value: Decimal | None) -> str | None:
    """Serialize money without binary floating-point artifacts."""
    if value is None:
        return None
    normalized = value.quantize(Decimal("0.01"))
    return format(normalized, "f")


@dataclass(frozen=True)
class Evidence:
    source: str
    locator: str
    excerpt: str

    def to_dict(self) -> dict[str, str]:
        return {"source": self.source, "locator": self.locator, "excerpt": self.excerpt}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Evidence:
        return cls(
            source=str(data.get("source", "unknown")),
            locator=str(data.get("locator", "unknown")),
            excerpt=str(data.get("excerpt", "")),
        )


@dataclass(frozen=True)
class LineItem:
    label: str
    normalized_label: str
    amount: Decimal
    category: str
    cadence: str
    evidence: Evidence
    confidence: float = 1.0

    def __post_init__(self) -> None:
        if self.category not in CATEGORIES:
            raise ValueError(f"unsupported category: {self.category}")
        if self.cadence not in CADENCES:
            raise ValueError(f"unsupported cadence: {self.cadence}")
        if not 0 <= self.confidence <= 1:
            raise ValueError("confidence must be between 0 and 1")

    def to_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "normalized_label": self.normalized_label,
            "amount": decimal_text(self.amount),
            "category": self.category,
            "cadence": self.cadence,
            "confidence": round(self.confidence, 4),
            "evidence": self.evidence.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LineItem:
        evidence_data = data.get("evidence")
        evidence = (
            Evidence.from_dict(evidence_data)
            if isinstance(evidence_data, dict)
            else Evidence("unknown", "unknown", str(data.get("label", "")))
        )
        return cls(
            label=str(data["label"]),
            normalized_label=str(data.get("normalized_label") or data["label"]),
            amount=Decimal(str(data["amount"])),
            category=str(data.get("category", "other")),
            cadence=str(data.get("cadence", "unknown")),
            confidence=float(data.get("confidence", 1.0)),
            evidence=evidence,
        )


@dataclass(frozen=True)
class Statement:
    provider: str
    statement_date: str | None
    period_start: str | None
    period_end: str | None
    due_date: str | None
    currency: str
    account_hint: str | None
    total: Decimal | None
    items: tuple[LineItem, ...]
    source_name: str
    source_sha256: str
    extractor: str
    warnings: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "provider": self.provider,
            "statement_date": self.statement_date,
            "period_start": self.period_start,
            "period_end": self.period_end,
            "due_date": self.due_date,
            "currency": self.currency,
            "account_hint": self.account_hint,
            "total": decimal_text(self.total),
            "items": [item.to_dict() for item in self.items],
            "source": {
                "name": self.source_name,
                "sha256": self.source_sha256,
                "extractor": self.extractor,
            },
            "warnings": list(self.warnings),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Statement:
        version_value = int(data.get("schema_version", SCHEMA_VERSION))
        if version_value != SCHEMA_VERSION:
            raise ValueError(f"unsupported statement schema version: {version_value}")
        source = data.get("source", {})
        if not isinstance(source, dict):
            source = {}
        raw_items = data.get("items", data.get("line_items", []))
        if not isinstance(raw_items, list):
            raise ValueError("statement items must be a list")
        total_value = data.get("total")
        return cls(
            provider=str(data.get("provider", "Unknown provider")),
            statement_date=_optional_text(data.get("statement_date")),
            period_start=_optional_text(data.get("period_start")),
            period_end=_optional_text(data.get("period_end")),
            due_date=_optional_text(data.get("due_date")),
            currency=str(data.get("currency", "USD")).upper(),
            account_hint=_optional_text(data.get("account_hint")),
            total=Decimal(str(total_value)) if total_value is not None else None,
            items=tuple(LineItem.from_dict(item) for item in raw_items),
            source_name=str(source.get("name", data.get("source_name", "snapshot.json"))),
            source_sha256=str(source.get("sha256", data.get("source_sha256", ""))),
            extractor=str(source.get("extractor", data.get("extractor", "json"))),
            warnings=tuple(str(item) for item in data.get("warnings", [])),
        )


@dataclass(frozen=True)
class Change:
    kind: str
    before: LineItem | None
    after: LineItem | None
    fields_changed: tuple[str, ...]
    delta: Decimal
    annualized_delta: Decimal | None
    match_score: float | None
    severity: str
    impact: str

    @property
    def label(self) -> str:
        if self.after is not None:
            return self.after.label
        if self.before is not None:
            return self.before.label
        return "Unknown item"

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "label": self.label,
            "before": self.before.to_dict() if self.before else None,
            "after": self.after.to_dict() if self.after else None,
            "fields_changed": list(self.fields_changed),
            "delta": decimal_text(self.delta),
            "annualized_delta": decimal_text(self.annualized_delta),
            "match_score": round(self.match_score, 4) if self.match_score is not None else None,
            "severity": self.severity,
            "impact": self.impact,
        }


@dataclass(frozen=True)
class Comparison:
    before: Statement
    after: Statement
    changes: tuple[Change, ...]
    total_delta: Decimal
    monthly_delta: Decimal
    annualized_delta: Decimal
    warnings: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        counts = {
            level: sum(change.severity == level for change in self.changes) for level in _LEVELS
        }
        return {
            "schema_version": SCHEMA_VERSION,
            "before": self.before.to_dict(),
            "after": self.after.to_dict(),
            "summary": {
                "change_count": len(self.changes),
                "severity_counts": counts,
                "total_delta": decimal_text(self.total_delta),
                "monthly_delta": decimal_text(self.monthly_delta),
                "annualized_delta": decimal_text(self.annualized_delta),
            },
            "changes": [change.to_dict() for change in self.changes],
            "warnings": list(self.warnings),
        }


_LEVELS = ("high", "medium", "low")


def _optional_text(value: Any) -> str | None:
    return None if value in (None, "") else str(value)
