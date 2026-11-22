"""Pantalla Layout (PAT 135, tareas T7.3 y T15; indicación 3 de la reunión y correo del profesor Torres del 04-11-2026).

Dimensiones de los equipos, propuesta automática de layout (modelo de lenguaje si hay clave; si no, algoritmo propio tipo
CRAFT), plano en planta donde el usuario arrastra y rota los equipos (componente ui/componentes/layout_planta, mismo mecanismo
que el lienzo de Diseño), dos elevaciones y un corte con cotas, y longitud de cañería por corriente para el costeo.
Todo queda en st.session_state["layout"] = {"posiciones": {id: [x, y, rot]}, "longitudes_m": {corriente: m}, "dims": {...}}.
PAT 135 (T15): pestañas Plano, Elevaciones, Isométrica, Cañerías y Red eléctrica. Red eléctrica: sala eléctrica o CCM que se
arrastra en el plano, alimentadores por bandeja con corriente, sección y caída de tensión; resultado en
st.session_state["layout"]["cables_m"] ({alimentador: m}) y ["cables"] (detalle). Vista isométrica interactiva al estilo Anatomy
(motor/isometrico.py y el componente ui/componentes/isometrico).
PAT 140 (19-11-2026): plano de disposición detallado (motor/plano_detalle.py): equipos a escala con su símbolo de vista superior y
zona de mantención, cañerías con ancho según el DN, flecha y código de línea, bandeja eléctrica, nave con muros, columnas y ejes,
salas, oficinas, bodega, patio, estacionamientos y cerco; botones «Vista de plano» y «Vista a color» y capas que se encienden y
apagan (lay["vista"]); la descarga SVG y la lámina (SVG, PDF y DXF) salen con el mismo dibujo. La tabla «Dimensiones de los
equipos» ya no lleva la columna de fuente (las fuentes propias de las dimensiones reemplazadas van en un ⓘ bajo la tabla).
"""
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from pat_sim.motor import layout as LY
from pat_sim.motor import isometrico as ISO
from pat_sim.motor import lamina as LAM   # PAT 136 (T19): lámina de ingeniería ISO 5457 e ISO 7200
from pat_sim.motor import plano_detalle as PD   # PAT 140: plano de disposición detallado
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

**Por qué importa.** En la etapa de diseño solo se conocen los diámetros; las longitudes salen del *layout*.
Una cañería más larga cuesta más, pierde más calor y más carga, y eso cambia la inversión y el ahorro de la recuperación
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

**Por qué importa.** Las vistas de elevación del *layout* muestran, en ingeniería básica, si las
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

**Para qué sirve y por qué importa.** Con las vistas isométricas interactivas del *layout* definido se ve
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

