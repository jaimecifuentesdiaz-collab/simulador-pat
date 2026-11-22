"""Cliente falso de Supabase para las pruebas sin red (PAT 144 b, tarea T8).

Imita lo que pat_sim/datos/nube.py usa de supabase-py (auth.sign_in_with_password, sign_out, refresh_session, postgrest.auth,
rpc().execute() y table().select/eq/order/limit/update/delete/upsert().execute()) y reproduce en Python las reglas de
«03 Base de datos/supabase»: perfiles con rol, RLS de proyectos, versiones y asignaciones, guardado con control de versión que
rechaza con PT409, guardado automático sin versiones y nadie cambia su propio rol. Varias sesiones (clientes) comparten un
ServidorFalso, como dos pestañas o dos personas contra el mismo proyecto de Supabase.
No es una prueba de PostgreSQL: el SQL se valida aparte (98_pruebas.sql y 99_verificacion.sql).
"""
from __future__ import annotations
import copy, itertools, uuid
from datetime import datetime, timezone
from types import SimpleNamespace


class APIErrorFalso(Exception):
    """Como postgrest.exceptions.APIError: code, message y details."""

    def __init__(self, code: str, message: str, details: str = ""):
        super().__init__(dict(code=code, message=message, details=details))
        self.code, self.message, self.details = code, message, details


class AuthErrorFalso(Exception):
    def __init__(self, message="Invalid login credentials"):
        super().__init__(message)
        self.message, self.code = message, "invalid_credentials"


def _ahora() -> str:
    return datetime.now(timezone.utc).isoformat()


