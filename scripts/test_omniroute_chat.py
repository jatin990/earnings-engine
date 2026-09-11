import urllib.request
import json
from earnings_engine.config import Settings

def test_chat_completion(model_name: str):
    s = Settings()
    url = f"{s.omniroute_base_url}/chat/completions"
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "Respond with exactly the word 'PING_OK' and nothing else."}
        ],
        "max_tokens": 10,
        "temperature": 0.1
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {s.omniroute_api_key}",
            "Content-Type": "application/json"
        }
    )
    try:
        with urllib.request.urlopen(req) as resp:
            body = resp.read().decode("utf-8")
            print(f"[{model_name}] Status: {resp.status}")
            res_json = json.loads(body)
            msg = res_json.get("choices", [{}])[0].get("message", {}).get("content", "")
            print(f"[{model_name}] Content: {msg.strip()}")
            return True
    except urllib.error.HTTPError as e:
        print(f"[{model_name}] HTTPError {e.code}: {e.read().decode('utf-8')}")
        return False
    except Exception as e:
        print(f"[{model_name}] Error: {e}")
        return False

if __name__ == "__main__":
    print("Testing combo 'antigravity':")
    test_chat_completion("antigravity")
    print("\nTesting combo 'anitgravity':")
    test_chat_completion("anitgravity")
    print("\nTesting direct model 'antigravity/gemini-3.7-flash-medium':")
    test_chat_completion("antigravity/gemini-3.7-flash-medium")
