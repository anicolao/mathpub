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
  };

  ws.onmessage = (event) => {
    if (typeof event.data === "string") {
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
  let knownPdfs = new Set();
  let refreshTimer = null;

  async function refreshPublications() {
    try {
      const res = await fetch("/api/publications");
      if (!res.ok) return;
      const data = await res.json();
      const pdfs = data.publications || [];

      let currentSelection = pdfSelect.value;
      let hasChanged = pdfs.length !== knownPdfs.size;

      if (hasChanged) {
        pdfSelect.innerHTML = '<option value="">-- Select Built PDF --</option>';
        knownPdfs.clear();

        pdfs.forEach((pdf) => {
          knownPdfs.add(pdf.path);
          const opt = document.createElement("option");
          opt.value = pdf.path;
          opt.textContent = `${pdf.path}`;
          pdfSelect.appendChild(opt);
        });

        // Auto-select latest PDF if none selected or new build appeared
        if (pdfs.length > 0) {
          const latestPath = pdfs[pdfs.length - 1].path;
          pdfSelect.value = latestPath;
          loadPdf(latestPath);
        }
      }
    } catch (e) {
      // Ignore network errors during shutdown
    }
  }

  function loadPdf(path) {
    if (!path) {
      pdfPreview.style.display = "none";
      pdfPlaceholder.style.display = "block";
      return;
    }
    pdfPreview.src = `/api/pdf-preview?path=${encodeURIComponent(path)}`;
    pdfPreview.style.display = "block";
    pdfPlaceholder.style.display = "none";
  }

  pdfSelect.addEventListener("change", (e) => {
    loadPdf(e.target.value);
  });

  function schedulePubsRefresh() {
    if (refreshTimer) clearTimeout(refreshTimer);
    refreshTimer = setTimeout(refreshPublications, 1500);
  }

  // Initial publication load and periodic polling
  refreshPublications();
  setInterval(refreshPublications, 5000);
});
