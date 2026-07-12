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
