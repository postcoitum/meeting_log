# Meeting Recorder

> CLI tool that transcribes meetings and labels who said what — built for Apple Silicon, optimised for Korean.

화자별로 구분된 한국어/영어 회의 자동 전사 CLI 도구입니다.
오디오 파일을 받아 **누가 무슨 말을 했는지**를 텍스트로 정리해 줍니다.

**파이프라인:** mlx-whisper(전사) → pyannote.audio(화자 분리) → 타임스탬프 정렬 → 화자별 transcript

```
예시) 홍길동: 일단은 내가 현재 새롭게 만들어봤는데
김영희: 이걸 어떻게 생각하는지 궁금해
```

---

## 특징

- **빠름** — Apple Silicon Metal 가속(mlx-whisper)으로 10분 오디오를 수십 초에 전사
- **정확함** — 기본 모델 `large-v3-turbo`로 한국어 고유명사까지 인식, 반복(hallucination) 억제
- **유연한 화자 처리** — 화자 수를 자동 감지하거나, 정확히 지정하거나, 상한만 둘 수 있음
- **완전 비대화형** — 이름을 안 줘도 `화자 1`, `화자 2`로 라벨링해 끝까지 자동 실행

---

## 기술 스택

| 구성 | 사용 |
|------|------|
| 전사(STT) | [mlx-whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) — Apple Silicon Metal 가속 Whisper |
| 모델 | `mlx-community/whisper-large-v3-turbo` (기본), tiny~large-v3 선택 가능 |
| 화자 분리 | [pyannote.audio](https://github.com/pyannote/pyannote-audio) `speaker-diarization-3.0` |
| 오디오 변환 | ffmpeg (16 kHz mono WAV) |

> Apple Silicon(M1 이상) macOS에 최적화돼 있습니다.

---

## 설치

```bash
# 1) Python 의존성
pip install -r requirements.txt

# 2) ffmpeg (pip 패키지가 아님 — 별도 설치)
brew install ffmpeg          # macOS
# sudo apt install ffmpeg    # Ubuntu/Debian

# 3) HuggingFace 토큰 설정 (화자 분리 모델 접근에 필요 — 아래 Troubleshooting e 참고)
export HF_TOKEN=hf_xxxxxxxxxxxxxxxxxxxx
```

전사 모델은 첫 실행 시 `mlx-community`에서 자동 다운로드됩니다(별도 설치 불필요).

---

## 사용법

### 기본 (화자 수 자동 감지, 이름 자동 라벨)

```bash
python3 meeting_recorder.py \
  --audio meeting.m4a \
  --language ko \
  --output meeting_transcript.txt \
  --hf-token $HF_TOKEN
```

### 화자 이름 지정

```bash
python3 meeting_recorder.py \
  --audio meeting.m4a \
  --speaker1 "홍길동" \
  --speaker2 "김영희" \
  --language ko \
  --hf-token $HF_TOKEN
```

### 타임스탬프 포함

```bash
python3 meeting_recorder.py --audio meeting.m4a --timestamps --hf-token $HF_TOKEN
```

### 영어 회의

```bash
python3 meeting_recorder.py \
  --audio standup.wav \
  --speaker1 "Alice" \
  --speaker2 "Bob" \
  --language en \
  --hf-token $HF_TOKEN
```

---

## CLI 옵션

| 옵션 | 설명 | 기본값 |
|------|------|--------|
| `--audio` | 입력 오디오 (MP3/WAV/M4A 등) **(필수)** | — |
| `--language` | `ko` / `en` / `auto` | `ko` |
| `--model` | `tiny`·`base`·`small`·`medium`·`large-v3`·`large-v3-turbo` | `large-v3-turbo` |
| `--model-repo` | mlx-community HF repo 또는 로컬 경로 직접 지정 | 없음 |
| `--speakers` | 정확한 화자 수, 또는 `auto`로 자동 감지 | `auto` |
| `--max-speakers` | 자동 감지 시 화자 수 상한 (예: `2` → 3명으로 안 쪼갬) | 없음 |
| `--speaker1`, `--speaker2` | 화자 이름 (미지정 시 `화자 1`, `화자 2`) | 없음 |
| `--output` | 출력 파일 경로 | `<오디오명>_transcript.txt` |
| `--timestamps` | 각 줄 앞에 `[HH:MM:SS]` 표시 | 꺼짐 |
| `--hf-token` | HuggingFace 토큰 (`$HF_TOKEN`로도 가능) | — |

### 화자 수 처리 예시

```bash
# 1명짜리 녹음 → 자동 감지로 충분
python3 meeting_recorder.py --audio solo.m4a --hf-token $HF_TOKEN

# 정확히 2명으로 강제
python3 meeting_recorder.py --audio meeting.m4a --speakers 2 --hf-token $HF_TOKEN

# 보통 1~2명 회의 → 상한만 지정해 안정적으로
python3 meeting_recorder.py --audio meeting.m4a --max-speakers 2 --hf-token $HF_TOKEN
```

---

## 출력 형식

**기본 (`--timestamps` 없음):**
```
홍길동: 안녕하세요, 회의 시작하겠습니다

김영희: 네, 좋습니다
```

**`--timestamps` 사용:**
```
[0:00:01] 홍길동: 안녕하세요, 회의 시작하겠습니다

[0:00:08] 김영희: 네, 좋습니다
```

---

## 동작 원리

1. **변환** — ffmpeg로 입력을 16 kHz mono WAV로 변환
2. **전사** — mlx-whisper가 파일 전체를 배치 처리해 `(start, end, text)` 세그먼트 생성
3. **화자 분리** — pyannote `speaker-diarization-3.0`이 화자 전환 구간 탐지
4. **정렬** — 각 전사 세그먼트를 시간상 가장 많이 겹치는 화자에 배정
5. **병합** — 같은 화자의 연속 발화를 하나로 합침
6. **출력** — 화자별 transcript를 파일로 저장

---

## Troubleshooting

### a. `IndexError: pop from empty list` (구버전 SimulWhisper)

초기 버전은 실시간 스트리밍용 **Lightning-SimulWhisper**를 1초 단위로 호출했는데,
어텐션 프레임 수가 토큰 수보다 적을 때 이 에러가 났고, 무음 구간에서 같은 말이
무한 반복(`뭐야? 뭐야? …`)되는 문제도 있었습니다.
→ **전사 엔진을 mlx-whisper 배치 방식으로 교체**하면서 해결됐습니다.
현재 코드에는 SimulWhisper 의존성이 없습니다.

### b. `AttributeError: 'DiarizeOutput' object has no attribute 'get'`

pyannote.audio **4.x**부터 파이프라인 반환값이 dict가 아니라 `DiarizeOutput`
데이터클래스로 바뀌었습니다. `.get("diarization")`은 더 이상 동작하지 않습니다.
→ 버전에 무관하게 처리합니다:

```python
result = pipeline(str(wav_path), **diar_kwargs)
if hasattr(result, "itertracks"):          # 3.x: Annotation
    annotation = result
else:                                       # 4.x: DiarizeOutput
    annotation = getattr(result, "speaker_diarization", result)
```

### c. `use_auth_token` deprecated

pyannote 최신 버전은 `use_auth_token=` 대신 `token=` 인자를 씁니다.
→ `Pipeline.from_pretrained("pyannote/speaker-diarization-3.0", token=hf_token)`.

### d. `ffmpeg not found`

ffmpeg는 pip 패키지가 아니라 시스템 도구입니다.

```bash
brew install ffmpeg          # macOS
sudo apt install ffmpeg      # Ubuntu/Debian
```

### e. HF_TOKEN 설정 / 모델 접근 (`401 Unauthorized`, `GatedRepoError`)

pyannote 화자 분리 모델은 **gated** 라서 토큰과 사용 조건 수락이 모두 필요합니다.

1. https://huggingface.co/settings/tokens 에서 read 토큰 생성
2. 아래 두 모델 페이지에서 사용 조건 **Accept**:
   - https://huggingface.co/pyannote/speaker-diarization-3.0
   - https://huggingface.co/pyannote/segmentation-3.0
3. 토큰 전달:
   ```bash
   export HF_TOKEN=hf_xxxxxxxxxxxx
   # 또는 실행 시 --hf-token hf_xxxxxxxxxxxx
   ```

### f. `scikit-learn` / `coremltools` 버전 경고

```
scikit-learn version 1.9.0 is not supported ...
Torch version 2.x.x has not been tested with coremltools ...
```

의존성 라이브러리가 띄우는 **무해한 경고**입니다. 전사/화자 분리 동작에는
영향이 없으니 무시해도 됩니다. (빨간 Traceback이 아닌 한 정상)

### 화자가 1명으로만 잡힐 때

닮은 목소리거나 녹음 품질이 낮으면 자동 감지가 2명을 1명으로 합칠 수 있습니다.
화자 수를 알고 있다면 `--speakers 2`처럼 명시하는 것이 가장 정확합니다.

---

## 파일 구성

| 파일 | 역할 |
|------|------|
| `meeting_recorder.py` | 메인 CLI (전사 + 화자 분리 + 정렬) |
| `audio_utils.py` | ffmpeg로 16 kHz mono WAV 변환 |
| `speaker_utils.py` | 타임스탬프 정렬·화자 이름 매핑·transcript 포맷 |
| `requirements.txt` | Python 의존성 |
