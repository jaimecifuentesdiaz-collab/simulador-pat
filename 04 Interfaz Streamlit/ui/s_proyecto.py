"""Proyecto y versión (PAT 134): lo que estaba en la barra lateral pasa al final de la pantalla Escenario, porque la barra
lateral queda solo para el índice de pantallas. Datos de la planta cargada, guardar versión, base de datos y formato de
los campos numéricos."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor.resumen import resumen_planta
from . import comun as C


def mostrar():
    ss = st.session_state; bd = C.obtener_bd(); pl = C.planta()
    st.divider()
    st.markdown("#### Proyecto y versión")
    proy = bd.obtener_proyecto(ss.pid) if ss.get("pid") else None
    linea = f"**Planta:** {pl.nombre} · **Proyecto:** {proy['nombre'] if proy else 'sin guardar'}"
    if ss.get("vid"):
        v = next((x for x in bd.listar_versiones(ss.pid) if x["id"] == ss.vid), None)
        if v:
            linea += f" · versión cargada v{v['numero']} del {v['fecha']}"
    st.markdown(linea)
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    nota = a.text_input("Nota de la versión", placeholder="Qué cambió", key="pry_nota")
    if b.button("Guardar versión en la base de datos", type="primary", width="stretch", key="pry_guardar"):
        try:
            if not ss.get("pid"):
                ss.pid = bd.crear_proyecto(pl.nombre if bd.obtener_proyecto(pl.nombre) is None else f"{pl.nombre} ({len(bd.listar_proyectos()) + 1})", pl.rubro)
            v = bd.guardar_version(ss.pid, pl, nota)
            ss.vid = v["id"]
            if pl.resuelta:
                bd.guardar_corrida(v["id"], resumen_planta(pl, cop=ss.cop))
            st.success(f"Guardada la versión {v['numero']}" + (" con su corrida." if pl.resuelta else " (planta sin resolver, sin corrida)."))
        except Exception as e:
            st.error(f"No se pudo guardar: {e}")
    st.toggle("Coma decimal en los campos numéricos", value=ss.get("formato_cl", True), key="formato_cl",
              help="Formato chileno: 1.234,5. Desactívelo para volver a los campos con flechas de Streamlit.")   # PAT 133, mejora 21
    n = bd.contar()
    st.caption(f"Base: {n['proyectos']} proyectos · {n['versiones']} versiones · {n['corridas']} corridas · {n['fuentes']} fuentes · archivo: {bd.ruta}")
