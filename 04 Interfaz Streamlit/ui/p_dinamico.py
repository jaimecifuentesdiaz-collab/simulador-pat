"""Pestaña Dinámica (PAT 133, mejora 20): arranque y parada del calentamiento (hot break o aire de secado) como sistema de
primer orden con la masa térmica del equipo, curva del calor recuperable en el tiempo y, en la biomasa, secado por cargas."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import dinamico as D
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def _submuestreo(serie: dict, n: int = 600) -> dict:
    largo = len(next(iter(serie.values()))); paso = max(1, largo // n)
    return {k: v[::paso] for k, v in serie.items()}


def mostrar():
    pl = C.planta()
    C.ayuda("Modelo de primer orden C·dT/dt = Q − CP·(T − T entrada), integrado con Euler explícito. La masa térmica C es la del acero "   # PAT 134: ayuda «?»
            "del equipo más la retención de producto; el calor lo regula un control con prealimentación y acción proporcional, con tope "
            "en la capacidad de la válvula o del hogar. En la parada se corta el calor. Todos los datos del equipo son supuestos declarados.",
            "Dinámica del arranque y la parada", 3)
    if not C.exigir_resuelta():
        return
    r = C.resumen_actual()
    if r.get("sin_sumidero"):
        st.warning("La planta no tiene un sumidero de calor: no hay calentamiento que simular.")
        return
    sp = D.supuestos(pl); just = sp.pop("justificacion")
    tomate = pl.rubro == "tomate"
    with st.container(border=True):
        a, b, c = st.columns(3)
        masa = a.number_input("Masa de acero del equipo (t)", 0.5, 200.0, float(sp["masa_acero_t"]), 0.5, key="din_masa", help=just["masa_acero_t"])
        resid = b.number_input("Retención de producto (min)", 0.0, 30.0, float(sp["residencia_min"]), 0.5, key="din_resid", help=just["residencia_min"])
        tauf = c.number_input("Retardo de las fuentes de calor residual (min)", 0.0, 60.0, float(sp["tau_fuentes_min"]), 1.0, key="din_tauf",
                              help=just["tau_fuentes_min"])
        d, e, f = st.columns(3)
        gan = d.number_input("Ganancia del control", 0.0, 20.0, float(sp["ganancia"]), 0.5, key="din_gan", help=just["ganancia"])
        sob = e.number_input("Capacidad máxima de calor (veces el estacionario)", 1.0, 3.0, float(sp["sobrecapacidad"]), 0.05, key="din_sob",
                             help=just["sobrecapacidad"])
        dt = f.number_input("Paso de tiempo (s); 0 = automático", 0.0, 120.0, 0.0, 0.1, key="din_dt",
                            help="Automático: 1 % de la constante de tiempo del lazo cerrado. El método explícito exige un paso menor que esa constante.")
    try:
        a_ = D.arranque_parada(pl, r, dt_s=dt or None, masa_acero_t=masa, residencia_min=resid, tau_fuentes_min=tauf,
                               ganancia=gan, sobrecapacidad=sob)
    except Exception as ex:                    # paso inestable o supuesto fuera de rango
        st.error(f"No se pudo simular: {ex}")
        return
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Tiempo para llegar al 95 %", "—" if a_["t95_min"] is None else C.fmt(a_["t95_min"], 1) + " min",
              f"constante de tiempo {C.fmt(a_['tau_min'], 1)} min", delta_color="off")
    m2.metric("Energía perdida en el arranque", C.fmt(a_["energia_arranque_kWh"], 0) + " kWh",
              f"{C.fmt(a_['energia_masa_kWh'], 0)} kWh quedan en el acero", delta_color="off")
    m3.metric("Calor en régimen", C.fmt(a_["Q_estacionario"], 0) + " kW", f"{C.fmt(a_['T0'], 0)} → {C.fmt(a_['Tsp'], 0)} °C", delta_color="off")
    m4.metric("Calor recuperable en régimen", C.fmt(a_["estado_final"]["Q_rec"], 0) + " kW", "cascada en serie del motor", delta_color="off")
    st.caption(f"Equipo: {a_['equipo']} · {a_['nombre_equipo']} ({a_['nombre']}). Paso de tiempo {C.fmt(a_['dt_s'], 2)} s; parada a los "
               f"{C.fmt(a_['t_parada_min'], 1)} min. Se va con el producto bajo la temperatura de proceso: "
               f"{C.fmt(a_['energia_producto_fuera_kWh'], 0)} kWh. En la parada el equipo devuelve {C.fmt(a_['energia_parada_kWh'], 0)} kWh al producto.")
    C.ayuda("La energía perdida en el arranque es el calor entregado hasta el 95 %, que no sirve al proceso: "   # PAT 134
            "una parte calienta el acero y el resto se va con el producto que sale bajo la temperatura de proceso.")
    S = _submuestreo(a_["series"])
    st.markdown("#### Temperatura de salida")
    st.line_chart(pd.DataFrame({"Temperatura (°C)": S["T"]}, index=pd.Index(S["t_min"], name="min")),
                  x_label="Tiempo (min)", y_label="°C")
    st.markdown("#### Calor entregado y calor recuperable")
    st.line_chart(pd.DataFrame({"Calor entregado (kW)": S["Q"], "Calor recuperable disponible (kW)": S["Q_rec_disp"],
                                "Calor externo (kW)": S["Q_ext"]}, index=pd.Index(S["t_min"], name="min")),
                  x_label="Tiempo (min)", y_label="kW")
    b_ = a_["balance"]
    AT.tabla("din_balance", "Balance de energía de la simulación")   # PAT 134: «?» de la tabla
    C.mostrar_tabla([dict(n="Calor entregado al equipo", v=b_["calor_kWh"]), dict(n="Calor que sale con el producto", v=b_["producto_kWh"]),
                     dict(n="Calor acumulado en el acero al final", v=b_["acumulado_kWh"]), dict(n="Cierre del balance integrado", v=b_["cierre_kWh"]),
                     dict(n="Calor cubierto con recuperación", v=b_["recuperado_kWh"]), dict(n="Calor externo (caldera o generador)", v=b_["externo_kWh"])],
                    [("n", "Balance de energía de toda la simulación", "txt", 0), ("v", "kWh", "num", 3)])
    with st.expander("Supuestos y fuentes del modelo dinámico"):
        AT.tabla("din_supuestos", "Supuestos del equipo")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=k, v=v, j=just.get(k, "")) for k, v in a_["supuestos"].items()],
                        [("n", "Supuesto", "txt", 0), ("v", "Valor", "num", 3), ("j", "Justificación o fuente", "txt", 0)])
        st.caption(f"Masa térmica C = {C.fmt(a_['C_kJ_K'], 0)} kJ/K; CP del sumidero {C.fmt(a_['K_kW_K'], 2)} kW/K.")
    if tomate:
        return
    C.ayuda("Periodo de velocidad constante y periodo de velocidad decreciente lineal entre la humedad crítica y la de equilibrio "   # PAT 134
            "(Mujumdar, 2014). Una carga es la materia seca de una hora de alimentación y recibe la potencia útil del secador continuo.",
            "Secado por cargas")
    g, h, i = st.columns(3)
    Xc = g.number_input("Humedad crítica (base seca)", 0.10, 1.0, D.SUPUESTOS_CARGAS["Xc"], 0.01, key="din_Xc",
                        help=D.SUPUESTOS_CARGAS["justificacion"]["Xc"])
    Xe = h.number_input("Humedad de equilibrio (base seca)", 0.0, 0.2, D.SUPUESTOS_CARGAS["Xe"], 0.005, key="din_Xe",
                        help=D.SUPUESTOS_CARGAS["justificacion"]["Xe"])
    hc = i.number_input("Horas de alimentación por carga", 0.25, 24.0, D.SUPUESTOS_CARGAS["horas_carga"], 0.25, key="din_hc",
                        help=D.SUPUESTOS_CARGAS["justificacion"]["horas_carga"])
    try:
        s = D.secado_cargas_planta(pl, Xc=Xc, Xe=Xe, horas_carga=hc)
    except Exception as ex:
        st.error(f"No se pudo simular el secado por cargas: {ex}")
        return
    n1, n2, n3 = st.columns(3)
    n1.metric("Tiempo de secado de la carga", C.fmt(s["t_euler_h"], 2) + " h", f"exacto {C.fmt(s['t_exacto_h'], 2)} h", delta_color="off")
    n2.metric("Periodo de velocidad constante", C.fmt(s["t_constante_h"], 2) + " h", f"decreciente {C.fmt(s['t_decreciente_h'], 2)} h", delta_color="off")
    n3.metric("Agua evaporada", C.fmt(s["agua_kg"], 0) + " kg", f"{C.fmt(s['energia_kWh'], 0)} kWh de calor latente", delta_color="off")
    T = _submuestreo(s["series"])
    st.line_chart(pd.DataFrame({"Humedad (base húmeda, %)": [100 * v for v in T["M_bh"]]}, index=pd.Index([60 * t for t in T["t_h"]], name="min")),
                  x_label="Tiempo (min)", y_label="%")
    st.line_chart(pd.DataFrame({"Velocidad de secado (kg agua/kg seco·h)": T["velocidad"]}, index=pd.Index([60 * t for t in T["t_h"]], name="min")),
                  x_label="Tiempo (min)", y_label="kg/kg·h")
    st.caption(f"Velocidad del periodo constante {C.fmt(s['Nc'], 3)} kg de agua por kg seco y hora (derivada del secador {s['equipo']}); "
               f"paso de tiempo {C.fmt(s['dt_h'] * 3600, 1)} s.")
    C.ayuda("Si el secado por cargas tarda más que la hora del secador continuo, el periodo decreciente es la restricción del lote.")   # PAT 134
