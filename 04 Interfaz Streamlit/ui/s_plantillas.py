"""Sección de la pestaña Escenario (PAT 133, mejora 14): plantillas mínimas por rubro y biblioteca de proyectos de ejemplo."""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import RUBROS
from pat_sim.escenarios import plantillas as PLT
from . import comun as C


def _limpiar():
    for k in ("rc_dT", "rc_Tfin", "esc_rubro"):
        st.session_state.pop(k, None)


def mostrar():
    ss = st.session_state; pl = C.planta(); bd = C.obtener_bd()
    C.ayuda("Una plantilla trae la línea típica del rubro ya conectada, sin capacidades, sin lazos de control y sin "   # PAT 134: ayuda «?»
            "la fuente de calor, para que usted la complete. Un ejemplo es un proyecto terminado de la biblioteca. Las dos reemplazan "
            "la planta de la sesión; la base de datos no cambia hasta que guarde una versión.", "Plantillas y proyectos de ejemplo")
    rubros = [r for r in RUBROS if r in PLT.MODULOS]
    a, b = st.columns([1, 2])
    with a:
        rub = st.selectbox("Rubro", rubros, index=rubros.index(pl.rubro) if pl.rubro in rubros else 0, format_func=lambda k: RUBROS[k], key="plt_rubro")
        tipo = st.radio("Partir de", ["Plantilla para completar", "Proyecto de ejemplo"], key="plt_tipo")
    opciones = PLT.listar(rub, ejemplos=(tipo == "Proyecto de ejemplo"))
    with b:
        if not opciones:
            st.info("No hay opciones para este rubro.")
            return
        sel = st.selectbox("Opción", [p.clave for p in opciones], format_func=lambda k: PLT.obtener(k).nombre,
                           key=f"plt_sel_{rub}_{int(tipo == 'Proyecto de ejemplo')}")   # PAT 133: una clave por lista de opciones
        p = PLT.obtener(sel)
        C.ayuda(p.descripcion)   # PAT 134
        if p.pendientes:
            st.markdown("**Qué le falta completar:**\n" + "\n".join(f"- {x}" for x in p.pendientes))
        if st.button(f"Cargar «{p.nombre}»", type="primary", key="plt_cargar"):
            try:
                ss.pl = PLT.cargar(sel)
                proy = bd.obtener_proyecto(ss.pl.nombre) if p.es_ejemplo else None
                ss.pid = (proy or {}).get("id"); ss.vid = None
                _limpiar()
                ss.aviso_rubro = ("ok", f"Cargada: {ss.pl.nombre}. Las demás pestañas ya trabajan con ella.")
                st.rerun()
            except Exception as e:
                st.error(f"No se pudo cargar: {e}")
