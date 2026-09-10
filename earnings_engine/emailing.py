"""Helpers for sending generated reports and real-time breakout alert notifications by email."""

from __future__ import annotations

import html
import os
import smtplib
import threading
from datetime import datetime, timezone, timedelta
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from earnings_engine.config import EmailSettings, Settings, load_email_settings
from earnings_engine.logging_utils import get_logger

logger = get_logger("earnings_engine.emailing")


def send_report_email(
    csv_path: Path,
    settings: EmailSettings | None = None,
    body: str | None = None,
    html_path: Path | None = None,
) -> None:
    """Send a generated CSV report to the configured recipients."""
    settings = settings or load_email_settings()
    if not settings.enabled:
        logger.info("Email delivery is disabled")
        return
    if not settings.smtp_host or not settings.from_address or not settings.to_addresses:
        logger.info("Email delivery is enabled but SMTP host/from/to are not fully configured")
        raise ValueError("Email delivery is enabled but SMTP host/from/to are not fully configured")

    if not csv_path.exists():
        logger.error("Email attachment path does not exist: %s", csv_path)
        return

    message = EmailMessage()
    message["Subject"] = f"Earnings engine report: {csv_path.name}"
    message["From"] = settings.from_address
    message["To"] = ", ".join(settings.to_addresses)
    if body is None:
        body = "Attached is the latest upcoming-results export from the earnings engine."
    message.set_content(body)
    message.add_attachment(csv_path.read_bytes(), maintype="application", subtype="octet-stream", filename=csv_path.name)
    if html_path is not None and html_path.exists():
        message.add_attachment(html_path.read_bytes(), maintype="text", subtype="html", filename=html_path.name)

    logger.info("Attempting to send email report to %s", settings.to_addresses)
    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        if settings.smtp_username:
            smtp.starttls()
            smtp.login(settings.smtp_username, settings.smtp_password)
        try:
            smtp.send_message(message)
            logger.info("Email report sent successfully: %s", csv_path.name)
        except Exception as e:
            logger.error("Failed to send email: %s", e)


def _deliver_email_smtp(message: EmailMessage, settings: EmailSettings) -> bool:
    """Execute raw SMTP delivery with error handling."""
    try:
        logger.info("Attempting to send breakout alert email to %s", settings.to_addresses)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
            if settings.smtp_username:
                smtp.starttls()
                smtp.login(settings.smtp_username, settings.smtp_password)
            smtp.send_message(message)
            logger.info("Breakout alert email delivered successfully to %s", settings.to_addresses)
            return True
    except Exception as e:
        logger.error("Failed to deliver breakout alert email: %s", e)
        return False


