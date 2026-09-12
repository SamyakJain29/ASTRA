// Run with Node.js: node tests/frontend_correctness.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const path = require("node:path");

const elements = new Map();
function element(id) {
  if (!elements.has(id)) {
    const classes = new Set(id.startsWith("op-sc-") ? ["scenario-btn"] : []);
    if (id === "op-sc-normal") classes.add("active");
    if (id.startsWith("feedback-")) classes.add("op-btn");
    elements.set(id, {
      id, innerText: "", textContent: "", innerHTML: "", hidden: false, disabled: false,
      style: {}, className: "",
      classList: {add: name => classes.add(name), remove: name => classes.delete(name),
        contains: name => classes.has(name), toggle: (name, on) => on ? classes.add(name) : classes.delete(name)}
    });
  }
  return elements.get(id);
}
const scenarioButtons = ["normal", "rare_first", "rare_repeat", "anomaly"].map(n => element(`op-sc-${n}`));
const feedback = element("feedback-valid");
const controls = [...scenarioButtons, feedback, element("reset-button")];
const sandbox = {
  document: {addEventListener() {}, getElementById: element,
    querySelectorAll: selector => selector.includes("#workspace-operations") ? controls : selector === ".scenario-btn" ? scenarioButtons : []},
  window: {location: {protocol: "http:", host: "localhost"}},
  console: {error() {}, warn() {}}, setInterval() {},
  WebSocket: class {constructor() { sandbox.socket = this; } close() {}},
};
vm.createContext(sandbox);
vm.runInContext(fs.readFileSync(path.join(__dirname, "../app/frontend/app.js"), "utf8"), sandbox);
const state = expression => vm.runInContext(expression, sandbox);
const response = (body = {}, status = 200) => ({ok: status >= 200 && status < 300, status, json: async () => body});
const goodFetch = async url => response(url === "/api/telemetry" ? {telemetry_charts: {channel_41: [1]}} : url === "/api/memory" ? {memories: []} : {status: "NOMINAL"});
let plotted;
sandbox.renderTelemetryCharts = charts => { plotted = charts; };
sandbox.renderAlertDecision = () => {};
sandbox.renderMemoryBank = () => {};
sandbox.renderGlobalOrbitMap = () => {};

async function main() {
  assert.equal(sandbox.formatLatitude(-38.1304), "38.1304° S");
  assert.equal(sandbox.formatLatitude(38.1304), "38.1304° N");
  assert.equal(sandbox.formatLongitude(-20), "20.0000° W");
  assert.equal(sandbox.formatLongitude(20), "20.0000° E");
  for (const value of [null, undefined, "", "invalid", Infinity]) {
    assert.equal(sandbox.formatLatitude(value), "--");
    assert.equal(sandbox.formatLongitude(value), "--");
  }
  assert.equal(sandbox.formatFreshness(0), "< 1 min");
  assert.equal(sandbox.formatFreshness(59), "< 1 min");
  assert.equal(sandbox.formatFreshness(720), "12 min");
  assert.equal(sandbox.formatFreshness(3599), "59 min");
  assert.equal(sandbox.formatFreshness(5040), "1.4 hrs");
  assert.equal(sandbox.formatFreshness(null), "N/A");

  sandbox.fetch = async () => response({
    norad_id: 25544, name: "TEST", derived_propagated_values: {latitude: -38, longitude: -20, altitude_km: 500, velocity_kms: 7},
    source_values: {inclination_deg: 1, eccentricity: 0, mean_motion: 1},
  });
  await sandbox.fetchObjectDetail(25544);
  assert.equal(element("sel-lat").innerText, "38.0000° S");
  assert.equal(element("sel-lon").innerText, "20.0000° W");
  assert.equal(element("sel-tm-auth").innerText, "NO AUTHORIZED MISSION TELEMETRY");
  sandbox.connectOrbitWebSocket(25544);
  sandbox.socket.onmessage({data: JSON.stringify({norad_id: 25544, latitude: 12, longitude: -34, altitude_km: 500, velocity_km_s: 7})});
  assert.equal(element("sel-lat").innerText, "12.0000° N");
  assert.equal(element("sel-lon").innerText, "34.0000° W");

  sandbox.fetchDataSourcesStatus = () => {};
  for (const nav of ["fleet", "spacecraft", "alerts", "operations", "sources", "research"]) {
    sandbox.switchNav(nav);
    assert(!element("prov-provider").innerText.includes("CelesTrak"));
    assert(!element("prov-engine").innerText.includes("SGP4"));
  }
  sandbox.switchNav("global");
  assert(element("prov-provider").innerText.includes("CelesTrak"));
  for (const source of ["SOURCE UNAVAILABLE", "USING CACHED SATNOGS DATA"]) {
    sandbox.renderSatnogsInspectorData({source_status: source, has_decoder: true});
    const expected = source.includes("CACHED") ? "USING CACHED DATA" : source;
    assert.equal(element("satnogs-rf-status").innerText, expected);
    assert.equal(element("satnogs-tm-status").innerText, expected);
    assert(element("satnogs-rf-status").className.includes("warning"));
    assert(element("satnogs-tm-status").className.includes("warning"));
  }

  sandbox.fetch = goodFetch;
  await sandbox.fetchScenarioData();
  let finishPost;
  sandbox.fetch = () => new Promise(resolve => { finishPost = resolve; });
  const changing = sandbox.setScenario("rare_first");
  assert.equal(state("currentScenario"), "normal");
  assert(element("op-sc-normal").classList.contains("active"));
  assert(controls.every(button => button.disabled));
  finishPost(response({}, 503));
  await changing;
  assert.equal(state("currentScenario"), "normal");
  assert(element("op-sc-normal").classList.contains("active"));
  assert(!element("operations-request-status").hidden);
  assert(element("operations-request-status").textContent.includes("503"));
  assert(controls.every(button => !button.disabled));

  sandbox.fetch = goodFetch;
  await sandbox.setScenario("rare_first");
  assert.equal(state("currentScenario"), "rare_first");
  assert(element("op-sc-rare_first").classList.contains("active"));
  assert.equal(plotted.channel_41[0], 1);
  for (const failing of ["/api/telemetry", "/api/alerts/current", "/api/memory"]) {
    sandbox.fetch = url => url === failing ? Promise.resolve(response({}, 500)) : goodFetch(url);
    assert.equal(await sandbox.fetchScenarioData(), false);
    assert.equal(Object.keys(plotted).length, 0);
    assert.equal(element("sc-alert-badge").innerText, "DATA UNAVAILABLE");
    assert(element("operations-request-status").textContent.includes(failing));
    assert(feedback.disabled);
  }
  sandbox.fetch = goodFetch;
  await sandbox.fetchScenarioData();
  sandbox.fetch = async () => response({}, 409);
  await sandbox.submitFeedback("VALID_OPERATION");
  assert(element("operations-request-status").textContent.includes("Feedback was not accepted"));
  await sandbox.resetDemoState();
  assert.equal(state("currentScenario"), "rare_first");
  assert(element("op-sc-rare_first").classList.contains("active"));
  assert(element("operations-request-status").textContent.includes("Reset failed"));
  sandbox.fetch = goodFetch;
  await sandbox.resetDemoState();
  assert.equal(state("currentScenario"), "normal");
  assert(element("op-sc-normal").classList.contains("active"));
  assert(!element("operations-request-status").hidden === false);
  console.log("Frontend checks passed: hemispheres HTTP/WS, freshness, provenance, SatNOGS, scenario/reset/feedback failures and recovery.");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
