let currentId = null;
let meetingsCache = [];
let recTimerId = null;
let recStartedAt = null;

const BAR_COLORS = ["#5b8ac4", "#3f9e7a", "#c46a8a", "#b08a3f", "#7a6ac4"];

async function api(name, ...args) {
  return await window.pywebview.api[name](...args);
}

function $(id) { return document.getElementById(id); }

let progressStage = "";
let progressStart = null;
let progressTicker = null;

function renderProgress() {
  const sec = Math.floor((Date.now() - progressStart) / 1000);
  const mm = String(Math.floor(sec / 60)).padStart(2, "0");
  const ss = String(sec % 60).padStart(2, "0");
  $("progress").textContent = `${progressStage} · 경과 ${mm}:${ss}`;
}

function setProgress(text) {
  if (!text) {
    progressStage = "";
    progressStart = null;
    clearInterval(progressTicker);
    progressTicker = null;
    $("progress").textContent = "";
    return;
  }
  progressStage = text;
  if (!progressStart) {
    progressStart = Date.now();
    progressTicker = setInterval(renderProgress, 1000);
  }
  renderProgress();
}

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

const STATUS_LABEL = { queued: "대기중", processing: "처리중…", error: "실패" };

function sortMeetings(list, mode) {
  const arr = [...list];
  if (mode === "date_asc") {
    arr.sort((a, b) => a.created_at.localeCompare(b.created_at) || a.id - b.id);
  } else if (mode === "title_asc") {
    arr.sort((a, b) => a.title.localeCompare(b.title, "ko"));
  } else if (mode === "duration_desc") {
    arr.sort((a, b) => (b.duration_sec || 0) - (a.duration_sec || 0));
  } else {
    arr.sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);
  }
  return arr;
}

function renderItem(el, m) {
  const d = document.createElement("div");
  const statusCls = m.status && m.status !== "done" ? " " + m.status : "";
  d.className = "meeting-item" + (m.id === currentId ? " active" : "") + statusCls;
  const title = document.createElement("span");
  title.className = "meeting-item-title";
  title.textContent = m.title;
  d.appendChild(title);
  const meta = document.createElement("span");
  meta.className = "meeting-item-meta";
  if (m.status === "queued" || m.status === "error") {
    meta.textContent = STATUS_LABEL[m.status];
  } else if (m.status === "processing") {
    meta.textContent = m._stage || STATUS_LABEL.processing;
  } else if (m.duration_sec) {
    meta.textContent = fmtTime(Math.round(m.duration_sec));
  }
  d.appendChild(meta);
  d.title = m.title;
  d.onclick = () => openMeeting(m.id);
  el.appendChild(d);
}

function renderList() {
  const q = $("search").value.trim().toLowerCase();
  const sortMode = $("sort-select") ? $("sort-select").value : "date_desc";
  let filtered = q
    ? meetingsCache.filter((m) => m.title.toLowerCase().includes(q))
    : meetingsCache;
  filtered = sortMeetings(filtered, sortMode);
  const el = $("meeting-list");
  el.innerHTML = "";
  const useGroups = sortMode === "date_desc" || sortMode === "date_asc";
  if (useGroups) {
    for (const [date, items] of Object.entries(groupByDate(filtered))) {
      const h = document.createElement("div");
      h.className = "date-group";
      h.textContent = date;
      el.appendChild(h);
      for (const m of items) renderItem(el, m);
    }
  } else {
    for (const m of filtered) renderItem(el, m);
  }
}

function setSummaryView(md) {
  $("summary").value = md;
  $("summary-view").innerHTML = renderSummaryMarkdown(md);
}

function setSummaryEditMode(on) {
  $("summary").classList.toggle("hidden", !on);
  $("summary-view").classList.toggle("hidden", on);
  if (on) $("summary").focus();
}

