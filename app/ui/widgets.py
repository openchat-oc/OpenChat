"""Widgets reutilizables del chat."""
from __future__ import annotations

from PySide6.QtCore import QEvent, QSize, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QDesktopServices, QFontMetrics, QGuiApplication
from PySide6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QPlainTextEdit, QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .chispa import ChispaWidget
from .markdown import md_to_html, split_blocks

THINKING = "OpenChat está pensando"


class ChatInput(QPlainTextEdit):
    """Intro envía · Mayús+Intro (o Alt+Intro) salto de línea · crece con el texto."""
    submitted = Signal()
    MIN_H, MAX_H = 54, 180

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setTabChangesFocus(False)
        self.setAccessibleName("Escribe tu mensaje")
        self.setPlaceholderText("Escribe lo que necesitas…   ·   Intro envía · Mayús+Intro nueva línea")
        self.document().contentsChanged.connect(self._fit)
        self._fit()

    def keyPressEvent(self, e) -> None:
        if e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if e.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
                self.insertPlainText("\n")
            else:
                self.submitted.emit()
            e.accept()
            return
        super().keyPressEvent(e)

    def insertFromMimeData(self, source) -> None:      # siempre texto plano
        if source.hasText():
            self.insertPlainText(source.text().replace("\r\n", "\n"))

    def _fit(self) -> None:
        h = int(self.document().size().height()) + 22
        self.setFixedHeight(max(self.MIN_H, min(self.MAX_H, h)))


class CodeBlock(QFrame):
    def __init__(self, lang: str, code: str, parent=None):
        super().__init__(parent)
        self.setObjectName("codeBlock")
        lay = QVBoxLayout(self); lay.setContentsMargins(10, 6, 10, 8); lay.setSpacing(4)
        top = QHBoxLayout()
        self.lang = QLabel(lang or "código"); self.lang.setProperty("muted", True)
        self.copy_btn = QPushButton("Copiar"); self.copy_btn.setObjectName("flat")
        self.copy_btn.setAccessibleName("Copiar bloque de código")
        self.copy_btn.clicked.connect(self._copy)
        top.addWidget(self.lang); top.addStretch(); top.addWidget(self.copy_btn); lay.addLayout(top)
        self.edit = QPlainTextEdit(); self.edit.setObjectName("code"); self.edit.setReadOnly(True)
        self.edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.edit.document().setDocumentMargin(2)
        self.edit.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        lay.addWidget(self.edit)
        self.set_code(lang, code)

    def set_code(self, lang: str, code: str) -> None:
        self.lang.setText(lang or "código")
        if self.edit.toPlainText() != code:
            self.edit.setPlainText(code)
        lines = max(1, code.count("\n") + 1)
        fm = QFontMetrics(self.edit.font())
        self.edit.setFixedHeight(min(lines, 26) * fm.lineSpacing() + 24)

    def code(self) -> str:
        return self.edit.toPlainText()

    def _copy(self) -> None:
        QGuiApplication.clipboard().setText(self.code())
        self.copy_btn.setText("¡Copiado!")
        QTimer.singleShot(1400, lambda: self.copy_btn.setText("Copiar"))


def _open_link(url: str) -> None:
    if url.startswith(("http://", "https://")):          # nunca file:, javascript:, etc.
        QDesktopServices.openUrl(QUrl(url))


