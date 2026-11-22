"""Pantalla Desafío (PAT 135, tarea T7.4; PAT 138, pedido de Jaime del 13-11-2026): la puerta de entrada del diseño asistido.

PAT 138: el desafío es siempre una planta de pasta de tomate. Se elige uno de los 10 tipos de planta de tomate
(catalogos/plantas_tomate.py, variantes de la planta basada en Agrozzi con distintas capacidades, °Brix, quiebre y evaporador)
y una de las 10 distribuciones de la llegada de tomate (motor/demanda.DISTRIBUCIONES: normal, log-normal, beta, media normal,
uniforme, normal truncada, triangular, Weibull, gamma y bimodal). La demanda del tomate es empujada por la producción agrícola:
la distribución da la forma de la llegada diaria a lo largo de la temporada y se escala al tomate de la temporada del tipo de
planta. «Armar la planta ideal automáticamente» llama a motor/sintesis.armar_planta con la variante y la serie (percentil 95 y
factor de servicio); «Partir en blanco» deja la planta vacía con la misma demanda. El desafío queda en
st.session_state["desafio"] con tipo_planta «tomate», variante_tomate y distribucion_tomate, para Planta ficticia, Planta real,
Equipos auxiliares, Demanda, Riesgo económico y el Montecarlo. Los desafíos del profesor siguen en la tabla del Mantenedor,
pero ya no se eligen aquí.

PAT 139: si el docente le asignó al estudiante un desafío de tomate (pantalla Docente, st.session_state.asignacion_docente con
familia «tomate»), el tipo de planta y la distribución quedan fijados en los selectores, con el curso a la vista.

PAT 139 (14-11-2026, comentarios del profesor Torres, punto 1): la pantalla se ordena en dos mitades. A la izquierda, la planta: el
«Modelo de planta», uno de 10 que se distinguen por los °Brix de la pasta y su proceso (quiebre *hot break* o *cold break*,
evaporador con o sin termocompresión y número de efectos), sin tamaño. A la derecha, el «Perfil de la demanda» con dos listas: la
«Distribución de la llegada» (10 formas) y el «Tamaño de la demanda» (chica, mediana y grande: tomate por temporada, días y horas
por día). Son 10 × 10 × 3 = 300 combinaciones; el modelo «agrozzi» con el tamaño «mediana» es la planta basada en Agrozzi. El
desafío guarda modelo_tomate, tamano_tomate, distribucion_tomate y variante_tomate compuesta («modelo|tamano»). Con una
asignación del docente, los tres quedan fijos. Las tres son listas desplegables (st.selectbox, PAT 139 del 14-11-2026; antes botones de opción) con las claves des_modelo, des_distribucion y des_tamano.

PAT 144 a (20-11-2026): arriba se elige el rubro del desafío (st.radio con la clave des_rubro): pasta de tomate, exactamente como
antes, o agar agar. El agar tiene las mismas tres listas, con las claves des_agar_modelo, des_agar_distribucion y des_agar_tamano:
10 modelos de proceso (catalogos/plantas_agar.py), las mismas 10 distribuciones de la llegada, ahora de alga seca, y 3 tamaños
(agar en polvo al año). La llegada es motor/demanda.llegada_agar y el desafío queda con tipo_planta y rubro «agar», modelo_agar,
tamano_agar, distribucion_agar y variante_agar («modelo|tamano»), sin las claves del tomate. La planta ideal y la planta en blanco
son las mismas funciones de motor/sintesis.py. Una asignación del docente de la familia «agar» deja fijos el rubro y las tres listas.
"""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos import plantas_tomate as PT, plantas_agar as PAG
from pat_sim.motor import desafio as D, demanda as DM
from . import comun as C

