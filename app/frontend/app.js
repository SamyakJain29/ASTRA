/* ASTRA Space Operations Intelligence Platform — Core Application Logic */

let activeNav = "global";
let currentScenario = "normal";
let selectedNoradId = 25544;
let catalogObjects = [];
let selectedObjectDetail = null;
let orbitWebSocket = null;
let telemetryChartsData = {};

// Continents for 2D equirectangular map background
const CONTINENT_POLYGONS = [
  [[-130, 50], [-120, 60], [-80, 60], [-60, 45], [-80, 25], [-105, 20], [-120, 35], [-130, 50]],
  [[-80, 10], [-50, -5], [-35, -10], [-55, -50], [-75, -45], [-80, 10]],
  [[-10, 35], [30, 30], [50, 15], [80, 10], [120, 25], [140, 55], [100, 70], [30, 70], [-10, 60], [-10, 35]],
  [[10, 35], [50, 30], [40, 0], [50, -30], [20, -35], [0, 5], [10, 35]],
  [[115, -15], [150, -15], [150, -35], [115, -35], [115, -15]]
];

document.addEventListener("DOMContentLoaded", () => {
  startSystemClock();
  initGlobalCatalog();
  fetchDataSourcesStatus();
  fetchScenarioData("normal");

  // Periodic catalog & data source refresh
  setInterval(refreshGlobalCatalogStates, 2000);
});

function startSystemClock() {
  setInterval(() => {
    document.getElementById("sys-clock").innerText = new Date().toISOString();
  }, 1000);
}

// 7-Workspace Navigation Switcher
function switchNav(nav) {
  activeNav = nav;
  document.querySelectorAll(".workspace").forEach(w => w.classList.remove("active"));
  document.querySelectorAll(".mode-btn").forEach(b => b.classList.remove("active"));

  const targetWs = document.getElementById(`workspace-${nav}`);
  const targetBtn = document.getElementById(`tab-btn-${nav}`);
  if (targetWs) targetWs.classList.add("active");
  if (targetBtn) targetBtn.classList.add("active");

  if (nav === "global") {
    renderGlobalOrbitMap();
  } else if (nav === "sources") {
    fetchDataSourcesStatus();
  }
}

// ==================== 1. GLOBAL ORBITAL AWARENESS ==================== //

async function initGlobalCatalog() {
  await refreshGlobalCatalogStates();
  if (catalogObjects.length > 0) {
    selectObject(selectedNoradId || catalogObjects[0].norad_id);
  }
}

let recentRfOnly = false;

function toggleRecentRfFilter(checked) {
  recentRfOnly = checked;
  refreshGlobalCatalogStates();
}

function switchInspectorTab(tabKey) {
  const tabs = ['orbital', 'rf', 'telemetry', 'feed'];
  tabs.forEach(t => {
    const btn = document.getElementById(`itab-btn-${t}`);
    const sec = document.getElementById(`isec-${t}`);
    if (btn) btn.classList.toggle('active', t === tabKey);
    if (sec) sec.classList.toggle('active', t === tabKey);
  });
}

