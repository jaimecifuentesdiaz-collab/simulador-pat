"""Pestaña Diseño: simulador de planta interactivo (PAT 128).

El lienzo (ui/lienzo.py y ui/componentes/lienzo_planta/index.html) funciona como el «Diseño libre» del simulador del
profesor (Scorm_pellet_profesor.html): se arrastran equipos del catálogo, se mueven, se conectan arrastrando de puerto
a puerto y se editan repartos y capacidades con recálculo inmediato. Cada acción llega como evento y la aplica
pat_sim.motor.lienzo.aplicar_evento; la pestaña corre dentro de un fragmento, así que solo ella se vuelve a ejecutar.
Debajo quedan, a todo el ancho, la tabla de corrientes y los catálogos. PAT 140 (16-11-2026): se eliminaron el formulario
«Todos los parámetros de un equipo», el diagrama ISO 10628 de esta pantalla y la tabla «Balance por equipo y capacidad efectiva»;
todos los parámetros (también las etiquetas de texto) se editan en el cuadro «Propiedades» del lienzo, la posición se cambia
arrastrando el equipo y la utilización se ve por colores en el lienzo.
PAT 133: deshacer, rehacer y duplicar. Cada evento que cambia la planta apila el estado anterior en un historial con tope
(pat_sim.motor.lienzo.Historial, en st.session_state.lienzo_historial); el lienzo envía «deshacer», «rehacer» y «duplicar».
PAT 134: el catálogo suma «Instrumentación ISA-5.1 y ISA-5.4»: burbujas, elementos primarios y finales y elementos de lazo que
se sueltan en el lienzo, se editan en Propiedades y se unen con líneas de señal (pat_sim.motor.instrumentacion). Un parámetro
escrito fuera de rango vuelve con el aviso «Mínimo …» y el campo muestra el valor que usó el motor.
PAT 135: la planta lleva la tabla de precedencia del mantenedor (pl.precedencia): el lienzo rechaza las conexiones que se
saltan etapas del proceso, con un mensaje que nombra las que faltan, y la misma regla rige «Secuencia sugerida» y «Diagnóstico».
El catálogo del lienzo deja solo «Todos los equipos (ISO 10628)» e «Instrumentación ISA-5.1 y ISA-5.4».
PAT 136 (T22, comentarios del profesor Torres del 13-11-2026): la pantalla parte en carta en blanco del tipo de planta de la
asignación o del desafío (punto 5) y trae «Armar planta automáticamente» (motor/sintesis.py, punto 6) y los ejemplos de los cuatro
rubros; el catálogo del lienzo y el buscador de abajo ordenan los equipos por función y familia ISO 10628 (punto 7); la precedencia
cubre las 10 plantas (punto 8); y el formulario de parámetros aplica cada cambio al instante sobre la planta única (punto 12).
"""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos.registro import TIPOS, RUBROS, catalogo
from pat_sim.motor import lienzo as LZ
from pat_sim.motor.corrientes import TIPOS as TIPOS_CORRIENTE
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from . import lienzo as L
from . import validacion as VAL     # PAT 143: validador del diseño y botón «Pista»


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


def _avisar(msg: str):
    """Guarda un mensaje y vuelve a ejecutar toda la aplicación (las otras pestañas también usan la planta)."""
    st.session_state.aviso_diseno = msg
    st.rerun()


@st.cache_data(show_spinner=False)
def _catalogo_lienzo() -> dict:
    # PAT 135 (capturas de Jaime): la lista desplegable queda con dos opciones, todos los equipos e instrumentación
    # PAT 136 (T22, punto 7): más una lista por tipo de planta y una por función de proceso, y el buscador del lienzo
    return LZ.catalogo_taxonomia(catalogo)


