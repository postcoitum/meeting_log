# 로컬 회의록 데스크톱 앱 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 CLI(전사+화자분리)를 재사용해, 파일 업로드→전사→로컬 AI 요약→마크다운 편집·메모·로컬 저장이 되는 pywebview 데스크톱 앱을 만든다.

**Architecture:** Python 단일 백엔드(전사 래퍼·요약·SQLite 저장)를 pywebview 브릿지로 노출하고, 웹(HTML/CSS/JS) 프론트가 4영역 레이아웃으로 호출한다. 무거운 작업(전사·요약)은 백그라운드 스레드에서 실행하고 진행 상태를 프론트로 전달한다.

**Tech Stack:** Python 3.12, pywebview, SQLite(stdlib `sqlite3`), mlx-whisper, pyannote.audio, mlx-lm(`Qwen2.5-3B-Instruct`), 바닐라 JS + marked.js(마크다운).

## Global Constraints

- 플랫폼: Apple Silicon macOS 전용
- 모든 처리·저장은 로컬 (네트워크 전송 없음; 모델 다운로드만 예외)
- 전사 기본 모델: `mlx-community/whisper-large-v3-turbo`
- 요약 기본 모델: `mlx-community/Qwen2.5-3B-Instruct-4bit`
- HF 토큰은 `$HF_TOKEN` 또는 앱 설정에서 읽음 (pyannote 게이트 모델용)
- 오디오 원본은 복사하지 않고 경로만 저장
- 기존 파일(`meeting_recorder.py`, `audio_utils.py`, `speaker_utils.py`)의 동작을 깨지 않는다
- 각 작업 끝에 커밋한다 (git 히스토리 = 진행 로그)

---

## 파일 구조

```
meeting_log/
  app/
    __init__.py
    store.py          # SQLite CRUD (회의 저장/조회/수정/삭제)
    transcribe.py     # 기존 meeting_recorder 로직을 함수로 감싼 래퍼
    summarizer.py     # mlx-lm으로 스크립트 → 마크다운 요약
    api.py            # pywebview JS↔Python 브릿지 (Api 클래스)
    main.py           # pywebview 앱 진입점 (창 생성 + Api 연결)
    web/
      index.html      # 4영역 레이아웃 셸 + 상단바 토글
      style.css       # 브라운베이지 글래스 스타일
      app.js          # 목록/요약·메모 에디터/스크립트 뷰어 + 브릿지 호출
  tests/
    __init__.py
    test_store.py
    test_transcribe.py
    test_summarizer.py
  meeting_recorder.py  # 기존 (CLI, 그대로 둠)
  audio_utils.py       # 기존 (재사용)
  speaker_utils.py     # 기존 (재사용)
  requirements.txt     # pywebview, mlx-lm 추가
```

각 파일 책임:
- `store.py`: DB 입출력만. 다른 모듈 의존 없음.
- `transcribe.py`: 오디오 경로 → 구조화된 전사 결과. `audio_utils`/`speaker_utils`/`meeting_recorder` 재사용.
- `summarizer.py`: 텍스트 → 마크다운 요약. LLM 호출 격리.
- `api.py`: 위 3개를 묶어 프론트에 노출. 백그라운드 스레드 관리.
- `web/*`: 표시·편집·상호작용.

---

## Task 1: 프로젝트 스캐폴드 + 빈 pywebview 창

**Files:**
- Create: `app/__init__.py`
- Create: `app/main.py`
- Create: `app/web/index.html`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `app/main.py`에 `main()` 진입점. `app/web/index.html` 정적 셸.

- [ ] **Step 1: requirements.txt에 의존성 추가**

`requirements.txt` 끝에 추가:
```
# 데스크톱 앱
pywebview
mlx-lm
```

- [ ] **Step 2: 의존성 설치**

Run: `pip install pywebview mlx-lm`
Expected: 설치 성공 (pyobjc 등 macOS 의존성 포함)

- [ ] **Step 3: 최소 index.html 작성**

`app/web/index.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>회의록</title>
</head>
<body>
  <h1 id="status">회의록 앱</h1>
</body>
</html>
```

- [ ] **Step 4: app/__init__.py (빈 파일)**

