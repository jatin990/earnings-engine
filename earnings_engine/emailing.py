"""Helpers for sending generated reports and real-time breakout alert notifications by email."""

from __future__ import annotations

import html
import os
import smtplib
import threading
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any

from earnings_engine.config import EmailSettings, load_email_settings
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

    # Badges and headers
    if tier_upper == "HOT" or "HOT" in event_upper:
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

          <!-- Key Metrics Table -->
          <tr>
            <td style="padding: 0 24px 20px 24px;">
              <table role="presentation" width="100%" border="0" cellspacing="0" cellpadding="0" style="background-color: #0b1120; border: 1px solid #1e293b; border-radius: 8px; font-size: 13px;">
                <tr>
                  <td style="padding: 10px 14px; color: #94a3b8; border-bottom: 1px solid #1e293b;">Risk / Reward Ratio</td>
                  <td align="right" style="padding: 10px 14px; font-weight: 700; color: #38bdf8; border-bottom: 1px solid #1e293b;">{rr_str}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; color: #94a3b8; border-bottom: 1px solid #1e293b;">Volume Surge Ratio</td>
                  <td align="right" style="padding: 10px 14px; font-weight: 700; color: #34d399; border-bottom: 1px solid #1e293b;">{vol_str}</td>
                </tr>
                <tr>
                  <td style="padding: 10px 14px; color: #94a3b8;">Recorded Event</td>
                  <td align="right" style="padding: 10px 14px; font-weight: 700; color: #f8fafc;">{event_upper}</td>
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
