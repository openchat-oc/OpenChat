#!/usr/bin/env python3
import sys, subprocess, re
from pathlib import Path
from .safe_files import is_safe_filename, write_text_safely
import requests
from PySide6.QtCore import QObject, Signal, QThread, Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout,
    QWidget, QFileDialog, QProgressBar, QGraphicsOpacityEffect)

CONFIG = Path.home()/".config"/"openchat"
KEYFILE = CONFIG/"openrouter.key"
LEGACY = Path.home()/".config"/"oi-auto"/"openrouter.key"
MODEL = "poolside/laguna-s-2.1:free"
LOCAL = "qwen2.5:1.5b"

def read_key():
    try:
        if KEYFILE.exists(): return KEYFILE.read_text(encoding="utf-8").strip()
        if LEGACY.exists():
            key=LEGACY.read_text(encoding="utf-8").strip()
            if key: save_key(key)
            return key
    except OSError: pass
    return ""

def save_key(key):
    CONFIG.mkdir(parents=True, exist_ok=True)
    KEYFILE.write_text(key.strip(), encoding="utf-8")
    try: KEYFILE.chmod(0o600)
    except OSError: pass

def validate_key(key):
    r=requests.get("https://openrouter.ai/api/v1/key",
        headers={"Authorization":"Bearer "+key.strip()}, timeout=(5,12))
    if r.status_code in (401,403): return False, "La clave no es válida. Revisa que la hayas copiado completa."
    r.raise_for_status()
    return True, "Clave verificada."

class ChatInput(QTextEdit):
    send_requested = Signal()
    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (event.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.send_requested.emit()
            event.accept()
            return
        super().keyPressEvent(event)

class SetupDialog(QDialog):
    def __init__(self):
        super().__init__(); self.setWindowTitle("Primer inicio · OpenChat"); self.setMinimumWidth(480); self.setModal(True)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowCloseButtonHint)
        box=QVBoxLayout(self); box.setContentsMargins(30,28,30,28); box.setSpacing(14)
        logo=QLabel("◕ᴗ◕"); logo.setObjectName("setupMascot"); logo.setAlignment(Qt.AlignmentFlag.AlignCenter); logo.setStyleSheet("font-size:38px;color:#b8a8ff;background:#29233e;border-radius:22px;padding:12px"); box.addWidget(logo)
        self.mascot=logo; self.mascot_phase=False; self.mascot_timer=QTimer(self); self.mascot_timer.timeout.connect(self.animate_mascot); self.mascot_timer.start(700)
        helper=QLabel("¡Hola! Soy Chispa, la mascota de OpenChat ✨\nTe acompaño paso a paso. Primero conectaremos tu IA y después podrás empezar a crear."); helper.setWordWrap(True); helper.setAlignment(Qt.AlignmentFlag.AlignCenter); helper.setStyleSheet("color:#d6d0f0;font-size:13px;background:#242333;border:1px solid #39354f;border-radius:14px;padding:12px"); box.addWidget(helper)
        title=QLabel("Vamos a preparar OpenChat"); title.setAlignment(Qt.AlignmentFlag.AlignCenter); title.setStyleSheet("font-size:25px;font-weight:800"); box.addWidget(title)
        subtitle=QLabel("Antes de entrar, conecta tu cuenta de OpenRouter. Es obligatorio para terminar la configuración."); subtitle.setWordWrap(True); subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter); subtitle.setStyleSheet("color:#aeb0c3;font-size:13px"); box.addWidget(subtitle)
        box.addSpacing(8); box.addWidget(QLabel("Tu clave API de OpenRouter"))
        self.entry=QLineEdit(); self.entry.setEchoMode(QLineEdit.EchoMode.Password); self.entry.setPlaceholderText("sk-or-v1-…"); box.addWidget(self.entry)
        link=QLabel('<a href="https://openrouter.ai/settings/keys">Crear o copiar mi clave en OpenRouter ↗</a>'); link.setOpenExternalLinks(True); box.addWidget(link)
        self.status=QLabel("La clave se guarda solo en este equipo, con permisos privados."); self.status.setWordWrap(True); self.status.setStyleSheet("color:#aeb0c3;font-size:12px"); box.addWidget(self.status)
        self.go=QPushButton("Verificar clave y empezar  →"); self.go.setMinimumHeight(44); self.go.clicked.connect(self.verify); box.addWidget(self.go)
        self.key=""
        self.setStyleSheet("""
        QDialog{background:#171820;color:#eeeeF8} QLabel{color:#eeeef8}
        QLineEdit{background:#242630;border:1px solid #48445f;border-radius:12px;padding:12px;color:#fff}
        QLineEdit:focus{border:1px solid #a092ff}
        QPushButton{background:#8875ee;color:white;border:0;border-radius:12px;padding:12px;font-weight:700}
        QPushButton:hover{background:#a092ff} QPushButton:disabled{background:#514a75;color:#d0c9ed}
        """)
        effect=QGraphicsOpacityEffect(self); self.setGraphicsEffect(effect)
        self.fade=QPropertyAnimation(effect,b"opacity",self); self.fade.setDuration(420); self.fade.setStartValue(0.25); self.fade.setEndValue(1.0); self.fade.setEasingCurve(QEasingCurve.Type.OutCubic); self.fade.start()
    def animate_mascot(self):
        self.mascot_phase=not self.mascot_phase
        self.mascot.setText("◕ᴗ◕" if self.mascot_phase else "◕‿◕")
        self.mascot.setStyleSheet("font-size:38px;color:#d5caff;background:#29233e;border:1px solid "+("#8d7cf1" if self.mascot_phase else "#25c7e8")+";border-radius:24px;padding:12px")
    def reject(self): pass
    def verify(self):
        key=self.entry.text().strip()
        if not key:
            self.status.setText("Necesitas introducir una clave para continuar."); return
        self.go.setEnabled(False); self.go.setText("Verificando…"); self.status.setText("Conectando de forma segura con OpenRouter…"); QApplication.processEvents()
        try:
            valid,msg=validate_key(key)
            if not valid: self.status.setText(msg); return
            save_key(key); self.key=key; self.accept()
        except Exception as e:
            self.status.setText("No se pudo verificar la clave. Comprueba Internet y vuelve a intentarlo.\n"+str(e))
        finally:
            self.go.setEnabled(True); self.go.setText("Verificar clave y empezar  →")

