"""Conexión opcional a Supabase: cuentas con rol y proyectos guardados en la nube (PAT 144 b, tarea T8, 20-11-2026).

Patrón del curso (mazo Supabase del 18-10-2026): la aplicación lleva solo datos públicos, la URL del proyecto y la clave
publicable (sb_publishable_...), y lo que cada cuenta ve o cambia lo deciden las reglas RLS de la base. Por eso cada sesión de
Streamlit tiene su propio cliente: ingresa con usuario y contraseña, y las consultas viajan con el token de esa sesión. La clave
secreta (service_role) nunca se usa: si la configurada no es publicable, el módulo no se conecta.

Secretos (st.secrets o variables de entorno): SUPABASE_URL y SUPABASE_KEY; opcional SUPABASE_DOMINIO, el dominio de los
usuarios cortos («usuario01» equivale a «usuario01@<dominio>», por defecto pat-sim.cl).

Sin claves, sin el paquete supabase o sin red, estado() lo informa y la aplicación sigue en modo local (SQLite). Nada de este
módulo guarda ni registra contraseñas: la contraseña solo pasa a sign_in_with_password.

AlmacenNube ofrece los mismos métodos de proyectos que BaseDatos (guardar_proyecto_usuario, listar_proyectos_usuario,
cargar_proyecto_usuario, autoguardar_proyecto_usuario y los demás que usa ui/proyectos.py), sobre las tablas y funciones de
«03 Base de datos/supabase». El control de versión: cada guardado numerado envía la versión que la sesión conoce (la del
momento en que cargó o guardó el proyecto) y la función guardar_proyecto lo rechaza si otra sesión guardó antes (ConflictoVersion).
"""
from __future__ import annotations
import base64, json, os, re, time
from datetime import datetime, timezone

from .bd import (NombreRepetido, limpiar_nombre, nombre_automatico, leer_nombre_automatico, a_json, planta_completa_a_dict,
                 planta_completa_desde_dict, _sin_tildes)

DOMINIO_DEFECTO = "pat-sim.cl"
ROLES = ("docente", "estudiante", "visita")
NOMBRE_ROL = {"docente": "docente", "estudiante": "estudiante", "visita": "visita"}
CACHE_S = 8.0                     # segundos que se reutiliza la lista de proyectos entre dos ejecuciones de la página
ZONA = "America/Santiago"
_COLS = ("id,owner_id,nombre,persona,nota,resumen,version,es_ejemplo,creado,updated_at,autoguardado_en,"
         "perfiles(usuario,nombre)")

# Fábrica del cliente: None usa supabase.create_client. Las pruebas ponen aquí un cliente falso (sin red).
FABRICA = None


# ---------------------------------------------------------------- errores
class ErrorNube(Exception):
    """Error de la nube con un mensaje para mostrar (nunca trae la contraseña)."""


class SinConexion(ErrorNube):
    pass


class CredencialesInvalidas(ErrorNube):
    pass


class SinPermiso(ErrorNube, PermissionError):
    pass


class ConflictoVersion(ErrorNube):
    """Otra sesión guardó una versión numerada después de que esta sesión cargó o guardó el proyecto."""

    def __init__(self, nombre: str, version_nube: int | None, version_sesion: int | None):
        self.nombre, self.version_nube, self.version_sesion = nombre, version_nube, version_sesion
        super().__init__(f"otra sesión guardó la versión {version_nube} de «{nombre}» después de que esta sesión la abrió "
                         f"(versión {version_sesion}). Para no sobrescribir ese trabajo no se guardó: use «Guardar como proyecto nuevo» "
                         "o cargue la versión más nueva")


# ---------------------------------------------------------------- configuración
def _leer(nombre: str, secretos=None) -> str:
    v = None
    try:
        if secretos is None:
            import streamlit as st
            secretos = st.secrets
        v = secretos[nombre]
    except Exception:                       # sin Streamlit, sin secrets.toml o sin la clave
        v = None
    return (str(v).strip() if v else "") or os.environ.get(nombre, "").strip()


def clave_es_secreta(clave: str) -> bool:
    """True si la clave da acceso total (sb_secret_... o un JWT con rol service_role): la aplicación no la usa."""
    clave = (clave or "").strip()
    if clave.startswith("sb_secret_"):
        return True
    partes = clave.split(".")
    if len(partes) == 3:
        try:
            carga = json.loads(base64.urlsafe_b64decode(partes[1] + "=" * (-len(partes[1]) % 4)).decode("utf-8"))
            return str(carga.get("role", "")).lower() == "service_role"
        except Exception:
            return False
    return False


