"""CSV + HTML report rendering for predictions and backtests.

Output goes to reports/output/ (gitignored). Plain stdlib string templating —
the report is a single self-contained HTML file.
"""

from __future__ import annotations

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

_EARNINGS_REPORT_PAGE = """<!DOCTYPE html>
<html lang=\"en\">
<head>
    <meta charset=\"UTF-8\">
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\">
    <title>Earnings Watch Report</title>
    <link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@300;400;600;700&display=swap\" rel=\"stylesheet\">
    <style>
        :root {{
            --bg-dark: #0f172a;
            --card-bg: rgba(30, 41, 59, 0.7);
            --accent-purple: #8b5cf6;
            --accent-blue: #3b82f6;
            --accent-green: #10b981;
            --accent-red: #ef4444;
            --text-light: #f8fafc;
            --text-muted: #94a3b8;
        }}
        body {{
            background: linear-gradient(135deg, var(--bg-dark), #1e1b4b);
            color: var(--text-light);
            font-family: 'Inter', sans-serif;
            margin: 0;
            padding: 2rem;
            min-height: 100vh;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        header {{
            display: flex; justify-content: space-between; align-items: center;
            border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 1.5rem; margin-bottom: 2rem;
        }}
        .title-group h1 {{ margin: 0; font-size: 2.2rem; background: linear-gradient(to right, #60a5fa, #c084fc, #f472b6); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }}
        .title-group p {{ color: var(--text-muted); margin: 0.5rem 0 0 0; }}
        .grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; }}
        .card {{ background: var(--card-bg); backdrop-filter: blur(16px); border: 1px solid rgba(255,255,255,0.08); border-radius: 1rem; padding: 1.5rem; }}
        .card-title {{ font-size: 1rem; font-weight: 700; margin-bottom: 0.75rem; color: #e2e8f0; }}
        .card-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 1rem; }}
        .symbol-name {{ font-size: 1.2rem; font-weight: 700; }}
        .badge {{ padding: 0.25rem 0.75rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }}
        .badge-bullish {{ background: rgba(16, 185, 129, 0.2); color: #34d399; border: 1px solid #059669; }}
        .badge-bearish {{ background: rgba(239, 68, 68, 0.2); color: #f87171; border: 1px solid #dc2626; }}
        .badge-neutral {{ background: rgba(59, 130, 246, 0.2); color: #60a5fa; border: 1px solid #2563eb; }}
        .metrics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 1rem; margin: 1rem 0; }}
        .metric {{ background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.08); border-radius: 0.6rem; padding: 0.75rem 0.8rem; }}
        .metric span {{ display: block; font-size: 0.72rem; color: var(--text-muted); margin-bottom: 0.25rem; }}
        .metric strong {{ font-size: 0.95rem; }}
        .commentary {{ font-size: 0.9rem; line-height: 1.6; color: #cbd5e1; border-top: 1px dashed rgba(255,255,255,0.1); padding-top: 1rem; margin-top: 1rem; }}
        .results-table {{ width: 100%; border-collapse: collapse; margin-top: 1rem; font-size: 0.9rem; }}
        .results-table th, .results-table td {{ padding: 0.6rem 0.7rem; border-bottom: 1px solid rgba(255,255,255,0.08); text-align: left; }}
        .results-table th {{ color: var(--text-muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.04em; }}
        footer {{ text-align: center; color: var(--text-muted); font-size: 0.8rem; border-top: 1px solid rgba(255,255,255,0.05); padding-top: 1.5rem; margin-top: 2rem; }}
    </style>
</head>
<body>
    <div class=\"container\">
        <header>
            <div class=\"title-group\">
                <h1>📈 Earnings Watch Report</h1>
                <p>Upcoming results, momentum, and risk context for the next earnings window</p>
            </div>
        </header>
        <section class=\"card\" style=\"margin-top: 1.5rem;\">
            <div class=\"card-header\">
                <div>
                    <div class=\"symbol-name\">📋 Upcoming Results Ledger</div>
                    <span style=\"font-size: 0.8rem; color: var(--text-muted);\">Every stock with an upcoming earnings result and the core data behind it</span>
                </div>
            </div>
            <table class=\"results-table\">
                <thead>
                    <tr>
                        <th>Stock</th>
                        <th>Result Date</th>
                        <th>Market Cap</th>
                        <th>Price</th>
                        <th>30D Return</th>
                        <th>1W Move</th>
                        <th>52W High Gap</th>
                        <th>52W Low Gap</th>
                        <th>1Q Quality</th>
                        <th>3Q Quality</th>
                        <th>Resistance</th>
                        <th>Support</th>
                    </tr>
                </thead>
                <tbody>
                    {results_rows}
                </tbody>
            </table>
        </section>
        <section class="grid" style="margin-top: 1.5rem;">
            {cards}
        </section>
        <footer>Generated automatically by the earnings engine • Research output, not financial advice.</footer>
    </div>
</body>
</html>
"""

