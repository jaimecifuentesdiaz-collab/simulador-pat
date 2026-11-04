"""Agua recuperable de los condensados (PAT 133, mejora 12): tabla por corriente y total por temporada."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import agua as A
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def mostrar(pl, r=None):
    AT.tabla("cal_agua", "Agua recuperable de los condensados", 4, fuente=A.FUENTE)   # PAT 134: «?» de la sección y de su tabla
    if not pl.resuelta:
        st.warning("Resuelva la planta para estimar el agua recuperable.")
        return
    a = A.agua_recuperada(pl, r)
    m1, m2, m3 = st.columns(3)
    m1.metric("Agua reutilizable por temporada", (C.fmt(a["total_m3_temporada"], 0) + " m³") if a["total_m3_temporada"] is not None else "—",
              (C.fmt(a["horas"], 0) + " h de operación") if a["horas"] else "sin horas", delta_color="off")
    m2.metric("Caudal de agua recuperable", C.fmt(a["total_m3_h"], 2) + " m³/h")
    m3.metric("Corrientes que aportan", str(sum(1 for f in a["filas"] if f["cuenta"] and f["m_kgh"] > 0)))
    if a["filas"]:
        C.mostrar_tabla(a["filas"], [("corriente", "Corriente", "txt", 0), ("equipo", "Equipo", "txt", 0), ("tipo", "Tipo", "txt", 0),
                                     ("T", "Temperatura (°C)", "num", 1), ("m_kgh", "Agua (kg/h)", "num", 0),
                                     ("m3_temporada", "Agua por temporada (m³)", "num", 0), ("nota", "Cálculo", "txt", 0)])
    for x in a["avisos"]:
        st.caption(x)
