"""Pantalla Planta real: selección de equipos comerciales (PAT 135, tarea T14, 05-11-2026; PAT 136, tarea T23, 13-11-2026).

Paso 2 a 4 del proceso iterativo del profesor Torres (correo del 04-11-2026): después del diseño teórico se eligen equipos
comerciales (un equipo más grande o varios en paralelo que sumen al menos la capacidad), cada uno con su MTBF y MTTR; con la
disponibilidad resultante se vuelve al flujo para la teoría de restricciones y el costo de ineficiencia, que se compara con el costo
de una redundancia. Motor: pat_sim/motor/seleccion.py; catálogo: tabla catalogo_comercial del mantenedor.
PAT 136, T23 (punto 10b de los comentarios del 13-11-2026): es la segunda de las tres pantallas de construcción (Planta ficticia =
Diseño, Planta real = esta, Equipos auxiliares). Para cada equipo se buscan fichas de máquinas reales con Tavily (motor/fichas.py,
guardadas en la base con su precio y su URL) o, sin clave o sin red, se usa el catálogo Supuesto de 99 modelos; se muestran las
fichas y se comparan combinaciones (una máquina grande contra varias chicas) en costo, disponibilidad k de n, espacio y energía.
Claves de widgets con prefijo «sel_».
PAT 138 (13-11-2026): arriba de las tablas, el mismo lienzo de la Planta ficticia con la selección comercial de cada equipo
(ui/lienzo.mostrar_vista, vista «real», clave sel_lienzo, solo lectura).
PAT 139 (punto 6 de los comentarios del profesor Torres del 14-11-2026): elección en vivo. Arriba, el estado de Tavily, la disponibilidad
del sistema A_sist, la capacidad y el costo total C de la planta, y los botones «Generar automáticamente» (aplica la de menor C en cada etapa),
«Deshacer» y «Quitar las elecciones». En el lienzo, a la izquierda, los candidatos reales de cada etapa (motor/costo_total.py,
candidatos_etapa, ordenados por C) se arrastran y se sueltan sobre su etapa; los equipos se pueden mover y Ctrl+Z deshace. Debajo, el
mismo panel en Streamlit (etapa y candidato, se aplica al tiro). La pila de deshacer es la de la Planta ficticia (motor/eleccion_viva.py).
Lo de PAT 135 y 136 (fichas, combinaciones, teoría de restricciones y redundancia) sigue en «Análisis detallado»."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import seleccion as S, fichas as FI, costos, costo_total as CT, eleccion_viva as EV, tres_opciones as T3
from pat_sim.datos import mantenedor as M, precios_web as PW, genericos as GE
from . import comun as C, lienzo as LV, eleccion_comun as EC
from . import validacion as VAL     # PAT 143: validador del diseño y botón «Pista»

AYUDA = """
**Elección en vivo (PAT 139).** Cada etapa de la planta ficticia tiene su lista de candidatos reales (fabricante, modelo, unidades en
paralelo n, origen Tavily, Respaldo o Williams) con su costo anual total C = C_inv + C_op + C_inef, su disponibilidad A, la eficiencia η
en operación y la fuente. La planta real se arma de uno en uno y arriba se recalculan al tiro A_sist, la capacidad y el C total.
«Generar automáticamente» pone en todas las etapas la opción de menor C (un criterio entre varios, no un juicio sobre las demás). Cómo
elegir en el lienzo, la ficha comparativa y «Deshacer» se explican en el «?» bajo el lienzo.

**Cómo se hace.** Para cada equipo se toma la capacidad que pide el diseño teórico (la carga que resolvió el balance, en t/h,
kg/h de agua evaporada o kW según el tipo) y se buscan en el catálogo comercial los modelos de su tipo. Con cada modelo se
calcula cuántas unidades iguales en paralelo hacen falta para sumar al menos esa capacidad (k = ⌈requerida / capacidad del
modelo⌉; k = 1 es un equipo más grande) y la misma alternativa con una unidad más de reserva (n = k + 1). La disponibilidad de
una unidad es A = MTBF / (MTBF + MTTR); la de la etapa es la probabilidad de tener al menos k de las n unidades operando
(binomial); la de la línea en serie es el producto de las etapas. La capacidad efectiva esperada de la etapa es la instalada por
la disponibilidad, y el cuello de botella es la etapa de menor capacidad efectiva referida al producto (teoría de restricciones).

**Costo de ineficiencia.** Producción perdida esperada por año (la demanda menos la capacidad útil esperada) por el margen, más
la capacidad ociosa esperada por el margen y la fracción de ociosidad (0,25, Supuesto de Riesgo económico); la unidad de reserva
espera detenida y no suma ociosidad. Se compara con el costo anualizado de la unidad adicional (precio del catálogo actualizado
con el CEPCI, factor de instalación 2,5 y factor de recuperación de capital con la tasa y los años de Economía): si el ahorro
supera el costo, la tabla lo indica; usted decide si agrega la unidad de reserva.

**Para qué sirve.** Pasa del equipo ideal del tamaño justo a equipos que se pueden comprar, y muestra cuánto cuesta la falta de
disponibilidad y cuándo se paga una unidad de reserva.

**Por qué.** No hay equipos del tamaño exacto, cada equipo real falla y se repara, y una etapa con varias unidades en paralelo
sigue produciendo cuando falla una. Al aplicar la selección, Diseño (teoría de restricciones), Línea (MTBF y MTTR), Riesgo
económico y Costeo (unidades y redundancia) usan lo elegido. El balance de materia y energía no cambia.

**Fichas de máquinas reales (Tavily).** Para cada equipo se puede buscar en internet con Tavily (una búsqueda por equipo, plan
gratuito de 1.000 al mes). De cada página se leen, con expresiones regulares y sin inventar nada, el nombre, el fabricante, el modelo,
la capacidad, el precio con moneda, fecha y URL, el MTBF y el MTTR, la potencia, las dimensiones, el peso, el material, la garantía y
el plazo de entrega; lo que la página no dice queda en «sin dato» y cada dato muestra su fuente (URL, fecha y frase de la página). Las
fichas quedan guardadas en la base (con el historial de precios) y se pueden volver a usar sin internet. Sin clave de Tavily
(`TAVILY_API_KEY` en `.streamlit/secrets.toml` o en el entorno) o sin red, la pantalla avisa y usa el catálogo Supuesto de 99 modelos.

