# Inputs and profiles

## Text format

Metadata uses `Key: value`; explicit pipe rows are the most reliable:

```text
Provider: Example Fiber
Account number: 0012345678
Statement date: 2026-05-01
Billing period: 2026-04-01 to 2026-04-30
Due date: 2026-05-20

Fiber plan | $50.00 | recurring | monthly
Autopay discount | -$5.00 | discount | monthly
Network fee | $2.00 | fee | monthly
Total due | $47.00
```

Without pipes, the last credible monetary token on a line is treated as its amount. Dates and bare
integer counters are not treated as money.

Categories: `recurring`, `usage`, `fee`, `tax`, `discount`, `one_time`, `other`.

Cadences: `monthly`, `one_time`, `unknown`.

## CSV

Required columns have accepted aliases:

- label: `label`, `description`, `item`, or `line_item`;
- amount: `amount`, `charge`, `value`, or `price`.

Optional columns: `provider`, `statement_date`, `period_start`, `period_end`, `due_date`,
`account_hint`, `total`, `currency`, `category`, `cadence`.

See [examples/line-items.csv](../examples/line-items.csv).

## JSON snapshot

`capture` writes the canonical structure. Amounts are decimal strings:

```json
{
  "schema_version": 1,
  "provider": "Example Fiber",
  "statement_date": "2026-05-01",
  "currency": "USD",
  "total": "47.00",
  "items": [
    {
      "label": "Fiber plan",
      "normalized_label": "fiber plan",
      "amount": "50.00",
      "category": "recurring",
      "cadence": "monthly",
      "confidence": 1.0,
      "evidence": {
        "source": "bill.txt",
        "locator": "line 7",
        "excerpt": "Fiber plan | $50.00 | recurring | monthly"
      }
    }
  ],
  "source": {"name": "bill.txt", "sha256": "...", "extractor": "text"},
  "warnings": []
}
```

## EML

The parser prefers `text/plain`, falls back to text extracted from HTML, and reads attached PDFs.
Non-PDF attachments are listed as warnings. Save one message as RFC 822 `.eml`; no Gmail or mail
provider access is required.

## PDF

PDF text is extracted page by page with pypdf. A page with no embedded text produces a warning. If
no comparable items exist, capture fails with an OCR-specific message. Run OCR in a tool you trust,
save a searchable PDF or text file, then retry.

## Amounts

Supported examples include `$1,234.56`, `1.234,56 EUR`, `£12.50`, `(€ 10,00)`, and `-$5.00`.
Ambiguous `¥` follows the profile/default currency when it is `CNY` or `JPY`.

## Profile JSON

A custom profile deep-merges over the bundled generic profile:

```json
{
  "name": "example-fiber",
  "currency": "USD",
  "match_threshold": 0.72,
  "high_monthly_delta": "10.00",
  "high_annual_delta": "120.00",
  "aliases": {
    "fiber plan plus": "fiber plan"
  },
  "category_patterns": {
    "fee": ["network access", "regulatory recovery"]
  },
  "monthly_patterns": ["per month"],
  "one_time_patterns": ["activation"],
  "ignore_patterns": ["^previous balance$"],
  "total_patterns": ["^total due$"]
}
```

Patterns are Python regular expressions applied to normalized labels. Keep profiles narrow and add
an anonymized regression fixture before contributing one.
