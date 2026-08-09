# Bill Changelog v0.1.0

The first public release turns two recurring bill statements into an evidence-linked changelog.

Highlights:

- entirely local TXT/CSV/JSON/EML/text-PDF processing;
- new-charge, removed-discount, price, rename, tax, usage, and cadence changes;
- monthly and annualized impact with explicit warnings;
- redacted HTML/JSON/CSV/Markdown evidence bundles and integrity verification;
- wheel, source distribution, portable `.pyz`, fictional demo bundle, and SHA-256 checksums.

Quick start after downloading the portable archive:

```bash
python billchangelog-0.1.0.pyz demo --output demo-report
python billchangelog-0.1.0.pyz verify demo-report
```

See `SHA256SUMS` before running a downloaded asset.
