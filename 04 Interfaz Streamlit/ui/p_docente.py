"""Pantalla Docente (PAT 136, tarea T20; puntos 2, 3 y 13 de los comentarios del profesor Torres del 13-11-2026).

El docente crea un curso, carga a sus estudiantes (uno por línea o en CSV), reparte al azar o a mano una combinación de tipo de
planta y tipo de demanda a cada uno y ve la tabla de asignaciones. El estudiante ingresa su nombre de usuario y ve la planta y la
demanda que le tocaron. Motor: pat_sim/datos/genericos.py y pat_sim/catalogos/plantas_genericas.py.

Acceso del docente: usuario docente con su clave (tabla usuarios, PBKDF2 con sal) o, por compatibilidad, la clave única del
profesor del Mantenedor (PROFESOR_CLAVE_SHA256). La asignación que carga el estudiante queda en st.session_state.asignacion_docente
(planta_id, demanda_id, curso) para que Diseño y Demanda la usen (tareas T21 y T22).

PAT 139 (13-11-2026): el docente elige qué reparte: el desafío de tomate (uno de los 10 tipos de planta de pasta de tomate ×
una de las 10 distribuciones de la llegada de tomate, como en la pantalla Desafío) o una planta genérica × demanda (10 rubros).
Por omisión, el de tomate. El estudiante con un desafío de tomate asignado lo ve en esta pantalla y en Desafío queda fijado.

PAT 139 (14-11-2026, comentarios del profesor Torres, punto 7): la combinación del desafío de tomate es modelo de planta (10, por °Brix y
proceso) × distribución de la llegada (10) × tamaño de la demanda (chica, mediana y grande) = 300, distinta para cada estudiante.
La asignación manual tiene tres listas, la tabla y el CSV traen el modelo y el tamaño, y la matriz de compatibilidad muestra un
símbolo por tamaño en cada celda. Las asignaciones guardadas con las 10 ids viejas (sin tamaño) se siguen mostrando.

PAT 144 a (20-11-2026): tercera familia, el desafío de agar agar (catalogos/plantas_agar.py): modelo de planta de agar (10) ×
distribución de la llegada de alga seca (10) × tamaño (3), con las mismas listas que el tomate (claves doc_man_agar_*). El
estudiante con un desafío de agar asignado lo ve aquí y en Desafío quedan fijos el rubro y las tres listas.

PAT 144 b (tarea T8, 20-11-2026): con sesión en la nube (ui/nube_ui.py) manda el rol de la cuenta. La cuenta docente entra sin
clave local, ve las cuentas de la nube, cambia el rol de otras cuentas (nunca el propio) y publica en la nube las asignaciones del
curso; la cuenta estudiante ve la asignación que le publicó su docente sin escribir su usuario. Sin sesión, todo sigue igual
(usuarios y claves PBKDF2 de la base local).
"""
from __future__ import annotations
import csv, io
import streamlit as st
from pat_sim.catalogos import plantas_genericas as PG
from pat_sim.catalogos import plantas_tomate as PT, plantas_agar as PAG
from pat_sim.motor import demanda as DM
from pat_sim.datos import genericos as GE
from pat_sim.datos import nube as N
from . import comun as C
from . import nube_ui as NU
from .p_desafio import cursiva

AYUDA = """**Para qué sirve.** Combina diez tipos de planta y diez tipos de demanda para que
cada estudiante reciba una combinación distinta. Esta pantalla guarda el curso, los estudiantes y sus asignaciones en la base.

**Cómo se usa.** El docente ingresa con su usuario y clave (o con la clave docente del Mantenedor), crea el curso, pega la
lista de estudiantes y reparte. El reparto al azar usa una semilla: con la misma semilla y la misma lista sale el mismo reparto.
Mientras alcancen las combinaciones compatibles, nadie repite; si hay más estudiantes, la repetición es la mínima y se avisa.

**Qué se reparte.** Por omisión, el desafío de tomate: uno de los 10 modelos de planta de pasta de tomate (que se distinguen por
los °Brix y el proceso), una de las 10 distribuciones de la llegada de tomate y uno de los 3 tamaños de la demanda (chica, mediana
y grande: 150.000 t, 450.000 t y 900.000 t de tomate por temporada), 300 combinaciones. El estudiante entra a Desafío y encuentra
su modelo, su distribución y su tamaño ya elegidos. También se puede repartir el desafío de agar agar (10 modelos de proceso, las
10 distribuciones de la llegada de alga seca y 3 tamaños: 200 t, 602 t y 1.200 t de agar al año, 300 combinaciones) o una planta
genérica de otro rubro con un tipo de demanda (10 × 10).

**Compatibilidad.** Cada combinación tiene un nivel: natural (la demanda propia del rubro), adaptable (tiene sentido con la
justificación que se muestra) o sin sentido. Por defecto se reparten las naturales y las adaptables. En el desafío de tomate las
300 combinaciones parten como naturales, porque la llegada de tomate es empujada por la cosecha; en el de agar agar también, porque
la llegada de alga seca es empujada por la oferta de los proveedores."""