_CARD = """<div class=\"card\">
  <div class=\"card-header\">
    <div>
      <div class=\"symbol-name\">{ticker}</div>
      <span style=\"font-size: 0.8rem; color: var(--text-muted);\">{earnings_date}</span>
    </div>
    <span class=\"badge {badge_class}\">{signal}</span>
  </div>
  <div class=\"metrics-grid\">
    <div class=\"metric\"><span>Market Cap</span><strong>{market_cap}</strong></div>
    <div class=\"metric\"><span>Current Price</span><strong>{current_price}</strong></div>
    <div class=\"metric\"><span>1W Move</span><strong>{week_change}</strong></div>
    <div class=\"metric\"><span>30D Return</span><strong>{thirty_day_return}</strong></div>
  </div>
  <div class=\"metrics-grid\">
    <div class=\"metric\"><span>52W High Gap</span><strong>{pct_from_52w_high}</strong></div>
    <div class=\"metric\"><span>52W Low Gap</span><strong>{pct_from_52w_low}</strong></div>
    <div class=\"metric\"><span>Earnings Week Move</span><strong>{earnings_week_move}</strong></div>
    <div class=\"metric\"><span>Prev. 1Q Quality</span><strong>{prev_quarter_score}</strong></div>
  </div>
  <div class=\"metrics-grid\">
    <div class=\"metric\"><span>Prev. 3Q Quality</span><strong>{prev_3q_score}</strong></div>
    <div class=\"metric\"><span>Next Resistance</span><strong>{next_resistance}</strong></div>
    <div class=\"metric\"><span>Current Support</span><strong>{current_support}</strong></div>
    <div class=\"metric\"><span>Setup</span><strong>{setup_signal}</strong></div>
  </div>  <div class="card-title">Risk/Reward</div>
  <div class="metrics-grid">
    <div class="metric"><span>Reward Potential</span><strong>{reward_potential}</strong></div>
    <div class="metric"><span>Risk Buffer</span><strong>{risk_buffer}</strong></div>
  </div>
  <div class="card-title">Momentum Bias</div>
  <div class="metrics-grid">
    <div class="metric"><span>Bias</span><strong>{momentum_bias}</strong></div>
    <div class="metric"><span>Breakout Context</span><strong>{breakout_context}</strong></div>
  </div>  <div class=\"commentary\">
    <i>💡 Take:</i> {take}
  </div>
</div>"""

_RESULT_ROW = """<tr><td>{ticker}</td><td>{earnings_date}</td><td>{market_cap}</td><td>{current_price}</td><td>{thirty_day_return}</td><td>{week_change}</td><td>{pct_from_52w_high}</td><td>{pct_from_52w_low}</td><td>{prev_quarter_score}</td><td>{prev_3q_score}</td><td>{next_resistance}</td><td>{current_support}</td></tr>"""


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
    html_path.write_text(html, encoding="utf-8")
    return csv_path, html_path