def _precedencia():
    """PAT 135: tabla de estados y precedencia del mantenedor (con la opción «Permitir conexiones libres»).
    PAT 136 (punto 8): más los estados y la cadena de los seis tipos de planta nuevos (motor/precedencia.tabla_plantas)."""
    from pat_sim.motor import precedencia as PR
    try:
        from pat_sim.datos import mantenedor as MANT
        base = MANT.tabla_precedencia(C.obtener_bd())
    except Exception:
        base = None
    try:
        return PR.tabla_plantas(base)
    except Exception:
        return base


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
    recalcular = False
    hist = _historial(pl)
    msgs = ss.setdefault("lienzo_mensajes", [])
    for ev in evs:                                   # sin llamadas a Streamlit en el ciclo: no se interrumpe a medias
        r = _guardar(pl) if ev.get("evento") == "guardar" else LZ.aplicar_con_historial(pl, ev, hist, TIPOS)
        if ev.get("evento") == "agregar" and r.get("ok") and r.get("id") in pl.equipos:   # PAT 135: parámetros por defecto del mantenedor
            try:
                from pat_sim.datos import mantenedor as MANT
                MANT.aplicar_defectos(pl.equipos[r["id"]], C.obtener_bd())
            except Exception:
                pass                                     # sin base queda el valor del catálogo
        ss.lienzo_seq = int(ev["seq"])
        recalcular = recalcular or r["recalcular"]
        if r.get("mensaje"):
            msgs.append(dict(seq=int(ev["seq"]), texto=r["mensaje"], tipo=r.get("tipo") or ("ok" if r["ok"] else "error"), id=r.get("id"),
                             sel=r.get("sel")))          # PAT 134: «aviso» de rango y selección de un instrumento
        if ev.get("evento") == "conectar" and not r.get("ok") and r.get("mensaje"):   # PAT 136: aviso claro también bajo el lienzo
            from pat_sim.motor import precedencia as PR
            ss.aviso_conexion = PR.mensaje_claro(r["mensaje"]) if ("necesita" in r["mensaje"] or "no acepta" in r["mensaje"]) \
                else "No se conectó. " + r["mensaje"]
    del msgs[:-6]
    C.marcar_cambio()                               # PAT 136 (punto 12): la planta única cambió; las demás pantallas se recalculan
    return recalcular