NIVEL_OPC = {"Natural y adaptable": 1, "Solo natural": 2, "Todas, incluso las sin sentido": 0}


def _g():
    return GE.genericos(C.obtener_bd())


def _secretos():
    try:
        return st.secrets
    except Exception:
        return None


def _nombre_planta(pid):
    return PG.PLANTAS[pid]["nombre"] if pid in PG.PLANTAS else pid


def _nombre_demanda(did):
    return PG.DEMANDAS[did]["nombre"] if did in PG.DEMANDAS else did


def _tabla_operaciones(planta_id: str):
    p = PG.planta(planta_id)
    filas = [dict(o=str(o["orden"]), n=o["nombre"] + (" (opcional)" if o["opcional"] else ""), f=o["funcion_nombre"],
                  iso=f"{o['familia']} · {o['familia_nombre']}", l=o["letra"], e=", ".join(o["entrada"]) or "inicio", s=o["salida"])
             for o in p["operaciones"]]
    C.mostrar_tabla(filas, [("o", "N.°", "cen", 0), ("n", "Operación", "txt", 0), ("f", "Función de proceso", "txt", 0),
                            ("iso", "Familia ISO 10628", "txt", 0), ("l", "Letra", "cen", 0), ("e", "Estado que entra", "txt", 0),
                            ("s", "Estado que sale", "txt", 0)])
    srv = [dict(s=k, u="Sí" if v["usa"] else "No", d=v["uso"]) for k, v in p["servicios"].items()]
    C.mostrar_tabla(srv, [("s", "Servicio", "txt", 0), ("u", "Lo usa", "cen", 0), ("d", "Dónde", "txt", 0)])
    st.caption("Referencias: " + " · ".join(p["referencias_texto"]))


def _nombre_variante(v):
    return PT.VARIANTES[v]["nombre"] if v in PT.VARIANTES else v


def _nombre_modelo(m):
    return cursiva(PT.MODELOS[m]["nombre"]) if m in PT.MODELOS else m


def _nombre_tamano(t):
    return PT.TAMANOS[t]["nombre"] if t in PT.TAMANOS else (t or "")


def _nombre_distribucion(d):
    return DM.DISTRIBUCIONES[d]["nombre"] if d in DM.DISTRIBUCIONES else d


# PAT 144 a: desafío de agar agar
def _nombre_modelo_agar(m):
    return PAG.MODELOS[m]["nombre"] if m in PAG.MODELOS else m


def _nombre_tamano_agar(t):
    return PAG.TAMANOS[t]["nombre"] if t in PAG.TAMANOS else (t or "")


def _nombre_distribucion_agar(d):
    return DM.nombre_distribucion(d, "agar") if d in DM.DISTRIBUCIONES else d


def _ficha_agar(a: dict):
    v = a["detalle_planta"] or {}; d = a["detalle_demanda"] or {}
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Planta asignada:** {v.get('nombre', a.get('planta', ''))}")
        if v:
            st.caption(f"{PAG.MODELOS[v['modelo']]['nombre']}. Tamaño de la demanda: {C.fmt(v['agar_t_ano'], 0)} t de agar al año en "
                       f"{C.fmt(v['dias'], 0)} días, {C.fmt(v['horas_dia'], 0)} h por día.")
    with c2:
        st.markdown(f"**Llegada de alga seca asignada:** distribución {_nombre_distribucion_agar(a['distribucion_agar']).lower()}")
        if d:
            st.caption(f"Forma: {DM.texto_agar(d['forma'])}. {DM.EXPLICACION_AGAR.get(a['distribucion_agar'], d['explicacion'])}")
    st.caption(f"Curso: {a['curso']}. Compatibilidad: {PG.NIVELES.get(a['nivel'], '')}. {a.get('justificacion', '')}")


