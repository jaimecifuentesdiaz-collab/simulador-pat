"""Pestaña Diseño: simulador de planta interactivo (PAT 128).

El lienzo (ui/lienzo.py y ui/componentes/lienzo_planta/index.html) funciona como el «Diseño libre» del simulador del
profesor (Scorm_pellet_profesor.html): se arrastran equipos del catálogo, se mueven, se conectan arrastrando de puerto
a puerto y se editan repartos y capacidades con recálculo inmediato. Cada acción llega como evento y la aplica
pat_sim.motor.lienzo.aplicar_evento; la pestaña corre dentro de un fragmento, así que solo ella se vuelve a ejecutar.
Debajo quedan, a todo el ancho, la tabla de corrientes, la utilización, el formulario con todos los parámetros y el
diagrama ISO 10628 con instrumentos (planta_svg) para el informe.
PAT 133: deshacer, rehacer y duplicar. Cada evento que cambia la planta apila el estado anterior en un historial con tope
(pat_sim.motor.lienzo.Historial, en st.session_state.lienzo_historial); el lienzo envía «deshacer», «rehacer» y «duplicar».
PAT 134: el catálogo suma «Instrumentación ISA-5.1 y ISA-5.4»: burbujas, elementos primarios y finales y elementos de lazo que
se sueltan en el lienzo, se editan en Propiedades y se unen con líneas de señal (pat_sim.motor.instrumentacion). Un parámetro
escrito fuera de rango vuelve con el aviso «Mínimo …» y el campo muestra el valor que usó el motor.
"""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import TIPOS, RUBROS, catalogo
from pat_sim.motor import lienzo as LZ
from pat_sim.simbolos import iso10628
from pat_sim.motor.diagrama import planta_svg
from pat_sim.motor.corrientes import TIPOS as TIPOS_CORRIENTE
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from . import lienzo as L


def tabla_corrientes(pl) -> list[dict]:
    filas = []
    for c in pl.conexiones:
        s = pl.salidas.get((c.origen, c.puerto_origen)) if pl.resuelta else None
        tipo = pl.tipo_conexion(c)
        f = dict(n=c.nombre or "", de=f"{c.origen} · {pl.equipos[c.origen].nombre}", a=f"{c.destino} · {pl.equipos[c.destino].nombre}",
                 tipo=TIPOS_CORRIENTE[tipo][0], reparto=c.reparto, m=None, T=None, brix=None, hum=None, q=None)
        if pl.resuelta:
            if pl.es_servicio(c):
                r = pl.equipos[c.destino].resultado
                f["q"] = (r.servicios.get(c.puerto_origen + "_kW") if r else None) or None     # vapor (tomate) o calor (secado)
            elif s is not None:
                s = s.fraccion(c.reparto / 100)
                if s.tipo in ("biomasa",) or (s.tipo == "subproducto" and s.fase == "solido"):   # biomasa: humedad en base húmeda
                    f.update(m=s.m, T=s.T, hum=100 * (1 - s.x) if s.m else None)
                else:
                    f.update(m=s.m, T=s.T, brix=s.brix if s.s else None)
        filas.append(f)
    return filas


COLS_CORRIENTES = [("n", "N.º", "txt", 0), ("de", "De", "txt", 0), ("a", "A", "txt", 0), ("tipo", "Tipo", "txt", 0), ("reparto", "Reparto (%)", "num", 1),
                   ("m", "Caudal (kg/h)", "num", 0), ("T", "T (°C)", "num", 1), ("brix", "°Brix", "num", 2), ("hum", "Humedad (%)", "num", 1),
                   ("q", "Calor (kW)", "num", 0)]


COLS_CAPACIDAD = [("eq", "Equipo", "txt", 0), ("nombre", "Nombre", "txt", 0), ("ent", "Entrada (t/h)", "num", 2), ("sal", "Salida (t/h)", "num", 2),
                  ("cap", "Capacidad nominal (t/h)", "num", 1), ("estado", "Estado", "num", 2), ("ef", "Capacidad efectiva (t/h)", "num", 1),
                  ("proc", "Procesado (t/h)", "num", 2), ("util", "Utilización (%)", "num", 1), ("acum", "Acumulación (t/h)", "num", 2),
                  ("cierre", "Cierre de energía (kW)", "num", 3)]


