"""Pantalla Riesgo económico (PAT 135, tarea T7.2): Montecarlo del VAN con la confiabilidad de los equipos (MTBF y MTTR de la
Línea) y la fluctuación de la demanda (Temporada o el desafío), con las estrategias de capacidad de seguimiento, un nivel y
dos niveles. Indicación 2 del profesor Torres (04-11-2026). Motor: pat_sim/motor/mc_economico.py. Funciona en los cuatro rubros."""
from __future__ import annotations
import numpy as np
import pandas as pd
import streamlit as st
from pat_sim.motor import mc_economico as M
from . import comun as C
from . import s_riesgo   # PAT 135: se reutiliza el dibujo del tornado

COMPARAR = "Comparar las tres"
OPC_ESTRATEGIA = {COMPARAR: None, **{v: k for k, v in M.NOMBRE_ESTRATEGIA.items()}}
OPC_PERIODO = {"Semanas": "semana", "Meses": "mes"}
OPC_ALCANCE = {v: k for k, v in M.NOMBRE_ALCANCE.items()}


def mm(v) -> str:
    """Millones de pesos con el signo antes del $ (como s_riesgo.mm)."""
    return C.esc(("−" if v < 0 else "") + "$" + C.fmt(abs(v), 1) + " MM")


def _fallas_linea(pl) -> dict | None:
    """PAT 135: MTBF y MTTR que el usuario dejó en la pestaña Línea para este rubro ({id: (mtbf, mttr) o None})."""
    P = (st.session_state.get("ln_parametros") or {}).get(pl.rubro)
    if not P or not P.get("fallas"):
        return None
    out = {}
    for f in P["fallas"]:
        try:
            out[f["Equipo"]] = (float(f["MTBF (h)"]), float(f["MTTR (h)"])) if f.get("Falla") and float(f.get("MTBF (h)") or 0) > 0 else None
        except (KeyError, TypeError, ValueError):
            continue
    if not P.get("con_fallas", True):
        out = {k: None for k in out}
    return out or None


