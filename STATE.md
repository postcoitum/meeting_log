# STATE.md — meeting_log (회의록 데스크톱 앱)
<!-- 이 파일은 프로젝트의 "기억"입니다.
     Claude Code가 세션 시작 때 읽고, 세션 끝에 갱신합니다.
     사람(포코)이 읽어도 프로젝트 현황이 한눈에 보여야 합니다. -->

## 1. 검증된 사실 (Verified facts)
<!-- 실제로 실행/확인해서 참이라고 확정된 것만 적는다. 추측 금지. -->
- **이 폴더가 유일한 진짜 프로젝트다.** 경로: `~/Desktop/go/meeting_log` (git remote: github.com/postcoitum/meeting_log). (2026-07-17 확인)
- **데이터 저장 위치**: `~/.meeting_log/` — `meetings.db`(SQLite) + `recordings/`(녹음 wav). 코드가 `Path.home()/".meeting_log"`로 참조함 (`app/main.py`의 `DB_PATH`, `app/api.py`의 recordings_dir). 절대 이 폴더를 지우거나 옮기지 말 것. (2026-07-17 확인)
- **형제 의존성**: `~/Desktop/go/Lightning-SimulWhisper` 가 프로젝트 옆에 있어야 함(README 기준, `../Lightning-SimulWhisper`). **이 저장소는 앱 코드에서 실제로 import되지 않는 폐기된 의존성**(초기 실시간 스트리밍 프로토타입 잔재, 4번 항목 참고) — `mlx_whisper`는 pip 패키지로 별도 설치됨. (2026-07-17 확인)
- **전사 엔진 = mlx-whisper(`large-v3-turbo`) 배치 방식.** Apple Silicon **Metal GPU** 가속 — **Apple Neural Engine(ANE)은 사용하지 않는다.** ANE를 쓰려면 whisper.cpp+CoreML 인코더나 macOS 26+ `SpeechAnalyzer` API로 전사 엔진 자체를 교체해야 하는 별도 규모 작업(정확도/속도 재검증 필요) — 아직 미착수. 10분 오디오 추론 ~25초. (DEVLOG 2026-06-22, ANE 조사 2026-07-17)
- **화자분리 = pyannote 4.x.** 결과가 dict가 아니라 `DiarizeOutput` 데이터클래스 → `.get()` 대신 속성으로 직접 접근해야 함. (DEVLOG 2026-06-22)
- **앱 구조**: pywebview + Python 단일 백엔드(`app/`) + 가벼운 웹 프론트(`app/web`). 로컬 SQLite 1파일 저장, 외부 전송 없음. 요약은 로컬 LLM(mlx-lm, `Qwen2.5-3B-Instruct-4bit`). (DEVLOG)
- **파일 처리는 큐 기반 순차 처리** (`app/api.py`의 `Api._queue`/`_worker_loop`). `add_meeting()`은 DB row를 `status='queued'`로 즉시 만들고 리턴 — pywebview RPC를 블록하지 않아 여러 파일을 연속으로 추가할 수 있다. 단일 백그라운드 워커 스레드가 순차 처리(진짜 동시 GPU 추론은 mlx-whisper/pyannote의 메모리 경합 위험 때문에 의도적으로 안 함). 진행 상황은 `job-progress` 브라우저 커스텀 이벤트(`{id, status, stage}` 객체, JSON 문자열 아님)로 프론트에 통지. 앱 재시작 시 `queued`/`processing` 상태로 남은 회의는 `_recover_pending()`이 자동으로 다시 큐에 넣는다. (2026-07-17)
- **요약이 짧아지는 원인 파악 완료 및 수정**: `app/summarizer.py`가 `MAX_INPUT_CHARS`(원래 6000자) 단위로 전사를 쪼개 조각마다 "5줄 이내"로 압축 후 다시 이어붙여 최종 요약을 만드는 구조라, 50분+ 회의처럼 긴 전사에서 손실이 두 번 누적됐다. `MAX_INPUT_CHARS=12000`, 조각당 "10줄 이내"로 완화, 최종 요약 `max_tokens=1536`(조각 요약은 700)로 조정. `DEFAULT_TEMPLATE`에 "논의 필요 사항" 섹션 추가(5번째 섹션). (2026-07-17) **→ 4차 세션에서 불충분 판정: 아래 "요약 품질 재진단" 참고 — 청킹 자체가 문제라 단일 패스로 가야 함.**
- **요약 품질 재진단 (4차 계획 세션, 실DB id=7·실모델로 재현·검증)**: (a) 청킹 경로가 12,000자 조각을 "10줄"로 66:1 압축 → 재압축해 20,559자 전사가 354자 요약으로 붕괴 — 길이 비례 실패의 원인. (b) 할루시네이션의 실체는 사실관계 왜곡(전사에 있는 단어로 없는 결정을 만듦). (c) 초창기(커밋 `1a55e31`)는 전사 전체 단일 패스였고 그래서 품질이 좋았다 — 20,559자 = 13,647토큰(실측)으로 32k 컨텍스트에 통째로 들어감. 청킹은 과잉 방어였음. (d) 단일 패스 비교 실험: Qwen2.5-3B는 후반부 통째 누락, **Qwen3-4B-Instruct-2507-4bit는 767자/69초로 전·후반 반영 + 왜곡 스팟체크 통과** → 포코 승인으로 모델 교체 확정. (e) **Metal OOM 실측**: 4B로 13.6k토큰 프리필 시 `[METAL] Insufficient Memory`로 프로세스 즉사(시스템 여유 78%에도 발생) — `mx.set_cache_limit(0)` 적용으로 해결 확인. 모델은 이 머신 HF 캐시에 다운로드 완료. 수정 계획: `~/.claude/plans/soft-churning-curry.md` (2026-07-17)
- **가져온 오디오는 복사되지 않는다**: `add_meeting()`이 사용자가 고른 파일 경로만 저장. 실DB id=3~7의 원본(`~/Downloads/*.m4a`)은 이미 삭제돼 길이 백필·재전사 불가(`duration_sec`이 0인 이유). 복구 불가 — 건드리지 말 것. 신규 파일부터 recordings/로 복사하는 수정이 위 계획 Part B. (2026-07-17)
- **요약 마크다운은 이제 카드 뷰로 렌더링됨**: `app/web/markdown.js`가 이 템플릿 전용 경량 파서(`##`→섹션, `- [ ]`→클릭 가능한 체크박스, `**볼드**`) 제공. 외부 라이브러리 없음(로컬 전용 원칙). `#summary-view`(렌더 뷰, 기본)와 `#summary`(raw textarea, "편집" 버튼으로 전환)가 공존. (2026-07-17)
- **DB 스키마에 `duration_sec`(REAL), `status`(TEXT, 기본 'done') 컬럼 추가됨** — `stats_json`과 같은 방식으로 `ALTER TABLE ... ADD COLUMN` try/except 마이그레이션. 구버전 DB도 열면 자동으로 컬럼이 추가된다. (2026-07-17)
- **테스트**: `tests/` 아래 pytest, 44개 전부 통과 확인(2026-07-17 3차 세션, 요약 버그 회귀 테스트 1개 추가). (`test_api.py`, `test_store.py`, `test_transcribe.py`, `test_summarizer.py`, `test_recorder.py`) `test_api.py`는 `add_meeting`이 큐잉 방식으로 바뀌면서 `api._queue.join()`으로 백그라운드 워커 완료를 기다린 뒤 결과를 재조회하는 패턴(`add_and_wait`/`stop_and_wait` 헬퍼)으로 갱신됨.
- **기존 녹음 길이 백필 구현 완료**: `app/api.py`의 `Api.__init__`이 `_recover_pending()` 뒤에 `_backfill_durations()`를 별도 데몬 스레드로 띄운다. `status='done'`이고 `duration_sec`이 0인 회의를 찾아 `audio_utils.to_wav_16k` + `soundfile.info()`로 길이를 역산해 채우고 임시 wav는 삭제한다(재전사 없음, 실패해도 조용히 넘어가고 다음 실행 때 재시도). (2026-07-17 3차 세션)
- **`Store`에 스레드 락 추가 — 백필 스레드 도입으로 실제 발견된 버그.** `Api`가 워커 스레드에 더해 백필 스레드까지 같은 sqlite3 커넥션(`check_same_thread=False`)에 즉시 동시 접근하자 `sqlite3.InterfaceError: bad parameter or other API misuse`가 재현됨(`pytest tests/test_api.py`로 확인, 백필 스레드 도입 전에는 안 나던 에러). 원인: sqlite3 커넥션 객체는 진짜 동시 호출에 안전하지 않음(내부 커서 상태 꼬임). `app/store.py`의 `Store`에 `threading.Lock()`을 추가해 모든 공개 메서드의 DB 접근을 직렬화해서 해결 — 5회 연속 재실행으로 재현 안 됨 확인. (2026-07-17 3차 세션)
- **요약 품질 개선 실행 완료 (5차 세션, `~/.claude/plans/soft-churning-curry.md` 실행).** Part A~D 전부 구현·검증:
  - `DEFAULT_SUMMARY_MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"`로 교체(`app/summarizer.py`).
  - `MAX_INPUT_CHARS = 40000`(기존 12000)로 상향 — 대부분의 회의가 단일 패스로 처리됨.
  - `_generate()`에 `mx.set_cache_limit(0)` 적용, `app/api.py._process_meeting()`에서 요약 시작 전 `mx.clear_cache()` 호출 — 4B 모델의 Metal OOM(`[METAL] Insufficient Memory`, 계획 세션에서 실측) 대책.
  - 청킹 경로(40k자 초과 시에만): `_split_at_timestamp_boundaries()`로 `\n[` 타임스탬프 줄 경계에서 자름(발화 중간 절단 방지). 조각 압축을 "10줄 이내" → "20~30줄 상세 정리"로 완화, 조각 `max_tokens=1200`. 최종 병합 프롬프트에 "구간별 정리, 중복만 합치고 줄이지 마라" 명시(`_MERGE_PROMPT_NOTE`).
  - 최종 요약 `max_tokens`를 입력 길이 비례로 산정: `min(3072, max(1024, len(text)//15))` — 상수 하나로 고정되던 문제 해결.
  - 메타 문장 필터 `_strip_meta_sentences()` 추가("이러한 내용을 요약하면…" 류 꼬리 문장 정규식 제거).
  - **실DB id=7(20,559자 전사)로 직접 실행 검증**: 696자/68.3초. 전반부(빈티지 반바지·신발 가격 문제)와 후반부(플리마켓·참가비 부담)가 모두 요약에 반영됨. 플리마켓 참가비는 "논의 필요 사항"(미결정)으로 정확히 분류돼 왜곡 스팟체크 통과(우리의 결정으로 둔갑하지 않음). 메타 문장 없음.
  - **가져온 오디오 복사 구현**(Part B): `app/api.py`에 `Api._ensure_in_recordings_dir()` 추가. `add_meeting()`에서 파일이 이미 `recordings_dir` 안이 아니면 `imported_{stamp}_{원본이름}`으로 복사(`shutil.copy2`), 복사 실패 시 원본 경로 폴백(앱 안 죽음). 이미 recordings_dir 안의 파일(녹음 기능 산출물)은 복사 생략.
  - `?mock=1` 브라우저 하니스로 UI 회귀 없음 확인(카드 뷰 렌더링·체크박스·화자 비율·스크립트 원본 모두 정상).
  - `python3 -m pytest` 49개 전부 통과(기존 44 + summarizer 신규 3개 + api 신규 2개). (2026-07-17 5차 세션)
