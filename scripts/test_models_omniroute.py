import urllib.request
import json
from earnings_engine.config import Settings

models_to_test = [
    "antigravity",
    "antigravity/gemini-3.7-flash-medium",
    "antigravity/gemini-3.8-flash-tiered",
    "openrouter/deepseek/deepseek-r1",
    "openrouter/meta-llama/llama-3.3-70b-instruct",
    "openrouter/google/gemini-2.0-flash-001"
]

s = Settings()
url = f"{s.omniroute_base_url}/chat/completions"

for m in models_to_test:
    payload = {
        "model": m,
        "messages": [{"role": "user", "content": "Respond with OK"}],
        "max_tokens": 10
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {s.omniroute_api_key}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"PASS: {m} -> {content.strip()[:30]}")
    except Exception as e:
        print(f"FAIL: {m} -> {e}")
