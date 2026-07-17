/* 회의 요약 전용 경량 마크다운 렌더러 (외부 라이브러리 없음 — 로컬 전용 앱 원칙).
   summarizer.py의 DEFAULT_TEMPLATE 형식(## 헤딩, - [ ] 체크박스, - 리스트, **볼드**)만 지원한다. */

function mdEscapeHtml(s) {
  return s
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;");
}

function mdRenderInline(text) {
  return mdEscapeHtml(text).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
}

function renderSummaryMarkdown(md) {
  const lines = (md || "").split("\n");
  let html = "";
  let inList = false;
  const closeList = () => {
    if (inList) { html += "</ul>"; inList = false; }
  };

  for (const raw of lines) {
    const line = raw.trimEnd();
    const heading = line.match(/^##\s+(.*)/);
    if (heading) {
      closeList();
      html += `<h3 class="sum-heading">${mdRenderInline(heading[1])}</h3>`;
      continue;
    }
    const checkbox = line.match(/^-\s+\[([ xX])\]\s*(.*)/);
    if (checkbox) {
      if (!inList) { html += `<ul class="sum-list sum-checklist">`; inList = true; }
      const checked = checkbox[1].toLowerCase() === "x";
      html +=
        `<li class="sum-check-item${checked ? " checked" : ""}" data-raw="${mdEscapeHtml(raw)}">` +
        `<input type="checkbox" ${checked ? "checked" : ""} disabled>` +
        `<span>${mdRenderInline(checkbox[2])}</span></li>`;
      continue;
    }
    const bullet = line.match(/^-\s+(.*)/);
    if (bullet) {
      if (!inList) { html += `<ul class="sum-list">`; inList = true; }
      html += `<li>${mdRenderInline(bullet[1])}</li>`;
      continue;
    }
    closeList();
    if (line.trim() === "") continue;
    html += `<p>${mdRenderInline(line)}</p>`;
  }
  closeList();
  return html;
}