def _guardar(pl) -> dict:
    """Botón «Guardar» del lienzo: lo mismo que «Guardar proyecto» de la barra lateral (PAT 138, ui/proyectos.py): guarda en el
    proyecto abierto o crea uno nuevo con el nombre automático."""
    from . import proyectos as PRY
    r = PRY.guardar(nota="Guardado desde el lienzo de Planta ficticia")
    return dict(ok=r["ok"], mensaje=r["mensaje"], recalcular=False)


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
    st.subheader("Planta ficticia: diseño de la planta")
    if ss.get("aviso_diseno"):
        st.success(ss.pop("aviso_diseno"))
    pl = _seguir_asignacion(pl)          # PAT 136: la carta en blanco sigue a la asignación o al desafío
    _partida(pl)                         # PAT 136: carta en blanco, planta automática y ejemplos
    pl.precedencia = _precedencia()      # PAT 135: el motor la toma como atributo de la planta
    pl.conexion_libre = True             # PAT 143: conexión libre; el validador marca lo que no corresponde
    with C.cargando(C.TXT_RECALCULANDO):     # PAT 140: círculo que gira con el motivo si el cálculo se demora
        _procesar_eventos(pl)
        if ss.get("aviso_conexion"):
            st.warning(ss.pop("aviso_conexion"))
        sol, motivo = _resolver(pl)          # 1 ms con la planta basada en Agrozzi: se resuelve en cada ejecución
        res = VAL.revisar("ficticia", motivo=motivo, precedencia=pl.precedencia)     # PAT 143
        datos = LZ.datos_lienzo(pl, sol, motivo, _catalogo_lienzo(), int(ss.get("lienzo_seq", 0)), ss.get("lienzo_mensajes", []),
                                _kpis_recuperacion(pl), _historial(pl).resumen(), libre=True, validacion=res)
    VAL.panel("ficticia", res)           # PAT 143: advertencia que no deja avanzar y botón «Pista», sobre el lienzo
    L.lienzo(datos)
    C.ayuda("- Arrastre equipos desde el catálogo al lienzo; conéctelos arrastrando desde un puerto de salida "   # PAT 134: ayuda «?»
            "(círculo a la derecha del equipo) hasta uno de entrada (a la izquierda); haga clic en un equipo o en una línea para "
            "editar sus propiedades, que se recalculan al instante.\n"
            "- Ctrl+Z deshace, Ctrl+Y o Ctrl+Mayús+Z rehace, Ctrl+C y Ctrl+V "
            "copian y pegan el equipo seleccionado (con sus parámetros y sin sus conexiones).\n"
            "- Símbolos de la ISO 10628 (UNE-EN ISO 10628:2001, Tabla C.1 y letras código del Anexo D).\n"
            "- Conexión libre: se puede unir cualquier salida con cualquier entrada. Si el diseño queda con un error (corrientes de "
            "distinto tipo, orden del proceso, entradas sin alimentación, repartos que no suman 100 %, servicios sin conectar o sin "
            "destino, balances que no cierran), aparece una advertencia sobre el lienzo que no deja pasar a la etapa siguiente y el "
            "botón «Pista» orienta paso a paso; con corrientes de distinto tipo la planta no se calcula.\n"
            "- Instrumentos: elija «Instrumentación ISA-5.1 y ISA-5.4» en el catálogo, suelte el símbolo "
            "sobre el equipo, escriba sus letras en Propiedades y únalo arrastrando desde su punto azul hasta un equipo, una corriente "
            "u otro instrumento; el tipo de señal se elige arriba del lienzo (ISA-5.1, tutorial de Carballo y Romero, 2011: Tablas 4, "
            "15 y 17; diagrama de lazo con la estructura de ISA-5.4).")
    _cadena(pl)                     # PAT 136: precedencia de estados del tipo de planta
    _tablas(pl, res)                # tablas a todo el ancho, debajo del lienzo
    _taxonomia(pl)                  # PAT 136: catálogo por función y familia con buscador
    _informe_sintesis(pl)
    VAL.redibujar_si_cambio("ficticia")    # PAT 143: la franja del proceso se pone al día si cambió el bloqueo


def _tablas(pl, res=None):
    if pl.resuelta:
        AT.tabla("dis_corrientes", "Tabla de corrientes", 4)   # PAT 134: «?» de la tabla
        C.mostrar_tabla(tabla_corrientes(pl), COLS_CORRIENTES)
        if pl.avisos:
            for av in pl.avisos:
                st.warning(av)
    elif res and res.get("errores"):                          # PAT 143: el motivo ya está en la advertencia sobre el lienzo
        st.caption("La tabla de corrientes aparece cuando la planta se pueda calcular.")
    else:
        C.exigir_resuelta()


# ---------------------------------------------------------------- PAT 136 (T22): carta en blanco, planta automática y ejemplos
def _tipos_planta():
    from pat_sim.catalogos import plantas_genericas as PG
    return PG


def _seguir_asignacion(pl):
    """Si la planta es una carta en blanco sin equipos y la sesión tiene otro tipo de planta (asignación o desafío), la carta en
    blanco pasa a ese tipo: no se pierde nada porque está vacía."""
    from pat_sim.motor import sintesis as SI
    if not SI.es_carta_en_blanco(pl):
        return pl
    t, _de = C.tipo_planta_sesion()
    tom = C.tomate_sesion() if t == "tomate" else None          # PAT 138: también si cambió el tipo de planta de tomate del desafío
    aga = SI.agar_de_desafio(st.session_state.get("desafio")) if t == "agar" else None   # PAT 144 a: y la planta de agar del desafío
    if SI.tipo_de(pl) != t or (tom and SI.variante_de(pl) != tom[0]) or (aga and SI.variante_agar_de(pl) != aga[0]):
        C.fijar_planta(C.planta_inicial(t))
        return C.planta()
    return pl


