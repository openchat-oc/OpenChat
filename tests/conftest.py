import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    """Cada prueba usa su propio directorio de datos: nunca toca la configuración real."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("OPENCHAT_HOME", str(home / "oc"))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    import app.config as cfg
    monkeypatch.setattr(cfg, "_keyring", lambda: None)   # sin llavero del sistema en pruebas
    return home


# ---------------------------------------------------------------- utilidades Qt compartidas
import time


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    from app.ui.theme import QSS
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    return app


@pytest.fixture(autouse=True)
def close_windows(request):
    """Cierra toda ventana que una prueba deje abierta (evita diálogos huérfanos en la siguiente)."""
    yield
    if "qapp" in request.fixturenames:
        from PySide6.QtCore import QEvent
        from PySide6.QtWidgets import QApplication
        for w in QApplication.topLevelWidgets():
            w.close(); w.deleteLater()
        QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)


def pump(qapp, cond, timeout=6.0):
    end = time.time() + timeout
    while time.time() < end:
        qapp.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    return False
