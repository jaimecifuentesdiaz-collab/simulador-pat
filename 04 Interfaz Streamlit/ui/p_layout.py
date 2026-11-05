"""Pantalla Layout (PAT 135, tareas T7.3 y T15; indicación 3 de la reunión y correo del profesor Torres del 04-11-2026).

Dimensiones de los equipos, propuesta automática de layout (modelo de lenguaje si hay clave; si no, algoritmo propio tipo
CRAFT), plano en planta donde el usuario arrastra y rota los equipos (componente ui/componentes/layout_planta, mismo mecanismo
que el lienzo de Diseño), dos elevaciones y un corte con cotas, y longitud de cañería por corriente para el costeo.
Todo queda en st.session_state["layout"] = {"posiciones": {id: [x, y, rot]}, "longitudes_m": {corriente: m}, "dims": {...}}.
PAT 135 (T15): pestañas Plano, Elevaciones, Isométrica, Cañerías y Red eléctrica. Red eléctrica: sala eléctrica o CCM que se
arrastra en el plano, alimentadores por bandeja con corriente, sección y caída de tensión; resultado en
st.session_state["layout"]["cables_m"] ({alimentador: m}) y ["cables"] (detalle). Vista isométrica interactiva al estilo Anatomy
(motor/isometrico.py y el componente ui/componentes/isometrico).
"""
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from pat_sim.motor import layout as LY
from pat_sim.motor import isometrico as ISO
from . import comun as C

# PAT 135: componente bidireccional del plano (HTML propio, sin internet ni compilación)
RUTA = Path(__file__).resolve().parent / "componentes" / "layout_planta"
_componente = components.declare_component("layout_planta", path=str(RUTA))
CLAVE = "lay_plano"
# PAT 135 (T15): componente de la vista isométrica (HTML y JavaScript propios, sin internet)
RUTA_ISO = Path(__file__).resolve().parent / "componentes" / "isometrico"
_componente_iso = components.declare_component("isometrico_planta", path=str(RUTA_ISO))

AYUDA = """**Cómo se hace.** 1) Cada equipo recibe un largo, un ancho y un alto según su familia (símbolo ISO 10628) y su tamaño:
carga en t/h, calor en kW o potencia de la caldera en MW. Las dimensiones de partida son Supuesto (orden de catálogos de fabricantes)
y escalan por semejanza geométrica (lados con exponente 1/3 del tamaño; equipos extendidos como el secador de banda, 1/2). Se reemplazan
con las de un fabricante, escritas abajo o traídas de internet con Tavily cuando esté el cliente. 2) «Proponer layout»: con clave de un
modelo de lenguaje se le envía la lista de equipos y corrientes y devuelve las posiciones en JSON; sin clave, o si su propuesta superpone
equipos, se usa el algoritmo propio: intercambio por pares tipo CRAFT (Armour y Buffa, 1963), que minimiza Σ flujo × distancia
rectilínea entre equipos conectados, con el orden del proceso como relación más fuerte (Muther, 1973, Systematic Layout Planning). Los
equipos van en filas en zigzag con pasillos de 1,5 m (Supuesto), así no se superponen. 3) En el plano usted arrastra (ajuste a 0,5 m)
y rota (doble clic o R) los equipos; el plano marca en rojo los que quedan a menos del pasillo. 4) Con el *layout* se dibujan la elevación
frontal (desde el sur), la lateral izquierda (desde el oeste) y el corte A-A, con cotas. 5) Cada corriente se lleva en recorrido
ortogonal de puerto a puerto: horizontal |Δx| + |Δy|, subida y bajada al *rack* de cañerías (5 m, Supuesto) y 20 % por codos, válvulas y
liras (Supuesto); los transportadores de biomasa van sin *rack*.

**Para qué sirve.** Ubicar los equipos en planta, ver alturas y despejes, y obtener la longitud de cada cañería, que con el diámetro de la
red hidráulica alimenta el costeo de la planta (las longitudes quedan en la sesión para la evaluación económica).

**Por qué importa.** En la etapa de diseño solo se conocen los diámetros; el profesor Torres pidió sacar las longitudes del *layout*
(04-11-2026). Una cañería más larga cuesta más, pierde más calor y más carga, y eso cambia la inversión y el ahorro de la recuperación
de calor en la planta de tomate y en las de biomasa."""


