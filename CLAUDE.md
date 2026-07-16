# CLAUDE.md — meeting_log

로컬 전용 **회의록 데스크톱 앱**. 녹음 → 전사(mlx-whisper) → 화자분리(pyannote) → 로컬 LLM 요약.
외부 전송 없음, 데이터는 로컬 SQLite 1파일.

## 작업 규칙 (반드시 지킬 것)

1. **세션 시작**: 작업을 시작하기 전에 반드시 `STATE.md`를 먼저 읽어라.
   이미 검증된 사실은 다시 확인하지 말고 그대로 믿고 사용해라.

2. **세션 종료**: 작업을 마치기 전에 반드시 `STATE.md`를 갱신해라.
   갱신할 내용: 이번에 새로 확인된 사실 / 내린 결정 / 실패한 것과 그 원인 / 다음에 할 일.

3. **실패 기록**: 에러나 실패가 생기면 그냥 넘어가지 말고,
   `STATE.md`의 "미해결 실패" 항목에 (a) 무엇이 실패했는지 (b) 에러 메시지 원문
   (c) 원인 추정 (d) 재현 방법을 적어라. 원인을 확정하면 "검증된 사실"로 옮겨라.

4. **거짓 완료 금지**: 테스트를 통과하지 않았거나 실제로 실행해보지 않은 것을
   "완료"라고 STATE.md에 적지 마라.

## 이 프로젝트 (핵심 사실)

- **여기가 유일한 진짜 프로젝트다.** 경로 `~/Desktop/go/meeting_log` (remote: github.com/postcoitum/meeting_log). 홈이나 다른 곳에 복사본을 만들지 마라.
- **데이터 폴더 `~/.meeting_log/`** (`meetings.db` + `recordings/`)는 앱이 실제로 쓰는 실데이터다. 절대 지우거나 옮기지 마라. 코드가 `Path.home()/".meeting_log"`로 참조.
- **형제 의존성**: `~/Desktop/go/Lightning-SimulWhisper` 가 프로젝트 옆에 있어야 함.
- 상세한 검증된 사실·안티패턴·이전 세션 기록은 `STATE.md` 참고. 개발 서사는 `docs/DEVLOG.md`.

## 구조 / 실행 / 테스트

- **구조**: `app/`(pywebview 백엔드: `main.py`·`api.py`·`store.py`·`transcribe.py`·`summarizer.py` + `web/` 프론트) · 루트 CLI `meeting_recorder.py` · `tests/`(pytest) · `scripts/`(빌드) · `docs/`.
- **앱 실행**: `export HF_TOKEN=hf_xxx && python3 -m app.main`
- **UI만 개발**: `python3 -m http.server 8765 --directory app/web` → `http://localhost:8765/index.html?mock=1` (가짜 API)
- **CLI 전사**: `python3 meeting_recorder.py --audio meeting.m4a --hf-token $HF_TOKEN` (화자 수 알면 `--speakers 2`가 가장 정확)
- **macOS .app 빌드**: `bash scripts/build_app.sh` → `/Applications/회의록.app` (더블클릭 실행은 셸 환경변수를 못 읽으니 HF 토큰은 앱 설정 화면에 저장)
- **테스트**: `python3 -m pytest`

## 사용자(포코) 작업 스타일 — 참고

- **한국어로 소통한다.** 답변도 한국어로.
- **비용 의식적이다.** 단순·기계적 작업(파일 정리, 반복 수정 등)은 Haiku 같은 저렴한 모델로 돌리려 한다. 무거운 추론이 필요 없는 일에 Opus를 낭비하지 마라.
- **깔끔한 정리를 중시하고 중복·군더더기 파일을 싫어한다.** 불필요한 새 파일을 함부로 만들지 말고, 만들어야 하면 먼저 알려라.
- **정직한 보고를 원한다.** 안 된 건 안 됐다고, 검증 안 한 건 안 했다고 말해라. 파괴적 작업(삭제/덮어쓰기) 전에는 확인하고 진행한다.
