/**
 * TechPulse — client-side renderer + smart data layer.
 *
 * Data flow:
 *   1. Paint instantly from localStorage (stale-while-revalidate); skeletons
 *      only ever show on a true first visit.
 *   2. Fetch data/feed.json — the initial request rides the <link rel=preload>
 *      and browser cache; background polls use cache:"no-cache" so the browser
 *      revalidates via ETag/Last-Modified (an unchanged feed costs one 304
 *      with no body).
 *   3. Poll every 5 minutes while the tab is visible; re-check on tab focus
 *      and when the network comes back. The DOM is only touched when
 *      updated_at actually changes, so updates land seamlessly with no
 *      layout shift and no hard refresh.
 */

const FEED_URL = "data/feed.json";
const STORAGE_KEY = "techpulse:feed";
const POLL_INTERVAL_MS = 5 * 60 * 1000;
const CLOCK_INTERVAL_MS = 60 * 1000;

const SOURCE_LABELS = {
  reddit: "REDDIT",
  hackernews: "HN",
  lobsters: "LOBSTERS",
  rss: "RSS",
};

const state = {
  data: null,
  catById: new Map(),    // id -> {id, label, accent}
  lastCheckAt: 0,
};

/* ---------- Boot ---------- */
function boot() {
  const cached = readCache();
  if (cached) {
    applyData(cached, { animate: false });
    setStatus("ok");
  }

  refresh({ initial: true });

  setInterval(() => {
    if (document.visibilityState === "visible") refresh();
  }, POLL_INTERVAL_MS);

  // Coming back to the tab after it sat hidden: catch up immediately
  // instead of waiting for the next interval tick.
  document.addEventListener("visibilitychange", () => {
    if (
      document.visibilityState === "visible" &&
      Date.now() - state.lastCheckAt > POLL_INTERVAL_MS
    ) {
      refresh();
    }
  });

  window.addEventListener("online", () => refresh());

  setInterval(tickClocks, CLOCK_INTERVAL_MS);
}

/* ---------- Fetch / poll ---------- */
async function refresh({ initial = false } = {}) {
  state.lastCheckAt = Date.now();
  try {
    // Default cache mode on the first request so it matches the
    // <link rel="preload"> in index.html; polls force revalidation.
    const res = await fetch(FEED_URL, initial ? {} : { cache: "no-cache" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    const hadData = state.data != null;
    const changed = data?.updated_at !== state.data?.updated_at;
    if (changed) {
      applyData(data, { animate: !hadData });
      writeCache(data);
      if (hadData) flashDot(); // new content arrived in the background
    } else {
      renderUpdated(); // keep the relative timestamp fresh
    }
    setStatus("ok");
  } catch (err) {
    console.error("Feed refresh failed:", err);
    if (state.data) {
      setStatus("stale"); // keep showing what we have
    } else {
      setStatus("error");
      showError();
    }
  }
}

function applyData(data, { animate }) {
  state.data = data;
  indexCategories();
  document.getElementById("error-state").classList.add("hidden");
  renderAll(animate);
}

function indexCategories() {
  state.catById.clear();
  for (const c of state.data?.categories || []) {
    state.catById.set(c.id, c);
  }
}

/* ---------- localStorage cache ---------- */
function readCache() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw);
    return parsed && Array.isArray(parsed.categories) ? parsed : null;
  } catch {
    return null; // corrupt cache / storage disabled — fall through to fetch
  }
}

function writeCache(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
  } catch {
    /* private mode / quota — cache is best-effort */
  }
}

/* ---------- Status / timestamp ---------- */
function setStatus(kind) {
  const dot = document.getElementById("status-dot");
  dot.classList.remove("ok", "error", "stale");
  dot.classList.add(kind);
  dot.title =
    kind === "ok" ? "feed loaded"
    : kind === "stale" ? "showing cached feed — refresh failing"
    : "feed unavailable";
}

