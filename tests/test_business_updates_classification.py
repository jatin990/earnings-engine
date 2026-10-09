from earnings_engine.data.catalysts_news import is_business_update_headline, score_catalyst_headline

def test_business_update_detection():
    # True positives: Operational & Business updates
    assert is_business_update_headline("PC Jeweller Ltd: Quarterly Business Update for Q3 FY25")
    assert is_business_update_headline("Titan Company: Key Operational Highlights for Q3")
    assert is_business_update_headline("Avenue Supermarts (DMart): Standalone Revenue & Store Count Update")
    assert is_business_update_headline("Godrej Properties: Q3 Pre-Sales & Gross Booking Value reaches record high")
    assert is_business_update_headline("Bajaj Auto: Monthly Sales & Dispatches December 2024")
    assert is_business_update_headline("HDFC Bank: Gross Advances and Deposits Update for Quarter ended Dec 31")

    # False positives: Regular results or routine board meetings
    assert not is_business_update_headline("TCS: Board Meeting on Jan 12 to consider Financial Results")
    assert not is_business_update_headline("Infosys Ltd: Un-audited Financial Results for Q3 FY25")
    assert not is_business_update_headline("Reliance Industries: Notice of Postal Ballot")
    assert not is_business_update_headline("Wipro: Audited Financial Results for the Quarter and Year ended March 31, 2025")

def test_business_update_category_scoring():
    scored = score_catalyst_headline("Titan Company reports 25% YoY revenue growth in Q3 business update")
    assert scored["category"] == "Business Updates & Operational Disclosures"
    assert scored["direction"] == "BULLISH"
    assert scored["impact_score"] >= 70
