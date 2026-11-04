"""Pestaña Experimentos (PAT 134, segunda ronda): escenarios × réplicas con números aleatorios comunes, medidas de desempeño con
intervalo de confianza t de Student, gráfico de réplicas, comparación pareada de dos escenarios y exportación, como el
Experimenter de FlexSim; y un optimizador simple (grilla o aleatorio con réplicas) en lugar de OptQuest.
El motor está en pat_sim/motor/experimentador.py. Todo queda en st.session_state.experimento; las claves llevan el prefijo ex_."""
from __future__ import annotations
import base64
import pandas as pd
import streamlit as st
from pat_sim.motor import experimentador as EX
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

SENTIDOS = {"auto": "Según la medida", "max": "Maximizar", "min": "Minimizar"}
METODOS = {"grilla": "Grilla: todas las combinaciones (hasta 500)", "aleatorio": "Aleatorio: n combinaciones distintas al azar"}
OPERADORES = ["<=", ">="]


def _estado() -> dict:
    return st.session_state.setdefault("experimento", {})


def _img(svg: str, alt: str) -> str:
    return (f'<img alt="{alt}" style="width:100%;height:auto;max-width:900px" src="data:image/svg+xml;base64,'
            + base64.b64encode(svg.encode("utf-8")).decode("ascii") + '">')


def _num(v, entero=False):
    return C.fmt(v, 0) if entero else C.fmt(v, 3 if abs(float(v)) < 10 else 2)


def _etq(m: dict) -> str:
    return f"{m['nombre']} ({m['unidad']})"


# ----------------------------------------------------------------------------------------------- escenarios
def _df_escenarios(pl, modelo, vs) -> pd.DataFrame:
    guardados = _estado().get("escenarios", {}).get(f"{modelo}|{pl.rubro}")
    esc = guardados or EX.escenarios_ejemplo(pl, modelo)
    base = {v["clave"]: v["defecto"] for v in vs}
    return pd.DataFrame([dict(Escenario=e["nombre"], **{k: e["params"].get(k, base[k]) for k in base}) for e in esc])


def _leer_escenarios(df: pd.DataFrame, vs) -> list:
    out = []
    for _i, f in df.iterrows():
        nom = f.get("Escenario")
        nom = "" if nom is None or (not isinstance(nom, str) and pd.isna(nom)) else str(nom).strip()
        if not nom:
            continue
        params = {}
        for v in vs:
            x = f.get(v["clave"])
            if x is not None and not pd.isna(x):
                params[v["clave"]] = float(x)
        out.append(dict(nombre=nom, params=params))
    return out


def _formulario(pl, modelo, M, vs):
    df0 = _df_escenarios(pl, modelo, vs)
    cfg = {"Escenario": st.column_config.TextColumn("Escenario", required=True, help="Nombre único del escenario")}
    for v in vs:
        cfg[v["clave"]] = st.column_config.NumberColumn(f"{v['nombre']} ({v['unidad']})", min_value=float(v["minimo"]), max_value=float(v["maximo"]),
                                                         step=1 if v["entero"] else None, help=v.get("ayuda") or None)
    with st.form("ex_form"):
        AT.tabla("ex_escenarios", "Escenarios (una fila por escenario, una columna por variable)")   # PAT 134: «?» de la tabla
        df = st.data_editor(df0, num_rows="dynamic", column_config=cfg, hide_index=True, width="stretch", key=f"ex_tabla_{modelo}_{pl.rubro}")
        df = df0 if df is None else df
        a, b, c = st.columns(3)
        rep = a.number_input("Réplicas por escenario", 1, 100, 5, 1, key="ex_replicas",
                             help="Cada réplica usa la semilla base + r en todos los escenarios (números aleatorios comunes).")
        sem = b.number_input("Semilla base", 0, 10 ** 6, 1, 1, key="ex_semilla")
        cal = c.number_input("Calentamiento (h)", 0.0, 1000.0, 0.0, 1.0, key="ex_calentamiento", disabled=not M.get("calentamiento"),
                             help="Horas iniciales que se descartan de cada réplica. Solo en el modelo de la línea; en temporada y "
                                  "operación el estado inicial es real y no se descarta nada.")
        enviar = st.form_submit_button("Correr experimento", type="primary")
    if not enviar:
        return
    esc = _leer_escenarios(df, vs)
    _estado().setdefault("escenarios", {})[f"{modelo}|{pl.rubro}"] = esc
    try:
        with st.spinner("Corriendo los escenarios y sus réplicas…"):
            _estado()["resultado"] = EX.correr(pl, modelo, esc, replicas=int(rep), semilla_base=int(sem), calentamiento=float(cal or 0.0))
    except ValueError as e:
        st.warning(f"No se pudo correr el experimento: {e}")


