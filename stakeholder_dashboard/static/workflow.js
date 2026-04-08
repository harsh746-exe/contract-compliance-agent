/**
 * Render the MCP audit log as a lightweight swim-lane diagram.
 */
(function () {
  const data = window.__workflowData;
  if (!data) return;

  const container = document.getElementById("workflow-swim-lanes");
  if (!container) return;

  const agents = data.agents || [];
  const messages = data.messages || [];
  if (!agents.length || !messages.length) {
    container.innerHTML = "<p class='empty-copy'>No audit log was available for this run.</p>";
    return;
  }

  const COL_WIDTH = 170;
  const ROW_HEIGHT = 48;
  const HEADER_HEIGHT = 70;
  const PADDING = 24;
  const agentIndex = {};
  agents.forEach((agent, index) => {
    agentIndex[agent] = index;
  });

  const svgWidth = agents.length * COL_WIDTH + PADDING * 2;
  const svgHeight = messages.length * ROW_HEIGHT + HEADER_HEIGHT + PADDING * 2;

  const typeColors = {
    spawn: "#10b981",
    terminate: "#6b7280",
    goal: "#3b82f6",
    result: "#8b5cf6",
    tool_call: "#f59e0b",
    tool_result: "#f97316",
    status: "#94a3b8",
    error: "#b91c1c",
  };

  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${svgWidth} ${svgHeight}`);
  svg.setAttribute("width", "100%");
  svg.classList.add("workflow-svg");

  const defs = document.createElementNS("http://www.w3.org/2000/svg", "defs");
  Object.entries(typeColors).forEach(([type, color]) => {
    const marker = document.createElementNS("http://www.w3.org/2000/svg", "marker");
    marker.setAttribute("id", `arrow-${type}`);
    marker.setAttribute("viewBox", "0 0 10 10");
    marker.setAttribute("refX", "9");
    marker.setAttribute("refY", "5");
    marker.setAttribute("markerWidth", "8");
    marker.setAttribute("markerHeight", "8");
    marker.setAttribute("orient", "auto-start-reverse");

    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", "M 0 0 L 10 5 L 0 10 z");
    path.setAttribute("fill", color);
    marker.appendChild(path);
    defs.appendChild(marker);
  });
  svg.appendChild(defs);

  agents.forEach((agent, index) => {
    const x = PADDING + index * COL_WIDTH + COL_WIDTH / 2;

    const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
    label.setAttribute("x", x);
    label.setAttribute("y", 28);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "11");
      label.setAttribute("font-weight", "700");
      label.setAttribute("fill", "#e2e8f0");
    label.textContent = agent.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
    svg.appendChild(label);

    const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
    line.setAttribute("x1", x);
    line.setAttribute("y1", HEADER_HEIGHT);
    line.setAttribute("x2", x);
    line.setAttribute("y2", svgHeight - PADDING);
      line.setAttribute("stroke", "#475569");
    line.setAttribute("stroke-width", "1");
    line.setAttribute("stroke-dasharray", "4,4");
    svg.appendChild(line);
  });

  messages.forEach((message, index) => {
    const y = HEADER_HEIGHT + PADDING + index * ROW_HEIGHT;
    const color = typeColors[message.type] || "#94a3b8";
    const senderAgent = String(message.sender || "").startsWith("skill:") ? null : message.sender;
    const recipientAgent = String(message.recipient || "").startsWith("skill:") ? null : message.recipient;
    const senderIdx = senderAgent != null ? agentIndex[senderAgent] : undefined;
    const recipientIdx = recipientAgent != null ? agentIndex[recipientAgent] : undefined;

    if (senderIdx !== undefined && recipientIdx !== undefined && senderIdx !== recipientIdx) {
      const x1 = PADDING + senderIdx * COL_WIDTH + COL_WIDTH / 2;
      const x2 = PADDING + recipientIdx * COL_WIDTH + COL_WIDTH / 2;

      const line = document.createElementNS("http://www.w3.org/2000/svg", "line");
      line.setAttribute("x1", x1);
      line.setAttribute("y1", y);
      line.setAttribute("x2", x2);
      line.setAttribute("y2", y);
      line.setAttribute("stroke", color);
      line.setAttribute("stroke-width", "2");
      line.setAttribute("marker-end", `url(#arrow-${message.type})`);
      line.dataset.messageIndex = String(index);
      svg.appendChild(line);

      const labelX = (x1 + x2) / 2;
      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", labelX);
      label.setAttribute("y", y - 8);
      label.setAttribute("text-anchor", "middle");
      label.setAttribute("font-size", "9");
      label.setAttribute("fill", color);
      label.textContent = message.type;
      label.dataset.messageIndex = String(index);
      svg.appendChild(label);
    } else {
      const anchorAgent = senderAgent || recipientAgent;
      const laneIndex = agentIndex[anchorAgent];
      if (laneIndex === undefined) return;

      const cx = PADDING + laneIndex * COL_WIDTH + COL_WIDTH / 2;
      const circle = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      circle.setAttribute("cx", cx);
      circle.setAttribute("cy", y);
      circle.setAttribute("r", "5");
      circle.setAttribute("fill", color);
      circle.dataset.messageIndex = String(index);
      svg.appendChild(circle);

      const label = document.createElementNS("http://www.w3.org/2000/svg", "text");
      label.setAttribute("x", cx + 10);
      label.setAttribute("y", y + 4);
      label.setAttribute("font-size", "9");
      label.setAttribute("fill", "#94a3b8");
      label.textContent =
        message.type === "tool_call"
          ? String(message.recipient || "").replace("skill:", "")
          : message.type === "tool_result"
            ? String(message.sender || "").replace("skill:", "")
            : message.type;
      label.dataset.messageIndex = String(index);
      svg.appendChild(label);
    }
  });

  svg.addEventListener("click", (event) => {
    const node = event.target.closest("[data-message-index]");
    if (!node) return;
    const message = messages[Number(node.dataset.messageIndex)];
    if (!message) return;

    const detail = document.getElementById("message-detail");
    if (!detail) return;

    const color = typeColors[message.type] || "#94a3b8";
    detail.innerHTML = `
      <div class="msg-detail-card">
        <div class="msg-detail-type" style="color: ${color}">${String(message.type || "").toUpperCase()}</div>
        <div class="msg-detail-flow">${message.sender} → ${message.recipient}</div>
        <div class="msg-detail-time">${message.timestamp || "n/a"}</div>
        <div class="msg-detail-phase">Phase: ${message.phase || "n/a"}</div>
        <div class="msg-detail-keys">Payload: ${(message.payload_keys || []).join(", ") || "none"}</div>
        ${message.correlation_id ? `<div class="msg-detail-corr">Correlation: ${message.correlation_id}</div>` : ""}
        <div class="msg-detail-desc">${message.display ? message.display[0] : ""}</div>
        <div class="msg-detail-comment">${message.display ? message.display[1] : ""}</div>
      </div>
    `;
    detail.hidden = false;
  });

  container.appendChild(svg);
})();