- **회의 삭제 시 오디오 파일도 지울지 매번 물어보게 구현 완료** (6차 세션, `~/.claude/plans/attach-polymorphic-chipmunk.md` 실행). `Api.delete_meeting(meeting_id, delete_audio=False)`로 시그니처 변경, `Api._path_in_recordings_dir()`로 안전 체크(recordings_dir 바깥 경로는 절대 안 지움 — 옛 DB row의 스테일 경로 보호). 프론트(`app/web/app.js`)는 삭제 확인 후 "오디오 파일도 함께 삭제할까요?" 두 번째 `confirm()`을 항상 띄워 값을 넘김. `?mock=1` 하니스로 두 확인창을 거쳐 목록에서 정상 삭제되는 것을 스크린샷으로 확인. 테스트 3개 추가(recordings_dir 안/기본값/바깥 경로 케이스), `python3 -m pytest` 52개 전부 통과. (2026-07-17 6차 세션)
- **요약 새로고침 시 placeholder 텍스트가 그대로 나오는 버그 — 원인 확정 + 수정 완료.** 실제 사용자 DB(`~/.meeting_log/meetings.db`, id=5 "New Recording 7")의 커스텀 `summary_template`과 실제 전사로 `app.summarizer.summarize()`를 직접 3회 반복 호출해 재현: 로컬 3B 모델(`Qwen2.5-3B-Instruct-4bit`)이 프롬프트의 "형식:" 섹션에 있는 괄호 예시 문구(예: `- (논의된 주제와 구체적인 내용)`)를 채워야 할 자리가 아니라 그대로 이어 써도 되는 텍스트로 취급해 통째로 베껴 씀(3회 중 "결정 사항" 섹션은 3회 모두 예시 그대로 출력). 프롬프트에 "베끼지 마라"는 지시만 추가하는 건 불충분했음(재현 유지). **베낄 대상 문자열 자체를 지우는 방식**(`app/summarizer.py`의 `_strip_examples()` — `- (...)`/`- [ ] (...)`/단독 `(...)` 줄의 괄호 내용만 제거)으로 `summarize()`에서 생성 직전에 적용하니 같은 프롬프트 3회 재실행 모두 placeholder 없이 실제 내용 생성 확인. 저장된 템플릿 자체는 건드리지 않고 생성 시점에만 동적으로 적용되므로 기본/커스텀 양식 모두에 적용됨. 회귀 테스트 `tests/test_summarizer.py::test_summarize_strips_bracketed_examples_from_template` 추가. **주의**: 실DB의 회의 id=5는 아직 예전(버그) 요약이 그대로 저장돼 있음 — 앱에서 "요약 새로고침"을 눌러야 새 요약으로 갱신됨(사용자 확인 없이 실DB를 직접 고치지 않았음). (2026-07-17 3차 세션)

