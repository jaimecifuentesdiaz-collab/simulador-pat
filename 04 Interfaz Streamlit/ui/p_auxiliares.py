"""Pantalla Equipos auxiliares (PAT 136, tarea T23, 13-11-2026; punto 10c de los comentarios del profesor Torres).
PAT 140 g (17-11-2026): el candidato se suelta en cualquier lugar libre del lienzo y las bombas se reconectan a otra línea.

Tercera pantalla de construcción, después de la Planta ficticia (Diseño) y la Planta real (Selección de equipos): lo que no es una
operación unitaria pero hace falta para que la planta funcione. Bombas y cañerías de las líneas de líquido (motor/hidraulica.py),
válvulas de control y de bloqueo, estanques pulmón entre equipos (tiempo de residencia o pulmón por falla) y servicios: vapor, calor,
agua, aire y electricidad, con su lista y su costo del costeo (motor/costeo.py). Motor: pat_sim/motor/auxiliares.py.
Claves de widgets con prefijo «aux_».
PAT 138 (13-11-2026): arriba de las tablas, el mismo lienzo de la Planta ficticia con la selección comercial y los equipos
auxiliares dibujados (ui/lienzo.mostrar_vista, vista «auxiliares», clave aux_lienzo, solo lectura).
PAT 139 (punto 6 de los comentarios del profesor Torres del 14-11-2026): elección en vivo de cada bomba, válvula de control, estanque
pulmón y generación de vapor o calor entre candidatos ordenados por C = C_inv + C_op + C_inef (motor/eleccion_auxiliares.py), con el
estado de Tavily, «Generar automáticamente», «Deshacer» (la misma pila de la Planta ficticia y de la Planta real) y la lista de
candidatos que se arrastra sobre el lienzo."""
from __future__ import annotations
import json
import streamlit as st
from pat_sim.motor import auxiliares as AX, costeo as CO, costos, seleccion as SEL, eleccion_auxiliares as EA, eleccion_viva as EV
from pat_sim.motor import tres_opciones as T3
from . import comun as C, lienzo as LV, eleccion_comun as EC
from . import validacion as VAL     # PAT 143: validador del diseño y botón «Pista»

AYUDA = """
**Elección en vivo (PAT 139).** Cada bomba, válvula de control, estanque pulmón y generación de vapor o calor tiene su lista de
candidatos con C = C_inv + C_op + C_inef, su disponibilidad A y la eficiencia η en operación, que se puede ordenar por cualquiera de esos
valores: equipos reales de la base de respaldo o de Tavily cuando
los hay, y tamaños escalados con Williams desde el precio de esta pantalla (uno del tamaño justo, uno más uno de reserva, dos de la
mitad y dos de la mitad más uno de reserva). «Generar automáticamente» pone el de menor C en todos (un criterio de partida, no un
juicio sobre los demás). Cómo elegir en el lienzo, la ficha comparativa y «Deshacer» se explican en el «?» bajo el lienzo.

**Qué es.** Los equipos auxiliares son los que no transforman el material pero hacen que la planta funcione: las bombas que mueven
los líquidos, las válvulas que los controlan y aíslan, los estanques pulmón que desacoplan un equipo del siguiente, las cañerías que
los unen y los servicios (vapor, calor, agua, aire y electricidad) que alimentan a los equipos.

**Cómo se calcula.** Las bombas, su altura y su potencia salen de la red hidráulica de la planta (diámetro por velocidad de diseño y
pérdida de carga); las cañerías usan el diámetro nominal más cercano y el largo del layout (sin layout, 30 m por línea, Supuesto); las
válvulas de control son las de los lazos de Instrumentación (Cv por ISA-75.01) y a cada bomba se le suman dos válvulas de bloqueo y una
de retención. Cada estanque pulmón va entre dos equipos consecutivos de la línea principal y se dimensiona con el **tiempo de
residencia** (por omisión 30 min de la carga del equipo siguiente, el mismo pulmón de la pestaña Línea), con el **pulmón por falla**
(el MTTR del equipo anterior por la carga del siguiente, para que éste siga trabajando mientras el otro se repara) o con el mayor de
los dos. El volumen geométrico es el útil dividido por el llenado máximo (80 %); el estanque es cilíndrico vertical con altura de dos
diámetros. Los costos vienen del costeo (precio de internet guardado, bibliografía o Supuesto, actualizado con el CEPCI); el estanque
no tiene referencia en el costeo y su costo es un Supuesto escalado con Williams. La electricidad suma la potencia de los equipos y de
las bombas y se valora con el precio de la electricidad.

**Para qué sirve.** Completa la inversión de la planta con lo que el diagrama de flujo no dibuja, y dice cuánto espacio y cuánto
pulmón necesita la planta para absorber las fallas de la Selección de equipos.

**Supuestos.** Tiempo de residencia, cobertura de la falla, llenado, relación altura/diámetro, densidad de los sólidos a granel y
precio del estanque son Supuesto con su justificación (más abajo). Sin planta o con la planta sin resolver, no hay nada que dimensionar.
"""


