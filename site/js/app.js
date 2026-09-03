(function () {
  const CATEGORY_LABELS = { light_cone: "Light Cone", relic_set: "Relic Set" };

  let entries = [];
  let entriesById = new Map();
  let activeFilter = "all";
  let searchQuery = "";

  function escapeHtml(str) {
    const div = document.createElement("div");
    div.textContent = str == null ? "" : str;
    return div.innerHTML;
  }

  function renderCard(entry, { expanded } = {}) {
    const label = CATEGORY_LABELS[entry.category] || entry.category;
    const wrapper = document.createElement("article");
    wrapper.className = "card";
    wrapper.id = "entry-" + entry.id;

    wrapper.innerHTML = `
      <span class="card-badge ${escapeHtml(entry.category)}">${escapeHtml(label)}</span>
      <h3 class="card-name">${escapeHtml(entry.name)}</h3>
      ${entry.subtitle ? `<p class="card-subtitle">${escapeHtml(entry.subtitle)}</p>` : ""}
      <p class="card-short">${escapeHtml(entry.short_text)}</p>
      <button type="button" class="card-toggle" aria-expanded="false">Read the full text</button>
      <div class="card-full" hidden>
        <blockquote>${escapeHtml(entry.raw_text)}</blockquote>
        <p class="card-source">Source: <a href="${escapeHtml(entry.source_url)}" target="_blank" rel="noopener">${escapeHtml(entry.source_url)}</a></p>
      </div>
    `;

    const btn = wrapper.querySelector(".card-toggle");
    const full = wrapper.querySelector(".card-full");
    const setExpanded = (isOpen) => {
      full.hidden = !isOpen;
      btn.setAttribute("aria-expanded", String(isOpen));
      btn.textContent = isOpen ? "Hide full text" : "Read the full text";
    };
    btn.addEventListener("click", () => setExpanded(full.hidden));
    if (expanded) setExpanded(true);

    return wrapper;
  }

  function renderDaily(dailyId) {
    const slot = document.getElementById("daily-card-slot");
    slot.innerHTML = "";
    const entry = dailyId ? entriesById.get(dailyId) : null;
    if (!entry) {
      slot.innerHTML = '<p class="card">No fact available today — check back soon.</p>';
      return;
    }
    slot.appendChild(renderCard(entry));
  }

  function renderFilterTabs() {
    const categories = ["all", ...new Set(entries.map((e) => e.category))];
    const tabs = document.getElementById("filter-tabs");
    tabs.innerHTML = "";
    categories.forEach((cat) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "filter-tab";
      btn.textContent = cat === "all" ? "All" : CATEGORY_LABELS[cat] || cat;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(cat === activeFilter));
      btn.addEventListener("click", () => {
        activeFilter = cat;
        renderFilterTabs();
        renderBrowse();
      });
      tabs.appendChild(btn);
    });
  }

  function renderBrowse() {
    const grid = document.getElementById("browse-grid");
    grid.innerHTML = "";
    const params = new URLSearchParams(window.location.search);
    const deepLinkId = params.get("id");
    const query = searchQuery.trim().toLowerCase();

    const visible = entries.filter(
      (e) =>
        e.reviewed &&
        (activeFilter === "all" || e.category === activeFilter) &&
        (!query || e.name.toLowerCase().includes(query))
    );

    if (visible.length === 0) {
      grid.innerHTML = '<p class="card no-results">No entries match your search.</p>';
      return;
    }
    visible.forEach((entry) => {
      grid.appendChild(renderCard(entry, { expanded: entry.id === deepLinkId }));
    });
  }

  function renderLastUpdated() {
    const footer = document.getElementById("last-updated");
    if (!footer || entries.length === 0) return;
    const latest = entries.reduce((max, e) => (e.date_updated > max ? e.date_updated : max), entries[0].date_updated);
    footer.textContent = `Lore data last updated ${latest}.`;
  }

  async function init() {
    const [entriesRes, cycleRes] = await Promise.all([
      fetch("data/entries.json"),
      fetch("data/daily_cycle.json"),
    ]);
    entries = await entriesRes.json();
    const cycleData = await cycleRes.json();
    entriesById = new Map(entries.map((e) => [e.id, e]));

    const dailyId = selectDailyId(cycleData, entriesById, new Date());
    renderDaily(dailyId);
    renderFilterTabs();
    renderBrowse();
    renderLastUpdated();

    const searchInput = document.getElementById("search-input");
    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value;
      renderBrowse();
    });

    const params = new URLSearchParams(window.location.search);
    const deepLinkId = params.get("id");
    if (deepLinkId) {
      const target = document.getElementById("entry-" + deepLinkId);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  init().catch((err) => {
    console.error("Failed to load lore data", err);
    const slot = document.getElementById("daily-card-slot");
    if (slot) slot.innerHTML = '<p class="card">Couldn\'t load today\'s fact. Try refreshing.</p>';
  });
})();
