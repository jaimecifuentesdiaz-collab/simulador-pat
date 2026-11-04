"""Base de datos SQLite del simulador PAT (fase 4). Usa solo la biblioteca estándar (sqlite3).

Tablas: proyectos, versiones (la planta completa en JSON), corridas (resultados de cada cálculo), fuentes (citas del
Capítulo 1) y parametros_catalogo (valor por defecto, unidad, categoría, fuente y justificación de cada parámetro de
cada tipo de equipo). SharePoint de la UTAL queda como extensión futura: exige que TI registre la aplicación.
"""
from __future__ import annotations
import csv, json, os, re, sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CSV_FUENTES = AQUI / "fuentes_capitulo1.csv"
CSV_FUENTES_BIOMASA = AQUI / "fuentes_biomasa.csv"     # fase 6: pellet, chip de madera y leña
# …/Aplicacion simulador/02 Motor de calculo Python/pat_sim/datos/bd.py  →  …/Aplicacion simulador/03 Base de datos
RUTA_PREDETERMINADA = AQUI.parents[2] / "03 Base de datos" / "simulador_pat.db"
NOMBRE_AGROZZI = "Planta basada en Agrozzi"

ESQUEMA = """
CREATE TABLE IF NOT EXISTS proyectos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    rubro TEXT NOT NULL,
    descripcion TEXT NOT NULL DEFAULT '',
    creado TEXT NOT NULL,
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS versiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    planta_json TEXT NOT NULL,
    nota TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL,
    UNIQUE (proyecto_id, numero)
);
CREATE TABLE IF NOT EXISTS corridas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    version_id INTEGER NOT NULL REFERENCES versiones(id) ON DELETE CASCADE,
    fecha TEXT NOT NULL,
    cobertura_cascada REAL,
    cascada_kw REAL,
    pinch_kw REAL,
    gas_base_mmbtu REAL,
    gas_cascada_mmbtu REAL,   -- gas que desplaza la cascada (no el gas que queda)
    resumen_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS fuentes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cita TEXT NOT NULL,
    archivo TEXT NOT NULL UNIQUE,
    doi TEXT,
    url TEXT,
    fecha_consulta TEXT,
    nota TEXT NOT NULL DEFAULT '',
    sha1 TEXT NOT NULL DEFAULT ''
);
CREATE TABLE IF NOT EXISTS parametros_catalogo (
    tipo_equipo TEXT NOT NULL,
    clave TEXT NOT NULL,
    nombre TEXT NOT NULL,
    valor_defecto TEXT,
    unidad TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    justificacion TEXT NOT NULL DEFAULT '',
    minimo REAL,
    maximo REAL,
    PRIMARY KEY (tipo_equipo, clave)
);
CREATE INDEX IF NOT EXISTS ix_versiones_proyecto ON versiones (proyecto_id, numero);
CREATE INDEX IF NOT EXISTS ix_corridas_version ON corridas (version_id);
"""

