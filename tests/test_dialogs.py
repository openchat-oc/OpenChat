import app.config as cfg
from app.agent import PermissionPolicy, build_registry
from app.ui import dialogs
from app.ui.dialogs import FileEditorDialog, PermissionDialog, SettingsDialog


def test_editor_creates_edits_and_overwrites_only_the_open_file(qapp, tmp_path):
    d = FileEditorDialog(None, "nota.md", "# Hola\n", tmp_path)
    d.edit.setPlainText("# Hola\nsegunda línea\n")
    d._write(tmp_path / "nota.md", overwrite=False)
    assert (tmp_path / "nota.md").read_text(encoding="utf-8") == "# Hola\nsegunda línea\n" and d.saved_path == tmp_path / "nota.md"
    assert "Guardado y verificado" in d.status.text()
    d.edit.setPlainText("versión editada\n"); d.save()                        # ya hay un archivo asociado: se actualiza ese
    assert (tmp_path / "nota.md").read_text(encoding="utf-8") == "versión editada\n"


def test_editor_keeps_content_when_saving_fails(qapp, tmp_path, monkeypatch):
    shown = []
    monkeypatch.setattr(dialogs.QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    blocker = tmp_path / "archivo"; blocker.write_text("x")
    d = FileEditorDialog(None, "a.txt", "contenido importante", tmp_path)
    d._write(blocker / "a.txt", overwrite=False)
    assert shown and d.content() == "contenido importante" and d.saved_path is None and "No se pudo guardar" in d.status.text()


def test_permission_dialog_defaults_to_deny_and_returns_choices(qapp, tmp_path):
    spec = build_registry()["write_file"]
    dec = PermissionPolicy(tmp_path, "ask").decide(spec, {"path": "a.txt", "content": "x"})
    d = PermissionDialog(None, "write_file", {"path": "a.txt", "content": "x" * 900}, dec)
    d.reject(); assert d.answer == "deny"
    d2 = PermissionDialog(None, "write_file", {"path": "a.txt", "content": "x"}, dec)
    d2._set("session"); assert d2.answer == "session"
    destructive = PermissionPolicy(tmp_path, "ask").decide(build_registry()["delete_file"], {"path": "a.txt"})
    assert destructive.key == ""                                              # no hay «permitir durante la tarea» para borrar
    assert PermissionDialog(None, "delete_file", {"path": "a.txt"}, destructive).answer == "deny"


def test_settings_dialog_persists_choices(qapp, tmp_path):
    s = cfg.Settings(); d = SettingsDialog(None, s, False, "")
    d.auto_update.setChecked(False); d.fallback.setChecked(True)
    d.workspace.setText(str(tmp_path / "ws")); d.perm.setCurrentIndex(d.perm.findData("auto_edits")); d._save()
    s2 = cfg.Settings()
    assert (s2["auto_update_check"], s2["fallback_to_local"], s2["agent_permission"], s2["workspace"]) == (False, True, "auto_edits", str(tmp_path / "ws"))


class FakeKeyring:
    def __init__(self): self.store = {}
    def set_password(self, svc, user, pw): self.store[(svc, user)] = pw
    def get_password(self, svc, user): return self.store.get((svc, user))
    def delete_password(self, svc, user): self.store.pop((svc, user), None)


def test_api_key_prefers_system_keyring_when_available(monkeypatch):
    fk = FakeKeyring(); monkeypatch.setattr(cfg, "_keyring", lambda: fk)
    cfg.config_dir().mkdir(parents=True); cfg._key_file().write_text("sk-or-v1-viejaenarchivo0000", encoding="utf-8")
    assert cfg.set_api_key("sk-or-v1-nuevaenllavero1111") == "keyring"
    assert not cfg._key_file().exists()                                       # no queda copia en texto plano
    assert cfg.get_api_key() == "sk-or-v1-nuevaenllavero1111"
    cfg.delete_api_key(); assert cfg.get_api_key() == "" and fk.store == {}


def test_keyring_failure_falls_back_to_private_file(monkeypatch):
    class Broken(FakeKeyring):
        def set_password(self, *a): raise RuntimeError("sin servicio de secretos")
    monkeypatch.setattr(cfg, "_keyring", lambda: Broken())
    assert cfg.set_api_key("sk-or-v1-fallback000000000") == "file" and cfg.get_api_key() == "sk-or-v1-fallback000000000"
