const overlay = document.getElementById("loading-overlay");
const loadingCopy = document.getElementById("loading-copy");

if (overlay) {
  overlay.hidden = true;
  overlay.classList.remove("is-visible");
}

for (const form of document.querySelectorAll("form[data-loading-copy]")) {
  form.addEventListener("submit", () => {
    if (!overlay || !loadingCopy) return;
    loadingCopy.textContent = form.dataset.loadingCopy || "Working...";
    overlay.hidden = false;
    overlay.classList.add("is-visible");
  });
}

for (const form of document.querySelectorAll("form[data-confirm]")) {
  form.addEventListener("submit", (event) => {
    const message = form.dataset.confirm || "Are you sure?";
    if (!window.confirm(message)) {
      event.preventDefault();
    }
  });
}

for (const row of document.querySelectorAll(".toggle-row, .decision-row")) {
  row.addEventListener("click", () => {
    const targetId = row.dataset.target;
    if (!targetId) return;
    const detailRow = document.getElementById(targetId);
    if (!detailRow) return;
    detailRow.hidden = !detailRow.hidden;
  });
}

const filterButtons = Array.from(document.querySelectorAll("[data-activity-filter]"));
const runFilter = document.getElementById("activity-run-filter");
const eventCards = Array.from(document.querySelectorAll(".event-card"));
let activeCategory = "all";

function applyActivityFilters() {
  if (!eventCards.length) return;
  const runValue = runFilter ? runFilter.value : "all";

  for (const card of eventCards) {
    const category = card.dataset.category || "system";
    const run = card.dataset.run || "";
    const categoryOk = activeCategory === "all" || category === activeCategory;
    const runOk = runValue === "all" || run === runValue;
    card.hidden = !(categoryOk && runOk);
  }
}

for (const button of filterButtons) {
  button.addEventListener("click", () => {
    activeCategory = button.dataset.activityFilter || "all";
    for (const candidate of filterButtons) {
      candidate.classList.toggle("is-active", candidate === button);
    }
    applyActivityFilters();
  });
}

if (runFilter) {
  runFilter.addEventListener("change", applyActivityFilters);
}

applyActivityFilters();

for (const zone of document.querySelectorAll(".upload-drop-zone")) {
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("dragover");
  });

  zone.addEventListener("dragleave", () => {
    zone.classList.remove("dragover");
  });

  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("dragover");
    const fileInput = zone.querySelector("input[type='file']");
    if (!fileInput || !event.dataTransfer || !event.dataTransfer.files) return;
    fileInput.files = event.dataTransfer.files;
  });
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text;
  return div.innerHTML;
}

function syntaxHighlightJson(text) {
  const escaped = escapeHtml(text);
  return escaped
    .replace(/("(?:\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"\s*:)/g, '<span class="json-key">$1</span>')
    .replace(/(:\s*)"([^"\\]*(?:\\.[^"\\]*)*)"/g, '$1<span class="json-string">"$2"</span>')
    .replace(/\b(true|false|null)\b/g, '<span class="json-bool">$1</span>')
    .replace(/\b(-?\d+(?:\.\d+)?)\b/g, '<span class="json-number">$1</span>');
}

function csvToTable(csv) {
  const lines = csv.trim().split(/\r?\n/).filter((line) => line.length > 0);
  if (!lines.length) return '<p class="subtle">Empty CSV file.</p>';

  const rows = lines.map((line) => line.split(","));
  let html = '<table class="csv-table"><thead><tr>';
  for (const header of rows[0]) {
    html += `<th>${escapeHtml(header)}</th>`;
  }
  html += "</tr></thead><tbody>";

  for (const row of rows.slice(1)) {
    html += "<tr>";
    for (const cell of row) {
      html += `<td>${escapeHtml(cell)}</td>`;
    }
    html += "</tr>";
  }
  html += "</tbody></table>";
  return html;
}

function simpleMarkdown(markdown) {
  return markdown
    .replace(/^### (.*$)/gim, "<h3>$1</h3>")
    .replace(/^## (.*$)/gim, "<h2>$1</h2>")
    .replace(/^# (.*$)/gim, "<h1>$1</h1>")
    .replace(/\*\*(.*?)\*\*/g, "<strong>$1</strong>")
    .replace(/\*(.*?)\*/g, "<em>$1</em>")
    .replace(/`(.*?)`/g, "<code>$1</code>")
    .replace(/\n/g, "<br>");
}

async function previewFile(path) {
  const panel = document.getElementById("preview-panel");
  const meta = document.getElementById("preview-meta");
  if (!panel) return;

  panel.innerHTML = '<p class="subtle">Loading preview...</p>';
  if (meta) meta.textContent = path;

  try {
    const resp = await fetch(`/files/preview?path=${encodeURIComponent(path)}`);
    const data = await resp.json();

    if (data.error) {
      panel.innerHTML = `<p class="error-text">${escapeHtml(data.error)}</p>`;
      return;
    }

    if (meta) {
      const size = typeof data.size === "number" ? `${Math.max(1, Math.round(data.size / 1024))} KB` : "";
      meta.textContent = `${data.path || path}${size ? ` · ${size}` : ""}`;
    }

    if (data.type === "json") {
      panel.innerHTML = `<pre class="json-preview">${syntaxHighlightJson(data.content || "")}</pre>`;
      return;
    }
    if (data.type === "csv") {
      panel.innerHTML = csvToTable(data.content || "");
      return;
    }
    if (data.type === "markdown") {
      panel.innerHTML = `<div class="md-preview">${data.html || simpleMarkdown(escapeHtml(data.content || ""))}</div>`;
      return;
    }

    panel.innerHTML = `<pre>${escapeHtml(data.content || "")}</pre>`;
  } catch (error) {
    panel.innerHTML = `<p class="error-text">Preview failed: ${escapeHtml(String(error))}</p>`;
  }
}

window.previewFile = previewFile;
