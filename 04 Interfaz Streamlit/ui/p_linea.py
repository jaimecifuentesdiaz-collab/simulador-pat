"""Pestaña Línea (PAT 134): simulación de la línea por *ticks* como la Fluid Library de FlexSim, con tanques pulmón entre
equipos, la capacidad efectiva de cada equipo como tasa máxima, bloqueo y hambre, fallas MTBF/MTTR por equipo y las paradas
del programa de la temporada (como las Time Tables). Motor: pat_sim/motor/linea_fluida.py. El último resultado queda en
st.session_state.linea_resultado para la animación y los tableros. Funciona en los cuatro rubros."""
from __future__ import annotations
import math
import pandas as pd
import streamlit as st
from pat_sim.motor import ajuste as AJ
from pat_sim.motor import linea_fluida as LF
from pat_sim.motor import temporada as TM
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from . import s_animacion as AN

DISTS = {"exponencial": "Exponencial", "gamma": "Gamma (CV 0,5)", "lognormal": "Lognormal (CV 0,5)", "uniforme": "Uniforme (±50 %)"}
AJUSTADA = "Ajustada en Datos de entrada"
BASES = {"operando": "Solo mientras opera", "todo": "Todo el tiempo"}
CV_FORMA = 0.5        # Supuesto PAT 134: coeficiente de variación de gamma y lognormal cuando solo se da la media


def _dist(nombre: str, media: float, ajustada: dict | None = None) -> dict:
    """Distribución con la media pedida (h). Gamma y lognormal con CV 0,5 y uniforme de 0,5 a 1,5 veces la media (Supuesto)."""
    m = max(1e-6, float(media))
    if nombre == AJUSTADA and ajustada:
        return ajustada
    if nombre == "gamma":
        k = 1 / CV_FORMA ** 2; return AJ.crear("gamma", forma=k, escala=m / k)
    if nombre == "lognormal":
        s2 = math.log(1 + CV_FORMA ** 2); return AJ.crear("lognormal", mu=math.log(m) - s2 / 2, sigma=math.sqrt(s2))
    if nombre == "uniforme":
        return AJ.crear("uniforme", minimo=0.5 * m, maximo=1.5 * m)
    return AJ.crear("exponencial", escala=m)


def _filas_defecto(pl) -> tuple[list, list]:
    ids, _av = LF.linea_principal(pl)
    eqs = [pl.equipos[k] for k in ids]; cargas = [float(e.resultado.detalle.get("carga_t_h") or 0) for e in eqs]
    fal = []
    for e in eqs:
        d = LF.fallas_defecto(e)
        fal.append({"Equipo": e.id, "Nombre": e.nombre, "Falla": d is not None,
                    "MTBF (h)": AJ.media(d["mtbf"]) if d else LF.FALLAS_TIPO[LF.categoria(e.tipo)][0], "Distribución MTBF": DISTS["exponencial"],
                    "MTTR (h)": AJ.media(d["mttr"]) if d else LF.FALLAS_TIPO[LF.categoria(e.tipo)][1], "Distribución MTTR": DISTS["exponencial"],
                    "Base": BASES["operando"]})
    tq = [{"Tanque": f"{ids[i]}-{ids[i + 1]}", "Entre": f"{eqs[i].nombre} y {eqs[i + 1].nombre}",
           "Capacidad (t)": round(LF.SUPUESTOS["tanque_min"].valor / 60 * cargas[i + 1], 2), "Nivel inicial (t)": 0.0}
          for i in range(len(ids) - 1)]
    return fal, tq


