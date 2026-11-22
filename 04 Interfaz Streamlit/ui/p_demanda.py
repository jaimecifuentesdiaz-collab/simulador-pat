"""Pantalla Demanda (PAT 136, tarea T21): las dos lógicas de demanda del punto 4 de los comentarios del profesor Torres
(13-11-2026) y el catálogo de 10 perfiles de motor/demanda.py.

- Oferta agrícola (tomate, fruta): balance cosechado = procesado + perdido, capacidad de recepción necesaria (pico,
  percentil 95 y la menor que pierde menos de 1 %) y la pérdida con varias capacidades.
- Mercado (agar agar y otros): pronóstico con Holt-Winters, descomposición clásica, regresión con tendencia o Croston,
  errores MAD, MAPE y señal de rastreo, estrategias de capacidad (adelantarse, seguir y rezagarse) y plan agregado
  (nivelación contra persecución).
- Mixta: cosecha estacional, venta todo el año e inventario de producto.
- PAT 138: «Tomate: distribución de llegada», los 10 tipos de planta de tomate (catalogos/plantas_tomate.py) con las 10
  distribuciones de la llegada diaria de tomate (motor/demanda.DISTRIBUCIONES), con el mismo balance de la oferta agrícola.
  PAT 139 (14-11): los 10 modelos de planta (por °Brix y proceso) × los 3 tamaños (chica, mediana y grande) × las 10 distribuciones.
El botón «Llevar la serie al desafío» deja la demanda en st.session_state["desafio"], la misma clave que llena la pantalla
Desafío (ui/p_desafio.py) y que leen Riesgo económico y Selección de equipos. Claves de widgets con prefijo «dem_».
"""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import RUBROS
from pat_sim.motor import demanda as M
from . import comun as C

LOGICA = {"agricola": "empujada por la oferta agrícola", "mercado": "tirada por el mercado", "mixta": "mixta: oferta agrícola y mercado"}
AYUDA = """
**Cómo se usa**

1. Elija un perfil de demanda. Cada uno trae sus parámetros por defecto con su fuente o la marca «Supuesto».
2. Cambie los parámetros que quiera y la semilla (la misma semilla repite la misma serie).
3. Oferta agrícola: revise cuánto se pierde con la capacidad de recepción elegida y la capacidad necesaria.
4. Mercado: elija el método de pronóstico, revise los errores (MAD, MAPE y señal de rastreo), compare las estrategias de
   capacidad y el plan agregado con inventario.
5. Presione «Llevar la serie al desafío»: la demanda del desafío en curso se reemplaza por esta serie (o por su pronóstico).
   Si no hay desafío en curso, se arma uno con el rubro de la planta de la sesión. La planta no cambia.

**Métodos**

Holt-Winters aditivo y multiplicativo y descomposición clásica según Hyndman y Athanasopoulos (2021), *Forecasting:
principles and practice*, 3.ª ed. Errores, señal de rastreo (límite de ±4 MAD), estrategias de capacidad y plan agregado
según Heizer, Render y Munson (2017), *Operations management*, 12.ª ed., y Jacobs y Chase, *Operations and supply chain
management* (cita general de la obra). Los costos por omisión son supuestos didácticos: cámbielos.
"""


def _parametros(pid: str) -> dict:
    """Un control por parámetro del perfil (clave dem_<perfil>_<parámetro>). Devuelve solo los valores cambiados."""
    P = M.PERFILES[pid]["parametros"]; out = {}
    with st.expander("Parámetros del perfil", expanded=False):
        cols = st.columns(3)
        for i, (k, p) in enumerate(P.items()):
            col = cols[i % 3]; lab = f"{p['nombre']}" + (f" ({p['unidad']})" if p["unidad"] else ""); key = f"dem_{pid}_{k}"
            if p["opciones"]:
                ops = list(p["opciones"])
                v = col.selectbox(lab, ops, index=ops.index(p["valor"]), key=key, help=p["fuente"])
            elif isinstance(p["valor"], int):
                v = col.number_input(lab, min_value=0, value=int(p["valor"]), step=1, key=key, help=p["fuente"])
            else:
                x = float(p["valor"]); paso = 0.01 if x < 1 else (1.0 if x < 1000 else 10.0)
                v = col.number_input(lab, min_value=0.0, value=x, step=paso, format="%.4f" if x < 0.1 else None, key=key, help=p["fuente"])
            if v != p["valor"]:
                out[k] = v
    return out


