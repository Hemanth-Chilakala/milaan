# Contributing

Use Python 3.12. Install `requirements.lock` in a virtual environment, then run `make lint` and `make test`. Database integration tests require a running Exasol Personal instance and replace the active demonstration tables with a small synthetic fixture:

```bash
.venv/bin/python -m pytest -m db
```

Restore a demonstration dataset with `make load DATA=data/10000000`, then `make recon explain`.

Keep matching and scoring in Exasol. Include rule evidence and meaningful fixture cases for changes to matching logic. Do not commit CSV files, connection credentials, real financial data or private preparation material. Document observed performance without turning a single run into a general claim.
