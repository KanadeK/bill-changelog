# Architecture

Bill Changelog separates extraction, normalization, matching, evidence rendering, and integrity
verification so a provider profile can change without rewriting the core.

```text
TXT / CSV / JSON / EML / PDF
             │
             ▼
       deterministic capture
  metadata + LineItem + Evidence
             │
             ▼
 profile normalization / aliases
             │
             ▼
 exact then scored one-to-one match
             │
             ▼
 Change objects + monthly impact
             │
             ├── report.json
             ├── changes.csv
             ├── support.md
             ├── report.html
             └── manifest.json
```

## Modules

- `extract.py`: format dispatch, metadata parsing, text/PDF/EML evidence locators, canonical capture.
- `amounts.py`: `Decimal` parsing for common thousands/decimal separators and currency markers.
- `profile.py`: category patterns, aliases, ignore/total patterns, match/severity thresholds.
- `diff.py`: deterministic candidate scoring, one-to-one matching, change and impact calculation.
- `redact.py`: default report masking for likely identifiers.
- `report.py`: stable JSON/CSV/Markdown/HTML serialization with HTML escaping.
- `manifest.py`: SHA-256 and size verification with path-traversal rejection.
- `cli.py`: argument validation, overwrite policy, exit-code contract.

## Matching contract

1. Labels are Unicode NFKC-normalized, case-folded, stripped of date noise, and tokenized.
2. Profile aliases map provider renames to one canonical label.
3. Exact canonical labels score `1.0`.
4. Other candidates combine sequence similarity and token Jaccard similarity, with a small category
   agreement bonus.
5. Candidates are sorted deterministically, then greedily selected one-to-one.
6. Near-threshold matches are surfaced as warnings; they are never hidden.

The amount is only a tie-breaker, not the principal identity signal. That prevents a new fee with
the same price as an old fee from being matched solely because the numbers happen to agree.

## Determinism

- Money uses `Decimal`, never binary floats.
- JSON keys, changes, CSV rows, files, and archive entries use stable ordering.
- Reports contain no wall-clock generation timestamp.
- ZIP timestamps and permissions are fixed.
- Python build subprocesses receive a fixed `SOURCE_DATE_EPOCH`.
- `scripts/verify.py` builds twice after a 2.1-second separation and compares every asset byte hash.

## Trust boundary

Input documents are untrusted. The tool reads them locally, treats extracted text as data, escapes
HTML, and never executes embedded content. A generated report is evidence navigation, not a claim
that extraction or authorization is correct. The human review loop is intentional.