`app/__init__.py`: 빈 파일로 생성.

- [ ] **Step 5: app/main.py 작성**

`app/main.py`:
```python
"""pywebview 앱 진입점."""
from pathlib import Path
import webview

WEB_DIR = Path(__file__).parent / "web"


def main() -> None:
    window = webview.create_window(
        "회의록",
        str(WEB_DIR / "index.html"),
        width=1200,
        height=760,
        min_size=(900, 600),
    )
    webview.start()
    _ = window


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 실행해서 창이 뜨는지 확인**

Run: `python3 -m app.main`
Expected: "회의록 앱" 텍스트가 보이는 네이티브 창이 열림. 창을 닫으면 종료.

- [ ] **Step 7: 커밋**

```bash
git add app requirements.txt
git commit -m "feat: scaffold pywebview app with empty window"
```

---

## Task 2: SQLite 저장 모듈 (store.py)

**Files:**
- Create: `app/store.py`
- Test: `tests/test_store.py`
- Create: `tests/__init__.py` (빈 파일)

**Interfaces:**
- Produces:
  - `Store(db_path: str)` — 생성 시 테이블 보장
  - `Store.create_meeting(title: str, created_at: str, audio_path: str, transcript: str) -> int` (id 반환)
  - `Store.list_meetings() -> list[dict]` (id, title, created_at; created_at 내림차순)
  - `Store.get_meeting(meeting_id: int) -> dict | None` (모든 컬럼)
  - `Store.update_fields(meeting_id: int, **fields) -> None` (title/summary_md/memo_md/transcript 중 일부)
  - `Store.delete_meeting(meeting_id: int) -> None`

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/__init__.py`: 빈 파일.

`tests/test_store.py`:
```python
from app.store import Store


def test_create_and_get(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("회의1", "2026-06-21T10:00:00", "/a.m4a", "원본 텍스트")
    got = s.get_meeting(mid)
    assert got["title"] == "회의1"
    assert got["transcript"] == "원본 텍스트"
    assert got["summary_md"] == ""
    assert got["memo_md"] == ""


def test_list_sorted_desc(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.create_meeting("old", "2026-06-20T10:00:00", "/a", "x")
    s.create_meeting("new", "2026-06-21T10:00:00", "/b", "y")
    rows = s.list_meetings()
    assert [r["title"] for r in rows] == ["new", "old"]


def test_update_fields(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    s.update_fields(mid, title="새 제목", summary_md="## 요약", memo_md="메모")
    got = s.get_meeting(mid)
    assert got["title"] == "새 제목"
    assert got["summary_md"] == "## 요약"
    assert got["memo_md"] == "메모"


def test_delete(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    s.delete_meeting(mid)
    assert s.get_meeting(mid) is None


def test_update_rejects_unknown_field(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    try:
        s.update_fields(mid, evil="x")
        assert False, "should have raised"
    except ValueError:
        pass
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: FAIL ("No module named 'app.store'")

- [ ] **Step 3: store.py 구현**

`app/store.py`:
```python
"""회의 데이터를 로컬 SQLite에 저장하는 모듈."""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone

_ALLOWED_UPDATE = {"title", "summary_md", "memo_md", "transcript"}

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meetings (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    audio_path  TEXT NOT NULL,
    transcript  TEXT NOT NULL DEFAULT '',
    summary_md  TEXT NOT NULL DEFAULT '',
    memo_md     TEXT NOT NULL DEFAULT '',
    updated_at  TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, db_path: str) -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute(_SCHEMA)
        self._conn.commit()

    def create_meeting(self, title, created_at, audio_path, transcript) -> int:
        cur = self._conn.execute(
            "INSERT INTO meetings (title, created_at, audio_path, transcript, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (title, created_at, audio_path, transcript, _now()),
        )
        self._conn.commit()
        return int(cur.lastrowid)

    def list_meetings(self) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, title, created_at FROM meetings ORDER BY created_at DESC, id DESC"
        ).fetchall()
        return [dict(r) for r in rows]

    def get_meeting(self, meeting_id: int) -> dict | None:
        row = self._conn.execute(
            "SELECT * FROM meetings WHERE id = ?", (meeting_id,)
        ).fetchone()
        return dict(row) if row else None

    def update_fields(self, meeting_id: int, **fields) -> None:
        if not fields:
            return
        bad = set(fields) - _ALLOWED_UPDATE
        if bad:
            raise ValueError(f"Unknown field(s): {', '.join(sorted(bad))}")
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [_now(), meeting_id]
        self._conn.execute(
            f"UPDATE meetings SET {cols}, updated_at = ? WHERE id = ?", vals
        )
        self._conn.commit()

    def delete_meeting(self, meeting_id: int) -> None:
        self._conn.execute("DELETE FROM meetings WHERE id = ?", (meeting_id,))
        self._conn.commit()
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_store.py -v`
Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add app/store.py tests/test_store.py tests/__init__.py
git commit -m "feat: add SQLite store module with CRUD"
```

