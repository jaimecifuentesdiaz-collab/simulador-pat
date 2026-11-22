"""Proyectos del usuario en la interfaz (PAT 138, pedido de Jaime del 13-11-2026).

Una sola forma de guardar: el botón «Guardar proyecto» de la barra lateral, la pantalla Proyectos, el botón «Guardar» del lienzo
de Planta ficticia y el de Escenario usan guardar() de este módulo. Cada proyecto se llama «Proyecto de <persona> <n>» (la
persona es el nombre escrito en Desafío o el usuario con sesión; sin nombre, «Proyecto <n>») y guarda la planta, el estado de la
sesión (pat_sim/datos/estado_sesion.py) y las cifras clave. Cargar deja la planta como planta única (C.fijar_planta) y el estado
como estaba al guardar, para que todas las pantallas queden como se dejaron.

La carga se pide con pedir_carga() y se aplica al comienzo de la ejecución siguiente (C.iniciar_estado), antes de dibujar los
widgets: Streamlit no deja cambiar el valor de un widget ya dibujado.

PAT 140 g (17-11-2026): guardado automático tipo «partida». autoguardar() corre al final de cada ejecución (app.py): si la sesión
cambió, sobrescribe la ranura de autoguardado del proyecto abierto (o crea uno con el nombre automático), como máximo una vez cada
INTERVALO segundos o al cambiar de pantalla; un fragmento con run_every guarda lo que quedó pendiente aunque el usuario no toque
nada. Al abrir la aplicación, oferta_partida() ofrece «Continuar con el último proyecto». Las versiones numeradas siguen siendo solo las
del botón «Guardar proyecto». Con PAT_AUTOGUARDADO=0 no se guarda solo (para pruebas que lo necesiten).

PAT 144 b (tarea T8, 20-11-2026): con sesión en la nube (ui/nube_ui.py), almacen() entrega los proyectos de la cuenta en Supabase
(pat_sim/datos/nube.AlmacenNube, con los mismos métodos que la base local) y todo lo de este módulo, también el guardado automático,
la última partida y los archivos .json, trabaja contra la nube. Lo que cada cuenta ve o cambia lo deciden las reglas RLS de la base;
la cuenta de visita es de solo lectura y no se guarda sola. Sin sesión, todo sigue igual con la base local.
"""
from __future__ import annotations
import hashlib, json, os, re, time
import streamlit as st
from pat_sim.datos import estado_sesion as ES
from pat_sim.datos.bd import NombreRepetido, limpiar_nombre, nombre_equipo, partida_a_json, leer_partida
from . import comun as C
from . import nube_ui as NU

CLAVE_ABIERTO = "proyecto_abierto"          # {id, nombre, version}
CLAVE_GUARDADO = "_proyecto_guardado"       # {v, hp, foto}: versión y huella de la planta y foto del estado al guardar o cargar
CLAVE_PENDIENTE = "_proyecto_por_cargar"    # (id, versión o None)
CLAVE_AVISO = "_proyecto_aviso"             # (tipo, texto) para la pantalla Proyectos
CLAVE_AVISO_LATERAL = "_proyecto_aviso_lateral"
CLAVE_AUTO = "_autoguardado"                # {h, hp0, foto0, t, fecha, pid, pagina, pendiente, al_dia, error, ajeno}
CLAVE_OFERTA = "_partida_oferta"            # última partida ofrecida al abrir ({} si no hay o ya se decidió)
CLAVE_ARCHIVO = "_partida_archivo"          # huella del último archivo de partida cargado (para no cargarlo dos veces)
INTERVALO = 20                              # segundos entre dos guardados automáticos (o antes, al cambiar de pantalla)
# claves que, si aparecen en una sesión nueva, cuentan como trabajo del usuario (crean el proyecto del guardado automático)
_CLAVES_TRABAJO = ("desafio", "persona_nombre", "datos_medidos", "distribuciones")
# resultados y avisos de la planta anterior que se borran al cargar (las pantallas los recalculan con la planta cargada)
_BORRAR_AL_CARGAR = ("op", "op_compra", "op_resultado", "op_meta", "linea_resultado", "alt_res", "alt_opt", "alt_clave", "rg_resultado",
                     "mce_resultado", "mce_tornado_res", "tb_demo", "dp_aplicado", "dp_informe", "xl_aplicado", "xl_detalle",
                     "error_resolucion", "error_operacion", "aviso_diseno", "aviso_conexion", "aviso_rubro", "aviso_operacion",
                     "aviso_evaluacion", "aviso_curso", "des_variante", "des_modelo", "des_tamano", "des_distribucion", "dis_tipo_planta", "dis_demanda",
                     "esc_rubro", "rc_dT", "rc_Tfin", "eco_inv_auto", "eco_inv_auto_b", "lienzo_mensajes",
                     "des_rubro", "des_agar_modelo", "des_agar_tamano", "des_agar_distribucion")     # PAT 144 a: rubro y listas del agar