def _parametros(pl) -> dict:
    ss = st.session_state; todos = ss.setdefault("ln_parametros", {})
    fal0, tq0 = _filas_defecto(pl)
    P = todos.get(pl.rubro)
    if P is None or [f["Equipo"] for f in P["fallas"]] != [f["Equipo"] for f in fal0]:
        carga0 = float(pl.equipos[fal0[0]["Equipo"]].resultado.detalle.get("carga_t_h") or 0)
        P = todos[pl.rubro] = dict(horas=72.0, tick=1.0, semilla=1, alim=round(carga0, 2), muestra=10.0, con_fallas=True,
                                   con_programa=False, inicio=0.0, fallas=fal0, tanques=tq0, carga0=carga0)
    falla_aj = (ss.get("distribuciones") or {}).get("falla_h")
    opciones_mttr = list(DISTS.values()) + ([AJUSTADA] if falla_aj else [])
    r = pl.rubro
    with st.form(f"ln_form_{r}"):
        st.markdown("##### Horizonte y alimentación")
        a, b, c, d = st.columns(4)
        horas = a.number_input("Horizonte (h)", 1.0, 5000.0, float(P["horas"]), 12.0, key=f"ln_horas_{r}")
        tick = b.number_input("*Tick* (min)", 0.1, 60.0, float(P["tick"]), 0.5, key=f"ln_tick_{r}",
                              help="Intervalo fijo en que avanza la materia, como el *Ticker* de la *Fluid Library* de FlexSim.")
        sem = c.number_input("Semilla", 0, 10 ** 6, int(P["semilla"]), 1, key=f"ln_sem_{r}",
                             help="La misma semilla entrega las mismas fallas (una corriente random.Random por equipo).")
        alim = d.number_input("Alimentación al primer equipo (t/h)", 0.0, 10.0 * max(1.0, P["carga0"]), float(P["alim"]), 1.0, key=f"ln_alim_{r}",
                              help=f"Carga de diseño: {C.fmt(P['carga0'], 2)} t/h.")
        a, b, c, d = st.columns(4)
        cf = a.checkbox("Con fallas MTBF/MTTR", value=bool(P["con_fallas"]), key=f"ln_cf_{r}")
        cp = b.checkbox("Aplicar el programa de la temporada", value=bool(P["con_programa"]), key=f"ln_cp_{r}",
                        help="Las barras que no son producción detienen toda la línea, como las *Time Tables* de FlexSim. Usa los parámetros de la pestaña Temporada.")
        ini = c.number_input("Hora de la temporada en que parte la simulación", 0.0, 10000.0, float(P["inicio"]), 24.0, key=f"ln_ini_{r}")
        mu = d.number_input("Muestra de los gráficos cada (min)", 1.0, 240.0, float(P["muestra"]), 5.0, key=f"ln_mu_{r}")
        AT.tabla("ln_fallas", "Fallas por equipo", 5,   # PAT 134: «?» de la tabla
                 antes="La distribución ajustada en Datos de entrada se puede elegir como MTTR." if falla_aj else None)
        df_f0 = pd.DataFrame(P["fallas"])
        df_f = st.data_editor(df_f0, key=f"ln_tabla_fallas_{r}", width="stretch", hide_index=True, num_rows="fixed",
                              disabled=["Equipo", "Nombre"],
                              column_config={"Distribución MTBF": st.column_config.SelectboxColumn("Distribución MTBF", options=list(DISTS.values())),
                                             "Distribución MTTR": st.column_config.SelectboxColumn("Distribución MTTR", options=opciones_mttr),
                                             "Base": st.column_config.SelectboxColumn("Base", options=list(BASES.values())),
                                             "MTBF (h)": st.column_config.NumberColumn("MTBF (h)", min_value=0.01, format="%.2f"),
                                             "MTTR (h)": st.column_config.NumberColumn("MTTR (h)", min_value=0.0, format="%.2f")})
        df_f = df_f0 if df_f is None else df_f
        AT.tabla("ln_tanques", "Tanques pulmón", 5)   # PAT 134: «?» de la tabla
        df_t0 = pd.DataFrame(P["tanques"])
        df_t = st.data_editor(df_t0, key=f"ln_tabla_tanques_{r}", width="stretch", hide_index=True, num_rows="fixed", disabled=["Tanque", "Entre"],
                              column_config={"Capacidad (t)": st.column_config.NumberColumn("Capacidad (t)", min_value=0.0, format="%.2f"),
                                             "Nivel inicial (t)": st.column_config.NumberColumn("Nivel inicial (t)", min_value=0.0, format="%.2f")})
        df_t = df_t0 if df_t is None else df_t
        enviar = st.form_submit_button("Simular la línea", type="primary")
    if enviar:
        P.update(horas=float(horas), tick=float(tick), semilla=int(sem), alim=float(alim), con_fallas=bool(cf), con_programa=bool(cp),
                 inicio=float(ini), muestra=float(mu), fallas=df_f.to_dict("records"), tanques=df_t.to_dict("records"))
    P["_enviar"] = bool(enviar)
    return P