function renderSatnogsInspectorData(satnogsData) {
  if (!satnogsData) return;

  const rfBadge = document.getElementById("satnogs-rf-status");
  const tmBadge = document.getElementById("satnogs-tm-status");

  let statusText = satnogsData.overall_status || "SOURCE UNAVAILABLE";
  if (satnogsData.source_status === "USING CACHED SATNOGS DATA") {
    statusText = "USING CACHED SATNOGS DATA";
  } else if (satnogsData.source_status === "SOURCE UNAVAILABLE") {
    statusText = "SOURCE UNAVAILABLE";
  }

  if (rfBadge) {
    rfBadge.innerText = statusText;
    rfBadge.className = `status-badge ${statusText === 'AVAILABLE' ? 'nominal' : (statusText.includes('CACHED') ? 'nominal' : 'warning')}`;
  }
  if (tmBadge) {
    const tmStatus = satnogsData.has_decoder ? "AVAILABLE" : (satnogsData.has_telemetry_frames ? "RAW ONLY" : "NO DECODER");
    tmBadge.innerText = tmStatus;
    tmBadge.className = `status-badge ${tmStatus === 'AVAILABLE' ? 'nominal' : 'warning'}`;
  }

  // RF Observations Section
  const latestObs = satnogsData.latest_observation;
  document.getElementById("rf-obs-time").innerText = latestObs ? (latestObs.timestamp || "--") : "NO RECENT DATA";
  document.getElementById("rf-obs-station").innerText = latestObs ? (latestObs.ground_station_identity || latestObs.ground_station_id || "--") : "--";
  document.getElementById("rf-obs-freq").innerText = latestObs ? `${latestObs.frequency_hz ? (latestObs.frequency_hz / 1e6).toFixed(3) + ' MHz' : '--'} | ${latestObs.mode || '--'}` : "--";
  document.getElementById("rf-obs-id").innerText = latestObs ? `#${latestObs.observation_id}` : "--";
  document.getElementById("rf-obs-count").innerText = (satnogsData.observations || []).length;

  const obsContainer = document.getElementById("rf-obs-list-container");
  if (obsContainer) {
    const obsList = satnogsData.observations || [];
    if (obsList.length === 0) {
      obsContainer.innerHTML = `<div class="notice-banner">No recent RF observations recorded for NORAD ${satnogsData.norad_id} in SatNOGS DB within 24h window.</div>`;
    } else {
      let html = `<table class="decoder-kv-table"><thead><tr><th>PASS ID</th><th>TIMESTAMP</th><th>GROUND STATION NODE</th><th>FREQ / MODE</th><th>STATUS</th></tr></thead><tbody>`;
      obsList.slice(0, 5).forEach(o => {
        html += `<tr>
          <td class="mono">#${o.observation_id || '--'}</td>
          <td>${o.timestamp || '--'}</td>
          <td>${o.ground_station_identity || o.ground_station_id || '--'}</td>
          <td class="mono">${o.frequency_hz ? (o.frequency_hz / 1e6).toFixed(3) + ' MHz' : '--'} / ${o.mode || '--'}</td>
          <td><span class="status-badge ${o.status === 'Good' ? 'nominal' : 'known'}">${o.status || 'RECORDED'}</span></td>
        </tr>`;
      });
      html += `</tbody></table>`;
      obsContainer.innerHTML = html;
    }
  }

  // Decoded Telemetry Section
  const tmContainer = document.getElementById("satnogs-telemetry-frames-container");
  if (tmContainer) {
    const frames = satnogsData.telemetry_frames || [];
    if (frames.length === 0) {
      tmContainer.innerHTML = `<div class="notice-banner">No public decoded telemetry frames available for NORAD ${satnogsData.norad_id}. Status: ${statusText}</div>`;
    } else {
      let html = "";
      frames.forEach((frame, idx) => {
        const rawPayload = frame.raw_frame || frame.raw_frame_hex;
        const decoded = frame.decoded_fields;
        const hasDecoded = decoded && typeof decoded === 'object' && Object.keys(decoded).length > 0;

        html += `<div class="subpanel" style="margin-top: 0.5rem;">
          <div class="panel-header" style="margin-bottom: 0.3rem; padding-bottom: 0.2rem;">
            <span class="panel-title">FRAME #${idx+1} — ${frame.timestamp || 'TIMESTAMP N/A'}</span>
            <span class="mono" style="font-size: 0.65rem; color: var(--color-accent);">${frame.observer ? 'Observer: ' + frame.observer : 'SatNOGS Network'}</span>
          </div>`;

        if (rawPayload) {
          html += `<div class="kv-row"><span class="kv-label">RAW FRAME</span><span class="kv-val mono" style="font-size: 0.65rem; word-break: break-all;">${rawPayload}</span></div>`;
        }

        if (hasDecoded) {
          html += `<div class="section-title" style="margin-top: 0.4rem;">DECODER FIELDS</div>
          <table class="decoder-kv-table"><thead><tr><th>FIELD NAME</th><th>DECODER VALUE</th></tr></thead><tbody>`;
          Object.entries(decoded).forEach(([k, v]) => {
            html += `<tr><td class="field-name mono">${k}</td><td class="field-val mono">${v}</td></tr>`;
          });
          html += `</tbody></table>`;
        } else {
          html += `<div style="margin-top: 0.4rem; font-family: var(--font-mono); font-size: 0.68rem; color: var(--color-warning);">RAW FRAME AVAILABLE &bull; DECODED TELEMETRY UNAVAILABLE</div>`;
        }
        html += `</div>`;
      });
      tmContainer.innerHTML = html;
    }
  }
}