def _clave_llm() -> str | None:
    """Clave del modelo de lenguaje: st.secrets o variable de entorno (nunca se muestra)."""
    try:
        k = st.secrets["ANTHROPIC_API_KEY"]
        if k and str(k).strip() and str(k).strip() != "...":
            return str(k).strip()
    except Exception:
        pass
    k = os.environ.get("ANTHROPIC_API_KEY")
    return k.strip() if k and k.strip() else None


AYUDA_ELEV = """**Cómo se hace.** Cada equipo se dibuja como un rectángulo de su largo (o ancho, según la rotación) por su alto. Elevación
frontal: observador al sur mirando al norte; lateral izquierda: observador al oeste mirando al este. Los equipos tapados por otro
más cercano van en contorno claro. El corte A-A pasa por el eje del equipo elegido en el plano: lo cortado va rayado. La línea naranja
es el *rack* de cañerías y la amarilla punteada, la bandeja eléctrica; los alimentadores bajan punteados a cada equipo y la sala
eléctrica (CCM) va en amarillo.

**Para qué sirve.** Revisar alturas, despejes bajo el *rack* y la bandeja, y el espacio vertical de los evaporadores o del secador.

**Por qué importa.** El profesor Torres pidió vistas de elevación del *layout* (04-11-2026); en ingeniería básica muestran si las
cañerías y los cables caben sin chocar con los equipos altos."""

AYUDA_ISO = """**Cómo se hace.** Proyección isométrica de 30° calculada al instante desde el *layout* (pat_sim/motor/isometrico.py): x al
este, y al norte, z hacia arriba; pantalla sx = (b − a)·cos 30° y sy = (a + b)·sen 30° − z, con (a, b) las coordenadas de la cámara.
Los equipos son sólidos: prismas para los rectangulares, cilindros verticales para estanques, evaporadores y columnas, y cilindros
horizontales sobre silletas para intercambiadores, secadores rotatorios y calderas. Cada sólido lleva el sombreado de cuatro tonos de
la skill Anatomy (superior, izquierda, derecha y contorno). Las cañerías son tubos con el color de su tipo de corriente (el mismo de la
leyenda de Diseño); suben al *rack* (vigas y postes grises) y bajan al equipo de destino. La bandeja eléctrica y los alimentadores van
en amarillo. El orden de dibujo es el algoritmo del pintor: lo más lejano primero, con un orden parcial entre las piezas que se
traslapan en pantalla. Botones: girar la cámara en cuatro orientaciones (sureste, noreste, noroeste y suroeste), *zoom* y arrastre;
al pasar el *mouse* por un equipo se resaltan sus cañerías y alimentadores y se muestran sus datos; clic para dejarlo fijo.

**Figuras de Anatomy.** Si en el Mantenedor, tabla de símbolos, hay un SVG con norma «ISO-ISOMETRICO» para el símbolo, el tipo o la
familia de un equipo (figuras hechas aparte con la skill Anatomy en Claude Code), esa figura reemplaza al sólido genérico.

**Para qué sirve y por qué importa.** El profesor Torres pidió vistas isométricas interactivas del *layout* definido (04-11-2026): se ve
de una vez la planta en tres dimensiones, con el recorrido de cañerías y cables, para revisar el diseño y presentarlo."""

AYUDA_CAN = """**Cómo se hace.** Cada corriente va de la boquilla de salida del origen a la de entrada del destino (o a la de servicio, en la
cara de atrás, si es vapor o calor). El recorrido es ortogonal: horizontal |Δx| + |Δy|, subida y bajada al *rack* (5 m, Supuesto) y un
porcentaje por codos, válvulas y liras (20 %, Supuesto). Los transportadores de biomasa van sin *rack*. El diámetro interno sale de la
red hidráulica por velocidad de diseño (motor/hidraulica.py), solo en líneas de líquido.

**Para qué sirve y por qué importa.** Las longitudes quedan en st.session_state["layout"]["longitudes_m"] y alimentan el costeo de
cañerías: en la etapa de diseño solo se conocen los diámetros y el largo sale del *layout*."""