def _partida(pl):
    """Punto de partida del diseño: tipo de planta, demanda, carta en blanco, planta automática y ejemplos."""
    from pat_sim.motor import sintesis as SI, demanda as DM
    PG = _tipos_planta(); ss = st.session_state
    vacia = not pl.equipos
    t_ses, de = C.tipo_planta_sesion()
    t_pl = SI.tipo_de(pl) or t_ses
    if vacia:
        st.info(f"Carta en blanco: {PG.PLANTAS[t_pl]['nombre'] if t_pl in PG.PLANTAS else 'planta'} ({de}). Arrastre equipos desde el "
                "catálogo del lienzo, o arme la planta automáticamente con la demanda y compárela con su diseño.")
    with st.expander("Punto de partida: carta en blanco, planta automática y ejemplos", expanded=vacia):
        C.ayuda("- **Carta en blanco**: la planta queda vacía, del tipo de planta elegido, con su demanda; usted elige los equipos de la "
                "librería y los conecta en el orden del proceso (la precedencia de estados rechaza las conexiones que se saltan etapas).\n"
                "- **Armar planta automáticamente**: toma la cadena de operaciones del tipo de planta, dimensiona cada equipo con la "
                "demanda (capacidad de diseño = percentil o pico de la serie × factor de servicio) y pone la alternativa comercial de menor "
                "costo anual (un equipo o varios en paralelo, con o sin redundancia), que después se revisa en Planta real (Selección de equipos y Costeo).\n"
                "- **Ejemplos**: la planta basada en Agrozzi y los escenarios de pellet, chip y leña, para el docente y para comparar.\n"
                "Todo reemplaza la planta de la sesión, que ven todas las pantallas. Guarde antes una versión si la modificó.",
                "Cómo partir", 5)
        ids = list(PG.IDS_PLANTAS)
        a, b = st.columns(2)
        tipo = a.selectbox("Tipo de planta", ids, index=ids.index(t_pl) if t_pl in ids else 0,
                           format_func=lambda k: PG.PLANTAS[k]["nombre"], key="dis_tipo_planta",
                           help="Por omisión, el de su asignación (pantalla Docente) o el del desafío en curso.")
        # PAT 138: con un desafío de tomate (pantalla Desafío), la llegada de tomate de su tipo de planta y su distribución
        tom = C.tomate_sesion() if tipo == "tomate" else None
        aga = SI.agar_de_desafio(ss.get("desafio")) if tipo == "agar" else None      # PAT 144 a: llegada de alga seca del desafío
        LLEGADA = DM.PERFIL_AGAR if aga else DM.PERFIL_TOMATE
        lleg = tom or aga
        dems = ([LLEGADA] if lleg else []) + list(PG.IDS_DEMANDAS)
        if ss.get("dis_demanda") is not None and ss.get("dis_demanda") not in dems:
            ss.pop("dis_demanda", None)

        def _nom_dem(k):
            if k == LLEGADA and aga:
                from pat_sim.catalogos import plantas_agar as PAG
                return f"Llegada {DM.nombre_distribucion(aga[1], 'agar').lower()} del desafío ({PAG.variante(aga[0])['nombre']})"
            if k == LLEGADA and tom:
                from pat_sim.catalogos import plantas_tomate as PT
                return f"Llegada {DM.DISTRIBUCIONES[tom[1]]['nombre'].lower()} del desafío ({PT.variante(tom[0])['corto']})"
            return PG.DEMANDAS[k]["nombre"]
        d0 = LLEGADA if lleg else C.demanda_sesion(tipo)
        dem = b.selectbox("Demanda", dems, index=dems.index(d0) if d0 in dems else 0, format_func=_nom_dem,
                          key="dis_demanda", help="Perfil de demanda de motor/demanda.py; por omisión, la llegada de tomate del desafío, "
                                                  "el perfil asignado o el natural del rubro.")
        if dem == LLEGADA and aga:
            st.caption("Compatibilidad: Natural. Llegada de alga seca empujada por la oferta de los proveedores, de la planta de agar agar "
                       "del desafío en curso.")
        elif dem == LLEGADA and tom:
            st.caption("Compatibilidad: Natural. Llegada de tomate empujada por la cosecha, del tipo de planta de tomate del desafío en curso.")
        else:
            n_, j_ = PG.compatibilidad(tipo, dem)
            st.caption(f"Compatibilidad: {PG.NIVELES[n_]}. {j_}")
        dem_arg, var_arg = dem, None
        if dem == LLEGADA and lleg:
            dem_arg = ss.get("desafio"); var_arg = lleg[0]     # la serie del desafío (motor/sintesis.leer_demanda la lee)
        c, d, e = st.columns(3)
        crit = c.selectbox("Capacidad de diseño", ["percentil", "pico", "media"], key="dis_criterio",
                           format_func=lambda k: {"percentil": "Percentil 95 de la serie", "pico": "Pico de la serie", "media": "Media de la serie"}[k])
        fs = d.number_input("Factor de servicio", 1.0, 2.0, value=float(SI.SUPUESTOS["factor_servicio"].valor), step=0.05, key="dis_factor",
                            help="Supuesto: " + SI.SUPUESTOS["factor_servicio"].justificacion)
        alts = e.checkbox("Comparar tipos alternativos", True, key="dis_alternativas",
                          help="En las operaciones con tipos de equipo alternativos (por ejemplo el secador) elige el de menor costo anual de su etapa.")
        b1, b2 = st.columns(2)
        if b1.button("Partir en carta en blanco", key="dis_blanco", width="stretch"):
            C.fijar_planta(SI.planta_en_blanco(tipo, dem_arg, ss.get("desafio"), variante=var_arg))
            _avisar(f"Carta en blanco: {C.planta().nombre.replace('Carta en blanco: ', '')}. Arrastre los equipos desde el catálogo.")
        if b2.button("Armar planta automáticamente", type="primary", key="dis_auto", width="stretch"):
            try:
                with st.spinner("Armando la planta con la demanda y las alternativas de menor costo anual…"):
                    nueva = SI.armar_planta(tipo, dem_arg, criterio=crit, factor_servicio=fs, alternativas=alts,
                                            catalogo=_catalogo_comercial(), economia=ss.get("economia"), desafio=ss.get("desafio"),
                                            variante=var_arg)
                C.fijar_planta(nueva)
                inf = SI.informe(nueva)
                _avisar(f"Planta automática de {inf.get('nombre') or PG.PLANTAS[tipo]['nombre']}: {len(nueva.equipos)} equipos, "
                        f"{C.fmt(inf['dimensionamiento']['materia_prima_operacion_t_h'], 2)} t/h de materia prima en operación y "
                        f"{C.fmt(inf['dimensionamiento']['materia_prima_diseno_t_h'], 2)} t/h de diseño. Vea el informe al final de la pantalla.")
            except Exception as x:
                st.error(f"No se pudo armar la planta automáticamente: {x}")
        f1, f2 = st.columns([2, 1])
        ej = f1.selectbox("Ejemplo", list(C.EJEMPLOS), format_func=lambda k: C.EJEMPLOS[k][0], key="dis_ejemplo")
        if f2.button("Cargar ejemplo", key="dis_cargar_ejemplo", width="stretch"):
            try:
                C.cargar_ejemplo(ej)
                _avisar(f"Cargado el ejemplo: {C.EJEMPLOS[ej][0]}. Todas las pantallas trabajan con él.")
            except Exception as x:
                st.error(f"No se pudo cargar el ejemplo: {x}")


