"""Red hidráulica de la planta (PAT 133, mejora 8): pérdida de carga y potencia de bombeo de cada línea de líquido."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import hidraulica as H
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def mostrar(pl):
    AT.tabla("k_hidraulica", "Bombeo de las líneas de líquido", 4)   # PAT 134: «?» de la sección y de su tabla
    if not pl.resuelta:
        st.warning("Resuelva la planta para estimar la red hidráulica.")
        return
    a, b, c = st.columns(3)
    va = a.number_input("Velocidad de diseño en agua y condensado (m/s)", 0.3, 4.0, float(H.V_DISENO_AGUA), 0.1, key="sh_va")
    vp = a.number_input("Velocidad de diseño en pasta (m/s)", 0.2, 3.0, float(H.V_DISENO_PASTA), 0.1, key="sh_vp")
    L = b.number_input("Largo equivalente de cada línea (m)", 1.0, 500.0, float(H.L_LINEA), 5.0, key="sh_L")
    dz = b.number_input("Altura a vencer en cada línea (m)", 0.0, 50.0, float(H.DZ_LINEA), 0.5, key="sh_dz")
    eta = c.number_input("Rendimiento de las bombas", 0.2, 0.92, float(H.ETA_BOMBA), 0.01, key="sh_eta")
    r = H.red_hidraulica(pl, va, vp, L, dz, H.RUGOSIDAD_INOX, eta)
    if not r["lineas"]:
        st.info("La planta no tiene líneas de líquido (las corrientes de biomasa, aire y servicios no se bombean); "
                f"se omitieron {r['omitidas']} conexiones.")
        return
    m1, m2, m3 = st.columns(3)
    m1.metric("Potencia total de bombeo", C.fmt(r["potencia_total_kW"], 1) + " kW", f"{len(r['lineas'])} líneas", delta_color="off")
    m2.metric("Energía por temporada", (C.fmt(r["energia_MWh"], 1) + " MWh") if r["energia_MWh"] is not None else "—",
              (C.fmt(r["horas"], 0) + " h") if r["horas"] else "sin horas", delta_color="off")
    m3.metric("Línea de mayor pérdida", max(r["lineas"], key=lambda f: f["dp_kPa"])["linea"],
              C.fmt(max(f["dp_kPa"] for f in r["lineas"]), 1) + " kPa", delta_color="off")
    C.mostrar_tabla(r["lineas"], [("linea", "Línea", "txt", 0), ("tipo", "Corriente", "txt", 0), ("modelo", "Modelo", "txt", 0),
                                  ("Q_m3h", "Caudal (m³/h)", "num", 1), ("brix", "°Brix", "num", 1), ("D_mm", "Diámetro (mm)", "num", 0),
                                  ("v", "Velocidad (m/s)", "num", 2), ("Re", "Reynolds", "num", 0), ("regimen", "Régimen", "txt", 0),
                                  ("dp_kPa", "Pérdida de carga (kPa)", "num", 1), ("H_m", "Altura (m)", "num", 1),
                                  ("potencia_kW", "Potencia (kW)", "num", 2)])
    for a_ in r["avisos"]:
        st.caption(a_)