---

## Task 3: 전사 백엔드 래퍼 (transcribe.py)

**Files:**
- Create: `app/transcribe.py`
- Test: `tests/test_transcribe.py`

**Interfaces:**
- Consumes: 기존 `audio_utils.to_wav_16k`, `meeting_recorder.transcribe_audio`, `meeting_recorder.diarize_audio`, `speaker_utils.align_segments/map_speakers/merge_consecutive/format_transcript`
- Produces:
  - `transcribe_meeting(audio_path: str, hf_token: str, model_repo: str = ..., progress=None) -> str` — 화자/시간 포함 전사 텍스트(format_transcript 결과)를 반환. `progress`는 `callable(stage: str)` 선택.

- [ ] **Step 1: 실패하는 테스트 작성 (의존성 모킹)**

`tests/test_transcribe.py`:
```python
import app.transcribe as t


def test_transcribe_meeting_pipeline(monkeypatch, tmp_path):
    fake_wav = tmp_path / "x.wav"
    fake_wav.write_bytes(b"")

    monkeypatch.setattr(t, "to_wav_16k", lambda p: fake_wav)
    monkeypatch.setattr(
        t, "transcribe_audio",
        lambda wav, lang, repo: [(0.0, 1.0, "안녕")],
    )
    monkeypatch.setattr(
        t, "diarize_audio",
        lambda wav, token, num_speakers=None, max_speakers=None: [(0.0, 1.0, "SPEAKER_00")],
    )

    stages = []
    out = t.transcribe_meeting("/in.m4a", "tok", progress=stages.append)

    assert "안녕" in out
    assert "변환" in stages[0] or "transcrib" in stages[0].lower()
    assert not fake_wav.exists()  # 임시 wav 정리됨
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_transcribe.py -v`
Expected: FAIL ("No module named 'app.transcribe'")

- [ ] **Step 3: transcribe.py 구현**

`app/transcribe.py`:
```python
"""기존 CLI 로직을 앱에서 호출할 수 있게 감싼 전사 래퍼."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from audio_utils import to_wav_16k
from meeting_recorder import transcribe_audio, diarize_audio
from speaker_utils import (
    align_segments, map_speakers, merge_consecutive, format_transcript,
)

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"


def transcribe_meeting(
    audio_path: str,
    hf_token: str,
    model_repo: str = DEFAULT_MODEL,
    progress: Callable[[str], None] | None = None,
) -> str:
    def report(stage: str) -> None:
        if progress:
            progress(stage)

    report("오디오 변환 중…")
    wav = to_wav_16k(Path(audio_path))
    try:
        report("전사 중…")
        whisper_segs = transcribe_audio(wav, "ko", model_repo)
        report("화자 분리 중…")
        diar_segs = diarize_audio(wav, hf_token)

        aligned = align_segments(whisper_segs, diar_segs)
        # 이름은 화자 N 기본 라벨 사용
        speakers = sorted({s for _, s, _ in aligned})
        name_map = {sid: f"화자 {i + 1}" for i, sid in enumerate(speakers)}
        named = map_speakers(aligned, name_map)
        merged = merge_consecutive(named)
        return format_transcript(merged, with_timestamps=True)
    finally:
        if wav != Path(audio_path):
            wav.unlink(missing_ok=True)
```