def _lay(ss) -> tuple[dict | None, dict | None]:
    lay = C.layout_vigente() or {}           # PAT 137 (estado único): largos del layout al día con la planta
    lg, cb = lay.get("longitudes_m"), lay.get("cables_m")
    return (lg if isinstance(lg, dict) else None), (cb if isinstance(cb, dict) else None)


def _prec():
    """PAT 143: tabla de precedencia de la Planta ficticia, para que el validador revise también esa pantalla."""
    from . import p_diseno as PD
    return PD._precedencia()


def mostrar():
    pl = C.planta()
    st.subheader("Equipos auxiliares: bombas, válvulas, estanques, cañerías y servicios")
    st.caption("Tercera pantalla de construcción: Planta ficticia (Diseño), Planta real (Selección de equipos) y Equipos auxiliares.")
    with st.expander("?  Cómo se hace, para qué y por qué"):
        st.markdown(C.esc(AYUDA))
    # PAT 139: primero se aplican los eventos del lienzo y de los botones (con los candidatos que el estudiante vio), después se
    # calculan los auxiliares con la planta al día y se dibujan arriba de las tablas, en este contenedor
    EC.mostrar_aviso("aux")
    t = EC.mostrar_estado_tavily()
    if pl.equipos:
        EC.resolver_si_hace_falta(pl)
        hist = EC.historial(pl)
        # PAT 143: conexión libre (un candidato se aplica aunque no calce en el auxiliar donde se suelta; lo marca el validador)
        EC.procesar_eventos(pl, "aux_lienzo", lambda ev: EA.procesar_evento(pl, hist, ev, st.session_state.get("aux_objs_vigentes") or [],
                                                                            libre=True))
    caja = st.container()
    r = _auxiliares(pl)
    with caja:
        _vivo(pl, r, t)
    VAL.redibujar_si_cambio("auxiliares")    # PAT 143: la franja del proceso se pone al día si cambió el bloqueo


AYUDA_LIENZO = ("- Es la planta de la Planta real (modelo y unidades de cada equipo) con sus equipos auxiliares: bombas con sus "
                "válvulas de bloqueo y de retención sobre las líneas de líquido, válvulas de control de los lazos, estanques pulmón "
                "entre equipos consecutivos de la línea principal y el diámetro nominal de cada cañería en la etiqueta de la línea.\n"
                "- A la izquierda, las 3 opciones de cada equipo auxiliar (PAT 140 c: 3 números de unidades n distintos, para cada n la de "
                "menor C) con C_inv, C_op, C_inef, C, A, η en operación y origen, ordenadas por la columna que elija, sin marcar ninguna. "
                "Arrástrela al lienzo: mientras la arrastra, su equipo queda marcado con un borde punteado verde y los de la misma clase con "
                "capacidad parecida (±20 %), con uno azul. Suéltela en un lugar libre y se aplica a su equipo, que queda donde la soltó, unido "
                "a su línea; suéltela sobre otro equipo marcado y se aplica a ese. También puede hacer clic en ella. Al pinchar el equipo (o con «Ver ficha "
                "comparativa» bajo «Elegir por equipo auxiliar») se abre su ficha comparativa en 3 columnas con «Elegir esta opción». El elegido aparece en verde junto al equipo y, si tiene varias unidades "
                "en paralelo, se dibuja una por unidad. Las demás opciones están en la tabla «Todas las opciones».\n"
                "- Los equipos y los auxiliares se pueden mover. Una bomba arrastrada sobre otra línea queda conectada a ella (o elija la "
                "«Línea que sirve» en su ficha): toma el caudal, el diámetro y la potencia de esa línea, la bomba que estaba ahí pasa a la "
                "línea que dejó y se recalculan los candidatos y el C de las dos. «Deshacer» o Ctrl+Z vuelve atrás el último cambio, varias veces.\n"
                "- El recuadro «Servicios» de la derecha resume vapor, calor, agua, aire y electricidad.")


