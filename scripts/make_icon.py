"""회의록.app 아이콘(.icns) 생성 — 브라운베이지 글래스 톤의 마이크 아이콘.

사용법: python3 scripts/make_icon.py <출력.icns 경로>
PIL과 macOS iconutil이 필요하다.
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

BASE = 1024  # 마스터 캔버스 크기


def draw_master() -> Image.Image:
    img = Image.new("RGBA", (BASE, BASE), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    # macOS 아이콘 관례: 캔버스의 ~82%를 차지하는 둥근 사각형
    m = int(BASE * 0.09)
    radius = int(BASE * 0.185)
    d.rounded_rectangle([m, m, BASE - m, BASE - m], radius=radius, fill=(231, 217, 196, 255))
    # 위쪽 하이라이트 (글래스 느낌)
    d.rounded_rectangle(
        [m, m, BASE - m, int(BASE * 0.5)], radius=radius, fill=(244, 236, 224, 255)
    )
    d.rounded_rectangle(
        [m, int(BASE * 0.32), BASE - m, BASE - m],
        radius=radius,
        fill=(225, 208, 183, 255),
    )

    brown = (110, 82, 50, 255)
    cx = BASE // 2

    # 마이크 캡슐
    cap_w = int(BASE * 0.17)
    cap_top = int(BASE * 0.24)
    cap_bottom = int(BASE * 0.52)
    d.rounded_rectangle(
        [cx - cap_w, cap_top, cx + cap_w, cap_bottom], radius=cap_w, fill=brown
    )

    # 스탠드 아치
    arc_r = int(BASE * 0.245)
    arc_box = [cx - arc_r, int(BASE * 0.20), cx + arc_r, int(BASE * 0.20) + arc_r * 2]
    d.arc(arc_box, start=20, end=160, fill=brown, width=int(BASE * 0.05))

    # 기둥 + 받침
    stem_w = int(BASE * 0.025)
    stem_top = int(BASE * 0.20) + arc_r * 2 - int(BASE * 0.02)
    stem_bottom = int(BASE * 0.76)
    d.rectangle([cx - stem_w, stem_top, cx + stem_w, stem_bottom], fill=brown)
    base_w = int(BASE * 0.13)
    d.rounded_rectangle(
        [cx - base_w, stem_bottom, cx + base_w, stem_bottom + int(BASE * 0.045)],
        radius=int(BASE * 0.02),
        fill=brown,
    )

    return img


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("사용법: make_icon.py <출력.icns>")
    out = Path(sys.argv[1])
    master = draw_master()

    with tempfile.TemporaryDirectory() as td:
        iconset = Path(td) / "icon.iconset"
        iconset.mkdir()
        for size in (16, 32, 64, 128, 256, 512):
            for scale in (1, 2):
                px = size * scale
                name = f"icon_{size}x{size}" + ("@2x" if scale == 2 else "") + ".png"
                master.resize((px, px), Image.LANCZOS).save(iconset / name)
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(out)], check=True
        )
    print(f"아이콘 생성됨: {out}")


if __name__ == "__main__":
    main()
