"""Pantalla Layout (PAT 135, tarea T7.3; indicación 3 de la reunión con el profesor Torres del 04-11-2026).

Dimensiones de los equipos, propuesta automática de layout (modelo de lenguaje si hay clave; si no, algoritmo propio tipo
CRAFT), plano en planta donde el usuario arrastra y rota los equipos (componente ui/componentes/layout_planta, mismo mecanismo
que el lienzo de Diseño), dos elevaciones y un corte con cotas, y longitud de cañería por corriente para el costeo.
Todo queda en st.session_state["layout"] = {"posiciones": {id: [x, y, rot]}, "longitudes_m": {corriente: m}, "dims": {...}}.
"""
from __future__ import annotations
import os
from pathlib import Path
import streamlit as st
import streamlit.components.v1 as components
from pat_sim.motor import layout as LY
from . import comun as C

# PAT 135: componente bidireccional del plano (HTML propio, sin internet ni compilación)
RUTA = Path(__file__).resolve().parent / "componentes" / "layout_planta"
_componente = components.declare_component("layout_planta", path=str(RUTA))
CLAVE = "lay_plano"

AYUDA = """**Cómo se hace.** 1) Cada equipo recibe un largo, un ancho y un alto según su familia (símbolo ISO 10628) y su tamaño:
carga en t/h, calor en kW o potencia de la caldera en MW. Las dimensiones de partida son Supuesto (orden de catálogos de fabricantes)
y escalan por semejanza geométrica (lados con exponente 1/3 del tamaño; equipos extendidos como el secador de banda, 1/2). Se reemplazan
con las de un fabricante, escritas abajo o traídas de internet con Tavily cuando esté el cliente. 2) «Proponer layout»: con clave de un
modelo de lenguaje se le envía la lista de equipos y corrientes y devuelve las posiciones en JSON; sin clave, o si su propuesta superpone
equipos, se usa el algoritmo propio: intercambio por pares tipo CRAFT (Armour y Buffa, 1963), que minimiza Σ flujo × distancia
rectilínea entre equipos conectados, con el orden del proceso como relación más fuerte (Muther, 1973, Systematic Layout Planning). Los
equipos van en filas en zigzag con pasillos de 1,5 m (Supuesto), así no se superponen. 3) En el plano usted arrastra (ajuste a 0,5 m)
y rota (doble clic o R) los equipos; el plano marca en rojo los que quedan a menos del pasillo. 4) Con el layout se dibujan la elevación
frontal (desde el sur), la lateral izquierda (desde el oeste) y el corte A-A, con cotas. 5) Cada corriente se lleva en recorrido
ortogonal de puerto a puerto: horizontal |Δx| + |Δy|, subida y bajada al rack de cañerías (5 m, Supuesto) y 20 % por codos, válvulas y
liras (Supuesto); los transportadores de biomasa van sin rack.

**Para qué sirve.** Ubicar los equipos en planta, ver alturas y despejes, y obtener la longitud de cada cañería, que con el diámetro de la
red hidráulica alimenta el costeo de la planta (las longitudes quedan en la sesión para la evaluación económica).

**Por qué importa.** En la etapa de diseño solo se conocen los diámetros; el profesor Torres pidió sacar las longitudes del layout
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


def _estado(pl) -> dict:
    """Layout de la sesión; se reinicia si cambia la planta (otro rubro u otro escenario)."""
    ss = st.session_state
    firma = f"{pl.nombre}|{pl.rubro}"
    lay = ss.get("layout")
    if not isinstance(lay, dict) or lay.get("firma") != firma:
        lay = dict(firma=firma, posiciones={}, longitudes_m={}, dims={}, overrides={}, version=1, seq=0,
                   pasillo=LY.PASILLO_M, h_rack=LY.H_RACK_M, accesorios=LY.ACCESORIOS)
        ss["layout"] = lay
    return lay


def _aplicar_plano(lay: dict, valor) -> bool:
    """Toma del navegador las posiciones movidas o rotadas (solo de la versión vigente y con número de envío nuevo)."""
    if not isinstance(valor, dict) or valor.get("version") != lay.get("version"):
        return False
    s = int(valor.get("seq") or 0)
    if s <= int(lay.get("seq") or 0):
        return False
    pos = valor.get("posiciones") or {}
    for k, v in pos.items():
        if k in lay["posiciones"]:
            try:
                lay["posiciones"][k] = [float(v[0]), float(v[1]), int(round(float(v[2] if len(v) > 2 else 0) / 90)) % 4 * 90]
            except (TypeError, ValueError, IndexError):
                continue
    lay["seq"] = s
    return True


def _datos_componente(pl, lay: dict, y_corte) -> dict:
    return dict(equipos=[dict(id=k, nombre=pl.equipos[k].nombre, largo=d["largo"], ancho=d["ancho"], alto=d["alto"])
                         for k, d in lay["dims"].items()],
                posiciones=lay["posiciones"], corrientes=[{k: f[k] for k in ("id", "origen", "destino", "tipo", "servicio")} for f in lay["filas"]],
                pasillo=lay["pasillo"], version=lay["version"], ultimo_seq=lay["seq"], y_corte=y_corte)


def mostrar():
    ss = st.session_state; pl = C.planta()
    st.subheader("Layout de planta")
    with st.expander("? Layout: cómo se hace, para qué sirve y por qué importa"):
        st.markdown(AYUDA)
    if not C.exigir_resuelta():
        return
    lay = _estado(pl)

    # ---------------------------------------------------------------- supuestos
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
        modelo = d.text_input("Modelo de lenguaje", os.environ.get("ANTHROPIC_MODEL", LY.MODELO_LLM), key="lay_modelo",
                              help="Se usa solo si hay clave ANTHROPIC_API_KEY en .streamlit/secrets.toml o en el entorno")
        st.caption(("Hay clave de modelo de lenguaje: «Proponer layout» le pide la propuesta y la revisa contra superposición." if clave else
                    "Sin clave de modelo de lenguaje: «Proponer layout» usa el algoritmo propio tipo CRAFT (Armour y Buffa, 1963)."))

    b1, b2, _ = st.columns([1, 1, 3])
    proponer = b1.button("Proponer layout", key="lay_proponer", type="primary")
    volver = b2.button("Volver a la propuesta", key="lay_volver", disabled=not lay.get("propuesta"))

    # cambios del plano que llegan del navegador (antes de recalcular)
    _aplicar_plano(lay, ss.get(CLAVE))
    lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))
    if proponer:
        r = LY.proponer_layout(pl, lay["dims"], lay["pasillo"], clave, modelo)
        lay["posiciones"] = {k: list(v) for k, v in r["posiciones"].items()}
        lay["propuesta"] = {k: list(v) for k, v in r["posiciones"].items()}
        lay["metodo"] = r["metodo"]; lay["version"] = int(lay["version"]) + 1
        for av in r.get("avisos", []):
            st.warning(av)
        lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))
    elif volver and lay.get("propuesta"):
        lay["posiciones"] = {k: list(v) for k, v in lay["propuesta"].items()}
        lay["version"] = int(lay["version"]) + 1
        lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))

    m1, m2, m3, m4 = st.columns(4)
    hs = [LY.huella(p, lay["dims"][k]) for k, p in lay["posiciones"].items()]
    largo_pl = max(h[2] for h in hs) + lay["pasillo"]; ancho_pl = max(h[3] for h in hs) + lay["pasillo"]
    m1.metric("Superficie de la planta", C.fmt(largo_pl * ancho_pl, 0) + " m²", f"{C.fmt(largo_pl, 1)} × {C.fmt(ancho_pl, 1)} m", delta_color="off")
    m2.metric("Σ flujo × distancia", C.fmt(lay["costo"], 0) + " t·m/h", lay.get("metodo", ""), delta_color="off")
    m3.metric("Cañerías y ductos", C.fmt(sum(f["total"] for f in lay["filas"] if f["medio"] in ("cañería", "ducto")), 1) + " m",
              f"{len(lay['filas'])} corrientes", delta_color="off")
    m4.metric("Equipos superpuestos", str(len(lay["superposiciones"])), "pares a menos del pasillo", delta_color="off")
    if lay["superposiciones"]:
        st.warning("Equipos a menos del pasillo: " + ", ".join(f"{a} con {b}" for a, b in lay["superposiciones"][:6]))

    # ---------------------------------------------------------------- plano en planta
    ids = list(lay["dims"])
    alto = max(ids, key=lambda k: lay["dims"][k]["alto"]) if ids else None
    st.markdown("#### Plano en planta")
    eq_corte = st.selectbox("Plano de corte A-A por el eje del equipo", ids, index=ids.index(alto) if alto in ids else 0, key="lay_corte",
                            format_func=lambda k: f"{k} · {pl.equipos[k].nombre}")
    y_corte = float(lay["posiciones"][eq_corte][1]) if eq_corte in lay["posiciones"] else None
    valor = _componente(datos=_datos_componente(pl, lay, y_corte), key=CLAVE, default=None)
    if _aplicar_plano(lay, valor):
        lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))
    st.download_button("Descargar el plano (SVG)", LY.plano_svg(lay["posiciones"], lay["dims"], lay["filas"],
                       {k: e.nombre for k, e in pl.equipos.items()}, y_corte), file_name="Layout_planta.svg", mime="image/svg+xml", key="lay_dl_plano")

    # ---------------------------------------------------------------- elevaciones y corte
    st.markdown("#### Elevaciones y corte")
    t1, t2, t3 = st.tabs(["Elevación frontal", "Elevación lateral izquierda", "Corte A-A"])
    svgs = [("frontal", LY.elevacion_svg(lay["posiciones"], lay["dims"], "frontal", lay["h_rack"])),
            ("lateral", LY.elevacion_svg(lay["posiciones"], lay["dims"], "lateral", lay["h_rack"])),
            ("corte", LY.corte_svg(lay["posiciones"], lay["dims"], y_corte, lay["h_rack"]))]
    for tab, (n, svg) in zip((t1, t2, t3), svgs):
        with tab:
            st.image(svg, width="stretch")
            st.download_button("Descargar (SVG)", svg, file_name=f"Layout_{n}.svg", mime="image/svg+xml", key=f"lay_dl_{n}")

    # ---------------------------------------------------------------- longitudes
    st.markdown("#### Longitud de cañerías por corriente")
    C.mostrar_tabla([dict(f, tramo=f"{f['origen']} → {f['destino']}") for f in lay["filas"]],
                    [("id", "Corriente", "txt", 0), ("tramo", "Tramo", "txt", 0), ("tipo", "Fluido", "txt", 0), ("medio", "Medio", "txt", 0),
                     ("D_mm", "Diámetro interno (mm)", "num", 0), ("horizontal", "Horizontal (m)", "num", 1), ("vertical", "Vertical (m)", "num", 1),
                     ("accesorios", "Accesorios (m)", "num", 1), ("total", "Longitud (m)", "num", 1)])
    st.caption("Diámetro: red hidráulica por velocidad de diseño (motor/hidraulica.py), solo en líneas de líquido. Las longitudes quedan en "
               "st.session_state[\"layout\"][\"longitudes_m\"] para el costeo.")

    # ---------------------------------------------------------------- dimensiones
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
            lay.update(LY.estado_layout(pl, lay, lay["overrides"], lay["pasillo"], lay["h_rack"], lay["accesorios"]))
            st.success(f"Dimensiones de {e} actualizadas; revise el plano por superposiciones.")
        if y2.button("Buscar en internet", key="lay_ov_web", help="Usa el cliente de Tavily (pat_sim.datos.precios_web) si está instalado"):
            r = LY.buscar_dimensiones_web(pl.equipos[e])
            if r:
                lay["overrides"][e] = r
                lay.update(LY.estado_layout(pl, lay, lay["overrides"], lay["pasillo"], lay["h_rack"], lay["accesorios"]))
                st.success(f"Dimensiones de {e} desde internet: {r.get('fuente', '')}")
            else:
                st.info("No hay cliente de búsqueda en internet o no encontró dimensiones; se mantienen las del Supuesto.")
        if y3.button("Volver al Supuesto", key="lay_ov_quitar", disabled=e not in lay["overrides"]):
            lay["overrides"].pop(e, None)
            lay.update(LY.estado_layout(pl, lay, lay["overrides"], lay["pasillo"], lay["h_rack"], lay["accesorios"]))