def _firma(r: dict, E: dict, en_linea: bool) -> str:
    b = [(x["id"], round(x["Q_m3h"], 6), x.get("costo_usd")) for x in r["bombas"]["filas"]]
    v = [(x["id"], x.get("Cv"), x.get("costo_usd")) for x in r["valvulas"]["control"]]
    e = [(x["id"], round(x["v_geo_m3"], 6), x.get("costo_usd")) for x in r["estanques"]["filas"]]
    s = [(x["servicio"], x.get("demanda"), x.get("costo_usd")) for x in r["servicios"]["filas"]]
    return json.dumps([b, v, e, s, sorted((k, str(x)) for k, x in (E or {}).items()), bool(en_linea)], default=str)


def _objetivos(pl, r: dict, en_linea: bool) -> dict:
    """Auxiliares con sus candidatos, guardados en la sesión mientras la planta pida lo mismo (Tavily no se consulta en cada clic)."""
    ss = st.session_state
    E = dict(ss.get("economia") or {})
    f = _firma(r, E, en_linea)
    cache = ss.setdefault("aux_cand_cache", {})
    if f not in cache:
        try:
            with C.cargando(C.TXT_BUSCANDO_EQUIPOS if en_linea else C.TXT_BUSCANDO_RESPALDO):    # PAT 140: círculo que gira con el motivo
                o = EA.objetivos(pl, r, E, en_linea)
        except Exception as e:                  # los auxiliares nunca deben botar la aplicación
            o = dict(objetivos=[], avisos=[f"No se pudieron armar los candidatos de los auxiliares: {e}"])
        o.pop("parametros", None)
        for ob in o.get("objetivos") or []:            # PAT 140 c: 3 opciones de distinto n y su ficha comparativa
            try:
                ob["tres"] = T3.elegir_tres(ob.get("candidatos") or [])
                ob["comparacion"] = T3.comparativa(ob["tres"], dict(equipo=ob["id"], nombre=ob["nombre"], requerida=ob["requerida"],
                                                                     unidad=ob["unidad"]))
            except Exception:
                ob["tres"], ob["comparacion"] = (ob.get("candidatos") or [])[:3], None
        cache.clear(); cache[f] = o
    return cache[f]


def _cb_generar():
    pl = C.planta()
    r = EA.generar_automaticamente(pl, EC.historial(pl), st.session_state.get("aux_objs_vigentes") or [])
    C.marcar_cambio(); EC.anotar("aux", r)


def _cb_deshacer():
    EC.anotar("aux", EC.deshacer(C.planta(), EV.deshacer))


def _cb_quitar():
    pl = C.planta()
    r = EA.quitar_todo(pl, EC.historial(pl))
    C.marcar_cambio(); EC.anotar("aux", r)


def _cb_elegir(c: dict):
    """PAT 140 c: «Elegir esta opción» de la ficha comparativa (lo mismo que elegir en la lista, con un paso de «Deshacer»)."""
    pl = C.planta()
    r = EA.aplicar_candidato(pl, EC.historial(pl), c)
    C.marcar_cambio(); EC.anotar("aux", r)


