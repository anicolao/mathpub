# E2E Visual Verification Guide

This project enforces strict visual layout verification for all compiled mathpub publications and the interactive GUI workspace. Our E2E tests are the primary source of truth for the correctness of document geometry, rendering engines, spacing, SyncTeX overlay mapping, and GUI interface components.

---

## 1. The Philosophy: "Zero-Pixel Tolerance"

We enforce a strict **Zero-Pixel Tolerance** policy for visual layout regression across both compiled publications and GUI editor sessions. Since PDF geometry, typography, and visual interface state directly affect readability and user interaction, any unintended visual shift is considered a bug.

*   **Software Rendering**: We use consistent TeX packages, `pdftoppm` rasterization, and software-rendered browser engines (`webkit` / `chromium` launched with `--disable-gpu` and `--font-render-hinting=none`) wrapped in Nix to guarantee 100% pixel-level reproducibility across local machines (macOS/Linux) and GitHub Actions runner environments.
*   **Tauri Native Webview Consistency**: The GUI workspace is packaged using **Tauri**, utilizing native OS webviews (WKWebView on macOS, WebKitGTK on Linux). This ensures native PDF rendering (Quartz/PDFKit) while allowing automated screenshot captures via `tauri-driver` and Playwright.
*   **Strict Determinism**: All visual test scenarios run with fixed random seeds and pinned viewports (e.g. `1280x720`).

---

## 2. Directory Structure

All E2E test scenarios live under `tests/e2e/`. Each scenario is contained in its own directory:

```
tests/e2e/
├── helpers/                           # Shared test utilities
│   ├── pdf_visual_helper.py           # Python visual diff engine for TeX/PDF rendering
│   └── gui_step_helper.ts             # Playwright/Tauri step recorder & doc generator
├── 001-physics-worksheet/             # PDF scenario directory
│   ├── test_physics_worksheet.py      # pytest test scenario
│   ├── README.md                      # Auto-generated verification walkthrough
│   └── baselines/                     # Committed 150 DPI baseline PNGs
│       ├── student-page-001.png
│       ├── answers-page-001.png
│       └── solutions-page-001.png
└── 002-gui-workspace/                 # Tauri GUI scenario directory
    ├── gui_workspace.spec.ts          # Playwright + tauri-driver test specification
    ├── README.md                      # Auto-generated visual walkthrough of the GUI run
    └── screenshots/                   # Committed GUI baseline screenshots
        ├── 000-initial-load.png
        ├── 001-synctex-highlight.png
        └── 002-comment-popup.png
```

---

## 3. The "Unified Step Pattern"

To keep preview documentation, verification specs, and screenshot baselines perfectly synchronized, we use an automated **Step Helper** pattern. Developers must **NEVER** manually name baseline images or build filepaths.

### A. PDF Visual Verification (`PDFVisualHelper`)

Wrapped in Python for document compilation:

```python
from pathlib import Path
from mathpub.config import find_project
from tests.e2e.helpers.pdf_visual_helper import PDFVisualHelper

def test_physics_worksheet_layout(update_baselines):
    project = find_project()
    scenario_dir = Path(__file__).parent
    
    helper = PDFVisualHelper(project, scenario_dir, update_baselines=update_baselines)
    helper.verify_publication(
        publication_path=Path("publications/physics-practice.toml"),
        seed="2026",
        variant="A"
    )
    helper.generate_markdown(title="Physics Practice Worksheet Layout")
```

### B. Tauri GUI Verification (`GUIStepHelper`)

For testing the Tauri-packaged GUI application, Playwright connects to `tauri-driver`:

```typescript
import { test, expect } from '@playwright/test';
import { GUIStepHelper } from '../helpers/gui-step-helper';

test('Interactive Workspace SyncTeX Flow', async ({ page }, testInfo) => {
  const helper = new GUIStepHelper(page, testInfo);
  
  // Step 1: Initial Load & Terminal Spawning
  await page.goto('http://localhost:1420'); // Tauri dev server / webview port
  await helper.step('initial-load', 'Workspace launches with terminal and PDF viewer', [
    { spec: 'Terminal emulator is ready', check: async () => await expect(page.locator('.xterm')).toBeVisible() },
    { spec: 'PDF iframe is loaded', check: async () => await expect(page.locator('iframe#pdf-viewer')).toBeVisible() }
  ]);

  // Step 2: SyncTeX Element Hover & Bounding Box Highlight
  await page.mouse.move(800, 300); // Hover over equation box
  await helper.step('synctex-highlight', 'Hovering highlights SyncTeX bounding box', [
    { spec: 'Green SyncTeX outline visible', check: async () => await expect(page.locator('.synctex-box-active')).toBeVisible() }
  ]);

  // Step 3: Click to Comment & Route to PTY
  await page.mouse.click(800, 300);
  await page.fill('#comment-input', 'Check variable definition.');
  await page.click('#submit-comment');
  await helper.step('comment-routed', 'Comment routed to terminal input buffer', [
    { spec: 'Terminal contains comment prompt', check: async () => await expect(page.locator('.xterm')).toContainText('Check variable definition') }
  ]);

  helper.generateDocs();
});
```

---

## 4. How Screenshots are Captured in Tauri

Testing desktop GUI applications requires capturing the exact rendered native webview state. We use two primary strategies depending on the execution context:

### 1. `tauri-driver` + Playwright CDP (Primary CI & Automated Visual Diffing)
- **Mechanism**: `tauri-driver` runs a WebDriver bridge over the Tauri native webview (WKWebView on macOS, WebKitGTK on Linux).
- **Capture**: Playwright issues `page.screenshot()` or `expect(page).toHaveScreenshot()` over the Chrome DevTools Protocol / WebDriver bridge.
- **Zero-Pixel Check**: Compares the captured PNG against `tests/e2e/002-gui-workspace/screenshots/00X-name.png` with `maxDiffPixels: 0`.

### 2. OS-Native Window Capture (Manual Walkthrough & Documentation)
- **macOS**: `screencapture -l <window_id>` captures the complete OS window (including titlebars and native macOS Quartz PDFKit anti-aliased rendering).
- **Linux**: `maim --window <window_id>` or `import -window <window_id>` captures native X11/Wayland window frames.

---

## 5. How Scenario `README.md` Walkthroughs are Generated

Calling `generateDocs()` or `generate_markdown()` automatically creates a scenario `README.md` inside the scenario directory.

- **Content**: Combines markdown headings, embedded image links (`![step](./screenshots/001-name.png)`), and an explicit checkbox list of all passed `verifications`.
- **Reviewer Walkthrough**: Reviewers can open `tests/e2e/002-gui-workspace/README.md` directly on GitHub to visually walk through every step of the GUI scenario without needing to launch the application locally.

---

## 6. Visual Baseline Management (Regeneration)

When UI layout or formatting rules intentionally change, developers must regenerate baseline images.

### Regenerating Baselines
- **PDF Baselines**:
  ```bash
  nix develop -c pytest tests/e2e/ --update-baselines
  ```
- **GUI Screenshots**:
  ```bash
  nix develop -c playwright test --update-snapshots
  ```

### CI Mismatch Artifacts
If visual diffing fails in CI:
1. The test step fails.
2. The workflow saves candidate images, baseline images, and high-contrast red-overlay diff highlight files in `tests/e2e/*/diffs/`.
3. The diff files are uploaded to the PR's `visual-regression-diffs` artifact for diagnostic review.
