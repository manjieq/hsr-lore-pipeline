(function () {
  const CATEGORY_LABELS = {
    light_cone: "Light Cone",
    relic_set: "Relic Set",
    character_story: "Character Story",
  };
  // Spelled out rather than derived by appending "s": "character story"
  // pluralizes to "character stories", and the naive form shipped
  // "9 character storys" into the summary line.
  const CATEGORY_LABELS_PLURAL = {
    light_cone: "light cones",
    relic_set: "relic sets",
    character_story: "character stories",
  };
  // Order categories consistently wherever they are listed, rather than by
  // whatever order the data happens to produce.
  const CATEGORY_ORDER = ["light_cone", "relic_set", "character_story"];

  // The browse list renders every matching connection's full evidence on
  // expand, so the initial page is capped and grown on demand -- 456
  // entities x their entries is far too much DOM to build up front.
  const PAGE_SIZE = 30;

  let entriesById = new Map();
  let entities = [];
  let entitiesById = new Map();
  let activeFilter = "all";
  let searchQuery = "";
  let visibleCount = PAGE_SIZE;
  // Read once at startup and cleared by the first browse render: ?id= means
  // "expand this on arrival", not "keep re-expanding it on every subsequent
  // render" (which is what re-reading the URL per render did -- it sprang
  // back open on each search keystroke).
  let pendingDeepLinkId = null;

  // Escapes for both text and attribute position, so the quote characters
  // matter: a textContent/innerHTML roundtrip leaves " and ' untouched,
  // which is fine inside an element but lets a value break out of an
  // attribute (href, class) it is interpolated into.
  function escapeHtml(str) {
    return String(str == null ? "" : str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function plural(n, singular, pluralForm) {
    return `${n} ${n === 1 ? singular : pluralForm || singular + "s"}`;
  }

  /** "4 light cones, 2 relic sets and 9 character stories" */
  function describeSpread(categoryCounts) {
    const parts = CATEGORY_ORDER.filter((c) => categoryCounts[c]).map((c) =>
      plural(categoryCounts[c], CATEGORY_LABELS[c].toLowerCase(), CATEGORY_LABELS_PLURAL[c])
    );
    if (parts.length === 1) return parts[0];
    return parts.slice(0, -1).join(", ") + " and " + parts[parts.length - 1];
  }

  /** One piece of evidence: the real in-game text, never a paraphrase. */
  function renderEvidence(entry) {
    const li = document.createElement("li");
    li.className = "evidence";
    li.innerHTML = `
      <div class="evidence-head">
        <span class="card-badge ${escapeHtml(entry.category)}">${escapeHtml(
      CATEGORY_LABELS[entry.category] || entry.category
    )}</span>
        <h4 class="evidence-name">${escapeHtml(entry.name)}</h4>
      </div>
      <blockquote class="evidence-text">${escapeHtml(entry.raw_text)}</blockquote>
      <p class="card-source">
        <a href="${escapeHtml(entry.source_url)}" target="_blank" rel="noopener">Source on the wiki</a>
      </p>
    `;
    return li;
  }

  function renderConnection(entity, { expanded = false, featured = false } = {}) {
    const wrapper = document.createElement("article");
    wrapper.className = "card connection" + (featured ? " featured" : "");
    wrapper.id = "entity-" + entity.id;

    const spread = describeSpread(entity.category_counts);
    const bridges = entity.category_span > 1;

    wrapper.innerHTML = `
      <div class="connection-head">
        <h3 class="connection-name">${escapeHtml(entity.name)}</h3>
        ${entity.kind === "character" ? '<span class="kind-tag">Character</span>' : ""}
      </div>
      <p class="connection-summary">
        Appears in <strong>${escapeHtml(
          plural(entity.entry_count, "entry", "entries")
        )}</strong> &mdash; ${escapeHtml(spread)}.
      </p>
      ${
        bridges
          ? `<p class="connection-note">Links ${escapeHtml(
              String(entity.category_span)
            )} different kinds of lore that never reference each other directly.</p>`
          : ""
      }
      <button type="button" class="card-toggle" aria-expanded="false">
        Show the ${escapeHtml(String(entity.entry_count))} sources
      </button>
      <ul class="evidence-list" hidden></ul>
    `;

    const btn = wrapper.querySelector(".card-toggle");
    const list = wrapper.querySelector(".evidence-list");
    let built = false;

    const setExpanded = (isOpen) => {
      if (isOpen && !built) {
        // Built lazily: a 36-entry connection is a lot of DOM to create
        // for a card the reader may never open.
        entity.entry_ids
          .map((id) => entriesById.get(id))
          .filter(Boolean)
          .sort(
            (a, b) =>
              CATEGORY_ORDER.indexOf(a.category) - CATEGORY_ORDER.indexOf(b.category) ||
              a.name.localeCompare(b.name)
          )
          .forEach((entry) => list.appendChild(renderEvidence(entry)));
        built = true;
      }
      list.hidden = !isOpen;
      btn.setAttribute("aria-expanded", String(isOpen));
      btn.textContent = isOpen
        ? "Hide sources"
        : `Show the ${entity.entry_count} sources`;
    };

    btn.addEventListener("click", () => setExpanded(list.hidden));
    if (expanded) setExpanded(true);
    return wrapper;
  }

  function renderDaily(entityId) {
    const slot = document.getElementById("daily-slot");
    slot.innerHTML = "";
    const entity = entityId ? entitiesById.get(entityId) : null;
    if (!entity) {
      slot.innerHTML = '<p class="card">No connection available today — check back soon.</p>';
      return;
    }
    slot.appendChild(renderConnection(entity, { expanded: true, featured: true }));
  }

  function renderFilterTabs() {
    const tabs = document.getElementById("filter-tabs");
    tabs.innerHTML = "";
    const options = [
      ["all", "All"],
      ["bridging", "Cross-category"],
      ["character", "Characters"],
    ];
    options.forEach(([value, label]) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "filter-tab";
      btn.textContent = label;
      btn.setAttribute("role", "tab");
      btn.setAttribute("aria-selected", String(value === activeFilter));
      btn.addEventListener("click", () => {
        activeFilter = value;
        visibleCount = PAGE_SIZE;
        renderFilterTabs();
        renderBrowse();
      });
      tabs.appendChild(btn);
    });
  }

  function matching() {
    const query = searchQuery.trim().toLowerCase();
    return entities.filter((e) => {
      if (activeFilter === "bridging" && e.category_span < 2) return false;
      if (activeFilter === "character" && e.kind !== "character") return false;
      return !query || e.name.toLowerCase().includes(query);
    });
  }

  function renderBrowse() {
    const grid = document.getElementById("browse-grid");
    const count = document.getElementById("result-count");
    const more = document.getElementById("show-more");
    grid.innerHTML = "";

    const deepLinkId = pendingDeepLinkId;
    pendingDeepLinkId = null;

    const all = matching();
    if (all.length === 0) {
      count.textContent = "";
      more.hidden = true;
      grid.innerHTML = '<p class="card no-results">No connections match your search.</p>';
      return;
    }

    // A deep-linked connection may sit past the visible window; make sure
    // it is rendered so the scroll target below actually exists.
    const deepLinkIndex = deepLinkId ? all.findIndex((e) => e.id === deepLinkId) : -1;
    if (deepLinkIndex >= visibleCount) visibleCount = deepLinkIndex + 1;

    const shown = all.slice(0, visibleCount);
    shown.forEach((entity) => {
      grid.appendChild(renderConnection(entity, { expanded: entity.id === deepLinkId }));
    });

    count.textContent = `Showing ${shown.length} of ${plural(all.length, "connection")}.`;
    more.hidden = shown.length >= all.length;
  }

  function renderLastUpdated(entries) {
    const footer = document.getElementById("last-updated");
    if (!footer || entries.length === 0) return;
    const latest = entries.reduce(
      (max, e) => (e.date_updated > max ? e.date_updated : max),
      entries[0].date_updated
    );
    footer.textContent = `Lore data last updated ${latest}.`;
  }

  async function init() {
    // renderBrowse() consumes pendingDeepLinkId, so keep a local copy for
    // the scroll-into-view below, which runs after that first render.
    const deepLinkId = new URLSearchParams(window.location.search).get("id");
    pendingDeepLinkId = deepLinkId;

    const [entriesRes, entitiesRes] = await Promise.all([
      fetch("data/entries.json"),
      fetch("data/entities.json"),
    ]);
    const entries = await entriesRes.json();
    const entityData = await entitiesRes.json();

    entriesById = new Map(entries.map((e) => [e.id, e]));
    entities = entityData.entities;
    entitiesById = new Map(entities.map((e) => [e.id, e]));

    renderDaily(
      selectDailyConnectionId(entityData.connection_cycle, entitiesById, new Date())
    );
    renderFilterTabs();
    renderBrowse();
    renderLastUpdated(entries);

    const searchInput = document.getElementById("search-input");
    searchInput.addEventListener("input", () => {
      searchQuery = searchInput.value;
      visibleCount = PAGE_SIZE;
      renderBrowse();
    });

    document.getElementById("show-more").addEventListener("click", () => {
      visibleCount += PAGE_SIZE;
      renderBrowse();
    });

    if (deepLinkId) {
      const target = document.getElementById("entity-" + deepLinkId);
      if (target) target.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  }

  init().catch((err) => {
    console.error("Failed to load lore data", err);
    const slot = document.getElementById("daily-slot");
    if (slot) slot.innerHTML = '<p class="card">Couldn\'t load today\'s connection. Try refreshing.</p>';
  });
})();
