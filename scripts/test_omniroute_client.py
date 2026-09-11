from earnings_engine.data.omniroute_client import OmniRouteClient

client = OmniRouteClient()
health = client.probe_health()
print("Health status:", health.get("status"))
print("Endpoint:", health.get("endpoint"))
print("Models count:", health.get("models_count"))

test_item = {
    "ticker": "RELIANCE.NS",
    "headline": "Reliance Industries bags INR 5,000 Cr renewable energy order from Solar Energy Corp",
    "summary": "Reliance New Energy secures major 5000 Cr grid battery storage contract, expected to enhance FY27 green margins.",
    "signal_price": 2950.0,
    "current_price": 2950.0,
}

print("\nTesting analyze_catalyst with default model:")
res = client.analyze_catalyst(test_item, model="antigravity")
print("Result sentiment:", res.get("sentiment"))
print("Result direction:", res.get("direction"))
print("Result target_price:", res.get("target_price"))
print("Result takeaway:", res.get("trading_takeaway"))
