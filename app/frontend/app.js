/* ASTRA Spacecraft Operations Intelligence Platform — Core Application Logic */

// Global State
let activeNav = "global";
let currentScenario = "normal";
let selectedNoradId = 25544;
let catalogStates = [];
let telemetryChartsData = {};

// Coastline Coordinates for 2D Map Rendering
const CONTINENT_OUTLINES = [
  [[-130, 50], [-120, 60], [-80, 60], [-60, 45], [-80, 25], [-105, 20], [-120, 35], [-130, 50]],
  [[-80, 10], [-50, -5], [-35, -10], [-55, -50], [-75, -45], [-80, 10]],
  [[-10, 35], [30, 30], [50, 15], [80, 10], [120, 25], [140, 55], [100, 70], [30, 70], [-10, 60], [-10, 35]],
  [[10, 35], [50, 30], [40, 0], [50, -30], [20, -35], [0, 5], [10, 35]],
  [[115, -15], [150, -15], [150, -35], [115, -35], [115, -15]]
];

document.addEventListener("DOMContentLoaded", () => {
  startClock();
  fetchGlobalSummary();
  fetchGlobalStates();
  fetchScenarioData("normal");
  fetchDataSourcesStatus();

  // Periodic Refresh
  setInterval(fetchGlobalStates, 2000);
});

function startClock() {
  setInterval(() => {
    document.getElementById("sys-clock").innerText = new Date().toISOString();
  }, 1000);
}

// 6-Tab Product Navigation
function switchNav(nav) {
  activeNav = nav;
  document.querySelectorAll(".workspace").forEach(w => w.classList.remove("active"));
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));

  document.getElementById(`workspace-${nav}`).classList.add("active");
  document.getElementById(`tab-btn-${nav}`).classList.add("active");

  if (nav === "global") {
    fetchGlobalStates();
  } else if (nav === "fleet") {
    fetchFleetData();
  } else if (nav === "sources") {
    fetchDataSourcesStatus();
  }
}

function openSpacecraftView(spacecraftId) {
  switchNav("spacecraft");
}

// ==================== 1. GLOBAL ORBITAL AWARENESS ==================== //

async function fetchGlobalSummary() {
  try {
    const res = await fetch("/api/v1/global/summary");
    const data = await res.json();

    document.getElementById("kpi-total-obj").innerText = data.total_catalog_objects || 0;
    document.getElementById("kpi-active-obj").innerText = data.active_spacecraft_count || 0;
    document.getElementById("reg-leo-count").innerText = `${data.orbit_regimes.LEO || 0} Objects`;
    document.getElementById("reg-auth-count").innerText = `${data.authorized_telemetry_spacecraft_count || 0} Spacecraft`;
  } catch (err) {
    console.error("Error fetching global summary:", err);
  }
}

async function fetchGlobalStates() {
  try {
    const res = await fetch("/api/v1/global/states");
    const data = await res.json();
    catalogStates = data.states || [];
    renderGlobalOrbitMap();
    updateSelectedObjectCard();
  } catch (err) {
    console.error("Error fetching global states:", err);
  }
}

function onGlobalSearch(query) {
  if (!query) return;
  const q = query.toLowerCase();
  const found = catalogStates.find(s => s.name.toLowerCase().includes(q) || String(s.norad_id).includes(q));
  if (found) {
    selectedNoradId = found.norad_id;
    renderGlobalOrbitMap();
    updateSelectedObjectCard();
  }
}

