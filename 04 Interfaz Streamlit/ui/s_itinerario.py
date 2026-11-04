"""Itinerario guiado (PAT 133, mejora 17; desde PAT 134 en la pantalla Curso): avance de las etapas y pista de la siguiente."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import itinerario as IT
from . import comun as C


def mostrar():
    ss = st.session_state; pl = C.planta()
    est = IT.evaluar(ss, pl, C.resumen_o_nada())
    hechas = sum(1 for e in est if e["cumplida"])
    st.markdown("**Itinerario de la práctica**")
    st.progress(IT.avance(est), text=f"{hechas} de {len(est)} etapas cumplidas")
    sig = IT.siguiente(est)
    if sig is None:
        st.success("Completó todas las etapas. Descargue el informe en la pestaña Evaluación.")
    else:
        st.info(f"Siguiente: {sig['nombre']} (pantalla {sig['pestana']}). {sig['pista']}")
        if sig["pestana"] != ss.get("pagina"):                 # PAT 134: salto a la pantalla del índice lateral
            st.button(f"Ir a {sig['pestana']}", key="it_ir", on_click=lambda: ss.update(pagina=sig["pestana"]))
    with st.expander("Ver las etapas", expanded=False):
        st.markdown("\n".join(f"- {'✔' if e['cumplida'] else '○'} {e['nombre']}: {e['meta']}" for e in est))
