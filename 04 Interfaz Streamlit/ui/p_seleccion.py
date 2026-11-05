"""Pantalla Selección de equipos comerciales (PAT 135, tarea T14, 05-11-2026).

Paso 2 a 4 del proceso iterativo del profesor Torres (correo del 04-11-2026): después del diseño teórico se eligen equipos
comerciales (un equipo más grande o varios en paralelo que sumen al menos la capacidad), cada uno con su MTBF y MTTR; con la
disponibilidad resultante se vuelve al flujo para la teoría de restricciones y el costo de ineficiencia, que dice si conviene
una redundancia. Motor: pat_sim/motor/seleccion.py; catálogo: tabla catalogo_comercial del mantenedor."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import seleccion as S
from pat_sim.datos import mantenedor as M
from . import comun as C

AYUDA = """
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
supera el costo, se recomienda la redundancia. La alternativa recomendada es la de menor costo anual total.

**Para qué sirve.** Pasa del equipo ideal del tamaño justo a equipos que se pueden comprar, y muestra cuánto cuesta la falta de
disponibilidad y cuándo se paga una unidad de reserva.

**Por qué.** No hay equipos del tamaño exacto, cada equipo real falla y se repara, y una etapa con varias unidades en paralelo
sigue produciendo cuando falla una. Al aplicar la selección, Diseño (teoría de restricciones), Línea (MTBF y MTTR), Riesgo
económico y Costeo (unidades y redundancia) usan lo elegido. El balance de materia y energía no cambia.

