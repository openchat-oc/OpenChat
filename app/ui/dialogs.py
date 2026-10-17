"""Diálogos: permisos del agente, editor de archivos y ajustes."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtWidgets import (QCheckBox, QComboBox, QDialog, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                               QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout)

from ..fileops import save_text


class PermissionDialog(QDialog):
    """Respuesta: «once» | «session» | «deny» (Denegar es la opción por defecto y la de Esc)."""
    def __init__(self, parent, name: str, args: dict, decision):
        super().__init__(parent)
        self.setWindowTitle("OpenChat pide permiso")
        self.setModal(True); self.setMinimumWidth(480)
        self.answer = "deny"
        lay = QVBoxLayout(self); lay.setSpacing(10)
        title = QLabel("🛡  El agente quiere realizar una acción"); title.setStyleSheet("font-size:16px;font-weight:700")
        lay.addWidget(title)
        lay.addWidget(QLabel(f"<b>{decision.detail or name}</b>"))
        why = QLabel(decision.reason); why.setWordWrap(True); why.setProperty("muted", True); lay.addWidget(why)
        preview = {k: (v if not isinstance(v, str) or len(v) < 400 else v[:400] + "…") for k, v in args.items()}
        box = QPlainTextEdit(); box.setReadOnly(True); box.setPlainText("\n".join(f"{k}: {v}" for k, v in preview.items()))
        box.setFixedHeight(130); lay.addWidget(box)
        row = QHBoxLayout()
        deny = QPushButton("Denegar"); deny.setDefault(True); deny.clicked.connect(self._deny)
        once = QPushButton("Permitir una vez"); once.setObjectName("primary"); once.clicked.connect(lambda: self._set("once"))
        row.addWidget(deny); row.addStretch()
        if decision.key:
            sess = QPushButton("Permitir durante esta tarea"); sess.clicked.connect(lambda: self._set("session")); row.addWidget(sess)
        row.addWidget(once); lay.addLayout(row)
        deny.setFocus()

    def _set(self, value: str) -> None:
        self.answer = value; self.accept()

    def _deny(self) -> None:
        self.answer = "deny"; self.reject()


class FileEditorDialog(QDialog):
    """Vista previa y edición de un archivo generado o existente; guarda de forma verificada."""
    def __init__(self, parent, name: str, content: str, default_dir: Path, existing: Path | None = None):
        super().__init__(parent)
        self.setWindowTitle(f"Editar · {name}")
        self.resize(780, 560)
        self.default_dir, self.name, self.existing = Path(default_dir), name, existing
        self.saved_path: Path | None = None
        lay = QVBoxLayout(self)
        self.info = QLabel(str(existing) if existing else "Archivo nuevo: aún no está guardado en el disco.")
        self.info.setProperty("muted", True); lay.addWidget(self.info)
        self.edit = QPlainTextEdit(); self.edit.setObjectName("code"); self.edit.setPlainText(content)
        self.edit.setStyleSheet("font-family:'JetBrains Mono','DejaVu Sans Mono',monospace;font-size:13px")
        lay.addWidget(self.edit, 1)
        row = QHBoxLayout()
        self.status = QLabel(""); self.status.setProperty("muted", True)
        close = QPushButton("Cerrar"); close.clicked.connect(self.reject)
        save_as = QPushButton("Guardar como…"); save_as.clicked.connect(self.save_as)
        self.save_btn = QPushButton("Guardar"); self.save_btn.setObjectName("primary"); self.save_btn.clicked.connect(self.save)
        row.addWidget(self.status, 1); row.addWidget(close); row.addWidget(save_as); row.addWidget(self.save_btn)
        lay.addLayout(row)

    def content(self) -> str:
        return self.edit.toPlainText()

    def save(self) -> None:
        if self.existing:
            self._write(self.existing, overwrite=True)      # editar un archivo existente = reemplazarlo a propósito
        else:
            self.save_as()

    def save_as(self) -> None:
        start = str((self.existing.parent if self.existing else self.default_dir) / self.name)
        path, _ = QFileDialog.getSaveFileName(self, "Guardar archivo", start, "Todos los archivos (*)",
                                              options=QFileDialog.Option.DontConfirmOverwrite)
        if not path:
            return
        p = Path(path)
        if p.exists():
            box = QMessageBox(QMessageBox.Icon.Warning, "El archivo ya existe", f"{p.name} ya existe. ¿Quieres reemplazarlo?",
                              QMessageBox.StandardButton.NoButton, self)
            rep = box.addButton("Reemplazar", QMessageBox.ButtonRole.DestructiveRole)
            box.addButton("Cancelar", QMessageBox.ButtonRole.RejectRole).setDefault(True)
            box.exec()
            if box.clickedButton() is not rep:
                return
            self._write(p, overwrite=True)
        else:
            self._write(p, overwrite=False)

    def _write(self, path: Path, overwrite: bool) -> None:
        try:
            self.saved_path = save_text(path, self.content(), overwrite=overwrite)
            self.existing = self.saved_path
            self.info.setText(str(self.saved_path))
            self.status.setText("✓ Guardado y verificado en " + str(self.saved_path))
        except OSError as exc:
            self.status.setText("✗ No se pudo guardar. Tu contenido sigue aquí.")
            QMessageBox.warning(self, "No se pudo guardar", f"{exc}\n\nTu texto sigue en el editor; prueba con otra carpeta.")


class SettingsDialog(QDialog):
    def __init__(self, parent, settings, has_key: bool, key_hint: str):
        super().__init__(parent)
        self.setWindowTitle("Ajustes · OpenChat"); self.setMinimumWidth(520)
        self.s = settings
        self.action = ""          # "wizard" | "clear_history" | "delete_key"
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.auto_update = QCheckBox("Comprobar actualizaciones al abrir OpenChat"); self.auto_update.setChecked(settings["auto_update_check"])
        self.fallback = QCheckBox("Respaldo: usar Ollama si la nube falla (siempre con aviso)")
        self.fallback.setChecked(settings["fallback_to_local"]); self.fallback.setToolTip("Desactivado por defecto: OpenChat nunca cambia de proveedor en silencio.")
        self.workspace = QLineEdit(str(settings.workspace_path())); pick = QPushButton("Elegir…"); pick.clicked.connect(self._pick)
        wrow = QHBoxLayout(); wrow.addWidget(self.workspace, 1); wrow.addWidget(pick)
        self.perm = QComboBox(); self.perm.addItem("Preguntar antes de modificar archivos o ejecutar comandos", "ask")
        self.perm.addItem("Permitir ediciones y pruebas dentro del espacio de trabajo", "auto_edits")
        self.perm.setCurrentIndex(max(0, self.perm.findData(settings["agent_permission"])))
        form.addRow(self.auto_update); form.addRow(self.fallback)
        form.addRow("Espacio de trabajo del agente", wrow); form.addRow("Permisos del agente", self.perm)
        lay.addLayout(form)
        note = QLabel("Las acciones destructivas, las instalaciones y todo lo que esté fuera del espacio de trabajo siempre piden confirmación o se bloquean."
                      f"\nClave de OpenRouter: {key_hint if has_key else 'no guardada'}.")
        note.setWordWrap(True); note.setProperty("muted", True); lay.addWidget(note)
        wiz = QPushButton("Abrir el asistente de configuración…"); wiz.clicked.connect(lambda: self._act("wizard"))
        hist = QPushButton("Borrar todo el historial…"); hist.clicked.connect(self._confirm_history)
        key = QPushButton("Eliminar la clave guardada…"); key.setEnabled(has_key); key.clicked.connect(self._confirm_key)
        for b in (wiz, hist, key):
            lay.addWidget(b)
        row = QHBoxLayout(); row.addStretch()
        cancel = QPushButton("Cancelar"); cancel.clicked.connect(self.reject)
        ok = QPushButton("Guardar"); ok.setObjectName("primary"); ok.clicked.connect(self._save)
        row.addWidget(cancel); row.addWidget(ok); lay.addLayout(row)

    def _pick(self) -> None:
        d = QFileDialog.getExistingDirectory(self, "Espacio de trabajo del agente", self.workspace.text())
        if d:
            self.workspace.setText(d)

    def _act(self, name: str) -> None:
        self.action = name; self.accept()

    def _confirm_history(self) -> None:
        if QMessageBox.question(self, "Borrar historial", "Se eliminarán todas las conversaciones guardadas. No se puede deshacer.") == QMessageBox.StandardButton.Yes:
            self._act("clear_history")

    def _confirm_key(self) -> None:
        if QMessageBox.question(self, "Eliminar clave", "Se eliminará tu clave de OpenRouter de este equipo.") == QMessageBox.StandardButton.Yes:
            self._act("delete_key")

    def _save(self) -> None:
        self.s.update(auto_update_check=self.auto_update.isChecked(), fallback_to_local=self.fallback.isChecked(),
                      workspace=self.workspace.text().strip(), agent_permission=self.perm.currentData())
        self.accept()