def _ficha_tomate(a: dict):
    v = a["detalle_planta"]; d = a["detalle_demanda"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(cursiva(f"**Planta asignada:** {v['nombre']}"))
        st.caption(cursiva(f"{PT.QUIEBRES[v['quiebre']]} a {C.fmt(v['T_quiebre'], 0)} °C; {C.fmt(v['brix'], 0)} °Brix; "
                           f"{PT.EVAPORADORES[v['evaporador']].lower()}. Tamaño de la demanda: {C.fmt(v['temporada_t'], 0)} t por temporada "
                           f"en {C.fmt(v['dias'], 0)} días, {C.fmt(v['horas_dia'], 0)} h por día."))
    with c2:
        st.markdown(f"**Llegada de tomate asignada:** distribución {d['nombre'].lower()}")
        st.caption(f"Forma: {d['forma']}. {d['explicacion']}")
    st.caption(f"Curso: {a['curso']}. Compatibilidad: {PG.NIVELES.get(a['nivel'], '')}. {a.get('justificacion', '')}")


def _ficha(a: dict):
    if a.get("familia") == "tomate":
        _ficha_tomate(a)
        return
    if a.get("familia") == "agar":
        _ficha_agar(a)
        return
    p = a["detalle_planta"]; d = a["detalle_demanda"]
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f"**Planta asignada:** {p['nombre']}")
        st.caption(f"Producto: {p['producto']}. Materia prima: {p['materia_prima']}. Región: {p['region']}.")
    with c2:
        st.markdown(f"**Demanda asignada:** {d['nombre']}")
        st.caption(f"Lógica: {PG.LOGICAS[d['logica']].lower()}. {d['descripcion']}")
    st.caption(f"Curso: {a['curso']}. Compatibilidad: {PG.NIVELES.get(a['nivel'], '')}. {a.get('justificacion', '')}")
    _tabla_operaciones(p["id"])


# ---------------------------------------------------------------- estudiante
def _estudiante(g):
    st.markdown("#### Mi asignación")
    usuario = st.text_input("Nombre de usuario", key="doc_usuario_est", help="El que le entregó su docente, por ejemplo ana.perez")
    clave = st.text_input("Clave (si su docente le fijó una)", type="password", key="doc_clave_est")
    if not usuario.strip():
        st.caption("Ingrese su nombre de usuario para ver su planta y su demanda.")
        return
    u = g.obtener_usuario(usuario)
    if u is None:
        st.warning("No encuentro ese usuario. Revise cómo lo escribió o pídale a su docente que lo cargue.")
        return
    if u["clave_hash"] and g.autenticar(usuario, clave) is None:
        st.info("Este usuario tiene clave: ingrésela para ver su asignación.")
        return
    a = g.asignacion_de(u["id"])
    if a is None:
        st.info("Todavía no tiene una asignación. Su docente debe repartir las combinaciones del curso.")
        return
    _mostrar_asignacion(a, u["nombre_usuario"])


def _estudiante_nube(s):
    """PAT 144 b: la asignación que el docente publicó en la nube para esta cuenta."""
    st.markdown("#### Mi asignación")
    if s.rol != "estudiante":
        st.caption("La asignación es de las cuentas con el rol estudiante: el docente la reparte en la pestaña Docente.")
        return
    try:
        fila = s.mi_asignacion()
    except N.ErrorNube as e:
        st.error(f"No se pudo leer la asignación en la nube: {e}")
        return
    if not fila or not (fila.get("datos") or {}).get("planta_id"):
        st.info("Todavía no tiene una asignación en la nube. Su docente debe repartir las combinaciones del curso y publicarlas.")
        return
    _mostrar_asignacion(fila["datos"], s.usuario)


