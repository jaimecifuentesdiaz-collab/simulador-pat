"""Pestaña Tableros (PAT 134): tableros como los de FlexSim con gráficos elegibles de Operación, Temporada, Dinámica y Línea.

PAT 134 (04-11-2026, pedido de Jaime): la forma de armar tableros pasa a ser como la biblioteca de FlexSim.
- Arriba, los tableros como fichas con su nombre; «Tablero nuevo» (con plantilla: vacío, Resumen de planta, Cuellos de botella,
  Temporada o Línea) y «Opciones del tablero» (renombrar, duplicar, cambiar por una plantilla y quitar) en ventanas emergentes.
- «Biblioteca de gráficos»: pestañas por categoría con tarjetas en grilla, cada una con su miniatura (TB.miniatura_svg), nombre,
  una línea de para qué sirve, marca «En el tablero» y botón «Agregar» o «Quitar»; un buscador filtra las tarjetas.
- El tablero: grilla de una o dos columnas (cada tablero guarda la suya); cada gráfico en un contenedor con borde, su título con
  «?» (qué muestra y cómo leerlo) y botones para subir, bajar, ancho completo o medio y quitar.
Se mantiene: turnos de demostración sobre copias, grupo «Línea (estados reales)» con st.session_state.linea_resultado,
exportación a HTML y CSV, tableros en st.session_state.tableros (nombre -> dict(graficos=[dict(id, ancho)], columnas); el
formato anterior nombre -> lista se migra solo) y claves con prefijo tb_. El modelo del tablero está en pat_sim.motor.tablero."""
from __future__ import annotations
import copy
import html as _h
import streamlit as st
from pat_sim.motor import operacion as OP
from pat_sim.motor import tablero as TB
from pat_sim.motor import temporada as TM
from . import comun as C

N_DEMO = 9
DISENOS = ["Una columna", "Dos columnas"]
COLS_BIB = 4                                  # tarjetas por fila en la biblioteca


# ----------------------------------------------------------------------------------------------- tableros guardados
def _tableros() -> dict:
    """st.session_state.tableros en el formato nuevo (migra el anterior nombre -> lista de ids)."""
    ss = st.session_state
    T = TB.normalizar_tableros(ss.get("tableros"))
    ss.tableros = T
    return T


def _pendientes():
    """Aplica los cambios de los botones antes de crear los widgets (Streamlit no deja cambiar un widget ya creado)."""
    ss = st.session_state
    for k, v in (ss.pop("tb_pendiente", None) or {}).items():
        ss[k] = v


def _ir(nombre: str, **otros):
    """Deja el tablero nombre como activo en la próxima pasada y vuelve a ejecutar la página."""
    st.session_state.tb_pendiente = dict(tb_activo=nombre, **otros)
    st.rerun()


def _avisar(texto: str):
    st.session_state.tb_aviso = texto


