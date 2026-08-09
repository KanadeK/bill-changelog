# Failure repair playbook

Start with the diagnostic and the full local gate:

```bash
uv run billchangelog doctor
uv run python scripts/verify.py
```

Fix the first failing section, then rerun that section and the full gate.

## `no comparable line items were found`

1. Open the input and confirm it contains text, not only an image.
2. For a text file, rewrite one line as `Label | $12.34 | category | cadence`.
3. Capture and inspect the intermediate JSON:

   ```bash
   uv run billchangelog capture bill.txt --output bill.json
   ```

4. If a harmless balance/payment row is included, add a narrow `ignore_patterns` regex to a custom
   profile and add a fixture test.

## `scanned PDFs need OCR before capture`

The PDF has no usable embedded text. OCR it locally with a trusted application, save a searchable
PDF or UTF-8 text export, then retry. Bill Changelog intentionally has no cloud OCR fallback.

## Wrong item match or duplicate add/remove pair

1. Read the warning and cited excerpts.
2. Add a canonical alias to a profile:

   ```json
   {"aliases": {"new provider label": "old provider label"}}
   ```

3. If labels are genuinely unrelated, raise `match_threshold`; if a legitimate rename remains
   unmatched, lower it only for that profile.
4. Add the before/after labels to a regression test before keeping the threshold change.

## Currency mismatch

Bill Changelog never invents an exchange rate. Export both statements in one currency or convert
outside the tool with a documented rate, then capture both with `--currency USD` (or another ISO
code).

## Report already exists

Choose another output directory or explicitly replace only Bill Changelog's known artifacts:

```bash
uv run billchangelog compare old.txt new.txt --output report --force
```

## `billchangelog verify` hash mismatch

Do not trust the edited bundle as the original output. Regenerate it from preserved source bills.
If editing was intentional, keep the edited copy separately and regenerate a fresh verified bundle
for evidence.

## Test temp-directory permission error on Windows

The repository pins pytest's base temp directory to `.pytest-tmp`, avoiding a damaged system pytest
temp directory. Run tests from the repository root:

```powershell
uv run pytest
```

Do not delete or take ownership of broad system temp directories to fix this project.

## Dependency install or lock failure

```bash
uv cache clean bill-changelog
uv sync --extra dev --locked
```

If `--locked` reports that the lock is stale after an intentional dependency edit:

```bash
uv lock
uv sync --extra dev --locked
```

Review the `uv.lock` diff; do not use force or legacy peer-dependency bypasses.

## Dependency audit finding

```bash
uv run python -m pip_audit --skip-editable
```

Upgrade the smallest direct dependency that resolves the advisory, regenerate `uv.lock`, run the
entire gate, and document the change. Do not suppress an advisory merely to make CI green.

## Non-deterministic release artifacts

Run twice into separate directories and compare:

```bash
uv run python scripts/package_release.py --output build-a
uv run python scripts/package_release.py --output build-b
```

Inspect ZIP member timestamps and generated report content. Release code fixes timestamps,
ordering, permissions, `SOURCE_DATE_EPOCH`, and omits wall-clock report fields. Any new generator
must follow the same rules.

## CI failure

1. Open the first failed job and reproduce its exact command locally.
2. For OS-only failures, run the named matrix Python version and avoid path/string assumptions.
3. Push a fix only after `uv run python scripts/verify.py` is green.
4. Wait for CI and CodeQL on the exact pushed commit; a local pass is not remote proof.

## Release checksum mismatch

Download `SHA256SUMS` and the asset again. Compute locally:

```powershell
Get-FileHash .\billchangelog-0.1.0.pyz -Algorithm SHA256
```

If it still differs, do not run the asset. Report the release URL, asset name, expected hash, and
actual hash without attaching a real statement.

## Dirty Git state before release

Inspect, do not discard:

```bash
git status --short
git diff --stat
uv run python scripts/release_check.py --json --strict
```

Commit intended files explicitly. Never use a destructive reset to make the release check pass.