def almacen():
    """PAT 144 b: dónde viven los proyectos: la nube con sesión iniciada o la base local (SQLite)."""
    a = NU.almacen()
    return a if a is not None else C.obtener_bd()


def _cuenta() -> dict:
    """Cuenta con sesión: la de la nube (PAT 144 b) o la del acceso controlado (PAT 138)."""
    ss = st.session_state
    return ss.get(NU.CLAVE_USUARIO) or ss.get("usuario_acceso") or {}


def solo_lectura() -> bool:
    """PAT 144 b: la cuenta de visita de la nube no guarda proyectos."""
    return NU.solo_lectura()


def persona() -> str:
    """Nombre para el nombre automático: el escrito en Desafío o el usuario con sesión (acceso controlado)."""
    ss = st.session_state
    for v in (ss.get("des_nombre"), ss.get("persona_nombre"), (ss.get("desafio") or {}).get("nombre")):
        if limpiar_nombre(v):
            return limpiar_nombre(v)
    u = _cuenta()
    return limpiar_nombre(u.get("nombre") or u.get("usuario") or "")


def usuario() -> str:
    return limpiar_nombre(_cuenta().get("usuario") or "")


def dueno() -> str | None:
    """PAT 139: con acceso controlado, el estudiante solo ve y escribe sus proyectos (devuelve su usuario). El docente, y la
    aplicación sin acceso controlado (el computador de Jaime), ven todos (None). PAT 144 b: con sesión en la nube, None: lo que
    se ve lo filtran las reglas RLS (los propios, los ejemplos y, para el docente, los de todas las cuentas)."""
    if NU.activa():
        return None
    u = st.session_state.get("usuario_acceso") or {}
    if not u or u.get("rol") == "docente":
        return None
    return limpiar_nombre(u.get("usuario") or "")


def abierto() -> dict | None:
    """Proyecto abierto en la sesión, o None (también si se eliminó)."""
    ss = st.session_state
    a = ss.get(CLAVE_ABIERTO)
    if not a:
        return None
    try:
        bd = almacen()
        p = bd.obtener_proyecto_usuario(a["id"])
    except Exception:
        return a
    if p is None or not bd.es_dueno(p, dueno()):
        ss.pop(CLAVE_ABIERTO, None)
        return None
    if p["nombre"] != a.get("nombre"):
        a = dict(a, nombre=p["nombre"]); ss[CLAVE_ABIERTO] = a
    return a


def _economia_defecto() -> dict:
    return dict(precio_gas=C.HENRY_HUB, dolar=C.DOLAR, inversion=0.0, costo_anual=0.0, anios=20, tasa=0.10,
                precio_biomasa=C.PRECIO_BIOMASA)


def capturar() -> tuple[dict, dict]:
    """(estado, resumen) de la sesión actual."""
    ss = st.session_state
    p = persona()
    if p and not ss.get("persona_nombre"):
        ss["persona_nombre"] = p
    estado = ES.capturar(ss, C.version_planta())
    return estado, ES.resumen(C.planta(), estado, cop=float(ss.get("cop") or 2.0))


def _marcar_guardado():
    ss = st.session_state
    ss[CLAVE_GUARDADO] = dict(v=C.version_planta(), hp=ES.huella_planta(C.planta()), foto=ES.foto(ss))


