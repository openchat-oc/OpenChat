"""Ventana principal de OpenChat."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import QEvent, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractSpinBox, QApplication, QComboBox, QDialog, QFileDialog, QFrame, QHBoxLayout,
                               QInputDialog, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMenu,
                               QMessageBox, QPlainTextEdit, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget)

from .. import REPO_URL, __version__, config, updater
from ..agent.loop import AGENT_SYSTEM, CHAT_SYSTEM
from ..conversations import ConversationStore, auto_title, build_context, import_legacy_history
from ..fileops import GeneratedFile, extract_files, save_text, strip_file_blocks, unique_path
from ..providers import OllamaProvider, OpenRouterProvider
from .chispa import ChispaWidget
from .dialogs import FileEditorDialog, PermissionDialog, SettingsDialog
from .widgets import THINKING, ChatInput, MessageBubble, ToolCard, TypingRow
from .wizard import SetupWizard
from .workers import GenerationWorker, GenRequest, run_async

LOGO = Path(__file__).resolve().parents[1] / "logo.svg"
MODE_LABEL = {"cloud": "Nube · OpenRouter", "local": "Local · Ollama"}
ERROR_HELP = {
    "auth": "Abre Ajustes → «Abrir el asistente» para introducir una clave válida.",
    "credits": "Añade créditos en OpenRouter o elige un modelo gratuito.",
    "rate": "Espera un momento o prueba con otro modelo.",
    "network": "Revisa tu conexión a Internet, o cambia al motor local.",
    "unavailable": "Arranca Ollama (ollama serve) y pulsa ↻ en la barra lateral.",
    "model": "Elige otro modelo en la barra lateral (en local: descárgalo con el asistente).",
}


class MainWindow(QMainWindow):
    def __init__(self, settings: config.Settings, store: ConversationStore | None = None):
        super().__init__()
        self.s = settings
        self.store = store or ConversationStore()
        import_legacy_history(self.store)
        self.log = config.setup_logging()
        self.conv_id: str | None = None
        self.history: list[dict] = []
        self.worker: GenerationWorker | None = None
        self.stream_bubble: MessageBubble | None = None
        self.typing: TypingRow | None = None
        self.tool_cards: list[ToolCard] = []
        self.generated: dict[str, dict] = {}
        self._last_user_bubble: MessageBubble | None = None
        self._last_draft = ""
        self._stick_bottom = True
        self.update_info: updater.UpdateResult | None = None

        self.setWindowTitle("OpenChat")
        if LOGO.exists():
            self.setWindowIcon(QIcon(str(LOGO)))
        self.resize(1120, 760); self.setMinimumSize(560, 480)
        root = QWidget(); root.setObjectName("root"); self.setCentralWidget(root)
        outer = QHBoxLayout(root); outer.setContentsMargins(0, 0, 0, 0); outer.setSpacing(0)
        self.sidebar = self._build_sidebar(); outer.addWidget(self.sidebar)
        main = QVBoxLayout(); main.setSpacing(0); outer.addLayout(main, 1)
        main.addWidget(self._build_header())
        self.banner = self._build_banner(); main.addWidget(self.banner)
        main.addWidget(self._build_chat(), 1)
        main.addWidget(self._build_bottom())
        self._shortcuts()
        QApplication.instance().installEventFilter(self)
        self.refresh_conversations(select_first=True)
        self.refresh_engine_ui()
        QTimer.singleShot(400, self, self._startup_checks)

    # ------------------------------------------------------------------ construcción
    def _build_sidebar(self) -> QFrame:
        sb = QFrame(); sb.setObjectName("sidebar"); sb.setFixedWidth(272)
        l = QVBoxLayout(sb); l.setContentsMargins(14, 14, 14, 12); l.setSpacing(8)
        brand = QHBoxLayout(); logo = QLabel("✦"); logo.setFixedSize(34, 34); logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size:20px;color:white;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d83f6,stop:1 #25c7e8);border-radius:11px")
        name = QLabel("OpenChat"); name.setStyleSheet("font-size:19px;font-weight:800"); brand.addWidget(logo); brand.addWidget(name); brand.addStretch(); l.addLayout(brand)
        self.new_btn = QPushButton("＋  Nueva conversación"); self.new_btn.setObjectName("primary"); self.new_btn.clicked.connect(self.new_conversation)
        self.new_btn.setAccessibleName("Nueva conversación"); l.addWidget(self.new_btn)
        self.conv_list = QListWidget(); self.conv_list.setAccessibleName("Historial de conversaciones")
        self.conv_list.currentItemChanged.connect(self._conv_selected)
        self.conv_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu); self.conv_list.customContextMenuRequested.connect(self._conv_menu)
        l.addWidget(self.conv_list, 1)
        l.addSpacing(6); sec = QLabel("MOTOR DE IA"); sec.setObjectName("section"); l.addWidget(sec)
        self.mode_combo = QComboBox(); self.mode_combo.setAccessibleName("Motor de IA")
        for k, v in MODE_LABEL.items():
            self.mode_combo.addItem(v, k)
        self.mode_combo.currentIndexChanged.connect(self._mode_changed); l.addWidget(self.mode_combo)
        mrow = QHBoxLayout(); self.model_combo = QComboBox(); self.model_combo.setAccessibleName("Modelo")
        self.model_combo.currentTextChanged.connect(self._model_changed)
        self.refresh_btn = QPushButton("↻"); self.refresh_btn.setFixedWidth(40); self.refresh_btn.setToolTip("Comprobar el motor y recargar los modelos")
        self.refresh_btn.setAccessibleName("Recargar modelos"); self.refresh_btn.clicked.connect(self.check_engine)
        mrow.addWidget(self.model_combo, 1); mrow.addWidget(self.refresh_btn); l.addLayout(mrow)
        self.engine_status = QLabel("○ sin comprobar"); self.engine_status.setProperty("muted", True); self.engine_status.setWordWrap(True); l.addWidget(self.engine_status)
        l.addSpacing(8); sec2 = QLabel("MODO AGENTE"); sec2.setObjectName("section"); l.addWidget(sec2)
        self.agent_btn = QPushButton("Agente: desactivado"); self.agent_btn.setCheckable(True); self.agent_btn.setChecked(self.s["agent_enabled"])
        self.agent_btn.setAccessibleName("Activar o desactivar el modo agente"); self.agent_btn.toggled.connect(self._agent_toggled); l.addWidget(self.agent_btn)
        self.ws_btn = QPushButton(); self.ws_btn.clicked.connect(self.pick_workspace); l.addWidget(self.ws_btn)
        for text, slot in (("↻  Actualizaciones", self.check_updates_manual), ("⚙  Ajustes", self.open_settings), ("ⓘ  Acerca de", self.about)):
            b = QPushButton(text); b.setObjectName("flat"); b.setStyleSheet("text-align:left"); b.clicked.connect(slot); l.addWidget(b)
            if "Actualizaciones" in text:
                self.update_btn = b
        return sb

    def _build_header(self) -> QFrame:
        h = QFrame(); h.setObjectName("header")
        l = QHBoxLayout(h); l.setContentsMargins(16, 10, 16, 10)
        self.toggle_sb = QPushButton("☰"); self.toggle_sb.setObjectName("flat"); self.toggle_sb.setAccessibleName("Mostrar u ocultar la barra lateral")
        self.toggle_sb.clicked.connect(lambda: self.sidebar.setVisible(not self.sidebar.isVisible())); l.addWidget(self.toggle_sb)
        self.title = QLabel("OpenChat"); self.title.setStyleSheet("font-size:16px;font-weight:700"); l.addWidget(self.title, 1)
        self.model_badge = QLabel(""); self.model_badge.setStyleSheet("color:#86e0bd;font-size:12px"); l.addWidget(self.model_badge)
        return h

    def _build_banner(self) -> QFrame:
        b = QFrame(); b.setObjectName("banner"); b.setVisible(False)
        l = QHBoxLayout(b); l.setContentsMargins(14, 8, 14, 8)
        self.banner_label = QLabel(); self.banner_label.setWordWrap(True); l.addWidget(self.banner_label, 1)
        self.banner_action = QPushButton(); self.banner_action.setObjectName("primary"); l.addWidget(self.banner_action)
        close = QPushButton("✕"); close.setObjectName("flat"); close.setAccessibleName("Cerrar aviso"); close.clicked.connect(lambda: b.setVisible(False)); l.addWidget(close)
        return b

    def _show_banner(self, text: str, action: str = "", slot=None) -> None:
        self.banner_label.setText(text)
        if getattr(self, "_banner_slot", None) is not None:
            self.banner_action.clicked.disconnect(self._banner_slot)
            self._banner_slot = None
        self.banner_action.setVisible(bool(action))
        if action and slot:
            self.banner_action.setText(action); self.banner_action.clicked.connect(slot); self._banner_slot = slot
        self.banner.setVisible(True)

    def _build_chat(self) -> QWidget:
        self.scroll = QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setObjectName("chatArea")
        self.column = QWidget(); self.column.setObjectName("column")
        self.col_layout = QVBoxLayout(self.column); self.col_layout.setSpacing(14); self.col_layout.setContentsMargins(24, 20, 24, 20)
        self.col_layout.addStretch()
        self.scroll.setWidget(self.column)
        self.scroll.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.empty = self._build_empty(); self.col_layout.insertWidget(0, self.empty)
        return self.scroll

    def _build_empty(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w); l.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.empty_chispa = ChispaWidget(110, "wave"); l.addWidget(self.empty_chispa, 0, Qt.AlignmentFlag.AlignHCenter)
        t = QLabel("¡Hola! Soy OpenChat"); t.setObjectName("h1"); t.setAlignment(Qt.AlignmentFlag.AlignCenter); l.addWidget(t)
        self.empty_sub = QLabel("Chispa, mi mascota, te acompaña. Escribe directamente o elige una idea:"); self.empty_sub.setProperty("muted", True)
        self.empty_sub.setAlignment(Qt.AlignmentFlag.AlignCenter); self.empty_sub.setWordWrap(True); l.addWidget(self.empty_sub)
        row = QHBoxLayout(); row.addStretch()
        for text, prompt in (("📄 Crear un README", "Crea un archivo README.md para mi proyecto con título, descripción e instrucciones de uso."),
                             ("💡 Explícame algo", "Explícame cómo funciona un modelo de lenguaje, con un ejemplo sencillo."),
                             ("🐍 Escribir un script", "Escribe un script de Python que renombre en lote los archivos de una carpeta y guárdalo como renombrar.py.")):
            b = QPushButton(text); b.setObjectName("chip"); b.clicked.connect(lambda _=False, p=prompt: self._fill_input(p)); row.addWidget(b)
        row.addStretch(); l.addLayout(row)
        self.empty_action = QPushButton("Configurar OpenChat"); self.empty_action.setObjectName("primary"); self.empty_action.clicked.connect(self.run_wizard)
        l.addWidget(self.empty_action, 0, Qt.AlignmentFlag.AlignHCenter); self.empty_action.setVisible(False)
        return w

    def _build_bottom(self) -> QFrame:
        b = QFrame(); b.setObjectName("bottom")
        l = QVBoxLayout(b); l.setContentsMargins(16, 10, 16, 14); l.setSpacing(8)
        self.files_panel = QFrame(); self.files_panel.setObjectName("filesPanel"); self.files_panel.setVisible(False)
        self.files_layout = QVBoxLayout(self.files_panel); self.files_layout.setContentsMargins(12, 8, 12, 8); self.files_layout.setSpacing(4)
        l.addWidget(self.files_panel)
        self.status = QLabel("Listo"); self.status.setProperty("muted", True); self.status.setAccessibleName("Estado"); l.addWidget(self.status)
        row = QHBoxLayout(); row.setSpacing(10)
        self.input = ChatInput(); self.input.submitted.connect(self.send_message); row.addWidget(self.input, 1)
        self.send_btn = QPushButton("Enviar  ↗"); self.send_btn.setObjectName("send"); self.send_btn.setMinimumHeight(46); self.send_btn.setMinimumWidth(110)
        self.send_btn.setAccessibleName("Enviar mensaje"); self.send_btn.clicked.connect(self.send_message); row.addWidget(self.send_btn, 0, Qt.AlignmentFlag.AlignBottom)
        self.stop_btn = QPushButton("■  Detener"); self.stop_btn.setObjectName("danger"); self.stop_btn.setMinimumHeight(46); self.stop_btn.setVisible(False)
        self.stop_btn.setAccessibleName("Detener la generación"); self.stop_btn.clicked.connect(self.cancel_generation); row.addWidget(self.stop_btn, 0, Qt.AlignmentFlag.AlignBottom)
        l.addLayout(row)
        self.setTabOrder(self.input, self.send_btn)
        return b

    def _shortcuts(self) -> None:
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.new_conversation)
        QShortcut(QKeySequence("Ctrl+,"), self, activated=self.open_settings)
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self.sidebar.setVisible(not self.sidebar.isVisible()))
        QShortcut(QKeySequence("Esc"), self, activated=self.cancel_generation)

    # ------------------------------------------------------------------ foco y teclado
    def eventFilter(self, obj, ev):
        """Escribir sin hacer clic: solo si OpenChat está activo, no hay diálogos y el foco no está en otro campo."""
        if ev.type() == QEvent.Type.KeyPress and QApplication.activeWindow() is self and QApplication.activeModalWidget() is None:
            focus = QApplication.focusWidget()
            editable = isinstance(focus, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox)) or (isinstance(focus, QComboBox) and focus.isEditable())
            if not editable and not (ev.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier | Qt.KeyboardModifier.MetaModifier)):
                ch = ev.text()
                if len(ch) == 1 and ch.isprintable() and not (isinstance(focus, QPushButton) and ch == " "):
                    self.input.setFocus(); self.input.insertPlainText(ch)
                    return True
        return super().eventFilter(obj, ev)

    def resizeEvent(self, e) -> None:
        super().resizeEvent(e)
        margin = max(20, (self.scroll.viewport().width() - 900) // 2)
        self.col_layout.setContentsMargins(margin, 20, margin, 20)
        self.sidebar.setVisible(self.width() >= 820 if not getattr(self, "_sb_manual", False) else self.sidebar.isVisible())

    # ------------------------------------------------------------------ conversaciones
    def refresh_conversations(self, select_first: bool = False) -> None:
        self.conv_list.blockSignals(True); self.conv_list.clear()
        for c in self.store.list():
            it = QListWidgetItem(c.title); it.setData(Qt.ItemDataRole.UserRole, c.id); self.conv_list.addItem(it)
            if c.id == self.conv_id:
                self.conv_list.setCurrentItem(it)
        self.conv_list.blockSignals(False)
        if select_first and self.conv_list.count() and self.conv_id is None:
            self.conv_list.setCurrentRow(0)

    def new_conversation(self) -> None:
        if self.worker:
            return
        self.conv_id = None; self.history = []; self.generated = {}
        self.conv_list.blockSignals(True); self.conv_list.clearSelection(); self.conv_list.setCurrentItem(None); self.conv_list.blockSignals(False)
        self._clear_chat(); self.title.setText("Conversación nueva"); self._refresh_files(); self.input.setFocus()

    def _conv_selected(self, cur: QListWidgetItem | None, _prev=None) -> None:
        if not cur or self.worker:
            return
        cid = cur.data(Qt.ItemDataRole.UserRole)
        if cid == self.conv_id:
            return
        self.conv_id = cid; self.history = self.store.messages(cid); self.generated = {}
        self._clear_chat(); self.title.setText(cur.text())
        for m in self.history:
            if m["role"] == "assistant":
                self._register_files(m["content"])
                self._add_bubble("assistant", strip_file_blocks(m["content"]))
            else:
                self._add_bubble("user", m["content"])
        self._refresh_files(); self._scroll_bottom(force=True)

    def _conv_menu(self, pos) -> None:
        it = self.conv_list.itemAt(pos)
        if not it:
            return
        menu = QMenu(self); ren = menu.addAction("Renombrar…"); dele = menu.addAction("Eliminar")
        act = menu.exec(self.conv_list.mapToGlobal(pos)); cid = it.data(Qt.ItemDataRole.UserRole)
        if act is ren:
            name, ok = QInputDialog.getText(self, "Renombrar conversación", "Nuevo nombre:", text=it.text())
            if ok and name.strip():
                self.store.rename(cid, name); self.refresh_conversations()
                if cid == self.conv_id: self.title.setText(name.strip())
        elif act is dele and QMessageBox.question(self, "Eliminar", f"¿Eliminar «{it.text()}»?") == QMessageBox.StandardButton.Yes:
            self.store.delete(cid)
            if cid == self.conv_id:
                self.conv_id = None; self.new_conversation()
            self.refresh_conversations()

    def _clear_chat(self) -> None:
        for i in reversed(range(self.col_layout.count())):
            w = self.col_layout.itemAt(i).widget()
            if w is not None and w is not self.empty:
                self.col_layout.removeWidget(w); w.deleteLater()
        self.empty.setVisible(True); self.stream_bubble = None; self.typing = None; self.tool_cards = []

    def _add_widget(self, w: QWidget, role: str = "bot") -> None:
        self.empty.setVisible(False)
        row = QHBoxLayout(); row.setSpacing(0)
        if role == "user":
            row.addStretch(1); row.addWidget(w, 5)
        else:
            row.addWidget(w, 6); row.addStretch(1)
        host = QWidget(); host.setLayout(row); row.setContentsMargins(0, 0, 0, 0)
        self.col_layout.insertWidget(self.col_layout.count() - 1, host)
        w._row_host = host  # type: ignore[attr-defined]
        self._scroll_bottom()

    def _add_bubble(self, role: str, text: str) -> MessageBubble:
        b = MessageBubble(role, text)
        b.save_requested.connect(self.save_answer)
        self._add_widget(b, "user" if role == "user" else "bot")
        return b

    def _remove_widget(self, w: QWidget) -> None:
        host = getattr(w, "_row_host", w)
        host.hide(); self.col_layout.removeWidget(host); host.deleteLater()

    def _on_scroll(self, v: int) -> None:
        bar = self.scroll.verticalScrollBar(); self._stick_bottom = v >= bar.maximum() - 40

    def _scroll_bottom(self, force: bool = False) -> None:
        if force or self._stick_bottom:
            QTimer.singleShot(30, lambda: self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))

    def _fill_input(self, text: str) -> None:
        self.input.setPlainText(text); self.input.setFocus(); self.input.moveCursor(self.input.textCursor().MoveOperation.End)

    # ------------------------------------------------------------------ motor
    def provider_and_model(self):
        if self.s["mode"] == "local":
            return OllamaProvider(), self.s["local_model"], f"{self.s['local_model']} · Ollama (local)"
        return OpenRouterProvider(config.get_api_key()), self.s["cloud_model"], f"{self.s['cloud_model']} · OpenRouter"

    def engine_ready(self) -> tuple[bool, str]:
        if not self.s["setup_done"]:
            return False, "Primero configura OpenChat para elegir un motor de IA."
        if self.s["mode"] == "cloud" and not config.get_api_key():
            return False, "Falta la clave de OpenRouter."
        if not (self.s["cloud_model"] if self.s["mode"] == "cloud" else self.s["local_model"]):
            return False, "No hay un modelo seleccionado."
        return True, ""

    def refresh_engine_ui(self) -> None:
        self.mode_combo.blockSignals(True); self.mode_combo.setCurrentIndex(self.mode_combo.findData(self.s["mode"])); self.mode_combo.blockSignals(False)
        self.model_combo.blockSignals(True); self.model_combo.clear()
        self.model_combo.setEditable(self.s["mode"] == "cloud")
        cur = self.s["cloud_model"] if self.s["mode"] == "cloud" else self.s["local_model"]
        if cur:
            self.model_combo.addItem(cur)
        self.model_combo.setCurrentText(cur); self.model_combo.blockSignals(False)
        self.agent_btn.setText("Agente: " + ("activado" if self.s["agent_enabled"] else "desactivado"))
        self.ws_btn.setText("📁  " + self.s.workspace_path().name); self.ws_btn.setToolTip(str(self.s.workspace_path())); self.ws_btn.setVisible(self.s["agent_enabled"])
        ok, why = self.engine_ready()
        self.model_badge.setText(f"● {MODE_LABEL[self.s['mode']]}" if ok else "")
        self.empty_action.setVisible(not ok)
        if not ok:
            self.empty_sub.setText(why + " Pulsa el botón y te guío paso a paso.")
        else:
            self.empty_sub.setText("Chispa, mi mascota, te acompaña. Escribe directamente o elige una idea:")
        self.send_btn.setEnabled(ok and not self.worker)

    def _mode_changed(self) -> None:
        self.s.update(mode=self.mode_combo.currentData()); self.refresh_engine_ui(); self.check_engine()

    def _model_changed(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        key = "cloud_model" if self.s["mode"] == "cloud" else "local_model"
        if text != self.s[key]:
            self.s.update(**{key: text})
            self.engine_status.setText("○ modelo cambiado; pulsa ↻ para comprobarlo")

    def check_engine(self) -> None:
        mode = self.s["mode"]; self.engine_status.setText("… comprobando"); self.engine_status.setStyleSheet("")
        if mode == "local":
            def done(models):
                names = [m["name"] for m in models]
                cur = self.s["local_model"]
                self.model_combo.blockSignals(True); self.model_combo.clear(); self.model_combo.addItems(names or [cur]); self.model_combo.setCurrentText(cur if cur in names or not names else names[0]); self.model_combo.blockSignals(False)
                if names and cur not in names:
                    self.s.update(local_model=names[0])
                self._set_status(bool(names), "✓ Ollama listo" if names else "Ollama funciona, pero no hay modelos: descarga uno con el asistente")
                self.refresh_engine_ui()
            run_async(OllamaProvider().installed_models, done, lambda e: self._set_status(False, getattr(e, "message", str(e))), self)
        else:
            key = config.get_api_key()
            if not key:
                self._set_status(False, "Falta la clave de OpenRouter"); return
            def done(res): self._set_status(res.ok, res.message)
            run_async(lambda: OpenRouterProvider(key).check(), done, lambda e: self._set_status(False, config.redact(e)), self)
            run_async(lambda: OpenRouterProvider(key).list_models(), self._fill_cloud_models, None, self)

    def _fill_cloud_models(self, models) -> None:
        if self.s["mode"] != "cloud" or not models:
            return
        cur = self.s["cloud_model"]
        self.model_combo.blockSignals(True); self.model_combo.clear(); self.model_combo.addItems(models); self.model_combo.setCurrentText(cur); self.model_combo.blockSignals(False)

    def _set_status(self, ok: bool, text: str) -> None:
        self.engine_status.setText(("● " if ok else "✕ ") + text)
        self.engine_status.setStyleSheet("color:#86e0bd" if ok else "color:#ff8f9d")

    def run_wizard(self) -> None:
        dlg = SetupWizard(self.s, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.refresh_engine_ui(); self.check_engine()

    # ------------------------------------------------------------------ agente
    def _agent_toggled(self, on: bool) -> None:
        if on:
            ws = self.s.workspace_path()
            try:
                ws.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                QMessageBox.warning(self, "Espacio de trabajo", f"No pude crear {ws}: {exc}"); self.agent_btn.setChecked(False); return
        self.s.update(agent_enabled=on); self.refresh_engine_ui()

    def pick_workspace(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Carpeta de trabajo del agente", str(self.s.workspace_path()))
        if d:
            self.s.update(workspace=d); self.refresh_engine_ui()

    def _ask_permission(self, name, args, decision, holder) -> None:
        dlg = PermissionDialog(self, name, args, decision)
        dlg.exec()
        holder.answer = dlg.answer; holder.event.set()

    # ------------------------------------------------------------------ envío y generación
    def send_message(self) -> None:
        text = self.input.toPlainText().strip()
        if not text or self.worker:
            return
        ok, why = self.engine_ready()
        if not ok:
            self._show_banner(why, "Configurar", self.run_wizard); return
        self._last_draft = self.input.toPlainText()
        self.input.clear()
        if self.conv_id is None:
            conv = self.store.create(auto_title(text)); self.conv_id = conv.id; self.title.setText(conv.title)
            self.refresh_conversations()
        self.history.append({"role": "user", "content": text}); self.store.add_message(self.conv_id, "user", text)
        self._last_user_bubble = self._add_bubble("user", text)
        provider, model, label = self.provider_and_model()
        agent = self.s["agent_enabled"]
        system = AGENT_SYSTEM if agent else CHAT_SYSTEM
        msgs, trimmed = build_context(CHAT_SYSTEM if not agent else "", self.history)
        fb = None
        if self.s["fallback_to_local"] and self.s["mode"] == "cloud" and not agent:
            lm = self.s["local_model"]
            if lm:
                fb = (OllamaProvider(), lm, f"{lm} · Ollama (local)")
        req = GenRequest(msgs, provider, model, label, float(self.s["temperature"]), fb,
                         {"workspace": self.s.workspace_path(), "mode": self.s["agent_permission"], "history": msgs[1:] if msgs and msgs[0]["role"] == "system" else msgs} if agent else None)
        if trimmed:
            self._add_widget(MessageBubble("notice", "La conversación es larga: envío al modelo solo los mensajes más recientes."))
        self._begin(req)

    def _begin(self, req: GenRequest) -> None:
        w = GenerationWorker(req); self.worker = w
        self.stream_bubble = None; self.tool_cards = []
        self.typing = TypingRow(); self._add_widget(self.typing); self.typing.start()
        self.send_btn.setVisible(False); self.stop_btn.setVisible(True); self.send_btn.setEnabled(False)
        for chispa in (self.empty_chispa,):
            chispa.set_state("thinking")
        w.status.connect(self._on_status); w.chunk.connect(self._on_chunk); w.notice.connect(self._on_notice)
        w.step_start.connect(self._on_step_start); w.step_end.connect(self._on_step_end)
        w.tool_call.connect(self._on_tool_call); w.tool_result.connect(self._on_tool_result)
        w.permission.connect(self._ask_permission)
        w.finished.connect(self._on_finished); w.failed.connect(self._on_failed); w.cancelled.connect(self._on_cancelled)
        self._on_status("Preparando la solicitud"); w.start()

    def cancel_generation(self) -> None:
        if self.worker:
            self.status.setText("Cancelando…"); self.worker.cancel()

    def _on_status(self, text: str) -> None:
        self.status.setText(text)
        if self.typing:
            self.typing.set_state(THINKING if text in ("Preparando la solicitud", "Esperando la respuesta del modelo") else text)

    def _on_chunk(self, piece: str) -> None:
        if self.typing is not None and self.stream_bubble is None:
            self._remove_widget(self.typing); self.typing.stop(); self.typing = None
        if self.stream_bubble is None:
            self.stream_bubble = self._add_bubble("assistant", "")
        self.stream_bubble.set_text(self.stream_bubble.text() + piece)
        self._scroll_bottom()

    def _on_notice(self, text: str) -> None:
        self._add_widget(MessageBubble("notice", "↪ " + text))

    def _on_step_start(self) -> None:
        self.stream_bubble = None

    def _on_step_end(self, visible: str) -> None:
        if self.stream_bubble is not None:
            if visible.strip():
                self.stream_bubble.set_text(visible)
            else:
                self._remove_widget(self.stream_bubble)
            self.stream_bubble = None
        if self.typing is None and self.worker:
            self.typing = TypingRow(); self._add_widget(self.typing); self.typing.start()

    def _on_tool_call(self, info) -> None:
        card = ToolCard(f"{info['detail']}"); self.tool_cards.append(card); self._add_widget(card)

    def _on_tool_result(self, info) -> None:
        if self.tool_cards:
            self.tool_cards[-1].finish(info["ok"], f"{info['name']}: {info['summary']}")
        self._scroll_bottom()

    def _finish_ui(self) -> None:
        if self.typing:
            self.typing.stop(); self._remove_widget(self.typing); self.typing = None
        self.worker = None
        self.stop_btn.setVisible(False); self.send_btn.setVisible(True)
        self.empty_chispa.set_state("wave"); self.refresh_engine_ui(); self.input.setFocus()

    def _on_finished(self, text: str, label: str, stopped: str) -> None:
        agent = self.s["agent_enabled"]
        if self.stream_bubble is not None and not agent:
            self.stream_bubble.set_text(strip_file_blocks(text))
        elif agent:
            self._add_bubble("assistant", text)
        self.stream_bubble = None
        self.history.append({"role": "assistant", "content": text})
        if self.conv_id:
            self.store.add_message(self.conv_id, "assistant", text)
        new_files = self._register_files(text)
        self.model_badge.setText("● " + label)
        notes = {"truncated": "La respuesta se cortó por el límite de longitud del modelo.", "max_steps": "El agente alcanzó el máximo de pasos.",
                 "timeout": "El agente alcanzó el tiempo máximo.", "loop": "El agente se detuvo para no repetirse."}
        if stopped in notes:
            self._add_widget(MessageBubble("notice", notes[stopped]))
        self.status.setText(f"{len(new_files)} archivo(s) listo(s) para guardar · {label}" if new_files else f"Respuesta recibida · {label}")
        self._refresh_files(); self._finish_ui()

    def _fail_cleanup(self, partial: str) -> None:
        """Sin respuesta útil: se retira el mensaje enviado, se devuelve el borrador y no se duplica el historial."""
        if partial.strip():
            if self.stream_bubble is not None:
                self.stream_bubble.set_text(partial)
            self.history.append({"role": "assistant", "content": partial})
            if self.conv_id: self.store.add_message(self.conv_id, "assistant", partial)
        else:
            if self.history and self.history[-1]["role"] == "user":
                self.history.pop()
                if self.conv_id: self.store.delete_last_message(self.conv_id, "user")
            if self._last_user_bubble is not None:
                self._remove_widget(self._last_user_bubble); self._last_user_bubble = None
            if not self.input.toPlainText().strip():
                self.input.setPlainText(self._last_draft)
        self.stream_bubble = None

    def _on_failed(self, kind: str, message: str, partial: str) -> None:
        self.log.warning("generación fallida (%s): %s", kind, message)
        self._fail_cleanup(partial)
        help_ = ERROR_HELP.get(kind, "")
        self._add_widget(MessageBubble("error", f"⚠ {message}" + (f"\n{help_}" if help_ else "") + "\nTu mensaje sigue en la caja de texto." * (not partial.strip())))
        self.status.setText("Error recuperable · " + message[:80]); self._finish_ui()

    def _on_cancelled(self, partial: str) -> None:
        self._fail_cleanup(partial)
        self._add_widget(MessageBubble("notice", "⏹ Generación cancelada."))
        self.status.setText("Cancelado"); self._finish_ui()

    # ------------------------------------------------------------------ archivos
    def _register_files(self, text: str) -> list[GeneratedFile]:
        files = extract_files(text)
        for f in files:
            self.generated[f.name] = {"content": f.content, "path": None, "complete": f.complete}
        return files

    def _refresh_files(self) -> None:
        while self.files_layout.count():
            it = self.files_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        self.files_panel.setVisible(bool(self.generated))
        if not self.generated:
            return
        head = QHBoxLayout(); t = QLabel(f"<b>Archivos creados ({len(self.generated)})</b>"); head.addWidget(t); head.addStretch()
        all_btn = QPushButton("Guardar todos…"); all_btn.clicked.connect(self.save_all_files); head.addWidget(all_btn)
        hw = QWidget(); hw.setLayout(head); head.setContentsMargins(0, 0, 0, 0); self.files_layout.addWidget(hw)
        for name, info in self.generated.items():
            row = QHBoxLayout(); row.setContentsMargins(0, 0, 0, 0)
            state = f"✓ guardado en {Path(info['path']).parent.name or info['path']}" if info["path"] else ("⚠ incompleto (respuesta cortada)" if not info["complete"] else "sin guardar")
            lab = QLabel(f"📄 <b>{name}</b> <span style='color:#9b9db2'>· {Path(name).suffix or 'archivo'} · {state}</span>"); lab.setTextFormat(Qt.TextFormat.RichText); lab.setToolTip(info["path"] or "Aún no está guardado en el disco")
            row.addWidget(lab, 1)
            for text, slot in (("Ver / editar", lambda _=False, n=name: self.edit_file(n)), ("Guardar", lambda _=False, n=name: self.save_file(n)),
                               ("↻ Regenerar", lambda _=False, n=name: self.regenerate(n))):
                b = QPushButton(text); b.setObjectName("flat"); b.clicked.connect(slot); b.setEnabled(not self.worker); row.addWidget(b)
            if info["path"]:
                b = QPushButton("Abrir ubicación"); b.setObjectName("flat"); b.clicked.connect(lambda _=False, p=info["path"]: self.reveal(Path(p))); row.addWidget(b)
            w = QWidget(); w.setLayout(row); self.files_layout.addWidget(w)

    def _default_dir(self) -> Path:
        d = self.s.workspace_path()
        return d if d.exists() else Path.home()

    def edit_file(self, name: str) -> None:
        info = self.generated[name]
        dlg = FileEditorDialog(self, name, info["content"], self._default_dir(), Path(info["path"]) if info["path"] else None)
        dlg.exec()
        info["content"] = dlg.content()
        if dlg.saved_path:
            info["path"] = str(dlg.saved_path)
        self._refresh_files()

    def save_file(self, name: str) -> None:
        info = self.generated[name]
        path, _ = QFileDialog.getSaveFileName(self, "Guardar archivo", str(self._default_dir() / name), "Todos los archivos (*)",
                                              options=QFileDialog.Option.DontConfirmOverwrite)
        if path:
            self._save_to(Path(path), name, info)
        self._refresh_files()

    def _save_to(self, p: Path, name: str, info: dict, quiet: bool = False) -> bool:
        overwrite = False
        if p.exists():
            box = QMessageBox(QMessageBox.Icon.Warning, "El archivo ya existe", f"{p.name} ya existe en esa carpeta.", QMessageBox.StandardButton.NoButton, self)
            rep = box.addButton("Reemplazar", QMessageBox.ButtonRole.DestructiveRole)
            other = box.addButton("Guardar con otro nombre", QMessageBox.ButtonRole.AcceptRole)
            box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole).setDefault(True)
            box.exec(); c = box.clickedButton()
            if c is rep: overwrite = True
            elif c is other: p = unique_path(p)
            else: return False
        try:
            saved = save_text(p, info["content"], overwrite=overwrite)
            info["path"] = str(saved); self.status.setText(f"Guardado y verificado: {saved}")
            return True
        except OSError as exc:
            QMessageBox.warning(self, "No se pudo guardar", f"{exc}\n\nEl contenido sigue disponible en OpenChat; prueba con otra carpeta.")
            return False

    def save_all_files(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "¿Dónde guardamos los archivos?", str(self._default_dir()))
        if not folder:
            return
        done = [n for n, i in self.generated.items() if self._save_to(Path(folder) / n, n, i)]
        self._refresh_files()
        if done:
            QMessageBox.information(self, "Archivos guardados", "Se guardaron:\n\n" + "\n".join(done) + f"\n\nCarpeta: {folder}")

    def regenerate(self, name: str) -> None:
        self._fill_input(f"Vuelve a generar el archivo «{name}» completo, corrigiendo cualquier fallo anterior.")
        self.send_message()

    def reveal(self, path: Path) -> None:
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", str(path)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except OSError as exc:
            QMessageBox.information(self, "Abrir ubicación", f"No pude abrir el explorador: {exc}\n{path}")

    def save_answer(self, text: str) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Guardar respuesta", str(self._default_dir() / "respuesta.md"),
                                              "Markdown (*.md);;Texto (*.txt);;Todos los archivos (*)", options=QFileDialog.Option.DontConfirmOverwrite)
        if path:
            self._save_to(Path(path), Path(path).name, {"content": text, "path": None})

    # ------------------------------------------------------------------ actualizaciones y ajustes
    def _startup_checks(self) -> None:
        if not self.isVisible():          # ventana cerrada antes de tiempo: no abrir diálogos huérfanos
            return
        if not self.s["setup_done"]:
            if not config.get_api_key() and not self.s.loaded_from_disk:
                self.run_wizard()
            elif config.get_api_key():                         # instalación anterior con clave: migración silenciosa
                self.s.update(setup_done=True, mode="cloud"); self.refresh_engine_ui()
        if self.engine_ready()[0]:
            self.check_engine()
        if self.s["auto_update_check"]:
            run_async(updater.check_for_update, self._on_update_result, None, self)

    def _on_update_result(self, res) -> None:
        self.update_info = res
        if res.state == updater.AVAILABLE:
            self._show_banner("✨ " + (res.message or "Hay una actualización disponible."), "Ver", self.check_updates_manual)

    def check_updates_manual(self) -> None:
        self.update_btn.setEnabled(False); self.status.setText("Comprobando actualizaciones…")
        def done(res):
            self.update_btn.setEnabled(True); self.update_info = res; self.status.setText(res.message)
            if res.state == updater.AVAILABLE:
                box = QMessageBox(QMessageBox.Icon.Information, "Actualización disponible",
                                  res.message + "\n\nSe ejecutará «git pull --ff-only» en la carpeta de OpenChat y se actualizarán las dependencias. "
                                  "Tu configuración, claves e historial NO se tocan (viven en ~/.config/openchat).", QMessageBox.StandardButton.NoButton, self)
                go = box.addButton("Actualizar ahora", QMessageBox.ButtonRole.AcceptRole); box.addButton("Más tarde", QMessageBox.ButtonRole.RejectRole); box.exec()
                if box.clickedButton() is go:
                    self.status.setText("Actualizando…")
                    run_async(updater.apply_update, lambda r: QMessageBox.information(self, "Actualización", ("✓ " if r[0] else "✗ ") + r[1] + ("\n\nReinicia OpenChat para usar la nueva versión." if r[0] else "")), None, self)
            elif res.state == updater.UP_TO_DATE:
                QMessageBox.information(self, "Actualizaciones", f"✓ OpenChat {res.installed} está actualizado.")
            else:
                QMessageBox.warning(self, "No se pudo comprobar", res.message + "\n\nNo significa que estés al día: simplemente no pude comprobarlo.")
        run_async(updater.check_for_update, done, lambda e: done(updater.UpdateResult(updater.ERROR, __version__, message=str(e))), self)

    def open_settings(self) -> None:
        key = config.get_api_key()
        dlg = SettingsDialog(self, self.s, bool(key), config.mask_key(key) if key else "")
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        if dlg.action == "wizard": self.run_wizard()
        elif dlg.action == "clear_history":
            self.store.delete_all(); self.conv_id = None; self.new_conversation(); self.refresh_conversations()
        elif dlg.action == "delete_key":
            config.delete_api_key(); self.refresh_engine_ui(); self._set_status(False, "Clave eliminada")
        else:
            self.refresh_engine_ui()

    def about(self) -> None:
        QMessageBox.about(self, "Acerca de OpenChat",
                          f"<b>OpenChat {__version__}</b><br>Asistente de IA de escritorio.<br><br>Chispa es la mascota de OpenChat; "
                          f"la IA es el modelo que elijas (nube con OpenRouter o local con Ollama).<br>"
                          f"<a href='{REPO_URL}'>{REPO_URL}</a><br><br>Datos personales: <code>{config.config_dir()}</code>")

    def closeEvent(self, e) -> None:
        if self.worker:
            self.worker.cancel()
        super().closeEvent(e)