> 참고: `align_segments`가 `(start, speaker, text)`를 반환하므로 화자 집합을 거기서 뽑는다. 기존 `speaker_utils.py`의 시그니처와 일치.

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_transcribe.py -v`
Expected: 1 passed

- [ ] **Step 5: 커밋**

```bash
git add app/transcribe.py tests/test_transcribe.py
git commit -m "feat: add transcription wrapper reusing CLI pipeline"
```

---

## Task 4: 로컬 AI 요약 모듈 (summarizer.py)

**Files:**
- Create: `app/summarizer.py`
- Test: `tests/test_summarizer.py`

**Interfaces:**
- Produces:
  - `summarize(transcript: str, model: str = DEFAULT_SUMMARY_MODEL) -> str` — 마크다운 요약 반환. 빈 transcript면 `""` 반환. mlx-lm은 함수 내부에서 지연 import(테스트에서 모킹 가능하도록 `_generate`로 분리).
  - `_generate(prompt: str, model: str) -> str` — 실제 LLM 호출 (모킹 지점).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_summarizer.py`:
```python
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
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_summarizer.py -v`
Expected: FAIL ("No module named 'app.summarizer'")

- [ ] **Step 3: summarizer.py 구현**

`app/summarizer.py`:
```python
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
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_summarizer.py -v`
Expected: 2 passed

- [ ] **Step 5: 커밋**

```bash
git add app/summarizer.py tests/test_summarizer.py
git commit -m "feat: add local LLM summarizer (mlx-lm)"
```

---

## Task 5: pywebview 브릿지 (api.py)

**Files:**
- Create: `app/api.py`
- Modify: `app/main.py`
- Test: `tests/test_api.py`

**Interfaces:**
- Consumes: `Store`, `transcribe_meeting`, `summarize`
- Produces (프론트가 `window.pywebview.api.*`로 호출):
  - `Api.list_meetings() -> list[dict]`
  - `Api.get_meeting(meeting_id) -> dict | None`
  - `Api.update_meeting(meeting_id, **fields) -> bool`
  - `Api.delete_meeting(meeting_id) -> bool`
  - `Api.add_meeting(audio_path) -> dict` — 전사+요약+저장 후 생성된 회의 dict 반환 (동기; 프론트는 로딩 표시)
  - `Api.summarize_meeting(meeting_id) -> str` — 저장된 transcript로 요약 생성·저장·반환

- [ ] **Step 1: 실패하는 테스트 작성 (전사·요약 모킹)**

`tests/test_api.py`:
```python
import app.api as api_mod
from app.store import Store


def make_api(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))
    monkeypatch.setattr(api_mod, "transcribe_meeting",
                        lambda path, token, progress=None: "화자 1: 안녕")
    monkeypatch.setattr(api_mod, "summarize", lambda text: "## 요약\n- x")
    return api_mod.Api(store=store, hf_token="tok")


def test_add_meeting_creates_with_transcript_and_summary(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/some/audio.m4a")
    assert m["transcript"] == "화자 1: 안녕"
    assert m["summary_md"] == "## 요약\n- x"
    assert m["title"] == "audio"  # 파일 stem 기본 제목


def test_update_and_get(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    assert api.update_meeting(m["id"], memo_md="내 메모") is True
    assert api.get_meeting(m["id"])["memo_md"] == "내 메모"


def test_list_after_add(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    api.add_meeting("/a/one.m4a")
    assert len(api.list_meetings()) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_api.py -v`
Expected: FAIL ("No module named 'app.api'")

- [ ] **Step 3: api.py 구현**