## 2. 일반 규칙 (다음에도 적용할 교훈)
<!-- 이 프로젝트를 넘어 비슷한 상황 전반에 통하는 규칙. -->
- Apple Silicon에서 파이썬 라이브러리 에러가 나면 arm64/x86_64 아키텍처 충돌부터 의심할 것. (`.app` 번들 런처가 arm64 강제 실행하는 이유)
- 라이브러리 메이저 버전이 오르면 반환 타입(dict → dataclass 등)이 바뀔 수 있으니 릴리스 노트를 먼저 볼 것. (pyannote 4.x 사례)

## 3. 미해결 실패 (Open failures) ★실패 사유 필수
<!-- 아직 원인을 못 밝힌 문제. 다음 세션의 출발점. -->
- **[해결됨] frameless 신호등 버튼이 안 보였던 문제.** 원인: pywebview의 macOS 백엔드(`webview/platforms/cocoa.py` 698-710번 줄 근처)가 `frameless=True`일 때 `standardWindowButton_(...).setHidden_(True)`로 닫기/최소화/최대화 버튼 3개를 **코드에서 명시적으로 숨긴다.** 여백을 아무리 줘도 애초에 hidden이라 안 보이는 게 정상 동작이었음 — pywebview는 Electron의 `titleBarStyle: hiddenInset`(타이틀바 투명 + 버튼 유지) 같은 옵션을 제공하지 않는다. **조치**: `app/main.py`에서 `frameless=True`/`easy_drag=True` 제거하고 대신 창 제목을 빈 문자열(`""`)로 바꿔 네이티브 창(신호등 정상 동작)은 유지하면서 "회의록" 텍스트만 없앰. `.topbar`의 `padding-left: 80px`도 되돌림(더 이상 안 겹치므로 불필요). **포코가 6차 세션에서 `python3 -m app.main`을 프로젝트 폴더 안에서 직접 실행해 GUI 정상 확인함**(이전 세션 실패는 다른 디렉토리에서 실행해 `ModuleNotFoundError: No module named 'app'`가 난 것 — 코드 문제 아님, 반드시 `cd ~/Desktop/go/meeting_log` 후 실행해야 함).
- **[해결됨] 기존 녹음 파일의 길이(duration)가 목록에 안 보임.** → 위 "검증된 사실"의 백필 항목 참고. `app/api.py`에 시작 시 백그라운드로 도는 `_backfill_durations()` 추가 완료.
- **[해결됨] 기존 녹음 파일에서 "요약 새로고침" 시 요약이 비거나 템플릿 placeholder 텍스트 그대로 나옴.** → 위 "검증된 사실"의 요약 버그 항목 참고. 원인(3B 모델의 괄호 예시 echo) 확정 + `_strip_examples()`로 수정 + 회귀 테스트 추가. 실DB의 기존 요약은 "요약 새로고침"을 눌러야 갱신됨.

