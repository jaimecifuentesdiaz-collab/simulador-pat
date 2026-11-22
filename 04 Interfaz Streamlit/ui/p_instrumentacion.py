"""Pantalla Lazos de control (antes Instrumentación): lazos ISA-5.1 puestos directo en el lienzo y su diagrama de lazo ISA-5.4.

PAT 134: muestra también los instrumentos y elementos ISA-5.4 agregados en el lienzo de Diseño, con su símbolo y sus líneas de
señal; el diagrama de lazo se elige por número de lazo (pat_sim.motor.instrumentacion.lazos) y toma la caja de conexiones unida
en el lienzo.
PAT 142 (pedido de Jaime del 19-11-2026): arriba, el mismo lienzo de la Planta ficticia en la vista «lazos» (clave lazos_lienzo):
los equipos y las corrientes no se editan; los instrumentos sí, y los lazos típicos (temperatura, presión, nivel, caudal y
concentración) se sueltan sobre un equipo. Una línea de señal entre instrumentos de lazos distintos es una relación entre lazos
(cascada, razón, prealimentación o enclavamiento). Debajo, tres pestañas: Lazos de la planta (tabla, revisión de los lazos y el
desplegable «Agregar un lazo sin lienzo»), Diagrama de lazo ISA-5.4 y Referencia ISA-5.1. El historial de deshacer es el mismo de
la Planta ficticia (la planta es una sola)."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor.planta import Instrumento
from pat_sim.simbolos import isa51, isa54
from pat_sim.motor import instrumentacion as IN, lienzo as LZ
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from . import lienzo as L           # PAT 142
from . import validacion as VAL     # PAT 143: validador del diseño y botón «Pista»

CLAVE_LIENZO = "lazos_lienzo"       # PAT 142: componente del lienzo de esta pantalla


def _procesar_eventos(pl) -> bool:
    """PAT 142: aplica los eventos del lienzo de lazos que aún no se aplican, con el historial de la Planta ficticia. Los eventos de
    equipos y corrientes no se aceptan aquí (se arman en Planta ficticia)."""
    from . import p_diseno as PD
    ss = st.session_state
    evs = L.eventos_nuevos(ss.get(CLAVE_LIENZO), int(ss.get(CLAVE_LIENZO + "_seq", 0)))
    if not evs:
        return False
    hist = PD._historial(pl)
    msgs = ss.setdefault(CLAVE_LIENZO + "_mensajes", [])
    for ev in evs:
        if ev.get("evento") not in LZ.EVENTOS_LAZOS:
            r = dict(ok=False, mensaje="En Lazos de control los equipos y las corrientes no se cambian: hágalo en Planta ficticia (Diseño).")
        else:
            try:
                r = LZ.aplicar_con_historial(pl, ev, hist, PD.TIPOS)
            except Exception as e:               # un evento malo no bota la pantalla
                r = dict(ok=False, mensaje=f"No se pudo aplicar «{ev.get('evento')}»: {e}")
        ss[CLAVE_LIENZO + "_seq"] = int(ev["seq"])
        if r.get("mensaje"):
            msgs.append(dict(seq=int(ev["seq"]), texto=r["mensaje"], tipo="ok" if r.get("ok") else "error", id=r.get("id"), sel=r.get("sel")))
    del msgs[:-6]
    C.marcar_cambio()                           # la planta única cambió: las demás pantallas lo ven
    return True


def _lienzo(pl):
    """PAT 142: lienzo en la vista «lazos» con el catálogo de lazos típicos e instrumentación."""
    from . import p_diseno as PD
    ss = st.session_state
    if not pl.equipos:
        st.info("Lienzo vacío: arme la planta en Planta ficticia (Diseño) y vuelva aquí para ponerle sus lazos de control.")
        return None
    with C.cargando(C.TXT_RECALCULANDO):
        _procesar_eventos(pl)
        if pl.resuelta and getattr(pl, "salidas", None):
            sol, motivo = pl, None
        else:
            sol, motivo = LZ.resolver_parcial(pl)
        prec = PD._precedencia()
        res = VAL.revisar("lazos", motivo=motivo, precedencia=prec)       # PAT 143: reglas ISA y de las pantallas anteriores
        datos = LZ.datos_lienzo(pl, sol, motivo, LZ.catalogo_lazos(), int(ss.get(CLAVE_LIENZO + "_seq", 0)),
                                ss.get(CLAVE_LIENZO + "_mensajes", []), PD._kpis_recuperacion(pl), PD._historial(pl).resumen(),
                                prec, vista="lazos", libre=True, validacion=res)
    VAL.panel("lazos", res)              # PAT 143: advertencia que no deja avanzar y botón «Pista», sobre el lienzo
    L.lienzo(datos, key=CLAVE_LIENZO)
    C.ayuda("- Arrastre un lazo típico del catálogo de la izquierda y suéltelo sobre un equipo: quedan sus instrumentos con el "
            "número de lazo siguiente libre y sus líneas de señal (medición unida a proceso, transmisor, controlador, convertidor I/P y "
            "válvula sobre la corriente de servicio del equipo).\n"
            "- Los instrumentos sueltos del catálogo se agregan igual; se mueven arrastrándolos y se editan en Propiedades (letras, "
            "número de lazo, acción en falla, alimentación, acción y consigna del controlador).\n"
            "- Para unir dos lazos, arrastre desde el punto azul de un instrumento hasta un instrumento de otro lazo: de controlador a "
            "controlador queda en cascada y de transmisor a controlador en prealimentación; la relación se cambia en Propiedades de la línea.\n"
            "- Los equipos y las corrientes se ven como en Planta ficticia y se cambian allá. Ctrl+Z deshace y Ctrl+Y rehace.\n"
            "- Las líneas de señal se unen libremente. Si un lazo queda mal armado (sin medición o sin elemento final, fuera de orden, "
            "I/P sin señal eléctrica a la entrada y neumática a la salida, etiquetas repetidas o no válidas), aparece una advertencia "
            "sobre el lienzo que no deja pasar a la etapa siguiente y el botón «Pista» orienta paso a paso.\n"
            "- Símbolos y líneas de señal según ISA-5.1 (Carballo y Romero, 2011: Tablas 4, 15 y 17); datos mínimos del lazo según "
            "ISA-5.4 (diapositivas ISA del curso, p. 32).")
    return res


def mostrar():
    pl = C.planta()
    C.ayuda("Identificación y símbolos según ISA-5.1 (tutorial de Carballo y Romero, 2011: Tablas 3, 4, 15 y 17); "   # PAT 134: ayuda «?»
            "el diagrama de lazo sigue la estructura de ISA-5.4 y rotula su información mínima (diapositivas ISA del curso, p. 32). "
            "Ambas normas actuales son pagadas y no están en la carpeta del proyecto: el diagrama de lazo es una versión simplificada "
            "y así se declara.", "Lazos de control", 3)
    res = _lienzo(pl)                                                 # PAT 142; PAT 143: con la revisión del validador
    t1, t2, t3 = st.tabs(["Lazos de la planta", "Diagrama de lazo ISA-5.4", "Referencia ISA-5.1"])   # PAT 142: pestañas grandes
    with t1:
        _tabla_lazos(pl, res)
    with t2:
        _diagrama(pl)
    with t3:
        _referencia()
    VAL.redibujar_si_cambio("lazos")         # PAT 143: la franja del proceso se pone al día si cambió el bloqueo


def _relaciones_de(rels, id_) -> str:
    return "; ".join(f"{r['nombre']} con el lazo {r['lazo_destino'] if r['origen'] == id_ else r['lazo_origen']} ({r['origen']} → {r['destino']})"
                     for r in rels if id_ in (r["origen"], r["destino"]))


def _tabla_lazos(pl, res=None):
    AT.tabla("ins_lazos", "Lazos de la planta", 4)
    if pl.instrumentos:
        rels = IN.relaciones(pl); filas = []
        for i in pl.instrumentos:
            k = isa51.tag(i.letras, i.numero)
            sen = ", ".join(f"{isa51.SENALES.get(x.get('senal'), ('?',))[0].lower()} a {x.get('destino')}" for x in i.conexiones if isinstance(x, dict))
            filas.append(dict(lz=IN.lazo_de(i) or "—", tag=k, sim=isa51.NOMBRE_SIMBOLO.get(i.simbolo, i.simbolo), eq=i.equipo or "—",
                              ub=isa51.UBICACIONES.get(i.ubicacion, i.ubicacion), d=IN.lectura(i),
                              desc=i.descripcion, par=i.parametro or "—", fin=i.elemento_final or "—", sen=sen or "—",
                              rel=_relaciones_de(rels, k) or "—"))
        C.mostrar_tabla(filas, [("lz", "Lazo", "txt", 0), ("tag", "Identificación", "txt", 0), ("sim", "Símbolo", "txt", 0), ("eq", "Equipo", "txt", 0),
                                ("ub", "Ubicación", "txt", 0), ("d", "Lectura ISA-5.1", "txt", 0), ("desc", "Descripción", "txt", 0),
                                ("par", "Parámetro que gobierna", "txt", 0), ("fin", "Elemento final", "txt", 0),
                                ("sen", "Líneas de señal", "txt", 0), ("rel", "Conexiones con otros lazos", "txt", 0)])
        q = st.selectbox("Quitar un instrumento", range(len(pl.instrumentos)), key="ins_del",
                         format_func=lambda i: f"{isa51.tag(pl.instrumentos[i].letras, pl.instrumentos[i].numero)} · {pl.instrumentos[i].equipo or 'sin equipo'}")
        if st.button("Quitar instrumento", key="ins_quitar"):
            IN.quitar(pl, IN.ident(pl.instrumentos[q])); C.marcar_cambio(); st.rerun()      # PAT 134: también sus líneas de señal
        # PAT 143: los errores van en la advertencia sobre el lienzo (con su botón «Pista»); aquí quedan los avisos, que no bloquean
        if res is None:
            from . import p_diseno as PD
            res = VAL.revisar("lazos", precedencia=PD._precedencia())
        av = [r for r in res.get("avisos") or [] if r.get("vista") == "lazos"]
        AT.tabla("ins_revision", "Revisión de los lazos: avisos", 4)
        if av:
            C.mostrar_tabla([dict(l=r.get("lazo") or "—", o=r.get("objeto") or "—", m=r["mensaje"], p=(r.get("pistas") or [""])[-1],
                                  f=r.get("fuente") or "") for r in av],
                            [("l", "Lazo", "txt", 0), ("o", "Instrumento", "txt", 0), ("m", "Observación", "txt", 0),
                             ("p", "Cómo completarlo", "txt", 0), ("f", "Origen de la regla", "txt", 0)])
        elif not res.get("errores"):
            st.success("Los lazos cumplen las reglas revisadas.")
        else:
            st.caption("Sin avisos; los errores están en la advertencia sobre el lienzo.")
    else:
        st.info("La planta no tiene lazos de control todavía.")
    _agregar_sin_lienzo(pl)


def _agregar_sin_lienzo(pl):
    """El formulario de antes, para quien no use el arrastre: un lazo típico completo o un instrumento suelto."""
    with st.expander("Agregar un lazo sin lienzo"):
        if pl.equipos:                                                  # PAT 142: lazo típico desde el formulario
            with st.form("form_lazo_tipico"):
                a, b = st.columns(2)
                var = a.selectbox("Lazo típico", list(IN.TIPICOS), format_func=lambda k: f"Control de {IN.NOMBRE_TIPICO[k]}", key="ins_tip_var")
                eq = b.selectbox("Equipo", list(pl.equipos), format_func=lambda k: f"{k} · {pl.equipos[k].nombre}", key="ins_tip_eq")
                ok_t = st.form_submit_button("Agregar lazo típico", type="primary")
            if ok_t:
                try:
                    r = IN.agregar_lazo(pl, var, eq)
                    C.marcar_cambio(); st.success(r["mensaje"]); st.rerun()
                except ValueError as ex:
                    st.error(str(ex))
        st.markdown("**Un instrumento con su número de lazo**")
        with st.form("form_lazo"):
            a, b, c = st.columns(3)
            letras = a.text_input("Letras de identificación (1 a 5)", "TIC", help="Primera letra: variable medida; las siguientes: función (I indicador, C controlador, T transmisor…)")
            numero = b.text_input("Número de lazo", "")
            eqid = c.selectbox("Equipo", list(pl.equipos) or ["—"], format_func=lambda k: f"{k} · {pl.equipos[k].nombre}" if k in pl.equipos else k)
            d, e, f = st.columns(3)
            ub = d.selectbox("Ubicación (símbolo)", list(isa51.UBICACIONES), index=list(isa51.UBICACIONES).index("dcs"), format_func=lambda k: isa51.UBICACIONES[k])
            params = ["—"] + (list(pl.equipos[eqid].params) if eqid in pl.equipos else [])
            par = e.selectbox("Parámetro que gobierna", params)
            fin = f.text_input("Elemento final de control", "", help="Por ejemplo TV-101")
            desc = st.text_input("Descripción", "")
            ok = st.form_submit_button("Agregar lazo", type="primary")
        if letras.strip():
            try:
                st.caption("Lectura: " + isa51.interpretar(letras)["descripcion"])
            except ValueError as ex:
                st.caption(f":red[{ex}]")
        if ok:
            try:
                isa51.interpretar(letras)
                if not numero.strip():
                    raise ValueError("Falta el número de lazo")
                if any(i.letras.upper() == letras.strip().upper() and i.numero == numero.strip() for i in pl.instrumentos):
                    raise ValueError(f"Ya existe el lazo {isa51.tag(letras, numero.strip())}")
                pl.instrumentos.append(Instrumento(letras.strip().upper(), numero.strip(), eqid if eqid in pl.equipos else "", ub, desc,
                                                   None if par == "—" else par, fin.strip() or None))
                C.marcar_cambio(); st.success(f"Lazo {isa51.tag(letras, numero.strip())} agregado.")
                st.rerun()
            except ValueError as ex:
                st.error(str(ex))


def _diagrama(pl):
    lz = IN.lazos(pl)
    if not lz:
        st.info("Agregue un lazo en el lienzo para ver su diagrama de lazo.")
        return
    i = st.selectbox("Lazo", range(len(lz)), key="ins_ver",
                     format_func=lambda k: f"Lazo {lz[k]['numero']} · {IN.ident(lz[k]['representante'])}"
                     + (f" · {lz[k]['representante'].descripcion}" if lz[k]['representante'].descripcion else "")
                     + (f" ({len(lz[k]['miembros'])} instrumentos)" if len(lz[k]['miembros']) > 1 else ""))
    Lz = lz[i]; ins = Lz["representante"]
    c1, c2 = st.columns(2)
    caja = c1.text_input("Caja de conexiones", Lz["caja"] or "JB-1", key=f"ins_caja_{Lz['numero']}")
    senal = c2.text_input("Señal", "4-20 mA", key="ins_senal_txt")
    try:
        ub = ins.ubicacion if ins.ubicacion in isa51.UBICACIONES else "dcs"
        if ins.simbolo in isa51.FUNCIONES:                 # PAT 134: tipo de burbuja del lienzo → forma del controlador
            ub = {"compartido": "dcs", "plc": "plc", "computador": "computador"}.get(ins.simbolo, ins.ubicacion)
        # PAT 142: información mínima de ISA-5.4 (p. 32): título, relaciones, alimentación y acción en falla
        fin = next((m for m in Lz["miembros"] if IN.es_final(m)), None)
        alim = {}
        for m in Lz["miembros"]:
            rol = "controlador" if IN.es_controlador(m) else ("convertidor" if IN.es_convertidor(m) else ("transmisor" if IN.es_medicion(m) else None))
            if rol and m.alimentacion and rol not in alim:
                alim[rol] = m.alimentacion
        rels = [f"{r['nombre'].capitalize()} con el lazo {r['lazo_destino'] if r['lazo_origen'] == Lz['numero'] else r['lazo_origen']} "
                f"({r['origen']} → {r['destino']})" for r in IN.relaciones(pl) if Lz["numero"] in (r["lazo_origen"], r["lazo_destino"])]
        desc = ins.descripcion or IN.titulo_lazo(Lz).split(" · ", 1)[-1].capitalize()
        svg = isa54.lazo_svg(ins.letras, ins.numero, desc, ins.equipo, ub, caja, senal,
                             accion_falla=(fin.accion_falla if fin is not None else "") or "", alimentacion=alim,
                             accion=ins.accion if IN.es_controlador(ins) else "", consigna=ins.consigna if IN.es_controlador(ins) else "",
                             relaciones=rels, final=IN.ident(fin) if fin is not None else "")
        st.image(svg)
        st.download_button("Descargar el diagrama de lazo (SVG)", svg, file_name=f"Lazo_ISA54_{ins.letras}{ins.numero}.svg", mime="image/svg+xml")
    except ValueError as ex:
        st.error(str(ex))
    if Lz["senales"] or len(Lz["miembros"]) > 1:
        AT.tabla("ins_senales", "Señales del lazo")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(o=x["origen"], s=isa51.SENALES.get(x.get("senal"), ("?",))[0], d=x.get("destino"), p=x.get("parametro") or "—",
                              r=IN.RELACIONES_CORTO.get(x.get("relacion") or "", "—"))
                         for x in Lz["senales"]],
                        [("o", "Desde", "txt", 0), ("s", "Señal ISA-5.1", "txt", 0), ("d", "Hasta", "txt", 0), ("p", "Parámetro", "txt", 0),
                         ("r", "Relación entre lazos", "txt", 0)])


def _referencia():
    a, b = st.columns(2)
    with a:
        AT.tabla("ins_primera", "Primera letra")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(l=k, d=v) for k, v in isa51.PRIMERA_LETRA.items()], [("l", "Primera letra", "txt", 0), ("d", "Variable medida", "txt", 0)])
    with b:
        AT.tabla("ins_sucesivas", "Letras sucesivas")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(l=k, d=v) for k, v in isa51.LETRAS_SUCESIVAS.items()], [("l", "Letra sucesiva", "txt", 0), ("d", "Función", "txt", 0)])
    st.markdown("**Símbolos por ubicación (Tabla 4)**")
    cols = st.columns(len(isa51.UBICACIONES))
    for col, (k, nombre) in zip(cols, isa51.UBICACIONES.items()):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">{isa51.burbuja("TIC", "101", 32, 32, k, r=20)}</svg>'
        col.image(svg, width=64); col.caption(nombre)
    st.markdown("**Líneas de señal (Tabla 15; la electromagnética o sónica, según ISA-5.1 sin número de tabla)**")
    cols = st.columns(len(isa51.SENALES))
    for col, (k, (nombre, _a, _b)) in zip(cols, isa51.SENALES.items()):
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="110" height="24" viewBox="0 0 110 24">{isa51.linea(5, 12, 105, 12, k)}</svg>'
        col.image(svg, width=110); col.caption(nombre)
    st.markdown("**Catálogo del lienzo: burbujas, elementos primarios y finales, y elementos de lazo ISA-5.4**")
    cat = IN.catalogo()
    for g in dict.fromkeys(c["grupo"] for c in cat):
        st.caption(g)
        cs = [c for c in cat if c["grupo"] == g]
        for j in range(0, len(cs), 8):
            cols = st.columns(8)
            for col, c in zip(cols, cs[j:j + 8]):
                svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="72" height="80" viewBox="-30 -26 60 66">{c["svg"]}</svg>'
                col.image(svg, width=64); col.caption(f"{c['letras']} · {c['nombre']}")