**Supuestos.** El catálogo de partida no viene de fabricantes: tamaños, MTBF, MTTR y precios son Supuesto con su justificación
(columnas de fuente); el profesor los reemplaza en el Mantenedor. Fallas independientes entre unidades y sin pulmones entre etapas.
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


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("Selección de equipos comerciales")
    with st.expander("?  Cómo se hace, para qué y por qué"):
        st.markdown(C.esc(AYUDA))
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
    r = S.seleccionar(pl, _catalogo(), E, des, f_inst=float(f_inst))
    P = r["parametros"]
    st.caption(C.esc(f"Horas de operación: {C.fmt(P['horas'], 0)} h/año ({P['fuente_horas']}). Tasa {C.pct(P['tasa'])} y "
                     f"{C.fmt(P['anios'], 0)} años de Economía. Dólar ${C.fmt(P['dolar'], 2)}. Fracción de ociosidad "
                     f"{C.fmt(P['frac_ocioso'], 2)} (Supuesto)."))
    for x in r["avisos"]:
        st.warning(x)
    etapas = [e for e in r["etapas"] if e["alternativas"]]
    if not etapas:
        st.warning("El catálogo comercial no tiene modelos para estos equipos. Agréguelos en el Mantenedor (pestaña Catálogo comercial).")
        return

    # ------------------------------------------------ elección por equipo
    st.markdown("#### Alternativas y elección por equipo")
    elegidas = {}
    cols = st.columns(2)
    for i, e in enumerate(etapas):
        alts = e["alternativas"]
        act = S.elegida_actual(e)
        defecto = alts.index(act) if act in alts else alts.index(e["recomendada"])
        with cols[i % 2]:
            j = st.selectbox(f"{e['equipo']} · {e['nombre']} (requiere {_cap(e['requerida'], e['unidad'])})", list(range(len(alts))),
                             index=defecto, key=f"sel_alt_{pl.rubro}_{e['equipo']}",
                             format_func=lambda j, alts=alts, rec=e["recomendada"]: alts[j]["etiqueta"] + ("  (recomendada)" if alts[j] is rec else ""))
        elegidas[e["equipo"]] = alts[j if isinstance(j, int) and 0 <= j < len(alts) else defecto]
    filas = []
    for e in etapas:
        a = elegidas[e["equipo"]]
        filas.append(dict(eq=f"{e['equipo']} · {e['nombre']}", req=_cap(e["requerida"], e["unidad"]), modelo=a["modelo"], n=a["n"], k=a["k"],
                          inst=_cap(a["instalada"], a["unidad"]), au=a["A_unidad"], ae=a["A_etapa"], inv=a["inversion_clp"] / 1e6,
                          an=a["anual_clp"] / 1e6, inef=a["ineficiencia_clp"] / 1e6, tot=a["total_clp"] / 1e6,
                          f=a["categoria"] + (" (genérico en t/h)" if a["generico"] else "")))
    C.mostrar_tabla(filas, [("eq", "Equipo", "txt", 0), ("req", "Capacidad requerida", "cen", 0), ("modelo", "Modelo elegido", "txt", 0),
                            ("n", "Unidades (n)", "num", 0), ("k", "Necesarias (k)", "num", 0), ("inst", "Capacidad instalada", "cen", 0),
                            ("au", "Disponibilidad de una unidad", "pct", 2), ("ae", "Disponibilidad de la etapa (k de n)", "pct", 2),
                            ("inv", "Inversión instalada (MM$)", "mm", 1), ("an", "Anualidad (MM$/año)", "mm", 1),
                            ("inef", "Ineficiencia (MM$/año)", "mm", 1), ("tot", "Costo anual total (MM$/año)", "mm", 1), ("f", "Categoría", "txt", 0)])
    with st.expander("Todas las alternativas de cada equipo"):
        for e in etapas:
            st.markdown(C.esc(f"**{e['equipo']} · {e['nombre']}**: requiere {_cap(e['requerida'], e['unidad'])} "
                              f"({C.fmt(e['carga_t_h'], 2)} t/h de carga)"))
            C.mostrar_tabla([dict(et=a["etiqueta"], inst=_cap(a["instalada"], a["unidad"]), mtbf=a["mtbf_h"], mttr=a["mttr_h"], ae=a["A_etapa"],
                                  ce=a["cap_esperada_t_h"], pu=a["precio_unitario_usd"], an=a["anual_clp"] / 1e6, inef=a["ineficiencia_clp"] / 1e6,
                                  tot=a["total_clp"] / 1e6) for a in e["alternativas"]],
                            [("et", "Alternativa", "txt", 0), ("inst", "Capacidad instalada", "cen", 0), ("mtbf", "MTBF (h)", "num", 0),
                             ("mttr", "MTTR (h)", "num", 1), ("ae", "Disponibilidad de la etapa", "pct", 2),
                             ("ce", "Capacidad efectiva (t/h de carga)", "num", 2), ("pu", "Precio por unidad (US$)", "clp", 0),
                             ("an", "Anualidad (MM$/año)", "mm", 1), ("inef", "Ineficiencia (MM$/año)", "mm", 1),
                             ("tot", "Costo anual total (MM$/año)", "mm", 1)])
        st.caption(C.esc("Fuentes del catálogo: " + "; ".join(sorted({a["fuente_precio"] for e in etapas for a in e["alternativas"]})[:3])
                         + ". MTBF y MTTR: " + "; ".join(sorted({a["fuente_confiabilidad"] for e in etapas for a in e["alternativas"]})[:3]) + "."))
    a1, a2 = st.columns(2)
    if a1.button("Aplicar selección a la planta", type="primary", key="sel_aplicar"):
        n = S.aplicar(pl, elegidas)
        st.success(f"Selección aplicada a {n} equipos: Diseño (capacidad instalada), Línea (MTBF y MTTR) y Costeo (unidades) ya la usan. "
                   "El balance de materia y energía no cambia.")
    if any(e.get("actual") for e in etapas) and a2.button("Quitar la selección aplicada", key="sel_quitar"):
        S.quitar(pl)
        st.success("Selección quitada: la Línea vuelve a las fallas por tipo de equipo (Supuesto PAT 134); la capacidad queda como estaba.")

    # ------------------------------------------------ teoría de restricciones con la capacidad efectiva
    st.markdown("#### Teoría de restricciones con la capacidad efectiva")
    L = S.analizar_linea([elegidas[e["equipo"]] for e in etapas], P["plan"])
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Cuello de botella", L["cuello"] or "—")
    m2.metric("Disponibilidad de la línea en serie", C.pct(L["A_linea"], 1))
    m3.metric("Capacidad efectiva de la línea", f"{C.fmt(L['capacidad_linea'], 2)} t/h")
    m4.metric("Costo de ineficiencia total", C.esc("$" + C.fmt(L["ineficiencia_clp"] / 1e6, 1) + " MM/año"))
    _grafico(L)
    C.mostrar_tabla([dict(eq=f["equipo"], mod=f"{f['n']} × {f['modelo']}", ins=f["instalada_producto"], ef=f["efectiva_producto"], ae=f["A_etapa"],
                          u=f["utilizacion"], c="Sí" if f["cuello"] else "") for f in L["etapas"]],
                    [("eq", "Equipo", "txt", 0), ("mod", "Selección", "txt", 0), ("ins", "Instalada (t/h de producto)", "num", 2),
                     ("ef", "Efectiva esperada (t/h de producto)", "num", 2), ("ae", "Disponibilidad de la etapa", "pct", 2),
                     ("u", "Utilización con la demanda", "pct", 1), ("c", "Cuello de botella", "txt", 0)])

    # ------------------------------------------------ ineficiencia contra redundancia
    st.markdown("#### Costo de ineficiencia contra costo de redundancia")
    filas = []
    for e in etapas:
        d = e["redundancia"]
        if not d:
            continue
        filas.append(dict(eq=f"{e['equipo']} · {e['nombre']}", mod=d["modelo"], nn=f"{d['n']} → {d['n_red']}", a0=d["A_sin"], a1=d["A_con"],
                          ah=d["ahorro_clp"] / 1e6, co=d["costo_clp"] / 1e6, ne=d["neto_clp"] / 1e6,
                          rec="Agregar una unidad de reserva" if d["recomendar"] else "No conviene"))
    C.mostrar_tabla(filas, [("eq", "Equipo", "txt", 0), ("mod", "Modelo de menor costo", "txt", 0), ("nn", "Unidades", "cen", 0),
                            ("a0", "Disponibilidad sin reserva", "pct", 2), ("a1", "Disponibilidad con reserva", "pct", 2),
                            ("ah", "Ahorro de ineficiencia (MM$/año)", "mm", 1), ("co", "Costo anualizado de la unidad (MM$/año)", "mm", 1),
                            ("ne", "Beneficio neto (MM$/año)", "mm", 1), ("rec", "Recomendación", "txt", 0)])
    st.caption(C.esc(f"Margen {C.clp(P['margen'], 0)} por t de producto ({f_mg if float(mg) == float(mg0) else 'valor ingresado'}). "
                     "Ahorro = ineficiencia sin reserva − ineficiencia con reserva; se recomienda la reserva cuando el ahorro supera "
                     "el costo anualizado de la unidad adicional."))