AYUDA = """
**Cómo se usa**

1. Escriba su nombre si quiere que el enunciado lo nombre (es opcional) y elija el rubro del desafío: pasta de tomate o agar agar.
2. A la izquierda elija el modelo de planta de tomate (10, que se distinguen por los °Brix de la pasta y su proceso: quiebre
   *hot break* o *cold break*, evaporador con o sin termocompresión y número de efectos). A la derecha, en el perfil de la demanda,
   elija la distribución de la llegada de tomate (10 formas) y el tamaño de la demanda (chica, mediana o grande: tomate por
   temporada, días y horas por día). En el agar agar, el modelo se distingue por las condiciones del proceso (NaOH y temperatura
   del baño alcalino, temperatura de extracción, agar en el extracto y en el gel prensado y rendimiento del alga), la llegada es
   de alga seca a lo largo del año de operación y el tamaño es el agar en polvo al año.
3. Presione «Armar la planta ideal automáticamente» para que el simulador arme la mejor planta con esa llegada (cadena de
   operaciones de la planta de tomate, dimensionamiento con el percentil 95 de la llegada y un factor de servicio, y mejor
   alternativa de cada equipo por costo y disponibilidad), o «Partir en blanco» para armarla usted.
4. Siga por la barra de etapas: Planta ficticia (Diseño), Planta real (equipos comerciales) y Equipos auxiliares; vea las
   restricciones (utilización y cuello de botella), decida si incorpora recuperación de calor y evalúe en Economía. Es un proceso
   iterativo: si la inversión es muy alta o la energía muy barata, quizás convenga sacar el recuperador.

**De dónde salen las cifras**

Los modelos son variantes de la planta basada en Agrozzi (30 °Brix, *hot break* y triple efecto con termocompresión) y el tamaño
mediano es su temporada (450.000 t en 76 días). Los modelos de agar agar son variantes del escenario base del agar (602 t de
agar al año en 330 días) con valores de los rangos de la literatura del proceso. Cada parámetro trae su fuente o la marca «Supuesto». Las formas de la
llegada son las de la lámina de distribuciones a priori; sus parámetros son supuestos didácticos, salvo la normal truncada, que es
la curva de Agrozzi. La serie queda en la sesión para el Montecarlo de la evaluación económica (exceso y déficit de capacidad
frente a la llegada). En la pantalla Demanda se ven las mismas distribuciones con el balance de lo procesado y lo perdido.

**Ojo**

Los dos botones reemplazan la planta que tiene abierta. Si la modificó, guarde antes una versión en Escenario.
"""

LOGICA_TXT = {
    "agricola": ("Demanda empujada por la producción agrícola",
                 "La planta debe procesar lo que se cosecha y llega a ella. Lo que no se procesa a tiempo se pierde, así que la "
                 "capacidad de recepción y de la línea se dimensiona con la llegada alta de la temporada (percentil 95), no con la media."),
    # PAT 144 a
    "agar": ("Demanda empujada por la llegada del alga seca",
             "La planta procesa el alga seca que entregan los proveedores en los días de operación. El alga seca se guarda en fardos y "
             "no se pierde por esperar en bodega; aun así, la planta ideal dimensiona la línea con la llegada alta (percentil 95), para "
             "no depender de la bodega y para que la forma de la llegada se note en el diseño."),
}
RUBROS = {"tomate": "Pasta de tomate", "agar": "Agar agar"}        # PAT 144 a


_INGLES = ("hot break", "cold break", "Hot break", "Cold break", "half-normal")


def cursiva(t: str) -> str:
    """Pone en cursiva (markdown) las palabras en inglés del texto, como pide el estilo del proyecto."""
    for w in _INGLES:
        t = t.replace(w, f"*{w}*")
    return t


def _italica(w: str) -> str:
    return "".join(chr(0x1D622 + ord(c) - 97) if "a" <= c <= "z" else chr(0x1D608 + ord(c) - 65) if "A" <= c <= "Z" else c for c in w)


def cursiva_plana(t: str) -> str:
    """Como cursiva(), pero para textos que Streamlit no interpreta como markdown (las opciones de una lista desplegable,
    st.selectbox): las palabras en inglés llevan letras itálicas Unicode (sans-serif cursiva), que se ven en cursiva sin markdown."""
    for w in _INGLES:
        t = t.replace(w, _italica(w))
    return t


def _modelo_tamano(modelo=None, tamano=None, variante=None, defecto=(PT.MODELO_BASE, PT.TAMANO_BASE)):
    """(modelo, tamaño) de un desafío o de una asignación: sus campos modelo_tomate y tamano_tomate o, si faltan (proyectos y
    asignaciones de PAT 138), los que salen de variante_tomate (id vieja, compuesta o un modelo solo). defecto si no hay nada válido."""
    try:
        if modelo in PT.MODELOS:
            return modelo, (tamano if tamano in PT.TAMANOS else PT.TAMANO_BASE)
        if variante:
            return PT.separar_id(variante, tamano if tamano in PT.TAMANOS else None)
    except KeyError:
        pass
    return defecto if defecto is not None else (None, None)


