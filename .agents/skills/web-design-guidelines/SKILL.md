---
name: web-design-guidelines
description: Comprehensive Web Interface Guidelines and accessibility/design auditing. Use when evaluating UI code, verifying WCAG accessibility, checking contrast, responsive layouts, focus rings, semantic HTML structure, and touch targets.
---

# Web Design & Interface Guidelines

## Auditing & Quality Checklist

### 1. Accessibility (a11y) & WCAG AA Compliance
- **Color Contrast**: Minimum contrast ratio of **4.5:1** for standard text and **3:1** for large headings and active UI components (WCAG AA).
- **Focus Rings & Keyboard Navigation**: Ensure all interactive elements (`<button>`, `<a>`, `<input>`, `<select>`) have visible focus rings (`:focus-visible`).
- **Semantic HTML**: Proper heading order (`h1` -> `h2` -> `h3`), semantic containers (`<header>`, `<nav>`, `<main>`, `<section>`, `<article>`, `<footer>`).
- **ARIA & Labels**: All icon-only buttons must have `aria-label` or `title` attributes. Form inputs must have matching `<label>` elements.

### 2. Responsive & Viewport Resilience
- **Fluid Layouts**: Use CSS Grid and Flexbox with `minmax()` and `clamp()` for responsive fluid typography and component scaling.
- **Touch Targets**: Minimum **44x44px** interactive area on touch screens.
- **Overflow Protection**: Prevent unexpected horizontal scrollbars (`overflow-x: hidden` on viewport wrappers, `text-overflow: ellipsis` on dynamic strings).

### 3. Motion & Performance
- **Respect `prefers-reduced-motion`**: Disable non-essential large animations when requested by user OS.
- **Fast First Paint**: Zero layout shifts (CLS), reserve dimension placeholders for images and charts.
