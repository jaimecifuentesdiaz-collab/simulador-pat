"""Calculadora de propiedades de la pasta según °Brix (PAT 133, mejora 9), para la pestaña Calculadoras:
cp y densidad por composición (Choi y Okos, 1986) y reología de ley de potencia (Supuesto declarado en motor/propiedades.py)."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import propiedades as PR
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def mostrar():
    a, b, c = st.columns(3)
    brix = a.number_input("Concentración (°Brix)", min_value=0.0, max_value=40.0, value=28.0, step=0.5, format="%.1f", key="sb_brix")
    T = b.number_input("Temperatura (°C)", min_value=0.0, max_value=110.0, value=40.0, step=1.0, format="%.1f", key="sb_T")
    g = c.number_input("Tasa de corte para la viscosidad aparente (1/s)", min_value=1.0, max_value=1000.0, value=float(PR.GAMMA_REF),
                       step=5.0, format="%.0f", key="sb_gamma", help="50 1/s es el orden de una línea de pasta (Supuesto)")
    p = PR.propiedades_pasta(brix, T, g)
    x = st.columns(5)
    x[0].metric("cp (Choi y Okos)", C.fmt(p["cp"], 3) + " kJ/kg·K", "modelo lineal del motor: " + C.fmt(p["cp_modelo_lineal"], 3), delta_color="off")
    x[1].metric("Densidad", C.fmt(p["densidad"], 1) + " kg/m³")
    x[2].metric("Índice de consistencia K", C.fmt(p["K"], 3) + " Pa·sⁿ")
    x[3].metric("Índice de flujo n", C.fmt(p["n"], 3))
    x[4].metric("Viscosidad aparente", C.fmt(p["mu_aparente"], 3) + " Pa·s", "a " + C.fmt(g, 0) + " 1/s", delta_color="off")
    bs = [0.5 * i for i in range(0, 81)]
    C.ayuda("Fuentes: cp y densidad, " + C.esc(PR.FUENTES_PASTA["cp"]) + ", con los sólidos tratados como "   # PAT 134: ayuda «?»
            "carbohidratos (Supuesto). Reología: " + C.esc(PR.FUENTES_PASTA["reologia"]) + ".",
            "Calor específico y viscosidad aparente según °Brix, a " + C.fmt(T, 1) + " °C")
    st.line_chart(pd.DataFrame({"°Brix": bs, "cp, Choi y Okos (kJ/kg·K)": [PR.cp_pasta(v, T) for v in bs],
                                "cp, modelo lineal del motor (kJ/kg·K)": [PR.CPW - (PR.CPW - 1.5) * v / 100 for v in bs]}),
                  x="°Brix", y_label="kJ/kg·K")
    bv = [v for v in bs if v >= 4]
    st.line_chart(pd.DataFrame({"°Brix": bv, "Viscosidad aparente (Pa·s)": [PR.viscosidad_aparente_pasta(v, T, g) for v in bv]}),
                  x="°Brix", y_label="Pa·s")
    filas = [dict(b=v, cp=PR.cp_pasta(v, T), rho=PR.densidad_pasta(v, T), K=PR.reologia_pasta(v, T)[0], n=PR.reologia_pasta(v, T)[1],
                  mu=PR.viscosidad_aparente_pasta(v, T, g)) for v in (5.0, 8.5, 15.0, 22.0, 28.0, 30.0, 36.0)]
    AT.tabla("k_brix", "Propiedades por °Brix a " + C.fmt(T, 1) + " °C")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("b", "°Brix", "num", 1), ("cp", "cp (kJ/kg·K)", "num", 3), ("rho", "Densidad (kg/m³)", "num", 1),
                            ("K", "K (Pa·sⁿ)", "num", 3), ("n", "n", "num", 3), ("mu", "Viscosidad aparente (Pa·s)", "num", 3)])
