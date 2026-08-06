# E2E Visual Verification: Interactive GUI Workspace

Auto-generated visual walkthrough for `tests/e2e/002_gui_workspace`:

The committed images below are exact Playwright WebKit renderer baselines. On Linux,
`nix run .#mathpub-gui-e2e` separately launches the packaged Tauri application through
`tauri-driver`, verifies the PTY and PDF preview, and writes a native screenshot artifact to
`build/e2e/tauri-driver.png`.

## Initial Workspace Load (WebKit / Safari Engine)

![Initial Workspace Load](./screenshots/000-initial-workspace-load.png)

## macOS Dictation Prompt

![Dictation Prompt](./screenshots/000-dictation-prompt.png)

## Hovered SyncTeX Region

![Hovered Region](./screenshots/001-hovered-region-visible.png)

## SyncTeX Mapped Regions

![Mapped Regions](./screenshots/001-mapped-regions-visible.png)

## Element Feedback Dialog

![Element Feedback Dialog](./screenshots/002-element-feedback-dialog.png)

## Feedback Inserted into the Active Terminal

![Feedback Inserted](./screenshots/003-feedback-inserted-in-terminal.png)

## Page Two with Page-Specific SyncTeX Mappings

![Page Two](./screenshots/003-page-two.png)

## Quick TeX Editor

![Quick TeX Editor](./screenshots/004-quick-tex-editor.png)

## Quick Edit Committed and Preview Updated

![Quick Edit Preview](./screenshots/005-quick-edit-preview-updated.png)

## Presentation Slide Quick Editor

![Presentation Slide Editor](./screenshots/006-presentation-slide-editor.png)

## Presentation Slide Committed and Rebuilt

![Updated Presentation Slide](./screenshots/007-presentation-slide-updated.png)

**Verifications:**
- [x] Header brand and subtitle render correctly
- [x] The package version and build Git revision are visible
- [x] Isolated PTY terminal emulator loads with clean prompt
- [x] macOS Dictation receives a focused standard text field and inserts without executing
- [x] PDF dropdown loads and displays the rendered first page
- [x] Hovering reveals one clickable mapped region without a prior toggle
- [x] Mapped component regions align with their rendered PDF content
- [x] Clicking a mapped region opens source-aware feedback controls
- [x] Feedback is inserted into the PTY for review without being executed
- [x] Multipage navigation loads page-specific PDF content and mappings
- [x] A mapped TeX source can be edited directly in the GUI
- [x] Saving commits only that source file in Git
- [x] The committed edit reuses instances and hot-swaps the active page within budget
- [x] A Beamer slide exposes a hoverable source-mapped region
- [x] Presentation feedback identifies the authored slide fragment
- [x] A quick slide edit commits only its TeX source and rebuilds the preview
- [x] The selected built PDF can be opened in the native viewer
