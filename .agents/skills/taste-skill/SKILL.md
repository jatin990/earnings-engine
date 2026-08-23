---
name: taste-skill
description: The Anti-Slop Frontend Framework for AI Agents. Enforces elite typography, intentional spatial composition, rich curated color palettes, bespoke micro-interactions, high-contrast hierarchy, and prevents generic AI template boilerplate (cards-in-cards, center-aligned dark hero clichés, low contrast muted text).
---

# Taste Skill: Anti-Slop Frontend Framework

## Core Philosophy
Deliver distinctive, handcrafted-feeling web experiences. AI models tend to converge on safe, generic averages ("slop"): excessive rounded card containers, identical 3-column feature grids, washed-out low-contrast gray text, and lack of visual rhythm. This skill aggressively breaks those defaults.

## Key Design Principles

### 1. Typography & Hierarchy
- **Distinctive Type Pairing**: Avoid browser defaults. Use curated Google Fonts (e.g. *Outfit*, *Inter Display*, *Space Grotesk*, *Plus Jakarta Sans*, *Syne* for headings; *Plus Jakarta Sans*, *Inter*, *Geist* for body; *JetBrains Mono* for data/code).
- **Proportional Contrast**: Scale contrast dramatically between `h1` (e.g. 2.5rem–4rem, bold, tight letter-spacing `-0.03em`) and body (`1rem`, relaxed line-height `1.55`).
- **High Readability**: Never use sub-4.5:1 contrast for body copy. Primary text must be crisp (`#f8fafc` on dark, `#0f172a` on light).

### 2. Layout & Composition (Anti-Card-Spam)
- **Break Container Fatigue**: Do not nest cards inside cards inside cards.
- **Asymmetry & Balance**: Mix full-width bleed sections, split hero layouts, staggered cards, and generous white space.
- **Generous Spacing Rhythm**: Use consistent multi-tier spacing scales (`0.5rem`, `1rem`, `1.5rem`, `2.5rem`, `4rem`). Let layouts breathe.

### 3. Color & Materials
- **Curated Palettes**: Use Tailwind/HSL balanced colors (e.g., Deep Slate `#0f172a`, Obsidian `#090d16`, Cyber Cyan `#38bdf8`, Emerald Accent `#10b981`, Vibrant Indigo `#6366f1`).
- **Glassmorphism & Depth**: Subtle multi-layered linear gradients (`linear-gradient(180deg, rgba(30,41,59,0.7) 0%, rgba(15,23,42,0.7) 100%)`), border highlights (`1px solid rgba(255,255,255,0.08)`), and soft drop shadows.

### 4. Micro-Interactions & Motion
- **Interactive Feedback**: Hover states with subtle scale (`transform: translateY(-2px)`), glow highlights, and transition curves (`transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1)`).
- **Smooth State Changes**: Animated tab indicators, loading spinners, skeleton loaders, and collapsible cards.
