// Problem page: statement maths, Monaco editor, run code, AI coach.

const $ = id => document.getElementById(id);

// Codeforces writes maths as $$$x$$$; MathJax wants \(x\). Work on textContent so nothing is parsed as HTML.
const st = $("statement-text");
if (st) {
  st.textContent = st.textContent.replace(/\$\$\$(.+?)\$\$\$/gs, "\\($1\\)");
  const typeset = () => window.MathJax?.typesetPromise ? MathJax.typesetPromise([st]) : setTimeout(typeset, 200);
  typeset();
}

const TEMPLATES = {
  cpp: "#include <bits/stdc++.h>\nusing namespace std;\n\nint main() {\n    ios::sync_with_stdio(false);\n    cin.tie(nullptr);\n\n    return 0;\n}\n",
  python: "import sys\ninput = sys.stdin.readline\n\n\ndef main():\n    pass\n\n\nmain()\n",
};
const storageKey = lang => `cpcoach:${PROBLEM.contest_id}${PROBLEM.index}:${lang}`;
const load = lang => { try { return localStorage.getItem(storageKey(lang)); } catch { return null; } };
const save = (lang, code) => { try { localStorage.setItem(storageKey(lang), code); } catch {} };

let editor;
require.config({ paths: { vs: "https://cdnjs.cloudflare.com/ajax/libs/monaco-editor/0.45.0/min/vs" } });
require(["vs/editor/editor.main"], () => {
  const lang = $("lang").value;
  editor = monaco.editor.create($("editor"), {
    value: load(lang) || TEMPLATES[lang],
    language: lang === "cpp" ? "cpp" : "python",
    theme: matchMedia("(prefers-color-scheme: dark)").matches ? "vs-dark" : "vs",
    automaticLayout: true, minimap: { enabled: false }, fontSize: 14,
  });
  editor.onDidChangeModelContent(() => save($("lang").value, editor.getValue()));
});

$("lang").addEventListener("change", () => {
  const lang = $("lang").value;
  monaco.editor.setModelLanguage(editor.getModel(), lang === "cpp" ? "cpp" : "python");
  editor.setValue(load(lang) || TEMPLATES[lang]);
});

$("run").addEventListener("click", async () => {
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

document.querySelectorAll("[data-mode]").forEach(btn => btn.addEventListener("click", async () => {
  const mode = btn.dataset.mode;
  if (mode === "solution" && !confirm("Show the full solution?")) return;
  const out = $("ai-out");
  out.textContent = "Thinking...";
  try {
    const res = await fetch("/api/hint", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mode, contest_id: PROBLEM.contest_id, index: PROBLEM.index, code: editor ? editor.getValue() : "" }),
    });
    const data = await res.json();
    out.textContent = data.response || data.detail || "No response";
  } catch (e) {
    out.textContent = `Error: ${e.message}`;
  }
}));
