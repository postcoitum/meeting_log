import app.summarizer as s


def test_empty_returns_empty():
    assert s.summarize("") == ""


def test_summarize_calls_llm_with_transcript(monkeypatch):
    captured = {}

    def fake_generate(prompt, model):
        captured["prompt"] = prompt
        return "## 핵심 논의\n- 테스트"

    monkeypatch.setattr(s, "_generate", fake_generate)
    out = s.summarize("화자 1: 안녕하세요 회의 시작합니다")
    assert "## 핵심 논의" in out
    assert "안녕하세요" in captured["prompt"]


def test_chat_empty_question_returns_empty():
    assert s.chat("전사 내용", "") == ""


def test_chat_no_transcript_says_so():
    assert "없습니다" in s.chat("", "질문?")


def test_chat_calls_llm(monkeypatch):
    monkeypatch.setattr(s, "_generate", lambda p, m: "답")
    assert s.chat("화자 1: 내용", "질문?") == "답"


def test_summarize_uses_custom_template(monkeypatch):
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m: prompts.append(p) or "요약")
    s.summarize("전사 내용", template="내 양식입니다\n{transcript}")
    assert prompts[0].startswith("내 양식입니다")
    assert "전사 내용" in prompts[0]


def test_summarize_template_without_placeholder(monkeypatch):
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m: prompts.append(p) or "요약")
    s.summarize("전사 내용", template="자리표시자 없는 양식")
    assert "자리표시자 없는 양식" in prompts[0]
    assert "전사 내용" in prompts[0]


def test_long_transcript_is_chunked(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "_generate", lambda p, m: calls.append(p) or "부분요약")
    long_text = "가" * (s.MAX_INPUT_CHARS * 2 + 100)  # 3조각
    out = s.summarize(long_text)
    # 부분 요약 3번 + 통합 요약 1번 = 4번 호출
    assert len(calls) == 4
    assert out == "부분요약"
    # 마지막(통합) 호출 입력은 원문이 아니라 부분 요약 모음이어야 함
    assert "가가가" not in calls[-1]


def test_long_chat_transcript_is_truncated(monkeypatch):
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m: prompts.append(p) or "답")
    long_text = "나" * (s.MAX_CHAT_CHARS + 5000)
    s.chat(long_text, "질문?")
    assert "…(중략)…" in prompts[0]
    assert len(prompts[0]) < s.MAX_CHAT_CHARS + 2000
