"""Almacenamiento común de proyectos, versiones y corridas (PAT 133, mejora 15).

Interfaz Almacen con dos implementaciones:
- AlmacenSQLite: la base actual (envuelve BaseDatos de datos/bd.py, sin cambiar su esquema);
- AlmacenSharePoint: tres listas de un sitio de SharePoint de la UTAL por la API REST de Microsoft Graph
  (/sites/{sitio}/lists/{lista}/items). El sitio, las listas y el token salen de variables de entorno o de
  config_sharepoint.json (el ejemplo no trae secretos).
Las dos usan bloqueo optimista por versión para varios usuarios: guardar_version(..., esperada=n) solo guarda si la última
versión del proyecto sigue siendo n; si otro usuario guardó antes, lanza ConflictoVersion y no se pierde ningún trabajo.
En SharePoint, además, la columna UltimaVersion del proyecto se actualiza con If-Match y la eTag del elemento (HTTP 412 si
cambió). Límite declarado: no hubo acceso a SharePoint desde el computador de trabajo; la implementación se probó con un
cliente HTTP simulado (tests/test_almacen.py) y falta probarla contra el sitio real cuando TI registre la aplicación."""
from __future__ import annotations
import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from .bd import BaseDatos, a_json, planta_a_dict

AQUI = Path(__file__).resolve().parent
CONFIG_SHAREPOINT = AQUI / "config_sharepoint.json"
GRAPH = "https://graph.microsoft.com/v1.0"


class ConflictoVersion(Exception):
    """Otro usuario guardó una versión del proyecto después de que usted la cargó."""

    def __init__(self, proyecto_id, esperada, actual):
        super().__init__(f"El proyecto {proyecto_id} ya va en la versión {actual} (usted trabajaba sobre la {esperada}). "
                         "Cargue la última versión y vuelva a aplicar sus cambios.")
        self.proyecto_id, self.esperada, self.actual = proyecto_id, esperada, actual


class ErrorAlmacen(Exception):
    pass


class Almacen:
    """Operaciones comunes. Los id son enteros en SQLite y texto en SharePoint; la interfaz no depende de eso."""
    nombre = "base"

    def listar_proyectos(self) -> list[dict]: raise NotImplementedError
    def obtener_proyecto(self, ref) -> dict | None: raise NotImplementedError
    def crear_proyecto(self, nombre: str, rubro: str = "general", descripcion: str = ""): raise NotImplementedError
    def ultima_version_numero(self, proyecto_id) -> int: raise NotImplementedError
    def guardar_version(self, proyecto_id, planta, nota: str = "", esperada: int | None = None) -> dict: raise NotImplementedError
    def listar_versiones(self, proyecto_id) -> list[dict]: raise NotImplementedError
    def dict_version(self, version_id) -> dict: raise NotImplementedError
    def guardar_corrida(self, version_id, resumen: dict): raise NotImplementedError
    def listar_corridas(self, version_id=None) -> list[dict]: raise NotImplementedError

    def cargar_version(self, version_id, resolver: bool = True):
        from ..catalogos.registro import planta_desde_dict
        pl = planta_desde_dict(self.dict_version(version_id))
        return pl.resolver() if resolver else pl