async function refreshGlobalCatalogStates() {
  try {
    const url = recentRfOnly ? "/api/v1/global/states?recent_rf_only=true" : "/api/v1/global/states";
    const res = await fetch(url);
    if (!res.ok) return;
    const data = await res.json();
    catalogObjects = data.states || [];

    const provElem = document.getElementById("glob-provider");
    const cacheStateElem = document.getElementById("glob-cache-state");
    const countElem = document.getElementById("glob-object-count");
    const ageElem = document.getElementById("glob-cache-age");

    if (provElem) provElem.innerText = data.provider || "CelesTrak GP/OMM Catalog Engine";
    if (countElem) countElem.innerText = `${data.total_catalog_objects || catalogObjects.length} Objects`;
    if (ageElem) ageElem.innerText = `${(data.cache_age_seconds / 3600.0 || 0).toFixed(1)} hrs`;

    if (cacheStateElem) {
      if (data.is_offline) {
        cacheStateElem.innerText = "USING CACHED ORBITAL ELEMENTS";
        cacheStateElem.className = "status-badge nominal";
      } else {
        cacheStateElem.innerText = "LIVE ONLINE (NEAR-REAL-TIME SOURCE)";
        cacheStateElem.className = "status-badge known";
      }
    }

    renderGlobalOrbitMap();
  } catch (err) {
    console.error("Error refreshing catalog states:", err);
  }
}

function selectObject(noradId) {
  selectedNoradId = parseInt(noradId, 10);
  fetchObjectDetail(selectedNoradId);
  connectOrbitWebSocket(selectedNoradId);
  renderGlobalOrbitMap();
}

async function fetchObjectDetail(noradId) {
  try {
    const res = await fetch(`/api/v1/global/object/${noradId}`);
    if (!res.ok) return;
    const detail = await res.json();
    selectedObjectDetail = detail;

    // Update Detail Inspector Fields
    document.getElementById("sel-obj-name").innerText = detail.name || `OBJECT ${detail.norad_id}`;
    document.getElementById("sel-norad-id").innerText = detail.norad_id;
    document.getElementById("sel-cospar-id").innerText = detail.cospar_id || "N/A";
    document.getElementById("sel-obj-type").innerText = detail.object_type || "ACTIVE_SPACECRAFT";
    document.getElementById("sel-orbit-regime").innerText = detail.orbit_regime || "LEO";

    const der = detail.derived_propagated_values || {};
    const src = detail.source_values || {};

    document.getElementById("sel-lat").innerText = der.latitude !== null ? `${der.latitude.toFixed(4)}° N` : "--";
    document.getElementById("sel-lon").innerText = der.longitude !== null ? `${der.longitude.toFixed(4)}° E` : "--";
    document.getElementById("sel-alt").innerText = der.altitude_km !== null ? `${der.altitude_km.toFixed(2)} km` : "--";
    document.getElementById("sel-vel").innerText = der.velocity_kms !== null ? `${der.velocity_kms.toFixed(3)} km/s` : "--";
    document.getElementById("sel-state-time").innerText = der.propagated_timestamp || new Date().toISOString();

    document.getElementById("sel-inc").innerText = src.inclination_deg !== null ? `${src.inclination_deg.toFixed(4)}°` : "--";
    document.getElementById("sel-ecc").innerText = src.eccentricity !== null ? src.eccentricity.toFixed(6) : "--";
    document.getElementById("sel-mm").innerText = src.mean_motion !== null ? `${src.mean_motion.toFixed(4)} rev/day` : "--";
    document.getElementById("sel-sma").innerText = der.semi_major_axis_km ? `${der.semi_major_axis_km.toFixed(1)} km` : "--";
    document.getElementById("sel-ap-per").innerText = (der.apogee_km && der.perigee_km) ? `${der.apogee_km.toFixed(1)} / ${der.perigee_km.toFixed(1)} km` : "--";
    document.getElementById("sel-period").innerText = der.period_minutes ? `${der.period_minutes.toFixed(2)} min` : "--";
    document.getElementById("sel-epoch").innerText = src.element_epoch || "--";
    document.getElementById("sel-age").innerText = der.element_age_hours ? `${der.element_age_hours.toFixed(1)} hrs` : "--";

    document.getElementById("sel-prov").innerText = src.provider || "CelesTrak OMM/GP Ingestion Engine";
    document.getElementById("sel-cache-state").innerText = detail.network_and_cache_state ? detail.network_and_cache_state.status : "USING CACHED ORBITAL ELEMENTS";

    // Ground Contact Subpanel
    const gc = detail.ground_contact;
    const badge = document.getElementById("pass-visibility-badge");
    if (gc) {
      document.getElementById("gc-az").innerText = `${gc.azimuth_deg.toFixed(1)}°`;
      document.getElementById("gc-el").innerText = `${gc.elevation_deg.toFixed(1)}°`;
      document.getElementById("gc-range").innerText = `${gc.range_km.toFixed(1)} km`;
      const maxEl = gc.max_elevation_deg || (gc.next_pass && gc.next_pass.max_elevation_deg);
      document.getElementById("gc-max-el").innerText = maxEl ? `${maxEl.toFixed(1)}°` : "--";

      const aosRaw = gc.next_aos || (gc.next_pass && gc.next_pass.next_aos);
      const losRaw = gc.next_los || (gc.next_pass && gc.next_pass.next_los);
      document.getElementById("gc-aos").innerText = aosRaw ? (typeof aosRaw === "string" && aosRaw.includes("T") ? aosRaw.split("T")[1].replace("Z", "").substring(0, 8) : aosRaw) : "UNAVAILABLE";
      document.getElementById("gc-los").innerText = losRaw ? (typeof losRaw === "string" && losRaw.includes("T") ? losRaw.split("T")[1].replace("Z", "").substring(0, 8) : losRaw) : "UNAVAILABLE";

      const durMinutes = gc.pass_duration_minutes || (gc.next_pass && gc.next_pass.duration_seconds ? gc.next_pass.duration_seconds / 60.0 : null);
      document.getElementById("gc-dur").innerText = durMinutes ? `${durMinutes.toFixed(1)} min` : "--";

      if (badge) {
        if (gc.is_visible) {
          badge.innerText = "IN VIEW (AOS ACTIVE)";
          badge.className = "status-badge nominal";
        } else {
          badge.innerText = "BELOW HORIZON";
          badge.className = "status-badge";
        }
      }
    }

    if (detail.satnogs_data) {
      renderSatnogsInspectorData(detail.satnogs_data);
    }

    renderGlobalOrbitMap();
  } catch (err) {
    console.error("Error fetching object detail:", err);
  }
}