**Por qué importa.** El *layout* preliminar incluye *piping* y alimentaciones eléctricas. Los motores
grandes (compresores de los evaporadores MVR, molinos, peletizadoras) pesan en la inversión eléctrica y su ubicación respecto de la sala
eléctrica cambia el largo y la sección de los cables. Sobre 250 kW se avisa que en la práctica se alimentan en media tensión."""


EXP_SUPUESTOS_ELEC = "⚠ Supuestos de la red eléctrica"


def texto_supuestos_red() -> str:
    """PAT 140 i: texto del desplegable «⚠ Supuestos de la red eléctrica» (las mismas constantes del motor de siempre)."""
    return (f"{LY.FUENTE_TENSION}. {LY.FUENTE_SECCIONES}. Los largos quedan en st.session_state[\"layout\"][\"cables_m\"] "
            "y el detalle en [\"cables\"].")


ROTS_ISO = [0, 90, 180, 270]


def sincronizar_rot_iso(ss) -> tuple[int, str]:
    """PAT 140 i: orientación de la vista isométrica sincronizada en los dos sentidos. Si el dibujo devolvió una orientación nueva (botones
    SE, NE, NO, SO o girar; cada envío trae una marca distinta) se copia a la lista «Orientación de la vista» antes de crearla; si no, manda
    la lista. Devuelve (orientación para el dibujo, marca del último envío ya aplicado): el dibujo no vuelve a girar mientras Python no
    haya recibido su último envío, así no hay bucles de recarga."""
    v = ss.get("lay_iso")
    if isinstance(v, dict) and v.get("marca") and v.get("marca") != ss.get("lay_iso_marca"):
        try:
            r = int(v.get("rot")) % 360
        except (TypeError, ValueError):
            r = None
        ss["lay_iso_marca"] = v.get("marca")
        if r in ROTS_ISO:
            ss["lay_iso_rot"] = r
    r = ss.get("lay_iso_rot", 0)
    if r not in ROTS_ISO:
        r = 0; ss["lay_iso_rot"] = 0
    return int(r), str(ss.get("lay_iso_marca") or "")


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
    if isinstance(valor.get("sel"), (str, type(None))):         # PAT 140 i: equipo seleccionado en el plano (manda donde se superponen)
        lay["sel"] = valor.get("sel")
    v = valor.get("vista")                                   # PAT 140: vista de plano o a color y capas visibles
    if isinstance(v, dict):
        lay["vista"] = dict(modo=v.get("modo"), capas=list(v.get("capas") or []))
        lay["vista"] = _vista(lay)
    return True


def _vista(lay: dict) -> dict:
    """PAT 140: vista del plano (plano o color) y grupos de capas visibles, que vuelven del componente."""
    v = lay.get("vista") if isinstance(lay.get("vista"), dict) else {}
    capas = [c for c in (v.get("capas") if isinstance(v.get("capas"), list) else list(PD.GRUPOS)) if c in PD.GRUPOS]
    return dict(modo=v.get("modo") if v.get("modo") in ("plano", "color") else "plano", capas=capas)


def _capas_mundo(vista: dict) -> set:
    return {c for g in vista["capas"] for c in PD.GRUPOS[g]}


def _autor() -> str:
    """PAT 140: el nombre escrito en Desafío (si lo hay); nunca un nombre fijo."""
    ss = st.session_state
    for v in (ss.get("persona_nombre"), ss.get("des_nombre"), (ss.get("desafio") or {}).get("nombre")):
        if v and str(v).strip():
            return " ".join(str(v).split())
    return ""


def _modelo(pl, lay: dict, nombres: dict) -> dict:
    """PAT 140: plano detallado; nunca bota la pantalla (si falla, el plano sigue con los rectángulos de siempre)."""
    try:
        return PD.construir(lay, nombres, pl, proyecto=pl.nombre, autor=_autor())
    except Exception as e:
        st.warning(f"No se pudo armar el plano detallado: {e}")
        return {"vacio": True}


def _datos_componente(pl, lay: dict, y_corte, modelo: dict | None = None) -> dict:
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
                pasillo=lay["pasillo"], version=lay["version"], ultimo_seq=lay["seq"], y_corte=y_corte,
                # PAT 140: dibujo detallado armado en Python, estilos de las dos vistas, leyenda, rótulo y vista elegida
                plano=PD.fragmentos(modelo) if modelo and not modelo.get("vacio") else None,
                css={"plano": PD.css("plano", raiz="#svg"), "color": PD.css("color", raiz="#svg")},
                leyenda=(modelo or {}).get("leyenda", []), cajetin=(modelo or {}).get("cajetin", {}), vista=_vista(lay),
                sel=lay.get("sel"))


def _recalcular(pl, lay: dict) -> None:
    lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))
    lay["pl_version"] = C.version_planta()   # PAT 137 (estado único): Costeo y Equipos auxiliares saben si está al día


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
        # PAT 140 i: etiqueta corta para que quepa en una línea y su cuadro quede a la altura de los otros de la fila
        lay["h_bandeja"] = float(e3.number_input("Altura bandeja eléctrica (m)", 2.0, 15.0, float(lay["h_bandeja"]), 0.5, key="lay_bandeja",
                                                 help="Altura de la bandeja eléctrica sobre el piso, por donde van los alimentadores "
                                                      "desde la sala eléctrica. Supuesto: 4 m, 1 m bajo el rack de cañerías"))
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


AYUDA_PLANO = ("**Qué muestra.** Vista superior a escala del sitio: cada equipo con su largo y ancho de la tabla de abajo y un símbolo "
               "según su forma (estanques y tolvas, evaporadores con un cuerpo por efecto y su condensador o compresor, intercambiadores con "
               "carcasa y cabezales, bandas con rodillos, bombas, trituradora y refinadora con su motor, calderas con quemador y llenadora con "
               "cabezales), la zona de mantención punteada, las cañerías con su ancho según el DN, flecha de sentido y código "
               "corriente-DN-servicio, las bombas de línea de Equipos auxiliares con sus válvulas, la bandeja eléctrica desde la sala eléctrica, "
               "la nave con muros, columnas, ejes y cotas, la sala de calderas, oficinas y baños, la bodega de producto terminado, el patio de "
               "camiones, los estacionamientos y el cerco. La nave se recalcula al soltar un equipo.\n\n"
               "**Cómo se dibujan las cañerías.** Recorrido ortogonal de boquilla a boquilla por los pasillos, sin atravesar equipos (búsqueda "
               "en una grilla de 0,5 m). Es un recorrido gráfico: el largo que va al costeo sigue siendo el del *rack* de la pestaña Cañerías.\n\n"
               "**Supuestos.**\n" + "\n".join(f"- {a}: {b}" for a, b in PD.SUPUESTOS))


AYUDA_LAM = """**Cómo se hace.** El plano en planta del *layout* se dibuja en una lámina ISO 5457 (A3 o A1 apaisada: marco de 0,7 mm,
margen izquierdo de 20 mm, otros de 10 mm, marcas de centrado y zonas de referencia de 50 mm con letras y números) con cajetín
ISO 7200 de 180 mm (título, proyecto, autor, revisor, institución, fecha, escala, número de plano, revisión, unidad y método de
proyección). La escala sale de la serie ISO 5455 (1:50, 1:100, 1:200 y 1:500): la automática es la menor que deja la planta dentro
del área útil. Lleva ejes de grilla con burbujas, cotas entre ejes de equipos, entre ejes de grilla y generales (ISO 129-1), barra de
escala, norte, tipos de línea ISO 128 y la lista de equipos. No recalcula nada: usa las posiciones, dimensiones, cañerías, bandeja
y sala eléctrica de las otras pestañas.