AYUDA_ELEC = """**Cómo se hace.** 1) Cada equipo con potencia eléctrica (servicio de electricidad de su resultado, potencia en el punto de
operación de las bombas o parámetro de potencia) lleva un alimentador propio desde la sala eléctrica o CCM (centro de control de
motores); también las bombas de las líneas de líquido que no están dibujadas en el diagrama (P-1xx, las mismas del costeo). Si un
equipo no tiene potencia, no lleva alimentador. 2) La sala eléctrica (6 × 4 × 3,5 m, Supuesto) se propone en el punto libre más cercano
al centro de carga, el promedio de las posiciones ponderado por la potencia; usted la arrastra en el plano como un equipo más.
3) Recorrido ortogonal por bandeja a 4 m (Supuesto, 1 m bajo el *rack*): sube del CCM (2,3 m) a la bandeja, va según x y después según y
y baja a la caja de bornes (0,5 m), más 15 % por subidas, curvas y holgura (Supuesto). 4) Corriente trifásica I = P / (√3 · U · cos φ)
con U = 380 V y cos φ = 0,85 (Supuesto). 5) Sección: la menor cuya capacidad cubre el 125 % de la corriente (Supuesto), con una tabla
de cobre XLPE en bandeja del orden de IEC 60364-5-52, tabla B.52.12, método E (Supuesto, verificar con el fabricante); si no alcanza la
mayor sección se ponen conductores en paralelo. 6) Caída de tensión ΔU = √3 · I · L · (R cos φ + X sen φ), con R del cobre a 90 °C
(resistividad a 20 °C de IEC 60028) y X = 0,08 Ω/km (Supuesto); si pasa de 3 % (Supuesto) se sube la sección.

**Para qué sirve.** Dimensionar los alimentadores y obtener el largo de cable por alimentador, que queda en
st.session_state["layout"]["cables_m"] para el costeo, con el detalle en ["cables"].

**Por qué importa.** El profesor Torres pidió un *layout* preliminar con *piping* y alimentaciones eléctricas (04-11-2026). Los motores
grandes (compresores de los evaporadores MVR, molinos, peletizadoras) pesan en la inversión eléctrica y su ubicación respecto de la sala
eléctrica cambia el largo y la sección de los cables. Sobre 250 kW se avisa que en la práctica se alimentan en media tensión."""


def _estado(pl) -> dict:
    """Layout de la sesión; se reinicia si cambia la planta (otro rubro u otro escenario)."""
    ss = st.session_state
    firma = f"{pl.nombre}|{pl.rubro}"
    lay = ss.get("layout")
    if not isinstance(lay, dict) or lay.get("firma") != firma:
        lay = dict(firma=firma, posiciones={}, longitudes_m={}, dims={}, overrides={}, version=1, seq=0,
                   pasillo=LY.PASILLO_M, h_rack=LY.H_RACK_M, accesorios=LY.ACCESORIOS)
        ss["layout"] = lay
    # PAT 135 (T15): supuestos de la red eléctrica (se agregan también a un layout de una sesión anterior)
    for k, v in (("ccm", None), ("h_bandeja", LY.H_BANDEJA_M), ("holgura_cable", LY.HOLGURA_CABLE), ("tension", LY.TENSION_V),
                 ("fp", LY.FP), ("du_max", LY.DU_MAX_PCT), ("bombas_linea", True), ("cables_m", {}), ("cables", [])):
        lay.setdefault(k, v)
    return lay


