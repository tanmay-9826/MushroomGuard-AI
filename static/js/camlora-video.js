(function () {
  "use strict";
  const root = document.getElementById("camlora-video-workflow");
  if (!root) return;
  const configured = root.dataset.configured === "true";
  const startUrl = root.dataset.startUrl;
  const unitSelect = document.getElementById("video-unit-id");
  const notes = document.getElementById("video-notes");
  const startButton = document.getElementById("video-record-start");
  const stopButton = document.getElementById("video-record-stop");
  const status = document.getElementById("video-record-status");
  let current = null;
  let pollHandle = null;

  function setStatus(message, state) {
    status.textContent = message;
    status.dataset.state = state || "neutral";
  }

  async function postForm(url, formData) {
    const response = await fetch(url, {
      method: "POST", body: formData,
      headers: { "Accept": "application/json" }, credentials: "same-origin"
    });
    let data = {};
    try { data = await response.json(); } catch (_) { /* response body was not JSON */ }
    if (!response.ok || !data.ok) throw new Error(data.error || "Request failed (HTTP " + response.status + ").");
    return data;
  }

  async function poll() {
    if (!current) return;
    try {
      const response = await fetch(current.statusUrl, { credentials: "same-origin", cache: "no-store" });
      const data = await response.json();
      if (!response.ok || !data.ok) throw new Error(data.error || "Could not read recording status.");
      setStatus("Recording " + data.status + " · " + Number(data.duration_seconds || 0).toFixed(1) + " sec · " + (data.frame_count || 0) + " frames", data.status === "recording" ? "success" : "pending");
      if (["stopped", "completed", "failed"].includes(data.status)) {
        clearInterval(pollHandle);
        pollHandle = null;
        current = null;
        startButton.disabled = !configured || !unitSelect.value;
        stopButton.disabled = true;
        if (data.status === "failed") {
          setStatus("Recording failed: " + (data.error || "No readable frames were recorded."), "error");
        } else {
          setStatus("Video saved. " + data.frame_count + " frames recorded. Reloading the page to show extraction and analysis actions…", "success");
          window.setTimeout(function () { window.location.reload(); }, 900);
        }
      }
    } catch (error) {
      setStatus("Recording status check failed: " + error.message, "error");
    }
  }

  unitSelect.addEventListener("change", function () {
    startButton.disabled = !configured || !unitSelect.value || Boolean(current);
  });

  startButton.addEventListener("click", async function () {
    if (!configured || !unitSelect.value || current) return;
    startButton.disabled = true;
    stopButton.disabled = false;
    setStatus("Connecting to Camlora and opening MP4 recorder…", "pending");
    const body = new FormData();
    body.append("unit_id", unitSelect.value);
    body.append("notes", notes.value || "");
    try {
      const data = await postForm(startUrl, body);
      current = { id: data.recording_id, statusUrl: data.status_url, stopUrl: data.stop_url };
      setStatus(data.message + " Recording is limited to 10 minutes per session.", "success");
      pollHandle = window.setInterval(poll, 1500);
      poll();
    } catch (error) {
      current = null;
      startButton.disabled = !configured || !unitSelect.value;
      stopButton.disabled = true;
      setStatus("Could not start recording: " + error.message, "error");
    }
  });

  stopButton.addEventListener("click", async function () {
    if (!current) return;
    stopButton.disabled = true;
    setStatus("Stopping the stream and finalising the MP4 file…", "pending");
    try {
      await postForm(current.stopUrl, new FormData());
      setStatus("Stop requested. Waiting for MP4 finalisation…", "pending");
      if (!pollHandle) pollHandle = window.setInterval(poll, 1500);
      poll();
    } catch (error) {
      stopButton.disabled = false;
      setStatus("Could not stop recording: " + error.message, "error");
    }
  });

  document.querySelectorAll(".video-extract-frames").forEach(function (button) {
    button.addEventListener("click", async function () {
      button.disabled = true;
      const oldText = button.textContent;
      button.textContent = "Extracting…";
      try {
        const data = await postForm(button.dataset.url, new FormData());
        setStatus(data.message, "success");
        window.setTimeout(function () { window.location.reload(); }, 700);
      } catch (error) {
        button.textContent = oldText;
        button.disabled = false;
        setStatus("Frame extraction failed: " + error.message, "error");
      }
    });
  });

  document.querySelectorAll(".video-run-yolo").forEach(function (button) {
    button.addEventListener("click", async function () {
      button.disabled = true;
      button.textContent = "Analysing…";
      try {
        const data = await postForm(button.dataset.url, new FormData());
        setStatus(data.message + " Predicted Stage " + data.stage + " (" + (data.confidence * 100).toFixed(1) + "%).", "success");
        window.setTimeout(function () { window.location.reload(); }, 1000);
      } catch (error) {
        button.disabled = false;
        button.textContent = "Analyse with YOLO";
        setStatus("YOLO analysis not completed: " + error.message, "error");
      }
    });
  });

  document.querySelectorAll(".video-label-form").forEach(function (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      const button = form.querySelector("button[type='submit']");
      button.disabled = true;
      try {
        const data = await postForm(form.action, new FormData(form));
        setStatus(data.message, "success");
        window.setTimeout(function () { window.location.reload(); }, 700);
      } catch (error) {
        button.disabled = false;
        setStatus("Could not save training label: " + error.message, "error");
      }
    });
  });

  document.querySelectorAll(".video-confirm-form").forEach(function (form) {
    form.addEventListener("submit", async function (event) {
      event.preventDefault();
      const button = form.querySelector("button[type='submit']");
      button.disabled = true;
      try {
        const data = await postForm(form.action, new FormData(form));
        setStatus(data.message, "success");
        window.setTimeout(function () { window.location.reload(); }, 700);
      } catch (error) {
        button.disabled = false;
        setStatus("Stage confirmation failed: " + error.message, "error");
      }
    });
  });

  if (!configured) setStatus("Camlora is not configured. Set CAMLORA_BASE_URL in .env.", "error");
})();
