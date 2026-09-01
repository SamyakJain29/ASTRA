/**
 * ASTRA Mission Control Dashboard - Frontend Logic
 * Zero-dependency Canvas 2D Telemetry Charting & Interactive 4-Stage Judge Demo Controller
 */

const API_BASE = ""; // Relative URL for seamless FastAPI serving

const CHANNEL_COLORS = {
  channel_41: "#38bdf8", // Cyan
  channel_42: "#10b981", // Emerald
  channel_43: "#a855f7", // Violet
  channel_44: "#f59e0b", // Amber
  channel_45: "#f43f5e", // Rose
  channel_46: "#3b82f6", // Blue
};

let currentScenario = "normal";
let activeTab = "memory";

document.addEventListener("DOMContentLoaded", () => {
  initEventListeners();
  loadDashboard();
});

function initEventListeners() {
  document.querySelectorAll(".demo-btn[data-scenario]").forEach((btn) => {
    btn.addEventListener("click", () => {
      const scenario = btn.getAttribute("data-scenario");
      switchScenario(scenario);
    });
  });

  const resetBtn = document.getElementById("btn-reset-demo");
  if (resetBtn) {
    resetBtn.addEventListener("click", resetDemo);
  }

  const btnValid = document.getElementById("btn-validate-op");
  if (btnValid) {
    btnValid.addEventListener("click", () => sendFeedback("VALID_OPERATION"));
  }

  const btnAnomaly = document.getElementById("btn-confirm-anom");
  if (btnAnomaly) {
    btnAnomaly.addEventListener("click", () => sendFeedback("CONFIRMED_ANOMALY"));
  }

  document.querySelectorAll(".tab-btn").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll(".tab-btn").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      activeTab = btn.getAttribute("data-tab");
      renderTabContent();
    });
  });
}

async function loadDashboard() {
  await Promise.all([
    fetchSummary(),
    fetchAlert(),
    fetchTelemetry(),
    fetchMemory(),
    fetchStatistics(),
  ]);
}

async function switchScenario(scenarioName) {
  try {
    const res = await fetch(`${API_BASE}/api/demo/scenario/${scenarioName}`, { method: "POST" });
    if (res.ok) {
      currentScenario = scenarioName;
      updateActiveDemoButton(scenarioName);
      await loadDashboard();
    }
  } catch (err) {
    console.error("Failed to switch scenario:", err);
  }
}

async function resetDemo() {
  try {
    const res = await fetch(`${API_BASE}/api/demo/reset`, { method: "POST" });
    if (res.ok) {
      currentScenario = "normal";
      updateActiveDemoButton("normal");
      await loadDashboard();
    }
  } catch (err) {
    console.error("Failed to reset demo:", err);
  }
}

