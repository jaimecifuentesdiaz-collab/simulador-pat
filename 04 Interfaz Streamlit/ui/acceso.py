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


def exigir() -> None:
    """Con el acceso activo y sin sesión, muestra el ingreso y detiene la página. Con sesión, muestra quién entró y «Salir»."""
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
