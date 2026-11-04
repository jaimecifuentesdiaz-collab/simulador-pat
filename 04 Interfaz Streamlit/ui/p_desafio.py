"""Pantalla Desafío (PAT 135, tarea T7.4): la puerta de entrada del diseño asistido de ingeniería básica.

Como pidió el profesor Torres el 04-11-2026 (indicación 4): «don Jaime Cifuentes, su desafío es diseñar una planta de
secado de agar agar; su demanda tiene este comportamiento», con el gráfico de demanda y los precios de venta. El botón
«Partir en blanco» deja en la sesión el desafío con su serie de demanda (st.session_state["desafio"]) y reemplaza la
planta de la sesión (st.session_state.pl, la que lee C.planta()) por una planta vacía del rubro del desafío.
Los desafíos se cargan y editan en la pantalla Mantenedor (solo el profesor).
"""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import RUBROS
from pat_sim.datos import mantenedor as M
from pat_sim.motor import desafio as D
from . import comun as C

TRATAMIENTOS = ("don", "doña", "")
AYUDA = """
**Cómo se usa**

1. Escriba su nombre y elija el tratamiento; el saludo del desafío lo usa.
2. Elija un desafío activo. El enunciado dice qué planta diseñar, el producto, la demanda por período y los precios de venta.
3. Presione «Partir en blanco»: la planta de la sesión queda vacía, del rubro del desafío, y las demás pantallas trabajan con ella.
4. En Diseño ponga los equipos y conéctelos; vea las restricciones (utilización y cuello de botella), decida si incorpora
   recuperación de calor y evalúe en Economía. Es un proceso iterativo: si la inversión es muy alta o la energía muy barata,
   quizás convenga sacar el recuperador.

**De dónde salen las cifras**

La demanda y los precios vienen de la base de datos (tabla desafios) y cada uno trae su fuente o la marca «Supuesto». El
profesor los cambia en la pantalla Mantenedor. La serie de demanda queda en la sesión para el Montecarlo de la evaluación
económica (exceso y déficit de capacidad frente a la demanda).

**Ojo**

Partir en blanco reemplaza la planta que tiene abierta. Si la modificó, guarde antes una versión en Escenario.
"""


def _mantenedor():
    m = M.mantenedor(C.obtener_bd())
    if not m.listar_desafios():                 # base nueva: siembra los desafíos de ejemplo (idempotente)
        m.sembrar()
    return m


def _grafico(d: dict):
    dem = d["demanda"]; serie = D.serie_demanda(d)
    et = dem.get("etiquetas") or [str(i + 1) for i in range(len(serie))]
    filas = [{"Período": e, "Orden": i, "Demanda": v} for i, (e, v) in enumerate(zip(et, serie))]
    spec = {"mark": {"type": "bar", "color": "#1b7a5a", "tooltip": True},
            "encoding": {"x": {"field": "Período", "type": "ordinal", "sort": None, "title": dem["periodo"].capitalize(),
                               "axis": {"labelAngle": -45 if len(serie) > 12 else 0, "labelOverlap": True}},
                         "y": {"field": "Demanda", "type": "quantitative", "title": f"Demanda ({dem['unidad']} por {dem['periodo']})"}},
            "height": 280}
    try:
        import pandas as pd
        st.vega_lite_chart(pd.DataFrame(filas), spec)
    except Exception:                            # sin pandas: tabla en vez del gráfico
        C.mostrar_tabla(filas, [("Período", "Período", "txt", 0), ("Demanda", f"Demanda ({dem['unidad']})", "num", 1)])
    e = D.estadisticas(d); u = dem["unidad"]
    C.mostrar_tabla([dict(c="Total", v=e["total"], u=u), dict(c=f"Media por {dem['periodo']}", v=e["media"], u=u),
                     dict(c=f"Máximo ({e['periodo_maximo']})", v=e["maximo"], u=u), dict(c="Mínimo", v=e["minimo"], u=u),
                     dict(c="Coeficiente de variación", v=100 * e["cv"], u="%")],
                    [("c", "Demanda", "txt", 0), ("v", "Valor", "num", 1), ("u", "Unidad", "txt", 0)])
    st.caption(C.esc(f"Fuente de la demanda: {dem.get('fuente', '')}"))


