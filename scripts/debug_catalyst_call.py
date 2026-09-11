import requests
import json
import time
from earnings_engine.data.omniroute_client import OmniRouteClient, OMNIROUTE_SYSTEM_PROMPT

client = OmniRouteClient()
test_item = {
    "ticker": "RELIANCE.NS",
    "headline": "Reliance Industries bags INR 5,000 Cr renewable energy order from Solar Energy Corp",
    "summary": "Reliance New Energy secures major 5000 Cr grid battery storage contract, expected to enhance FY27 green margins.",
    "signal_price": 2950.0,
    "current_price": 2950.0,
}
prompt = client.format_prompt(test_item)
url = client.get_completions_url()
api_key = client.get_api_key()

headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}"
}
payload = {
    "model": "antigravity",
    "messages": [
        {"role": "system", "content": OMNIROUTE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ],
    "temperature": 0.2,
    "max_tokens": 350,
}

t0 = time.perf_counter()
try:
    resp = requests.post(url, headers=headers, json=payload, timeout=10)
    print("Status:", resp.status_code, "Time:", round(time.perf_counter() - t0, 2), "s")
    if resp.status_code == 200:
        data = resp.json()
        print("Response keys:", data.keys())
        choice = (data.get("choices") or [{}])[0]
        msg = choice.get("message") or {}
        print("Message keys:", msg.keys())
        print("Content:", msg.get("content"))
        print("Reasoning:", msg.get("reasoning"))
    else:
        print("Error text:", resp.text)
except Exception as e:
    print("Exception:", e)