def _df(cols: dict, indice: list):
    import pandas as pd
    return pd.DataFrame(cols, index=pd.Index(list(range(1, len(indice) + 1)), name="Período"))


def _linea(cols: dict, n: int, x_label: str, y_label: str):
    try:
        st.line_chart(_df(cols, list(range(n))), x_label=x_label, y_label=y_label)
    except ImportError:                          # sin pandas: la tabla resumida queda abajo
        st.caption("No está pandas: se omite el gráfico.")


def _barras(res: dict):
    filas = [{"Período": e, "Orden": i, "Demanda": v} for i, (e, v) in enumerate(zip(res["etiquetas"], res["serie"]))]
    spec = {"mark": {"type": "bar", "color": "#1b7a5a", "tooltip": True},
            "encoding": {"x": {"field": "Período", "type": "ordinal", "sort": None, "title": res["periodo"].capitalize(),
                               "axis": {"labelAngle": -45 if len(filas) > 12 else 0, "labelOverlap": True}},
                         "y": {"field": "Demanda", "type": "quantitative", "title": f"Demanda ({res['unidad']} por {res['periodo']})"}},
            "height": 280}
    try:
        from .p_desafio import grafico_barras      # PAT 139: el navegador no redibujaba el gráfico al cambiar la serie (ver allí)
        grafico_barras(filas, spec, "dem_barras")
    except ImportError:
        C.mostrar_tabla(filas, [("Período", "Período", "txt", 0), ("Demanda", f"Demanda ({res['unidad']})", "num", 1)])


def _estadisticas(res: dict):
    e = res["estadisticas"]; u = res["unidad"]; per = res["periodo"]
    i = e["i_max"]
    C.mostrar_tabla([dict(c="Total", v=e["total"], u=u), dict(c=f"Media por {per}", v=e["media"], u=u),
                     dict(c=f"Máximo ({res['etiquetas'][i] if i is not None else '—'})", v=e["maximo"], u=u),
                     dict(c="Percentil 95", v=e["p95"], u=u), dict(c="Mínimo", v=e["minimo"], u=u),
                     dict(c="Coeficiente de variación", v=100 * e["cv"], u="%")],
                    [("c", "Demanda", "txt", 0), ("v", "Valor", "num", 1), ("u", "Unidad", "txt", 0)])


# ------------------------------------------------------------------ oferta agrícola
def _agricola(res: dict, pid: str | None, params: dict, regenerar=None):
    """regenerar(capacidad_t_h) -> extra de la serie con esa capacidad (PAT 138: la llegada de tomate); None usa el perfil pid."""
    x = res["extra"]; b = x["balance"]; cap = x["capacidad"]
    st.markdown("##### Balance de la temporada")
    a, c, d = st.columns(3)
    a.metric("Cosechado", C.fmt(b["cosechado"], 0) + " t")
    c.metric("Procesado", C.fmt(b["procesado"], 0) + " t")
    d.metric("Perdido", C.fmt(b["perdido"], 0) + " t", C.pct(b["fraccion_perdida"], 2) + " de lo cosechado", delta_color="off")
    n = len(res["serie"])
    _linea({f"Llega ({res['unidad']})": res["serie"], f"Procesado ({res['unidad']})": x["procesado"], f"Perdido ({res['unidad']})": x["perdido"]},
           n, res["periodo"].capitalize() + " de la temporada", f"Materia prima ({res['unidad']} por {res['periodo']})")
    st.caption("Cierre de masa: cosechado = procesado + perdido. Lo que espera en el patio se procesa primero (FIFO), se degrada "
               "sobre el umbral de espera y se descarta si supera la perecibilidad.")
    st.markdown("##### Capacidad de recepción necesaria")
    C.mostrar_tabla([dict(c="Llegada media de la temporada", v=cap["media_t_h"]), dict(c="Percentil 95 de la llegada diaria", v=cap["percentil_t_h"]),
                     dict(c="Peak de la llegada diaria", v=cap["pico_t_h"]),
                     dict(c="Menor capacidad que pierde 1 % o menos", v=cap.get("para_perdida_1pct_t_h")),
                     dict(c="Capacidad elegida", v=cap["capacidad_t_h"])],
                    [("c", "Capacidad", "txt", 0), ("v", "t/h", "num", 1)])
    filas = []
    for f in (0.6, 0.8, 0.9, 1.0, 1.1, 1.2):
        k = f * cap["pico_t_h"]
        r = regenerar(k) if regenerar else M.generar(pid, dict(params, capacidad_t_h=k), res["semilla"])["extra"]
        filas.append(dict(c=f"{C.fmt(100 * f, 0)} % del peak", k=k, p=r["balance"]["fraccion_perdida"], u=r["capacidad"]["utilizacion"]))
    C.mostrar_tabla(filas, [("c", "Caso", "txt", 0), ("k", "Capacidad (t/h)", "num", 1), ("p", "Pérdida", "pct", 2), ("u", "Utilización", "pct", 1)])


