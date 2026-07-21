# E2E Visual Verification Guide

This project enforces strict visual layout verification for all compiled mathpub publications. Our E2E tests are the primary source of truth for the correctness of document geometry, rendering engines, spacing, and page break isolation.

---

## 1. The Philosophy: "Zero-Pixel Tolerance"

We enforce a strict **Zero-Pixel Tolerance** policy for visual layout regression. Since PDF geometry and formatting directly affect readability and grading, any unintended visual shift is considered a layout bug.

*   **Software Rendering**: We use consistent TeX packages and the `pdftoppm` utility wrapped in Nix to guarantee 100% pixel-level reproducibility across local machines (macOS/Linux) and GitHub Actions runner environments.
*   **Determinism**: All visual test scenarios run with fixed random seeds. Random variables are pinned to ensure that candidates do not shift based on variable selection.

---

## 2. Directory Structure

All E2E test scenarios live in `tests/e2e/`. Each scenario is contained in its own directory:

```
tests/e2e/
├── helpers/                           # Shared test utilities (PDFVisualHelper)
├── 001-physics-worksheet/             # Scenario directory
│   ├── test_physics_worksheet.py      # pytest test scenario
│   ├── README.md                      # Auto-generated verification walkthrough
│   └── baselines/                     # Committed visual baseline PNGs
│       ├── student-page-001.png
│       ├── answers-page-001.png
│       └── solutions-page-001.png
```

---

## 3. The "Unified Visual Pattern"

To keep preview documentation and actual test expectations synchronized, we use an automated **Visual Helper**. You must **NEVER** manually name baseline images or build filepaths.

### The `PDFVisualHelper`

We use a helper class `PDFVisualHelper` that automates three operations in a single call:

1.  **Rendering**: Builds the publication and extracts the generated PDFs.
2.  **Conversion**: Converts each page of the generated PDFs to 150 DPI PNGs (using `pdftoppm`).
3.  **Assertion**: Compares the candidate page images pixel-by-pixel with the baseline.
4.  **Documentation**: Auto-generates a structured walkthrough `README.md` containing embedded markdown links to the baseline images and checklists.

#### Test Usage Example

```python
from pathlib import Path
from mathpub.config import find_project
from tests.e2e.helpers.pdf_visual_helper import PDFVisualHelper

def test_physics_worksheet_layout(update_baselines):
    project = find_project()
    scenario_dir = Path(__file__).parent
    
    # 1. Initialize the Visual Helper
    helper = PDFVisualHelper(
        project, 
        scenario_dir, 
        update_baselines=update_baselines
    )
    
    # 2. Verify publication against the seed
    helper.verify_publication(
        publication_path=Path("publications/physics-practice.toml"),
        seed="2026",
        variant="A"
    )
    
    # 3. Generate the visual verification README
    helper.generate_markdown(title="Physics Practice Worksheet Layout")
```

---

## 4. How the README and Preview Documents are Generated

When the helper runs `generate_markdown()`, it automatically creates a scenario `README.md`. 

- **Structure**: It lays out each projection (`student`, `answers`, `solutions`, and `validation`) with its respective page-by-page baseline PNG.
- **Verification Checklist**: Each page features a checklist of layout items that the rendering engine guarantees.
- **Reviewer Preview**: This allows reviewers to walk through the visual output directly in GitHub's file explorer.

---

## 5. Visual Baseline Management (Regeneration)

When formatting intentionally changes (e.g. updating border thickness, adding line breaks, or amending paragraph skips), developers must regenerate baselines.

### Updating Baselines
To update baselines, run the test suite with the custom `--update-baselines` flag:
```bash
nix develop -c pytest tests/e2e/ --update-baselines
```

This updates all baseline PNGs inside `tests/e2e/*/baselines/` and updates the walkthrough `README.md`. These visual changes must then be reviewed (using GitHub's image diffing slider/onion skin tools) and committed.

### CI Failure Action
If visual diffing fails in CI:
1. The test step fails.
2. The workflow writes red-overlay highlight images showing exactly which pixels shifted.
3. These visual mismatch files are uploaded as a `visual-validation-proofs` artifact for diagnostic review.
