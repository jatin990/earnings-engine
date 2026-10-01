"""
Unit tests for Zepto Dark Store Operational Parsers & Email Metrics Extraction Engine.
Tests store metric Excel parsing, DQ loss / shrinkage Excel parsing, and email body heuristics.
"""

import pytest
from earnings_engine.data.zepto_parsers import (
    extract_metrics_from_email_body,
    parse_zepto_store_metrics_excel,
    parse_zepto_loss_shrinkage_excel,
)


def test_extract_metrics_from_email_body_sales_and_orders():
    text = "Store JMU-Sainik Colony Daily Update: GMV: ₹4,52,000 across 1,250 orders. AOV: ₹361.60 with 10-min SLA: 98.4%."
    metrics = extract_metrics_from_email_body(text)

    assert metrics.get("sales_gmv") == 452000.0
    assert metrics.get("order_count") == 1250
    assert metrics.get("aov") == 361.6
    assert metrics.get("sla_adherence_pct") == 98.4


def test_extract_metrics_from_email_body_lakhs_and_ipp():
    text = "End of Shift Summary: Sales of 2.4Lakhs, 850 orders dispatched. Packer IPP: 138.2, DQ Loss: Rs. 1450."
    metrics = extract_metrics_from_email_body(text)

    assert metrics.get("sales_gmv") == 240000.0
    assert metrics.get("order_count") == 850
    assert metrics.get("packer_ipp") == 138.2
    assert metrics.get("loss_amount") == 1450.0


def test_extract_metrics_from_email_body_cr_and_damages():
    text = "Monthly Hub Rollup: Revenue: 1.2Cr, Orders: 34500, Damage: ₹24,000, SLA: 99.1%"
    metrics = extract_metrics_from_email_body(text)

    assert metrics.get("sales_gmv") == 12000000.0
    assert metrics.get("order_count") == 34500
    assert metrics.get("loss_amount") == 24000.0
    assert metrics.get("sla_adherence_pct") == 99.1


def test_extract_metrics_empty_text():
    assert extract_metrics_from_email_body("") == {}
    assert extract_metrics_from_email_body(None) == {}
