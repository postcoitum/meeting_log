let currentId = null;

async function api(name, ...args) {
  return await window.pywebview.api[name](...args);
}

function groupByDate(meetings) {
  const groups = {};
  for (const m of meetings) {
    const d = m.created_at.slice(0, 10).replace(/-/g, ". ");
    (groups[d] = groups[d] || []).push(m);
  }
  return groups;
}

async function renderList() {
  const list = await api("list_meetings");
  const el = document.getElementById("meeting-list");
  el.innerHTML = "";
  const groups = groupByDate(list);
  for (const [date, items] of Object.entries(groups)) {
    const h = document.createElement("div");
    h.className = "date-group";
    h.textContent = date;
    el.appendChild(h);
    for (const m of items) {
      const d = document.createElement("div");
      d.className = "meeting-item" + (m.id === currentId ? " active" : "");
      d.textContent = m.title;
      d.onclick = () => openMeeting(m.id);
      el.appendChild(d);
    }
  }
}

async function openMeeting(id) {
  currentId = id;
  const m = await api("get_meeting", id);
  document.getElementById("summary").value = m.summary_md || "";
  document.getElementById("memo").value = m.memo_md || "";
  document.getElementById("transcript").textContent = m.transcript || "";
  renderList();
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

const saveSummary = debounce(() => {
  if (currentId) api("update_meeting", currentId, { summary_md: document.getElementById("summary").value });
}, 600);
const saveMemo = debounce(() => {
  if (currentId) api("update_meeting", currentId, { memo_md: document.getElementById("memo").value });
}, 600);

function bind() {
  document.getElementById("summary").addEventListener("input", saveSummary);
  document.getElementById("memo").addEventListener("input", saveMemo);

  document.getElementById("toggle-sidebar").onclick = () =>
    document.querySelector(".layout").classList.toggle("sidebar-hidden");
  document.getElementById("toggle-memo").onclick = () =>
    document.querySelector(".right").classList.toggle("memo-collapsed");

  document.getElementById("edit-title").onclick = async () => {
    if (!currentId) return;
    const name = prompt("새 제목");
    if (name) { await api("update_meeting", currentId, { title: name }); renderList(); }
  };

  document.getElementById("new-meeting").onclick = async () => {
    const path = await window.pywebview.api.pick_audio();
    if (!path) return;
    setProgress("처리 중…");
    try {
      const m = await api("add_meeting", path);
      currentId = m.id;
      await renderList();
      await openMeeting(m.id);
    } catch (e) {
      setProgress("실패: " + e);
      return;
    }
    setProgress("");
  };
}

function setProgress(text) {
  document.getElementById("progress").textContent = text;
}

window.addEventListener("pywebviewready", () => { bind(); renderList(); });
