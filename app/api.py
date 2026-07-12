"""pywebview JS↔Python 브릿지."""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

import webview

from app.store import Store
from app.transcribe import transcribe_meeting
from app.summarizer import summarize
from app.recorder import Recorder


class Api:
    def __init__(
        self,
        store: Store,
        hf_token: str = "",
        recorder: Recorder | None = None,
        recordings_dir: str | None = None,
    ) -> None:
        self._store = store
        self._hf_token = hf_token or os.environ.get("HF_TOKEN", "")
        self._recorder = recorder or Recorder()
        self._recordings_dir = Path(
            recordings_dir or Path.home() / ".meeting_log" / "recordings"
        )

    def list_meetings(self) -> list[dict]:
        return self._store.list_meetings()

    def get_meeting(self, meeting_id: int) -> dict | None:
        return self._store.get_meeting(meeting_id)

    def update_meeting(self, meeting_id: int, fields: dict) -> bool:
        # pywebview passes the JS object as a positional dict, not kwargs.
        self._store.update_fields(meeting_id, **fields)
        return True

    def delete_meeting(self, meeting_id: int) -> bool:
        self._store.delete_meeting(meeting_id)
        return True

    def add_meeting(self, audio_path: str, title: str | None = None) -> dict:
        def report(stage: str) -> None:
            win = webview.active_window()
            if win:
                win.evaluate_js(f"window.dispatchEvent(new CustomEvent('progress', {{detail: {stage!r} }}))")
        transcript, stats = transcribe_meeting(
            audio_path, self._hf_token, progress=report
        )
        report("요약 중…")
        summary = summarize(transcript)
        created = datetime.now(timezone.utc).isoformat()
        mid = self._store.create_meeting(
            title or Path(audio_path).stem, created, audio_path, transcript
        )
        self._store.update_fields(
            mid, summary_md=summary, stats_json=json.dumps(stats, ensure_ascii=False)
        )
        return self._store.get_meeting(mid)

    # --- 녹음 ---

    def is_recording(self) -> bool:
        return self._recorder.is_recording

    def start_recording(self) -> bool:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out = str(self._recordings_dir / f"rec_{stamp}.wav")
        self._recorder.start(out)
        return True

    def stop_recording(self) -> dict:
        path = self._recorder.stop()
        title = "녹음 " + datetime.now().strftime("%Y-%m-%d %H:%M")
        return self.add_meeting(path, title=title)

    def summarize_meeting(self, meeting_id: int) -> str:
        m = self._store.get_meeting(meeting_id)
        if not m:
            return ""
        summary = summarize(m["transcript"])
        self._store.update_fields(meeting_id, summary_md=summary)
        return summary

    def pick_audio(self) -> str:
        win = webview.active_window()
        if not win:
            return ""
        result = win.create_file_dialog(
            dialog_type=webview.OPEN_DIALOG,
            file_types=("오디오 (*.m4a;*.mp3;*.wav;*.mp4)",),
        )
        if not result:
            return ""
        return result[0]