def cambios_sin_guardar() -> bool:
    """True si la planta o el estado cambiaron desde el último guardado o carga (o si nunca se guardó)."""
    ss = st.session_state
    g = ss.get(CLAVE_GUARDADO)
    if not g:
        return True
    if ES.cambio(g.get("foto") or {}, ES.foto(ss)):
        return True
    v = C.version_planta()
    if v == g.get("v"):
        return False
    if ES.huella_planta(C.planta()) == g.get("hp"):   # la versión subió sin cambiar el contenido (se volvió a resolver)
        g["v"] = v
        return False
    return True


def guardar(nombre: str | None = None, nota: str = "", nuevo: bool = False, sobrescribir: bool = False) -> dict:
    """Guarda la sesión. Sin nuevo: en el proyecto abierto (una versión más) o, si no hay, en uno nuevo con el nombre dado o el
    automático. Con nuevo: crea un proyecto con el nombre (si se repite, NombreRepetido en «repetido», salvo sobrescribir).
    No llama a Streamlit fuera de la sesión (lo usa el lienzo dentro de su ciclo de eventos).
    Devuelve {ok, mensaje, id, nombre, version, repetido}."""
    ss = st.session_state; bd = almacen()
    ab = None if nuevo else abierto()
    try:
        estado, resumen = capturar()
        g = bd.guardar_proyecto_usuario(C.planta(), nombre=nombre, estado=estado, resumen=resumen, persona=persona(), nota=nota,
                                        usuario=usuario(), proyecto_id=ab["id"] if ab else None, sobrescribir=sobrescribir,
                                        dueno=dueno())
    except NombreRepetido as e:
        return dict(ok=False, repetido=e, mensaje=f"{e}. Puede sobrescribirlo (queda como una versión más de ese proyecto) "
                                                  f"o guardarlo como «{e.sugerido}».")
    except Exception as e:
        return dict(ok=False, repetido=None, mensaje=f"No se pudo guardar el proyecto: {e}")
    ss[CLAVE_ABIERTO] = dict(id=g["id"], nombre=g["nombre"], version=g["version"])
    _marcar_guardado()
    autoguardar(forzar=True)                  # la última partida queda igual a la versión recién guardada
    omit = (estado.get("_meta") or {}).get("omitidas") or []
    txt = (f"Guardado «{g['nombre']}»" + (" (proyecto nuevo)." if g["nuevo"] else f", versión {g['version']}.")
           + (f" No se guardaron {', '.join(omit)} (no se pueden escribir en la base)." if omit else ""))
    return dict(ok=True, repetido=None, mensaje=txt, **g)


def pedir_carga(proyecto_id: int, version: int | None = None):
    """Deja la carga pendiente y relanza la ejecución; se aplica en C.iniciar_estado antes de dibujar los widgets."""
    st.session_state[CLAVE_PENDIENTE] = (int(proyecto_id), version)
    st.rerun()


def aplicar_pendiente() -> dict | None:
    ss = st.session_state
    p = ss.pop(CLAVE_PENDIENTE, None)
    if not p:
        return None
    r = cargar(p[0], p[1])
    ss[CLAVE_AVISO] = ("ok" if r["ok"] else "error", r["mensaje"])
    return r


