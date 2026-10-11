"""
Nova terminal icons — a small inline Lucide-style SVG icon set.

Lucide (https://lucide.dev) icons are simple 24x24 stroke SVGs (ISC licence).
We embed a compact subset as path data and render it with QtSvg so the terminal
gets clean line icons without adding a runtime dependency (and without any
network/font fetch at render time).

If QtSvg is unavailable, `icon_available` is False and callers should fall back
to text-only controls (the UI never depends on icons for function).
"""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QRect, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap

try:
    from PySide6.QtSvg import QSvgRenderer

    icon_available = True
except Exception:  # pragma: no cover - QtSvg not shipped in some builds
    icon_available = False


# Minimal, reliable Lucide path subsets (24x24 viewBox).
ICONS: dict[str, list[str]] = {
    "search": [
        '<circle cx="11" cy="11" r="8"/>',
        '<line x1="21" y1="21" x2="16.65" y2="16.65"/>',
    ],
    "trending-up": [
        '<polyline points="22 7 13.5 15.5 8.5 10.5 2 17"/>',
        '<polyline points="16 7 22 7 22 13"/>',
    ],
    "trending-down": [
        '<polyline points="22 17 13.5 8.5 8.5 13.5 2 7"/>',
        '<polyline points="16 17 22 17 22 11"/>',
    ],
    "activity": [
        '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    ],
    "zap": [
        '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>',
    ],
    "shield": [
        '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
    ],
    "refresh": [
        '<polyline points="23 4 23 10 17 10"/>',
        '<polyline points="1 20 1 14 7 14"/>',
        '<path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>',
    ],
    "clock": [
        '<circle cx="12" cy="12" r="9"/>',
        '<polyline points="12 7 12 12 15.5 14"/>',
    ],
    "chart": [
        '<line x1="3" y1="21" x2="21" y2="21"/>',
        '<line x1="7" y1="17" x2="7" y2="13"/>',
        '<line x1="12" y1="17" x2="12" y2="8"/>',
        '<line x1="17" y1="17" x2="17" y2="4"/>',
    ],
    "line-chart": [
        '<path d="M3 3v18h18"/>',
        '<polyline points="7 14 11 10 15 14 21 8"/>',
    ],
    "layers": [
        '<polygon points="12 2 2 7 12 12 22 7 12 2"/>',
        '<polyline points="2 12 12 17 22 12"/>',
        '<polyline points="2 17 12 22 22 17"/>',
    ],
    "book": [
        '<path d="M2 3h6a4 4 0 0 1 4 4v14a3 3 0 0 0-3-3H2z"/>',
        '<path d="M22 3h-6a4 4 0 0 0-4 4v14a3 3 0 0 1 3-3h7z"/>',
    ],
    "target": [
        '<circle cx="12" cy="12" r="9"/>',
        '<circle cx="12" cy="12" r="5"/>',
        '<circle cx="12" cy="12" r="1.5"/>',
    ],
    "scale": [
        '<path d="M12 3v18"/>',
        '<path d="M5 7h14"/>',
        '<path d="M7 7l-3 6h6z"/>',
        '<path d="M17 7l-3 6h6z"/>',
    ],
    "alert": [
        '<path d="M12 2 2 20h20z"/>',
        '<line x1="12" y1="9" x2="12" y2="14"/>',
        '<circle cx="12" cy="17" r="0.8"/>',
    ],
    "check": [
        '<polyline points="20 6 9 17 4 12"/>',
    ],
}


_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
    'viewBox="0 0 24 24" fill="none" stroke="{color}" stroke-width="2" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


def svg_markup(name: str, color: str) -> str:
    """Return the SVG source for an icon in the given stroke color."""
    body = "".join(ICONS.get(name, []))
    return _TEMPLATE.format(color=color, body=body)


def icon_pixmap(name: str, color: str, size: int = 16) -> QPixmap | None:
    """Render an icon to a `size`-square QPixmap in the given color, or None."""
    if not icon_available:
        return None
    renderer = QSvgRenderer(QByteArray(svg_markup(name, color).encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    renderer.render(painter, QRect(0, 0, size, size))
    painter.end()
    return pixmap


def make_icon(name: str, color: str, size: int = 16) -> QIcon:
    """A QIcon for the icon (an empty QIcon if QtSvg is unavailable)."""
    pixmap = icon_pixmap(name, color, size)
    return QIcon(pixmap) if pixmap is not None else QIcon()