// Realtime 1 Hz SGP4 WebSocket Stream
function connectOrbitWebSocket(noradId) {
  if (orbitWebSocket) {
    orbitWebSocket.close();
    orbitWebSocket = null;
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  const wsUrl = `${protocol}//${window.location.host}/ws/orbit/${noradId}`;

  try {
    orbitWebSocket = new WebSocket(wsUrl);

    orbitWebSocket.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.norad_id !== selectedNoradId) return;

      // Update 1 Hz changing telemetry values
      document.getElementById("sel-lat").innerText = `${data.latitude.toFixed(4)}° N`;
      document.getElementById("sel-lon").innerText = `${data.longitude.toFixed(4)}° E`;
      document.getElementById("sel-alt").innerText = `${data.altitude_km.toFixed(2)} km`;
      document.getElementById("sel-vel").innerText = `${data.velocity_km_s.toFixed(3)} km/s`;
      document.getElementById("sel-state-time").innerText = data.timestamp;

      // Ground Contact Stream Update
      if (data.ground_contact) {
        const gc = data.ground_contact;
        document.getElementById("gc-az").innerText = `${gc.azimuth_deg.toFixed(1)}°`;
        document.getElementById("gc-el").innerText = `${gc.elevation_deg.toFixed(1)}°`;
        document.getElementById("gc-range").innerText = `${gc.range_km.toFixed(1)} km`;
        const badge = document.getElementById("pass-visibility-badge");
        if (badge) {
          if (gc.is_visible) {
            badge.innerText = "IN VIEW (AOS ACTIVE)";
            badge.className = "status-badge nominal";
          } else {
            badge.innerText = "BELOW HORIZON";
            badge.className = "status-badge";
          }
        }
      }

      // Update catalog object position for canvas map
      const targetObj = catalogObjects.find(o => o.norad_id === noradId);
      if (targetObj) {
        targetObj.lat = data.latitude;
        targetObj.lon = data.longitude;
        targetObj.alt_km = data.altitude_km;
        targetObj.vel_kms = data.velocity_km_s;
      }

      if (data.orbit_path && selectedObjectDetail) {
        selectedObjectDetail.orbit_path = data.orbit_path;
      }

      renderGlobalOrbitMap();
    };

    orbitWebSocket.onerror = (err) => {
      console.warn("WebSocket stream error, falling back to HTTP polling:", err);
    };
  } catch (err) {
    console.warn("WebSocket init error:", err);
  }
}

