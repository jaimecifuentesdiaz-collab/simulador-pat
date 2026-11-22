"""Pantalla Proyectos (PAT 138, pedido de Jaime del 13-11-2026): guardar el proyecto actual con su nombre automático
«Proyecto de <persona> <n>» (editable y sin repetir), lista de proyectos guardados con buscador, y Cargar, Renombrar y Eliminar.
Cada proyecto guarda la planta y el estado de la sesión (desafío, economía, temporada, layout y demás) con su historial de
versiones. Las plantas de ejemplo y las versiones guardadas antes de PAT 138 se cargan desde el desplegable del final.
PAT 140 g (17-11-2026): cada proyecto muestra su último guardado automático (la «partida») y permite abrirlo; «Descargar partida
(.json)» y «Cargar partida (.json)» llevan la partida a un archivo, para la versión publicada en internet.
PAT 144 b (tarea T8, 20-11-2026): con sesión en la nube la pantalla lista, guarda y abre los proyectos de Supabase (los propios,
los ejemplos y, para el docente, los de todas las cuentas, según las reglas RLS); la cuenta de visita solo abre y descarga."""
from __future__ import annotations
import streamlit as st
from pat_sim.catalogos import plantas_genericas as PG, plantas_tomate as PT
from pat_sim.motor import demanda as DM
from pat_sim.datos import nube as N
from . import comun as C
from . import nube_ui as NU
from . import proyectos as PRY

MAX_FILAS = 100          # filas de la tabla; el buscador y el selector llegan a todos


def _tipo(r: dict) -> str:
    t = r.get("tipo_planta") or ""
    nombre = PG.PLANTAS[t]["nombre"] if t in PG.PLANTAS else (t or "—")
    v = r.get("variante_tomate")
    if v in PT.VARIANTES:
        nombre = PT.VARIANTES[v]["nombre"]
    d = r.get("distribucion_tomate")
    if d in DM.DISTRIBUCIONES:
        nombre += f", llegada {DM.DISTRIBUCIONES[d]['nombre'].lower()}"
    return nombre


def _fecha(t: str | None) -> str:
    """2026-11-13T16:39:05 → 13-11-2026 16:39."""
    if not t or len(t) < 16:
        return t or ""
    return f"{t[8:10]}-{t[5:7]}-{t[0:4]} {t[11:16]}"


def _aviso():
    av = st.session_state.pop(PRY.CLAVE_AVISO, None)
    if av:
        (st.success if av[0] == "ok" else st.error)(C.esc(av[1]))


def _guardar_seccion(bd, ab):
    ss = st.session_state
    st.markdown("#### Guardar el proyecto actual")
    if PRY.solo_lectura():                       # PAT 144 b: cuenta de visita de la nube
        st.info("La cuenta de visita es de solo lectura: puede abrir los proyectos de ejemplo de la lista y descargarlos en un "
                "archivo (.json), pero no guardarlos en la nube.")
        return
    if ab:
        a, b = st.columns([3, 1], vertical_alignment="bottom")
        nota = a.text_input("Nota de esta versión (opcional)", key="pys_nota_abierto", placeholder="Qué cambió")
        if b.button("Guardar cambios", type="primary", key="pys_guardar", width="stretch",
                    help=f"Agrega una versión a «{ab['nombre']}». Las versiones anteriores quedan en el historial."):
            r = PRY.guardar(nota=nota)
            ss[PRY.CLAVE_AVISO] = ("ok" if r["ok"] else "error", r["mensaje"])
            st.rerun()
    pers = PRY.persona()
    sugerido = bd.nombre_sugerido(pers)
    st.caption(C.esc(f"Nombre automático: «Proyecto de <su nombre> <n>», con el nombre escrito en Desafío"
                     + (f" ({pers})." if pers else " (no hay nombre: queda «Proyecto <n>»).") + " Puede cambiarlo antes de guardar."))
    a, b, c = st.columns([2, 2, 1], vertical_alignment="bottom")
    nombre = a.text_input("Nombre del proyecto nuevo", value=sugerido, key=f"pys_nombre__{sugerido}")
    nota = b.text_input("Nota (opcional)", key="pys_nota_nuevo", placeholder="Por ejemplo, primera planta ideal")
    if c.button("Guardar como proyecto nuevo", type="secondary" if ab else "primary", key="pys_nuevo", width="stretch"):
        r = PRY.guardar(nombre=nombre, nota=nota, nuevo=True)
        if r.get("repetido") is not None:
            e = r["repetido"]
            ss["_pys_repetido"] = dict(nombre=e.nombre, sugerido=e.sugerido, nota=nota)
        else:
            ss.pop("_pys_repetido", None)
            ss[PRY.CLAVE_AVISO] = ("ok" if r["ok"] else "error", r["mensaje"])
            st.rerun()
    rep = ss.get("_pys_repetido")
    if rep:
        st.warning(C.esc(f"Ya existe un proyecto llamado «{rep['nombre']}». Puede sobrescribirlo (la planta y la sesión actuales "
                         f"quedan como su versión más nueva; las anteriores siguen en su historial) o usar el siguiente número."))
        x, y, z = st.columns(3)
        if x.button(f"Sobrescribir «{rep['nombre']}»", key="pys_sobrescribir", width="stretch"):
            r = PRY.guardar(nombre=rep["nombre"], nota=rep["nota"], nuevo=True, sobrescribir=True)
            ss.pop("_pys_repetido", None); ss[PRY.CLAVE_AVISO] = ("ok" if r["ok"] else "error", r["mensaje"]); st.rerun()
        if y.button(f"Guardar como «{rep['sugerido']}»", key="pys_siguiente", type="primary", width="stretch"):
            r = PRY.guardar(nombre=rep["sugerido"], nota=rep["nota"], nuevo=True)
            ss.pop("_pys_repetido", None); ss[PRY.CLAVE_AVISO] = ("ok" if r["ok"] else "error", r["mensaje"]); st.rerun()
        if z.button("Cancelar", key="pys_repetido_no", width="stretch"):
            ss.pop("_pys_repetido", None); st.rerun()