def _precios(d: dict):
    precios = d.get("precios") or []
    if not precios:
        st.caption("Este desafío no trae precios de venta.")
        return
    filas = [dict(p=p.get("producto", ""), v=p.get("precio"), u=f"{p.get('moneda', '')}/{p.get('unidad', '')}", f=p.get("fuente", "")) for p in precios]
    C.mostrar_tabla(filas, [("p", "Producto", "txt", 0), ("u", "Unidad", "txt", 0), ("v", "Precio de venta", "mm", 2), ("f", "Fuente", "txt", 0)])


def _partir(d: dict, nombre: str, trato: str):
    """Deja el desafío en la sesión y reemplaza la planta por una vacía del rubro (como p_curso carga su variante)."""
    ss = st.session_state
    ss.pl = D.planta_vacia(d); ss.pid = None; ss.vid = None
    ss["desafio"] = D.estado_sesion(d, nombre, trato)
    for k in ("rc_dT", "rc_Tfin", "esc_rubro", "op", "op_compra"):
        ss.pop(k, None)
    ss.aviso_desafio = (f"Partió en blanco: planta vacía del rubro {RUBROS.get(ss.pl.rubro, ss.pl.rubro)} para «{d['titulo']}». "
                        "Vaya a Diseño para poner los equipos.")


def mostrar():
    ss = st.session_state
    st.subheader("Desafío")
    with st.expander("?  Cómo usar el desafío"):
        st.markdown(AYUDA)
    try:
        m = _mantenedor()
        activos = m.listar_desafios(solo_activos=True)
    except Exception as e:                        # base no disponible: los desafíos de la semilla
        st.warning(f"No se pudo leer la base de datos ({e}); se muestran los desafíos de ejemplo.")
        activos = [dict(s, id=None) for s in M.semilla_desafios()]
    if not activos:
        st.info("No hay desafíos activos. El profesor los crea o activa en la pantalla Mantenedor.")
        return
    av = ss.pop("aviso_desafio", None)
    if av:
        st.success(av)

    a, b, c = st.columns([1, 2, 3])
    trato = a.selectbox("Tratamiento", TRATAMIENTOS, format_func=lambda t: t or "(ninguno)", key="des_trato")
    nombre = b.text_input("Su nombre", value="Jaime Cifuentes", key="des_nombre")
    titulos = [x["titulo"] for x in activos]
    actual = (ss.get("desafio") or {}).get("titulo")
    if ss.get("des_sel") not in titulos:          # el desafío elegido se desactivó o se borró en el Mantenedor
        ss.pop("des_sel", None)
    sel = c.selectbox("Desafío", titulos, index=titulos.index(actual) if actual in titulos else 0, key="des_sel")
    d = next((x for x in activos if x["titulo"] == sel), activos[0])
    err = D.validar(d)
    if err:
        st.error("Este desafío tiene errores; el profesor debe corregirlo en Mantenedor: " + "; ".join(err))
        return

    st.markdown(f"#### {C.esc(d['titulo'])}")
    st.markdown(C.esc(f"**{D.saludo(nombre, trato)}** {d['enunciado']}"))
    st.markdown(C.esc(f"**Producto:** {d['producto']}. **Rubro de la planta:** {RUBROS.get(d['rubro'], d['rubro'])}."
                      + (f" **Autor:** {d['autor']}, {d.get('fecha', '')}." if d.get("autor") else "")))

    st.markdown("##### Demanda")
    _grafico(d)
    st.markdown("##### Precios de venta")
    _precios(d)

    if st.button("Partir en blanco", type="primary", key="des_partir", width="stretch",
                 help="Reemplaza la planta de la sesión por una vacía del rubro del desafío. Guarde antes una versión si modificó la planta."):
        _partir(d, nombre, trato)
        st.success(ss.pop("aviso_desafio"))
    en_curso = ss.get("desafio")
    if en_curso:
        pl = C.planta()
        st.caption(C.esc(f"Desafío en curso: «{en_curso['titulo']}». Planta de la sesión: {pl.nombre}, con {len(pl.equipos)} equipo(s). "
                         f"La demanda ({len(en_curso['demanda'])} períodos, en {en_curso['unidad']} por {en_curso['periodo']}) "
                         "queda en la sesión para el Montecarlo."))