async function sendFeedback(label) {
  try {
    const res = await fetch(`${API_BASE}/api/feedback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_name: currentScenario, operator_label: label }),
    });
    if (res.ok) {
      alert(`Pattern stored into Adaptive Event Memory (${label})!`);
      await loadDashboard();
    }
  } catch (err) {
    console.error("Failed to submit feedback:", err);
  }
}

function updateActiveDemoButton(scenarioName) {
  document.querySelectorAll(".demo-btn[data-scenario]").forEach((btn) => {
    if (btn.getAttribute("data-scenario") === scenarioName) {
      btn.classList.add("active");
    } else {
      btn.classList.remove("active");
    }
  });
}

async function fetchSummary() {
  try {
    const res = await fetch(`${API_BASE}/api/mission/summary`);
    const data = await res.json();
    document.getElementById("sc-state-val").textContent = data.operational_state || "Nominal";
    document.getElementById("memory-count-badge").textContent = `${data.stored_memory_patterns_count} Patterns`;
  } catch (err) {
    console.error("Error fetching summary:", err);
  }
}

async function fetchAlert() {
  try {
    const res = await fetch(`${API_BASE}/api/alerts/current`);
    const alert = await res.json();

    // Update Status Pill
    const pill = document.getElementById("status-pill");
    const statusText = document.getElementById("status-text");
    pill.className = `status-pill ${getStatusClass(alert.status)}`;
    statusText.textContent = formatStatusText(alert.status);

    // Update Evidence Card
    document.getElementById("alert-category").textContent = alert.category || "Nominal";
    document.getElementById("alert-score").textContent = alert.unusualness_score.toFixed(2);
    document.getElementById("alert-tc-count").textContent = `${alert.recent_tc_count_5m} TCs (5m)`;
    document.getElementById("alert-explanation").textContent = alert.explanation;
    document.getElementById("alert-action").textContent = alert.recommended_action;

    // Update Similarity Card
    const simPct = (alert.similarity_score * 100).toFixed(1);
    document.getElementById("sim-val").textContent = `${simPct}%`;
    document.getElementById("sim-bar-fill").style.width = `${simPct}%`;

    const matchText = document.getElementById("nearest-match-desc");
    if (alert.nearest_pattern) {
      matchText.textContent = `Pattern: ${alert.nearest_pattern.memory_id} (Source: ${alert.nearest_pattern.source_event_id})`;
    } else {
      matchText.textContent = "No stored memory pattern matched (> 80.0% threshold)";
    }
  } catch (err) {
    console.error("Error fetching alert:", err);
  }
}

function getStatusClass(status) {
  switch (status) {
    case "NOMINAL":
      return "nominal";
    case "KNOWN_OPERATIONAL_PATTERN":
      return "recognized";
    case "UNKNOWN_UNUSUAL_EVENT":
      return "warning";
    case "CRITICAL_COMPONENT_ANOMALY":
      return "critical";
    default:
      return "nominal";
  }
}

function formatStatusText(status) {
  switch (status) {
    case "NOMINAL":
      return "Nominal Orbit Telemetry";
    case "KNOWN_OPERATIONAL_PATTERN":
      return "Recognized Operational Maneuver";
    case "UNKNOWN_UNUSUAL_EVENT":
      return "Unusual Telemetry Detected";
    case "CRITICAL_COMPONENT_ANOMALY":
      return "Critical Component Anomaly";
    default:
      return status;
  }
}

async function fetchTelemetry() {
  try {
    const res = await fetch(`${API_BASE}/api/telemetry`);
    const data = await res.json();
    const charts = data.telemetry_charts || {};

    for (let i = 41; i <= 46; i++) {
      const chKey = `channel_${i}`;
      const series = charts[chKey] || [];
      renderCanvasChart(`canvas-${chKey}`, series, CHANNEL_COLORS[chKey]);
    }
  } catch (err) {
    console.error("Error fetching telemetry:", err);
  }
}

function renderCanvasChart(canvasId, series, color) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const rect = canvas.getBoundingClientRect();
  canvas.width = rect.width * window.devicePixelRatio;
  canvas.height = rect.height * window.devicePixelRatio;
  ctx.scale(window.devicePixelRatio, window.devicePixelRatio);

  const width = rect.width;
  const height = rect.height;

  ctx.clearRect(0, 0, width, height);

  if (series.length < 2) return;

  const vals = series.map((s) => s.value);
  let minVal = Math.min(...vals);
  let maxVal = Math.max(...vals);
  if (minVal === maxVal) {
    minVal -= 1.0;
    maxVal += 1.0;
  }
  const pad = (maxVal - minVal) * 0.1;
  minVal -= pad;
  maxVal += pad;

  // Grid lines
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  for (let y = 10; y < height; y += 30) {
    ctx.beginPath();
    ctx.moveTo(0, y);
    ctx.lineTo(width, y);
    ctx.stroke();
  }

  // Draw telemetry line
  ctx.beginPath();
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;

  series.forEach((pt, idx) => {
    const x = (idx / (series.length - 1)) * width;
    const y = height - ((pt.value - minVal) / (maxVal - minVal)) * height;
    if (idx === 0) {
      ctx.moveTo(x, y);
    } else {
      ctx.lineTo(x, y);
    }
  });
  ctx.stroke();

  // Fill gradient underneath
  const lastX = width;
  const lastY = height - ((series[series.length - 1].value - minVal) / (maxVal - minVal)) * height;
  ctx.lineTo(lastX, height);
  ctx.lineTo(0, height);
  ctx.closePath();

  const gradient = ctx.createLinearGradient(0, 0, 0, height);
  gradient.addColorStop(0, hexToRgba(color, 0.2));
  gradient.addColorStop(1, hexToRgba(color, 0.0));
  ctx.fillStyle = gradient;
  ctx.fill();
}

function hexToRgba(hex, alpha) {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

let cachedMemory = [];
let cachedStats = null;

async function fetchMemory() {
  try {
    const res = await fetch(`${API_BASE}/api/memory`);
    const data = await res.json();
    cachedMemory = data.memories || [];
    if (activeTab === "memory") renderTabContent();
  } catch (err) {
    console.error("Error fetching memory:", err);
  }
}

async function fetchStatistics() {
  try {
    const res = await fetch(`${API_BASE}/api/statistics`);
    cachedStats = await res.json();
    if (activeTab === "ablation") renderTabContent();
  } catch (err) {
    console.error("Error fetching statistics:", err);
  }
}

function renderTabContent() {
  const container = document.getElementById("tab-content");
  if (!container) return;

  if (activeTab === "memory") {
    if (cachedMemory.length === 0) {
      container.innerHTML = `
        <div style="text-align:center; padding: 2rem; color: var(--text-muted);">
          Adaptive Event Memory is currently empty. Run Stage 2 ("Validate Operation & Learn") to store your first operational pattern.
        </div>`;
      return;
    }

    let rowsHtml = cachedMemory
      .map(
        (m) => `
      <tr>
        <td style="color:var(--color-accent);">${m.memory_id}</td>
        <td>${m.source_event_id}</td>
        <td><span class="brand-badge">${m.operator_label}</span></td>
        <td>${(m.affected_channels || []).join(", ") || "channel_41..46"}</td>
        <td>${m.creation_timestamp}</td>
      </tr>`
      )
      .join("");

    container.innerHTML = `
      <table class="custom-table">
        <thead>
          <tr>
            <th>Memory ID</th>
            <th>Source Event</th>
            <th>Operator Label</th>
            <th>Channels</th>
            <th>Creation Date</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>`;
  } else if (activeTab === "ablation") {
    if (!cachedStats) return;
    const ab = cachedStats.context_ablation_summary || {};
    container.innerHTML = `
      <div class="stats-grid">
        <div class="glass-card stat-card">
          <div class="stat-num">${cachedStats.rare_event_alarm_reduction_pct}%</div>
          <div class="metric-label">Rare Event Alarm Reduction</div>
          <div class="btn-sub">36 baseline alarms -> 5 after memory</div>
        </div>
        <div class="glass-card stat-card">
          <div class="stat-num">${cachedStats.genuine_anomaly_recall_pct}%</div>
          <div class="metric-label">Genuine Anomaly Recall</div>
          <div class="btn-sub">25 / 29 genuine anomalies detected</div>
        </div>
        <div class="glass-card stat-card">
          <div class="stat-num" style="color:var(--color-nominal);">+13.8%</div>
          <div class="metric-label">Telecommand Safety Impact</div>
          <div class="btn-sub">${ab.context_safety_impact || ""}</div>
        </div>
      </div>`;
  }
}
