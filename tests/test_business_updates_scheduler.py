from datetime import date
from earnings_engine.data.business_updates_scheduler import (
    compute_anticipated_business_update_schedules,
    KNOWN_UPDATE_CADENCES,
    sync_business_update_schedules_db,
    get_anticipated_schedules,
)

def test_cadence_calculation():
    # Test for Q3 season (as of Jan 2)
    schedules = compute_anticipated_business_update_schedules(as_of_date=date(2025, 1, 2))
    assert len(schedules) > 0
    pcj = next((s for s in schedules if "PCJEWELLER" in s["ticker"]), None)
    assert pcj is not None
    assert pcj["status"] in ["ANTICIPATED", "DUE_NOW"]
    assert "2025-01" in pcj["next_expected_window_start"]

    # Test monthly sales cadence (e.g. Bajaj Auto or Tata Motors)
    bajaj = next((s for s in schedules if "BAJAJ-AUTO" in s["ticker"]), None)
    assert bajaj is not None
    assert bajaj["frequency"] == "MONTHLY"
    assert bajaj["update_type"] == "MONTHLY_SALES"

    # Test Q1 season (as of July 3)
    q1_schedules = compute_anticipated_business_update_schedules(as_of_date=date(2025, 7, 3))
    titan = next((s for s in q1_schedules if s["ticker"] == "TITAN.NS"), None)
    assert titan is not None
    assert "2025-07" in titan["next_expected_window_start"]

def test_db_sync_and_get_schedules():
    count = sync_business_update_schedules_db(as_of_date=date(2025, 1, 3))
    assert count > 0
    fetched = get_anticipated_schedules(days_ahead=30, as_of_date=date(2025, 1, 3))
    assert len(fetched) > 0
    assert any(item["ticker"] == "PCJEWELLER.NS" for item in fetched)

    # Test status filtering
    due_now = get_anticipated_schedules(status="DUE_NOW", days_ahead=30, as_of_date=date(2025, 1, 3))
    assert isinstance(due_now, list)
    for item in due_now:
        assert item["status"] == "DUE_NOW"