function updateSelectedObjectCard() {
  const objState = catalogStates.find(s => s.norad_id === selectedNoradId) || catalogStates[0];
  if (!objState) return;

  document.getElementById("sel-obj-name").innerText = objState.name;
  document.getElementById("sel-norad-id").innerText = objState.norad_id;
  document.getElementById("sel-cospar-id").innerText = objState.norad_id === 25544 ? "1998-067A" : (objState.norad_id === 44804 ? "2019-089A" : "2022-013A");
  document.getElementById("sel-obj-type").innerText = objState.type || "ACTIVE_SPACECRAFT";
  document.getElementById("sel-orbit-regime").innerText = objState.regime || "LEO";
  document.getElementById("sel-lat").innerText = `${(objState.lat || 0).toFixed(4)}° N`;
  document.getElementById("sel-lon").innerText = `${(objState.lon || 0).toFixed(4)}° E`;
  document.getElementById("sel-alt").innerText = `${(objState.alt_km || 0).toFixed(1)} km`;
  document.getElementById("sel-speed").innerText = `${(objState.vel_kms || 0).toFixed(3)} km/s`;
  document.getElementById("sel-epoch").innerText = new Date().toISOString();
  document.getElementById("sel-age").innerText = `${(objState.age_h || 1.2).toFixed(1)} hrs`;

  const authElem = document.getElementById("sel-tm-auth");
  if (objState.norad_id === 25544 || objState.name.includes("ISS")) {
    authElem.innerText = "AUTHORIZED (ESA MISSION-1)";
    authElem.style.color = "var(--color-nominal)";
  } else {
    authElem.innerText = "NO TELEMETRY SOURCE";
    authElem.style.color = "var(--text-muted)";
  }
}

