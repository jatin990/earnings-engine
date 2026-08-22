"""Native Python MCP Server for Local Ollama DeepSeek.

Runs over stdio to provide seamless, free local LLM reasoning and code analysis
using Ollama running on localhost:11434.
"""

from __future__ import annotations

import json
import sys
import urllib.request
import urllib.error

OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_MODEL = "deepseek-r1:8b"


def call_ollama(prompt: str, model: str = DEFAULT_MODEL, system: str = "") -> str:
    """Send prompt to Ollama /api/generate endpoint."""
    payload = {
        "model": model,
        "prompt": prompt,
        "system": system or "You are DeepSeek-R1, an expert reasoning and coding AI.",
        "stream": False,
    }
    req = urllib.request.Request(
        f"{OLLAMA_HOST}/api/generate",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("response", "")
    except Exception as e:
        return f"Error calling Ollama: {e}"


def handle_request(req: dict) -> dict | None:
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "ollama-deepseek-mcp", "version": "1.0.0"},
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "deepseek_reasoning",
                        "description": "Run advanced reasoning, step-by-step logic, or complex analysis with local DeepSeek-R1.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "prompt": {"type": "string", "description": "The complex question, logic problem, or task to reason through"},
                                "system_prompt": {"type": "string", "description": "Optional custom system instructions"}
                            },
                            "required": ["prompt"],
                        },
                    },
                    {
                        "name": "deepseek_code_assistant",
                        "description": "Generate, debug, refactor, or explain code using DeepSeek-R1 on local GPU.",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "task": {"type": "string", "description": "Coding task or question"},
                                "code_context": {"type": "string", "description": "Relevant code snippets or context"}
                            },
                            "required": ["task"],
                        },
                    },
                ]
            },
        }

    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name")
        args = params.get("arguments", {})

        if tool_name == "deepseek_reasoning":
            prompt = args.get("prompt", "")
            sys_prompt = args.get("system_prompt", "")
            response = call_ollama(prompt, system=sys_prompt)
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": response}]
                },
            }

        elif tool_name == "deepseek_code_assistant":
            task = args.get("task", "")
            context = args.get("code_context", "")
            full_prompt = f"Code Context:\n```\n{context}\n```\n\nTask:\n{task}" if context else task
            response = call_ollama(full_prompt, system="You are an expert programming assistant powered by DeepSeek.")
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": response}]
                },
            }

        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -32601, "message": f"Tool '{tool_name}' not found"},
        }

    return None


def main():
    while True:
        try:
            line = sys.stdin.readline()
            if not line:
                break
            req = json.loads(line.strip())
            res = handle_request(req)
            if res:
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()
        except Exception:
            break


if __name__ == "__main__":
    main()
