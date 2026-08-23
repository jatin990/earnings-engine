---
name: awesome-design-md
description: DESIGN.md plain-text design system standard for AI agents (Google Stitch / VoltAgent standard). Defines visual tokens, surface materials, component styles, typography scales, color palettes, and responsive layouts in a markdown specification that AI agents read to build consistent, premium UIs.
---

# Awesome DESIGN.md Specification

## What is DESIGN.md?
`DESIGN.md` is a plain-text design system document located in the project root. While `AGENTS.md` instructs coding agents on *how to build and run* the project, `DESIGN.md` instructs design and frontend agents on *how the UI must look and feel*.

## Structure of a DESIGN.md File

A complete `DESIGN.md` specifies:
1. **Design Tokens & Theme Constants**: CSS root variables for colors, surface elevations, shadows, borders, radiuses.
2. **Typography System**: Primary and display font families, font sizes, line heights, letter-spacing scales.
3. **Component Specs**: Badges, action buttons, table designs, dialogs, status chips, charts.
4. **Layout Patterns & Breakpoints**: Sidebar/topbar layouts, responsive grid behaviors, max-widths, padding scales.
5. **Motion Guidelines**: Transition durations, easing curves, hover reactions.

## Usage
When generating or modifying frontend code in a repository containing `DESIGN.md`, always read and strictly adhere to the defined tokens and component guidelines in `DESIGN.md`.