# ------------------------------------------------------------------ mixta
def _mixta(res: dict):
    x = res["extra"]
    _linea({"Producción (t)": res["serie"], "Venta del mercado (t)": x["demanda_mercado"], "Inventario al cierre (t)": x["inventario"]},
           len(res["serie"]), "Mes (el año parte con la cosecha)", "t de producto")
    C.mostrar_tabla([dict(c="Materia prima ofrecida por la cosecha", v=x["oferta_materia_prima_t"]),
                     dict(c="Materia prima procesada", v=x["materia_prima_usada_t"]), dict(c="Materia prima sobrante", v=x["materia_prima_sobrante_t"]),
                     dict(c="Inventario inicial necesario", v=x["inventario_inicial"]), dict(c="Inventario máximo", v=max(x["inventario"])),
                     dict(c="Venta no cubierta por la oferta", v=x["venta_no_cubierta_t"])],
                    [("c", "Concepto", "txt", 0), ("v", "t", "num", 1)])


# ------------------------------------------------------------------ mercado: pronóstico
def _pronostico(res: dict) -> dict | None:
    serie = res["serie"]; m = int(res["extra"].get("m") or 12)
    st.markdown("##### Pronóstico")
    if sum(serie) <= 0:
        st.info("La serie es cero en todos los períodos: no hay nada que pronosticar.")
        return None
    validos = M.metodos_validos(serie, m)
    if not validos:
        st.info("La serie es muy corta para pronosticar.")
        return None
    if st.session_state.get("dem_metodo") not in validos:     # PAT 136: el método elegido no sirve para este perfil
        st.session_state.pop("dem_metodo", None)
    defecto = res["extra"].get("metodo") if res["extra"].get("metodo") in validos else validos[0]
    a, b, c = st.columns(3)
    met = a.selectbox("Método", validos, index=validos.index(defecto), format_func=lambda k: M.METODOS[k], key="dem_metodo")
    h = int(b.number_input("Horizonte (períodos)", min_value=1, max_value=4 * m, value=m, step=1, key="dem_h"))
    opt = c.checkbox("Elegir alfa, beta y gamma con la rejilla", value=True, key="dem_optimizar",
                     help="Minimiza el error cuadrático medio del ajuste un paso adelante (175 combinaciones)")
    alfa, beta, gamma = 0.3, 0.1, 0.2
    if not opt:
        x, y, z = st.columns(3)
        alfa = x.slider("Alfa (nivel)", 0.01, 1.0, 0.3, 0.01, key="dem_alfa")
        beta = y.slider("Beta (tendencia)", 0.0, 1.0, 0.1, 0.01, key="dem_beta")
        gamma = z.slider("Gamma (estacionalidad)", 0.0, 1.0, 0.2, 0.01, key="dem_gamma")
    try:
        r = M.pronosticar(serie, m, met, h, opt, alfa, beta, gamma)
    except ValueError as e:
        st.warning(f"No se pudo pronosticar: {e}")
        return None
    n = len(serie)
    real = serie + [None] * h; aj = list(r["ajuste"]) + [None] * h; fc = [None] * (n - 1) + [serie[-1]] + list(r["pronostico"])
    _linea({"Real": real, "Ajuste un paso adelante": aj, "Pronóstico": fc}, n + h, f"{res['periodo'].capitalize()}", f"{res['unidad']} por {res['periodo']}")
    if any(k in r for k in ("alfa", "beta", "gamma")):
        st.caption(C.esc(f"{r['nombre']}: " + ", ".join(f"{k} = {C.fmt(r[k], 2)}" for k in ("alfa", "beta", "gamma") if k in r)
                         + (f". Error cuadrático medio del ajuste: {C.fmt(r['ecm'], 2)}" if "ecm" in r else "")))
    ini = m if met.startswith("hw_") or met == "descomposicion" else 1
    e = M.errores(serie[ini:], r["ajuste"][ini:])
    st.markdown("###### Errores del ajuste y comparación de métodos en la última estación")
    filas = [dict(n=f"{r['nombre']} (ajuste, desde el período {ini + 1})", mad=e["mad"], mape=e["mape"], ses=e["sesgo"], ts=e["senal_max"],
                  ok="fuera de control" if e["fuera_de_control"] else "en control")]
    for x in M.evaluar_metodos(serie, m, m):
        ee = x["errores"]
        filas.append(dict(n=f"{x['nombre']} (prueba con los últimos {m})", mad=ee["mad"], mape=ee["mape"], ses=ee["sesgo"], ts=ee["senal_max"],
                          ok="fuera de control" if ee["fuera_de_control"] else "en control"))
    C.mostrar_tabla(filas, [("n", "Método", "txt", 0), ("mad", "MAD", "num", 2), ("mape", "MAPE (%)", "num", 1), ("ses", "Sesgo", "num", 2),
                            ("ts", "Señal de rastreo máxima", "num", 2), ("ok", "Control (±4 MAD)", "txt", 0)])
    st.caption("MAD: desviación absoluta media. MAPE: error porcentual absoluto medio (solo períodos con demanda). Señal de rastreo: "
               "suma acumulada de errores / MAD acumulado; fuera de ±4 indica sesgo del pronóstico.")
    return r


