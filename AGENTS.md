# AGENTS.md — Agent Master Guidelines & Knowledge Base

> **Single Source of Truth**: All agent guidelines, architecture rules, database synchronization policies, protocols, and workflows have been consolidated and refined into **[`CLAUDE.md`](./CLAUDE.md)**.
> Please refer directly to [`CLAUDE.md`](./CLAUDE.md) for the authoritative documentation.

---

## Quick Reference Summary

- **Primary Documentation**: Read **[`CLAUDE.md`](./CLAUDE.md)** for complete specifications.
- **Git Commit & Push**: Always commit and push changes to the remote branch upon completing each task.
- **Zero-Error Hygiene**: Check open issues via `python scripts/error_ledger.py open` before starting, and verify with `python scripts/error_ledger.py scan` upon completion.
- **Strict Point-in-Time (PIT)**: In `features/`, `dataset.py`, and `backtest/`, feature computation for an event date $T$ must filter prices strictly up to $T-1$ (`prices.loc[prices.index <= asof_date]`).
- **Temporal Window Association**: Every metric, delta, signal, accumulation flow, momentum score, and forecast must explicitly state its horizon/window.
- **Anti-Fabrication**: Never use synthetic dummy values or mock data in production endpoints.
- **Remote DB Sync**: Any new SQLite table MUST be added to `SYNC_TABLES` in `earnings_engine/data/turso_sync.py`.
- **Targeted Tests**: Favor targeted tests (`pytest tests/<test_file>.py -k "<test_func>"`) over slow full-suite runs.
- **FastAPI Routes**: Always define static/literal routes before parameterized routes.
