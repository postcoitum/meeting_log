"""Pure helper functions for aligning Whisper segments with diarization output."""

from __future__ import annotations

import datetime
from typing import NamedTuple


# Type aliases
WhisperSeg = tuple[float, float, str]   # (start_sec, end_sec, text)
DiarSeg    = tuple[float, float, str]   # (start_sec, end_sec, speaker_id)
AlignedSeg = tuple[float, str, str]     # (start_sec, speaker_id, text)
NamedSeg   = tuple[float, str, str]     # (start_sec, speaker_name, text)


def align_segments(
    whisper_segs: list[WhisperSeg],
    diar_segs: list[DiarSeg],
) -> list[AlignedSeg]:
    """Assign each Whisper segment to the diarization speaker with the most overlap.

    When a Whisper segment overlaps no diarization segment at all (e.g., brief
    silence at the very start), the closest speaker by midpoint distance is used.
    """
    result: list[AlignedSeg] = []

    for w_start, w_end, text in whisper_segs:
        text = text.strip()
        if not text:
            continue

        best_speaker = "SPEAKER_00"
        best_overlap = -1.0

        w_mid = (w_start + w_end) / 2.0
        best_dist = float("inf")

        for d_start, d_end, spk in diar_segs:
            overlap = max(0.0, min(w_end, d_end) - max(w_start, d_start))
            if overlap > best_overlap:
                best_overlap = overlap
                best_speaker = spk
            # Track closest segment midpoint as fallback
            dist = abs(w_mid - (d_start + d_end) / 2.0)
            if overlap == 0.0 and dist < best_dist:
                best_dist = dist
                if best_overlap == 0.0:
                    best_speaker = spk

        result.append((w_start, best_speaker, text))

    return result


def map_speakers(
    aligned: list[AlignedSeg],
    speaker_map: dict[str, str],
) -> list[NamedSeg]:
    """Replace pyannote speaker IDs with human-readable names."""
    return [
        (ts, speaker_map.get(spk, spk), text)
        for ts, spk, text in aligned
    ]


def merge_consecutive(segments: list[NamedSeg]) -> list[NamedSeg]:
    """Collapse adjacent segments from the same speaker into a single entry."""
    if not segments:
        return []

    merged: list[list] = [list(segments[0])]  # mutable copy of first seg

    for ts, speaker, text in segments[1:]:
        if speaker == merged[-1][1]:
            merged[-1][2] = merged[-1][2] + " " + text
        else:
            merged.append([ts, speaker, text])

    return [(ts, spk, txt) for ts, spk, txt in merged]


def format_transcript(
    segments: list[NamedSeg],
    with_timestamps: bool = False,
) -> str:
    """Render segments as a human-readable transcript string."""
    lines: list[str] = []

    for ts, speaker, text in segments:
        if with_timestamps:
            hms = str(datetime.timedelta(seconds=int(ts)))
            lines.append(f"[{hms}] {speaker}: {text}")
        else:
            lines.append(f"{speaker}: {text}")
        lines.append("")  # blank line between utterances

    return "\n".join(lines).strip()
