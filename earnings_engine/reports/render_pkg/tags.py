"""Multi-dimensional institutional tags for stock price and market action."""

from __future__ import annotations

import html
from typing import Any
from earnings_engine.reports.render_pkg.scoring import _safe_float


def build_institutional_tags(row: dict | Any) -> list[dict[str, str]]:
    """Build multi-dimensional institutional tags for stock price, technical action, verified filings, active news, and radar status."""
    tags: list[dict[str, str]] = []

    def _get(k: str, default=None):
        if hasattr(row, "get"):
            return row.get(k, default)
        return getattr(row, k, default)

    # 1. Source / Official Exchange Regulatory Provenance
    source = str(_get("source", "")).lower().strip()
    if source == "nse":
        tags.append({
            "label": "🏛 NSE Verified",
            "icon": "🏛",
            "bg": "rgba(16, 185, 129, 0.12)",
            "color": "#10b981",
            "border": "rgba(16, 185, 129, 0.35)",
            "title": "Official board meeting announcement verified on National Stock Exchange (NSE)",
        })
    elif source == "bse":
        tags.append({
            "label": "🏛 BSE Verified",
            "icon": "🏛",
            "bg": "rgba(16, 185, 129, 0.12)",
            "color": "#10b981",
            "border": "rgba(16, 185, 129, 0.35)",
            "title": "Official board meeting announcement verified on Bombay Stock Exchange (BSE)",
        })
    elif source in ("yfinance", "projected", "estimate"):
        tags.append({
            "label": "⚠️ Projected (Unconfirmed)",
            "icon": "⚠️",
            "bg": "rgba(245, 158, 11, 0.12)",
            "color": "#f59e0b",
            "border": "rgba(245, 158, 11, 0.35)",
            "title": "Projected earnings date; awaiting official corporate exchange filing on NSE/BSE",
        })

    # 2. Active News Catalysts
    news_items = _get("news_items") or []
    if news_items:
        has_order_win = False
        has_regulatory = False
        has_capex = False
        for n in news_items:
            cat = str(n.get("category", "")).upper()
            title = str(n.get("title", "")).lower()
            if cat == "ORDER_WIN" or "order" in title or "contract" in title:
                has_order_win = True
            elif cat == "REGULATORY" or "approval" in title or "usfda" in title or "sebi" in title:
                has_regulatory = True
            elif cat == "CAPEX" or "expansion" in title or "plant" in title:
                has_capex = True

        if has_order_win:
            tags.append({
                "label": "⚡ Order Win",
                "icon": "⚡",
                "bg": "rgba(59, 130, 246, 0.15)",
                "color": "#60a5fa",
                "border": "rgba(59, 130, 246, 0.35)",
                "title": "Recent material order win or commercial contract reported in corporate news",
            })
        if has_regulatory:
            tags.append({
                "label": "⚖ Regulatory",
                "icon": "⚖",
                "bg": "rgba(168, 85, 247, 0.15)",
                "color": "#c084fc",
                "border": "rgba(168, 85, 247, 0.35)",
                "title": "Recent regulatory, compliance, or statutory disclosure",
            })
        if has_capex:
            tags.append({
                "label": "🏭 Capex Expansion",
                "icon": "🏭",
                "bg": "rgba(34, 197, 94, 0.15)",
                "color": "#4ade80",
                "border": "rgba(34, 197, 94, 0.35)",
                "title": "Capacity expansion or capital expenditure announcement",
            })
        if not (has_order_win or has_regulatory or has_capex):
            tags.append({
                "label": f"📰 {len(news_items)} Active News",
                "icon": "📰",
                "bg": "rgba(100, 116, 139, 0.15)",
                "color": "#94a3b8",
                "border": "rgba(100, 116, 139, 0.3)",
                "title": f"{len(news_items)} corporate news headlines in past 14 days",
            })

    # 3. Technical & Price Action Flags
    pct_52h = _safe_float(_get("pct_from_52w_high"))
    if pct_52h is not None and pct_52h >= -2.5:
        tags.append({
            "label": "🎯 Testing 52W High",
            "icon": "🎯",
            "bg": "rgba(16, 185, 129, 0.15)",
            "color": "#34d399",
            "border": "rgba(16, 185, 129, 0.35)",
            "title": f"Consolidating within {abs(pct_52h):.1f}% of 52-week high",
        })

    pct_52l = _safe_float(_get("pct_from_52w_low"))
    if pct_52l is not None and pct_52l <= 3.0:
        tags.append({
            "label": "🔻 Near 52W Low",
            "icon": "🔻",
            "bg": "rgba(239, 68, 68, 0.15)",
            "color": "#f87171",
            "border": "rgba(239, 68, 68, 0.35)",
            "title": f"Trading within {pct_52l:.1f}% of 52-week low",
        })

    rel_vol = _safe_float(_get("rel_vol_5d_vs_63d"))
    if rel_vol is not None and rel_vol >= 2.0:
        tags.append({
            "label": f"⚡ Vol Surge {rel_vol:.1f}x",
            "icon": "⚡",
            "bg": "rgba(245, 158, 11, 0.15)",
            "color": "#fbbf24",
            "border": "rgba(245, 158, 11, 0.35)",
            "title": f"5-day trading volume expanded to {rel_vol:.1f}x of 63-day benchmark",
        })

    # 4. Breakout Radar Flags
    is_breakout = bool(_get("is_breakout_active"))
    bo_score = _safe_float(_get("breakout_score")) or 0.0
    if is_breakout:
        if bo_score >= 70.0:
            tags.append({
                "label": "🔥 Elite Hot Breakout",
                "icon": "🔥",
                "bg": "rgba(239, 68, 68, 0.18)",
                "color": "#f87171",
                "border": "rgba(239, 68, 68, 0.4)",
                "title": f"Active on Breakout Radar Elite Hot list with composite score {bo_score:.0f}",
            })
        else:
            tags.append({
                "label": "🚀 Breakout Radar",
                "icon": "🚀",
                "bg": "rgba(147, 51, 234, 0.15)",
                "color": "#c084fc",
                "border": "rgba(147, 51, 234, 0.35)",
                "title": f"Active on Breakout Radar with composite score {bo_score:.0f}",
            })

    # 5. Earnings Consistency & Quality Flags
    beat_rate = _safe_float(_get("beat_rate_pct"))
    quarters = _safe_float(_get("total_historical_quarters")) or 0
    if quarters >= 6 and beat_rate is not None and beat_rate >= 80.0:
        tags.append({
            "label": f"👑 Consistent Beater ({beat_rate:.0f}%)",
            "icon": "👑",
            "bg": "rgba(16, 185, 129, 0.12)",
            "color": "#10b981",
            "border": "rgba(16, 185, 129, 0.3)",
            "title": f"Beat market estimates in {beat_rate:.0f}% of past {int(quarters)} quarters",
        })
    elif quarters >= 4 and beat_rate is not None and beat_rate <= 30.0:
        tags.append({
            "label": f"⚠️ Serial Misser ({beat_rate:.0f}%)",
            "icon": "⚠️",
            "bg": "rgba(239, 68, 68, 0.12)",
            "color": "#f87171",
            "border": "rgba(239, 68, 68, 0.3)",
            "title": f"Missed market estimates in {100 - beat_rate:.0f}% of past {int(quarters)} quarters",
        })

    return tags


def render_institutional_tags_html(tags: list[dict[str, str]]) -> str:
    """Render a list of institutional tag dictionaries into compact HTML pills."""
    if not tags:
        return ""
    pills = [
        f'<span class="inst-tag" style="background:{t["bg"]};color:{t["color"]};border:1px solid {t["border"]};font-size:0.60rem;padding:0.06rem 0.32rem;border-radius:3px;font-weight:600;white-space:nowrap;letter-spacing:0.01em;" title="{html.escape(t.get("title", "")) if t.get("title") else html.escape(t["label"])}">{t["label"]}</span>'
        for t in tags
    ]
    return "".join(pills)