class ServidorFalso:
    def __init__(self):
        self.usuarios: dict[str, dict] = {}          # email -> {id, clave}
        self.perfiles: dict[str, dict] = {}
        self.proyectos: dict[int, dict] = {}
        self.versiones: list[dict] = []
        self.asignaciones: dict[str, dict] = {}
        self.actividad: list[dict] = []
        self.sin_red = False
        self.ids = itertools.count(1)
        self.ids_version = itertools.count(1)
        self.llamadas: list[tuple] = []              # (uid, tipo, nombre, claves de los parámetros): nunca la contraseña
        self.vencidos: set[str] = set()              # uid cuyo próximo pedido responde «JWT expired»

    # ---- administración (lo que Jaime hace en el panel de Supabase)
    def crear_cuenta(self, email: str, clave: str, rol: str = "visita", nombre: str = "") -> str:
        uid = str(uuid.uuid4()); email = email.lower()
        self.usuarios[email] = dict(id=uid, clave=clave)
        self.perfiles[uid] = dict(id=uid, email=email, usuario=email.split("@")[0], nombre=nombre, rol=rol)
        return uid

    def cliente(self, url="https://falso.supabase.co", key="sb_publishable_falsa"):
        assert key.startswith("sb_publishable_"), "la aplicación solo debe usar la clave publicable"
        return ClienteFalso(self)

    # ---- reglas
    def rol(self, uid):
        return (self.perfiles.get(uid) or {}).get("rol")

    def ve_proyecto(self, uid, p):
        return uid is not None and (p["owner_id"] == uid or p["es_ejemplo"] or self.rol(uid) == "docente")

    def _puede_editar(self, uid):
        if uid is None:
            raise APIErrorFalso("28000", "Se requiere una sesión iniciada")
        if self.rol(uid) not in ("docente", "estudiante"):
            raise APIErrorFalso("42501", "La cuenta no tiene permiso para guardar proyectos (rol visita: solo lectura)")

    def _nombre_libre(self, uid, nombre, excepto=None):
        for p in self.proyectos.values():
            if p["owner_id"] == uid and p["nombre"].lower() == nombre.lower() and p["id"] != excepto:
                raise APIErrorFalso("23505", f"nombre_repetido: ya existe un proyecto llamado «{nombre}»")

    def _version(self, p, uid):
        self.versiones.append(dict(id=next(self.ids_version), proyecto_id=p["id"], numero=p["version"], nombre=p["nombre"], nota=p["nota"],
                                   datos=copy.deepcopy(p["datos"]), resumen=copy.deepcopy(p["resumen"]), autor_id=uid, fecha=_ahora()))
        self.actividad.append(dict(actor_id=uid, tabla="proyectos", accion="update" if p["version"] > 1 else "insert", registro=str(p["id"])))

    # ---- funciones (RPC)
    def rpc(self, uid, nombre, a):
        if nombre == "guardar_proyecto":
            self._puede_editar(uid)
            if a.get("p_id") is None:
                self._nombre_libre(uid, a["p_nombre"])
                i = next(self.ids); t = _ahora()
                p = dict(id=i, owner_id=uid, nombre=a["p_nombre"], persona=a.get("p_persona") or "", nota=a.get("p_nota") or "",
                         datos=copy.deepcopy(a["p_datos"]), resumen=copy.deepcopy(a.get("p_resumen") or {}), version=1, autoguardado=None,
                         autoguardado_en=None, es_ejemplo=False, creado=t, updated_at=t)
                self.proyectos[i] = p; self._version(p, uid)
                return dict(id=i, nombre=p["nombre"], version=1, nuevo=True, fecha=t)
            p = self.proyectos.get(a["p_id"])
            if p is None:
                raise APIErrorFalso("P0002", f"El proyecto {a['p_id']} no existe")
            if p["owner_id"] != uid:
                raise APIErrorFalso("42501", "Solo la cuenta dueña puede guardar en este proyecto")
            if a.get("p_version_esperada") is None:
                raise APIErrorFalso("22023", "Falta la versión esperada del proyecto")
            if p["version"] != a["p_version_esperada"]:
                raise APIErrorFalso("PT409", f"conflicto_version: otra sesión guardó la versión {p['version']} de «{p['nombre']}»",
                                    str(p["version"]))
            if a.get("p_nombre"):
                self._nombre_libre(uid, a["p_nombre"], p["id"]); p["nombre"] = a["p_nombre"]
            if a.get("p_persona"):
                p["persona"] = a["p_persona"]
            p.update(nota=a.get("p_nota") or "", datos=copy.deepcopy(a["p_datos"]), resumen=copy.deepcopy(a.get("p_resumen") or {}),
                     version=p["version"] + 1, updated_at=_ahora())
            self._version(p, uid)
            return dict(id=p["id"], nombre=p["nombre"], version=p["version"], nuevo=False, fecha=p["updated_at"])
        if nombre == "autoguardar_proyecto":
            self._puede_editar(uid)
            t = _ahora()
            if a.get("p_id") is None:
                self._nombre_libre(uid, a["p_nombre"])
                i = next(self.ids)
                self.proyectos[i] = dict(id=i, owner_id=uid, nombre=a["p_nombre"], persona=a.get("p_persona") or "",
                                         nota="Creado por el guardado automático", datos=copy.deepcopy(a["p_datos"]),
                                         resumen=copy.deepcopy(a.get("p_resumen") or {}), version=0, autoguardado=copy.deepcopy(a["p_datos"]),
                                         autoguardado_en=t, es_ejemplo=False, creado=t, updated_at=t)
                return dict(id=i, nombre=a["p_nombre"], fecha=t, nuevo=True)
            p = self.proyectos.get(a["p_id"])
            if p is None:
                raise APIErrorFalso("P0002", "no existe")
            if p["owner_id"] != uid:
                raise APIErrorFalso("42501", "El guardado automático solo escribe en los proyectos propios")
            p.update(autoguardado=copy.deepcopy(a["p_datos"]), autoguardado_en=t)
            return dict(id=p["id"], nombre=p["nombre"], fecha=t, nuevo=False)
        if nombre == "asignar_perfil":
            if self.rol(uid) != "docente":
                raise APIErrorFalso("42501", "Solo una cuenta con el rol docente asigna roles")
            if a["p_perfil"] == uid:
                raise APIErrorFalso("42501", "Nadie puede cambiar su propio rol")
            f = self.perfiles[a["p_perfil"]]; f["rol"] = a["p_rol"]
            if a.get("p_nombre") is not None:
                f["nombre"] = a["p_nombre"]
            return dict(f)
        if nombre == "marcar_ejemplo":
            if self.rol(uid) != "docente":
                raise APIErrorFalso("42501", "Solo una cuenta con el rol docente publica ejemplos")
            self.proyectos[a["p_id"]]["es_ejemplo"] = bool(a["p_valor"])
            return None
        if nombre == "preasignar":
            if self.rol(uid) != "docente":
                raise APIErrorFalso("42501", "Solo una cuenta con el rol docente preasigna roles")
            for f in self.perfiles.values():
                if f["email"] == a["p_email"]:
                    if f["id"] == uid:
                        raise APIErrorFalso("42501", "Nadie puede cambiar su propio rol")
                    f["rol"] = a["p_rol"]
            return None
        raise APIErrorFalso("PGRST202", f"No existe la función {nombre}")

    # ---- tablas con RLS
    def filas(self, uid, tabla):
        if uid is None:
            raise APIErrorFalso("42501", f"permission denied for table {tabla}")
        if tabla == "proyectos":
            out = []
            for p in self.proyectos.values():
                if self.ve_proyecto(uid, p):
                    f = copy.deepcopy(p)
                    dueno = self.perfiles.get(p["owner_id"])
                    f["perfiles"] = (dict(usuario=dueno["usuario"], nombre=dueno["nombre"])
                                     if dueno and (p["owner_id"] == uid or self.rol(uid) == "docente") else None)
                    out.append(f)
            return out
        if tabla == "proyectos_versiones":
            return [copy.deepcopy(v) for v in self.versiones if v["proyecto_id"] in self.proyectos
                    and self.ve_proyecto(uid, self.proyectos[v["proyecto_id"]])]
        if tabla == "perfiles":
            return [dict(f) for f in self.perfiles.values() if f["id"] == uid or self.rol(uid) == "docente"]
        if tabla == "asignaciones":
            return [copy.deepcopy(a) for a in self.asignaciones.values() if a["estudiante_id"] == uid or self.rol(uid) == "docente"]
        raise APIErrorFalso("42P01", f"relation {tabla} does not exist")

    def actualizar(self, uid, tabla, cambios, filtros):
        if tabla == "proyectos":
            if set(cambios) - {"nombre"}:
                raise APIErrorFalso("42501", "permission denied for table proyectos")
            out = []
            for f in self.filas(uid, tabla):
                if all(f.get(k) == v for k, v in filtros) and f["owner_id"] == uid and self.rol(uid) in ("docente", "estudiante"):
                    self._nombre_libre(uid, cambios["nombre"], f["id"])
                    self.proyectos[f["id"]]["nombre"] = cambios["nombre"]; out.append(dict(self.proyectos[f["id"]]))
            return out
        if tabla == "perfiles":
            if set(cambios) - {"nombre"}:
                raise APIErrorFalso("42501", "permission denied for table perfiles")
            out = []
            for f in self.filas(uid, tabla):
                if all(f.get(k) == v for k, v in filtros) and f["id"] == uid:
                    self.perfiles[uid].update(cambios); out.append(dict(self.perfiles[uid]))
            return out
        raise APIErrorFalso("42501", f"permission denied for table {tabla}")

    def borrar(self, uid, tabla, filtros):
        if tabla != "proyectos":
            raise APIErrorFalso("42501", f"permission denied for table {tabla}")
        out = []
        for f in self.filas(uid, tabla):
            if all(f.get(k) == v for k, v in filtros) and f["owner_id"] == uid and self.rol(uid) in ("docente", "estudiante"):
                out.append(self.proyectos.pop(f["id"]))
                self.versiones = [v for v in self.versiones if v["proyecto_id"] != f["id"]]
        return out

    def upsert(self, uid, tabla, filas):
        if tabla != "asignaciones" or self.rol(uid) != "docente":
            raise APIErrorFalso("42501", "new row violates row-level security policy")
        for f in filas:
            if self.rol(f["estudiante_id"]) != "estudiante":
                raise APIErrorFalso("22023", "Solo se asigna a cuentas con el rol estudiante")
            self.asignaciones[f["estudiante_id"]] = dict(copy.deepcopy(f), docente_id=uid, updated_at=_ahora())
        return filas


