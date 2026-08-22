"""Automated 2FA Time-based One-Time Password (TOTP) generator using pyotp.

Complies with SEBI mandates for automated headless authentication across
Indian stock brokers (Zerodha, Angel One, Dhan, Fyers).
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger("earnings_engine.brokers.totp")


def generate_totp(secret: str) -> str:
    """Generate a current 6-digit TOTP code from a base32 TOTP secret.

    Parameters
    ----------
    secret:
        Base32 TOTP secret key provided by broker during 2FA setup.

    Returns
    -------
    Current 6-digit TOTP code as string.
    """
    clean_secret = secret.replace(" ", "").strip().upper()
    try:
        import pyotp
        totp = pyotp.TOTP(clean_secret)
        return totp.now()
    except Exception as e:
        logger.error("Failed to generate TOTP: %s", e)
        raise ValueError(f"Invalid TOTP secret or pyotp error: {e}") from e


def verify_totp(secret: str, otp: str) -> bool:
    """Verify if a given OTP code is valid for the TOTP secret."""
    clean_secret = secret.replace(" ", "").strip().upper()
    try:
        import pyotp
        totp = pyotp.TOTP(clean_secret)
        return bool(totp.verify(otp))
    except Exception:
        return False