def send_breakout_alert_email(
    ticker: str,
    company_name: str | None = None,
    strategy: str | None = "Classic Technical",
    tier: str = "HOT",
    event_type: str = "PROMOTED_HOT",
    composite_score: float | None = None,
    current_price: float | None = None,
    trigger_price: float | None = None,
    target_price: float | None = None,
    stop_loss: float | None = None,
    risk_reward_ratio: float | None = None,
    volume_ratio: float | None = None,
    reason: str = "",
    catalyst_impact: str | None = None,
    technical_data: dict[str, Any] | None = None,
    settings: EmailSettings | None = None,
    sync: bool = False,
    base_url: str | None = None,
) -> bool:
    """Format and deliver a breakout alert email to configured recipients in background or synchronously."""
    settings = settings or load_email_settings()

    if not settings.enabled:
        logger.debug("[EMAIL-ALERT] Breakout email alerts disabled (enabled=False).")
        return False

    if not settings.smtp_host or not settings.from_address or not settings.to_addresses:
        logger.warning(
            "[EMAIL-ALERT] Email alerts enabled but SMTP host (%s), from (%s), or to addresses (%s) are missing.",
            settings.smtp_host,
            settings.from_address,
            settings.to_addresses,
        )
        return False

    # Sanitization and currency resolution
    ticker_clean = ticker.strip().upper()
    is_nse = ticker_clean.endswith(".NS") or ticker_clean.endswith(".BO") or (".US" not in ticker_clean and not ticker_clean.isalpha())
    currency = "₹" if is_nse or ticker_clean.endswith(".NS") else "$"
    strat_clean = (strategy or "Classic Technical").strip()
    tier_upper = (tier or "HOT").strip().upper()
    event_upper = (event_type or "PROMOTED_HOT").strip().upper()
    now_utc_str = datetime.now(timezone.utc).strftime("%d %b %Y, %H:%M UTC")

    # Score and level fallbacks
    score_str = f"{composite_score:.1f}" if composite_score is not None else "N/A"
    price_str = f"{currency}{current_price:,.2f}" if current_price is not None and current_price > 0 else "N/A"
    trigger_str = f"{currency}{trigger_price:,.2f}" if trigger_price is not None and trigger_price > 0 else price_str

    target_str = f"{currency}{target_price:,.2f}" if target_price is not None and target_price > 0 else "N/A"
    target_gain_pct_str = ""
    if target_price and current_price and current_price > 0:
        gain_pct = ((target_price - current_price) / current_price) * 100
        target_gain_pct_str = f" (+{gain_pct:.1f}%)"

    stop_str = f"{currency}{stop_loss:,.2f}" if stop_loss is not None and stop_loss > 0 else "N/A"
    stop_risk_pct_str = ""
    if stop_loss and current_price and current_price > 0:
        risk_pct = ((current_price - stop_loss) / current_price) * 100
        stop_risk_pct_str = f" (-{risk_pct:.1f}%)"

    rr_str = f"{risk_reward_ratio:.2f} : 1" if risk_reward_ratio is not None and risk_reward_ratio > 0 else "2.0 : 1"
    vol_str = f"{volume_ratio:.2f}x (20D Avg)" if volume_ratio is not None and volume_ratio > 0 else "Normal Vol"

    comp_display = company_name or ticker_clean.replace(".NS", "")
    base_url = (base_url or os.getenv("DASHBOARD_URL") or os.getenv("APP_URL") or "http://localhost:8000").rstrip("/")
    stock_link = f"{base_url}/stock/{ticker_clean}"
    dashboard_link = f"{base_url}/dashboard"

    # Technical decision context resolution
    tech = technical_data or {}
    sma_20_val = tech.get("sma_20")
    sma_50_val = tech.get("sma_50")
    sma_200_val = tech.get("sma_200")
    dist_sma_20 = tech.get("dist_sma_20_pct")
    dist_sma_50 = tech.get("dist_sma_50_pct")
    dist_sma_200 = tech.get("dist_sma_200_pct")
    trend_align = tech.get("trend_alignment") or "Bullish Structure"
    high_52w = tech.get("high_52w")
    low_52w = tech.get("low_52w")
    dist_52w_high = tech.get("dist_52w_high_pct")
    dist_52w_low = tech.get("dist_52w_low_pct")
    range_20d = tech.get("range_20d_pct")
    atr_14 = tech.get("atr_14")
    atr_14_pct = tech.get("atr_14_pct")
    squeeze_on = bool(tech.get("squeeze_on", False))
    rsi_14 = tech.get("rsi_14")
    ret_30d = tech.get("ret_30d_pct")

    sma_20_str = f"{currency}{sma_20_val:,.2f} ({'+' if dist_sma_20 and dist_sma_20 > 0 else ''}{dist_sma_20}%)" if sma_20_val is not None else "N/A"
    sma_50_str = f"{currency}{sma_50_val:,.2f} ({'+' if dist_sma_50 and dist_sma_50 > 0 else ''}{dist_sma_50}%)" if sma_50_val is not None else "N/A"
    sma_200_str = f"{currency}{sma_200_val:,.2f} ({'+' if dist_sma_200 and dist_sma_200 > 0 else ''}{dist_sma_200}%)" if sma_200_val is not None else "N/A"
    w52_high_str = f"{currency}{high_52w:,.2f} ({dist_52w_high}%)" if high_52w is not None else "N/A"
    w52_low_str = f"{currency}{low_52w:,.2f} (+{dist_52w_low}%)" if low_52w is not None else "N/A"
    squeeze_str = "🔥 ACTIVE SQUEEZE (Coiling)" if squeeze_on else "Expanding Volatility"
    rsi_str = f"{rsi_14:.1f}" if rsi_14 is not None else "N/A"
    atr_str = f"{currency}{atr_14:,.2f} ({atr_14_pct}%)" if atr_14 is not None else "N/A"
    range_20d_str = f"{range_20d:.2f}%" if range_20d is not None else "N/A"
    ret_30d_str = f"{'+' if ret_30d and ret_30d > 0 else ''}{ret_30d:.1f}%" if ret_30d is not None else "N/A"

    # Badges and headers
    if "BREAKOUT" in event_upper or tier_upper == "BREAKOUT":
        badge_bg = "#10b981"
        badge_text = "🚀 BREAKOUT TRIGGERED / CONFIRMED"
        subject_prefix = "🚀 [BREAKOUT TRIGGERED]"
    elif tier_upper == "HOT" or "HOT" in event_upper:
        badge_bg = "#dc2626"
        badge_text = "🔥 HIGH CONVICTION HOT BREAKOUT"
        subject_prefix = "🔥 [HOT ALERT]"
    elif tier_upper == "WARM" or "WARM" in event_upper:
        badge_bg = "#d97706"
        badge_text = "⚡ WARM BREAKOUT SETUP COILING"
        subject_prefix = "⚡ [WARM ALERT]"
    else:
        badge_bg = "#0284c7"
        badge_text = "🎯 BREAKOUT RADAR ALERT"
        subject_prefix = "🎯 [RADAR ALERT]"

    subject = f"{subject_prefix} {ticker_clean} ({comp_display}) - {strat_clean} Breakout Setup ({score_str} pts)"

    # Plain text body fallback
    plain_text = f"""=======================================================
NEXUS INTELLIGENCE PLATFORM · BREAKOUT RADAR ALERT
=======================================================

Ticker:           {ticker_clean} ({comp_display})
Strategy:         {strat_clean}
Conviction Score: {score_str} / 100
Setup Tier:       {tier_upper} ({event_upper})
Timestamp:        {now_utc_str}

-------------------------------------------------------
KEY TRADE LEVELS & PARAMETERS
-------------------------------------------------------
• Current Price:     {price_str}
• Breakout Trigger:  {trigger_str}
• Upside Target:     {target_str}{target_gain_pct_str}
• Invalidation Stop: {stop_str}{stop_risk_pct_str}
• Risk/Reward Ratio: {rr_str}
• Volume Surge:      {vol_str}

-------------------------------------------------------
TECHNICAL DECISION CONTEXT & STRUCTURE
-------------------------------------------------------
• Trend Alignment:   {trend_align}
• 20-Day SMA:        {sma_20_str}
• 50-Day SMA:        {sma_50_str}
• 200-Day SMA:       {sma_200_str}
• 52-Week High/Low:  High: {w52_high_str} | Low: {w52_low_str}
• 20-Day Range %:    {range_20d_str}
• ATR(14) Volatility:{atr_str}
• TTM Squeeze:       {squeeze_str}
• RSI(14) Momentum:  {rsi_str}
• 30-Day Return:     {ret_30d_str}

-------------------------------------------------------
TECHNICAL RATIONALE & CATALYSTS
-------------------------------------------------------
{reason if reason else "Compression coiling setup detected near resistance with positive price-volume momentum."}
{f"Catalyst: {catalyst_impact}" if catalyst_impact else ""}

-------------------------------------------------------
INTELLIGENCE HUBS & CHARTS
-------------------------------------------------------
Stock Dashboard:     {stock_link}
Breakout Radar:      {dashboard_link}

=======================================================
Automated quant alert generated by Nexus Intelligence Platform.
"""

    # Rich Obsidian Dark HTML Template
    escaped_ticker = html.escape(ticker_clean)
    escaped_comp = html.escape(comp_display)
    escaped_strat = html.escape(strat_clean)
    escaped_reason = html.escape(reason if reason else "Compression coiling setup detected near resistance with positive price-volume momentum.")
    escaped_catalyst = html.escape(catalyst_impact) if catalyst_impact else ""
    escaped_trend = html.escape(trend_align)
    escaped_squeeze = html.escape(squeeze_str)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #07090e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0; -webkit-font-smoothing: antialiased;">
  <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #07090e; padding: 24px 12px;">
    <tr>
      <td align="center">
        <!-- Main Card Container -->
        <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="max-width: 620px; background-color: #0f172a; border: 1px solid #1e293b; border-radius: 12px; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);">

          <!-- Header Banner -->
          <tr>
            <td style="padding: 20px 24px; background: linear-gradient(135deg, #0b1120 0%, #1e1b4b 100%); border-bottom: 1px solid #1e293b;">
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <span style="font-size: 11px; font-weight: 700; letter-spacing: 0.1em; color: #38bdf8; text-transform: uppercase;">Nexus Intelligence Engine</span>
                    <h1 style="margin: 6px 0 0 0; font-size: 20px; font-weight: 800; color: #f8fafc; letter-spacing: -0.02em;">Breakout Radar Signal</h1>
                  </td>
                  <td align="right">
                    <span style="display: inline-block; padding: 4px 10px; font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.05em; background-color: {badge_bg}; color: #ffffff; border-radius: 6px;">
                      {badge_text}
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Stock Hero Section -->
          <tr>
            <td style="padding: 24px 24px 16px 24px;">
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0">
                <tr>
                  <td>
                    <div style="font-size: 26px; font-weight: 800; color: #ffffff; line-height: 1.2;">
                      {escaped_ticker}
                    </div>
                    <div style="font-size: 14px; font-weight: 500; color: #94a3b8; margin-top: 4px;">
                      {escaped_comp} · <span style="color: #38bdf8; font-weight: 600;">{escaped_strat}</span>
                    </div>
                  </td>
                  <td align="right" valign="top">
                    <div style="display: inline-block; text-align: right; background-color: #1e293b; padding: 6px 12px; border-radius: 8px; border: 1px solid #334155;">
                      <div style="font-size: 10px; font-weight: 700; color: #94a3b8; text-transform: uppercase;">Score</div>
                      <div style="font-size: 18px; font-weight: 800; color: #fbbf24;">{score_str}<span style="font-size: 12px; color: #64748b;">/100</span></div>
                    </div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- 4-Card Trade Parameters Grid -->
          <tr>
            <td style="padding: 0 24px 20px 24px;">
              <table role="presentation" width="100%" border="0" cellspacing="8" cellpadding="0">
                <tr>
                  <!-- Current Price -->
                  <td width="50%" style="background-color: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 12px 14px;">
                    <div style="font-size: 11px; font-weight: 600; color: #94a3b8; text-transform: uppercase;">Current Price</div>
                    <div style="font-size: 18px; font-weight: 700; color: #f8fafc; margin-top: 4px;">{price_str}</div>
                  </td>
                  <!-- Breakout Trigger -->
                  <td width="50%" style="background-color: #1e293b; border: 1px solid #0284c7; border-radius: 8px; padding: 12px 14px;">
                    <div style="font-size: 11px; font-weight: 600; color: #38bdf8; text-transform: uppercase;">Breakout Trigger</div>
                    <div style="font-size: 18px; font-weight: 700; color: #38bdf8; margin-top: 4px;">{trigger_str}</div>
                  </td>
                </tr>
                <tr>
                  <!-- Target Price -->
                  <td width="50%" style="background-color: #1e293b; border: 1px solid #059669; border-radius: 8px; padding: 12px 14px;">
                    <div style="font-size: 11px; font-weight: 600; color: #34d399; text-transform: uppercase;">Upside Target</div>
                    <div style="font-size: 18px; font-weight: 700; color: #34d399; margin-top: 4px;">{target_str} <span style="font-size: 12px; font-weight: 600;">{target_gain_pct_str}</span></div>
                  </td>
                  <!-- Stop Loss -->
                  <td width="50%" style="background-color: #1e293b; border: 1px solid #dc2626; border-radius: 8px; padding: 12px 14px;">
                    <div style="font-size: 11px; font-weight: 600; color: #f87171; text-transform: uppercase;">Invalidation Stop</div>
                    <div style="font-size: 18px; font-weight: 700; color: #f87171; margin-top: 4px;">{stop_str} <span style="font-size: 12px; font-weight: 600;">{stop_risk_pct_str}</span></div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Technical Decision Context Matrix -->
          <tr>
            <td style="padding: 0 24px 20px 24px;">
              <div style="font-size: 12px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em; color: #38bdf8; margin-bottom: 8px;">
                📊 Technical Decision Context & Moving Averages
              </div>
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0b1120; border: 1px solid #1e293b; border-radius: 8px; font-size: 12px;">
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">Trend Alignment</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 700; color: #34d399; border-bottom: 1px solid #1e293b;">{escaped_trend}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">20-Day SMA</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 600; color: #f8fafc; border-bottom: 1px solid #1e293b;">{sma_20_str}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">50-Day SMA</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 600; color: #f8fafc; border-bottom: 1px solid #1e293b;">{sma_50_str}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">200-Day SMA</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 600; color: #f8fafc; border-bottom: 1px solid #1e293b;">{sma_200_str}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">52W High / Low</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 600; color: #cbd5e1; border-bottom: 1px solid #1e293b;">H: {w52_high_str} | L: {w52_low_str}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">ATR(14) Volatility / 20D Range</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 600; color: #f8fafc; border-bottom: 1px solid #1e293b;">{atr_str} | {range_20d_str}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">John Carter TTM Squeeze</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 700; color: {'#38bdf8' if squeeze_on else '#94a3b8'}; border-bottom: 1px solid #1e293b;">{escaped_squeeze}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8; border-bottom: 1px solid #1e293b;">RSI(14) Momentum</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 700; color: #fbbf24; border-bottom: 1px solid #1e293b;">{rsi_str}</td>
                </tr>
                <tr>
                  <td style="padding: 9px 12px; color: #94a3b8;">Volume Surge / 30D Return</td>
                  <td align="right" style="padding: 9px 12px; font-weight: 700; color: #34d399;">{vol_str} | {ret_30d_str}</td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Rationale & Catalyst Box -->
          <tr>
            <td style="padding: 0 24px 24px 24px;">
              <div style="background-color: #1e293b; border-left: 3px solid #38bdf8; border-radius: 0 8px 8px 0; padding: 14px 16px;">
                <div style="font-size: 11px; font-weight: 700; text-transform: uppercase; color: #38bdf8; letter-spacing: 0.05em; margin-bottom: 6px;">Technical Analysis & Setup Thesis</div>
                <div style="font-size: 13px; line-height: 1.5; color: #cbd5e1;">{escaped_reason}</div>
                {f'<div style="font-size: 12px; margin-top: 8px; padding-top: 8px; border-top: 1px solid #334155; color: #fbbf24;"><strong>📰 Catalyst:</strong> {escaped_catalyst}</div>' if escaped_catalyst else ''}
              </div>
            </td>
          </tr>

          <!-- Action Buttons -->
          <tr>
            <td style="padding: 0 24px 28px 24px;" align="center">
              <table role="presentation" border="0" cellspacing="8" cellpadding="0">
                <tr>
                  <td>
                    <a href="{stock_link}" target="_blank" style="display: inline-block; padding: 12px 22px; font-size: 13px; font-weight: 700; text-decoration: none; color: #ffffff; background-color: #0284c7; border-radius: 6px; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);">
                      Inspect Stock Intelligence Hub →
                    </a>
                  </td>
                  <td>
                    <a href="{dashboard_link}" target="_blank" style="display: inline-block; padding: 12px 20px; font-size: 13px; font-weight: 600; text-decoration: none; color: #94a3b8; background-color: #1e293b; border: 1px solid #334155; border-radius: 6px;">
                      Open Breakout Radar
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 24px; background-color: #070a12; border-top: 1px solid #1e293b; text-align: center; font-size: 11px; color: #64748b;">
              Nexus Intelligence Platform · Real-time quantitative breakout monitoring<br>
              Generated at {now_utc_str} · Configured recipients via Control Center
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    # Assemble multipart message
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.from_address
    msg["To"] = ", ".join(settings.to_addresses)
    msg.set_content(plain_text)
    msg.add_alternative(html_content, subtype="html")

    if sync:
        return _deliver_email_smtp(msg, settings)
    else:
        # Background delivery via daemon thread to keep scanner/API non-blocking
        t = threading.Thread(
            target=_deliver_email_smtp,
            args=(msg, settings),
            daemon=True,
            name=f"BreakoutEmailAlert-{ticker_clean}",
        )
        t.start()
        return True


