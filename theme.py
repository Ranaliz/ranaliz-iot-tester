"""
Ranaliz brand theme for Ranaliz iOT Tester.
Dark navy / teal palette aligned with the Ranaliz product look.
Compact controls with soft rounded surfaces.
"""
import sys
from pathlib import Path

RANALIZ_NAVY = "#0F2438"
RANALIZ_NAVY_LIGHT = "#1A334D"
RANALIZ_NAVY_LIGHTER = "#254560"
RANALIZ_ACCENT = "#00C2A8"
RANALIZ_ACCENT_DARK = "#00A48F"
RANALIZ_BG = "#0B1220"
RANALIZ_CARD_BG = "#152033"
RANALIZ_INPUT_BG = "#1A2A3D"
RANALIZ_BORDER = "#2A3F55"
RANALIZ_TEXT = "#E8EEF5"
RANALIZ_TEXT_MUTED = "#8FA3B8"
RANALIZ_SUCCESS = "#22C55E"
RANALIZ_ERROR = "#EF4444"
RANALIZ_WARNING = "#F59E0B"
RANALIZ_CHIP_IDLE = "#1A2A3D"
RANALIZ_CHIP_OK_BG = "#0F2E24"
RANALIZ_CHIP_ERR_BG = "#2E1518"


def _asset_url(filename: str) -> str:
    """Absolute file URL for QSS image: (works in dev and PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).resolve().parent
    path = (base / "assets" / filename).resolve()
    # Qt stylesheet url() — quote path (may contain spaces)
    return path.as_posix()


_CHEVRON_DOWN = _asset_url("chevron_down.svg")
_CHEVRON_UP = _asset_url("chevron_up.svg")

QSS = f"""
QMainWindow {{
    background-color: {RANALIZ_BG};
}}

QWidget {{
    color: {RANALIZ_TEXT};
    font-family: "Segoe UI", "SF Pro Text", "Helvetica Neue", Arial, sans-serif;
    font-size: 13px;
}}

/* ---------- Top bar / header ---------- */
QWidget#HeaderBar {{
    background-color: {RANALIZ_NAVY};
    border-bottom: 2px solid {RANALIZ_ACCENT};
}}
QLabel#HeaderTitle {{
    color: #FFFFFF;
    font-size: 17px;
    font-weight: 600;
    letter-spacing: 0.3px;
}}
QLabel#HeaderSubtitle {{
    color: #9FB4C7;
    font-size: 11px;
}}
QComboBox#HeaderLangCombo {{
    background-color: {RANALIZ_NAVY_LIGHT};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    padding: 2px 8px;
    color: #FFFFFF;
    min-height: 24px;
    font-size: 12px;
    font-weight: 600;
}}
QComboBox#HeaderLangCombo:hover {{
    border-color: {RANALIZ_ACCENT};
}}
QComboBox#HeaderLangCombo::drop-down {{
    border: none;
    width: 18px;
}}
QComboBox#HeaderLangCombo QAbstractItemView {{
    background-color: {RANALIZ_CARD_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    selection-background-color: {RANALIZ_ACCENT};
    selection-color: {RANALIZ_BG};
    color: {RANALIZ_TEXT};
    min-height: 96px;
    padding: 4px;
}}
QComboBox#HeaderLangCombo QAbstractItemView::item {{
    min-height: 28px;
    padding: 4px 8px;
}}

/* ---------- Status strip ---------- */
QWidget#StatusStrip {{
    background-color: {RANALIZ_CARD_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 10px;
}}
QLabel.StatusChip {{
    padding: 2px 8px;
    border-radius: 8px;
    background-color: {RANALIZ_CHIP_IDLE};
    font-weight: 600;
    font-size: 11px;
}}

