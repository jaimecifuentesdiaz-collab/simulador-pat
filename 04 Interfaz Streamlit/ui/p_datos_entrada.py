"""Pestaña Datos de entrada (PAT 134): las herramientas de datos de FlexSim llevadas a la aplicación.

Dos secciones, como en FlexSim se usan juntas: el Excel de ida y vuelta (tablas globales con Excel Import/Export) trae
los datos de la planta y los datos medidos, y el ajuste de distribuciones (como ExpertFit, método de Law, 2015, cap. 6)
convierte esos datos medidos en la distribución que usan Temporada y Operación.
Diseño en 01 Requisitos y diseno/Diseno_FlexSim_PAT134_02nov2026.md."""
from __future__ import annotations
import streamlit as st
from . import comun as C


def mostrar():
    C.ayuda("Primero el Excel de ida y vuelta (plantilla con las tablas de la planta y los datos medidos); después el ajuste de "   # PAT 134: ayuda «?»
            "distribuciones, que toma esos datos medidos y entrega la distribución que usan Temporada y Operación.", "Datos de entrada", 3)
    st.markdown("#### Excel de ida y vuelta")
    try:
        from . import s_excel
        s_excel.mostrar()
    except Exception as e:                 # una sección con error no tumba la otra
        st.error(f"Error en el Excel de ida y vuelta: {e}")
    st.divider()
    st.markdown("#### Ajuste de distribuciones")
    try:
        from . import s_ajuste
        s_ajuste.mostrar()
    except Exception as e:
        st.error(f"Error en el ajuste de distribuciones: {e}")
