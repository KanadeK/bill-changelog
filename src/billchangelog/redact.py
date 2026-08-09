"""Conservative masking for report evidence."""

from __future__ import annotations

import re

_EMAIL_RE = re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d(?:[\s().-]*\d){8,14})(?!\d)")
_LONG_DIGITS_RE = re.compile(r"(?<!\d)(\d{6,})(?!\d)")


def redact_text(value: str) -> str:
    """Mask likely email, phone, card, and account identifiers while preserving amounts/dates."""
    text = _EMAIL_RE.sub("[redacted-email]", value)
    # Mask contiguous account/card-like identifiers before the more permissive
    # phone matcher. This keeps both classes private without mislabelling account
    # numbers, while formatted phone numbers still retain their last four digits.
    text = _LONG_DIGITS_RE.sub(lambda match: _mask_digits(match.group(1)), text)
    return _PHONE_RE.sub(_mask_phone, text)


def redact_account(value: str | None) -> str | None:
    if value is None:
        return None
    digits = "".join(character for character in value if character.isdigit())
    if len(digits) < 4:
        return "[redacted-account]"
    return f"••••{digits[-4:]}"


def redact_payload(value: object, key: str | None = None) -> object:
    """Redact report JSON recursively without corrupting hashes or machine enums."""
    if isinstance(value, dict):
        return {
            str(item_key): redact_payload(item_value, str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [redact_payload(item, key) for item in value]
    if isinstance(value, str):
        if key == "sha256":
            return value
        if key == "account_hint":
            return redact_account(value)
        if key in {"label", "normalized_label", "excerpt", "provider"}:
            return redact_text(value)
    return value


def _mask_phone(match: re.Match[str]) -> str:
    digits = "".join(character for character in match.group(0) if character.isdigit())
    if len(digits) < 9:
        return match.group(0)
    return f"[redacted-phone:{digits[-4:]}]"


def _mask_digits(digits: str) -> str:
    return f"••••{digits[-4:]}"
