"""로컬 LLM(mlx-lm)으로 전사 스크립트를 마크다운으로 요약."""
from __future__ import annotations

DEFAULT_SUMMARY_MODEL = "mlx-community/Qwen2.5-3B-Instruct-4bit"

_PROMPT = """다음은 회의 전사 내용입니다. 한국어로 간결한 회의록 요약을 마크다운으로 작성하세요.
형식:
## 핵심 논의
- ...
## 결정 사항
- ...
## 액션 아이템
- [ ] ...

전사 내용:
{transcript}
"""


def _generate(prompt: str, model: str) -> str:
    from mlx_lm import load, generate
    mdl, tokenizer = load(model)
    messages = [{"role": "user", "content": prompt}]
    text = tokenizer.apply_chat_template(
        messages, add_generation_prompt=True, tokenize=False
    )
    return generate(mdl, tokenizer, prompt=text, max_tokens=1024, verbose=False)


def summarize(transcript: str, model: str = DEFAULT_SUMMARY_MODEL) -> str:
    if not transcript.strip():
        return ""
    prompt = _PROMPT.format(transcript=transcript)
    return _generate(prompt, model).strip()


_CHAT_PROMPT = """다음은 회의 전사 내용입니다. 이 내용을 근거로 질문에 한국어로 간결하게 답하세요.
회의에 없는 내용은 지어내지 말고 "회의에서 언급되지 않았습니다"라고 답하세요.

전사 내용:
{transcript}

질문: {question}
"""


def chat(transcript: str, question: str, model: str = DEFAULT_SUMMARY_MODEL) -> str:
    """회의 전사 내용에 대한 질문에 로컬 LLM으로 답한다."""
    if not question.strip():
        return ""
    if not transcript.strip():
        return "전사 내용이 없습니다."
    prompt = _CHAT_PROMPT.format(transcript=transcript, question=question)
    return _generate(prompt, model).strip()
