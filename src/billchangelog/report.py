"""Deterministic JSON, CSV, Markdown, and self-contained HTML reports."""

from __future__ import annotations

import csv
import html
import io
import json
from decimal import Decimal
from pathlib import Path

from billchangelog.manifest import build_manifest
from billchangelog.models import Change, Comparison, LineItem, decimal_text
from billchangelog.redact import redact_account, redact_payload, redact_text

ARTIFACT_NAMES = ("report.json", "changes.csv", "support.md", "report.html", "manifest.json")


def write_report_bundle(
    comparison: Comparison,
    output_dir: Path,
    *,
    include_sensitive_evidence: bool = False,
    force: bool = False,
) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    existing = [output_dir / name for name in ARTIFACT_NAMES if (output_dir / name).exists()]
    if existing and not force:
        names = ", ".join(path.name for path in existing)
        raise FileExistsError(
            f"report artifacts already exist ({names}); pass --force to replace them"
        )
    payload: object = comparison.to_dict()
    if not include_sensitive_evidence:
        payload = redact_payload(payload)
    assert isinstance(payload, dict)
    report_json = output_dir / "report.json"
    report_json.write_text(_json_text(payload), encoding="utf-8", newline="\n")

    changes_csv = output_dir / "changes.csv"
    changes_csv.write_text(
        _csv_text(comparison, include_sensitive_evidence), encoding="utf-8", newline="\n"
    )
    support_md = output_dir / "support.md"
    support_md.write_text(
        _support_markdown(comparison, include_sensitive_evidence),
        encoding="utf-8",
        newline="\n",
    )
    report_html = output_dir / "report.html"
    report_html.write_text(
        _html_report(comparison, include_sensitive_evidence),
        encoding="utf-8",
        newline="\n",
    )
    artifacts = [report_json, changes_csv, support_md, report_html]
    manifest = build_manifest(output_dir, artifacts, comparison)
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(_json_text(manifest), encoding="utf-8", newline="\n")
    return [*artifacts, manifest_path]