def _programa(pl, P):
    if not P["con_programa"]:
        return None
    T = (st.session_state.get("temporada") or {}).get(pl.rubro) or {}
    pr = TM.programa_temporada(pl, arranque_h=T.get("arranque"), cip_cada_h=T.get("cip_cada"), cip_duracion_h=T.get("cip_dur"),
                               parada_cada_d=T.get("parada_cada"), parada_duracion_h=T.get("parada_dur"), parada_final_h=T.get("parada_final"),
                               resumen=C.resumen_o_nada())
    a, b = P["inicio"], P["inicio"] + P["horas"]
    return [dict(x, inicio_h=max(a, x["inicio_h"]) - a, fin_h=min(b, x["fin_h"]) - a) for x in pr["barras"] if x["fin_h"] > a and x["inicio_h"] < b]


def _fallas(P, falla_aj):
    if not P["con_fallas"]:
        return False
    inv_d = {v: k for k, v in DISTS.items()}; inv_b = {v: k for k, v in BASES.items()}; out = {}
    for f in P["fallas"]:
        if not f.get("Falla"):
            out[f["Equipo"]] = None; continue
        mttr_n = f.get("Distribución MTTR") or DISTS["exponencial"]
        out[f["Equipo"]] = dict(mtbf=_dist(inv_d.get(f.get("Distribución MTBF"), "exponencial"), f.get("MTBF (h)") or 1.0),
                                mttr=_dist(AJUSTADA if mttr_n == AJUSTADA else inv_d.get(mttr_n, "exponencial"), f.get("MTTR (h)") or 0.0, falla_aj),
                                base=inv_b.get(f.get("Base"), "operando"))
    return out


def _firma(pl, P) -> tuple:
    caps = tuple((k, e.capacidad_efectiva()) for k, e in pl.equipos.items())
    return (pl.rubro, caps, repr({k: v for k, v in P.items() if not k.startswith("_")}))


