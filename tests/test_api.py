import app.api as api_mod
from app.store import Store


FAKE_STATS = {"speakers": [{"name": "화자 1", "share": 100, "quotes": ["안녕"]}]}


def make_api(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))
    monkeypatch.setattr(
        api_mod, "transcribe_meeting",
        lambda path, token, progress=None, num_speakers=None, rates=None, timings_out=None: ("화자 1: 안녕", FAKE_STATS),
    )
    monkeypatch.setattr(api_mod, "summarize",
                        lambda text, template=None: "## 요약\n- x")
    return api_mod.Api(store=store, hf_token="tok")


def test_add_meeting_creates_with_transcript_and_summary(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/some/audio.m4a")
    assert m["transcript"] == "화자 1: 안녕"
    assert m["summary_md"] == "## 요약\n- x"
    assert m["title"] == "audio"
    assert "화자 1" in m["stats_json"]


def test_update_and_get(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    assert api.update_meeting(m["id"], {"memo_md": "내 메모"}) is True
    assert api.get_meeting(m["id"])["memo_md"] == "내 메모"


def test_list_after_add(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    api.add_meeting("/a/one.m4a")
    assert len(api.list_meetings()) == 1


def test_recording_flow_creates_meeting(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)

    class FakeRecorder:
        def __init__(self):
            self.path = None
            self.is_recording = False

        def start(self, out):
            self.path = out
            self.is_recording = True

        def stop(self):
            self.is_recording = False
            return self.path

    api._recorder = FakeRecorder()
    api._recordings_dir = tmp_path

    assert api.is_recording() is False
    assert api.start_recording() is True
    assert api.is_recording() is True

    m = api.stop_recording()
    assert m["title"].startswith("녹음 ")
    assert m["transcript"] == "화자 1: 안녕"
    assert api.is_recording() is False


def test_pick_audio_returns_first(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.webview, "active_window",
                        lambda: type("W", (), {"create_file_dialog": lambda s, **k: ["/x.m4a"]})())
    assert api.pick_audio() == "/x.m4a"


def test_pick_audio_cancel_returns_empty(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    monkeypatch.setattr(api_mod.webview, "active_window",
                        lambda: type("W", (), {"create_file_dialog": lambda s, **k: None})())
    assert api.pick_audio() == ""


def test_chat_meeting_uses_transcript(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    captured = {}

    def fake_chat(transcript, question):
        captured["t"], captured["q"] = transcript, question
        return "답변입니다"

    monkeypatch.setattr(api_mod, "chat", fake_chat)
    out = api.chat_meeting(m["id"], "결정 사항이 뭐야?")
    assert out == "답변입니다"
    assert captured["t"] == "화자 1: 안녕"
    assert captured["q"] == "결정 사항이 뭐야?"


def test_export_meeting_writes_markdown(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    dest = str(tmp_path / "out.md")
    monkeypatch.setattr(
        api_mod.webview, "active_window",
        lambda: type("W", (), {"create_file_dialog": lambda s, **k: dest})(),
    )
    path = api.export_meeting(m["id"])
    assert path == dest
    content = open(dest, encoding="utf-8").read()
    assert "# b" in content
    assert "화자 1: 안녕" in content
    assert "## 요약" in content


def test_copy_for_notion_pipes_markdown_to_pbcopy(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    captured = {}

    def fake_run(cmd, input=None, check=False):
        captured["cmd"], captured["input"] = cmd, input
        return None

    monkeypatch.setattr(api_mod.subprocess, "run", fake_run)
    assert api.copy_for_notion(m["id"]) is True
    assert captured["cmd"] == ["pbcopy"]
    text = captured["input"].decode("utf-8")
    assert text.startswith("# b")
    assert "## 요약" in text and "화자 1: 안녕" in text


def test_copy_for_notion_missing_meeting(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    assert api.copy_for_notion(9999) is False


def test_summary_template_roundtrip(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    default = api.get_summary_template()
    assert "{transcript}" in default
    api.set_summary_template("내 커스텀 양식 {transcript}")
    assert api.get_summary_template() == "내 커스텀 양식 {transcript}"
    # 기본값과 동일하게 저장하면 커스텀 해제
    api.set_summary_template(api.default_summary_template())
    assert api.get_summary_template() == default


def test_regen_uses_custom_template(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    api.set_summary_template("커스텀! {transcript}")
    captured = {}

    def fake_summarize(text, template=None):
        captured["template"] = template
        return "요약"

    monkeypatch.setattr(api_mod, "summarize", fake_summarize)
    api.summarize_meeting(m["id"])
    assert captured["template"] == "커스텀! {transcript}"


def test_hf_token_setting_roundtrip(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    assert api.get_hf_token() == ""
    api.set_hf_token("  hf_new_token  ")
    assert api.get_hf_token() == "hf_new_token"


def test_add_meeting_prefers_db_token(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    captured = {}

    def fake_transcribe(path, token, progress=None, num_speakers=None, rates=None, timings_out=None):
        captured["token"] = token
        return ("화자 1: 안녕", FAKE_STATS)

    monkeypatch.setattr(api_mod, "transcribe_meeting", fake_transcribe)
    api.add_meeting("/a/b.m4a")
    assert captured["token"] == "tok"  # 설정 없음 → 생성자(환경변수) 폴백
    api.set_hf_token("hf_db_token")
    api.add_meeting("/a/c.m4a")
    assert captured["token"] == "hf_db_token"  # 설정이 우선


def test_num_speakers_setting_passed_to_transcribe(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    captured = {}

    def fake_transcribe(path, token, progress=None, num_speakers=None, rates=None, timings_out=None):
        captured["n"] = num_speakers
        return ("화자 1: 안녕", FAKE_STATS)

    monkeypatch.setattr(api_mod, "transcribe_meeting", fake_transcribe)
    api.add_meeting("/a/a.m4a")
    assert captured["n"] is None  # 기본: 자동
    api.set_num_speakers("1")
    assert api.get_num_speakers() == "1"
    api.add_meeting("/a/b.m4a")
    assert captured["n"] == 1


def test_rates_learned_after_add(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)

    def fake_transcribe(path, token, progress=None, num_speakers=None, rates=None, timings_out=None):
        if timings_out is not None:
            timings_out.update({"audio_sec": 100.0, "transcribe_sec": 6.0, "diarize_sec": 50.0})
        return ("화자 1: 안녕", FAKE_STATS)

    import time as time_module
    def fake_summarize(text, template=None):
        time_module.sleep(0.001)
        return "## 요약\n- x"

    monkeypatch.setattr(api_mod, "transcribe_meeting", fake_transcribe)
    monkeypatch.setattr(api_mod, "summarize", fake_summarize)
    api.add_meeting("/a/b.m4a")
    import json as _json
    rates = _json.loads(api._store.get_setting("stage_rates"))
    assert abs(rates["transcribe"] - 0.06) < 1e-6
    assert abs(rates["diarize"] - 0.5) < 1e-6
    assert rates["summary_chunk_sec"] > 0
