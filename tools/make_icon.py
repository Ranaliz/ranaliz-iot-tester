#!/usr/bin/env python3
"""Generate AppIcon.ico from logo512.png for Windows PyInstaller builds."""
from __future__ import annotations

import sys
from pathlib import Path

SIZES = ((16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256))


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    src = root / "logo512.png"
    out = root / "AppIcon.ico"

    if not src.is_file():
        print(f"ERROR: missing {src}", file=sys.stderr)
        return 1

    try:
        from PIL import Image
    except ImportError:
        print("Pillow not installed; falling back to logo512.png as icon", file=sys.stderr)
        print(src.name)
        return 0

    img = Image.open(src).convert("RGBA")
    w, h = img.size
    side = max(w, h)
    canvas = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    canvas.paste(img, ((side - w) // 2, (side - h) // 2), img)
    # Pillow generates each size from the master image when sizes= is set
    canvas.save(out, format="ICO", sizes=list(SIZES))
    print(out.name)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
