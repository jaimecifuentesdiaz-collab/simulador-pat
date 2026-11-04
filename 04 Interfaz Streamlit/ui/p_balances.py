"""Pestaña Balances: cierre de masa, sólidos y energía por equipo."""
from __future__ import annotations
import streamlit as st
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def mostrar():
    pl = C.planta()
    st.subheader("Balances de materia y energía")
    if not C.exigir_resuelta():
        return
    cierres = pl.cierres()
    AT.tabla("bal_cierre", "Cierre por equipo", 4)   # PAT 134: «?» de la tabla
    tol = st.number_input("Tolerancia de cierre (kg/h o kW)", value=1e-6, format="%g", min_value=0.0)
    filas = []
    for c in cierres:
        ok = all(abs(c[k] or 0) <= tol for k in ("cierre_masa", "cierre_solidos", "cierre_energia"))
        filas.append(dict(c, estado="Cierra" if ok else "No cierra"))
    C.mostrar_tabla(filas, [("equipo", "Equipo", "txt", 0), ("nombre", "Nombre", "txt", 0), ("masa_entra", "Masa que entra (kg/h)", "num", 1), ("masa_sale", "Masa que sale (kg/h)", "num", 1),
                            ("cierre_masa", "Cierre de masa (kg/h)", "num", 6), ("solidos_entra", "Sólidos que entran (kg/h)", "num", 1),
                            ("solidos_sale", "Sólidos que salen (kg/h)", "num", 1), ("cierre_solidos", "Cierre de sólidos (kg/h)", "num", 6),
                            ("energia_entra", "Energía que entra (kW)", "num", 1), ("energia_sale", "Energía que sale (kW)", "num", 1),
                            ("cierre_energia", "Cierre de energía (kW)", "num", 6), ("estado", "Estado", "txt", 0)])
    k = st.selectbox("Detalle de energía del equipo", [c["equipo"] for c in cierres], format_func=lambda k: f"{k} · {pl.equipos[k].nombre}")
    r = pl.equipos[k].resultado
    a, b = st.columns(2)
    with a:
        AT.tabla("bal_entra", "Energía que entra")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(c=c, v=v) for c, v in r.energia_in], [("c", "Entra", "txt", 0), ("v", "kW", "num", 1)])
    with b:
        AT.tabla("bal_sale", "Energía que sale")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(c=c, v=v) for c, v in r.energia_out], [("c", "Sale", "txt", 0), ("v", "kW", "num", 1)])
    if r.servicios:
        st.caption("Servicios que consume: " + "; ".join(f"{k2} = {C.fmt(v, 1)}" for k2, v in r.servicios.items()))
    for av in r.avisos:
        st.warning(av)
