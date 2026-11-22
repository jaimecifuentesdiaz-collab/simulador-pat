"""Proyecto y versión (PAT 134): lo que estaba en la barra lateral pasa al final de la pantalla Escenario, porque la barra
lateral queda solo para el índice de pantallas. Datos de la planta cargada, guardar versión, base de datos y formato de
los campos numéricos. PAT 138: «Guardar» usa el sistema de proyectos del usuario (ui/proyectos.py)."""
from __future__ import annotations
import streamlit as st
from . import comun as C


def mostrar():
    from . import proyectos as PRY                 # PAT 138: un solo sistema de guardado (pantalla Proyectos y barra lateral)
    ss = st.session_state; bd = C.obtener_bd(); pl = C.planta()
    st.divider()
    st.markdown("#### Proyecto y versión")
    ab = PRY.abierto()
    linea = f"**Proyecto abierto:** {ab['nombre'] if ab else 'ninguno (sin guardar)'}"   # PAT 140: el nombre de la planta ya está arriba, en «Planta actual»
    if ab:
        linea += f" · versión {ab['version']}"
    st.markdown(C.esc(linea))
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    nota = a.text_input("Nota de la versión", placeholder="Qué cambió", key="pry_nota")
    if b.button("Guardar proyecto", type="primary", width="stretch", key="pry_guardar",
                help="Lo mismo que «Guardar proyecto» de la barra lateral: guarda en el proyecto abierto o crea uno nuevo."):
        r = PRY.guardar(nota=nota)
        (st.success if r["ok"] else st.error)(C.esc(r["mensaje"]))
    st.toggle("Coma decimal en los campos numéricos", value=ss.get("formato_cl", True), key="formato_cl",
              help="Formato chileno: 1.234,5. Desactívelo para volver a los campos con flechas de Streamlit.")   # PAT 133, mejora 21
    n = bd.contar(); m = bd.contar_proyectos_usuario()
    st.caption(f"Base: {m['proyectos']} proyectos de usuarios ({m['versiones']} versiones) · {n['proyectos']} plantas de ejemplo y "
               f"proyectos antiguos · {n['versiones']} versiones antiguas · {n['fuentes']} fuentes · archivo: {bd.ruta}")
