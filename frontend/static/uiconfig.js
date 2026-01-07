(function () {
  async function loadUiConfig() {
    const titleEl = document.getElementById("headerTitle");
    const navEl = document.getElementById("headerLinks");
    if (!titleEl || !navEl) return;

    function fallbackLinks() {
      navEl.innerHTML = "";
      for (let i = 1; i <= 5; i++) {
        const a = document.createElement("a");
        a.textContent = `Link${i}`;
        a.href = "#";
        a.onclick = () => false;
        navEl.appendChild(a);
      }
    }

    try {
      const r = await fetch("/static/ui-config.json", { cache: "no-store" });
      if (!r.ok) throw new Error("ui-config.json not found");
      const cfg = await r.json();

      const cls = String(cfg.class_name || "<Class Name>").trim();
      const room = String(cfg.room || "<Room Placeholder>").trim();
      titleEl.textContent = `${cls} ${room} Vision System`;

      navEl.innerHTML = "";
      const links = Array.isArray(cfg.links) ? cfg.links : [];
      for (const item of links.slice(0, 5)) {
        const name = String(item?.name || "").trim();
        const url = String(item?.url || "").trim();
        if (!name) continue;

        const a = document.createElement("a");
        a.textContent = name;
        a.href = url || "#";
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        navEl.appendChild(a);
      }

      if (!navEl.children.length) fallbackLinks();
    } catch (_e) {
      // If config read fails, show placeholder links
      fallbackLinks();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadUiConfig);
  } else {
    loadUiConfig();
  }
})();
