#!/usr/bin/env python3
import sys, subprocess, re, json, os, platform
from pathlib import Path
from .safe_files import is_safe_filename, write_text_safely
from .agent import launch_agent
import requests
from PySide6.QtCore import QObject, Signal, QThread, Qt, QTimer, QPropertyAnimation, QEasingCurve, QEvent
from PySide6.QtGui import QIcon, QFont
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QLineEdit,
    QMainWindow, QMessageBox, QPushButton, QScrollArea, QTextEdit, QVBoxLayout,
    QWidget, QFileDialog, QProgressBar, QGraphicsOpacityEffect, QComboBox, QInputDialog)

CONFIG = Path.home()/".config"/"openchat"
KEYFILE = CONFIG/"openrouter.key"
SETTINGS = CONFIG/"settings.json"
HISTORY = CONFIG/"conversation.json"
LEGACY = Path.home()/".config"/"oi-auto"/"openrouter.key"
MODEL = "poolside/laguna-s-2.1:free"
LOCAL = "qwen2.5:1.5b"

def system_profile():
    """Return a conservative local-model recommendation based on available RAM."""
    ram_gb = 8.0
    try:
        if sys.platform.startswith("linux"):
            with open("/proc/meminfo", encoding="utf-8") as f:
                for line in f:
                    if line.startswith("MemTotal:"):
                        ram_gb = int(line.split()[1]) / 1024 / 1024
                        break
        elif sys.platform == "win32":
            import ctypes
            class MemoryStatus(ctypes.Structure):
                _fields_ = [("length", ctypes.c_ulong), ("memoryLoad", ctypes.c_ulong),
                    ("totalPhys", ctypes.c_ulonglong), ("availPhys", ctypes.c_ulonglong),
                    ("totalPageFile", ctypes.c_ulonglong), ("availPageFile", ctypes.c_ulonglong),
                    ("totalVirtual", ctypes.c_ulonglong), ("availVirtual", ctypes.c_ulonglong),
                    ("availExtendedVirtual", ctypes.c_ulonglong)]
            status = MemoryStatus()
            status.length = ctypes.sizeof(MemoryStatus)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                ram_gb = status.totalPhys / (1024 ** 3)
    except (OSError, ValueError, AttributeError):
        pass
    cores = os.cpu_count() or 2
    if ram_gb < 6 or cores <= 2:
        model, tier = "qwen2.5:0.5b", "básico"
    elif ram_gb <= 10:
        model, tier = "qwen2.5:1.5b", "equilibrado"
    else:
        model, tier = "qwen2.5:3b", "más capaz"
    return {"ram_gb": round(ram_gb, 1), "cores": cores, "local_model": model, "tier": tier}

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

def load_settings():
    defaults={"mode":"auto","model":MODEL,"local_model":system_profile()["local_model"],"setup_complete":False}
    try:
        value=json.loads(SETTINGS.read_text(encoding="utf-8"))
        if isinstance(value,dict):
            if value.get("mode") in ("auto","cloud","local"): defaults["mode"]=value["mode"]
            if isinstance(value.get("model"),str) and value["model"].strip(): defaults["model"]=value["model"].strip()
            if isinstance(value.get("local_model"),str) and value["local_model"].strip(): defaults["local_model"]=value["local_model"].strip()
            if isinstance(value.get("setup_complete"),bool): defaults["setup_complete"]=value["setup_complete"]
    except (OSError,ValueError,TypeError):
        pass
    return defaults

def save_settings(settings):
    CONFIG.mkdir(parents=True,exist_ok=True)
    payload={"mode":settings.get("mode","auto"),"model":settings.get("model",MODEL),"local_model":settings.get("local_model",system_profile()["local_model"]),"setup_complete":bool(settings.get("setup_complete",True))}
    temporary=SETTINGS.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    try: temporary.chmod(0o600)
    except OSError: pass
    temporary.replace(SETTINGS)
    try: SETTINGS.chmod(0o600)
    except OSError: pass

def load_history():
    try:
        data=json.loads(HISTORY.read_text(encoding="utf-8"))
        if isinstance(data,list):
            return [item for item in data[-80:] if isinstance(item,dict) and item.get("role") in ("user","assistant") and isinstance(item.get("content"),str)]
    except (OSError,ValueError,TypeError):
        pass
    return []

def save_history(messages):
    try:
        CONFIG.mkdir(parents=True,exist_ok=True)
        history=[item for item in messages if item.get("role") in ("user","assistant") and isinstance(item.get("content"),str)][-80:]
        temp=HISTORY.with_suffix(".tmp")
        temp.write_text(json.dumps(history,ensure_ascii=False,indent=2),encoding="utf-8")
        try: temp.chmod(0o600)
        except OSError: pass
        temp.replace(HISTORY)
        try: HISTORY.chmod(0o600)
        except OSError: pass
    except OSError:
        # A history-write failure must not prevent the current conversation from working.
        pass