def _json_text(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def _csv_text(comparison: Comparison, sensitive: bool) -> str:
    buffer = io.StringIO(newline="")
    fieldnames = [
        "severity",
        "kind",
        "label",
        "category",
        "cadence",
        "before_amount",
        "after_amount",
        "delta",
        "annualized_delta",
        "before_evidence",
        "after_evidence",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames, lineterminator="\n")
    writer.writeheader()
    for change in comparison.changes:
        label = change.label if sensitive else redact_text(change.label)
        writer.writerow(
            {
                "severity": change.severity,
                "kind": change.kind,
                "label": label,
                "category": _category(change),
                "cadence": _cadence(change),
                "before_amount": decimal_text(change.before.amount) if change.before else "",
                "after_amount": decimal_text(change.after.amount) if change.after else "",
                "delta": decimal_text(change.delta),
                "annualized_delta": decimal_text(change.annualized_delta) or "",
                "before_evidence": _evidence_cell(change.before, sensitive),
                "after_evidence": _evidence_cell(change.after, sensitive),
            }
        )
    return buffer.getvalue()


def _support_markdown(comparison: Comparison, sensitive: bool) -> str:
    currency = comparison.after.currency
    before_account = comparison.before.account_hint
    after_account = comparison.after.account_hint
    if not sensitive:
        before_account = redact_account(before_account)
        after_account = redact_account(after_account)
    lines = [
        "# Bill change evidence pack",
        "",
        "> Generated locally. This is a factual review aid, not a finding of fraud or legal advice.",
        "",
        "## Statements compared",
        "",
        f"- Before: {comparison.before.source_name} — SHA-256 `{comparison.before.source_sha256}`",
        f"- After: {comparison.after.source_name} — SHA-256 `{comparison.after.source_sha256}`",
        f"- Provider: {_display(comparison.after.provider, sensitive)}",
        f"- Account hint: {after_account or before_account or 'not captured'}",
        f"- Statement dates: {comparison.before.statement_date or 'unknown'} → {comparison.after.statement_date or 'unknown'}",
        "",
        "## Summary",
        "",
        f"- Total change: {_money(comparison.total_delta, currency, signed=True)}",
        f"- Detected monthly change: {_money(comparison.monthly_delta, currency, signed=True)}",
        f"- Annualized monthly impact: {_money(comparison.annualized_delta, currency, signed=True)}",
        f"- Review items: {len(comparison.changes)}",
        "",
        "## Detected changes",
        "",
    ]
    if not comparison.changes:
        lines.append("No line-item changes were detected.")
    for index, change in enumerate(comparison.changes, 1):
        label = _display(change.label, sensitive)
        lines.extend(
            [
                f"### {index}. [{change.severity.upper()}] {label}",
                "",
                f"- Change: {change.kind}; fields: {', '.join(change.fields_changed)}",
                f"- Before: {_item_amount(change.before, currency)}",
                f"- After: {_item_amount(change.after, currency)}",
                f"- Delta: {_money(change.delta, currency, signed=True)}",
                f"- Annualized: {_money(change.annualized_delta, currency, signed=True) if change.annualized_delta is not None else 'not inferred'}",
                f"- Before evidence: {_evidence_markdown(change.before, sensitive)}",
                f"- After evidence: {_evidence_markdown(change.after, sensitive)}",
                "",
                _suggested_question(change, currency),
                "",
            ]
        )
    if comparison.warnings:
        lines.extend(["## Review warnings", ""])
        lines.extend(f"- {warning}" for warning in comparison.warnings)
        lines.append("")
    lines.extend(
        [
            "## Before contacting the provider",
            "",
            "1. Open both source statements and verify each cited page or line.",
            "2. Check whether a plan, usage level, tax jurisdiction, or promotional term changed.",
            "3. Ask the provider to identify the authorization or notice for each unexplained change.",
            "4. Keep the original statements and this bundle together; run `billchangelog verify` before reuse.",
            "",
        ]
    )
    return "\n".join(lines)


def _html_report(comparison: Comparison, sensitive: bool) -> str:
    currency = comparison.after.currency
    cards = "\n".join(_html_change(change, currency, sensitive) for change in comparison.changes)
    if not cards:
        cards = '<section class="empty">No line-item changes were detected.</section>'
    warning_html = "".join(f"<li>{html.escape(warning)}</li>" for warning in comparison.warnings)
    warning_section = (
        f'<section class="warnings"><h2>Review warnings</h2><ul>{warning_html}</ul></section>'
        if warning_html
        else ""
    )
    provider = html.escape(_display(comparison.after.provider, sensitive))
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Bill Changelog — {provider}</title>
  <style>
    :root {{ color-scheme: light; --ink:#17221c; --muted:#607067; --paper:#f4f1e8; --card:#fffdf7; --line:#d8d2c2; --high:#9d2e25; --medium:#9a6500; --good:#1d7350; }}
    * {{ box-sizing:border-box; }} body {{ margin:0; background:var(--paper); color:var(--ink); font:16px/1.55 ui-monospace,SFMono-Regular,Consolas,monospace; }}
    main {{ width:min(1040px,calc(100% - 32px)); margin:40px auto 72px; }}
    header {{ border:1px solid var(--line); background:var(--card); padding:28px; box-shadow:8px 8px 0 #d8d2c2; }}
    h1,h2,h3,p {{ margin-top:0; }} h1 {{ font-size:clamp(2rem,6vw,4.2rem); line-height:.95; letter-spacing:-.06em; margin-bottom:18px; }}
    .eyebrow {{ color:var(--muted); text-transform:uppercase; letter-spacing:.12em; font-size:.78rem; }}
    .summary {{ display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin:24px 0; }}
    .metric,.change,.warnings,.empty {{ background:var(--card); border:1px solid var(--line); padding:18px; }}
    .metric b {{ display:block; font-size:1.5rem; }} .metric span,.meta {{ color:var(--muted); font-size:.84rem; }}
    .change {{ margin:14px 0; border-left:7px solid var(--medium); }} .change.high {{ border-left-color:var(--high); }} .change.low {{ border-left-color:var(--good); }}
    .pill {{ display:inline-block; border:1px solid currentColor; border-radius:99px; padding:2px 8px; font-size:.74rem; text-transform:uppercase; }}
    .amounts {{ display:grid; grid-template-columns:1fr auto 1fr; gap:12px; align-items:center; margin:14px 0; }} .amounts strong:last-child {{ text-align:right; }}
    code {{ overflow-wrap:anywhere; }} details {{ margin-top:10px; }} .warnings {{ margin-top:24px; }} footer {{ color:var(--muted); margin-top:28px; font-size:.82rem; }}
    @media (max-width:700px) {{ .summary {{ grid-template-columns:1fr; }} .amounts {{ grid-template-columns:1fr; }} .amounts strong:last-child {{ text-align:left; }} }}
    @media print {{ body {{ background:white; }} main {{ width:100%; margin:0; }} header {{ box-shadow:none; }} }}
  </style>
</head>
<body><main>
  <header>
    <div class="eyebrow">Local evidence report · {html.escape(comparison.before.statement_date or "unknown")} → {html.escape(comparison.after.statement_date or "unknown")}</div>
    <h1>Bill<br>Changelog</h1>
    <p>{provider} · {len(comparison.changes)} review item(s)</p>
  </header>
  <section class="summary">
    <div class="metric"><span>Total change</span><b>{html.escape(_money(comparison.total_delta, currency, True))}</b></div>
    <div class="metric"><span>Monthly change</span><b>{html.escape(_money(comparison.monthly_delta, currency, True))}</b></div>
    <div class="metric"><span>Annualized</span><b>{html.escape(_money(comparison.annualized_delta, currency, True))}</b></div>
  </section>
  {cards}
  {warning_section}
  <footer>Generated locally. Verify cited evidence in the original statements. This report does not determine authorization, fraud, or legal liability.</footer>
</main></body></html>
"""


def _html_change(change: Change, currency: str, sensitive: bool) -> str:
    label = html.escape(_display(change.label, sensitive))
    before = html.escape(_item_amount(change.before, currency))
    after = html.escape(_item_amount(change.after, currency))
    delta = html.escape(_money(change.delta, currency, True))
    evidence = "".join(
        block
        for block in (
            _html_evidence("Before evidence", change.before, sensitive),
            _html_evidence("After evidence", change.after, sensitive),
        )
        if block
    )
    return f"""<article class="change {change.severity}">
  <span class="pill">{html.escape(change.severity)}</span>
  <h3>{label}</h3>
  <div class="meta">{html.escape(change.kind)} · {html.escape(", ".join(change.fields_changed))} · delta {delta}</div>
  <div class="amounts"><strong>{before}</strong><span>→</span><strong>{after}</strong></div>
  {evidence}
</article>"""


def _html_evidence(title: str, item: LineItem | None, sensitive: bool) -> str:
    if item is None:
        return ""
    excerpt = _display(item.evidence.excerpt, sensitive)
    return (
        f"<details><summary>{html.escape(title)} — {html.escape(item.evidence.locator)}</summary>"
        f"<code>{html.escape(excerpt)}</code></details>"
    )


def _display(value: str, sensitive: bool) -> str:
    return value if sensitive else redact_text(value)


def _item_amount(item: LineItem | None, currency: str) -> str:
    return "not present" if item is None else _money(item.amount, currency)


def _money(value: Decimal | None, currency: str, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{currency} {value:.2f}"


def _category(change: Change) -> str:
    item = change.after or change.before
    return item.category if item else "other"


def _cadence(change: Change) -> str:
    item = change.after or change.before
    return item.cadence if item else "unknown"


def _evidence_cell(item: LineItem | None, sensitive: bool) -> str:
    if item is None:
        return ""
    excerpt = _display(item.evidence.excerpt, sensitive)
    return f"{item.evidence.source} {item.evidence.locator}: {excerpt}"


def _evidence_markdown(item: LineItem | None, sensitive: bool) -> str:
    if item is None:
        return "not present"
    excerpt = _display(item.evidence.excerpt, sensitive).replace("`", "'")
    return f"`{item.evidence.source} {item.evidence.locator}` — `{excerpt}`"


def _suggested_question(change: Change, currency: str) -> str:
    label = change.label.replace("`", "'")
    if change.kind == "added":
        return f"> Suggested question: What authorized the new `{label}` charge of {_item_amount(change.after, currency)}?"
    if change.kind == "removed" and change.before and change.before.category == "discount":
        return f"> Suggested question: Why did the `{label}` discount disappear, and when was its end disclosed?"
    if "amount" in change.fields_changed:
        return f"> Suggested question: Why did `{label}` change by {_money(change.delta, currency, True)}?"
    return f"> Suggested question: Please explain the change to `{label}` and identify any related notice."