// 2D Map Rendering with SGP4 Orbit Path
function renderGlobalOrbitMap() {
  const canvas = document.getElementById("global-map-canvas");
  if (!canvas || activeNav !== "global") return;

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

  // 30 degree Latitude / Longitude Grid
  ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
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
  CONTINENT_POLYGONS.forEach(poly => {
    ctx.beginPath();
    poly.forEach(([lon, lat], i) => {
      const [x, y] = toCanvasCoords(lat, lon);
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
    });
    ctx.closePath(); ctx.fill(); ctx.stroke();
  });

  // Ground Station Target Dot (Hyderabad HQ)
  const [gsX, gsY] = toCanvasCoords(17.3850, 78.4867);
  ctx.fillStyle = "#00e676";
  ctx.beginPath(); ctx.arc(gsX, gsY, 4, 0, 2 * Math.PI); ctx.fill();
  ctx.strokeStyle = "rgba(0, 230, 118, 0.4)";
  ctx.beginPath(); ctx.arc(gsX, gsY, 8, 0, 2 * Math.PI); ctx.stroke();

  // Draw Selected Object Orbit Path Trajectory
  if (selectedObjectDetail && selectedObjectDetail.orbit_path && selectedObjectDetail.orbit_path.length > 0) {
    ctx.strokeStyle = "rgba(0, 229, 255, 0.6)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();

    let prevX = null;
    selectedObjectDetail.orbit_path.forEach((pt, i) => {
      const [x, y] = toCanvasCoords(pt.lat, pt.lon);
      if (i === 0 || (prevX !== null && Math.abs(x - prevX) > width * 0.5)) {
        ctx.moveTo(x, y);
      } else {
        ctx.lineTo(x, y);
      }
      prevX = x;
    });
    ctx.stroke();
  }

  // Plot Loaded Catalog Space Objects
  catalogObjects.forEach(st => {
    const [x, y] = toCanvasCoords(st.lat, st.lon);
    const isSelected = st.norad_id === selectedNoradId;

    ctx.fillStyle = isSelected ? "#ffab00" : "#00e5ff";
    ctx.beginPath();
    ctx.arc(x, y, isSelected ? 5 : 3.5, 0, 2 * Math.PI);
    ctx.fill();

    if (isSelected) {
      ctx.strokeStyle = "#ffab00";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(x - 8, y); ctx.lineTo(x + 8, y);
      ctx.moveTo(x, y - 8); ctx.lineTo(x, y + 8);
      ctx.stroke();

      ctx.fillStyle = "#e6e8eb";
      ctx.font = '700 11px "JetBrains Mono"';
      ctx.fillText(st.name, x + 10, y - 3);
    }
  });
}

// Search with Ranking: Exact NORAD -> Exact COSPAR -> Exact Name -> Partial Name
function onGlobalSearch(query) {
  const dropdown = document.getElementById("search-results-dropdown");
  if (!query || query.trim().length === 0) {
    if (dropdown) dropdown.style.display = "none";
    return;
  }

  const q = query.trim().toLowerCase();
  const exactNorad = catalogObjects.filter(o => String(o.norad_id) === q);
  const exactCospar = catalogObjects.filter(o => (o.cospar_id || "").toLowerCase() === q && String(o.norad_id) !== q);
  const exactName = catalogObjects.filter(o => o.name.toLowerCase() === q && String(o.norad_id) !== q);
  const partialName = catalogObjects.filter(o => o.name.toLowerCase().includes(q) && o.name.toLowerCase() !== q && String(o.norad_id) !== q);

  const ranked = [...exactNorad, ...exactCospar, ...exactName, ...partialName];

  if (dropdown) {
    if (ranked.length === 0) {
      dropdown.innerHTML = '<div class="search-result-item muted">No matching space objects found</div>';
    } else {
      dropdown.innerHTML = ranked.map(o => `
        <div class="search-result-item" onclick="selectSearchResult(${o.norad_id})">
          <span style="color: var(--color-accent); font-weight: 700;">${o.norad_id}</span> — ${o.name} <span class="muted">(${o.regime || 'LEO'})</span>
        </div>
      `).join("");
    }
    dropdown.style.display = "block";
  }
}

function selectSearchResult(noradId) {
  const dropdown = document.getElementById("search-results-dropdown");
  if (dropdown) dropdown.style.display = "none";
  document.getElementById("global-search-input").value = "";
  selectObject(noradId);
}

// ==================== DATA SOURCES PROVENANCE MATRIX ==================== //