# ------------------------------------------------------------------ mercado: capacidad y plan agregado
def _capacidad(serie: list, unidad: str, periodo: str):
    st.markdown("##### Estrategias de capacidad")
    mx = max(serie) if serie else 0.0
    a, b, c = st.columns(3)
    c0 = a.number_input(f"Capacidad inicial ({unidad} por {periodo})", min_value=0.0, value=float(round(serie[0], 1)) if serie else 0.0, key="dem_cap0")
    q = b.number_input(f"Tamaño del bloque de expansión ({unidad} por {periodo})", min_value=0.0, value=float(round(0.1 * mx, 1)) or 1.0, key="dem_bloque")
    ad = int(c.number_input("Períodos de adelanto", min_value=0, max_value=24, value=1, step=1, key="dem_adelanto"))
    x, y, z = st.columns(3)
    cc = x.number_input(f"Costo de la capacidad (US$ por {unidad} y {periodo})", min_value=0.0, value=20.0, key="dem_costo_cap",
                        help="Supuesto didáctico: costo fijo de tener capacidad instalada (depreciación, personal, mantención)")
    ce = y.number_input("Costo de cada expansión (US$ por bloque)", min_value=0.0, value=20000.0, step=1000.0, key="dem_costo_exp",
                        help="Supuesto didáctico: ingeniería, montaje y puesta en marcha de un bloque")
    mg = z.number_input(f"Margen perdido (US$ por {unidad} no atendida)", min_value=0.0, value=300.0, key="dem_margen",
                        help="Supuesto didáctico: margen de contribución de la venta perdida")
    r = M.estrategias_capacidad(serie, c0, q or None, ad, cc, ce, mg)
    E = r["estrategias"]
    filas = [dict(n=v["nombre"], cf=v["capacidad_final"], bl=v["bloques"], fa=v["faltante_total"], oc=v["ocioso_total"], ut=v["utilizacion"],
                  ns=v["nivel_servicio"], co=v["costo_total"]) for v in E.values()]
    C.mostrar_tabla(filas, [("n", "Estrategia", "txt", 0), ("cf", f"Capacidad final ({unidad})", "num", 1), ("bl", "Bloques", "num", 0),
                            ("fa", f"No atendido ({unidad})", "num", 1), ("oc", f"Capacidad ociosa ({unidad})", "num", 1),
                            ("ut", "Utilización", "pct", 1), ("ns", "Nivel de servicio", "pct", 1), ("co", "Costo total (US$)", "mm", 0)])
    _linea({"Demanda": serie, **{v["nombre"].split(" (")[0]: v["capacidad"] for v in E.values()}}, len(serie), periodo.capitalize(),
           f"{unidad} por {periodo}")
    mejor = min(E, key=lambda k: E[k]["costo_total"])
    st.caption(C.esc(f"Con estos costos la estrategia de menor costo es «{E[mejor]['nombre']}». Adelantarse no deja demanda sin atender "
                     "pero tiene capacidad ociosa; rezagarse usa bien la capacidad pero pierde ventas; seguir queda entre ambas."))