class MessageBubble(QFrame):
    """Un mensaje. ``set_text`` es incremental: sirve para el streaming sin reconstruir todo."""
    save_requested = Signal(str)

    def __init__(self, role: str, text: str = "", parent=None):
        super().__init__(parent)
        self.role = role
        self.setObjectName({"user": "userBubble", "assistant": "botBubble", "notice": "noticeBubble", "error": "errorBubble"}.get(role, "botBubble"))
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        self._text = ""
        self._segments: list[tuple[str, QWidget]] = []
        self.body = QVBoxLayout(self); self.body.setContentsMargins(16, 12, 16, 10); self.body.setSpacing(6)
        if role in ("user", "assistant"):
            name = QLabel("TÚ" if role == "user" else "✦  OPENCHAT")
            name.setStyleSheet(f"font-size:10px;font-weight:800;letter-spacing:1px;color:{'#8fd9c0' if role == 'user' else '#aaa0ff'};background:transparent;border:0")
            self.body.addWidget(name)
        self.actions: QHBoxLayout | None = None
        self.set_text(text)
        if role == "assistant":
            self._add_actions()

    def _add_actions(self) -> None:
        row = QHBoxLayout(); row.addStretch()
        copy = QPushButton("Copiar"); copy.setObjectName("flat"); copy.setAccessibleName("Copiar respuesta")
        copy.clicked.connect(lambda: QGuiApplication.clipboard().setText(self._text))
        save = QPushButton("Guardar…"); save.setObjectName("flat"); save.setAccessibleName("Guardar respuesta en un archivo")
        save.clicked.connect(lambda: self.save_requested.emit(self._text))
        row.addWidget(copy); row.addWidget(save)
        self.actions_widget = QWidget(); self.actions_widget.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        self.body.addWidget(self.actions_widget)

    def text(self) -> str:
        return self._text

    def set_text(self, text: str) -> None:
        self._text = text
        blocks = split_blocks(text) if self.role != "user" else [("text", "", text)]
        if self.role == "user":
            blocks = [("plain", "", text)]
        insert_at = 1 if self.role in ("user", "assistant") else 0
        # reutiliza los widgets existentes mientras coincida el tipo; solo crea/elimina el sobrante
        for i, (kind, lang, content) in enumerate(blocks):
            if i < len(self._segments) and self._segments[i][0] == kind:
                w = self._segments[i][1]
            else:
                if i < len(self._segments):
                    self._drop_from(i)
                w = self._make(kind)
                self.body.insertWidget(insert_at + i, w)
                self._segments.append((kind, w))
            self._fill(kind, w, lang, content)
        if len(self._segments) > len(blocks):
            self._drop_from(len(blocks))

    def _drop_from(self, i: int) -> None:
        for _k, w in self._segments[i:]:
            self.body.removeWidget(w); w.deleteLater()
        del self._segments[i:]

    def _make(self, kind: str) -> QWidget:
        if kind == "code":
            return CodeBlock("", "")
        lab = QLabel(); lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse | Qt.TextInteractionFlag.LinksAccessibleByMouse)
        lab.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Minimum)
        lab.setStyleSheet("background:transparent;border:0")
        if kind == "plain":
            lab.setTextFormat(Qt.TextFormat.PlainText)
        else:
            lab.setTextFormat(Qt.TextFormat.RichText)
            lab.linkActivated.connect(_open_link)
            lab.setOpenExternalLinks(False)
        return lab

    def _fill(self, kind: str, w: QWidget, lang: str, content: str) -> None:
        if kind == "code":
            w.set_code(lang, content)          # type: ignore[attr-defined]
        elif kind == "plain":
            if w.text() != content:            # type: ignore[attr-defined]
                w.setText(content)             # type: ignore[attr-defined]
        else:
            html_ = md_to_html(content)
            if w.property("html") != html_:
                w.setText(html_); w.setProperty("html", html_)   # type: ignore[attr-defined]


class ToolCard(QFrame):
    """Línea de actividad del agente: qué herramienta se usó y con qué resultado."""
    def __init__(self, text: str, state: str = "run", parent=None):
        super().__init__(parent)
        self.setObjectName("toolCard")
        lay = QHBoxLayout(self); lay.setContentsMargins(12, 7, 12, 7)
        self.icon = QLabel("⚙"); self.label = QLabel(text); self.label.setWordWrap(True)
        self.label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        for w in (self.icon, self.label):
            w.setStyleSheet("background:transparent;border:0")
        lay.addWidget(self.icon); lay.addWidget(self.label, 1)

    def finish(self, ok: bool, summary: str) -> None:
        self.icon.setText("✓" if ok else "✗")
        self.icon.setStyleSheet(f"background:transparent;border:0;color:{'#86e0bd' if ok else '#ff8f9d'}")
        self.label.setText(summary)


class TypingRow(QWidget):
    """«OpenChat está pensando» con puntos animados. Se detiene al ocultarse o destruirse."""
    def __init__(self, parent=None):
        super().__init__(parent)
        lay = QHBoxLayout(self); lay.setContentsMargins(4, 4, 4, 4); lay.setSpacing(10)
        self.chispa = ChispaWidget(38, "thinking")
        self.label = QLabel(THINKING); self.label.setStyleSheet("color:#aaa0ff;font-weight:650")
        self.dots = QLabel("○ ○ ○"); self.dots.setStyleSheet("color:#9383ff;letter-spacing:2px")
        lay.addWidget(self.chispa); lay.addWidget(self.label); lay.addWidget(self.dots); lay.addStretch()
        self._n = 0
        self.timer = QTimer(self); self.timer.setInterval(380); self.timer.timeout.connect(self._tick)
        self.setAccessibleName(THINKING)

    def start(self) -> None:
        self._n = 0; self.timer.start(); self._tick()

    def stop(self) -> None:
        self.timer.stop()

    def set_state(self, text: str) -> None:
        self.label.setText(text or THINKING)

    def _tick(self) -> None:
        self._n = (self._n + 1) % 4
        self.dots.setText(" ".join(["●"] * self._n + ["○"] * (3 - self._n)))

    def hideEvent(self, e) -> None:
        self.timer.stop(); super().hideEvent(e)