def _lista(bd, ab):
    ss = st.session_state
    st.markdown("#### Proyectos guardados")
    buscar = st.text_input("Buscar por nombre o persona", key="pys_buscar", placeholder="Por ejemplo, Ana o pérez")
    du = PRY.dueno()                             # PAT 139: con acceso controlado, el estudiante ve solo sus proyectos
    filas = bd.listar_proyectos_usuario(buscar=buscar, usuario=du)
    total = bd.contar_proyectos_usuario()["proyectos"] if du is None else len(bd.listar_proyectos_usuario(usuario=du))
    nube = NU.sesion()
    if du is not None:
        st.caption(f"Proyectos del usuario {du}. Los de otros usuarios no se ven ni se pueden cambiar.")
    elif nube is not None:                       # PAT 144 b: qué deja ver la nube a cada rol
        st.caption({"docente": "Se ven los proyectos de todas las cuentas del curso. Solo se guarda, renombra o elimina en los "
                               "propios; los de los estudiantes se abren para revisarlos.",
                    "estudiante": "Se ven sus proyectos y los ejemplos que publica el docente. Los de otras cuentas no se ven.",
                    "visita": "Se ven solo los proyectos de ejemplo."}.get(nube.rol, ""))
    if not filas:
        st.info("No hay proyectos guardados con ese nombre." if buscar and total else
                "Todavía no hay proyectos guardados. Arme la planta (Desafío o Planta ficticia) y presione «Guardar proyecto».")
        return
    try:
        autos = bd.fechas_autoguardado()
    except Exception:
        autos = {}
    tabla = []
    for p in filas[:MAX_FILAS]:
        r = p.get("resumen") or {}
        marca = ", ".join(x for x, si in (("Abierto", ab and ab["id"] == p["id"]), ("Ejemplo", p.get("es_ejemplo"))) if si)
        tabla.append(dict(abierto=marca, cuenta=p.get("usuario") or "—", nombre=p["nombre"], persona=p["persona"] or "—",
                          mod=_fecha(p["modificado"]) if p.get("n_versiones") else "—", auto=_fecha(autos.get(p["id"])) or "—",
                          tipo=_tipo(r), eq=r.get("equipos"), cap=r.get("capacidad_t_h"),
                          kw=r.get("kw_recuperados"), inv=r.get("inversion_m"), van=r.get("van_m"), n=p["n_versiones"]))
    C.ayuda("Una fila por proyecto, del último guardado al primero. Guardado: la última versión numerada («Guardar proyecto»). "
            "Guardado automático: la última vez que el simulador guardó solo los cambios (lo que se retoma al volver a abrir el simulador). Capacidad: tomate (u otra materia prima) de diseño por hora. "
            "kW recuperados: calor de la cascada en serie. Inversión: la de la pantalla Economía; VAN de la cascada con esa inversión "
            "(solo si se ingresó una). «—»: la cifra no aplica o la planta no estaba resuelta al guardar.", "Lista de proyectos", 5)
    col_cuenta = [("cuenta", "Cuenta", "txt", 0)] if nube is not None and nube.es_docente() else []   # PAT 144 b
    C.mostrar_tabla(tabla, [("abierto", "", "txt", 0), ("nombre", "Proyecto", "txt", 0)] + col_cuenta + [("persona", "Persona", "txt", 0),
                            ("mod", "Guardado", "txt", 0), ("auto", "Guardado automático", "txt", 0), ("tipo", "Tipo de planta", "txt", 0), ("eq", "Equipos", "num", 0),
                            ("cap", "Capacidad (t/h)", "num", 1), ("kw", "kW recuperados", "num", 1), ("inv", "Inversión (M$)", "mm", 1),
                            ("van", "VAN (M$)", "mm", 1), ("n", "Versiones", "num", 0)])
    st.caption(f"{len(filas)} de {total} proyectos" + (f"; la tabla muestra los {MAX_FILAS} más recientes, el selector de abajo los tiene todos."
                                                      if len(filas) > MAX_FILAS else "."))
    ids = [p["id"] for p in filas]; por_id = {p["id"]: p for p in filas}
    i0 = ids.index(ab["id"]) if ab and ab["id"] in ids else 0
    if ss.get("pys_sel") not in ids:
        ss.pop("pys_sel", None)
    a, b = st.columns([3, 2])
    sel = a.selectbox("Proyecto", ids, index=i0, key="pys_sel",
                      format_func=lambda i: f"{por_id[i]['nombre']} · {_fecha(por_id[i]['modificado'])}")
    vers = bd.listar_versiones_usuario(sel)
    opciones = [0] + [v["numero"] for v in vers]; por_num = {v["numero"]: v for v in vers}   # 0: la última
    fa = autos.get(sel)                          # PAT 140 g: -1 es el guardado automático del proyecto
    if fa:                                       # primero si tiene cambios más nuevos que la última versión numerada
        ultima = vers[0]["fecha"] if vers else ""
        try:
            igual = bool(vers) and bd.autoguardado_igual_a_version(sel)
        except Exception:
            igual = False
        opciones = ([-1] + opciones) if fa >= ultima and not igual else (opciones[:1] + [-1] + opciones[1:])
    if not vers and fa:
        opciones = [n for n in opciones if n != 0]
    if ss.get(f"pys_ver_{sel}") not in opciones:
        ss.pop(f"pys_ver_{sel}", None)
    ver = b.selectbox("Versión", opciones, key=f"pys_ver_{sel}",
                      format_func=lambda n: f"Guardado automático · {_fecha(fa)}" if n == -1 else "La última" if not n else
                      f"v{n} · {_fecha(por_num[n]['fecha'])}" + (f" · {por_num[n]['nota']}" if por_num[n]["nota"] else ""))
    propio = nube is None or por_id[sel].get("propio", True)   # PAT 144 b: en la nube solo la cuenta dueña renombra o elimina
    x, y, z = st.columns(3)
    if x.button("Cargar", type="primary", key="pys_cargar", width="stretch",
                help="Reemplaza la planta y la sesión por las del proyecto. Guarde antes si tiene cambios."):
        PRY.pedir_carga(sel, "auto" if ver == -1 else (ver or None))
    nuevo = y.text_input("Nuevo nombre", value=por_id[sel]["nombre"], key=f"pys_renombre_{sel}", label_visibility="collapsed")
    if y.button("Renombrar", key="pys_renombrar", width="stretch", disabled=not propio):
        try:
            n = bd.renombrar_proyecto_usuario(sel, nuevo)
            if ab and ab["id"] == sel:
                ss[PRY.CLAVE_ABIERTO] = dict(ab, nombre=n)
            ss[PRY.CLAVE_AVISO] = ("ok", f"Proyecto renombrado: «{n}».")
            ss.pop(f"pys_renombre_{sel}", None)
        except (ValueError, KeyError, N.ErrorNube) as e:
            ss[PRY.CLAVE_AVISO] = ("error", str(e) + "." + (f" Pruebe con «{e.sugerido}»." if getattr(e, "sugerido", None) else ""))
        st.rerun()
    if ss.get("_pys_confirmar") == sel:
        z.warning(C.esc(f"¿Eliminar «{por_id[sel]['nombre']}» con sus {por_id[sel]['n_versiones']} versiones? No se puede deshacer."))
        s1, s2 = z.columns(2)
        if s1.button("Sí, eliminar", key="pys_eliminar_si", type="primary", width="stretch"):
            try:
                bd.eliminar_proyecto_usuario(sel)
                if ab and ab["id"] == sel:
                    PRY.cerrar()
                ss[PRY.CLAVE_AVISO] = ("ok", f"Proyecto «{por_id[sel]['nombre']}» eliminado.")
            except N.ErrorNube as e:                 # PAT 144 b: la nube no deja eliminar lo ajeno
                ss[PRY.CLAVE_AVISO] = ("error", str(e) + ".")
            ss.pop("_pys_confirmar", None); ss.pop("pys_sel", None)
            st.rerun()
        if s2.button("Cancelar", key="pys_eliminar_no", width="stretch"):
            ss.pop("_pys_confirmar", None); st.rerun()
    elif z.button("Eliminar", key="pys_eliminar", width="stretch", disabled=not propio):
        ss["_pys_confirmar"] = sel
        st.rerun()
    if nube is not None and nube.es_docente():  # PAT 144 b: el docente publica ejemplos para todas las cuentas
        ej = bool(por_id[sel].get("es_ejemplo"))
        if st.button("Quitar de los ejemplos" if ej else "Publicar como ejemplo", key="pys_ejemplo",
                     help="Un ejemplo lo ven y lo abren todas las cuentas, también la de visita; solo su dueño lo cambia."):
            try:
                bd.marcar_ejemplo(sel, not ej)
                ss[PRY.CLAVE_AVISO] = ("ok", f"«{por_id[sel]['nombre']}» " + ("ya no es un ejemplo." if ej else "quedó publicado como ejemplo."))
            except N.ErrorNube as e:
                ss[PRY.CLAVE_AVISO] = ("error", str(e) + ".")
            st.rerun()


