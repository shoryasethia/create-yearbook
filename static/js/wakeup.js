(function () {
  const POLL_MS = 4000;
  const MAX_ATTEMPTS = 30;

  function sleep(ms) {
    return new Promise(function (resolve) {
      window.setTimeout(resolve, ms);
    });
  }

  async function pingHealth() {
    try {
      const response = await fetch("/health", {
        cache: "no-store",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return false;
      const data = await response.json();
      return data && data.status === "ok";
    } catch (_err) {
      return false;
    }
  }

  function showWake(overlay, shell, message) {
    if (overlay) overlay.classList.remove("hidden");
    if (shell) {
      shell.classList.add("invisible");
      shell.setAttribute("aria-hidden", "true");
    }
    if (message) {
      const el = document.getElementById("wake-message");
      if (el) el.textContent = message;
    }
  }

  function hideWake(overlay, shell) {
    if (overlay) overlay.classList.add("hidden");
    if (shell) {
      shell.classList.remove("invisible");
      shell.removeAttribute("aria-hidden");
    }
  }

  async function waitForBackend(overlay, shell) {
    if (await pingHealth()) {
      hideWake(overlay, shell);
      return true;
    }

    showWake(overlay, shell);

    for (let attempt = 0; attempt < MAX_ATTEMPTS; attempt += 1) {
      await sleep(POLL_MS);
      if (await pingHealth()) {
        hideWake(overlay, shell);
        return true;
      }
    }

    showWake(
      overlay,
      shell,
      "Still waking up. Please refresh in a minute or try again shortly."
    );
    return false;
  }

  document.addEventListener("DOMContentLoaded", function () {
    const overlay = document.getElementById("wake-overlay");
    const shell = document.getElementById("app-shell");
    if (!overlay || !shell) return;
    waitForBackend(overlay, shell);
  });

  window.waitForBackend = waitForBackend;
})();
