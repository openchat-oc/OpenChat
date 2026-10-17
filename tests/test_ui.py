"""Pruebas de interfaz con Qt «offscreen» y un servidor Ollama falso real (sin mocks de widgets)."""
import json
import time
from pathlib import Path

import pytest
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QLineEdit

import app.ui.main_window as mw
from app import config
from app.providers import OllamaProvider
from app.ui.chispa import ChispaWidget
from app.ui.theme import QSS
from app.ui.widgets import THINKING, ChatInput, MessageBubble
from tests.fakeserver import make_server, send_json



@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance() or QApplication([])
    app.setStyleSheet(QSS)
    return app


@pytest.fixture(autouse=True)
def close_windows(qapp):
    yield
    for w in qapp.topLevelWidgets():
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


class FakeOllama:
    def __init__(self, reply, delay=0.0, fail=False):
        self.reply, self.delay, self.fail, self.bodies = reply, delay, fail, []
        def tags(h, body): send_json(h, 200, {"models": [{"name": "qwen2.5:1.5b"}]})
        def chat(h, body):
            self.bodies.append(body)
            if self.fail:
                send_json(h, 500, {"error": "boom"}); return
            h.send_response(200); h.end_headers()
            try:
                for i in range(0, len(self.reply), 5):
                    h.wfile.write(json.dumps({"message": {"content": self.reply[i:i + 5]}, "done": False}).encode() + b"\n"); h.wfile.flush()
                    time.sleep(self.delay)
                h.wfile.write(json.dumps({"message": {"content": ""}, "done": True}).encode() + b"\n")
            except (BrokenPipeError, ConnectionResetError):
                pass
        self.srv, self.url = make_server({("GET", "/api/tags"): tags, ("POST", "/api/chat"): chat})


@pytest.fixture
def window(qapp, monkeypatch, tmp_path):
    fake = {}
    def build(reply="Hola desde el modelo", delay=0.0, fail=False, **settings):
        f = FakeOllama(reply, delay, fail); fake["f"] = f
        monkeypatch.setattr(mw, "OllamaProvider", lambda: OllamaProvider(base=f.url))
        monkeypatch.setattr(mw.updater, "check_for_update", lambda *a, **k: mw.updater.UpdateResult("up_to_date", "1.1.0"))
        s = config.Settings()
        s.update(setup_done=True, mode="local", local_model="qwen2.5:1.5b", workspace=str(tmp_path / "ws"), **settings)
        w = mw.MainWindow(s); w.resize(1000, 700); w.show(); qapp.processEvents()
        w._test_fake = f
        return w
    yield build
    if "f" in fake:
        fake["f"].srv.shutdown()


def type_and_send(qapp, w, text):
    w.input.setPlainText(text)
    QTest.keyClick(w.input, Qt.Key.Key_Return)


def test_enter_sends_and_streams_response_then_indicator_stops(qapp, window):
    w = window(reply="Línea uno\nLínea dos con **negrita**", delay=0.02)
    w.input.setFocus()
    type_and_send(qapp, w, "hola")
    assert w.worker is not None and w.stop_btn.isVisible() and not w.send_btn.isVisible()
    assert pump(qapp, lambda: w.typing is not None), "debe aparecer «OpenChat está pensando»"
    assert w.typing.label.text() == THINKING and w.typing.timer.isActive()
    assert pump(qapp, lambda: w.worker is None)
    assert w.typing is None and w.send_btn.isVisible() and not w.stop_btn.isVisible()
    bubbles = w.findChildren(MessageBubble)
    assert [b.role for b in bubbles] == ["user", "assistant"]
    assert bubbles[1].text() == "Línea uno\nLínea dos con **negrita**"
    assert "<b>negrita</b>" in bubbles[1]._segments[0][1].text() and "<br>" in bubbles[1]._segments[0][1].text()   # salto real, sin «\n» literal
    assert w.history[-1]["content"].startswith("Línea uno")
    assert w._test_fake.bodies[0]["model"] == "qwen2.5:1.5b"                  # el modelo mostrado es el usado
    assert w._test_fake.bodies[0]["messages"][-1] == {"role": "user", "content": "hola"}