`app/api.py`:
```python
"""pywebview JS↔Python 브릿지."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from app.store import Store
from app.transcribe import transcribe_meeting
from app.summarizer import summarize


class Api:
    def __init__(self, store: Store, hf_token: str = "") -> None:
        self._store = store
        self._hf_token = hf_token or os.environ.get("HF_TOKEN", "")

    def list_meetings(self) -> list[dict]:
        return self._store.list_meetings()

    def get_meeting(self, meeting_id: int) -> dict | None:
        return self._store.get_meeting(meeting_id)

    def update_meeting(self, meeting_id: int, **fields) -> bool:
        self._store.update_fields(meeting_id, **fields)
        return True

    def delete_meeting(self, meeting_id: int) -> bool:
        self._store.delete_meeting(meeting_id)
        return True

    def add_meeting(self, audio_path: str) -> dict:
        transcript = transcribe_meeting(audio_path, self._hf_token)
        summary = summarize(transcript)
        title = Path(audio_path).stem
        created = datetime.now(timezone.utc).isoformat()
        mid = self._store.create_meeting(title, created, audio_path, transcript)
        self._store.update_fields(mid, summary_md=summary)
        return self._store.get_meeting(mid)

    def summarize_meeting(self, meeting_id: int) -> str:
        m = self._store.get_meeting(meeting_id)
        if not m:
            return ""
        summary = summarize(m["transcript"])
        self._store.update_fields(meeting_id, summary_md=summary)
        return summary
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_api.py -v`
Expected: 3 passed

- [ ] **Step 5: main.py에서 Api 연결**

`app/main.py`를 수정:
```python
"""pywebview 앱 진입점."""
import os
from pathlib import Path

import webview

from app.store import Store
from app.api import Api

WEB_DIR = Path(__file__).parent / "web"
DB_PATH = str(Path.home() / ".meeting_log" / "meetings.db")


def main() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    api = Api(store=Store(DB_PATH), hf_token=os.environ.get("HF_TOKEN", ""))
    window = webview.create_window(
        "회의록",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1200,
        height=760,
        min_size=(900, 600),
    )
    webview.start()
    _ = window


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: 전체 백엔드 테스트 통과 확인**

Run: `python3 -m pytest tests/ -v`
Expected: 모든 테스트 passed

- [ ] **Step 7: 커밋**

```bash
git add app/api.py app/main.py tests/test_api.py
git commit -m "feat: add pywebview bridge API and wire into app"
```

---

## Task 6: 프론트 레이아웃 셸 + 글래스 스타일

**Files:**
- Modify: `app/web/index.html`
- Create: `app/web/style.css`

**Interfaces:**
- Produces: 4영역 레이아웃 DOM(상단바 토글, 좌측 `#meeting-list`, 중앙 `#summary`, 우상단 `#memo`, 우하단 `#transcript`). `app.js`가 이 id들을 채운다.

- [ ] **Step 1: index.html 레이아웃 작성**