def _valida(clave: str, opciones: list):
    """Si el valor guardado en la sesión ya no es una opción, se quita (para que el selector no falle)."""
    if st.session_state.get(clave) is not None and st.session_state.get(clave) not in opciones:
        st.session_state.pop(clave, None)


def grafico_barras(filas: list, spec: dict, clave: str):
    """Gráfico de barras vega-lite que sí se redibuja cuando cambia la serie (PAT 139, 14-11-2026).
    Causa del error: con la misma especificación y la misma forma de datos (mismas columnas y mismo número de filas), el
    navegador de Streamlit 1.65 solo actualiza el conjunto de datos del gráfico ya montado y deja dibujadas las barras anteriores
    (el servidor sí manda la serie nueva): al cambiar la distribución de la llegada las métricas cambiaban y el gráfico no. Se
    corrige haciendo que la especificación cambie junto con la serie (una huella de los datos en «usermeta»): así el navegador
    vuelve a montar el gráfico completo."""
    import hashlib, json
    huella = hashlib.sha1(json.dumps([clave, filas], sort_keys=True, default=str).encode()).hexdigest()[:12]
    import pandas as pd
    st.vega_lite_chart(pd.DataFrame(filas), dict(spec, usermeta={"huella": huella}))


def _grafico(res: dict):
    filas = [{"Día": i + 1, "Llegada": v} for i, v in enumerate(res["serie_t_h"])]
    spec = {"mark": {"type": "bar", "color": "#1b7a5a", "tooltip": True},
            "encoding": {"x": {"field": "Día", "type": "ordinal", "title": "Día de la temporada",
                               "axis": {"labelAngle": 0, "labelOverlap": True}},
                         "y": {"field": "Llegada", "type": "quantitative", "title": "Llegada de tomate fresco (t/h)"}},
            "height": 280}
    try:
        grafico_barras(filas, spec, "des_grafico")
    except ImportError:                          # sin pandas: tabla en vez del gráfico
        C.mostrar_tabla(filas, [("Día", "Día", "num", 0), ("Llegada", "Llegada (t/h)", "num", 1)])


def _metricas(res: dict):
    m = DM.resumen_llegada(res)
    a, b, c, d = st.columns(4)
    a.metric("Tomate de la temporada", C.fmt(m["total_t"], 0) + " t")
    b.metric("Pico de la llegada", C.fmt(m["pico_t_h"], 1) + " t/h")
    c.metric("Percentil 95", C.fmt(m["p95_t_h"], 1) + " t/h")
    d.metric("Días de temporada", C.fmt(m["dias"], 0), f"{C.fmt(m['horas_dia'], 0)} h por día", delta_color="off")
    st.caption(C.esc(f"Media de la temporada: {C.fmt(m['media_t_h'], 1)} t/h. La capacidad de diseño de la planta ideal es el "
                     "percentil 95 por el factor de servicio (motor/sintesis.py)."))


def _parametros(res: dict):
    P = DM.DISTRIBUCIONES[res["distribucion"]]; v = PT.variante(res["variante"]); f = PT.fuentes(v["id"])
    with st.expander("Parámetros del modelo, del tamaño y de la distribución, con sus fuentes"):
        filas = [dict(n="Tomate de la temporada (tamaño)", v=C.fmt(v["temporada_t"], 0), u="t", f=f["temporada_t"]),
                 dict(n="Días de la temporada (tamaño)", v=C.fmt(v["dias"], 0), u="d", f=f["dias"]),
                 dict(n="Horas de proceso por día (tamaño)", v=C.fmt(v["horas_dia"], 0), u="h/d", f=f["horas_dia"]),
                 dict(n="°Brix de la pasta (modelo)", v=C.fmt(v["brix"], 0), u="°Brix", f=f["brix"]),
                 dict(n=PT.QUIEBRES[v["quiebre"]] + " (modelo)", v=C.fmt(v["T_quiebre"], 0), u="°C", f=f["quiebre"]),
                 dict(n="Evaporación (modelo)", v=PT.EVAPORADORES[v["evaporador"]], u="", f=f["evaporador"])]
        filas += [dict(n=f"{q['nombre']} ({q['significado']})", v=C.fmt(res["parametros"][k], 2), u=q["unidad"], f=q["fuente"])
                  for k, q in P["parametros"].items()]
        C.mostrar_tabla(filas, [("n", "Parámetro", "txt", 0), ("v", "Valor", "cen", 0), ("u", "Unidad", "txt", 0), ("f", "Fuente", "txt", 0)])
        st.caption("*Hot break* y *cold break*: calentamiento del tomate triturado para inactivar las enzimas, a alta o a baja temperatura. "
                   "TVR: termocompresión del vapor en el primer efecto del evaporador.")


