# 13 — Configuration & Environment

> Related: [09-cli-config](09-cli-config.md) → [14-modification-points](14-modification-points.md)

## `.env` variables (optional):
- `EARNINGS_ENGINE_EMAIL_ENABLED` — "true"/"false"
- `EARNINGS_ENGINE_SMTP_HOST`
- `EARNINGS_ENGINE_SMTP_PORT` — default 587
- `EARNINGS_ENGINE_SMTP_USERNAME`
- `EARNINGS_ENGINE_SMTP_PASSWORD`
- `EARNINGS_ENGINE_EMAIL_FROM`
- `EARNINGS_ENGINE_EMAIL_TO` — comma/semicolon-separated

## Data directories (created automatically):
- `data/cache/prices/` — SQLite databases
- `data/cache/earnings/` — Parquet files
- `data/cache/dataset.parquet` — built event dataset
- `reports/output/` — generated CSV/HTML
- `logs/` — per-run log files