# ----------------------------------------------------------------------------------------------- resultados
def _resultado(res: dict):
    AT.tabla("ex_resultados", "Resultados", 4, antes=f"{res['metodo']} {res['nota_calentamiento']} Método: {res['fuente']}.")   # PAT 134: «?» de la tabla
    st.caption(C.esc(f"{res['nombre_modelo']}. {res['replicas']} réplicas por escenario (semillas {', '.join(map(str, res['semillas']))})."))
    for a in res["avisos"]:
        st.warning(a)
    filas = []
    for m in res["medidas"]:
        d = m.get("decimales", 2)
        for f in res["resumen"]:
            if f["medida"] != m["clave"]:
                continue
            ic = "—" if f["ic_inf"] is None else f"{C.fmt(f['ic_inf'], d)} a {C.fmt(f['ic_sup'], d)}"
            filas.append(dict(medida=_etq(m), escenario=f["escenario"], media=C.fmt(f["media"], d), ic=ic, sd=C.fmt(f["desviacion"], d),
                              mn=C.fmt(f["minimo"], d), mx=C.fmt(f["maximo"], d)))
    C.mostrar_tabla(filas, [("medida", "Medida de desempeño", "txt", 0), ("escenario", "Escenario", "txt", 0), ("media", "Media", "cen", 0),
                            ("ic", "IC al 95 %", "cen", 0), ("sd", "Desviación", "cen", 0), ("mn", "Mínimo", "cen", 0), ("mx", "Máximo", "cen", 0)])

    claves = [m["clave"] for m in res["medidas"]]; nom = {m["clave"]: _etq(m) for m in res["medidas"]}
    C.ayuda("Cada punto es una réplica; la raya es la media y la barra el intervalo de confianza al 95 %.", "Gráfico de réplicas", 5)   # PAT 134
    med = st.selectbox("Medida", claves, format_func=nom.get, key="ex_graf_medida")
    if med not in claves:
        med = claves[0]
    st.html(_img(EX.grafico_replicas_svg(res, med), "Réplicas por escenario"))

    nombres = [e["nombre"] for e in res["escenarios"]]
    if len(nombres) >= 2:
        C.ayuda("Como ambos escenarios usan las mismas semillas, la diferencia se calcula réplica a réplica y el ruido común se "   # PAT 134
                "cancela (Law, 2015, cap. 10).", "Comparar dos escenarios (diferencias pareadas)", 5)
        a, b, c = st.columns(3)
        ea = a.selectbox("Escenario A", nombres, index=0, key="ex_cmp_a")
        eb = b.selectbox("Escenario B", nombres, index=1, key="ex_cmp_b")
        mc = c.selectbox("Medida", claves, format_func=nom.get, key="ex_cmp_medida")
        ea = ea if ea in nombres else nombres[0]; eb = eb if eb in nombres else nombres[1]; mc = mc if mc in claves else claves[0]
        if ea == eb:
            st.info("Elija dos escenarios distintos.")
        else:
            cp = EX.comparar(res, ea, eb, mc)
            (st.success if cp["significativa"] else st.info)(C.esc(cp["texto"]))
    d1, d2 = st.columns(2)
    d1.download_button("Descargar resultados (HTML)", EX.exportar_html(res), file_name="Experimento_pat_sim.html", mime="text/html",
                       key="ex_dl_html", width="stretch")
    d2.download_button("Descargar resultados (CSV)", EX.a_csv(res).encode("utf-8-sig"), file_name="Experimento_pat_sim.csv", mime="text/csv",
                       key="ex_dl_csv", width="stretch")


# ----------------------------------------------------------------------------------------------- optimizador
def _rango(v) -> tuple:
    lo, hi, x = float(v["minimo"]), float(v["maximo"]), float(v["defecto"])
    if x > 0:
        a, b = max(lo, 0.75 * x), min(hi, 1.25 * x)
    else:
        a, b = lo, min(hi, lo + 0.1 * (hi - lo))
    paso = (b - a) / 4 if b > a else 0.0
    if v["entero"]:
        a, b, paso = round(a), round(b), max(1, round(paso))
    elif paso > 0:
        paso = float(f"{paso:.2g}")
    return a, b, paso


