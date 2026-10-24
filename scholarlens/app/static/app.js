/* ScholarLens — giao diện chat tối giản (vanilla JS) */
const $ = (s, el = document) => el.querySelector(s);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const state = { convId: null, focus: [], streaming: null };

async function api(path, opts = {}) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
  return r.json();
}
function scrollBottom(force) {
  const sc = $("#scroll");
  if (force || sc.scrollHeight - sc.scrollTop - sc.clientHeight < 150) sc.scrollTop = sc.scrollHeight;
}
function renderMarkdown(md) {
  // [1], [2, 3], [1-3] -> chip trích dẫn bấm được (không đụng link markdown [text](url))
  const withCites = (md || "").replace(/\[(\d{1,2}(?:\s*[,–-]\s*\d{1,2})*)\](?!\()/g, (_, g) =>
    g.split(/\s*,\s*/).map((part) => {
      const m = part.match(/^(\d+)\s*[–-]\s*(\d+)$/);
      const ns = m ? Array.from({ length: +m[2] - +m[1] + 1 }, (_, i) => +m[1] + i) : [+part];
      return ns.map((n) => `<sup class="cite" data-n="${n}">${n}</sup>`).join("");
    }).join(""));
  return DOMPurify.sanitize(marked.parse(withCites), { ADD_ATTR: ["data-n"] });
}

// ---------------- lịch sử ----------------
async function loadConversations() {
  const list = await api("/api/conversations");
  $("#convList").innerHTML = list.map((c) => `<li class="${c.id === state.convId ? "active" : ""}" data-id="${c.id}">
      <a href="#" title="${esc(c.title)}">${esc(c.title)}</a><button class="del" title="Xoá">✕</button></li>`).join("")
    || `<li class="none">Chưa có cuộc trò chuyện nào</li>`;
}
function clearThread() {
  $("#thread").innerHTML = `<div class="empty" id="empty">Hỏi về các bài báo trong kho, hoặc đính kèm PDF để thêm bài mới.</div>`;
}
function newChat() {
  if (state.streaming) state.streaming.abort();
  state.convId = null;
  setFocus([]);
  clearThread();
  $("#convTitle").textContent = "Cuộc trò chuyện mới";
  loadConversations();
  $("#input").focus();
}
async function openConversation(id) {
  if (state.streaming) state.streaming.abort();
  const c = await api(`/api/conversations/${id}`);
  state.convId = c.id;
  $("#convTitle").textContent = c.title;
  $("#thread").innerHTML = "";
  for (const m of c.messages) {
    if (m.role === "user") addUser(m.content);
    else {
      const el = addAssistant();
      $(".body", el).innerHTML = renderMarkdown(m.content);
      fillExtras(el, m.sources, m.graph);
    }
  }
  const last = [...c.messages].reverse().find((m) => m.role === "user");
  const ids = (last && last.focus) || [];
  const papers = await Promise.all(ids.map((pid) => api(`/api/papers/${encodeURIComponent(pid)}`).catch(() => null)));
  setFocus(papers.filter(Boolean).map((d) => ({ id: d.paper.paper_id, title: d.paper.title })));
  loadConversations();
  scrollBottom(true);
}

// ---------------- tin nhắn ----------------
function addUser(text) {
  $("#empty")?.remove();
  const el = document.createElement("div");
  el.className = "msg user";
  el.innerHTML = `<div class="bubble">${esc(text)}</div>`;
  $("#thread").append(el);
  scrollBottom(true);
}
function addAssistant() {
  $("#empty")?.remove();
  const el = document.createElement("div");
  el.className = "msg assistant";
  el.innerHTML = `<div class="status" hidden></div><div class="body"></div>`;
  $("#thread").append(el);
  return el;
}
// dưới mỗi câu trả lời: danh sách nguồn (thu gọn) + nút mở đồ thị ngay trong khung chat
function fillExtras(el, sources, graph) {
  if (!sources || !sources.length) return;
  const bar = document.createElement("div");
  bar.className = "extras";
  bar.innerHTML = `<details class="sources"><summary>${sources.length} nguồn</summary><ol>${sources.map((s) => `<li data-n="${s.n}">
      ${esc(s.title)} (${esc(s.year || "n.d.")})${s.url ? ` · <a href="${esc(s.url)}" target="_blank" rel="noopener">arXiv</a>` : ""}
      ${s.has_pdf ? ` · <a href="/api/papers/${encodeURIComponent(s.paper_id)}/pdf" target="_blank">PDF</a>` : ""}</li>`).join("")}</ol></details>
    ${graph && graph.nodes && graph.nodes.length ? `<button type="button" class="graph-btn">◎ Đồ thị (${graph.nodes.length} nút)</button>` : ""}`;
  el.append(bar);
  const btn = $(".graph-btn", bar);
  if (!btn) return;
  btn.onclick = () => {
    let wrap = $(".graph-wrap", bar);
    if (wrap) { wrap.remove(); btn.classList.remove("on"); return; }
    wrap = document.createElement("div");
    wrap.className = "graph-wrap";
    wrap.innerHTML = `<button type="button" class="graph-expand" title="Xem toàn màn hình">⤢ Mở rộng</button>
      <div class="graph-box"></div><div class="graph-legend">${legendHTML()}</div>`;
    bar.append(wrap);
    btn.classList.add("on");
    drawGraph($(".graph-box", wrap), graph);
    $(".graph-expand", wrap).onclick = () => openFullGraph(graph);
    scrollBottom();
  };
}

const COLORS = { focus: "#c96442", paper: "#e9c9b8", author: "#5b7fb8", concept: "#5e8c59", category: "#b9b3a1" };
const TYPE_VI = { paper: "Bài báo", author: "Tác giả", concept: "Khái niệm", category: "Chuyên mục" };
const legendHTML = () => `<span><i style="background:${COLORS.focus}"></i>Bài đang hỏi</span>
  <span><i style="background:${COLORS.paper}"></i>Bài báo</span><span><i style="background:${COLORS.author}"></i>Tác giả</span>
  <span><i style="background:${COLORS.concept}"></i>Khái niệm</span><span>— trích dẫn · - - tương đồng</span>`;

// ---------- xem đồ thị toàn màn hình ----------
let fullNet = null;
function openFullGraph(g) {
  $("#graphFull").hidden = false;
  $("#gfLegend").innerHTML = legendHTML();
  $("#gfInfo").textContent = "Bấm vào một nút để xem chi tiết. Lăn chuột để phóng to, kéo để di chuyển.";
  if (fullNet) fullNet.destroy();
  fullNet = drawGraph($("#gfBox"), g, true);
  const byId = Object.fromEntries(g.nodes.map((n) => [n.id, n]));
  fullNet.on("click", (p) => {
    const n = byId[p.nodes[0]];
    if (!n) return;
    const pid = n.paper_id || "";
    const links = n.type === "paper" && pid ? (pid.startsWith("local:") ? "" :
      `<a href="https://arxiv.org/abs/${esc(pid)}" target="_blank" rel="noopener">arXiv ↗</a>`) +
      `<a href="/api/papers/${encodeURIComponent(pid)}/pdf" target="_blank">PDF ↗</a>` : "";
    const degree = fullNet.getConnectedNodes(n.id).length;
    $("#gfInfo").innerHTML = `${TYPE_VI[n.type] || n.type}: <b>${esc(n.label)}</b>${n.year ? ` (${esc(n.year)})` : ""}
      · ${degree} liên kết${links}`;
  });
}
function closeFullGraph() {
  $("#graphFull").hidden = true;
  if (fullNet) { fullNet.destroy(); fullNet = null; }
}

function drawGraph(box, g, large = false) {
  const text = getComputedStyle(document.documentElement).getPropertyValue("--text").trim() || "#2a2822";
  const max = large ? 60 : 40;
  const short = (s) => (s.length > max ? s.slice(0, max - 2) + "…" : s);
  const k = large ? 1.25 : 1;  // toàn màn hình: nút và chữ to hơn
  const nodes = g.nodes.map((n) => {
    const c = n.focus ? COLORS.focus : COLORS[n.type] || COLORS.category;
    return { id: n.id, label: n.type === "paper" ? short(n.label) : n.label,
      title: `${n.label}${n.year ? " (" + n.year + ")" : ""}`,
      shape: n.type === "paper" ? "dot" : n.type === "author" ? "diamond" : "triangle",
      size: (n.type === "paper" ? (n.focus ? 20 : 13) : 8) * k,
      color: { background: c, border: c }, font: { color: text, size: (n.type === "paper" ? 12 : 10) * k } };
  });
  const edges = g.edges.map((e, i) => ({ id: i, from: e.from, to: e.to, title: e.label, smooth: false,
    arrows: e.label === "CITES" ? "to" : undefined, dashes: e.label === "SIMILAR_TO",
    width: e.label === "CITES" ? 1.6 : 0.8, color: { color: e.label === "CITES" ? COLORS.focus : "#c8c3b6" } }));
  const net = new vis.Network(box, { nodes, edges }, {
    physics: { solver: "forceAtlas2Based", stabilization: { iterations: 160 },
      forceAtlas2Based: { gravitationalConstant: large ? -70 : -45, springLength: large ? 120 : 85 } },
    interaction: { hover: true, tooltipDelay: 120 },
  });
  net.once("stabilizationIterationsDone", () => { net.setOptions({ physics: false }); net.fit({ animation: false }); });
  return net;
}

async function send() {
  const text = $("#input").value.trim();
  if (!text || state.streaming) return;
  $("#input").value = ""; autosize();
  addUser(text);
  const el = addAssistant();
  const body = $(".body", el), status = $(".status", el);
  let answer = "", pending = false;
  const paint = () => { pending = false; body.innerHTML = renderMarkdown(answer); scrollBottom(); };
  const ctrl = new AbortController();
  state.streaming = ctrl;
  $("#sendBtn").classList.add("stop");
  try {
    const resp = await fetch("/api/chat", {
      method: "POST", headers: { "Content-Type": "application/json" }, signal: ctrl.signal,
      body: JSON.stringify({ message: text, conversation_id: state.convId, mode: "auto", focus_ids: state.focus.map((f) => f.id) }),
    });
    const reader = resp.body.getReader(), dec = new TextDecoder();
    let buf = "";
    for (;;) {
      const { value, done } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      let i;
      while ((i = buf.indexOf("\n\n")) >= 0) {
        const line = buf.slice(0, i).replace(/^data: /, "");
        buf = buf.slice(i + 2);
        if (!line.trim()) continue;
        const ev = JSON.parse(line);
        if (ev.type === "meta") {
          const isNew = !state.convId;
          state.convId = ev.conversation_id;
          $("#convTitle").textContent = ev.title;
          if (isNew) loadConversations();
        } else if (ev.type === "status") {
          status.hidden = false; status.textContent = ev.text;
        } else if (ev.type === "sources") {
          fillExtras(el, ev.sources, ev.graph);
        } else if (ev.type === "token") {
          status.hidden = true; answer += ev.text;
          if (!pending) { pending = true; requestAnimationFrame(paint); }
        }
      }
    }
  } catch (e) {
    if (e.name !== "AbortError") answer += `\n\n*(Lỗi kết nối: ${e.message})*`;
  } finally {
    paint(); status.hidden = true;
    state.streaming = null; $("#sendBtn").classList.remove("stop");
    loadConversations();
  }
}

// ---------------- bài đang hỏi (sau khi thêm PDF) ----------------
function setFocus(list) {
  state.focus = list;
  const f = $("#focus");
  f.hidden = !list.length;
  f.innerHTML = list.length ? `<span>Đang hỏi về: ${esc(list.map((x) => x.title).join("; "))}</span><button type="button" title="Bỏ chọn">✕</button>` : "";
}

// ---------------- thêm PDF ----------------
async function uploadFiles(files) {
  files = [...files].filter((f) => f.name.toLowerCase().endsWith(".pdf"));
  if (!files.length) return;
  const el = addAssistant();
  const box = $(".body", el);
  box.className = "body upload";
  const fd = new FormData();
  files.forEach((f) => fd.append("files", f));
  let job = await api("/api/upload", { method: "POST", body: fd });
  const render = () => {
    box.innerHTML = job.items.map((it) => {
      const name = esc(it.title || it.file);
      if (it.state === "added") return `<div class="ok">✓ Đã thêm: ${name}</div>`;
      if (it.state === "duplicate") return `<div class="dup">• Đã có trong kho: ${name} (${esc(it.reason)})</div>`;
      if (it.state === "error") return `<div class="err">✗ Lỗi: ${esc(it.file)} — ${esc(it.reason)}</div>`;
      return `<div>⏳ ${esc(it.file)}${it.current ? ` — ${esc(it.current)}` : " — đang chờ"}</div>`;
    }).join("");
    scrollBottom();
  };
  render();
  while (!job.done) {
    await new Promise((r) => setTimeout(r, 900));
    job = await api(`/api/jobs/${job.id}`);
    render();
  }
  const usable = job.items.filter((i) => (i.state === "added" || i.state === "duplicate") && i.paper_id);
  if (usable.length) {
    setFocus(usable.slice(0, 5).map((i) => ({ id: i.paper_id, title: i.title })));
    box.insertAdjacentHTML("beforeend", `<div class="dup">Bạn có thể đặt câu hỏi về ${usable.length > 1 ? "các bài này" : "bài này"} ngay.</div>`);
  }
  scrollBottom(true);
}

// ---------------- máy chủ LLM ----------------
function showLlm(info) {
  const dot = $("#llmDot"), label = $("#llmLabel"), msg = $("#llmMsg");
  dot.className = "dot"; msg.className = "llm-msg";
  const ok = info.active !== "none" && info.status && info.status.ok;
  if (info.active === "none") {
    label.textContent = "LLM: chưa kết nối"; msg.textContent = "";
  } else if (ok) {
    dot.classList.add("ok"); label.textContent = `LLM: ${info.active_model || "đã kết nối"}`;
    msg.classList.add("ok"); msg.textContent = "Đã kết nối";
  } else {
    dot.classList.add("bad"); label.textContent = "LLM: mất kết nối";
    msg.classList.add("bad"); msg.textContent = info.status?.error || "";
  }
  $("#llmBox").title = info.base_url || "";
  return ok;
}
async function loadLlm(fillForm) {
  try {
    const info = await api("/api/llm");
    if (fillForm) {
      $("#llmForm").base_url.value = info.base_url || "";
      $("#llmForm").api_key.placeholder = info.api_key_set ? "API key (đã lưu, để trống = giữ)" : "API key";
    }
    const ok = showLlm(info);
    if (fillForm && !ok) $("#llmBox").open = true; // chưa kết nối được -> mở sẵn ô nhập
  } catch { /* server đang khởi động */ }
}
async function saveLlm(e) {
  e.preventDefault();
  const f = $("#llmForm");
  $("#llmSave").disabled = true;
  $("#llmMsg").className = "llm-msg"; $("#llmMsg").textContent = "Đang kết nối…";
  try {
    const info = await api("/api/llm", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider: f.base_url.value.trim() ? "openai" : "none", base_url: f.base_url.value, model: "",
        api_key: f.api_key.value ? f.api_key.value : null }),
    });
    f.base_url.value = info.base_url || "";
    f.api_key.value = "";
    f.api_key.placeholder = info.api_key_set ? "API key (đã lưu, để trống = giữ)" : "API key";
    if (showLlm(info)) setTimeout(() => { $("#llmBox").open = false; }, 1200); // kết nối xong -> thu gọn lại
  } catch (err) {
    $("#llmMsg").className = "llm-msg bad"; $("#llmMsg").textContent = err.message;
  } finally { $("#llmSave").disabled = false; }
}

