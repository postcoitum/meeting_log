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


def test_dedupe_repeated_lines_cuts_after_third_repeat():
    text = (
        "## 결정 사항\n"
        "- 7월 16일 회의\n"
        "- 7월 20일 촬영\n"
        "- 7월 16일 회의\n"
        "- 7월 20일 촬영\n"
        "- 7월 16일 회의\n"  # 3번째 반복 -> 여기서 잘림
        "- 이 뒤는 잘려야 함\n"
    )
    out = s._dedupe_repeated_lines(text)
    assert out.count("- 7월 16일 회의") == 2
    assert "이 뒤는 잘려야 함" not in out


def test_dedupe_keeps_normal_text_untouched():
    text = "## 한 줄 요약\n\n회의 내용 요약입니다.\n\n## 결정 사항\n\n- 항목1\n- 항목2\n"
    assert s._dedupe_repeated_lines(text) == text.rstrip()


def test_generate_uses_sampler_and_repetition_penalty(monkeypatch):
    captured = {}

    class FakeSampler:
        pass

    class FakeProcessors:
        pass

    def fake_make_sampler(**kwargs):
        captured["sampler_kwargs"] = kwargs
        return FakeSampler()

    def fake_make_logits_processors(**kwargs):
        captured["penalty_kwargs"] = kwargs
        return FakeProcessors()

    def fake_generate(mdl, tok, prompt, max_tokens, verbose, sampler, logits_processors):
        captured["sampler"] = sampler
        captured["logits_processors"] = logits_processors
        return "결과"

    fake_mlx_lm = type("M", (), {"generate": staticmethod(fake_generate)})
    fake_sample_utils = type("SU", (), {
        "make_sampler": staticmethod(fake_make_sampler),
        "make_logits_processors": staticmethod(fake_make_logits_processors),
    })
    monkeypatch.setitem(__import__("sys").modules, "mlx_lm", fake_mlx_lm)
    monkeypatch.setitem(__import__("sys").modules, "mlx_lm.sample_utils", fake_sample_utils)
    monkeypatch.setattr(
        s, "_load_model",
        lambda model: (object(), type("T", (), {
            "apply_chat_template": lambda self, messages, add_generation_prompt, tokenize: "프롬프트"
        })()),
    )

    out = s._generate("테스트 프롬프트", s.DEFAULT_SUMMARY_MODEL)
    assert out == "결과"
    assert isinstance(captured["sampler"], FakeSampler)
    assert isinstance(captured["logits_processors"], FakeProcessors)
    assert captured["sampler_kwargs"]["temp"] > 0  # 순수 greedy 아님
    assert captured["penalty_kwargs"]["repetition_penalty"] > 1.0