def local_status():
    response=requests.get("http://127.0.0.1:11434/api/tags",timeout=(2,4))
    response.raise_for_status()
    data=response.json()
    return [item.get("name","") for item in data.get("models",[]) if item.get("name")]

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
    def __init__(self, settings=None, current_key=""):
        super().__init__()
        self.settings=settings or load_settings()
        self.key=""
        self.setWindowTitle("Configuración · OpenChat")
        self.setMinimumWidth(500); self.setModal(True)
        box=QVBoxLayout(self); box.setContentsMargins(30,26,30,26); box.setSpacing(12)
        logo=QLabel("◕ᴗ◕"); logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo.setStyleSheet("font-size:36px;color:#c9c0ff;background:#29233e;border-radius:22px;padding:10px"); box.addWidget(logo)
        title=QLabel("Prepara OpenChat"); title.setAlignment(Qt.AlignmentFlag.AlignCenter); title.setStyleSheet("font-size:24px;font-weight:800"); box.addWidget(title)
        helper=QLabel("Chispa es la mascota de OpenChat. Elige dónde quieres ejecutar la IA; puedes cambiarlo después en Ajustes.")
        helper.setWordWrap(True); helper.setAlignment(Qt.AlignmentFlag.AlignCenter); box.addWidget(helper)
        box.addWidget(QLabel("Motor de IA"))
        self.mode=QComboBox(); self.mode.addItem("Automático · recomendado","auto"); self.mode.addItem("Nube · OpenRouter","cloud"); self.mode.addItem("Local · Ollama","local")
        idx=self.mode.findData(self.settings.get("mode","auto"))
        if idx>=0: self.mode.setCurrentIndex(idx)
        box.addWidget(self.mode)
        box.addWidget(QLabel("Modelo"))
        self.model=QComboBox(); self.model.setEditable(True)
        for model in (MODEL,"anthropic/claude-3.5-sonnet","openai/gpt-4o-mini",LOCAL,system_profile()["local_model"]):
            if self.model.findText(model)<0: self.model.addItem(model)
        self.model.setCurrentText(self.settings.get("model",MODEL)); box.addWidget(self.model)
        profile=system_profile()
        self.profile_info=QLabel(f"Este PC: {profile['ram_gb']} GB de RAM · {profile['cores']} núcleos. Modelo local recomendado: {profile['local_model']} ({profile['tier']}).")
        self.profile_info.setWordWrap(True); self.profile_info.setStyleSheet("color:#b6b3ca;font-size:12px"); box.addWidget(self.profile_info)
        box.addWidget(QLabel("Clave API de OpenRouter (solo para modo nube)"))
        self.entry=QLineEdit(current_key or read_key()); self.entry.setEchoMode(QLineEdit.EchoMode.Password); self.entry.setPlaceholderText("sk-or-v1-…"); box.addWidget(self.entry)
        self.show_key=QPushButton("Mostrar / ocultar clave"); self.show_key.setCheckable(True)
        self.show_key.toggled.connect(lambda shown:self.entry.setEchoMode(QLineEdit.EchoMode.Normal if shown else QLineEdit.EchoMode.Password)); box.addWidget(self.show_key)
        link=QLabel('<a href="https://openrouter.ai/settings/keys">1. Crear / gestionar clave API ↗</a>'); link.setOpenExternalLinks(True); box.addWidget(link)
        api_help=QLabel("2. Inicia sesión en OpenRouter y crea una key. 3. Cópiala completa aquí (suele empezar por sk-or-). 4. Pulsa «Comprobar y guardar». No la compartas ni la subas a GitHub. Puedes usar Automático sin clave si tienes un modelo local en Ollama.")
        api_help.setWordWrap(True); api_help.setStyleSheet("color:#b6b3ca;font-size:12px"); box.addWidget(api_help)
        self.status=QLabel("La clave se almacena localmente. En modo local no se envían mensajes a OpenRouter.")
        self.status.setWordWrap(True); box.addWidget(self.status)
        row=QHBoxLayout(); cancel=QPushButton("Cancelar"); cancel.clicked.connect(self.reject); row.addWidget(cancel)
        self.go=QPushButton("Comprobar y guardar"); self.go.clicked.connect(self.verify); row.addWidget(self.go); box.addLayout(row)
        self.setStyleSheet("QDialog{background:#171820;color:#eeeef8} QLabel{color:#eeeef8} QLineEdit,QComboBox{background:#242630;border:1px solid #48445f;border-radius:10px;padding:10px;color:#fff} QPushButton{background:#8875ee;color:white;border:0;border-radius:10px;padding:11px;font-weight:700} QPushButton:hover{background:#a092ff}")
        self.mode.currentIndexChanged.connect(self.update_mode); self.update_mode()
    def update_mode(self,*_):
        mode=self.mode.currentData(); cloud=mode in ("cloud","auto")
        self.entry.setEnabled(cloud); self.show_key.setEnabled(cloud)
        if mode=="auto": self.status.setText("Automático: prefiere OpenRouter si hay una clave válida; si falla, prueba el modelo local recomendado de Ollama. El estado del proveedor se mostrará en el chat.")
        elif mode=="cloud": self.status.setText("Se usará OpenRouter; se necesita una clave válida.")
        else:
            self.status.setText("Se usará Ollama local. Selecciona abajo un modelo que ya esté instalado; no se descargarán modelos sin permiso.")
            if self.model.currentText() not in (LOCAL, system_profile()["local_model"]): self.model.setCurrentText(self.settings.get("local_model",system_profile()["local_model"]))
    def verify(self):
        mode=self.mode.currentData(); model=self.model.currentText().strip(); key=self.entry.text().strip()
        if not model: self.status.setText("Escribe el identificador del modelo de OpenRouter."); return
        self.go.setEnabled(False); self.status.setText("Comprobando proveedor…")
        try:
            if mode in ("cloud","auto") and key:
                valid,msg=validate_key(key)
                if not valid: self.status.setText(msg); return
                save_key(key); self.key=key
            elif mode=="cloud":
                self.status.setText("Introduce una clave API válida de OpenRouter."); return
            else:
                self.key=""
            if mode=="local" or (mode=="auto" and not key):
                models=local_status()
                if not models:
                    self.status.setText("No responde Ollama o no hay modelos. Inicia Ollama y descarga un modelo; o introduce una clave para usar la nube.")
                    return
                recommended=system_profile()["local_model"]
                selected_local=recommended if recommended in models else models[0]
                if mode=="local" and model not in models:
                    self.status.setText("El modelo local elegido no está instalado. Disponibles: "+", ".join(models)); return
            else:
                selected_local=system_profile()["local_model"]
                try:
                    models=local_status()
                    if selected_local not in models and models:
                        selected_local=models[0]
                except Exception:
                    pass
            self.settings={"mode":mode,"model":model,"local_model":selected_local,"setup_complete":True}
            save_settings(self.settings); self.accept()
        except requests.HTTPError as e:
            code=e.response.status_code if e.response is not None else "?"
            self.status.setText("El proveedor devolvió HTTP "+str(code)+". Revisa clave, modelo y cuota.")
        except Exception as e:
            self.status.setText("No se pudo comprobar el proveedor: "+str(e))
        finally:
            self.go.setEnabled(True)


