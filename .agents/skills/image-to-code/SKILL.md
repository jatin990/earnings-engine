---
name: image-to-code
description: Elite image-first website design-to-code workflow. For visual frontend creation and redesign tasks, generate reference mockups with generate_image first, deeply inspect and extract design tokens (colors, type scale, spacing, layout hierarchy), then implement pixel-precise frontend code matching the visual design.
---

# Image-to-Code Design Workflow

## Core Directive: Image-First Visual Translation
For visually important UI tasks:
1. **Generate Image First**: Use `generate_image` to create art-directed, high-fidelity mockups of the component, hero, or page layout.
2. **Deep Image Analysis Second**: Inspect the generated image, extracting:
   - Color palette (hex codes for backgrounds, surface cards, primary accents, text hierarchy).
   - Typography scales and font weights.
   - Spacing rhythm and component padding.
   - Micro-details (border radiuses, shadows, badge styles, glow effects).
3. **Implementation Third**: Write the HTML/CSS/JS or framework code faithfully translating the design tokens and layout structure into working, responsive code.

## Rules & Disciplines
- **Avoid Under-generation**: Generate dedicated images for complex sections or detail states rather than guessing.
- **Avoid Slop Defaults**: Don't collapse into generic centered cards; maintain the asymmetry and hierarchy present in the visual reference.
- **Small Viewport Realistic**: Ensure the hero and primary call to action remain prominent and legible on standard laptop viewports.