def render_upcoming_results_report(enriched: pd.DataFrame, csv_path: Path | None = None,
                                   html_path: Path | None = None) -> Path:
    """Render a polished HTML report for upcoming-results data."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if html_path is None:
        stamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
        html_path = OUTPUT_DIR / f"upcoming-results-{stamp}.html"
    if csv_path is None:
        csv_path = html_path.with_suffix(".csv")

    cards: list[str] = []
    rows: list[str] = []
    for _, row in enriched.iterrows():
        ticker = str(row.get("ticker", ""))
        earnings_date = row.get("earnings_date")
        if pd.notna(earnings_date):
            earnings_text = pd.Timestamp(earnings_date).strftime("%Y-%m-%d")
        else:
            earnings_text = "—"

        def _fmt(v: object, suffix: str = "", signed: bool = False) -> str:
            if pd.isna(v):
                return "—"
            if isinstance(v, (int, float)):
                value = float(v)
                prefix = "+" if signed and value > 0 else "" if signed else ""
                if suffix == "%":
                    return f"{prefix}{value:.2f}%"
                if suffix == "Cr":
                    return f"{value/1000:.1f}k Cr"
                return f"{prefix}{value:,.2f}"
            return str(v)

        def _to_float(v: object, default: float = 0.0) -> float:
            """Safely convert a value to float, handling strings like '4.2%'."""
            if v is None or pd.isna(v):
                return default
            if isinstance(v, (int, float)):
                return float(v)
            s = str(v).strip().rstrip("%").replace(",", "")
            try:
                return float(s)
            except ValueError:
                return default

        market_cap = _fmt(row.get("market_cap"), suffix="Cr")
        current_price = _fmt(row.get("current_price"))
        week_change = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)
        thirty_day_return = _fmt(row.get("thirty_day_return_pct"), "%", signed=True)
        pct_from_52w_high = _fmt(row.get("pct_from_52w_high"), "%", signed=True)
        pct_from_52w_low = _fmt(row.get("pct_from_52w_low"), "%", signed=True)
        earnings_week_move = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)
        prev_quarter_score = _fmt(row.get("prev_quarter_earnings_score"))
        prev_3q_score = _fmt(row.get("prev_3q_earnings_score"))
        next_resistance = _fmt(row.get("next_resistance"))
        current_support = _fmt(row.get("current_support"))

        thirty_day_return_value = _to_float(row.get("thirty_day_return_pct"))
        earnings_week_move_value = _to_float(row.get("earnings_week_move_pct"))
        signal = "Bullish" if thirty_day_return_value > 0 else "Mixed"
        badge_class = "badge-bullish" if signal == "Bullish" else "badge-neutral"
        if thirty_day_return_value > 3 and earnings_week_move_value > 2:
            setup_signal = "Constructive"
        elif thirty_day_return_value > 0 or earnings_week_move_value > 0:
            setup_signal = "Improving"
        else:
            setup_signal = "Cautious"

        reward_potential = "High" if thirty_day_return_value > 5 else "Medium" if thirty_day_return_value > 0 else "Low"
        support_value = _to_float(row.get("current_support"))
        resistance_value = _to_float(row.get("next_resistance"))
        risk_buffer = "Wide" if support_value and resistance_value and (resistance_value - support_value) > 10 else "Tight"
        if thirty_day_return_value > 0 and earnings_week_move_value > 0:
            momentum_bias = "Positive"
            breakout_context = "Momentum is leading into the print"
        elif thirty_day_return_value < 0 and earnings_week_move_value < 0:
            momentum_bias = "Negative"
            breakout_context = "Momentum is fading ahead of the event"
        else:
            momentum_bias = "Neutral"
            breakout_context = "Range-bound setup ahead of results"

        earnings_data = []
        for col in ["eps_estimate", "eps_reported", "surprise_pct", "earnings_date"]:
            if col in row.index and pd.notna(row.get(col)):
                if col == "earnings_date":
                    earnings_data.append(f"result date: {earnings_text}")
                elif col == "surprise_pct":
                    earnings_data.append(f"surprise: {float(row[col]):.2f}%")
                else:
                    earnings_data.append(f"{col}: {row[col]}")
        earnings_text_items = "; ".join(earnings_data) if earnings_data else "no additional earnings data available"

        quality_score_desc = "Quality is scored on a 1–9 scale from recent earnings surprises, where higher values mean stronger recent print quality."
        momentum_desc = "Momentum is derived from the cached price history using the 30-day return and the week-ahead move around the earnings window."
        if thirty_day_return_value > 0 and earnings_week_move_value > 0:
            take = (
                f"{ticker} is heading into {earnings_text} with a constructive setup: the 30D return is {thirty_day_return} and the 1W move is {earnings_week_move}. "
                f"{quality_score_desc} Recent quality is {prev_quarter_score}/{prev_3q_score}, and the risk/reward backdrop is shaped by support near {current_support} and resistance around {next_resistance}. "
                f"{momentum_desc} Earnings details: {earnings_text_items}."
            )
        elif abs(thirty_day_return_value) > 3:
            take = (
                f"{ticker} reaches {earnings_text} with a more dramatic backdrop: the stock has moved {thirty_day_return} over the last month, with a support/resistance profile around {current_support}/{next_resistance}. "
                f"Recent quality remains {prev_quarter_score}/{prev_3q_score}, so traders should watch whether the move is backed by stronger earnings quality or just short-term momentum. "
                f"Earnings details: {earnings_text_items}."
            )
        else:
            take = (
                f"{ticker} enters {earnings_text} with a balanced profile: the 1W move is {earnings_week_move} and the 30D return is {thirty_day_return}. "
                f"Support is near {current_support} and resistance around {next_resistance}, while recent quality remains {prev_quarter_score}/{prev_3q_score}. "
                f"This is the kind of setup that rewards patience and a close look at the earnings details: {earnings_text_items}."
            )

        cards.append(
            _CARD.format(
                ticker=ticker,
                earnings_date=earnings_text,
                badge_class=badge_class,
                signal=signal,
                market_cap=market_cap,
                current_price=current_price,
                week_change=week_change,
                thirty_day_return=thirty_day_return,
                pct_from_52w_high=pct_from_52w_high,
                pct_from_52w_low=pct_from_52w_low,
                earnings_week_move=earnings_week_move,
                prev_quarter_score=prev_quarter_score,
                prev_3q_score=prev_3q_score,
                next_resistance=next_resistance,
                current_support=current_support,
                setup_signal=setup_signal,
                reward_potential=reward_potential,
                risk_buffer=risk_buffer,
                momentum_bias=momentum_bias,
                breakout_context=breakout_context,
                take=take,
            )
        )
        rows.append(
            _RESULT_ROW.format(
                ticker=ticker,
                earnings_date=earnings_text,
                market_cap=market_cap,
                current_price=current_price,
                thirty_day_return=thirty_day_return,
                week_change=week_change,
                pct_from_52w_high=pct_from_52w_high,
                pct_from_52w_low=pct_from_52w_low,
                prev_quarter_score=prev_quarter_score,
                prev_3q_score=prev_3q_score,
                next_resistance=next_resistance,
                current_support=current_support,
            )
        )

    html = _EARNINGS_REPORT_PAGE.format(
        cards="\n".join(cards) if cards else "<p>No upcoming earnings data.</p>",
        results_rows="\n".join(rows) if rows else "<tr><td colspan='12'>No upcoming results.</td></tr>",
    )
    html_path.write_text(html, encoding="utf-8")
    return html_path
