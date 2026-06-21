"""
Speaker-separated meeting transcription.

Uses mlx-whisper (Apple-Silicon Metal acceleration) for fast, accurate batch
transcription and pyannote.audio for 2-speaker diarization, then aligns the two
outputs by timestamp overlap.

Usage:
    python meeting_recorder.py --audio meeting.mp3 --speaker1 홍길동 --speaker2 김영희
    python meeting_recorder.py --audio meeting.mp3           # prompts for names
"""

from __future__ import annotations

import argparse
import itertools
import os
import re
import sys
import threading
import time
from pathlib import Path

from audio_utils import to_wav_16k
from speaker_utils import (
    align_segments,
    format_transcript,
    map_speakers,
    merge_consecutive,
)

SAMPLING_RATE = 16000

# HuggingFace repo IDs have the form "org/model" (exactly one "/", no path chars).
# Used to distinguish remote HF repos from local paths in --model-repo validation.
_HF_REPO_ID = re.compile(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$")

# Whisper size shorthand → mlx-community HuggingFace repo.
# Note the naming is inconsistent upstream: turbo has no "-mlx" suffix.
MLX_MODEL_MAP = {
    "tiny":           "mlx-community/whisper-tiny-mlx",
    "base":           "mlx-community/whisper-base-mlx",
    "small":          "mlx-community/whisper-small-mlx",
    "medium":         "mlx-community/whisper-medium-mlx",
    "large-v3":       "mlx-community/whisper-large-v3-mlx",
    "large-v3-turbo": "mlx-community/whisper-large-v3-turbo",
}


# ---------------------------------------------------------------------------
# Spinner context manager
# ---------------------------------------------------------------------------

class Spinner:
    """Simple terminal spinner for long-running operations with no progress bar."""

    def __init__(self, message: str) -> None:
        self.message = message
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._spin, daemon=True)

    def __enter__(self) -> "Spinner":
        self._thread.start()
        return self

    def __exit__(self, *_) -> None:
        self._stop.set()
        self._thread.join()
        # Overwrite the spinning line cleanly
        print(f"\r  {self.message} done.{' ' * 10}")

    def _spin(self) -> None:
        for ch in itertools.cycle("|/-\\"):
            if self._stop.is_set():
                break
            print(f"\r  {self.message} {ch}", end="", flush=True)
            time.sleep(0.1)


# ---------------------------------------------------------------------------
# Phase 1 – Transcription
# ---------------------------------------------------------------------------

def transcribe_audio(
    wav_path: Path,
    language: str | None,
    model_repo: str,
) -> list[tuple[float, float, str]]:
    """Transcribe *wav_path* with mlx-whisper and return (start, end, text) segments.

    Batch transcription on the whole file (not streaming chunks), which is far
    faster and avoids the repetition/hallucination loops that streaming produces
    on silent or ambiguous passages.
    """
    import mlx_whisper

    result = mlx_whisper.transcribe(
        str(wav_path),
        path_or_hf_repo=model_repo,
        language=language,                  # None → autodetect
        task="transcribe",
        # Disable carrying decoded text across windows: this is the main guard
        # against the "뭐야? 뭐야? 뭐야?" repetition loops.
        condition_on_previous_text=False,
        # Hallucination / low-confidence filtering (Whisper defaults).
        compression_ratio_threshold=2.4,
        logprob_threshold=-1.0,
        no_speech_threshold=0.6,
        # Skip hallucinated text over long silences.
        hallucination_silence_threshold=2.0,
        word_timestamps=False,
        verbose=False,
    )

    segments: list[tuple[float, float, str]] = []
    for seg in result.get("segments", []):
        text = seg.get("text", "").strip()
        if text:
            segments.append((seg["start"], seg["end"], text))

    return segments


# ---------------------------------------------------------------------------
# Phase 2 – Diarization
# ---------------------------------------------------------------------------

