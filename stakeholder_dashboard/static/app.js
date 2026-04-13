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

const notificationShell = document.getElementById("notification-shell");
const notificationPanel = document.getElementById("notification-panel");
const notificationTrigger = document.getElementById("notification-trigger");
const chatShell = document.getElementById("chat-shell");
const chatWindow = document.getElementById("chat-window");
const chatTrigger = document.getElementById("chat-trigger");
const chatTriggerLabel = document.getElementById("chat-trigger-label");
const chatInput = document.getElementById("chat-input");
const chatMessages = document.getElementById("chat-messages");

function setNotificationOpenState(isOpen) {
  if (!notificationPanel) return;
  notificationPanel.classList.toggle("is-open", isOpen);
  if (notificationShell) {
    notificationShell.classList.toggle("is-open", isOpen);
  }
  if (notificationTrigger) {
    notificationTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
  }
}

function closeNotifications() {
  setNotificationOpenState(false);
}

function setChatOpenState(isOpen) {
  if (!chatWindow) return;
  chatWindow.classList.toggle("is-open", isOpen);
  if (chatShell) {
    chatShell.classList.toggle("is-open", isOpen);
  }
  if (chatTrigger) {
    chatTrigger.setAttribute("aria-expanded", isOpen ? "true" : "false");
    chatTrigger.setAttribute("aria-label", isOpen ? "Close assistant chat" : "Open assistant chat");
  }
  if (chatTriggerLabel) {
    chatTriggerLabel.textContent = isOpen ? "Hide assistant chat" : "Open assistant chat";
  }
}

function toggleNotifications(event) {
  if (event) event.stopPropagation();
  if (!notificationPanel) return;
  const shouldOpen = !notificationPanel.classList.contains("is-open");
  if (shouldOpen) {
    toggleChat(false);
  }
  setNotificationOpenState(shouldOpen);
}

if (notificationTrigger && notificationTrigger.tagName !== "BUTTON") {
  notificationTrigger.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" && event.key !== " ") return;
    event.preventDefault();
    toggleNotifications(event);
  });
}

function toggleChat(forceState) {
  if (!chatWindow) return;
  const shouldOpen =
    typeof forceState === "boolean" ? forceState : !chatWindow.classList.contains("is-open");
  if (shouldOpen) {
    closeNotifications();
  }
  setChatOpenState(shouldOpen);
  if (shouldOpen && chatInput) {
    chatInput.focus();
  }
}

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Node)) return;

  if (notificationPanel && notificationPanel.classList.contains("is-open")) {
    if (!notificationShell || !notificationShell.contains(target)) {
      closeNotifications();
    }
  }

  if (chatWindow && chatWindow.classList.contains("is-open")) {
    if (!chatShell || !chatShell.contains(target)) {
      toggleChat(false);
    }
  }
});

document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  closeNotifications();
  toggleChat(false);
});

setNotificationOpenState(false);
setChatOpenState(false);

function appendChatBubble(role, text, extraClass = "") {
  if (!chatMessages) return null;
  const bubble = document.createElement("div");
  bubble.className = `chat-bubble ${role}${extraClass ? ` ${extraClass}` : ""}`;
  bubble.textContent = text;
  chatMessages.appendChild(bubble);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return bubble;
}

async function sendChat() {
  if (!chatInput || !chatMessages) return;
  const q = chatInput.value.trim();
  if (!q) return;

  appendChatBubble("user", q);
  chatInput.value = "";
  chatInput.disabled = true;

  const thinking = appendChatBubble("thinking", "Thinking...");
  try {
    const resp = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question: q }),
    });
    const data = await resp.json();
    if (thinking) thinking.remove();
    appendChatBubble("assistant", data.answer || "I could not generate an answer.");
  } catch (_error) {
    if (thinking) thinking.remove();
    appendChatBubble("assistant", "Sorry, I could not process that. Please try again.");
  } finally {
    chatInput.disabled = false;
    if (chatWindow && chatWindow.classList.contains("is-open")) {
      chatInput.focus();
    }
    chatMessages.scrollTop = chatMessages.scrollHeight;
  }
}

window.previewFile = previewFile;
window.toggleNotifications = toggleNotifications;
window.toggleChat = toggleChat;
window.sendChat = sendChat;
