(function () {
  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) {
      return navigator.clipboard.writeText(text);
    }

    return new Promise(function (resolve, reject) {
      const input = document.createElement("textarea");
      input.value = text;
      input.setAttribute("readonly", "");
      input.style.position = "fixed";
      input.style.left = "-9999px";
      document.body.appendChild(input);
      input.select();
      try {
        document.execCommand("copy") ? resolve() : reject();
      } catch (err) {
        reject(err);
      } finally {
        document.body.removeChild(input);
      }
    });
  }

  function showCopied(btn, label, toast, defaultLabel) {
    if (label) label.textContent = "Copied!";
    btn.setAttribute("aria-label", "Link copied");
    if (toast) {
      toast.textContent = "Copied to clipboard";
      toast.classList.add("visible");
    }

    window.setTimeout(function () {
      if (label) label.textContent = defaultLabel;
      btn.setAttribute("aria-label", "Copy site link to share");
      if (toast) toast.classList.remove("visible");
    }, 2200);
  }

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("share-btn");
    if (!btn) return;

    const url = btn.dataset.url || window.location.origin;
    const label = btn.querySelector("[data-share-label]");
    const toast = document.getElementById("share-toast");
    const defaultLabel = label ? label.textContent : "Share";

    btn.addEventListener("click", function () {
      copyText(url)
        .then(function () {
          showCopied(btn, label, toast, defaultLabel);
        })
        .catch(function () {
          if (label) label.textContent = "Failed";
          if (toast) {
            toast.textContent = "Could not copy link";
            toast.classList.add("visible");
          }
          window.setTimeout(function () {
            if (label) label.textContent = defaultLabel;
            if (toast) {
              toast.classList.remove("visible");
              toast.textContent = "Copied to clipboard";
            }
          }, 2200);
        });
    });
  });
})();
