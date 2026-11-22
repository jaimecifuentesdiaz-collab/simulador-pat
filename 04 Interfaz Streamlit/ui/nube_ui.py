"""Ingreso a la nube en la barra lateral (PAT 144 b, tarea T8, 20-11-2026). Motor: pat_sim/datos/nube.py.

Con SUPABASE_URL y SUPABASE_KEY (clave publicable) en los secretos y el paquete supabase instalado, la barra lateral ofrece
«Ingresar a la nube» con usuario (corto o correo) y contraseña. Con sesión, Proyectos guarda y abre desde la nube
(ui/proyectos.almacen) y Docente usa el rol de la cuenta. Sin claves, sin paquete o sin red, la aplicación sigue en modo local
con SQLite y la barra lateral lo dice en una línea.

La sesión queda en st.session_state (cada persona tiene la suya; nunca en st.cache_resource, que comparten todas las sesiones del
servidor). La contraseña se lee de un formulario que se vacía al enviarlo y no se guarda en ninguna parte.
"""
from __future__ import annotations
import streamlit as st
from pat_sim.datos import nube as N
from . import comun as C

CLAVE_SESION = "_nube_sesion"      # SesionNube: cliente con el token de la sesión y el perfil
CLAVE_USUARIO = "usuario_nube"     # {usuario, rol, nombre, email, id} para mostrar (sin tokens)
CLAVE_ESTADO = "_nube_estado"      # resultado de N.estado(), una vez por sesión


def estado() -> dict:
    ss = st.session_state
    if CLAVE_ESTADO not in ss:
        try:
            ss[CLAVE_ESTADO] = N.estado()
        except Exception as e:                     # nunca bota la aplicación
            ss[CLAVE_ESTADO] = dict(disponible=False, motivo="error", aviso=f"Modo local: {e}")
    return ss[CLAVE_ESTADO]


def sesion():
    """SesionNube de esta persona o None (modo local)."""
    return st.session_state.get(CLAVE_SESION)


def activa() -> bool:
    return sesion() is not None


def datos() -> dict:
    return st.session_state.get(CLAVE_USUARIO) or {}


def rol() -> str | None:
    s = sesion()
    return s.rol if s else None


def almacen():
    """Almacén de proyectos de la nube con sesión, o None (se usa la base local)."""
    s = sesion()
    return s.almacen() if s else None


def solo_lectura() -> bool:
    s = sesion()
    return bool(s) and not s.puede_editar()


def _limpiar_proyecto():
    """Al entrar o salir cambia dónde viven los proyectos: se cierra el proyecto abierto (la planta de la sesión sigue igual)."""
    from . import proyectos as PRY
    ss = st.session_state
    PRY.cerrar()
    for k in (PRY.CLAVE_OFERTA, PRY.CLAVE_PENDIENTE, "_pys_confirmar", "pys_sel", "_pys_repetido"):
        ss.pop(k, None)


def ingresar(usuario: str, clave: str) -> tuple[bool, str]:
    try:
        s = N.SesionNube.ingresar(usuario, clave)
    except N.ErrorNube as e:
        return False, str(e)
    except Exception as e:
        return False, f"No se pudo ingresar a la nube ({type(e).__name__})."
    ss = st.session_state
    ss[CLAVE_SESION] = s; ss[CLAVE_USUARIO] = s.datos_sesion()
    _limpiar_proyecto()
    return True, ""


def salir():
    ss = st.session_state
    s = ss.pop(CLAVE_SESION, None); ss.pop(CLAVE_USUARIO, None)
    if s is not None:
        s.cerrar()
    _limpiar_proyecto()


def panel_lateral():
    """Arriba del proyecto abierto en la barra lateral: modo local, formulario de ingreso o la cuenta con su rol."""
    s = sesion()
    if s is not None:
        a, b = st.columns([3, 2], vertical_alignment="center")
        a.caption(C.esc(f"Nube: **{s.usuario}**, rol {N.NOMBRE_ROL.get(s.rol, s.rol)}"))
        if b.button("Salir", key="nube_salir", width="stretch", help="Cierra la sesión de la nube; el simulador sigue en modo local."):
            salir()
            st.rerun()
        return
    e = estado()
    if not e.get("disponible"):
        st.caption(":gray[Modo local]", help=e.get("aviso") or "Sin conexión a la nube configurada.")
        return
    with st.expander("Ingresar a la nube"):
        with st.form("nube_form", clear_on_submit=True, border=False):
            usuario = st.text_input("Usuario", key="nube_usuario", placeholder="usuario01",
                                    help=f"Usuario corto (usuario01 equivale a usuario01@{e.get('dominio') or N.DOMINIO_DEFECTO}) o el correo completo.")
            clave = st.text_input("Contraseña", type="password")          # sin key: no queda en st.session_state
            entrar = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if entrar:                                 # el formulario se vacía al enviarlo: la contraseña no queda en la sesión
            ok, msg = ingresar(usuario, clave)
            if ok:
                st.rerun()
            st.caption(f":orange[{C.esc(msg)}]")
