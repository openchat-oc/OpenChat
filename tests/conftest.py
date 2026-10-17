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
