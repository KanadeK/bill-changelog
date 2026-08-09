# Security and privacy model

## Data flow

Bill Changelog reads local paths and writes only the output path named by the user. Runtime modules
do not import an HTTP client or call a remote service. CI and development dependency tools may use
the network to install packages or query vulnerability advisories; that is separate from statement
processing.

## Sensitive content

Captured JSON retains evidence needed for accurate matching and should be protected like the source
bill. Generated reports mask likely account, phone, card, and email identifiers by default. This is
best-effort masking, not a formal de-identification guarantee. Inspect a report before sharing it.

Use `--include-sensitive-evidence` only when the destination and access controls are understood.

## Untrusted documents

- HTML email is converted to text; scripts are not executed.
- Extracted statement labels are HTML-escaped in reports.
- PDF JavaScript, links, and attachments are not executed.
- Manifest verification rejects artifact paths that escape the bundle directory.
- Existing reports are not overwritten without `--force`.

## Integrity, not authenticity

SHA-256 manifests detect changes after generation. They do not prove who created a bill or that a
source was authentic. Preserve originals and obtain statements from a trusted provider channel.

## Reporting vulnerabilities

Follow [SECURITY.md](../SECURITY.md). Do not attach real bills, account numbers, or credentials to a
public issue.
