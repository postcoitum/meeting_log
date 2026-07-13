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
    mdl, tokenizer = _load_model(model)
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    return generate(mdl, tokenizer, prompt=text, max_tokens=1024, verbose=False)


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
