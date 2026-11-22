"""Acceso controlado por usuarios (PAT 138, tarea T25, 13-11-2026).

Se activa solo cuando la aplicación corre publicada con acceso controlado, por ejemplo en Hugging Face Spaces: la variable
o el secreto PAT_ACCESO vale «usuarios». En el computador de Jaime y en las pruebas no se activa y todo sigue igual.

Con el acceso activo, antes de abrir el simulador se pide nombre de usuario y clave:
- Usuarios de la tabla usuarios de la base (pantalla Docente, PAT 136), con su clave PBKDF2 y sal.
- El docente con la clave docente (secreto PROFESOR_CLAVE_SHA256), solo si ese secreto está configurado: la clave por
  defecto del código no abre la aplicación publicada.
- Usuarios iniciales del secreto PAT_USUARIOS, una línea por usuario con «usuario;rol;clave» o «usuario;rol;clave;nombre»
  (rol docente o estudiante). Se cargan en la base al arrancar, porque el espacio gratuito de Hugging Face no guarda la base
  entre reinicios: lo que el docente cree en la pantalla Docente dura hasta que el espacio se reinicie.
"""
from __future__ import annotations
import os
import streamlit as st
from . import comun as C

CLAVE_SESION = "usuario_acceso"


def _secreto(nombre: str) -> str:
    v = os.environ.get(nombre)
    if v:
        return str(v)
    try:
        return str(st.secrets.get(nombre) or "")
    except Exception:                               # sin archivo de secretos, st.secrets lanza un error al leerlo
        return ""


def activo() -> bool:
    return _secreto("PAT_ACCESO").strip().lower() == "usuarios"


def leer_usuarios(texto: str) -> tuple[list[dict], list[str]]:
    """Usuarios del secreto PAT_USUARIOS y los avisos de las líneas que no se pudieron leer (sin mostrar claves)."""
    filas, avisos = [], []
    for n, linea in enumerate((texto or "").replace("\r", "").split("\n"), 1):
        linea = linea.strip()
        if not linea or linea.startswith("#"):
            continue
        c = [x.strip() for x in linea.split(";")]
        if len(c) < 3 or not c[0] or not c[2]:
            avisos.append(f"Línea {n} de PAT_USUARIOS: se esperaba «usuario;rol;clave»")
            continue
        filas.append(dict(usuario=c[0], rol=c[1] or "estudiante", clave=c[2], nombre=c[3] if len(c) > 3 else ""))
    return filas, avisos


def sembrar_usuarios(g, texto: str | None = None) -> int:
    """Crea o actualiza en la base los usuarios del secreto PAT_USUARIOS. Devuelve cuántos se cargaron."""
    filas, _avisos = leer_usuarios(_secreto("PAT_USUARIOS") if texto is None else texto)
    n = 0
    for f in filas:
        try:
            g.crear_usuario(f["usuario"], f["nombre"], f["rol"], f["clave"])
            n += 1
        except ValueError:
            pass
    return n


def _genericos():
    from pat_sim.datos import genericos as GE
    return GE.genericos(C.obtener_bd())


def autenticar(g, usuario: str, clave: str) -> dict | None:
    """Usuario que entra (nombre_usuario y rol) o None. La clave docente solo vale si su secreto está configurado."""
    usuario, clave = (usuario or "").strip(), clave or ""
    if not usuario or not clave:
        return None
    u = g.autenticar(usuario, clave)
    if u is not None:
        return dict(usuario=u["nombre_usuario"], rol=u["rol"], nombre=u.get("nombre") or "")
    from pat_sim.datos import mantenedor as M
    esperado, origen = M.hash_esperado(None, {"PROFESOR_CLAVE_SHA256": _secreto("PROFESOR_CLAVE_SHA256")})
    if origen != "defecto" and M.verificar_profesor(clave, esperado):
        return dict(usuario=usuario, rol="docente", nombre="")
    return None


# PAT 146: con la nube configurada el ingreso es obligatorio, en una pantalla propia como en un ERP
_CSS_SIN_LATERAL = """<style>
[data-testid="stSidebar"], [data-testid="stSidebarCollapsedControl"] {display: none !important;}
</style>"""


