(function () {
  const STEPS = [
    "Authenticating with Yearbook…",
    "Fetching posts written for you…",
    "Fetching posts written by you…",
    "Downloading gallery images…",
    "Building your export…",
    "Almost done…",
  ];

  const BASE_SECONDS = 25;
  const GALLERY_EXTRA = 20;
  const PDF_EXTRA = 10;

  const form = document.getElementById("export-form");
  const overlay = document.getElementById("loader-overlay");
  const stepEl = document.getElementById("loader-step");
  const barEl = document.getElementById("loader-bar");
  const elapsedEl = document.getElementById("loader-elapsed");
  const etaEl = document.getElementById("loader-eta");
  const submitBtn = document.getElementById("submit-btn");

  if (!form || !overlay) return;

  let timer = null;
  let startTime = 0;
  let estimate = BASE_SECONDS;

  function formatTime(sec) {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return m > 0 ? `${m}:${String(s).padStart(2, "0")}` : `${s}s`;
  }

  function startLoader() {
    const isPdf = form.querySelector('[name="format"]:checked')?.value === "pdf";
    const includeGallery = form.querySelector('[name="include_gallery"]').checked;

    estimate = BASE_SECONDS;
    if (includeGallery) estimate += GALLERY_EXTRA;
    if (isPdf) estimate += PDF_EXTRA;

    overlay.classList.remove("hidden");
    overlay.classList.add("flex");
    submitBtn.disabled = true;
    startTime = Date.now();
    etaEl.textContent = `~${formatTime(estimate)} left`;

    let stepIndex = 0;
    let progress = 0;
    const stepInterval = (estimate * 1000) / STEPS.length;

    stepEl.textContent = STEPS[0];

    const stepTimer = setInterval(function () {
      stepIndex = Math.min(stepIndex + 1, STEPS.length - 1);
      stepEl.textContent = STEPS[stepIndex];
    }, stepInterval);

    timer = setInterval(function () {
      const elapsed = Math.floor((Date.now() - startTime) / 1000);
      elapsedEl.textContent = `${formatTime(elapsed)} elapsed`;

      const targetProgress = Math.min(92, (elapsed / estimate) * 100);
      progress += (targetProgress - progress) * 0.15;
      barEl.style.width = progress + "%";

      const remaining = Math.max(0, estimate - elapsed);
      if (remaining > 0) {
        etaEl.textContent = `~${formatTime(remaining)} left`;
      } else {
        etaEl.textContent = "Finishing up…";
        barEl.style.width = "96%";
      }
    }, 200);

    form._loaderTimers = { stepTimer, timer };
  }

  form.addEventListener("submit", function () {
    startLoader();
  });
})();
