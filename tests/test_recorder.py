import numpy as np
import pytest
import soundfile as sf

from app.recorder import Recorder, SAMPLE_RATE


class FakeStream:
    """실제 마이크 대신 start/stop만 흉내내는 스트림."""

    def __init__(self, callback):
        self.callback = callback
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        self.started = False

    def close(self):
        pass


def test_record_lifecycle_writes_wav(tmp_path):
    streams = []

    def factory(cb):
        s = FakeStream(cb)
        streams.append(s)
        return s

    r = Recorder(stream_factory=factory)
    out = str(tmp_path / "rec.wav")

    assert r.is_recording is False
    r.start(out)
    assert r.is_recording is True
    assert streams[0].started is True

    # 마이크 콜백이 들어온 것처럼 1초 분량의 소리를 흘려보냄
    chunk = np.zeros((SAMPLE_RATE, 1), dtype="float32")
    streams[0].callback(chunk, SAMPLE_RATE, None, None)

    path = r.stop()
    assert path == out
    assert r.is_recording is False

    data, sr = sf.read(out)
    assert sr == SAMPLE_RATE
    assert len(data) == SAMPLE_RATE


def test_start_twice_raises(tmp_path):
    r = Recorder(stream_factory=lambda cb: FakeStream(cb))
    r.start(str(tmp_path / "a.wav"))
    with pytest.raises(RuntimeError):
        r.start(str(tmp_path / "b.wav"))


def test_stop_without_start_raises():
    r = Recorder(stream_factory=lambda cb: FakeStream(cb))
    with pytest.raises(RuntimeError):
        r.stop()
