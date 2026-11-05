"""Franja del proceso de diseño iterativo (PAT 135, tarea T16): las nueve etapas como pasos numerados arriba de cada pantalla.

Gris: pendiente; verde: hecha; naranjo: por revisar (cambió una etapa anterior); la etapa actual va resaltada con borde oscuro.
Cada paso es un botón que lleva a la primera pantalla de la etapa. «Etapa anterior» y «Etapa siguiente» recorren el proceso.
Desde app.py, después de la barra lateral y antes de mostrar la pantalla:  FL.barra(ss.pagina, PAGINAS)
"""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import flujo as F

_COLOR = {F.PENDIENTE: ("#e4e6e5", "#555555", "#c9ccca"), F.HECHA: ("#d6efe2", "#14583f", "#1b7a5a"),
          F.POR_REVISAR: ("#fde3c4", "#8a4b00", "#e0891a")}      # fondo, letra, borde

def _css(est: dict, actual) -> str:
    r = ['div[class*="st-key-flujo_"] button{min-height:1.85rem;padding:0.1rem 0.3rem;line-height:1.1}',
         'div[class*="st-key-flujo_"] button p{font-size:0.78rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}',
         'div[class*="st-key-flujo_"]{margin:0}',
         'div.st-key-flujo_franja [data-testid="stHorizontalBlock"]{gap:0.25rem;margin-bottom:0.2rem}']
    for n, e in est.items():
        f, l, b = _COLOR[e]
        borde = f"2px solid #1f2a26;box-shadow:0 0 0 1px #1f2a26;font-weight:700" if n == actual else f"1px solid {b}"
        r.append(f'.st-key-flujo_paso_{n} button{{background:{f};color:{l};border:{borde}}}')
        r.append(f'.st-key-flujo_paso_{n} button:hover{{border-color:#1f2a26;color:{l}}}')
    r.append('@media (max-width:640px){div.st-key-flujo_franja [data-testid="stHorizontalBlock"]{flex-wrap:wrap}'
             'div.st-key-flujo_franja [data-testid="stColumn"]{min-width:30% !important}}')
    return "<style>" + "".join(r) + "</style>"


def registrar(etapa: int) -> None:
    """Guarda la huella de la etapa (y la de las anteriores) al completarse; la llaman las pantallas o la propia franja."""
    F.registrar_huella(st.session_state, etapa)


def _ir(pagina: str, etapa: int) -> None:
    ss = st.session_state
    ss["pagina"] = pagina
    ss[F.CLAVE_ETAPA] = etapa


def _paso(etapa: int, validas, key: str, texto: str, ayuda: str, tipo: str = "secondary"):
    """Botón que lleva a la primera pantalla de la etapa. Con on_click la sesión cambia antes de dibujar el índice (Streamlit
    no deja cambiar el valor de un widget ya dibujado); si el cambio no ocurrió (sustituto de pruebas), se hace aquí y se
    relanza la ejecución."""
    pag = F.pagina_de_etapa(etapa, validas) if etapa else None
    clic = st.button(texto, key=key, help=ayuda, disabled=pag is None, width="stretch",
                     on_click=_ir, args=(pag, etapa) if pag else None)
    if clic and pag:
        ss = st.session_state
        if ss.get("pagina") != pag or ss.get(F.CLAVE_ETAPA) != etapa:
            _ir(pag, etapa)
            st.rerun()
    return clic


def barra(pagina_actual: str, paginas=None) -> None:
    """Dibuja la franja. pagina_actual: nombre de la pantalla elegida; paginas: nombres del índice (PAGINAS de app.py) para
    saltar las pantallas que aún no existen (por ejemplo «Selección de equipos»)."""
    ss = st.session_state
    validas = set(paginas) if paginas is not None else None
    if validas is not None:
        ss["flujo_paginas"] = sorted(validas)          # lo lee el itinerario del Curso (s_itinerario)
    F.sincronizar(ss)
    est = F.estados(ss)
    actual = F.etapa_de_pagina(pagina_actual, ss.get(F.CLAVE_ETAPA))
    st.html(_css(est, actual))
    with st.container(key="flujo_franja"):
        cols = st.columns([1.15] + [1] * len(F.ETAPAS) + [1.15], gap="small")
        with cols[0]:
            _paso(F.etapa_vecina(actual, -1, validas), validas, "flujo_ant", "‹ Etapa anterior", "Volver a la etapa anterior")
        for c, e in zip(cols[1:-1], F.ETAPAS):
            with c:
                _paso(e.num, validas, f"flujo_paso_{e.num}", f"{e.num} {e.corto}",
                      f"Etapa {e.num}: {e.nombre} ({est[e.num]})", "primary" if e.num == actual else "secondary")
        with cols[-1]:
            _paso(F.etapa_vecina(actual, +1, validas), validas, "flujo_sig", "Etapa siguiente ›", "Ir a la etapa siguiente")
    if actual is not None and est[actual] == F.POR_REVISAR:
        cambiadas = ", ".join(f"{k} {F.etapa(k).corto}" for k in F.etapas_cambiadas(actual, ss))
        a, b = st.columns([5, 1.4], gap="small")
        a.caption(f"Esta etapa quedó por revisar porque cambió: {cambiadas}. Revísela y márquela como revisada.")
        if b.button("Marcar revisada", key="flujo_revisada", width="stretch"):
            registrar(actual)
            st.rerun()