def _aplicar_plano(lay: dict, valor) -> bool:
    """Toma del navegador las posiciones movidas o rotadas (solo de la versión vigente y con número de envío nuevo).
    PAT 135 (T15): la sala eléctrica viene con la clave CCM y va a lay["ccm"]."""
    if not isinstance(valor, dict) or valor.get("version") != lay.get("version"):
        return False
    s = int(valor.get("seq") or 0)
    if s <= int(lay.get("seq") or 0):
        return False
    pos = valor.get("posiciones") or {}
    for k, v in pos.items():
        if k in lay["posiciones"] or k == LY.ID_CCM:
            try:
                p = [float(v[0]), float(v[1]), int(round(float(v[2] if len(v) > 2 else 0) / 90)) % 4 * 90]
            except (TypeError, ValueError, IndexError):
                continue
            if k == LY.ID_CCM and k not in lay["posiciones"]:
                lay["ccm"] = p
            else:
                lay["posiciones"][k] = p
    lay["seq"] = s
    return True


def _datos_componente(pl, lay: dict, y_corte) -> dict:
    eqs = [dict(id=k, nombre=pl.equipos[k].nombre, largo=d["largo"], ancho=d["ancho"], alto=d["alto"]) for k, d in lay["dims"].items()]
    pos = dict(lay["posiciones"])
    red = lay.get("red") or {}
    if red.get("ccm") and LY.ID_CCM not in pos:          # PAT 135 (T15): la sala eléctrica se arrastra como un equipo más
        dc = red["ccm_dim"]
        eqs.append(dict(id=LY.ID_CCM, nombre="Sala eléctrica", largo=dc["largo"], ancho=dc["ancho"], alto=dc["alto"], electrico=True))
        pos[LY.ID_CCM] = red["ccm"]
    cables = [dict(id=c["id"], equipo=c["equipo"], ruta=[[p[0], p[1]] for p in c["ruta"]],
                   texto=f"{c['nombre']}, {C.fmt(c['P_kW'], 1)} kW, {c['conductor']}, {C.fmt(c['total'], 1)} m") for c in red.get("cables", [])]
    return dict(equipos=eqs, posiciones=pos, cables=cables,
                corrientes=[{k: f[k] for k in ("id", "origen", "destino", "tipo", "servicio")} for f in lay["filas"]],
                pasillo=lay["pasillo"], version=lay["version"], ultimo_seq=lay["seq"], y_corte=y_corte)


def _recalcular(pl, lay: dict) -> None:
    lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))


def _figuras() -> dict:
    """Figuras isométricas del mantenedor (norma ISO-ISOMETRICO); vacío si no hay base o mantenedor."""
    try:
        from pat_sim.datos import mantenedor as M
        return ISO.figuras_isometricas(M.mantenedor(C.obtener_bd()))
    except Exception:
        return {}


