"""Chispa, la mascota de OpenChat (no es la IA). Dibujada con QPainter: ligera y sin recursos externos."""
from __future__ import annotations

import math
import os
import time

from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QLinearGradient, QPainter, QPainterPath, QPen, QRadialGradient
from PySide6.QtWidgets import QWidget

STATES = ("idle", "wave", "thinking", "happy", "error")


def reduced_motion() -> bool:
    return os.environ.get("OPENCHAT_REDUCE_MOTION", "") not in ("", "0", "false")


class ChispaWidget(QWidget):
    def __init__(self, size: int = 96, state: str = "idle", parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._state = state
        self._t0 = time.monotonic()
        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.update)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAccessibleName("Chispa, la mascota de OpenChat")
        self._sync_timer()

    # el temporizador solo corre mientras el widget es visible: cero consumo si no se ve
    def showEvent(self, e):
        self._sync_timer(); super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop(); super().hideEvent(e)

    def _sync_timer(self) -> None:
        if self.isVisible() and not reduced_motion():
            self._timer.start()

    def state(self) -> str:
        return self._state

    def set_state(self, state: str) -> None:
        if state in STATES and state != self._state:
            self._state = state
            self._t0 = time.monotonic()
            self.update()

    def is_animating(self) -> bool:
        return self._timer.isActive()

    def paintEvent(self, _e) -> None:
        t = 0.0 if reduced_motion() else time.monotonic() - self._t0
        s = min(self.width(), self.height())
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.scale(s / 100.0, s / 100.0)
        st = self._state
        bob = math.sin(t * (6 if st == "happy" else 2.2)) * (4 if st == "happy" else 2)
        p.translate(0, bob)

        glow = QRadialGradient(QPointF(50, 58), 46)
        pulse = 0.5 + 0.5 * math.sin(t * (5 if st == "thinking" else 1.6))
        glow.setColorAt(0, QColor(136, 117, 238, int(60 + 60 * pulse)))
        glow.setColorAt(1, QColor(136, 117, 238, 0))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(glow))
        p.drawEllipse(QPointF(50, 58), 46, 46)

        body = QLinearGradient(20, 26, 80, 90)
        body.setColorAt(0, QColor("#a98af8"))
        body.setColorAt(1, QColor("#28c8e9") if st != "error" else QColor("#8b86a8"))
        p.setBrush(QBrush(body))
        path = QPainterPath()
        path.addRoundedRect(QRectF(20, 32, 60, 52), 24, 24)
        p.drawPath(path)

        # ojos (◕): parpadeo cada ~3,5 s
        blink = 1.0
        if st != "thinking" and (t % 3.5) > 3.35:
            blink = 0.12
        look = math.sin(t * 1.3) * 2 if st == "thinking" else 0
        for cx in (38, 62):
            p.setBrush(QColor("#1a1530"))
            p.drawEllipse(QPointF(cx + look, 56), 6.2, 7.2 * blink)
            if blink > 0.5:
                p.setBrush(QColor("white"))
                p.drawEllipse(QPointF(cx + look + 2, 53.5), 2.1, 2.1)

        pen = QPen(QColor("#1a1530"), 2.6, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        if st == "error":
            p.drawArc(QRectF(43, 70, 14, 8), 20 * 16, 140 * 16)      # boca triste
        elif st == "happy":
            p.setBrush(QColor("#1a1530")); p.drawChord(QRectF(40, 64, 20, 16), 200 * 16, 140 * 16)
        else:
            p.drawArc(QRectF(43, 64, 14, 10), 200 * 16, 140 * 16)    # sonrisa
        p.setPen(Qt.PenStyle.NoPen)

        if st == "wave":                                             # saludo con una manita
            ang = math.sin(t * 7) * 18
            p.save(); p.translate(84, 56); p.rotate(ang)
            p.setBrush(QColor("#c9bcff")); p.drawEllipse(QPointF(0, -8), 6, 9); p.restore()

        # chispa de la cabeza (misma estrella de cuatro puntas del logo)
        spin = t * (240 if st == "thinking" else 40)
        scale = 1.0 + (0.18 * pulse if st != "error" else -0.3)
        p.save(); p.translate(50, 18); p.rotate(spin if st == "thinking" else math.sin(t * 2) * 12); p.scale(scale, scale)
        star = QPainterPath()
        star.moveTo(0, -13); star.lineTo(3.4, -3.4); star.lineTo(13, 0); star.lineTo(3.4, 3.4)
        star.lineTo(0, 13); star.lineTo(-3.4, 3.4); star.lineTo(-13, 0); star.lineTo(-3.4, -3.4); star.closeSubpath()
        p.setBrush(QColor("#ffffff" if st != "error" else "#bdb8d6")); p.drawPath(star); p.restore()
        p.end()