def _cabecera(T: dict) -> str:
    """Fichas con los tableros, «Tablero nuevo», «Opciones del tablero» y el interruptor de la biblioteca. Devuelve el activo."""
    ss = st.session_state
    if ss.get("tb_activo") not in T:
        ss.tb_activo = next(iter(T))
    a, b, c = st.columns([6, 2, 2], vertical_alignment="bottom")
    with a:
        activo = st.segmented_control("Tableros guardados", list(T), key="tb_activo", required=True,
                                      help="Clic en un tablero para verlo. Cada tablero guarda sus gráficos, su orden y su diseño.")
    if activo not in T:                            # sin selección (el sustituto de Streamlit o un nombre recién cambiado)
        activo = ss.get("tb_ultimo") if ss.get("tb_ultimo") in T else next(iter(T))
    ss.tb_ultimo = activo
    with b.popover("Tablero nuevo", icon=":material/add:", width="stretch"):
        nombre = st.text_input("Nombre", key="tb_nuevo", placeholder=TB.nombre_libre(f"Tablero {len(T) + 1}", T))
        plantilla = st.radio("Partir con", list(TB.PLANTILLAS), key="tb_plantilla",
                             captions=[d for d, _ids in TB.PLANTILLAS.values()])
        if st.button("Crear tablero", key="tb_crear", type="primary", width="stretch"):
            n = TB.nombre_libre((nombre or "").strip() or f"Tablero {len(T) + 1}", T)
            T[n] = TB.tablero_nuevo(plantilla or "Vacío")
            _avisar(f"Tablero «{n}» creado" + ("." if not T[n]["graficos"] else f" con la plantilla «{plantilla}»."))
            _ir(n, tb_nuevo="")
    with c.popover("Opciones del tablero", icon=":material/tune:", width="stretch"):
        st.markdown(f"**{_h.escape(activo)}**")
        otro = st.text_input("Nuevo nombre", key="tb_renombre", placeholder=activo)
        if st.button("Renombrar", key="tb_renombrar", width="stretch"):
            n = (otro or "").strip()
            if not n:
                st.warning("Escriba el nuevo nombre del tablero.")
                return activo
            if n != activo:
                n = TB.nombre_libre(n, [k for k in T if k != activo])
                orden = [(n if k == activo else k, v) for k, v in T.items()]
                T.clear(); T.update(orden)
            _ir(n, tb_renombre="")
        if st.button("Duplicar", key="tb_duplicar", icon=":material/content_copy:", width="stretch"):
            n = TB.nombre_libre(f"{activo} (copia)", T)
            T[n] = copy.deepcopy(T[activo])
            _avisar(f"Tablero «{n}» creado como copia de «{activo}».")
            _ir(n)
        st.divider()
        pl_otra = st.selectbox("Cambiar los gráficos por la plantilla", [p for p in TB.PLANTILLAS if p != "Vacío"], key="tb_plantilla_otra")
        if st.button("Aplicar la plantilla", key="tb_aplicar", width="stretch"):
            T[activo] = TB.tablero_nuevo(pl_otra or "Resumen de planta", T[activo]["columnas"])
            _avisar(f"El tablero «{activo}» quedó con la plantilla «{pl_otra}».")
            _ir(activo)
        if st.button("Vaciar el tablero", key="tb_vaciar", width="stretch", disabled=not T[activo]["graficos"]):
            T[activo]["graficos"] = []
            _ir(activo)
        st.divider()
        if st.button("Quitar este tablero", key="tb_quitar", icon=":material/delete:", width="stretch", disabled=len(T) <= 1,
                     help="Debe quedar al menos un tablero." if len(T) <= 1 else None):
            T.pop(activo, None)
            _avisar(f"Tablero «{activo}» quitado.")
            _ir(next(iter(T)))
    return activo


# ----------------------------------------------------------------------------------------------- biblioteca visual
def _tarjeta_html(i: str, esta: bool) -> str:
    marca = ('<span style="position:absolute;top:6px;right:6px;background:#1b7a5a;color:#fff;font-size:0.72rem;font-weight:600;'
             'padding:2px 8px;border-radius:999px;box-shadow:0 1px 2px rgba(0,0,0,.2)">En el tablero</span>') if esta else ""
    borde = "outline:2px solid #1b7a5a;outline-offset:-2px;" if esta else ""
    img = TB.svg_como_img(TB.miniatura_svg(i), "Miniatura: " + TB.TITULO[i])
    return (f'<div style="position:relative;border-radius:8px;overflow:hidden;{borde}">{img}{marca}</div>'
            f'<div style="font-weight:600;line-height:1.25;margin-top:6px;min-height:2.5em">{_h.escape(TB.TITULO[i])}</div>'
            f'<div style="font-size:0.8rem;opacity:0.78;line-height:1.3;margin-top:2px;min-height:3.9em">{_h.escape(TB.descripcion(i))}</div>'
            f'<div style="font-size:0.72rem;opacity:0.6;margin-top:2px">Datos de {_h.escape(TB.NOMBRE_FUENTE.get(TB.FUENTE[i], ""))}</div>')