function renderGlobalOrbitMap() {
  const canvas = document.getElementById("global-map-canvas");
  if (!canvas) return;

  const ctx = canvas.getContext("2d");
  const width = canvas.parentElement.clientWidth;
  const height = canvas.parentElement.clientHeight;
  canvas.width = width;
  canvas.height = height;

  ctx.fillStyle = "#040608";
  ctx.fillRect(0, 0, width, height);

  function toCanvasCoords(lat, lon) {
    const x = ((lon + 180) / 360) * width;
    const y = ((90 - lat) / 180) * height;
    return [x, y];
  }

  // 30 deg grid
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  for (let lon = -180; lon <= 180; lon += 30) {
    const [x] = toCanvasCoords(0, lon);
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
  }
  for (let lat = -90; lat <= 90; lat += 30) {
    const [, y] = toCanvasCoords(lat, 0);
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
  }

  // Continents
  ctx.strokeStyle = "rgba(255, 255, 255, 0.12)";
  ctx.fillStyle = "rgba(255, 255, 255, 0.02)";
  CONTINENT_OUTLINES.forEach(poly => {
    ctx.beginPath();
    poly.forEach(([lon, lat], i) => {
      const [x, y] = toCanvasCoords(lat, lon);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath(); ctx.fill(); ctx.stroke();
  });

  // Plot Objects
  catalogStates.forEach(st => {
    const [x, y] = toCanvasCoords(st.lat, st.lon);
    const isSelected = st.norad_id === selectedNoradId;

    ctx.fillStyle = isSelected ? "#ffab00" : "#00e5ff";
    ctx.beginPath();
    ctx.arc(x, y, isSelected ? 6 : 4, 0, 2 * Math.PI);
    ctx.fill();

    if (isSelected) {
      ctx.strokeStyle = "#ffab00";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x - 10, y); ctx.lineTo(x + 10, y);
      ctx.moveTo(x, y - 10); ctx.lineTo(x, y + 10);
      ctx.stroke();

      ctx.fillStyle = "#e6e8eb";
      ctx.font = '700 11px "JetBrains Mono"';
      ctx.fillText(st.name, x + 12, y - 4);
    }
  });
}

// ==================== 2. AUTHORIZED FLEET ==================== //

async function fetchFleetData() {
  try {
    const res = await fetch("/api/v1/fleet");
    const data = await res.json();
    const tbody = document.getElementById("fleet-table-body");
    tbody.innerHTML = data.spacecraft.map(sc => `
      <tr>
        <td style="font-family: var(--font-mono); color: var(--color-accent); font-weight: 700;">${sc.spacecraft_id}</td>
        <td style="font-weight: 600;">${sc.name}</td>
        <td>${sc.agency}</td>
        <td><span class="status-badge nominal">${sc.telemetry_stream_status}</span></td>
        <td style="font-family: var(--font-mono);">${sc.monitored_parameters_count} PARAMETERS</td>
        <td><span style="color: var(--color-nominal); font-weight: 600;">ACTIVE (ANOMALY GUARD)</span></td>
        <td><button class="op-btn" onclick="openSpacecraftView('${sc.spacecraft_id}')">INSPECT HEALTH</button></td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Error fetching fleet:", err);
  }
}

// ==================== 3. SPACECRAFT HEALTH & OPERATIONS ==================== //

async function setScenario(name) {
  currentScenario = name;
  document.querySelectorAll(".scenario-btn").forEach(b => b.classList.remove("active"));
  const elem = document.getElementById(`op-sc-${name}`);
  if (elem) elem.classList.add("active");

  try {
    await fetch(`/api/demo/scenario/${name}`, { method: "POST" });
    fetchScenarioData(name);
  } catch (err) {
    console.error("Error setting scenario:", err);
  }
}

async function resetDemoState() {
  try {
    await fetch("/api/demo/reset", { method: "POST" });
    setScenario("normal");
  } catch (err) {
    console.error("Error resetting memory:", err);
  }
}

async function fetchScenarioData(name) {
  try {
    const [telemetryRes, alertRes, memoryRes] = await Promise.all([
      fetch("/api/telemetry"),
      fetch("/api/alerts/current"),
      fetch("/api/memory")
    ]);

    const telemetry = await telemetryRes.json();
    const alert = await alertRes.json();
    const memory = await memoryRes.json();

    renderTelemetryCharts(telemetry.telemetry_charts || {});
    renderAlertDecision(alert);
    renderMemoryBank(memory.memories || []);
  } catch (err) {
    console.error("Error fetching scenario data:", err);
  }
}

function renderTelemetryCharts(chartsData) {
  telemetryChartsData = chartsData;
  const channels = [41, 42, 43, 44, 45, 46];

  channels.forEach(chNum => {
    const chKey = `channel_${chNum}`;
    const canvas = document.getElementById(`chart-ch${chNum}`);
    if (!canvas) return;

    const dataPoints = chartsData[chKey] || [];
    renderEngineeringPlot(canvas, dataPoints);

    const valElem = document.getElementById(`ch${chNum}-val`);
    if (valElem && dataPoints.length > 0) {
      const lastVal = dataPoints[dataPoints.length - 1];
      valElem.innerText = typeof lastVal === "number" ? lastVal.toFixed(3) : lastVal;
    }
  });
}

function renderEngineeringPlot(canvas, data) {
  const ctx = canvas.getContext("2d");
  const width = canvas.parentElement.clientWidth;
  const height = canvas.parentElement.clientHeight;
  canvas.width = width;
  canvas.height = height;

  ctx.fillStyle = "#11151a";
  ctx.fillRect(0, 0, width, height);
  if (!data || data.length === 0) return;

  // Grid
  ctx.strokeStyle = "rgba(255, 255, 255, 0.05)";
  ctx.lineWidth = 1;
  for (let x = 0; x < width; x += 40) {
    ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, height); ctx.stroke();
  }
  for (let y = 0; y < height; y += 30) {
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(width, y); ctx.stroke();
  }

  let min = Math.min(...data);
  let max = Math.max(...data);
  if (max === min) { max += 1.0; min -= 1.0; }
  const range = max - min;

  // Zero Threshold
  const zeroY = height - ((0 - min) / range) * height;
  ctx.strokeStyle = "rgba(255, 171, 0, 0.3)";
  ctx.setLineDash([4, 4]);
  ctx.beginPath(); ctx.moveTo(0, zeroY); ctx.lineTo(width, zeroY); ctx.stroke();
  ctx.setLineDash([]);

  // Telemetry Line
  ctx.strokeStyle = "#00e5ff";
  ctx.lineWidth = 1.5;
  ctx.beginPath();

  const stepX = width / (data.length - 1);
  data.forEach((val, i) => {
    const x = i * stepX;
    const y = height - ((val - min) / range) * height;
    if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
  });
  ctx.stroke();
}

function renderAlertDecision(alert) {
  const badge = document.getElementById("sc-alert-badge");
  badge.className = "status-badge";

  if (alert.status === "NOMINAL") {
    badge.classList.add("nominal"); badge.innerText = "NOMINAL";
  } else if (alert.status === "KNOWN_OPERATIONAL_PATTERN") {
    badge.classList.add("known"); badge.innerText = "KNOWN OPERATIONAL PATTERN";
  } else if (alert.status === "UNKNOWN_UNUSUAL_EVENT") {
    badge.classList.add("warning"); badge.innerText = "UNKNOWN UNUSUAL EVENT";
  } else if (alert.status === "CRITICAL_COMPONENT_ANOMALY") {
    badge.classList.add("critical"); badge.innerText = "CRITICAL COMPONENT ANOMALY";
  } else {
    badge.classList.add("nominal"); badge.innerText = alert.status;
  }

  document.getElementById("sc-evt-id").innerText = alert.event_id || "normal_window";
  document.getElementById("sc-unusual-score").innerText = `${(alert.unusualness_score || 0).toFixed(3)} / 3.000`;
  document.getElementById("sc-affected-params").innerText = (alert.affected_channels || []).join(", ") || "NONE";
  document.getElementById("sc-tc-context").innerText = `${alert.recent_tc_count_5m || 0} TC EXECUTED`;

  const simPct = (alert.similarity_score * 100).toFixed(1);
  document.getElementById("sc-sim-val").innerText = `${simPct}%`;
  document.getElementById("sc-sim-fill").style.width = `${simPct}%`;

  if (alert.nearest_pattern) {
    document.getElementById("sc-nearest-match").innerText = `NEAREST MATCH: ${alert.nearest_pattern.memory_id} (${alert.nearest_pattern.source_event_id})`;
  } else {
    document.getElementById("sc-nearest-match").innerText = "NEAREST MATCH: NONE";
  }
  document.getElementById("sc-explanation").innerText = alert.explanation || "";
}

function renderMemoryBank(memories) {
  const tbody = document.getElementById("op-memory-table-body");
  document.getElementById("op-memory-count").innerText = `${memories.length} PATTERNS`;

  if (memories.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" style="color: var(--text-muted); text-align: center;">No stored operational patterns.</td></tr>';
    return;
  }

  tbody.innerHTML = memories.map(m => `
    <tr>
      <td style="color: var(--color-accent); font-weight: 600;">${m.memory_id}</td>
      <td>${m.source_event_id}</td>
      <td style="color: var(--color-nominal); font-weight: 600;">${m.operator_label}</td>
    </tr>
  `).join("");
}

async function submitFeedback(label) {
  try {
    const res = await fetch("/api/feedback", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scenario_name: currentScenario, operator_label: label })
    });
    if (res.ok) {
      fetchScenarioData(currentScenario);
    }
  } catch (err) {
    console.error("Error submitting feedback:", err);
  }
}

// ==================== 6. DATA SOURCES PROVENANCE ==================== //

async function fetchDataSourcesStatus() {
  try {
    const res = await fetch("/api/v1/sources/status");
    const data = await res.json();
    const tbody = document.getElementById("sources-table-body");
    tbody.innerHTML = data.sources.map(src => `
      <tr>
        <td style="font-weight: 600; color: var(--text-primary);">${src.provider_name}</td>
        <td style="font-family: var(--font-mono); color: var(--color-accent);">${src.data_scope}</td>
        <td><span class="status-badge nominal">${src.status}</span></td>
        <td style="font-family: var(--font-mono);">${src.last_successful_update}</td>
        <td style="font-family: var(--font-mono);">${src.age_hours.toFixed(1)} hrs</td>
        <td>${src.coverage_summary}</td>
      </tr>
    `).join("");
  } catch (err) {
    console.error("Error fetching data sources:", err);
  }
}
