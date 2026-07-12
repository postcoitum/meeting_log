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


def test_migrates_old_db_without_stats_column(tmp_path):
    import sqlite3
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE meetings (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, created_at TEXT NOT NULL, audio_path TEXT NOT NULL, "
        "transcript TEXT NOT NULL DEFAULT '', summary_md TEXT NOT NULL DEFAULT '', "
        "memo_md TEXT NOT NULL DEFAULT '', updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO meetings (title, created_at, audio_path, updated_at) "
        "VALUES ('구버전', '2026-06-20T10:00:00', '/a', '2026-06-20T10:00:00')"
    )
    conn.commit()
    conn.close()

    s = Store(db)  # 열기만 해도 stats_json 컬럼이 추가돼야 함
    got = s.list_meetings()
    assert got[0]["title"] == "구버전"
    mid = got[0]["id"]
    s.update_fields(mid, stats_json='{"speakers": []}')
    assert s.get_meeting(mid)["stats_json"] == '{"speakers": []}'