def cargar(proyecto_id: int, version: int | str | None = None) -> dict:
    """Carga el proyecto (su última versión, la pedida o, con version="auto", su guardado automático): planta única y estado de
    la sesión como se guardaron."""
    ss = st.session_state
    auto = version == "auto"
    try:
        bd = almacen()
        p0 = bd.obtener_proyecto_usuario(int(proyecto_id))
        if p0 is not None and not bd.es_dueno(p0, dueno()):
            raise PermissionError(f"el proyecto «{p0['nombre']}» es de otro usuario")
        d = bd.cargar_autoguardado(int(proyecto_id)) if auto else bd.cargar_proyecto_usuario(int(proyecto_id), version)
    except Exception as e:
        return dict(ok=False, mensaje=f"No se pudo cargar el proyecto: {e}")
    for k in _BORRAR_AL_CARGAR:
        ss.pop(k, None)
    C.fijar_planta(d["planta"])
    ES.restaurar(ss, d["estado"], C.version_planta(), defectos=dict(cop=2.0, economia=_economia_defecto()))
    if ss.get("persona_nombre"):
        ss["des_nombre"] = ss["persona_nombre"]            # el campo «Su nombre» de Desafío vuelve con el nombre guardado
    else:
        ss.pop("des_nombre", None)
    p = d["proyecto"]
    ss[CLAVE_ABIERTO] = dict(id=p["id"], nombre=p["nombre"], version=d["version"])
    if not auto or d.get("igual_a_version"):
        _marcar_guardado()
    ss[CLAVE_OFERTA] = {}                     # ya hay partida en la sesión: no se ofrece otra
    # la ranura de autoguardado queda con lo cargado al final de esta ejecución (la próxima vez se retoma desde aquí)
    ss[CLAVE_AUTO] = dict(h="", hp0="", foto0={}, t=0.0, fecha=d.get("fecha") if auto else None, pid=p["id"],
                          pagina=ss.get("pagina"), pendiente=True, al_dia=False, error=None, ajeno=False)
    if auto:
        return dict(ok=True, mensaje=f"Retomado el proyecto «{p['nombre']}», guardado automáticamente el {fecha_corta(d.get('fecha'))}: "
                                     f"{d['planta'].nombre}, con {len(d['planta'].equipos)} equipo(s). Todas las pantallas quedan "
                                     "como se dejaron.")
    return dict(ok=True, mensaje=f"Cargado «{p['nombre']}», versión {d['version']}: {d['planta'].nombre}, con "
                                 f"{len(d['planta'].equipos)} equipo(s). Todas las pantallas quedan como se guardaron.")


def cerrar():
    """Deja la sesión sin proyecto abierto (el próximo «Guardar proyecto» crea uno nuevo). El guardado automático toma la sesión
    actual como punto de partida: solo crea un proyecto nuevo con el próximo cambio."""
    st.session_state.pop(CLAVE_ABIERTO, None); st.session_state.pop(CLAVE_GUARDADO, None); st.session_state.pop(CLAVE_AUTO, None)


# ---------------------------------------------------------------- PAT 140 g: guardado automático tipo «partida»
def fecha_corta(t: str | None, segundos: bool = False) -> str:
    """2026-11-17T16:39:05 → 17-11 16:39 (con segundos, 17-11 16:39:05)."""
    if not t or len(t) < 16:
        return t or ""
    return f"{t[8:10]}-{t[5:7]} {t[11:19] if segundos else t[11:16]}"


def autoguardado_activo() -> bool:
    return (os.environ.get("PAT_AUTOGUARDADO") or "1").strip().lower() not in ("0", "no", "false")


def _con_acceso() -> bool:
    return bool(_cuenta())


def _estado_actual() -> dict:
    ss = st.session_state
    p = persona()
    if p and not ss.get("persona_nombre"):
        ss["persona_nombre"] = p
    return ES.capturar(ss, C.version_planta())