def _catalogo_comercial():
    try:
        from pat_sim.datos import mantenedor as MANT
        return MANT.catalogo_comercial(C.obtener_bd())
    except Exception:
        return None


def _cadena(pl):
    """Cadena de estados del material del rubro (la que exige la precedencia) y las conexiones que no la cumplen."""
    from pat_sim.motor import precedencia as PR
    t = PR.regla(pl)
    if t is None:
        return
    # PAT 143: con la conexión libre, las conexiones fuera de orden quedan en la advertencia del validador (sobre el lienzo)
    with st.expander("Precedencia de estados del material", expanded=False):
        st.caption(C.esc("Orden del proceso: " + t.cadena(pl.rubro) + ". Una conexión de producto es correcta si el estado que entrega "
                         "el equipo de origen es el que necesita el de destino; las etapas opcionales se pueden saltar."))


def _taxonomia(pl):
    """Catálogo de todos los equipos de las 10 plantas por función de proceso y familia ISO 10628, con buscador y filtros."""
    from pat_sim.catalogos import taxonomia as TX
    PG = _tipos_planta()
    with st.expander("Catálogo de equipos por función y familia ISO 10628 (buscador)", expanded=False):
        C.ayuda("Cada equipo del registro está en su función de proceso (la de la operación donde lo usa alguno de los 10 tipos de planta) "
                "y en su familia de la ISO 10628 (categoría de la Tabla C.1 y letra código del Anexo D). Los equipos que ninguna planta usa "
                "toman la función de su familia (Supuesto). En el lienzo, la lista desplegable del catálogo tiene las mismas listas y un "
                "buscador. " + TX.FUENTE)
        fs = TX.fichas()
        a, b, c, d = st.columns([2, 1.3, 1.3, 1.3])
        q = a.text_input("Buscar", key="tx_buscar", placeholder="secador, bomba, W, evaporación…")
        funs = [None] + [k for k, _n, _f in TX.GRUPOS]
        fun = b.selectbox("Función", funs, format_func=lambda k: "Todas" if k is None else TX.NOMBRES[k], key="tx_funcion")
        fams = [None] + sorted({f["familia"] for f in fs})
        from pat_sim.simbolos import iso10628 as ISO
        fam = c.selectbox("Familia ISO 10628", fams, format_func=lambda k: "Todas" if k is None else f"{k} · {ISO.CATEGORIAS.get(k, '')}", key="tx_familia")
        pls = [None] + list(PG.IDS_PLANTAS)
        pla = d.selectbox("Tipo de planta", pls, format_func=lambda k: "Todas" if k is None else PG.PLANTAS[k]["nombre"], key="tx_planta")
        simp = st.checkbox("Incluir versiones de balance simplificado", False, key="tx_simples")
        res = TX.buscar(q, fun, fam, pla, fs, simplificados=simp)
        st.caption(f"{len(res)} de {len(fs)} tipos de equipo.")
        filas = [dict(f=", ".join(x["funcion_nombres"]), fam=f"{x['familia']} · {x['familia_nombre']}", l=x["letra"], n=x["nombre"], t=x["tipo"],
                      p=", ".join(x["plantas_nombres"]) or "Ninguna (función por familia, Supuesto)") for x in res]
        C.mostrar_tabla(filas[:200], [("f", "Función", "txt", 0), ("fam", "Familia ISO 10628", "txt", 0), ("l", "Letra", "txt", 0),
                                      ("n", "Equipo", "txt", 0), ("t", "Tipo", "txt", 0), ("p", "Plantas que lo usan", "txt", 0)])
        if len(filas) > 200:
            st.caption("Se muestran los primeros 200; afine la búsqueda.")
        if not q and fun is None and fam is None and pla is None:
            st.markdown("**Árbol por función y familia**")
            lin = []
            for g in TX.arbol([x for x in fs if simp or not x["simplificado"]]):
                lin.append(f"- **{g['nombre']}** ({g['n']})")
                for fa in g["familias"]:
                    lin.append(f"    - {fa['familia']} · {fa['nombre']} ({', '.join(fa['letras'])}): "
                               + ", ".join(e["nombre"] for e in fa["equipos"]))
            st.markdown(C.esc("\n".join(lin)))


