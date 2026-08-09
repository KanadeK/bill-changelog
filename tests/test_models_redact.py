from __future__ import annotations

from decimal import Decimal

import pytest

from billchangelog.models import Change, Evidence, LineItem, Statement, decimal_text
from billchangelog.redact import redact_account, redact_payload, redact_text


def test_line_item_validation() -> None:
    evidence = Evidence("x", "line 1", "x")
    with pytest.raises(ValueError, match="unsupported category"):
        LineItem("x", "x", Decimal("1"), "bad", "unknown", evidence)
    with pytest.raises(ValueError, match="unsupported cadence"):
        LineItem("x", "x", Decimal("1"), "other", "weekly", evidence)
    with pytest.raises(ValueError, match="confidence"):
        LineItem("x", "x", Decimal("1"), "other", "unknown", evidence, 1.5)


def test_statement_from_dict_fallbacks_and_validation() -> None:
    statement = Statement.from_dict(
        {
            "provider": "Fixture",
            "total": None,
            "line_items": [{"label": "Charge", "amount": "2.00"}],
            "source": "not-an-object",
        }
    )
    assert statement.items[0].evidence.excerpt == "Charge"
    assert statement.source_name == "snapshot.json"
    with pytest.raises(ValueError, match="schema version"):
        Statement.from_dict({"schema_version": 2})
    with pytest.raises(ValueError, match="items must be a list"):
        Statement.from_dict({"items": "bad"})
    assert decimal_text(None) is None


def test_change_label_fallbacks() -> None:
    item = LineItem(
        "Old",
        "old",
        Decimal("1"),
        "other",
        "unknown",
        Evidence("x", "line 1", "Old $1.00"),
    )
    removed = Change(
        "removed", item, None, ("presence",), Decimal("-1"), None, None, "medium", "cost_decrease"
    )
    empty = Change("modified", None, None, (), Decimal("0"), None, None, "low", "neutral")
    assert removed.label == "Old"
    assert empty.label == "Unknown item"


def test_redaction_boundaries() -> None:
    text = "Email alice@example.com phone +1 (415) 555-0199 account 123456789 amount $1234.56"
    redacted = redact_text(text)
    assert "alice@example.com" not in redacted
    assert "0199" in redacted
    assert "••••6789" in redacted
    assert "$1234.56" in redacted
    assert redact_account(None) is None
    assert redact_account("abc") == "[redacted-account]"
    assert redact_account("ACCT-123456") == "••••3456"
    payload = redact_payload([{"sha256": "123456789", "label": "line 123456789"}])
    assert payload == [{"sha256": "123456789", "label": "line ••••6789"}]