def _ayuda():
    with st.expander("?  Cómo se hace, para qué y por qué", expanded=False):
        st.markdown(C.esc(
            "**Para qué.** El profesor Torres pidió (04-11-2026) llevar a la evaluación económica la incertidumbre de la confiabilidad de "
            "los equipos y de la demanda: la planta se diseña con una estrategia de capacidad y en algunos períodos sobra capacidad "
            "(exceso, costo fijo sin uso) y en otros falta (déficit, venta perdida).\n\n"
            "**Cómo se hace.**\n"
            "1. Demanda por período: la curva de llegada de Temporada sumada por semanas o meses, o la demanda del desafío si existe. "
            "En pellet, chip y leña la llegada es pareja y se le da una estacionalidad de invierno (Supuesto). En cada réplica y año la "
            "demanda de cada período se multiplica por un factor gamma de media 1 con el coeficiente de variación elegido.\n"
            "2. Estrategia de capacidad (planeación agregada, Heizer, Render y Munson, 2017, cap. 13): seguimiento, la tasa sigue a la "
            "demanda esperada; un nivel, una tasa igual a la demanda media; dos niveles, una tasa para la temporada alta y otra para la "
            "baja. Se les suma la holgura y se limitan a la capacidad de la línea (recurso crítico).\n"
            "3. Confiabilidad: cada equipo de la línea tiene disponibilidad A = MTBF/(MTBF + MTTR). En cada período el número de fallas "
            "es Poisson con media horas × A / MTBF y cada reparación es exponencial de media MTTR (Law, 2015, cap. 6 y 14); la capacidad "
            "disponible es la del cuello de botella disponible. El mantenimiento preventivo baja la tasa de falla con un costo anual.\n"
            "4. Producción = mín(demanda, capacidad disponible); déficit × margen = margen perdido; exceso × fracción del margen = costo "
            "de la capacidad ociosa; cambiar la tasa entre períodos tiene un costo de ajuste. El ahorro de energía del recuperador es "
            "proporcional a la producción real.\n"
            "5. VAN de cada réplica con la tasa, el horizonte, la inversión y los precios de Economía (o el costo total del costeo de la "
            "planta). NumPy vectorizado con semilla fija y los mismos números aleatorios para las tres estrategias.\n\n"
            "**Por qué.** El VAN determinista supone que la planta produce siempre lo de diseño. Con fallas y demanda variable la "
            "producción real es menor, el ahorro del recuperador baja y aparecen costos de desajuste: la distribución del VAN, "
            "P(VAN < 0) y los percentiles 5 y 95 muestran ese riesgo y permiten elegir la estrategia de capacidad.\n\n"
            "**Alcance.** «Recuperador (VAN incremental)»: proyecto con recuperador menos situación sin recuperador. El margen perdido, "
            "la capacidad ociosa, el ajuste y el preventivo de la línea ocurren igual con o sin recuperador y se cancelan; la confiabilidad "
            "y la demanda solo mueven el ahorro de energía (proporcional a la producción real) y las paradas del propio recuperador, que "
            "dan ahorro cero mientras está detenido. «Planta completa con recuperador»: margen de lo producido + ahorro − costos de "
            "desajuste, con la inversión de toda la planta (costeo). En ambos se informan el déficit y el exceso medios.\n\n"
            "**Límites.** Sin inventario entre períodos; las paradas de equipos distintos no se suman (cota optimista frente a una línea "
            "en serie sin pulmones); el margen, la holgura, la estacionalidad y los costos de ociosidad, ajuste y preventivo son Supuestos "
            "didácticos sin fuente de la planta."))
        st.markdown("**Supuestos de partida (PAT 135)**")
        C.mostrar_tabla([dict(n=s.nombre, v=s.valor, u=s.unidad, j=s.justificacion) for s in M.SUPUESTOS.values()],
                        [("n", "Supuesto", "txt", 0), ("v", "Valor", "num", 2), ("u", "Unidad", "txt", 0), ("j", "Justificación", "txt", 0)])


