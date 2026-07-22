# Mathpub Testing & Visual Validation Strategy

This document outlines the testing strategy for the `mathpub` publication engine and tooling. It defines a strict, automated visual regression framework modeled after the **Zero-Pixel Tolerance** guidelines.

---

## 1. Visual Validation Philosophy: "Zero-Pixel Tolerance"

Visual state is the primary output of the `mathpub` publication engine and GUI workspace. Any unintended shift in margins, page breaks, fonts, TikZ diagram coordinates, spacing, or interface overlays is considered a regression bug. 

To enforce this, we apply the following guidelines:
1. **Zero-Pixel Threshold**: For all PDF previews and GUI pages, comparison tests must assert exactly **0 differing pixels** between the generated output and the committed baseline.
2. **Software-Consistent Rendering**: PDF rasterization and browser rendering are executed with software-only settings and fixed compiler paths (packaged via Nix) to ensure 100% pixel-level reproducibility across local environments (macOS/Linux) and CI runner environments (GitHub Actions).
3. **Tauri Desktop Packaging & Native Webview Consistency**: The GUI workspace is packaged using **Tauri**, utilizing native OS webviews (WKWebView on macOS, WebKitGTK on Linux). Automated screenshot captures are performed via `tauri-driver` connected to Playwright.
4. **Strict Determinism**: Every test scenario utilizes a hardcoded, reproducible random seed and fixed viewport dimensions (`1280x720`).

---

## 2. Directory Structure

All visual and end-to-end tests live under `tests/e2e/`. Scenarios are isolated in their own folders and include automated documentation.

```
tests/e2e/
├── helpers/                           # Shared test utilities
│   ├── pdf_visual_helper.py           # Python visual diff engine for TeX/PDF rendering
│   └── gui_step_helper.ts             # Playwright/Tauri step recorder & doc generator
├── 001-physics-worksheet/             # Scenario folder
│   ├── test_physics_worksheet.py      # E2E test file compiling and checking worksheet layout
│   ├── README.md                      # Auto-generated verification walkthrough of the run
│   └── baselines/                     # Committed 150 DPI baseline PNGs
│       ├── student-page-001.png
│       ├── answers-page-001.png
│       ├── solutions-page-001.png
│       └── validation-page-001.png
└── 002-gui-workspace/                 # Tauri GUI scenario folder
    ├── gui_workspace.spec.ts          # Playwright + tauri-driver specification
    ├── README.md                      # Auto-generated verification walkthrough of GUI run
    └── screenshots/                   # Committed GUI screenshots
        ├── 000-initial-load.png
        ├── 001-synctex-highlight.png
        └── 002-comment-popup.png
```

---

## 3. The PDF Visual Regression Framework (Python)

For document rendering, our pytest suite converts generated PDF pages to high-resolution PNGs and compares them pixel-by-pixel.

### The `PDFVisualHelper` Python Engine

The E2E tests use a helper class that encapsulates compiling, rasterizing, and pixel diffing:

```python
import shutil
import subprocess
from pathlib import Path
from PIL import Image, ImageChops
from mathpub.config import Project
from mathpub.publish import build

class PDFVisualHelper:
    def __init__(self, project: Project, scenario_dir: Path, update_baselines: bool = False):
        self.project = project
        self.scenario_dir = scenario_dir
        self.baseline_dir = scenario_dir / "baselines"
        self.update_baselines = update_baselines
        self.baseline_dir.mkdir(exist_ok=True)
        self.steps = []

    def verify_publication(self, publication_path: Path, seed: str, variant: str):
        # 1. Compile the publication
        result = build(self.project, publication_path, root_seed=seed, variant=variant, replace=True)
        edition_dir = self.project.root / result["edition"]
        
        # 2. Iterate through each output PDF (projections: student, answers, solutions, validation)
        manifest_path = edition_dir / "manifest.json"
        import json
        manifest = json.loads(manifest_path.read_text())
        
        for output in manifest["outputs"]:
            projection = output["projection"]
            pdf_path = edition_dir / output["path"]
            
            # 3. Convert PDF pages to 150 DPI PNGs using pdftoppm
            tmp_png_prefix = edition_dir / f"temp-{projection}"
            subprocess.run([
                "pdftoppm", "-png", "-r", "150", 
                str(pdf_path), str(tmp_png_prefix)
            ], check=True)
            
            # Find generated pages (e.g. temp-student-1.png, temp-student-2.png)
            generated_pages = sorted(edition_dir.glob(f"temp-{projection}-*.png"))
            
            for index, page_png in enumerate(generated_pages):
                page_number = index + 1
                baseline_name = f"{projection}-page-{page_number:03d}.png"
                baseline_path = self.baseline_dir / baseline_name
                
                if self.update_baselines:
                    # Regenerate mode: copy page to baselines directory
                    shutil.copy(page_png, baseline_path)
                else:
                    # Strict validation mode
                    if not baseline_path.exists():
                        raise AssertionError(f"Missing visual baseline: {baseline_name}")
                    
                    self._assert_pixel_match(page_png, baseline_path, projection, page_number)
                
                self.steps.append({
                    "projection": projection,
                    "page": page_number,
                    "image_path": f"./baselines/{baseline_name}"
                })

    def _assert_pixel_match(self, candidate_path: Path, baseline_path: Path, projection: str, page: int):
        img_cand = Image.open(candidate_path).convert("RGB")
        img_base = Image.open(baseline_path).convert("RGB")
        
        if img_cand.size != img_base.size:
            raise AssertionError(f"Dimension mismatch for {projection} page {page}: {img_cand.size} vs {img_base.size}")
            
        # Perform visual diff
        diff = ImageChops.difference(img_cand, img_base)
        bbox = diff.getbbox()
        
        if bbox is not None:
            # Diffs detected! Write a diff highlights file
            diff_dir = self.scenario_dir / "diffs"
            diff_dir.mkdir(exist_ok=True)
            diff_path = diff_dir / f"diff-{projection}-page-{page:03d}.png"
            
            import numpy as np
            arr_cand = np.array(img_cand)
            arr_base = np.array(img_base)
            mask = np.any(arr_cand != arr_base, axis=-1)
            out_arr = arr_cand.copy()
            out_arr[mask] = [255, 0, 0] # Highlight differing pixels in red
            
            Image.fromarray(out_arr).save(diff_path)
            
            raise AssertionError(
                f"Visual regression detected in {projection} page {page}!\n"
                f"Candidate: {candidate_path}\n"
                f"Baseline: {baseline_path}\n"
                f"Diff overlay saved to: {diff_path}"
            )

    def generate_markdown(self, title: str):
        readme_path = self.scenario_dir / "README.md"
        content = f"# Visual Verification: {title}\n\n"
        content += "Automated end-to-end visual validation pages (150 DPI baseline preview):\n\n"
        
        for step in self.steps:
            content += f"## Projection: {step['projection']} (Page {step['page']})\n\n"
            content += f"![{step['projection']} Page {step['page']}]({step['image_path']})\n\n"
            content += "---\n\n"
            
        readme_path.write_text(content)
```

