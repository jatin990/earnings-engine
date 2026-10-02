"""
Frontend UI Component for the Unified High-Impact Reg 30 Disclosures Stream.
Compatible with Streamlit or can be embedded into dashboards.
"""

import streamlit as st
from datetime import datetime
from earnings_engine.db.reg30_storage import fetch_reg30_stream, fetch_reg30_stats
from earnings_engine.scrapers.bse_reg30_scraper import process_and_ingest_bse_filings


def render_reg30_stream_tab():
    """Renders the Unified Reg 30 Live Feed tab in the dashboard."""
    st.title("⚡ High-Impact Reg 30 Disclosures Stream")
    st.caption("Real-time actionable statutory corporate disclosures filtered for upside catalysts and risk vetoes.")

    # Top Controls & Trigger
    col_refresh, col_stats = st.columns([1, 4])
    with col_refresh:
        if st.button("🔄 Poll Live BSE", type="primary", use_container_width=True):
            with st.spinner("Scanning BSE Corporate Disclosures..."):
                res = process_and_ingest_bse_filings(pages=3)
                st.success(f"Scanned {res['total_scanned']} filings. Captured {res['high_impact_captured']} high-impact events ({res['new_inserted']} new).")

    # Summary Metrics Row
    stats = fetch_reg30_stats()
    by_sent = stats.get("by_sentiment", {})
    bullish_cnt = by_sent.get("BULLISH", 0)
    bearish_cnt = by_sent.get("BEARISH", 0)
    neutral_cnt = by_sent.get("NEUTRAL", 0)
    total_cnt = stats.get("total_disclosures", 0)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Total High-Impact", total_cnt)
    m2.metric("🟢 Bullish Catalysts", bullish_cnt)
    m3.metric("🔴 Risk Vetoes / Red Flags", bearish_cnt)
    m4.metric("⚪ Neutral / Strategic", neutral_cnt)

    st.divider()

    # Filter Bar
    f1, f2, f3, f4 = st.columns([2, 2, 2, 2])
    with f1:
        search_symbol = st.text_input("🔍 Search Ticker / Company", placeholder="e.g. RATNAVEER, INFY")
    with f2:
        selected_category = st.selectbox(
            "Category Filter",
            options=["All Categories", "ORDER_WIN", "CAPEX_COD", "RATING_UPGRADE", "RATING_DOWNGRADE", "AUDITOR_RESIGN", "KMP_RESIGN", "DEFAULT_LEGAL", "M_AND_A"],
            format_func=lambda x: {
                "All Categories": "All Categories",
                "ORDER_WIN": "🟢 Order Wins & Contracts",
                "CAPEX_COD": "🟢 Capex & COD",
                "RATING_UPGRADE": "🟢 Rating Upgrades",
                "RATING_DOWNGRADE": "🔴 Rating Downgrades",
                "AUDITOR_RESIGN": "🔴 Auditor Resignations",
                "KMP_RESIGN": "🔴 KMP Exits",
                "DEFAULT_LEGAL": "🔴 Defaults & Legal",
                "M_AND_A": "⚪ M&A / Partnerships",
            }.get(x, x),
        )
    with f3:
        selected_sentiment = st.selectbox("Sentiment", ["All", "BULLISH", "BEARISH", "NEUTRAL"])
    with f4:
        selected_impact = st.selectbox("Impact Level", ["All", "CRITICAL", "HIGH", "MEDIUM"])

    cat_filter = None if selected_category == "All Categories" else selected_category
    sent_filter = None if selected_sentiment == "All" else selected_sentiment
    imp_filter = None if selected_impact == "All" else selected_impact
    sym_filter = search_symbol.strip() if search_symbol.strip() else None

    items = fetch_reg30_stream(
        category=cat_filter,
        sentiment=sent_filter,
        impact_level=imp_filter,
        symbol=sym_filter,
        limit=50,
    )

    if not items:
        st.info("No corporate disclosures match the selected filter criteria.")
        return

    # Render Feed Cards
    for row in items:
        sentiment_color = "#10b981" if row["sentiment"] == "BULLISH" else ("#ef4444" if row["sentiment"] == "BEARISH" else "#6b7280")
        sentiment_icon = "🟢" if row["sentiment"] == "BULLISH" else ("🔴" if row["sentiment"] == "BEARISH" else "⚪")

        with st.container():
            st.markdown(
                f"""
                <div style="border-left: 4px solid {sentiment_color}; padding: 12px 16px; margin-bottom: 12px; background: rgba(255,255,255,0.03); border-radius: 4px;">
                    <div style="display: flex; justify-content: space-between; align-items: center;">
                        <h4 style="margin: 0; font-size: 1.1rem; color: #f3f4f6;">
                            {sentiment_icon} <b>{row['company_name']}</b> <span style="color: #9ca3af; font-size: 0.9rem;">({row['symbol']})</span>
                        </h4>
                        <span style="font-size: 0.85rem; color: #9ca3af;">⏱️ {row['timestamp']}</span>
                    </div>
                    <div style="margin: 6px 0;">
                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; font-weight: 600;">
                            {row['category_name']}
                        </span>
                        <span style="background: rgba(255,255,255,0.1); padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 6px;">
                            Impact: <b>{row['impact_level']}</b>
                        </span>
                        {f"<span style='background: rgba(16,185,129,0.2); color: #10b981; padding: 2px 8px; border-radius: 4px; font-size: 0.8rem; margin-left: 6px; font-weight: bold;'>₹{row['order_value_cr']} Cr Deal</span>" if row.get('order_value_cr') else ""}
                    </div>
                    <p style="margin: 8px 0 4px 0; font-size: 0.95rem; line-height: 1.4;">
                        {row['headline']}
                    </p>
                    <div style="margin-top: 8px;">
                        <a href="{row['pdf_url']}" target="_blank" style="font-size: 0.85rem; color: #38bdf8; text-decoration: none; font-weight: 500;">
                            📄 View Statutory Exchange PDF ↗
                        </a>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