def huella_sesion(estado: dict | None = None) -> tuple[str, str]:
    """(huella de la sesión, huella de la planta). La huella de la sesión es la de capturar() sin la fecha de _meta y sin el
    número de versión de la planta que llevan el costeo y el layout (sube al volver a resolver sin cambiar nada)."""
    e = dict(estado if estado is not None else _estado_actual())
    meta = e.pop("_meta", None) or {}
    for k, campo in ES.CON_VERSION.items():
        if isinstance(e.get(k), dict) and campo in e[k]:
            e[k] = dict(e[k]); e[k][campo] = k in (meta.get("vigentes") or [])
    hp = ES.huella_planta(C.planta())
    t = hp + json.dumps(e, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha1(t.encode("utf-8")).hexdigest(), hp


def _trabajo_nuevo(A: dict, hp: str) -> bool:
    """True si, respecto de cómo partió la sesión, el usuario cambió algo de verdad (la planta o lo que fija a mano). Abrir y
    recorrer pantallas no crea proyectos."""
    if hp != A.get("hp0"):
        return True
    antes, ahora = A.get("foto0") or {}, ES.foto(st.session_state)
    return ES.cambio(antes, ahora) or any(k in ahora and k not in antes for k in _CLAVES_TRABAJO)


def autoguardar(forzar: bool = False) -> dict | None:
    """Guarda solo la sesión si cambió (ver el comienzo del módulo). Nunca lanza un error: si falla, lo deja anotado para el
    aviso de la barra lateral y reintenta después de INTERVALO segundos. Devuelve {id, nombre, fecha, nuevo} si escribió."""
    ss = st.session_state
    if not autoguardado_activo() or "pl" not in ss or solo_lectura():     # PAT 144 b: la visita no se guarda sola
        return None
    A = ss.get(CLAVE_AUTO)
    try:
        estado = _estado_actual()
        h, hp = huella_sesion(estado)
        if A is None:                         # primera ejecución de la sesión: punto de partida, sin escribir
            ss[CLAVE_AUTO] = dict(h=h, hp0=hp, foto0=ES.foto(ss), t=0.0, fecha=None, pid=None, pagina=ss.get("pagina"),
                                  pendiente=False, al_dia=False, error=None, ajeno=False)
            if not forzar:
                return None
            A = ss[CLAVE_AUTO]
        pagina = ss.get("pagina"); cambio_pantalla = pagina != A.get("pagina"); A["pagina"] = pagina
        ab = abierto()
        if h == A.get("h") and not forzar and (ab is None or ab["id"] == A.get("pid")):
            A["pendiente"] = False
            return None
        bd = almacen()
        if ab is None and not forzar and not _trabajo_nuevo(A, hp):
            A["h"] = h; A["pendiente"] = False
            return None
        if ab is not None and _con_acceso():  # con acceso controlado solo en los proyectos propios (también el docente)
            p = bd.obtener_proyecto_usuario(ab["id"])
            if p is not None and not bd.es_dueno(p, usuario()):
                A.update(h=h, pendiente=False, al_dia=False, ajeno=True)
                return None
        A["ajeno"] = False
        if not forzar and A.get("t") and time.monotonic() - A["t"] < INTERVALO and not cambio_pantalla:
            A["pendiente"] = True; A["al_dia"] = False
            return None
        try:
            resumen = ES.resumen(C.planta(), estado, cop=float(ss.get("cop") or 2.0))
        except Exception:
            resumen = {}
        g = bd.autoguardar_proyecto_usuario(C.planta(), estado=estado, resumen=resumen, proyecto_id=ab["id"] if ab else None,
                                            persona=persona(), usuario=usuario(), huella=h, dueno=dueno())
        if ab is None or ab["id"] != g["id"]:
            ss[CLAVE_ABIERTO] = dict(id=g["id"], nombre=g["nombre"], version=0)
        elif ab.get("nombre") != g["nombre"]:
            ss[CLAVE_ABIERTO] = dict(ab, nombre=g["nombre"])
        A.update(h=h, t=time.monotonic(), fecha=g["fecha"], pid=g["id"], pendiente=False, al_dia=True, error=None)
        ss[CLAVE_OFERTA] = {}                 # la sesión ya tiene su propia partida
        return g
    except Exception as e:                    # el guardado automático nunca bota la aplicación
        A = ss.setdefault(CLAVE_AUTO, dict(h="", hp0="", foto0={}, pagina=ss.get("pagina")))
        A.update(error=str(e) or type(e).__name__, t=time.monotonic(), pendiente=True, al_dia=False)
        return None


def ultima_partida() -> dict | None:
    """El último guardado automático del usuario (acceso controlado o nube) o, sin acceso controlado, el de este computador."""
    bd = almacen()
    if _con_acceso():
        return bd.ultimo_autoguardado(usuario=usuario() or "")
    return bd.ultimo_autoguardado(equipo=nombre_equipo())


def oferta_partida():
    """Arriba de la pantalla, al abrir la aplicación sin partida en la sesión: «Continuar», «Empezar de nuevo» o «Cargar proyecto»."""
    ss = st.session_state
    if not autoguardado_activo() or ss.get(CLAVE_PENDIENTE):
        return
    if CLAVE_OFERTA not in ss:
        try:
            ss[CLAVE_OFERTA] = (ultima_partida() or {}) if abierto() is None else {}
        except Exception:
            ss[CLAVE_OFERTA] = {}
    p = ss.get(CLAVE_OFERTA) or {}
    if not p or abierto() is not None:
        return
    with st.container(border=True):
        # PAT 140 h (pedido de Jaime, 19-11-2026): «Continuar con el último proyecto», tres botones y la explicación en un ⓘ desplegable
        st.markdown(C.esc(f"**Continuar con el último proyecto** (proyecto {p['nombre']}, guardado el {fecha_corta(p['fecha'])})"))
        with st.expander("ⓘ Cómo funciona"):
            st.caption("El simulador guarda solo cada cambio. «Continuar» deja la planta y todas las pantallas como se dejaron; "
                       "«Empezar de nuevo» parte con la carta en blanco y el proyecto anterior queda en la pantalla Proyectos; "
                       "«Cargar proyecto» abre la pantalla Proyectos para elegir otro proyecto o versión, o subir uno guardado en un archivo (.json).")
        a, b, c, _ = st.columns([1, 1, 1, 2])
        if a.button("Continuar", type="primary", key="partida_continuar", width="stretch"):
            ss[CLAVE_OFERTA] = {}
            pedir_carga(p["proyecto_id"], "auto")
        if b.button("Empezar de nuevo", key="partida_nueva", width="stretch"):
            ss[CLAVE_OFERTA] = {}
            st.rerun()
        c.button("Cargar proyecto", key="partida_cargar", width="stretch", on_click=_ir_a_proyectos)


def _ir_a_proyectos():
    """Botón «Cargar proyecto» de la oferta: cierra la oferta y abre la pantalla Proyectos (callback: cambia el radio de pantallas)."""
    st.session_state[CLAVE_OFERTA] = {}
    st.session_state["pagina"] = "Proyectos"


def _proyecto_abierto_lateral(auto: bool = False):
    ab = abierto()
    if ab:
        st.caption(C.esc(f"Proyecto abierto: **{ab['nombre']}**"))
    elif auto and autoguardado_activo():
        st.caption("Sin proyecto abierto: con el primer cambio se crea uno con el nombre automático.")
    else:
        st.caption("Sin proyecto abierto: «Guardar proyecto» crea uno con el nombre automático.")


def _indicador():
    """Proyecto abierto y estado del guardado en la barra lateral (va en un fragmento que se repite mientras haya algo por guardar)."""
    _proyecto_abierto_lateral(auto=True)
    if solo_lectura():                        # PAT 144 b: cuenta de visita de la nube
        st.caption(":gray[Cuenta de solo lectura: los cambios no se guardan]")
        return
    A = st.session_state.get(CLAVE_AUTO) or {}
    numerado_al_dia = not cambios_sin_guardar()
    if A.get("error"):
        st.caption(C.esc(f":gray[No se pudo guardar automáticamente ({A['error'][:80]}). Se reintenta solo; «Guardar proyecto» "
                         "sigue disponible.]"))
    elif A.get("ajeno"):
        st.caption(":gray[Guardado automático detenido: el proyecto abierto es de otro usuario.]")
    if A.get("al_dia") and A.get("fecha") and not A.get("error"):
        st.caption(f":green[Guardado automático: {A['fecha'][11:19]}]")
        st.caption(":green[Todo guardado]" if numerado_al_dia else ":gray[Versión numerada: cambios sin guardar]")
    elif numerado_al_dia:
        st.caption(":green[Todo guardado]")
    elif autoguardado_activo() and not A.get("pendiente") and abierto() is None and not A.get("error"):
        pass                                  # sin cambios todavía: la línea de arriba ya lo explica
    else:
        st.caption(":orange[Hay cambios sin guardar]")


def _indicador_con_repeticion():
    """Estado del guardado dentro de un fragmento: mientras quede algo pendiente, se repite cada INTERVALO segundos y guarda
    aunque el usuario no toque nada."""
    pendiente = autoguardado_activo() and bool((st.session_state.get(CLAVE_AUTO) or {}).get("pendiente"))
    primera = [True]

    def cuerpo():
        if not primera[0]:                    # repetición del fragmento (no la ejecución completa): guarda lo pendiente
            autoguardar()
        primera[0] = False
        _indicador()
    try:
        st.fragment(run_every=INTERVALO if pendiente else None)(cuerpo)()
    except Exception:
        cuerpo()


def exportar_partida() -> tuple[bytes, str]:
    """(contenido, nombre de archivo) de «Descargar partida (.json)» con la sesión actual."""
    ab = abierto()
    nombre = ab["nombre"] if ab else almacen().nombre_sugerido(persona())
    texto = partida_a_json(C.planta(), _estado_actual(), nombre)
    archivo = (re.sub(r"[^0-9A-Za-zÁÉÍÓÚÑáéíóúñ_-]+", "_", nombre).strip("_") or "Proyecto_simulador") + ".json"   # PAT 141: «Proyecto_de_Ana_1.json»
    return texto.encode("utf-8"), archivo


def importar_partida(contenido: bytes) -> dict:
    """Crea un proyecto con la partida del archivo (versión 1, nota «Cargada desde un archivo») y pide cargarlo. Si el nombre ya
    existe, usa el siguiente nombre libre. Devuelve {ok, mensaje, id}."""
    ss = st.session_state; bd = almacen()
    try:
        d = leer_partida(contenido)
        pers = limpiar_nombre((d["estado"] or {}).get("persona_nombre")) or persona()
        args = dict(estado=d["estado"], resumen=d["resumen"], persona=pers, nota="Subido desde un archivo (.json)",
                    usuario=usuario(), dueno=dueno())
        try:
            g = bd.guardar_proyecto_usuario(d["planta"], nombre=d["nombre"] or None, **args)
        except NombreRepetido as e:
            g = bd.guardar_proyecto_usuario(d["planta"], nombre=e.sugerido, **args)
    except Exception as e:
        return dict(ok=False, mensaje=f"No se pudo subir el proyecto desde el archivo: {e}.", id=None)
    ss[CLAVE_PENDIENTE] = (int(g["id"]), None)
    return dict(ok=True, mensaje=f"Proyecto subido desde el archivo como «{g['nombre']}».", id=g["id"])


def barra_lateral(autoguardado: bool = False):
    """Arriba del índice: proyecto abierto, si hay cambios sin guardar y el botón «Guardar proyecto». PAT 140 g: con
    autoguardado=True (app.py, al final de cada ejecución) primero guarda solo la sesión y muestra «Guardado automático: hh:mm:ss»."""
    ss = st.session_state
    try:                                      # PAT 144 b: modo local, ingreso a la nube o la cuenta con su rol
        NU.panel_lateral()
    except Exception as e:
        st.caption(f":gray[Modo local: no se pudo mostrar el ingreso a la nube ({e}).]")
    if autoguardado:
        autoguardar()
        _indicador_con_repeticion()
    else:
        _proyecto_abierto_lateral()
        if cambios_sin_guardar():
            st.caption(":orange[Hay cambios sin guardar]")
        else:
            st.caption(":green[Todo guardado]")
    if st.button("Guardar proyecto", key="pry_guardar_lateral", type="primary", width="stretch", disabled=solo_lectura(),
                 help="Guarda una versión numerada en el proyecto abierto o crea uno nuevo «Proyecto de <su nombre> <n>». Además, "
                      "cada cambio se guarda solo (guardado automático) para retomar el proyecto al volver a abrir el simulador. "
                      "Para ver, cargar, renombrar o eliminar proyectos, abra la pantalla Proyectos."):
        r = guardar(nota="Guardado desde la barra lateral")
        ss[CLAVE_AVISO_LATERAL] = ("ok" if r["ok"] else "error", r["mensaje"])
        st.rerun()
    av = ss.pop(CLAVE_AVISO_LATERAL, None)
    if av:
        (st.success if av[0] == "ok" else st.error)(C.esc(av[1]))
