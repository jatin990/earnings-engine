---
name: andrej-karpathy-skills
description: Andrej Karpathy's first-principles AI engineering, neural network training recipe, Software 2.0 / LLM OS architecture, tokenization mastery, and minimalist clean-code craftsmanship (nanoGPT, micrograd, llm.c standard). Use when architecting deep learning pipelines, debugging loss curves/gradients, building LLM reasoning loops, optimizing inference/training, or writing clean self-contained PyTorch/Python code.
---

# Andrej Karpathy Engineering & AI Skills

> *"A recipe for training neural networks: become one with the data, set up an end-to-end skeleton, overfit a tiny batch, regularize, and scale."* — Andrej Karpathy

---

## 1. First-Principles AI & Deep Learning

### Understand Every Byte & Gradient
- **No Black Boxes**: Understand the mechanics from the ground up—from scalar autograd engines (`micrograd`) to vectorized multi-head attention (`nanoGPT`, `llm.c`).
- **Explicit Tensor Shapes**: Always annotate multi-dimensional tensor dimensions with explicit comments:
  ```python
  # x: (B, T, C) -> Q, K, V: (B, nh, T, hs) -> Attn: (B, nh, T, T) -> Out: (B, T, C)
  ```
- **Numerical Stability**:
  - Use `F.cross_entropy` instead of manual `log(softmax(x))` to prevent underflow/overflow.
  - Apply the `log-sum-exp` trick where appropriate.
  - Maintain small epsilon values in LayerNorm / RMSNorm and AdamW (`eps=1e-5` to `1e-8`).

---

## 2. Karpathy's 5-Step Recipe for Training Neural Networks

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Become One with the Data                                 │
│    (Inspect thousands of samples, token distributions, bugs)│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Set Up End-to-End Skeleton + Dumb Baselines              │
│    (Verify loss = -ln(1/vocab_size), measure simple metric) │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Overfit a Single Micro-Batch                             │
│    (Drive training loss to ~0.0 to prove model capacity)    │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Regularize & Hyperparameter Tuning                       │
│    (Warmup + Cosine Decay, Weight Decay, Dropout, Gradient Clip)│
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Scale Up & Measure System Efficiency                     │
│    (Track MFU, tokens/sec, KV-cache, FlashAttention-2/3)    │
└─────────────────────────────────────────────────────────────┘
```

### Step 1: Become One with the Data
- Never start coding the architecture before deeply inspecting the dataset.
- Look for duplicate rows, label imbalance, data leakage from future timestamps, encoding errors, and anomalous outliers.
- Visualize distributions and print raw text/token sequences.

### Step 2: Set Up End-to-End Skeleton & Dumb Baselines
- Build a fast, runnable validation pipeline with zero architectural complexity.
- **Sanity check initial loss**:
  - For classification across $V$ uniform classes: $\text{loss}_0 \approx -\ln(1/V) = \ln(V)$.
  - If initial loss is significantly higher or lower, initialization or loss masking is broken.
- Verify evaluation loops and metric calculations before tuning complex networks.

### Step 3: Overfit a Single Micro-Batch
- Take a single batch of 4–16 samples and train for 100–200 iterations.
- If the training loss cannot reach $\approx 0.0$, stop immediately—do not tune hyperparameters on a model that cannot fit trivial data. Fix bugs in gradient flow, loss functions, learning rate, or tensor reshapes.

### Step 4: Regularize & Tune
- **Learning Rate Schedule**: Warmup linearly for 1–5% of total steps, followed by Cosine Decay down to 10% of peak learning rate ($\eta_{\min} = 0.1 \times \eta_{\max}$).
- **Weight Decay**: Apply weight decay (e.g. `0.1` or `0.01`) strictly to 2D weight matrices (linear projections, embeddings), while skipping 1D biases and normalization scales.
- **Gradient Clipping**: Clip global gradient norm ($\|\mathbf{g}\| \le 1.0$) to avoid instability.

### Step 5: Scale Up & Maximize MFU
- Track **Model FLOPs Utilization (MFU)**: Measure actual floating point throughput versus theoretical peak GPU compute.
- Utilize FlashAttention-2 / FlashAttention-3, RoPE embeddings, RMSNorm, SwiGLU activations, and Grouped-Query Attention (GQA).

---

## 3. LLM as an Operating System (Software 2.0 Framework)

```
┌─────────────────────────────────────────────────────────────┐
│                        USER / AGENT                         │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    LLM Central Processor                    │
│      (DeepSeek-R1 / Llama-3.3-70B / Qwen / Mistral / Claude)│
├──────────────────────────────┬──────────────────────────────┤
│ Working Memory (RAM):        │ System Storage (ROM):        │
│ Context Window & KV-Cache    │ Pretrained & Fine-tuned Base │
│ Multi-turn scratchpad        │ Weights (Embedded Knowledge) │
├──────────────────────────────┴──────────────────────────────┤
│ System Calls & Peripherals (Tool Use):                      │
│ ├── Database Engine (SQLite / Turso / DuckDB)               │
│ ├── Web & Financial Data Feeds (NSE Bhavcopy / yfinance)    │
│ ├── Code Execution Environment (Python REPL / PowerShell)   │
│ └── Multi-Model Consensus Arbiter & Structured Validators   │
└─────────────────────────────────────────────────────────────┘
```

- **Context Window Management**:
  - Context is finite RAM: Keep system prompts dense, eliminate redundant tokens, and use clean schemas.
  - Structure long-term knowledge in external indexed storage (RAG / SQLite / Vector stores) rather than dumping massive raw documents into prompts.
- **Inference-Time Compute & Reasoning**:
  - For complex problems, trade test-time compute for accuracy: allow Chain-of-Thought (CoT), reflective error correction, and multi-model consensus verification.

---

## 4. Tokenization Mastery & Pitfalls

- **BPE Awareness**: Tokenizers break words into subwords. Numbers, punctuation, whitespace, and non-English scripts behave differently across tokenizers.
- **Whitespace Traps**: Leading spaces matter (`" hello"` vs `"hello"` are often completely different tokens).
- **Code Tokenization**: Preserve exact indentation and newline structures.

---

## 5. Minimalist Code Craftsmanship (The `nanoGPT` Standard)

1. **Self-Contained & Readable**: Keep architectures unified in concise, readable files rather than fragmented across dozens of inheritance layers.
2. **Minimal Dependencies**: Prefer pure PyTorch and standard library over bloated abstraction wrappers.
3. **Deterministic & Reproducible**: Set random seeds across Python, NumPy, and PyTorch (`torch.manual_seed(1337)`).
4. **Fast Iteration Velocity**: Prototype on CPU/single-GPU in seconds $\rightarrow$ verify math and gradients $\rightarrow$ scale to cluster.