def _partida_archivo():
    """PAT 140 g: la partida en un archivo, para llevarla a otro computador o guardarla fuera de la versión publicada."""
    ss = st.session_state
    st.markdown("#### Subir o descargar un proyecto en un archivo")
    st.caption("«Subir proyecto desde un archivo» abre el explorador de archivos del computador para elegir un .json, como cuando se "
               "adjunta un documento. «Descargar proyecto» guarda el proyecto como está ahora en un archivo .json, en la carpeta de "
               "descargas del navegador; ese archivo se puede mover a cualquier carpeta y subir después, también en otro computador.")
    a, b = st.columns(2)
    try:
        datos, archivo = PRY.exportar_partida()
        a.download_button("Descargar proyecto (.json)", datos, file_name=archivo, mime="application/json", key="pys_partida_bajar",
                          width="stretch", help="Descarga la planta y todas las pantallas como están ahora, en un archivo que se "
                                               "vuelve a abrir con «Subir proyecto desde un archivo (.json)».")
    except Exception as e:
        a.caption(f"No se pudo preparar el proyecto para descargar: {e}")
    if PRY.solo_lectura():                       # PAT 144 b: subir crea un proyecto; la visita solo descarga
        return
    sub = b.file_uploader("Subir proyecto desde un archivo (.json)", type=["json"], key="pys_partida_subir",
                          help="Abre un proyecto descargado antes. Queda como un proyecto nuevo (versión 1) y se carga en todas las pantallas.")
    if sub is not None:
        try:
            contenido = sub.getvalue()
        except Exception:
            contenido = sub.read()
        import hashlib
        h = hashlib.sha1(contenido or b"").hexdigest()
        if ss.get(PRY.CLAVE_ARCHIVO) != h:     # el archivo queda en el campo después de cargarlo: se carga una sola vez
            ss[PRY.CLAVE_ARCHIVO] = h
            r = PRY.importar_partida(contenido)
            ss[PRY.CLAVE_AVISO] = ("ok" if r["ok"] else "error", r["mensaje"])
            st.rerun()


