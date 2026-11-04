"""Sección Exportar de la pestaña Informe (PAT 133, mejora 18): el balance en Excel con fórmulas y el informe listo para
imprimir o guardar como PDF desde el navegador."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import exportar as X
from . import comun as C


def mostrar(pl, r):
    """pl: planta resuelta; r: C.resumen_actual(). Dos botones de descarga."""
    from .p_informe import construir_html
    ss = st.session_state
    C.ayuda("El Excel trae dos hojas: Corrientes (caudal, temperatura y calor) y Recuperación (sumidero, mapa, cascada y coberturas). "   # PAT 134: ayuda «?»
            "Los totales, las coberturas y el calor de cada etapa son fórmulas que referencian las celdas de datos. "
            "El informe para imprimir se abre en el navegador; su botón «Imprimir o guardar como PDF» lo deja en tamaño carta.", "Exportar")
    if not pl.resuelta:
        st.caption("Resuelva la planta para exportar el balance.")
        return
    E = ss.get("economia") or {}
    try:
        xlsx = X.balance_xlsx(pl, r, E)
    except Exception as e:                    # planta sin corrientes o resumen incompleto
        st.error(f"No se pudo armar el Excel: {e}")
        xlsx = None
    doc = X.informe_imprimible(construir_html(pl, r, E, ss.get("cop", 2.0)))
    a, b = st.columns(2)
    if xlsx:
        a.download_button("Descargar el balance (Excel)", xlsx, file_name="Balance_simulador_PAT.xlsx",
                          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", key="ex_xlsx", width="stretch")
    b.download_button("Descargar el informe para imprimir (HTML)", doc, file_name="Informe_simulador_PAT_imprimible.html",
                      mime="text/html", key="ex_imprimible", width="stretch")
