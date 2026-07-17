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
        "## 한 줄 요약\n\n4분기 캠페인 예산과 데이터 보안(전부 로컬 처리)을 확정했다.\n\n## 핵심 논의\n\n- 4분기 캠페인 예산 검토 — 목표가 공격적이라 재검토 필요\n- 데이터 보안: **전부 로컬 처리**로 확정, 외부 전송 없음\n\n## 결정 사항\n\n- [x] 로컬 처리 방침 확정\n\n## 액션 아이템\n\n- [ ] 예산안 재검토 @정연\n\n## 논의 필요 사항\n\n- 팀 플랜 가격 정책 (다음 회의에서 결정)",
      memo_md: "",
      duration_sec: 1830,
      status: "done",
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
      summary_md: "## 핵심 논의\n\n- 모듈 분리 구조 재검토",
      memo_md: "다음 회의 전에 다이어그램 준비",
      duration_sec: 240,
      status: "done",
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
      duration_sec: 0,
      status: "done",
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
          .map((m) => ({
            id: m.id, title: m.title, created_at: m.created_at,
            duration_sec: m.duration_sec || 0, status: m.status || "done",
          }))
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
        // 실제 API처럼 즉시 '대기중' row를 만들고 리턴 — 처리는 뒤에서 비동기로.
        // 그래야 mock 하니스로도 "여러 파일 연속 추가" 동작을 확인할 수 있다.
        const id = nextId++;
        const m = {
          id,
          title: title || path.split("/").pop().replace(/\.[^.]+$/, ""),
          created_at: iso(new Date()),
          audio_path: path,
          transcript: "",
          summary_md: "",
          memo_md: "",
          duration_sec: 0,
          status: "queued",
          stats_json: "",
        };
        meetings.push(m);

        (async () => {
          m.status = "processing";
          window.dispatchEvent(new CustomEvent("job-progress", {
            detail: { id, status: "processing", stage: "오디오 변환 중…" },
          }));
          await delay(600);
          window.dispatchEvent(new CustomEvent("job-progress", {
            detail: { id, status: "processing", stage: "전사 중…" },
          }));
          await delay(700);
          window.dispatchEvent(new CustomEvent("job-progress", {
            detail: { id, status: "processing", stage: "요약 중…" },
          }));
          await delay(500);
          m.transcript = "[0:00:01] 화자 1: (모의 전사 결과)";
          m.summary_md =
            "## 한 줄 요약\n\n(모의 요약)\n\n## 핵심 논의\n\n- (모의 논의 사항)\n\n" +
            "## 결정 사항\n\n- 없음\n\n## 액션 아이템\n\n- [ ] (모의 액션)\n\n" +
            "## 논의 필요 사항\n\n- 없음";
          m.stats_json = JSON.stringify({
            speakers: [{ name: "화자 1", share: 100, quotes: ["(모의 전사 결과)"] }],
          });
          m.duration_sec = 185;
          m.status = "done";
          window.dispatchEvent(new CustomEvent("job-progress", {
            detail: { id, status: "done", stage: "" },
          }));
        })();

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
