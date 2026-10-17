"""Paleta y hoja de estilos (oscuro, morado/azul, coherente con el logo de OpenChat)."""

BG = "#14151b"
SURFACE = "#1b1c24"
SURFACE2 = "#232530"
BORDER = "#31333f"
TEXT = "#ececf5"
MUTED = "#9b9db2"
ACCENT = "#8875ee"
ACCENT_HI = "#a092ff"
CYAN = "#25c7e8"
GREEN = "#86e0bd"
RED = "#ff8f9d"
AMBER = "#f2c46d"

QSS = f"""
QWidget {{ font-family: 'Noto Sans','Inter','Segoe UI',sans-serif; font-size: 14px; color: {TEXT}; }}
QMainWindow, QDialog, #root {{ background: {BG}; }}
#sidebar {{ background: {SURFACE}; border-right: 1px solid {BORDER}; }}
#header, #bottom {{ background: {SURFACE}; }}
#header {{ border-bottom: 1px solid {BORDER}; }}
#bottom {{ border-top: 1px solid {BORDER}; }}
#chatArea, #column {{ background: {BG}; }}
QScrollArea {{ border: 0; background: {BG}; }}
QLabel#muted, QLabel[muted="true"] {{ color: {MUTED}; font-size: 12px; }}
QLabel#h1 {{ font-size: 24px; font-weight: 800; }}
QLabel#section {{ color: {MUTED}; font-size: 11px; font-weight: 700; letter-spacing: 1px; }}
QPushButton {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 10px; padding: 8px 12px; font-weight: 600; }}
QPushButton:hover {{ background: #34324a; border-color: #6f68a4; }}
QPushButton:focus {{ border-color: {ACCENT_HI}; }}
QPushButton:disabled {{ background: #1f2028; color: #6a6c7d; border-color: #2a2c36; }}
QPushButton#primary, QPushButton#send {{ background: {ACCENT}; border: 0; color: white; }}
QPushButton#primary:hover, QPushButton#send:hover {{ background: {ACCENT_HI}; }}
QPushButton#primary:disabled, QPushButton#send:disabled {{ background: #433e66; color: #a9a4c8; }}
QPushButton#danger {{ background: #4a2a33; border-color: #7b3b49; }}
QPushButton#flat {{ background: transparent; border: 0; padding: 6px; }}
QPushButton#flat:hover {{ background: {SURFACE2}; }}
QPushButton#chip {{ background: {SURFACE}; border-radius: 14px; padding: 8px 14px; font-weight: 500; }}
QLineEdit, QPlainTextEdit, QTextEdit, QComboBox {{ background: {SURFACE2}; border: 1px solid {BORDER}; border-radius: 12px; padding: 9px 11px; selection-background-color: #6556b4; }}
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus {{ border: 1px solid {ACCENT_HI}; }}
QComboBox::drop-down {{ border: 0; width: 22px; }}
QComboBox QAbstractItemView {{ background: {SURFACE2}; border: 1px solid {BORDER}; selection-background-color: #45405f; }}
QListWidget {{ background: transparent; border: 0; outline: 0; }}
QListWidget::item {{ padding: 9px 10px; border-radius: 9px; }}
QListWidget::item:hover {{ background: {SURFACE2}; }}
QListWidget::item:selected {{ background: #3a3556; color: white; }}
QFrame#userBubble {{ background: #2a2c3a; border: 1px solid #3a3d50; border-radius: 16px; }}
QFrame#botBubble {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 16px; }}
QFrame#noticeBubble {{ background: #2b2740; border: 1px dashed #5b5290; border-radius: 12px; }}
QFrame#errorBubble {{ background: #33232b; border: 1px solid #7b3b49; border-radius: 12px; }}
QFrame#toolCard {{ background: #1c2230; border: 1px solid #2e3d57; border-radius: 10px; }}
QFrame#codeBlock {{ background: #101117; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#filesPanel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#banner {{ background: #2b2740; border: 1px solid #5b5290; border-radius: 10px; }}
QPlainTextEdit#code {{ background: transparent; border: 0; padding: 4px; font-family: 'JetBrains Mono','Fira Code','DejaVu Sans Mono',monospace; font-size: 13px; }}
QProgressBar {{ background: {SURFACE2}; border: 0; border-radius: 6px; height: 10px; text-align: center; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 6px; }}
QCheckBox {{ spacing: 8px; }}
QToolTip {{ background: {SURFACE2}; color: {TEXT}; border: 1px solid {BORDER}; }}
"""

QSS += f"""
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: #3a3d4e; border-radius: 4px; min-height: 36px; }}
QScrollBar::handle:vertical:hover {{ background: #55597a; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: #3a3d4e; border-radius: 4px; min-width: 36px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""
