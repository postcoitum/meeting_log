let currentId = null;
let meetingsCache = [];
let recTimerId = null;
let recStartedAt = null;

const BAR_COLORS = ["#5b8ac4", "#3f9e7a", "#c46a8a", "#b08a3f", "#7a6ac4"];

async function api(name, ...args) {
  return await window.pywebview.api[name](...args);
}

function $(id) { return document.getElementById(id); }

function setProgress(text) { $("progress").textContent = text; }

/* ---------- 목록 ---------- */

function groupByDate(meetings) {
  const groups = {};
  for (const m of meetings) {
    const d = m.created_at.slice(0, 10).replace(/-/g, ". ");
    (groups[d] = groups[d] || []).push(m);
  }
  return groups;
}

async function refreshList() {
  meetingsCache = await api("list_meetings");
  renderList();
}

function renderList() {
  const q = $("search").value.trim().toLowerCase();
  const filtered = q
    ? meetingsCache.filter((m) => m.title.toLowerCase().includes(q))
    : meetingsCache;
  const el = $("meeting-list");
  el.innerHTML = "";
  for (const [date, items] of Object.entries(groupByDate(filtered))) {
    const h = document.createElement("div");
    h.className = "date-group";
    h.textContent = date;
    el.appendChild(h);
    for (const m of items) {
      const d = document.createElement("div");
      d.className = "meeting-item" + (m.id === currentId ? " active" : "");
      d.textContent = m.title;
      d.title = m.title;
      d.onclick = () => openMeeting(m.id);
      el.appendChild(d);
    }
  }
}

async function openMeeting(id) {
  currentId = id;
  const m = await api("get_meeting", id);
  if (!m) return;
  $("summary").value = m.summary_md || "";
  $("memo").value = m.memo_md || "";
  $("transcript").textContent = m.transcript || "";
  renderStats(m.stats_json);
  $("chat-log").innerHTML = "";
  renderList();
}

/* ---------- 화자 통계 ---------- */

function renderStats(statsJson) {
  const box = $("stats");
  box.innerHTML = "";
  let stats = null;
  try { stats = JSON.parse(statsJson || ""); } catch (e) { /* 통계 없음 */ }
  const speakers = stats && stats.speakers ? stats.speakers : [];
  if (!speakers.length) { box.classList.remove("show"); return; }

  speakers.forEach((s, i) => {
    const row = document.createElement("div");
    row.className = "stat-row";
    const color = BAR_COLORS[i % BAR_COLORS.length];

    const top = document.createElement("div");
    top.className = "stat-top";
    const name = document.createElement("span");
    name.className = "stat-name";
    name.textContent = s.name;
    name.style.color = color;
    const bar = document.createElement("div");
    bar.className = "stat-bar";
    const fill = document.createElement("div");
    fill.className = "stat-fill";
    fill.style.width = Math.max(2, s.share) + "%";
    fill.style.background = color;
    bar.appendChild(fill);
    const pct = document.createElement("span");
    pct.className = "stat-pct";
    pct.textContent = s.share + "%";
    top.append(name, bar, pct);
    row.appendChild(top);

    if (s.quotes && s.quotes.length) {
      const quote = document.createElement("div");
      quote.className = "stat-quote";
      quote.textContent = "“" + s.quotes[0] + "”";
      quote.title = s.quotes.join("\n");
      row.appendChild(quote);
    }
    box.appendChild(row);
  });
  box.classList.add("show");
}

/* ---------- 자동 저장 ---------- */

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

const saveSummary = debounce(() => {
  if (currentId) api("update_meeting", currentId, { summary_md: $("summary").value });
}, 600);
const saveMemo = debounce(() => {
  if (currentId) api("update_meeting", currentId, { memo_md: $("memo").value });
}, 600);

/* ---------- 녹음 ---------- */

function fmtTime(sec) {
  const m = String(Math.floor(sec / 60)).padStart(2, "0");
  const s = String(sec % 60).padStart(2, "0");
  return m + ":" + s;
}

function startRecUI() {
  $("record").classList.add("recording");
  $("rec-label").textContent = "녹음 중";
  recStartedAt = Date.now();
  recTimerId = setInterval(() => {
    $("rec-time").textContent = fmtTime(Math.floor((Date.now() - recStartedAt) / 1000));
  }, 500);
}

