"""pywebview 앱 진입점."""
import os
from pathlib import Path

import webview

from app.store import Store
from app.api import Api

WEB_DIR = Path(__file__).parent / "web"
DB_PATH = str(Path.home() / ".meeting_log" / "meetings.db")


def main() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    api = Api(store=Store(DB_PATH), hf_token=os.environ.get("HF_TOKEN", ""))
    window = webview.create_window(
        # pywebview(cocoa)는 frameless=True일 때 신호등 버튼(닫기/최소화/최대화)을
        # 코드에서 강제로 setHidden_(True) 시켜버려서 되살릴 방법이 없다 — 그래서
        # frameless 대신 타이틀만 비워 네이티브 창은 그대로 두고 텍스트만 없앤다.
        "",
        str(WEB_DIR / "index.html"),
        js_api=api,
        width=1200,
        height=760,
        min_size=(900, 600),
    )
    webview.start()
    _ = window


if __name__ == "__main__":
    main()
