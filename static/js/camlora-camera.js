(function () {
  "use strict";
  const panel = document.getElementById("camlora-camera-panel");
  if (!panel) return;

  const configured = panel.dataset.configured === "true";
  const streamUrl = panel.dataset.streamUrl;
  const captureUrl = panel.dataset.captureUrl;
  const scanUrl = panel.dataset.scanUrl;
  const preview = document.getElementById("camlora-live-preview");
  const placeholder = document.getElementById("camlora-preview-placeholder");
  const cameraStatus = document.getElementById("camlora-camera-status");
  const startButton = document.getElementById("camlora-start");
  const stopButton = document.getElementById("camlora-stop");
  const captureForm = document.getElementById("camlora-capture-form");
  const captureButton = document.getElementById("camlora-capture");
  const captureResult = document.getElementById("camlora-capture-result");
  const scanButton = document.getElementById("camlora-scan-qr");
  const stopScanButton = document.getElementById("camlora-stop-qr");
  const scanStatus = document.getElementById("camlora-qr-status");
  const verifiedPanel = document.getElementById("camlora-unit-verified");
  const verifiedTitle = document.getElementById("camlora-verified-title");
  const verifiedDetails = document.getElementById("camlora-verified-details");
  const detailLink = document.getElementById("camlora-unit-detail-link");
  const stageReview = document.getElementById("camlora-stage-review");
  const stageSelect = document.getElementById("camlora-observed-stage");
  const confirmStage = document.getElementById("camlora-confirm-stage");
  const captureUnit = document.getElementById("camlora-unit-id");
  const observationUnit = document.getElementById("unit_id");

  let streamStarted = false;
  let scanActive = false;
  let scanTimer = null;
  let scanBusy = false;
  let verifiedUnit = null;

  const stageNames = {
    mushroom: ["Preparation & Spawning", "Incubation & Mycelium Growth", "Pinhead Formation & Fruiting", "Harvesting"],
    microgreen: ["Seed & Tray Preparation", "Germination", "Growth & Development", "Harvesting"]
  };

  function setCameraStatus(message, state) {
    cameraStatus.textContent = message;
    cameraStatus.dataset.state = state || "neutral";
  }

  function stopPreview() {
    preview.removeAttribute("src");
    preview.hidden = true;
    placeholder.hidden = false;
    streamStarted = false;
    startButton.disabled = !configured;
    stopButton.disabled = true;
    setCameraStatus(configured ? "Preview stopped. Phone camera remains available." : "Camlora is not configured.", "neutral");
  }

  startButton.addEventListener("click", function () {
    if (!configured || streamStarted) return;
    setCameraStatus("Connecting to your Android phone camera…", "pending");
    preview.hidden = false;
    placeholder.hidden = true;
    startButton.disabled = true;
    stopButton.disabled = false;
    streamStarted = true;
    preview.src = streamUrl + "?t=" + Date.now();
  });

  preview.addEventListener("load", function () {
    setCameraStatus("Live preview connected to Camlora.", "success");
  });

  preview.addEventListener("error", function () {
    setCameraStatus("Could not load the camera stream. Check Camlora, USB tethering and the phone IP in .env.", "error");
    preview.hidden = true;
    placeholder.hidden = false;
    streamStarted = false;
    startButton.disabled = !configured;
    stopButton.disabled = true;
  });

  stopButton.addEventListener("click", stopPreview);

  function stopQrScan(message) {
    scanActive = false;
    scanBusy = false;
    if (scanTimer) window.clearTimeout(scanTimer);
    scanTimer = null;
    scanButton.disabled = !configured;
    stopScanButton.disabled = true;
    if (message) scanStatus.textContent = message;
  }

  function showVerifiedUnit(unit) {
    verifiedUnit = unit;
    captureUnit.value = String(unit.id);
    if (observationUnit) observationUnit.value = String(unit.id);
    verifiedTitle.textContent = unit.unit_name + " — " + unit.crop_name;
    verifiedDetails.textContent = "Registered " + unit.crop_type + " · Current saved stage: Stage " + unit.growth_stage + " — " + unit.stage_name + (unit.batch_code ? " · Batch " + unit.batch_code : "") + (unit.rack ? " · Rack " + unit.rack : "");
    detailLink.href = unit.detail_url;
    verifiedPanel.hidden = false;

    stageSelect.replaceChildren();
    const names = stageNames[unit.crop_type] || [];
    names.forEach(function (name, index) {
      const option = document.createElement("option");
      option.value = String(index + 1);
      option.textContent = "Stage " + (index + 1) + " — " + name;
      if (index + 1 === Number(unit.growth_stage)) option.selected = true;
      stageSelect.appendChild(option);
    });
    stageReview.hidden = false;
    confirmStage.checked = false;
    scanStatus.textContent = "Verified: " + unit.unit_name + ". The current stage was loaded from the registered database record.";
  }

  async function scanOneFrame() {
    if (!scanActive || scanBusy) return;
    scanBusy = true;
    try {
      const response = await fetch(scanUrl, {
        method: "POST",
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "QR scan request failed.");
      if (!data.detected) {
        scanStatus.textContent = data.message || "No QR code found. Keep the label inside the frame.";
      } else if (!data.registered) {
        stopQrScan(data.message || "QR detected, but no registered unit matched it.");
        verifiedUnit = null;
        verifiedPanel.hidden = true;
        stageReview.hidden = true;
        captureUnit.value = "";
      } else {
        showVerifiedUnit(data.unit);
        stopQrScan("Registered unit verified: " + data.unit.unit_name + ". You can now capture its photograph.");
      }
    } catch (error) {
      stopQrScan("QR scan failed: " + error.message);
    } finally {
      scanBusy = false;
    }
    if (scanActive) scanTimer = window.setTimeout(scanOneFrame, 1300);
  }

  scanButton.addEventListener("click", function () {
    if (!configured || scanActive) return;
    if (!streamStarted) {
      scanStatus.textContent = "Start Live Preview first, then scan the unit QR label.";
      return;
    }
    verifiedUnit = null;
    verifiedPanel.hidden = true;
    stageReview.hidden = true;
    confirmStage.checked = false;
    scanActive = true;
    scanButton.disabled = true;
    stopScanButton.disabled = false;
    scanStatus.textContent = "Reading QR from the live Camlora camera… hold the label steady.";
    scanOneFrame();
  });

  stopScanButton.addEventListener("click", function () {
    stopQrScan("QR scan stopped.");
  });

  captureUnit.addEventListener("change", function () {
    if (verifiedUnit && captureUnit.value !== String(verifiedUnit.id)) {
      verifiedUnit = null;
      verifiedPanel.hidden = true;
      stageReview.hidden = true;
      confirmStage.checked = false;
      scanStatus.textContent = "The selected unit changed. Read its QR label again before confirming a stage update.";
    }
  });

  captureForm.addEventListener("submit", async function (event) {
    event.preventDefault();
    if (!configured) return;
    if (confirmStage.checked && !verifiedUnit) {
      captureResult.textContent = "Scan and verify a registered unit QR before confirming a stage update.";
      return;
    }
    captureButton.disabled = true;
    captureResult.textContent = "Requesting a JPEG snapshot from your phone…";
    try {
      const response = await fetch(captureUrl, {
        method: "POST",
        body: new FormData(captureForm),
        headers: { "Accept": "application/json" },
        credentials: "same-origin"
      });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Snapshot could not be saved.");
      captureResult.textContent = data.message;
      if (data.stage_changed) {
        captureResult.textContent += " Growth stage updated from Stage " + data.previous_stage + " to Stage " + data.current_stage + " after your confirmation.";
      } else if (data.unit_id) {
        captureResult.textContent += " Linked to the verified growing unit; its saved stage was not changed.";
      } else {
        captureResult.textContent += " Saved without a growing-unit link.";
      }
      const oldLink = document.getElementById("camlora-last-snapshot");
      if (oldLink) oldLink.remove();
      const link = document.createElement("a");
      link.id = "camlora-last-snapshot";
      link.href = data.image_url;
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = " View saved photo";
      captureResult.appendChild(link);
      if (data.detail_url) {
        const detail = document.createElement("a");
        detail.href = data.detail_url;
        detail.textContent = " · Open updated unit record";
        captureResult.appendChild(detail);
      }
      if (data.stage_changed && verifiedUnit) {
        verifiedUnit.growth_stage = data.current_stage;
        const names = stageNames[verifiedUnit.crop_type] || [];
        verifiedUnit.stage_name = names[data.current_stage - 1] || "Unknown stage";
        verifiedDetails.textContent = "Registered " + verifiedUnit.crop_type + " · Current saved stage: Stage " + verifiedUnit.growth_stage + " — " + verifiedUnit.stage_name;
        const stageLabel = document.getElementById("selected-growth-stage-label");
        const stageProgress = document.getElementById("selected-growth-stage-progress");
        if (stageLabel && Number(stageLabel.dataset.unitId) === Number(verifiedUnit.id)) {
          stageLabel.textContent = "Stage " + data.current_stage + " / 4";
        }
        if (stageProgress && Number(stageProgress.dataset.unitId) === Number(verifiedUnit.id)) {
          stageProgress.style.width = (Number(data.current_stage) * 25) + "%";
        }
        confirmStage.checked = false;
      }
    } catch (error) {
      captureResult.textContent = "Capture failed: " + error.message;
    } finally {
      captureButton.disabled = false;
    }
  });

  window.addEventListener("pagehide", function () {
    stopQrScan();
  });
  if (!configured) setCameraStatus("Not configured. Add CAMLORA_BASE_URL to .env and restart MushroomGuard AI.", "error");
})();
