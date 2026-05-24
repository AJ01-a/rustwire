/**
 * TechPulse — client-side renderer.
 * Fetches data/feed.json and renders:
 *   • Pulse strip (per-category counts in the header)
 *   • Top TL;DR cards (one per category, AI-generated bullets)
 *   • Category feed sections (each with top items)
 */

const FEED_URL = "data/feed.json";

const SOURCE_LABELS = {
  reddit: "REDDIT",
  hackernews: "HN",
  lobsters: "LOBSTERS",
  rss: "RSS",
};

const state = {
  data: null,
  catById: new Map(),    // id -> {id, label, accent}
};

/* ---------- Fetch ---------- */
async function loadFeed() {
  try {
    const res = await fetch(`${FEED_URL}?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    state.data = data;
    indexCategories();
    renderAll();
    setStatus("ok");
  } catch (err) {
    console.error("Feed load failed:", err);
    setStatus("error");
    showError();
  }
}

function indexCategories() {
  state.catById.clear();
  for (const c of state.data?.categories || []) {
    state.catById.set(c.id, c);
  }
}

/* ---------- Status / timestamp ---------- */
function setStatus(kind) {
  const dot = document.getElementById("status-dot");
  dot.classList.remove("ok", "error");
  if (kind === "ok") dot.classList.add("ok");
  if (kind === "error") dot.classList.add("error");
  dot.title = kind === "ok" ? "feed loaded" : "feed unavailable";
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

/* ---------- TL;DR cards ---------- */
function renderTldr() {
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

  grid.innerHTML = items.map((item) => {
    const cat = state.catById.get(item.category) || { label: item.category || "OTHER", accent: "var(--accent)" };
    const bullets = (item.bullets || [])
      .map((b) => `<li>${escapeHtml(b)}</li>`)
      .join("");
    const sourceLabel = SOURCE_LABELS[item.source] || (item.source || "").toUpperCase();
    const metaBits = [];
    if (typeof item.score === "number") metaBits.push(`▲ ${item.score}`);
    if (typeof item.comments === "number") metaBits.push(`◷ ${item.comments}`);
    if (item.author) metaBits.push(`by ${escapeHtml(item.author)}`);

    return `
      <article class="tldr-card" style="--cat-color:${safeColor(cat.accent)}">
        <div class="tldr-cat">
          ${escapeHtml(cat.label)}
          <span class="sep">/</span>
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
function renderFeedSections() {
  const root = document.getElementById("feed-sections");
  const grouped = new Map();
  for (const item of state.data?.discussions || []) {
    if (!grouped.has(item.category)) grouped.set(item.category, []);
    grouped.get(item.category).push(item);
  }

  const html = (state.data?.categories || []).map((cat) => {
    const items = grouped.get(cat.id) || [];
    if (items.length === 0) return ""; // omit empty categories
    const rows = items.map((item) => renderRow(item, cat)).join("");
    const accent = safeColor(cat.accent);
    const id = safeSlug(cat.id);
    return `
      <section class="feed-cat" id="cat-${escapeAttr(id)}" style="--cat-color:${accent}">
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

function renderRow(item, cat) {
  const sourceLabel = SOURCE_LABELS[item.source] || (item.source || "").toUpperCase();
  const meta = [`<span class="source-tag">${escapeHtml(sourceLabel)}</span>`];
  if (item.subsource) meta.push(`<span>${escapeHtml(item.subsource)}</span>`);
  if (item.author) meta.push(`<span>${escapeHtml(item.author)}</span>`);
  if (item.published) meta.push(`<span>${escapeHtml(relativeTime(new Date(item.published)))}</span>`);

  const side = [];
  if (typeof item.score === "number") side.push(`▲ ${item.score}`);
  if (typeof item.comments === "number") {
    side.push(item.discuss_url
      ? `<a href="${escapeAttr(item.discuss_url)}" target="_blank" rel="noopener">◷ ${item.comments}</a>`
      : `◷ ${item.comments}`);
  }

  return `
    <li class="feed-item">
      <span class="feed-arrow" aria-hidden="true">→</span>
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

function renderAll() {
  renderUpdated();
  renderPulse();
  renderTldr();
  renderFeedSections();
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

// Allow only [a-z0-9_-] in slug positions used in id= and href="#..." —
// belt-and-suspenders on top of escapeAttr.
function safeSlug(s) {
  return typeof s === "string" ? s.replace(/[^a-zA-Z0-9_-]/g, "") : "";
}

/* ---------- Init ---------- */
loadFeed();
