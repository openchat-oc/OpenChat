#!/usr/bin/env python3
import sys
import subprocess
from pathlib import Path
import requests
from PySide6.QtCore import QObject, Signal, QThread, Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QDialog, QDialogButtonBox, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout, QWidget, QFileDialog

CONFIG = Path.home()/".config"/"openchat"
KEYFILE = CONFIG/"openrouter.key"
LEGACY = Path.home()/".config"/"oi-auto"/"openrouter.key"
MODEL = "poolside/laguna-s-2.1:free"
LOCAL = "qwen2.5:1.5b"

def read_key():
    try:
        if KEYFILE.exists(): return KEYFILE.read_text().strip()
        if LEGACY.exists():
            key=LEGACY.read_text().strip()
            if key: save_key(key)
            return key
    except OSError: pass
    return ""

def save_key(key):
    CONFIG.mkdir(parents=True, exist_ok=True)
    KEYFILE.write_text(key.strip(), encoding="utf-8")
    try: KEYFILE.chmod(0o600)
    except OSError: pass

class KeyDialog(QDialog):
    def __init__(self, parent=None, current=""):
        super().__init__(parent); self.setWindowTitle("Configurar OpenChat")
        box=QVBoxLayout(self)
        title=QLabel("Conecta OpenChat"); title.setStyleSheet("font-size:22px;font-weight:700")
        box.addWidget(title); box.addWidget(QLabel("Clave de OpenRouter (se guarda solo en este equipo):"))
        self.entry=QLineEdit(); self.entry.setEchoMode(QLineEdit.EchoMode.Password); self.entry.setPlaceholderText("sk-or-v1-…"); self.entry.setText(current); box.addWidget(self.entry)
        link=QLabel('<a href="https://openrouter.ai/settings/keys">Crear una clave en OpenRouter</a>'); link.setOpenExternalLinks(True); box.addWidget(link)
        buttons=QDialogButtonBox(QDialogButtonBox.StandardButton.Save|QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept); buttons.rejected.connect(self.reject); box.addWidget(buttons)