**Para qué sirve y por qué importa.** El plano sale con dibujo profesional de ingeniería: el DXF se
abre en AutoCAD (capas EQUIPOS, CANERIAS, ELECTRICO, COTAS, TEXTOS, MARCO y EJES, en metros) y el PDF sale listo para imprimir."""


def _lamina(pl, lay: dict, nombres: dict, modelo: dict | None = None) -> None:
    """Pestaña Lámina: formato, escala, cajetín editable y descargas SVG, PDF y DXF (PAT 136, T19)."""
    with st.expander("? Lámina: cómo se hace, para qué sirve y por qué importa"):
        st.markdown(AYUDA_LAM)
    c1, c2, c3 = st.columns(3)
    fmt = c1.selectbox("Formato de lámina", list(LAM.FORMATOS), key="lam_formato", help="ISO 5457, apaisado")
    esc = c2.selectbox("Escala", ["Automática"] + [f"1:{e}" for e in LAM.ESCALAS], key="lam_escala", help="ISO 5455")
    num = c3.text_input("Número de plano", "PAT136-LAY-001", key="lam_numero")
    t1, t2 = st.columns(2)
    titulo = t1.text_input("Título", "Plano de disposición general en planta", key="lam_titulo")
    rev = t2.text_input("Revisión", "A", key="lam_revision")
    vista = _vista(lay)
    m = LAM.generar_lamina(lay, nombres, fmt, None if esc == "Automática" else esc, proyecto=pl.nombre, titulo=titulo,
                           numero_plano=num, revision=rev, plano=modelo, modo=vista["modo"], capas=_capas_mundo(vista) | {"MARCO"},
                           autor=_autor())
    for av in m["avisos"]:
        st.warning(av)
    st.caption(f"Lámina {fmt} a escala {m['escala_txt']}; {len(m['equipos'])} equipos en la lista; "
               f"{'vista a color' if vista['modo'] == 'color' else 'vista de plano'} y capas elegidas en la pestaña Plano.")
    svg = LAM.a_svg(m)
    st.image(svg, width="stretch")
    d1, d2, d3 = st.columns(3)
    d1.download_button("Descargar lámina (SVG)", svg, file_name=f"Lamina_{fmt}.svg", mime="image/svg+xml", key="lam_dl_svg")
    try:
        d2.download_button("Descargar lámina (PDF)", LAM.a_pdf(m), file_name=f"Lamina_{fmt}.pdf", mime="application/pdf", key="lam_dl_pdf")
    except ImportError:
        d2.info("Falta reportlab para el PDF: instálelo con pip install reportlab.")
    dxf, aviso = LAM.a_dxf(m)
    if dxf is None:
        d3.warning(aviso)
    else:
        d3.download_button("Descargar lámina (DXF)", dxf, file_name=f"Lamina_{fmt}.dxf", mime="application/dxf", key="lam_dl_dxf")


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
    nombres = {k: e.nombre for k, e in pl.equipos.items()}
    modelo = _modelo(pl, lay, nombres)                       # PAT 140: plano detallado (nave derivada de equipos y pasillos)
    if modelo.get("nave"):
        nv = modelo["nave"]; largo_pl, ancho_pl = nv[2] - nv[0], nv[3] - nv[1]
        m1.metric("Superficie de la nave", C.fmt(largo_pl * ancho_pl, 0) + " m²", f"{C.fmt(largo_pl, 1)} × {C.fmt(ancho_pl, 1)} m", delta_color="off")
    else:
        m1.metric("Superficie de la planta", C.fmt(largo_pl * ancho_pl, 0) + " m²", f"{C.fmt(largo_pl, 1)} × {C.fmt(ancho_pl, 1)} m", delta_color="off")
    m2.metric("Σ flujo × distancia", C.fmt(lay["costo"], 0) + " t·m/h", lay.get("metodo", ""), delta_color="off")
    m3.metric("Cañerías y ductos", C.fmt(sum(f["total"] for f in lay["filas"] if f["medio"] in ("cañería", "ducto")), 1) + " m",
              f"{len(lay['filas'])} corrientes", delta_color="off")
    m4.metric("Cable de alimentadores", C.fmt(red["largo_total_m"], 1) + " m", f"{len(red['cables'])} alimentadores", delta_color="off")
    m5.metric("Equipos superpuestos", str(len(lay["superposiciones"])), "pares a menos del pasillo", delta_color="off")
    # PAT 140 i: el aviso va en un espacio fijo; si aparecía o desaparecía, el plano de abajo se volvía a montar al soltar un equipo
    aviso_sup = st.empty()
    if lay["superposiciones"]:
        aviso_sup.warning("Equipos a menos del pasillo: " + ", ".join(f"{a} con {b}" for a, b in lay["superposiciones"][:6]))

    ids = list(lay["dims"])
    alto = max(ids, key=lambda k: lay["dims"][k]["alto"]) if ids else None
    # PAT 141 (pedido de Jaime, 19-11-2026): que se entienda que las vistas están enlazadas
    st.caption("Las seis pestañas usan la misma disposición: lo que mueva o rote en Plano se actualiza de inmediato en Lámina, "
               "Elevaciones, Isométrica, Cañerías y Red eléctrica, con las longitudes de cañerías y cables y el flujo por distancia.")
    t_plano, t_lam, t_elev, t_iso, t_can, t_elec = st.tabs(["Plano", "Lámina", "Elevaciones", "Isométrica", "Cañerías", "Red eléctrica"])

    # ---------------------------------------------------------------- plano en planta
    with t_plano:
        eq_corte = st.selectbox("Plano de corte A-A por el eje del equipo", ids, index=ids.index(alto) if alto in ids else 0, key="lay_corte",
                                format_func=lambda k: f"{k} · {pl.equipos[k].nombre}")
        y_corte = float(lay["posiciones"][eq_corte][1]) if eq_corte in lay["posiciones"] else None
        with st.expander("? Plano detallado: qué muestra y con qué supuestos se dibuja"):
            st.markdown(C.esc(AYUDA_PLANO))
        valor = _componente(datos=_datos_componente(pl, lay, y_corte, modelo), key=CLAVE, default=None)
        if _aplicar_plano(lay, valor):
            _recalcular(pl, lay); red = lay["red"]
            modelo = _modelo(pl, lay, nombres)
        for av in modelo.get("avisos", []) if not modelo.get("vacio") else []:
            st.warning(av)
        vista = _vista(lay)
        st.download_button("Descargar el plano (SVG)", PD.a_svg(modelo, vista["modo"], _capas_mundo(vista), y_corte=y_corte),
                           file_name="Plano_disposicion_planta.svg", mime="image/svg+xml", key="lay_dl_plano",
                           help="Sale con la vista (plano o color) y las capas que están encendidas en el plano")
        st.markdown("#### Dimensiones de los equipos")
        # PAT 140: sin la columna de fuente; el criterio común de las dimensiones de partida ya está en la ayuda de arriba
        C.mostrar_tabla([dict(id=k, nombre=pl.equipos[k].nombre, tam=d["tamano"], u=d["unidad"], **d) for k, d in lay["dims"].items()],
                        [("id", "Equipo", "txt", 0), ("nombre", "Nombre", "txt", 0), ("familia", "Familia", "txt", 0), ("tam", "Tamaño", "num", 1),
                         ("u", "Unidad", "txt", 0), ("largo", "Largo (m)", "num", 1), ("ancho", "Ancho (m)", "num", 1), ("alto", "Alto (m)", "num", 1),
                         ("categoria", "Categoría", "txt", 0)])
        propias = [(k, d["fuente"]) for k, d in lay["dims"].items() if d.get("categoria") != "Supuesto"]
        if propias:
            with st.expander("ⓘ Fuente de las dimensiones reemplazadas"):
                st.markdown(C.esc("\n".join(f"- {k}: {f}" for k, f in propias)))
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
                _recalcular(pl, lay); modelo = _modelo(pl, lay, nombres)   # PAT 141: la Lámina sale con las dimensiones nuevas
                st.success(f"Dimensiones de {e} actualizadas; revise el plano por superposiciones.")
            if y2.button("Buscar en internet", key="lay_ov_web", help="Usa el cliente de Tavily (pat_sim.datos.precios_web) si está instalado"):
                r = LY.buscar_dimensiones_web(pl.equipos[e])
                if r:
                    lay["overrides"][e] = r
                    _recalcular(pl, lay); modelo = _modelo(pl, lay, nombres)
                    st.success(f"Dimensiones de {e} desde internet: {r.get('fuente', '')}")
                else:
                    st.info("No hay cliente de búsqueda en internet o no encontró dimensiones; se mantienen las del Supuesto.")
            if y3.button("Volver al Supuesto", key="lay_ov_quitar", disabled=e not in lay["overrides"]):
                lay["overrides"].pop(e, None)
                _recalcular(pl, lay); modelo = _modelo(pl, lay, nombres)
    red = lay["red"]

    # ---------------------------------------------------------------- lámina de ingeniería (PAT 136, T19)
    with t_lam:
        _lamina(pl, lay, nombres, modelo)

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
        rot, marca = sincronizar_rot_iso(ss)
        _componente_iso(datos=dict(vistas=vistas, info=info, rot=rot, marca=marca, alto=640, firma=firma), key="lay_iso", default=None)
        if figuras:
            st.caption(f"Figuras isométricas del Mantenedor en uso (norma {ISO.NORMA_FIGURAS}): {len(figuras)}.")
        o1, o2 = st.columns([2, 1])
        rot_dl = o1.selectbox("Orientación de la vista", ROTS_ISO, key="lay_iso_rot", format_func=lambda r: ISO.VISTAS[r],
                              help="La misma de los botones SE, NE, NO y SO del dibujo: al cambiar una, cambia la otra")
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

    # ---------------------------------------------------------------- red eléctrica
    with t_elec:
        with st.expander("? Red eléctrica: cómo se hace, para qué sirve y por qué importa"):
            st.markdown(AYUDA_ELEC)
        # PAT 140: sin la métrica «Cable total»: el largo del cable ya está arriba, en «Cable de alimentadores», y la altura de la
        # bandeja, en su campo de los supuestos de la red eléctrica
        n1, n2, n4 = st.columns(3)
        n1.metric("Potencia conectada", C.fmt(red["P_total_kW"], 1) + " kW", f"{len(red['cables'])} alimentadores", delta_color="off")
        n2.metric("Corriente total", C.fmt(red["I_total_A"], 0) + " A", f"{C.fmt(lay['tension'], 0)} V; cos φ {C.fmt(lay['fp'], 2)}", delta_color="off")
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
        # PAT 140 i: los supuestos van en un desplegable cerrado con el símbolo de advertencia, en vez del texto gris bajo la tabla
        with st.expander(EXP_SUPUESTOS_ELEC, expanded=False):
            st.markdown(C.esc(texto_supuestos_red()))
