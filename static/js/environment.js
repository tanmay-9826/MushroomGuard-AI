(function () {
  "use strict";

  var panel = document.getElementById("environment-live");
  if (!panel) return;
  var endpoint = panel.dataset.statusUrl;
  var temperatures = JSON.parse(panel.dataset.chartLogs || "[]");
  var humidities = JSON.parse(panel.dataset.humidityLogs || "[]");
  var times = JSON.parse(panel.dataset.times || "[]");
  var selectedMetric = "temperature";

  function drawChart() {
    var canvas = document.getElementById("environment-chart");
    var empty = document.getElementById("chart-empty");
    if (!canvas) return;
    var values = selectedMetric === "temperature" ? temperatures : humidities;
    if (!values.length || !values.some(function (v) { return v !== null && v !== undefined; })) {
      canvas.hidden = true;
      if (empty) empty.hidden = false;
      return;
    }
    canvas.hidden = false;
    if (empty) empty.hidden = true;
    var dpr = window.devicePixelRatio || 1;
    var rect = canvas.getBoundingClientRect();
    var width = Math.max(320, rect.width);
    var height = 190;
    canvas.width = Math.round(width * dpr);
    canvas.height = Math.round(height * dpr);
    var ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, width, height);
    var valid = values.filter(function (v) { return v !== null && Number.isFinite(Number(v)); }).map(Number);
    var min = Math.min.apply(null, valid);
    var max = Math.max.apply(null, valid);
    if (min === max) { min -= 1; max += 1; }
    var pad = { left: 42, right: 14, top: 12, bottom: 28 };
    var plotW = width - pad.left - pad.right;
    var plotH = height - pad.top - pad.bottom;
    ctx.font = "11px system-ui, sans-serif";
    ctx.fillStyle = "#718079";
    ctx.strokeStyle = "#e7eee8";
    ctx.lineWidth = 1;
    for (var tick = 0; tick <= 4; tick++) {
      var y = pad.top + plotH * tick / 4;
      var val = max - (max - min) * tick / 4;
      ctx.beginPath(); ctx.moveTo(pad.left, y); ctx.lineTo(width - pad.right, y); ctx.stroke();
      ctx.fillText(val.toFixed(1), 3, y + 4);
    }
    var points = [];
    values.forEach(function (value, i) {
      if (value === null || value === undefined || !Number.isFinite(Number(value))) return;
      var x = pad.left + (values.length <= 1 ? plotW / 2 : plotW * i / (values.length - 1));
      var y = pad.top + plotH * (max - Number(value)) / (max - min);
      points.push([x, y]);
    });
    ctx.strokeStyle = selectedMetric === "temperature" ? "#2e8540" : "#258b9a";
    ctx.lineWidth = 2.5;
    ctx.lineJoin = "round";
    ctx.beginPath();
    points.forEach(function (p, i) { if (i === 0) ctx.moveTo(p[0], p[1]); else ctx.lineTo(p[0], p[1]); });
    ctx.stroke();
    points.forEach(function (p) { ctx.beginPath(); ctx.arc(p[0], p[1], 3, 0, Math.PI * 2); ctx.fillStyle = selectedMetric === "temperature" ? "#2e8540" : "#258b9a"; ctx.fill(); });
    if (times.length) {
      ctx.fillStyle = "#718079";
      var first = String(times[0]).slice(11, 16) || String(times[0]).slice(0, 10);
      var last = String(times[times.length - 1]).slice(11, 16) || String(times[times.length - 1]).slice(0, 10);
      ctx.fillText(first, pad.left, height - 7);
      ctx.textAlign = "right"; ctx.fillText(last, width - pad.right, height - 7); ctx.textAlign = "left";
    }
  }

  document.querySelectorAll("[data-chart]").forEach(function (button) {
    button.addEventListener("click", function () {
      document.querySelectorAll("[data-chart]").forEach(function (b) { b.classList.remove("active"); });
      button.classList.add("active");
      selectedMetric = button.dataset.chart;
      drawChart();
    });
  });

  async function refreshStatus() {
    try {
      var response = await fetch(endpoint, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!response.ok) return;
      var state = await response.json();
      if (String(state.region_id) !== String(panel.dataset.regionId)) return;
      var temperature = document.getElementById("live-temperature");
      var humidity = document.getElementById("live-humidity");
      var message = document.getElementById("live-message");
      if (temperature && state.temperature != null) temperature.textContent = Number(state.temperature).toFixed(1) + " °C";
      if (humidity && state.humidity != null) humidity.textContent = Number(state.humidity).toFixed(1) + " %";
      if (message) message.textContent = state.message || "No serial status available";
      var fanStatus = document.getElementById("fan-state");
      if (fanStatus && state.fan_state) fanStatus.textContent = state.fan_state;
      var ledStatus = document.getElementById("led-state");
      if (ledStatus && state.led_state) ledStatus.textContent = state.led_state;
      var modeStatus = document.getElementById("fan-mode");
      if (modeStatus && state.mode) modeStatus.textContent = state.mode;
      var conn = document.getElementById("arduino-state");
      if (conn) conn.textContent = state.connected ? "Port open" : "Disconnected";
    } catch (error) {
      // Keep the last valid readings visible when a polling request fails.
    }
  }

  async function refreshThingSpeak() {
    var statusUrl = panel.dataset.thingspeakStatusUrl;
    var latestUrl = panel.dataset.thingspeakLatestUrl;
    var badge = document.getElementById("thingspeak-state");
    var message = document.getElementById("thingspeak-message");
    var lastUpload = document.getElementById("thingspeak-last-upload");
    if (!statusUrl || !latestUrl) return;
    try {
      var statusResponse = await fetch(statusUrl, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (statusResponse.ok) {
        var cloudStatus = await statusResponse.json();
        if (badge) {
          badge.textContent = cloudStatus.connected ? "Connected" : (cloudStatus.enabled ? "Waiting / Offline" : "Not configured");
          badge.className = "status-badge " + (cloudStatus.connected ? "good" : "neutral");
        }
        if (message) message.textContent = cloudStatus.message || "No cloud status available";
        if (lastUpload) lastUpload.textContent = cloudStatus.last_success_at ? "Last upload: " + new Date(cloudStatus.last_success_at).toLocaleTimeString() : "No upload yet";
      }
      var latestResponse = await fetch(latestUrl, { credentials: "same-origin", headers: { Accept: "application/json" } });
      if (!latestResponse.ok) return;
      var latest = await latestResponse.json();
      var cloudTemp = document.getElementById("cloud-temperature");
      var cloudHum = document.getElementById("cloud-humidity");
      var created = document.getElementById("thingspeak-created-at");
      if (cloudTemp && latest.temperature != null) cloudTemp.textContent = Number(latest.temperature).toFixed(1) + " °C";
      if (cloudHum && latest.humidity != null) cloudHum.textContent = Number(latest.humidity).toFixed(1) + " %";
      if (created && latest.created_at) created.textContent = "Latest cloud entry: " + new Date(latest.created_at).toLocaleString();
    } catch (error) {
      if (badge) { badge.textContent = "Unavailable"; badge.className = "status-badge neutral"; }
    }
  }

  drawChart();
  refreshStatus();
  refreshThingSpeak();
  window.addEventListener("resize", drawChart);
  window.setInterval(refreshStatus, 3000);
  window.setInterval(refreshThingSpeak, 15000);
})();