def _mostrar_asignacion(a: dict, nombre_usuario: str):
    """Ficha de la asignación y su paso a la sesión (asignacion_docente) para Desafío, Diseño y Demanda."""
    ss = st.session_state
    _ficha(a)
    if a.get("familia") == "tomate":
        # PAT 139: sin demanda genérica, para que manden la variante y la distribución del desafío (comun.demanda_sesion)
        ss.asignacion_docente = dict(planta_id=a["planta_id"], demanda_id=None, curso=a["curso"], usuario=nombre_usuario,
                                     familia="tomate", variante_tomate=a["variante_tomate"], distribucion_tomate=a["distribucion_tomate"],
                                     tamano_tomate=a.get("tamano_tomate"), modelo_tomate=a.get("modelo_tomate"))
        st.info("Vaya a la pantalla Desafío: su modelo de planta, su distribución de la llegada y su tamaño de la demanda ya quedan "
                "elegidos. Ahí arma la planta ideal automáticamente o parte en blanco.")
        return
    if a.get("familia") == "agar":                  # PAT 144 a: como el tomate, sin demanda genérica
        ss.asignacion_docente = dict(planta_id=a["planta_id"], demanda_id=None, curso=a["curso"], usuario=nombre_usuario,
                                     familia="agar", variante_agar=a["variante_agar"], distribucion_agar=a["distribucion_agar"],
                                     tamano_agar=a.get("tamano_agar"), modelo_agar=a.get("modelo_agar"))
        st.info("Vaya a la pantalla Desafío: el rubro agar agar, su modelo de planta, su distribución de la llegada y su tamaño de la "
                "demanda ya quedan elegidos. Ahí arma la planta ideal automáticamente o parte en blanco.")
        return
    ss.asignacion_docente = dict(planta_id=a["planta_id"], demanda_id=a["demanda_id"], curso=a["curso"], usuario=nombre_usuario)
    p = a["detalle_planta"]
    if p["escenario"]:
        if st.button("Cargar el escenario base de mi planta", key="doc_cargar_escenario", width="stretch"):
            try:
                ss.pl = PG.crear_escenario(p["id"]); ss.pid = None; ss.vid = None
                for k in ("rc_dT", "rc_Tfin", "esc_rubro"):
                    ss.pop(k, None)
                st.success(f"Cargado el escenario de {p['nombre']}. Todas las pestañas trabajan con él.")
            except Exception as e:
                st.error(f"No se pudo cargar el escenario: {e}")
    else:
        st.info("Esta planta todavía no tiene un escenario calculado: parta en blanco en la pantalla Diseño con la cadena de "
                "operaciones de la tabla.")


# ---------------------------------------------------------------- docente
def _csv(filas) -> str:
    buf = io.StringIO(); w = csv.writer(buf, delimiter=";", lineterminator="\r\n")
    w.writerow(["Usuario", "Nombre", "Tipo", "Planta", "Modelo", "Tamaño", "Demanda o llegada", "Lógica", "Compatibilidad", "Modo", "Semilla",
                "Fecha"])
    for f in filas:
        tom = f.get("familia") == "tomate"
        aga = f.get("familia") == "agar"            # PAT 144 a
        w.writerow([f["nombre_usuario"], f["nombre"], "Tomate" if tom else "Agar agar" if aga else "Genérica", f["planta"],
                    (PT.MODELOS[f["modelo_tomate"]]["nombre"] if f.get("modelo_tomate") in PT.MODELOS else "") if tom
                    else _nombre_modelo_agar(f.get("modelo_agar")) if aga else "",
                    _nombre_tamano(f.get("tamano_tomate")) if tom else _nombre_tamano_agar(f.get("tamano_agar")) if aga else "", f["demanda"],
                    f["logica"], PG.NIVELES.get(f["nivel"], ""), f["modo"],
                    "" if f["semilla"] is None else f["semilla"], f["fecha"]])
    return "﻿" + buf.getvalue()


def _docente(g):
    st.markdown("#### Docente")
    usuario = st.text_input("Usuario docente (vacío = clave docente del Mantenedor)", key="doc_usuario")
    clave = st.text_input("Clave", type="password", key="doc_clave")
    if not clave:
        st.caption("Ingrese su clave para administrar cursos y asignaciones.")
        return
    if not g.es_docente(usuario.strip(), clave, _secretos()):
        st.error("Usuario o clave incorrectos.")
        return
    st.success("Acceso de docente.")
    _panel_docente(g, usuario.strip(), usuario.strip() or "docente")


