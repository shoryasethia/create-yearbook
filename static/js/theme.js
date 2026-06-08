(function () {
  const STORAGE_KEY = "scrape-yearbook-theme";

  function getPreferred() {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved === "light" || saved === "dark") return saved;
    return "dark";
  }

  function apply(theme) {
    document.documentElement.classList.toggle("dark", theme === "dark");
    localStorage.setItem(STORAGE_KEY, theme);
  }

  apply(getPreferred());

  document.addEventListener("DOMContentLoaded", function () {
    const btn = document.getElementById("theme-toggle");
    if (!btn) return;

    btn.addEventListener("click", function () {
      const next = document.documentElement.classList.contains("dark") ? "light" : "dark";
      apply(next);
    });
  });
})();