class Worker(QObject):
    done=Signal(str,str); status=Signal(str)
    def __init__(self,messages,key): super().__init__(); self.messages=messages; self.key=key
    def run(self):
        try:
            self.status.emit("Conectando con Laguna")
            with requests.post("https://openrouter.ai/api/v1/chat/completions",
                headers={"Authorization":"Bearer "+self.key,"Content-Type":"application/json",
                "HTTP-Referer":"https://github.com/openchat-oc/OpenChat","X-Title":"OpenChat"},
                json={"model":MODEL,"messages":self.messages,"temperature":0.6},
                timeout=(5,45)) as r:
                r.raise_for_status(); answer=r.json()["choices"][0]["message"]["content"]
            if isinstance(answer,list): answer="\n".join(p.get("text","") for p in answer if isinstance(p,dict))
            if str(answer).strip(): self.done.emit(str(answer).strip(),"Laguna · OpenRouter"); return
            raise RuntimeError("El modelo no devolvió texto.")
        except Exception as cloud_error:
            try:
                self.status.emit("Probando la IA local")
                r=requests.post("http://127.0.0.1:11434/api/chat",
                    json={"model":LOCAL,"messages":self.messages,"stream":False},
                    timeout=(2,75)); r.raise_for_status()
                answer=r.json().get("message",{}).get("content","").strip()
                if answer: self.done.emit(answer,"Ollama · local"); return
                raise RuntimeError("Ollama no devolvió texto.")
            except Exception as local_error:
                self.done.emit("No he podido generar una respuesta.\n\nOpenRouter: "+str(cloud_error)+"\nOllama: "+str(local_error),"Error")