def _informe_sintesis(pl):
    """Informe de la planta automática: dimensionamiento, decisiones por equipo, tipos alternativos, supuestos y límites."""
    from pat_sim.motor import sintesis as SI
    inf = SI.informe(pl)
    if not inf:
        return
    with st.expander(f"Informe de la planta automática: {inf['nombre']}", expanded=False):
        d = inf["dimensionamiento"]
        st.markdown(C.esc(f"**Demanda:** {inf['demanda']['nombre']} (lógica {inf['demanda']['logica']}, por {inf['demanda']['periodo']}); "
                          f"medida en t de {d['de']}. Horas de operación: {C.fmt(d['horas'], 0)} h al año ({d['fuente_horas']})."))
        C.mostrar_tabla([dict(c="Criterio de capacidad", v=None, t={"percentil": f"Percentil {C.fmt(d['percentil'], 0)}", "pico": "Pico", "media": "Media"}[d["criterio"]]),
                         dict(c="Factor de servicio", v=d["factor_servicio"], t=""),
                         dict(c="Demanda de diseño (t/h de operación)", v=d["diseno_t_h"], t=d["de"]),
                         dict(c="Demanda en operación (t/h)", v=d["operacion_t_h"], t=d["de"]),
                         dict(c="Rendimiento másico (producto / materia prima)", v=d["rendimiento"], t=""),
                         dict(c="Materia prima de diseño (t/h)", v=d["materia_prima_diseno_t_h"], t=""),
                         dict(c="Materia prima en operación (t/h)", v=d["materia_prima_operacion_t_h"], t=""),
                         dict(c="Producto en operación (t/h)", v=inf.get("producto_t_h"), t="")],
                        [("c", "Dimensionamiento", "txt", 0), ("v", "Valor", "num", 3), ("t", "Nota", "txt", 0)])
        C.mostrar_tabla([dict(o=x["operacion"], e=x["equipo"], t=x["tipo"], s=x["etiqueta"], i=x["instalada_t_h"], a=x["A_etapa"],
                              c=None if x["costo_anual_clp"] is None else x["costo_anual_clp"] / 1e6) for x in inf["decisiones"]],
                        [("o", "Operación", "txt", 0), ("e", "Equipo", "txt", 0), ("t", "Tipo", "txt", 0), ("s", "Alternativa elegida", "txt", 0),
                         ("i", "Capacidad instalada (t/h)", "num", 1), ("a", "Disponibilidad de la etapa", "num", 4),
                         ("c", "Costo anual total (M$)", "mm", 1)])
        for a in inf.get("alternativas") or []:
            st.caption(C.esc(f"{a['operacion']}: " + "; ".join(f"{o['tipo']} " + ("sin resultado (" + o['nota'] + ")" if o['costo_anual_clp'] is None
                                                                                     else f"{C.fmt(o['costo_anual_clp'] / 1e6, 1)} M$ al año")
                                                               for o in a["opciones"]) + f". Elegido: {a['elegido']}."))
        for av in inf.get("avisos_seleccion") or []:
            st.caption(C.esc(av))
        st.markdown("**Supuestos**")
        C.mostrar_tabla([dict(n=s_["nombre"], v=s_["valor"], u=s_["unidad"], j=s_["justificacion"]) for s_ in inf["supuestos"]],
                        [("n", "Supuesto", "txt", 0), ("v", "Valor", "num", 2), ("u", "Unidad", "txt", 0), ("j", "Justificación", "txt", 0)])
        st.markdown("**Límites declarados**")
        st.markdown(C.esc("\n".join("- " + x for x in inf["limites"])))