class _Consulta:
    def __init__(self, cliente, tabla):
        self.c, self.tabla = cliente, tabla
        self.op, self.cambios, self.filtros, self.orden, self.limite, self.cols = "select", None, [], [], None, "*"

    def select(self, cols="*"):
        self.cols = cols; return self

    def eq(self, k, v):
        self.filtros.append((k, v)); return self

    def order(self, k, desc=False):
        self.orden.append((k, desc)); return self

    def limit(self, n):
        self.limite = n; return self

    def update(self, cambios):
        self.op, self.cambios = "update", dict(cambios); return self

    def delete(self):
        self.op = "delete"; return self

    def upsert(self, filas, on_conflict=None):
        self.op, self.cambios = "upsert", list(filas); return self

    def execute(self):
        s = self.c.servidor; uid = self.c._uid_para_pedido("tabla", self.tabla, self.op)
        if self.op == "update":
            return SimpleNamespace(data=s.actualizar(uid, self.tabla, self.cambios, self.filtros))
        if self.op == "delete":
            return SimpleNamespace(data=s.borrar(uid, self.tabla, self.filtros))
        if self.op == "upsert":
            return SimpleNamespace(data=s.upsert(uid, self.tabla, self.cambios))
        filas = [f for f in s.filas(uid, self.tabla) if all(f.get(k) == v for k, v in self.filtros)]
        for k, desc in reversed(self.orden):
            filas.sort(key=lambda f: (f.get(k) is None, f.get(k)), reverse=desc)
        if self.limite is not None:
            filas = filas[: self.limite]
        if self.cols != "*":
            cols = [c.split("(")[0] for c in self.cols.replace("perfiles(usuario,nombre)", "perfiles").split(",")]
            filas = [{k: f.get(k) for k in cols} for f in filas]
        return SimpleNamespace(data=filas)