def tabla_capacidad(pl) -> list[dict]:
    """Como la tabla «Balance por equipo» del simulador del profesor, con la capacidad efectiva y el cierre de energía."""
    from pat_sim.motor.planta import TIPOS_SERVICIO
    tr = LZ.restricciones(pl, pl) or {"equipos": {}}
    filas = []
    for k, eq in pl.equipos.items():
        r = eq.resultado
        if r is None or eq.tipo.startswith("caldera"):
            continue
        v = tr["equipos"].get(k, {})
        sal = sum(pl.salidas[(k, p.nombre)].m for p in eq.salidas if p.tipo not in TIPOS_SERVICIO and (k, p.nombre) in pl.salidas) / 1000
        filas.append(dict(eq=k, nombre=eq.nombre, ent=r.detalle.get("carga_t_h"), sal=sal,
                          cap=eq.params["capacidad"].valor if "capacidad" in eq.params else None,
                          estado=eq.params["estado"].valor if "estado" in eq.params else None, ef=v.get("efectiva"),
                          proc=v.get("procesado"), util=100 * v["util_demanda"] if v.get("util_demanda") is not None else None,
                          acum=v.get("sobrecarga") if v.get("efectiva") else None, cierre=r.cierre_energia()))
    return filas


def _avisar(msg: str):
    """Guarda un mensaje y vuelve a ejecutar toda la aplicación (las otras pestañas también usan la planta)."""
    st.session_state.aviso_diseno = msg
    st.rerun()


@st.cache_data(show_spinner=False)
def _catalogo_lienzo() -> dict:
    return LZ.catalogo_lienzo(RUBROS, catalogo)


TOPE_HISTORIAL = 30          # PAT 133: pasos de deshacer que se guardan (Supuesto: suficiente para una sesión de diseño)


def _historial(pl) -> "LZ.Historial":
    """Historial de deshacer y rehacer de la planta actual; se reinicia cuando se carga otra planta (otro rubro o versión)."""
    ss = st.session_state
    marca = getattr(pl, "_marca_historial", None)        # la planta lleva una marca; una planta nueva no la tiene
    if ss.get("lienzo_historial") is None or marca is None or marca != ss.get("lienzo_historial_marca"):
        marca = ss["lienzo_historial_marca"] = int(ss.get("lienzo_historial_marca") or 0) + 1
        pl._marca_historial = marca
        ss.lienzo_historial = LZ.Historial(TOPE_HISTORIAL)
    return ss.lienzo_historial


def _procesar_eventos(pl):
    """Aplica los eventos del lienzo que todavía no se han procesado y recalcula una sola vez."""
    ss = st.session_state
    ultimo = int(ss.get("lienzo_seq", 0))
    evs = L.eventos_nuevos(ss.get(L.CLAVE), ultimo)
    if not evs:
        return False
    recalcular = False; restaurada = False
    hist = _historial(pl)
    msgs = ss.setdefault("lienzo_mensajes", [])
    for ev in evs:                                   # sin llamadas a Streamlit en el ciclo: no se interrumpe a medias
        r = _guardar(pl) if ev.get("evento") == "guardar" else LZ.aplicar_con_historial(pl, ev, hist, TIPOS)
        restaurada = restaurada or bool(r.get("restaurada"))
        ss.lienzo_seq = int(ev["seq"])
        recalcular = recalcular or r["recalcular"]
        if r.get("mensaje"):
            msgs.append(dict(seq=int(ev["seq"]), texto=r["mensaje"], tipo=r.get("tipo") or ("ok" if r["ok"] else "error"), id=r.get("id"),
                             sel=r.get("sel")))          # PAT 134: «aviso» de rango y selección de un instrumento
    del msgs[:-6]
    # el formulario de abajo guarda sus valores en la sesión: se borran para que muestre lo que se cambió en el lienzo
    tocados = {(e.get("datos") or {}).get("id") for e in evs} - {None}
    for k in [k for k in ss.keys() if isinstance(k, str) and k.startswith(("par_", "nom_", "x_", "y_"))]:
        if k == "par_eq":
            continue
        if restaurada or any(k.startswith(f"{p}_{i}") for i in tocados for p in ("par", "nom", "x", "y")):
            del ss[k]
    if ss.get("par_eq") is not None and ss.get("par_eq") not in pl.equipos:
        del ss["par_eq"]
    return recalcular