class Worker(QObject):
    done=Signal(str,str); status=Signal(str)
    def __init__(self,messages,key,mode,model,local_model=None):
        super().__init__(); self.messages=messages; self.key=key; self.mode=mode; self.model=model; self.local_model=local_model or system_profile()["local_model"]
    def ask_local(self):
        self.status.emit("Conectando con Ollama local · "+self.local_model)
        r=requests.post("http://127.0.0.1:11434/api/chat",json={"model":self.local_model,"messages":self.messages,"stream":False},timeout=(2,120))
        r.raise_for_status()
        answer=r.json().get("message",{}).get("content","").strip()
        if not answer: raise RuntimeError("Ollama no devolvió texto.")
        return answer, "Ollama · local · "+self.local_model
    def ask_cloud(self):
        self.status.emit("Conectando con OpenRouter · "+self.model)
        with requests.post("https://openrouter.ai/api/v1/chat/completions",
            headers={"Authorization":"Bearer "+self.key,"Content-Type":"application/json","HTTP-Referer":"https://github.com/openchat-oc/OpenChat","X-Title":"OpenChat"},
            json={"model":self.model,"messages":self.messages,"temperature":0.6},timeout=(5,60)) as r:
            r.raise_for_status(); answer=r.json()["choices"][0]["message"]["content"]
        if isinstance(answer,list): answer="\\n".join(p.get("text","") for p in answer if isinstance(p,dict))
        if not str(answer).strip(): raise RuntimeError("El modelo no devolvió texto.")
        return str(answer).strip(), "OpenRouter · "+self.model
    def run(self):
        if self.mode=="local":
            try:
                answer,source=self.ask_local(); self.done.emit(answer,source)
            except Exception as e: self.done.emit("No se pudo obtener respuesta de Ollama.\\n\\n"+str(e),"Error")
            return
        if self.mode=="cloud":
            try:
                answer,source=self.ask_cloud(); self.done.emit(answer,source)
            except requests.HTTPError as e:
                code=e.response.status_code if e.response is not None else "?"
                self.done.emit("OpenRouter devolvió HTTP "+str(code)+". Comprueba clave, modelo y cuota. No se ha cambiado de proveedor automáticamente.","Error")
            except Exception as e: self.done.emit("No se pudo conectar con OpenRouter.\\n\\n"+str(e),"Error")
            return
        # Auto mode: cloud is preferred when a key exists; fallback is explicit in status/source.
        if self.key:
            try:
                answer,source=self.ask_cloud(); self.done.emit(answer,source+" · automático"); return
            except Exception as cloud_error:
                self.status.emit("OpenRouter no está disponible; probando Ollama local…")
                try:
                    answer,source=self.ask_local()
                    self.done.emit(answer,source+" · alternativa automática (OpenRouter falló)")
                    return
                except Exception as local_error:
                    self.done.emit("Fallaron OpenRouter y Ollama.\\n\\nOpenRouter: "+str(cloud_error)+"\\nOllama: "+str(local_error)+"\\n\\nRevisa Ajustes y los modelos instalados.","Error")
                    return
        try:
            answer,source=self.ask_local(); self.done.emit(answer,source+" · automático (sin clave de nube)")
        except Exception as e:
            self.done.emit("El modo automático no tiene clave de OpenRouter y Ollama no está disponible.\\n\\n"+str(e)+"\\n\\nAbre Ajustes para añadir una clave o inicia Ollama con un modelo instalado.","Error")