class Worker(QObject):
    done=Signal(str,bool); status=Signal(str)
    def __init__(self,messages,key): super().__init__(); self.messages=messages; self.key=key
    def run(self):
        cloud="No hay clave de OpenRouter configurada."
        if self.key:
            try:
                self.status.emit("Conectando con Laguna…")
                r=requests.post("https://openrouter.ai/api/v1/chat/completions",headers={"Authorization":"Bearer "+self.key,"Content-Type":"application/json","HTTP-Referer":"https://github.com/openchat-oc/OpenChat","X-Title":"OpenChat"},json={"model":MODEL,"messages":self.messages,"temperature":0.7},timeout=(8,55))
                r.raise_for_status(); answer=r.json()["choices"][0]["message"]["content"]
                if isinstance(answer,list): answer="\n".join(p.get("text","") for p in answer if isinstance(p,dict))
                if str(answer).strip(): self.done.emit(str(answer).strip(),False); return
                raise RuntimeError("El modelo no devolvió texto.")
            except Exception as e: cloud=str(e)
        try:
            self.status.emit("Probando Ollama local…")
            r=requests.post("http://127.0.0.1:11434/api/chat",json={"model":LOCAL,"messages":self.messages,"stream":False},timeout=(3,90))
            r.raise_for_status(); answer=r.json().get("message",{}).get("content","").strip()
            if answer: self.done.emit(answer,True); return
            raise RuntimeError("Ollama no devolvió texto.")
        except Exception as e:
            self.done.emit("No he podido responder.\n\nOpenRouter: "+cloud+"\nOllama: "+str(e)+"\n\nComprueba la clave o instala Ollama y ejecuta: ollama pull "+LOCAL,True)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__(); self.setWindowTitle("OpenChat"); self.setWindowIcon(QIcon(str(Path(__file__).with_name("logo.svg")))); self.resize(900,680); self.setMinimumSize(580,440)
        self.key=read_key(); self.thread=None; self.worker=None; self.last_answer=""
        self.messages=[{"role":"system","content":"Eres OpenChat, un asistente útil, claro y preciso. Responde en el idioma del usuario."}]
        root=QWidget(); root.setObjectName("root"); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QWidget(); header.setObjectName("header"); row=QHBoxLayout(header); row.setContentsMargins(22,15,22,15)
        brand_icon=QLabel("✦"); brand_icon.setFixedSize(40,40); brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); brand_icon.setStyleSheet("font-size:25px;color:#fff;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d83f6,stop:1 #25c7e8);border-radius:13px"); row.addWidget(brand_icon); brand=QLabel("OpenChat"); brand.setStyleSheet("font-size:21px;font-weight:700;letter-spacing:0.3px"); row.addWidget(brand); row.addStretch()
        self.model=QLabel("Laguna + Ollama"); self.model.setStyleSheet("color:#aaaabb;font-size:12px"); row.addWidget(self.model)
        self.update_btn=QPushButton("Buscar actualizaciones"); self.update_btn.clicked.connect(self.check_updates); row.addWidget(self.update_btn)
        gear=QPushButton("⚙"); gear.clicked.connect(self.configure); row.addWidget(gear); outer.addWidget(header)
        hero=QLabel("🐾  ¡Hola! Soy Chispa, tu compañera de IA. Pídeme ideas, código o que prepare el contenido de un archivo."); hero.setWordWrap(True); hero.setStyleSheet("margin:14px 22px 0 22px;padding:14px 16px;background:#28243e;border:1px solid #49416e;border-radius:15px;color:#dcd7ff;font-size:13px"); outer.addWidget(hero)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.chat=QWidget(); self.chatbox=QVBoxLayout(self.chat); self.chatbox.setContentsMargins(24,24,24,24); self.chatbox.setSpacing(14); self.chatbox.addStretch(); self.scroll.setWidget(self.chat); outer.addWidget(self.scroll,1)
        bottom=QWidget(); bottom.setObjectName("bottom"); b=QVBoxLayout(bottom); b.setContentsMargins(22,12,22,18)
        self.status=QLabel("Listo: Laguna + IA local disponibles" if self.key else "IA local lista. Para activar Laguna, añade tu clave de OpenRouter en ⚙"); self.status.setStyleSheet("color:#aaaabb;font-size:12px"); b.addWidget(self.status)
        actions=QHBoxLayout(); self.savefile=QPushButton("Guardar respuesta como archivo…"); self.savefile.setToolTip("Exporta la última respuesta a un archivo de texto o código"); self.savefile.clicked.connect(self.save_answer); actions.addWidget(self.savefile); actions.addStretch(); b.addLayout(actions)
        line=QHBoxLayout(); self.input=QTextEdit(); self.input.setPlaceholderText("Escribe tu mensaje… (Ctrl+Intro para enviar)"); self.input.setFixedHeight(76); self.input.setAcceptRichText(False); line.addWidget(self.input,1)
        self.send=QPushButton("Enviar  ↗"); self.send.setMinimumWidth(110); self.send.clicked.connect(self.send_message); line.addWidget(self.send); b.addLayout(line); outer.addWidget(bottom)
        self.setStyleSheet("""
        QWidget{font-family:'Noto Sans','Inter',sans-serif;font-size:14px;color:#e9eaf1}
        QMainWindow,#root{background:#17181d} #header,#bottom{background:#202127;border:0}
        #header{border-bottom:1px solid #30313a} #bottom{border-top:1px solid #30313a}
        #chat{background:#17181d} QPushButton{background:#30313a;border:0;border-radius:10px;padding:10px}
        QPushButton:hover{background:#51466f} QPushButton:disabled{background:#4a485f;color:#aaa}
        QTextEdit{background:#292a32;border:1px solid #41424d;border-radius:14px;padding:12px}
        QTextEdit:focus{border:1px solid #8a83f6} QPushButton{font-weight:600}
        """)
        self.add_message("assistant","¡Hola! Soy OpenChat ✨. Puedes pedirme ayuda, código o contenido para archivos. Cuando responda, usa «Guardar respuesta como archivo…» para guardarlo en tu equipo.\\n\\nLa IA local funciona sin clave. Para usar también Laguna, añade tu clave de OpenRouter desde ⚙.")
    def add_message(self,role,text):
        bubble=QWidget(); lay=QVBoxLayout(bubble); lay.setContentsMargins(15,11,15,11)
        name=QLabel("Tú" if role=="user" else "OpenChat"); name.setStyleSheet("font-weight:700;color:#91c9b6" if role=="user" else "font-weight:700;color:#aaa4ff"); lay.addWidget(name)
        body=QLabel(text); body.setWordWrap(True); body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); lay.addWidget(body)
        bubble.setStyleSheet("background:#292a33;border:1px solid #373843;border-radius:14px")
        line=QHBoxLayout()
        if role=="user": line.addStretch(); line.addWidget(bubble)
        else: line.addWidget(bubble); line.addStretch()
        self.chatbox.insertLayout(self.chatbox.count()-1,line)
        self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum())
    def check_updates(self):
        self.update_btn.setEnabled(False); self.status.setText("Comprobando actualizaciones de OpenChat…")
        try:
            result=subprocess.run(["git","-C",str(Path(__file__).resolve().parents[1]),"ls-remote","origin","refs/heads/main"],capture_output=True,text=True,timeout=8,check=True)
            remote=result.stdout.split()[0] if result.stdout.split() else ""
            local=subprocess.run(["git","-C",str(Path(__file__).resolve().parents[1]),"rev-parse","HEAD"],capture_output=True,text=True,timeout=3,check=True).stdout.strip()
            if not remote:
                raise RuntimeError("GitHub no devolvió la versión actual.")
            if remote==local:
                self.status.setText("OpenChat está actualizado.")
                QMessageBox.information(self,"OpenChat está actualizado","Ya tienes la versión más reciente de la rama main.")
            else:
                self.status.setText("Hay una actualización disponible.")
                QMessageBox.information(self,"Actualización disponible","Hay cambios en GitHub. Cierra OpenChat y ejecuta en una terminal:\n\ncd ~/OpenChat && git pull --ff-only\n\nDespués vuelve a abrir la aplicación.")
        except Exception as e:
            self.status.setText("No se pudo comprobar la actualización.")
            QMessageBox.warning(self,"No se pudo comprobar", "Comprueba la conexión a Internet y que Git esté instalado.\n\n"+str(e))
        finally:
            self.update_btn.setEnabled(True)
    def save_answer(self):
        if not self.last_answer.strip():
            QMessageBox.information(self,"Todavía no hay respuesta","Primero pídele a Chispa que cree el contenido que quieres guardar.")
            return
        path,_=QFileDialog.getSaveFileName(self,"Guardar respuesta de OpenChat",str(Path.home()/"respuesta-openchat.txt"),"Texto (*.txt);;Python (*.py);;JavaScript (*.js);;HTML (*.html);;CSS (*.css);;Markdown (*.md);;JSON (*.json);;Todos los archivos (*)")
        if not path: return
        try:
            Path(path).write_text(self.last_answer,encoding="utf-8")
            self.status.setText("Archivo guardado: "+Path(path).name)
        except OSError as e:
            QMessageBox.critical(self,"No se pudo guardar el archivo",str(e))
    def configure(self):
        d=KeyDialog(self,self.key)
        if d.exec()==QDialog.DialogCode.Accepted and d.entry.text().strip():
            try: save_key(d.entry.text()); self.key=d.entry.text().strip(); self.status.setText("Clave guardada localmente.")
            except OSError as e: QMessageBox.critical(self,"Error al guardar",str(e))
    def send_message(self):
        text=self.input.toPlainText().strip()
        if not text or self.thread is not None: return
        self.input.clear(); self.add_message("user",text); self.messages.append({"role":"user","content":text})
        self.send.setEnabled(False); self.status.setText("Pensando…")
        self.thread=QThread(self); self.worker=Worker(self.messages.copy(),self.key); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.status.connect(self.status.setText); self.worker.done.connect(self.answer); self.worker.done.connect(self.thread.quit); self.thread.finished.connect(self.cleanup); self.thread.start()
    def answer(self,text,local):
        self.last_answer=text; self.add_message("assistant",text); self.messages.append({"role":"assistant","content":text})
        self.status.setText("Respuesta de Ollama (local)" if local else "Respuesta de Laguna (OpenRouter)")
        self.model.setText("Ollama · local" if local else "Laguna · respaldo local"); self.send.setEnabled(True)
    def cleanup(self):
        if self.worker: self.worker.deleteLater()
        self.worker=None; self.thread=None; self.send.setEnabled(True)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier: self.send_message(); event.accept(); return
        super().keyPressEvent(event)

def main():
    app=QApplication(sys.argv); app.setApplicationName("OpenChat"); win=MainWindow(); win.show(); sys.exit(app.exec())
if __name__=="__main__": main()