def _optimizador(pl, modelo, vs, meds):
    C.ayuda(EX.NOTA_OPTQUEST, "Optimizador (en lugar de OptQuest)")   # PAT 134: ayuda «?»
    filas = []
    for i, v in enumerate(vs):
        a, b, p = _rango(v)
        filas.append(dict(Usar=i == 0, Variable=f"{v['nombre']} ({v['unidad']})", Mínimo=a, Máximo=b, Paso=p))
    dv0 = pd.DataFrame(filas, index=[v["clave"] for v in vs])
    nom = {m["clave"]: _etq(m) for m in meds}; por_nombre = {v: k for k, v in nom.items()}
    dr0 = pd.DataFrame({"Medida": pd.Series([], dtype="object"), "Operador": pd.Series([], dtype="object"), "Valor": pd.Series([], dtype="float")})
    with st.form("ex_opt_form"):
        AT.tabla("ex_opt_vars", "Variables de diseño (las no marcadas quedan en su valor por defecto)")   # PAT 134: «?» de la tabla
        dv = st.data_editor(dv0, hide_index=True, width="stretch", key=f"ex_opt_vars_{modelo}_{pl.rubro}", disabled=["Variable"],
                            column_config={"Usar": st.column_config.CheckboxColumn("Usar"), "Paso": st.column_config.NumberColumn("Paso", min_value=0.0)})
        dv = dv0 if dv is None else dv
        a, b = st.columns(2)
        obj = a.selectbox("Objetivo", [m["clave"] for m in meds], format_func=nom.get, key="ex_opt_objetivo")
        sen = b.selectbox("Sentido", list(SENTIDOS), format_func=SENTIDOS.get, key="ex_opt_sentido")
        AT.tabla("ex_opt_restr", "Restricciones sobre la media de las réplicas (opcionales)")   # PAT 134: «?» de la tabla
        dr = st.data_editor(dr0, num_rows="dynamic", hide_index=True, width="stretch", key=f"ex_opt_restr_{modelo}",
                            column_config={"Medida": st.column_config.SelectboxColumn("Medida", options=list(nom.values())),
                                           "Operador": st.column_config.SelectboxColumn("Operador", options=OPERADORES),
                                           "Valor": st.column_config.NumberColumn("Valor")})
        dr = dr0 if dr is None else dr
        a, b, c, d = st.columns(4)
        met = a.selectbox("Método", list(METODOS), format_func=METODOS.get, key="ex_opt_metodo")
        n = b.number_input("Candidatos (método aleatorio)", 1, 500, 20, 1, key="ex_opt_n")
        rep = c.number_input("Réplicas por candidato", 1, 50, 3, 1, key="ex_opt_replicas")
        sem = d.number_input("Semilla base", 0, 10 ** 6, 1, 1, key="ex_opt_semilla")
        enviar = st.form_submit_button("Buscar la mejor configuración", type="primary")
    if enviar:
        info = {v["clave"]: v for v in vs}
        var = {k: (float(f["Mínimo"]), float(f["Máximo"]), float(f["Paso"] or 0.0)) for k, f in dv.iterrows()
               if k in info and bool(f["Usar"]) and not pd.isna(f["Mínimo"]) and not pd.isna(f["Máximo"])}
        restr = [(por_nombre[f["Medida"]], f["Operador"], float(f["Valor"])) for _i, f in dr.iterrows()
                 if f.get("Medida") in por_nombre and f.get("Operador") in OPERADORES and f.get("Valor") is not None and not pd.isna(f.get("Valor"))]
        obj = obj if obj in nom else meds[0]["clave"]
        sentido = next(m["sentido"] for m in meds if m["clave"] == obj) if sen not in ("max", "min") else sen
        try:
            with st.spinner("Evaluando los candidatos con sus réplicas…"):
                _estado()["optimizacion"] = EX.optimizar(pl, modelo, var, (obj, sentido), restr, replicas=int(rep), metodo=met or "grilla",
                                                         n=int(n), semilla_base=int(sem))
        except ValueError as e:
            st.warning(f"No se pudo optimizar: {e}")
    o = _estado().get("optimizacion")
    if not o or o["modelo"] != modelo or o["rubro"] != pl.rubro:
        return
    for a_ in o["avisos"]:
        st.warning(a_)
    ob = o["objetivo"]; mj = o["mejor"]; ent = {v["clave"]: v["entero"] for v in vs}; nv = {v["clave"]: v["nombre"] for v in vs}
    a, b, c = st.columns(3)
    a.metric("Candidatos evaluados", C.fmt(o["evaluados"], 0), f"{o['replicas']} réplicas cada uno", delta_color="off")
    b.metric("Cumplen las restricciones", C.fmt(o["factibles"], 0), delta_color="off")
    c.metric(f"Mejor {ob['nombre'].lower()}", "—" if mj is None else C.fmt(mj["objetivo"], 2) + " " + ob["unidad"],
             "maximizar" if ob["sentido"] == "max" else "minimizar", delta_color="off")
    if mj:
        st.success(C.esc("Mejor configuración: " + "; ".join(f"{nv.get(k, k)} = {_num(v, ent.get(k))}" for k, v in mj["params"].items()) + "."))
    claves = list(o["variables"])
    filas = []
    for cd in o["candidatos"][:50]:
        lo, hi = cd["ic"][ob["medida"]]
        f = dict(pos=cd["posicion"], cand=cd["candidato"], obj=C.fmt(cd["objetivo"], 3),
                 ic="—" if lo is None else f"{C.fmt(lo, 3)} a {C.fmt(hi, 3)}", fac="sí" if cd["factible"] else "no", vio="; ".join(cd["violaciones"]))
        f.update({f"v_{k}": _num(cd["params"][k], ent.get(k)) for k in claves})
        filas.append(f)
    AT.tabla("ex_candidatos", "Candidatos evaluados")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("pos", "Posición", "num", 0), ("cand", "Candidato", "txt", 0)] + [(f"v_{k}", nv.get(k, k), "cen", 0) for k in claves]
                    + [("obj", f"{ob['nombre']} (media)", "cen", 0), ("ic", "IC al 95 %", "cen", 0), ("fac", "Factible", "txt", 0),
                       ("vio", "Restricciones no cumplidas", "txt", 0)])
    if len(o["candidatos"]) > 50:
        st.caption("Se muestran los 50 primeros; las descargas traen todos.")
    d1, d2 = st.columns(2)
    d1.download_button("Descargar la optimización (HTML)", EX.exportar_html(o), file_name="Optimizacion_pat_sim.html", mime="text/html",
                       key="ex_opt_dl_html", width="stretch")
    d2.download_button("Descargar la optimización (CSV)", EX.a_csv(o).encode("utf-8-sig"), file_name="Optimizacion_pat_sim.csv", mime="text/csv",
                       key="ex_opt_dl_csv", width="stretch")


