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
        speakers = sorted({s for _, s, _ in aligned})
        name_map = {sid: f"화자 {i + 1}" for i, sid in enumerate(speakers)}
        named = map_speakers(aligned, name_map)
        merged = merge_consecutive(named)
        return format_transcript(merged, with_timestamps=True)
    finally:
        if wav != Path(audio_path):
            wav.unlink(missing_ok=True)