def _armar(res: dict, nombre: str, auto: bool):
    from pat_sim.motor import sintesis as SI
    ss = st.session_state; v = res["variante"]
    ss["desafio"] = DM.desafio_tomate(res, nombre)
    for k in ("rc_dT", "rc_Tfin", "esc_rubro", "op", "op_compra"):
        ss.pop(k, None)
    try:
        if auto:
            with st.spinner("Armando la planta ideal con la llegada de tomate y las mejores alternativas…"):
                nueva = SI.armar_planta("tomate", res, economia=ss.get("economia"), desafio=ss["desafio"], variante=v)
            C.fijar_planta(nueva)
            inf = SI.informe(nueva)
            st.success(C.esc(f"Planta ideal armada: {len(nueva.equipos)} equipos, "
                             f"{C.fmt(inf['dimensionamiento']['materia_prima_diseno_t_h'], 1)} t/h de tomate de diseño y "
                             f"{C.fmt(inf['dimensionamiento']['materia_prima_operacion_t_h'], 1)} t/h en operación. "
                             "Revísela en Planta ficticia (Diseño) y siga con Planta real y Equipos auxiliares."))
        else:
            C.fijar_planta(SI.planta_en_blanco("tomate", res, ss["desafio"], variante=v))
            st.success(cursiva(C.esc(f"Carta en blanco: {PT.variante(v)['nombre']}. Vaya a Planta ficticia (Diseño) para poner los equipos.")))
    except Exception as e:
        st.error(f"No se pudo armar la planta: {e}")