def _plan(serie: list, unidad: str, periodo: str):
    st.markdown("##### Plan agregado con inventario")
    a, b, c, d = st.columns(4)
    i0 = a.number_input(f"Inventario inicial ({unidad})", min_value=0.0, value=0.0, key="dem_inv0")
    cm = b.number_input(f"Mantener inventario (US$ por {unidad} y {periodo})", min_value=0.0, value=15.0, key="dem_c_mant",
                        help="Supuesto didáctico: costo de capital, bodega y seguros del producto guardado")
    cc = c.number_input(f"Cambiar la tasa (US$ por {unidad} de cambio)", min_value=0.0, value=40.0, key="dem_c_cambio",
                        help="Supuesto didáctico: contratar, despedir, horas extra o encender y apagar líneas")
    cf = d.number_input(f"Faltante (US$ por {unidad})", min_value=0.0, value=300.0, key="dem_c_falta",
                        help="Supuesto didáctico: margen de la venta perdida")
    cap = st.number_input(f"Capacidad máxima de producción ({unidad} por {periodo}; 0 = sin límite)", min_value=0.0, value=0.0, key="dem_cap_max")
    r = M.plan_agregado(serie, i0, cm, cc, cf, cap or None)
    filas = [dict(n=v["nombre"], t=v["tasa_max"], im=v["inventario_medio"], ix=v["inventario_max"], ca=v["cambios"], fa=v["faltante_total"],
                  cm=v["costo_mantener"], cc=v["costo_cambio"], cf=v["costo_faltante"], ct=v["costo_total"]) for v in r["planes"].values()]
    C.mostrar_tabla(filas, [("n", "Plan", "txt", 0), ("t", f"Tasa máxima ({unidad})", "num", 1), ("im", "Inventario medio", "num", 1),
                            ("ix", "Inventario máximo", "num", 1), ("ca", "Cambios de tasa", "num", 1), ("fa", "Faltante", "num", 1),
                            ("cm", "Mantener (US$)", "mm", 0), ("cc", "Cambios (US$)", "mm", 0), ("cf", "Faltante (US$)", "mm", 0),
                            ("ct", "Total (US$)", "mm", 0)])
    N, P = r["planes"]["nivelacion"], r["planes"]["persecucion"]
    _linea({"Demanda": serie, "Producción nivelada": N["produccion"], "Inventario nivelado": N["inventario"], "Producción persecución": P["produccion"]},
           len(serie), periodo.capitalize(), f"{unidad} por {periodo}")
    st.caption(C.esc(f"Plan de menor costo: «{r['planes'][r['mejor']]['nombre']}». La nivelación acumula inventario antes del peak; la "
                     "persecución no guarda inventario pero cambia la tasa en cada período."))


# ------------------------------------------------------------------ llevar al desafío
def _rubro_planta() -> str:
    try:
        r = C.planta().rubro
    except Exception:
        return "todos"
    return r if r in RUBROS else "todos"