def _cb_elegir_select(oid: str):
    ss = st.session_state
    cid = ss.get(f"aux_viva_{oid}")
    pl = C.planta()
    if not cid:
        def quitar(p):
            el = EA.elecciones(p); el.pop(oid, None); EA._guardar(p, el)
        r = EV.con_historial(pl, EC.historial(pl), f"quitar el auxiliar elegido en {oid}", quitar)
        r["mensaje"] = f"{oid}: sin equipo elegido." if r["cambio"] else None
    else:
        c = EA.buscar_candidato(ss.get("aux_objs_vigentes") or [], cid)
        if c is None:
            return
        r = EA.aplicar_candidato(pl, EC.historial(pl), c)
    C.marcar_cambio(); EC.anotar("aux", r)


def _vivo(pl, r: dict | None, t: dict) -> None:
    """Botones, indicadores, lienzo con los candidatos y panel de elección de los auxiliares."""
    ss = st.session_state
    if not pl.equipos:               # PAT 140 d: el aviso de planta vacía ya está arriba; sin lienzo vacío que lo repita
        ss["aux_objs_vigentes"] = []
        return
    if not r:
        ss["aux_objs_vigentes"] = []
        res = VAL.revisar("auxiliares", precedencia=_prec())       # PAT 143: errores de las pantallas anteriores
        VAL.panel("auxiliares", res)
        LV.mostrar_eleccion("auxiliares", "aux_lienzo", dict(modo="auxiliares", objetivos=[]), aux=r, libre=True, validacion=res)
        return
    o = _objetivos(pl, r, t["en_linea"])
    objs = o["objetivos"]
    ss["aux_objs_vigentes"] = objs
    hist = EC.historial(pl)
    h = hist.resumen()
    if objs:
        b1, b2, b3, b4 = st.columns([1.3, 1, 1.1, 2.2])
        b1.button("Generar automáticamente", type="primary", key="aux_generar", on_click=_cb_generar,
                  help="Aplica en cada equipo auxiliar el candidato de menor costo anual total C (un solo paso de «Deshacer»). Es un "
                       "criterio de partida: revise A, η en operación, origen y fuente y cambie la elección si lo estima.")
        b2.button("Deshacer", key="aux_deshacer", on_click=_cb_deshacer, disabled=not h["deshacer"],
                  help=(f"Deshace: {h['etiqueta_deshacer']} ({h['deshacer']} pasos guardados)." if h["deshacer"] else "No hay cambios que deshacer."))
        b3.button("Quitar las elecciones", key="aux_quitar_todo", on_click=_cb_quitar, help="Quita los auxiliares elegidos (se puede deshacer).")
        b4.caption((f"Último cambio: {h['etiqueta_deshacer']}. " if h["deshacer"] else "") + f"{h['deshacer']} pasos para deshacer.")
        est = EA.estado(pl, objs)
        A_real = None
        try:
            from . import p_seleccion as PS
            cands, _av = PS._candidatos(pl, t["en_linea"])
            A_real = EV.estado_planta_real(pl, cands)["A_sist"]
        except Exception:
            A_real = None
        m1, m2, m3, m4 = st.columns(4)
        m1.metric("Auxiliares elegidos", f"{est['n_elegidos']} de {est['n_objetivos']}")
        m2.metric("Disponibilidad de los auxiliares", C.pct(est["A_sist"], 2))
        m3.metric("A_sist de la planta real con auxiliares", C.pct(A_real * est["A_sist"], 2) if (A_real is not None and est["A_sist"] is not None) else "—")
        m4.metric("C total de los auxiliares", EC.usd(est["C"]))
        st.caption(C.esc((f"C_inv {EC.usd(est['C_inv'])}, C_op {EC.usd(est['C_op'])} y C_inef {EC.usd(est['C_inef'])} de los elegidos. "
                          if est["n_elegidos"] else "Todavía no hay auxiliares elegidos. ")
                         + "A_sist con auxiliares = A_sist de las etapas elegidas en "
                         "la Planta real × disponibilidad de los auxiliares elegidos (todo en serie, Supuesto «serie_aux»)."))
    else:
        est = dict(filas=[])
    payload = []
    for f, ob in zip(est["filas"], objs):
        cs = ob["candidatos"]
        payload.append(dict(id=ob["id"], nombre=ob["nombre"], grupo=ob["grupo"], nombre_largo=ob.get("nombre_largo") or ob["nombre"],
                            clase=ob["clase"], requerida=ob["requerida"], unidad=ob["unidad"],     # PAT 140 g: destinos del arrastre
                            req=f"requiere {C.fmt(ob['requerida'], 1 if ob['requerida'] < 100 else 0)} {ob['unidad']}", dianas=ob["dianas"],
                            elegido=(f["elegido"] or {}).get("id"), etq_elegido=(f["elegido"] or {}).get("etiqueta") or "", n_todos=len(cs),
                            candidatos=[EC.para_lienzo(c) for c in (ob.get("tres") or cs[:3])],
                            comparacion=EC.para_lienzo_ficha(ob.get("comparacion"))))
    res = VAL.revisar("auxiliares", precedencia=_prec(), aux=r, objetivos=objs)   # PAT 143: advertencia y botón «Pista»
    VAL.panel("auxiliares", res, avisos=True)
    LV.mostrar_eleccion("auxiliares", "aux_lienzo", dict(modo="auxiliares", titulo="Candidatos de los auxiliares", objetivos=payload,
                                                         moneda="US$/año", paralelo=EC.paralelo_elegidos(est["filas"], objs)),
                        int(ss.get("aux_lienzo_seq", 0)), ss.get("aux_lienzo_mensajes", []), h, aux=r, libre=True, validacion=res)
    C.ayuda(AYUDA_LIENZO)
    for x in o.get("avisos") or []:
        st.caption(C.esc(x))
    if not objs:
        return
    st.markdown("#### Elegir por equipo auxiliar")
    ids = [ob["id"] for ob in objs]
    nombre = {ob["id"]: f"{ob['grupo']} · {ob['nombre']}" for ob in objs}
    if ss.get("aux_obj_viva") not in ids:
        ss["aux_obj_viva"] = ids[0]
    a, b = st.columns([1, 2])
    oid = a.selectbox("Equipo auxiliar", ids, key="aux_obj_viva", format_func=lambda k: nombre.get(k, k))
    ob = next(x for x in objs if x["id"] == oid)
    fila = next(f for f in est["filas"] if f["objetivo"] == oid)
    orden = a.selectbox("Ordenar los candidatos por", list(EC.ORDENES), key="aux_orden_cand", format_func=lambda k: EC.ORDENES[k][0],
                        help="Ordena la lista; ninguna posición significa que el candidato convenga más. Compare los valores y decida.")
    cs = EC.ordenar(ob["candidatos"], orden)
    k = f"aux_viva_{oid}"
    act = (fila["elegido"] or {}).get("id") or ""
    # PAT 140 d: la comparación de las 3 opciones vive solo en la ficha (lienzo o este botón), sin repetir la tabla en la página
    if ob.get("comparacion") and ob.get("tres"):
        EC.boton_ficha("aux_ficha", oid, nombre.get(oid, oid),
                       lambda ka: EC.mostrar_comparativa(ob.get("comparacion"), ob.get("tres") or [], act, _cb_elegir, "aux_cmp",
                                                         f"Requiere {C.fmt(ob['requerida'], 1)} {ob['unidad']}", len(cs),
                                                         "la tabla «Todas las opciones» de la página", ka))
    st.markdown(f"##### Todas las opciones de {oid} ({len(cs)})")
    ss[k] = act if act in [c["id"] for c in cs] else ""
    etq = {c["id"]: f"{c['etiqueta']} · C = {C.fmt(c['C'], 0)} US$/año · A {C.pct(c.get('A'), 2)}" for c in cs}
    b.selectbox(f"Candidato para {oid} (se aplica al tiro)", [""] + [c["id"] for c in cs], key=k, on_change=_cb_elegir_select, args=(oid,),
                format_func=lambda x: "(sin elegir)" if not x else etq.get(x, x))
    C.mostrar_tabla(EC.filas_candidatos(cs, act), EC.COLS_CAND)
    if cs:
        st.caption(C.esc(f"Requiere {C.fmt(ob['requerida'], 1)} {ob['unidad']}. "
                         + EA.SUPUESTOS["serie_aux"].justificacion + "."))
    with st.expander("Equipos auxiliares elegidos"):
        C.mostrar_tabla([dict(g=f["grupo"], o=f["objetivo"], el=(f["elegido"] or {}).get("etiqueta") or "(sin elegir)",
                              org=(f["elegido"] or {}).get("origen") or "", c=(f["elegido"] or {}).get("C"), a=(f["elegido"] or {}).get("A"),
                              eta=(f["elegido"] or {}).get("eta_operacion"))
                         for f in est["filas"]],
                        [("g", "Grupo", "txt", 0), ("o", "Equipo", "txt", 0), ("el", "Elegido", "txt", 0), ("org", "Origen", "cen", 0),
                         ("c", "C (US$/año)", "mm", 0), ("a", "A", "pct", 2), ("eta", "η en operación", "pct", 1)])


