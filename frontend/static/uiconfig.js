// Loads ui-config.json and applies UI name + link URLs/labels.
// To customize: edit static/ui-config.json (no rebuild needed).

async function applyUiConfig() {
  try {
    const resp = await fetch('ui-config.json', { cache: 'no-store' });
    if (!resp.ok) throw new Error(`Failed to load ui-config.json: ${resp.status}`);
    const cfg = await resp.json();

    // UI name
    const name = cfg.uiName || 'ENES100 Vision System 2';
    const logoEl = document.getElementById('logo');
    if (logoEl) logoEl.textContent = name;
    document.title = name;

    // Navbar / general links
    const linkMap = {};
    (cfg.navLinks || []).forEach(l => { if (l && l.id) linkMap[l.id] = l; });

    document.querySelectorAll('[data-link-id]').forEach(a => {
      const id = a.getAttribute('data-link-id');
      const entry = linkMap[id];
      if (!entry) return;
      if (entry.url) a.setAttribute('href', entry.url);
      if (entry.label) a.textContent = entry.label;
      if (!a.getAttribute('target')) a.setAttribute('target', '_blank');
      a.setAttribute('rel', 'noopener');
    });

    // Other links (singletons)
    if (cfg.otherLinks && cfg.otherLinks.troubleshootingDoc) {
      const t = document.getElementById('troubleshooting-link');
      if (t) {
        t.setAttribute('href', cfg.otherLinks.troubleshootingDoc);
        t.setAttribute('target', '_blank');
        t.setAttribute('rel', 'noopener');
      }
    }
  } catch (err) {
    console.warn(err);
  }
}

document.addEventListener('DOMContentLoaded', applyUiConfig);
