document.addEventListener("DOMContentLoaded", () => {
  // 1. Initialize Terminal
  const termContainer = document.getElementById("terminal-container");
  const term = new Terminal({
    cursorBlink: false,
    fontFamily: 'Menlo, Monaco, "Courier New", monospace',
    fontSize: 13,
    theme: {
      background: "#000000",
      foreground: "#ffffff",
      cursor: "#38bdf8",
      selectionBackground: "rgba(56, 189, 248, 0.3)"
    }
  });

  const fitAddon = new FitAddon.FitAddon();
  term.loadAddon(fitAddon);
  term.open(termContainer);
  fitAddon.fit();

  // 2. Connect WebSocket to PTY Backend
  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/terminal`;
  const ws = new WebSocket(wsUrl);

  ws.binaryType = "arraybuffer";

  ws.onopen = () => {
    document.getElementById("status-terminal").textContent = "PTY Connected";
    updateDictationAvailability();
    sendResize();
    sendPreviewSelection();
  };

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
      try {
        const message = JSON.parse(event.data);
        if (handleWorkspaceEvent(message)) return;
      } catch (error) {
        // Text that is not a workspace event belongs to the terminal.
      }
      term.write(event.data);
    } else if (event.data instanceof ArrayBuffer) {
      const bytes = new Uint8Array(event.data);
      term.write(bytes);
    }
    // Refresh publications list after terminal activity
    schedulePubsRefresh();
  };

  ws.onclose = () => {
    document.getElementById("status-terminal").textContent = "PTY Disconnected";
    document.getElementById("status-terminal").className = "badge";
    updateDictationAvailability();
    term.write("\r\n\x1b[31m[mathpub workspace] Connection closed.\x1b[0m\r\n");
  };

  term.onData((data) => {
    if (ws.readyState === WebSocket.OPEN) {
      ws.send(JSON.stringify({ type: "input", data: data }));
    }
  });

  function sendResize() {
    if (ws.readyState === WebSocket.OPEN) {
      const cols = term.cols;
      const rows = term.rows;
      ws.send(JSON.stringify({ type: "resize", cols: cols, rows: rows }));
    }
  }

  window.addEventListener("resize", () => {
    fitAddon.fit();
    sendResize();
  });

  // 3. Drag-to-Resize Split Pane Logic
  const resizer = document.getElementById("pane-resizer");
  const leftPane = document.getElementById("pane-left");
  let isResizing = false;

  resizer.addEventListener("mousedown", () => {
    isResizing = true;
    document.body.style.cursor = "col-resize";
  });

  document.addEventListener("mousemove", (e) => {
    if (!isResizing) return;
    const percentage = (e.clientX / window.innerWidth) * 100;
    if (percentage > 20 && percentage < 80) {
      leftPane.style.width = `${percentage}%`;
      fitAddon.fit();
      sendResize();
    }
  });

  document.addEventListener("mouseup", () => {
    if (isResizing) {
      isResizing = false;
      document.body.style.cursor = "default";
      fitAddon.fit();
      sendResize();
    }
  });

  // 4. PDF Discovery & Auto-Loading Logic
  const pdfSelect = document.getElementById("pdf-select");
  const pdfPreview = document.getElementById("pdf-preview");
  const pdfPlaceholder = document.getElementById("pdf-placeholder");
  const previousPage = document.getElementById("page-previous");
  const nextPage = document.getElementById("page-next");
  const pagePosition = document.getElementById("page-position");
  const openNativePreview = document.getElementById("open-native-preview");
  const mappedRegionsToggle = document.getElementById("mapped-regions-toggle");
  const synctexOverlay = document.getElementById("synctex-overlay");
  const synctexStatus = document.getElementById("status-synctex");
  const buildStatus = document.getElementById("status-build");
  const feedbackDialog = document.getElementById("feedback-dialog");
  const feedbackForm = document.getElementById("feedback-form");
  const feedbackText = document.getElementById("feedback-text");
  const feedbackComponent = document.getElementById("feedback-component");
  const feedbackFragment = document.getElementById("feedback-fragment");
  const feedbackSource = document.getElementById("feedback-source");
  const feedbackClose = document.getElementById("feedback-close");
  const feedbackCancel = document.getElementById("feedback-cancel");
  const feedbackEdit = document.getElementById("feedback-edit");
  const editorDialog = document.getElementById("editor-dialog");
  const editorForm = document.getElementById("editor-form");
  const editorSource = document.getElementById("editor-source");
  const editorContent = document.getElementById("editor-content");
  const editorStatus = document.getElementById("editor-status");
  const editorClose = document.getElementById("editor-close");
  const editorCancel = document.getElementById("editor-cancel");
  const editorSave = document.getElementById("editor-save");
  const appVersion = document.getElementById("app-version");
  const libraryName = document.getElementById("library-name");
  const openLibrary = document.getElementById("open-library");
  const openLibraryDialog = document.getElementById("open-library-dialog");
  const openLibraryForm = document.getElementById("open-library-form");
  const openLibraryPath = document.getElementById("open-library-path");
  const openLibraryError = document.getElementById("open-library-error");
  const openLibraryClose = document.getElementById("open-library-close");
  const openLibraryCancel = document.getElementById("open-library-cancel");
  const openLibrarySubmit = document.getElementById("open-library-submit");
  const recentLibraries = document.getElementById("recent-libraries");
  const createLibrary = document.getElementById("create-library");
  const importReference = document.getElementById("import-reference");
  const referenceFile = document.getElementById("reference-file");
  const referenceDialog = document.getElementById("reference-dialog");
  const referenceTitle = document.getElementById("reference-title");
  const referenceStatus = document.getElementById("reference-status");
  const referencePath = document.getElementById("reference-path");
  const libraryDialog = document.getElementById("library-dialog");
  const libraryForm = document.getElementById("library-form");
  const libraryParent = document.getElementById("library-parent");
  const libraryProjectName = document.getElementById("library-project-name");
  const libraryError = document.getElementById("library-error");
  const libraryClose = document.getElementById("library-close");
  const libraryCancel = document.getElementById("library-cancel");
  const librarySubmit = document.getElementById("library-submit");
  const startAgent = document.getElementById("start-agent");
  const agentStatus = document.getElementById("agent-status");
  const dictatePrompt = document.getElementById("dictate-prompt");
  const dictationDialog = document.getElementById("dictation-dialog");
  const dictationForm = document.getElementById("dictation-form");
  const dictationText = document.getElementById("dictation-text");
  const dictationClose = document.getElementById("dictation-close");
  const dictationCancel = document.getElementById("dictation-cancel");
  const starterPrompt = document.getElementById("starter-prompt");
  const placeholderTitle = document.getElementById("placeholder-title");
  const placeholderCopy = document.getElementById("placeholder-copy");
  const svgNamespace = "http://www.w3.org/2000/svg";
  let publicationsFingerprint = "";
  let publicationsRequestId = 0;
  let latestForcedPublicationsRequestId = 0;
  let publicationsByPath = new Map();
  let currentPublication = null;
  let currentSpatialIndex = null;
  let mappedRegionsVisible = false;
  let selectedFeedbackBox = null;
  let editorRevision = null;
  let editorOriginalContent = "";
  let refreshTimer = null;
  let mappingRequestId = 0;
  let previewBuildRequestId = 0;
  let currentPage = 1;
  let workspaceState = null;

  function updateDictationAvailability() {
    dictatePrompt.disabled = !workspaceState?.project || ws.readyState !== WebSocket.OPEN;
  }

  async function refreshWorkspace() {
    try {
      const response = await fetch("/api/workspace");
      if (!response.ok) throw new Error(`Workspace request failed: ${response.status}`);
      workspaceState = await response.json();
      appVersion.textContent = workspaceState.version || "unknown build";
      libraryName.textContent = workspaceState.project || "No library open";
      libraryName.title = workspaceState.root || "";
      importReference.disabled = !workspaceState.project;
      if (!libraryParent.value) libraryParent.value = workspaceState.default_parent || "";
      renderRecentLibraries(workspaceState.recent_libraries || []);

      const agent = workspaceState.agent || {};
      startAgent.textContent = `Start ${agent.label || "agent"}`;
      startAgent.disabled = !workspaceState.project || agent.available !== true;
      updateDictationAvailability();
      if (!workspaceState.project) {
        agentStatus.textContent = "Create or open a library first";
        placeholderTitle.textContent = "Open or create your authoring library";
        placeholderCopy.textContent =
          "Return to a recent library, open another MathPub repository, or create a private " +
          "library for many publications and reusable components.";
      } else if (agent.available === true) {
        agentStatus.textContent = `${agent.label} ready`;
        placeholderTitle.textContent = "Your authoring agent is ready";
        placeholderCopy.textContent =
          "Start the agent, then insert a first-book prompt or give it your own direction.";
      } else {
        agentStatus.textContent = `${agent.label || "Agent"} unavailable`;
        startAgent.title = `${agent.command || "Configured agent command"} was not found`;
        placeholderTitle.textContent = "No built PDF selected";
        placeholderCopy.textContent =
          "Configure an authoring agent or use the terminal to build a publication.";
      }
      updatePageControls();
    } catch (error) {
      agentStatus.textContent = "Workspace unavailable";
      agentStatus.title = error.message;
    }
  }

  function svgElement(name, attributes = {}) {
    const element = document.createElementNS(svgNamespace, name);
    Object.entries(attributes).forEach(([key, value]) => element.setAttribute(key, value));
    return element;
  }

  function openFeedbackDialog(box) {
    selectedFeedbackBox = box;
    feedbackComponent.textContent = box.component_id;
    feedbackFragment.textContent = box.fragment;
    feedbackSource.textContent = box.authored_source;
    feedbackText.value = "";
    feedbackDialog.showModal();
    feedbackText.focus();
  }

  function sourceFailureMessage(payload, status) {
    const lines = [payload.error || `Source request failed: ${status}`];
    const details = payload.details || {};
    if (details.command) lines.push(`Command: ${details.command}`);
    if (details.exit_status !== undefined) {
      lines.push(`Exit status: ${details.exit_status}`);
    }
    if (details.output) lines.push("", details.output);
    return lines.join("\n");
  }

  async function openSourceEditor() {
    if (!selectedFeedbackBox) return;
    const sourcePath = selectedFeedbackBox.authored_source;
    feedbackDialog.close();
    editorSource.textContent = sourcePath;
    editorContent.value = "";
    editorContent.disabled = true;
    editorStatus.classList.remove("error");
    editorStatus.textContent = "Loading source…";
    editorSave.disabled = true;
    editorDialog.showModal();
    try {
      const response = await fetch(`/api/source?path=${encodeURIComponent(sourcePath)}`);
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(sourceFailureMessage(payload, response.status));
      editorRevision = payload.source.revision;
      editorOriginalContent = payload.source.content;
      editorContent.value = editorOriginalContent;
      editorContent.disabled = false;
      editorStatus.textContent = "Source loaded";
      editorContent.focus();
    } catch (error) {
      editorRevision = null;
      editorStatus.classList.add("error");
      editorStatus.textContent = error.message;
    }
  }

  function mappingAvailable(publication) {
    return Boolean(
      publication?.publication_id &&
      publication?.variant &&
      publication?.projection &&
      publication?.synctex_ready === true
    );
  }

  function sendPreviewSelection() {
    if (ws.readyState !== WebSocket.OPEN || !currentPublication) return;
    if (
      !currentPublication.publication_path ||
      !currentPublication?.root_seed ||
      !currentPublication?.variant ||
      !currentPublication?.projection ||
      !currentPublication?.font_family
    ) {
      buildStatus.textContent = "Preview watch unavailable";
      buildStatus.title = "This PDF is missing reproducible build metadata";
      return;
    }
    buildStatus.textContent = "Starting preview watch…";
    ws.send(
      JSON.stringify({
        type: "watch-preview",
        publication_path: currentPublication.publication_path,
        root_seed: currentPublication.root_seed,
        variant: currentPublication.variant,
        projection: currentPublication.projection,
        font_family: currentPublication.font_family,
        page: currentPage,
        lesson_ids: currentPublication.lesson_ids || []
      })
    );
  }

  function handleWorkspaceEvent(message) {
    if (!message || typeof message.type !== "string") return false;
    if (message.type === "preview-watch-ready") {
      buildStatus.textContent = "Preview watching";
      buildStatus.title = "Authored component changes rebuild this PDF automatically";
      return true;
    }
    if (message.type === "preview-watch-failed") {
      buildStatus.textContent = "Preview watch unavailable";
      buildStatus.title = message.error || "";
      return true;
    }
    if (message.type === "preview-build-started") {
      buildStatus.textContent = "Rebuilding preview…";
      buildStatus.removeAttribute("title");
      return true;
    }
    if (message.type === "preview-build-failed") {
      buildStatus.textContent = "Preview build failed";
      buildStatus.title = message.error || "";
      return true;
    }
    if (message.type === "preview-built") {
      const buildRequestId = ++previewBuildRequestId;
      const cache = message.instance_cache || {};
      const reused =
        (cache.questions_reused || 0) + (cache.components_reused || 0);
      buildStatus.textContent = "Rendering preview…";
      buildStatus.removeAttribute("title");
      refreshPublications(message.path).then(() => {
        if (buildRequestId !== previewBuildRequestId) return;
        buildStatus.textContent = "Preview updated";
        buildStatus.title =
          `${message.duration_ms} ms; ${reused} instances reused; ` +
          `format: ${message.format || "none"}`;
      });
      return true;
    }
    if (message.type === "agent-started") {
      agentStatus.textContent = `${message.label || "Agent"} started`;
      startAgent.disabled = true;
      starterPrompt.disabled = false;
      term.focus();
      return true;
    }
    if (message.type === "agent-unavailable") {
      agentStatus.textContent = `${message.label || "Agent"} unavailable`;
      startAgent.disabled = true;
      return true;
    }
    if (message.type === "starter-prompt-inserted") {
      agentStatus.textContent = "First-book prompt ready";
      starterPrompt.disabled = true;
      term.focus();
      return true;
    }
    return false;
  }

  function updateMappingAvailability() {
    if (!currentPublication) {
      mappedRegionsToggle.disabled = true;
      mappedRegionsToggle.setAttribute("aria-pressed", "false");
      mappedRegionsToggle.textContent = "Show mapped regions";
      mappedRegionsToggle.removeAttribute("title");
      synctexStatus.textContent = "No mappings selected";
      synctexStatus.removeAttribute("title");
      return;
    }

    if (mappingAvailable(currentPublication)) {
      mappedRegionsToggle.disabled = !currentSpatialIndex;
      mappedRegionsToggle.setAttribute(
        "aria-pressed",
        mappedRegionsVisible ? "true" : "false"
      );
      mappedRegionsToggle.textContent = mappedRegionsVisible
        ? "Hide mapped regions"
        : "Show mapped regions";
      mappedRegionsToggle.title = mappedRegionsVisible
        ? "Hide persistent outlines; regions remain available on hover"
        : "Show all source regions; regions are already available on hover";
      synctexStatus.textContent = currentSpatialIndex
        ? mappedRegionsVisible
          ? `${currentSpatialIndex.boxes.length} regions mapped`
          : "SyncTeX Ready"
        : "Mapping regions…";
      synctexStatus.removeAttribute("title");
      return;
    }

    const details = [
      currentPublication.mapping_error,
      currentPublication.mapping_rebuild_command
        ? `Rebuild with: ${currentPublication.mapping_rebuild_command}`
        : null
    ].filter(Boolean).join("\n");
    mappedRegionsToggle.disabled = true;
    mappedRegionsToggle.setAttribute("aria-pressed", "false");
    mappedRegionsToggle.textContent = "Mappings need rebuild";
    mappedRegionsToggle.title = details;
    synctexStatus.textContent = "Rebuild PDF for mappings";
    synctexStatus.title = details;
  }

  function clearMappedRegions() {
    mappingRequestId += 1;
    mappedRegionsVisible = false;
    currentSpatialIndex = null;
    synctexOverlay.replaceChildren();
    synctexOverlay.classList.remove("show-all-regions");
    synctexOverlay.setAttribute("aria-hidden", "true");
    updateMappingAvailability();
  }

  function renderMappedRegions() {
    synctexOverlay.replaceChildren();
    if (!currentSpatialIndex || !pdfPreview.naturalWidth) return;

    const pageWidth = currentSpatialIndex.page_size.width;
    const pageHeight = currentSpatialIndex.page_size.height;
    const previewWidth = pdfPreview.clientWidth;
    const previewHeight = pdfPreview.clientHeight;
    const renderedScale = Math.min(
      previewWidth / pdfPreview.naturalWidth,
      previewHeight / pdfPreview.naturalHeight
    );
    const renderedWidth = pdfPreview.naturalWidth * renderedScale;
    const renderedHeight = pdfPreview.naturalHeight * renderedScale;
    const imageLeft = (previewWidth - renderedWidth) / 2;

    currentSpatialIndex.boxes.forEach((box) => {
      const left = Math.round(imageLeft + (box.x / pageWidth) * renderedWidth);
      const top = Math.round((box.y / pageHeight) * renderedHeight);
      const right = Math.round(
        imageLeft + ((box.x + box.w) / pageWidth) * renderedWidth
      );
      const bottom = Math.round(((box.y + box.h) / pageHeight) * renderedHeight);
      const width = right - left;
      const height = bottom - top;
      const labelTop = Math.max(0, top - 16);
      const labelWidth = Math.min(width, Math.round(box.component_id.length * 6.1 + 8));

      const region = svgElement("g", {
        class: "synctex-region",
        role: "button",
        tabindex: "0",
        "aria-label": `Review or edit ${box.component_id} ${box.fragment}`
      });
      region.dataset.componentId = box.component_id;
      region.dataset.fragment = box.fragment;

      const regionBox = svgElement("rect", {
        class: "synctex-region-box",
        x: left,
        y: top,
        width,
        height
      });
      regionBox.dataset.componentId = box.component_id;
      regionBox.dataset.fragment = box.fragment;
      region.appendChild(regionBox);

      region.appendChild(
        svgElement("rect", {
          class: "synctex-region-label-bg",
          x: left,
          y: labelTop,
          width: labelWidth,
          height: 16
        })
      );
      const label = svgElement("text", {
        class: "synctex-region-label",
        x: left + 4,
        y: labelTop + 11
      });
      label.textContent = box.component_id;
      region.appendChild(label);
      region.addEventListener("click", () => openFeedbackDialog(box));
      region.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          openFeedbackDialog(box);
        }
      });
      synctexOverlay.appendChild(region);
    });
  }

  async function loadMappedRegions() {
    if (!mappingAvailable(currentPublication)) return;
    const requestId = ++mappingRequestId;
    const publication = currentPublication;
    const page = currentPage;
    const params = new URLSearchParams({
      publication_id: publication.publication_id,
      variant: publication.variant,
      projection: publication.projection,
      page: String(page)
    });
    updateMappingAvailability();
    try {
      const response = await fetch(`/api/synctex/boxes?${params}`);
      if (!response.ok) {
        const payload = await response.json().catch(() => ({}));
        throw new Error(payload.error || `SyncTeX request failed: ${response.status}`);
      }
      const spatialIndex = await response.json();
      if (
        requestId !== mappingRequestId ||
        publication !== currentPublication ||
        page !== currentPage
      ) return;
      currentSpatialIndex = spatialIndex;
      synctexOverlay.setAttribute("aria-hidden", "false");
      renderMappedRegions();
      updateMappingAvailability();
    } catch (error) {
      if (requestId !== mappingRequestId || publication !== currentPublication) return;
      currentSpatialIndex = null;
      synctexOverlay.replaceChildren();
      synctexOverlay.setAttribute("aria-hidden", "true");
      synctexStatus.textContent = "SyncTeX error";
      synctexStatus.title = error.message;
      mappedRegionsToggle.title = error.message;
      mappedRegionsToggle.disabled = true;
    }
  }

  function setMappedRegionsVisible(visible) {
    if (!currentSpatialIndex) return;
    mappedRegionsVisible = visible;
    synctexOverlay.classList.toggle("show-all-regions", visible);
    updateMappingAvailability();
  }

  async function refreshPublications(forcePath = null) {
    const requestId = ++publicationsRequestId;
    if (forcePath) latestForcedPublicationsRequestId = requestId;
    try {
      const res = await fetch("/api/publications");
      if (!res.ok) return;
      const data = await res.json();
      if (!forcePath && requestId < latestForcedPublicationsRequestId) return;
      const pdfs = data.publications || [];
      publicationsByPath = new Map(pdfs.map((pdf) => [pdf.path, pdf]));
      const nextFingerprint = JSON.stringify(
        pdfs.map((pdf) => [
          pdf.path,
          pdf.publication_id,
          pdf.publication_path,
          pdf.root_seed,
          pdf.variant,
          pdf.projection,
          pdf.font_family,
          pdf.pages,
          pdf.lesson_ids,
          pdf.synctex_ready,
          pdf.mapping_error,
          pdf.mapping_rebuild_command
        ])
      );

      if (nextFingerprint !== publicationsFingerprint) {
        const currentSelection = pdfSelect.value;
        pdfSelect.innerHTML = '<option value="">-- Select Built PDF --</option>';

        pdfs.forEach((pdf) => {
          const opt = document.createElement("option");
          opt.value = pdf.path;
          opt.textContent = pdf.synctex_ready
            ? pdf.path
            : `${pdf.path} (rebuild for mappings)`;
          pdfSelect.appendChild(opt);
        });

        const selectedStillExists = publicationsByPath.has(currentSelection);
        const newestFirst = pdfs.slice().reverse();
        const preferred =
          newestFirst.find(
            (pdf) => mappingAvailable(pdf) && pdf.projection === "student"
          ) ||
          newestFirst.find((pdf) => mappingAvailable(pdf)) ||
          newestFirst[0];
        const selectedPath =
          forcePath && publicationsByPath.has(forcePath)
            ? forcePath
            : selectedStillExists
              ? currentSelection
              : preferred?.path || "";
        const shouldLoad =
          Boolean(forcePath) || selectedPath !== currentPublication?.path;
        pdfSelect.value = selectedPath;
        publicationsFingerprint = nextFingerprint;
        if (shouldLoad) {
          await loadPdf(selectedPath, forcePath ? Date.now() : null, !forcePath);
        } else {
          currentPublication = publicationsByPath.get(selectedPath) || null;
          updatePageControls();
          updateMappingAvailability();
        }
      } else if (forcePath && publicationsByPath.has(forcePath)) {
        pdfSelect.value = forcePath;
        await loadPdf(forcePath, Date.now(), false);
      }
    } catch (e) {
      // Ignore network errors during shutdown
    }
  }

  function pageCount() {
    const pages = Number(currentPublication?.pages || 1);
    return Number.isInteger(pages) && pages > 0 ? pages : 1;
  }

  function updatePageControls() {
    const nativeViewer = workspaceState?.native_pdf_viewer || {};
    if (!currentPublication) {
      pagePosition.textContent = "Page 0 of 0";
      previousPage.disabled = true;
      nextPage.disabled = true;
      openNativePreview.disabled = true;
      openNativePreview.title = "Select a built PDF first";
      return;
    }
    const pages = pageCount();
    pagePosition.textContent = `Page ${currentPage} of ${pages}`;
    previousPage.disabled = currentPage <= 1;
    nextPage.disabled = currentPage >= pages;
    openNativePreview.disabled = nativeViewer.available !== true;
    openNativePreview.title =
      nativeViewer.available === true
        ? `Open ${currentPublication.name || "this PDF"} in ${nativeViewer.label || "Preview"}`
        : "The native Preview application is available only on macOS";
  }

  async function loadPreviewPage(cacheBust = null, notifyWatcher = true) {
    clearMappedRegions();
    updatePageControls();
    if (!currentPublication) {
      pdfPreview.style.display = "none";
      pdfPlaceholder.style.display = "block";
      return;
    }
    const previewLoaded = new Promise((resolve) => {
      const finish = () => {
        pdfPreview.removeEventListener("load", finish);
        pdfPreview.removeEventListener("error", finish);
        resolve();
      };
      pdfPreview.addEventListener("load", finish);
      pdfPreview.addEventListener("error", finish);
    });
    const version = cacheBust ? `&version=${cacheBust}` : "";
    pdfPreview.src =
      `/api/pdf-preview?path=${encodeURIComponent(pdfSelect.value)}` +
      `&page=${currentPage}${version}`;
    pdfPreview.style.display = "block";
    pdfPlaceholder.style.display = "none";
    if (notifyWatcher) sendPreviewSelection();
    await previewLoaded;
    await loadMappedRegions();
  }

  function loadPdf(path, cacheBust = null, notifyWatcher = true) {
    const selectionChanged = path !== pdfSelect.value || currentPublication?.path !== path;
    currentPublication = publicationsByPath.get(path) || null;
    if (selectionChanged) currentPage = 1;
    return loadPreviewPage(cacheBust, notifyWatcher);
  }

  function showPage(page) {
    if (!currentPublication) return;
    const next = Math.max(1, Math.min(pageCount(), page));
    if (next === currentPage) return;
    currentPage = next;
    loadPreviewPage(null, true);
  }

  pdfSelect.addEventListener("change", (e) => {
    loadPdf(e.target.value);
  });

  previousPage.addEventListener("click", () => showPage(currentPage - 1));
  nextPage.addEventListener("click", () => showPage(currentPage + 1));
  openNativePreview.addEventListener("click", async () => {
    if (!currentPublication || openNativePreview.disabled) return;
    openNativePreview.disabled = true;
    openNativePreview.textContent = "Opening…";
    buildStatus.textContent = "Opening in Preview…";
    buildStatus.removeAttribute("title");
    try {
      const response = await fetch("/api/pdf/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: currentPublication.path })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(payload.error || `Preview request failed: ${response.status}`);
      }
      buildStatus.textContent = "Opened in Preview";
      buildStatus.title = currentPublication.path;
    } catch (error) {
      buildStatus.textContent = "Preview open failed";
      buildStatus.title = error.message;
    } finally {
      openNativePreview.textContent = "Open in Preview";
      updatePageControls();
    }
  });

  mappedRegionsToggle.addEventListener("click", () => {
    setMappedRegionsVisible(!mappedRegionsVisible);
  });

  function libraryFailureMessage(payload, status) {
    const lines = [payload.error || `Library creation failed: ${status}`];
    if (payload.code) lines.push(`Code: ${payload.code}`);
    const details = payload.details || {};
    if (details.stage) lines.push(`Stage: ${details.stage}`);
    if (details.command) lines.push(`Command: ${details.command}`);
    if (details.exit_status !== undefined) {
      lines.push(`Exit status: ${details.exit_status}`);
    }
    if (details.output) lines.push("", details.output);
    return lines.join("\n");
  }

  function renderRecentLibraries(libraries) {
    recentLibraries.replaceChildren();
    libraries.forEach((library) => {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "recent-library";
      button.dataset.path = library.path;

      const identity = document.createElement("span");
      const name = document.createElement("span");
      name.className = "recent-library-name";
      name.textContent = library.name;
      const path = document.createElement("span");
      path.className = "recent-library-path";
      path.textContent = library.path;
      identity.append(name, path);

      const action = document.createElement("span");
      action.className = "recent-library-action";
      action.textContent = "Open";
      button.append(identity, action);
      button.addEventListener("click", () => openLibraryAt(library.path));
      recentLibraries.appendChild(button);
    });
  }

  async function openLibraryAt(path) {
    openLibraryError.textContent = "";
    openLibraryPath.disabled = true;
    openLibrarySubmit.disabled = true;
    openLibrarySubmit.textContent = "Opening…";
    recentLibraries.querySelectorAll("button").forEach((button) => {
      button.disabled = true;
    });
    try {
      const response = await fetch("/api/libraries/open", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(libraryFailureMessage(payload, response.status));
      window.location.reload();
    } catch (error) {
      openLibraryError.textContent = error.message;
      openLibraryPath.disabled = false;
      openLibrarySubmit.disabled = false;
      openLibrarySubmit.textContent = "Open library";
      recentLibraries.querySelectorAll("button").forEach((button) => {
        button.disabled = false;
      });
    }
  }

  openLibrary.addEventListener("click", () => {
    openLibraryError.textContent = "";
    openLibraryPath.value = workspaceState?.root || "";
    openLibraryDialog.showModal();
    openLibraryPath.focus();
    openLibraryPath.select();
  });
  openLibraryClose.addEventListener("click", () => openLibraryDialog.close());
  openLibraryCancel.addEventListener("click", () => openLibraryDialog.close());
  openLibraryForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!openLibraryForm.reportValidity()) return;
    openLibraryAt(openLibraryPath.value.trim());
  });

  createLibrary.addEventListener("click", () => {
    libraryError.textContent = "";
    libraryDialog.showModal();
    libraryProjectName.focus();
  });
  libraryClose.addEventListener("click", () => libraryDialog.close());
  libraryCancel.addEventListener("click", () => libraryDialog.close());
  libraryForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!libraryForm.reportValidity()) return;
    libraryError.textContent = "";
    librarySubmit.disabled = true;
    librarySubmit.textContent = "Creating and pinning…";
    try {
      const response = await fetch("/api/libraries", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          parent: libraryParent.value.trim(),
          name: libraryProjectName.value.trim()
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(libraryFailureMessage(payload, response.status));
      libraryDialog.close();
      window.location.reload();
    } catch (error) {
      libraryError.textContent = error.message;
      librarySubmit.disabled = false;
      librarySubmit.textContent = "Create private library";
    }
  });

  importReference.addEventListener("click", () => {
    if (importReference.disabled) return;
    referenceFile.value = "";
    referenceFile.click();
  });
  referenceFile.addEventListener("change", async () => {
    const file = referenceFile.files?.[0];
    if (!file) return;

    referenceTitle.textContent = "Importing reference";
    referenceStatus.classList.remove("error");
    referenceStatus.textContent = `Copying and committing ${file.name}…`;
    referencePath.textContent = "";
    referenceDialog.showModal();
    importReference.disabled = true;
    try {
      const response = await fetch(
        `/api/references?filename=${encodeURIComponent(file.name)}`,
        {
          method: "POST",
          headers: { "Content-Type": "application/octet-stream" },
          body: file
        }
      );
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(sourceFailureMessage(payload, response.status));
      const imported = payload.reference;
      referenceTitle.textContent = "Reference imported";
      referenceStatus.textContent =
        "The file is committed in this library. You can now mention it in prompts to the agent.";
      referencePath.textContent = imported.path;
      referencePath.title = imported.commit ? `Git commit ${imported.commit.slice(0, 12)}` : "";
    } catch (error) {
      referenceTitle.textContent = "Reference import failed";
      referenceStatus.classList.add("error");
      referenceStatus.textContent = error.message;
      referencePath.textContent = file.name;
    } finally {
      referenceFile.value = "";
      importReference.disabled = !workspaceState?.project;
    }
  });

  startAgent.addEventListener("click", () => {
    if (ws.readyState !== WebSocket.OPEN || startAgent.disabled) return;
    startAgent.disabled = true;
    agentStatus.textContent = "Starting agent…";
    ws.send(JSON.stringify({ type: "start-agent" }));
  });

  function closeDictationDialog() {
    dictationDialog.close();
  }

  dictatePrompt.addEventListener("click", () => {
    if (dictatePrompt.disabled) return;
    dictationText.value = "";
    dictationDialog.showModal();
    dictationText.focus();
  });
  dictationClose.addEventListener("click", closeDictationDialog);
  dictationCancel.addEventListener("click", closeDictationDialog);
  dictationForm.addEventListener("submit", (event) => {
    event.preventDefault();
    if (ws.readyState !== WebSocket.OPEN) return;
    const prompt = dictationText.value.trim().replace(/\s*[\r\n]+\s*/g, " ");
    if (!prompt) return;
    ws.send(JSON.stringify({ type: "input", data: prompt }));
    dictationDialog.close();
    dictationText.value = "";
    term.focus();
  });

  starterPrompt.addEventListener("click", () => {
    if (ws.readyState !== WebSocket.OPEN || starterPrompt.disabled) return;
    ws.send(JSON.stringify({ type: "starter-prompt" }));
  });

  feedbackClose.addEventListener("click", () => feedbackDialog.close());
  feedbackCancel.addEventListener("click", () => feedbackDialog.close());
  feedbackEdit.addEventListener("click", openSourceEditor);
  feedbackForm.addEventListener("submit", (event) => {
    event.preventDefault();
    const feedback = feedbackText.value.trim();
    if (!selectedFeedbackBox || !feedback || ws.readyState !== WebSocket.OPEN) return;

    ws.send(
      JSON.stringify({
        type: "feedback",
        component_id: selectedFeedbackBox.component_id,
        fragment: selectedFeedbackBox.fragment,
        authored_source: selectedFeedbackBox.authored_source,
        feedback
      })
    );
    feedbackDialog.close();
    selectedFeedbackBox = null;
    synctexStatus.textContent = "Feedback inserted";
    term.focus();
  });
  feedbackDialog.addEventListener("close", () => {
    feedbackText.value = "";
  });

  function closeSourceEditor() {
    editorDialog.close();
  }

  editorClose.addEventListener("click", closeSourceEditor);
  editorCancel.addEventListener("click", closeSourceEditor);
  editorContent.addEventListener("input", () => {
    editorSave.disabled =
      !editorRevision || editorContent.value === editorOriginalContent;
    if (editorStatus.classList.contains("error")) {
      editorStatus.classList.remove("error");
      editorStatus.textContent = "";
    }
  });
  editorForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (
      !selectedFeedbackBox ||
      !editorRevision ||
      editorContent.value === editorOriginalContent
    ) return;

    editorContent.disabled = true;
    editorSave.disabled = true;
    editorSave.textContent = "Saving and committing…";
    editorStatus.classList.remove("error");
    editorStatus.textContent = "Saving source and creating a Git commit…";
    try {
      const response = await fetch("/api/source", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: selectedFeedbackBox.authored_source,
          content: editorContent.value,
          revision: editorRevision
        })
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(sourceFailureMessage(payload, response.status));
      const commit = payload.source.commit || "";
      editorDialog.close();
      synctexStatus.textContent = "Edit committed";
      synctexStatus.title = commit ? `Git commit ${commit.slice(0, 12)}` : "";
      selectedFeedbackBox = null;
    } catch (error) {
      editorContent.disabled = false;
      editorSave.disabled = false;
      editorStatus.classList.add("error");
      editorStatus.textContent = error.message;
    } finally {
      editorSave.textContent = "Save and commit";
    }
  });
  editorDialog.addEventListener("close", () => {
    editorRevision = null;
    editorOriginalContent = "";
    editorContent.value = "";
    editorContent.disabled = true;
    editorStatus.classList.remove("error");
    editorStatus.textContent = "";
    editorSave.disabled = true;
    editorSave.textContent = "Save and commit";
  });

  pdfPreview.addEventListener("load", renderMappedRegions);

  function schedulePubsRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshPublications, 1500);
  }

  // Initial publication load and periodic polling
  refreshWorkspace();
  refreshPublications();
  setInterval(refreshPublications, 5000);

  window.addEventListener("resize", renderMappedRegions);
});