def diarize_audio(
    wav_path: Path,
    hf_token: str,
    num_speakers: int | None = None,
    max_speakers: int | None = None,
) -> list[tuple[float, float, str]]:
    """Run pyannote speaker-diarization and return (start, end, speaker) segments.

    *num_speakers* forces an exact speaker count. If it is None, the count is
    auto-detected; *max_speakers* then caps how many the pipeline may find.
    """
    from pyannote.audio import Pipeline

    pipeline = Pipeline.from_pretrained(
        "pyannote/speaker-diarization-3.0",
        token=hf_token,
    )

    # Use MPS on Apple Silicon when available
    try:
        import torch
        if torch.backends.mps.is_available():
            pipeline = pipeline.to(torch.device("mps"))
    except ImportError:
        pass
    except Exception as e:
        print(f"  Warning: could not move pipeline to MPS: {e}", file=sys.stderr)

    diar_kwargs: dict[str, int] = {}
    if num_speakers is not None:
        diar_kwargs["num_speakers"] = num_speakers
    elif max_speakers is not None:
        diar_kwargs["max_speakers"] = max_speakers
    result = pipeline(str(wav_path), **diar_kwargs)

    # pyannote.audio 3.x returns an Annotation with .itertracks();
    # 4.x wraps it in a DiarizeOutput dataclass under .speaker_diarization.
    if hasattr(result, "itertracks"):
        annotation = result
    elif hasattr(result, "speaker_diarization"):
        annotation = result.speaker_diarization
    else:
        raise RuntimeError(
            f"Unexpected pyannote output type: {type(result).__name__}. "
            "Expected Annotation (.itertracks) or DiarizeOutput (.speaker_diarization)."
        )

    return [
        (turn.start, turn.end, speaker)
        for turn, _, speaker in annotation.itertracks(yield_label=True)
    ]


# ---------------------------------------------------------------------------
# Speaker name resolution
# ---------------------------------------------------------------------------