def _llevar(res: dict, pron: dict | None):
    ss = st.session_state
    st.markdown("##### Llevar la serie al desafío")
    opciones = ["serie"] + (["pronostico"] if pron and pron.get("pronostico") else [])
    usar = st.radio("Qué serie llevar", opciones, format_func=lambda k: "Serie del perfil" if k == "serie" else "Pronóstico del método elegido",
                    horizontal=True, key="dem_usar") if len(opciones) > 1 else "serie"
    if st.button("Llevar la serie al desafío", type="primary", key="dem_llevar", width="stretch",
                 help="Reemplaza la demanda del desafío en curso (o arma uno con el rubro de la planta). La planta no cambia."):
        r = dict(res)
        if usar == "pronostico":
            r["extra"] = dict(res["extra"], pronostico=list(pron["pronostico"]), nombre_metodo=pron.get("nombre", ""))
        try:
            ss["desafio"] = M.estado_desafio(r, ss.get("desafio"), usar, nombre=ss.get("des_nombre", "") or "",
                                             tratamiento=ss.get("des_trato", "") or "", rubro=_rubro_planta())
        except ValueError as e:
            st.error(f"No se pudo llevar la serie al desafío: {e}")
            return
        d = ss["desafio"]
        st.success(C.esc(f"Listo: el desafío «{d['titulo']}» tiene ahora {len(d['demanda'])} períodos de demanda en {d['unidad']} por "
                         f"{d['periodo']} (perfil {res['nombre']}). Riesgo económico la usa en el Montecarlo."))
    en_curso = ss.get("desafio")
    if en_curso:
        st.caption(C.esc(f"Desafío en curso: «{en_curso['titulo']}», {len(en_curso.get('demanda') or [])} períodos en {en_curso.get('unidad')} por "
                         f"{en_curso.get('periodo')}" + (f", perfil {en_curso['perfil_demanda']}." if en_curso.get("perfil_demanda") else ".")))


def _supuestos(res: dict):
    with st.expander("Parámetros y fuentes del perfil"):
        C.mostrar_tabla([dict(n=s["nombre"], v=C.fmt(s["valor"], 4).rstrip("0").rstrip(",") if isinstance(s["valor"], float) else str(s["valor"]),
                              u=s["unidad"], f=s["fuente"]) for s in res["supuestos"]],
                        [("n", "Parámetro", "txt", 0), ("v", "Valor", "cen", 0), ("u", "Unidad", "txt", 0), ("f", "Fuente", "txt", 0)])


# ------------------------------------------------------------------ PAT 138: tomate, distribución de la llegada
def _tomate():
    from pat_sim.catalogos import plantas_tomate as PT
    ss = st.session_state
    from .p_desafio import cursiva, cursiva_plana
    ids = list(PT.IDS_MODELOS); tams = list(PT.IDS_TAMANOS); dists = list(M.IDS_DISTRIBUCIONES)
    ss.pop("dem_tom_variante", None)                      # PAT 139 (14-11): la lista vieja de 10 tipos de planta ya no existe
    for k, ops in (("dem_tom_modelo", ids), ("dem_tom_tamano", tams), ("dem_tom_dist", dists)):
        if ss.get(k) is not None and ss.get(k) not in ops:
            ss.pop(k, None)
    t = C.tomate_sesion() or (PT.BASE, M.DISTRIBUCION_DEFECTO)
    try:                                                  # el desafío puede traer una id vieja de PAT 138 o la compuesta «modelo|tamano»
        m0, t0 = PT.separar_id(t[0])
    except KeyError:
        m0, t0 = PT.MODELO_BASE, PT.TAMANO_BASE
    a, b = st.columns(2)
    m = a.radio("Modelo de planta de tomate", ids, index=ids.index(m0), format_func=lambda k: cursiva(PT.MODELOS[k]["nombre"]),
                key="dem_tom_modelo")
    d = b.selectbox("Distribución de la llegada", dists, index=dists.index(t[1]), format_func=lambda k: cursiva_plana(M.DISTRIBUCIONES[k]["nombre"]),
                    key="dem_tom_dist")
    tam = b.radio("Tamaño de la demanda", tams, index=tams.index(t0), format_func=lambda k: PT.TAMANOS[k]["nombre"],
                  key="dem_tom_tamano", horizontal=True)
    v = PT.id_compuesta(m, tam)                           # PAT 139 (14-11): modelo × tamaño; la serie usa la id compuesta
    P = M.DISTRIBUCIONES[d]
    st.markdown(cursiva(C.esc(f"**Lógica:** {LOGICA['agricola']}. **{P['nombre']}** ({P['forma']}). {P['explicacion']}")))
    cambios = {}
    with st.expander("Parámetros de la distribución", expanded=False):
        cols = st.columns(3)
        for i, (k, q) in enumerate(P["parametros"].items()):
            x = float(q["valor"])
            val = cols[i % 3].number_input(f"{q['nombre']} ({q['significado']})", min_value=0.0, value=x, step=0.01 if x < 1 else 0.5,
                                           key=f"dem_tom_{d}_{k}", help=q["fuente"])
            if val != x:
                cambios[k] = val
    c1, c2, c3 = st.columns(3)
    semilla = int(c1.number_input("Semilla de los números aleatorios", min_value=0, max_value=10 ** 6, value=M.SEMILLA_DEFECTO, step=1,
                                  key="dem_tom_semilla"))
    cv = c2.number_input("Variación diaria de la cosecha (cv)", min_value=0.0, max_value=1.0, value=0.10, step=0.01, key="dem_tom_cv",
                         help="Supuesto: variación diaria por clima y logística (gamma de media 1); la serie se reescala al total de la temporada")
    cap0 = PT.capacidad_media_t_h(v) * 1.5
    cap = c3.number_input("Capacidad de recepción (t/h; 0 = sin límite)", min_value=0.0, value=float(round(cap0, 1)), key=f"dem_tom_cap_{v}",
                          help="Supuesto: 1,5 veces la llegada media de la temporada, para ver cuánto se pierde con los peaks")
    try:
        res = M.llegada_tomate(v, d, semilla, cambios, cv, cap or None)
    except ValueError as e:
        st.error(f"Revise los parámetros: {e}")
        return
    st.markdown("##### Serie de llegada de tomate")
    _barras(res)
    _estadisticas(res)
    # PAT 140: sin la línea «Pico, percentil 95 y media en t/h»: esas cifras están en la tabla de capacidad de recepción de abajo
    # y las horas por día y los días, en la tabla de parámetros y fuentes
    _agricola(res, None, {}, lambda k: M.llegada_tomate(v, d, semilla, cambios, cv, k, perdida_1pct=False)["extra"])
    st.markdown("##### Llevar la serie al desafío")
    if st.button("Llevar la serie al desafío", type="primary", key="dem_llevar", width="stretch",
                 help="El desafío pasa a ser esta planta de tomate con esta llegada. La planta de la sesión no cambia."):
        ss["desafio"] = M.desafio_tomate(res, ss.get("des_nombre", "") or "")
        st.success(C.esc(f"Listo: el desafío «{ss['desafio']['titulo']}» tiene ahora {len(res['serie'])} días de llegada de tomate. "
                         "Riesgo económico la usa en el Montecarlo y Planta ficticia la ofrece para armar la planta."))
    _supuestos(res)


