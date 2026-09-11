"""
Loads the Ranaliz logo for the application window/taskbar icon and header.
Uses the bundled logo512.png next to this module (preferred). Falls back to a
simple wordmark SVG only if the PNG is missing.
"""
import pathlib
import sys

from PySide6.QtCore import QByteArray, QSize, Qt, QRectF
from PySide6.QtGui import QIcon, QPixmap, QPainter
from PySide6.QtSvg import QSvgRenderer

FALLBACK_SVG = b"""<?xml version="1.0" encoding="UTF-8"?>
<svg width="220" height="48" viewBox="0 0 220 48" xmlns="http://www.w3.org/2000/svg">
  <defs>
    <linearGradient id="g" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#00C2A8"/>
      <stop offset="100%" stop-color="#008F7E"/>
    </linearGradient>
  </defs>
  <rect x="0" y="8" width="32" height="32" rx="8" fill="url(#g)"/>
  <path d="M8 32 L16 14 L20 22 L24 14 L28 32" stroke="white" stroke-width="2.6"
        fill="none" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="42" y="32" font-family="Segoe UI, Arial, sans-serif" font-size="22"
        font-weight="700" fill="#E8EEF5">Ranaliz</text>
</svg>"""


def _bundle_dir():
    """Directory containing logo512.png (dev tree or PyInstaller _MEIPASS)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return pathlib.Path(sys._MEIPASS)
    return pathlib.Path(__file__).resolve().parent


def logo_png_path():
    return _bundle_dir() / "logo512.png"


def asset_path(filename: str):
    """Path to a file under assets/ (dev tree or PyInstaller _MEIPASS)."""
    return _bundle_dir() / "assets" / filename


_FLAG_FILES = {
    "en": "flag_en.svg",
    "tr": "flag_tr.svg",
    "ar": "flag_sa.svg",
}


def flag_icon(lang_code: str, height: int = 14) -> QIcon:
    """Load a language flag SVG as QIcon (avoids emoji flags on Windows)."""
    name = _FLAG_FILES.get(lang_code)
    icon = QIcon()
    if not name:
        return icon
    path = asset_path(name)
    if not path.is_file():
        return icon
    renderer = QSvgRenderer(str(path))
    if not renderer.isValid():
        return icon
    default = renderer.defaultSize()
    if default.width() and default.height():
        width = max(1, int(height * default.width() / default.height()))
    else:
        width = int(height * 20 / 14)
    pixmap = QPixmap(QSize(width, height))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, width, height))
    painter.end()
    icon.addPixmap(pixmap)
    return icon


def _load_source_pixmap():
    path = logo_png_path()
    if path.is_file():
        pm = QPixmap(str(path))
        if not pm.isNull():
            return pm
    return None


def render_logo_pixmap(height=32, svg_bytes=None):
    """Return a header logo pixmap of the given height, preserving aspect ratio."""
    source = _load_source_pixmap()
    if source is not None:
        scaled = source.scaledToHeight(height, Qt.SmoothTransformation)
        return scaled

    data = svg_bytes if svg_bytes is not None else FALLBACK_SVG
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        renderer = QSvgRenderer(QByteArray(FALLBACK_SVG))

    default_size = renderer.defaultSize()
    if default_size.width() == 0 or default_size.height() == 0:
        width = height * 4
    else:
        aspect = default_size.width() / default_size.height()
        width = int(height * aspect)

    pixmap = QPixmap(QSize(width, height))
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter)
    painter.end()
    return pixmap


def build_app_icon(svg_bytes=None):
    """Build a multi-resolution QIcon for window/taskbar from logo512.png."""
    source = _load_source_pixmap()
    icon = QIcon()

    if source is not None:
        for size in (16, 24, 32, 48, 64, 128, 256, 512):
            pm = source.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            # Ensure square canvas so OS taskbar icons stay crisp
            canvas = QPixmap(size, size)
            canvas.fill(Qt.transparent)
            painter = QPainter(canvas)
            painter.setRenderHint(QPainter.Antialiasing)
            x = (size - pm.width()) // 2
            y = (size - pm.height()) // 2
            painter.drawPixmap(x, y, pm)
            painter.end()
            icon.addPixmap(canvas)
        return icon

    data = svg_bytes if svg_bytes is not None else FALLBACK_SVG
    renderer = QSvgRenderer(QByteArray(data))
    if not renderer.isValid():
        renderer = QSvgRenderer(QByteArray(FALLBACK_SVG))

    for size in (16, 24, 32, 48, 64, 128, 256):
        pm = QPixmap(size, size)
        pm.fill(Qt.transparent)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.Antialiasing)
        pad = size * 0.14
        target_w = size - 2 * pad
        target_h = size - 2 * pad
        default_size = renderer.defaultSize()
        if default_size.width() and default_size.height():
            aspect = default_size.width() / default_size.height()
            if aspect > 1:
                draw_w = target_w
                draw_h = target_w / aspect
            else:
                draw_h = target_h
                draw_w = target_h * aspect
        else:
            draw_w, draw_h = target_w, target_h
        x = (size - draw_w) / 2
        y = (size - draw_h) / 2
        renderer.render(painter, QRectF(x, y, draw_w, draw_h))
        painter.end()
        icon.addPixmap(pm)
    return icon
