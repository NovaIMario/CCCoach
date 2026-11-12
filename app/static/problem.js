// Problem page: VS Code-style panels, statement maths, Monaco editor, run code, AI coach chat.

const $ = id => document.getElementById(id);
const store = {
  get(key, fallback) { try { const v = localStorage.getItem(key); return v === null ? fallback : JSON.parse(v); } catch { return fallback; } },
  set(key, value) { try { localStorage.setItem(key, JSON.stringify(value)); } catch {} },
};
const problemId = PROBLEM.slug ? `lc:${PROBLEM.slug}` : `${PROBLEM.contest_id}${PROBLEM.index}`;

// ---------- Panels: resize by dragging the gutters, collapse by clicking a title bar ----------

const panels = [...document.querySelectorAll(".ide-panel")];
const LAYOUT_KEY = "cccoach:layout";   // shared by all problems, like an editor's window layout
const MIN_PX = 220;
const defaults = () => ({ grow: Object.fromEntries(panels.map(p => [p.id, +p.dataset.grow])), collapsed: {} });
let layout = { ...defaults(), ...store.get(LAYOUT_KEY, {}) };

function applyLayout() {
  for (const p of panels) {
    p.classList.toggle("collapsed", !!layout.collapsed[p.id]);
    p.style.flex = layout.collapsed[p.id] ? "" : `${layout.grow[p.id] || 1} 1 0`;
    p.querySelector(".ide-head").setAttribute("aria-expanded", String(!layout.collapsed[p.id]));
  }
  document.querySelectorAll(".gutter").forEach(g => {
    const [a, b] = g.dataset.between.split(" ");
    g.classList.toggle("disabled", !!(layout.collapsed[a] || layout.collapsed[b]));
  });
  store.set(LAYOUT_KEY, layout);
}

panels.forEach(p => p.querySelector(".ide-head").addEventListener("click", e => {
  if (e.target.closest(".ide-actions")) return;             // clicks on Run / language / Clear
  const open = panels.filter(q => !layout.collapsed[q.id]);
  if (!layout.collapsed[p.id] && open.length === 1) return; // keep at least one panel open
  layout.collapsed[p.id] = !layout.collapsed[p.id];
  applyLayout();
}));

document.querySelectorAll(".gutter").forEach(g => {
  const [leftId, rightId] = g.dataset.between.split(" ");
  g.addEventListener("pointerdown", e => {
    if (g.classList.contains("disabled")) return;
    e.preventDefault();
    const left = $(leftId), right = $(rightId);
    const startX = e.clientX, lw = left.offsetWidth, rw = right.offsetWidth;
    const growSum = layout.grow[leftId] + layout.grow[rightId];
    g.setPointerCapture(e.pointerId);
    g.classList.add("dragging");
    document.body.classList.add("resizing");
    const move = ev => {
      const newLeft = Math.min(Math.max(lw + ev.clientX - startX, MIN_PX), lw + rw - MIN_PX);
      layout.grow[leftId] = growSum * newLeft / (lw + rw);
      layout.grow[rightId] = growSum - layout.grow[leftId];
      left.style.flex = `${layout.grow[leftId]} 1 0`;
      right.style.flex = `${layout.grow[rightId]} 1 0`;
    };
    const up = () => {
      g.removeEventListener("pointermove", move);
      g.classList.remove("dragging");
      document.body.classList.remove("resizing");
      applyLayout();
    };
    g.addEventListener("pointermove", move);
    g.addEventListener("pointerup", up, { once: true });
  });
  g.addEventListener("dblclick", () => { layout.grow = defaults().grow; applyLayout(); }); // reset sizes
});

applyLayout();

// ---------- Statement maths ----------

// Codeforces writes maths as $$$x$$$; MathJax wants \(x\). Work on textContent so nothing is parsed as HTML.
const st = $("statement-text");
if (st) {
  st.textContent = st.textContent.replace(/\$\$\$(.+?)\$\$\$/gs, "\\($1\\)");
  const typesetStatement = () => window.MathJax?.typesetPromise ? MathJax.typesetPromise([st]) : setTimeout(typesetStatement, 200);
  typesetStatement();
}

// ---------- Editor + runner ----------

const TEMPLATES = {
  cpp: "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n",
  python: "import sys\ninput = sys.stdin.readline\n\n\ndef main():\n    pass\n\n\nmain()\n",
};
const codeKey = lang => `cccoach:${problemId}:${lang}`;
const loadCode = lang => { try { return localStorage.getItem(codeKey(lang)); } catch { return null; } };
const saveCode = (lang, code) => { try { localStorage.setItem(codeKey(lang), code); } catch {} };

let editor;
require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs" } });
require(["vs/editor/editor.main"], () => {
  const lang = $("lang").value;
  editor = monaco.editor.create($("editor"), {
    value: loadCode(lang) || TEMPLATES[lang],
    language: lang === "cpp" ? "cpp" : "python",
    theme: matchMedia("(prefers-color-scheme: dark)").matches ? "vs-dark" : "vs",
    automaticLayout: true, minimap: { enabled: false }, fontSize: 14, scrollBeyondLastLine: false,
  });
  editor.onDidChangeModelContent(() => saveCode($("lang").value, editor.getValue()));
  editor.addCommand(monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter, () => $("run").click()); // Ctrl+Enter runs
});

$("lang").addEventListener("change", () => {
  const lang = $("lang").value;
  monaco.editor.setModelLanguage(editor.getModel(), lang === "cpp" ? "cpp" : "python");
  editor.setValue(loadCode(lang) || TEMPLATES[lang]);
});

