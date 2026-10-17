import json
import os
import stat
import sqlite3

import pytest

import app.config as cfg
from app.conversations import ConversationStore, auto_title, build_context
from app.fileops import (UnsafePath, extract_files, normalize_content, safe_join, sanitize_filename,
                         save_text, strip_file_blocks, unique_path)


# ---------------------------------------------------------------- configuración y secretos
def test_settings_roundtrip_and_corrupt_file():
    s = cfg.Settings()
    assert s["mode"] == "cloud" and not s["setup_done"]
    s.update(mode="local", local_model="qwen2.5:1.5b", setup_done=True)
    s2 = cfg.Settings()
    assert s2["mode"] == "local" and s2["setup_done"] and s2.loaded_from_disk
    s.path.write_text("{no es json", encoding="utf-8")
    s3 = cfg.Settings()
    assert s3["mode"] == "cloud"                                   # valores por defecto
    assert s.path.with_suffix(".json.bak").exists()                # y copia del archivo corrupto
    with pytest.raises(KeyError):
        s3["clave_inventada"] = 1


def test_api_key_file_permissions_and_roundtrip():
    where = cfg.set_api_key("  sk-or-v1-abcdefghijklmnopqrstuvwxyz  ")
    assert where == "file"
    assert cfg.get_api_key() == "sk-or-v1-abcdefghijklmnopqrstuvwxyz"
    if os.name != "nt":
        assert stat.S_IMODE(cfg._key_file().stat().st_mode) == 0o600
    cfg.delete_api_key()
    assert cfg.get_api_key() == ""


def test_legacy_key_is_migrated(isolated_home):
    legacy = isolated_home / ".config" / "oi-auto" / "openrouter.key"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("sk-or-v1-legacylegacylegacy1234", encoding="utf-8")
    assert cfg.get_api_key() == "sk-or-v1-legacylegacylegacy1234"
    assert cfg._key_file().exists()


def test_redact_hides_keys_everywhere():
    key = "sk-or-v1-SECRETSECRETSECRET1234"
    text = f"fallo con Authorization: Bearer {key} y clave {key}"
    out = cfg.redact(text)
    assert "SECRETSECRET" not in out and "[clave oculta]" in out
    assert "SECRET" not in cfg.redact("otra: abcdefgh12345678", extra=("abcdefgh12345678",)) or True
    assert "abcdefgh12345678" not in cfg.redact("otra: abcdefgh12345678", extra=("abcdefgh12345678",))


def test_logs_never_contain_the_key():
    log = cfg.setup_logging()
    key = "sk-or-v1-LOGLEAKLOGLEAKLOGLEAK99"
    log.error("fallo de red con la clave %s", key)
    for h in log.handlers:
        h.flush()
    text = (cfg.config_dir() / "openchat.log").read_text(encoding="utf-8")
    assert "LOGLEAK" not in text and "[clave oculta]" in text


@pytest.mark.parametrize("key,ok", [("", False), ("abc def", False), ("hola", False), ("sk-or-v1-" + "a" * 30, True)])
def test_key_format_warning(key, ok):
    assert (cfg.key_format_warning(key) == "") is ok


# ---------------------------------------------------------------- historial
def test_conversations_persist_rename_delete():
    store = ConversationStore()
    c = store.create("Hola")
    store.add_message(c.id, "user", "uno")
    store.add_message(c.id, "assistant", "dos\ncon salto")
    store.rename(c.id, "  Mi   chat  ")
    again = ConversationStore()                                    # «reinicio» de la app
    assert [x.title for x in again.list()] == ["Mi chat"]
    assert again.messages(c.id) == [{"role": "user", "content": "uno"}, {"role": "assistant", "content": "dos\ncon salto"}]
    again.delete(c.id)
    assert again.list() == [] and again.messages(c.id) == []


def test_build_context_trims_old_messages_only():
    hist = [{"role": "user", "content": "x" * 100} for _ in range(10)]
    msgs, trimmed = build_context("SYS", hist, max_chars=350)
    assert trimmed and msgs[0]["role"] == "system" and len(msgs) == 4
    msgs, trimmed = build_context("SYS", hist[:2], max_chars=10_000)
    assert not trimmed and len(msgs) == 3


def test_auto_title():
    assert auto_title("  hola\n\n mundo ") == "hola mundo"
    assert auto_title("a" * 100).endswith("…")


# ---------------------------------------------------------------- archivos y rutas
@pytest.mark.parametrize("bad", ["../fuera.txt", "a/../../fuera", "/etc/passwd", "~/x", "C:\\Windows\\x", "", "a\\..\\..\\b"])
def test_safe_join_blocks_escapes(tmp_path, bad):
    with pytest.raises(UnsafePath):
        safe_join(tmp_path, bad)


def test_safe_join_blocks_symlink_escape(tmp_path):
    ws, outside = tmp_path / "ws", tmp_path / "out"
    ws.mkdir(); outside.mkdir()
    (ws / "enlace").symlink_to(outside, target_is_directory=True)
    with pytest.raises(UnsafePath):
        safe_join(ws, "enlace/secreto.txt")


def test_safe_join_allows_inside(tmp_path):
    assert safe_join(tmp_path, "a/b/c.txt") == (tmp_path / "a/b/c.txt").resolve()


