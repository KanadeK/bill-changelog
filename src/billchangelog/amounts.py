"""Locale-tolerant money parsing without floating-point arithmetic."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

_CURRENCY_MAP = {
    "$": "USD",
    "USD": "USD",
    "US$": "USD",
    "€": "EUR",
    "EUR": "EUR",
    "£": "GBP",
    "GBP": "GBP",
    "JPY": "JPY",
    "CNY": "CNY",
    "RMB": "CNY",
    "¥": "JPY",
    "￥": "CNY",
}
_TOKEN_RE = re.compile(
    r"(?P<open>\()?\s*(?P<sign>[+-])?\s*"
    r"(?P<prefix>US\$|USD|EUR|GBP|JPY|CNY|RMB|[$€£¥￥])?\s*"
    r"(?P<number>\d(?:[\d\s,.']*\d)?)\s*"
    r"(?P<suffix>USD|EUR|GBP|JPY|CNY|RMB)?\s*(?P<close>\))?",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ParsedAmount:
    value: Decimal
    currency: str
    start: int
    end: int
    token: str


def parse_decimal(raw: str) -> Decimal:
    """Parse common decimal and thousands separator conventions."""
    text = raw.strip().replace(" ", "").replace("'", "")
    if not text:
        raise ValueError("empty amount")
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    text = text.strip("()+-")
    if "," in text and "." in text:
        decimal_sep = "," if text.rfind(",") > text.rfind(".") else "."
        thousands_sep = "." if decimal_sep == "," else ","
        text = text.replace(thousands_sep, "").replace(decimal_sep, ".")
    elif "," in text:
        tail = text.rsplit(",", 1)[1]
        text = text.replace(",", ".") if len(tail) in {1, 2} else text.replace(",", "")
    elif "." in text:
        tail = text.rsplit(".", 1)[1]
        if len(tail) == 3 and text.count(".") >= 1:
            text = text.replace(".", "")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise ValueError(f"invalid amount: {raw}") from exc
    return -value if negative else value


def find_amounts(line: str, default_currency: str = "USD") -> list[ParsedAmount]:
    """Return credible money tokens, rejecting bare dates and counters."""
    results: list[ParsedAmount] = []
    for match in _TOKEN_RE.finditer(line):
        number = match.group("number")
        prefix = (match.group("prefix") or "").upper()
        suffix = (match.group("suffix") or "").upper()
        has_currency = bool(prefix or suffix)
        has_decimal_cents = bool(re.search(r"[.,]\d{2}$", number.strip()))
        has_parentheses = bool(match.group("open") and match.group("close"))
        if not (has_currency or has_decimal_cents or has_parentheses):
            continue
        token = match.group(0).strip()
        try:
            value = parse_decimal(token_without_currency(token))
        except ValueError:
            continue
        if match.group("sign") == "-" and value > 0:
            value = -value
        if has_parentheses and value > 0:
            value = -value
        currency_token = prefix or suffix
        currency = _CURRENCY_MAP.get(currency_token, default_currency.upper())
        if currency_token in {"¥", "￥"} and default_currency.upper() in {"CNY", "JPY"}:
            currency = default_currency.upper()
        results.append(ParsedAmount(value, currency, match.start(), match.end(), token))
    return results


def parse_amount(raw: str, default_currency: str = "USD") -> tuple[Decimal, str]:
    """Parse one amount field, including bare numeric CSV/JSON values."""
    matches = find_amounts(raw, default_currency)
    if matches:
        match = matches[-1]
        return match.value, match.currency
    return parse_decimal(raw), default_currency.upper()


def token_without_currency(token: str) -> str:
    cleaned = token
    for currency in sorted(_CURRENCY_MAP, key=len, reverse=True):
        cleaned = re.sub(re.escape(currency), "", cleaned, flags=re.IGNORECASE)
    return cleaned.strip()
