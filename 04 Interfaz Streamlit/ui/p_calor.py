"""Pestaña Recuperación de calor: mapa de corrientes, cascada, pinch, alternativa 2, bomba de calor y sensibilidad."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.datos.bd import copiar_planta
from pat_sim.motor.resumen import resumen_planta
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("Recuperación de calor")
    if not C.exigir_resuelta():
        return
    with st.container(border=True):
        a, b, c = st.columns(3)
        pl.globales["dT_min"] = a.slider("Aproximación mínima de temperatura (°C)", 1.0, 20.0, float(pl.globales.get("dT_min", 5.0)), 0.5, key="rc_dT")
        pl.globales["T_final_residual"] = b.slider("Temperatura final de los residuales (°C)", 15.0, 45.0, float(pl.globales.get("T_final_residual", 30.0)), 1.0, key="rc_Tfin")
        ss.cop = c.slider("COP de la bomba de calor", 1.5, 5.0, float(ss.cop), 0.1, help="Elwardany et al. (2026) usan un COP cercano a 2,0", key="rc_cop")
    # en los secadores de biomasa el escape se enfría hasta la temperatura final de los residuales (revisión PAT 125, A03)
    cambio = False
    for e in pl.equipos.values():
        if "T_condensacion" in e.params and float(e.v("T_condensacion")) != float(pl.globales["T_final_residual"]):
            e.set("T_condensacion", float(pl.globales["T_final_residual"])); cambio = True
    if cambio:
        pl.resolver()
    r = C.resumen_actual()
    if r.get("sin_sumidero"):
        st.warning("La planta no tiene un sumidero de calor (equipo que calienta una corriente fría), así que no hay recuperación que calcular.")
        return
    s = r["sumidero"]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Sumidero: " + s["nombre"], C.fmt(r["Qsumidero"], 1) + " kW", f"{C.fmt(s['T_in'], 0)} → {C.fmt(s['T_out'], 0)} °C", delta_color="off")
    m2.metric("Cascada en serie", C.fmt(r["cascada"], 1) + " kW", C.pct(r["cobertura_cascada"]) + " del sumidero", delta_color="off")
    m3.metric("Objetivo pinch", C.fmt(r["pinch"], 1) + " kW", C.pct(r["cobertura_pinch"]) + " del sumidero", delta_color="off")
    if r.get("combustible") == "biomasa":     # en la biomasa no hay vapor latente aparte: la alternativa 2 coincide con la cascada
        m4.metric("Oferta de calor residual", C.fmt(r["oferta"], 1) + " kW", "escapes y aire del enfriador", delta_color="off")
    else:
        m4.metric("Solo condensados (alt. 2)", C.fmt(r["alt2"], 1) + " kW", C.pct(r["cobertura_alt2"]) + " del sumidero", delta_color="off")

    AT.tabla("cal_mapa", "Mapa de corrientes calientes", 4)   # PAT 134: «?» de la tabla
    filas = []
    for n, v in r["corrientes"].items():
        latente = v[3] is None
        filas.append(dict(n=n, tipo="Calor latente" if latente else "Calor sensible", Ti=v[1], To=None if latente else v[2], CP=v[3], Q=v[4]))
    C.mostrar_tabla(filas, [("n", "Corriente", "txt", 0), ("tipo", "Tipo", "txt", 0), ("Ti", "T de cesión (°C)", "num", 2), ("To", "T final (°C)", "num", 1),
                            ("CP", "CP (kW/K)", "num", 2), ("Q", "Calor (kW)", "num", 1)])
    st.caption(f"Oferta total del mapa: {C.fmt(r['oferta'], 1)} kW, frente a una demanda de {C.fmt(r['Qsumidero'], 1)} kW.")

    AT.tabla("cal_cascada", "Cascada en serie", 4)   # PAT 134: «?» de la tabla
    C.mostrar_tabla([dict(f) for f in r["cascada_filas"]],
                    [("corriente", "Corriente", "txt", 0), ("Q_kW", "Calor intercambiado (kW)", "num", 1), ("T_entra", "El tomate entra a (°C)", "num", 2), ("T_sale", "El tomate sale a (°C)", "num", 2)])
    st.markdown("#### Pinch")
    st.markdown(f"Objetivo de recuperación: **{C.fmt(r['pinch'], 1)} kW** · calor externo mínimo: **{C.fmt(r['Q_externo_min'], 1)} kW** · "
                f"temperatura de pinch: **{', '.join(C.fmt(t, 2) for t in r['T_pinch'])} °C**.")

    from . import s_red                      # PAT 133, mejora 3: red de intercambiadores desde el pinch
    s_red.mostrar(pl, r)

    st.markdown("#### Bomba de calor")
    hp = r["bomba_calor"]
    st.markdown(f"Para cubrir todo el sumidero con COP {C.fmt(r['cop'], 1)}: electricidad **{C.fmt(hp['electricidad_kW'], 1)} kW** y calor de baja temperatura "
                f"**{C.fmt(hp['calor_baja_kW'], 1)} kW**, tomado de: " + ", ".join(f"{n} ({C.fmt(q, 1)} kW)" for n, q in hp["fuentes"]) +
                (f". Faltan {C.fmt(hp['falta_kW'], 1)} kW de fuente." if hp["falta_kW"] > 1e-6 else "."))

    st.markdown("#### Sensibilidad")
    xs = [x / 2 for x in range(2, 41)]
    filas = []
    for dT in xs:
        p2 = copiar_planta(pl, resolver=False); p2.globales["dT_min"] = dT; p2.resolver()
        q = resumen_planta(p2, cop=ss.cop)
        fila = {"dT": dT, "Cascada (kW)": q["cascada"], "Pinch (kW)": q["pinch"]}
        if r.get("combustible") != "biomasa":
            fila["Solo condensados (kW)"] = q["alt2"]
        filas.append(fila)
    df = pd.DataFrame(filas).set_index("dT")
    st.line_chart(df, x_label="Aproximación mínima de temperatura (°C)", y_label="Calor recuperado (kW)")
    cops = [1.5 + 0.25 * i for i in range(15)]
    AT.tabla("cal_cop", "Bomba de calor según el COP")   # PAT 134: «?» de la tabla
    h = [dict(cop=c, elec=r["Qsumidero"] / c, baja=r["Qsumidero"] - r["Qsumidero"] / c) for c in cops]
    C.mostrar_tabla(h, [("cop", "COP", "num", 2), ("elec", "Electricidad de la bomba (kW)", "num", 1), ("baja", "Calor de baja temperatura (kW)", "num", 1)])
    from . import s_agua                     # PAT 133, mejora 12
    s_agua.mostrar(pl, r)