# PAT 133 (mejora 16): modo curso. Tablas nuevas con CREATE TABLE IF NOT EXISTS, así una base creada antes las recibe al
# abrirse sin perder nada. La clave del profesor se guarda solo como hash con sal (motor/curso.py), nunca en claro.
ESQUEMA_CURSO = """
CREATE TABLE IF NOT EXISTS curso (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    rubro TEXT NOT NULL DEFAULT 'tomate',
    clave_hash TEXT NOT NULL DEFAULT '',
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS estudiantes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    curso_id INTEGER NOT NULL REFERENCES curso(id) ON DELETE CASCADE,
    identificador TEXT NOT NULL,
    nombre TEXT NOT NULL DEFAULT '',
    creado TEXT NOT NULL,
    UNIQUE (curso_id, identificador)
);
CREATE TABLE IF NOT EXISTS entregas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    estudiante_id INTEGER NOT NULL REFERENCES estudiantes(id) ON DELETE CASCADE,
    puntaje INTEGER NOT NULL,
    detalle_json TEXT NOT NULL DEFAULT '{}',
    rubro TEXT NOT NULL DEFAULT '',
    semilla INTEGER,
    fecha TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_estudiantes_curso ON estudiantes (curso_id);
CREATE INDEX IF NOT EXISTS ix_entregas_estudiante ON entregas (estudiante_id);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _json_default(o):
    """Convierte tipos de numpy y conjuntos a tipos de JSON."""
    if hasattr(o, "item"):
        return o.item()
    if isinstance(o, (set, tuple)):
        return list(o)
    raise TypeError(f"No se puede guardar {type(o).__name__} en JSON")


def a_json(d) -> str:
    return json.dumps(d, ensure_ascii=False, default=_json_default)


def planta_a_dict(pl) -> dict:
    """Planta completa lista para guardar: equipos, conexiones, especificaciones, instrumentos y la semilla _p."""
    d = pl.a_dict()
    d["_p"] = getattr(pl, "_p", None)
    return d


def planta_desde_json(texto: str, resolver: bool = True):
    from ..catalogos.registro import planta_desde_dict
    pl = planta_desde_dict(json.loads(texto))
    return pl.resolver() if resolver else pl


def copiar_planta(pl, resolver: bool = True):
    """Copia independiente de una planta (para escenarios de sensibilidad)."""
    from ..catalogos.registro import planta_desde_dict
    nueva = planta_desde_dict(json.loads(a_json(planta_a_dict(pl))))
    return nueva.resolver() if resolver else nueva


class BaseDatos:
    """Acceso a simulador_pat.db. Abre una conexión por operación (Streamlit ejecuta cada recarga en un hilo distinto)."""

    def __init__(self, ruta: str | os.PathLike | None = None):
        ruta = ruta or os.environ.get("PAT_SIM_DB") or RUTA_PREDETERMINADA
        self.ruta = str(ruta)
        self._memoria = self.ruta == ":memory:"
        self._persistente = sqlite3.connect(":memory:", check_same_thread=False) if self._memoria else None
        if self._persistente is not None:
            self._persistente.row_factory = sqlite3.Row
        elif Path(self.ruta).parent.exists() is False:
            Path(self.ruta).parent.mkdir(parents=True, exist_ok=True)
        self.inicializar()

    @contextmanager
    def _con(self):
        if self._persistente is not None:
            con = self._persistente
            con.execute("PRAGMA foreign_keys = ON")
            try:
                yield con
                con.commit()
            except Exception:
                con.rollback(); raise
            return
        con = sqlite3.connect(self.ruta, timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys = ON")
        try:
            yield con
            con.commit()
        except Exception:
            con.rollback(); raise
        finally:
            con.close()

    def inicializar(self):
        with self._con() as con:
            con.executescript(ESQUEMA)
            con.executescript(ESQUEMA_CURSO)          # PAT 133: tablas del modo curso

    # ------------------------------------------------------------------ proyectos
    def crear_proyecto(self, nombre: str, rubro: str = "general", descripcion: str = "") -> int:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El proyecto necesita un nombre")
        ahora = _ahora()
        with self._con() as con:
            try:
                cur = con.execute("INSERT INTO proyectos (nombre, rubro, descripcion, creado, modificado) VALUES (?,?,?,?,?)",
                                  (nombre, rubro, descripcion, ahora, ahora))
            except sqlite3.IntegrityError:
                raise ValueError(f"Ya existe un proyecto llamado «{nombre}»") from None
            return int(cur.lastrowid)

    def obtener_proyecto(self, ref: int | str) -> dict | None:
        with self._con() as con:
            col = "id" if isinstance(ref, int) else "nombre"
            f = con.execute(f"SELECT * FROM proyectos WHERE {col} = ?", (ref,)).fetchone()
            return dict(f) if f else None

    def listar_proyectos(self) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute(
                "SELECT p.*, (SELECT COUNT(*) FROM versiones v WHERE v.proyecto_id = p.id) AS n_versiones "
                "FROM proyectos p ORDER BY p.modificado DESC, p.id DESC")]

    def eliminar_proyecto(self, proyecto_id: int):
        with self._con() as con:
            con.execute("DELETE FROM proyectos WHERE id = ?", (proyecto_id,))

    # ------------------------------------------------------------------ versiones
    def guardar_version(self, proyecto_id: int, planta, nota: str = "") -> dict:
        """Guarda la planta como una versión nueva del proyecto (número correlativo). Devuelve {id, numero}."""
        texto = a_json(planta_a_dict(planta)); ahora = _ahora()
        with self._con() as con:
            if con.execute("SELECT 1 FROM proyectos WHERE id = ?", (proyecto_id,)).fetchone() is None:
                raise ValueError(f"No existe el proyecto {proyecto_id}")
            numero = con.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM versiones WHERE proyecto_id = ?", (proyecto_id,)).fetchone()[0]
            cur = con.execute("INSERT INTO versiones (proyecto_id, numero, planta_json, nota, fecha) VALUES (?,?,?,?,?)",
                              (proyecto_id, numero, texto, nota, ahora))
            con.execute("UPDATE proyectos SET modificado = ?, rubro = ? WHERE id = ?", (ahora, getattr(planta, "rubro", "general"), proyecto_id))
            return dict(id=int(cur.lastrowid), numero=int(numero))

    def listar_versiones(self, proyecto_id: int) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute(
                "SELECT v.id, v.proyecto_id, v.numero, v.nota, v.fecha, "
                "(SELECT COUNT(*) FROM corridas c WHERE c.version_id = v.id) AS n_corridas "
                "FROM versiones v WHERE v.proyecto_id = ? ORDER BY v.numero DESC", (proyecto_id,))]

    def dict_version(self, version_id: int) -> dict:
        with self._con() as con:
            f = con.execute("SELECT planta_json FROM versiones WHERE id = ?", (version_id,)).fetchone()
        if f is None:
            raise KeyError(f"No existe la versión {version_id}")
        return json.loads(f["planta_json"])

    def cargar_version(self, version_id: int, resolver: bool = True):
        """Reconstruye la planta guardada y la vuelve a resolver (mismas cifras que al guardarla)."""
        from ..catalogos.registro import planta_desde_dict
        pl = planta_desde_dict(self.dict_version(version_id))
        return pl.resolver() if resolver else pl

    def ultima_version(self, proyecto_id: int) -> int | None:
        with self._con() as con:
            f = con.execute("SELECT id FROM versiones WHERE proyecto_id = ? ORDER BY numero DESC LIMIT 1", (proyecto_id,)).fetchone()
            return int(f["id"]) if f else None

    def eliminar_version(self, version_id: int):
        with self._con() as con:
            con.execute("DELETE FROM versiones WHERE id = ?", (version_id,))

    # ------------------------------------------------------------------ corridas
    def guardar_corrida(self, version_id: int, resumen: dict) -> int:
        gb = resumen.get("gas_base") or {}; gc = resumen.get("gas_cascada") or {}
        with self._con() as con:
            cur = con.execute(
                "INSERT INTO corridas (version_id, fecha, cobertura_cascada, cascada_kw, pinch_kw, gas_base_mmbtu, gas_cascada_mmbtu, resumen_json) "
                "VALUES (?,?,?,?,?,?,?,?)",
                (version_id, _ahora(), resumen.get("cobertura_cascada"), resumen.get("cascada"), resumen.get("pinch"),
                 gb.get("MMBtu"), gc.get("MMBtu"), a_json(resumen)))
            return int(cur.lastrowid)

    def listar_corridas(self, version_id: int | None = None) -> list[dict]:
        sql = ("SELECT c.id, c.version_id, v.numero AS version, p.nombre AS proyecto, c.fecha, c.cobertura_cascada, c.cascada_kw, "
               "c.pinch_kw, c.gas_base_mmbtu, c.gas_cascada_mmbtu FROM corridas c JOIN versiones v ON v.id = c.version_id "
               "JOIN proyectos p ON p.id = v.proyecto_id")
        args: tuple = ()
        if version_id is not None:
            sql += " WHERE c.version_id = ?"; args = (version_id,)
        with self._con() as con:
            return [dict(f) for f in con.execute(sql + " ORDER BY c.id DESC", args)]

    def obtener_corrida(self, corrida_id: int) -> dict:
        with self._con() as con:
            f = con.execute("SELECT * FROM corridas WHERE id = ?", (corrida_id,)).fetchone()
        if f is None:
            raise KeyError(f"No existe la corrida {corrida_id}")
        d = dict(f); d["resumen"] = json.loads(d.pop("resumen_json")); return d

    # ------------------------------------------------------------------ fuentes
    def agregar_fuente(self, cita: str, archivo: str, doi: str | None = None, url: str | None = None,
                       fecha_consulta: str | None = None, nota: str = "", sha1: str = "") -> int:
        with self._con() as con:
            con.execute(
                "INSERT INTO fuentes (cita, archivo, doi, url, fecha_consulta, nota, sha1) VALUES (?,?,?,?,?,?,?) "
                "ON CONFLICT(archivo) DO UPDATE SET cita=excluded.cita, doi=excluded.doi, url=excluded.url, "
                "fecha_consulta=excluded.fecha_consulta, nota=excluded.nota, sha1=excluded.sha1",
                (cita, archivo, doi, url, fecha_consulta, nota, sha1))
            return int(con.execute("SELECT id FROM fuentes WHERE archivo = ?", (archivo,)).fetchone()["id"])

    def listar_fuentes(self, buscar: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM fuentes", ()
        if buscar:
            sql += " WHERE cita LIKE ? OR archivo LIKE ? OR nota LIKE ?"; args = (f"%{buscar}%",) * 3
        with self._con() as con:
            return [dict(f) for f in con.execute(sql + " ORDER BY archivo", args)]

    def cargar_fuentes_csv(self, ruta: str | os.PathLike = CSV_FUENTES) -> int:
        n = 0
        with open(ruta, encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                self.agregar_fuente(r["cita"], r["archivo"], r.get("doi") or None, r.get("url") or None,
                                    r.get("fecha_consulta") or None, r.get("nota", ""), r.get("sha1", ""))
                n += 1
        return n

    # ------------------------------------------------------------------ catálogo de parámetros
    def sembrar_catalogo(self) -> int:
        """Copia a la base los parámetros por defecto de cada tipo de equipo (tal como están en los catálogos de Python)."""
        from ..catalogos.registro import TIPOS
        n = 0
        with self._con() as con:
            for tipo, cls in TIPOS.items():
                for p in cls.params_base:
                    con.execute(
                        "INSERT OR REPLACE INTO parametros_catalogo (tipo_equipo, clave, nombre, valor_defecto, unidad, categoria, fuente, justificacion, minimo, maximo) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (tipo, p.clave, p.nombre, a_json(p.valor), p.unidad, p.categoria, p.fuente, p.justificacion, p.minimo, p.maximo))
                    n += 1
        return n

    def parametros_catalogo(self, tipo_equipo: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM parametros_catalogo", ()
        if tipo_equipo:
            sql += " WHERE tipo_equipo = ?"; args = (tipo_equipo,)
        with self._con() as con:
            filas = [dict(f) for f in con.execute(sql + " ORDER BY tipo_equipo, rowid", args)]
        for f in filas:
            f["valor_defecto"] = json.loads(f["valor_defecto"]) if f["valor_defecto"] is not None else None
        return filas

    # ------------------------------------------------------------------ precarga
    def precargar(self) -> dict:
        """Deja listos los proyectos (Agrozzi y los escenarios de pellet, chip y leña), las fuentes y el catálogo de parámetros (idempotente)."""
        from ..escenarios import agrozzi
        from ..motor.resumen import resumen_planta
        out = {}
        if CSV_FUENTES.exists():
            out["fuentes"] = self.cargar_fuentes_csv()
        out["parametros"] = self.sembrar_catalogo()
        if self.obtener_proyecto(NOMBRE_AGROZZI) is None:
            pid = self.crear_proyecto(NOMBRE_AGROZZI, "tomate",
                                      "Línea de pasta de tomate de la planta basada en Agrozzi (Empresas Carozzi S.A., Teno), "
                                      "como en el Capítulo 1 y en Modelo_PAT_Agrozzi_v2.xlsx.")
            pl = agrozzi.crear()
            v = self.guardar_version(pid, pl, "Línea base del Capítulo 1 (Modelo_PAT_Agrozzi_v2.xlsx, parámetros del 26-10-2026)")
            self.guardar_corrida(v["id"], resumen_planta(pl))
            out["proyecto_agrozzi"] = pid
        if CSV_FUENTES_BIOMASA.exists():
            out["fuentes_biomasa"] = self.cargar_fuentes_csv(CSV_FUENTES_BIOMASA)
        # fase 6: un proyecto por rubro de biomasa con su escenario base
        from ..escenarios import pellet, chip, lena
        for mod, rubro in ((pellet, "pellet"), (chip, "chip"), (lena, "lena")):
            if self.obtener_proyecto(mod.NOMBRE) is None:
                pid = self.crear_proyecto(mod.NOMBRE, rubro, (mod.__doc__ or "").strip().split("\n")[0])
                pl = mod.crear()
                v = self.guardar_version(pid, pl, "Escenario base de la fase 6 (parámetros con fuente, 29-10-2026)")
                self.guardar_corrida(v["id"], resumen_planta(pl))
                out[f"proyecto_{rubro}"] = pid
        return out

    def contar(self) -> dict:
        with self._con() as con:
            return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                    for t in ("proyectos", "versiones", "corridas", "fuentes", "parametros_catalogo")}

    # ------------------------------------------------------------------ modo curso (PAT 133, mejora 16)
    def obtener_curso(self, ref: int | str) -> dict | None:
        with self._con() as con:
            col = "id" if isinstance(ref, int) else "nombre"
            f = con.execute(f"SELECT * FROM curso WHERE {col} = ?", (ref,)).fetchone()
            return dict(f) if f else None

    def obtener_o_crear_curso(self, nombre: str, rubro: str = "tomate") -> dict:
        nombre = nombre.strip()
        if not nombre:
            raise ValueError("El curso necesita un nombre")
        with self._con() as con:
            con.execute("INSERT OR IGNORE INTO curso (nombre, rubro, creado) VALUES (?,?,?)", (nombre, rubro, _ahora()))
        return self.obtener_curso(nombre)

    def actualizar_curso(self, curso_id: int, rubro: str | None = None, clave_hash: str | None = None):
        with self._con() as con:
            if rubro is not None:
                con.execute("UPDATE curso SET rubro = ? WHERE id = ?", (rubro, curso_id))
            if clave_hash is not None:
                con.execute("UPDATE curso SET clave_hash = ? WHERE id = ?", (clave_hash, curso_id))

    def registrar_estudiante(self, curso_id: int, identificador: str, nombre: str = "") -> int:
        """Alta del estudiante en el curso (si ya existe, devuelve su id y actualiza el nombre si viene uno)."""
        with self._con() as con:
            con.execute("INSERT OR IGNORE INTO estudiantes (curso_id, identificador, nombre, creado) VALUES (?,?,?,?)",
                        (curso_id, identificador, nombre, _ahora()))
            if nombre:
                con.execute("UPDATE estudiantes SET nombre = ? WHERE curso_id = ? AND identificador = ?", (nombre, curso_id, identificador))
            return int(con.execute("SELECT id FROM estudiantes WHERE curso_id = ? AND identificador = ?",
                                   (curso_id, identificador)).fetchone()["id"])

    def listar_estudiantes(self, curso_id: int) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM estudiantes WHERE curso_id = ? ORDER BY identificador", (curso_id,))]

    def guardar_entrega(self, estudiante_id: int, puntaje: int, detalle: dict | None = None, rubro: str = "",
                        semilla: int | None = None) -> int:
        with self._con() as con:
            cur = con.execute("INSERT INTO entregas (estudiante_id, puntaje, detalle_json, rubro, semilla, fecha) VALUES (?,?,?,?,?,?)",
                              (estudiante_id, int(puntaje), a_json(detalle or {}), rubro, semilla, _ahora()))
            return int(cur.lastrowid)

    def listar_entregas(self, curso_id: int) -> list[dict]:
        with self._con() as con:
            filas = [dict(f) for f in con.execute(
                "SELECT e.id, s.identificador, s.nombre, e.puntaje, e.rubro, e.semilla, e.fecha, e.detalle_json "
                "FROM entregas e JOIN estudiantes s ON s.id = e.estudiante_id WHERE s.curso_id = ? "
                "ORDER BY s.identificador, e.id", (curso_id,))]
        for f in filas:
            f["detalle"] = json.loads(f.pop("detalle_json") or "{}")
        return filas