def mostrar():
    ss = st.session_state
    st.subheader("Desafío")
    with st.expander("?  Cómo usar el desafío"):
        st.markdown(AYUDA)
    if "des_nombre" not in ss and ss.get("persona_nombre"):   # PAT 138: Streamlit borra el campo al cambiar de pantalla; vuelve el nombre
        ss["des_nombre"] = ss["persona_nombre"]
    nombre = st.text_input("Su nombre (opcional)", key="des_nombre", placeholder="Por ejemplo, Ana Pérez")   # PAT 138: sin trato ni nombre fijo
    ss["persona_nombre"] = " ".join(str(nombre or "").split())   # PAT 138: para «Proyecto de <nombre> <n>» aunque cambie de pantalla

    en_curso = ss.get("desafio") or {}
    # PAT 144 a: rubro del desafío (tomate, como hasta PAT 143, o agar agar); una asignación del docente lo deja fijo
    asig0 = ss.get("asignacion_docente") or {}
    r_fijo = asig0.get("familia") if asig0.get("familia") in RUBROS else None
    rubros = list(RUBROS)
    r0 = r_fijo or ("agar" if en_curso.get("tipo_planta") == "agar" else "tomate")
    if r_fijo and ss.get("des_rubro") != r_fijo:
        ss.pop("des_rubro", None)
    _valida("des_rubro", rubros)
    rubro = st.radio("Rubro del desafío", rubros, index=rubros.index(r0), key="des_rubro", horizontal=True, disabled=bool(r_fijo),
                     format_func=lambda k: RUBROS[k],
                     help="Pasta de tomate (planta basada en Agrozzi, llegada de tomate en la temporada) o agar agar (planta del escenario "
                          "base del agar, llegada de alga seca en el año de operación).")
    if rubro == "agar":
        _mostrar_agar(nombre, en_curso, asig0)
        _en_curso()
        return
    modelos = list(PT.IDS_MODELOS); tamanos = list(PT.IDS_TAMANOS); dists = list(DM.IDS_DISTRIBUCIONES)
    for k in ("des_variante",):                  # PAT 139 (14-11): la lista vieja de 10 tipos de planta ya no existe
        ss.pop(k, None)
    _valida("des_modelo", modelos); _valida("des_tamano", tamanos); _valida("des_distribucion", dists)
    m0, t0 = _modelo_tamano(en_curso.get("modelo_tomate"), en_curso.get("tamano_tomate"), en_curso.get("variante_tomate"))
    d0 = en_curso.get("distribucion_tomate") if en_curso.get("distribucion_tomate") in dists else DM.DISTRIBUCION_DEFECTO
    asig = ss.get("asignacion_docente") or {}
    am, at = _modelo_tamano(asig.get("modelo_tomate"), asig.get("tamano_tomate"), asig.get("variante_tomate"), None)
    fijo = asig.get("familia") == "tomate" and am is not None and asig.get("distribucion_tomate") in dists
    if fijo:                                     # PAT 139: la combinación la fijó el docente
        m0, t0, d0 = am, at, asig["distribucion_tomate"]
        if ss.get("des_modelo") != m0 or ss.get("des_tamano") != t0 or ss.get("des_distribucion") != d0:
            for k in ("des_modelo", "des_tamano", "des_distribucion"):
                ss.pop(k, None)
        st.info(C.esc(f"Su docente le asignó este desafío en el curso «{asig.get('curso', '')}» (usuario {asig.get('usuario', '')}): "
                      "el modelo de planta, la distribución de la llegada y el tamaño de la demanda quedan fijos."))
    izq, der = st.columns(2)
    with izq:
        st.markdown("##### Planta")
        m = st.selectbox("Modelo de planta", modelos, index=modelos.index(m0), key="des_modelo", disabled=fijo,
                     format_func=lambda k: cursiva_plana(PT.MODELOS[k]["nombre"]),
                     help="10 modelos de planta de pasta de tomate basados en Agrozzi, que se distinguen por los °Brix de la pasta y su "
                          "proceso: quiebre, evaporador con o sin termocompresión (TVR) y número de efectos. No incluyen el tamaño.")
    with der:
        st.markdown("##### Perfil de la demanda")
        d = st.selectbox("Distribución de la llegada", dists, index=dists.index(d0), key="des_distribucion", disabled=fijo,
                     format_func=lambda k: cursiva_plana(DM.DISTRIBUCIONES[k]["nombre"]),
                     help="Forma de la llegada diaria de tomate a lo largo de la temporada (curva de cosecha).")
        t = st.selectbox("Tamaño de la demanda", tamanos, index=tamanos.index(t0), key="des_tamano", disabled=fijo,
                     format_func=lambda k: PT.TAMANOS[k]["nombre"],
                     help="Tomate por temporada, días y horas de proceso por día: la planta chica recibe un tercio de la temporada de "
                          "Agrozzi, la mediana es Agrozzi y la grande el doble.")
        T = PT.tamano(t)
        st.caption(C.esc(T["descripcion"]))   # PAT 140: las cifras del tamaño (t, días, h por día y media) están en las métricas de abajo
    V = PT.variante(PT.id_compuesta(m, t)); P = DM.DISTRIBUCIONES[d]; M = PT.modelo(m)
    try:
        res = DM.llegada_tomate(modelo=m, tamano=t, dist_id=d)
    except ValueError as e:
        st.error(f"No se pudo generar la llegada de tomate: {e}")
        return
    enunciado = (f"diseñar esta planta. La llegada de tomate sigue una distribución "   # PAT 140: el nombre de la planta ya está en el título de arriba
                 f"{P['nombre'].lower()} a lo largo de {V['dias']} días.")
    st.markdown(f"#### {cursiva(C.esc(V['nombre']))}")
    st.markdown(cursiva(C.esc(f"**{D.saludo(nombre, '')}** {enunciado}")))
    st.caption(cursiva(C.esc(f"{M['descripcion']} {PT.QUIEBRES[M['quiebre']]} a {C.fmt(M['T_quiebre'], 0)} °C; "
                             f"{PT.EVAPORADORES[M['evaporador']].lower()}.")))
    tit, expl = LOGICA_TXT["agricola"]
    st.markdown(C.esc(f"**{tit}.** {expl}"))
    st.markdown(cursiva(C.esc(f"**Distribución {P['nombre'].lower()}** ({P['forma']}). {P['explicacion']}")))
    st.markdown("##### Llegada diaria de tomate")
    _grafico(res)
    _metricas(res)
    _parametros(res)
    b1, b2 = st.columns(2)
    auto = b1.button("Armar la planta ideal automáticamente", type="primary", key="des_auto", width="stretch",
                     help="El simulador arma la mejor planta de tomate para esta llegada: cadena de operaciones del tipo de planta, "
                          "dimensionamiento con la llegada (percentil 95 y factor de servicio) y la mejor alternativa de cada equipo "
                          "por costo anual y disponibilidad. Reemplaza la planta de la sesión.")
    blanco = b2.button("Partir en blanco", key="des_blanco", width="stretch",
                       help="La planta queda vacía, de este tipo de planta de tomate y con esta llegada; usted elige y conecta los "
                            "equipos en Planta ficticia.")
    if auto or blanco:
        _armar(res, nombre, auto)
    _en_curso()