def _cuentas_nube(s):
    """PAT 144 b: cuentas de la nube con su rol; el docente cambia el rol de otras cuentas (nunca el propio)."""
    with st.expander("Cuentas de la nube y sus roles"):
        st.caption("Las cuentas se crean en el panel de Supabase (*Authentication*, *Users*) y nacen con el rol visita, salvo que "
                   "tengan un rol preasignado. Aquí se cambia el rol de cada cuenta; nadie puede cambiar el suyo.")
        av = st.session_state.pop("_doc_nube_aviso", None)
        if av:
            (st.success if av[0] == "ok" else st.error)(av[1])
        try:
            perfiles = s.listar_perfiles()
        except N.ErrorNube as e:
            st.error(f"No se pudieron leer las cuentas de la nube: {e}")
            return
        C.mostrar_tabla([dict(u=p.get("usuario") or "", n=p.get("nombre") or "—", r=p.get("rol") or "") for p in perfiles],
                        [("u", "Usuario", "txt", 0), ("n", "Nombre", "txt", 0), ("r", "Rol", "cen", 0)])
        otras = [p for p in perfiles if p.get("id") != s.id]
        if not otras:
            st.caption("No hay otras cuentas en la nube.")
            return
        por_id = {p["id"]: p for p in otras}
        a, b, c = st.columns([2, 1, 1], vertical_alignment="bottom")
        pid = a.selectbox("Cuenta", list(por_id), format_func=lambda i: por_id[i].get("usuario") or por_id[i].get("email", i),
                          key="doc_nube_cuenta")
        rol = b.selectbox("Rol", list(N.ROLES), index=list(N.ROLES).index(por_id[pid].get("rol") or "visita"),
                          key=f"doc_nube_rol_{pid}")
        if c.button("Cambiar el rol", key="doc_nube_asignar", width="stretch", disabled=rol == por_id[pid].get("rol")):
            try:
                r = s.asignar_perfil(pid, rol)
                st.session_state["_doc_nube_aviso"] = ("ok", f"La cuenta {r.get('usuario') or por_id[pid].get('usuario')} quedó con el "
                                                             f"rol {r.get('rol', rol)}.")
            except (N.ErrorNube, ValueError) as e:
                st.session_state["_doc_nube_aviso"] = ("error", str(e))
            st.rerun()


def _publicar_nube(g, s, curso: dict):
    """PAT 144 b: copia en la nube las asignaciones del curso, cuenta por cuenta, por el nombre de usuario."""
    if st.button("Publicar las asignaciones en la nube", key="doc_nube_publicar", width="stretch",
                 help="Cada estudiante del curso con una cuenta de rol estudiante del mismo usuario en la nube ve su asignación al "
                      "ingresar, en la pestaña Estudiante."):
        try:
            cuentas = {(p.get("usuario") or "").casefold(): p for p in s.listar_perfiles() if p.get("rol") == "estudiante"}
            filas, sin_cuenta = [], []
            for f in g.asignaciones(curso["id"]):
                p = cuentas.get((f["nombre_usuario"] or "").casefold())
                if p is None:
                    sin_cuenta.append(f["nombre_usuario"])
                    continue
                a = g.asignacion_de(f["nombre_usuario"], curso["id"])
                filas.append(dict(estudiante_id=p["id"], curso=curso["nombre"], familia=a.get("familia") or "", datos=a))
            n = s.publicar_asignaciones(filas)
            st.success(f"Publicadas {n} asignaciones en la nube.")
            if sin_cuenta:
                st.warning("Sin cuenta de rol estudiante con el mismo usuario en la nube: " + ", ".join(sin_cuenta) + ".")
        except (N.ErrorNube, ValueError, TypeError, KeyError) as e:
            st.error(f"No se pudieron publicar las asignaciones: {e}")


def _docente_nube(g, s):
    """PAT 144 b: con sesión en la nube, el rol de la cuenta decide el acceso a esta pestaña."""
    st.markdown("#### Docente")
    if not s.es_docente():
        st.info("Esta pestaña es solo para las cuentas con el rol docente.")
        return
    _cuentas_nube(s)
    _panel_docente(g, s.usuario, s.usuario, nube=s)


