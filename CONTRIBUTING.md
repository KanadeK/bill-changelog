# Contributing

Thank you for helping make recurring bills easier to inspect.

## Privacy first

Never commit a real bill, account number, address, email, phone number, barcode, QR code, or source
document hash. Create a fictional fixture that preserves only the layout behavior needed by the
test.

## Development

```bash
uv sync --extra dev --locked
uv run python scripts/verify.py
```

For a focused change:

```bash
uv run pytest tests/test_extract.py
uv run ruff check .
uv run mypy src scripts
```

## Provider profiles

Profiles should:

- extend the generic profile instead of copying parser logic;
- use the narrowest regular expressions that work;
- avoid hard-coded current prices or policy claims;
- include fictional before/after fixtures and expected changes;
- document ambiguous labels and cadence assumptions.

## Pull requests

Explain the user problem, the evidence contract affected, tests run, and privacy considerations.
Do not include generated `.venv`, report directories, release assets, or secrets.