def _en_curso():
    ss = st.session_state
    en_curso = ss.get("desafio")
    if en_curso:
        pl = C.planta()
        st.caption(C.esc(f"Desafío en curso: «{en_curso['titulo']}». Planta de la sesión: {pl.nombre}, con {len(pl.equipos)} equipo(s). "
                         f"La demanda ({len(en_curso['demanda'])} períodos, en {en_curso['unidad']} por {en_curso['periodo']}) "
                         "queda en la sesión para el Montecarlo."))


# ================================================================== PAT 144 a: desafío de agar agar
def _valores_agar(en_curso: dict, asig: dict) -> tuple:
    """(modelo, tamaño, distribución, fijo) del desafío de agar: los de la asignación del docente (familia «agar», fijos), los del
    desafío de agar en curso o los del escenario base con la llegada uniforme."""
    dists = list(DM.IDS_DISTRIBUCIONES)

    def _mt(m, t, v):
        try:
            if m in PAG.MODELOS:
                return m, (t if t in PAG.TAMANOS else PAG.TAMANO_BASE)
            if v:
                return PAG.separar_id(v)
        except KeyError:
            pass
        return None, None
    am, at = _mt(asig.get("modelo_agar"), asig.get("tamano_agar"), asig.get("variante_agar"))
    if asig.get("familia") == "agar" and am is not None and asig.get("distribucion_agar") in dists:
        return am, at, asig["distribucion_agar"], True
    m0, t0 = (None, None)
    if en_curso.get("tipo_planta") == "agar":
        m0, t0 = _mt(en_curso.get("modelo_agar"), en_curso.get("tamano_agar"), en_curso.get("variante_agar"))
    d0 = en_curso.get("distribucion_agar") if en_curso.get("distribucion_agar") in dists else DM.DISTRIBUCION_DEFECTO_AGAR
    return m0 or PAG.MODELO_BASE, t0 or PAG.TAMANO_BASE, d0, False


def _grafico_agar(res: dict):
    filas = [{"Día": i + 1, "Llegada": 1000 * v} for i, v in enumerate(res["serie_t_h"])]
    spec = {"mark": {"type": "bar", "color": "#1b7a5a", "tooltip": True},
            "encoding": {"x": {"field": "Día", "type": "ordinal", "title": "Día de operación",
                               "axis": {"labelAngle": 0, "labelOverlap": True}},
                         "y": {"field": "Llegada", "type": "quantitative", "title": "Llegada de alga seca (kg/h)"}},
            "height": 280}
    try:
        grafico_barras(filas, spec, "des_agar_grafico")
    except ImportError:                          # sin pandas: tabla en vez del gráfico
        C.mostrar_tabla(filas, [("Día", "Día", "num", 0), ("Llegada", "Llegada (kg/h)", "num", 0)])


def _metricas_agar(res: dict):
    m = DM.resumen_llegada(res)
    a, b, c, d = st.columns(4)
    a.metric("Alga seca del año", C.fmt(m["total_t"], 0) + " t")
    b.metric("Pico de la llegada", C.fmt(1000 * m["pico_t_h"], 0) + " kg/h")
    c.metric("Percentil 95", C.fmt(1000 * m["p95_t_h"], 0) + " kg/h")
    d.metric("Días de operación", C.fmt(m["dias"], 0), f"{C.fmt(m['horas_dia'], 0)} h por día", delta_color="off")
    st.caption(C.esc(f"Media del año: {C.fmt(1000 * m['media_t_h'], 0)} kg/h de alga seca. La capacidad de diseño de la planta ideal es "
                     "el percentil 95 por el factor de servicio (motor/sintesis.py)."))


