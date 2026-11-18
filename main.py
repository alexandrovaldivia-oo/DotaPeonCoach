import sys
import os
import json
import time
import threading
import asyncio
import tempfile
import string
import requests
from http.server import BaseHTTPRequestHandler, HTTPServer
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QLabel, QLineEdit, QPushButton, QCheckBox)
from PyQt6.QtCore import Qt, pyqtSignal, QObject
from PyQt6.QtGui import QFont
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

class SenalesUI(QObject):
    actualizar_texto = pyqtSignal(str, str)
    actualizar_estado = pyqtSignal(str)

class PeonCerebro:
    def __init__(self, senales):
        self.senales = senales
        self.api_key = ""
        self.usar_clonacion = True
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

    def cargar_config(self):
        if os.path.exists(ARCHIVO_CONFIG):
            try:
                with open(ARCHIVO_CONFIG, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    self.api_key = data.get("api_key", "")
                    self.usar_clonacion = data.get("usar_clonacion", True)
            except:
                pass

    def guardar_config(self, key, clonar):
        self.api_key = key.strip()
        self.usar_clonacion = clonar
        with open(ARCHIVO_CONFIG, "w", encoding="utf-8") as f:
            json.dump({"api_key": self.api_key, "usar_clonacion": self.usar_clonacion}, f)

    def hablar(self, texto):
        def _tarea_audio():
            archivo_temp = os.path.join(tempfile.gettempdir(), f"peon_{int(time.time()*1000)}.wav")
            exito_clon = False

            if self.usar_clonacion and os.path.exists(RUTA_VOZ_PEON):
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
                
                prompt = (
                    f"Eres un Peon Orco renegon, sarcastico y explotado de Warcraft 3 que hace de companero y coach inmortal de Dota 2. "
                    f"Hablas con jerga dotera peruana/latina y puedes soltar lisuras o groserias graciosas (como carajo, mierda, huevadas, manco) "
                    f"cuando el jugador compra un item absurdo, muere por tonto o hace una jugada epica. "
                    f"REGLA OBLIGATORIA: Di SIEMPRE los nombres de habilidades y objetos en espanol natural de Dota, NUNCA nombres de codigo en ingles. "
                    f"No repitas estas frases que ya dijiste: ({memoria}). "
                    f"{rival_info} Responde en maximo 22 palabras, directo, expresivo y sin saludos: {situacion}"
                )

                payload = {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.95, "maxOutputTokens": 90},
                    "safetySettings": [
                        {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
                        {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"}
                    ]
                }
                headers = {"Content-Type": "application/json", "x-goog-api-key": self.api_key}
                dominio = "generativelanguage" + ".googleapis.com"
                
                resp_texto = None
                for modelo in ["gemini-3.5-flash-lite", "gemini-3.8-flash"]:
                    try:
                        url = f"https://{dominio}/v1beta/models/{modelo}:generateContent"
                        r = requests.post(url, headers=headers, json=payload, timeout=7)
                        if r.status_code == 200:
                            data = r.json()
                            primer_cand = next(iter(data.get("candidates", [])))
                            primera_parte = next(iter(primer_cand.get("content", {}).get("parts", [])))
                            resp_texto = primera_parte.get("text", "").strip()
                            break
                    except:
                        continue

                if resp_texto:
                    self.historial_frases.append(resp_texto)
                    self.senales.actualizar_texto.emit(resp_texto, color)
                    self.hablar(resp_texto)
            finally:
                self.ocupado = False

        threading.Thread(target=_worker, daemon=True).start()

    def procesar_datos_dota(self, datos):
        self.senales.actualizar_estado.emit("🟢 Conectado a Dota 2")
        hero = datos.get("hero", {})
        player = datos.get("player", {})
        mapa = datos.get("map", {})
        items = datos.get("items", {})
        abilities = datos.get("abilities", {})

        if not hero or not hero.get("level"):
            return

        heroe = hero.get("name", "").replace("npc_dota_hero_", "")
        nivel = int(hero.get("level", 0))
        oro = int(player.get("gold", 0))
        kills = int(player.get("kills", 0))
        deaths = int(player.get("deaths", 0))
        assists = int(player.get("assists", 0))
        racha_actual = int(player.get("kill_streak", 0))
        tiempo_seg = int(mapa.get("clock_time", 0))
        tiempo_min = tiempo_seg // 60

        skills_lista = []
        for k, v in abilities.items():
            if isinstance(v, dict) and v.get("level", 0) > 0:
                s_name = v.get("name", "").replace(f"{heroe}_", "")
                skills_lista.append(f"{s_name} nivel {v.get('level')}")
        skills_txt = ", ".join(skills_lista) if skills_lista else "ninguna"

        items_actuales = []
        nuevo_item_comprado = None