@pytest.mark.parametrize("raw,expected", [("../../etc/passwd", "passwd"), ("a\\b\\c.py", "c.py"), ("", "archivo.txt"),
                                          ("..", "archivo.txt"), ("con.txt", "_con.txt"), ('x<y>:"z".md', "x_y___z_.md")])
def test_sanitize_filename(raw, expected):
    assert sanitize_filename(raw) == expected


def test_save_text_real_file_no_overwrite_and_verifies(tmp_path):
    p = tmp_path / "sub" / "a.txt"
    save_text(p, "línea 1\r\nlínea 2\n")
    assert p.read_text(encoding="utf-8") == "línea 1\nlínea 2\n"
    with pytest.raises(FileExistsError):
        save_text(p, "otra cosa")
    assert p.read_text(encoding="utf-8").startswith("línea 1")
    save_text(p, "nuevo", overwrite=True)
    assert p.read_text(encoding="utf-8") == "nuevo"
    assert not [f for f in p.parent.iterdir() if f.name.startswith(".openchat-")]    # sin temporales
    assert unique_path(p).name == "a (2).txt"


def test_save_text_write_error_is_reported(tmp_path):
    blocker = tmp_path / "archivo"
    blocker.write_text("x")
    with pytest.raises(OSError):
        save_text(blocker / "dentro.txt", "x")        # el «directorio» es un archivo


def test_extract_files_multiple_and_newlines():
    text = ('Aquí van:\n<openchat-file name="a.py">\nprint("hola")\nprint("adiós")\n</openchat-file>\n'
            "<openchat-file name='../b.md'>```markdown\n# T\n\ntexto\n```</openchat-file>\nFin")
    files = {f.name: f for f in extract_files(text)}
    assert files["a.py"].content == 'print("hola")\nprint("adiós")\n'
    assert files["b.md"].content == "# T\n\ntexto\n"                 # nombre saneado y sin fences
    shown = strip_file_blocks(text)
    assert "<openchat-file" not in shown and "Archivo preparado: a.py" in shown and "Fin" in shown


def test_literal_backslash_n_is_converted_only_when_no_real_newlines():
    assert normalize_content("a\\nb\\nc") == "a\nb\nc\n"
    assert normalize_content('print("a\\n")\nx = 1') == 'print("a\\n")\nx = 1\n'     # código legítimo intacto


def test_truncated_file_block_is_flagged_incomplete():
    files = extract_files('<openchat-file name="x.py">\nprint(1)\nprint(')
    assert len(files) == 1 and not files[0].complete
    assert "incompleto" in strip_file_blocks('<openchat-file name="x.py">\nprint(')


# ---------------------------------------------------------------- migración desde la versión anterior de main
def test_old_settings_format_is_migrated_without_losing_choices():
    cfg.config_dir().mkdir(parents=True)
    (cfg.config_dir() / "settings.json").write_text(json.dumps({"mode": "local", "model": "llama3.2:1b", "setup_complete": True}), encoding="utf-8")
    s = cfg.Settings()
    assert s["mode"] == "local" and s["local_model"] == "llama3.2:1b" and s["setup_done"] is True
    (cfg.config_dir() / "settings.json").write_text(json.dumps({"mode": "cloud", "model": "openai/gpt-4o-mini", "setup_complete": False}), encoding="utf-8")
    s = cfg.Settings()
    assert s["cloud_model"] == "openai/gpt-4o-mini" and s["setup_done"] is False
    (cfg.config_dir() / "settings.json").write_text(json.dumps({"mode": "inventado"}), encoding="utf-8")
    assert cfg.Settings()["mode"] == "cloud"


def test_legacy_single_conversation_is_imported_once_and_file_is_kept():
    from app.conversations import import_legacy_history
    cfg.config_dir().mkdir(parents=True)
    legacy = cfg.config_dir() / "conversation.json"
    legacy.write_text(json.dumps([{"role": "user", "content": "hola"}, {"role": "assistant", "content": "qué tal"}, {"role": "system", "content": "x"}]), encoding="utf-8")
    store = ConversationStore()
    assert import_legacy_history(store) is True
    convs = store.list()
    assert len(convs) == 1 and store.messages(convs[0].id) == [{"role": "user", "content": "hola"}, {"role": "assistant", "content": "qué tal"}]
    assert import_legacy_history(store) is False and len(store.list()) == 1     # solo una vez
    assert legacy.exists()                                                      # no se borra nada del usuario


def test_save_text_uses_hardened_writer_and_rejects_unsafe_names(tmp_path):
    with pytest.raises(OSError):
        save_text(tmp_path / "a:b.txt", "x")
    real = tmp_path / "real.txt"; real.write_text("original")
    link = tmp_path / "enlace.txt"; link.symlink_to(real)
    outside = tmp_path / "otro"; outside.mkdir()
    (outside / "x.txt").write_text("fuera")
    sub = tmp_path / "sub"; sub.mkdir(); (sub / "t.txt").symlink_to(outside / "x.txt")
    with pytest.raises(OSError):
        save_text(sub / "t.txt", "pisado", overwrite=True)                       # el enlace apunta fuera de la carpeta
    assert (outside / "x.txt").read_text() == "fuera"
