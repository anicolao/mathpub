# Interactive mathpub Workspace: GUI Design Specification

This document details the interface layout, feature specifications, and architectural approach for building an interactive authoring environment directly into the `mathpub` Nix flake.

## 1. Interface Mockup

Below is a design mockup of the split-window workspace showing the terminal emulator on the left and the annotatable PDF with SyncTeX highlighting on the right:

![mathpub Workspace Mockup](file:///Users/anicolao/.gemini/antigravity-cli/brain/e8bf2315-6a6e-43da-acb9-ebf1a4847554/mathpub_ui_mockup_v2_1784637318422.jpg)

---

## 2. Layout & Interactions

The interface is divided into two primary vertical columns:

*   **Left Pane: Terminal Emulator**
    *   **Agent Pluggability**: Instead of a hardcoded chat UI, this panel embeds a full-featured terminal emulator (e.g., via `xterm.js`).
    *   **User Control**: The user runs their shell or preferred CLI chatbot agent (e.g., `antigravity-cli`, `claude-code`, standard Python/Sage REPLs). The workspace tool provides the terminal window but does not control the agent inside it.
*   **Right Pane: SyncTeX-Enabled PDF Viewer**
    *   **Visual Highlights**: The PDF viewer parses SyncTeX outputs to overlay selectable boundary boxes around page elements (lessons, examples, or equations).
    *   **Annotating elements**: Hovering over or clicking a textbook element reveals options to add feedback, copy details, or inspect the source. Adding feedback registers a comment associated with that specific TeX source code line.

---

## 3. Connecting PDF Layout Elements to Source Components

To bridge visual elements in the generated PDF with the source code components in the filesystem, the workspace utilizes **SyncTeX** and compiler-generated **source maps**:

```mermaid
sequenceDiagram
    participant User
    participant Viewer as PDF Viewer
    participant SyncTeX as SyncTeX Engine
    participant SourceMap as source-map.json
    participant Editor as Workspace Backend
    participant Agent as Terminal Agent

    User->>Viewer: Clicks element in PDF
    Viewer->>SyncTeX: Query page & (X,Y) coordinates
    SyncTeX-->>Viewer: Returns generated-tex file & line number
    Viewer->>Editor: Sends file and line info
    Editor->>SourceMap: Look up matching range
    SourceMap-->>Editor: Returns component_id, fragment, and authored_source path
    Editor->>User: Prompts for comment
    User->>Editor: Enters review feedback
    Editor->>Agent: Routes comment + absolute path + fragment context to agent session
```

### Detailed Mapping Steps:
1.  **Code Markers**: During compilation, `src/mathpub/render.py` wraps generated TeX output in structured comments containing metadata:
    `% BEGIN mathpub {"component_id": "algebra.cumulative.01-linear", "fragment": "prompt", "authored_source": "questions/algebra/.../prompt.tex"}`
2.  **SyncTeX Generation**: Building the document generates a SyncTeX database (`.synctex.gz`).
3.  **Coordinate Lookup**: When the user clicks an element in the PDF viewer, the workspace requests the matching generated `.tex` line number using SyncTeX.
4.  **Source Resolution**: The backend matches the generated line number against the `% BEGIN mathpub` JSON comments or the parsed `source-map.json` array.
5.  **Agent Context**: The workspace feeds the user's review feedback, alongside the exact `component_id`, `fragment` (e.g., `prompt`), and absolute path to the `authored_source` file, into the terminal shell/agent.

---

## 4. Native Desktop Packaging & Sync-Aware Componentry (Tauri & WebKit)

To deliver a high-performance, lightweight experience with exact native PDF rendering and zero subpixel font substitution, the workspace is packaged using **Tauri**:

*   **Tauri Architecture**: The GUI application is packaged into a native desktop shell via Tauri, utilizing system-native webviews:
    *   **macOS**: Uses native WKWebView (WebKit), leveraging macOS Quartz/PDFKit rendering for smooth scrolling, subpixel text anti-aliasing, and trackpad pinch-to-zoom.
    *   **Linux**: Uses WebKitGTK with native Poppler/PDF.js fallback.
*   **Transparent Interactive Overlay**: A dynamically sized transparent HTML `div` overlay is positioned exactly on top of the PDF container.
    *   The workspace backend reads the SyncTeX database to build a lightweight spatial index of coordinate bounding boxes for the current page.
    *   Mouse hovers and clicks are intercepted by the HTML overlay. Hovering over a box outlines the textbook element (e.g. green SyncTeX outline), and clicking it sends the page-space $(X, Y)$ coordinate to the backend to locate the source code without disturbing native PDF rendering underneath.
*   **E2E Screenshot Capture via `tauri-driver`**: E2E tests launch the packaged app using `tauri-driver` (WebDriver server for Tauri) connected to Playwright. This enables capturing true native webview screenshots with **0-pixel tolerance** visual regression checking.

---

## 5. Incremental & Fast PDF Regeneration

To achieve near-instantaneous page refreshes when a user edits individual components, the workspace utilizes three levels of build optimizations:

1.  **Component Cache**: The `mathpub` compiler hashes each component's configuration (`component.toml`), seed, and generator (`generate.sage`). If the hash matches the cache, execution of the Sage/Python generator is skipped, and pre-generated TeX fragments are pulled instantly.
2.  **LaTeX Format Dumps (`.fmt`)**: Standard LuaLaTeX compilations spend 90% of their time parsing packages (tikz, amsmath, siunitx, geometry). The workspace pre-compiles these packages into a custom binary format dump (`mathpub.fmt`). Compilation then starts directly from the user's content, reducing standard document compiling times to sub-second.
3.  **Partial Chapter/Section Compilations**: Instead of rebuilds of the entire book, the compiler compiles only the single lesson or chapter currently being viewed. The resulting small PDF pages are spliced or hot-swapped into the viewer, ensuring the edit-to-preview loop takes less than 500 milliseconds.

---

## 6. Nix Flake Integration

The Tauri GUI workspace is packaged directly into the public `mathpub` repository. It can be built and launched via the Nix flake apps:

```bash
nix run .#mathpub-gui
```

This compiles the Tauri desktop shell, launches the local Python backend service, connects the terminal PTY socket, and presents the native workspace application.