def send_hourly_breakout_digest_email(
    hours_lookback: float = 1.0,
    settings: EmailSettings | None = None,
    app_settings: Settings | None = None,
    sync: bool = False,
    base_url: str | None = None,
) -> bool:
    """Consolidate breakout candidate transitions from the audit log and deliver an hourly digest email."""
    settings = settings or load_email_settings()

    if not settings.enabled:
        logger.debug("[HOURLY-DIGEST-EMAIL] Breakout email alerts disabled (enabled=False).")
        return False

    if not settings.smtp_host or not settings.from_address or not settings.to_addresses:
        logger.warning(
            "[HOURLY-DIGEST-EMAIL] Email alerts enabled but SMTP host (%s), from (%s), or to addresses (%s) are missing.",
            settings.smtp_host,
            settings.from_address,
            settings.to_addresses,
        )
        return False

    app_settings = app_settings or Settings()
    try:
        from earnings_engine.data.db import get_db_connection
        from earnings_engine.data.migrations import apply_migrations

        apply_migrations(app_settings)
        conn = get_db_connection(app_settings)

        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=max(0.1, hours_lookback))
        cutoff_iso = cutoff_dt.isoformat()
        cutoff_sqlite = cutoff_dt.strftime("%Y-%m-%d %H:%M:%S")

        query = """
            SELECT id, ticker, company_name, event_type, from_tier, to_tier,
                   score_before, score_after, price, trigger_price,
                   reason, catalyst_impact, created_at, strategy, counter, updated_at
            FROM breakout_audit_log
            WHERE (created_at >= ? OR updated_at >= ? OR created_at >= ? OR updated_at >= ?)
              AND (
                  UPPER(to_tier) IN ('HOT', 'WARM', 'BREAKOUT')
                  OR UPPER(event_type) LIKE '%WARM%'
                  OR UPPER(event_type) LIKE '%HOT%'
                  OR UPPER(event_type) LIKE '%BREAKOUT%'
              )
              AND UPPER(ticker) NOT LIKE '%TEST%'
              AND UPPER(ticker) NOT LIKE '%MOCK%'
              AND UPPER(ticker) NOT LIKE '%DUMMY%'
            ORDER BY id DESC
        """
        rows = conn.execute(query, (cutoff_iso, cutoff_iso, cutoff_sqlite, cutoff_sqlite)).fetchall()
    except Exception as e:
        logger.warning("[HOURLY-DIGEST-EMAIL] Failed querying breakout_audit_log: %s", e)
        return False

    if not rows:
        logger.info("[HOURLY-DIGEST-EMAIL] No coiling or promoted breakout setups found in last %.1f hour(s).", hours_lookback)
        return False

    # Deduplicate transitions by (ticker, strategy), keeping the newest record
    seen: set[tuple[str, str]] = set()
    setups: list[dict[str, Any]] = []
    for r in rows:
        sym_clean = str(r[1]).strip().upper()
        strat_clean = str(r[13] or "Classic Technical").strip()
        key = (sym_clean, strat_clean.upper())
        if key in seen:
            continue
        seen.add(key)
        setups.append({
            "id": r[0],
            "ticker": sym_clean,
            "company_name": r[2] or sym_clean.replace(".NS", ""),
            "event_type": r[3],
            "from_tier": (r[4] or "COLD").upper(),
            "to_tier": (r[5] or "WARM").upper(),
            "score_before": r[6],
            "score_after": r[7],
            "price": r[8],
            "trigger_price": r[9],
            "reason": r[10] or "Quantitative breakout setup coiling",
            "catalyst_impact": r[11],
            "created_at": r[12],
            "strategy": strat_clean,
            "counter": r[14] or 1,
            "updated_at": r[15] or r[12],
        })

    # Sort: HOT/BREAKOUT first, then descending by score_after
    def _sort_key(s: dict[str, Any]) -> tuple[int, float]:
        tier_prio = 0 if s["to_tier"] in ("HOT", "BREAKOUT") else 1
        score_val = float(s["score_after"]) if s["score_after"] is not None else 0.0
        return (tier_prio, -score_val)

    setups.sort(key=_sort_key)

    hot_count = sum(1 for s in setups if s["to_tier"] in ("HOT", "BREAKOUT"))
    warm_count = sum(1 for s in setups if s["to_tier"] == "WARM")
    total_count = len(setups)

    now_utc = datetime.now(timezone.utc)
    now_utc_str = now_utc.strftime("%d %b %Y, %H:%M UTC")
    base_url = (base_url or os.getenv("DASHBOARD_URL") or os.getenv("APP_URL") or "http://localhost:8000").rstrip("/")
    dashboard_link = f"{base_url}/dashboard"

    subject = f"⚡ [HOURLY DIGEST] {total_count} Breakout Setups Coiling & Promoted ({now_utc_str})"

    # Plain-text fallback
    plain_lines = [
        "=" * 70,
        f"⚡ NEXUS QUANTITATIVE BREAKOUT HOURLY DIGEST",
        f"Generated: {now_utc_str} | Window: Last {hours_lookback:.1f} hour(s)",
        f"Total Active Setups: {total_count} ({hot_count} Hot/Breakout, {warm_count} Coiling Warm)",
        "=" * 70,
        "",
    ]

    for idx, s in enumerate(setups, 1):
        is_nse = s["ticker"].endswith(".NS") or s["ticker"].endswith(".BO")
        curr = "₹" if is_nse else "$"
        p_str = f"{curr}{s['price']:,.2f}" if s["price"] else "N/A"
        trig_str = f"{curr}{s['trigger_price']:,.2f}" if s["trigger_price"] else "N/A"
        sc_before = f"{s['score_before']:.1f}" if s["score_before"] is not None else "--"
        sc_after = f"{s['score_after']:.1f}" if s["score_after"] is not None else "--"
        badge_symbol = "🔥" if s["to_tier"] == "HOT" else ("🚀" if s["to_tier"] == "BREAKOUT" else "⚡")

        plain_lines.append(f"{idx}. {badge_symbol} {s['ticker']} ({s['company_name']}) - {s['strategy']}")
        plain_lines.append(f"   Transition: {s['from_tier']} -> {s['to_tier']} | Score: {sc_before} -> {sc_after} pts")
        plain_lines.append(f"   Current: {p_str} | Trigger: {trig_str}")
        plain_lines.append(f"   Thesis: {s['reason']}")
        if s["catalyst_impact"]:
            plain_lines.append(f"   Catalyst: {s['catalyst_impact']}")
        plain_lines.append(f"   Inspect: {base_url}/stock/{s['ticker']}")
        plain_lines.append("")

    plain_lines.append("=" * 70)
    plain_lines.append(f"Open Breakout Radar Dashboard: {dashboard_link}")
    plain_text = "\n".join(plain_lines)

    # HTML rows generation
    table_rows_html = []
    for s in setups:
        is_nse = s["ticker"].endswith(".NS") or s["ticker"].endswith(".BO")
        curr = "₹" if is_nse else "$"
        p_str = f"{curr}{s['price']:,.2f}" if s["price"] else "N/A"
        trig_str = f"{curr}{s['trigger_price']:,.2f}" if s["trigger_price"] else "N/A"
        sc_before = f"{s['score_before']:.1f}" if s["score_before"] is not None else "--"
        sc_after = f"{s['score_after']:.1f}" if s["score_after"] is not None else "--"

        if s["to_tier"] in ("HOT", "BREAKOUT"):
            tier_badge_bg = "#dc2626" if s["to_tier"] == "HOT" else "#10b981"
            tier_badge_icon = "🔥" if s["to_tier"] == "HOT" else "🚀"
        else:
            tier_badge_bg = "#d97706"
            tier_badge_icon = "⚡"

        escaped_reason = html.escape(s["reason"])
        escaped_catalyst = html.escape(s["catalyst_impact"] or "")
        stock_url = f"{base_url}/stock/{s['ticker']}"

        row_html = f"""
        <tr style="border-bottom: 1px solid #1e293b;">
          <td style="padding: 12px 14px; vertical-align: top;">
            <div style="font-weight: 700; font-size: 14px; color: #f8fafc;">
              <a href="{stock_url}" target="_blank" style="color: #38bdf8; text-decoration: none;">{html.escape(s['ticker'])}</a>
            </div>
            <div style="font-size: 12px; color: #94a3b8; margin-top: 2px;">{html.escape(s['company_name'])}</div>
            <div style="display: inline-block; font-size: 10px; font-weight: 600; padding: 2px 6px; border-radius: 4px; background-color: #1e293b; color: #94a3b8; margin-top: 4px;">
              {html.escape(s['strategy'])}
            </div>
          </td>
          <td style="padding: 12px 14px; vertical-align: top;">
            <span style="display: inline-block; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 700; color: #ffffff; background-color: {tier_badge_bg};">
              {tier_badge_icon} {s['from_tier']} &rarr; {s['to_tier']}
            </span>
            <div style="font-size: 11px; color: #64748b; margin-top: 4px;">
              Count: #{s['counter']}
            </div>
          </td>
          <td align="right" style="padding: 12px 14px; vertical-align: top;">
            <div style="font-weight: 600; font-size: 13px; color: #f8fafc;">{p_str}</div>
            <div style="font-size: 11px; color: #38bdf8; margin-top: 2px;">Trig: {trig_str}</div>
          </td>
          <td align="center" style="padding: 12px 14px; vertical-align: top;">
            <div style="font-weight: 700; font-size: 14px; color: #34d399;">{sc_after}</div>
            <div style="font-size: 10px; color: #64748b;">(from {sc_before})</div>
          </td>
          <td style="padding: 12px 14px; vertical-align: top; font-size: 12px; color: #cbd5e1; max-width: 240px; line-height: 1.4;">
            <div>{escaped_reason}</div>
            {f'<div style="font-size: 11px; color: #fbbf24; margin-top: 4px;"><strong>Catalyst:</strong> {escaped_catalyst}</div>' if escaped_catalyst else ''}
          </td>
          <td align="center" style="padding: 12px 14px; vertical-align: middle;">
            <a href="{stock_url}" target="_blank" style="display: inline-block; padding: 6px 12px; font-size: 11px; font-weight: 700; text-decoration: none; color: #ffffff; background-color: #0284c7; border-radius: 4px; white-space: nowrap;">
              Inspect &rarr;
            </a>
          </td>
        </tr>
        """
        table_rows_html.append(row_html)

    rows_joined = "\n".join(table_rows_html)

    html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{html.escape(subject)}</title>
