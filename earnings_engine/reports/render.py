"""CSV + HTML report rendering for predictions and backtests.

Output goes to reports/output/ (gitignored). HTML page templates live in
earnings_engine/reports/templates/ as standalone .html files with {placeholder}
tokens. Placeholders are substituted via simple string replacement so the
templates can contain clean CSS without brace escaping.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pandas as pd

from earnings_engine.config import PROJECT_ROOT

OUTPUT_DIR = PROJECT_ROOT / "reports" / "output"
TEMPLATES_DIR = Path(__file__).parent / "templates"

_TEMPLATE_CACHE: dict[str, str] = {}


def _load_template(name: str) -> str:
    """Load an HTML template from the templates directory, cached in memory."""
    if name not in _TEMPLATE_CACHE:
        _TEMPLATE_CACHE[name] = (TEMPLATES_DIR / name).read_text(encoding="utf-8")
    return _TEMPLATE_CACHE[name]


def _render_template(name: str, **values: object) -> str:
    """Substitute {placeholder} tokens in a template file via plain replacement."""
    html = _load_template(name)
    for key, value in values.items():
        html = html.replace("{" + key + "}", str(value))
    return html


def _style_direction(val: str) -> str:
    cls = "up" if val == "UP" else "down"
    return f'<span class="{cls}">{val}</span>'


def render_dashboard(html_path: Path | None = None) -> Path:
    """Render the interactive dashboard for exploring ticker data."""
    if html_path is None:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        html_path = OUTPUT_DIR / "dashboard.html"
    
    html = _render_template("dashboard.html")
    html_path.write_text(html, encoding="utf-8")
    return html_path


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
    html = _render_template(
        "predictions_page.html",
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
                    # market_cap is in rupees; 1 crore = 10,000,000 rupees
                    return f"{value/1e7:,.1f} Cr"
                if suffix == "/9":
                    return f"{value:.0f}/9"
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

        def _fmt_pct_only(v: object) -> str:
            """Format just a percent gap, e.g. '+5.2%'."""
            if pd.isna(v):
                return "—"
            cv = _to_float(v)
            sign = "+" if cv >= 0 else ""
            return f"{sign}{cv:.1f}%"

        def _fmt_hl_pair(high_pct: object, high_price: object, low_pct: object, low_price: object) -> str:
            """Format high/low as '+5.2%/+2.3%<br>(1,240/980)'."""
            high_str = _fmt_pct_only(high_pct)
            low_str = _fmt_pct_only(low_pct)
            prices_str = ""
            if not pd.isna(high_price) or not pd.isna(low_price):
                hp = f"{float(high_price):,.0f}" if not pd.isna(high_price) else "—"
                lp = f"{float(low_price):,.0f}" if not pd.isna(low_price) else "—"
                prices_str = f"<br>({hp}/{lp})"
            return f"{high_str}/{low_str}{prices_str}"
        
        def _fmt_quarter_week_hl(high_pct: object, high_price: object, low_pct: object, low_price: object) -> str:
            """Format quarter week high/low as '+8.7%/+2.3%<br>(8,500/7,800)'."""
            return _fmt_hl_pair(high_pct, high_price, low_pct, low_price)

        market_cap = _fmt(row.get("market_cap"), suffix="Cr")
        current_price = _fmt(row.get("current_price"))
        week_change = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)
        thirty_day_return = _fmt(row.get("thirty_day_return_pct"), "%", signed=True)
        eps_estimate = _fmt(row.get("eps_estimate"))
        eps_reported = _fmt(row.get("eps_reported"))
        surprise_pct = _fmt(row.get("surprise_pct"), "%", signed=True)
        pct_from_52w_high_low = _fmt_hl_pair(row.get("pct_from_52w_high"), row.get("week_high"),
                                              row.get("pct_from_52w_low"), row.get("week_low"))
        earnings_week_move = _fmt(row.get("earnings_week_move_pct"), "%", signed=True)
        
        # Per-quarter week high/low (±4 business days around each earnings date)
        q1_week_hl = _fmt_quarter_week_hl(row.get("q1_week_high_pct"), row.get("q1_week_high_price"),
                                           row.get("q1_week_low_pct"), row.get("q1_week_low_price"))
        q2_week_hl = _fmt_quarter_week_hl(row.get("q2_week_high_pct"), row.get("q2_week_high_price"),
                                           row.get("q2_week_low_pct"), row.get("q2_week_low_price"))
        q3_week_hl = _fmt_quarter_week_hl(row.get("q3_week_high_pct"), row.get("q3_week_high_price"),
                                           row.get("q3_week_low_pct"), row.get("q3_week_low_price"))
        
        prev_quarter_score = _fmt(row.get("prev_quarter_earnings_score"), suffix="/9")
        prev_3q_score = _fmt(row.get("prev_3q_earnings_score"), suffix="/9")
        q1_score = _fmt(row.get("q1_earnings_score"), suffix="/9")
        q2_score = _fmt(row.get("q2_earnings_score"), suffix="/9")
        q3_score = _fmt(row.get("q3_earnings_score"), suffix="/9")
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

        card_values = {
            "ticker": ticker,
            "earnings_date": earnings_text,
            "badge_class": badge_class,
            "signal": signal,
            "market_cap": market_cap,
            "current_price": current_price,
            "week_change": week_change,
            "thirty_day_return": thirty_day_return,
            "pct_from_52w_high_low": pct_from_52w_high_low,
            "earnings_week_move": earnings_week_move,
            "q1_week_hl": q1_week_hl,
            "q2_week_hl": q2_week_hl,
            "q3_week_hl": q3_week_hl,
            "prev_quarter_score": prev_quarter_score,
            "prev_3q_score": prev_3q_score,
            "q1_score": q1_score,
            "q2_score": q2_score,
            "q3_score": q3_score,
            "next_resistance": next_resistance,
            "current_support": current_support,
            "eps_estimate": eps_estimate,
            "eps_reported": eps_reported,
            "surprise_pct": surprise_pct,
            "setup_signal": setup_signal,
            "reward_potential": reward_potential,
            "risk_buffer": risk_buffer,
            "momentum_bias": momentum_bias,
            "breakout_context": breakout_context,
            "take": take,
        }
        cards.append(_render_template("card.html", **card_values))

        row_values = {
            "ticker": ticker,
            "earnings_date": earnings_text,
            "market_cap": market_cap,
            "current_price": current_price,
            "thirty_day_return": thirty_day_return,
            "week_change": week_change,
            "q1_week_hl": q1_week_hl,
            "q2_week_hl": q2_week_hl,
            "q3_week_hl": q3_week_hl,
            "pct_from_52w_high_low": pct_from_52w_high_low,
            "quality_scores": f"{q1_score} | {q2_score} | {q3_score}",
            "prev_3q_score": prev_3q_score,
            "next_resistance": next_resistance,
            "current_support": current_support,
        }
        rows.append(_render_template("result_row.html", **row_values))

    html = _render_template(
        "earnings_report_page.html",
        cards="\n".join(cards) if cards else "<p>No upcoming earnings data.</p>",
        results_rows="\n".join(rows) if rows else "<tr><td colspan='13'>No upcoming results.</td></tr>",
    )
    html_path.write_text(html, encoding="utf-8")
    return html_path