def _supuestos(lay: dict) -> None:
    with st.container(border=True):
        a, b, c, d = st.columns(4)
        lay["pasillo"] = float(a.number_input("Pasillo mínimo entre equipos (m)", 0.5, 5.0, float(lay["pasillo"]), 0.1, key="lay_pasillo",
                                              help="Supuesto: 1,5 m para tránsito y mantención"))
        lay["h_rack"] = float(b.number_input("Altura del rack de cañerías (m)", 2.5, 15.0, float(lay["h_rack"]), 0.5, key="lay_rack",
                                             help="Supuesto: 5 m deja paso a una grúa horquilla y a la mantención"))
        acc = c.number_input("Accesorios sobre el recorrido (%)", 0.0, 100.0, float(lay["accesorios"]) * 100, 5.0, key="lay_acc",
                             help="Supuesto: 20 % por codos, válvulas, liras de dilatación y desvíos")
        lay["accesorios"] = float(acc) / 100
        clave = _clave_llm()
        lay["_modelo"] = d.text_input("Modelo de lenguaje", os.environ.get("ANTHROPIC_MODEL", LY.MODELO_LLM), key="lay_modelo",
                                      help="Se usa solo si hay clave ANTHROPIC_API_KEY en .streamlit/secrets.toml o en el entorno")
        e1, e2, e3, e4, e5 = st.columns(5)                   # PAT 135 (T15): supuestos de la red eléctrica
        lay["tension"] = float(e1.number_input("Tensión entre fases (V)", 220.0, 1000.0, float(lay["tension"]), 10.0, key="lay_tension",
                                               help="Supuesto: 380 V trifásico 50 Hz, baja tensión industrial habitual en Chile"))
        lay["fp"] = float(e2.number_input("Factor de potencia", 0.5, 1.0, float(lay["fp"]), 0.01, key="lay_fp",
                                          help="Supuesto: 0,85, motores de inducción a plena carga sin compensación"))
        lay["h_bandeja"] = float(e3.number_input("Altura de la bandeja eléctrica (m)", 2.0, 15.0, float(lay["h_bandeja"]), 0.5, key="lay_bandeja",
                                                 help="Supuesto: 4 m, 1 m bajo el rack de cañerías"))
        hol = e4.number_input("Subidas y holgura del cable (%)", 0.0, 100.0, float(lay["holgura_cable"]) * 100, 5.0, key="lay_holgura",
                              help="Supuesto: 15 % por subidas a tableros, curvas de la bandeja y colas de conexión")
        lay["holgura_cable"] = float(hol) / 100
        lay["du_max"] = float(e5.number_input("Caída de tensión máxima (%)", 0.5, 10.0, float(lay["du_max"]), 0.5, key="lay_dumax",
                                              help="Supuesto: 3 % en el alimentador (criterio usual)"))
        lay["bombas_linea"] = bool(st.checkbox("Incluir las bombas de línea que no están en el diagrama (P-1xx del costeo)",
                                               bool(lay["bombas_linea"]), key="lay_bombas_linea"))
        st.caption(("Hay clave de modelo de lenguaje: «Proponer layout» le pide la propuesta y la revisa contra superposición." if clave else
                    "Sin clave de modelo de lenguaje: «Proponer layout» usa el algoritmo propio tipo CRAFT (Armour y Buffa, 1963)."))
        lay["_clave"] = clave


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("*Layout* de planta")
    with st.expander("? *Layout*: cómo se hace, para qué sirve y por qué importa"):
        st.markdown(AYUDA)
    if not pl.equipos:       # PAT 135: planta vacía (desafío en blanco)
        st.info("La planta está vacía: agregue equipos en Diseño.")
        return
    if not C.exigir_resuelta():
        return
    lay = _estado(pl)
    _supuestos(lay)
    clave, modelo = lay.pop("_clave", None), lay.pop("_modelo", None)

    b1, b2, b3, _ = st.columns([1, 1, 1.3, 2])
    proponer = b1.button("Proponer layout", key="lay_proponer", type="primary")
    volver = b2.button("Volver a la propuesta", key="lay_volver", disabled=not lay.get("propuesta"))
    ccm_auto = b3.button("Proponer posición del CCM", key="lay_ccm_auto",
                         help="Pone la sala eléctrica en el punto libre más cercano al centro de carga ponderado por potencia")

    # cambios del plano que llegan del navegador (antes de recalcular)
    _aplicar_plano(lay, ss.get(CLAVE))
    _recalcular(pl, lay)
    if proponer:
        r = LY.proponer_layout(pl, lay["dims"], lay["pasillo"], clave, modelo)
        lay["posiciones"] = {k: list(v) for k, v in r["posiciones"].items()}
        lay["propuesta"] = {k: list(v) for k, v in r["posiciones"].items()}
        lay["metodo"] = r["metodo"]; lay["version"] = int(lay["version"]) + 1; lay["ccm"] = None
        for av in r.get("avisos", []):
            st.warning(av)
        _recalcular(pl, lay)
    elif volver and lay.get("propuesta"):
        lay["posiciones"] = {k: list(v) for k, v in lay["propuesta"].items()}
        lay["version"] = int(lay["version"]) + 1; lay["ccm"] = None
        _recalcular(pl, lay)
    elif ccm_auto:
        lay["ccm"] = None; lay["version"] = int(lay["version"]) + 1
        _recalcular(pl, lay)

    red = lay["red"]
    m1, m2, m3, m4, m5 = st.columns(5)
    hs = [LY.huella(p, lay["dims"][k]) for k, p in lay["posiciones"].items()]
    largo_pl = max(h[2] for h in hs) + lay["pasillo"]; ancho_pl = max(h[3] for h in hs) + lay["pasillo"]
    m1.metric("Superficie de la planta", C.fmt(largo_pl * ancho_pl, 0) + " m²", f"{C.fmt(largo_pl, 1)} × {C.fmt(ancho_pl, 1)} m", delta_color="off")
    m2.metric("Σ flujo × distancia", C.fmt(lay["costo"], 0) + " t·m/h", lay.get("metodo", ""), delta_color="off")
    m3.metric("Cañerías y ductos", C.fmt(sum(f["total"] for f in lay["filas"] if f["medio"] in ("cañería", "ducto")), 1) + " m",
              f"{len(lay['filas'])} corrientes", delta_color="off")
    m4.metric("Cable de alimentadores", C.fmt(red["largo_total_m"], 1) + " m", f"{len(red['cables'])} alimentadores", delta_color="off")
    m5.metric("Equipos superpuestos", str(len(lay["superposiciones"])), "pares a menos del pasillo", delta_color="off")
    if lay["superposiciones"]:
        st.warning("Equipos a menos del pasillo: " + ", ".join(f"{a} con {b}" for a, b in lay["superposiciones"][:6]))

    ids = list(lay["dims"])
    alto = max(ids, key=lambda k: lay["dims"][k]["alto"]) if ids else None
    nombres = {k: e.nombre for k, e in pl.equipos.items()}
    t_plano, t_elev, t_iso, t_can, t_elec = st.tabs(["Plano", "Elevaciones", "Isométrica", "Cañerías", "Red eléctrica"])

    # ---------------------------------------------------------------- plano en planta
    with t_plano:
        eq_corte = st.selectbox("Plano de corte A-A por el eje del equipo", ids, index=ids.index(alto) if alto in ids else 0, key="lay_corte",
                                format_func=lambda k: f"{k} · {pl.equipos[k].nombre}")
        y_corte = float(lay["posiciones"][eq_corte][1]) if eq_corte in lay["posiciones"] else None
        valor = _componente(datos=_datos_componente(pl, lay, y_corte), key=CLAVE, default=None)
        if _aplicar_plano(lay, valor):
            _recalcular(pl, lay); red = lay["red"]
        st.download_button("Descargar el plano (SVG)", LY.plano_svg(lay["posiciones"], lay["dims"], lay["filas"], nombres, y_corte, red=red),
                           file_name="Layout_planta.svg", mime="image/svg+xml", key="lay_dl_plano")
        st.markdown("#### Dimensiones de los equipos")
        C.mostrar_tabla([dict(id=k, nombre=pl.equipos[k].nombre, tam=d["tamano"], u=d["unidad"], **d) for k, d in lay["dims"].items()],
                        [("id", "Equipo", "txt", 0), ("nombre", "Nombre", "txt", 0), ("familia", "Familia", "txt", 0), ("tam", "Tamaño", "num", 1),
                         ("u", "Unidad", "txt", 0), ("largo", "Largo (m)", "num", 1), ("ancho", "Ancho (m)", "num", 1), ("alto", "Alto (m)", "num", 1),
                         ("categoria", "Categoría", "txt", 0), ("fuente", "Fuente o justificación", "txt", 0)])
        with st.container(border=True):
            st.markdown("**Reemplazar las dimensiones de un equipo** (dato de fabricante o de internet)")
            e = st.selectbox("Equipo", ids, key="lay_ov_eq", format_func=lambda k: f"{k} · {pl.equipos[k].nombre}")
            dd = lay["dims"].get(e, {})
            x1, x2, x3 = st.columns(3)
            L = x1.number_input("Largo (m)", 0.1, 200.0, float(dd.get("largo", 1.0)), 0.1, key=f"lay_ov_L_{e}")
            W = x2.number_input("Ancho (m)", 0.1, 200.0, float(dd.get("ancho", 1.0)), 0.1, key=f"lay_ov_W_{e}")
            H = x3.number_input("Alto (m)", 0.1, 100.0, float(dd.get("alto", 1.0)), 0.1, key=f"lay_ov_H_{e}")
            fuente = st.text_input("Fuente (fabricante, modelo, página o enlace)", "", key=f"lay_ov_f_{e}")
            y1, y2, y3 = st.columns(3)
            if y1.button("Aplicar dimensiones", key="lay_ov_aplicar"):
                lay["overrides"][e] = dict(largo=L, ancho=W, alto=H, fuente=fuente or "Dimensión escrita por el usuario")
                _recalcular(pl, lay)
                st.success(f"Dimensiones de {e} actualizadas; revise el plano por superposiciones.")
            if y2.button("Buscar en internet", key="lay_ov_web", help="Usa el cliente de Tavily (pat_sim.datos.precios_web) si está instalado"):
                r = LY.buscar_dimensiones_web(pl.equipos[e])
                if r:
                    lay["overrides"][e] = r
                    _recalcular(pl, lay)
                    st.success(f"Dimensiones de {e} desde internet: {r.get('fuente', '')}")
                else:
                    st.info("No hay cliente de búsqueda en internet o no encontró dimensiones; se mantienen las del Supuesto.")
            if y3.button("Volver al Supuesto", key="lay_ov_quitar", disabled=e not in lay["overrides"]):
                lay["overrides"].pop(e, None)
                _recalcular(pl, lay)
    red = lay["red"]

    # ---------------------------------------------------------------- elevaciones y corte
    with t_elev:
        with st.expander("? Elevaciones y corte: cómo se hacen, para qué sirven y por qué importan"):
            st.markdown(AYUDA_ELEV)
        s1, s2, s3 = st.tabs(["Elevación frontal", "Elevación lateral izquierda", "Corte A-A"])
        svgs = [("frontal", LY.elevacion_svg(lay["posiciones"], lay["dims"], "frontal", lay["h_rack"], red)),
                ("lateral", LY.elevacion_svg(lay["posiciones"], lay["dims"], "lateral", lay["h_rack"], red)),
                ("corte", LY.corte_svg(lay["posiciones"], lay["dims"], y_corte, lay["h_rack"]))]
        for tab, (n, svg) in zip((s1, s2, s3), svgs):
            with tab:
                st.image(svg, width="stretch")
                st.download_button("Descargar (SVG)", svg, file_name=f"Layout_{n}.svg", mime="image/svg+xml", key=f"lay_dl_{n}")

    # ---------------------------------------------------------------- vista isométrica
    with t_iso:
        with st.expander("? Vista isométrica: cómo se hace, para qué sirve y por qué importa"):
            st.markdown(AYUDA_ISO)
        figuras = _figuras()
        codigos = {k: [getattr(e_, "simbolo", ""), getattr(e_, "tipo", ""), lay["dims"].get(k, {}).get("familia", "")] for k, e_ in pl.equipos.items()}
        vistas = ISO.vistas_isometricas(lay["posiciones"], lay["dims"], lay["filas"], red, h_rack=lay["h_rack"], nombres=nombres,
                                        codigos=codigos, figuras=figuras)
        info = ISO.datos_interaccion(lay["posiciones"], lay["dims"], lay["filas"], red, nombres)
        firma = f"{lay['version']}|{lay['seq']}|{red['ccm']}|{lay['h_rack']}|{lay['h_bandeja']}|{len(figuras)}|{sorted(lay['overrides'])}"
        _componente_iso(datos=dict(vistas=vistas, info=info, rot=0, alto=640, firma=firma), key="lay_iso", default=None)
        if figuras:
            st.caption(f"Figuras isométricas del Mantenedor en uso (norma {ISO.NORMA_FIGURAS}): {len(figuras)}.")
        o1, o2 = st.columns([2, 1])
        rot_dl = o1.selectbox("Orientación para descargar", [0, 90, 180, 270], key="lay_iso_rot", format_func=lambda r: ISO.VISTAS[r])
        o2.download_button("Descargar la vista isométrica (SVG)", vistas[str(rot_dl)], file_name=f"Layout_isometrica_{rot_dl}.svg",
                           mime="image/svg+xml", key="lay_dl_iso")

    # ---------------------------------------------------------------- cañerías
    with t_can:
        with st.expander("? Cañerías: cómo se miden, para qué sirven y por qué importan"):
            st.markdown(AYUDA_CAN)
        C.mostrar_tabla([dict(f, tramo=f"{f['origen']} → {f['destino']}") for f in lay["filas"]],
                        [("id", "Corriente", "txt", 0), ("tramo", "Tramo", "txt", 0), ("tipo", "Fluido", "txt", 0), ("medio", "Medio", "txt", 0),
                         ("D_mm", "Diámetro interno (mm)", "num", 0), ("horizontal", "Horizontal (m)", "num", 1), ("vertical", "Vertical (m)", "num", 1),
                         ("accesorios", "Accesorios (m)", "num", 1), ("total", "Longitud (m)", "num", 1)])
        st.caption("Diámetro: red hidráulica por velocidad de diseño (motor/hidraulica.py), solo en líneas de líquido. Las longitudes quedan en "
                   "st.session_state[\"layout\"][\"longitudes_m\"] para el costeo.")

    # ---------------------------------------------------------------- red eléctrica
    with t_elec:
        with st.expander("? Red eléctrica: cómo se hace, para qué sirve y por qué importa"):
            st.markdown(AYUDA_ELEC)
        n1, n2, n3, n4 = st.columns(4)
        n1.metric("Potencia conectada", C.fmt(red["P_total_kW"], 1) + " kW", f"{len(red['cables'])} alimentadores", delta_color="off")
        n2.metric("Corriente total", C.fmt(red["I_total_A"], 0) + " A", f"{C.fmt(lay['tension'], 0)} V; cos φ {C.fmt(lay['fp'], 2)}", delta_color="off")
        n3.metric("Cable total", C.fmt(red["largo_total_m"], 1) + " m", f"bandeja a +{C.fmt(lay['h_bandeja'], 1)} m", delta_color="off")
        cc = red.get("centro")
        n4.metric("Sala eléctrica (CCM)", f"{C.fmt(red['ccm'][0], 1)}; {C.fmt(red['ccm'][1], 1)} m",
                  ("centro de carga " + f"{C.fmt(cc[0], 1)}; {C.fmt(cc[1], 1)} m") if cc else "sin cargas", delta_color="off")
        for av in red["avisos"]:
            st.warning(av)
        if not red["cables"]:
            st.info("Ningún equipo de la planta tiene potencia eléctrica en su resultado o en sus parámetros: no hay alimentadores.")
        else:
            C.mostrar_tabla(red["cables"],
                            [("id", "Alimentador", "txt", 0), ("nombre", "Carga", "txt", 0), ("P_kW", "Potencia (kW)", "num", 1),
                             ("I_A", "Corriente (A)", "num", 1), ("I_diseno_A", "Corriente de diseño (A)", "num", 1),
                             ("conductor", "Conductor", "txt", 0), ("capacidad_A", "Capacidad (A)", "num", 0),
                             ("horizontal", "Horizontal (m)", "num", 1), ("vertical", "Vertical (m)", "num", 1), ("holgura", "Holgura (m)", "num", 1),
                             ("total", "Longitud (m)", "num", 1), ("dU_pct", "Caída de tensión (%)", "num", 2), ("criterio", "Criterio", "txt", 0),
                             ("fuente_P", "Fuente de la potencia", "txt", 0)])
        st.caption(f"{LY.FUENTE_TENSION}. {LY.FUENTE_SECCIONES}. Los largos quedan en st.session_state[\"layout\"][\"cables_m\"] "
                   "y el detalle en [\"cables\"].")