`app/web/index.html`:
```html
<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="utf-8">
  <title>회의록</title>
  <link rel="stylesheet" href="style.css">
  <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
</head>
<body>
  <header class="topbar">
    <button id="toggle-sidebar" aria-label="사이드바 토글">☰</button>
    <span class="app-title">회의록</span>
    <span id="progress" class="progress"></span>
  </header>
  <main class="layout">
    <aside id="sidebar" class="pane sidebar">
      <div class="pane-head">
        <span>회의 목록</span>
        <button id="edit-title" aria-label="제목 수정">✎</button>
      </div>
      <div id="meeting-list" class="list"></div>
      <button id="new-meeting" class="new-btn">+ 새 회의</button>
    </aside>
    <section class="pane summary">
      <div class="pane-head"><span>회의 요약</span></div>
      <textarea id="summary" class="editor" placeholder="로컬 AI 요약…"></textarea>
    </section>
    <section class="right">
      <div id="memo-pane" class="pane memo">
        <div class="pane-head">
          <span>내 메모</span>
          <button id="toggle-memo" aria-label="메모 접기">⌄</button>
        </div>
        <textarea id="memo" class="editor" placeholder="여기에 메모… (마크다운)"></textarea>
      </div>
      <div class="pane transcript">
        <div class="pane-head"><span>스크립트 원본</span></div>
        <pre id="transcript" class="script"></pre>
      </div>
    </section>
  </main>
  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 2: style.css 작성 (브라운베이지 글래스)**

`app/web/style.css`:
```css
* { box-sizing: border-box; margin: 0; }
body {
  font-family: -apple-system, "Apple SD Gothic Neo", sans-serif;
  height: 100vh; color: #3c3324;
  background: linear-gradient(135deg, #d8c7b0, #e7d9c4 55%, #cbb89c);
}
.topbar {
  display: flex; align-items: center; gap: 12px;
  padding: 10px 16px; -webkit-app-region: drag;
}
.topbar button { -webkit-app-region: no-drag; }
.app-title { font-size: 13px; color: #4a3f30; }
.progress { margin-left: auto; font-size: 12px; color: #8a6d3b; }
.layout {
  display: grid; grid-template-columns: 200px 1fr 1fr; gap: 12px;
  padding: 0 14px 14px; height: calc(100vh - 48px);
}
.layout.sidebar-hidden { grid-template-columns: 0 1fr 1fr; }
.layout.sidebar-hidden .sidebar { display: none; }
.right { display: grid; grid-template-rows: 1fr 1.5fr; gap: 12px; }
.right.memo-collapsed { grid-template-rows: 40px 1fr; }
.pane {
  background: rgba(255, 252, 246, 0.45);
  border: 1px solid rgba(255, 255, 255, 0.6);
  border-radius: 12px; padding: 12px;
  display: flex; flex-direction: column;
  backdrop-filter: blur(12px); overflow: hidden;
}
.pane-head {
  display: flex; align-items: center; justify-content: space-between;
  font-size: 13px; font-weight: 500; color: #4a3f30; margin-bottom: 8px;
}
.pane-head button { background: none; border: none; cursor: pointer; font-size: 14px; color: #8a7a64; }
.list { flex: 1; overflow-y: auto; }
.date-group { font-size: 11px; color: #9a8a72; margin: 8px 0 4px; }
.meeting-item {
  padding: 7px 9px; border-radius: 8px; font-size: 12px; cursor: pointer;
  background: rgba(255, 252, 246, 0.4); margin-bottom: 6px; color: #5c5343;
}
.meeting-item.active { background: rgba(255, 252, 246, 0.85); color: #3c3324; }
.new-btn {
  margin-top: 8px; background: rgba(120, 90, 55, 0.85); color: #fff;
  border: none; border-radius: 8px; padding: 9px; font-size: 12px; cursor: pointer;
}
.editor {
  flex: 1; resize: none; border: none; background: transparent;
  font-size: 13px; line-height: 1.7; color: #3c3324; outline: none;
}
.script { flex: 1; overflow-y: auto; font-size: 12px; line-height: 1.7; color: #5c5343; white-space: pre-wrap; }
```

- [ ] **Step 3: 실행해서 레이아웃 확인**

Run: `python3 -m app.main`
Expected: 4영역 글래스 레이아웃이 보임 (목록은 비어 있음, 입력칸·토글 버튼 존재). 콘솔 에러 없음.

- [ ] **Step 4: 커밋**

```bash
git add app/web/index.html app/web/style.css
git commit -m "feat: add 4-pane glass layout shell"
```

---

## Task 7: 프론트 로직 (app.js) — 목록·편집·전환

**Files:**
- Create: `app/web/app.js`

**Interfaces:**
- Consumes: `window.pywebview.api.{list_meetings,get_meeting,update_meeting,add_meeting,summarize_meeting}`
- Produces: 사용자 상호작용 (목록 렌더, 회의 선택, 요약/메모 자동저장, 토글, 제목수정).

- [ ] **Step 1: app.js 작성**

`app/web/app.js`:
```javascript
let currentId = null;

async function api(name, ...args) {
  return await window.pywebview.api[name](...args);
}

function groupByDate(meetings) {
  const groups = {};
  for (const m of meetings) {
    const d = m.created_at.slice(0, 10).replace(/-/g, ". ");
    (groups[d] = groups[d] || []).push(m);
  }
  return groups;
}

async function renderList() {
  const list = await api("list_meetings");
  const el = document.getElementById("meeting-list");
  el.innerHTML = "";
  const groups = groupByDate(list);
  for (const [date, items] of Object.entries(groups)) {
    const h = document.createElement("div");
    h.className = "date-group";
    h.textContent = date;
    el.appendChild(h);
    for (const m of items) {
      const d = document.createElement("div");
      d.className = "meeting-item" + (m.id === currentId ? " active" : "");
      d.textContent = m.title;
      d.onclick = () => openMeeting(m.id);
      el.appendChild(d);
    }
  }
}

async function openMeeting(id) {
  currentId = id;
  const m = await api("get_meeting", id);
  document.getElementById("summary").value = m.summary_md || "";
  document.getElementById("memo").value = m.memo_md || "";
  document.getElementById("transcript").textContent = m.transcript || "";
  renderList();
}

function debounce(fn, ms) {
  let t;
  return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); };
}

const saveSummary = debounce(() => {
  if (currentId) api("update_meeting", currentId, { summary_md: document.getElementById("summary").value });
}, 600);
const saveMemo = debounce(() => {
  if (currentId) api("update_meeting", currentId, { memo_md: document.getElementById("memo").value });
}, 600);

function bind() {
  document.getElementById("summary").addEventListener("input", saveSummary);
  document.getElementById("memo").addEventListener("input", saveMemo);

  document.getElementById("toggle-sidebar").onclick = () =>
    document.querySelector(".layout").classList.toggle("sidebar-hidden");
  document.getElementById("toggle-memo").onclick = () =>
    document.querySelector(".right").classList.toggle("memo-collapsed");

  document.getElementById("edit-title").onclick = async () => {
    if (!currentId) return;
    const name = prompt("새 제목");
    if (name) { await api("update_meeting", currentId, { title: name }); renderList(); }
  };

  document.getElementById("new-meeting").onclick = async () => {
    const path = await window.pywebview.api.pick_audio();
    if (!path) return;
    setProgress("처리 중…");
    try {
      const m = await api("add_meeting", path);
      currentId = m.id;
      await renderList();
      await openMeeting(m.id);
    } catch (e) {
      setProgress("실패: " + e);
      return;
    }
    setProgress("");
  };
}

function setProgress(text) {
  document.getElementById("progress").textContent = text;
}

window.addEventListener("pywebviewready", () => { bind(); renderList(); });
```

> 참고: `pick_audio`는 Task 8에서 `Api`에 추가한다 (파일 선택 다이얼로그).

- [ ] **Step 2: 커밋**

```bash
git add app/web/app.js
git commit -m "feat: add frontend logic for list, edit, autosave"
```

---

## Task 8: 파일 선택 + 새 회의 흐름 완성

**Files:**
- Modify: `app/api.py` (pick_audio 추가)
- Test: `tests/test_api.py` (pick_audio 모킹 테스트 추가)

**Interfaces:**
- Produces: `Api.pick_audio() -> str` — 네이티브 파일 다이얼로그로 오디오 경로 반환 (취소 시 `""`).

- [ ] **Step 1: pick_audio 테스트 추가**

`tests/test_api.py` 끝에 추가:
```python
def test_pick_audio_returns_first(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.webview, "active_window",
                        lambda: type("W", (), {"create_file_dialog": lambda s, **k: ["/x.m4a"]})())
    assert api.pick_audio() == "/x.m4a"


def test_pick_audio_cancel_returns_empty(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.webview, "active_window",
                        lambda: type("W", (), {"create_file_dialog": lambda s, **k: None})())
    assert api.pick_audio() == ""
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `python3 -m pytest tests/test_api.py -v`
Expected: 새 2개 FAIL ("module 'webview' ... " 또는 AttributeError pick_audio)

- [ ] **Step 3: api.py에 webview import + pick_audio 추가**

`app/api.py` 상단 import에 추가:
```python
import webview
```
`Api` 클래스에 메서드 추가:
```python
    def pick_audio(self) -> str:
        result = webview.active_window().create_file_dialog(
            webview.OPEN_DIALOG,
            file_types=("오디오 (*.m4a;*.mp3;*.wav;*.mp4)",),
        )
        if not result:
            return ""
        return result[0]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `python3 -m pytest tests/test_api.py -v`
Expected: 5 passed

- [ ] **Step 5: 커밋**

```bash
git add app/api.py tests/test_api.py
git commit -m "feat: add native audio file picker"
```

---

## Task 9: 진행 상태 전달 + 통합 스모크 테스트

**Files:**
- Modify: `app/api.py` (add_meeting 진행 콜백 → 프론트 이벤트)
- Modify: `app/web/app.js` (진행 이벤트 수신)

**Interfaces:**
- Produces: 전사 중 단계 메시지가 상단바 `#progress`에 표시.

- [ ] **Step 1: api.py add_meeting에 진행 전달**

`app/api.py`의 `add_meeting`을 수정 (전사 progress를 JS 이벤트로 전달):
```python
    def add_meeting(self, audio_path: str) -> dict:
        def report(stage: str) -> None:
            win = webview.active_window()
            if win:
                win.evaluate_js(f"window.dispatchEvent(new CustomEvent('progress', {{detail: {stage!r} }}))")
        transcript = transcribe_meeting(audio_path, self._hf_token, progress=report)
        report("요약 중…")
        summary = summarize(transcript)
        title = Path(audio_path).stem
        created = datetime.now(timezone.utc).isoformat()
        mid = self._store.create_meeting(title, created, audio_path, transcript)
        self._store.update_fields(mid, summary_md=summary)
        return self._store.get_meeting(mid)
```

> 기존 `add_meeting` 테스트는 `webview.active_window()`가 None을 반환하면 report가 조용히 넘어가므로 그대로 통과한다. 테스트 환경에선 `webview.active_window`가 None을 반환하도록 monkeypatch가 없으면 실제 None → 안전.

- [ ] **Step 2: app.js에 진행 이벤트 수신 추가**

`app/web/app.js`의 `bind()` 안에 추가:
```javascript
  window.addEventListener("progress", (e) => setProgress(e.detail));
```

- [ ] **Step 3: 백엔드 테스트 회귀 확인**

Run: `python3 -m pytest tests/ -v`
Expected: 모든 테스트 passed (10개 내외)

- [ ] **Step 4: 수동 통합 스모크 테스트**

Run: `HF_TOKEN=$HF_TOKEN python3 -m app.main`
수동 확인 체크리스트:
- `+ 새 회의` → 짧은 m4a 선택 → 진행 메시지 표시 → 끝나면 목록에 추가
- 회의 클릭 → 요약·메모·스크립트가 각 영역에 로드
- 요약/메모 수정 → 다른 회의 갔다 와도 유지(자동저장)
- 제목 수정(연필) → 목록 반영
- 사이드바/메모 토글 동작

- [ ] **Step 5: 커밋**

```bash
git add app/api.py app/web/app.js
git commit -m "feat: forward transcription progress to UI"
```

---

## Task 10: README 갱신 + (선택) DEVLOG

**Files:**
- Modify: `README.md`
- Create(선택): `docs/DEVLOG.md`

- [ ] **Step 1: README에 앱 실행 섹션 추가**

`README.md`에 "데스크톱 앱" 섹션 추가:
```markdown
## 데스크톱 앱 (GUI)

```bash
pip install -r requirements.txt
export HF_TOKEN=hf_xxx
python3 -m app.main
```

파일 업로드 → 전사·화자분리 → 로컬 AI 요약 → 마크다운 편집·메모·로컬 저장.
```

- [ ] **Step 2: (선택) DEVLOG.md 생성**

원하면 `docs/DEVLOG.md`에 날짜별 진행 일지 시작:
```markdown
# 개발 일지

## 2026-06-21
- 회의록 데스크톱 앱 MVP 구현 (pywebview + 기존 CLI 재사용)
- 전사·화자분리·로컬 요약·로컬 저장·4영역 글래스 UI
```

- [ ] **Step 3: 커밋 + push**

```bash
git add README.md docs/DEVLOG.md
git commit -m "docs: add desktop app usage and devlog"
git push
```

---

## 자체 검토 메모

- 스펙 커버리지: 레이아웃(T6/7), 전사·화자(T3), 요약(T4), 저장(T2), 메모·편집(T7), 새 회의 흐름(T8/9), 디자인(T6) 모두 작업 존재.
- 기존 `speaker_utils.align_segments` 반환은 `(start, speaker, text)` — T3에서 화자 집합 추출에 사용(일치).
- 요약 실패가 전체를 막지 않도록: `summarize` 실패 시 호출부에서 빈 요약 허용 (실행 시 try/except로 보강 가능; MVP는 정상 경로 우선).