def resolve_speaker_names(
    diar_segs: list[tuple[float, float, str]],
    speaker1: str | None,
    speaker2: str | None,
) -> dict[str, str]:
    """Map speaker IDs (e.g. SPEAKER_00) to human names.

    Any name supplied via --speaker1/--speaker2 is used; speakers without a
    given name get a readable default label ("화자 1", "화자 2", …) so the run
    stays fully non-interactive. Rename them later in the output file.
    """
    unique_ids = sorted({spk for _, _, spk in diar_segs})
    preset = [speaker1, speaker2]
    mapping: dict[str, str] = {}

    for i, sid in enumerate(unique_ids):
        if i < len(preset) and preset[i]:
            mapping[sid] = preset[i]
        else:
            mapping[sid] = f"화자 {i + 1}"

    return mapping


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Speaker-separated meeting transcription (mlx-whisper + pyannote).",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--audio",       required=True,
                   help="Input audio file (MP3, WAV, M4A, …)")
    p.add_argument("--speaker1",    default=None,
                   help="Name for SPEAKER_00 (first detected speaker)")
    p.add_argument("--speaker2",    default=None,
                   help="Name for SPEAKER_01 (second detected speaker)")
    p.add_argument("--language",    default="ko",
                   choices=["ko", "en", "auto"],
                   help="Transcription language")
    p.add_argument("--model",       default="large-v3-turbo",
                   choices=list(MLX_MODEL_MAP.keys()),
                   metavar="SIZE",
                   help="Whisper model size (mlx-community). "
                        "tiny | base | small | medium | large-v3 | large-v3-turbo")
    p.add_argument("--model-repo",  default=None,
                   metavar="REPO",
                   help="Override with an explicit mlx-community HF repo or local "
                        "path (e.g. mlx-community/whisper-large-v3-turbo)")
    p.add_argument("--speakers",    default="auto",
                   metavar="N",
                   help="Exact number of speakers, or 'auto' to let pyannote "
                        "detect it (default: auto)")
    p.add_argument("--max-speakers", type=int, default=None,
                   metavar="M",
                   help="Upper bound on speaker count when auto-detecting "
                        "(e.g. 2 = never split into 3+). Ignored if --speakers "
                        "is a fixed number.")
    p.add_argument("--output",      default=None,
                   metavar="FILE",
                   help="Output transcript file "
                        "(defaults to <audio_stem>_transcript.txt)")
    p.add_argument("--timestamps",  action="store_true",
                   help="Prepend [HH:MM:SS] to each line")
    p.add_argument("--hf-token",    default=None,
                   metavar="TOKEN",
                   help="HuggingFace access token (falls back to $HF_TOKEN)")
    return p.parse_args()


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    args = parse_args()

    # --- Validate inputs ---
    audio_path = Path(args.audio)
    if not audio_path.exists():
        sys.exit(f"Error: audio file not found: {audio_path}")

    hf_token = (
        args.hf_token
        or os.environ.get("HF_TOKEN")
        or os.environ.get("HUGGINGFACE_TOKEN")
    )
    if not hf_token:
        sys.exit(
            "Error: HuggingFace token required for speaker diarization.\n"
            "  Pass --hf-token TOKEN  or  export HF_TOKEN=your_token\n"
            "  Get a token at https://huggingface.co/settings/tokens"
        )

    # Resolve model size shorthand → mlx-community repo (or use explicit override).
    model_repo: str = args.model_repo or MLX_MODEL_MAP[args.model]

    # If an explicit local path was given, verify it exists.
    # HF repo IDs look like "org/model" (exactly one "/", no leading path chars).
    # Anything else — absolute paths, "./rel", bare names — is treated as local.
    if args.model_repo and not _HF_REPO_ID.match(args.model_repo) and not Path(args.model_repo).exists():
        sys.exit(f"Error: local model path not found: {args.model_repo}")

    output_path = (
        Path(args.output)
        if args.output
        else audio_path.with_name(audio_path.stem + "_transcript.txt")
    )
    language: str | None = None if args.language == "auto" else args.language

    # Resolve speaker-count mode: a fixed integer, or auto-detect (optionally
    # capped by --max-speakers).
    num_speakers: int | None = None
    max_speakers: int | None = None
    if str(args.speakers).lower() in ("auto", "0", ""):
        max_speakers = args.max_speakers
    else:
        try:
            num_speakers = int(args.speakers)
            if num_speakers < 1:
                raise ValueError
        except ValueError:
            sys.exit(f"Error: --speakers must be a positive integer or 'auto' "
                     f"(got {args.speakers!r})")

    print(f"\nMeeting Transcription")
    print(f"  Audio    : {audio_path.name}")
    print(f"  Model    : {model_repo}")
    print(f"  Language : {args.language}")
    print(f"  Output   : {output_path}\n")

    # --- Convert audio to 16 kHz mono WAV ---
    print("  Converting audio...")
    with Spinner("Converting"):
        wav_path = to_wav_16k(audio_path)

    tmp_wav = wav_path   # keep reference for cleanup

    try:
        # --- Phase 1: Transcription ---
        print("\n[Phase 1] Transcribing with mlx-whisper...")
        with Spinner("Transcribing"):
            whisper_segs = transcribe_audio(wav_path, language, model_repo)
        print(f"  → {len(whisper_segs)} segment(s) transcribed")

        if not whisper_segs:
            sys.exit("Error: no speech detected. Check that the audio contains speech.")

        # --- Phase 2: Diarization ---
        print("\n[Phase 2] Identifying speakers with pyannote...")
        with Spinner("Diarizing"):
            diar_segs = diarize_audio(
                wav_path, hf_token,
                num_speakers=num_speakers,
                max_speakers=max_speakers,
            )
        print(f"  → {len(diar_segs)} speaker turn(s) detected")

        if not diar_segs:
            sys.exit("Error: diarization returned no speaker segments.")

        # --- Resolve speaker names ---
        n_speakers = len({spk for _, _, spk in diar_segs})
        print(f"  → {n_speakers} speaker(s) identified")
        if num_speakers is not None and n_speakers != num_speakers:
            print(f"  Warning: you requested {num_speakers} speaker(s) but "
                  f"{n_speakers} were found. Continuing.")

        print()
        speaker_map = resolve_speaker_names(diar_segs, args.speaker1, args.speaker2)
        for sid, name in speaker_map.items():
            print(f"    {sid} → {name}")

        # --- Align, merge, format, write ---
        aligned  = align_segments(whisper_segs, diar_segs)
        named    = map_speakers(aligned, speaker_map)
        merged   = merge_consecutive(named)
        transcript = format_transcript(merged, with_timestamps=args.timestamps)

        output_path.write_text(transcript, encoding="utf-8")
        print(f"\nTranscript saved to: {output_path}")

    finally:
        if tmp_wav != audio_path:
            tmp_wav.unlink(missing_ok=True)


if __name__ == "__main__":
    main()
