import sys
import os
import json
import time
import threading
import asyncio
import tempfile
import string
import requests
import tkinter as tk
from http.server import BaseHTTPRequestHandler, HTTPServer
import edge_tts
import pygame

pygame.mixer.init()

def obtener_ruta_recurso(relativa):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relativa)
    return os.path.join(os.path.abspath("."), relativa)

RUTA_VOZ_PEON = obtener_ruta_recurso("voz_peon.wav")
ARCHIVO_CONFIG = os.path.join(os.path.expanduser("~"), "dota_peon_config.json")

def auto_configurar_dota():
    letras = [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]
    rutas_posibles = [
        r"Program Files (x86)\Steam\steamapps\common\dota 2 beta\game\dota\cfg",
        r"Program Files\Steam\steamapps\common\dota 2 beta\game\dota\cfg",
        r"SteamLibrary\steamapps\common\dota 2 beta\game\dota\cfg",
        r"Steam\steamapps\common\dota 2 beta\game\dota\cfg"
    ]
    ip_local = "127." + "0.0.1:4123/"
    contenido_cfg = f'''"Dota 2 Peon Coach"
{{
    "uri"           "http://{ip_local}"
    "timeout"       "15.0"
    "buffer"        "0.1"
    "throttle"      "0.5"
    "heartbeat"     "30.0"
    "data"
    {{
        "provider"      "1"
        "map"           "1"
        "player"        "1"
        "hero"          "1"
        "abilities"     "1"
        "items"         "1"
        "draft"         "1"
    }}
}}'''
    for disco in letras:
        for subruta in rutas_posibles:
            ruta_cfg = os.path.join(disco, subruta)
            if os.path.exists(ruta_cfg):
                carpeta_gsi = os.path.join(ruta_cfg, "gamestate_integration")
                os.makedirs(carpeta_gsi, exist_ok=True)
                archivo_final = os.path.join(carpeta_gsi, "gamestate_integration_peon.cfg")
                with open(archivo_final, "w", encoding="utf-8") as f:
                    f.write(contenido_cfg)
                return True
    return False