def _antiguas(bd):
    """Plantas de ejemplo y versiones de la fase 4 (tablas proyectos y versiones): se cargan solo como planta."""
    ss = st.session_state
    with st.expander("Plantas de ejemplo y versiones guardadas antes de PAT 138"):
        st.caption("La planta basada en Agrozzi, los escenarios de pellet, chip y leña y las versiones guardadas antes de esta "
                   "pantalla. Se cargan como planta de la sesión; el resto de la sesión no cambia.")
        proy = bd.listar_proyectos()
        if not proy:
            st.info("No hay versiones antiguas en la base.")
            return
        nombres = {p["id"]: p["nombre"] for p in proy}
        a, b = st.columns(2)
        pid = a.selectbox("Planta o proyecto antiguo", list(nombres), format_func=lambda i: nombres[i], key="pys_ant_proy")
        vers = bd.listar_versiones(pid)
        if not vers:
            st.info("Ese proyecto no tiene versiones.")
            return
        por = {v["id"]: v for v in vers}
        vid = b.selectbox("Versión", list(por), key=f"pys_ant_ver_{pid}",
                          format_func=lambda i: f"v{por[i]['numero']} · {por[i]['fecha']} · {por[i]['nota'] or 'sin nota'}")
        if st.button("Cargar esta planta", key="pys_ant_cargar"):
            try:
                C.fijar_planta(C.con_capacidades(bd.cargar_version(vid)), pid=pid, vid=vid)
                for k in ("rc_dT", "rc_Tfin", "esc_rubro"):
                    ss.pop(k, None)
                ss[PRY.CLAVE_AVISO] = ("ok", f"Cargada la versión {por[vid]['numero']} de «{nombres[pid]}». El proyecto abierto no "
                                             "cambia: «Guardar proyecto» la guarda en él.")
            except Exception as e:
                ss[PRY.CLAVE_AVISO] = ("error", f"No se pudo cargar la versión: {e}")
            st.rerun()


