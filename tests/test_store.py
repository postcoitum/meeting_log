from app.store import Store


def test_create_and_get(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("회의1", "2026-06-21T10:00:00", "/a.m4a", "원본 텍스트")
    got = s.get_meeting(mid)
    assert got["title"] == "회의1"
    assert got["transcript"] == "원본 텍스트"
    assert got["summary_md"] == ""
    assert got["memo_md"] == ""


def test_list_sorted_desc(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    s.create_meeting("old", "2026-06-20T10:00:00", "/a", "x")
    s.create_meeting("new", "2026-06-21T10:00:00", "/b", "y")
    rows = s.list_meetings()
    assert [r["title"] for r in rows] == ["new", "old"]


def test_update_fields(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    s.update_fields(mid, title="새 제목", summary_md="## 요약", memo_md="메모")
    got = s.get_meeting(mid)
    assert got["title"] == "새 제목"
    assert got["summary_md"] == "## 요약"
    assert got["memo_md"] == "메모"


def test_delete(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    s.delete_meeting(mid)
    assert s.get_meeting(mid) is None


def test_update_rejects_unknown_field(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    try:
        s.update_fields(mid, evil="x")
        assert False, "should have raised"
    except ValueError:
        pass