def _panel_docente(g, usuario: str, quien: str, nube=None):
    """Cursos, estudiantes, reparto y asignaciones (con acceso de docente local o con la cuenta docente de la nube)."""
    ss = st.session_state

    with st.expander("Crear un curso o una cuenta de docente"):
        nuevo = st.text_input("Nombre del curso", key="doc_curso_nuevo", placeholder="Por ejemplo PAT 2026-2")
        periodo = st.text_input("Período", key="doc_periodo", placeholder="2026-2")
        if st.button("Crear el curso", key="doc_crear_curso", disabled=not nuevo.strip()):
            doc = g.obtener_usuario(usuario) if usuario else None
            g.crear_curso(nuevo, doc["id"] if doc and doc["rol"] == "docente" else None, periodo.strip())
            ss.doc_curso = nuevo.strip()
            st.success(f"Curso «{nuevo.strip()}» listo.")
        st.divider()
        nd = st.text_input("Usuario del nuevo docente", key="doc_nuevo_docente")
        nn = st.text_input("Nombre del nuevo docente", key="doc_nuevo_nombre")
        nc = st.text_input("Clave del nuevo docente (8 caracteres o más)", type="password", key="doc_nueva_clave")
        if st.button("Crear la cuenta de docente", key="doc_crear_docente", disabled=not nd.strip() or len(nc) < 8):
            g.crear_usuario(nd, nn, "docente", nc)
            st.success("Cuenta creada. La clave se guarda solo como hash PBKDF2 con sal.")

    cursos = [c["nombre"] for c in g.listar_cursos()]
    if not cursos:
        st.info("Todavía no hay cursos: cree uno arriba.")
        return
    if ss.get("doc_curso") not in cursos:
        ss.pop("doc_curso", None)
    nombre_curso = st.selectbox("Curso", cursos, key="doc_curso")
    curso = g.obtener_curso(nombre_curso)

    st.markdown("##### Estudiantes")
    texto = st.text_area("Uno por línea o CSV (usuario;nombre). Solo el nombre también sirve: «Ana Pérez» queda como ana.perez",
                         key="doc_estudiantes", height=140)
    if st.button("Cargar estudiantes", key="doc_cargar", disabled=not (texto or "").strip()):
        r = g.cargar_estudiantes(curso["id"], texto)
        st.success(f"Estudiantes nuevos: {r['creados']}. Ya estaban: {r['existentes']}.")
        for e in r["errores"]:
            st.warning(e)
    est = g.listar_usuarios(curso["id"], "estudiante")
    st.metric("Estudiantes del curso", len(est))

    fam = st.radio("Qué se reparte", list(GE.FAMILIAS), format_func=lambda k: GE.FAMILIAS[k], key="doc_familia", horizontal=True,
                   help="Desafío de tomate o de agar agar: modelo de planta × distribución de la llegada × tamaño de la demanda, como en "
                        "la pantalla Desafío. Planta genérica: uno de los 10 rubros con un tipo de demanda.")
    tom = fam == "tomate"
    aga = fam == "agar"                              # PAT 144 a

    st.markdown("##### Reparto al azar")
    c1, c2, c3 = st.columns(3)
    semilla = c1.number_input("Semilla", min_value=0, max_value=2**31 - 1, value=2026, step=1, key="doc_semilla",
                              help="Con la misma semilla y la misma lista sale el mismo reparto")
    nivel_txt = c2.selectbox("Combinaciones", list(NIVEL_OPC), key="doc_nivel")
    conservar = c3.checkbox("Conservar las asignaciones manuales", value=True, key="doc_conservar")
    n_comb = len(g.combinaciones(NIVEL_OPC[nivel_txt], fam))
    total = (len(PT.IDS_MODELOS) * len(PT.IDS_TAMANOS) * len(DM.IDS_DISTRIBUCIONES) if tom
             else len(PAG.IDS_MODELOS) * len(PAG.IDS_TAMANOS) * len(DM.IDS_DISTRIBUCIONES) if aga
             else len(PG.IDS_PLANTAS) * len(PG.IDS_DEMANDAS))
    st.caption(f"Combinaciones disponibles: {n_comb} de {total}.")
    if st.button("Repartir al azar", type="primary", key="doc_repartir", disabled=not est, width="stretch"):
        r = g.asignar_al_azar(curso["id"], int(semilla), NIVEL_OPC[nivel_txt], conservar, quien, familia=fam)
        st.success(f"Repartidas {len(r['asignaciones'])} asignaciones con la semilla {r['semilla']}.")
        for a in r["avisos"]:
            st.warning(a)

    st.markdown("##### Asignación manual")
    if est:
        if tom:
            m1, m2, m3, m4 = st.columns([1, 2, 1, 1])
            u_sel = m1.selectbox("Estudiante", [u["nombre_usuario"] for u in est], key="doc_man_est")
            m_sel = m2.radio("Modelo de planta de tomate", list(PT.IDS_MODELOS), format_func=_nombre_modelo, key="doc_man_modelo")
            d_sel = m3.selectbox("Distribución de la llegada", list(DM.IDS_DISTRIBUCIONES), format_func=_nombre_distribucion,
                                 key="doc_man_distribucion")
            t_sel = m4.radio("Tamaño de la demanda", list(PT.IDS_TAMANOS), format_func=_nombre_tamano, key="doc_man_tamano")
            p_sel = m_sel
            n = g.nivel_tomate(m_sel, d_sel, t_sel) or 0
            k = g.compatibilidad_tomate(m_sel, d_sel, t_sel)
            nom_p = lambda x: _nombre_variante(PT.id_compuesta(x, t_sel))
            nom_d = lambda x: "llegada " + _nombre_distribucion(x).lower()
        elif aga:                                    # PAT 144 a: las mismas listas que el tomate
            m1, m2, m3, m4 = st.columns([1, 2, 1, 1])
            u_sel = m1.selectbox("Estudiante", [u["nombre_usuario"] for u in est], key="doc_man_est")
            m_sel = m2.radio("Modelo de planta de agar agar", list(PAG.IDS_MODELOS), format_func=_nombre_modelo_agar, key="doc_man_agar_modelo")
            d_sel = m3.selectbox("Distribución de la llegada", list(DM.IDS_DISTRIBUCIONES), format_func=_nombre_distribucion_agar,
                                 key="doc_man_agar_distribucion")
            t_sel = m4.radio("Tamaño de la demanda", list(PAG.IDS_TAMANOS), format_func=_nombre_tamano_agar, key="doc_man_agar_tamano")
            p_sel = m_sel
            n = g.nivel_agar(m_sel, d_sel, t_sel) or 0
            k = g.compatibilidad_agar(m_sel, d_sel, t_sel)
            nom_p = lambda x: PAG.variante(PAG.id_compuesta(x, t_sel))["nombre"]
            nom_d = lambda x: "llegada " + _nombre_distribucion_agar(x).lower()
        else:
            m1, m2, m3 = st.columns(3)
            u_sel = m1.selectbox("Estudiante", [u["nombre_usuario"] for u in est], key="doc_man_est")
            p_sel = m2.selectbox("Planta", list(PG.IDS_PLANTAS), format_func=_nombre_planta, key="doc_man_planta")
            d_sel = m3.selectbox("Demanda", list(PG.IDS_DEMANDAS), format_func=_nombre_demanda, key="doc_man_demanda")
            t_sel = None
            n = g.nivel(p_sel, d_sel) or 0
            k = g.compatibilidad(p_sel, d_sel)
            nom_p, nom_d = _nombre_planta, _nombre_demanda
        st.caption(f"Compatibilidad: {PG.NIVELES[n]}. {k[0]['justificacion'] if k else ''}")
        forzar = st.checkbox("Asignar aunque la base la marque sin sentido", key="doc_man_forzar", disabled=n > 0)
        if st.button("Asignar", key="doc_asignar"):
            try:
                r = g.asignar(curso["id"], u_sel, p_sel, d_sel, forzar, quien, familia=fam, tamano_id=t_sel)
                st.success(f"Asignado a {u_sel}: {nom_p(p_sel)} con {nom_d(d_sel)}.")
                for a in r["avisos"]:
                    st.warning(a)
            except ValueError as e:
                st.error(str(e))
    else:
        st.caption("Cargue estudiantes para asignar a mano.")

    st.markdown("##### Asignaciones del curso")
    filas = g.asignaciones(curso["id"])
    if not filas:
        st.info("Todavía no hay asignaciones en este curso.")
    else:
        distintas = len({GE.combinacion(f) for f in filas})
        st.caption(f"{len(filas)} asignaciones, {distintas} combinaciones distintas.")
        C.mostrar_tabla([dict(f, niv=PG.NIVELES.get(f["nivel"], ""), sem="" if f["semilla"] is None else str(f["semilla"]),
                              tip={"tomate": "Tomate", "agar": "Agar agar"}.get(f.get("familia"), "Genérica"),
                              tam=(_nombre_tamano(f.get("tamano_tomate")) or "—" if f.get("familia") == "tomate"
                                   else _nombre_tamano_agar(f.get("tamano_agar")) or "—" if f.get("familia") == "agar" else ""),
                              mod="Al azar" if f["modo"] == "azar" else "Manual", fec=f["fecha"].replace("T", " ")) for f in filas],
                        [("nombre_usuario", "Usuario", "txt", 0), ("nombre", "Nombre", "txt", 0), ("tip", "Tipo", "cen", 0),
                         ("planta", "Planta", "txt", 0), ("tam", "Tamaño", "cen", 0), ("demanda", "Demanda o llegada", "txt", 0),
                         ("niv", "Compatibilidad", "cen", 0), ("mod", "Modo", "cen", 0),
                         ("sem", "Semilla", "cen", 0), ("fec", "Fecha", "cen", 0)])
        st.download_button("Exportar asignaciones (CSV)", _csv(filas), file_name=f"Asignaciones_{nombre_curso.replace(' ', '_')}.csv",
                           mime="text/csv", key="doc_csv", width="stretch")
        if nube is not None:
            _publicar_nube(g, nube, curso)

    if tom:
        with st.expander("Matriz de compatibilidad modelo de planta × distribución de la llegada × tamaño"):
            sig = {2: "N", 1: "A", 0: "·"}
            mapa = {(f["variante_id"], f["tamano_id"], f["distribucion_id"]): f["nivel"] for f in g.compatibilidad_tomate()
                    if f.get("tamano_id")}
            cols = [("p", "Modelo de planta", "txt", 0)] + [(d, DM.DISTRIBUCIONES[d]["nombre"], "cen", 0) for d in DM.IDS_DISTRIBUCIONES]
            C.mostrar_tabla([dict(p=PT.MODELOS[m]["corto"], **{d: " ".join(sig[mapa.get((m, t, d), 0)] for t in PT.IDS_TAMANOS)
                                                              for d in DM.IDS_DISTRIBUCIONES}) for m in PT.IDS_MODELOS], cols)
            st.caption("Cada celda trae tres símbolos, en el orden tamaño chica, mediana y grande. N = natural, A = adaptable, · = sin sentido. "
                       "Criterio: Supuesto del equipo PAT 139 (todas naturales); se cambia en la base.")
        return
    if aga:                                          # PAT 144 a
        with st.expander("Matriz de compatibilidad modelo de planta × distribución de la llegada × tamaño"):
            sig = {2: "N", 1: "A", 0: "·"}
            mapa = {(f["variante_id"], f["tamano_id"], f["distribucion_id"]): f["nivel"] for f in g.compatibilidad_agar()}
            cols = [("p", "Modelo de planta", "txt", 0)] + [(d, _nombre_distribucion_agar(d), "cen", 0) for d in DM.IDS_DISTRIBUCIONES]
            C.mostrar_tabla([dict(p=PAG.MODELOS[m]["etiqueta"], **{d: " ".join(sig[mapa.get((m, t, d), 0)] for t in PAG.IDS_TAMANOS)
                                                                  for d in DM.IDS_DISTRIBUCIONES}) for m in PAG.IDS_MODELOS], cols)
            st.caption("Cada celda trae tres símbolos, en el orden tamaño chica, mediana y grande. N = natural, A = adaptable, · = sin sentido. "
                       "Criterio: Supuesto del equipo PAT 144 a (todas naturales).")
        return
    with st.expander("Matriz de compatibilidad planta × demanda"):
        sig = {2: "N", 1: "A", 0: "·"}
        mapa = {(f["planta_id"], f["demanda_id"]): f["nivel"] for f in g.compatibilidad()}
        cols = [("p", "Planta", "txt", 0)] + [(d, PG.DEMANDAS[d]["nombre"], "cen", 0) for d in PG.IDS_DEMANDAS]
        C.mostrar_tabla([dict(p=PG.PLANTAS[p]["nombre"], **{d: sig[mapa.get((p, d), 0)] for d in PG.IDS_DEMANDAS}) for p in PG.IDS_PLANTAS], cols)
        st.caption("N = natural, A = adaptable, · = sin sentido. Criterio: Supuesto del equipo T20 (PAT 136); se cambia en la base.")


