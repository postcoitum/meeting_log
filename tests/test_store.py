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


def test_settings_get_set(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    assert s.get_setting("summary_template", "기본") == "기본"
    s.set_setting("summary_template", "커스텀 양식")
    assert s.get_setting("summary_template") == "커스텀 양식"
    s.set_setting("summary_template", "수정됨")  # upsert
    assert s.get_setting("summary_template") == "수정됨"


def test_update_fields_accepts_folder_id(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    s.update_fields(mid, folder_id=5)
    assert s.get_meeting(mid)["folder_id"] == 5
    s.update_fields(mid, folder_id=None)  # 미분류로 되돌리기
    assert s.get_meeting(mid)["folder_id"] is None


def test_list_meetings_includes_folder_id(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    assert s.list_meetings()[0]["folder_id"] is None
    s.update_fields(mid, folder_id=3)
    assert s.list_meetings()[0]["folder_id"] == 3


def test_migrates_old_db_without_folder_id_column(tmp_path):
    import sqlite3
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE meetings (id INTEGER PRIMARY KEY AUTOINCREMENT, "
        "title TEXT NOT NULL, created_at TEXT NOT NULL, audio_path TEXT NOT NULL, "
        "transcript TEXT NOT NULL DEFAULT '', summary_md TEXT NOT NULL DEFAULT '', "
        "memo_md TEXT NOT NULL DEFAULT '', stats_json TEXT NOT NULL DEFAULT '', "
        "duration_sec REAL NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'done', "
        "updated_at TEXT NOT NULL)"
    )
    conn.execute(
        "INSERT INTO meetings (title, created_at, audio_path, updated_at) "
        "VALUES ('구버전', '2026-06-20T10:00:00', '/a', '2026-06-20T10:00:00')"
    )
    conn.commit()
    conn.close()
    s = Store(db)  # 열기만 해도 folder_id 컬럼이 추가돼야 함
    rows = s.list_meetings()
    assert rows[0]["folder_id"] is None
    s.update_fields(rows[0]["id"], folder_id=1)
    assert s.get_meeting(rows[0]["id"])["folder_id"] == 1


def test_create_and_list_folders_sorted_by_name(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    fid1 = s.create_folder("주간회의")
    fid2 = s.create_folder("고객미팅")
    folders = s.list_folders()
    assert [f["name"] for f in folders] == ["고객미팅", "주간회의"]
    assert {f["id"] for f in folders} == {fid1, fid2}
    assert all("created_at" in f for f in folders)


def test_create_folder_duplicate_name_raises(tmp_path):
    import pytest
    s = Store(str(tmp_path / "t.db"))
    s.create_folder("업무")
    with pytest.raises(ValueError):
        s.create_folder("업무")


def test_create_folder_empty_name_raises(tmp_path):
    import pytest
    s = Store(str(tmp_path / "t.db"))
    for bad in ("", "   "):
        with pytest.raises(ValueError):
            s.create_folder(bad)


def test_rename_folder(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    fid = s.create_folder("옛이름")
    s.rename_folder(fid, "새이름")
    assert s.list_folders()[0]["name"] == "새이름"


def test_rename_folder_to_existing_name_raises(tmp_path):
    import pytest
    s = Store(str(tmp_path / "t.db"))
    fid = s.create_folder("a")
    s.create_folder("b")
    with pytest.raises(ValueError):
        s.rename_folder(fid, "b")


def test_delete_folder_removes_row_only(tmp_path):
    s = Store(str(tmp_path / "t.db"))
    fid = s.create_folder("삭제될폴더")
    mid = s.create_meeting("t", "2026-06-21T10:00:00", "/a", "x")
    s.update_fields(mid, folder_id=fid)
    s.delete_folder(fid)
    assert s.list_folders() == []
    # store 레벨은 폴더 row만 지운다 — 회의 캐스케이드는 Api.delete_folder 책임
    assert s.get_meeting(mid) is not None
