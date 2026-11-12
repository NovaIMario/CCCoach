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
  $("count").textContent = results.length
    ? `${results.length} problems · showing ${start + 1}–${Math.min(start + PAGE, results.length)}`
    : "No problems found.";
  $("prev").disabled = page === 0;
  $("next").disabled = start + PAGE >= results.length;
}

async function search() {
  hideDropdown();
  const params = new URLSearchParams({ limit: 1000, platform: $("platform").value });
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
$("prev").addEventListener("click", () => { page--; render(); scrollTo({ top: 0, behavior: "smooth" }); });
$("next").addEventListener("click", () => { page++; render(); scrollTo({ top: 0, behavior: "smooth" }); });
document.addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches("input, select")) search(); });

search();