## 4. 하지 말 것 (Anti-patterns)
<!-- 실제로 사고가 났던 방식. 반복 금지 목록. -->
- **실시간 스트리밍 전사(Lightning-SimulWhisper)로 되돌리지 말 것.** 무음 구간에서 같은 말을 무한 반복(`뭐야? 뭐야? …`)하고 느렸음. 그래서 배치 mlx-whisper로 교체함. (DEVLOG 2026-06-22)
- `~/.meeting_log/`(실데이터)와 git 히스토리를 임의로 건드리지 말 것.

## 5. 마지막 세션 기록 (Resume pointer)
<!-- 다음 세션이 "이어서" 시작할 수 있게 하는 부분. -->
- 날짜: 2026-07-17 (2차 세션 — "Alt 수준으로 끌어올리기")
- 이번에 한 것 (계획 파일: `~/.claude/plans/meeting-log-new-hidden-mango.md`):
  1. **Lightning-SimulWhisper 중복 정리**: `~/Lightning-SimulWhisper`(홈)의 커밋 안 된 패딩 버그 수정을 `~/Desktop/go/Lightning-SimulWhisper`(정식 경로)에 반영 후, 중복이던 홈 폴더 삭제(포코 확인 받고 진행).
  2. **녹음 길이 표시**: `duration_sec` DB 컬럼 추가, 목록/상세뷰에 `mm:ss` 표시.
  3. **여러 파일 큐 처리**: `Api`에 `queue.Queue` + 워커 스레드 도입. `add_meeting()`이 즉시 리턴하도록 변경 — 파일을 연속으로 추가할 수 있게 됨. 목록 각 항목에 대기중/처리중(%)/완료/실패 상태 배지.
  4. **요약 품질 개선**: 청크 크기·압축 강도·max_tokens 조정으로 긴 회의 요약 손실 완화, "논의 필요 사항" 섹션 추가.
  5. **요약 마크다운 렌더링**: `app/web/markdown.js` 신규 — 볼드/체크박스(클릭 토글)/섹션 카드 뷰. 편집 모드 토글로 raw 마크다운 직접 수정 기능 유지.
  6. **정렬 기능**: 사이드바에 최신순/오래된순/제목순/길이순 드롭다운 추가.
  7. **창 디자인**: 처음엔 `frameless=True`/`easy_drag=True`로 갔다가 — 포코가 실제 앱에서 신호등 버튼이 아예 안 보인다고 확인해줘서 원인 조사(위 3번 "미해결 실패" 참고) 후 **되돌림**. 현재는 네이티브 창 그대로 두고 타이틀만 빈 문자열로 바꿔 "회의록" 텍스트만 제거한 상태.
  8. 백엔드 테스트(`test_api.py`, `test_store.py`, `test_summarizer.py`) 새 큐/스키마/프롬프트 계약에 맞춰 갱신, 전체 43개 통과 확인. `?mock=1` 브라우저 하니스로 큐잉·길이 표시·마크다운 렌더링(체크박스 토글 포함) 실제 스크린샷으로 확인함.
