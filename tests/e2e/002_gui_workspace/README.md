# E2E Visual Verification: Interactive GUI Workspace

Auto-generated visual walkthrough for `tests/e2e/002_gui_workspace`:

The committed images below are exact Playwright WebKit renderer baselines. On Linux,
`nix run .#mathpub-gui-e2e` separately launches the packaged Tauri application through
`tauri-driver`, verifies the PTY and PDF preview, and writes a native screenshot artifact to
`build/e2e/tauri-driver.png`.

## Initial Workspace Load (WebKit / Safari Engine)

![Initial Workspace Load](./screenshots/000-initial-workspace-load.png)

## Hovered SyncTeX Region

![Hovered Region](./screenshots/001-hovered-region-visible.png)

## SyncTeX Mapped Regions

![Mapped Regions](./screenshots/001-mapped-regions-visible.png)

## Element Feedback Dialog

![Element Feedback Dialog](./screenshots/002-element-feedback-dialog.png)

## Feedback Inserted into the Active Terminal

![Feedback Inserted](./screenshots/003-feedback-inserted-in-terminal.png)

## Incremental Preview Updated

![Incremental Preview](./screenshots/004-incremental-preview-updated.png)

**Verifications:**
- [x] Header brand and subtitle render correctly
- [x] Isolated PTY terminal emulator loads with clean prompt
- [x] PDF dropdown loads and displays the rendered first page
- [x] Hovering reveals one clickable mapped region without a prior toggle
- [x] Mapped component regions align with their rendered PDF content
- [x] Clicking a mapped region opens source-aware feedback controls
- [x] Feedback is inserted into the PTY for review without being executed
- [x] Authored changes reuse instances and hot-swap the active PDF
