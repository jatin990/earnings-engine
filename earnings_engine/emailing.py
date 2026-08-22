"""Helpers for sending generated reports by email."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage
from pathlib import Path

from earnings_engine.config import EmailSettings
from earnings_engine.logging_utils import get_logger


def send_report_email(csv_path: Path, settings: EmailSettings, body: str | None = None, html_path: Path | None = None) -> None:
    """Send a generated CSV report to the configured recipients."""
    logger = get_logger("earnings_engine.emailing")
    if not settings.enabled:
        logger.info("Email delivery is disabled")
        logger.info(settings)
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