---

## 4. The Tauri GUI Visual Regression Framework (Playwright + `tauri-driver`)

For the visual state of the interactive compiler workspace UI, we use TypeScript Playwright tests connected to `tauri-driver`.

### Playwright Configuration (`playwright.config.ts`)
```typescript
import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30000,
  expect: {
    timeout: 2000,
    toHaveScreenshot: { maxDiffPixels: 0 }, // ZERO-pixel tolerance
  },
  use: {
    browserName: 'webkit', // Native WKWebView engine on macOS
    headless: true,
    launchOptions: {
      args: [
        '--disable-gpu',
        '--font-render-hinting=none',
        '--window-size=1280,720'
      ]
    }
  }
});
```

### The `GUIStepHelper` (TypeScript)
A custom step-helper recorder maps the verification steps, captures screenshots, and creates structured reports:

```typescript
import { type Page, type TestInfo, expect } from '@playwright/test';
import * as fs from 'fs';
import * as path from 'path';

export interface Verification {
  spec: string;
  check: () => Promise<void>;
}

export class GUIStepHelper {
  private stepCount = 0;
  private steps: Array<{ title: string; image: string; specs: string[] }> = [];

  constructor(private page: Page, private testInfo: TestInfo) {}

  async step(id: string, description: string, verifications: Verification[]) {
    // 1. Run all code assertions
    for (const v of verifications) {
      await v.check();
    }

    // 2. Generate standard filename
    const paddedIndex = String(this.stepCount++).padStart(3, '0');
    const filename = `${paddedIndex}-${id.replace(/_/g, '-')}.png`;

    // 3. Assert zero-pixel screen matching
    await expect(this.page).toHaveScreenshot(filename.replace(/\.png$/, ''));

    // 4. Save metadata for Markdown generation
    this.steps.push({
      title: description,
      image: `./screenshots/${filename}`,
      specs: verifications.map(v => v.spec)
    });
  }

  generateDocs() {
    const docPath = path.join(path.dirname(this.testInfo.file), 'README.md');
    let content = `# Test Scenario: ${this.testInfo.title}\n\n`;

    for (const step of this.steps) {
      content += `## Step: ${step.title}\n\n`;
      content += `![${step.title}](${step.image})\n\n`;
      content += `**Verifications:**\n`;
      for (const spec of step.specs) {
        content += `- [x] ${spec}\n`;
      }
      content += `\n---\n\n`;
    }

    fs.writeFileSync(docPath, content);
  }
}
```

---

## 5. Visual Baseline Management (Regeneration)

When layout modifications are intentional (e.g., modifying default line widths, tweaking fonts, changing warning box border radius), developers must regenerate baselines.

### Pytest PDF Baseline Regeneration
Adding a custom `--update-baselines` flag to `conftest.py` enables updating baselines:
```bash
nix develop -c pytest tests/e2e/ --update-baselines
```

### Playwright GUI Screenshot Update
To update GUI snapshots when UI elements intentionally change:
```bash
nix develop -c playwright test --update-snapshots
```

---

## 6. Pull Request Review Workflow

With zero-pixel visual testing enforced, reviewers can perform rapid, accurate visual checks directly within the PR:

1. **Reviewing Baseline Diffs**: 
   - A pull request changing the renderer or GUI will contain modified PNG files in `tests/e2e/*/baselines/` or `tests/e2e/*/screenshots/`.
   - Reviewers can view these diffs directly using GitHub's **rich diff image viewer** (2-up, swipe, or onion skin modes) to verify changes down to individual pixels.
2. **Reviewing Layout Documents**:
   - Every E2E scenario directory contains an auto-generated `README.md` containing the step-by-step walkthrough. Reviewers can read these markdown pages directly on the PR file tree to see the complete rendered output flow.
3. **CI Regression Failures**:
   - If a layout change was accidental, the CI pipeline fails. The reviewer and author can download the `visual-regression-diffs` artifact containing the generated candidate PNG, the original baseline, and the red overlay highlighted diff image.
