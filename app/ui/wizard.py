"""Asistente de configuración inicial: bienvenida → motor → nube/local → listo."""
from __future__ import annotations

import sys
import threading
import webbrowser

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QHBoxLayout, QLabel, QLineEdit, QProgressBar, QPushButton,
                               QRadioButton, QStackedWidget, QVBoxLayout, QWidget)

from .. import config
from ..providers import CancelToken, Cancelled, OllamaProvider, OpenRouterProvider, ProviderError
from ..sysinfo import describe, local_model_advice, total_ram_gb
from .chispa import ChispaWidget
from .workers import run_async

WELCOME, ENGINE, CLOUD, LOCAL, DONE = range(5)


def ollama_install_hint() -> str:
    if sys.platform.startswith("win"):
        return "Instálalo con: winget install --id Ollama.Ollama   (o desde https://ollama.com/download)"
    if sys.platform == "darwin":
        return "Instálalo desde https://ollama.com/download"
    return ("Instálalo con tu gestor de paquetes (en Arch/CachyOS: sudo pacman -S ollama) o desde https://ollama.com/download, "
            "y arráncalo con: ollama serve")


class SetupWizard(QDialog):
    pull_progress = Signal(str, int, int)
    pull_done = Signal(str)          # "" = éxito, o mensaje de error

    def __init__(self, settings, parent=None):
        super().__init__(parent)
        self.s = settings
        self.setWindowTitle("Configurar OpenChat")
        self.setModal(True)
        self.setMinimumSize(580, 640)
        self.cloud_ok = False
        self.key_verified = ""
        self._pull_token: CancelToken | None = None
        self._ollama = OllamaProvider()
        self.mode = settings["mode"]

        root = QVBoxLayout(self); root.setContentsMargins(30, 22, 30, 22); root.setSpacing(10)
        self.chispa = ChispaWidget(104, "wave"); root.addWidget(self.chispa, 0, Qt.AlignmentFlag.AlignHCenter)
        self.title = QLabel(); self.title.setObjectName("h1"); self.title.setAlignment(Qt.AlignmentFlag.AlignCenter); root.addWidget(self.title)
        self.stack = QStackedWidget(); root.addWidget(self.stack, 1)
        self.stack.addWidget(self._page_welcome()); self.stack.addWidget(self._page_engine())
        self.stack.addWidget(self._page_cloud()); self.stack.addWidget(self._page_local()); self.stack.addWidget(self._page_done())
        nav = QHBoxLayout()
        self.cancel_btn = QPushButton("Cancelar"); self.cancel_btn.clicked.connect(self._cancel)
        self.back_btn = QPushButton("Atrás"); self.back_btn.clicked.connect(self._back)
        self.next_btn = QPushButton("Siguiente"); self.next_btn.setObjectName("primary"); self.next_btn.clicked.connect(self._next)
        nav.addWidget(self.cancel_btn); nav.addStretch(); nav.addWidget(self.back_btn); nav.addWidget(self.next_btn); root.addLayout(nav)
        self.pull_progress.connect(self._on_pull_progress); self.pull_done.connect(self._on_pull_done)
        self._goto(WELCOME)

    # ------------------------------------------------------------ páginas
    def _label(self, text: str, muted: bool = False) -> QLabel:
        lab = QLabel(text); lab.setWordWrap(True)
        if muted:
            lab.setProperty("muted", True)
        return lab

    def _page_welcome(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self._label("¡Hola! Soy <b>Chispa</b>, la mascota de OpenChat ✨ — te acompaño en la configuración. "
                                "<b>OpenChat</b> es el asistente de IA: conversa, programa, crea archivos y, si lo activas, "
                                "puede trabajar sobre un proyecto con herramientas y tu permiso."))
        l.addWidget(self._label("Son dos pasos: elegir dónde «piensa» la IA (nube o tu ordenador) y comprobar que funciona.", True))
        l.addWidget(self._label(describe(), True)); l.addStretch()
        return w

    def _page_engine(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w)
        self.r_cloud = QRadioButton("☁  Nube · OpenRouter"); self.r_local = QRadioButton("🖥  Local · Ollama")
        for r in (self.r_cloud, self.r_local):
            r.setStyleSheet("font-weight:700;font-size:15px"); r.toggled.connect(self._engine_changed)
        l.addWidget(self.r_cloud)
        l.addWidget(self._label("Necesita Internet y una clave de OpenRouter. Tus conversaciones se envían a OpenRouter y al modelo que elijas.", True))
        l.addSpacing(10); l.addWidget(self.r_local)
        l.addWidget(self._label("Funciona sin Internet y tus conversaciones no salen del ordenador. Necesita Ollama, un modelo descargado, "
                                "y memoria/almacenamiento suficientes.", True))
        l.addWidget(self._label(local_model_advice(total_ram_gb()), True)); l.addStretch()
        (self.r_local if self.mode == "local" else self.r_cloud).setChecked(True)
        return w

    def _page_cloud(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w)
        l.addWidget(self._label("Tu clave de API de OpenRouter se guarda solo en este equipo (llavero del sistema si existe; si no, un archivo con permisos privados)."))
        row = QHBoxLayout()
        self.key_edit = QLineEdit(); self.key_edit.setEchoMode(QLineEdit.EchoMode.Password); self.key_edit.setPlaceholderText("sk-or-v1-…")
        self.key_edit.setAccessibleName("Clave de API de OpenRouter")
        self.key_edit.textChanged.connect(self._key_changed)
        self.show_btn = QPushButton("👁"); self.show_btn.setCheckable(True); self.show_btn.setFixedWidth(46); self.show_btn.setToolTip("Mostrar u ocultar la clave")
        self.show_btn.toggled.connect(lambda on: self.key_edit.setEchoMode(QLineEdit.EchoMode.Normal if on else QLineEdit.EchoMode.Password))
        row.addWidget(self.key_edit, 1); row.addWidget(self.show_btn); l.addLayout(row)
        link = QLabel('<a href="https://openrouter.ai/settings/keys" style="color:#a092ff">Crear o copiar mi clave en OpenRouter ↗</a>')
        link.setOpenExternalLinks(True); l.addWidget(link)
        self.check_btn = QPushButton("Comprobar conexión"); self.check_btn.clicked.connect(self._check_cloud); l.addWidget(self.check_btn)
        self.cloud_status = self._label("", True); l.addWidget(self.cloud_status)
        l.addWidget(self._label("Modelo"))
        mrow = QHBoxLayout()
        self.model_combo = QComboBox(); self.model_combo.setEditable(True); self.model_combo.addItem(self.s["cloud_model"])
        self.model_combo.setAccessibleName("Modelo de OpenRouter")
        self.load_btn = QPushButton("Cargar lista"); self.load_btn.setEnabled(False); self.load_btn.clicked.connect(self._load_models)
        mrow.addWidget(self.model_combo, 1); mrow.addWidget(self.load_btn); l.addLayout(mrow)
        self.fb_check = QCheckBox("Respaldo: usar Ollama si la nube falla (siempre con aviso)")
        self.fb_check.setChecked(self.s["fallback_to_local"]); l.addWidget(self.fb_check); l.addStretch()
        if config.get_api_key():
            self.key_edit.setPlaceholderText("Ya hay una clave guardada: déjalo vacío para comprobarla, o pega otra")
        return w

    def _page_local(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w)
        self.ollama_status = self._label("Comprobando Ollama…"); l.addWidget(self.ollama_status)
        self.ollama_help = self._label("", True); l.addWidget(self.ollama_help)
        row = QHBoxLayout(); recheck = QPushButton("Volver a comprobar"); recheck.clicked.connect(self._refresh_local)
        self.dl_page = QPushButton("Abrir ollama.com/download"); self.dl_page.clicked.connect(lambda: webbrowser.open("https://ollama.com/download"))
        row.addWidget(recheck); row.addWidget(self.dl_page); l.addLayout(row)
        l.addWidget(self._label("Modelos descargados"))
        self.local_combo = QComboBox(); self.local_combo.setAccessibleName("Modelo local instalado"); l.addWidget(self.local_combo)
        l.addWidget(self._label("Descargar otro modelo (escribe su nombre; el tamaño lo informará Ollama al empezar y puedes cancelar)"))
        drow = QHBoxLayout(); self.pull_edit = QLineEdit(self.s["local_model"]); self.pull_edit.setAccessibleName("Nombre del modelo a descargar")
        self.pull_btn = QPushButton("Descargar"); self.pull_btn.clicked.connect(self._start_pull)
        self.pull_cancel = QPushButton("Cancelar descarga"); self.pull_cancel.setVisible(False); self.pull_cancel.clicked.connect(self._cancel_pull)
        drow.addWidget(self.pull_edit, 1); drow.addWidget(self.pull_btn); drow.addWidget(self.pull_cancel); l.addLayout(drow)
        self.pull_bar = QProgressBar(); self.pull_bar.setVisible(False); l.addWidget(self.pull_bar)
        self.pull_label = self._label("", True); l.addWidget(self.pull_label); l.addStretch()
        return w

    def _page_done(self) -> QWidget:
        w = QWidget(); l = QVBoxLayout(w)
        self.summary = self._label(""); l.addWidget(self.summary)
        l.addWidget(self._label("Puedes cambiar de motor o de modelo cuando quieras desde la barra lateral, y repetir este asistente desde Ajustes.", True))
        l.addStretch(); return w

    # ------------------------------------------------------------ navegación
    def _goto(self, page: int) -> None:
        self.stack.setCurrentIndex(page)
        titles = {WELCOME: "Bienvenido a OpenChat", ENGINE: "¿Dónde quieres que piense la IA?", CLOUD: "Conecta OpenRouter",
                  LOCAL: "Prepara la IA local", DONE: "¡Todo listo!"}
        self.title.setText(titles[page])
        self.chispa.set_state({WELCOME: "wave", DONE: "happy"}.get(page, "idle"))
        self.back_btn.setVisible(page != WELCOME)
        self.next_btn.setText({WELCOME: "Empezar", DONE: "Terminar"}.get(page, "Siguiente"))
        if page == LOCAL:
            self._refresh_local()
        if page == DONE:
            self._build_summary()
        self._update_next()

    def _update_next(self) -> None:
        page = self.stack.currentIndex()
        ok = True
        if page == CLOUD:
            ok = self.cloud_ok
        elif page == LOCAL:
            ok = self.local_combo.count() > 0 and bool(self.local_combo.currentData())
        self.next_btn.setEnabled(ok)

    def _next(self) -> None:
        page = self.stack.currentIndex()
        if page == WELCOME: self._goto(ENGINE)
        elif page == ENGINE: self._goto(CLOUD if self.r_cloud.isChecked() else LOCAL)
        elif page in (CLOUD, LOCAL): self._goto(DONE)
        else: self._finish()

    def _back(self) -> None:
        page = self.stack.currentIndex()
        self._goto({ENGINE: WELCOME, CLOUD: ENGINE, LOCAL: ENGINE, DONE: CLOUD if self.r_cloud.isChecked() else LOCAL}.get(page, WELCOME))

    def _cancel(self) -> None:
        self._cancel_pull(); self.reject()

    def closeEvent(self, e) -> None:
        self._cancel_pull(); super().closeEvent(e)

    def _engine_changed(self) -> None:
        self.mode = "cloud" if self.r_cloud.isChecked() else "local"

    # ------------------------------------------------------------ nube
    def _key_changed(self) -> None:
        self.cloud_ok = False; self.key_verified = ""
        warn = config.key_format_warning(self.key_edit.text()) if self.key_edit.text() else ""
        self.cloud_status.setText(warn); self.load_btn.setEnabled(False); self._update_next()

    def _check_cloud(self) -> None:
        typed = self.key_edit.text().strip()
        key = typed or config.get_api_key()
        if not key:
            self.cloud_status.setText("Introduce tu clave de OpenRouter."); return
        warn = config.key_format_warning(key)
        self.check_btn.setEnabled(False); self.cloud_status.setText("Conectando con OpenRouter…")
        def work():
            return OpenRouterProvider(key).check()
        def done(res):
            self.check_btn.setEnabled(True)
            self.cloud_ok = res.ok
            self.key_verified = key if res.ok else ""
            prefix = ("⚠ " + warn + "\n") if warn and not res.ok else ""
            self.cloud_status.setText(("✓ " if res.ok else "✗ ") + res.message if res.ok else prefix + "✗ " + res.message)
            self.cloud_status.setStyleSheet("color:#86e0bd" if res.ok else "color:#ff8f9d")
            self.load_btn.setEnabled(res.ok); self._update_next()
        run_async(work, done, lambda e: done(type("R", (), {"ok": False, "message": config.redact(e)})()), self)

    def _load_models(self) -> None:
        key = self.key_verified
        self.load_btn.setEnabled(False)
        def done(models):
            current = self.model_combo.currentText()
            self.model_combo.clear(); self.model_combo.addItems(models)
            self.model_combo.setCurrentText(current); self.load_btn.setEnabled(True)
            self.cloud_status.setText(f"✓ {len(models)} modelos disponibles en OpenRouter.")
        def err(e):
            self.load_btn.setEnabled(True); self.cloud_status.setText("✗ No se pudo cargar la lista: " + config.redact(getattr(e, "message", e)))
        run_async(lambda: OpenRouterProvider(key).list_models(), done, err, self)

    # ------------------------------------------------------------ local
    def _refresh_local(self) -> None:
        self.ollama_status.setText("Comprobando Ollama…")
        def done(models):
            self.local_combo.clear()
            for m in models:
                self.local_combo.addItem(m["name"], m["name"])
            if models:
                want = self.s["local_model"]
                idx = self.local_combo.findData(want)
                self.local_combo.setCurrentIndex(max(0, idx))
                self.ollama_status.setText(f"✓ Ollama funciona y tiene {len(models)} modelo(s) descargado(s).")
                self.ollama_help.setText("")
            else:
                self.ollama_status.setText("Ollama funciona, pero aún no hay ningún modelo descargado.")
                self.ollama_help.setText("Descarga uno con el botón de abajo. Instalar Ollama no basta: hace falta un modelo.")
            self._update_next()
        def err(e):
            self.local_combo.clear()
            self.ollama_status.setText("✗ Ollama no responde en este equipo.")
            self.ollama_help.setText(ollama_install_hint())
            self._update_next()
        run_async(self._ollama.installed_models, done, err, self)

    def _start_pull(self) -> None:
        name = self.pull_edit.text().strip()
        if not name:
            return
        self._pull_token = CancelToken()
        self.pull_btn.setEnabled(False); self.pull_cancel.setVisible(True); self.pull_bar.setVisible(True); self.pull_bar.setRange(0, 0)
        self.pull_label.setText(f"Descargando «{name}»…")
        token = self._pull_token
        def work():
            try:
                self._ollama.pull(name, token, lambda s, c, t: self.pull_progress.emit(s, c, t))
                self.pull_done.emit("")
            except Cancelled:
                self.pull_done.emit("Descarga cancelada. No se dejó nada a medias en OpenChat.")
            except ProviderError as exc:
                self.pull_done.emit(exc.message)
            except Exception as exc:  # noqa: BLE001
                self.pull_done.emit(str(exc))
        threading.Thread(target=work, daemon=True).start()

    def _on_pull_progress(self, status: str, done: int, total: int) -> None:
        if total:
            self.pull_bar.setRange(0, 1000); self.pull_bar.setValue(int(1000 * done / total))
            self.pull_label.setText(f"{status} · {done / 1e6:.0f} de {total / 1e6:.0f} MB")
        else:
            self.pull_bar.setRange(0, 0); self.pull_label.setText(status)

    def _on_pull_done(self, error: str) -> None:
        self.pull_btn.setEnabled(True); self.pull_cancel.setVisible(False); self.pull_bar.setVisible(False)
        self.pull_label.setText("✗ " + error if error else "✓ Modelo descargado.")
        if not error:
            self.s["local_model"] = self.pull_edit.text().strip()
        self._refresh_local()

    def _cancel_pull(self) -> None:
        if self._pull_token:
            self._pull_token.cancel()

    # ------------------------------------------------------------ final
    def _build_summary(self) -> None:
        if self.r_cloud.isChecked():
            self.summary.setText(f"<b>Motor:</b> nube · OpenRouter<br><b>Modelo:</b> {self.model_combo.currentText().strip()}<br>"
                                 "<b>Privacidad:</b> tus mensajes se envían a OpenRouter.")
        else:
            self.summary.setText(f"<b>Motor:</b> local · Ollama<br><b>Modelo:</b> {self.local_combo.currentData()}<br>"
                                 "<b>Privacidad:</b> nada sale de tu ordenador.")

    def _finish(self) -> None:
        if self.r_cloud.isChecked():
            where = config.set_api_key(self.key_verified) if self.key_verified and self.key_verified != config.get_api_key() else ""
            self.s.update(mode="cloud", cloud_model=self.model_combo.currentText().strip() or config.DEFAULT_CLOUD_MODEL,
                          fallback_to_local=self.fb_check.isChecked(), setup_done=True)
        else:
            self.s.update(mode="local", local_model=self.local_combo.currentData(), setup_done=True)
        self.accept()