def mostrar():
    bd = PRY.almacen()                           # PAT 144 b: la nube con sesión iniciada; si no, la base local
    st.subheader("Proyectos")
    st.caption("El simulador guarda solo cada cambio, como una partida de juego, y al volver a abrirlo ofrece «Continuar con el "
               "último proyecto». «Guardar proyecto» deja además una versión numerada, para volver a ella cuando quiera.")
    if NU.activa():
        st.caption("Los proyectos de esta cuenta quedan en la nube: se abren al ingresar con la misma cuenta desde cualquier computador. "
                   "Si otra sesión guardó una versión más nueva del mismo proyecto, el guardado se rechaza para no sobrescribir ese trabajo.")
    else:
        st.caption("En la versión publicada en internet lo guardado se borra cada vez que el servidor se reinicia: antes de cerrar, use "
                   "«Descargar proyecto (.json)» (más abajo) y la próxima vez súbalo con «Subir proyecto desde un archivo (.json)». En un computador "
                   "propio los proyectos y la partida quedan guardados en ese computador.")
    _aviso()
    ab = PRY.abierto()
    A = st.session_state.get(PRY.CLAVE_AUTO) or {}
    if ab:
        st.markdown(C.esc(f"**Proyecto abierto:** {ab['nombre']}" + (f" (versión {ab['version']})" if ab.get("version") else
                                                                       " (sin versiones numeradas todavía)")))
        if A.get("al_dia") and A.get("fecha"):
            st.caption(f":green[Guardado automático: {PRY.fecha_corta(A['fecha'], segundos=True)}.]")
        st.caption(":orange[Hay cambios sin guardar como versión numerada.]" if PRY.cambios_sin_guardar() else ":green[Todo guardado.]")
    else:
        st.markdown("**Proyecto abierto:** ninguno. Con el primer cambio, el guardado automático crea un proyecto con el nombre automático.")
    try:
        _guardar_seccion(bd, ab)
        st.divider()
        _lista(bd, ab)
    except N.ErrorNube as e:                     # PAT 144 b: sin red la pantalla avisa; la sesión sigue con lo que tiene
        st.error(f"No se pudo leer la nube: {e}")
    st.divider()
    _partida_archivo()
    _antiguas(C.obtener_bd())                    # las plantas de ejemplo y las versiones antiguas son de la base local