class MainWindow(QMainWindow):
    def __init__(self,key):
        super().__init__(); self.key=key; self.setWindowTitle("OpenChat"); self.setWindowIcon(QIcon(str(Path(__file__).with_name("logo.svg")))); self.resize(1000,740); self.setMinimumSize(650,520)
        self.thread=None; self.worker=None; self.last_answer=""; self.generated_files={}; self.typing_dots=0; self.typing_row=None; self.intro_phase=False
        self.messages=[{"role":"system","content":"""Eres OpenChat, la IA. Chispa es únicamente tu mascota, no la IA. Responde en el idioma del usuario y sé útil, claro y preciso.
Cuando el usuario solicite crear uno o varios archivos, genera el contenido completo y envuelve CADA archivo en este formato exacto:
<openchat-file name="ejemplo.py">
contenido completo del archivo
</openchat-file>
Pon el nombre correcto con extensión, no omitas contenido ni uses puntos suspensivos. Puedes explicar brevemente antes o después de los bloques. No uses este formato para código que solo sea un ejemplo si el usuario no pide un archivo."""}]
        root=QWidget(); root.setObjectName("root"); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QWidget(); header.setObjectName("header"); row=QHBoxLayout(header); row.setContentsMargins(24,16,24,16); row.setSpacing(12)
        brand_icon=QLabel("✦"); brand_icon.setFixedSize(44,44); brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); brand_icon.setStyleSheet("font-size:27px;color:white;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d83f6,stop:1 #25c7e8);border-radius:15px"); row.addWidget(brand_icon)
        titles=QVBoxLayout(); brand=QLabel("OpenChat"); brand.setStyleSheet("font-size:22px;font-weight:800"); sub=QLabel("Tu espacio para pensar y crear"); sub.setStyleSheet("font-size:11px;color:#9b9db2"); titles.addWidget(brand); titles.addWidget(sub); row.addLayout(titles); row.addStretch()
        self.model=QLabel("●  Laguna conectada"); self.model.setStyleSheet("color:#86e0bd;font-size:12px"); row.addWidget(self.model)
        self.update_btn=QPushButton("↻  Actualizaciones"); self.update_btn.clicked.connect(self.check_updates); row.addWidget(self.update_btn)
        gear=QPushButton("⚙  Ajustes"); gear.clicked.connect(self.configure); row.addWidget(gear); outer.addWidget(header)
        hero=QWidget(); hero.setObjectName("hero"); hr=QHBoxLayout(hero); hr.setContentsMargins(22,14,22,14)
        pet=QLabel("◕ᴗ◕"); pet.setAlignment(Qt.AlignmentFlag.AlignCenter); pet.setFixedSize(58,58); pet.setStyleSheet("font-size:22px;font-weight:800;color:#c9c0ff;background:#29233e;border:1px solid #554a7e;border-radius:20px"); hr.addWidget(pet)
        hv=QVBoxLayout(); ht=QLabel("Chispa está contigo"); ht.setStyleSheet("font-size:15px;font-weight:700;color:#e3dcff"); hd=QLabel("Pregunta, programa, crea ideas o prepara contenido para guardar como archivo."); hd.setWordWrap(True); hd.setStyleSheet("font-size:12px;color:#b6b3ca"); hv.addWidget(ht); hv.addWidget(hd); hr.addLayout(hv,1); outer.addWidget(hero)
        self.scroll=QScrollArea(); self.scroll.setWidgetResizable(True); self.scroll.setFrameShape(QScrollArea.Shape.NoFrame); self.scroll.setObjectName("scroll")
        self.chat=QWidget(); self.chat.setObjectName("chat"); self.chatbox=QVBoxLayout(self.chat); self.chatbox.setContentsMargins(28,26,28,26); self.chatbox.setSpacing(18); self.chatbox.addStretch(); self.scroll.setWidget(self.chat); outer.addWidget(self.scroll,1)
        bottom=QWidget(); bottom.setObjectName("bottom"); b=QVBoxLayout(bottom); b.setContentsMargins(24,12,24,20); b.setSpacing(10)
        self.status=QLabel("Listo para empezar · clave verificada"); self.status.setStyleSheet("color:#9b9db2;font-size:12px"); b.addWidget(self.status)
        line=QHBoxLayout(); line.setSpacing(10); self.input=ChatInput(); self.input.setPlaceholderText("Escribe lo que necesitas…  ·  Intro para enviar · Mayús+Intro para nueva línea"); self.input.setFixedHeight(82); self.input.setAcceptRichText(False); self.input.send_requested.connect(self.send_message); self.input.setTabChangesFocus(False); line.addWidget(self.input,1)
        self.send=QPushButton("Enviar  ↗"); self.send.setObjectName("send"); self.send.setMinimumWidth(120); self.send.setMinimumHeight(48); self.send.clicked.connect(self.send_message); line.addWidget(self.send); b.addLayout(line)
        actions=QHBoxLayout(); self.savefile=QPushButton("↓  Guardar respuesta"); self.savefile.clicked.connect(self.save_answer); actions.addWidget(self.savefile); self.files_btn=QPushButton("▣  Guardar archivos creados"); self.files_btn.clicked.connect(self.save_generated_files); self.files_btn.setEnabled(False); actions.addWidget(self.files_btn); actions.addStretch(); tip=QLabel("Tus conversaciones se procesan con la IA elegida"); tip.setStyleSheet("color:#77798d;font-size:11px"); actions.addWidget(tip); b.addLayout(actions); outer.addWidget(bottom)
        self.setStyleSheet("""
        QWidget{font-family:'Noto Sans','Inter',sans-serif;font-size:14px;color:#ececf5}
        QMainWindow,#root,#chat{background:#15161c} #header,#bottom{background:#1d1e26;border:0}
        #header{border-bottom:1px solid #30313d} #bottom{border-top:1px solid #30313d} #hero{background:#211f31;border-bottom:1px solid #38334d}
        QPushButton{background:#2c2e3a;border:1px solid #3a3c4b;border-radius:12px;padding:10px 14px;font-weight:650}
        QPushButton:hover{background:#45405f;border-color:#7770a8} QPushButton:disabled{background:#292a33;color:#77798d}
        #send{background:#8875ee;color:white;border:0;font-size:14px} #send:hover{background:#a092ff}
        QTextEdit{background:#242630;border:1px solid #3b3d4b;border-radius:15px;padding:13px;selection-background-color:#6556b4}
        QTextEdit:focus{border:1px solid #9383ff} QScrollArea{border:0}
        """)
        self.add_message("assistant","¡Hola! Soy OpenChat ✨. Chispa, mi mascota, te acompañará mientras trabajamos.\n\nPuedes escribirme directamente sin pulsar el cuadro de texto. Pulsa Intro para enviar y Mayús+Intro para saltar de línea. Si me pides crear archivos, prepararé el contenido para que puedas guardarlo. ¿Qué hacemos hoy?")
        effect=QGraphicsOpacityEffect(self); self.setGraphicsEffect(effect); effect.setOpacity(0.0)
        self.fade=QPropertyAnimation(effect,b"opacity",self); self.fade.setDuration(600); self.fade.setStartValue(0.0); self.fade.setEndValue(1.0); self.fade.setEasingCurve(QEasingCurve.Type.OutCubic); self.fade.start()
        QApplication.instance().installEventFilter(self)
    def add_message(self,role,text):
        bubble=QWidget(); bubble.setMaximumWidth(760); lay=QVBoxLayout(bubble); lay.setContentsMargins(17,14,17,14); lay.setSpacing(7)
        name=QLabel("TÚ" if role=="user" else "✦  OPENCHAT"); name.setStyleSheet("font-size:10px;font-weight:800;letter-spacing:1px;color:#8fd9c0" if role=="user" else "font-size:10px;font-weight:800;letter-spacing:1px;color:#aaa0ff"); lay.addWidget(name)
        body=QLabel(text); body.setWordWrap(True); body.setTextFormat(Qt.TextFormat.PlainText); body.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); body.setStyleSheet("font-size:14px;line-height:1.5;color:#e8e8f1"); lay.addWidget(body)
        bubble.setStyleSheet("background:#252731;border:1px solid #373946;border-radius:17px" if role=="user" else "background:#1e2029;border:1px solid #30323e;border-radius:17px")
        line=QHBoxLayout()
        if role=="user": line.addStretch(); line.addWidget(bubble)
        else: line.addWidget(bubble); line.addStretch()
        self.chatbox.insertLayout(self.chatbox.count()-1,line); QTimer.singleShot(20,lambda:self.scroll.verticalScrollBar().setValue(self.scroll.verticalScrollBar().maximum()))
    def show_typing(self):
        bubble=QWidget(); lay=QHBoxLayout(bubble); lay.setContentsMargins(16,10,16,10); lay.setSpacing(9)
        lab=QLabel("OpenChat está pensando"); lab.setStyleSheet("color:#aaa0ff;font-weight:650"); self.dots=QLabel("●  ●  ●"); self.dots.setStyleSheet("color:#9383ff;letter-spacing:3px"); lay.addWidget(lab); lay.addWidget(self.dots); lay.addStretch()
        self.chatbox.insertWidget(self.chatbox.count()-1,bubble); self.typing_row=bubble
        self.dot_timer=QTimer(self); self.dot_timer.timeout.connect(self.animate_dots); self.dot_timer.start(360)
    def animate_dots(self):
        self.typing_dots=(self.typing_dots+1)%4; self.dots.setText(" ".join(["●"]*self.typing_dots+["○"]*(3-self.typing_dots)))
    def hide_typing(self):
        if hasattr(self,"dot_timer"): self.dot_timer.stop()
        if self.typing_row:
            self.chatbox.removeWidget(self.typing_row); self.typing_row.deleteLater(); self.typing_row=None
    def check_updates(self):
        self.update_btn.setEnabled(False); self.status.setText("Comprobando actualizaciones…")
        try:
            repo=Path(__file__).resolve().parents[1]
            remote=subprocess.run(["git","-C",str(repo),"ls-remote","origin","refs/heads/main"],capture_output=True,text=True,timeout=8,check=True).stdout.split()
            local=subprocess.run(["git","-C",str(repo),"rev-parse","HEAD"],capture_output=True,text=True,timeout=3,check=True).stdout.strip()
            if not remote: raise RuntimeError("GitHub no devolvió una versión.")
            if remote[0]==local: self.status.setText("✓ OpenChat está actualizado."); QMessageBox.information(self,"OpenChat","Ya tienes la versión más reciente.")
            else: self.status.setText("Hay una actualización disponible."); QMessageBox.information(self,"Actualización disponible","Cierra OpenChat y ejecuta:\n\ncd ~/OpenChat && git pull --ff-only\n\nDespués vuelve a abrirlo.")
        except Exception as e: self.status.setText("No se pudo comprobar la actualización."); QMessageBox.warning(self,"Actualizaciones",str(e))
        finally: self.update_btn.setEnabled(True)
    def eventFilter(self, watched, event):
        if event.type()==QEvent.Type.KeyPress and self.isActiveWindow():
            focus=QApplication.focusWidget()
            if focus not in (self.input, self.input.viewport()):
                if not (event.modifiers() & (Qt.KeyboardModifier.ControlModifier|Qt.KeyboardModifier.AltModifier|Qt.KeyboardModifier.MetaModifier)):
                    ch=event.text()
                    if ch and ch.isprintable() and len(ch)==1:
                        self.input.setFocus()
                        self.input.insertPlainText(ch)
                        return True
        return super().eventFilter(watched,event)
    def save_generated_files(self):
        if not self.generated_files:
            QMessageBox.information(self,"No hay archivos","Pide a OpenChat que cree un archivo y después podrás guardarlo aquí.")
            return
        folder=QFileDialog.getExistingDirectory(self,"¿Dónde guardamos los archivos?",str(Path.home()/"Documents"))
        if not folder: return
        root=Path(folder)
        saved=[]; errors=[]; skipped=[]
        conflicts=[name for name in self.generated_files if (root/name).exists()]
        overwrite=False
        if conflicts:
            answer=QMessageBox.question(
                self,"Confirmar sobrescritura",
                "Ya existen estos archivos y se reemplazarán solo si lo autorizas:\n\n"+
                "\n".join(conflicts)+"\n\n¿Quieres sobrescribirlos?",
                QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No)
            overwrite=answer==QMessageBox.StandardButton.Yes
        for name,content in self.generated_files.items():
            try:
                path=write_text_safely(root,name,content,overwrite=overwrite)
                if path is None:
                    skipped.append(name)
                else:
                    saved.append(name)
            except (OSError,ValueError) as e:
                errors.append(name+": "+str(e))
        if saved:
            self.status.setText("Guardados "+str(len(saved))+" archivo(s) en "+str(root))
            message="Se han guardado estos archivos:\n\n"+"\n".join(saved)+"\n\nCarpeta: "+str(root)
            if skipped: message+="\n\nNo se sobrescribieron:\n"+"\n".join(skipped)
            if errors: message+="\n\nErrores:\n"+"\n".join(errors)
            QMessageBox.information(self,"Archivos creados",message)
        elif errors or skipped:
            message="No se guardó ningún archivo."
            if skipped: message+="\n\nNo se sobrescribieron:\n"+"\n".join(skipped)
            if errors: message+="\n\nErrores:\n"+"\n".join(errors)
            QMessageBox.warning(self,"No se pudieron guardar",message)
    def save_answer(self):
        if not self.last_answer.strip(): QMessageBox.information(self,"Aún no hay respuesta","Primero pide a OpenChat el contenido que quieres guardar."); return
        path,_=QFileDialog.getSaveFileName(self,"Guardar archivo",str(Path.home()/"respuesta-openchat.txt"),"Texto (*.txt);;Python (*.py);;JavaScript (*.js);;HTML (*.html);;CSS (*.css);;Markdown (*.md);;JSON (*.json);;Todos los archivos (*)")
        if not path: return
        try: Path(path).write_text(self.last_answer,encoding="utf-8"); self.status.setText("Archivo guardado: "+Path(path).name)
        except OSError as e: QMessageBox.critical(self,"Error al guardar",str(e))
    def configure(self):
        d=SetupDialog()
        if d.exec()==QDialog.DialogCode.Accepted: self.key=d.key; self.status.setText("Clave verificada y guardada.")
    def send_message(self):
        text=self.input.toPlainText().strip()
        if not text or self.thread is not None: return
        self.input.clear(); self.add_message("user",text); self.messages.append({"role":"user","content":text})
        self.send.setEnabled(False); self.status.setText("OpenChat está pensando"); self.show_typing()
        self.thread=QThread(self); self.worker=Worker(self.messages.copy(),self.key); self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run); self.worker.status.connect(self.status.setText); self.worker.done.connect(self.answer); self.worker.done.connect(self.thread.quit); self.thread.finished.connect(self.cleanup); self.thread.start()
    def answer(self,text,source):
        self.hide_typing(); self.last_answer=text
        matches=re.findall(r"""<openchat-file\s+name=["']([^"']+)["']\s*>(.*?)</openchat-file>""",text,re.S|re.I)
        self.generated_files={}
        rejected=[]
        for name,content in matches:
            name=name.strip()
            if is_safe_filename(name):
                self.generated_files[name]=content.strip()+"\n"
            else:
                rejected.append(name or "(nombre vacío)")
        self.files_btn.setEnabled(bool(self.generated_files))
        shown=re.sub(r"""<openchat-file\s+name=["']([^"']+)["']\s*>(.*?)</openchat-file>""",lambda m:"📄 Archivo preparado: "+(m.group(1).strip() if is_safe_filename(m.group(1).strip()) else "nombre de archivo no permitido"),text,flags=re.S|re.I)
        if rejected:
            shown += "\n\nSe han descartado nombres de archivo no seguros: " + ", ".join(rejected)
        shown=shown.replace("\\\n","\n")
        self.add_message("assistant",shown); self.messages.append({"role":"assistant","content":text})
        if self.generated_files: self.status.setText(str(len(self.generated_files))+" archivo(s) listo(s) para guardar · "+source)
        else: self.status.setText("Respuesta recibida · "+source)
        self.model.setText("●  "+source); self.send.setEnabled(True)
    def cleanup(self):
        self.hide_typing()
        if self.worker: self.worker.deleteLater()
        self.worker=None; self.thread=None; self.send.setEnabled(True)
    def keyPressEvent(self,event):
        if event.key() in (Qt.Key.Key_Return,Qt.Key.Key_Enter) and event.modifiers() & Qt.KeyboardModifier.ControlModifier: self.send_message(); event.accept(); return
        super().keyPressEvent(event)

def main():
    app=QApplication(sys.argv); app.setApplicationName("OpenChat")
    key=read_key()
    if not key:
        setup=SetupDialog()
        if setup.exec()!=QDialog.DialogCode.Accepted: return
        key=setup.key
    else:
        try:
            valid,_=validate_key(key)
            if not valid: key=""
        except Exception: pass
        if not key:
            setup=SetupDialog()
            if setup.exec()!=QDialog.DialogCode.Accepted: return
            key=setup.key
    win=MainWindow(key); win.show(); sys.exit(app.exec())
if __name__=="__main__": main()
