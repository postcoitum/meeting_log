import app.api as api_mod
from app.store import Store


FAKE_STATS = {"speakers": [{"name": "화자 1", "share": 100, "quotes": ["안녕"]}]}


def make_api(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))
    monkeypatch.setattr(api_mod, "transcribe_meeting",
                        lambda path, token, progress=None: ("화자 1: 안녕", FAKE_STATS))
    monkeypatch.setattr(api_mod, "summarize", lambda text: "## 요약\n- x")
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
