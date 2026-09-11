import urllib.request
import json
from earnings_engine.config import Settings

s = Settings()
url = f"{s.omniroute_base_url}/chat/completions"
m = "openrouter/deepseek/deepseek-r1"

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
        print("Success:", resp.read().decode())
except urllib.error.HTTPError as e:
    print("HTTPError:", e.code, e.read().decode())
