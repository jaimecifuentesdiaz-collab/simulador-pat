"""Pestaña Alternativas (PAT 133, mejoras 1 y 4): la comparación multicriterio del Capítulo 3 dentro de la aplicación y la
aproximación mínima de temperatura que da el menor costo total anual. Economía evalúa la alternativa que se elige aquí."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import alternativas as AL
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def precio_sesion(r) -> float:
    E = st.session_state.economia
    return float(E.get("precio_biomasa", C.PRECIO_BIOMASA)) if r.get("combustible") == "biomasa" else float(E["precio_gas"])


def alternativas_sesion(pl, r) -> dict:
    """Alternativas con los precios, la tasa y los pesos de la sesión; se guardan en la sesión para no recalcular."""
    ss = st.session_state; E = ss.economia
    pesos = tuple(ss.get("alt_pesos", (1 / 3, 1 / 3, 1 / 3)))
    clave = (id(pl), pl.nombre, round(r["Qsumidero"], 3), round(r["cascada"], 3), r["dT_min"], r["T_final"], precio_sesion(r),
             E["dolar"], E["tasa"], ss.cop, pesos)
    if ss.get("alt_clave") != clave:
        ss.alt_res = AL.alternativas(pl, r, precio_sesion(r), E["dolar"], E["tasa"], AL.VIDA, cop=ss.cop, pesos=pesos)
        ss.alt_clave = clave
    return ss.alt_res


def elegida(X) -> str:
    """Alternativa que evalúa Economía: la que el usuario fijó, o la ganadora del multicriterio."""
    k = st.session_state.economia.get("alternativa")
    return k if k in X["alts"] and X["alts"][k]["Q"] > 1e-6 else (X["ganador"] or "A2")


def mostrar():
    ss = st.session_state; pl = C.planta(); E = ss.economia
    C.ayuda(C.esc("Las mismas cuatro alternativas y el mismo método del Capítulo 3: suma ponderada con normalización por rango de "
                  "tres criterios y barrido de pesos con paso 0,01. Precio, dólar y tasa se toman de la pestaña Economía; el horizonte es la vida útil "
                  "tributaria de 15 años (SII, Res. Ex. 43/2002), como en el Capítulo 4."), "Alternativas de recuperación de calor", 3)   # PAT 134: ayuda «?»
    if not C.exigir_resuelta():
        return
    r = C.resumen_actual()
    if r.get("sin_sumidero") or not r.get("horas"):
        st.warning("La planta necesita un sumidero de calor y horas de operación para comparar alternativas.")
        return
    bio = r.get("combustible") == "biomasa"
    with st.form("form_alt"):
        a, b, c = st.columns(3)
        p = ss.get("alt_pesos", (1 / 3, 1 / 3, 1 / 3))
        w1 = a.slider("Peso de la cobertura del sumidero", 0.0, 1.0, float(p[0]), 0.05, key="alt_w1")
        w2 = b.slider("Peso del precio de equilibrio", 0.0, 1.0, float(p[1]), 0.05, key="alt_w2")
        w3 = c.slider("Peso del número de equipos", 0.0, 1.0, float(p[2]), 0.05, key="alt_w3")
        if st.form_submit_button("Aplicar pesos", type="primary"):
            s = w1 + w2 + w3
            ss.alt_pesos = (w1 / s, w2 / s, w3 / s) if s > 0 else (1 / 3, 1 / 3, 1 / 3)
    X = alternativas_sesion(pl, r)
    up = X["unidad_precio"]
    filas = []
    for k, a in X["alts"].items():
        filas.append(dict(k=k, n=a["nombre"], q=a["Q"], cob=a["cob"] * 100, eq=a["equipos"], ar=a["area_medio"] or None,
                          inv=a["inv"]["medio"], pe=a["p_eq"], van=a["ev"]["VAN"], pt=X["puntajes"].get(k), ba=X["barrido"].get(k, 0) * 100))
    AT.tabla("alt_comparacion", "Comparación", 4,   # PAT 134: «?» de la tabla
             u_bio="; en biomasa, U del gas de escape como Supuesto con el orden de magnitud de Incropera et al. (2007)" if bio else "")
    C.mostrar_tabla(filas, [("k", "Alternativa", "txt", 0), ("n", "Descripción", "txt", 0), ("q", "Calor (kW)", "num", 1), ("cob", "Cobertura (%)", "num", 1),
                            ("eq", "Equipos", "num", 0), ("ar", "Área con U medio (m²)", "num", 0), ("inv", "Inversión (MM$)", "clp", 1),
                            ("pe", f"Precio de equilibrio ({up})", "num", 2), ("van", "VAN al precio de Economía (MM$)", "clp", 1),
                            ("pt", "Puntaje", "num", 3), ("ba", "Gana en el barrido (%)", "num", 1)])
    g = X["ganador"]
    pw = ss.get("alt_pesos", (1 / 3, 1 / 3, 1 / 3))
    st.success(C.esc(f"Con pesos {C.fmt(pw[0], 2)}, {C.fmt(pw[1], 2)} y {C.fmt(pw[2], 2)} gana {g}, {X['alts'][g]['nombre'].lower()}, "
                     f"que además gana en el {C.fmt(X['barrido'].get(g, 0) * 100, 1)} % de las combinaciones de pesos."))
    opciones = [k for k in X["alts"] if X["alts"][k]["Q"] > 1e-6]
    actual = elegida(X)
    sel = st.selectbox("Alternativa que evalúa la pestaña Economía", opciones, index=opciones.index(actual),
                       format_func=lambda k: f"{k} · {X['alts'][k]['nombre']}", key="alt_sel")
    if sel != E.get("alternativa"):
        E["alternativa"] = sel
    with st.expander(f"Etapas de {sel}", expanded=False):
        et = X["alts"][sel]["etapas"]
        if et:
            AT.tabla("alt_etapas", "Etapas de intercambio")   # PAT 134: «?» de la tabla
            C.mostrar_tabla(et, [("corriente", "Corriente", "txt", 0), ("tipo", "Tipo", "txt", 0), ("Q", "Calor (kW)", "num", 1),
                                 ("Tc_in", "Frío entra (°C)", "num", 1), ("Tc_out", "Frío sale (°C)", "num", 1), ("Th_in", "Caliente entra (°C)", "num", 1),
                                 ("Th_out", "Caliente sale (°C)", "num", 1), ("LMTD", "LMTD (°C)", "num", 1), ("A_medio", "Área (m²)", "num", 1)])
        else:
            st.caption("La bomba de calor no tiene etapas de intercambio directo.")

    st.markdown("#### Aproximación mínima de temperatura óptima")
    a, b = st.columns(2)
    alt_opt = a.selectbox("Alternativa", [k for k in ("A3", "A2", "A1") if k in opciones], key="alt_opt_k")
    if b.button("Calcular el costo total anual", key="alt_opt_btn"):
        ss.alt_opt = AL.dTmin_optimo(pl, r, precio_sesion(r), E["dolar"], E["tasa"], AL.VIDA, alternativa=alt_opt)
    o = ss.get("alt_opt")
    if o:
        op = o["optimo"]
        x = st.columns(4)
        x[0].metric("ΔTmin óptimo", C.fmt(op["dT"], 1) + " °C")
        x[1].metric("Calor recuperado", C.fmt(op["Q"], 0) + " kW")
        x[2].metric("Área", C.fmt(op["area"], 0) + " m²")
        x[3].metric("Costo total anual", C.esc("$" + C.fmt(op["total"], 1) + " MM"))
        df = pd.DataFrame([{"dT": f["dT"], "Capital anualizado": f["capital"], "Operación y mantención": f["om"],
                            "Combustible remanente": f["combustible"], "Total": f["total"]} for f in o["filas"]]).set_index("dT")
        st.line_chart(df, x_label="Aproximación mínima de temperatura (°C)", y_label="MM$ por temporada")
        borde = op["dT"] in (o["filas"][0]["dT"], o["filas"][-1]["dT"])
        if borde:
            st.caption("El óptimo queda en el borde del rango: con este precio del combustible conviene ir al extremo.")
        C.ayuda(C.esc(f"Factor de recuperación del capital {C.fmt(o['crf'], 4)} con la tasa de Economía y 15 años. "   # PAT 134
                      "Método: Linnhoff y Ahmad (1990), en Kemp (2007), cap. 3."))
        if st.button(f"Usar ΔTmin = {C.fmt(op['dT'], 1)} °C en la planta", key="alt_opt_usar"):
            pl.globales["dT_min"] = float(op["dT"]); ss["rc_dT"] = float(op["dT"]); C.resolver(pl); ss.pop("alt_opt", None); st.rerun()