def _parametros(pl, hay_desafio: bool, alcance0: str) -> dict:
    """Formulario de parámetros; quedan en st.session_state.mce_parametros, uno por rubro."""
    ss = st.session_state; todos = ss.setdefault("mce_parametros", {}); r = pl.rubro
    P = todos.get(r)
    if P is None:
        P = todos[r] = dict(margen=M.margen_defecto(r), cv=M.SUPUESTOS["cv_demanda"].valor * 100, holgura=M.SUPUESTOS["holgura"].valor * 100,
                            periodo="Semanas", estac=M.ESTACIONALIDAD.get(r, 0.0) * 100, programa=True, red_pm=0.0,
                            costo_pm=M.SUPUESTOS["costo_pm_equipo"].valor, ocioso=M.SUPUESTOS["frac_ocioso"].valor * 100,
                            ajuste=M.SUPUESTOS["frac_ajuste"].valor * 100, n=2000, semilla=135, alcance=M.NOMBRE_ALCANCE[alcance0],
                            alcance_auto=True)
    if P.get("alcance_auto", True) and P["alcance"] != M.NOMBRE_ALCANCE[alcance0]:
        # PAT 135: mientras el usuario no elija el alcance, sigue al costeo (planta si hay costo total, recuperador si no)
        P["alcance"] = M.NOMBRE_ALCANCE[alcance0]; ss[f"mce_alc_{r}"] = P["alcance"]
    with st.form(f"mce_form_{r}"):
        st.markdown("##### Demanda y estrategia")
        a, b, c, d = st.columns(4)
        margen = a.number_input(C.esc("Margen de contribución ($/t de producto)"), 0.0, 1e8, float(P["margen"]), 1000.0, key=f"mce_margen_{r}",
                                help=C.esc("Precio de venta menos costos variables por tonelada. " + M.SUPUESTOS["margen"].justificacion + "."))
        cv = b.number_input("Variación de la demanda (CV, %)", 0.0, 100.0, float(P["cv"]), 1.0, key=f"mce_cv_{r}",
                            help=M.SUPUESTOS["cv_demanda"].justificacion + ".")
        holg = c.number_input("Holgura de capacidad (%)", 0.0, 100.0, float(P["holgura"]), 1.0, key=f"mce_holg_{r}",
                              help=M.SUPUESTOS["holgura"].justificacion + ".")
        per = d.selectbox("Períodos", list(OPC_PERIODO), index=list(OPC_PERIODO).index(P["periodo"]), key=f"mce_per_{r}",
                          disabled=hay_desafio, help="Con demanda del desafío se usan sus períodos.")
        a, b, c, d = st.columns(4)
        est = a.number_input("Estacionalidad de la demanda (%)", 0.0, 95.0, float(P["estac"]), 5.0, key=f"mce_est_{r}", disabled=hay_desafio,
                             help=M.SUPUESTOS["estacionalidad"].justificacion + ".")
        prog = b.checkbox("Descontar las paradas del programa de la temporada", value=bool(P["programa"]), key=f"mce_prog_{r}",
                          help="Las horas de cada período se multiplican por la disponibilidad del programa de Temporada (arranque, limpiezas y paradas).")
        alc = c.selectbox("Alcance del VAN", list(OPC_ALCANCE), index=list(OPC_ALCANCE).index(P["alcance"]), key=f"mce_alc_{r}")
        st.markdown("##### Confiabilidad y costos de desajuste")
        a, b, c, d = st.columns(4)
        red = a.number_input("Reducción de la tasa de falla por preventivo (%)", 0.0, M.REDUCCION_MAX * 100, float(P["red_pm"]), 5.0, key=f"mce_red_{r}",
                             help=M.SUPUESTOS["reduccion_pm"].justificacion + ".")
        cpm = b.number_input(C.esc("Costo del preventivo (MM$/año por equipo, para bajar a la mitad)"), 0.0, 1e4, float(P["costo_pm"]), 0.5,
                             key=f"mce_cpm_{r}", help=M.SUPUESTOS["costo_pm_equipo"].justificacion + ".")
        oc = c.number_input("Costo de la capacidad ociosa (% del margen)", 0.0, 100.0, float(P["ocioso"]), 5.0, key=f"mce_oc_{r}",
                            help=M.SUPUESTOS["frac_ocioso"].justificacion + ".")
        aj = d.number_input("Costo de cambiar la capacidad (% del margen)", 0.0, 100.0, float(P["ajuste"]), 5.0, key=f"mce_aj_{r}",
                            help=M.SUPUESTOS["frac_ajuste"].justificacion + ".")
        st.markdown("##### Montecarlo")
        a, b = st.columns(2)
        n = a.number_input("Réplicas", 100, 50000, int(P["n"]), 500, key=f"mce_n_{r}")
        sem = b.number_input("Semilla", 0, 10 ** 9, int(P["semilla"]), 1, key=f"mce_sem_{r}", help="La misma semilla repite exactamente los resultados.")
        if st.form_submit_button("Simular", type="primary"):
            P.update(margen=margen, cv=cv, holgura=holg, periodo=per, estac=est, programa=prog, alcance=alc, red_pm=red, costo_pm=cpm,
                     ocioso=oc, ajuste=aj, n=int(n), semilla=int(sem),
                     alcance_auto=P.get("alcance_auto", True) and alc == M.NOMBRE_ALCANCE[alcance0])
    return P