def mostrar():
    st.subheader("Demanda")
    C.ayuda(AYUDA, "Perfiles de demanda: oferta agrícola y mercado")
    origen = st.radio("Origen de la demanda", ["perfiles", "tomate"], horizontal=True, key="dem_origen",
                      format_func=lambda k: {"perfiles": "Perfiles de demanda (10)", "tomate": "Tomate: distribución de llegada (10 × 10 × 3)"}[k])
    if origen == "tomate":
        _tomate()
        return
    ids = list(M.PERFILES)
    pid = st.selectbox("Perfil de demanda", ids, format_func=lambda k: M.PERFILES[k]["nombre"], key="dem_perfil")
    P = M.PERFILES[pid]
    st.markdown(C.esc(f"**Lógica:** {LOGICA[P['logica']]}. {P['descripcion']}"))
    params = _parametros(pid)
    semilla = int(st.number_input("Semilla de los números aleatorios", min_value=0, max_value=10 ** 6, value=M.SEMILLA_DEFECTO, step=1,
                                  key="dem_semilla"))
    try:
        res = M.generar(pid, params, semilla)
    except ValueError as e:
        st.error(f"Revise los parámetros: {e}")
        return
    st.markdown("##### Serie de demanda")
    _barras(res)
    _estadisticas(res)
    pron = None
    if res["logica"] == "agricola":
        _agricola(res, pid, params)
    elif res["logica"] == "mixta":
        _mixta(res)
        _capacidad(res["serie"], res["unidad"], res["periodo"])
    else:
        pron = _pronostico(res)
        base = pron["pronostico"] if pron and pron.get("pronostico") else res["serie"]
        if pron:
            st.caption("Las estrategias de capacidad y el plan agregado usan el pronóstico: la capacidad se decide para la demanda futura.")
        if sum(base) > 0:
            _capacidad(base, res["unidad"], res["periodo"])
            _plan(base, res["unidad"], res["periodo"])
        else:
            st.info("El pronóstico es cero en todo el horizonte: no hay capacidad que planificar.")
    _llevar(res, pron)
    _supuestos(res)
