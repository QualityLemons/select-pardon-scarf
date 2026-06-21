# Contributing to PLeC

Thank you for your interest in PLeC! Contributions are welcome — whether that's fixing a bug, improving a lesson, adding a new challenge, or improving accessibility.

---

## Table of Contents

- [Running locally](#running-locally)
- [Project structure](#project-structure)
- [Adding a new challenge page](#adding-a-new-challenge-page)
- [Code standards](#code-standards)
- [Accessibility requirements](#accessibility-requirements)
- [Submitting a pull request](#submitting-a-pull-request)

---

## Running locally

**Requirements:** Python 3.x (any version), a modern browser.

```bash
git clone https://github.com/QualityLemons/plec.git
cd plec
python serve.py
# Open http://localhost:5000
```

No build step. No npm install. No framework. The server just serves the `challenge/` directory as static files, plus a `/api/assess` endpoint for the milestone assessment engine.

---

## Project structure

```
plec/
├── serve.py                   ← Python HTTP server (port 5000) + /api/assess endpoint
├── challenge/
│   ├── index.html             ← Mission grid landing page
│   ├── supervisor.css         ← Shared Supervisor widget styles
│   ├── assess.js              ← Shared milestone assessment engine
│   ├── assess.css             ← Assessment panel styles
│   ├── .jshintrc              ← JSHint ES11 config
│   ├── level1.html            ← Challenge: Start/Stop Latching Circuit
│   ├── level2.html            ← Challenge: Tank Filling System
│   ├── level3.html            ← Challenge: Modbus TCP Communication
│   ├── level4.html            ← Challenge: Safety Interlock Drill
│   ├── level5.html            ← Challenge: Timed Conveyor (TON)
│   ├── level6.html            ← Challenge: Sequential Batching
│   ├── learn-your-log.html    ← Lesson: Maintenance Logging
│   ├── maintenance-log.html   ← Practice: Log Template
│   ├── multimeter-lesson.html ← Lesson: Digital Multimeter
│   └── multimeter.html        ← Tool: Interactive DMM Simulator
└── apps/
    └── assessment/            ← Python scoring + feedback engine
        ├── gold_standards.py  ← Per-level milestone definitions and weights
        ├── scorer.py          ← Computes score from submitted milestones
        └── reviewer.py        ← Generates plain-English feedback text
```

---

## Adding a new challenge page

1. **Copy an existing challenge** as a starting point — `level1.html` is the simplest.

2. **Update the `<head>`:**
   - Set a unique `<title>` — `PLeC | Your Challenge Name`
   - Keep the Google Fonts link and the FOUC-prevention inline script

3. **Add to the mission grid** in `challenge/index.html`:
   - Copy an existing `.mission-card` block
   - Update the `href`, title, description, badge, and threat level

4. **Add gold standard milestones** in `apps/assessment/gold_standards.py`:
   ```python
   "levelN": {
       "title": "Your Challenge Title",
       "role":  "Relevant Engineering Role",
       "milestones": [
           {"id": "m1", "label": "...", "weight": 25},
           # weights should sum to 100
       ],
       "efficiency_thresholds": {
           "exceptional": 300,   # seconds
           "proficient":  600,
           "satisfactory": 1200,
           "poor": 2400,
       },
       "bonus_criteria": [],
   }
   ```

5. **Add Supervisor tips** — define a `T` array in your page's `<script>` block following the pattern in any existing challenge. Use the five tip variants: `default` (cyan), `tv-warn` (amber), `tv-danger` (red), `tv-good` (green), `tv-purple`.

6. **Validate before submitting** — see [Code standards](#code-standards).

---

## Code standards

PLeC is vanilla HTML5/CSS/ES6. No frameworks, no bundlers, no preprocessors.

### HTML

Every page must pass **W3C Nu HTML Checker** with 0 errors and 0 warnings.

Check locally:
```bash
# Install once
pip install html5validator

# Check a single file
html5validator --root challenge/ --also-check-css challenge/level1.html
```

Or use the online checker: https://validator.w3.org/nu/

### JavaScript

All scripts are linted with **JSHint** using `challenge/.jshintrc` (ES11).

```bash
# Install once
npm install -g jshint

# Lint a file
jshint challenge/level1.html
```

Rules:
- Use `const` / `let`, never `var`
- Wrap all page logic in an IIFE or use `DOMContentLoaded`
- No external JS dependencies — everything must work offline

### CSS

- All colours via CSS custom properties (`--cyan`, `--bg`, etc.) defined in `:root`
- No inline styles except for dynamic JS-driven values
- Respect `prefers-reduced-motion` for any new animations

---

## Accessibility requirements

PLeC targets **WCAG 2.1 Level AA**. Every page must have:

| Requirement | Implementation |
|---|---|
| Skip link | `<a href="#main-content" class="skip-link">Skip to content</a>` |
| Page landmarks | `<header>`, `<main id="main-content">`, `<footer>` |
| Interactive elements | All buttons/controls reachable by keyboard (Tab / Enter / Space) |
| Live regions | PLC state changes announced via `role="status"` or `role="alert"` |
| Colour contrast | Minimum 4.5:1 ratio for all text |
| `aria-label` on controls | Any icon-only button must have a descriptive `aria-label` |

If you're adding interactive elements, run a quick check with a screen reader (NVDA on Windows, VoiceOver on macOS/iOS) before submitting.

---

## Submitting a pull request

1. Fork the repo and create a branch: `git checkout -b feature/my-new-challenge`
2. Make your changes
3. Validate HTML (0 W3C errors), lint JS (0 JSHint errors)
4. Open a pull request with a clear description of what you added and why
5. The CI workflow will automatically run W3C validation on your changes

Pull requests that fail W3C validation will not be merged until the errors are fixed.

---

## Questions?

Open a GitHub Discussion or file an issue. All skill levels are welcome — if you're learning PLC engineering yourself while contributing, that's exactly the spirit of this project.
