"""Sección Optimización de la pestaña Economía (mejora 10, PAT 133): busca los valores de una o dos variables de la planta
que maximizan el VAN de la cascada o el calor recuperado, sobre copias de la planta (la planta de la sesión no cambia)."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import optimizacion as O
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def _etiqueta(c):
    return c["nombre"] + (f" ({c['unidad']})" if c["unidad"] and c["unidad"] != "—" else "")


def mostrar(pl, r, E):
    """pl: planta; r: resumen de la planta (C.resumen_actual()); E: st.session_state.economia."""
    ss = st.session_state
    st.markdown("#### Optimización de la recuperación")
    if r.get("sin_sumidero"):
        st.info("La planta no tiene un sumidero de calor: no hay recuperación que optimizar.")
        return
    cands = O.candidatos(pl); etq = [_etiqueta(c) for c in cands]; por_etq = dict(zip(etq, cands))
    objetivos = list(O.OBJETIVOS.values()); clave_obj = dict(zip(objetivos, O.OBJETIVOS))
    with st.container(border=True):
        a, b = st.columns(2)
        obj_txt = a.selectbox("Objetivo", objetivos, index=0, key="op_objetivo",
                              help="El VAN usa los precios, la tasa, el horizonte y la inversión de la sesión. Con inversión según el área, la inversión sale "
                                   "del área de la cascada con U medio (Capítulo 4) y la correlación de Shamoushaki et al. (2021).")
        dos = b.toggle("Optimizar dos variables (grilla)", value=False, key="op_dos")
        elegidas = []
        for i in range(2 if dos else 1):
            c1, c2, c3 = st.columns([3, 1, 1])
            e = c1.selectbox(f"Variable {i + 1}", etq, index=min(i, len(etq) - 1), key=f"op_var{i}")
            c = por_etq[e]
            lo = c2.number_input("Mínimo", value=float(c["minimo"]), key=f"op_min{i}_{e}")
            hi = c3.number_input("Máximo", value=float(c["maximo"]), key=f"op_max{i}_{e}")
            elegidas.append((c["ref"], lo, hi, e))
        n = int(st.number_input("Puntos de la grilla por variable", 3, 41, 21 if not dos else 11, 1, key=f"op_n{int(dos)}"))
    objetivo = clave_obj[obj_txt]
    if objetivo == "van" and float(E["inversion"]) <= 0:
        st.caption(C.esc("Con inversión 0 el VAN solo crece con el calor recuperado: el óptimo coincide con el máximo calor. "
                         "Use la inversión según el área para buscar un compromiso entre ahorro e inversión."))
    if dos and len({str(v[0]) for v in elegidas}) < 2:
        st.warning("Elija dos variables distintas.")
        return
    llave = (pl.rubro, objetivo, tuple((str(v[0]), v[1], v[2]) for v in elegidas), n, tuple(sorted(E.items())), ss.get("cop", 2.0),
             tuple(sorted(pl.globales.items())))
    if st.button("Optimizar", type="primary", key="op_boton"):
        with st.spinner("Evaluando la planta en cada punto…"):
            try:
                res = O.optimizar(pl, [(v[0], v[1], v[2]) for v in elegidas], objetivo, E=E, cop=ss.get("cop", 2.0), n_grilla=n)
                ss["op_resultado"] = (llave, res, [v[3] for v in elegidas])
            except Exception as ex:                   # rango inválido o planta que no resuelve
                st.error(f"No se pudo optimizar: {ex}")
                return
    guardado = ss.get("op_resultado")
    if not guardado or guardado[0] != llave:
        st.caption("Presione Optimizar. La búsqueda trabaja sobre copias de la planta: la planta de la sesión no cambia.")
        return
    _llave, res, nombres = guardado
    for av in res["avisos"][:8]:
        st.warning(C.esc(av))
    if res["optimo_lista"] is None:
        return
    unidad = "MM$" if objetivo.startswith("van") else "kW"
    m = st.columns(len(nombres) + 2)
    for col, nom, x, xb in zip(m, nombres, res["optimo_lista"], res["base_lista"]):
        col.metric("Óptimo: " + nom, C.fmt(x, 2), "actual " + C.fmt(xb, 2), delta_color="off")
    m[-2].metric(C.esc(res["objetivo"]), C.esc(C.fmt(res["valor_optimo"], 1) + " " + unidad))
    m[-1].metric("Mejora sobre la planta actual", C.esc(C.fmt(res["mejora"], 1) + " " + unidad) if res["mejora"] is not None else "—")
    if len(nombres) == 1:
        df = pd.DataFrame({res["objetivo"]: [c["valor"] for c in res["curva"]]}, index=[c["x"] for c in res["curva"]])
        st.line_chart(df, x_label=nombres[0], y_label=res["objetivo"])
        AT.tabla("opt_curva", "Valores de la curva")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(x=c["x"], v=c["valor"]) for c in res["curva"]],
                        [("x", nombres[0], "num", 2), ("v", res["objetivo"], "mm" if unidad == "MM$" else "num", 1)])
    else:
        filas = [dict(x=c["x"], y=c["y"], v=c["valor"]) for c in res["curva"]]
        tabla = pd.DataFrame(filas).pivot(index="x", columns="y", values="v")
        df = pd.DataFrame({C.fmt(y, 1): tabla[y].values for y in tabla.columns}, index=tabla.index)
        st.line_chart(df, x_label=nombres[0], y_label=res["objetivo"])
        C.ayuda(f"Una línea por valor de {nombres[1]}.")   # PAT 134: ayuda «?»
    st.caption(f"{res['evaluaciones']} puntos evaluados.")
    C.ayuda(f"Grilla de {n} puntos por variable"   # PAT 134
            + (" y refinamiento por sección dorada alrededor del mejor punto." if len(nombres) == 1 else ".")
            + " El óptimo es de la grilla y del modelo; antes de llevarlo al diseño revise que la planta siga siendo factible.")
