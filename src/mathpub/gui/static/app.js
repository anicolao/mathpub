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
  const svgNamespace = "http://www.w3.org/2000/svg";
  let publicationsFingerprint = "";
  let publicationsRequestId = 0;
  let latestForcedPublicationsRequestId = 0;
  let publicationsByPath = new Map();
  let currentPublication = null;
  let currentSpatialIndex = null;
  let mappedRegionsVisible = false;
  let selectedFeedbackBox = null;
  let refreshTimer = null;
  let mappingRequestId = 0;
  let currentPage = 1;

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
      const cache = message.instance_cache || {};
      const reused =
        (cache.questions_reused || 0) + (cache.components_reused || 0);
      buildStatus.textContent = "Preview updated";
      buildStatus.title =
        `${message.duration_ms} ms; ${reused} instances reused; ` +
        `format: ${message.format || "none"}`;
      refreshPublications(message.path);
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
        "aria-label": `Add feedback for ${box.component_id} ${box.fragment}`
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
          loadPdf(selectedPath, forcePath ? Date.now() : null, !forcePath);
        } else {
          currentPublication = publicationsByPath.get(selectedPath) || null;
          updatePageControls();
          updateMappingAvailability();
        }
      } else if (forcePath && publicationsByPath.has(forcePath)) {
        pdfSelect.value = forcePath;
        loadPdf(forcePath, Date.now(), false);
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
    if (!currentPublication) {
      pagePosition.textContent = "Page 0 of 0";
      previousPage.disabled = true;
      nextPage.disabled = true;
      return;
    }
    const pages = pageCount();
    pagePosition.textContent = `Page ${currentPage} of ${pages}`;
    previousPage.disabled = currentPage <= 1;
    nextPage.disabled = currentPage >= pages;
  }

  function loadPreviewPage(cacheBust = null, notifyWatcher = true) {
    clearMappedRegions();
    updatePageControls();
    if (!currentPublication) {
      pdfPreview.style.display = "none";
      pdfPlaceholder.style.display = "block";
      return;
    }
    const version = cacheBust ? `&version=${cacheBust}` : "";
    pdfPreview.src =
      `/api/pdf-preview?path=${encodeURIComponent(pdfSelect.value)}` +
      `&page=${currentPage}${version}`;
    pdfPreview.style.display = "block";
    pdfPlaceholder.style.display = "none";
    loadMappedRegions();
    if (notifyWatcher) sendPreviewSelection();
  }

  function loadPdf(path, cacheBust = null, notifyWatcher = true) {
    const selectionChanged = path !== pdfSelect.value || currentPublication?.path !== path;
    currentPublication = publicationsByPath.get(path) || null;
    if (selectionChanged) currentPage = 1;
    loadPreviewPage(cacheBust, notifyWatcher);
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

  mappedRegionsToggle.addEventListener("click", () => {
    setMappedRegionsVisible(!mappedRegionsVisible);
  });

  feedbackClose.addEventListener("click", () => feedbackDialog.close());
  feedbackCancel.addEventListener("click", () => feedbackDialog.close());
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

  pdfPreview.addEventListener("load", renderMappedRegions);

  function schedulePubsRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshPublications, 1500);
  }

  // Initial publication load and periodic polling
  refreshPublications();
  setInterval(refreshPublications, 5000);

  window.addEventListener("resize", renderMappedRegions);
});