/* ---------- Group boxes (cards) ---------- */
QGroupBox {{
    background-color: {RANALIZ_CARD_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 12px;
    margin-top: 8px;
    padding: 8px 8px 6px 8px;
    font-weight: 600;
    color: {RANALIZ_TEXT};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    top: 1px;
    padding: 0 6px;
    color: {RANALIZ_ACCENT};
    font-size: 11px;
    font-weight: 700;
}}

/* ---------- Tabs ---------- */
QTabWidget::pane {{
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 10px;
    top: -1px;
    background-color: {RANALIZ_CARD_BG};
}}
QTabBar::tab {{
    background-color: {RANALIZ_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-bottom: none;
    padding: 5px 12px;
    margin-right: 2px;
    border-top-left-radius: 8px;
    border-top-right-radius: 8px;
    color: {RANALIZ_TEXT_MUTED};
    font-weight: 600;
}}
QTabBar::tab:selected {{
    background-color: {RANALIZ_CARD_BG};
    color: {RANALIZ_TEXT};
    border-bottom: 2px solid {RANALIZ_ACCENT};
}}
QTabBar::tab:hover:!selected {{
    color: {RANALIZ_ACCENT};
}}

/* ---------- Inputs ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background-color: {RANALIZ_INPUT_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    padding: 3px 7px;
    min-height: 20px;
    color: {RANALIZ_TEXT};
    selection-background-color: {RANALIZ_ACCENT};
    selection-color: {RANALIZ_BG};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
    border: 1.5px solid {RANALIZ_ACCENT};
}}
QSpinBox, QDoubleSpinBox {{
    padding-right: 22px;
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 18px;
    height: 12px;
    background-color: {RANALIZ_NAVY_LIGHT};
    border-left: 1px solid {RANALIZ_BORDER};
    border-top-right-radius: 7px;
    border-bottom: none;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 18px;
    height: 12px;
    background-color: {RANALIZ_NAVY_LIGHT};
    border-left: 1px solid {RANALIZ_BORDER};
    border-bottom-right-radius: 7px;
    border-top: none;
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background-color: {RANALIZ_NAVY_LIGHTER};
    border-left-color: {RANALIZ_ACCENT};
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    image: url("{_CHEVRON_UP}");
    width: 10px;
    height: 6px;
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    image: url("{_CHEVRON_DOWN}");
    width: 10px;
    height: 6px;
}}
QComboBox::drop-down {{
    border: none;
    width: 20px;
}}
QComboBox QAbstractItemView {{
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    selection-background-color: {RANALIZ_ACCENT};
    selection-color: {RANALIZ_BG};
    background-color: {RANALIZ_INPUT_BG};
    color: {RANALIZ_TEXT};
}}

/* History-enabled combobox: visible accent chevron */
QComboBox#HistoryCombo {{
    padding-right: 28px;
}}
QComboBox#HistoryCombo::drop-down {{
    border: none;
    width: 26px;
    background: transparent;
}}
QComboBox#HistoryCombo::down-arrow {{
    image: url("{_CHEVRON_DOWN}");
    width: 12px;
    height: 8px;
    margin-right: 8px;
}}
QToolButton#HistoryPopupBtn {{
    background-color: {RANALIZ_INPUT_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    color: {RANALIZ_ACCENT};
    font-size: 13px;
    font-weight: 700;
    padding: 2px 6px;
    min-width: 28px;
    min-height: 26px;
}}
QToolButton#HistoryPopupBtn:hover {{
    border-color: {RANALIZ_ACCENT};
    color: white;
    background-color: {RANALIZ_NAVY_LIGHT};
}}

QLabel {{
    color: {RANALIZ_TEXT};
}}
QLabel.FieldLabel {{
    color: {RANALIZ_TEXT_MUTED};
    font-size: 10px;
    font-weight: 600;
    text-transform: uppercase;
}}

/* ---------- Buttons ---------- */
QPushButton {{
    background-color: {RANALIZ_NAVY_LIGHT};
    color: white;
    border: none;
    border-radius: 8px;
    padding: 5px 12px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: {RANALIZ_NAVY_LIGHTER};
}}
QPushButton:pressed {{
    background-color: {RANALIZ_NAVY};
}}
QPushButton:disabled {{
    background-color: #243447;
    color: #5A6B7D;
}}

QPushButton#PrimaryAction {{
    background-color: {RANALIZ_ACCENT};
    color: {RANALIZ_BG};
    font-size: 12px;
    font-weight: 700;
    border-radius: 8px;
    padding: 5px 14px;
}}
QPushButton#PrimaryAction:hover {{
    background-color: {RANALIZ_ACCENT_DARK};
    color: white;
}}
QPushButton#DangerAction {{
    background-color: {RANALIZ_ERROR};
    color: white;
    border-radius: 8px;
}}
QPushButton#DangerAction:hover {{
    background-color: #DC2626;
}}
QPushButton#SecondaryAction {{
    background-color: transparent;
    color: {RANALIZ_TEXT};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    padding: 4px 10px;
}}
QPushButton#SecondaryAction:hover {{
    border-color: {RANALIZ_ACCENT};
    color: {RANALIZ_ACCENT};
}}