async function openMeeting(id) {
  currentId = id;
  const m = await api("get_meeting", id);
  if (!m) return;
  setSummaryEditMode(false);
  if (m.status === "queued" || m.status === "processing") {
    setSummaryView("");
    $("summary-view").innerHTML = `<p>처리 중입니다… 목록에서 진행 상황을 확인하세요.</p>`;
  } else if (m.status === "error") {
    setSummaryView("");
    $("summary-view").innerHTML = `<p>처리 중 오류가 발생했습니다.</p>`;
  } else {
    setSummaryView(m.summary_md || "");
  }
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
      // stop_recording도 add_meeting과 동일하게 큐에 넣고 바로 리턴한다.
      const m = await api("stop_recording");
      await refreshList();
      await openMeeting(m.id);
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
  $("summary").addEventListener("input", () => {
    saveSummary();
    $("summary-view").innerHTML = renderSummaryMarkdown($("summary").value);
  });
  $("memo").addEventListener("input", saveMemo);
  $("search").addEventListener("input", renderList);
  $("sort-select").addEventListener("change", renderList);

  $("toggle-summary-edit").onclick = () => {
    setSummaryEditMode($("summary").classList.contains("hidden"));
  };

  $("summary-view").addEventListener("click", (e) => {
    const li = e.target.closest(".sum-check-item");
    if (!li || !currentId) return;
    const raw = li.dataset.raw;
    const checked = li.classList.contains("checked");
    const newRaw = checked
      ? raw.replace(/\[[xX]\]/, "[ ]")
      : raw.replace(/\[\s\]/, "[x]");
    const full = $("summary").value;
    const idx = full.indexOf(raw);
    if (idx === -1) return;
    const updated = full.slice(0, idx) + newRaw + full.slice(idx + raw.length);
    setSummaryView(updated);
    saveSummary();
  });

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
    setSummaryEditMode(false);
    setSummaryView("");
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
      setSummaryView(summary);
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

  $("copy-notion").onclick = async () => {
    if (!currentId) return;
    const ok = await api("copy_for_notion", currentId);
    if (ok) {
      setProgress("복사됨 — 노션에 붙여넣기(⌘V)만 하면 됩니다");
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
    // add_meeting은 큐에 넣고 바로 리턴한다 — 처리를 기다리지 않으므로
    // 이 버튼을 다시 눌러 다른 파일을 곧바로 또 추가할 수 있다.
    try {
      const m = await api("add_meeting", path);
      await refreshList();
      await openMeeting(m.id);
    } catch (e) {
      setProgress("실패: " + e);
    }
  };

  // 설정 모달 (HF 토큰 + 요약 양식)
  $("settings").onclick = async () => {
    $("hf-token").value = await api("get_hf_token");
    $("num-speakers").value = await api("get_num_speakers");
    $("tpl-text").value = await api("get_summary_template");
    $("tpl-modal").classList.remove("hidden");
  };
  $("tpl-close").onclick = () => $("tpl-modal").classList.add("hidden");
  $("tpl-modal").addEventListener("click", (e) => {
    if (e.target === $("tpl-modal")) $("tpl-modal").classList.add("hidden");
  });
  $("tpl-reset").onclick = async () => {
    $("tpl-text").value = await api("default_summary_template");
  };
  $("tpl-save").onclick = async () => {
    await api("set_hf_token", $("hf-token").value);
    await api("set_num_speakers", $("num-speakers").value);
    await api("set_summary_template", $("tpl-text").value);
    $("tpl-modal").classList.add("hidden");
    setProgress("설정 저장됨");
    setTimeout(() => setProgress(""), 3000);
  };

  window.addEventListener("job-progress", async (e) => {
    const detail = e.detail;
    if (!detail) return;
    if (detail.status === "done" || detail.status === "error") {
      await refreshList();
      if (currentId === detail.id) await openMeeting(detail.id);
    } else {
      const m = meetingsCache.find((x) => x.id === detail.id);
      if (m) { m.status = detail.status; m._stage = detail.stage; }
      renderList();
    }
  });
}

window.addEventListener("pywebviewready", async () => {
  bind();
  await refreshList();
  // 앱 재시작 시 녹음이 이어지고 있으면 UI 복원
  if (await api("is_recording")) startRecUI();
});