def _guardar(pl) -> dict:
    """Botón «Guardar versión» del lienzo: lo mismo que el botón de la barra lateral."""
    from pat_sim.motor.resumen import resumen_planta
    ss = st.session_state; bd = C.obtener_bd()
    try:
        if not ss.get("pid"):
            ss.pid = bd.crear_proyecto(pl.nombre if bd.obtener_proyecto(pl.nombre) is None else f"{pl.nombre} ({len(bd.listar_proyectos()) + 1})", pl.rubro)
        v = bd.guardar_version(ss.pid, pl, "Guardada desde el simulador de Diseño")
        ss.vid = v["id"]
        if pl.resuelta:
            bd.guardar_corrida(v["id"], resumen_planta(pl, cop=ss.cop))
        return dict(ok=True, mensaje=f"Guardada la versión {v['numero']}" + (" con su corrida." if pl.resuelta else " (planta sin resolver, sin corrida)."), recalcular=False)
    except Exception as e:
        return dict(ok=False, mensaje=f"No se pudo guardar: {e}", recalcular=False)


def _resolver(pl):
    """Resuelve la planta; si falta algo, resuelve la parte alimentada para que el lienzo siga mostrando flujos."""
    sol, motivo = LZ.resolver_parcial(pl)
    st.session_state.error_resolucion = motivo
    return sol, motivo


def _kpis_recuperacion(pl) -> dict:
    if not pl.resuelta:
        return {}
    try:
        r = C.resumen_actual()
    except Exception:
        return {}
    if r.get("sin_sumidero"):
        return dict(sin_sumidero=True)
    return dict(cascada_kW=float(r["cascada"]), cobertura=float(r["cobertura_cascada"]), sumidero=r["sumidero"]["nombre"],
                sumidero_kW=float(r["Qsumidero"]))


@st.fragment
def mostrar():
    pl = C.planta(); ss = st.session_state
    st.subheader("Diseño de la planta")
    if ss.get("aviso_diseno"):
        st.success(ss.pop("aviso_diseno"))
    _procesar_eventos(pl)
    sol, motivo = _resolver(pl)          # 1 ms con la planta basada en Agrozzi: se resuelve en cada ejecución
    datos = LZ.datos_lienzo(pl, sol, motivo, _catalogo_lienzo(), int(ss.get("lienzo_seq", 0)), ss.get("lienzo_mensajes", []),
                            _kpis_recuperacion(pl), _historial(pl).resumen())
    L.lienzo(datos)
    C.ayuda("- Arrastre equipos desde el catálogo al lienzo; conéctelos arrastrando desde un puerto de salida "   # PAT 134: ayuda «?»
            "(círculo a la derecha del equipo) hasta uno de entrada (a la izquierda); haga clic en un equipo o en una línea para "
            "editar sus propiedades, que se recalculan al instante.\n"
            "- Ctrl+Z deshace, Ctrl+Y o Ctrl+Mayús+Z rehace, Ctrl+C y Ctrl+V "
            "copian y pegan el equipo seleccionado (con sus parámetros y sin sus conexiones).\n"
            "- Símbolos de la ISO 10628 (UNE-EN ISO 10628:2001, Tabla C.1 y letras código del Anexo D).\n"
            "- Instrumentos: elija «Instrumentación ISA-5.1 y ISA-5.4» en el catálogo, suelte el símbolo "
            "sobre el equipo, escriba sus letras en Propiedades y únalo arrastrando desde su punto azul hasta un equipo, una corriente "
            "u otro instrumento; el tipo de señal se elige arriba del lienzo (ISA-5.1, tutorial de Carballo y Romero, 2011: Tablas 4, "
            "15 y 17; diagrama de lazo con la estructura de ISA-5.4).")
    _tablas(pl)                     # tablas a todo el ancho, debajo del lienzo
    _parametros(pl)
    _diagrama(pl)


