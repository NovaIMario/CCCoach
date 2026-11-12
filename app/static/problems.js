// Problem search page: Trie autocomplete on names + filtered search through /api/problems.

// One Trie per platform, built lazily the first time that platform is searched.
const tries = {};
function trieFor(platform) {
  if (!tries[platform]) {
    const t0 = performance.now();
    tries[platform] = new Trie();
    NAMES[platform].forEach(n => tries[platform].insert(n));
    console.log(`Trie built over ${NAMES[platform].length} ${platform} names in ${(performance.now() - t0).toFixed(0)}ms`);
  }
  return tries[platform];
}

const PAGE = 24;
const LIMIT = 1000;  // the API caps a search at this many results
let results = [];
let page = 0;

const $ = id => document.getElementById(id);

function ratingClass(r) {
  if (!r) return "r-none";
  if (r < 1200) return "r-gray";
  if (r < 1400) return "r-green";
  if (r < 1600) return "r-cyan";
  if (r < 1900) return "r-blue";
  if (r < 2100) return "r-purple";
  if (r < 2400) return "r-orange";
  return "r-red";
}

function el(tag, cls, text) {
  const e = document.createElement(tag);
  if (cls) e.className = cls;
  if (text !== undefined) e.textContent = text;  // textContent, never innerHTML: names come from outside
  return e;
}

function card(p) {
  const lc = p.platform === "lc";
  const a = el("a", "problem-card");
  a.href = lc ? `/lc/${encodeURIComponent(p.slug)}` : `/problem/${p.contest_id}/${encodeURIComponent(p.index)}`;
  const top = el("div", "card-top");
  top.append(el("span", "problem-name", p.name));
  const r = p.rating ?? p.predicted_rating;
  const rating = el("span", `rating ${ratingClass(r)}`, r ? (p.rating ? r : `~${r}`) : "?");
  if (!p.rating && r) rating.title = lc ? `Estimated from difficulty (${p.difficulty})` : "Predicted by the rating model";
  if (lc && p.rating) rating.title = `LeetCode rating ${p.lc_rating}, converted to the Codeforces scale`;
  top.append(rating);
  const tags = el("div", "card-tags");
  p.tags.forEach(t => tags.append(el("span", "tag", t)));
  a.append(top, tags, el("div", "card-id muted small", lc ? `LeetCode ${p.frontend_id} · ${p.difficulty}` : `${p.contest_id}${p.index}`));
  return a;
}

function render() {
  const start = page * PAGE;
  $("results").replaceChildren(...results.slice(start, start + PAGE).map(card));
  const total = results.length >= LIMIT ? `${LIMIT}+ problems (narrow the search to see more)` : `${results.length} problems`;
  $("count").textContent = results.length
    ? `${total} · showing ${start + 1}–${Math.min(start + PAGE, results.length)}`
    : "No problems found.";
  const pages = Math.ceil(results.length / PAGE);
  $("prev").disabled = page === 0;
  $("next").disabled = page >= pages - 1;
  document.querySelector(".pager").hidden = pages <= 1;
  $("pages").replaceChildren(...pageList(page, pages).map(n => {
    if (n === null) return el("span", "pg-gap", "…");
    const b = el("button", n === page ? "pg on" : "pg", String(n + 1));
    if (n === page) b.setAttribute("aria-current", "page");
    b.addEventListener("click", () => goTo(n));
    return b;
  }));
}

// Page numbers to show (0-based), with null for a "…" gap: always the first and last page plus a
// window around the current one, e.g. 1 … 4 5 [6] 7 8 … 42. A gap that would hide a single page
// shows that page instead, so "…" always stands for at least two pages.
function pageList(current, total) {
  const span = matchMedia("(max-width: 600px)").matches ? 1 : 2;
  const keep = new Set([0, total - 1]);
  for (let i = current - span; i <= current + span; i++) if (i >= 0 && i < total) keep.add(i);
  const sorted = [...keep].sort((a, b) => a - b), out = [];
  sorted.forEach((n, i) => {
    const prev = sorted[i - 1];
    if (i && n - prev === 2) out.push(n - 1);
    else if (i && n - prev > 2) out.push(null);
    out.push(n);
  });
  return out;
}

function goTo(n) {
  page = n;
  render();
  scrollTo({ top: 0, behavior: "smooth" });
}

async function search() {
  hideDropdown();
  const params = new URLSearchParams({ limit: LIMIT, platform: $("platform").value });
  if ($("name").value) params.set("name", $("name").value);
  if ($("tag").value) params.set("tag", $("tag").value);
  if ($("min").value) params.set("min_rating", $("min").value);
  if ($("max").value) params.set("max_rating", $("max").value);
  $("count").textContent = "Searching...";
  try {
    const res = await fetch(`/api/problems?${params}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    results = await res.json();
    page = 0;
    render();
  } catch (e) {
    $("count").textContent = `Search failed: ${e.message}`;
  }
}

function hideDropdown() {
  $("name-dropdown").replaceChildren();
  $("name-dropdown").style.display = "none";
}

$("name").addEventListener("input", () => {
  const q = $("name").value.trim();
  if (!q) return hideDropdown();
  const matches = trieFor($("platform").value).searchPrefix(q, 12);
  if (!matches.length) return hideDropdown();
  $("name-dropdown").replaceChildren(...matches.map(m => {
    const d = el("div", "dropdown-item", m);
    d.addEventListener("mousedown", () => { $("name").value = m; search(); });
    return d;
  }));
  $("name-dropdown").style.display = "block";
});

$("name").addEventListener("blur", () => setTimeout(hideDropdown, 100));
$("go").addEventListener("click", search);
$("platform").addEventListener("change", search);
$("prev").addEventListener("click", () => goTo(page - 1));
$("next").addEventListener("click", () => goTo(page + 1));
document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches("input, select")) search(); });

search();