/* ---------- Table ---------- */
QTableWidget {{
    background-color: {RANALIZ_CARD_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 10px;
    gridline-color: {RANALIZ_BORDER};
    selection-background-color: #1A3D36;
    selection-color: {RANALIZ_TEXT};
    alternate-background-color: #121C2C;
    color: {RANALIZ_TEXT};
}}
QHeaderView::section {{
    background-color: {RANALIZ_NAVY};
    color: white;
    padding: 6px;
    border: none;
    border-right: 1px solid {RANALIZ_BORDER};
    font-weight: 600;
    font-size: 11px;
}}
QTableWidget::item {{
    padding: 3px;
}}

/* ---------- Menu bar ---------- */
QMenuBar {{
    background-color: {RANALIZ_NAVY};
    color: white;
    padding: 2px;
}}
QMenuBar::item {{
    padding: 5px 10px;
    background: transparent;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background-color: {RANALIZ_NAVY_LIGHT};
}}
QMenu {{
    background-color: {RANALIZ_CARD_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 10px;
    padding: 4px;
    color: {RANALIZ_TEXT};
}}
QMenu::item {{
    padding: 6px 24px 6px 12px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background-color: {RANALIZ_ACCENT};
    color: {RANALIZ_BG};
}}

/* ---------- Status bar ---------- */
QStatusBar {{
    background-color: {RANALIZ_CARD_BG};
    border-top: 1px solid {RANALIZ_BORDER};
    color: {RANALIZ_TEXT_MUTED};
}}

/* ---------- Scrollbars ---------- */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #3A5168;
    border-radius: 4px;
    min-height: 24px;
}}
QScrollBar::handle:vertical:hover {{
    background: {RANALIZ_ACCENT};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: #3A5168;
    border-radius: 4px;
    min-width: 24px;
}}

/* ---------- Checkbox ---------- */
QCheckBox {{
    spacing: 8px;
    color: {RANALIZ_TEXT};
}}
QCheckBox::indicator {{
    width: 15px;
    height: 15px;
    border-radius: 5px;
    border: 1.5px solid {RANALIZ_BORDER};
    background-color: {RANALIZ_INPUT_BG};
}}
QCheckBox::indicator:checked {{
    background-color: {RANALIZ_ACCENT};
    border-color: {RANALIZ_ACCENT};
}}

/* ---------- Dialogs ---------- */
QDialog {{
    background-color: {RANALIZ_BG};
}}

/* ---------- Text / plain edits ---------- */
QTextEdit, QPlainTextEdit {{
    background-color: {RANALIZ_INPUT_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    color: {RANALIZ_TEXT};
    selection-background-color: {RANALIZ_ACCENT};
}}

/* ---------- List ---------- */
QListWidget {{
    background-color: {RANALIZ_INPUT_BG};
    border: 1px solid {RANALIZ_BORDER};
    border-radius: 8px;
    color: {RANALIZ_TEXT};
}}

/* ---------- Splitter ---------- */
QSplitter::handle {{
    background-color: {RANALIZ_BORDER};
    border-radius: 2px;
}}

/* ---------- Brand footer promo ---------- */
QFrame#BrandFooter {{
    background-color: {RANALIZ_NAVY};
    border-top: 2px solid {RANALIZ_ACCENT};
    min-height: 44px;
    max-height: 52px;
}}
QLabel#BrandFooterTitle {{
    color: #FFFFFF;
    font-size: 12px;
    font-weight: 700;
}}
QLabel#BrandFooterBlurb {{
    color: #9FB4C7;
    font-size: 11px;
}}
QPushButton#BrandFooterLink {{
    background-color: transparent;
    color: {RANALIZ_ACCENT};
    border: 1px solid {RANALIZ_ACCENT};
    border-radius: 8px;
    padding: 4px 12px;
    font-size: 11px;
    font-weight: 700;
}}
QPushButton#BrandFooterLink:hover {{
    background-color: {RANALIZ_ACCENT};
    color: {RANALIZ_BG};
}}
"""