def _grafico_periodos(ctx, res, est):
    x = res["estrategias"][est]["por_periodo"]; et = ctx["periodos"]["etiquetas"]
    df = pd.DataFrame({"Demanda esperada": x["demanda"], "Capacidad planificada": x["capacidad"],
                       "Capacidad disponible media (con fallas)": x["disponible"], "Producción media": x["produccion"]},
                      index=pd.Index(range(1, len(et) + 1), name="Período"))
    st.line_chart(df, x_label="Período (" + ("semana" if ctx["periodos"]["periodo"] == "semana" else "mes") + ")"
                  if ctx["periodos"]["origen"] == "temporada" else "Período del desafío", y_label="t de producto por período")


def mostrar():
    ss = st.session_state; pl = C.planta(); E = ss.economia
    st.subheader("Riesgo económico: confiabilidad y demanda")
    if not C.exigir_resuelta():
        return
    _ayuda()
    r = C.resumen_actual()
    demanda = (ss.get("desafio") or {}).get("demanda") or None
    costeo = ss.get("costeo") if isinstance(ss.get("costeo"), dict) else None
    alcance0 = "planta" if costeo and (costeo.get("total_clp") or 0) > 0 else "recuperador"
    P = _parametros(pl, bool(demanda), alcance0)
    try:
        ctx = M.contexto(pl, r, E, periodo=OPC_PERIODO[P["periodo"]], demanda=demanda, costeo=costeo, fallas=_fallas_linea(pl),
                         aplicar_programa=P["programa"], margen=P["margen"], estacionalidad=P["estac"] / 100)
    except ValueError as e:
        st.warning(f"No se puede armar el Montecarlo económico: {e}")
        return
    if ctx is None:
        st.info("La planta no tiene una caldera o un generador de calor con horas de operación: no hay ahorro que evaluar.")
        return
    for a in ctx["avisos"]:
        st.info(C.esc(a))
    if demanda:
        st.caption(f"Demanda del desafío: {len(ctx['periodos']['demanda'])} períodos.")
    params = dict(cv_demanda=P["cv"] / 100, holgura=P["holgura"] / 100, reduccion_pm=P["red_pm"] / 100, costo_pm_equipo=P["costo_pm"],
                  frac_ocioso=P["ocioso"] / 100, frac_ajuste=P["ajuste"] / 100, alcance=OPC_ALCANCE[P["alcance"]])
    if params["alcance"] == "planta" and not (costeo and (costeo.get("total_clp") or 0) > 0):
        st.warning("El alcance planta completa suma el margen de toda la producción, pero la inversión es la de Economía (el recuperador): "
                   "el VAN queda sobrestimado hasta que exista el costeo de la planta.")
    llave = (pl.rubro, repr(sorted(P.items())), repr(sorted((k, v) for k, v in E.items() if isinstance(v, (int, float, str)))),
             repr(costeo and costeo.get("total_clp")), repr(demanda), repr(_fallas_linea(pl)), id(pl), pl.nombre)
    g = ss.get("mce_resultado")
    if not g or g[0] != llave:
        with st.spinner("Simulando…"):
            ss["mce_resultado"] = g = (llave, M.simular(ctx, params, n=P["n"], semilla=P["semilla"]))
    res = g[1]

    sel = st.selectbox("Estrategia de capacidad", list(OPC_ESTRATEGIA), index=0, key="mce_estrategia",
                       help="Seguimiento, un nivel o dos niveles; «Comparar las tres» muestra las tres en el histograma y la tabla.")
    est = OPC_ESTRATEGIA[sel]
    vistas = list(M.ESTRATEGIAS) if est is None else [est]
    if est is None:
        est = max(M.ESTRATEGIAS, key=lambda k: res["estrategias"][k]["media"])
        st.caption("Estrategia con mayor VAN medio: " + M.NOMBRE_ESTRATEGIA[est] + ".")
    x = res["estrategias"][est]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("VAN medio", mm(x["media"]))
    m2.metric("Percentiles 5 y 95", C.esc(C.fmt(x["p5"], 0) + " a " + C.fmt(x["p95"], 0) + " MM$"))
    m3.metric("P(VAN < 0)", C.pct(x["prob_negativo"]))
    m4.metric("Nivel de servicio", C.pct(x["servicio"]))

    st.markdown("#### Distribución del VAN")
    todos = np.concatenate([res["estrategias"][k]["van"] for k in vistas])
    lo, hi = float(todos.min()), float(todos.max())
    clases = {k: M.histograma(res["estrategias"][k]["van"], 30, lo, hi) for k in vistas}
    marcas = [round((a + b) / 2, 1) for a, b, _c in clases[vistas[0]]]
    df = pd.DataFrame({M.NOMBRE_ESTRATEGIA[k]: [c for _a, _b, c in clases[k]] for k in vistas}, index=marcas)
    st.bar_chart(df, x_label="VAN (MM$, marca de clase)", y_label="Réplicas", stack=False)
    st.caption(f"{C.fmt(res['n'], 0)} réplicas × {res['anios']} años × {res['periodos']} períodos con la semilla {res['semilla']}, "
               f"en {C.fmt(res['segundos'], 2)} s. Alcance: {M.NOMBRE_ALCANCE[res['alcance']].lower()}.")

    st.markdown("#### Resultados por estrategia")
    filas = []
    for k in M.ESTRATEGIAS:
        y = res["estrategias"][k]; cp = y["componentes"]
        filas.append(dict(n=y["nombre"], van=y["media"], p5=y["p5"], p50=y["p50"], p95=y["p95"], pneg=y["prob_negativo"], prod=y["produccion_t"],
                          dfc=y["deficit_t"], exc=y["exceso_t"], serv=y["servicio"], perd=cp["margen_perdido"], oc=cp["ocioso"], aj=cp["ajuste"],
                          ah=cp["ahorro"], fl=cp["flujo"], mp=cp["margen_produccion"]))
    C.mostrar_tabla(filas, [("n", "Estrategia", "txt", 0), ("van", "VAN medio (MM$)", "mm", 1), ("p5", "Percentil 5 (MM$)", "mm", 1),
                            ("p50", "Mediana (MM$)", "mm", 1), ("p95", "Percentil 95 (MM$)", "mm", 1), ("pneg", "P(VAN < 0)", "pct", 1),
                            ("prod", "Producción (t/año)", "num", 0), ("dfc", "Déficit (t/año)", "num", 0), ("exc", "Exceso (t/año)", "num", 0),
                            ("serv", "Nivel de servicio", "pct", 1)])
    if res["alcance"] == "planta":
        C.mostrar_tabla(filas, [("n", "Estrategia", "txt", 0), ("mp", "Margen de lo producido (MM$/año)", "mm", 1),
                                ("ah", "Ahorro de energía (MM$/año)", "mm", 1), ("oc", "Capacidad ociosa (MM$/año)", "mm", 1),
                                ("aj", "Ajuste de capacidad (MM$/año)", "mm", 1), ("fl", "Flujo medio (MM$/año)", "mm", 1),
                                ("perd", "Margen perdido, informativo (MM$/año)", "mm", 1)])
        st.caption(C.esc(f"Inversión de la planta: {C.fmt(res['inversion'], 1)} MM$. Preventivo: {C.fmt(res['costo_pm'], 1)} MM$/año. "
                         f"Costo anual: {C.fmt(res['params']['costo_anual'], 1)} MM$/año. El margen perdido ya está en la menor producción."))
    else:
        C.mostrar_tabla(filas, [("n", "Estrategia", "txt", 0), ("ah", "Ahorro de energía (MM$/año)", "mm", 1),
                                ("fl", "Flujo medio (MM$/año)", "mm", 1), ("perd", "Margen perdido, informativo (MM$/año)", "mm", 1),
                                ("oc", "Capacidad ociosa, informativo (MM$/año)", "mm", 1)])
        st.caption(C.esc(f"VAN incremental del recuperador con la inversión de Economía: {C.fmt(res['inversion'], 1)} MM$; costo anual "
                         f"{C.fmt(res['params']['costo_anual'], 1)} MM$/año. Ahorro de diseño: {C.fmt(res['ahorro_diseno'], 1)} MM$/año. El margen "
                         "perdido y la capacidad ociosa ocurren igual sin recuperador: no entran al VAN y se muestran como indicadores."))
    st.caption("Déficit y exceso en t de producto por año: indicadores operacionales en ambos alcances.")

    st.markdown("#### Demanda y capacidad por período: " + M.NOMBRE_ESTRATEGIA[est].lower())
    _grafico_periodos(ctx, res, est)

    st.markdown("#### Confiabilidad de los equipos de la línea")
    eqf = [dict(id=e["id"], n=e["nombre"], t=e["tasa_mp"], mtbf=e["mtbf"], mttr=e["mttr"], a=e["disponibilidad"],
                hc=float(np.mean(c)) if c is not None else None, o=e["origen"]) for e, c in zip(ctx["equipos"], res["horas_caidas"])]
    rc = ctx.get("recuperador")
    if rc is not None:      # PAT 135: el recuperador no limita la línea; sus paradas solo quitan ahorro
        eqf.append(dict(id="—", n=rc["nombre"] + " (sin ahorro mientras está detenido)", t=None, mtbf=rc["mtbf"], mttr=rc["mttr"],
                        a=rc["disponibilidad"], hc=float(np.mean(res["horas_caidas_recuperador"])), o=rc["origen"]))
    C.mostrar_tabla(eqf, [("id", "Equipo", "txt", 0), ("n", "Nombre", "txt", 0), ("t", "Tasa máxima (t/h de materia prima)", "num", 1),
                          ("mtbf", "MTBF (h)", "num", 1), ("mttr", "MTTR (h)", "num", 2), ("a", "Disponibilidad", "pct", 1),
                          ("hc", "Horas caídas medias por período", "num", 2), ("o", "Origen", "txt", 0)])
    st.caption(C.esc(f"Capacidad de la línea: {C.fmt(ctx['cap_t_h'], 1)} t/h de materia prima. Disponibilidad del programa de la temporada: "
                     f"{C.pct(ctx['disp_programa'])}. Los MTBF y MTTR se cambian en la pestaña Línea."))

    st.markdown("#### Tornado del VAN medio: " + M.NOMBRE_ESTRATEGIA[est].lower())
    if st.checkbox("Calcular el tornado (unos segundos)", value=False, key="mce_tornado"):
        lt = (llave, est)
        t = ss.get("mce_tornado_res")
        if not t or t[0] != lt:
            with st.spinner("Calculando el tornado…"):
                ss["mce_tornado_res"] = t = (lt, M.tornado(ctx, est, params, n=min(400, int(P["n"])), semilla=P["semilla"]))
        st.image(s_riesgo.tornado_svg(t[1]), width="stretch")
        C.mostrar_tabla([dict(n=f["nombre"], lo=C.fmt(f["valor_bajo"], 2), hi=C.fmt(f["valor_alto"], 2), vb=f["van_bajo"], va=f["van_alto"],
                              amp=f["amplitud"]) for f in t[1]],
                        [("n", "Variable", "txt", 0), ("lo", "Valor bajo", "cen", 0), ("hi", "Valor alto", "cen", 0),
                         ("vb", "VAN con el bajo (MM$)", "mm", 1), ("va", "VAN con el alto (MM$)", "mm", 1), ("amp", "Amplitud (MM$)", "mm", 1)])
        st.caption("Cada variable va a su mínimo y a su máximo con las demás en el valor base; cada punto es un Montecarlo de hasta 400 "
                   "réplicas con la misma semilla. Rangos: precio, tasa e inversión como en Economía; margen ±30 %; variación de la demanda "
                   "de 5 a 30 %; MTBF y MTTR de 0,5 a 1,5 veces; holgura de 0 a 25 % (Supuesto PAT 135).")
