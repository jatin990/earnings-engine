"""CSV + HTML report rendering for predictions and backtests.

Output goes to reports/output/ (gitignored). Plain stdlib string templating —
the report is a single self-contained HTML file.
"""

from datetime import datetime
from pathlib import Path

import pandas as pd

from earnings_engine.config import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "reports" / "output"

_PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
 body {{ font-family: -apple-system, Helvetica, Arial, sans-serif; margin: 2rem; color: #1a1a2e; }}
 h1 {{ font-size: 1.4rem; }} .meta {{ color: #666; font-size: .85rem; margin-bottom: 1rem; }}
 table {{ border-collapse: collapse; width: 100%; font-size: .9rem; }}
 th, td {{ padding: .45rem .7rem; border-bottom: 1px solid #e3e3ee; text-align: right; }}
 th {{ background: #f4f4fb; text-transform: uppercase; font-size: .72rem; letter-spacing: .04em; }}
 td:first-child, th:first-child {{ text-align: left; }}
 .up {{ color: #0a7a3d; font-weight: 600; }} .down {{ color: #b3261e; font-weight: 600; }}
 .note {{ margin-top: 1.2rem; color: #666; font-size: .8rem; }}
</style></head><body>
<h1>{title}</h1>
<div class="meta">Generated {generated} · {subtitle}</div>
{table}
<div class="note">{note}</div>
</body></html>
"""


def _style_direction(val: str) -> str:
    cls = "up" if val == "UP" else "down"
    return f'<span class="{cls}">{val}</span>'


def render_predictions(preds: pd.DataFrame, name: str = "predictions") -> tuple[Path, Path]:
    """Write CSV + HTML for a predictions frame. Returns (csv_path, html_path)."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d")
    csv_path = OUTPUT_DIR / f"{name}-{stamp}.csv"
    html_path = OUTPUT_DIR / f"{name}-{stamp}.html"

    preds.to_csv(csv_path, index=False)

    show = preds.copy()
    show["earnings_date"] = show["earnings_date"].dt.date
    show["asof_date"] = show["asof_date"].dt.date
    show["p_up"] = show["p_up"].map("{:.1%}".format)
    show["confidence"] = show["confidence"].map("{:.1%}".format)
    show["direction"] = show["direction"].map(_style_direction)
    cols = ["ticker", "market", "earnings_date", "direction", "confidence", "p_up",
            "n_past_events", "asof_date"]
    table = show[cols].to_html(index=False, escape=False, border=0)

    model = preds["model"].iloc[0] if len(preds) else "?"
    n_train = preds["train_events"].iloc[0] if len(preds) else 0
    html = _PAGE.format(
        title="Upcoming Earnings — Direction Predictions",
        generated=datetime.now().strftime("%Y-%m-%d %H:%M"),
        subtitle=f"model: {model} · trained on {n_train} labeled events · {len(preds)} upcoming",
        table=table,
        note=("Research output, not financial advice. Direction = predicted sign of the "
              "close(T−1)→close(T+1) move around the announcement. Confidence is the "
              "calibrated model probability; consider acting only above your backtested threshold."),
    )
    html_path.write_text(html)
    return csv_path, html_path
