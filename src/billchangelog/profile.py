"""Provider-neutral parsing and comparison profiles."""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from importlib.resources import files
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class Profile:
    name: str = "generic"
    currency: str = "USD"
    match_threshold: float = 0.72
    high_monthly_delta: Decimal = Decimal("10.00")
    high_annual_delta: Decimal = Decimal("120.00")
    aliases: dict[str, str] = field(default_factory=dict)
    category_patterns: dict[str, tuple[str, ...]] = field(default_factory=dict)
    monthly_patterns: tuple[str, ...] = field(default_factory=tuple)
    one_time_patterns: tuple[str, ...] = field(default_factory=tuple)
    ignore_patterns: tuple[str, ...] = field(default_factory=tuple)
    total_patterns: tuple[str, ...] = field(default_factory=tuple)

    def normalize(self, label: str) -> str:
        text = unicodedata.normalize("NFKC", label).casefold()
        text = re.sub(r"\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\b", " ", text)
        text = re.sub(r"\b\d{4}-\d{2}(?:-\d{2})?\b", " ", text)
        text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
        normalized = " ".join(text.split())
        alias_key = self.aliases.get(normalized)
        return alias_key or normalized

    def classify(self, label: str, amount: Decimal) -> str:
        normalized = self.normalize(label)
        ordered = ("discount", "tax", "fee", "usage", "one_time", "recurring", "other")
        for category in ordered:
            if any(
                re.search(pattern, normalized, re.IGNORECASE)
                for pattern in self.category_patterns.get(category, ())
            ):
                return category
        if amount < 0:
            return "discount"
        return "other"

    def cadence_for(self, label: str, category: str) -> str:
        normalized = self.normalize(label)
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in self.one_time_patterns):
            return "one_time"
        if category == "one_time":
            return "one_time"
        if category in {"recurring", "discount"}:
            return "monthly"
        if any(re.search(pattern, normalized, re.IGNORECASE) for pattern in self.monthly_patterns):
            return "monthly"
        return "unknown"

    def should_ignore(self, label: str) -> bool:
        normalized = self.normalize(label)
        return any(
            re.search(pattern, normalized, re.IGNORECASE) for pattern in self.ignore_patterns
        )

    def is_total(self, label: str) -> bool:
        normalized = self.normalize(label)
        return any(re.search(pattern, normalized, re.IGNORECASE) for pattern in self.total_patterns)


def load_profile(path: Path | None = None) -> Profile:
    base_resource = files("billchangelog.data").joinpath("generic-profile.json")
    data = json.loads(base_resource.read_text(encoding="utf-8"))
    if path is not None:
        custom = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(custom, dict):
            raise ValueError("profile root must be a JSON object")
        data = _deep_merge(data, custom)
    return profile_from_dict(data)


def profile_from_dict(data: dict[str, Any]) -> Profile:
    category_data = data.get("category_patterns", {})
    if not isinstance(category_data, dict):
        raise ValueError("category_patterns must be an object")
    aliases = data.get("aliases", {})
    if not isinstance(aliases, dict):
        raise ValueError("aliases must be an object")
    normalized_aliases = {
        _basic_normalize(str(key)): _basic_normalize(str(value)) for key, value in aliases.items()
    }
    threshold = float(data.get("match_threshold", 0.72))
    if not 0 <= threshold <= 1:
        raise ValueError("match_threshold must be between 0 and 1")
    return Profile(
        name=str(data.get("name", "generic")),
        currency=str(data.get("currency", "USD")).upper(),
        match_threshold=threshold,
        high_monthly_delta=Decimal(str(data.get("high_monthly_delta", "10.00"))),
        high_annual_delta=Decimal(str(data.get("high_annual_delta", "120.00"))),
        aliases=normalized_aliases,
        category_patterns={
            str(category): tuple(str(pattern) for pattern in patterns)
            for category, patterns in category_data.items()
        },
        monthly_patterns=tuple(str(item) for item in data.get("monthly_patterns", [])),
        one_time_patterns=tuple(str(item) for item in data.get("one_time_patterns", [])),
        ignore_patterns=tuple(str(item) for item in data.get("ignore_patterns", [])),
        total_patterns=tuple(str(item) for item in data.get("total_patterns", [])),
    )


def _deep_merge(base: dict[str, Any], custom: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in custom.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _basic_normalize(value: str) -> str:
    text = unicodedata.normalize("NFKC", value).casefold()
    return " ".join(re.sub(r"[^\w]+", " ", text, flags=re.UNICODE).split())