def configuracion(secretos=None) -> dict | None:
    """{url, key, dominio} o None si falta la URL o la clave."""
    url, key = _leer("SUPABASE_URL", secretos), _leer("SUPABASE_KEY", secretos)
    if not url or not key:
        return None
    dominio = _leer("SUPABASE_DOMINIO", secretos).lstrip("@").lower() or DOMINIO_DEFECTO
    return dict(url=url.rstrip("/"), key=key, dominio=dominio)


def paquete_disponible() -> bool:
    if FABRICA is not None:
        return True
    try:
        import supabase  # noqa: F401
        return True
    except Exception:
        return False


def estado(secretos=None) -> dict:
    """{disponible, motivo, aviso, dominio}: motivo es «ok», «sin_claves», «clave_secreta», «url_invalida» o «sin_paquete»."""
    cfg = configuracion(secretos)
    if cfg is None:
        return dict(disponible=False, motivo="sin_claves", dominio=DOMINIO_DEFECTO,
                    aviso="Modo local: no hay conexión a la nube configurada (SUPABASE_URL y SUPABASE_KEY).")
    if clave_es_secreta(cfg["key"]):
        return dict(disponible=False, motivo="clave_secreta", dominio=cfg["dominio"],
                    aviso="Modo local: la clave configurada es secreta; la aplicación solo usa la clave publicable (sb_publishable_...).")
    if not re.match(r"^https://[^/\s]+$", cfg["url"]):
        return dict(disponible=False, motivo="url_invalida", dominio=cfg["dominio"],
                    aviso="Modo local: SUPABASE_URL no es una dirección https válida.")
    if not paquete_disponible():
        return dict(disponible=False, motivo="sin_paquete", dominio=cfg["dominio"],
                    aviso="Modo local: falta el paquete supabase (pip install supabase).")
    return dict(disponible=True, motivo="ok", dominio=cfg["dominio"], aviso="")


def correo_de(usuario: str, dominio: str = DOMINIO_DEFECTO) -> str:
    """«usuario01» → «usuario01@<dominio>»; un correo completo queda igual (en minúsculas)."""
    u = (usuario or "").strip().lower()
    if not u:
        return ""
    return u if "@" in u else f"{u}@{(dominio or DOMINIO_DEFECTO).lstrip('@')}"


def crear_cliente(cfg: dict):
    if FABRICA is not None:
        return FABRICA(cfg["url"], cfg["key"])
    from supabase import create_client
    return create_client(cfg["url"], cfg["key"])


# ---------------------------------------------------------------- utilidades
def fecha_local(t) -> str | None:
    """Fecha de PostgreSQL (UTC, con zona) a «2026-11-20T16:39:05» en hora de Chile, como las fechas de la base local."""
    if not t:
        return None
    if isinstance(t, datetime):
        d = t
    else:
        s = str(t).strip().replace(" ", "T")
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s)    # fracciones de segundo de largo variable
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return str(t)[:19]
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    try:
        from zoneinfo import ZoneInfo
        d = d.astimezone(ZoneInfo(ZONA))
    except Exception:                       # sin datos de zonas horarias: queda en UTC
        d = d.astimezone(timezone.utc)
    return d.replace(tzinfo=None).isoformat(timespec="seconds")


def _codigo(e) -> str:
    c = getattr(e, "code", None)
    if c is None and e.args and isinstance(e.args[0], dict):
        c = e.args[0].get("code")
    return str(c or "")


def _mensaje(e) -> str:
    m = getattr(e, "message", None)
    if m is None and e.args and isinstance(e.args[0], dict):
        m = e.args[0].get("message")
    return str(m if m is not None else e)


def _detalle(e) -> str:
    d = getattr(e, "details", None)
    if d is None and e.args and isinstance(e.args[0], dict):
        d = e.args[0].get("details")
    return str(d or "")


def _es_red(e) -> bool:
    n = type(e).__name__
    return isinstance(e, (ConnectionError, TimeoutError, OSError)) or any(
        x in n for x in ("ConnectError", "ConnectTimeout", "ReadTimeout", "NetworkError", "RemoteProtocolError", "TimeoutException"))


