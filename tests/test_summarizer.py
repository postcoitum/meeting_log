import app.summarizer as s


def test_empty_returns_empty():
    assert s.summarize("") == ""


def test_summarize_calls_llm_with_transcript(monkeypatch):
    captured = {}

    def fake_generate(prompt, model, max_tokens=1024):
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
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: "답")
    assert s.chat("화자 1: 내용", "질문?") == "답"


def test_summarize_uses_custom_template(monkeypatch):
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: prompts.append(p) or "요약")
    s.summarize("전사 내용", template="내 양식입니다\n{transcript}")
    assert prompts[0].startswith("내 양식입니다")
    assert "전사 내용" in prompts[0]


def test_summarize_strips_bracketed_examples_from_template(monkeypatch):
    """로컬 3B 모델이 "형식:" 섹션의 괄호 예시를 그대로 베껴 쓰는 버그 재현 방지.

    실제 사용자 회의로 재현: 괄호 예시가 프롬프트에 남아 있으면 모델이
    빈 채로 그 문구를 그대로 출력한다. 생성 프롬프트에서 예시 문구
    자체를 지워버리면(_strip_examples) 더 이상 베낄 텍스트가 없다.
    """
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: prompts.append(p) or "요약")
    template = (
        "형식:\n"
        "## 핵심 논의\n\n"
        "- (논의된 주제와 구체적인 내용)\n\n"
        "## 결정 사항\n\n"
        "- (합의되거나 확정된 것 모두)\n\n"
        "## 액션 아이템\n\n"
        "- [ ] (해야 할 일 — 담당자가 있으면 함께 표기)\n\n"
        "전사 내용:\n{transcript}"
    )
    s.summarize("전사 내용", template=template)
    assert "(논의된 주제와 구체적인 내용)" not in prompts[0]
    assert "(합의되거나 확정된 것 모두)" not in prompts[0]
    assert "(해야 할 일 — 담당자가 있으면 함께 표기)" not in prompts[0]
    assert "- [ ]" in prompts[0]  # 체크박스 자체는 유지돼야 함


def test_summarize_template_without_placeholder(monkeypatch):
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: prompts.append(p) or "요약")
    s.summarize("전사 내용", template="자리표시자 없는 양식")
    assert "자리표시자 없는 양식" in prompts[0]
    assert "전사 내용" in prompts[0]


def test_long_transcript_is_chunked(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: calls.append(p) or "부분요약")
    long_text = "가" * (s.MAX_INPUT_CHARS * 2 + 100)  # 3조각(타임스탬프 경계 없음 → 균등 분할)
    out = s.summarize(long_text)
    # 부분 요약 3번 + 통합 요약 1번 = 4번 호출
    assert len(calls) == 4
    assert out == "부분요약"
    # 마지막(통합) 호출 입력은 원문이 아니라 부분 요약 모음이어야 함
    assert "가가가" not in calls[-1]


def test_chunking_splits_at_timestamp_boundary(monkeypatch):
    calls = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: calls.append(p) or "부분요약")
    line = "[00:00:00] 화자 1: " + ("가" * 50) + "\n"
    long_text = line * ((s.MAX_INPUT_CHARS // len(line)) + 200)
    s.summarize(long_text)
    parts = s._split_at_timestamp_boundaries(long_text, s.MAX_INPUT_CHARS)
    assert len(parts) > 1
    for p in parts[:-1]:
        assert p.endswith("\n")  # 줄 중간이 아니라 줄 끝에서 잘렸어야 함


def test_final_max_tokens_scales_with_input_length(monkeypatch):
    captured = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: captured.append(kw.get("max_tokens")) or "요약")
    s.summarize("짧은 전사")
    short_tokens = captured[-1]
    s.summarize("가" * 20000)
    long_tokens = captured[-1]
    assert short_tokens == 1024  # 하한
    assert long_tokens > short_tokens
    assert long_tokens <= 3072  # 상한


def test_strip_meta_sentences_removes_trailing_summary_line():
    text = "## 핵심 논의\n- 실제 내용\n\n이러한 내용을 요약하면 다음과 같습니다."
    out = s._strip_meta_sentences(text)
    assert "실제 내용" in out
    assert "이러한 내용을 요약하면" not in out


def test_long_chat_transcript_is_truncated(monkeypatch):
    prompts = []
    monkeypatch.setattr(s, "_generate", lambda p, m, **kw: prompts.append(p) or "답")
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
