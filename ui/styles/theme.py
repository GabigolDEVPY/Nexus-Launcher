"""
Tema QSS completo do NexusLauncher — estilo escuro, console, PS4/Steam.
"""

from core.constants import FONT_DISPLAY, FONT_BODY

STYLESHEET = f"""
/* ===== GLOBAL ===== */
QWidget {{
    background-color: #0d0d0d;
    color: #e8e4dc;
    font-family: '{FONT_BODY}', 'Consolas', monospace;
    font-size: 13px;
}}

/* ===== SCROLLBARS ===== */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #333;
    border-radius: 4px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: #555;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
}}
QScrollBar::handle:horizontal {{
    background: #333;
    border-radius: 4px;
    min-width: 40px;
}}
QScrollBar::handle:horizontal:hover {{
    background: #555;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ===== BUTTONS ===== */
QPushButton {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 10px 24px;
    font-size: 13px;
    font-weight: 600;
}}
QPushButton:hover {{
    background-color: #252525;
    border-color: #1EA1FF;
}}
QPushButton:pressed {{
    background-color: #1EA1FF;
    color: #0d0d0d;
}}
QPushButton#playButton {{
    background-color: #22c55e;
    background: #22c55e;
    color: #08110b;
    font-size: 16px;
    font-weight: bold;
    border: 2px solid #16a34a;
    border-radius: 8px;
    padding: 14px 48px;
    letter-spacing: 2px;
}}
QPushButton#playButton:hover {{
    background-color: #4ade80;
    background: #4ade80;
    border-color: #22c55e;
}}
QPushButton#playButton:pressed {{
    background-color: #16a34a;
    background: #16a34a;
    color: #f7fff9;
}}
QPushButton#playButton:disabled {{
    background-color: #14532d;
    background: #14532d;
    color: #d1fae5;
    border: 2px solid #166534;
}}
QPushButton#favoriteButton {{
    background: transparent;
    border: none;
    font-size: 20px;
    padding: 4px;
}}
QPushButton#favoriteButton:hover {{
    color: #1EA1FF;
}}

/* ===== LABELS ===== */
QLabel {{
    background: transparent;
    border: none;
}}
QLabel#gameTitle {{
    font-family: '{FONT_DISPLAY}', 'Impact', sans-serif;
    font-size: 42px;
    font-weight: bold;
    color: #ffffff;
    letter-spacing: 1px;
}}
QLabel#gameGenre {{
    font-size: 12px;
    color: #1EA1FF;
    letter-spacing: 2px;
    text-transform: uppercase;
}}
QLabel#gameDescription {{
    font-size: 13px;
    color: #aaa;
    line-height: 1.5;
}}
QLabel#playtimeLabel {{
    font-size: 14px;
    color: #888;
}}
QLabel#syncStatusLabel {{
    font-size: 12px;
    color: #5a9;
}}
QLabel#sidebarTitle {{
    font-family: '{FONT_DISPLAY}', sans-serif;
    font-size: 28px;
    color: #1EA1FF;
    letter-spacing: 3px;
}}

/* ===== LINE EDIT ===== */
QLineEdit {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 10px 14px;
    font-size: 13px;
    selection-background-color: #1EA1FF;
    selection-color: #ffffff;
}}
QLineEdit:focus {{
    border-color: #1EA1FF;
}}
QLineEdit::placeholder {{
    color: #555;
}}

/* ===== TEXT EDIT ===== */
QTextEdit, QPlainTextEdit {{
    background-color: #141414;
    color: #ccc;
    border: 1px solid #2a2a2a;
    border-radius: 6px;
    padding: 8px;
    font-size: 12px;
}}

/* ===== COMBO BOX ===== */
QComboBox {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
}}
QComboBox:hover {{
    border-color: #1EA1FF;
}}
QComboBox::drop-down {{
    border: none;
    width: 30px;
}}
QComboBox QAbstractItemView {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    selection-background-color: #1EA1FF;
    selection-color: #ffffff;
    border: 1px solid #333;
}}

/* ===== CHECKBOX ===== */
QCheckBox {{
    spacing: 8px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid #444;
    background: #1a1a1a;
}}
QCheckBox::indicator:checked {{
    background: #1EA1FF;
    border-color: #1EA1FF;
}}

/* ===== TAB WIDGET ===== */
QTabWidget::pane {{
    border: 1px solid #2a2a2a;
    background: #0d0d0d;
}}
QTabBar::tab {{
    background: #1a1a1a;
    color: #888;
    padding: 10px 20px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: #1EA1FF;
    border-bottom: 2px solid #1EA1FF;
}}
QTabBar::tab:hover {{
    color: #fff;
}}

/* ===== GROUP BOX ===== */
QGroupBox {{
    border: 1px solid #2a2a2a;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 20px;
    font-weight: bold;
    color: #1EA1FF;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    padding: 0 10px;
}}

/* ===== SPIN BOX ===== */
QSpinBox {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    border: 1px solid #333;
    border-radius: 6px;
    padding: 6px 10px;
}}

/* ===== DIALOG ===== */
QDialog {{
    background-color: #0d0d0d;
}}

/* ===== MENU ===== */
QMenu {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    border: 1px solid #333;
    padding: 4px;
}}
QMenu::item {{
    padding: 8px 30px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background-color: #1EA1FF;
    color: #ffffff;
}}

/* ===== TOOLTIP ===== */
QToolTip {{
    background-color: #1a1a1a;
    color: #e8e4dc;
    border: 1px solid #1EA1FF;
    padding: 6px;
    font-size: 12px;
}}

/* ===== PROGRESS BAR ===== */
QProgressBar {{
    background-color: #1a1a1a;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}}
QProgressBar::chunk {{
    background-color: #1EA1FF;
    border-radius: 4px;
}}
"""
