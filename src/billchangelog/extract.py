"""Input extraction with page/line evidence and no network calls."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from datetime import datetime
from email import policy
from email.message import EmailMessage, MIMEPart
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from billchangelog.amounts import ParsedAmount, find_amounts, parse_amount
from billchangelog.models import Evidence, LineItem, Statement
from billchangelog.profile import Profile


class ExtractionError(ValueError):
    """Raised when a source cannot produce a reviewable statement."""


@dataclass(frozen=True)
class CaptureOverrides:
    provider: str | None = None
    statement_date: str | None = None
    due_date: str | None = None
    period_start: str | None = None
    period_end: str | None = None
    account_hint: str | None = None
    currency: str | None = None


@dataclass(frozen=True)
class LocatedLine:
    text: str
    source: str
    locator: str


_DATE_FORMATS = (
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%b %d, %Y",
    "%B %d, %Y",
    "%m/%d/%Y",
    "%d/%m/%Y",
)
_METADATA_PATTERNS = {
    "provider": re.compile(r"^(?:provider|biller|merchant|company)\s*:\s*(.+)$", re.I),
    "statement_date": re.compile(r"^(?:statement|bill|invoice)\s+date\s*:\s*(.+)$", re.I),
    "due_date": re.compile(r"^(?:payment\s+)?due\s+date\s*:\s*(.+)$", re.I),
    "period": re.compile(
        r"^(?:billing|statement)\s+period\s*:\s*(.+?)\s+(?:to|through|[-\u2013\u2014])\s+(.+)$",
        re.I,
    ),
    "account_hint": re.compile(
        r"^(?:account|customer)(?:\s+(?:number|no\.?|id))?\s*:\s*(.+)$", re.I
    ),
}


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def capture_path(
    path: Path,
    profile: Profile,
    overrides: CaptureOverrides | None = None,
) -> Statement:
    """Capture a statement from JSON, CSV, text, EML, or text-based PDF."""
    source = path.resolve()
    if not source.is_file():
        raise ExtractionError(f"input file does not exist: {path}")
    overrides = overrides or CaptureOverrides()
    suffix = source.suffix.casefold()
    if suffix == ".json":
        return _capture_json(source, profile, overrides)
    if suffix == ".csv":
        return _capture_csv(source, profile, overrides)
    if suffix in {".txt", ".md"}:
        lines = _text_lines(source)
        return _capture_lines(source, lines, profile, overrides, "text")
    if suffix == ".eml":
        lines, warnings = _eml_lines(source)
        return _capture_lines(source, lines, profile, overrides, "eml", warnings)
    if suffix == ".pdf":
        lines, warnings = _pdf_lines(source)
        return _capture_lines(source, lines, profile, overrides, "pdf", warnings)
    raise ExtractionError(
        f"unsupported input format '{source.suffix}'; use .txt, .csv, .json, .eml, or .pdf"
    )


def _capture_json(path: Path, profile: Profile, overrides: CaptureOverrides) -> Statement:
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ExtractionError(f"invalid JSON statement: {exc}") from exc
    if not isinstance(data, dict):
        raise ExtractionError("JSON statement root must be an object")
    try:
        statement = Statement.from_dict(data)
    except (KeyError, TypeError, ValueError) as exc:
        raise ExtractionError(f"invalid statement snapshot: {exc}") from exc
    items = tuple(
        replace(
            item,
            normalized_label=profile.normalize(item.label),
            category=item.category
            if item.category != "other"
            else profile.classify(item.label, item.amount),
            cadence=(
                item.cadence
                if item.cadence != "unknown"
                else profile.cadence_for(item.label, profile.classify(item.label, item.amount))
            ),
        )
        for item in statement.items
    )
    result = replace(
        statement,
        items=items,
        source_name=path.name,
        source_sha256=sha256_file(path),
        extractor="json",
    )
    return _apply_overrides(result, overrides)


def _capture_csv(path: Path, profile: Profile, overrides: CaptureOverrides) -> Statement:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ExtractionError("CSV must be UTF-8 encoded") from exc
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ExtractionError("CSV has no header row")
    items: list[LineItem] = []
    metadata: dict[str, str] = {}
    warnings: list[str] = []
    detected_currency = overrides.currency or profile.currency
    for row_number, raw_row in enumerate(reader, start=2):
        row = {str(key).strip().casefold(): (value or "").strip() for key, value in raw_row.items()}
        label = _first(row, "label", "description", "item", "line_item")
        amount_text = _first(row, "amount", "charge", "value", "price")
        if not label and not amount_text:
            continue
        if not label or not amount_text:
            warnings.append(f"row {row_number} skipped: both label and amount are required")
            continue
        try:
            amount, row_currency = parse_amount(
                amount_text,
                _first(row, "currency") or detected_currency,
            )
        except ValueError:
            warnings.append(f"row {row_number} skipped: invalid amount '{amount_text}'")
            continue
        detected_currency = row_currency
        category = _first(row, "category") or profile.classify(label, amount)
        cadence = _first(row, "cadence") or profile.cadence_for(label, category)
        evidence = Evidence(path.name, f"row {row_number}", f"{label} | {amount_text}")
        try:
            items.append(
                LineItem(
                    label=label,
                    normalized_label=profile.normalize(label),
                    amount=amount,
                    category=category,
                    cadence=cadence,
                    evidence=evidence,
                    confidence=1.0,
                )
            )
        except ValueError as exc:
            warnings.append(f"row {row_number} skipped: {exc}")
        for key in (
            "provider",
            "statement_date",
            "period_start",
            "period_end",
            "due_date",
            "account_hint",
            "total",
        ):
            value = _first(row, key)
            if value and key not in metadata:
                metadata[key] = value
    if not items:
        raise ExtractionError("CSV contained no usable line items")
    total = None
    if metadata.get("total"):
        try:
            total, _ = parse_amount(metadata["total"], detected_currency)
        except ValueError:
            warnings.append(f"ignored invalid CSV total '{metadata['total']}'")
    statement = Statement(
        provider=metadata.get("provider", _provider_from_stem(path)),
        statement_date=_date_or_none(metadata.get("statement_date"), warnings, "statement date"),
        period_start=_date_or_none(metadata.get("period_start"), warnings, "period start"),
        period_end=_date_or_none(metadata.get("period_end"), warnings, "period end"),
        due_date=_date_or_none(metadata.get("due_date"), warnings, "due date"),
        currency=detected_currency,
        account_hint=metadata.get("account_hint"),
        total=total,
        items=tuple(items),
        source_name=path.name,
        source_sha256=sha256_file(path),
        extractor="csv",
        warnings=tuple(warnings),
    )
    return _apply_overrides(statement, overrides)


def _capture_lines(
    path: Path,
    lines: list[LocatedLine],
    profile: Profile,
    overrides: CaptureOverrides,
    extractor: str,
    initial_warnings: Iterable[str] = (),
) -> Statement:
    metadata: dict[str, str] = {}
    warnings = list(initial_warnings)
    items: list[LineItem] = []
    total = None
    detected_currency = overrides.currency or profile.currency
    first_heading: str | None = None
    for line in lines:
        text = line.text.strip()
        if not text:
            continue
        if first_heading is None and not find_amounts(text, detected_currency):
            first_heading = text
        matched_metadata = False
        for key in ("provider", "statement_date", "due_date", "account_hint"):
            match = _METADATA_PATTERNS[key].match(text)
            if match:
                metadata[key] = match.group(1).strip()
                matched_metadata = True
                break
        if matched_metadata:
            continue
        period_match = _METADATA_PATTERNS["period"].match(text)
        if period_match:
            metadata["period_start"] = period_match.group(1).strip()
            metadata["period_end"] = period_match.group(2).strip()
            continue
        parsed = _parse_line_item(line, profile, detected_currency)
        if parsed is None:
            continue
        item, amount_match = parsed
        detected_currency = amount_match.currency
        if profile.is_total(item.label):
            total = item.amount
            continue
        if profile.should_ignore(item.label):
            continue
        items.append(item)
    if not items:
        message = "no comparable line items were found"
        if extractor == "pdf":
            message += "; scanned PDFs need OCR before capture"
        raise ExtractionError(message)
    provider = (
        metadata.get("provider") or _clean_heading(first_heading) or _provider_from_stem(path)
    )
    statement_date = _date_or_none(metadata.get("statement_date"), warnings, "statement date")
    due_date = _date_or_none(metadata.get("due_date"), warnings, "due date")
    period_start = _date_or_none(metadata.get("period_start"), warnings, "period start")
    period_end = _date_or_none(metadata.get("period_end"), warnings, "period end")
    if total is not None:
        item_sum = sum((item.amount for item in items), start=type(total)("0"))
        if abs(total - item_sum) > type(total)("0.01"):
            warnings.append(
                f"line items sum to {item_sum:.2f}, which differs from total {total:.2f}; "
                "review excluded balances, payments, or extraction gaps"
            )
    statement = Statement(
        provider=provider,
        statement_date=statement_date,
        period_start=period_start,
        period_end=period_end,
        due_date=due_date,
        currency=detected_currency,
        account_hint=metadata.get("account_hint"),
        total=total,
        items=tuple(items),
        source_name=path.name,
        source_sha256=sha256_file(path),
        extractor=extractor,
        warnings=tuple(warnings),
    )
    return _apply_overrides(statement, overrides)


def _parse_line_item(
    line: LocatedLine,
    profile: Profile,
    default_currency: str,
) -> tuple[LineItem, ParsedAmount] | None:
    text = line.text.strip()
    parts = [part.strip() for part in text.split("|")]
    category_override = ""
    cadence_override = ""
    if len(parts) >= 2:
        label = parts[0].strip("-•* ")
        amount_matches = find_amounts(parts[1], default_currency)
        if not amount_matches:
            try:
                amount, currency = parse_amount(parts[1], default_currency)
                amount_match = ParsedAmount(amount, currency, 0, len(parts[1]), parts[1])
            except ValueError:
                return None
        else:
            amount_match = amount_matches[-1]
        if len(parts) >= 3:
            category_override = parts[2].casefold()
        if len(parts) >= 4:
            cadence_override = parts[3].casefold()
    else:
        amount_matches = find_amounts(text, default_currency)
        if not amount_matches:
            return None
        amount_match = amount_matches[-1]
        label = (text[: amount_match.start] + " " + text[amount_match.end :]).strip()
        label = re.sub(r"^[\s\-•*]+|[\s.:·…_-]+$", "", label)
    if not label or len(label) < 2:
        return None
    category = category_override or profile.classify(label, amount_match.value)
    cadence = cadence_override or profile.cadence_for(label, category)
    confidence = 0.95 if "|" in text else 0.85
    try:
        item = LineItem(
            label=label,
            normalized_label=profile.normalize(label),
            amount=amount_match.value,
            category=category,
            cadence=cadence,
            evidence=Evidence(line.source, line.locator, text),
            confidence=confidence,
        )
    except ValueError:
        return None
    return item, amount_match


def _text_lines(path: Path) -> list[LocatedLine]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        try:
            text = path.read_text(encoding="cp1252")
        except UnicodeDecodeError as exc:
            raise ExtractionError("text input must be UTF-8 or Windows-1252") from exc
    return [
        LocatedLine(value, path.name, f"line {index}")
        for index, value in enumerate(text.splitlines(), 1)
    ]


def _pdf_lines(path: Path) -> tuple[list[LocatedLine], list[str]]:
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover - dependency metadata guarantees normal installs
        raise ExtractionError("PDF support requires pypdf; reinstall bill-changelog") from exc
    try:
        reader = PdfReader(path)
    except Exception as exc:
        raise ExtractionError(f"unable to open PDF: {exc}") from exc
    if reader.is_encrypted:
        try:
            reader.decrypt("")
        except Exception as exc:
            raise ExtractionError("encrypted PDF requires an unencrypted copy") from exc
    lines: list[LocatedLine] = []
    warnings: list[str] = []
    for page_index, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            warnings.append(f"page {page_index} text extraction failed: {exc}")
            continue
        if not text.strip():
            warnings.append(f"page {page_index} has no extractable text")
        for line_index, value in enumerate(text.splitlines(), 1):
            lines.append(LocatedLine(value, path.name, f"page {page_index}, line {line_index}"))
    return lines, warnings


def _eml_lines(path: Path) -> tuple[list[LocatedLine], list[str]]:
    try:
        message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
    except Exception as exc:
        raise ExtractionError(f"unable to parse EML: {exc}") from exc
    blocks: list[tuple[str, str]] = []
    warnings: list[str] = []
    _collect_message_blocks(message, blocks, warnings)
    lines: list[LocatedLine] = []
    for block_name, text in blocks:
        for line_index, value in enumerate(text.splitlines(), 1):
            lines.append(LocatedLine(value, path.name, f"{block_name}, line {line_index}"))
    return lines, warnings


def _collect_message_blocks(
    message: EmailMessage | MIMEPart[Any, Any],
    blocks: list[tuple[str, str]],
    warnings: list[str],
) -> None:
    if message.is_multipart():
        for part in message.iter_parts():
            disposition = part.get_content_disposition()
            content_type = part.get_content_type()
            filename = part.get_filename() or "attachment"
            if disposition == "attachment":
                if content_type == "application/pdf":
                    decoded = part.get_payload(decode=True)
                    payload = decoded if isinstance(decoded, bytes) else b""
                    attachment_lines, attachment_warnings = _pdf_bytes_lines(payload, filename)
                    blocks.extend(attachment_lines)
                    warnings.extend(attachment_warnings)
                else:
                    warnings.append(f"ignored attachment '{filename}' ({content_type})")
                continue
            _collect_message_blocks(part, blocks, warnings)
        return
    content_type = message.get_content_type()
    if content_type == "text/plain":
        blocks.append(("message body", str(message.get_content())))
    elif content_type == "text/html" and not any(name == "message body" for name, _ in blocks):
        parser = _HTMLTextExtractor()
        parser.feed(str(message.get_content()))
        blocks.append(("message body", parser.text()))


def _pdf_bytes_lines(payload: bytes, filename: str) -> tuple[list[tuple[str, str]], list[str]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(io.BytesIO(payload))
    except Exception as exc:
        return [], [f"unable to read PDF attachment '{filename}': {exc}"]
    blocks: list[tuple[str, str]] = []
    warnings: list[str] = []
    for page_index, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if not text.strip():
            warnings.append(
                f"PDF attachment '{filename}' page {page_index} has no extractable text"
            )
        blocks.append((f"attachment {filename}, page {page_index}", text))
    return blocks, warnings


class _HTMLTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"br", "p", "div", "li", "tr"}:
            self._chunks.append("\n")

    def handle_data(self, data: str) -> None:
        self._chunks.append(data)

    def text(self) -> str:
        return "".join(self._chunks)


def parse_date(raw: str) -> str:
    value = raw.strip().rstrip(".")
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"unsupported date '{raw}'")


def _date_or_none(raw: str | None, warnings: list[str], label: str) -> str | None:
    if not raw:
        return None
    try:
        return parse_date(raw)
    except ValueError:
        warnings.append(f"ignored {label}: unsupported date '{raw}'")
        return None


def _apply_overrides(statement: Statement, overrides: CaptureOverrides) -> Statement:
    date_values: dict[str, str | None] = {}
    for name in ("statement_date", "due_date", "period_start", "period_end"):
        raw = getattr(overrides, name)
        if raw is None:
            date_values[name] = getattr(statement, name)
        else:
            try:
                date_values[name] = parse_date(raw)
            except ValueError as exc:
                raise ExtractionError(str(exc)) from exc
    return replace(
        statement,
        provider=overrides.provider or statement.provider,
        account_hint=overrides.account_hint or statement.account_hint,
        currency=(overrides.currency or statement.currency).upper(),
        statement_date=date_values["statement_date"],
        due_date=date_values["due_date"],
        period_start=date_values["period_start"],
        period_end=date_values["period_end"],
    )


def _first(row: dict[str, str], *keys: str) -> str:
    for key in keys:
        value = row.get(key, "")
        if value:
            return value
    return ""


def _provider_from_stem(path: Path) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]", path.stem) if part)


def _clean_heading(value: str | None) -> str | None:
    if value is None or len(value) > 120:
        return None
    cleaned = re.sub(r"\b(?:monthly\s+)?(?:bill|statement|invoice)\b", "", value, flags=re.I)
    cleaned = cleaned.strip(" -\u2013\u2014:|")
    return cleaned or None
