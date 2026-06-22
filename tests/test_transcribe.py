import app.transcribe as t


def test_transcribe_meeting_pipeline(monkeypatch, tmp_path):
    fake_wav = tmp_path / "x.wav"
    fake_wav.write_bytes(b"")

    monkeypatch.setattr(t, "to_wav_16k", lambda p: fake_wav)
    monkeypatch.setattr(
        t, "transcribe_audio",
        lambda wav, lang, repo: [(0.0, 1.0, "안녕")],
    )
    monkeypatch.setattr(
        t, "diarize_audio",
        lambda wav, token, num_speakers=None, max_speakers=None: [(0.0, 1.0, "SPEAKER_00")],
    )

    stages = []
    out = t.transcribe_meeting("/in.m4a", "tok", progress=stages.append)

    assert "안녕" in out
    assert "변환" in stages[0] or "transcrib" in stages[0].lower()
    assert not fake_wav.exists()  # 임시 wav 정리됨
