(function () {
  "use strict";
  var video = document.getElementById("qr-video");
  var start = document.getElementById("start-scan");
  var stop = document.getElementById("stop-scan");
  var status = document.getElementById("scan-status");
  var input = document.getElementById("code");
  var stream = null;
  var detector = null;
  var active = false;
  if (!video || !start) return;
  function stopCamera() {
    active = false;
    if (stream) stream.getTracks().forEach(function (track) { track.stop(); });
    stream = null;
    video.srcObject = null;
    start.disabled = false;
    stop.disabled = true;
  }
  async function scanFrame() {
    if (!active) return;
    try {
      if (video.readyState >= 2) {
        var codes = await detector.detect(video);
        if (codes.length) {
          input.value = codes[0].rawValue;
          status.textContent = "QR detected. Looking up the growing unit…";
          stopCamera();
          input.form.requestSubmit();
          return;
        }
      }
    } catch (err) {
      status.textContent = "Camera scan error: " + err.message;
      stopCamera();
      return;
    }
    window.setTimeout(scanFrame, 250);
  }
  start.addEventListener("click", async function () {
    if (!("BarcodeDetector" in window)) {
      status.textContent = "This browser does not support native QR scanning. Enter the printed bag ID below.";
      return;
    }
    try {
      detector = new BarcodeDetector({ formats: ["qr_code"] });
      stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment" }, audio: false });
      video.srcObject = stream;
      await video.play();
      active = true;
      start.disabled = true;
      stop.disabled = false;
      status.textContent = "Point the camera at a MushroomGuard QR label.";
      scanFrame();
    } catch (err) {
      status.textContent = "Could not start the camera: " + err.message + ". Enter the bag ID manually.";
      stopCamera();
    }
  });
  stop.addEventListener("click", function () {
    stopCamera();
    status.textContent = "Camera scan stopped.";
  });
  window.addEventListener("pagehide", stopCamera);
})();