</head>
<body style="margin: 0; padding: 0; background-color: #07090e; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; color: #e2e8f0;">
  <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="background-color: #07090e; padding: 24px 8px;">
    <tr>
      <td align="center">
        <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="max-width: 780px; background-color: #0f172a; border-radius: 12px; border: 1px solid #1e293b; overflow: hidden; box-shadow: 0 10px 25px -5px rgba(0, 0, 0, 0.5);">

          <!-- Header Bar -->
          <tr>
            <td style="padding: 24px 28px; background: linear-gradient(135deg, #1e1b4b 0%, #0f172a 100%); border-bottom: 1px solid #1e293b;">
              <div style="font-size: 11px; font-weight: 800; text-transform: uppercase; color: #818cf8; letter-spacing: 0.1em; margin-bottom: 6px;">
                ⚡ NEXUS QUANTITATIVE BREAKOUT HOURLY DIGEST
              </div>
              <div style="font-size: 20px; font-weight: 800; color: #f8fafc; line-height: 1.3;">
                {total_count} Breakout Candidates Coiling & Promoted
              </div>
              <div style="font-size: 13px; color: #94a3b8; margin-top: 6px;">
                Window: Last {hours_lookback:.1f}h &bull; <strong style="color: #f87171;">{hot_count} Hot / Breakout</strong> &bull; <strong style="color: #fbbf24;">{warm_count} Coiling Warm</strong> &bull; {now_utc_str}
              </div>
            </td>
          </tr>

          <!-- Summary Table -->
          <tr>
            <td style="padding: 20px 24px;">
              <table role="presentation" border="0" cellpadding="0" cellspacing="0" width="100%" style="border-collapse: collapse;">
                <thead>
                  <tr style="border-bottom: 2px solid #334155; font-size: 11px; font-weight: 700; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.05em;">
                    <th align="left" style="padding: 8px 14px;">Asset / Strategy</th>
                    <th align="left" style="padding: 8px 14px;">Tier Transition</th>
                    <th align="right" style="padding: 8px 14px;">Price / Trigger</th>
                    <th align="center" style="padding: 8px 14px;">Score</th>
                    <th align="left" style="padding: 8px 14px;">Setup Rationale</th>
                    <th align="center" style="padding: 8px 14px;">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {rows_joined}
                </tbody>
              </table>
            </td>
          </tr>

          <!-- CTA Buttons -->
          <tr>
            <td style="padding: 0 24px 24px 24px;" align="center">
              <table role="presentation" border="0" cellspacing="8" cellpadding="0">
                <tr>
                  <td>
                    <a href="{dashboard_link}" target="_blank" style="display: inline-block; padding: 12px 24px; font-size: 13px; font-weight: 700; text-decoration: none; color: #ffffff; background-color: #0284c7; border-radius: 6px; box-shadow: 0 4px 12px rgba(2, 132, 199, 0.4);">
                      Launch Breakout Radar Dashboard &rarr;
                    </a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding: 16px 24px; background-color: #070a12; border-top: 1px solid #1e293b; text-align: center; font-size: 11px; color: #64748b;">
              Nexus Intelligence Platform &bull; Automated Hourly Quantitative Digest<br>
              Generated at {now_utc_str} &bull; Configured recipients via Control Center
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = settings.from_address
    msg["To"] = ", ".join(settings.to_addresses)
    msg.set_content(plain_text)
    msg.add_alternative(html_content, subtype="html")

    if sync:
        return _deliver_email_smtp(msg, settings)
    else:
        t = threading.Thread(
            target=_deliver_email_smtp,
            args=(msg, settings),
            daemon=True,
            name=f"BreakoutHourlyDigest-{int(now_utc.timestamp())}",
        )
        t.start()
        return True

