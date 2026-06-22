"""pywebview 앱 진입점."""
from pathlib import Path
import webview

WEB_DIR = Path(__file__).parent / "web"


def main() -> None:
    window = webview.create_window(
        "회의록",
        str(WEB_DIR / "index.html"),
        width=1200,
        height=760,
        min_size=(900, 600),
    )
    webview.start()
    _ = window


if __name__ == "__main__":
    main()