$("run").addEventListener("click", async () => {
  if (layout.collapsed["panel-editor"]) { layout.collapsed["panel-editor"] = false; applyLayout(); }
  $("run").disabled = true;
  $("status").textContent = "Running...";
  $("stdout").textContent = "";
  try {
    const res = await fetch("/api/run", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ language: $("lang").value, code: editor.getValue(), stdin: $("stdin").value }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
    $("status").textContent = data.status.replace("_", " ");
    $("stdout").textContent = data.stdout + (data.stderr ? `\n${data.stderr}` : "");
  } catch (e) {
    $("status").textContent = "error";
    $("stdout").textContent = e.message;
  } finally {
    $("run").disabled = false;
  }
});

// ---------- AI coach chat ----------

// Tiny Markdown renderer for the coach's replies. Everything is HTML-escaped FIRST, so the
// model's output can never inject markup; only our own tags are added afterwards.
const esc = s => s.replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
function inline(s) {
  // `code` spans are left alone; elsewhere $..$ / $$..$$ maths becomes MathJax \(..\) / \[..\], **x** bold.
  return s.split(/(`[^`]+`)/).map((part, i) => i % 2
    ? `<code>${part.slice(1, -1)}</code>`
    : part.replace(/\$\$([^$]+)\$\$/g, "\\[$1\\]")
          .replace(/\$([^$\n]+?)\$/g, "\\($1\\)")
          .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")).join("");
}
const typeset = el => window.MathJax?.typesetPromise ? MathJax.typesetPromise([el]).catch(() => {}) : setTimeout(() => typeset(el), 300);
function markdown(text) {
  return esc(text).split(/```[\w+-]*\n?/).map((chunk, i) => {
    if (i % 2) return `<pre><code>${chunk.replace(/\n$/, "")}</code></pre>`;   // inside a ``` fence
    return chunk.split(/\n{2,}/).map(block => {
      const lines = block.split("\n").filter(l => l.trim());
      if (!lines.length) return "";
      if (lines.every(l => /^\s*[-*] /.test(l))) return `<ul>${lines.map(l => `<li>${inline(l.replace(/^\s*[-*] /, ""))}</li>`).join("")}</ul>`;
      if (lines.every(l => /^\s*\d+[.)] /.test(l))) return `<ol>${lines.map(l => `<li>${inline(l.replace(/^\s*\d+[.)] /, ""))}</li>`).join("")}</ol>`;
      return `<p>${lines.map(l => inline(l.replace(/^#{1,6}\s+(.*)$/, "**$1**"))).join("<br>")}</p>`;
    }).join("");
  }).join("");
}

const log = $("chat-log");
if (log) {
  const CHAT_KEY = `cccoach:${problemId}:chat`;
  const QUICK = { hint: "Give me a hint", review: "Review my code", solution: "Show me the full solution" };
  let history = store.get(CHAT_KEY, []);
  let busy = false;
  const welcome = log.querySelector(".chat-welcome");

  const bubble = (role, text, extra = "") => {
    const div = document.createElement("div");
    div.className = `msg ${role} ${extra}`.trim();
    if (role === "coach" && !extra) { div.innerHTML = markdown(text); typeset(div); } else div.textContent = text;
    log.append(div);
    log.scrollTop = log.scrollHeight;
    return div;
  };
  const render = () => {
    log.replaceChildren(welcome);
    welcome.hidden = history.length > 0;
    history.forEach(t => bubble(t.role, t.text));
  };

  async function send(mode, message) {
    if (busy) return;
    if (mode === "solution" && !confirm("Show the full solution?")) return;
    if (layout.collapsed["panel-ai"]) { layout.collapsed["panel-ai"] = false; applyLayout(); }
    busy = true;
    document.querySelectorAll("#chat-form button").forEach(b => b.disabled = true);
    const earlier = history.slice(-10);
    const userText = mode === "chat" ? message : QUICK[mode];
    history.push({ role: "user", text: userText });
    welcome.hidden = true;
    bubble("user", userText);
    const thinking = bubble("coach", "Thinking...", "thinking");
    try {
      const res = await fetch("/api/hint", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...PROBLEM, mode, message: mode === "chat" ? message : "",
                               code: editor ? editor.getValue() : "", history: earlier }),
      });
      const data = await res.json().catch(() => ({}));
      const detail = Array.isArray(data.detail) ? "That message is too long." : data.detail;
      if (!res.ok) throw new Error(data.response || detail || `HTTP ${res.status}`);
      thinking.remove();
      history.push({ role: "coach", text: data.response });
      bubble("coach", data.response);
    } catch (e) {
      thinking.remove();
      bubble("coach", e.message, "error");   // shown, but not saved or sent back as context
    } finally {
      history = history.slice(-40);
      store.set(CHAT_KEY, history);
      busy = false;
      document.querySelectorAll("#chat-form button").forEach(b => b.disabled = false);
    }
  }

  document.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => send(b.dataset.mode)));
  const input = $("chat-input");
  $("chat-form").addEventListener("submit", e => {
    e.preventDefault();
    const text = input.value.trim();
    if (!text || busy) return;
    input.value = "";
    send("chat", text);
  });
  input.addEventListener("keydown", e => {
    if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("chat-form").requestSubmit(); }
  });
  $("chat-clear").addEventListener("click", () => {
    if (history.length && !confirm("Clear this conversation?")) return;
    history = [];
    store.set(CHAT_KEY, history);
    render();
  });
  render();
}