class _Auth:
    def __init__(self, cliente):
        self.c = cliente

    def sign_in_with_password(self, cred):
        s = self.c.servidor
        if s.sin_red:
            raise ConnectionError("sin red")
        u = s.usuarios.get(str(cred.get("email", "")).lower())
        if u is None or u["clave"] != cred.get("password"):
            raise AuthErrorFalso()
        self.c.uid = u["id"]; s.llamadas.append((u["id"], "auth", "sign_in", ("email",)))
        user = SimpleNamespace(id=u["id"], email=cred["email"].lower())
        return SimpleNamespace(user=user, session=SimpleNamespace(access_token="token-" + u["id"], refresh_token="r", user=user))

    def sign_out(self):
        self.c.uid = None

    def refresh_session(self):
        self.c.servidor.vencidos.discard(self.c.uid)
        return SimpleNamespace(session=SimpleNamespace(access_token="token-nuevo-" + str(self.c.uid)))


class _Postgrest:
    def __init__(self, cliente):
        self.c = cliente

    def auth(self, token):
        self.c.token = token


class _Rpc:
    def __init__(self, cliente, nombre, params):
        self.c, self.nombre, self.params = cliente, nombre, params

    def execute(self):
        uid = self.c._uid_para_pedido("rpc", self.nombre, tuple(sorted(self.params)))
        return SimpleNamespace(data=self.c.servidor.rpc(uid, self.nombre, copy.deepcopy(self.params)))


class ClienteFalso:
    def __init__(self, servidor: ServidorFalso):
        self.servidor, self.uid, self.token = servidor, None, None
        self.auth, self.postgrest = _Auth(self), _Postgrest(self)

    def _uid_para_pedido(self, tipo, nombre, detalle):
        s = self.servidor
        if s.sin_red:
            raise ConnectionError("sin red")
        if self.uid in s.vencidos:
            raise APIErrorFalso("PGRST303", "JWT expired")
        s.llamadas.append((self.uid, tipo, nombre, detalle))
        return self.uid

    def table(self, nombre):
        return _Consulta(self, nombre)

    def rpc(self, nombre, params):
        return _Rpc(self, nombre, params)