**Combinaciones de máquinas.** Con las fichas elegidas se arman las combinaciones de una máquina grande contra varias chicas (y cada
una con una unidad de reserva) y se comparan en cuatro criterios: costo (inversión instalada, anualidad e ineficiencia), disponibilidad
de la etapa (k de n), espacio (área de planta de las n unidades más un pasillo de 1,5 m por dimensión) y energía (potencia de las k
unidades en operación, con el precio de la electricidad de Economía). Las combinaciones que no cumplen el área máxima o la disponibilidad
mínima que se pidan quedan fuera de la lista. Sin dimensiones o potencia en la ficha, el espacio y la energía se escalan desde
el equipo de la planta (Supuesto declarado más abajo).

**Supuestos.** El catálogo de partida no viene de fabricantes: tamaños, MTBF, MTTR y precios son Supuesto con su justificación
(columnas de fuente); el docente los reemplaza en el Mantenedor. Fallas independientes entre unidades y sin pulmones entre etapas.
"""


def _catalogo():
    try:
        return M.catalogo_comercial(C.obtener_bd())
    except Exception:
        return M.semilla_catalogo_comercial()


def _desafio(pl):
    d = st.session_state.get("desafio")
    if isinstance(d, dict) and d.get("precios"):
        return d
    p = getattr(pl, "_p", None)
    return p.get("desafio") if isinstance(p, dict) else None


def _cap(v, u):
    return f"{C.fmt(v, 1 if v < 100 else 0)} {u}"


def _grafico(L):
    filas = [dict(Etapa=f["equipo"], Orden=i, Capacidad=f["efectiva_producto"], Tipo="Cuello de botella" if f["cuello"] else "Etapa")
             for i, f in enumerate(L["etapas"])]
    capas = [{"mark": {"type": "bar", "tooltip": True},
              "encoding": {"x": {"field": "Etapa", "type": "ordinal", "sort": None, "title": "Equipo"},
                           "y": {"field": "Capacidad", "type": "quantitative", "title": "Capacidad efectiva esperada (t/h de producto)"},
                           "color": {"field": "Tipo", "type": "nominal", "title": "",
                                     "scale": {"domain": ["Etapa", "Cuello de botella"], "range": ["#2a78d6", "#e34948"]}}}}]
    if L.get("plan"):
        capas.append({"mark": {"type": "rule", "color": "#1baf7a", "strokeWidth": 2, "strokeDash": [6, 4]},
                      "encoding": {"y": {"datum": L["plan"]}}})
    try:
        import pandas as pd
        st.vega_lite_chart(pd.DataFrame(filas), {"layer": capas, "height": 300})
    except Exception:
        C.mostrar_tabla(filas, [("Etapa", "Equipo", "txt", 0), ("Capacidad", "Capacidad efectiva (t/h de producto)", "num", 2),
                                ("Tipo", "Tipo", "txt", 0)])
    if L.get("plan"):
        st.caption(f"Línea verde: producción planificada del diseño teórico, {C.fmt(L['plan'], 2)} t/h de producto. "
                   "En rojo, el cuello de botella con la capacidad efectiva (instalada × disponibilidad).")



# ---------------------------------------------------------------- PAT 136, T23: fichas de máquinas
def _genericos():
    try:
        return GE.genericos(C.obtener_bd())
    except Exception:
        return None


def _clave_ficha(f: dict) -> str:
    return (f.get("url") or "") + "|" + str(FI.valor(f, "modelo") or FI.valor(f, "nombre") or "")


def _etiqueta_ficha(f: dict) -> str:
    fab = FI.valor(f, "fabricante")
    nom = str(FI.valor(f, "modelo") or FI.valor(f, "nombre") or "sin nombre")[:60]
    host = (f.get("url") or "").split("//")[-1].split("/")[0]
    return f"{(fab + ' ') if fab else ''}{nom}" + (f" · {host}" if host else f" · {f.get('origen', '')}")


def _pool(rubro: str, req: dict) -> list[dict]:
    """Fichas del equipo: las de la búsqueda de esta sesión y las guardadas antes en la base (categoría Internet)."""
    ss = st.session_state
    sesion = list(ss.get("sel_fichas", {}).get(rubro, {}).get(req["equipo"], []))
    base = []
    g = _genericos()
    if g is not None:
        try:
            base = [FI.ficha_desde_modelo(r) for r in g.listar_modelos(req["tipo"]) if r.get("categoria") == "Internet"]
        except Exception:
            base = []
    vistas = {(f.get("url") or FI.valor(f, "modelo")) for f in sesion}
    return sesion + [f for f in base if (f.get("url") or FI.valor(f, "modelo")) not in vistas]


def _usadas(rubro: str, req: dict, pool: list[dict]) -> list[dict]:
    claves = [_clave_ficha(f) for f in pool]
    sel = st.session_state.get(f"sel_usar_{rubro}_{req['equipo']}")
    if sel is None:
        return pool
    return [f for f, k in zip(pool, claves) if k in sel]


def _filas_fichas(rubro: str, reqs: list[dict], dolar: float) -> tuple[dict, set, dict]:
    """(filas por equipo, equipos que usan solo fichas, descartadas por equipo) con las fichas marcadas de cada equipo."""
    ss = st.session_state; filas, solo, malas = {}, set(), {}
    for r in reqs:
        usadas = _usadas(rubro, r, _pool(rubro, r))
        f, m = FI.filas_de_fichas(usadas, r["unidad"], r["tipo_catalogo"], dolar)
        malas[r["equipo"]] = m
        if f:
            filas[r["equipo"]] = f
            if ss.get(f"sel_solo_{rubro}_{r['equipo']}", True):
                solo.add(r["equipo"])
    return filas, solo, malas


def _buscar(pl, req: dict, clave: str, dolar: float) -> None:
    """Busca fichas con Tavily, las guarda en la base (con su precio) y deja las marcadas para la comparación."""
    ss = st.session_state
    with C.cargando(C.TXT_BUSCANDO_FICHAS):             # PAT 140: círculo que gira con el motivo
        r = FI.buscar_fichas(req["tipo"], req["requerida"], req["unidad"], clave, nombre=req["nombre"], dolar=dolar)
    for a in r["avisos"]:
        st.warning(a)
    if not r["fichas"]:
        return
    ss.setdefault("sel_fichas", {}).setdefault(pl.rubro, {})[req["equipo"]] = r["fichas"]
    g = _genericos(); n = 0
    if g is not None:
        for f in r["fichas"]:
            if FI.tiene(f, "capacidad") or FI.tiene(f, "precio"):
                try:
                    FI.guardar_ficha(g, f); n += 1
                except Exception as e:
                    st.warning(f"No se pudo guardar una ficha: {e}")
    pool = _pool(pl.rubro, req)
    ss[f"sel_usar_{pl.rubro}_{req['equipo']}"] = [_clave_ficha(f) for f in pool]
    st.success(f"Tavily devolvió {len(r['fichas'])} páginas ({n} con capacidad o precio quedaron guardadas en la base). Consulta: «{r['consulta']}»")


def _bloque_fichas(pl, reqs: list[dict], E: dict) -> dict | None:
    """Fichas del equipo elegido: búsqueda, tabla de resumen, ficha completa con la fuente de cada dato y fichas que entran a la
    comparación. Devuelve el requerimiento del equipo en estudio."""
    ss = st.session_state; rubro = pl.rubro
    st.markdown("#### Fichas de máquinas reales")
    clave = PW.obtener_clave()
    if clave:
        st.caption("Clave de Tavily encontrada: se pueden buscar fichas de máquinas en internet (una búsqueda por equipo).")
    else:
        st.info("Sin clave de Tavily (TAVILY_API_KEY en `.streamlit/secrets.toml` o en el entorno): se usa el catálogo Supuesto de 99 modelos "
                "y las fichas que ya estén guardadas en la base.")
    ids = [r["equipo"] for r in reqs]
    nombre = {r["equipo"]: f"{r['equipo']} · {r['nombre']}" for r in reqs}
    a, b = st.columns([3, 2])
    eid = a.selectbox("Equipo en estudio", ids, key=f"sel_eq_{rubro}", format_func=lambda k: nombre.get(k, k))
    req = next((r for r in reqs if r["equipo"] == eid), reqs[0])
    buscar = b.button("Buscar fichas en internet (Tavily)", key="sel_buscar_fichas", disabled=not clave,
                      help=f"Una búsqueda de Tavily para {req['nombre']} con {C.fmt(req['requerida'], 1)} {req['unidad']}. Cada ficha queda "
                           "guardada en la base con su precio, fecha y URL.")
    if buscar and clave:
        _buscar(pl, req, clave, float(E.get("dolar", costos.DOLAR)))
    pool = _pool(rubro, req)
    if not pool:
        st.caption(f"{req['equipo']} no tiene fichas de internet: la comparación usa el catálogo Supuesto.")
        return req
    claves = [_clave_ficha(f) for f in pool]
    kusar = f"sel_usar_{rubro}_{req['equipo']}"
    if kusar in ss:
        ss[kusar] = [k for k in ss[kusar] if k in claves]
    C.mostrar_tabla([dict(et=_etiqueta_ficha(f), org=f.get("origen", ""), cap=FI.texto_campo(f, "capacidad"), pr=FI.texto_campo(f, "precio"),
                          pot=FI.texto_campo(f, "potencia_kw"), mt=FI.texto_campo(f, "mtbf_h"), comp=FI.completitud(f),
                          fe=f.get("fecha", ""), url=f.get("url") or "sin URL") for f in pool],
                    [("et", "Ficha", "txt", 0), ("org", "Origen", "txt", 0), ("cap", "Capacidad", "cen", 0), ("pr", "Precio", "cen", 0),
                     ("pot", "Potencia", "cen", 0), ("mt", "MTBF", "cen", 0), ("comp", "Campos con dato", "pct", 0), ("fe", "Fecha", "cen", 0),
                     ("url", "URL", "txt", 0)])
    kw = dict(default=claves) if kusar not in ss else {}
    st.multiselect("Fichas que entran a la comparación", claves, key=kusar,
                   format_func=lambda k: _etiqueta_ficha(pool[claves.index(k)]) if k in claves else k, **kw)
    st.checkbox("Usar solo estas fichas (sin el catálogo Supuesto) para este equipo", value=True, key=f"sel_solo_{rubro}_{req['equipo']}",
                help="Si se desmarca, las máquinas del catálogo Supuesto de 99 modelos compiten con las fichas.")
    _, malas = FI.filas_de_fichas(_usadas(rubro, req, pool), req["unidad"], req["tipo_catalogo"], float(E.get("dolar", costos.DOLAR)))
    for m in malas:
        st.caption(C.esc(f"Descartada: {_etiqueta_ficha(m['ficha'])}, {m['motivo']}."))
    with st.expander(f"Ficha completa de cada máquina ({len(pool)}), con la fuente de cada dato"):
        for f in pool:
            st.markdown(C.esc(f"**{_etiqueta_ficha(f)}**: consultada el {f.get('fecha') or 'sin fecha'}; {f.get('url') or 'sin URL'}"))
            C.mostrar_tabla(FI.tabla_ficha(f), [("campo", "Campo", "txt", 0), ("valor", "Valor", "txt", 0), ("fuente", "Fuente", "txt", 0),
                                                ("cita", "Frase de la página", "txt", 0)])
    return req


def _txt(v, d=1, u=""):
    return "sin dato" if v is None else (C.fmt(v, d) + (" " + u if u else ""))


def _comparacion(pl, req: dict, filas: list[dict], P: dict, E: dict) -> None:
    """Combinaciones de máquinas del equipo en estudio: tabla, una grande contra varias chicas y aplicar (PAT 139b: sin recomendación)."""
    st.markdown(f"#### Combinaciones de máquinas para {req['equipo']} · {req['nombre']}")
    a, b, c = st.columns(3)
    amax = a.number_input("Área máxima de planta (m², 0 = sin límite)", 0.0, 1e6, 0.0, 10.0, key=f"sel_area_max_{pl.rubro}")
    dmin = b.number_input("Disponibilidad mínima de la etapa (%)", 0.0, 100.0, 0.0, 1.0, key=f"sel_disp_min_{pl.rubro}")
    kwh = c.number_input(C.esc("Precio de la electricidad ($/kWh)"), 0.0, 10000.0, float(S.PRECIO_KWH), 1.0, key="sel_kwh",
                         help=C.esc("Por defecto 84,004 $/kWh: " + C.FUENTE_PMM + " (clientes libres)."))
    ref = S.referencias_equipo(pl, req["equipo"])
    r = S.comparar_combinaciones(req, filas, P, ref, area_max=float(amax) or None, disp_min=float(dmin) / 100.0 or None, precio_kwh=float(kwh))
    for x in r["avisos"]:
        st.warning(x)
    alts = r["alternativas"]
    if not alts:
        return
    rec = r["recomendacion"]
    if rec["recomendada"] is None:
        st.warning(rec["motivo"])
    fa = [dict(et=x["etiqueta"], cat=x["categoria"], inst=_txt(x["instalada"], 1, x["unidad"]),
               ae=x["A_etapa"], inv=x["inversion_clp"] / 1e6, ar=_txt(x["area_total_m2"], 1, "m²"), pw=_txt(x["potencia_operando_kw"], 1, "kW"),
               en=x["costo_energia_clp"] / 1e6, an=x["anual_clp"] / 1e6, inef=x["ineficiencia_clp"] / 1e6, tot=x["total_con_energia_clp"] / 1e6)
          for x in alts]
    C.mostrar_tabla(fa, [("et", "Combinación", "txt", 0), ("cat", "Categoría", "txt", 0), ("inst", "Capacidad instalada", "cen", 0),
                         ("ae", "Disponibilidad de la etapa (k de n)", "pct", 2), ("inv", "Inversión instalada (M$)", "mm", 1),
                         ("ar", "Espacio: área de planta", "cen", 0), ("pw", "Energía: potencia en operación", "cen", 0),
                         ("en", "Energía (M$/año)", "mm", 1), ("an", "Anualidad (M$/año)", "mm", 1), ("inef", "Ineficiencia (M$/año)", "mm", 1),
                         ("tot", "Costo anual total (M$/año)", "mm", 1)])
    gc = r["grande_chicas"]
    if gc["grande"] and gc["chicas"]:
        st.markdown("##### Una máquina grande contra varias chicas")
        f_ = {"costo": lambda v: C.clp(v / 1e6, 1) + " M", "disp": lambda v: C.pct(v, 2), "area": lambda v: _txt(v, 1, "m²"),
              "energia": lambda v: _txt(v, 1, "kW"), "total": lambda v: C.clp(v / 1e6, 1) + " M"}
        nombre_g = {"grande": "La grande", "chicas": "Las chicas", "empate": "Empate", "sin dato": "Sin dato"}
        C.mostrar_tabla([dict(cr=x["criterio"], g=("sin dato" if x["grande"] is None else f_[x["clave"]](x["grande"])),
                              c=("sin dato" if x["chicas"] is None else f_[x["clave"]](x["chicas"])), w=nombre_g[x["ganador"]]) for x in gc["filas"]],
                        [("cr", "Criterio", "txt", 0), ("g", gc["grande"]["etiqueta"], "cen", 0), ("c", gc["chicas"]["etiqueta"], "cen", 0),
                         ("w", "Más favorable en este criterio", "cen", 0)])
    else:
        st.caption("Con estas fichas no hay a la vez una máquina que sola cubra la capacidad y varias chicas que la sumen: "
                   "agregue fichas de otros tamaños para compararlas.")
    om = r["mejores"]
    if om:
        nom = {"costo": "Menor inversión", "disponibilidad": "Mayor disponibilidad", "espacio": "Menor espacio", "energia": "Menor potencia en operación",
               "total": "Menor costo anual total"}
        C.mostrar_tabla([dict(c=nom[k], et=v["etiqueta"]) for k, v in om.items()], [("c", "Criterio", "txt", 0), ("et", "Combinación", "txt", 0)])
    st.caption(C.esc("Espacio y energía: " + "; ".join(sorted({(x.get("fuente_area") or "") for x in alts if x.get("fuente_area")})[:2])
                     + ". Potencia: " + "; ".join(sorted({(x.get("fuente_potencia") or "") for x in alts if x.get("fuente_potencia")})[:2]) + "."))
    j = st.selectbox("Combinación que se aplica a la planta", list(range(len(alts))), key=f"sel_comb_{pl.rubro}_{req['equipo']}",
                     index=0, format_func=lambda i: alts[i]["etiqueta"])
    alt = alts[j if isinstance(j, int) and 0 <= j < len(alts) else 0]
    st.button("Aplicar esta combinación a la planta", key="sel_aplicar_comb", on_click=_cb_elegir, args=(dict(alt, equipo=req["equipo"]),),
              help="Se aplica con un paso de «Deshacer», como una elección en el lienzo.")




# ---------------------------------------------------------------- PAT 139 (punto 6): elección en vivo
AYUDA_LIENZO = ("- A la izquierda del lienzo están las 3 opciones de instalación de cada etapa (PAT 140 c): 3 números de unidades n distintos, "
                "para cada n la de menor C y de esas las 3 de menor C, con el equipo real más cercano a la capacidad por unidad o, si no hay, la "
                "estimación de Williams. Cada una muestra C_inv, C_op, C_inef, C, A, η en operación y origen; se ordenan por la columna que elija, "
                "sin marcar ninguna. Arrástrela al lienzo: su etapa queda marcada con un borde punteado verde y las del mismo tipo con capacidad "
                "parecida (±20 %), con uno azul. Suéltela en un lugar libre y se aplica a su etapa, que queda donde la soltó con sus líneas; "
                "suéltela sobre otra etapa marcada y se aplica a esa. También puede hacer clic en ella. Se aplica al tiro y la etapa muestra "
                "el modelo, las unidades en paralelo y la disponibilidad de la etapa k de n. Las demás opciones están en la tabla «Todas las opciones».\n"
                "- Haga clic en una etapa del lienzo (o en «Ver ficha comparativa» bajo «Elegir por etapa») para ver su ficha comparativa: "
                "3 columnas (una por opción) con los resultados del equipo, la selección comercial, la eficiencia en operación, el costo "
                "total y un gráfico con la curva η/η_max de las 3, con el valor más conveniente de cada fila en verde suave y el botón "
                "«Elegir esta opción». Los equipos se pueden mover (cambio del *layout*).\n"
                "- «Deshacer» (o Ctrl+Z en el lienzo) vuelve atrás el último cambio, sea una elección, «Generar automáticamente» o un "
                "movimiento; se puede apretar varias veces. Es la misma pila de la Planta ficticia.\n"
                "- C = C_inv + C_op + C_inef en US$ por año (motor/costo_total.py); A de la etapa = k de n (binomial); A_sist = producto de "
                "las etapas elegidas (serie).")


def _firma(pl, E: dict, en_linea: bool):
    reqs = S.requerimientos(pl)
    f = (pl.rubro, tuple((r["equipo"], r["tipo"], round(r["requerida"], 6), r["unidad"], round(r["carga_t_h"], 6)) for r in reqs),
         tuple(sorted((k, str(v)) for k, v in (E or {}).items())), bool(en_linea))
    return f, reqs


def _cache_candidatos(pl, en_linea: bool) -> tuple[dict, list[str], dict]:
    """(candidatos, avisos, tres) de cada etapa, guardados en la sesión mientras la planta pida lo mismo: así Tavily no se consulta en
    cada clic. PAT 140 c: los candidatos son los de costo_total más las divisiones en 1, 2 y 3 unidades (motor/tres_opciones.py) y
    «tres» son las 3 opciones de distinto n de cada etapa."""
    ss = st.session_state
    E = dict(ss.get("economia") or {})
    firma, reqs = _firma(pl, E, en_linea)
    cache = ss.setdefault("sel_cand_cache", {})
    if firma not in cache or len(cache[firma]) < 3:
        cands, avisos, tres = {}, [], {}
        with C.cargando(C.TXT_BUSCANDO_EQUIPOS if en_linea else C.TXT_BUSCANDO_RESPALDO):    # PAT 140: círculo que gira con el motivo
            for r in reqs:
                try:
                    res = T3.candidatos_tres(pl, r["equipo"], E, en_linea)
                except Exception as e:                      # una etapa mala no bota la pantalla
                    res = dict(candidatos=[], tres=[], avisos=[f"no se pudieron calcular los candidatos ({e})."])
                cands[r["equipo"]] = res["candidatos"]
                tres[r["equipo"]] = res.get("tres") or []
                avisos += [f"{r['equipo']}: {a}" for a in res["avisos"]]
        cache.clear()
        cache[firma] = (cands, list(dict.fromkeys(avisos)), tres)
    return cache[firma]


def _candidatos(pl, en_linea: bool) -> tuple[dict, list[str]]:
    """Candidatos de cada etapa y avisos (Equipos auxiliares también lo usa)."""
    cands, avisos, _tres = _cache_candidatos(pl, en_linea)
    return cands, avisos


def _tres(pl, en_linea: bool) -> dict:
    """PAT 140 c: las 3 opciones de distinto n de cada etapa."""
    return _cache_candidatos(pl, en_linea)[2]


def _fichas(pl, tres: dict) -> dict:
    """PAT 140 c: ficha comparativa de las 3 opciones de cada etapa (resultados con la planta tal como está ahora)."""
    reqs = {r["equipo"]: r for r in S.requerimientos(pl)}
    tr = T3.restricciones(pl)
    out = {}
    for eid, ops in (tres or {}).items():
        try:
            out[eid] = T3.ficha_etapa(pl, eid, ops, reqs.get(eid), tr)
        except Exception:                                    # una ficha mala no bota la pantalla
            out[eid] = None
    return out


def _cb_elegir(c: dict):
    pl = C.planta()
    r = EV.aplicar_candidato(pl, EC.historial(pl), c)
    C.marcar_cambio(); EC.anotar("sel", r)


def _cb_generar():
    pl = C.planta()
    r = EV.generar_automaticamente(pl, EC.historial(pl), st.session_state.get("sel_cands_vigentes") or {})
    C.marcar_cambio(); EC.anotar("sel", r)


def _cb_deshacer():
    EC.anotar("sel", EC.deshacer(C.planta(), EV.deshacer))


def _cb_quitar():
    pl = C.planta()
    r = EV.quitar_todo(pl, EC.historial(pl))
    C.marcar_cambio(); EC.anotar("sel", r)


def _cb_elegir_select(eid: str):
    ss = st.session_state
    cid = ss.get(f"sel_viva_{eid}")
    pl = C.planta()
    if not cid:
        r = EV.con_historial(pl, EC.historial(pl), f"quitar el equipo elegido en {eid}", lambda p: S.quitar(p, [eid]))
        r["mensaje"] = f"{eid}: sin equipo elegido." if r["cambio"] else None
        C.marcar_cambio(); EC.anotar("sel", r)
        return
    c = EV.buscar_candidato(ss.get("sel_cands_vigentes") or {}, cid)
    if c is not None:
        _cb_elegir(c)


def _prec():
    """PAT 143: tabla de precedencia de la Planta ficticia, para que el validador revise también esa pantalla."""
    from . import p_diseno as PD
    return PD._precedencia()


def mostrar():
    pl = C.planta()
    st.subheader("Planta real: elección de equipos reales por costo total")
    st.caption("Segunda pantalla de construcción: Planta ficticia (Diseño), Planta real (esta pantalla) y Equipos auxiliares.")
    with st.expander("?  Cómo se hace, para qué y por qué"):
        st.markdown(C.esc(AYUDA))
    hay = _vivo(pl)
    if hay:
        with st.expander("Análisis detallado: fichas de Tavily, combinaciones, teoría de restricciones y redundancia"):
            _seleccion(pl)
    VAL.redibujar_si_cambio("real")          # PAT 143: la franja del proceso se pone al día si cambió el bloqueo


def _vivo(pl) -> bool:
    """Estado de Tavily, indicadores, botones, lienzo con los candidatos y panel de elección. Devuelve True si hay etapas."""
    ss = st.session_state
    EC.mostrar_aviso("sel")
    t = EC.mostrar_estado_tavily()
    if not pl.equipos:
        st.info("La planta está vacía: arme la planta en Planta ficticia (Diseño) y vuelva aquí para elegir sus equipos reales.")
        return False                 # PAT 140 d: sin lienzo vacío, que repetía «La planta está vacía»
    EC.resolver_si_hace_falta(pl)
    if not pl.resuelta:                   # PAT 143: si la Planta ficticia tiene errores, la advertencia lo explica
        res = VAL.revisar("real", precedencia=_prec())
        VAL.panel("real", res)
        if not res["errores"]:
            C.exigir_resuelta()
        return False
    hist = EC.historial(pl)
    cands, avisos = _candidatos(pl, t["en_linea"])
    # PAT 143: conexión libre (un candidato se aplica aunque no calce en la etapa donde se suelta; lo marca el validador)
    if EC.procesar_eventos(pl, "sel_lienzo", lambda ev: EV.procesar_evento(pl, hist, ev, cands, dict(ss.get("economia") or {}), libre=True)):
        if not C.exigir_resuelta():
            return False
        cands, avisos = _candidatos(pl, t["en_linea"])          # deshacer pudo devolver otra planta
    ss["sel_cands_vigentes"] = cands
    if not cands:
        st.info("La planta no tiene etapas con capacidad que elegir. Agregue equipos en Diseño y resuelva la planta; después vuelva aquí.")
        return False

    # ------------------------------------------------ botones e indicadores (se recalculan con cada elección)
    h = hist.resumen()
    b1, b2, b3, b4 = st.columns([1.3, 1, 1.1, 2.2])
    b1.button("Generar automáticamente", type="primary", key="sel_generar", on_click=_cb_generar,
              help="Aplica en cada etapa el candidato de menor costo anual total C (un solo paso de «Deshacer»). Es un criterio de "
                   "partida: revise A, η en operación, origen y fuente y cambie la elección si lo estima.")
    b2.button("Deshacer", key="sel_deshacer", on_click=_cb_deshacer, disabled=not h["deshacer"],
              help=(f"Deshace: {h['etiqueta_deshacer']} ({h['deshacer']} pasos guardados)." if h["deshacer"] else "No hay cambios que deshacer."))
    b3.button("Quitar las elecciones", key="sel_quitar_todo", on_click=_cb_quitar, help="La planta vuelve a los equipos teóricos (se puede deshacer).")
    b4.caption((f"Último cambio: {h['etiqueta_deshacer']}. " if h["deshacer"] else "") + f"{h['deshacer']} pasos para deshacer.")
    try:
        plan = S.parametros(pl, dict(ss.get("economia") or {}))["plan"]
    except Exception:
        plan = None
    est = EV.estado_planta_real(pl, cands, plan)
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Etapas elegidas", f"{est['n_elegidas']} de {est['n_etapas']}")
    m2.metric("Disponibilidad del sistema A_sist", C.pct(est["A_sist"], 2))
    m3.metric("Capacidad efectiva de la línea", "—" if est["capacidad_t_h"] is None else f"{C.fmt(est['capacidad_t_h'], 2)} t/h")
    m4.metric("C total de la planta", EC.usd(est["C"]))
    if est["n_elegidas"]:
        st.caption(C.esc(f"C_inv {EC.usd(est['C_inv'])}, C_op {EC.usd(est['C_op'])} y C_inef {EC.usd(est['C_inef'])} de las etapas elegidas. "
                         + (f"Cuello de botella: {est['cuello']}. " if est["cuello"] else "")
                         + "Capacidad en t/h de producto (instalada × disponibilidad, teoría de restricciones)."))
    else:
        st.caption("Todavía no hay equipos elegidos: arrastre un candidato al lienzo o use «Generar automáticamente».")

    # ------------------------------------------------ lienzo con la lista de candidatos para arrastrar
    # PAT 140 c: en el lienzo, las 3 opciones de distinto n de cada etapa y su ficha comparativa (al pinchar la etapa)
    tres = _tres(pl, t["en_linea"])
    fichas = _fichas(pl, tres)
    objetivos = []
    tipos = {r["equipo"]: f"{r.get('tipo_catalogo')}|{r.get('unidad')}" for r in S.requerimientos(pl)}   # PAT 140 g: misma clase = mismo tipo
    for f in est["filas"]:
        cs = cands.get(f["equipo"]) or []
        tr = tres.get(f["equipo"]) or cs[:3]
        objetivos.append(dict(id=f["equipo"], nombre=f"{f['equipo']} · {f['nombre']}", grupo="", nombre_largo="E" + EV.nombre_etapa(pl, f["equipo"])[1:],
                              clase=tipos.get(f["equipo"], f["equipo"]), requerida=f["requerida"], unidad=f["unidad"],
                              req=("requiere " + _cap(f["requerida"], f["unidad"])) if f["requerida"] else "",
                              dianas=[f["equipo"]], elegido=(f["elegido"] or {}).get("id"),
                              etq_elegido=(f["elegido"] or {}).get("etiqueta") or "", n_todos=len(cs),
                              candidatos=[EC.para_lienzo(c) for c in tr], comparacion=EC.para_lienzo_ficha(fichas.get(f["equipo"]))))
    res = VAL.revisar("real", precedencia=_prec())          # PAT 143: advertencia que no deja avanzar y botón «Pista»
    VAL.panel("real", res, avisos=True)
    LV.mostrar_eleccion("real", "sel_lienzo", dict(modo="real", titulo="Candidatos reales", objetivos=objetivos, moneda="US$/año"),
                        int(ss.get("sel_lienzo_seq", 0)), ss.get("sel_lienzo_mensajes", []), h, libre=True, validacion=res)
    C.ayuda(AYUDA_LIENZO)

    # ------------------------------------------------ el mismo panel en Streamlit (sin arrastrar)
    st.markdown("#### Elegir por etapa")
    ids = [f["equipo"] for f in est["filas"]]
    nombre = {f["equipo"]: f"{f['equipo']} · {f['nombre']}" for f in est["filas"]}
    if ss.get("sel_etapa_viva") not in ids:
        ss["sel_etapa_viva"] = ids[0]
    a, b = st.columns([1, 2])
    eid = a.selectbox("Etapa", ids, key="sel_etapa_viva", format_func=lambda k: nombre.get(k, k))
    fila = next(f for f in est["filas"] if f["equipo"] == eid)
    orden = a.selectbox("Ordenar los candidatos por", list(EC.ORDENES), key="sel_orden_cand", format_func=lambda k: EC.ORDENES[k][0],
                        help="Ordena la lista; ninguna posición significa que el candidato convenga más. Compare los valores y decida.")
    cs = EC.ordenar(cands.get(eid) or [], orden)
    el_id = (fila["elegido"] or {}).get("id")
    # PAT 140 d: la comparación de las 3 opciones vive solo en la ficha (lienzo o este botón), sin repetir la tabla en la página
    if fichas.get(eid) and tres.get(eid):
        EC.boton_ficha("sel_ficha", eid, nombre.get(eid, eid),
                       lambda ka: EC.mostrar_comparativa(fichas.get(eid), tres.get(eid) or [], el_id, _cb_elegir, "sel_cmp",
                                                         "Requiere " + _cap(fila["requerida"], fila["unidad"]), len(cs),
                                                         "la tabla «Todas las opciones» de la página", ka))
    st.markdown(f"##### Todas las opciones de {eid} ({len(cs)})")
    k = f"sel_viva_{eid}"
    ss[k] = (fila["elegido"] or {}).get("id") or ""            # muestra lo aplicado (también después de deshacer)
    etq = {c["id"]: f"{c['etiqueta']} · C = {C.fmt(c['C'], 0)} US$/año · A {C.pct(c.get('A'), 2)}" for c in cs}
    b.selectbox(f"Candidato para {eid} (se aplica al tiro)", [""] + [c["id"] for c in cs], key=k, on_change=_cb_elegir_select, args=(eid,),
                format_func=lambda x: "(sin elegir)" if not x else etq.get(x, x))
    if fila["aplicado_fuera"]:
        st.caption(f"{eid} tiene aplicada una combinación que no está en esta lista (de las fichas o de una sesión anterior).")
    C.mostrar_tabla(EC.filas_candidatos(cs, (fila["elegido"] or {}).get("id")), EC.COLS_CAND)
    if cs:
        st.caption(C.esc(f"Requiere {_cap(fila['requerida'], fila['unidad'])}."))

    st.markdown("#### Planta real armada")
    C.mostrar_tabla([dict(eq=f"{f['equipo']} · {f['nombre']}", req=_cap(f["requerida"], f["unidad"]) if f["requerida"] else "",
                          el=(f["elegido"] or {}).get("etiqueta") or "(sin elegir)", fab=(f["elegido"] or {}).get("fabricante") or "",
                          org=(f["elegido"] or {}).get("origen") or "", c=(f["elegido"] or {}).get("C"), a=(f["elegido"] or {}).get("A"),
                          eta=(f["elegido"] or {}).get("eta_operacion"))
                     for f in est["filas"]],
                    [("eq", "Etapa", "txt", 0), ("req", "Capacidad requerida", "cen", 0), ("el", "Equipo elegido", "txt", 0),
                     ("fab", "Fabricante", "txt", 0), ("org", "Origen", "cen", 0), ("c", "C (US$/año)", "mm", 0), ("a", "A de la etapa", "pct", 2),
                     ("eta", "η en operación", "pct", 1)])
    if avisos:
        with st.expander(f"Avisos de los candidatos ({len(avisos)})"):
            for x in avisos[:40]:
                st.caption(C.esc(x))
    return True


def _seleccion(pl):
    """Análisis detallado de PAT 135 y 136 con la elección vigente (la aplicada o, si la etapa no tiene, la de menor costo anual total)."""
    ss = st.session_state
    if not C.exigir_resuelta():
        return
    reqs = S.requerimientos(pl)
    if not reqs:
        st.info("La planta no tiene equipos con capacidad que seleccionar. Agregue equipos en Diseño y resuelva la planta; "
                "después vuelva aquí para elegir los modelos comerciales.")
        return
    E = dict(ss.get("economia") or {})
    des = _desafio(pl)
    mg0, f_mg = S.margen(pl.rubro, E, des)
    with st.container(border=True):
        a, b = st.columns(2)
        mg = a.number_input(C.esc("Margen de contribución ($/t de producto)"), 0.0, 1e9, float(mg0), 1000.0, key=f"sel_margen_{pl.rubro}",
                            help=C.esc(f"Fuente: {f_mg}."))
        f_inst = b.number_input("Factor de instalación", 1.0, 6.0, 2.5, 0.1, key="sel_finst",
                                help="Costo instalado / costo del equipo: 1/0,40, Danish Energy Agency (2026), hoja 2.a (Supuesto de motor/costos.py).")
    E["margen"] = float(mg)
    catalogo = _catalogo()
    req_sel = _bloque_fichas(pl, reqs, E)                                   # PAT 136, T23: fichas de máquinas reales
    f_fichas, solo, _malas = _filas_fichas(pl.rubro, reqs, float(E.get("dolar", costos.DOLAR)))
    r = S.seleccionar(pl, catalogo, E, des, f_inst=float(f_inst), fichas=f_fichas, solo_fichas=solo)
    P = r["parametros"]
    if req_sel is not None:
        _comparacion(pl, req_sel, S.filas_equipo(req_sel, catalogo, f_fichas.get(req_sel["equipo"]), req_sel["equipo"] in solo), P, E)
    st.caption(C.esc(f"Horas de operación: {C.fmt(P['horas'], 0)} h/año ({P['fuente_horas']}). Tasa {C.pct(P['tasa'])} y "
                     f"{C.fmt(P['anios'], 0)} años de Economía. Dólar ${C.fmt(P['dolar'], 2)}. Fracción de ociosidad "
                     f"{C.fmt(P['frac_ocioso'], 2)} (Supuesto)."))
    for x in r["avisos"]:
        st.warning(x)
    etapas = [e for e in r["etapas"] if e["alternativas"]]
    if not etapas:
        st.warning("El catálogo comercial no tiene modelos para estos equipos. Agréguelos en el Mantenedor (pestaña Catálogo comercial).")
        return

    # ------------------------------------------------ elección vigente por equipo (PAT 139: se elige arriba, en vivo)
    st.markdown("#### Alternativas del catálogo con la elección vigente")
    elegidas = {e["equipo"]: (S.elegida_actual(e) or e["recomendada"] or e["alternativas"][0]) for e in etapas}
    filas = []
    for e in etapas:
        a = elegidas[e["equipo"]]
        filas.append(dict(eq=f"{e['equipo']} · {e['nombre']}", req=_cap(e["requerida"], e["unidad"]), modelo=a["modelo"], n=a["n"], k=a["k"],
                          inst=_cap(a["instalada"], a["unidad"]), au=a["A_unidad"], ae=a["A_etapa"], inv=a["inversion_clp"] / 1e6,
                          an=a["anual_clp"] / 1e6, inef=a["ineficiencia_clp"] / 1e6, tot=a["total_clp"] / 1e6,
                          f=("Aplicada" if S.elegida_actual(e) else "Sin elegir: se muestra la de menor costo anual total") + " · " + a["categoria"]
                          + (" (genérico en t/h)" if a["generico"] else "")))
    C.mostrar_tabla(filas, [("eq", "Equipo", "txt", 0), ("req", "Capacidad requerida", "cen", 0), ("modelo", "Modelo", "txt", 0),
                            ("n", "Unidades (n)", "num", 0), ("k", "Necesarias (k)", "num", 0), ("inst", "Capacidad instalada", "cen", 0),
                            ("au", "Disponibilidad de una unidad", "pct", 2), ("ae", "Disponibilidad de la etapa (k de n)", "pct", 2),
                            ("inv", "Inversión instalada (M$)", "mm", 1), ("an", "Anualidad (M$/año)", "mm", 1),
                            ("inef", "Ineficiencia (M$/año)", "mm", 1), ("tot", "Costo anual total (M$/año)", "mm", 1), ("f", "Estado", "txt", 0)],
                   anchos={"eq": 170, "modelo": 150, "f": 280})
    with st.expander("Todas las alternativas de cada equipo"):
        for e in etapas:
            st.markdown(C.esc(f"**{e['equipo']} · {e['nombre']}**: requiere {_cap(e['requerida'], e['unidad'])} "
                              f"({C.fmt(e['carga_t_h'], 2)} t/h de carga)"))
            C.mostrar_tabla([dict(et=a["etiqueta"], inst=_cap(a["instalada"], a["unidad"]), mtbf=a["mtbf_h"], mttr=a["mttr_h"], ae=a["A_etapa"],
                                  ce=a["cap_esperada_t_h"], pu=a["precio_unitario_usd"], an=a["anual_clp"] / 1e6, inef=a["ineficiencia_clp"] / 1e6,
                                  tot=a["total_clp"] / 1e6) for a in e["alternativas"]],
                            [("et", "Alternativa", "txt", 0), ("inst", "Capacidad instalada", "cen", 0), ("mtbf", "MTBF (h)", "num", 0),
                             ("mttr", "MTTR (h)", "num", 1), ("ae", "Disponibilidad de la etapa", "pct", 2),
                             ("ce", "Capacidad efectiva (t/h de carga)", "num", 2), ("pu", "Precio por unidad (US$)", "mm", 0),
                             ("an", "Anualidad (M$/año)", "mm", 1), ("inef", "Ineficiencia (M$/año)", "mm", 1),
                             ("tot", "Costo anual total (M$/año)", "mm", 1)])
        # PAT 140 g (pedido de Jaime, 17-11-2026): sin la línea «Fuentes del catálogo … MTBF y MTTR …» bajo las alternativas

    # ------------------------------------------------ teoría de restricciones con la capacidad efectiva
    st.markdown("#### Teoría de restricciones con la capacidad efectiva")
    L = S.analizar_linea([elegidas[e["equipo"]] for e in etapas], P["plan"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cuello de botella", L["cuello"] or "—")
    m2.metric("Disponibilidad de la línea en serie", C.pct(L["A_linea"], 1))
    m3.metric("Capacidad efectiva esperada", f"{C.fmt(L['capacidad_linea'], 2)} t/h")
    m4.metric("Costo de ineficiencia total", C.esc("$" + C.fmt(L["ineficiencia_clp"] / 1e6, 1) + " M/año"))
    _grafico(L)
    C.mostrar_tabla([dict(eq=f["equipo"], mod=f"{f['n']} × {f['modelo']}", ins=f["instalada_producto"], ef=f["efectiva_producto"], ae=f["A_etapa"],
                          u=f["utilizacion"], c="Sí" if f["cuello"] else "") for f in L["etapas"]],
                    [("eq", "Equipo", "txt", 0), ("mod", "Selección", "txt", 0), ("ins", "Instalada (t/h de producto)", "num", 2),
                     ("ef", "Efectiva esperada (t/h de producto)", "num", 2), ("ae", "Disponibilidad de la etapa", "pct", 2),
                     ("u", "Utilización con la demanda", "pct", 1), ("c", "Cuello de botella", "cen", 0)])

    # ------------------------------------------------ ineficiencia contra redundancia
    st.markdown("#### Costo de ineficiencia contra costo de redundancia")
    filas = []
    for e in etapas:
        d = e["redundancia"]
        if not d:
            continue
        filas.append(dict(eq=f"{e['equipo']} · {e['nombre']}", mod=d["modelo"], nn=f"{d['n']} → {d['n_red']}", a0=d["A_sin"], a1=d["A_con"],
                          ah=d["ahorro_clp"] / 1e6, co=d["costo_clp"] / 1e6, ne=d["neto_clp"] / 1e6,
                          rec="Sí" if d["recomendar"] else "No"))
    C.mostrar_tabla(filas, [("eq", "Equipo", "txt", 0), ("mod", "Modelo de menor costo anual", "txt", 0), ("nn", "Unidades", "cen", 0),
                            ("a0", "Disponibilidad sin reserva", "pct", 2), ("a1", "Disponibilidad con reserva", "pct", 2),
                            ("ah", "Ahorro de ineficiencia (M$/año)", "mm", 1), ("co", "Costo anualizado de la unidad (M$/año)", "mm", 1),
                            ("ne", "Beneficio neto (M$/año)", "mm", 1), ("rec", "El ahorro supera el costo", "cen", 0)])
