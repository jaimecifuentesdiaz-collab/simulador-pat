"""Envoltura en Python del componente «lienzo_planta» (simulador de planta de la pestaña Diseño).

El componente es un archivo HTML propio (ui/componentes/lienzo_planta/index.html: HTML, CSS y JavaScript con SVG
nativo, sin internet ni compilación) que habla con Streamlit por postMessage. Recibe la planta y sus resultados y
devuelve {eventos: [{evento, datos, seq}, ...], seq}: todos los eventos que todavía no se han procesado, para que no
se pierda ninguno si llegan dos seguidos mientras Python está calculando.
"""
from __future__ import annotations
from pathlib import Path
import streamlit.components.v1 as components

RUTA = Path(__file__).resolve().parent / "componentes" / "lienzo_planta"
_componente = components.declare_component("lienzo_planta", path=str(RUTA))
CLAVE = "lienzo_planta"


def lienzo(datos: dict, key: str = CLAVE):
    """Dibuja el lienzo. Devuelve el último valor enviado por el navegador (o None)."""
    return _componente(datos=datos, key=key, default=None)


def eventos_nuevos(valor, ultimo_seq: int) -> list[dict]:
    """Eventos del valor del componente que todavía no se han aplicado, en orden."""
    if not isinstance(valor, dict):
        return []
    evs = [e for e in valor.get("eventos", []) if isinstance(e, dict) and int(e.get("seq", 0)) > ultimo_seq]
    return sorted(evs, key=lambda e: int(e["seq"]))
