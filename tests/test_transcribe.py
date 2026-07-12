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
    out, stats = t.transcribe_meeting("/in.m4a", "tok", progress=stages.append)

    assert "안녕" in out
    assert "변환" in stages[0] or "transcrib" in stages[0].lower()
    assert not fake_wav.exists()  # 임시 wav 정리됨
    assert stats["speakers"][0]["name"] == "화자 1"
    assert stats["speakers"][0]["share"] == 100
    assert "안녕" in stats["speakers"][0]["quotes"][0]


def test_speaker_stats_two_speakers(monkeypatch, tmp_path):
    fake_wav = tmp_path / "x.wav"
    fake_wav.write_bytes(b"")

    monkeypatch.setattr(t, "to_wav_16k", lambda p: fake_wav)
    monkeypatch.setattr(
        t, "transcribe_audio",
        lambda wav, lang, repo: [
            (0.0, 6.0, "첫 화자의 긴 발언입니다 아주 길어요"),
            (6.0, 8.0, "짧은 답변"),
        ],
    )
    monkeypatch.setattr(
        t, "diarize_audio",
        lambda wav, token, num_speakers=None, max_speakers=None: [
            (0.0, 6.0, "SPEAKER_00"),
            (6.0, 8.0, "SPEAKER_01"),
        ],
    )

    _, stats = t.transcribe_meeting("/in.m4a", "tok")
    names = {s["name"]: s for s in stats["speakers"]}
    assert names["화자 1"]["share"] == 75
    assert names["화자 2"]["share"] == 25
    assert "긴 발언" in names["화자 1"]["quotes"][0]