- 포코가 실사용 중 보고한 버그 (2026-07-17, 같은 세션 중간에):
  1. frameless 신호등 버튼 안 보임 → 원인 확정 후 위 7번처럼 되돌림 (해결).
  2. 기존 녹음 파일 길이 표시 안 됨 → 원인 파악됨(마이그레이션이 기존 값은 0으로만 채움), **백필 로직 아직 미구현** — 위 3번 참고.
  3. 기존 녹음 하나에서 "요약 새로고침" 했더니 요약이 커스텀 템플릿 placeholder 그대로 나옴 → **원인 미확정, 손 안 댐** — 위 3번 재현 방법 참고.
  포코가 "위 두 개(1,2) 먼저 해결해줘"라고 해서 1번은 끝냈고, 2번(길이 백필)과 3번(요약 버그)은 착수 전에 "내일 이어서 하고 싶다"는 요청으로 세션을 멈춤.
- 이번에 의도적으로 제외한 것(범위 밖):
  - **폴더 기능**: 정렬/검색만 추가, 폴더 트리·드래그앤드롭은 미착수.
  - **Apple Neural Engine 활용**: 조사만 하고 구현 안 함 (위 "검증된 사실" 참고 — 엔진 교체가 필요한 별도 규모 작업).
- **3차 세션 (2026-07-17, 이어서 진행)에서 한 것**:
  1. **기존 녹음 파일 길이 백필** — `app/api.py`에 `_backfill_durations()` 추가(백그라운드 스레드, `to_wav_16k`+`soundfile.info`로 역산). 구현 중 백필 스레드가 워커 스레드와 동시에 sqlite3 커넥션을 건드리며 `test_api.py`에서 `InterfaceError` 재현 → `app/store.py`의 `Store`에 `threading.Lock()` 추가해 해결(5회 연속 재실행 확인).
  2. **요약 새로고침 placeholder 버그 원인 확정 + 수정** — 실DB(id=5)의 실제 커스텀 템플릿·전사로 `summarize()`를 반복 재현해 로컬 3B 모델이 "형식:" 섹션 괄호 예시를 그대로 베끼는 실패 모드임을 확정. "베끼지 마라" 지시 추가만으론 불충분함을 확인 후, 괄호 예시 문구 자체를 생성 시점에 제거하는 `_strip_examples()`로 수정(저장된 템플릿은 안 건드림). 3회 반복 재현으로 수정 확인 + 회귀 테스트 추가.
  3. 전체 테스트 44개 통과 확인(`python3 -m pytest`).
