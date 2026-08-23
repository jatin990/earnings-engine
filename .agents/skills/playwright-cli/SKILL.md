---
name: playwright-cli
description: Playwright CLI headless and headed browser automation and testing skill. Use for running end-to-end browser tests, capturing page screenshots, verifying UI flows, filling forms, clicking elements, and validating web interfaces via fast, token-efficient command-line execution.
---

# Playwright CLI Browser Automation Skill

## Overview
`playwright-cli` provides a token-efficient command-line interface for browser automation, UI testing, and snapshot verification.

## Common Workflows

### 1. Installation & Environment Check
```bash
# Check if playwright CLI is installed globally or locally
npx -y @playwright/cli@latest --help
# Or run with npx
npx -y @playwright/cli@latest open <url>
```

### 2. Opening Pages & Interactive Headed Mode
```bash
# Open headless
npx -y @playwright/cli@latest open http://127.0.0.1:8000/dashboard

# Open headed (visible browser)
npx -y @playwright/cli@latest open http://127.0.0.1:8000/dashboard --headed
```

### 3. Interacting with Elements
```bash
# Type into an input
npx -y @playwright/cli@latest type "RELIANCE.NS"

# Press keys
npx -y @playwright/cli@latest press Enter

# Click element by text or selector
npx -y @playwright/cli@latest click "Load Report"

# Take verification screenshot
npx -y @playwright/cli@latest screenshot --path=artifacts/dashboard_view.png
```

### 4. Sessions & Persistence
```bash
# Run within a named session to preserve cookies and local storage
npx -y @playwright/cli@latest -s=e2e open http://127.0.0.1:8000/dashboard --persistent
```