def mostrar():
    st.subheader("Docente: plantas, demandas y asignaciones")
    C.ayuda(AYUDA, "Ayuda de la pantalla")
    try:
        g = _g()
    except Exception as e:                      # la base no responde: la pantalla avisa y no detiene la aplicación
        st.error(f"No se pudo abrir la base de datos genérica: {e}")
        return
    t_est, t_doc, t_cat = st.tabs(["Estudiante", "Docente", "Catálogo de plantas"])
    s = NU.sesion()                              # PAT 144 b: con sesión en la nube manda el rol de la cuenta
    with t_est:
        _estudiante_nube(s) if s is not None else _estudiante(g)
    with t_doc:
        _docente_nube(g, s) if s is not None else _docente(g)
    with t_cat:
        pid = st.selectbox("Tipo de planta", list(PG.IDS_PLANTAS), format_func=_nombre_planta, key="doc_cat_planta")
        p = PG.planta(pid)
        st.caption(f"Producto: {p['producto']}. Materia prima: {p['materia_prima']}. Unidad: {p['unidad']}. "
                   f"Demanda por defecto: {_nombre_demanda(p['demanda_defecto'])}. "
                   + ("Escenario calculado: " + p["escenario_funcion"] if p["escenario"] else "Sin escenario calculado todavía."))
        _tabla_operaciones(pid)