// ---------------- sự kiện ----------------
function autosize() { const t = $("#input"); t.style.height = "auto"; t.style.height = Math.min(t.scrollHeight, 200) + "px"; }

$("#composer").onsubmit = (e) => { e.preventDefault(); state.streaming ? state.streaming.abort() : send(); };
$("#input").addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); } });
$("#input").addEventListener("input", autosize);
$("#newChat").onclick = newChat;
$("#fileInput").onchange = (e) => { uploadFiles(e.target.files); e.target.value = ""; };
$("#focus").onclick = (e) => { if (e.target.tagName === "BUTTON") setFocus([]); };
$("#llmForm").onsubmit = saveLlm;
$("#gfClose").onclick = closeFullGraph;
$("#gfFit").onclick = () => fullNet && fullNet.fit({ animation: true });
document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("#graphFull").hidden) closeFullGraph(); });
// thu gọn / mở rộng thanh bên (màn hình rộng: thu hẳn vào; màn hình hẹp: trượt ra đè lên chat)
const narrow = () => window.matchMedia("(max-width: 760px)").matches;
function setCollapsed(c) {
  $(".app").classList.toggle("collapsed", c);
  try { localStorage.setItem("sl-sidebar-collapsed", c ? "1" : "0"); } catch { /* bỏ qua */ }
}
$("#openSidebar").onclick = () => (narrow() ? $("#sidebar").classList.add("open") : setCollapsed(false));
$("#collapseSidebar").onclick = () => (narrow() ? $("#sidebar").classList.remove("open") : setCollapsed(true));
try { if (localStorage.getItem("sl-sidebar-collapsed") === "1") setCollapsed(true); } catch { /* bỏ qua */ }
$("#convList").onclick = async (e) => {
  const li = e.target.closest("li[data-id]"); if (!li) return;
  e.preventDefault();
  if (e.target.classList.contains("del")) {
    await api(`/api/conversations/${li.dataset.id}`, { method: "DELETE" });
    li.dataset.id === state.convId ? newChat() : loadConversations();
  } else openConversation(li.dataset.id);
  $("#sidebar").classList.remove("open");
};
// bấm [n] -> mở danh sách nguồn của câu trả lời đó và tô sáng nguồn n
document.addEventListener("click", (e) => {
  const c = e.target.closest(".cite"); if (!c) return;
  const det = c.closest(".msg")?.querySelector(".sources"); if (!det) return;
  det.open = true;
  det.querySelectorAll("li").forEach((li) => li.classList.toggle("hl", li.dataset.n === c.dataset.n));
});
// kéo-thả PDF vào cửa sổ
let depth = 0;
window.addEventListener("dragenter", (e) => { if ([...e.dataTransfer.types].includes("Files")) { depth++; $("#dropOverlay").classList.add("show"); } });
window.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; $("#dropOverlay").classList.remove("show"); } });
window.addEventListener("dragover", (e) => e.preventDefault());
window.addEventListener("drop", (e) => { e.preventDefault(); depth = 0; $("#dropOverlay").classList.remove("show"); uploadFiles(e.dataTransfer.files); });

marked.setOptions({ gfm: true });
loadConversations();
loadLlm(true);
setInterval(() => loadLlm(false), 60000);
const hash = new URLSearchParams(location.hash.slice(1));
// #c=<id> mở thẳng một hội thoại; thêm &graph=1 để mở luôn đồ thị của câu trả lời cuối
if (hash.get("c")) openConversation(hash.get("c")).then(() => {
  if (hash.get("graph")) [...document.querySelectorAll(".graph-btn")].pop()?.click();
  if (hash.get("graph") === "full") [...document.querySelectorAll(".graph-expand")].pop()?.click();
});
