# DESIGN.md — Earnings Engine Design System

> Visual design language, design tokens, typography, surface materials, and component specifications for the Earnings Engine interactive dashboard and UI.

---

## 1. Design Tokens & Color Palette

### Dark Theme Palette (Obsidian Slate)
| Token | Hex / HSL | Usage |
| :--- | :--- | :--- |
| `--bg` | `#0f172a` (Slate 900) | Main background |
| `--card` | `#1e293b` (Slate 800) | Surface cards, dialogs, sidebar |
| `--card-border` | `rgba(255, 255, 255, 0.08)` | Subtly elevated container borders |
| `--accent` | `#6366f1` (Indigo 500) | Primary interactive buttons, active indicators |
| `--accent-glow`| `rgba(99, 102, 241, 0.25)` | Focus rings, highlighted cards |
| `--green` | `#10b981` (Emerald 500) | Bullish signals, positive returns, beats |
| `--red` | `#ef4444` (Red 500) | Bearish signals, negative returns, misses |
| `--yellow` | `#f59e0b` (Amber 500) | Neutral / pending / warning states |
| `--light` | `#f8fafc` (Slate 50) | High-contrast primary headings and text |
| `--muted` | `#94a3b8` (Slate 400) | Subtitles, timestamps, auxiliary labels |

---

## 2. Typography System

- **Display & Headings**: `system-ui, -apple-system, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif`
  - `h1`: `1.75rem` / `700` / line-height `1.2` / letter-spacing `-0.025em`
  - `h2`: `1.35rem` / `700` / line-height `1.3`
  - `h3`: `1.15rem` / `600` / line-height `1.35`
  - `h4`: `0.95rem` / `600`
- **Data & Tables**: `0.82rem` / `400`–`600` / tabular-nums
- **Code / Tickers**: `ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace`

---

## 3. Surface & Elevation Guidelines

- **Cards**:
  - `background: linear-gradient(180deg, rgba(30, 41, 59, 0.7) 0%, rgba(15, 23, 42, 0.7) 100%)`
  - `border: 1px solid rgba(255, 255, 255, 0.08)`
  - `border-radius: 0.75rem` (12px)
  - `box-shadow: 0 4px 16px rgba(0, 0, 0, 0.35)`
- **Interactive Hover**:
  - `transition: transform 0.2s cubic-bezier(0.16, 1, 0.3, 1), box-shadow 0.2s ease`
  - On hover: `transform: translateY(-2px); border-color: rgba(99, 102, 241, 0.4)`

---

## 4. Components

### Badges & Chips
- **Pill Badges**: `border-radius: 9999px; padding: 0.2rem 0.6rem; font-size: 0.75rem; font-weight: 600; display: inline-flex; align-items: center; gap: 0.3rem;`
- **Signal States**:
  - Positive: `background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3);`
  - Negative: `background: rgba(239, 68, 68, 0.15); color: #f87171; border: 1px solid rgba(239, 68, 68, 0.3);`
  - Neutral / AI: `background: rgba(139, 92, 246, 0.15); color: #c084fc; border: 1px solid rgba(139, 92, 246, 0.3);`

### Buttons
- **Primary**: `background: linear-gradient(135deg, #6366f1, #4f46e5); color: #fff; border-radius: 0.45rem; font-weight: 600;`
- **Secondary**: `background: rgba(255, 255, 255, 0.06); color: var(--light); border: 1px solid rgba(255, 255, 255, 0.12);`