def nube_obligatoria() -> bool:
    """PAT 146: True si la nube está configurada (claves, URL válida, clave publicable y paquete supabase). Nunca bota la aplicación."""
    try:
        from . import nube_ui as NU
        return bool(NU.estado().get("disponible"))
    except Exception:
        return False


def _mensaje_ingreso(msg: str) -> str:
    """PAT 146: el mensaje de nube_ui.ingresar dice «sigue en modo local» cuando no hay red; con el ingreso obligatorio no se abre."""
    msg = (msg or "No se pudo ingresar.").replace("; el simulador sigue en modo local.", ". Revise la conexión e intente de nuevo.")
    return msg


def pantalla_ingreso_nube() -> None:
    """PAT 146: sin sesión de nube muestra solo la pantalla de ingreso (sin barra lateral, índice ni barra de etapas) y detiene la
    página con st.stop(); ninguna pantalla se abre antes de ingresar, tampoco con ?p= en la dirección. Con sesión no hace nada."""
    from . import nube_ui as NU
    if NU.activa():
        return
    st.html(_CSS_SIN_LATERAL)
    _a, centro, _b = st.columns([1, 1.4, 1])
    with centro:
        st.title("Simulador PAT")
        st.markdown("Simulador de diseño de plantas de proceso y recuperación de calor")
        with st.form("ing_form", border=True):
            usuario = st.text_input("Usuario", key="ing_usuario", placeholder="usuario01",
                                    help="Su usuario, por ejemplo usuario01; también acepta el correo completo")
            clave = st.text_input("Contraseña", type="password")      # sin key: la contraseña no queda en st.session_state
            entrar = st.form_submit_button("Ingresar", type="primary", width="stretch")
        if entrar:
            try:
                ok, msg = NU.ingresar(usuario, clave)
            except Exception as e:                               # nunca bota la aplicación
                ok, msg = False, f"No se pudo ingresar a la nube ({type(e).__name__})."
            if ok:
                st.rerun()
            st.error(C.esc(_mensaje_ingreso(msg)))
        st.caption("Las cuentas las crea el administrador. Si olvidó su contraseña, pídale una nueva.")
    st.stop()


def limpiar_sesion() -> None:
    """PAT 146: borra todas las claves de st.session_state (proyecto, planta y datos de la cuenta anterior) y la dirección ?p=.
    Algunas claves de widgets no se dejan borrar en la misma ejecución: se saltan sin botar la aplicación."""
    ss = st.session_state
    for k in list(ss.keys()):
        try:
            del ss[k]
        except Exception:
            pass
    try:
        st.query_params.clear()
    except Exception:
        pass


def exigir() -> None:
    """Con el acceso activo y sin sesión, muestra el ingreso y detiene la página. Con sesión, muestra quién entró y «Salir».
    PAT 146: si la nube está configurada, manda el ingreso a la nube (pantalla_ingreso_nube) y el acceso T25 no se usa."""
    if nube_obligatoria():                         # PAT 146
        pantalla_ingreso_nube()
        return
    if not activo():
        return
    ss = st.session_state
    u = ss.get(CLAVE_SESION)
    if u:
        with st.sidebar:
            st.caption(f"Sesión: {u['usuario']} ({u['rol']})")
            if st.button("Salir", key="acc_salir"):
                for k in list(ss.keys()):
                    del ss[k]
                st.rerun()
        return
    try:
        g = _genericos()
        if not ss.get("_acc_sembrado"):
            sembrar_usuarios(g)
            ss._acc_sembrado = True
    except Exception as e:                          # la base no responde: no se abre la aplicación sin control
        st.error(f"No se pudo abrir la base de usuarios: {e}")
        st.stop()
    st.title("Simulador PAT")
    st.markdown("Ingrese con el nombre de usuario y la clave que le entregó su docente.")
    with st.form("acc_form"):
        usuario = st.text_input("Nombre de usuario", key="acc_usuario")
        clave = st.text_input("Clave", type="password", key="acc_clave")
        entrar = st.form_submit_button("Entrar", type="primary")
    if entrar:
        r = autenticar(g, usuario, clave)
        if r is None:
            st.error("Usuario o clave incorrectos. Si no tiene usuario, pídaselo a su docente.")
        else:
            ss[CLAVE_SESION] = r
            st.rerun()
    st.stop()