def _parametros_agar(res: dict):
    P = DM.DISTRIBUCIONES[res["distribucion"]]; v = PAG.variante(res["variante"]); f = PAG.fuentes(v["id"])
    with st.expander("Parámetros del modelo, del tamaño y de la distribución, con sus fuentes"):
        filas = [dict(n="Agar en polvo al año (tamaño)", v=C.fmt(v["agar_t_ano"], 0), u="t", f=f["agar_t_ano"]),
                 dict(n="Días de operación al año (tamaño)", v=C.fmt(v["dias"], 0), u="d", f=f["dias"]),
                 dict(n="Horas de operación por día (tamaño)", v=C.fmt(v["horas_dia"], 0), u="h/d", f=f["horas_dia"]),
                 dict(n="Alga seca del año (modelo y tamaño)", v=C.fmt(v["alga_t_ano"], 0), u="t", f=f["alga_t_ano"])]
        dec = dict(naoh=1, Tbano=0, Text=0, cext=1, xgel=0, rend=2)
        filas += [dict(n=f"{PAG.ETIQUETAS[k]} (modelo)", v=C.fmt(v[k] * (100 if PAG.UNIDADES[k] == "%" else 1), dec[k]), u=PAG.UNIDADES[k],
                       f=f[k]) for k in PAG.ETIQUETAS]
        if "combinacion" in f:
            filas.append(dict(n="Combinación de valores (modelo)", v="", u="", f=f["combinacion"]))
        filas += [dict(n=DM.texto_agar(f"{q['nombre']} ({q['significado']})"), v=C.fmt(res["parametros"][k], 2), u=DM.texto_agar(q["unidad"]),
                       f=DM.SUPUESTO_FORMA_AGAR) for k, q in P["parametros"].items()]
        C.mostrar_tabla(filas, [("n", "Parámetro", "txt", 0), ("v", "Valor", "cen", 0), ("u", "Unidad", "txt", 0), ("f", "Fuente", "txt", 0)])


def _armar_agar(res: dict, nombre: str, auto: bool):
    from pat_sim.motor import sintesis as SI
    ss = st.session_state; v = res["variante"]
    ss["desafio"] = DM.desafio_agar(res, nombre)
    for k in ("rc_dT", "rc_Tfin", "esc_rubro", "op", "op_compra"):
        ss.pop(k, None)
    try:
        if auto:
            with st.spinner("Armando la planta ideal con la llegada de alga seca y las mejores alternativas…"):
                nueva = SI.armar_planta("agar", res, economia=ss.get("economia"), desafio=ss["desafio"], variante=v)
            C.fijar_planta(nueva)
            inf = SI.informe(nueva)
            st.success(C.esc(f"Planta ideal armada: {len(nueva.equipos)} equipos, "
                             f"{C.fmt(1000 * inf['dimensionamiento']['materia_prima_diseno_t_h'], 0)} kg/h de alga seca de diseño y "
                             f"{C.fmt(1000 * inf['dimensionamiento']['materia_prima_operacion_t_h'], 0)} kg/h en operación. "
                             "Revísela en Planta ficticia (Diseño) y siga con Planta real y Equipos auxiliares."))
        else:
            C.fijar_planta(SI.planta_en_blanco("agar", res, ss["desafio"], variante=v))
            st.success(C.esc(f"Carta en blanco: {PAG.variante(v)['nombre']}. Vaya a Planta ficticia (Diseño) para poner los equipos."))
    except Exception as e:
        st.error(f"No se pudo armar la planta: {e}")


