import app.api as api_mod
from app.store import Store


def make_api(tmp_path, monkeypatch):
    store = Store(str(tmp_path / "t.db"))
    monkeypatch.setattr(api_mod, "transcribe_meeting",
                        lambda path, token, progress=None: "화자 1: 안녕")
    monkeypatch.setattr(api_mod, "summarize", lambda text: "## 요약\n- x")
    return api_mod.Api(store=store, hf_token="tok")


def test_add_meeting_creates_with_transcript_and_summary(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/some/audio.m4a")
    assert m["transcript"] == "화자 1: 안녕"
    assert m["summary_md"] == "## 요약\n- x"
    assert m["title"] == "audio"


def test_update_and_get(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    m = api.add_meeting("/a/b.m4a")
    assert api.update_meeting(m["id"], memo_md="내 메모") is True
    assert api.get_meeting(m["id"])["memo_md"] == "내 메모"


def test_list_after_add(tmp_path, monkeypatch):
    api = make_api(tmp_path, monkeypatch)
    api.add_meeting("/a/one.m4a")
    assert len(api.list_meetings()) == 1


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