class MainWindow(QMainWindow):
    def __init__(self,key,settings=None):
        super().__init__(); self.key=key; self.settings=settings or load_settings(); self.mode=self.settings.get("mode","auto"); self.selected_model=self.settings.get("model",MODEL); self.local_model=self.settings.get("local_model",system_profile()["local_model"]); self.setWindowTitle("OpenChat"); self.setWindowIcon(QIcon(str(Path(__file__).with_name("logo.svg")))); self.resize(1000,740); self.setMinimumSize(650,520)
        self.thread=None; self.worker=None; self.last_answer=""; self.generated_files={}; self.typing_dots=0; self.typing_row=None; self.intro_phase=False
        self.messages=[{"role":"system","content":"""Eres OpenChat, la IA. Chispa es únicamente tu mascota, no la IA. Responde en el idioma del usuario y sé útil, claro y preciso.
Cuando el usuario solicite crear uno o varios archivos, genera el contenido completo y envuelve CADA archivo en este formato exacto:
<openchat-file name="ejemplo.py">
contenido completo del archivo
</openchat-file>
Pon el nombre correcto con extensión, no omitas contenido ni uses puntos suspensivos. Puedes explicar brevemente antes o después de los bloques. No uses este formato para código que solo sea un ejemplo si el usuario no pide un archivo."""}]
        self.messages.extend(load_history())
        root=QWidget(); root.setObjectName("root"); self.setCentralWidget(root); outer=QVBoxLayout(root); outer.setContentsMargins(0,0,0,0); outer.setSpacing(0)
        header=QWidget(); header.setObjectName("header"); row=QHBoxLayout(header); row.setContentsMargins(24,16,24,16); row.setSpacing(12)
        brand_icon=QLabel("✦"); brand_icon.setFixedSize(44,44); brand_icon.setAlignment(Qt.AlignmentFlag.AlignCenter); brand_icon.setStyleSheet("font-size:27px;color:white;background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #9d83f6,stop:1 #25c7e8);border-radius:15px"); row.addWidget(brand_icon)
        titles=QVBoxLayout(); brand=QLabel("OpenChat"); brand.setStyleSheet("font-size:22px;font-weight:800"); sub=QLabel("Tu espacio para pensar y crear"); sub.setStyleSheet("font-size:11px;color:#9b9db2"); titles.addWidget(brand); titles.addWidget(sub); row.addLayout(titles); row.addStretch()
        self.model=QLabel("●  "+("Automático · "+self.selected_model if self.mode=="auto" else ("OpenRouter · "+self.selected_model if self.mode=="cloud" else "Ollama local · "+self.local_model))); self.model.setStyleSheet("color:#86e0bd;font-size:12px"); row.addWidget(self.model)
        self.update_btn=QPushButton("↻  Actualizaciones"); self.update_btn.clicked.connect(self.check_updates); row.addWidget(self.update_btn)
        self.agent_btn=QPushButton("⚡  Agente PC"); self.agent_btn.setToolTip("Abrir Open Interpreter para ejecutar una tarea real con confirmación"); self.agent_btn.clicked.connect(self.launch_pc_agent); row.addWidget(self.agent_btn)
        gear=QPushButton("⚙  Ajustes"); gear.clicked.connect(self.configure); row.addWidget(gear); outer.addWidget(header)
        hero=QWidget(); hero.setObjectName("hero"); hr=QHBoxLayout(hero); hr.setContentsMargins(22,14,22,14)
        pet=QLabel("◕ᴗ◕"); pet.setAlignment(Qt.AlignmentFlag.AlignCenter); pet.setFixedSize(58,58); pet.setStyleSheet("font-size:22px;font-weight:800;color:#c9c0ff;background:#29233e;border:1px solid #554a7e;border-radius:20px"); hr.addWidget(pet)
        hv=QVBoxLayout(); ht=QLabel("Chispa está contigo"); ht.setStyleSheet("font-size:15px;font-weight:700;color:#e3dcff"); hd=QLabel("Pregunta, crea archivos o usa ⚡ Agente PC para pedirle a Open Interpreter que trabaje en tu ordenador con confirmación antes de ejecutar acciones."); hd.setWordWrap(True); hd.setStyleSheet("font-size:12px;color:#b6b3ca"); hv.addWidget(ht); hv.addWidget(hd); hr.addLayout(hv,1); outer.addWidget(hero)
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
        if len(self.messages)==1:
            self.add_message("assistant","¡Hola! Soy OpenChat ✨. Chispa, mi mascota, te acompañará mientras trabajamos.\\n\\nPuedes escribirme directamente sin pulsar el cuadro de texto. Pulsa Intro para enviar y Mayús+Intro para saltar de línea. Si me pides crear archivos, prepararé el contenido para que puedas guardarlo. ¿Qué hacemos hoy?")
        else:
            for item in self.messages[1:]:
                self.add_message(item["role"],item["content"])
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
    def launch_pc_agent(self):
        suggested=self.input.toPlainText().strip()
        task,ok=QInputDialog.getMultiLineText(
            self,"Agente de escritorio · Open Interpreter",
            "Describe la tarea que quieres que realice en este PC. Se abrirá una terminal y Open Interpreter pedirá aprobación antes de ejecutar código.",
            suggested)
        if not ok or not task.strip(): return
        try:
            launch_agent(task)
            self.status.setText("Agente de escritorio abierto en una terminal · revisa y aprueba cada acción.")
        except (OSError,RuntimeError,ValueError) as e:
            QMessageBox.warning(self,"No se pudo abrir el agente",str(e))
            self.status.setText("El agente no se ha iniciado.")
    def configure(self):
        d=SetupDialog(self.settings,self.key)
        if d.exec()==QDialog.DialogCode.Accepted:
            self.key=d.key; self.settings=d.settings; self.mode=self.settings["mode"]; self.selected_model=self.settings["model"]; self.local_model=self.settings.get("local_model",system_profile()["local_model"])
            self.model.setText("●  "+("Automático · "+self.selected_model if self.mode=="auto" else ("OpenRouter · "+self.selected_model if self.mode=="cloud" else "Ollama local · "+self.local_model)))
            self.status.setText("Configuración guardada.")
    def send_message(self):
        text=self.input.toPlainText().strip()
        if not text or self.thread is not None: return
        self.input.clear(); self.add_message("user",text); self.messages.append({"role":"user","content":text})
        save_history(self.messages)
        self.send.setEnabled(False); self.status.setText("OpenChat está pensando"); self.show_typing()
        # Keep the system prompt plus a bounded recent context; full recent history stays on disk.
        context=[self.messages[0]]+self.messages[-30:]
        self.thread=QThread(self); self.worker=Worker(context,self.key,self.mode,self.selected_model,self.local_model); self.worker.moveToThread(self.thread)
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
        shown=shown.replace("\\n", "\n")
        self.add_message("assistant",shown); self.messages.append({"role":"assistant","content":text})
        save_history(self.messages)
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
    settings=load_settings(); key=read_key()
    needs_setup=not settings.get("setup_complete",False) or (settings.get("mode")=="cloud" and not key)
    if needs_setup:
        setup=SetupDialog(settings,key)
        if setup.exec()!=QDialog.DialogCode.Accepted: return
        settings=setup.settings; key=setup.key
    win=MainWindow(key,settings); win.show(); sys.exit(app.exec())
if __name__=="__main__": main()
