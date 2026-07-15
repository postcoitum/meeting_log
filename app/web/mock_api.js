/* 브라우저 개발 하니스: index.html?mock=1 로 열 때만 로드되는 가짜 pywebview API.
   실제 앱(pywebview)에서는 이 파일이 로드되지 않는다. */
(function () {
  const now = new Date();
  const iso = (d) => d.toISOString();
  const daysAgo = (n) => new Date(now.getTime() - n * 864e5);

  const meetings = [
    {
      id: 1,
      title: "마케팅 전략 회의",
      created_at: iso(daysAgo(0)),
      audio_path: "/tmp/a.m4a",
      transcript:
        "[0:00:01] 화자 1: 일단 새 캠페인 예산부터 얘기해볼게요. 4분기 목표가 꽤 공격적이라서요.\n" +
        "[0:00:12] 화자 2: 데이터 보안 쪽 검토는 끝났나요?\n" +
        "[0:00:20] 화자 1: 네, 전부 로컬에서 처리하기로 했습니다. 외부 전송이 없어요.",
      summary_md:
        "## 핵심 논의\n- 4분기 캠페인 예산 검토\n- 데이터 보안: 전부 로컬 처리 확정\n\n## 결정 사항\n- [x] 로컬 처리 방침 확정\n- [ ] 예산안 재검토",
      memo_md: "",
      stats_json: JSON.stringify({
        speakers: [
          { name: "화자 1", share: 72, quotes: ["일단 새 캠페인 예산부터 얘기해볼게요. 4분기 목표가 꽤 공격적이라서요"] },
          { name: "화자 2", share: 28, quotes: ["데이터 보안 쪽 검토는 끝났나요?"] },
        ],
      }),
    },
    {
      id: 2,
      title: "기술 아키텍처 리뷰",
      created_at: iso(daysAgo(3)),
      audio_path: "/tmp/b.m4a",
      transcript: "[0:00:02] 화자 1: 모듈 분리 구조를 다시 봅시다.",
      summary_md: "## 핵심 논의\n- 모듈 분리 구조 재검토",
      memo_md: "다음 회의 전에 다이어그램 준비",
      stats_json: JSON.stringify({
        speakers: [{ name: "화자 1", share: 100, quotes: ["모듈 분리 구조를 다시 봅시다"] }],
      }),
    },
    {
      id: 3,
      title: "AWS 파트너십 논의",
      created_at: iso(daysAgo(3)),
      audio_path: "/tmp/c.m4a",
      transcript: "",
      summary_md: "",
      memo_md: "",
      stats_json: "",
    },
  ];
  let nextId = 4;
  let recording = false;
  const delay = (ms) => new Promise((r) => setTimeout(r, ms));

  window.pywebview = {
    api: {
      async list_meetings() {
        return meetings
          .map((m) => ({ id: m.id, title: m.title, created_at: m.created_at }))
          .sort((a, b) => b.created_at.localeCompare(a.created_at) || b.id - a.id);
      },
      async get_meeting(id) {
        return meetings.find((m) => m.id === id) || null;
      },
      async update_meeting(id, fields) {
        const m = meetings.find((x) => x.id === id);
        if (m) Object.assign(m, fields);
        return true;
      },
      async delete_meeting(id) {
        const i = meetings.findIndex((m) => m.id === id);
        if (i >= 0) meetings.splice(i, 1);
        return true;
      },
      async pick_audio() {
        return "/tmp/새회의.m4a";
      },
      async add_meeting(path, title) {
        window.dispatchEvent(new CustomEvent("progress", { detail: "전사 중…" }));
        await delay(700);
        window.dispatchEvent(new CustomEvent("progress", { detail: "요약 중…" }));
        await delay(500);
        const m = {
          id: nextId++,
          title: title || path.split("/").pop().replace(/\.[^.]+$/, ""),
          created_at: iso(new Date()),
          audio_path: path,
          transcript: "[0:00:01] 화자 1: (모의 전사 결과)",
          summary_md: "## 핵심 논의\n- (모의 요약)",
          memo_md: "",
          stats_json: JSON.stringify({
            speakers: [{ name: "화자 1", share: 100, quotes: ["(모의 전사 결과)"] }],
          }),
        };
        meetings.push(m);
        return m;
      },
      async is_recording() {
        return recording;
      },
      async start_recording() {
        recording = true;
        return true;
      },
      async stop_recording() {
        recording = false;
        return this.add_meeting("/tmp/rec.wav", "녹음 " + new Date().toISOString().slice(0, 16).replace("T", " "));
      },
      async summarize_meeting(id) {
        await delay(600);
        const m = meetings.find((x) => x.id === id);
        const s = "## 핵심 논의\n- (다시 생성된 모의 요약)\n\n## 액션 아이템\n- [ ] 후속 확인";
        if (m) m.summary_md = s;
        return s;
      },
      async chat_meeting(id, question) {
        await delay(500);
        return "『" + question + "』에 대한 모의 답변입니다. 회의에서는 로컬 처리 방침이 확정됐습니다.";
      },
      async export_meeting(id) {
        return "/Users/me/Downloads/meeting.md";
      },
      async copy_for_notion(id) {
        return true;
      },
      async get_summary_template() {
        return this._tpl || "다음 회의 전사 내용을 읽고 요약하세요. (모의 기본 양식)\n\n{transcript}";
      },
      async default_summary_template() {
        return "다음 회의 전사 내용을 읽고 요약하세요. (모의 기본 양식)\n\n{transcript}";
      },
      async set_summary_template(t) {
        this._tpl = t;
        return true;
      },
      async get_hf_token() {
        return this._token || "";
      },
      async get_num_speakers() {
        return this._nspk || "";
      },
      async set_num_speakers(v) {
        this._nspk = v;
        return true;
      },
      async set_hf_token(t) {
        this._token = t;
        return true;
      },
    },
  };

  window.addEventListener("DOMContentLoaded", () => {
    window.dispatchEvent(new Event("pywebviewready"));
  });
})();
