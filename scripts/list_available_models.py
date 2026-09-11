import urllib.request
import json
from earnings_engine.config import Settings

s = Settings()
url = f"{s.omniroute_base_url}/models"
req = urllib.request.Request(
    url,
    headers={"Authorization": f"Bearer {s.omniroute_api_key}"}
)
with urllib.request.urlopen(req) as resp:
    data = json.loads(resp.read().decode())
    models = [m.get("id") for m in data.get("data", [])]
    print(f"Total models: {len(models)}")
    ag_models = [m for m in models if "antigravity" in m]
    or_models = [m for m in models if "openrouter" in m]
    print("Antigravity models:", ag_models)
    print(f"OpenRouter models count: {len(or_models)}")
    print("Sample OpenRouter models:", or_models[:20])