def mostrar():
    pl = C.planta()
    st.subheader("Línea: simulación por *ticks* con tanques pulmón y fallas")
    if not C.exigir_resuelta():
        return
    ss = st.session_state
    try:
        P = _parametros(pl)
    except ValueError as e:
        st.warning(f"No se pudo armar la línea: {e}")
        return
    falla_aj = (ss.get("distribuciones") or {}).get("falla_h")
    firma = _firma(pl, P)
    res = ss.get("linea_resultado")
    if P.pop("_enviar", False) or res is None or ss.get("ln_firma") != firma:
        try:
            with st.spinner("Simulando la línea…"):
                res = LF.simular_linea(pl, horas=P["horas"], tick_min=P["tick"], semilla=P["semilla"], fallas=_fallas(P, falla_aj),
                                       tanques={t["Tanque"]: dict(capacidad_t=float(t.get("Capacidad (t)") or 0.0),
                                                                  nivel_inicial_t=float(t.get("Nivel inicial (t)") or 0.0)) for t in P["tanques"]},
                                       programa=_programa(pl, P), muestra_min=P["muestra"], alimentacion_t_h=P["alim"])
        except ValueError as e:
            st.warning(f"No se pudo simular la línea: {e}")
            return
        ss.linea_resultado = res; ss.ln_firma = firma
    for a in res["avisos"]:
        st.warning(C.esc(a))

    o = res.get("oee_detalle") or {}
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Producción de la línea", C.fmt(res["produccion_t"], 1) + " t",
              "sin fallas " + C.fmt(res["produccion_sin_fallas_t"], 1) + " t", delta_color="off")
    m2.metric("OEE de la línea", C.pct(res["oee"]), "rendimiento " + C.pct(o.get("rendimiento")), delta_color="off")
    m3.metric("Disponibilidad de la línea", C.pct(res["disponibilidad"]),
              C.fmt(res["horas_planificadas"], 1) + " h planificadas", delta_color="off")
    nf = sum(v["fallas"] for v in res["por_equipo"].values())
    m4.metric("Fallas en el horizonte", C.fmt(nf, 0), C.fmt(sum(v["horas_por_estado"]["en_falla"] for v in res["por_equipo"].values()), 1)
              + " h de equipo en falla", delta_color="off")
    b = res["balance"]
    st.caption(C.esc(f"Balance de masa: entrada {C.fmt(b['entrada_t'], 1)} t + inventario inicial {C.fmt(b['inventario_inicial_t'], 1)} t = "
                     f"producto {C.fmt(b['producto_t'], 1)} t + salidas del proceso {C.fmt(b['salidas_proceso_t'], 1)} t (agua evaporada y descarte) "
                     f"+ inventario final {C.fmt(b['inventario_final_t'], 1)} t; diferencia {C.fmt(b['cierre_t'], 6)} t. "
                     f"Tasa de la línea {C.fmt(res['tasa_linea_t_h'], 2)} t/h; tasa máxima (recurso crítico) {C.fmt(res['tasa_maxima_linea_t_h'], 2)} t/h. "
                     f"OEE de Nakajima (1988) con calculadoras.oee y la tasa planificada de la planta, {C.fmt(res.get('tasa_planificada_t_h'), 2)} t/h, "
                     f"como Temporada y Tableros; respecto del recurso crítico, {C.pct(res.get('oee_critico'))}. "
                     f"{res['parametros']['ticks']} *ticks* de {C.fmt(res['parametros']['tick_min'], 1)} min."))

    eqs = res["equipos"]; nom = {e["id"]: f"{e['id']} {e['nombre']}" for e in eqs}
    st.markdown("#### Horas por estado de cada equipo")
    est_usados = [s for s in LF.ESTADOS if any(res["por_equipo"][e["id"]]["horas_por_estado"][s] > 0 for e in eqs)]
    df = pd.DataFrame([{LF.NOMBRE_ESTADO[s]: res["por_equipo"][e["id"]]["horas_por_estado"][s] for s in est_usados} for e in eqs],
                      index=pd.Index([nom[e["id"]] for e in eqs], name="Equipo"))
    st.bar_chart(df, x_label="Equipo", y_label="Horas", stack=True, color=[LF.COLOR_ESTADO[s] for s in est_usados])

    st.markdown("#### Niveles de los tanques pulmón")
    th = res["tiempo_h"]
    if res["tanques"]:
        dn = pd.DataFrame({f"{t['id']} (t)": res["niveles"][t["id"]] for t in res["tanques"]}, index=pd.Index(th, name="h"))
        st.line_chart(dn, x_label="Hora de la simulación", y_label="Nivel (t)")
    st.markdown("#### Producción acumulada")
    dp = pd.DataFrame({"Producción simulada (t)": res["produccion_acumulada_t"],
                       "Sin fallas a la tasa de la línea (t)": [res["tasa_linea_t_h"] * h for h in th]}, index=pd.Index(th, name="h"))
    st.line_chart(dp, x_label="Hora de la simulación", y_label="Producto (t)")
    with st.expander("Tasa de proceso de cada equipo en el tiempo"):
        st.line_chart(pd.DataFrame({nom[k] + " (t/h)": v for k, v in res["tasas"].items()}, index=pd.Index(th, name="h")),
                      x_label="Hora de la simulación", y_label="t/h de la carga de cada equipo")

    AT.tabla("ln_resultado", "Resultado por equipo", 4)   # PAT 134: «?» de la tabla
    filas = []
    for e in eqs:
        v = res["por_equipo"][e["id"]]; h = v["horas_por_estado"]
        filas.append(dict(eq=nom[e["id"]], cap=e["capacidad_t_h"], carga=e["carga_t_h"], util=v["utilizacion"], op=h["operando"], bl=h["bloqueado"],
                          es=h["esperando"], fa=h["en_falla"], ma=h["en_mantenimiento"], de=h["detenido_programado"], nf=v["fallas"],
                          di=v["disponibilidad"], dt=v["disponibilidad_teorica"]))
    C.mostrar_tabla(filas, [("eq", "Equipo", "txt", 0), ("cap", "Tasa máxima (t/h)", "num", 1), ("carga", "Carga de diseño (t/h)", "num", 1),
                            ("util", "Utilización", "pct", 1), ("op", "Operando (h)", "num", 1), ("bl", "Bloqueado (h)", "num", 1),
                            ("es", "Esperando (h)", "num", 1), ("fa", "En falla (h)", "num", 1), ("ma", "En mantenimiento (h)", "num", 1),
                            ("de", "Detenido programado (h)", "num", 1), ("nf", "Fallas", "num", 0), ("di", "Disponibilidad", "pct", 1),
                            ("dt", "MTBF/(MTBF + MTTR)", "pct", 1)])
    st.markdown("#### Animación de la línea")      # PAT 134: vista 2D como la del modelo de FlexSim
    AN.mostrar(res)
    with st.expander("Supuestos y datos de la simulación"):
        AT.tabla("ln_supuestos", "Supuestos")   # PAT 134: «?» de la tabla
        C.mostrar_tabla(res["supuestos"], [("nombre", "Supuesto", "txt", 0), ("valor", "Valor", "num", 2), ("unidad", "Unidad", "txt", 0),
                                           ("justificacion", "Justificación", "txt", 0)])
        fa = res["parametros"]["fallas"]
        AT.tabla("ln_fallas_usadas", "Fallas simuladas")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(eq=nom[k], mtbf=v["mtbf"]["expresion"] if v else "sin fallas", mttr=v["mttr"]["expresion"] if v else "—",
                              base=BASES.get(v["base"], v["base"]) if v else "—", ori=v["origen"] if v else "—") for k, v in fa.items()],
                        [("eq", "Equipo", "txt", 0), ("mtbf", "Tiempo entre fallas (h)", "txt", 0), ("mttr", "Tiempo de reparación (h)", "txt", 0),
                         ("base", "Reloj de falla", "txt", 0), ("ori", "Origen", "txt", 0)])
        AT.tabla("ln_tanques_usados", "Tanques simulados")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(id=t["id"], c=t["capacidad_t"], n=t["nivel_inicial_t"], o="anulado" if t["anulado"] else t["origen"]) for t in res["tanques"]],
                        [("id", "Tanque", "txt", 0), ("c", "Capacidad (t)", "num", 2), ("n", "Nivel inicial (t)", "num", 2), ("o", "Origen", "txt", 0)])
        st.caption(C.esc("Gamma y lognormal con coeficiente de variación 0,5 y uniforme de 0,5 a 1,5 veces la media cuando solo se da la media: "
                         "Supuesto PAT 134. Método de fallas por tiempo ocupado o calendario: Law (2015, cap. 14); fuente de FlexSim: manual "
                         "público (*Fluid Library*, *Ticker* y MTBF/MTTR)."))