function stopRecUI() {
  $("record").classList.remove("recording");
  $("rec-label").textContent = "녹음";
  $("rec-time").textContent = "";
  clearInterval(recTimerId);
  recTimerId = null;
}

async function toggleRecord() {
  const btn = $("record");
  btn.disabled = true;
  try {
    if (await api("is_recording")) {
      stopRecUI();
      setProgress("녹음 처리 중…");
      const m = await api("stop_recording");
      await refreshList();
      await openMeeting(m.id);
      setProgress("");
    } else {
      await api("start_recording");
      startRecUI();
    }
  } catch (e) {
    stopRecUI();
    setProgress("녹음 실패: " + e);
  } finally {
    btn.disabled = false;
  }
}

/* ---------- 채팅 ---------- */

function appendChat(cls, text) {
  const d = document.createElement("div");
  d.className = "chat-msg " + cls;
  d.textContent = (cls === "q" ? "Q. " : "") + text;
  $("chat-log").appendChild(d);
  $("chat-log").scrollTop = $("chat-log").scrollHeight;
}

async function sendChat() {
  const input = $("chat-input");
  const q = input.value.trim();
  if (!q || !currentId) return;
  input.value = "";
  input.disabled = true;
  appendChat("q", q);
  try {
    const a = await api("chat_meeting", currentId, q);
    appendChat("a", a || "(응답 없음)");
  } catch (e) {
    appendChat("a", "오류: " + e);
  } finally {
    input.disabled = false;
    input.focus();
  }
}

/* ---------- 투명도 ---------- */

function applyOpacity(value) {
  document.documentElement.style.setProperty("--pane-alpha", (value / 100).toFixed(2));
}

/* ---------- 바인딩 ---------- */

function bind() {
  $("summary").addEventListener("input", saveSummary);
  $("memo").addEventListener("input", saveMemo);
  $("search").addEventListener("input", renderList);

  $("toggle-sidebar").onclick = () =>
    $("layout").classList.toggle("sidebar-hidden");
  $("toggle-memo").onclick = () =>
    $("right").classList.toggle("memo-collapsed");

  $("edit-title").onclick = async () => {
    if (!currentId) return;
    const name = prompt("새 제목");
    if (name && name.trim()) {
      await api("update_meeting", currentId, { title: name.trim() });
      await refreshList();
    }
  };

  $("delete-meeting").onclick = async () => {
    if (!currentId) return;
    const m = meetingsCache.find((x) => x.id === currentId);
    if (!confirm(`"${m ? m.title : ""}" 회의를 삭제할까요?`)) return;
    await api("delete_meeting", currentId);
    currentId = null;
    $("summary").value = "";
    $("memo").value = "";
    $("transcript").textContent = "";
    renderStats("");
    $("chat-log").innerHTML = "";
    await refreshList();
  };

  $("regen-summary").onclick = async () => {
    if (!currentId) return;
    setProgress("요약 생성 중…");
    try {
      const summary = await api("summarize_meeting", currentId);
      $("summary").value = summary;
    } catch (e) {
      setProgress("요약 실패: " + e);
      return;
    }
    setProgress("");
  };

  $("export-meeting").onclick = async () => {
    if (!currentId) return;
    const path = await api("export_meeting", currentId);
    if (path) {
      setProgress("저장됨: " + path);
      setTimeout(() => setProgress(""), 3000);
    }
  };

  $("record").onclick = toggleRecord;

  $("chat-send").onclick = sendChat;
  $("chat-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") sendChat();
  });

  const slider = $("opacity");
  const saved = localStorage.getItem("paneAlpha");
  if (saved) slider.value = saved;
  applyOpacity(slider.value);
  slider.addEventListener("input", () => {
    applyOpacity(slider.value);
    localStorage.setItem("paneAlpha", slider.value);
  });

  $("new-meeting").onclick = async () => {
    const path = await api("pick_audio");
    if (!path) return;
    setProgress("처리 중…");
    try {
      const m = await api("add_meeting", path);
      await refreshList();
      await openMeeting(m.id);
    } catch (e) {
      setProgress("실패: " + e);
      return;
    }
    setProgress("");
  };

  window.addEventListener("progress", (e) => setProgress(e.detail));
}

window.addEventListener("pywebviewready", async () => {
  bind();
  await refreshList();
  // 앱 재시작 시 녹음이 이어지고 있으면 UI 복원
  if (await api("is_recording")) startRecUI();
});
