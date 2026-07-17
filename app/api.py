"""pywebview JS↔Python 브릿지."""
from __future__ import annotations

import json
import os
import queue
import shutil
import subprocess
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import webview

from app.store import Store
from app.transcribe import transcribe_meeting
from app.summarizer import summarize, chat, DEFAULT_TEMPLATE, MAX_INPUT_CHARS
from app.recorder import Recorder
from audio_utils import to_wav_16k


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
        # 파일을 여러 개 넣어도 즉시 큐에 쌓이고 백그라운드 워커가 하나씩
        # 순차 처리한다(mlx-whisper/pyannote는 GPU 경합 위험이 있어 동시
        # 추론은 하지 않음 — "넣기"와 "처리"만 분리).
        self._queue: "queue.Queue[int]" = queue.Queue()
        self._worker = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker.start()
        self._recover_pending()
        threading.Thread(target=self._backfill_durations, daemon=True).start()

    def _recover_pending(self) -> None:
        """이전 세션이 처리 도중 종료됐다면 남은 작업을 다시 큐에 넣는다."""
        for m in self._store.list_meetings():
            if m.get("status") in ("queued", "processing"):
                self._store.update_fields(m["id"], status="queued")
                self._queue.put(m["id"])

    def _backfill_durations(self) -> None:
        """duration_sec 마이그레이션으로 0인 채 남은 기존 완료 회의의 길이를
        오디오 파일에서 역산해 채운다(재전사는 하지 않음). 앱 시작을 막지
        않도록 별도 스레드에서 조용히 실행 — 실패해도 무시(다음 실행 때 재시도)."""
        import soundfile as sf

        for m in self._store.list_meetings():
            if m.get("status") != "done" or m.get("duration_sec"):
                continue
            full = self._store.get_meeting(m["id"])
            if not full:
                continue
            audio_path = Path(full["audio_path"])
            if not audio_path.exists():
                continue
            wav = None
            try:
                wav = to_wav_16k(audio_path)
                duration = float(sf.info(str(wav)).duration)
                if duration > 0:
                    self._store.update_fields(m["id"], duration_sec=duration)
            except Exception:
                pass
            finally:
                if wav is not None:
                    wav.unlink(missing_ok=True)

    def list_meetings(self) -> list[dict]:
        return self._store.list_meetings()

    def get_meeting(self, meeting_id: int) -> dict | None:
        return self._store.get_meeting(meeting_id)

    def update_meeting(self, meeting_id: int, fields: dict) -> bool:
        # pywebview passes the JS object as a positional dict, not kwargs.
        self._store.update_fields(meeting_id, **fields)
        return True

    def _path_in_recordings_dir(self, path: Path) -> bool:
        """path가 self._recordings_dir 바로 아래에 있는지 확인.
        존재하지 않는 경로 등 resolve() 실패는 False로 취급(안전 쪽으로 폴백)."""
        try:
            return path.resolve().parent == self._recordings_dir.resolve()
        except OSError:
            return False

    def delete_meeting(self, meeting_id: int, delete_audio: bool = False) -> bool:
        """meeting_id를 DB에서 삭제한다. delete_audio=True면 recordings_dir 안에
        있는 오디오 파일도 함께 지운다 — 바깥 경로(가져오기 실패 등으로 원본 그대로
        남은 old row)는 안전을 위해 건드리지 않는다. 프론트가 항상 사용자에게
        오디오 삭제 여부를 물어본 뒤 이 값을 넘긴다."""
        if delete_audio:
            meeting = self._store.get_meeting(meeting_id)
            if meeting and meeting.get("audio_path"):
                audio_path = Path(meeting["audio_path"])
                if self._path_in_recordings_dir(audio_path):
                    try:
                        audio_path.unlink(missing_ok=True)
                    except OSError:
                        pass  # best-effort — 파일 삭제 실패해도 DB 삭제는 계속
        self._store.delete_meeting(meeting_id)
        return True

    def add_meeting(self, audio_path: str, title: str | None = None) -> dict:
        """DB row를 즉시 만들고 처리는 백그라운드 큐에 맡긴 뒤 바로 리턴한다.

        pywebview RPC 호출을 블록하지 않으므로, 프론트는 이 호출이 끝나자마자
        (전사가 끝나길 기다리지 않고) 다음 파일을 또 추가할 수 있다. 실제
        전사·요약 진행 상황은 'job-progress' 브라우저 이벤트로 통지된다.
        """
        audio_path = self._ensure_in_recordings_dir(audio_path)
        created = datetime.now(timezone.utc).isoformat()
        mid = self._store.create_meeting(
            title or Path(audio_path).stem, created, audio_path, status="queued"
        )
        self._queue.put(mid)
        return self._store.get_meeting(mid)

    def _ensure_in_recordings_dir(self, audio_path: str) -> str:
        """가져온 오디오를 recordings_dir로 복사해 원본이 지워져도 재전사·재생이
        가능하게 한다. 녹음 기능(stop_recording)이 만든 파일은 이미 recordings_dir
        안에 있으므로 그대로 두고(복사 생략), 사용자가 파일 선택으로 가져온
        외부 경로만 복사한다. 복사 실패(권한 등)는 원본 경로를 그대로 써서
        앱이 죽지 않게 한다 — 기존 동작과 동일하게 폴백."""
        src = Path(audio_path)
        try:
            if src.resolve().parent == self._recordings_dir.resolve():
                return audio_path
        except OSError:
            return audio_path
        self._recordings_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        dest = self._recordings_dir / f"imported_{stamp}_{src.name}"
        try:
            shutil.copy2(src, dest)
            return str(dest)
        except OSError:
            return audio_path

    def _worker_loop(self) -> None:
        while True:
            mid = self._queue.get()
            try:
                self._process_meeting(mid)
            except Exception as e:
                self._store.update_fields(mid, status="error")
                self._notify(mid, "error", f"처리 실패: {e}")
            finally:
                self._queue.task_done()

    def _process_meeting(self, mid: int) -> None:
        m = self._store.get_meeting(mid)
        if not m:
            return
        audio_path = m["audio_path"]
        self._store.update_fields(mid, status="processing")
        self._notify(mid, "processing", "오디오 변환 중…")

        timings: dict = {}
        transcript, stats = transcribe_meeting(
            audio_path, self._token(),
            progress=lambda stage: self._notify(mid, "processing", stage),
            num_speakers=self._num_speakers(),
            rates=self._rates(), timings_out=timings,
        )
        n_chunks = max(1, -(-len(transcript) // MAX_INPUT_CHARS))  # ceil
        chunk_rate = self._rates().get("summary_chunk_sec")
        eta = f" (예상 약 {max(1, round(n_chunks * chunk_rate / 60))}분)" if chunk_rate else ""
        self._notify(mid, "processing", f"요약 중…{eta}")
        # 같은 프로세스에서 전사(whisper)→요약(mlx-lm)을 연달아 돌리므로,
        # whisper가 남긴 mlx 캐시를 비워야 요약 프리필에서 Metal OOM을 피한다.
        import mlx.core as mx
        mx.clear_cache()
        t0 = time.monotonic()
        summary = summarize(transcript, template=self._summary_template())
        self._save_rates(timings, time.monotonic() - t0, n_chunks)

        self._store.update_fields(
            mid,
            transcript=transcript,
            summary_md=summary,
            stats_json=json.dumps(stats, ensure_ascii=False),
            duration_sec=timings.get("audio_sec") or 0,
            status="done",
        )
        self._notify(mid, "done", "")

    def _notify(self, mid: int, status: str, stage: str) -> None:
        win = webview.active_window()
        if not win:
            return
        payload = json.dumps({"id": mid, "status": status, "stage": stage}, ensure_ascii=False)
        win.evaluate_js(f"window.dispatchEvent(new CustomEvent('job-progress', {{detail: {payload}}}))")

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
        summary = summarize(m["transcript"], template=self._summary_template())
        self._store.update_fields(meeting_id, summary_md=summary)
        return summary

    # --- 단계별 처리율 (소요시간 예측용, 실행마다 실측·학습) ---

    def _rates(self) -> dict:
        raw = self._store.get_setting("stage_rates", "")
        try:
            return json.loads(raw) if raw else {}
        except ValueError:
            return {}

    def _save_rates(self, timings: dict, summary_sec: float, n_chunks: int) -> None:
        """실측치를 지수이동평균(0.5)으로 반영. audio_sec 없으면 저장 안 함."""
        audio = timings.get("audio_sec") or 0
        if audio <= 0:
            return
        rates = self._rates()

        def blend(key: str, new: float) -> None:
            old = rates.get(key)
            rates[key] = round(new if old is None else old * 0.5 + new * 0.5, 4)

        if timings.get("transcribe_sec"):
            blend("transcribe", timings["transcribe_sec"] / audio)
        if timings.get("diarize_sec"):
            blend("diarize", timings["diarize_sec"] / audio)
        if summary_sec > 0 and n_chunks > 0:
            blend("summary_chunk_sec", summary_sec / n_chunks)
        self._store.set_setting("stage_rates", json.dumps(rates))

    # --- 화자 수 설정 ---
    # "1"이면 화자 분리를 건너뛰어(pyannote 미실행) 긴 파일에서 크게 빨라진다.

    def _num_speakers(self) -> int | None:
        v = self._store.get_setting("num_speakers", "")
        return int(v) if v.isdigit() and int(v) > 0 else None

    def get_num_speakers(self) -> str:
        return self._store.get_setting("num_speakers", "")

    def set_num_speakers(self, value: str) -> bool:
        self._store.set_setting("num_speakers", str(value or "").strip())
        return True

    # --- HF 토큰 설정 ---
    # .app으로 실행하면 터미널 환경변수($HF_TOKEN)를 읽지 못하므로,
    # 앱 설정(DB)에 저장된 토큰을 우선 사용하고 환경변수는 폴백으로 둔다.

    def _token(self) -> str:
        return self._store.get_setting("hf_token", "") or self._hf_token

    def get_hf_token(self) -> str:
        return self._store.get_setting("hf_token", "")

    def set_hf_token(self, token: str) -> bool:
        self._store.set_setting("hf_token", (token or "").strip())
        return True

    # --- 요약 양식 설정 ---

    def _summary_template(self) -> str | None:
        """저장된 사용자 양식 (없으면 None → 기본 양식 사용)."""
        return self._store.get_setting("summary_template", "") or None

    def get_summary_template(self) -> str:
        return self._summary_template() or DEFAULT_TEMPLATE

    def default_summary_template(self) -> str:
        return DEFAULT_TEMPLATE

    def set_summary_template(self, template: str) -> bool:
        """빈 문자열이거나 기본 양식과 같으면 커스텀 설정을 지운다."""
        t = (template or "").strip()
        if t == DEFAULT_TEMPLATE.strip():
            t = ""
        self._store.set_setting("summary_template", t)
        return True

    def chat_meeting(self, meeting_id: int, question: str) -> str:
        m = self._store.get_meeting(meeting_id)
        if not m:
            return ""
        return chat(m["transcript"], question)

    @staticmethod
    def _meeting_markdown(m: dict) -> str:
        return (
            f"# {m['title']}\n\n"
            f"날짜: {m['created_at'][:10]}\n\n"
            f"## 요약\n\n{m['summary_md'] or '(없음)'}\n\n"
            f"## 메모\n\n{m['memo_md'] or '(없음)'}\n\n"
            f"## 전사 스크립트\n\n{m['transcript']}\n"
        )

    def export_meeting(self, meeting_id: int) -> str:
        """회의를 마크다운 파일로 저장하고 경로를 반환 (취소 시 '')."""
        m = self._store.get_meeting(meeting_id)
        if not m:
            return ""
        win = webview.active_window()
        if not win:
            return ""
        result = win.create_file_dialog(
            dialog_type=webview.SAVE_DIALOG,
            save_filename=f"{m['title']}.md",
        )
        if not result:
            return ""
        path = result if isinstance(result, str) else result[0]
        content = self._meeting_markdown(m)
        Path(path).write_text(content, encoding="utf-8")
        return path

    def copy_for_notion(self, meeting_id: int) -> bool:
        """회의록 마크다운을 클립보드에 복사 — 노션에 그대로 붙여넣으면 서식 변환됨."""
        m = self._store.get_meeting(meeting_id)
        if not m:
            return False
        subprocess.run(["pbcopy"], input=self._meeting_markdown(m).encode("utf-8"), check=True)
        return True

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