def _auxiliares(pl):
    """Parámetros, cálculo y tablas de los equipos auxiliares; devuelve el resultado de AX.auxiliares para el lienzo (o None)."""
    ss = st.session_state
    if not pl.equipos:
        st.info("La planta está vacía. Arme la planta en Diseño y resuélvala; después vuelva aquí para dimensionar sus equipos auxiliares.")
        return
    if not pl.resuelta:                         # PAT 143: si la causa es un error de diseño, la advertencia del lienzo lo explica
        if not VAL.revisar("auxiliares", precedencia=_prec())["errores"]:
            C.exigir_resuelta()
        return
    E = dict(ss.get("economia") or {}); P = ss.get("costeo_param") or {}
    longitudes, cables_m = _lay(ss)
    with st.container(border=True):
        a, b, c, d, e = st.columns(5)
        metodo = a.selectbox("Dimensionar el pulmón con", list(AX.METODOS_PULMON), key="aux_metodo", format_func=lambda k: AX.NOMBRE_METODO[k],
                             help="Tiempo de residencia, pulmón por falla (MTTR del equipo anterior) o el mayor de los dos.")
        minutos = b.number_input("Residencia (min)", 1.0, 600.0, float(AX.SUPUESTOS["residencia_min"].valor), 5.0, key="aux_min",
                                 help=C.esc("Supuesto: " + AX.SUPUESTOS["residencia_min"].justificacion))
        cob = c.number_input("Cobertura de la falla (veces el MTTR)", 0.5, 10.0, float(AX.SUPUESTOS["cobertura_falla"].valor), 0.5, key="aux_cob",
                             help=C.esc("Supuesto: " + AX.SUPUESTOS["cobertura_falla"].justificacion))
        kwh = d.number_input(C.esc("Electricidad ($/kWh)"), 0.0, 10000.0, float(SEL.PRECIO_KWH), 1.0, key="aux_kwh",
                             help=C.esc("Por defecto: " + C.FUENTE_PMM + " (clientes libres)."))
        fi = e.number_input("Factor de instalación", 1.0, 6.0, float(costos.F_INSTALACION), 0.1, key="aux_finst",
                            help="Costo instalado / costo del equipo (motor/costos.py, Supuesto).")
    try:
        r = AX.auxiliares(pl, longitudes, cables_m, metodo, float(minutos), float(cob), float(kwh), f_inst=float(fi),
                          cepci_hoy=float(P.get("cepci", CO.CEPCI_HOY)), dolar=float(E.get("dolar", costos.DOLAR)))
    except Exception as ex:                    # los auxiliares nunca deben botar la aplicación
        st.error(f"No se pudieron dimensionar los equipos auxiliares: {ex}")
        return None
    r = EA.aplicar_lineas(pl, r)               # PAT 140 g: bombas que el estudiante conectó a otra línea
    ss["auxiliares"] = dict(total_usd=r["total_usd"], total_instalado_usd=r["total_instalado_usd"], total_clp=r["total_clp"],
                            total_instalado_clp=r["total_instalado_clp"], resumen=r["resumen"], metodo=metodo)
    for x in r["avisos"]:
        st.warning(x)
    dolar = float(E.get("dolar", costos.DOLAR))
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Inversión en equipos auxiliares", C.esc("$" + C.fmt(r["total_clp"] / 1e6, 1) + " M"), f"US$ {C.fmt(r['total_usd'] / 1e6, 2)} M", delta_color="off")
    m2.metric(f"Instalada (factor {C.fmt(fi, 1)})", C.esc("$" + C.fmt(r["total_instalado_clp"] / 1e6, 1) + " M"))
    m3.metric("Potencia de bombeo", f"{C.fmt(r['bombas']['total_kw'], 1)} kW")
    m4.metric("Volumen de los pulmones", f"{C.fmt(sum(x['v_geo_m3'] for x in r['estanques']['filas']), 0)} m³")
    st.markdown("#### Resumen por rubro")
    C.mostrar_tabla([dict(rubro=x["rubro"], n=x["cantidad"], usd=x["costo_usd"], clp=x["costo_clp"], inst=x["instalado_usd"]) for x in r["resumen"]],
                    [("rubro", "Rubro", "txt", 0), ("n", "Cantidad", "num", 0), ("usd", "Costo comprado (US$)", "mm", 0),
                     ("clp", "Costo comprado ($)", "clp", 0), ("inst", "Costo instalado (US$)", "mm", 0)])
    st.caption(C.esc(f"Dólar ${C.fmt(dolar, 2)}. Costos del costeo (precio guardado, bibliografía o Supuesto, con CEPCI) salvo el estanque, que es Supuesto."))

    # ------------------------------------------------ bombas
    st.markdown("#### Bombas")
    b = r["bombas"]
    if b["filas"]:
        C.mostrar_tabla([dict(id=x["id"], ln=x["linea"], q=x["Q_m3h"], h=x["H_m"], d=x["D_mm"], v=x["v"], p=x["potencia_kW"],
                              dg="En el diagrama" if x["en_diagrama"] else "Agregada por el costeo", usd=x["costo_usd"], f=x["fuente_costo"])
                         for x in b["filas"]],
                        [("id", "Bomba", "txt", 0), ("ln", "Línea", "txt", 0), ("q", "Caudal (m³/h)", "num", 1), ("h", "Altura (m)", "num", 1),
                         ("d", "Diámetro interno (mm)", "num", 0), ("v", "Velocidad (m/s)", "num", 2), ("p", "Potencia (kW)", "num", 1),
                         ("dg", "Origen", "txt", 0), ("usd", "Costo (US$)", "mm", 0), ("f", "Fuente del costo", "txt", 0)])
        st.caption(C.esc(f"Potencia total {C.fmt(b['total_kw'], 1)} kW" + (f" y {C.fmt(b['energia_mwh'], 0)} MWh por temporada de {C.fmt(b['horas'], 0)} h." if b["energia_mwh"] else ".")))
    else:
        st.caption("La planta no mueve líquidos por cañería: no hay bombas que dimensionar.")

    # ------------------------------------------------ válvulas
    st.markdown("#### Válvulas")
    v = r["valvulas"]
    if v["control"]:
        C.mostrar_tabla([dict(id=x["id"], nb=x["nombre"], cv=x["Cv"], usd=x["costo_usd"], nota=x["nota"]) for x in v["control"]],
                        [("id", "Válvula", "txt", 0), ("nb", "Lazo", "txt", 0), ("cv", "Cv", "num", 1), ("usd", "Costo (US$)", "mm", 0),
                         ("nota", "Nota", "txt", 0)])
    else:
        st.caption("La planta no tiene lazos con válvula de control (se agregan en Lazos de control).")   # PAT 142
    st.caption(C.esc(f"Válvulas de bloqueo y retención de las bombas: {v['n_bloqueo']} de bloqueo y {v['n_retencion']} de retención. "
                     "El costeo no trae un precio para ellas: no suman a la inversión."))

    # ------------------------------------------------ estanques pulmón
    st.markdown("#### Estanques pulmón entre equipos")
    es = r["estanques"]
    if es["filas"]:
        C.mostrar_tabla([dict(id=f"{x['id']}", ent=f"{x['nombre_antes']} y {x['nombre_despues']}", c=x["carga_t_h"], r=x["masa_residencia_t"],
                              mt=x["mttr_h"], fa=x["masa_falla_t"], t=x["masa_t"], vu=x["v_util_m3"], vg=x["v_geo_m3"], dd=x["D_m"], hh=x["H_m"],
                              usd=x["costo_usd"]) for x in es["filas"]],
                        [("id", "Pulmón", "txt", 0), ("ent", "Entre", "txt", 0), ("c", "Carga del siguiente (t/h)", "num", 1),
                         ("r", "Por residencia (t)", "num", 1), ("mt", "MTTR anterior (h)", "num", 1), ("fa", "Por falla (t)", "num", 1),
                         ("t", "Capacidad adoptada (t)", "num", 1), ("vu", "Volumen útil (m³)", "num", 1), ("vg", "Volumen geométrico (m³)", "num", 1),
                         ("dd", "Diámetro (m)", "num", 2), ("hh", "Altura (m)", "num", 2), ("usd", "Costo (US$)", "mm", 0)])
        st.caption(C.esc(f"Método: {AX.NOMBRE_METODO[es['metodo']]}. La capacidad en t es comparable con los tanques de la pestaña Línea. "
                         f"Densidad: {es['filas'][0]['fuente_rho']}. Costo: {es['filas'][0]['fuente_costo']}."))
    else:
        st.caption("No hay pulmones: la línea principal tiene menos de dos equipos de proceso.")

    # ------------------------------------------------ cañerías
    st.markdown("#### Cañerías")
    cn = r["canerias"]
    if cn["lineas"]:
        C.mostrar_tabla([dict(ln=x["linea"], d=x["D_mm"], dn=f"DN {x['DN']} ({x['pulgadas']}\")", L=x["largo_m"], f=x["fuente_largo"]) for x in cn["lineas"]],
                        [("ln", "Línea", "txt", 0), ("d", "Diámetro interno (mm)", "num", 0), ("dn", "Diámetro nominal", "cen", 0),
                         ("L", "Largo (m)", "num", 1), ("f", "Fuente del largo", "txt", 0)])
        C.mostrar_tabla([dict(dn=f"DN {x['DN']} ({x['pulgadas']}\")", L=x["largo_m"], usd=x["costo_usd"], f=x["fuente_costo"]) for x in cn["por_dn"]],
                        [("dn", "Diámetro nominal", "txt", 0), ("L", "Largo total (m)", "num", 1), ("usd", "Costo (US$)", "mm", 0),
                         ("f", "Fuente del costo", "txt", 0)])
        if longitudes is None:
            st.caption("Sin layout, cada línea mide 30 m (Supuesto de motor/hidraulica.py). Calcule el layout para usar los largos reales.")
    else:
        st.caption("La planta no tiene líneas de líquido: no hay cañerías que dimensionar.")

    # ------------------------------------------------ servicios
    st.markdown("#### Servicios: vapor, calor, agua, aire y electricidad")
    sv = r["servicios"]
    C.mostrar_tabla([dict(s=x["servicio"], d=x["demanda"], u=x["unidad"], g=x["genera"], usd=x["costo_usd"], f=x["fuente"], n=x["nota"]) for x in sv["filas"]],
                    [("s", "Servicio", "txt", 0), ("d", "Demanda", "num", 1), ("u", "Unidad", "cen", 0), ("g", "Lo genera", "txt", 0),
                     ("usd", "Inversión (US$)", "mm", 0), ("f", "Fuente del costo", "txt", 0), ("n", "Nota", "txt", 0)])
    if sv.get("energia_kwh") is not None:
        st.caption(C.esc(f"Energía eléctrica: {C.fmt(sv['energia_kwh'] / 1e6, 2)} GWh por año con {C.fmt(sv['horas'], 0)} h, "
                         f"${C.fmt(sv['energia_clp'] / 1e6, 1)} M por año a ${C.fmt(float(kwh), 1)}/kWh."))
    with st.expander("Supuestos de los equipos auxiliares"):
        C.mostrar_tabla([dict(n=s.nombre, v=s.valor, u=s.unidad, j=s.justificacion) for s in AX.SUPUESTOS.values()],
                        [("n", "Supuesto", "txt", 0), ("v", "Valor", "num", 2), ("u", "Unidad", "cen", 0), ("j", "Justificación", "txt", 0)])
    return r
