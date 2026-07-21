# Mathpub Testing & Visual Validation Strategy

This document outlines the testing strategy for the `mathpub` publication engine and tooling, covering local developer verification, automated CI testing, and visual validation of CLI/GUI outputs.

---

## 1. Objectives

- **Core Engine Correctness**: Ensure the GPLv3 engine behaves deterministically (reproducibility of seeds, instance generation, and compilation).
- **Format & Layout Stability**: Guard against regressions in output formats (worksheets, worksheets with component questions, and textbooks) across different PDF engines (`lualatex`, `pdflatex`) and fonts (`concrete`, `libertinus`, `computer-modern`).
- **Visual Verification**: Allow developers and maintainers to inspect PDF styling and GUI interfaces visually during PR review using automated CI artifacts.
- **Fast Feedback Loop**: Maintain a clear separation between quick local unit/integration tests and heavy end-to-end PDF rendering tests.

---

## 2. Test Architecture

Testing is split into three main tiers:

### Tier 1: Unit & Integration Tests (Fast)
- **Scope**:
  - Metadata parsing, schema validation, and TOML deserialization.
  - Sage generator instantiation and context evaluation (without calling fully compiled Sage if mockable).
  - CLI argument parsing, directory discovery, and configuration resolution.
- **Execution**: Run via standard Python unit testing in the Nix developer shell.
- **Commands**:
  ```bash
  nix develop -c pytest tests/
  ```

### Tier 2: End-to-End (e2e) Document Verification (Medium)
- **Scope**:
  - Full compile loop validation using public sample fixtures (e.g., the physics review worksheet and textbook).
  - Validation of all projections: `student`, `answers`, `solutions`, and `validation`.
  - PDF property checks (pages, fonts, embedded elements) using tools like `pypdf` and `pdftotext` to ensure the structure and metadata are intact.
- **Test Fixtures**:
  - Retain `components/questions/physics/` and `publications/physics-practice.toml` as the primary reference and regression fixtures.
  - **No algebra or private publication files may be added to these test fixtures.**
- **Commands**:
  ```bash
  nix run .#mathpub -- check publication publications/physics-practice.toml --json
  nix run .#mathpub -- build publications/physics-practice.toml --seed 2026 --variant A --replace --json
  ```

### Tier 3: Visual Verification & Playwright GUI Tests (CI-Driven)
- **Scope**:
  - Capturing GUI application layouts, interactive elements, terminal emulator mappings, and SyncTeX coordinates.
  - Rendering PDFs to high-resolution images to verify exact visual layout.
- **Execution**:
  - Run Playwright-based tests inside a headless browser environment in CI.
  - Automatically generate documentation screenshots (e.g. updating GUI screenshots in `README.md` or a `docs/` folder).

---

## 3. CI Pipeline Design (GitHub Actions)

The proposed GitHub Actions workflow (`.github/workflows/ci.yml`) will validate all changes on every pull request.

```yaml
name: CI Validation

on:
  push:
    branches: [ main, tooling/* ]
  pull_request:
    branches: [ main ]

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout Code
        uses: actions/checkout@v4

      - name: Install Nix
        uses: cachix/install-nix-action@v25
        with:
          nix_path: nixpkgs=channel:nixos-unstable

      - name: Nix Flake Check
        run: nix flake check

      - name: Run Test Suite
        run: nix develop -c pytest

      - name: Run Playwright GUI Tests & Capture Screenshots
        run: |
          nix develop -c playwright install chromium
          nix develop -c pytest tests/e2e_gui_playwright.py

      - name: Build Sample Publications (Visual Proofs)
        run: |
          nix run .#mathpub -- build publications/physics-practice.toml --seed 2026 --variant A --replace --json
          # Convert PDF pages to PNG for PR visual preview
          nix develop -c pdftoppm -png -r 150 build/physics.practice/A/physics.practice-A-student.pdf build/physics.practice/A/preview-student
          nix develop -c pdftoppm -png -r 150 build/physics.practice/A/physics.practice-A-solutions.pdf build/physics.practice/A/preview-solutions

      - name: Upload Visual Artifacts
        uses: actions/upload-artifact@v4
        with:
          name: visual-validation-proofs
          path: |
            build/physics.practice/A/preview-*.png
            screenshots/gui-*.png
```

---

## 4. Visual Validation Workflow for Reviewers

When reviewing a PR, reviewers can validate layout changes and GUI updates without pulling the branch locally:

1. **GUI Screenshots**:
   - The Playwright suite runs a headless server of the GUI editor, performs actions (e.g. loading a physics component, triggering a build, verifying SyncTeX maps), captures screenshots, and saves them to a `screenshots/` directory.
   - If screenshots differ from the baseline in `main`, the test report lists the delta, and the generated images are uploaded as PR artifacts.
2. **PDF Preview Proofs**:
   - The CI build pipeline automatically compiles `publications/physics-practice.toml` (both the student view and solutions view).
   - `pdftoppm` converts these compiled PDFs into PNG images.
   - Reviewers can view these images directly in the PR's uploaded build artifacts under `visual-validation-proofs` to confirm margins, spacing, fonts (Concrete/Libertinus), and TikZ diagram positioning.
3. **E2E Layout Diffing (Optional)**:
   - For changes targeting the rendering engine (`src/mathpub/render.py`), a visual diff step can compare the generated preview PNGs against pre-rendered baselines to identify any pixel-level shifts in spacing or typography.