async function fetchDataSourcesStatus() {
  try {
    const res = await fetch("/api/v1/sources/status");
    if (!res.ok) return;
    const data = await res.json();
    const tbody = document.getElementById("sources-table-body");
    if (!tbody) return;

    const headerBadge = document.getElementById("sources-header-status");
    if (headerBadge) {
      headerBadge.innerText = "LIVE MATRIX AUDITED";
      headerBadge.className = "status-badge nominal";
    }

    tbody.innerHTML = data.sources.map(src => {
      let statusBadgeClass = "nominal";
      if (src.status === "OFFLINE" || src.status === "NOT_CONFIGURED") statusBadgeClass = "warning";
      if (src.status === "HISTORICAL") statusBadgeClass = "known";

      const ageStr = typeof src.age_seconds === "number" && src.age_seconds >= 0 ? `${(src.age_seconds / 3600.0).toFixed(1)} hrs` : "N/A";
      const countsStr = `${src.objects_retrieved ?? 0} / ${src.objects_loaded ?? src.objects_accepted ?? 0} / ${src.objects_skipped_by_limit ?? 0} / ${src.objects_invalid ?? src.objects_rejected ?? 0}`;
      const latencyStr = typeof src.refresh_duration_ms === "number" ? `${src.refresh_duration_ms.toFixed(1)} ms` : "0.0 ms";

      return `
        <tr>
          <td class="mono" style="font-weight: 700; color: var(--text-primary);">${src.provider_name}</td>
          <td class="accent">${src.data_scope}</td>
          <td class="mono muted">${src.type}</td>
          <td><span class="status-badge ${statusBadgeClass}">${src.status_detail || src.status}</span></td>
          <td class="mono">${src.http_status || '200 OK'}</td>
          <td class="mono">${countsStr}</td>
          <td class="mono muted">${src.cache_path || 'N/A'}</td>
          <td class="mono">${src.last_success || 'N/A'}</td>
          <td class="mono">${latencyStr}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Error fetching data sources status:", err);
  }
}

// ==================== OPERATIONS & TELEMETRY SCENARIOS ==================== //

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
    console.error("Error resetting memory state:", err);
  }
}

async function fetchScenarioData(name) {
  try {
    const [telemetryRes, alertRes, memoryRes] = await Promise.all([
      fetch("/api/telemetry"),
      fetch("/api/alerts/current"),
      fetch("/api/memory")
    ]);

    if (telemetryRes.ok) {
      const telemetry = await telemetryRes.json();
      renderTelemetryCharts(telemetry.telemetry_charts || {});
    }
    if (alertRes.ok) {
      const alert = await alertRes.json();
      renderAlertDecision(alert);
    }
    if (memoryRes.ok) {
      const memory = await memoryRes.json();
      renderMemoryBank(memory.memories || []);
    }
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
  ctx.strokeStyle = "rgba(255, 255, 255, 0.04)";
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
  if (badge) {
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
  }

  document.getElementById("sc-unusual-score").innerText = `${(alert.unusualness_score || 0).toFixed(3)} / 3.000`;
  document.getElementById("sc-affected-params").innerText = (alert.affected_channels || []).join(", ") || "NONE";
  document.getElementById("sc-tc-context").innerText = `${alert.recent_tc_count_5m || 0} TC EXECUTED`;

  const simPct = ((alert.similarity_score || 0) * 100).toFixed(1);
  document.getElementById("sc-sim-val").innerText = `${simPct}%`;
  document.getElementById("sc-sim-fill").style.width = `${simPct}%`;

  if (alert.nearest_pattern) {
    document.getElementById("sc-nearest-match").innerText = `NEAREST MATCH: ${alert.nearest_pattern.memory_id} (${alert.nearest_pattern.source_event_id})`;
  } else {
    document.getElementById("sc-nearest-match").innerText = "NEAREST MATCH: NONE";
  }
  document.getElementById("sc-explanation").innerText = alert.explanation || "Telemetry within nominal bounds.";
}

function renderMemoryBank(memories) {
  const tbody = document.getElementById("op-memory-table-body");
  const countElem = document.getElementById("op-memory-count");
  if (countElem) countElem.innerText = `${memories.length} PATTERNS`;
  if (!tbody) return;

  if (memories.length === 0) {
    tbody.innerHTML = '<tr><td colspan="3" class="muted" style="text-align: center;">No stored operational patterns.</td></tr>';
    return;
  }

  tbody.innerHTML = memories.map(m => `
    <tr>
      <td class="accent">${m.memory_id}</td>
      <td class="mono">${m.source_event_id}</td>
      <td class="mono" style="color: var(--color-nominal); font-weight: 600;">${m.operator_label}</td>
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
