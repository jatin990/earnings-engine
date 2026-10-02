"""Tests for Zepto Hub Offer Letter Generation subsystem."""

from __future__ import annotations

import json
import uuid
import pytest
from fastapi.testclient import TestClient

from earnings_engine.api.server import app
from earnings_engine.config import Settings
from earnings_engine.data import zepto_db
from earnings_engine.data.auth import create_session_token


@pytest.fixture
def client():
    c = TestClient(app)
    token = create_session_token(
        user_id="usr_owner",
        role="owner",
        email="owner@nexus.local",
        name="Nexus Owner",
        scopes=["*"],
    )
    c.cookies.set("nexus_session", token)
    return c


def test_offer_letter_crud():
    settings = Settings()
    zepto_db.ensure_zepto_schema(settings)

    test_id = f"ol_test_{uuid.uuid4().hex[:8]}"
    letter_data = {
        "id": test_id,
        "cand_id": "cand_12345",
        "candidate_name": "Akash Kumar",
        "title": "Mr.",
        "role": "Pickpackers",
        "department": "Operations",
        "work_location": "Sector F Sainik Colony Jammu",
        "date_of_joining": "2026-10-01",
        "employment_type": "Full - Time",
        "doc_ref": "RPS-ZEP-2026/10-01",
        "basic_pay": 12000.0,
        "total_potential": 17000.0,
        "signatory_name": "Jatin",
        "signatory_title": "Authorized Signatory",
        "data_json": json.dumps({
            "slabs": [
                {"kpi": "BASIC PAY", "s1": "₹12,000", "s2": "₹12,000", "s3": "₹12,000"},
                {"kpi": "ATTENDANCE BONUS", "s1": "₹1,000", "s2": "₹700", "s3": "₹500"},
                {"kpi": "TOTAL POTENTIAL", "s1": "₹17,000", "s2": "₹15,600", "s3": "₹14,200"}
            ],
            "achievers": {"first": "₹1,500", "second": "₹1,000", "third": "₹700"}
        }, ensure_ascii=False),
        "html_snapshot": "<div class='offer-letter-test'>Official Offer</div>",
    }

    # 1. Create/Save
    saved = zepto_db.save_offer_letter(letter_data, settings=settings)
    assert saved["id"] == test_id
    assert saved["candidate_name"] == "Akash Kumar"
    assert saved["total_potential"] == 17000.0

    # 2. Get by ID
    fetched = zepto_db.get_offer_letter(test_id, settings=settings)
    assert fetched is not None
    assert fetched["id"] == test_id
    assert fetched["cand_id"] == "cand_12345"
    assert fetched["role"] == "Pickpackers"
    parsed_json = json.loads(fetched["data_json"])
    assert parsed_json["slabs"][2]["s1"] == "₹17,000"

    # 3. List
    letters = zepto_db.get_offer_letters(search="Akash", settings=settings)
    assert any(l["id"] == test_id for l in letters)

    # 4. Update
    letter_data["total_potential"] = 18000.0
    updated = zepto_db.save_offer_letter(letter_data, settings=settings)
    assert updated["total_potential"] == 18000.0

    # 5. Delete
    deleted = zepto_db.delete_offer_letter(test_id, settings=settings)
    assert deleted is True

    # 6. Verify Deleted
    assert zepto_db.get_offer_letter(test_id, settings=settings) is None


def test_offer_letter_endpoints(client):
    test_id = f"ol_api_{uuid.uuid4().hex[:8]}"
    payload = {
        "id": test_id,
        "candidate_name": "Rohan Sharma",
        "title": "Mr.",
        "role": "Shift Incharges",
        "department": "Operations",
        "work_location": "Sector F Sainik Colony Jammu",
        "date_of_joining": "2026-10-15",
        "employment_type": "Full - Time",
        "doc_ref": "RPS-ZEP-2026/10-02",
        "basic_pay": 15000.0,
        "total_potential": 20000.0,
        "signatory_name": "Jatin",
        "data_json": json.dumps({"test": "data"}),
        "html_snapshot": "<div>Rohan Offer Letter</div>",
    }

    # POST create
    res = client.post("/api/v1/zepto/offer-letters", json=payload)
    assert res.status_code == 200, res.text
    data = res.json()
    assert data["success"] is True
    assert data["letter"]["candidate_name"] == "Rohan Sharma"

    # GET list
    res_list = client.get("/api/v1/zepto/offer-letters?search=Rohan")
    assert res_list.status_code == 200
    list_data = res_list.json()
    assert list_data["success"] is True
    assert any(item["id"] == test_id for item in list_data["items"])

    # GET by ID
    res_single = client.get(f"/api/v1/zepto/offer-letters/{test_id}")
    assert res_single.status_code == 200
    assert res_single.json()["letter"]["role"] == "Shift Incharges"

    # DELETE
    res_del = client.delete(f"/api/v1/zepto/offer-letters/{test_id}")
    assert res_del.status_code == 200
    assert res_del.json()["success"] is True

    # GET 404
    res_404 = client.get(f"/api/v1/zepto/offer-letters/{test_id}")
    assert res_404.status_code == 404
