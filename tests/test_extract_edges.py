from __future__ import annotations

import io
import json
from email.message import EmailMessage
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from billchangelog.extract import CaptureOverrides, ExtractionError, capture_path
from billchangelog.profile import load_profile


def test_invalid_json_variants(tmp_path: Path) -> None:
    profile = load_profile()
    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    with pytest.raises(ExtractionError, match="invalid JSON"):
        capture_path(invalid, profile)

    root_list = tmp_path / "list.json"
    root_list.write_text("[]", encoding="utf-8")
    with pytest.raises(ExtractionError, match="root must be an object"):
        capture_path(root_list, profile)

    wrong_version = tmp_path / "version.json"
    wrong_version.write_text('{"schema_version": 99, "items": []}', encoding="utf-8")
    with pytest.raises(ExtractionError, match="unsupported statement schema"):
        capture_path(wrong_version, profile)

    wrong_items = tmp_path / "items.json"
    wrong_items.write_text('{"items": {}}', encoding="utf-8")
    with pytest.raises(ExtractionError, match="items must be a list"):
        capture_path(wrong_items, profile)


def test_csv_warnings_and_failures(tmp_path: Path) -> None:
    profile = load_profile()
    empty = tmp_path / "empty.csv"
    empty.write_text("", encoding="utf-8")
    with pytest.raises(ExtractionError, match="no header"):
        capture_path(empty, profile)

    mixed = tmp_path / "mixed.csv"
    mixed.write_text(
        "label,amount,total,statement_date,category,cadence\n"
        "Missing amount,,nope,not-a-date,,\n"
        "Broken amount,nope,nope,not-a-date,,\n"
        "Service,$12.00,nope,not-a-date,unsupported,monthly\n"
        "Monthly plan,$20.00,nope,not-a-date,recurring,monthly\n",
        encoding="utf-8",
    )
    statement = capture_path(mixed, profile)
    assert len(statement.items) == 1
    assert any("both label and amount" in warning for warning in statement.warnings)
    assert any("invalid amount" in warning for warning in statement.warnings)
    assert any("unsupported category" in warning for warning in statement.warnings)
    assert any("unsupported date" in warning for warning in statement.warnings)
    assert any("invalid CSV total" in warning for warning in statement.warnings)

    unusable = tmp_path / "unusable.csv"
    unusable.write_text("label,amount\nOnly,nope\n", encoding="utf-8")
    with pytest.raises(ExtractionError, match="no usable line items"):
        capture_path(unusable, profile)


def test_freeform_text_cp1252_heading_and_warnings(tmp_path: Path) -> None:
    path = tmp_path / "fiber.txt"
    path.write_bytes(
        "Café Fiber Monthly Statement\r\n"
        "Statement date: someday\r\n"
        "Core monthly plan ........ $20.00\r\n"
        "Unexplained total | $25.00\r\n"
        "Total due | $30.00\r\n".encode("cp1252")
    )
    statement = capture_path(path, load_profile())
    assert statement.provider == "Café Fiber"
    assert statement.items[0].label == "Core monthly plan"
    assert any("unsupported date" in warning for warning in statement.warnings)
    assert any("differs from total" in warning for warning in statement.warnings)


def test_plain_eml_ignored_attachment_and_pdf_attachment(tmp_path: Path) -> None:
    profile = load_profile()
    ignored = EmailMessage()
    ignored.set_content(
        "Provider: Mail Fiber\nStatement date: 2026-06-01\n"
        "Monthly plan | $42.00 | recurring | monthly\nTotal due | $42.00\n"
    )
    ignored.add_attachment(
        b"not parsed", maintype="application", subtype="octet-stream", filename="raw.bin"
    )
    ignored_path = tmp_path / "ignored.eml"
    ignored_path.write_bytes(ignored.as_bytes())
    ignored_statement = capture_path(ignored_path, profile)
    assert any("ignored attachment" in warning for warning in ignored_statement.warnings)

    pdf_bytes = io.BytesIO()
    canvas = Canvas(pdf_bytes)
    canvas.drawString(72, 740, "Provider: Attached Energy")
    canvas.drawString(72, 720, "Statement date: 2026-07-01")
    canvas.drawString(72, 700, "Monthly service | $30.00 | recurring | monthly")
    canvas.drawString(72, 680, "Total due | $30.00")
    canvas.save()
    attached = EmailMessage()
    attached.set_content("Your statement is attached.")
    attached.add_attachment(
        pdf_bytes.getvalue(), maintype="application", subtype="pdf", filename="statement.pdf"
    )
    attached_path = tmp_path / "attached.eml"
    attached_path.write_bytes(attached.as_bytes())
    statement = capture_path(attached_path, profile)
    assert statement.provider == "Attached Energy"
    assert "attachment statement.pdf" in statement.items[0].evidence.locator


def test_pdf_with_blank_page_keeps_warning(tmp_path: Path) -> None:
    path = tmp_path / "two-pages.pdf"
    canvas = Canvas(str(path))
    canvas.drawString(72, 740, "Provider: Page Energy")
    canvas.drawString(72, 720, "Monthly plan | $10.00 | recurring | monthly")
    canvas.drawString(72, 700, "Total due | $10.00")
    canvas.showPage()
    canvas.showPage()
    canvas.save()
    statement = capture_path(path, load_profile())
    assert len(statement.items) == 1
    assert any("has no extractable text" in warning for warning in statement.warnings)


def test_json_overrides_currency_and_metadata(tmp_path: Path) -> None:
    source = tmp_path / "statement.json"
    source.write_text(
        json.dumps(
            {
                "provider": "Original",
                "currency": "USD",
                "items": [{"label": "Unknown credit", "amount": "-2.00"}],
                "source": "malformed-source",
            }
        ),
        encoding="utf-8",
    )
    statement = capture_path(
        source,
        load_profile(),
        CaptureOverrides(
            provider="Override",
            currency="EUR",
            due_date="2026/08/20",
            period_start="2026-07-01",
            period_end="2026-07-31",
            account_hint="ABC-1234",
        ),
    )
    assert statement.provider == "Override"
    assert statement.currency == "EUR"
    assert statement.items[0].category == "discount"
    assert statement.due_date == "2026-08-20"
    assert statement.account_hint == "ABC-1234"