def _tarjetas(ids: list, tab: dict, activo: str):
    """Grilla de tarjetas de la biblioteca con su botón «Agregar» o «Quitar»."""
    en = set(TB.ids_tablero(tab))
    for k in range(0, len(ids), COLS_BIB):
        cols = st.columns(COLS_BIB, gap="small")
        for col, i in zip(cols, ids[k:k + COLS_BIB]):
            with col:
                with st.container(border=True):
                    st.html(_tarjeta_html(i, i in en))
                    if i in en:
                        if st.button("Quitar", key=f"tb_bib_{i}", icon=":material/remove:", type="tertiary", width="stretch",
                                     help=f"Quitar «{TB.TITULO[i]}» del tablero «{activo}»"):
                            TB.quitar_grafico(tab, i)
                            _avisar(f"«{TB.TITULO[i]}» quitado del tablero «{activo}».")
                            st.rerun()
                    elif st.button("Agregar", key=f"tb_bib_{i}", icon=":material/add:", width="stretch",
                                   help=f"Agregar «{TB.TITULO[i]}» al final del tablero «{activo}»"):
                        TB.agregar_grafico(tab, i)
                        _avisar(f"«{TB.TITULO[i]}» agregado al final del tablero «{activo}».")
                        st.rerun()


def _biblioteca(tab: dict, activo: str):
    with st.container(border=True):
        C.ayuda("Como la biblioteca de tableros de FlexSim: cada tarjeta muestra la forma del gráfico (un dibujo, sin datos), para qué "
                "sirve y de qué pestaña saca sus datos. «Agregar» lo pone al final del tablero elegido arriba; la marca verde "
                "«En el tablero» indica los que ya están. El buscador mira el nombre, la descripción, la categoría y la forma "
                "(por ejemplo: torta, Gantt, OEE, camiones, tanque).", f"Biblioteca de gráficos para «{activo}»", 4)
        texto = st.text_input("Buscar gráfico", key="tb_buscar", placeholder="Buscar: torta, Gantt, OEE, camiones, tanque…",
                              icon=":material/search:", label_visibility="collapsed")
        if (texto or "").strip():
            ids = TB.buscar_graficos(texto)
            if ids:
                st.caption(f"{len(ids)} gráficos con «{texto.strip()}».")
                _tarjetas(ids, tab, activo)
            else:
                st.info(f"Ningún gráfico coincide con «{texto.strip()}». Pruebe con otra palabra o borre la búsqueda.")
            return
        cats = TB.biblioteca_por_categoria()
        for pest, ids in zip(st.tabs(list(cats), key="tb_bib_cat"), cats.values()):
            with pest:
                _tarjetas(ids, tab, activo)