def test_shift_enter_inserts_newline_and_empty_message_is_ignored(qapp, window):
    w = window()
    w.input.setPlainText("a"); w.input.moveCursor(w.input.textCursor().MoveOperation.End)
    QTest.keyClick(w.input, Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    QTest.keyClicks(w.input, "b")
    assert w.input.toPlainText() == "a\nb" and w.worker is None
    w.input.clear(); QTest.keyClick(w.input, Qt.Key.Key_Return); w.send_btn.click()
    assert w.worker is None and w.findChildren(MessageBubble) == []
    w.input.setPlainText("   \n  "); w.send_message()
    assert w.worker is None


def test_double_send_while_generating_is_ignored(qapp, window):
    w = window(reply="x" * 200, delay=0.05)
    type_and_send(qapp, w, "uno")
    first = w.worker
    w.input.setPlainText("dos"); w.send_message()
    assert w.worker is first and len([b for b in w.findChildren(MessageBubble) if b.role == "user"]) == 1
    w.cancel_generation(); assert pump(qapp, lambda: w.worker is None)


def test_cancel_stops_generation_and_keeps_partial_without_zombie_indicator(qapp, window):
    w = window(reply="palabra " * 80, delay=0.05)
    type_and_send(qapp, w, "cuenta")
    assert pump(qapp, lambda: w.stream_bubble is not None and len(w.stream_bubble.text()) > 10)
    t0 = time.time(); w.cancel_generation()
    assert pump(qapp, lambda: w.worker is None, 3) and time.time() - t0 < 2.5
    assert w.typing is None and w.send_btn.isVisible()
    assert w.history[-1]["role"] == "assistant" and 0 < len(w.history[-1]["content"]) < 640
    assert any("cancelada" in b.text() for b in w.findChildren(MessageBubble) if b.role == "notice")


def test_failure_restores_draft_and_does_not_duplicate_history(qapp, window):
    w = window(fail=True)
    type_and_send(qapp, w, "mensaje importante\ncon dos líneas")
    assert pump(qapp, lambda: w.worker is None)
    assert w.input.toPlainText() == "mensaje importante\ncon dos líneas"        # el texto no se pierde
    assert w.history == [] and w.store.messages(w.conv_id) == []
    errs = [b for b in w.findChildren(MessageBubble) if b.role == "error"]
    assert errs and "Ollama" in errs[0].text()
    assert w.typing is None


def test_failure_with_unreachable_ollama_has_clear_message(qapp, window, monkeypatch):
    w = window()
    monkeypatch.setattr(mw, "OllamaProvider", lambda: OllamaProvider(base="http://127.0.0.1:9"))
    type_and_send(qapp, w, "hola")
    assert pump(qapp, lambda: w.worker is None)
    assert any("no responde" in b.text() for b in w.findChildren(MessageBubble) if b.role == "error")


def test_generated_files_are_listed_saved_for_real_and_never_overwritten(qapp, window, tmp_path):
    reply = 'Listo:\n<openchat-file name="hola.py">\nprint("hola")\nprint("adiós")\n</openchat-file>\n<openchat-file name="notas.md">\n# Notas\n</openchat-file>'
    w = window(reply=reply)
    type_and_send(qapp, w, "crea archivos")
    assert pump(qapp, lambda: w.worker is None)
    assert set(w.generated) == {"hola.py", "notas.md"} and w.files_panel.isVisible()
    shown = [b for b in w.findChildren(MessageBubble) if b.role == "assistant"][0].text()
    assert "<openchat-file" not in shown and "Archivo preparado" in shown
    dest = tmp_path / "salida" / "hola.py"
    assert w._save_to(dest, "hola.py", w.generated["hola.py"])
    assert dest.read_text(encoding="utf-8") == 'print("hola")\nprint("adiós")\n'
    assert w.generated["hola.py"]["path"] == str(dest)
    dest.write_text("MIO", encoding="utf-8")
    # existe: la ventana pregunta; simulamos «Cancelar» cerrando el cuadro y comprobamos que NO se sobrescribe
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QMessageBox
    def press_cancel():
        for box in qapp.topLevelWidgets():
            if isinstance(box, QMessageBox) and box.isVisible():
                box.button(QMessageBox.StandardButton.NoButton) if False else None
                for b in box.buttons():
                    if b.text() == "Cancelar": b.click(); return
        QTimer.singleShot(50, press_cancel)
    QTimer.singleShot(50, press_cancel)
    assert not w._save_to(dest, "hola.py", w.generated["hola.py"])
    assert dest.read_text(encoding="utf-8") == "MIO"


def test_save_error_is_reported_and_content_kept(qapp, window, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    shown = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: shown.append(a[2]))
    w = window()
    blocker = tmp_path / "archivo"; blocker.write_text("x")
    info = {"content": "contenido", "path": None}
    assert not w._save_to(blocker / "dentro.txt", "dentro.txt", info)
    assert shown and info["content"] == "contenido" and info["path"] is None


def test_type_without_clicking_goes_to_input(qapp, window):
    w = window(); w.activateWindow(); w.new_btn.setFocus(); qapp.processEvents()
    if QApplication.activeWindow() is not w:
        pytest.skip("el plataforma offscreen no activó la ventana")
    QTest.keyClick(w, Qt.Key.Key_H)
    assert w.input.hasFocus()                              # el foco se movió solo
    QTest.keyClick(w.input, Qt.Key.Key_O)
    assert w.input.toPlainText() == "ho" and w.input.hasFocus()


def test_typing_does_not_steal_focus_from_other_fields_or_dialogs(qapp, window):
    w = window(); w.activateWindow(); qapp.processEvents()
    if QApplication.activeWindow() is not w:
        pytest.skip("el plataforma offscreen no activó la ventana")
    field = QLineEdit(w); field.show(); field.setFocus(); qapp.processEvents()
    QTest.keyClicks(field, "abc")
    assert field.text() == "abc" and w.input.toPlainText() == ""
    field.deleteLater()
    dlg = QDialog(w); dlg.setModal(True); le = QLineEdit(dlg); dlg.show(); le.setFocus(); qapp.processEvents()
    QTest.keyClicks(le, "zz")
    assert le.text() == "zz" and w.input.toPlainText() == ""
    dlg.close()


def test_conversations_persist_and_reload(qapp, window):
    w = window(reply="respuesta uno")
    type_and_send(qapp, w, "primera pregunta")
    assert pump(qapp, lambda: w.worker is None)
    cid = w.conv_id; w.store.rename(cid, "Mi conversación"); w.refresh_conversations()
    w.new_conversation(); QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert w.history == [] and w.findChildren(MessageBubble) == []
    w.conv_list.setCurrentRow(0); QApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert w.conv_id == cid and [b.role for b in w.findChildren(MessageBubble)] == ["user", "assistant"]
    w2 = mw.MainWindow(w.s); w2.show(); qapp.processEvents()                  # «reinicio»
    assert w2.conv_list.count() == 1 and w2.conv_list.item(0).text() == "Mi conversación"
    assert w2.conv_id == cid and len(w2.history) == 2


def test_not_configured_blocks_send_and_offers_setup(qapp, monkeypatch):
    monkeypatch.setattr(mw.updater, "check_for_update", lambda *a, **k: mw.updater.UpdateResult("up_to_date", "1.1.0"))
    monkeypatch.setattr(mw.MainWindow, "run_wizard", lambda self: None)
    w = mw.MainWindow(config.Settings()); w.show(); qapp.processEvents()
    assert not w.send_btn.isEnabled() and w.empty_action.isVisible()
    w.input.setPlainText("hola"); w.send_message()
    assert w.worker is None and w.banner.isVisible() and w.input.toPlainText() == "hola"


def test_agent_mode_edits_project_with_permission_dialog(qapp, window, monkeypatch, tmp_path):
    ws = tmp_path / "ws"; ws.mkdir(); (ws / "a.txt").write_text("viejo", encoding="utf-8")
    calls = [f'<openchat-tool name="edit_file">{json.dumps({"path": "a.txt", "old": "viejo", "new": "nuevo"})}</openchat-tool>', "Hecho: cambié a.txt."]
    w = window(agent_enabled=True)
    w._test_fake.reply = calls[0]
    # el servidor devuelve primero la herramienta y luego el resumen final
    seq = iter(calls)
    orig = w._test_fake.srv.RequestHandlerClass
    import app.agent.permissions as perms
    asked = []
    monkeypatch.setattr(mw.PermissionDialog, "exec", lambda self: (asked.append(self.windowTitle()), setattr(self, "answer", "once"))[0])
    # sustituimos el proveedor por uno guionizado para controlar los dos turnos
    from tests.test_agent import Scripted
    prov = Scripted(calls)
    monkeypatch.setattr(w, "provider_and_model", lambda: (prov, "m", "m · prueba"))
    type_and_send(qapp, w, "cambia a.txt")
    assert pump(qapp, lambda: w.worker is None, 8)
    assert (ws / "a.txt").read_text(encoding="utf-8") == "nuevo" and asked == ["OpenChat pide permiso"]
    assert w.tool_cards and w.history[-1]["content"].startswith("Hecho")


def test_chispa_animates_only_when_visible_and_respects_reduced_motion(qapp, monkeypatch):
    c = ChispaWidget(80); assert not c.is_animating()
    c.show(); qapp.processEvents(); assert c.is_animating()
    c.hide(); assert not c.is_animating()
    monkeypatch.setenv("OPENCHAT_REDUCE_MOTION", "1")
    c2 = ChispaWidget(80); c2.show(); assert not c2.is_animating()
    for st in ("idle", "wave", "thinking", "happy", "error"):
        c.set_state(st); c.grab()                                              # pinta sin errores


def test_assistant_html_is_never_interpreted(qapp):
    b = MessageBubble("assistant", "<img src=x onerror=alert(1)> <script>x</script> [a](javascript:alert(1))")
    html = b._segments[0][1].text()
    assert "<img" not in html and "<script" not in html and 'href="javascript' not in html
