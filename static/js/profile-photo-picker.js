(function () {
  "use strict";
  const MAX_DIMENSION = 1920;
  const JPEG_QUALITY = 0.88;

  function putFile(input, file) {
    const transfer = new DataTransfer();
    transfer.items.add(file);
    input.files = transfer.files;
  }

  function compress(file, cropSquare) {
    return new Promise((resolve, reject) => {
      const image = new Image();
      const url = URL.createObjectURL(file);
      image.onload = function () {
        URL.revokeObjectURL(url);
        const canvas = document.createElement("canvas");
        const context = canvas.getContext("2d");

        if (cropSquare) {
          const sourceSize = Math.min(image.width, image.height);
          const sourceX = Math.round((image.width - sourceSize) / 2);
          const sourceY = Math.round((image.height - sourceSize) / 2);
          const outputSize = Math.max(1, Math.min(MAX_DIMENSION, sourceSize));
          canvas.width = outputSize;
          canvas.height = outputSize;
          context.drawImage(
            image,
            sourceX,
            sourceY,
            sourceSize,
            sourceSize,
            0,
            0,
            outputSize,
            outputSize
          );
        } else {
          const scale = Math.min(1, MAX_DIMENSION / Math.max(image.width, image.height));
          canvas.width = Math.max(1, Math.round(image.width * scale));
          canvas.height = Math.max(1, Math.round(image.height * scale));
          context.drawImage(image, 0, 0, canvas.width, canvas.height);
        }

        canvas.toBlob((blob) => {
          if (!blob) return reject(new Error("The photo could not be prepared."));
          const name = (file.name.replace(/\.[^.]+$/, "") || "profile-photo") + ".jpg";
          resolve(new File([blob], name, {type: "image/jpeg"}));
        }, "image/jpeg", JPEG_QUALITY);
      };
      image.onerror = function () {
        URL.revokeObjectURL(url);
        reject(new Error("This photo format is not supported."));
      };
      image.src = url;
    });
  }

  function cameraErrorMessage(error) {
    if (!window.isSecureContext) {
      return "Camera access requires HTTPS or localhost.";
    }
    if (error && (error.name === "NotAllowedError" || error.name === "SecurityError")) {
      return "Camera permission was denied. Allow camera access in your browser settings and try again.";
    }
    if (error && error.name === "NotFoundError") {
      return "No camera was found on this device.";
    }
    if (error && (error.name === "NotReadableError" || error.name === "AbortError")) {
      return "The camera is busy or unavailable. Close other camera apps and try again.";
    }
    return "The camera could not be opened on this device.";
  }

  function initialise(root) {
    if (root.dataset.initialised) return;
    root.dataset.initialised = "true";
    const form = root.closest("form");
    const realInput = form && form.querySelector('input[name="picture"]');
    if (!realInput) { root.hidden = true; return; }

    const oldField = realInput.closest(".form-group") || realInput.parentElement;
    if (oldField) oldField.style.display = "none";
    const preview = root.querySelector("[data-photo-preview]");
    const placeholder = root.querySelector("[data-photo-placeholder]");
    const status = root.querySelector("[data-photo-status]");
    const help = root.querySelector("[data-photo-help]");
    const processing = root.querySelector("[data-photo-processing]");
    const removeButton = root.querySelector('[data-photo-action="remove"]');
    const removeInput = root.querySelector("[data-remove-photo]");
    const galleryInput = root.querySelector("[data-gallery-input]");
    const autoCrop = root.querySelector("[data-auto-crop]");
    const recordSelect = form.querySelector("[data-photo-record-select]");
    const allowCurrentRemove = root.dataset.allowCurrentRemove === "true";
    const cameraStage = root.querySelector("[data-camera-stage]");
    const cameraVideo = root.querySelector("[data-camera-video]");
    const cameraMessage = root.querySelector("[data-camera-message]");
    const captureButton = root.querySelector("[data-camera-capture]");
    const cancelButton = root.querySelector("[data-camera-cancel]");
    let objectUrl = "";
    let cameraStream = null;

    function show(url, label, removable) {
      preview.src = url;
      preview.hidden = false;
      placeholder.hidden = true;
      removeButton.hidden = removable === false;
      status.textContent = label;
      status.classList.remove("photo-picker__error");
      help.classList.remove("photo-picker__error");
    }

    function stopCamera() {
      if (cameraStream) {
        cameraStream.getTracks().forEach((track) => track.stop());
        cameraStream = null;
      }
      cameraVideo.srcObject = null;
      cameraStage.hidden = true;
      document.body.classList.remove("photo-camera-open");
    }

    let selectedRecordValue = null;

    function showSelectedRecord() {
      if (!recordSelect) return;
      const value = recordSelect.value || "";
      selectedRecordValue = value;
      realInput.value = "";
      removeInput.value = "0";

      if (!value) {
        preview.removeAttribute("src");
        preview.hidden = true;
        placeholder.hidden = false;
        removeButton.hidden = true;
        status.textContent = "Select a client";
        help.textContent = "Select a name to see the current photo.";
        return;
      }

      const option = Array.from(recordSelect.options).find((item) => item.value === value);
      const photoUrl = option ? option.dataset.photoUrl : "";
      if (photoUrl) {
        show(photoUrl, "Current photo", allowCurrentRemove);
        help.textContent = "This is the current profile photo. Take or upload a new photo to replace it.";
      } else {
        preview.removeAttribute("src");
        preview.hidden = true;
        placeholder.hidden = false;
        removeButton.hidden = true;
        status.textContent = "No current photo";
        help.textContent = "No existing photo was found. Take a photo or upload one from the gallery.";
      }
    }

    async function choose(file) {
      if (!file) return;
      if (!file.type.startsWith("image/")) {
        help.textContent = "Please choose an image file.";
        help.classList.add("photo-picker__error");
        return;
      }
      processing.hidden = false;
      status.textContent = "Preparing…";
      try {
        const resized = await compress(file, autoCrop.checked);
        putFile(realInput, resized);
        if (objectUrl) URL.revokeObjectURL(objectUrl);
        objectUrl = URL.createObjectURL(resized);
        removeInput.value = "0";
        show(objectUrl, autoCrop.checked ? "Cropped and ready" : "Resized and ready", true);
        help.textContent = (autoCrop.checked ? "Square crop ready: " : "Photo ready: ") + Math.round(resized.size / 1024) + " KB. You can retake, replace, or remove it.";
      } catch (error) {
        status.textContent = "Photo error";
        status.classList.add("photo-picker__error");
        help.textContent = error.message;
        help.classList.add("photo-picker__error");
      } finally {
        processing.hidden = true;
        galleryInput.value = "";
      }
    }

    async function openCamera() {
      cameraMessage.textContent = "Starting camera…";
      cameraMessage.classList.remove("photo-picker__error");
      captureButton.disabled = true;
      cameraStage.hidden = false;
      document.body.classList.add("photo-camera-open");

      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        cameraMessage.textContent = "Live camera access is not supported by this browser. Use Upload from Gallery instead.";
        cameraMessage.classList.add("photo-picker__error");
        return;
      }

      try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
          audio: false,
          video: {
            facingMode: {ideal: "environment"},
            width: {ideal: 2560},
            height: {ideal: 1440}
          }
        });
        cameraVideo.srcObject = cameraStream;
        await cameraVideo.play();
        cameraMessage.textContent = "Position the person clearly, then tap Capture Photo.";
        captureButton.disabled = false;
      } catch (error) {
        cameraMessage.textContent = cameraErrorMessage(error);
        cameraMessage.classList.add("photo-picker__error");
        status.textContent = "Camera unavailable";
        status.classList.add("photo-picker__error");
      }
    }

    function capturePhoto() {
      if (!cameraStream || !cameraVideo.videoWidth) return;
      captureButton.disabled = true;
      const canvas = document.createElement("canvas");
      canvas.width = cameraVideo.videoWidth;
      canvas.height = cameraVideo.videoHeight;
      canvas.getContext("2d").drawImage(cameraVideo, 0, 0);
      canvas.toBlob((blob) => {
        stopCamera();
        if (!blob) {
          help.textContent = "The camera image could not be captured. Please try again.";
          help.classList.add("photo-picker__error");
          return;
        }
        choose(new File([blob], "camera-photo.jpg", {type: "image/jpeg"}));
      }, "image/jpeg", 0.92);
    }

    if (recordSelect) {
      recordSelect.addEventListener("change", showSelectedRecord);
      recordSelect.addEventListener("input", showSelectedRecord);
      document.addEventListener("change", (event) => {
        if (event.target === recordSelect) showSelectedRecord();
      }, true);
      showSelectedRecord();

      // Some enhanced searchable selects update the original value without
      // consistently dispatching a native event. Keep the preview in sync.
      window.setInterval(() => {
        if (recordSelect.value !== selectedRecordValue) showSelectedRecord();
      }, 300);
    } else if (root.dataset.currentPhoto) {
      show(root.dataset.currentPhoto, "Current photo", true);
    }
    root.querySelector('[data-photo-action="camera"]').onclick = openCamera;
    root.querySelector('[data-photo-action="gallery"]').onclick = () => galleryInput.click();
    galleryInput.onchange = () => choose(galleryInput.files[0]);
    captureButton.onclick = capturePhoto;
    cancelButton.onclick = stopCamera;
    cameraStage.addEventListener("click", (event) => {
      if (event.target === cameraStage) stopCamera();
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && !cameraStage.hidden) stopCamera();
    });
    window.addEventListener("pagehide", stopCamera);

    removeButton.onclick = function () {
      if (!window.confirm("Remove this client's current profile picture?")) return;
      realInput.value = "";
      removeInput.value = "1";
      preview.hidden = true;
      placeholder.hidden = false;
      removeButton.hidden = true;
      status.textContent = "Removed";
      help.textContent = "The photo will be removed when this record is saved.";
    };

    form.addEventListener("submit", function () {
      stopCamera();
      const button = form.querySelector('button[type="submit"]');
      if (button) {
        button.disabled = true;
        button.innerHTML = '<span class="spinner-border spinner-border-sm mr-1" aria-hidden="true"></span>Saving photo…';
      }
      const progress = root.querySelector("[data-upload-progress]");
      const bar = progress.querySelector(".progress-bar");
      progress.hidden = false;
      bar.style.width = "100%";
      bar.textContent = "Uploading…";
      status.textContent = "Saving…";
      help.textContent = "Please keep this page open while the photo is being saved.";
    });
  }

  function boot() {
    document.querySelectorAll("[data-photo-picker]").forEach(initialise);
  }

  document.readyState === "loading"
    ? document.addEventListener("DOMContentLoaded", boot)
    : boot();
}());
