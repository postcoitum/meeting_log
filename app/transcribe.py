"""기존 CLI 로직을 앱에서 호출할 수 있게 감싼 전사 래퍼."""
from __future__ import annotations

import time
from pathlib import Path
from typing import Callable

from audio_utils import to_wav_16k
from meeting_recorder import transcribe_audio, diarize_audio
from speaker_utils import (
    align_segments, map_speakers, merge_consecutive, format_transcript,
)

DEFAULT_MODEL = "mlx-community/whisper-large-v3-turbo"

# 첫 실행용 기본 처리율 (오디오 1초당 처리 초). 실행 후 실측값으로 대체된다.
DEFAULT_RATES = {"transcribe": 0.06, "diarize": 0.55}


def _audio_duration(wav_path) -> float:
    """오디오 길이(초). 실패 시 0(예상 표시 생략)."""
    try:
        import soundfile as sf
        return float(sf.info(str(wav_path)).duration)
    except Exception:
        return 0.0


def _fmt_eta(seconds: float) -> str:
    if seconds < 90:
        return "1~2분"
    return f"약 {round(seconds / 60)}분"


def _speaker_stats(
    diar_segs: list[tuple[float, float, str]],
    named: list[tuple[float, str, str]],
    name_map: dict[str, str],
) -> dict:
    """화자별 점유율(%)과 주요 발언(가장 긴 발언 2개)을 계산."""
    durations: dict[str, float] = {}
    for start, end, sid in diar_segs:
        name = name_map.get(sid, sid)
        durations[name] = durations.get(name, 0.0) + max(0.0, end - start)
    total = sum(durations.values()) or 1.0

    quotes: dict[str, list[str]] = {}
    for _, name, text in named:
        quotes.setdefault(name, []).append(text.strip())
    for name in quotes:
        quotes[name] = [
            q[:90] for q in sorted(quotes[name], key=len, reverse=True)[:2]
        ]

    speakers = []
    for name in sorted(durations):
        speakers.append({
            "name": name,
            "share": round(durations[name] / total * 100),
            "quotes": quotes.get(name, []),
        })
    return {"speakers": speakers}


def transcribe_meeting(
    audio_path: str,
    hf_token: str,
    model_repo: str = DEFAULT_MODEL,
    progress: Callable[[str], None] | None = None,
    num_speakers: int | None = None,
    rates: dict | None = None,
    timings_out: dict | None = None,
) -> tuple[str, dict]:
    """전사 텍스트와 화자 통계를 함께 반환한다.

    num_speakers=1이면 화자 분리(pyannote)를 통째로 건너뛴다(혼자 녹음 —
    가장 빠름). 그 외에는 전사(mlx/GPU)와 화자 분리(torch/CPU)를 서로 다른
    장치에서 돌기 때문에 병렬로 실행해 벽시계 시간을 줄인다.
    rates는 단계별 처리율(초/오디오초), timings_out은 호출자가 넘긴 dict에
    실측 시간(audio_sec, transcribe_sec, diarize_sec)을 채워 돌려주는 out-param.
    """
    def report(stage: str) -> None:
        if progress:
            progress(stage)

    report("오디오 변환 중…")
    wav = to_wav_16k(Path(audio_path))
    r = {**DEFAULT_RATES, **(rates or {})}
    audio_sec = _audio_duration(wav)
    if timings_out is not None:
        timings_out["audio_sec"] = audio_sec
    try:
        if num_speakers == 1:
            eta = f" (예상 {_fmt_eta(audio_sec * r['transcribe'])})" if audio_sec else ""
            report(f"전사 중… 화자 분리 건너뜀{eta}")
            t0 = time.monotonic()
            whisper_segs = transcribe_audio(wav, "ko", model_repo)
            if timings_out is not None:
                timings_out["transcribe_sec"] = time.monotonic() - t0
            end = whisper_segs[-1][1] if whisper_segs else 0.0
            diar_segs = [(0.0, end, "SPEAKER_00")]
        else:
            est = max(audio_sec * r["transcribe"], audio_sec * r["diarize"])
            eta = f" (예상 {_fmt_eta(est)})" if audio_sec else ""
            report(f"전사 · 화자 분리 동시 진행 중…{eta}")
            from concurrent.futures import ThreadPoolExecutor

            def _timed(key, fn, *a, **k):
                t0 = time.monotonic()
                try:
                    return fn(*a, **k)
                finally:
                    if timings_out is not None:
                        timings_out[key] = time.monotonic() - t0

            with ThreadPoolExecutor(max_workers=2) as pool:
                f_whisper = pool.submit(_timed, "transcribe_sec", transcribe_audio, wav, "ko", model_repo)
                f_diar = pool.submit(
                    _timed, "diarize_sec", diarize_audio, wav, hf_token, num_speakers=num_speakers
                )
                whisper_segs = f_whisper.result()
                diar_segs = f_diar.result()

        aligned = align_segments(whisper_segs, diar_segs)
        speakers = sorted({s for _, s, _ in aligned})
        name_map = {sid: f"화자 {i + 1}" for i, sid in enumerate(speakers)}
        named = map_speakers(aligned, name_map)
        merged = merge_consecutive(named)
        transcript = format_transcript(merged, with_timestamps=True)
        stats = _speaker_stats(diar_segs, named, name_map)
        return transcript, stats
    finally:
        if wav != Path(audio_path):
            wav.unlink(missing_ok=True)
