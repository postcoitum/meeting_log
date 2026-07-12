"""마이크 녹음: 시작/중지하면 16 kHz mono WAV로 저장한다."""
from __future__ import annotations

import threading
from pathlib import Path

SAMPLE_RATE = 16000


class Recorder:
    """마이크 입력을 WAV 파일로 스트리밍 저장하는 녹음기.

    stream_factory(callback) -> stream 형태의 팩토리를 주입할 수 있어
    테스트에서 실제 마이크 없이 동작을 검증할 수 있다.
    """

    def __init__(self, stream_factory=None) -> None:
        self._factory = stream_factory or self._default_stream
        self._stream = None
        self._file = None
        self._path: str | None = None
        self._lock = threading.Lock()

    @staticmethod
    def _default_stream(callback):
        import sounddevice as sd
        return sd.InputStream(
            samplerate=SAMPLE_RATE, channels=1, dtype="float32", callback=callback
        )

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    def start(self, out_path: str) -> None:
        with self._lock:
            if self._stream is not None:
                raise RuntimeError("이미 녹음 중입니다")
            import soundfile as sf
            Path(out_path).parent.mkdir(parents=True, exist_ok=True)
            self._file = sf.SoundFile(
                out_path, mode="w", samplerate=SAMPLE_RATE, channels=1
            )
            self._path = out_path
            self._stream = self._factory(self._callback)
            self._stream.start()

    def _callback(self, indata, frames, time_info, status) -> None:
        f = self._file
        if f is not None:
            f.write(indata.copy())

    def stop(self) -> str:
        with self._lock:
            if self._stream is None:
                raise RuntimeError("녹음 중이 아닙니다")
            self._stream.stop()
            self._stream.close()
            self._stream = None
            self._file.close()
            self._file = None
            path, self._path = self._path, None
            return path
