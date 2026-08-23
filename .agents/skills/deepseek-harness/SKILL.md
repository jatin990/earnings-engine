---
name: deepseek-harness
description: DeepSeek Harness (dsh) agent runtime and plugin infrastructure. Use when scaffolding modular agents, running DeepSeek-R1/V3 evaluations, interacting with the Cordis meta-framework, or executing sandboxed tool workflows.
---

# DeepSeek Harness (dsh) Skill

## Overview
**DeepSeek Harness (`dsh`)** is DeepSeek AI's open-source agent runtime based on the principle that *"Everything is a Plugin"*. Built on top of the **Cordis** framework, it provides a composable infrastructure layer for AI agents, allowing interchangeable models, tool execution environments, sandboxes, and skills.

## Core Capabilities
- **Modular Runtime**: Supports multiple operational modes (Standard, Code, Minimal, and Creator modes).
- **Reasoning Scaffolding**: Optimized for **DeepSeek-R1** (chain-of-thought distillation) and **DeepSeek-V3** (high-throughput multi-turn task completion).
- **Plugin Lifecycle**: Modular sandboxes for file operations, shell commands, and automated code review / verification.

## Common Workflows

### 1. Environment Configuration
Ensure your `.env` contains the DeepSeek API credentials:
```env
DEEPSEEK_API_KEY=sk-...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
```

### 2. Python SDK Integration (OpenAI-compatible)
```python
from openai import OpenAI
import os

client = OpenAI(
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url=os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/v1")
)

# DeepSeek-R1 Reasoning Call
response = client.chat.completions.create(
    model="deepseek-reasoner",
    messages=[
        {"role": "system", "content": "You are a quantitative earnings analyst."},
        {"role": "user", "content": "Analyze quarterly surprise implications for RELIANCE.NS"}
    ],
    temperature=0.6,
)
reasoning_content = response.choices[0].message.reasoning_content
final_answer = response.choices[0].message.content
```

### 3. CLI Commands
```bash
# Initialize / run with npx
npx -y deepseek-harness run --model deepseek-reasoner

# Execute task with sandbox
npx -y deepseek-harness exec "audit earnings history database indexes"
```