# ----------------------------------------------------------------------------------------------- datos
def _demo(op, pl):
    """Nueve turnos de demostración sobre copias de la operación y de la planta: ss.op y ss.pl no cambian."""
    ss = st.session_state; p2 = copy.deepcopy(pl)
    o2 = OP.Operacion.desde_dict(copy.deepcopy(op.a_dict()))
    meta = float(ss.get("op_meta", 90.0)) / 100
    for i in range(N_DEMO):
        OP.correr_turno(o2, p2, meta, None, "preventivo" if i == N_DEMO // 2 else "ninguno")
    ss.tb_demo = dict(rubro=pl.rubro, turnos=o2.turnos, pl=p2)


def _extra_llegadas() -> dict:
    dist = (st.session_state.get("distribuciones") or {}).get("descarga_h")
    if dist and TB.acepta(TM.llegadas_temporada, "dist_descarga"):
        return dict(dist_descarga=dist)
    return {}


def _contexto(pl, turnos, pl_turnos, ids: list, equipos: list | None) -> dict:
    """Operación con la planta de los turnos (la de la sesión o la copia de demostración); temporada, dinámica y línea con la de
    la sesión. La línea usa st.session_state.linea_resultado y no se simula aquí sin el botón."""
    fuentes = {TB.FUENTE[i] for i in ids} | ({"temporada"} if "ind_oee" in ids else set())
    temporada = (st.session_state.get("temporada") or {}).get(pl.rubro); r = C.resumen_o_nada()
    ctx = TB.contexto(pl_turnos, turnos, None, equipos, necesita={"operacion"} & fuentes)
    if fuentes - {"operacion"}:
        otro = TB.contexto(pl, [], equipos=equipos, resumen=r, temporada=temporada, extra_llegadas=_extra_llegadas(),
                           necesita=fuentes - {"operacion"}, linea=st.session_state.get("linea_resultado"), simular_linea=False)
        for k in ("programa", "llegadas", "dinamica", "secado", "linea", "linea_equipos"):
            ctx[k] = otro[k]
        ctx["avisos"].update(otro["avisos"])
    return ctx


def _linea(pl, T: dict):
    """PAT 134: estado del resultado de la Línea y botón para simular 72 h con los valores por defecto si falta."""
    ss = st.session_state
    if not any(TB.FUENTE.get(i) == "linea" for v in T.values() for i in TB.ids_tablero(v)):
        return
    res = ss.get("linea_resultado"); a, b = st.columns([3, 1])
    if TB.linea_vale(res, pl):
        p = res.get("parametros") or {}
        a.caption(f"Datos de la Línea: simulación de {C.fmt(p.get('horas'), 0)} h con *ticks* de {C.fmt(p.get('tick_min'), 1)} min "
                  "(pestaña Línea).")
    else:
        a.info("Los gráficos de la Línea necesitan una simulación: hágala en la pestaña Línea o simule 72 h con los valores por defecto.")
    if b.button("Simular la línea 72 h (valores por defecto)", key="tb_linea_boton", width="stretch"):
        try:
            with st.spinner("Simulando la línea…"):
                ss.linea_resultado = TB.simular_linea_defecto(pl, 72.0)
        except ValueError as e:
            st.error(str(e)); return
        ss.pop("ln_firma", None)            # la pestaña Línea vuelve a simular con sus parámetros al abrirla
        st.rerun()


# ----------------------------------------------------------------------------------------------- dibujo
def _acciones(w: dict, g: dict, n: int, total: int, tab: dict, activo: str, columnas: int):
    """Botones pequeños de cada gráfico: subir, bajar, ancho completo o medio y quitar."""
    i = w["id"]
    with st.container(horizontal=True, horizontal_alignment="right", gap="small"):
        sube = st.button("", key=f"tb_sube_{i}", icon=":material/arrow_upward:", type="tertiary", disabled=n == 0, help="Subir")
        baja = st.button("", key=f"tb_baja_{i}", icon=":material/arrow_downward:", type="tertiary", disabled=n >= total - 1, help="Bajar")
        completo = g["ancho"] == "completo"
        ancho = st.button("", key=f"tb_ancho_{i}", icon=":material/close_fullscreen:" if completo else ":material/open_in_full:",
                          type="tertiary", disabled=columnas == 1,
                          help=("Medio ancho" if completo else "Ancho completo") + (" (en el diseño de dos columnas)" if columnas == 1 else ""))
        quita = st.button("", key=f"tb_quita_{i}", icon=":material/close:", type="tertiary", help="Quitar del tablero")
    if sube or baja:
        TB.mover_grafico(tab, i, -1 if sube else 1); st.rerun()
    if ancho:
        TB.alternar_ancho(tab, i); st.rerun()
    if quita:
        TB.quitar_grafico(tab, i)
        _avisar(f"«{w['titulo']}» quitado del tablero «{activo}».")
        st.rerun()


def _dibujar(w: dict, g: dict | None = None, n: int = 0, total: int = 1, tab: dict | None = None, activo: str = "", columnas: int = 2):
    with st.container(border=True):
        a, b = st.columns([2, 1], vertical_alignment="center")
        texto = TB.ayuda_grafico(w["id"]) + ("\n\n" + w["nota"] if w.get("nota") else "")
        with a:
            C.ayuda(C.esc(texto), C.esc(w["titulo"]), 5)        # título con su «?»
        if tab is not None and g is not None:
            with b:
                _acciones(w, g, n, total, tab, activo, columnas)
        for av in w["avisos"]:
            st.info(av)
        if w["tarjetas"]:
            tj = w["tarjetas"]
            for k in range(0, len(tj), 2):
                cols = st.columns(2)
                for col, t in zip(cols, tj[k:k + 2]):
                    col.metric(t["nombre"], C.pct(t["valor"]) if t.get("tipo") == "pct" else C.fmt(t["valor"]), t.get("nota"), delta_color="off")
        svgs = [w["svg"]] if isinstance(w["svg"], str) else (w["svg"] or [])
        if w["id"] in TB.MULTIPLES and len(svgs) > 1:
            ancho = columnas == 1 or (g is not None and g.get("ancho") == "completo")
            por_fila = (4 if w["id"] == "estado_torta" else 3) if ancho else 2
            for k in range(0, len(svgs), por_fila):
                cols = st.columns(por_fila)
                for col, s in zip(cols, svgs[k:k + por_fila]):
                    with col:
                        st.html(TB.svg_como_img(s, w["titulo"]))
        else:
            for s in svgs:
                st.html(TB.svg_como_img(s, w["titulo"]))
        if w["tabla"]:
            C.mostrar_tabla(*w["tabla"])


def _vacio(activo: str):
    st.info(f"El tablero «{activo}» está vacío. Agregue gráficos desde la «Biblioteca de gráficos» de arriba con «Agregar», "
            "o elija una plantilla en «Opciones del tablero».", icon=":material/arrow_upward:")


def mostrar():
    ss = st.session_state; pl = C.planta()
    C.ayuda("Como los tableros de FlexSim: arriba elige el tablero (o crea uno nuevo, con o sin plantilla); en la biblioteca agrega "   # PAT 134
            "gráficos con su tarjeta; en el tablero cada gráfico tiene botones para subir, bajar, ancho completo o medio y quitar, y "
            "su «?» explica cómo leerlo. Los estados por equipo salen de los turnos de Operación; el programa, la cola y las "
            "esperas, de la pestaña Temporada; el arranque y el secado, de la pestaña Dinámica. Cada tablero queda guardado en la "
            "sesión.\n\n"
            "Dos vistas de los estados por equipo: la de turnos de Operación (categoría Estado) reparte las horas de cada turno en "
            "estados con reglas declaradas, porque Operación no registra la hora de cada evento; la de la Línea (categoría Línea, "
            "estados reales) los simula por *ticks*, con tanques pulmón y fallas, y cada cambio de estado tiene su hora real.",
            "Tableros", 3)
    _pendientes()
    if not C.exigir_resuelta():
        return
    aviso = ss.pop("tb_aviso", None)
    if aviso:
        st.toast(aviso)
    op = C.operacion()
    demo = ss.get("tb_demo")
    if demo and demo.get("rubro") != pl.rubro:
        ss.pop("tb_demo", None); demo = None
    if op.turnos:
        turnos, pl_turnos, origen = op.turnos, pl, f"{len(op.turnos)} turnos de la pestaña Operación"
    elif demo:
        turnos, pl_turnos, origen = demo["turnos"], demo["pl"], f"{len(demo['turnos'])} turnos de demostración (la Operación no cambia)"
    else:
        turnos, pl_turnos, origen = [], pl, None
    a, b = st.columns([3, 1])
    if origen:
        a.caption("Datos de Operación: " + origen + ".")
    else:
        a.info(f"La Operación está vacía: ejecute turnos en la pestaña Operación o simule {N_DEMO} turnos de demostración.")
    if not op.turnos:
        if b.button(f"Simular {N_DEMO} turnos de demostración", key="tb_demo_boton", width="stretch", type="primary" if not demo else "secondary"):
            try:
                _demo(op, pl)
            except ValueError as e:
                st.error(str(e)); return
            st.rerun()

    T = _tableros()
    activo = _cabecera(T)
    tab = T[activo]
    ids = TB.ids_tablero(tab)
    if not ids:                                   # tablero vacío: la biblioteca se abre y queda abierta mientras se arma
        ss.tb_bib_ver = True
    elif "tb_bib_ver" not in ss:
        ss.tb_bib_ver = False
    ver = st.toggle("Mostrar la biblioteca de gráficos", key="tb_bib_ver",
                    help="Se abre sola cuando el tablero está vacío y queda abierta hasta que la cierre.")
    if ver or not ids:
        _biblioteca(tab, activo)
    _linea(pl, T)
    ln = OP.linea(pl_turnos)
    todos = TB.equipos_linea(pl_turnos, ln) if ln else []
    if ss.get("tb_diseno_de") != activo or ss.get("tb_diseno") not in DISENOS:
        ss.tb_diseno = DISENOS[tab["columnas"] - 1]; ss.tb_diseno_de = activo
    a, b = st.columns([3, 1], vertical_alignment="bottom")
    equipos = a.multiselect("Equipos que miran los gráficos de estado", todos, default=todos, key=f"tb_eq_{pl.rubro}",
                            format_func=lambda k: f"{k} · {pl_turnos.equipos[k].nombre}" if k in pl_turnos.equipos else k,
                            placeholder="Todos los equipos") or todos
    with b:
        diseno = st.segmented_control("Diseño", DISENOS, key="tb_diseno", required=True)
    tab["columnas"] = 1 if diseno == DISENOS[0] else 2
    columnas = tab["columnas"]
    # todos los tableros se arman con un solo contexto, para mostrar el activo y exportarlos todos
    todos_ids = list(dict.fromkeys(i for v in T.values() for i in TB.ids_tablero(v)))
    ctx = _contexto(pl, turnos, pl_turnos, todos_ids, equipos)
    hechos = {}

    def widget(i):
        if i not in hechos:
            try:
                hechos[i] = TB.construir(i, ctx)
            except Exception as e:                 # un gráfico que falla no bota el tablero
                hechos[i] = TB._w(i, avisos=[f"No se pudo armar el gráfico: {e}"])
        return hechos[i]

    if not ids:
        _vacio(activo)
    total = len(tab["graficos"]); pos = {g["id"]: n for n, g in enumerate(tab["graficos"])}
    for fila in TB.filas_grilla(tab, columnas):
        if columnas == 1 or (len(fila) == 1 and fila[0]["ancho"] == "completo"):
            g = fila[0]
            _dibujar(widget(g["id"]), g, pos[g["id"]], total, tab, activo, columnas)
            continue
        cols = st.columns(2, gap="medium")
        for col, g in zip(cols, fila):
            with col:
                _dibujar(widget(g["id"]), g, pos[g["id"]], total, tab, activo, columnas)
    ws = [widget(i) for i in ids]

    C.ayuda("El HTML junta todos los tableros guardados con sus gráficos, tarjetas y tablas, como «Export All Dashboards to HTML» de FlexSim, "   # PAT 134
            "con el ancho de cada gráfico y el diseño del tablero elegido. El CSV usa punto y coma y coma decimal, para abrirlo en Excel.", "Exportar")
    todos_ws = {nombre: [dict(widget(g["id"]), ancho=g["ancho"]) for g in v["graficos"]] for nombre, v in T.items()}
    d1, d2 = st.columns(2)
    d1.download_button("Descargar todos los tableros (HTML)", TB.exportar_html(todos_ws, f"Tableros de la planta ({pl.rubro})", columnas),
                       file_name=f"tableros_{pl.rubro}.html", mime="text/html", key="tb_html", width="stretch")
    d2.download_button("Descargar los datos del tablero (CSV)", TB.exportar_csv(ws).encode("utf-8-sig"), file_name=f"tablero_{pl.rubro}.csv",
                       mime="text/csv", key="tb_csv", width="stretch", disabled=not ws)
    with st.expander("Reglas de los estados por equipo"):
        C.mostrar_tabla([dict(n=s.nombre, j=s.justificacion) for s in TB.REGLAS.values()], [("n", "Regla", "txt", 0), ("j", "Justificación", "txt", 0)])
        st.caption(TB.FUENTE_OEE + ".")
