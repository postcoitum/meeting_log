# STATE.md — meeting_log (회의록 데스크톱 앱)
<!-- 이 파일은 프로젝트의 "기억"입니다.
     Claude Code가 세션 시작 때 읽고, 세션 끝에 갱신합니다.
     사람(포코)이 읽어도 프로젝트 현황이 한눈에 보여야 합니다. -->

## 1. 검증된 사실 (Verified facts)
<!-- 실제로 실행/확인해서 참이라고 확정된 것만 적는다. 추측 금지. -->
- **이 폴더가 유일한 진짜 프로젝트다.** 경로: `~/Desktop/go/meeting_log` (git remote: github.com/postcoitum/meeting_log). (2026-07-17 확인)
- **데이터 저장 위치**: `~/.meeting_log/` — `meetings.db`(SQLite) + `recordings/`(녹음 wav). 코드가 `Path.home()/".meeting_log"`로 참조함 (`app/main.py`의 `DB_PATH`, `app/api.py`의 recordings_dir). 절대 이 폴더를 지우거나 옮기지 말 것. (2026-07-17 확인)
- **형제 의존성**: `~/Desktop/go/Lightning-SimulWhisper` 가 프로젝트 옆에 있어야 함(README 기준, `../Lightning-SimulWhisper`). (2026-07-17 확인)
- **전사 엔진 = mlx-whisper(`large-v3-turbo`) 배치 방식.** Apple Silicon Metal 가속. 10분 오디오 추론 ~25초. (DEVLOG 2026-06-22)
- **화자분리 = pyannote 4.x.** 결과가 dict가 아니라 `DiarizeOutput` 데이터클래스 → `.get()` 대신 속성으로 직접 접근해야 함. (DEVLOG 2026-06-22)
- **앱 구조**: pywebview + Python 단일 백엔드(`app/`) + 가벼운 웹 프론트(`app/web`). 로컬 SQLite 1파일 저장, 외부 전송 없음. 요약은 로컬 LLM(mlx-lm, `Qwen2.5-3B-Instruct-4bit`). (DEVLOG)
- **테스트**: `tests/` 아래 pytest. (`test_api.py`, `test_store.py`, `test_transcribe.py`, `test_summarizer.py`, `test_recorder.py`)

## 2. 일반 규칙 (다음에도 적용할 교훈)
<!-- 이 프로젝트를 넘어 비슷한 상황 전반에 통하는 규칙. -->
- Apple Silicon에서 파이썬 라이브러리 에러가 나면 arm64/x86_64 아키텍처 충돌부터 의심할 것. (`.app` 번들 런처가 arm64 강제 실행하는 이유)
- 라이브러리 메이저 버전이 오르면 반환 타입(dict → dataclass 등)이 바뀔 수 있으니 릴리스 노트를 먼저 볼 것. (pyannote 4.x 사례)

## 3. 미해결 실패 (Open failures) ★실패 사유 필수
<!-- 아직 원인을 못 밝힌 문제. 다음 세션의 출발점. -->
- (없음)

## 4. 하지 말 것 (Anti-patterns)
<!-- 실제로 사고가 났던 방식. 반복 금지 목록. -->
- **실시간 스트리밍 전사(Lightning-SimulWhisper)로 되돌리지 말 것.** 무음 구간에서 같은 말을 무한 반복(`뭐야? 뭐야? …`)하고 느렸음. 그래서 배치 mlx-whisper로 교체함. (DEVLOG 2026-06-22)
- `~/.meeting_log/`(실데이터)와 git 히스토리를 임의로 건드리지 말 것.

## 5. 마지막 세션 기록 (Resume pointer)
<!-- 다음 세션이 "이어서" 시작할 수 있게 하는 부분. -->
- 날짜: 2026-07-17
- 이번에 한 것:
  1. 흩어진 폴더 정리. 홈의 옛 프로토타입 `~/meeting_log_new`(6월 flat 스크립트, 모든 파일이 이 프로젝트에 더 발전된 버전으로 존재함을 검증)와 빈 폴더 `~/"meeting log"`를 영구 삭제. 본 프로젝트 내부 잡파일(.DS_Store, __pycache__, .pytest_cache, voice1_transcript.txt) 제거, `.gitignore`에 `.pytest_cache/` 추가. `~/.meeting_log`(실데이터)와 git 히스토리는 손대지 않음.
  2. STATE.md/CLAUDE.md 신설 (기존 CLAUDE.md가 프로젝트·전역 어디에도 없어서 새로 만듦 — "덧붙이기"가 아닌 "신설"이었음을 포코에게 명시적으로 알림).
  3. CLAUDE.md를 최소 추가지침본에서 확장: 프로젝트 개요, 핵심 사실(진짜 경로/데이터 폴더/형제 의존성), 구조·실행·테스트 명령(README 기준 검증), 포코 작업 스타일(한국어 소통·비용 의식적 모델 선택·깔끔한 정리 선호·정직한 보고 요구) 추가.
  4. 브랜치 `chore/project-cleanup-state-md`로 커밋 2건 푸시 후 PR #1 오픈 (https://github.com/postcoitum/meeting_log/pull/1). 소스/동작 변경 없음, 문서+ignore만.
- 다음에 할 것: PR #1 머지 여부는 포코 결정. 머지 후 로컬을 `main`으로 돌아와 브랜치 정리(삭제) 필요.