- **4차 세션 (2026-07-17, 계획 전용 세션 — 코드 수정 없음)**: 포코의 "요약이 분량에 비례하지 않고 할루시네이션 있다" 보고를 실DB·실모델로 재현·진단(위 "요약 품질 재진단" 참고). Qwen3-4B-2507 다운로드 + 비교 실험 + OOM 해결책까지 검증 완료. **실행 계획 `~/.claude/plans/soft-churning-curry.md` 승인됨 — 다음 세션(다른 모델)이 이 계획대로 실행할 것.** 범위: Part A 요약 개선(모델 교체·단일 패스·OOM 대책), Part B 가져온 오디오 복사, Part C 커밋 정리, Part D 검증. 폴더 기능(~1세션, 10-15만 토큰)과 ANE 교체(2-4세션, 30-60만 토큰, 보류 권고)는 규모 산정만 하고 제외 — 포코 결정 대기.
- **5차 세션 (2026-07-17, `~/.claude/plans/soft-churning-curry.md` 실행)**: Part A(요약 품질: 모델 교체·단일 패스 확대·OOM 대책·비례 길이·메타 문장 필터), Part B(가져온 오디오 recordings_dir 복사) 구현 완료. Part D 검증: pytest 49개 통과, 실DB id=7로 `summarize()` 직접 실행해 품질 확인(전·후반부 반영, 왜곡 없음), `?mock=1` 브라우저 하니스로 UI 회귀 없음 확인. 자세한 내용은 위 "검증된 사실"의 "요약 품질 개선 실행 완료" 항목 참고. Part C(커밋 정리)는 이 세션에서 이어서 진행 — 논리 단위로 커밋하되 push/PR은 포코 확인 후.
- **6차 세션 (2026-07-17, `~/.claude/plans/attach-polymorphic-chipmunk.md` 실행)**: 포코가 프로젝트 폴더 안에서 `python3 -m app.main` 직접 실행해 GUI(신호등·타이틀·길이 백필·오디오 복사 등) 정상 확인. 회의 삭제 시 오디오 파일 삭제 여부를 매번 물어보는 기능 구현(위 "검증된 사실" 참고). **push + PR 진행**: `chore/project-cleanup-state-md` 브랜치 4개 커밋(5bbeaed, e3233f8, d7dcf6c, d9d97b7)을 push. **PR #1은 이미 2026-07-16에 머지 완료된 상태였음**(이번 세션 전에 확인) — 그래서 같은 브랜치로 **새 PR #2**를 생성함(https://github.com/postcoitum/meeting_log/pull/2). PR #2 머지는 포코 결정.
- 다음에 할 것:
  1. GitHub에서 **PR #2 머지 여부 결정**(포코).
  2. 폴더 기능/ANE 엔진 교체는 포코가 다음에 우선순위 정할 것.
- **커밋 상태**: 3~6차 세션 변경 전부 논리 단위로 커밋 완료 + push 완료. **PR #2가 머지 대기 중.**