def _parametros(pl):
    if not pl.equipos:
        return
    with st.expander("Todos los parámetros de un equipo (formulario)", expanded=False):
        k = st.selectbox("Equipo", list(pl.equipos), format_func=lambda k: f"{k} · {pl.equipos[k].nombre}", key="par_eq")
        eq = pl.equipos[k]
        st.caption(f"{eq.nombre_tipo} · símbolo {iso10628.SIMBOLOS.get(eq.simbolo, ('',))[0]} · ISO 10628 categoría {eq.iso_categoria}, letra {eq.iso_letra}")
        fijados = {(e.equipo_var, e.param): e for e in pl.especs}
        with st.form(f"form_{k}"):
            nnombre = st.text_input("Nombre del equipo", value=eq.nombre, key=f"nom_{k}")
            nuevos = {}
            c1, c2 = st.columns(2)
            for n_, (clave, p) in enumerate(eq.params.items()):
                with (c1 if n_ % 2 == 0 else c2):
                    esp = fijados.get((k, clave))
                    et = f"{p.nombre} [{p.unidad}]" if p.unidad else p.nombre
                    key = f"par_{k}_{clave}"
                    ayuda = f"Categoría: {p.categoria}. Fuente: {p.fuente or '—'}." + (f" Justificación: {p.justificacion}" if p.justificacion else "")
                    v = p.valor
                    if esp is not None:
                        st.number_input(et + " (lo calcula la especificación de diseño)", value=float(v), disabled=True, key=key, help=ayuda)
                    elif isinstance(v, bool):
                        nuevos[clave] = st.checkbox(et, value=v, key=key, help=ayuda)
                    elif isinstance(v, int):
                        lo = int(p.minimo) if p.minimo is not None else None; hi = int(p.maximo) if p.maximo is not None else None
                        nuevos[clave] = st.number_input(et, value=v, min_value=lo, max_value=hi, step=1, key=key, help=ayuda)
                    elif isinstance(v, float) or v is None:
                        nuevos[clave] = st.number_input(et, value=None if v is None else float(v),
                                                        min_value=None if p.minimo is None else float(p.minimo),
                                                        max_value=None if p.maximo is None else float(p.maximo), format="%g", key=key, help=ayuda)
                    else:
                        nuevos[clave] = st.text_input(et, value=str(v), key=key, help=ayuda)
                    st.caption(f"{p.categoria} · {p.fuente or 'sin fuente'}")
            xx, yy = st.columns(2)
            nx = xx.number_input("Posición x en el diagrama", value=float(eq.x), step=20.0, key=f"x_{k}")
            ny = yy.number_input("Posición y en el diagrama", value=float(eq.y), step=20.0, key=f"y_{k}")
            ok = st.form_submit_button("Aplicar parámetros y recalcular", type="primary")
        if ok:
            antes = LZ.instantanea(pl)          # PAT 133: el formulario también se puede deshacer desde el lienzo
            if nnombre.strip() and nnombre.strip() != eq.nombre:
                eq.nombre = nnombre.strip()
            for clave, v in nuevos.items():
                if v != eq.params[clave].valor:
                    eq.set(clave, v)
            eq.x, eq.y = nx, ny
            if LZ.instantanea(pl) != antes:
                _historial(pl).apilar(antes, f"aplicar el formulario de {k}")
            if C.resolver(pl):
                _avisar(f"Parámetros de {k} aplicados y planta recalculada.")


def _diagrama(pl):
    if not pl.equipos:
        return
    with st.expander("Diagrama de flujo ISO 10628 con instrumentos ISA-5.1 (para el informe)", expanded=False):
        a, b, c = st.columns(3)
        ins = a.checkbox("Mostrar instrumentos ISA-5.1", True); num = b.checkbox("Numerar corrientes", True); tab = c.checkbox("Tabla de corrientes en el diagrama", False)
        try:
            svg = planta_svg(pl, instrumentos=ins, numeros=num, tabla=tab and pl.resuelta)
            st.image(svg, width="stretch")
            st.download_button("Descargar el diagrama (SVG)", svg, file_name="PFD_planta.svg", mime="image/svg+xml")
        except Exception as e:
            st.warning(f"El diagrama no se pudo dibujar todavía: {e}")


def _tablas(pl):
    if pl.resuelta:
        AT.tabla("dis_corrientes", "Tabla de corrientes", 4)   # PAT 134: «?» de la tabla
        C.mostrar_tabla(tabla_corrientes(pl), COLS_CORRIENTES)
        if pl.avisos:
            for av in pl.avisos:
                st.warning(av)
        AT.tabla("dis_capacidad", "Balance por equipo y capacidad efectiva (teoría de restricciones)", 4)   # PAT 134: «?» de la tabla
        filas = tabla_capacidad(pl)
        if filas:
            C.mostrar_tabla(filas, COLS_CAPACIDAD)
            if not any(f["cap"] for f in filas):
                st.caption("Ningún equipo tiene capacidad nominal declarada: use «Asignar capacidades» en el lienzo o escríbala en Propiedades.")
    else:
        C.exigir_resuelta()
