"""pywebview JS↔Python 브릿지."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

import webview

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

    def pick_audio(self) -> str:
        result = webview.active_window().create_file_dialog(
            dialog_type=webview.OPEN_DIALOG,
            file_types=("오디오 (*.m4a;*.mp3;*.wav;*.mp4)",),
        )
        if not result:
            return ""
        return result[0]