def _mostrar_agar(nombre: str, en_curso: dict, asig: dict):
    ss = st.session_state
    modelos = list(PAG.IDS_MODELOS); tamanos = list(PAG.IDS_TAMANOS); dists = list(DM.IDS_DISTRIBUCIONES)
    _valida("des_agar_modelo", modelos); _valida("des_agar_tamano", tamanos); _valida("des_agar_distribucion", dists)
    m0, t0, d0, fijo = _valores_agar(en_curso, asig)
    if fijo:                                     # la combinación la fijó el docente
        if ss.get("des_agar_modelo") != m0 or ss.get("des_agar_tamano") != t0 or ss.get("des_agar_distribucion") != d0:
            for k in ("des_agar_modelo", "des_agar_tamano", "des_agar_distribucion"):
                ss.pop(k, None)
        st.info(C.esc(f"Su docente le asignó este desafío en el curso «{asig.get('curso', '')}» (usuario {asig.get('usuario', '')}): "
                      "el rubro, el modelo de planta, la distribución de la llegada y el tamaño de la demanda quedan fijos."))
    izq, der = st.columns(2)
    with izq:
        st.markdown("##### Planta")
        m = st.selectbox("Modelo de planta", modelos, index=modelos.index(m0), key="des_agar_modelo", disabled=fijo,
                         format_func=lambda k: PAG.MODELOS[k]["nombre"],
                         help="10 modelos de planta de agar agar en polvo basados en el escenario base del agar, que se distinguen por "
                              "las condiciones del proceso: NaOH y temperatura del baño alcalino, temperatura de extracción, agar en el "
                              "extracto y en el gel prensado y rendimiento del alga. No incluyen el tamaño.")
    with der:
        st.markdown("##### Perfil de la demanda")
        d = st.selectbox("Distribución de la llegada", dists, index=dists.index(d0), key="des_agar_distribucion", disabled=fijo,
                         format_func=lambda k: cursiva_plana(DM.nombre_distribucion(k, "agar")),
                         help="Forma de la llegada diaria de alga seca a lo largo del año de operación.")
        t = st.selectbox("Tamaño de la demanda", tamanos, index=tamanos.index(t0), key="des_agar_tamano", disabled=fijo,
                         format_func=lambda k: PAG.TAMANOS[k]["nombre"],
                         help="Agar en polvo al año, días y horas de operación por día: la planta chica produce cerca de un tercio del "
                              "escenario base, la mediana es el escenario base (602 t al año) y la grande cerca del doble.")
        st.caption(C.esc(PAG.tamano(t)["descripcion"]))
    V = PAG.variante(PAG.id_compuesta(m, t)); P = DM.DISTRIBUCIONES[d]; M = PAG.modelo(m)
    try:
        res = DM.llegada_agar(modelo=m, tamano=t, dist_id=d)
    except ValueError as e:
        st.error(f"No se pudo generar la llegada de alga seca: {e}")
        return
    dn = DM.nombre_distribucion(d, "agar")
    enunciado = (f"diseñar esta planta. La llegada de alga seca sigue una distribución {dn.lower()} a lo largo de "
                 f"{V['dias']} días de operación.")
    st.markdown(f"#### {C.esc(V['nombre'])}")
    st.markdown(C.esc(f"**{D.saludo(nombre, '')}** {enunciado}"))
    st.caption(C.esc(M["descripcion"]))
    tit, expl = LOGICA_TXT["agar"]
    st.markdown(C.esc(f"**{tit}.** {expl}"))
    st.markdown(cursiva(C.esc(f"**Distribución {dn.lower()}** ({DM.texto_agar(P['forma'])}). {DM.EXPLICACION_AGAR.get(d, P['explicacion'])}")))
    st.markdown("##### Llegada diaria de alga seca")
    _grafico_agar(res)
    _metricas_agar(res)
    _parametros_agar(res)
    b1, b2 = st.columns(2)
    auto = b1.button("Armar la planta ideal automáticamente", type="primary", key="des_auto", width="stretch",
                     help="El simulador arma la mejor planta de agar agar para esta llegada: cadena de operaciones del escenario base del "
                          "agar con sus equipos, dimensionamiento con la llegada (percentil 95 y factor de servicio) y la mejor alternativa "
                          "de cada equipo por costo anual y disponibilidad. Reemplaza la planta de la sesión.")
    blanco = b2.button("Partir en blanco", key="des_blanco", width="stretch",
                       help="La planta queda vacía, de este modelo de planta de agar agar y con esta llegada; usted elige y conecta los "
                            "equipos en Planta ficticia.")
    if auto or blanco:
        _armar_agar(res, nombre, auto)