# ----------------------------------------------------------------------------------------------- pestaña
def mostrar():
    pl = C.planta()
    mods = EX.disponibles()
    C.ayuda("Como el Experimenter de FlexSim: cada escenario cambia variables del modelo y se corre varias veces (réplicas) con las "   # PAT 134
            "mismas semillas en todos los escenarios; los resultados traen media, intervalo de confianza t de Student, mínimo y máximo."
            + ("" if "linea" in mods else " El modelo de la línea aparece cuando esté listo motor/linea_fluida.py."),
            "Experimentos: escenarios, réplicas y optimizador", 3)
    if not C.exigir_resuelta():
        return
    modelo = st.selectbox("Modelo", list(mods), format_func=lambda k: mods[k]["nombre"], key="ex_modelo")
    if modelo not in mods:
        modelo = next(iter(mods))
    M = mods[modelo]
    try:
        vs = EX.variables(pl, modelo)
    except ValueError as e:
        st.warning(f"El modelo no se puede usar con esta planta: {e}")
        return
    meds = EX.medidas(modelo)
    with st.expander("Variables y medidas de desempeño del modelo"):
        st.caption(C.esc(M.get("nota", "")))
        AT.tabla("ex_variables", "Variables del modelo")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=v["nombre"], u=v["unidad"], d=_num(v["defecto"], v["entero"]), lo=_num(v["minimo"], v["entero"]),
                              hi=_num(v["maximo"], v["entero"])) for v in vs],
                        [("n", "Variable", "txt", 0), ("u", "Unidad", "txt", 0), ("d", "Por defecto", "cen", 0), ("lo", "Mínimo", "cen", 0),
                         ("hi", "Máximo", "cen", 0)])
        AT.tabla("ex_medidas", "Medidas de desempeño")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=m["nombre"], u=m["unidad"], s="Mayor es mejor" if m["sentido"] == "max" else "Menor es mejor") for m in meds],
                        [("n", "Medida de desempeño", "txt", 0), ("u", "Unidad", "txt", 0), ("s", "Sentido", "txt", 0)])
    _formulario(pl, modelo, M, vs)
    res = _estado().get("resultado")
    if res and res["modelo"] == modelo and res["rubro"] == pl.rubro:
        _resultado(res)
    elif res:
        st.info("El último experimento es de otro modelo o de otro rubro: corra el experimento de nuevo para ver sus resultados.")
    st.divider()
    _optimizador(pl, modelo, vs, meds)