def _datos(planta, estado: dict | None) -> dict:
    """Planta y estado como JSON puro (los tipos de numpy pasan a números)."""
    return json.loads(a_json(dict(planta=planta_completa_a_dict(planta), estado=estado or {})))


def json_seguro(x):
    """Copia apta para jsonb: números de numpy a números, tuplas y conjuntos a listas; descarta funciones y objetos sin JSON."""
    if x is None or isinstance(x, (bool, int, float, str)):
        return x
    if isinstance(x, dict):
        out = {}
        for k, v in x.items():
            v2 = json_seguro(v)
            if v2 is not _NADA:
                out[str(k)] = v2
        return out
    if isinstance(x, (list, tuple, set)):
        return [v2 for v2 in (json_seguro(v) for v in x) if v2 is not _NADA]
    if hasattr(x, "item"):
        try:
            return x.item()
        except Exception:
            return _NADA
    return _NADA


_NADA = object()


def _sin_meta(estado: dict | None) -> dict:
    e = dict(estado or {})
    e.pop("_meta", None)
    return e


# ---------------------------------------------------------------- sesión
class SesionNube:
    """Una sesión de una cuenta: cliente propio (clave publicable + token de la sesión) y su perfil."""

    def __init__(self, cliente, cfg: dict, perfil: dict):
        self.cliente, self.cfg, self.perfil = cliente, cfg, perfil
        self._almacen = None

    # ---- ingreso y salida
    @classmethod
    def ingresar(cls, usuario: str, clave: str, secretos=None, cfg: dict | None = None) -> "SesionNube":
        """Ingresa con usuario corto o correo y contraseña. Lanza CredencialesInvalidas, SinConexion o ErrorNube."""
        est = estado(secretos) if cfg is None else dict(disponible=True)
        if not est["disponible"]:
            raise ErrorNube(est["aviso"])
        cfg = cfg or configuracion(secretos)
        correo = correo_de(usuario, cfg["dominio"])
        if not correo or not clave:
            raise CredencialesInvalidas("Ingrese el usuario y la contraseña.")
        try:
            cliente = crear_cliente(cfg)
            r = cliente.auth.sign_in_with_password({"email": correo, "password": clave})
        except Exception as e:
            if _es_red(e):
                raise SinConexion("No hay conexión con la nube; el simulador sigue en modo local.") from None
            texto = (_mensaje(e) + " " + _codigo(e)).lower()
            if "invalid" in texto or "credentials" in texto or "not confirmed" in texto or "400" in texto:
                raise CredencialesInvalidas("Usuario o contraseña incorrectos.") from None
            raise ErrorNube(f"La nube no aceptó el ingreso ({_mensaje(e)[:120]}).") from None
        sesion = getattr(r, "session", None); user = getattr(r, "user", None) or getattr(sesion, "user", None)
        if sesion is None or user is None:
            raise CredencialesInvalidas("Usuario o contraseña incorrectos.")
        try:                                                       # las consultas viajan con el token de esta sesión
            cliente.postgrest.auth(sesion.access_token)
        except Exception:
            pass
        s = cls(cliente, cfg, dict(id=str(user.id), email=str(getattr(user, "email", "") or correo)))
        s.perfil = s.leer_perfil()
        return s

    def cerrar(self):
        try:
            self.cliente.auth.sign_out()
        except Exception:                                          # sin red: la sesión local se cierra igual
            pass
        self._almacen = None

    @property
    def rol(self) -> str:
        return self.perfil.get("rol") or "visita"

    @property
    def usuario(self) -> str:
        return self.perfil.get("usuario") or (self.perfil.get("email") or "").split("@")[0]

    @property
    def id(self) -> str:
        return self.perfil["id"]

    def puede_editar(self) -> bool:
        return self.rol in ("docente", "estudiante")

    def es_docente(self) -> bool:
        return self.rol == "docente"

    def datos_sesion(self) -> dict:
        """Lo que la interfaz guarda en st.session_state (sin tokens ni contraseñas)."""
        return dict(usuario=self.usuario, rol=self.rol, nombre=self.perfil.get("nombre") or "", email=self.perfil.get("email") or "",
                    id=self.id)

    # ---- llamadas con manejo de errores
    def _ejecutar(self, fn):
        """Ejecuta una llamada; si el token venció, renueva la sesión y reintenta una vez. Traduce los errores."""
        for intento in (1, 2):
            try:
                r = fn()
                return getattr(r, "data", r)
            except ErrorNube:
                raise
            except Exception as e:
                cod, msg = _codigo(e), _mensaje(e)
                if intento == 1 and (cod in ("PGRST301", "PGRST303") or "jwt expired" in msg.lower()):
                    try:
                        rs = self.cliente.auth.refresh_session()
                        tok = getattr(getattr(rs, "session", None), "access_token", None)
                        if tok:
                            self.cliente.postgrest.auth(tok)
                        continue
                    except Exception:
                        raise ErrorNube("La sesión en la nube venció: vuelva a ingresar.") from None
                if _es_red(e):
                    raise SinConexion("No hay conexión con la nube. Lo hecho sigue en la sesión; reintente en un momento.") from None
                if cod == "PT409" or msg.startswith("conflicto_version"):
                    try:
                        v = int(_detalle(e))
                    except ValueError:
                        v = None
                    raise ConflictoVersion("", v, None) from None
                if cod == "23505" or msg.startswith("nombre_repetido"):
                    raise NombreRepetido(msg.split("«")[-1].rstrip("»") if "«" in msg else "", {}, "") from None
                if cod == "42501":
                    raise SinPermiso(msg) from None
                if cod == "P0002":
                    raise KeyError(msg) from None
                raise ErrorNube(f"La nube respondió con un error ({cod or type(e).__name__}): {msg[:200]}") from None
        raise ErrorNube("La nube no respondió.")

    def rpc(self, nombre: str, params: dict):
        return self._ejecutar(lambda: self.cliente.rpc(nombre, params).execute())

    def leer_perfil(self) -> dict:
        filas = self._ejecutar(lambda: self.cliente.table("perfiles").select("id,email,usuario,nombre,rol")
                               .eq("id", self.perfil["id"]).execute()) or []
        if not filas:                                              # la cuenta existe pero su perfil no (falta el disparador)
            return dict(self.perfil, usuario=(self.perfil.get("email") or "").split("@")[0], nombre="", rol="visita")
        f = filas[0]
        return dict(id=str(f["id"]), email=f.get("email") or self.perfil.get("email") or "", usuario=f.get("usuario") or "",
                    nombre=f.get("nombre") or "", rol=f.get("rol") if f.get("rol") in ROLES else "visita")

    def almacen(self) -> "AlmacenNube":
        if self._almacen is None:
            self._almacen = AlmacenNube(self)
        return self._almacen

    # ---- docente: cuentas, roles y asignaciones
    def listar_perfiles(self) -> list[dict]:
        return list(self._ejecutar(lambda: self.cliente.table("perfiles").select("id,email,usuario,nombre,rol")
                                   .order("usuario").execute()) or [])

    def asignar_perfil(self, perfil_id: str, rol: str, nombre: str | None = None) -> dict:
        if rol not in ROLES:
            raise ValueError(f"Rol no válido: {rol}")
        return self.rpc("asignar_perfil", dict(p_perfil=perfil_id, p_rol=rol, p_nombre=nombre))

    def preasignar(self, email: str, rol: str, nombre: str = "") -> None:
        if rol not in ROLES:
            raise ValueError(f"Rol no válido: {rol}")
        self.rpc("preasignar", dict(p_email=correo_de(email, self.cfg.get("dominio", DOMINIO_DEFECTO)), p_rol=rol, p_nombre=nombre or ""))

    def publicar_asignaciones(self, filas: list[dict]) -> int:
        """filas: {estudiante_id, curso, familia, datos}. Escribe (o reemplaza) la asignación de cada estudiante."""
        if not filas:
            return 0
        filas = [dict(estudiante_id=f["estudiante_id"], curso=f.get("curso") or "", familia=f.get("familia") or "",
                      datos=json_seguro(f.get("datos") or {})) for f in filas]
        self._ejecutar(lambda: self.cliente.table("asignaciones").upsert(filas, on_conflict="estudiante_id").execute())
        return len(filas)

    def mi_asignacion(self) -> dict | None:
        filas = self._ejecutar(lambda: self.cliente.table("asignaciones").select("estudiante_id,curso,familia,datos,updated_at")
                               .eq("estudiante_id", self.id).execute()) or []
        return filas[0] if filas else None


