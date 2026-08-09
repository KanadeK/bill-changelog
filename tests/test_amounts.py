from decimal import Decimal

import pytest

from billchangelog.amounts import find_amounts, parse_amount, parse_decimal


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1,234.56", Decimal("1234.56")),
        ("1.234,56", Decimal("1234.56")),
        ("12,50", Decimal("12.50")),
        ("1,234", Decimal("1234")),
        ("(10.00)", Decimal("-10.00")),
        ("-0.35", Decimal("-0.35")),
    ],
)
def test_parse_decimal_conventions(raw: str, expected: Decimal) -> None:
    assert parse_decimal(raw) == expected


def test_parse_currency_amounts() -> None:
    assert parse_amount("$1,234.56") == (Decimal("1234.56"), "USD")
    assert parse_amount("1.234,56 EUR") == (Decimal("1234.56"), "EUR")
    assert parse_amount("(€ 10,00)") == (Decimal("-10.00"), "EUR")
    assert parse_amount("¥500.00", "CNY") == (Decimal("500.00"), "CNY")


def test_find_amounts_rejects_dates_and_counters() -> None:
    assert find_amounts("Statement date: 2026-02-15") == []
    matches = find_amounts("Monthly plan ........ $65.00")
    assert len(matches) == 1
    assert matches[0].value == Decimal("65.00")


def test_parse_decimal_rejects_invalid() -> None:
    with pytest.raises(ValueError, match="invalid amount"):
        parse_decimal("not-money")
