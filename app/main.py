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
        "회의록",
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