class PeonApp:
    def __init__(self, root):
        self.root = root
        self.api_key = ""
        self.usar_clonacion = tk.BooleanVar(value=True)
        self.rival_linea = ""
        self.cargar_config()

        self.ultimo_nivel = 0
        self.ultimo_minuto_check = -1
        self.aviso_sabiduria = -1
        self.aviso_tormentor = False
        self.items_conocidos = set()
        self.ultimos_kills = 0
        self.ultimas_muertes = 0
        self.tiempo_ultimo_kill = 0
        self.racha_multikill = 0
        self.historial_frases = []
        self.ocupado = False
        self.cliente_clonacion = None
        self.pos_x = 0
        self.pos_y = 0

        self.construir_ventana()

    def cargar_config(self):
        if os.path.exists(ARCHIVO_CONFIG):
            try:
                with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key = data.get("api_key", "")
                    self.usar_clonacion.set(data.get("usar_clonacion", True))
            except:
                pass

    def guardar_config(self):
        self.api_key = self.entry_api.get().strip()
        with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"api_key": self.api_key, "usar_clonacion": self.usar_clonacion.get()}, f)
        self.actualizar_texto("¡Configuración guardada, jefe! A trabajar.", "#81C784")
        self.hablar("¡Listo para trabajar, jefe!")

    def construir_ventana(self):
        self.root.title("Peón Orco Coach")
        self.root.geometry("410x240+50+120")
        self.root.overrideredirect(True)
        self.root.attributes("-topmost", True)
        self.root.attributes("-alpha", 0.92)
        self.root.configure(bg="#121614", highlightbackground="#4caf50", highlightthickness=2)

        # Barra superior arrastrable
        barra_top = tk.Frame(self.root, bg="#1b241e")
        barra_top.pack(fill="x", padx=4, pady=4)
        barra_top.bind("<Button-1>", self.iniciar_arrastre)
        barra_top.bind("<B1-Motion>", self.arrastrar_ventana)

        self.lbl_estado = tk.Label(barra_top, text="🟡 Esperando partida de Dota 2...", bg="#1b241e", fg="#e8f5e9", font=("Segoe UI", 9, "bold"))
        self.lbl_estado.pack(side="left", padx=6)
        self.lbl_estado.bind("<Button-1>", self.iniciar_arrastre)
        self.lbl_estado.bind("<B1-Motion>", self.arrastrar_ventana)

        btn_cerrar = tk.Button(barra_top, text="X", bg="#b71c1c", fg="white", bd=0, font=("Segoe UI", 9, "bold"), width=3, command=self.root.destroy)
        btn_cerrar.pack(side="right", padx=2)

        # Texto del Peon
        self.lbl_mensaje = tk.Label(
            self.root,
            text="🪓 Peón: ¡Listo para trabajar! Pega tu API Key abajo y entra a jugar.",
            bg="#121614", fg="#a5d6a7", font=("Segoe UI", 10, "bold"),
            wraplength=385, justify="left"
        )
        self.lbl_mensaje.pack(fill="both", expand=True, padx=12, pady=6)

        # Fila Rival de linea
        fila_rival = tk.Frame(self.root, bg="#121614")
        fila_rival.pack(fill="x", padx=10, pady=4)

        self.entry_rival = tk.Entry(fila_rival, bg="#1e2621", fg="white", insertbackground="white", font=("Segoe UI", 9))
        self.entry_rival.insert(0, "Rival en linea (ej: Lina, DP, Pudge)")
        self.entry_rival.bind("<FocusIn>", lambda e: self.entry_rival.delete(0, tk.END) if "Rival en linea" in self.entry_rival.get() else None)
        self.entry_rival.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)

        btn_rival = tk.Button(fila_rival, text="Fijar Rival", bg="#2e7d32", fg="white", bd=0, font=("Segoe UI", 9, "bold"), padx=10, pady=4, command=self.fijar_rival)
        btn_rival.pack(side="right")

        # Fila API Key y Voz Clonada
        fila_api = tk.Frame(self.root, bg="#121614")
        fila_api.pack(fill="x", padx=10, pady=(4, 10))

        self.entry_api = tk.Entry(fila_api, bg="#1e2621", fg="white", insertbackground="white", show="*", font=("Segoe UI", 9))
        self.entry_api.insert(0, self.api_key)
        self.entry_api.pack(side="left", fill="x", expand=True, padx=(0, 6), ipady=3)

        chk_voz = tk.Checkbutton(fila_api, text="Voz Peón", variable=self.usar_clonacion, bg="#121614", fg="#e8f5e9", selectcolor="#1e2621", activebackground="#121614")
        chk_voz.pack(side="left", padx=4)

        btn_guardar = tk.Button(fila_api, text="Guardar", bg="#2e7d32", fg="white", bd=0, font=("Segoe UI", 9, "bold"), padx=10, pady=4, command=self.guardar_config)
        btn_guardar.pack(side="right")

    def iniciar_arrastre(self, event):
        self.pos_x = event.x
        self.pos_y = event.y

    def arrastrar_ventana(self, event):
        x = self.root.winfo_x() + (event.x - self.pos_x)
        y = self.root.winfo_y() + (event.y - self.pos_y)
        self.root.geometry(f"+{x}+{y}")

    def actualizar_texto(self, texto, color="#a5d6a7"):
        self.root.after(0, lambda: self.lbl_mensaje.config(text=f"🪓 Peón: {texto}", fg=color))

    def actualizar_estado(self, texto):
        self.root.after(0, lambda: self.lbl_estado.config(text=texto))

    def fijar_rival(self):
        rival = self.entry_rival.get().strip()
        if rival and "Rival en linea" not in rival:
            self.rival_linea = rival
            self.consultar_ia(
                f"Acabo de ver que voy en linea contra {rival}! Haz una burla epica estilo Dota 1 sobre {rival} y dime como ganarle la linea.",
                "#FFEB3B"
            )

    def hablar(self, texto):
        def _tarea_audio():
            archivo_temp = os.path.join(tempfile.gettempdir(), f"peon_{int(time.time()*1000)}.wav")
            exito_clon = False

            if self.usar_clonacion.get() and os.path.exists(RUTA_VOZ_PEON):
                try:
                    from gradio_client import Client, handle_file
                    if self.cliente_clonacion is None:
                        self.cliente_clonacion = Client("mrfakename/E2-F5-TTS", verbose=False)
                    resultado = self.cliente_clonacion.predict(
                        ref_audio_input=handle_file(RUTA_VOZ_PEON),
                        ref_text_input="Listo para trabajar. ¿Más trabajo? Sí, mi señor.",
                        gen_text_input=texto,
                        remove_silence=True,
                        api_name="/basic_tts"
                    )
                    ruta_generada = next(iter(resultado)) if isinstance(resultado, (list, tuple)) else resultado
                    if ruta_generada and os.path.exists(ruta_generada):
                        archivo_temp = ruta_generada
                        exito_clon = True
                except:
                    exito_clon = False

            if not exito_clon:
                archivo_temp = os.path.join(tempfile.gettempdir(), f"peon_edge_{int(time.time()*1000)}.mp3")
                async def _generar_edge():
                    comunicador = edge_tts.Communicate(texto, "es-MX-JorgeNeural", pitch="-22Hz", rate="+8%")
                    await comunicador.save(archivo_temp)
                try:
                    asyncio.run(_generar_edge())
                except:
                    return

            try:
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                pygame.mixer.music.load(archivo_temp)
                pygame.mixer.music.play()
            except:
                pass

        threading.Thread(target=_tarea_audio, daemon=True).start()

    def consultar_ia(self, situacion, color="#00FFAA"):
        if not self.api_key or self.ocupado:
            return
        self.ocupado = True

        def _worker():
            try:
                ultimas = list(self.historial_frases)[-8:]
                memoria = " | ".join(ultimas) if ultimas else "ninguna"
                rival_info = f"Tu rival directo en linea es {self.rival_linea}." if self.rival_linea else ""
                