# ----------------------------------------------------------------------------------------------- SQLite
class AlmacenSQLite(Almacen):
    nombre = "sqlite"

    def __init__(self, bd: BaseDatos | None = None, ruta=None):
        self.bd = bd if bd is not None else BaseDatos(ruta)

    def listar_proyectos(self): return self.bd.listar_proyectos()
    def obtener_proyecto(self, ref): return self.bd.obtener_proyecto(ref)
    def crear_proyecto(self, nombre, rubro="general", descripcion=""): return self.bd.crear_proyecto(nombre, rubro, descripcion)
    def listar_versiones(self, proyecto_id): return self.bd.listar_versiones(proyecto_id)
    def dict_version(self, version_id): return self.bd.dict_version(version_id)
    def guardar_corrida(self, version_id, resumen): return self.bd.guardar_corrida(version_id, resumen)
    def listar_corridas(self, version_id=None): return self.bd.listar_corridas(version_id)

    def ultima_version_numero(self, proyecto_id) -> int:
        v = self.bd.listar_versiones(proyecto_id)
        return int(v[0]["numero"]) if v else 0

    def guardar_version(self, proyecto_id, planta, nota="", esperada=None):
        if esperada is None:
            return self.bd.guardar_version(proyecto_id, planta, nota)
        # bloqueo optimista: la restricción UNIQUE (proyecto_id, numero) impide que dos usuarios escriban la misma versión
        texto = a_json(planta_a_dict(planta)); ahora = datetime.now().isoformat(timespec="seconds")
        with self.bd._con() as con:
            if con.execute("SELECT 1 FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone() is None:
                raise ValueError(f"No existe el proyecto {proyecto_id}")
            actual = con.execute("SELECT COALESCE(MAX(numero), 0) FROM versiones WHERE proyecto_id = ?", (proyecto_id,)).fetchone()[0]
            if int(actual) != int(esperada):
                raise ConflictoVersion(proyecto_id, esperada, int(actual))
            try:
                cur = con.execute("INSERT INTO versiones (proyecto_id, numero, planta_json, nota, fecha) VALUES (?,?,?,?,?)",
                                  (proyecto_id, int(esperada) + 1, texto, nota, ahora))
            except sqlite3.IntegrityError:
                raise ConflictoVersion(proyecto_id, esperada, int(esperada) + 1) from None
            con.execute("UPDATE proyectos SET modificado = ?, rubro = ? WHERE id = ?", (ahora, getattr(planta, "rubro", "general"), proyecto_id))
            return dict(id=int(cur.lastrowid), numero=int(esperada) + 1)


# ----------------------------------------------------------------------------------------------- HTTP
class ClienteHTTP:
    """Cliente mínimo con urllib (biblioteca estándar). solicitar devuelve (estado, encabezados, cuerpo como dict o None)."""

    def __init__(self, tiempo: float = 30.0):
        self.tiempo = tiempo

    def solicitar(self, metodo: str, url: str, encabezados: dict, cuerpo: dict | None = None):
        datos = json.dumps(cuerpo).encode("utf-8") if cuerpo is not None else None
        req = urllib.request.Request(url, data=datos, method=metodo, headers=encabezados)
        try:
            with urllib.request.urlopen(req, timeout=self.tiempo) as r:
                t = r.read().decode("utf-8")
                return r.status, dict(r.headers), (json.loads(t) if t else None)
        except urllib.error.HTTPError as e:
            t = e.read().decode("utf-8", "replace")
            try:
                c = json.loads(t) if t else None
            except ValueError:
                c = {"error": {"message": t}}
            return e.code, dict(e.headers or {}), c


def leer_config(ruta: str | os.PathLike | None = None) -> dict:
    """Configuración de SharePoint: archivo JSON (si existe) y encima las variables de entorno PAT_SP_*."""
    cfg = dict(graph=GRAPH, sitio="", listas={}, token="")
    ruta = Path(ruta or os.environ.get("PAT_SP_CONFIG") or CONFIG_SHAREPOINT)
    if ruta.exists():
        d = json.loads(ruta.read_text(encoding="utf-8"))
        cfg.update({k: v for k, v in d.items() if not k.startswith("_")})
    cfg["listas"] = dict(cfg.get("listas") or {})
    env = os.environ
    cfg["graph"] = env.get("PAT_SP_GRAPH", cfg["graph"]); cfg["sitio"] = env.get("PAT_SP_SITIO", cfg["sitio"])
    cfg["token"] = env.get("PAT_SP_TOKEN", cfg.get("token") or "")
    for k in ("proyectos", "versiones", "corridas"):
        if env.get(f"PAT_SP_LISTA_{k.upper()}"):
            cfg["listas"][k] = env[f"PAT_SP_LISTA_{k.upper()}"]
    return cfg


def _ahora():
    return datetime.now().isoformat(timespec="seconds")


class AlmacenSharePoint(Almacen):
    """Tres listas de SharePoint (Microsoft Graph). Columnas de texto de cada lista:
    PAT_Proyectos: Title (nombre), Rubro, Descripcion, Creado, Modificado, UltimaVersion (número);
    PAT_Versiones: Title, ProyectoId, Numero, PlantaJson (texto de varias líneas), Nota, Fecha;
    PAT_Corridas: Title, VersionId, Fecha, CoberturaCascada, CascadaKW, PinchKW, GasBaseMMBtu, GasCascadaMMBtu, ResumenJson."""
    nombre = "sharepoint"

    def __init__(self, config: dict | None = None, cliente=None):
        self.cfg = config if config is not None else leer_config()
        faltan = [k for k in ("sitio", "token") if not self.cfg.get(k) or "<" in str(self.cfg.get(k))]
        faltan += [f"lista {k}" for k in ("proyectos", "versiones", "corridas") if not self.cfg["listas"].get(k) or "<" in self.cfg["listas"][k]]
        if faltan:
            raise ErrorAlmacen("Falta configurar SharePoint: " + ", ".join(faltan) + " (variables PAT_SP_* o config_sharepoint.json)")
        self.http = cliente or ClienteHTTP()

    # --- bajo nivel
    def _url(self, lista: str, *partes, **consulta) -> str:
        base = f"{self.cfg['graph'].rstrip('/')}/sites/{self.cfg['sitio']}/lists/{self.cfg['listas'][lista]}/items"
        u = "/".join([base] + [urllib.parse.quote(str(p)) for p in partes])
        return u + ("?" + urllib.parse.urlencode(consulta) if consulta else "")

    def _pedir(self, metodo, url, cuerpo=None, etag=None, aceptar=(200, 201, 204)):
        enc = {"Authorization": f"Bearer {self.cfg['token']}", "Accept": "application/json", "Content-Type": "application/json",
               "Prefer": "HonorNonIndexedQueriesWarningMayFailRandomly"}
        if etag:
            enc["If-Match"] = etag
        estado, _h, c = self.http.solicitar(metodo, url, enc, cuerpo)
        if estado == 412:
            return estado, c
        if estado not in aceptar:
            msg = ((c or {}).get("error") or {}).get("message", "") if isinstance(c, dict) else ""
            raise ErrorAlmacen(f"SharePoint respondió {estado} a {metodo}: {msg}")
        return estado, c

    def _items(self, lista, filtro: str | None = None) -> list[dict]:
        q = {"expand": "fields"}
        if filtro:
            q["$filter"] = filtro
        url = self._url(lista, **q); out = []
        while url:                                   # paginación de Graph con @odata.nextLink
            _e, c = self._pedir("GET", url)
            out += (c or {}).get("value", [])
            url = (c or {}).get("@odata.nextLink")
        return out

    def _item(self, lista, item_id) -> dict | None:
        estado, c = self._pedir("GET", self._url(lista, item_id, expand="fields"), aceptar=(200, 404))
        return None if estado == 404 else c

    @staticmethod
    def _proyecto(it, n_versiones=None) -> dict:
        f = it.get("fields", {})
        d = dict(id=str(it["id"]), nombre=f.get("Title", ""), rubro=f.get("Rubro", "general"), descripcion=f.get("Descripcion", ""),
                 creado=f.get("Creado", ""), modificado=f.get("Modificado", ""), ultima_version=int(f.get("UltimaVersion") or 0),
                 etag=it.get("eTag") or it.get("@odata.etag"))
        d["n_versiones"] = d["ultima_version"] if n_versiones is None else n_versiones
        return d

    # --- proyectos
    def listar_proyectos(self):
        return sorted((self._proyecto(it) for it in self._items("proyectos")), key=lambda p: p["modificado"], reverse=True)

    def obtener_proyecto(self, ref):
        if isinstance(ref, str) and not ref.isdigit():
            nombre = ref.replace("'", "''")
            v = self._items("proyectos", f"fields/Title eq '{nombre}'")
            return self._proyecto(v[0]) if v else None
        it = self._item("proyectos", ref)
        return self._proyecto(it) if it else None

    def crear_proyecto(self, nombre, rubro="general", descripcion=""):
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El proyecto necesita un nombre")
        if self.obtener_proyecto(nombre) is not None:
            raise ValueError(f"Ya existe un proyecto llamado «{nombre}»")
        a = _ahora()
        _e, c = self._pedir("POST", self._url("proyectos"), {"fields": dict(Title=nombre, Rubro=rubro, Descripcion=descripcion,
                                                                              Creado=a, Modificado=a, UltimaVersion=0)})
        return str(c["id"])

    def ultima_version_numero(self, proyecto_id) -> int:
        p = self.obtener_proyecto(str(proyecto_id))
        if p is None:
            raise ValueError(f"No existe el proyecto {proyecto_id}")
        return p["ultima_version"]

    # --- versiones
    def guardar_version(self, proyecto_id, planta, nota="", esperada=None):
        """Reserva el número con If-Match sobre el proyecto (bloqueo optimista) y después crea la versión."""
        it = self._item("proyectos", proyecto_id)
        if it is None:
            raise ValueError(f"No existe el proyecto {proyecto_id}")
        p = self._proyecto(it)
        actual = p["ultima_version"]
        if esperada is not None and int(esperada) != actual:
            raise ConflictoVersion(proyecto_id, esperada, actual)
        numero = actual + 1; a = _ahora()
        estado, _c = self._pedir("PATCH", self._url("proyectos", proyecto_id, "fields"),
                                 dict(UltimaVersion=numero, Modificado=a, Rubro=getattr(planta, "rubro", p["rubro"])), etag=p["etag"])
        if estado == 412:                            # otro usuario cambió el proyecto entre la lectura y la escritura
            otro = self.obtener_proyecto(str(proyecto_id))
            raise ConflictoVersion(proyecto_id, actual if esperada is None else esperada, otro["ultima_version"] if otro else None)
        _e, c = self._pedir("POST", self._url("versiones"), {"fields": dict(
            Title=f"{p['nombre']} v{numero}", ProyectoId=str(proyecto_id), Numero=numero, PlantaJson=a_json(planta_a_dict(planta)),
            Nota=nota, Fecha=a)})
        return dict(id=str(c["id"]), numero=numero)

    def listar_versiones(self, proyecto_id):
        vs = self._items("versiones", f"fields/ProyectoId eq '{proyecto_id}'")
        out = [dict(id=str(it["id"]), proyecto_id=str(proyecto_id), numero=int(it["fields"].get("Numero") or 0),
                    nota=it["fields"].get("Nota", ""), fecha=it["fields"].get("Fecha", "")) for it in vs]
        return sorted(out, key=lambda v: -v["numero"])

    def dict_version(self, version_id):
        it = self._item("versiones", version_id)
        if it is None:
            raise KeyError(f"No existe la versión {version_id}")
        return json.loads(it["fields"]["PlantaJson"])

    # --- corridas
    def guardar_corrida(self, version_id, resumen):
        gb = resumen.get("gas_base") or {}; gc = resumen.get("gas_cascada") or {}
        _e, c = self._pedir("POST", self._url("corridas"), {"fields": dict(
            Title=f"Corrida de la versión {version_id}", VersionId=str(version_id), Fecha=_ahora(),
            CoberturaCascada=resumen.get("cobertura_cascada"), CascadaKW=resumen.get("cascada"), PinchKW=resumen.get("pinch"),
            GasBaseMMBtu=gb.get("MMBtu"), GasCascadaMMBtu=gc.get("MMBtu"), ResumenJson=a_json(resumen))})
        return str(c["id"])

    def listar_corridas(self, version_id=None):
        its = self._items("corridas", f"fields/VersionId eq '{version_id}'" if version_id is not None else None)
        out = []
        for it in its:
            f = it["fields"]
            out.append(dict(id=str(it["id"]), version_id=f.get("VersionId"), fecha=f.get("Fecha", ""), cobertura_cascada=f.get("CoberturaCascada"),
                            cascada_kw=f.get("CascadaKW"), pinch_kw=f.get("PinchKW"), gas_base_mmbtu=f.get("GasBaseMMBtu"),
                            gas_cascada_mmbtu=f.get("GasCascadaMMBtu")))
        return sorted(out, key=lambda c: c["fecha"], reverse=True)


def abrir(tipo: str | None = None, **kw) -> Almacen:
    """Almacén según PAT_SIM_ALMACEN («sqlite», por defecto, o «sharepoint»)."""
    tipo = (tipo or os.environ.get("PAT_SIM_ALMACEN") or "sqlite").lower()
    if tipo == "sqlite":
        return AlmacenSQLite(**kw)
    if tipo == "sharepoint":
        return AlmacenSharePoint(**kw)
    raise ValueError(f"Almacén desconocido: {tipo}")
