(function () {
  async function loadUiConfig() {
    const titleEl = document.getElementById("headerTitle");
    const navEl = document.getElementById("headerLinks");
    if (!titleEl || !navEl) return;

    function renderFallbackLinks() {
      navEl.innerHTML = "";
      for (let i = 1; i <= 5; i++) {
        const a = document.createElement("a");
        a.textContent = `Link${i}`;
        a.href = "#";
        a.onclick = () => false;
        a.style.display = "inline-block";
        navEl.appendChild(a);
      }
    }

    function normalizeLinks(cfg) {
      // Preferred schema:
      // { links: [ {name:"Link1", url:"https://..."}, ... ] }
      if (Array.isArray(cfg.links)) {
        return cfg.links
          .slice(0, 5)
          .map((x) => ({
            name: String(x?.name ?? "").trim(),
            url: String(x?.url ?? "").trim(),
          }))
          .filter((x) => x.name.length > 0);
      }

      // Backward/alternate schemas:
      // link1_name/link1_url, link2_name/link2_url, ...
      // OR link1/link1_url, ...
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

      const links = normalizeLinks(cfg);

      navEl.innerHTML = "";
      if (links.length === 0) {
        // If config has no usable link entries, keep a visible placeholder set
        renderFallbackLinks();
        return;
      }

      for (const item of links) {
        if (!item.name) continue;

        const a = document.createElement("a");
        a.textContent = item.name;
        a.href = item.url || "#";
        a.target = "_blank";
        a.rel = "noopener noreferrer";
        a.style.display = "inline-block"; // protect against accidental CSS hiding
        navEl.appendChild(a);
      }
    } catch (_e) {
      renderFallbackLinks();
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", loadUiConfig);
  } else {
    loadUiConfig();
  }
})();
