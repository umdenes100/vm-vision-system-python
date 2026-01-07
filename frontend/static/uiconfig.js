(function () {
  async function loadUiConfig() {
    const titleEl = document.getElementById("headerTitle");
    const navEl = document.getElementById("headerLinks");
    if (!titleEl || !navEl) return;

    function forceVisibleText(el) {
      // Use important to defeat external CSS (bootstrap/theme/index.css)
      el.style.setProperty("display", "inline-block", "important");
      el.style.setProperty("color", "#ffffff", "important");
      el.style.setProperty("-webkit-text-fill-color", "#ffffff", "important");
      el.style.setProperty("opacity", "1", "important");
      el.style.setProperty("visibility", "visible", "important");
      el.style.setProperty("text-decoration", "none", "important");
      el.style.setProperty("font-weight", "600", "important");
      el.style.setProperty("font-size", "14px", "important");
      el.style.setProperty("line-height", "1", "important");

      // Defeat weird theme tricks
      el.style.setProperty("filter", "none", "important");
      el.style.setProperty("mix-blend-mode", "normal", "important");
      el.style.setProperty("text-shadow", "0 0 1px rgba(0,0,0,0.35)", "important");
    }

    function renderFallbackLinks() {
      navEl.innerHTML = "";
      for (let i = 1; i <= 5; i++) {
        const a = document.createElement("a");
        a.textContent = `Link${i}`;
        a.href = "#";
        a.onclick = () => false;
        forceVisibleText(a);
        navEl.appendChild(a);
      }
    }

    function normalizeLinks(cfg) {
      if (Array.isArray(cfg.links)) {
        return cfg.links
          .slice(0, 5)
          .map((x) => ({
            name: String(x?.name ?? "").trim(),
            url: String(x?.url ?? "").trim(),
          }))
          .filter((x) => x.name.length > 0);
      }

      const out = [];
      for (let i = 1; i <= 5; i++) {
        const name =
          String(
            cfg[`link${i}_name`] ??
              cfg[`link${i}Name`] ??
              cfg[`link${i}`] ??
              ""
          ).trim();

        const url =
          String(
            cfg[`link${i}_url`] ??
              cfg[`link${i}Url`] ??
              cfg[`url${i}`] ??
              "#"
          ).trim();

        if (name) out.push({ name, url });
      }
      return out;
    }

    try {
      const r = await fetch("/static/ui-config.json", { cache: "no-store" });
      if (!r.ok) throw new Error("ui-config.json not found");
      const cfg = await r.json();

      const cls = String(cfg.class_name || "<Class Name>").trim();
      const room = String(cfg.room || "<Room Placeholder>").trim();

      titleEl.textContent = `${cls} ${room} Vision System`;
      forceVisibleText(titleEl);

      const links = normalizeLinks(cfg);

      navEl.innerHTML = "";
      if (links.length === 0) {
        renderFallbackLinks();
        return;
      }

      for (const item of links) {
        const a = document.createElement("a");
        a.textContent = item.name;
        a.href = item.url || "#";
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        forceVisibleText(a);
        navEl.appendChild(a);
      }
    } catch (_e) {
      renderFallbackLinks();
      if (titleEl) forceVisibleText(titleEl);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadUiConfig);
  } else {
    loadUiConfig();
  }
})();