function flashDot() {
  const dot = document.getElementById("status-dot");
  dot.classList.remove("flash");
  void dot.offsetWidth; // restart the animation
  dot.classList.add("flash");
}

function renderUpdated() {
  const el = document.getElementById("updated-time");
  if (!state.data?.updated_at) {
    el.textContent = "never";
    return;
  }
  const d = new Date(state.data.updated_at);
  el.dateTime = state.data.updated_at;
  el.textContent = relativeTime(d);
  el.title = d.toLocaleString();
}

// Re-render only the relative timestamps, leaving the rest of the DOM alone.
function tickClocks() {
  renderUpdated();
  for (const el of document.querySelectorAll("[data-published]")) {
    const d = new Date(el.dataset.published);
    if (!isNaN(d)) el.textContent = relativeTime(d);
  }
}

function relativeTime(date) {
  const diff = (Date.now() - date.getTime()) / 1000;
  if (diff < 60) return "just now";              // also catches small clock skew
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

/* ---------- Pulse strip (per-category counts in header) ---------- */
function renderPulse() {
  const strip = document.getElementById("pulse-strip");
  const counts = new Map();
  for (const item of state.data?.discussions || []) {
    counts.set(item.category, (counts.get(item.category) || 0) + 1);
  }

  strip.innerHTML = (state.data?.categories || []).map((cat) => {
    const count = counts.get(cat.id) || 0;
    const accent = safeColor(cat.accent);
    const id = safeSlug(cat.id);
    return `
      <a class="pulse-pill" href="#cat-${escapeAttr(id)}" style="--cat-color:${accent}">
        ${escapeHtml(cat.label)}<span class="count" style="color:${accent}">${count}</span>
      </a>`;
  }).join("");
}

/* ---------- TL;DR cards (bento grid, first card featured) ---------- */
function renderTldr(animate) {
  const grid = document.getElementById("tldr-grid");
  const items = state.data?.tldr ?? [];

  if (items.length === 0) {
    grid.innerHTML = `
      <div class="tldr-card" style="grid-column: 1 / -1">
        <p style="color:var(--text-dim);text-align:center">
          No briefings yet. The next pipeline run will populate this section.
        </p>
      </div>`;
    return;
  }

  grid.innerHTML = items.map((item, i) => {
    const cat = state.catById.get(item.category) || { label: item.category || "OTHER", accent: "var(--accent)" };
    const bullets = (item.bullets || [])
      .map((b) => `<li>${escapeHtml(b)}</li>`)
      .join("");
    const sourceLabel = SOURCE_LABELS[item.source] || (item.source || "").toUpperCase();
    const metaBits = [];
    if (typeof item.score === "number") metaBits.push(`<span class="glyph">▲</span> ${item.score}`);
    if (typeof item.comments === "number") metaBits.push(`<span class="glyph">◷</span> ${item.comments}`);
    if (item.author) metaBits.push(`by ${escapeHtml(item.author)}`);

    const classes = ["tldr-card"];
    if (i === 0) classes.push("featured");
    if (animate) classes.push("card-in");

    return `
      <article class="${classes.join(" ")}" style="--cat-color:${safeColor(cat.accent)};--i:${i}">
        <div class="tldr-head">
          <span class="tldr-cat">${escapeHtml(cat.label)}</span>
          <span class="tldr-source">${escapeHtml(sourceLabel)} ${escapeHtml(item.subsource || "")}</span>
        </div>
        <h3 class="tldr-title">
          <a href="${escapeAttr(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
        </h3>
        <ul class="tldr-bullets">${bullets}</ul>
        <div class="tldr-meta">
          ${metaBits.map((b) => `<span>${b}</span>`).join("")}
        </div>
      </article>`;
  }).join("");
}

/* ---------- Per-category feed sections ---------- */
function renderFeedSections(animate) {
  const root = document.getElementById("feed-sections");
  const grouped = new Map();
  for (const item of state.data?.discussions || []) {
    if (!grouped.has(item.category)) grouped.set(item.category, []);
    grouped.get(item.category).push(item);
  }

  const html = (state.data?.categories || []).map((cat, i) => {
    const items = grouped.get(cat.id) || [];
    if (items.length === 0) return ""; // omit empty categories
    const rows = items.map((item, idx) => renderRow(item, idx)).join("");
    const accent = safeColor(cat.accent);
    const id = safeSlug(cat.id);
    return `
      <section class="feed-cat${animate ? " card-in" : ""}" id="cat-${escapeAttr(id)}"
               style="--cat-color:${accent};--i:${i}">
        <header class="feed-cat-header">
          <h2 class="feed-cat-name">${escapeHtml(cat.label)}</h2>
          <span class="feed-cat-count">${items.length} items</span>
        </header>
        <ol class="feed-list">${rows}</ol>
      </section>`;
  }).join("");

  root.innerHTML = html || `
    <div class="error-state" style="border-color:var(--line);color:var(--text-dim);background:transparent">
      No items yet — waiting for the first pipeline run.
    </div>`;
}

function renderRow(item, idx) {
  const sourceLabel = SOURCE_LABELS[item.source] || (item.source || "").toUpperCase();
  const sourceClass = `source-${safeSlug(item.source) || "rss"}`;
  const meta = [`<span class="source-tag ${sourceClass}">${escapeHtml(sourceLabel)}</span>`];
  if (item.subsource) meta.push(`<span>${escapeHtml(item.subsource)}</span>`);
  if (item.author) meta.push(`<span>${escapeHtml(item.author)}</span>`);
  if (item.published) {
    const d = new Date(item.published);
    if (!isNaN(d)) {
      meta.push(`<span data-published="${escapeAttr(item.published)}">${escapeHtml(relativeTime(d))}</span>`);
    }
  }

  const side = [];
  if (typeof item.score === "number") {
    side.push(`<span class="side-stat"><span class="glyph">▲</span>${item.score}</span>`);
  }
  if (typeof item.comments === "number") {
    const inner = `<span class="glyph">◷</span>${item.comments}`;
    side.push(item.discuss_url
      ? `<a class="side-stat" href="${escapeAttr(item.discuss_url)}" target="_blank" rel="noopener">${inner}</a>`
      : `<span class="side-stat">${inner}</span>`);
  }

  return `
    <li class="feed-item">
      <span class="feed-rank" aria-hidden="true">${String(idx + 1).padStart(2, "0")}</span>
      <div class="feed-main">
        <a class="feed-title" href="${escapeAttr(item.url)}" target="_blank" rel="noopener">${escapeHtml(item.title)}</a>
        <div class="feed-meta">${meta.join("")}</div>
      </div>
      <div class="feed-side">${side.join("")}</div>
    </li>`;
}

/* ---------- Error state ---------- */
function showError() {
  document.getElementById("tldr-grid").innerHTML = "";
  document.getElementById("feed-sections").innerHTML = "";
  document.getElementById("error-state").classList.remove("hidden");
}

function renderAll(animate) {
  renderUpdated();
  renderPulse();
  renderTldr(animate);
  renderFeedSections(animate);
}

/* ---------- Helpers ---------- */
function escapeHtml(s) {
  if (s == null) return "";
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
function escapeAttr(s) {
  return escapeHtml(s).replace(/`/g, "&#096;");
}

// Whitelist hex colors only — prevents CSS injection if feed.json is tampered.
// Allows #rgb, #rgba, #rrggbb, #rrggbbaa.
const HEX_COLOR_RE = /^#[0-9a-fA-F]{3,8}$/;
function safeColor(c) {
  return (typeof c === "string" && HEX_COLOR_RE.test(c)) ? c : "var(--accent)";
}

// Allow only [a-z0-9_-] in slug positions used in id=, class= and href="#..."
// — belt-and-suspenders on top of escapeAttr.
function safeSlug(s) {
  return typeof s === "string" ? s.replace(/[^a-zA-Z0-9_-]/g, "") : "";
}

/* ---------- Init ---------- */
boot();
