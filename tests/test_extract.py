from __future__ import annotations

import json
from decimal import Decimal
from email.message import EmailMessage
from pathlib import Path

import pytest
from reportlab.pdfgen.canvas import Canvas

from billchangelog.extract import (
    CaptureOverrides,
    ExtractionError,
    capture_path,
    parse_date,
)
from billchangelog.profile import load_profile


def test_capture_text_with_evidence(example_before: Path, example_profile: Path) -> None:
    statement = capture_path(example_before, load_profile(example_profile))
    assert statement.provider == "Acme Mobile"
    assert statement.statement_date == "2026-01-15"
    assert statement.period_start == "2025-12-15"
    assert statement.total == Decimal("76.25")
    assert len(statement.items) == 4
    assert statement.items[0].evidence.locator == "line 7"
    assert statement.source_sha256
    assert not statement.warnings


def test_capture_csv(project_root: Path) -> None:
    statement = capture_path(project_root / "examples" / "line-items.csv", load_profile())
    assert statement.provider == "Example Energy"
    assert statement.currency == "USD"
    assert [item.category for item in statement.items] == ["recurring", "usage", "tax"]
    assert statement.items[0].evidence.locator == "row 2"


def test_capture_json_round_trip(example_before: Path, tmp_path: Path) -> None:
    profile = load_profile()
    original = capture_path(example_before, profile)
    snapshot = tmp_path / "snapshot.json"
    snapshot.write_text(json.dumps(original.to_dict()), encoding="utf-8")
    captured = capture_path(snapshot, profile)
    assert captured.items == original.items
    assert captured.extractor == "json"
    assert captured.source_name == "snapshot.json"


def test_capture_eml_html_body(tmp_path: Path) -> None:
    message = EmailMessage()
    message["Subject"] = "Your bill"
    message.set_content(
        "<p>Provider: Email Energy</p><p>Statement date: 2026-04-01</p>"
        "<p>Monthly service | $20.00 | recurring | monthly</p>"
        "<p>Total due | $20.00</p>",
        subtype="html",
    )
    path = tmp_path / "bill.eml"
    path.write_bytes(message.as_bytes())
    statement = capture_path(path, load_profile())
    assert statement.provider == "Email Energy"
    assert len(statement.items) == 1
    assert statement.extractor == "eml"


def test_capture_text_pdf_with_page_locator(tmp_path: Path) -> None:
    path = tmp_path / "bill.pdf"
    canvas = Canvas(str(path))
    for index, line in enumerate(
        [
            "Provider: PDF Fiber",
            "Statement date: 2026-05-01",
            "Fiber plan | $50.00 | recurring | monthly",
            "Total due | $50.00",
        ]
    ):
        canvas.drawString(72, 740 - (index * 20), line)
    canvas.save()
    statement = capture_path(path, load_profile())
    assert statement.provider == "PDF Fiber"
    assert statement.items[0].evidence.locator.startswith("page 1")


def test_scanned_pdf_explains_ocr_requirement(tmp_path: Path) -> None:
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    with path.open("wb") as handle:
        writer.write(handle)
    with pytest.raises(ExtractionError, match="need OCR"):
        capture_path(path, load_profile())


def test_overrides_and_date_validation(example_before: Path) -> None:
    statement = capture_path(
        example_before,
        load_profile(),
        CaptureOverrides(provider="Override Co", statement_date="03/04/2026"),
    )
    assert statement.provider == "Override Co"
    assert statement.statement_date == "2026-03-04"
    assert parse_date("March 4, 2026") == "2026-03-04"
    with pytest.raises(ExtractionError, match="unsupported date"):
        capture_path(
            example_before,
            load_profile(),
            CaptureOverrides(statement_date="tomorrow"),
        )


def test_missing_and_unsupported_inputs(tmp_path: Path) -> None:
    with pytest.raises(ExtractionError, match="does not exist"):
        capture_path(tmp_path / "missing.txt", load_profile())
    path = tmp_path / "bill.xlsx"
    path.write_bytes(b"data")
    with pytest.raises(ExtractionError, match="unsupported input format"):
        capture_path(path, load_profile())
