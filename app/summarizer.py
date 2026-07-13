"""로컬 LLM(mlx-lm)으로 전사 스크립트를 마크다운으로 요약."""
from __future__ import annotations

DEFAULT_SUMMARY_MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"

# 사용자가 설정에서 바꿀 수 있는 기본 요약 양식.
# {transcript} 자리에 전사 내용(또는 부분 요약 모음)이 들어간다.
DEFAULT_TEMPLATE = """다음 회의 전사 내용을 읽고, 한국어 회의록 요약을 마크다운으로 작성하세요.

규칙:
- 각 항목은 구체적인 내용을 담은 완전한 문장으로 쓴다
- 전사에 없는 내용은 지어내지 않는다
- 해당 사항이 없는 섹션은 "없음" 한 단어로 쓴다
- 섹션 제목(##) 앞뒤에는 반드시 빈 줄을 넣는다

형식:
## 한 줄 요약

(회의 전체를 한 문장으로)

## 핵심 논의

- (논의된 주제와 구체적인 내용)

## 결정 사항

- (합의되거나 확정된 것)

## 액션 아이템

- [ ] (해야 할 일 — 담당자가 언급됐으면 함께 표기)

전사 내용:
{transcript}
"""

# 로컬 3B 모델의 컨텍스트를 넘지 않도록 긴 전사는 조각내 처리한다.
MAX_INPUT_CHARS = 6000

_PARTIAL_PROMPT = """다음은 긴 회의 전사의 일부입니다. 이 부분에서 논의된 내용만 한국어로 5줄 이내로 간결히 정리하세요. 지어내지 마세요.

{transcript}
"""


# 모델을 호출마다 다시 로드하지 않도록 캐시 (긴 회의의 조각 요약에서 특히 중요)
_MODEL_CACHE: dict = {}


def _load_model(model: str):
    if model not in _MODEL_CACHE:
        from mlx_lm import load
        _MODEL_CACHE[model] = load(model)
    return _MODEL_CACHE[model]


def _generate(prompt: str, model: str) -> str:
    from mlx_lm import generate
    from mlx_lm.sample_utils import make_sampler, make_logits_processors

    mdl, tokenizer = _load_model(model)
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    # 순수 greedy 디코딩(temp=0, 페널티 없음)은 긴 입력·복잡한 형식에서
    # 같은 문장이 무한 반복되는 루프에 잘 빠진다. 약한 temperature/top_p로
    # 매 스텝의 결정론을 깨고, repetition penalty로 최근에 쓴 토큰의 재선택을
    # 억제한다.
    #
    # 주의: penalty=1.3/ctx=200은 반복 루프는 막았지만 이 3B 모델에게는
    # 지나치게 세서, 정상적으로 재사용해야 할 토큰까지 막아버려 없는 사실을
    # 지어내고(예: "무드보드"를 "전자기억장치(EEG)"로 창작) 중국어 문자가
    # 섞여 나오는 심각한 품질 저하를 유발했다(실제 모델로 재현·확인함).
    # penalty=1.12/ctx=64로 완화한 뒤에는 같은 긴 입력에서 사실관계 왜곡·
    # 이물 문자 없이 정상 출력되는 것을 재확인했다. 무한 반복 자체는
    # 아래 _dedupe_repeated_lines()가 최후 안전망으로 계속 막아준다.
    sampler = make_sampler(temp=0.3, top_p=0.85)
    logits_processors = make_logits_processors(
        repetition_penalty=1.12, repetition_context_size=64
    )
    out = generate(
        mdl, tokenizer, prompt=text, max_tokens=1024, verbose=False,
        sampler=sampler, logits_processors=logits_processors,
    )
    return _dedupe_repeated_lines(out)


def _dedupe_repeated_lines(text: str) -> str:
    """반복 억제가 뚫렸을 때의 안전망: 같은 줄이 3번 이상 반복되면 그 지점에서 자른다."""
    lines = text.split("\n")
    seen: dict[str, int] = {}
    out: list[str] = []
    for line in lines:
        key = line.strip()
        if key:
            seen[key] = seen.get(key, 0) + 1
            if seen[key] > 2:
                break
        out.append(line)
    return "\n".join(out).rstrip()


def _fill(template: str, transcript: str) -> str:
    """{transcript} 자리 치환. 사용자 양식에 자리표시자가 없으면 뒤에 붙인다.

    str.format 대신 replace를 쓰는 이유: 사용자 양식에 다른 중괄호가
    있어도 깨지지 않아야 한다.
    """
    if "{transcript}" in template:
        return template.replace("{transcript}", transcript)
    return template + "\n\n전사 내용:\n" + transcript


def summarize(
    transcript: str,
    model: str = DEFAULT_SUMMARY_MODEL,
    template: str | None = None,
) -> str:
    if not transcript.strip():
        return ""
    tpl = template or DEFAULT_TEMPLATE

    text = transcript
    if len(text) > MAX_INPUT_CHARS:
        # 컨텍스트 초과 방지: 조각별 부분 요약 → 통합 요약
        parts = [
            text[i : i + MAX_INPUT_CHARS]
            for i in range(0, len(text), MAX_INPUT_CHARS)
        ]
        partials = [
            _generate(_fill(_PARTIAL_PROMPT, p), model).strip() for p in parts
        ]
        text = "\n".join(partials)

    return _generate(_fill(tpl, text), model).strip()


_CHAT_PROMPT = """다음은 회의 전사 내용입니다. 이 내용을 근거로 질문에 한국어로 간결하게 답하세요.
회의에 없는 내용은 지어내지 말고 "회의에서 언급되지 않았습니다"라고 답하세요.

전사 내용:
{transcript}

질문: {question}
"""

MAX_CHAT_CHARS = 12000


def chat(transcript: str, question: str, model: str = DEFAULT_SUMMARY_MODEL) -> str:
    """회의 전사 내용에 대한 질문에 로컬 LLM으로 답한다."""
    if not question.strip():
        return ""
    if not transcript.strip():
        return "전사 내용이 없습니다."
    if len(transcript) > MAX_CHAT_CHARS:
        # 컨텍스트 초과 방지: 앞부분 + 뒷부분만 사용
        transcript = transcript[:4000] + "\n…(중략)…\n" + transcript[-8000:]
    prompt = _CHAT_PROMPT.replace("{transcript}", transcript).replace(
        "{question}", question
    )
    return _generate(prompt, model).strip()