# ---------------------------------------------------------------- proyectos en la nube (misma interfaz que BaseDatos)
class AlmacenNube:
    """Proyectos de la cuenta en la nube con los métodos de proyectos de BaseDatos (ui/proyectos.py no distingue)."""

    @staticmethod
    def es_dueno(proyecto: dict | None, usuario: str | None) -> bool:
        """Igual que BaseDatos.es_dueno (usuario None = sin control de dueño)."""
        if usuario is None:
            return True
        if not proyecto:
            return False
        return limpiar_nombre(proyecto.get("usuario") or "").casefold() == limpiar_nombre(usuario).casefold() != ""

    def __init__(self, sesion: SesionNube):
        self.s = sesion
        self.conocidas: dict[int, int] = {}       # versión de cada proyecto al cargarlo o guardarlo en esta sesión
        self._cache: tuple[float, list[dict]] | None = None
        self._igual: dict[tuple, bool] = {}

    @property
    def solo_lectura(self) -> bool:
        return not self.s.puede_editar()

    # ---- lectura
    def _invalidar(self):
        self._cache = None

    def _fila(self, r: dict) -> dict:
        perfil = r.get("perfiles") or {}
        propio = str(r.get("owner_id")) == self.s.id
        resumen = r.get("resumen") or {}
        auto = leer_nombre_automatico(r.get("nombre") or "")
        return dict(id=int(r["id"]), nombre=r.get("nombre") or "", persona=r.get("persona") or "", numero=auto[1] if auto else None,
                    usuario=self.s.usuario if propio else (perfil.get("usuario") or ""), owner_id=str(r.get("owner_id")),
                    propio=propio, nota=r.get("nota") or "", rubro=resumen.get("rubro") or "", tipo_planta=resumen.get("tipo_planta") or "",
                    creado=fecha_local(r.get("creado")), modificado=fecha_local(r.get("updated_at")), n_versiones=int(r.get("version") or 0),
                    version=int(r.get("version") or 0), resumen=resumen, es_ejemplo=bool(r.get("es_ejemplo")),
                    autoguardado_en=fecha_local(r.get("autoguardado_en")))

    def _todas(self, fresca: bool = False) -> list[dict]:
        if not fresca and self._cache and time.monotonic() - self._cache[0] < CACHE_S:
            return self._cache[1]
        filas = self.s._ejecutar(lambda: self.s.cliente.table("proyectos").select(_COLS).order("updated_at", desc=True)
                                 .order("id", desc=True).execute()) or []
        filas = [self._fila(r) for r in filas]
        self._cache = (time.monotonic(), filas)
        return filas

    def _propias(self) -> list[dict]:
        return [f for f in self._todas() if f["propio"]]

    def obtener_proyecto_usuario(self, proyecto_id: int) -> dict | None:
        for f in self._todas():
            if f["id"] == int(proyecto_id):
                return f
        return None

    def buscar_proyecto_usuario(self, nombre: str) -> dict | None:
        clave = limpiar_nombre(nombre).casefold()
        return next((f for f in self._propias() if f["nombre"].casefold() == clave), None)

    def siguiente_numero(self, persona: str = "") -> int:
        clave = limpiar_nombre(persona).casefold(); usados = [0]
        for f in self._propias():
            a = leer_nombre_automatico(f["nombre"])
            if a and a[0].casefold() == clave:
                usados.append(a[1])
        return max(usados) + 1

    def nombre_sugerido(self, persona: str = "") -> str:
        n = self.siguiente_numero(persona)
        while self.buscar_proyecto_usuario(nombre_automatico(persona, n)) is not None:
            n += 1
        return nombre_automatico(persona, n)

    def listar_proyectos_usuario(self, buscar: str | None = None, persona: str | None = None, usuario: str | None = None) -> list[dict]:
        """Lo que RLS deja ver: los propios, los ejemplos y, para el docente, los de todas las cuentas. usuario filtra por dueño
        (los ejemplos se ven igual)."""
        filas = list(self._todas())
        if usuario is not None:
            u = limpiar_nombre(usuario).casefold()
            filas = [f for f in filas if f["es_ejemplo"] or limpiar_nombre(f["usuario"]).casefold() == u]
        if persona is not None:
            c = limpiar_nombre(persona).casefold()
            filas = [f for f in filas if limpiar_nombre(f["persona"]).casefold() == c]
        if buscar and buscar.strip():
            b = _sin_tildes(buscar)
            filas = [f for f in filas if b in _sin_tildes(f["nombre"]) or b in _sin_tildes(f["persona"]) or b in _sin_tildes(f["usuario"])]
        return filas

    def contar_proyectos_usuario(self) -> dict:
        filas = self._todas()
        return dict(proyectos=len(filas), versiones=sum(f["n_versiones"] for f in filas))

    def listar_versiones_usuario(self, proyecto_id: int) -> list[dict]:
        filas = self.s._ejecutar(lambda: self.s.cliente.table("proyectos_versiones").select("id,proyecto_id,numero,fecha,nota")
                                 .eq("proyecto_id", int(proyecto_id)).order("numero", desc=True).execute()) or []
        return [dict(id=int(f["id"]), proyecto_id=int(f["proyecto_id"]), numero=int(f["numero"]), fecha=fecha_local(f.get("fecha")),
                     nota=f.get("nota") or "") for f in filas]

    def _fila_completa(self, proyecto_id: int, columnas: str) -> dict:
        filas = self.s._ejecutar(lambda: self.s.cliente.table("proyectos").select(columnas).eq("id", int(proyecto_id)).execute()) or []
        if not filas:
            raise KeyError(f"No existe el proyecto {proyecto_id} (o la cuenta no puede verlo)")
        return filas[0]

    def _version(self, proyecto_id: int, numero: int | None) -> dict | None:
        q = lambda: (self.s.cliente.table("proyectos_versiones").select("numero,datos,resumen").eq("proyecto_id", int(proyecto_id))
                     .order("numero", desc=True).limit(1).execute() if numero is None else
                     self.s.cliente.table("proyectos_versiones").select("numero,datos,resumen").eq("proyecto_id", int(proyecto_id))
                     .eq("numero", int(numero)).execute())
        filas = self.s._ejecutar(q) or []
        return filas[0] if filas else None

    def cargar_proyecto_usuario(self, proyecto_id: int, version: int | None = None, resolver: bool = True) -> dict:
        p = self.obtener_proyecto_usuario(proyecto_id) or self._fila(self._fila_completa(proyecto_id, _COLS))
        f = self._version(proyecto_id, version)
        if f is None and version is None:                          # sin versiones numeradas: los datos de la fila
            r = self._fila_completa(proyecto_id, "datos,resumen,version")
            f = dict(numero=0, datos=r.get("datos") or {}, resumen=r.get("resumen") or {})
        if f is None:
            raise KeyError(f"El proyecto {proyecto_id} no tiene la versión {version}")
        d = f.get("datos") or {}
        if not isinstance(d.get("planta"), dict):
            raise ValueError("El proyecto de la nube no trae una planta")
        self.conocidas[int(proyecto_id)] = p["version"]
        pl = planta_completa_desde_dict(d["planta"], resolver=resolver)
        return dict(proyecto=p, version=int(f["numero"]), planta=pl, estado=d.get("estado") or {}, resumen=f.get("resumen") or {})

    def fechas_autoguardado(self) -> dict:
        return {f["id"]: f["autoguardado_en"] for f in self._todas() if f.get("autoguardado_en")}

    def obtener_autoguardado(self, proyecto_id: int) -> dict | None:
        p = self.obtener_proyecto_usuario(proyecto_id)
        if not p or not p.get("autoguardado_en"):
            return None
        return dict(proyecto_id=p["id"], usuario=p["usuario"], equipo="", fecha=p["autoguardado_en"], huella="")

    def ultimo_autoguardado(self, usuario: str | None = None, equipo: str | None = None) -> dict | None:
        """La última partida de la cuenta (solo sus proyectos)."""
        filas = sorted((f for f in self._propias() if f.get("autoguardado_en")), key=lambda f: (f["autoguardado_en"], f["id"]),
                       reverse=True)
        if not filas:
            return None
        f = filas[0]
        return dict(proyecto_id=f["id"], nombre=f["nombre"], persona=f["persona"], dueno=f["usuario"], fecha=f["autoguardado_en"],
                    usuario=f["usuario"], equipo="")

    def cargar_autoguardado(self, proyecto_id: int, resolver: bool = True) -> dict:
        p = self.obtener_proyecto_usuario(proyecto_id) or self._fila(self._fila_completa(proyecto_id, _COLS))
        r = self._fila_completa(proyecto_id, "autoguardado,autoguardado_en,version,resumen")
        d = r.get("autoguardado") or {}
        if not isinstance(d.get("planta"), dict):
            raise KeyError(f"El proyecto «{p['nombre']}» no tiene guardado automático")
        self.conocidas[int(proyecto_id)] = int(r.get("version") or 0)
        pl = planta_completa_desde_dict(d["planta"], resolver=resolver)
        return dict(proyecto=p, version=int(r.get("version") or 0), planta=pl, estado=d.get("estado") or {},
                    resumen=r.get("resumen") or {}, fecha=fecha_local(r.get("autoguardado_en")), autoguardado=True,
                    igual_a_version=self.autoguardado_igual_a_version(proyecto_id))

    def autoguardado_igual_a_version(self, proyecto_id: int) -> bool:
        p = self.obtener_proyecto_usuario(proyecto_id)
        if not p or not p.get("autoguardado_en") or not p.get("version"):
            return False
        clave = (int(proyecto_id), p["autoguardado_en"], p["version"])
        if clave in self._igual:
            return self._igual[clave]
        a = (self._fila_completa(proyecto_id, "autoguardado").get("autoguardado") or {})
        v = (self._version(proyecto_id, None) or {}).get("datos") or {}
        igual = bool(a) and a.get("planta") == v.get("planta") and _sin_meta(a.get("estado")) == _sin_meta(v.get("estado"))
        self._igual[clave] = igual
        return igual

    # ---- escritura
    def _exigir_edicion(self):
        if self.solo_lectura:
            raise SinPermiso("La cuenta de visita es de solo lectura: puede abrir los ejemplos y descargarlos (.json), pero no guardar.")

    def guardar_proyecto_usuario(self, planta, nombre: str | None = None, estado: dict | None = None, resumen: dict | None = None,
                                 persona: str = "", nota: str = "", usuario: str = "", proyecto_id: int | None = None,
                                 sobrescribir: bool = False, dueno: str | None = None) -> dict:
        """Como BaseDatos.guardar_proyecto_usuario, con control de versión: ConflictoVersion si otra sesión guardó antes."""
        self._exigir_edicion()
        persona = limpiar_nombre(persona)
        actual = self.obtener_proyecto_usuario(proyecto_id) if proyecto_id is not None else None
        if proyecto_id is not None and actual is None:
            proyecto_id = None                                     # se eliminó (o no se ve): se crea de nuevo
        if actual is not None and not actual["propio"]:
            raise SinPermiso(f"El proyecto «{actual['nombre']}» es de otra cuenta: guárdelo como un proyecto nuevo")
        nombre = limpiar_nombre(nombre) or (actual["nombre"] if actual else self.nombre_sugerido(persona))
        otro = self.buscar_proyecto_usuario(nombre)
        auto = leer_nombre_automatico(nombre)
        if proyecto_id is None and otro is not None:
            if not sobrescribir:
                raise NombreRepetido(nombre, otro, self.nombre_sugerido(otro["persona"] or (auto[0] if auto else persona)))
            proyecto_id, actual = otro["id"], otro
            esperada = otro["version"]                             # sobrescribir lo pide la persona: va sobre la versión vigente
        elif proyecto_id is not None and otro is not None and otro["id"] != proyecto_id:
            raise NombreRepetido(nombre, otro, self.nombre_sugerido(otro["persona"] or (auto[0] if auto else persona)))
        else:
            esperada = self.conocidas.get(int(proyecto_id), actual["version"]) if proyecto_id is not None else None
        pers = (auto[0] if auto and auto[0] else persona)
        try:
            r = self.s.rpc("guardar_proyecto", dict(p_id=proyecto_id, p_nombre=nombre, p_datos=_datos(planta, estado),
                                                     p_resumen=json.loads(a_json(resumen or {})), p_persona=pers, p_nota=nota or "",
                                                     p_version_esperada=esperada))
        except ConflictoVersion as e:
            self._invalidar()
            raise ConflictoVersion(nombre, e.version_nube, esperada) from None
        except NombreRepetido:
            self._invalidar()
            raise NombreRepetido(nombre, otro or {}, self.nombre_sugerido(persona)) from None
        finally:
            self._invalidar()
        r = r[0] if isinstance(r, list) else r
        self.conocidas[int(r["id"])] = int(r["version"])
        return dict(id=int(r["id"]), nombre=r["nombre"], version=int(r["version"]), nuevo=bool(r["nuevo"]))

    def autoguardar_proyecto_usuario(self, planta, estado: dict | None = None, resumen: dict | None = None,
                                     proyecto_id: int | None = None, persona: str = "", usuario: str = "", equipo: str | None = None,
                                     huella: str = "", dueno: str | None = None) -> dict:
        """Ranura de guardado automático del proyecto propio (sin versiones). Sin proyecto, lo crea con el nombre automático."""
        self._exigir_edicion()
        persona = limpiar_nombre(persona)
        actual = self.obtener_proyecto_usuario(proyecto_id) if proyecto_id is not None else None
        if actual is not None and not actual["propio"]:
            raise SinPermiso(f"El proyecto «{actual['nombre']}» es de otra cuenta: el guardado automático no lo cambia")
        datos = _datos(planta, estado); res = json.loads(a_json(resumen or {}))
        if actual is None:
            nombre = self.nombre_sugerido(persona)
            for _ in range(3):                                     # otra pestaña pudo tomar el mismo nombre al mismo tiempo
                try:
                    r = self.s.rpc("autoguardar_proyecto", dict(p_id=None, p_datos=datos, p_resumen=res, p_huella=huella or "",
                                                                 p_nombre=nombre, p_persona=persona))
                    break
                except NombreRepetido:
                    self._invalidar()
                    nombre = self.nombre_sugerido(persona)
            else:
                raise ErrorNube("No se encontró un nombre libre para el guardado automático")
            self._invalidar()
            r = r[0] if isinstance(r, list) else r
            self.conocidas[int(r["id"])] = 0
            return dict(id=int(r["id"]), nombre=r["nombre"], fecha=fecha_local(r.get("fecha")), nuevo=True)
        nombre = actual["nombre"]; auto = leer_nombre_automatico(nombre)
        if persona and not actual.get("n_versiones") and auto and not auto[0]:
            try:                                                   # «Proyecto 3» pasa a «Proyecto de <persona> <n>»
                nombre = self.renombrar_proyecto_usuario(actual["id"], self.nombre_sugerido(persona))
            except Exception:
                pass
        r = self.s.rpc("autoguardar_proyecto", dict(p_id=int(actual["id"]), p_datos=datos, p_resumen=res, p_huella=huella or "",
                                                     p_nombre=None, p_persona=persona))
        self._invalidar()
        r = r[0] if isinstance(r, list) else r
        return dict(id=int(r["id"]), nombre=r.get("nombre") or nombre, fecha=fecha_local(r.get("fecha")), nuevo=False)

    def renombrar_proyecto_usuario(self, proyecto_id: int, nuevo: str) -> str:
        self._exigir_edicion()
        nuevo = limpiar_nombre(nuevo)
        if not nuevo:
            raise ValueError("El proyecto necesita un nombre")
        p = self.obtener_proyecto_usuario(proyecto_id)
        if p is None:
            raise KeyError(f"No existe el proyecto {proyecto_id}")
        if not p["propio"]:
            raise SinPermiso("Solo la cuenta dueña renombra el proyecto")
        otro = self.buscar_proyecto_usuario(nuevo)
        if otro is not None and otro["id"] != int(proyecto_id):
            raise NombreRepetido(nuevo, otro, self.nombre_sugerido(otro["persona"] or (leer_nombre_automatico(nuevo) or ("", 0))[0]))
        filas = self.s._ejecutar(lambda: self.s.cliente.table("proyectos").update({"nombre": nuevo}).eq("id", int(proyecto_id)).execute())
        self._invalidar()
        if not filas:
            raise SinPermiso("La nube no dejó renombrar el proyecto (solo la cuenta dueña puede hacerlo)")
        return nuevo

    def eliminar_proyecto_usuario(self, proyecto_id: int):
        self._exigir_edicion()
        filas = self.s._ejecutar(lambda: self.s.cliente.table("proyectos").delete().eq("id", int(proyecto_id)).execute())
        self._invalidar()
        if not filas:
            raise SinPermiso("La nube no dejó eliminar el proyecto (solo la cuenta dueña puede hacerlo)")
        self.conocidas.pop(int(proyecto_id), None)

    def marcar_ejemplo(self, proyecto_id: int, valor: bool = True):
        if not self.s.es_docente():
            raise SinPermiso("Solo una cuenta con el rol docente publica ejemplos")
        self.s.rpc("marcar_ejemplo", dict(p_id=int(proyecto_id), p_valor=bool(valor)))
        self._invalidar()
