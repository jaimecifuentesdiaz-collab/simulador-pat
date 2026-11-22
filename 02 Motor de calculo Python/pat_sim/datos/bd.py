"""Base de datos SQLite del simulador PAT (fase 4). Usa solo la biblioteca estándar (sqlite3).

Tablas: proyectos, versiones (la planta completa en JSON), corridas (resultados de cada cálculo), fuentes (citas del
Capítulo 1) y parametros_catalogo (valor por defecto, unidad, categoría, fuente y justificación de cada parámetro de
cada tipo de equipo). PAT 138: proyectos_usuario y proyectos_usuario_versiones (proyectos que guarda cada persona, con la
planta y el estado de la sesión). PAT 140 g: proyectos_usuario_autoguardado (una ranura de guardado automático por proyecto,
la «partida» que se retoma al volver a abrir la aplicación). SharePoint de la UTAL queda como extensión futura: exige que TI
registre la aplicación.
"""
from __future__ import annotations
import csv, hashlib, json, os, re, socket, sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

AQUI = Path(__file__).resolve().parent
CSV_FUENTES = AQUI / "fuentes_capitulo1.csv"
CSV_FUENTES_BIOMASA = AQUI / "fuentes_biomasa.csv"     # fase 6: pellet, chip de madera y leña
CSV_FUENTES_AGAR = AQUI / "fuentes_agar.csv"           # PAT 143 b: agar agar
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

# PAT 138 (pedido de Jaime, 13-11-2026): proyectos del usuario. Cada proyecto se llama «Proyecto de <persona> <n>» (o el nombre
# que la persona escriba, sin repetir) y guarda la planta, el estado de la sesión para retomar (desafío, economía, temporada,
# datos medidos, layout y demás) y las cifras clave para la lista. Cada «Guardar» agrega una versión al historial del proyecto;
# la fila del proyecto lleva la copia de la última. Sin límite de cantidad. Las tablas proyectos y versiones de la fase 4 siguen
# igual (plantas precargadas y versiones antiguas).
ESQUEMA_PROYECTOS_USUARIO = """
CREATE TABLE IF NOT EXISTS proyectos_usuario (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE COLLATE NOCASE,
    persona TEXT NOT NULL DEFAULT '',
    numero INTEGER,
    usuario TEXT NOT NULL DEFAULT '',
    nota TEXT NOT NULL DEFAULT '',
    rubro TEXT NOT NULL DEFAULT '',
    tipo_planta TEXT NOT NULL DEFAULT '',
    creado TEXT NOT NULL,
    modificado TEXT NOT NULL,
    n_versiones INTEGER NOT NULL DEFAULT 0,
    planta_json TEXT NOT NULL,
    estado_json TEXT NOT NULL DEFAULT '{}',
    resumen_json TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS proyectos_usuario_versiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proyecto_id INTEGER NOT NULL REFERENCES proyectos_usuario(id) ON DELETE CASCADE,
    numero INTEGER NOT NULL,
    fecha TEXT NOT NULL,
    nota TEXT NOT NULL DEFAULT '',
    planta_json TEXT NOT NULL,
    estado_json TEXT NOT NULL DEFAULT '{}',
    resumen_json TEXT NOT NULL DEFAULT '{}',
    UNIQUE (proyecto_id, numero)
);
CREATE INDEX IF NOT EXISTS ix_proyectos_usuario_persona ON proyectos_usuario (persona, numero);
CREATE INDEX IF NOT EXISTS ix_proyectos_usuario_versiones ON proyectos_usuario_versiones (proyecto_id, numero);
"""
# PAT 140 g (17-11-2026): guardado automático tipo «partida». Una sola fila por proyecto que se sobrescribe en cada guardado
# automático (no llena el historial: las versiones numeradas siguen siendo solo las del botón «Guardar proyecto»). usuario: el
# usuario con acceso controlado que escribió; equipo: el nombre del computador, para ofrecer «Continuar la última partida» del
# mismo computador sin acceso controlado. Tabla nueva con CREATE TABLE IF NOT EXISTS: una base anterior la recibe sin perder nada.
ESQUEMA_AUTOGUARDADO = """
CREATE TABLE IF NOT EXISTS proyectos_usuario_autoguardado (
    proyecto_id INTEGER PRIMARY KEY REFERENCES proyectos_usuario(id) ON DELETE CASCADE,
    usuario TEXT NOT NULL DEFAULT '',
    equipo TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL,
    huella TEXT NOT NULL DEFAULT '',
    planta_json TEXT NOT NULL,
    estado_json TEXT NOT NULL DEFAULT '{}',
    resumen_json TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS ix_autoguardado_fecha ON proyectos_usuario_autoguardado (fecha);
"""
FORMATO_PARTIDA = "partida_simulador_pat"      # archivo .json de «Descargar partida» y «Cargar partida»
_RE_NOMBRE_AUTO = re.compile(r"^proyecto(?: de (.+?))? (\d+)$", re.IGNORECASE)


class NombreRepetido(ValueError):
    """El nombre ya lo usa otro proyecto: existente es su fila y sugerido el siguiente nombre libre de la misma persona."""

    def __init__(self, nombre: str, existente: dict, sugerido: str):
        super().__init__(f"Ya existe un proyecto llamado «{nombre}»")
        self.nombre, self.existente, self.sugerido = nombre, existente, sugerido


def _sin_tildes(texto) -> str:
    """Texto en minúsculas y sin tildes, para buscar «perez» y encontrar «Pérez»."""
    import unicodedata
    t = unicodedata.normalize("NFKD", str(texto or "").casefold())
    return "".join(c for c in t if not unicodedata.combining(c))


def limpiar_nombre(texto) -> str:
    """Quita espacios de más (al inicio, al final y repetidos)."""
    return " ".join(str(texto or "").split())


def nombre_automatico(persona: str, numero: int) -> str:
    """«Proyecto de <persona> <n>», o «Proyecto <n>» si no hay nombre de persona."""
    persona = limpiar_nombre(persona)
    return f"Proyecto de {persona} {int(numero)}" if persona else f"Proyecto {int(numero)}"


def leer_nombre_automatico(nombre: str) -> tuple[str, int] | None:
    """(persona, n) de un nombre con la forma automática, o None."""
    m = _RE_NOMBRE_AUTO.match(limpiar_nombre(nombre))
    return (limpiar_nombre(m.group(1) or ""), int(m.group(2))) if m else None


def planta_completa_a_dict(pl) -> dict:
    """planta_a_dict más la categoría, la fuente y la justificación de los parámetros que difieren del catálogo (selección
    comercial, datos medidos), para que la planta cargada muestre lo mismo. planta_desde_dict ignora la clave _meta_params."""
    d = planta_a_dict(pl)
    try:
        from ..catalogos.registro import TIPOS
        meta = {}
        for eid, eq in pl.equipos.items():
            cls = TIPOS.get(eq.tipo)
            ref = cls(eid) if cls else None
            for k, p in eq.params.items():
                q = ref.params.get(k) if ref is not None else None
                m = {a: getattr(p, a) for a in ("categoria", "fuente", "justificacion")
                     if q is None or getattr(p, a) != getattr(q, a)}
                if m:
                    meta.setdefault(eid, {})[k] = m
        if meta:
            d["_meta_params"] = meta
    except Exception:
        pass                                            # sin metadatos: la planta y sus cifras se guardan igual
    return d


def planta_completa_desde_dict(d: dict, resolver: bool = True):
    """Reconstruye la planta de planta_completa_a_dict (también sirve con planta_a_dict). Si no se puede resolver (carta en
    blanco o planta a medio armar), queda sin resolver, como estaba."""
    from ..catalogos.registro import planta_desde_dict
    pl = planta_desde_dict(d)
    for eid, ps in (d.get("_meta_params") or {}).items():
        eq = pl.equipos.get(eid)
        for k, m in (ps or {}).items():
            if eq is not None and k in eq.params:
                for a, v in m.items():
                    setattr(eq.params[k], a, v)
    if resolver and pl.equipos:
        try:
            pl.resolver()
        except Exception:
            pl.resuelta = False
    return pl


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def nombre_equipo() -> str:
    """Nombre del computador donde corre la aplicación (para la última partida sin acceso controlado)."""
    try:
        return limpiar_nombre(socket.gethostname())[:120]
    except Exception:
        return ""


def partida_a_json(planta, estado: dict | None = None, nombre: str = "", resumen: dict | None = None) -> str:
    """Archivo de «Descargar partida (.json)»: la planta completa, el estado de la sesión y, si viene, el resumen."""
    return json.dumps(dict(formato=FORMATO_PARTIDA, version=1, nombre=limpiar_nombre(nombre), fecha=_ahora(),
                           planta=planta_completa_a_dict(planta), estado=estado or {}, resumen=resumen or {}),
                      ensure_ascii=False, default=_json_default, indent=1)


def leer_partida(texto, resolver: bool = True) -> dict:
    """Lee el archivo de una partida: {nombre, fecha, planta, estado, resumen}. ValueError con un mensaje claro si no es una
    partida del simulador o viene dañada."""
    if isinstance(texto, (bytes, bytearray)):
        texto = texto.decode("utf-8-sig", errors="replace")
    try:
        d = json.loads(texto)
    except Exception:
        raise ValueError("El archivo no es un JSON válido") from None
    if not isinstance(d, dict) or d.get("formato") != FORMATO_PARTIDA or not isinstance(d.get("planta"), dict):
        raise ValueError("El archivo no es una partida del simulador (se descarga con «Descargar partida (.json)»)")
    try:
        pl = planta_completa_desde_dict(d["planta"], resolver=resolver)
    except Exception as e:
        raise ValueError(f"La planta del archivo no se pudo leer: {e}") from None
    estado = d.get("estado") if isinstance(d.get("estado"), dict) else {}
    return dict(nombre=limpiar_nombre(d.get("nombre")), fecha=d.get("fecha") or "", planta=pl, estado=estado,
                resumen=d.get("resumen") if isinstance(d.get("resumen"), dict) else {})


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
            con.executescript(ESQUEMA_PROYECTOS_USUARIO)   # PAT 138: proyectos del usuario (se crean solas en una base anterior)
            con.executescript(ESQUEMA_AUTOGUARDADO)        # PAT 140 g: ranura de guardado automático por proyecto

    # ------------------------------------------------------------------ proyectos del usuario (PAT 138)
    _COLS_LISTA = ("id, nombre, persona, numero, usuario, nota, rubro, tipo_planta, creado, modificado, n_versiones, resumen_json")

    @staticmethod
    def _fila_lista(f) -> dict:
        d = dict(f)
        d["resumen"] = json.loads(d.pop("resumen_json", None) or "{}")
        return d

    def buscar_proyecto_usuario(self, nombre: str) -> dict | None:
        """Proyecto con ese nombre (sin distinguir mayúsculas ni espacios de más), sin la planta ni el estado."""
        nombre = limpiar_nombre(nombre)
        with self._con() as con:
            f = con.execute(f"SELECT {self._COLS_LISTA} FROM proyectos_usuario WHERE nombre = ? COLLATE NOCASE", (nombre,)).fetchone()
            if f is None:                               # NOCASE solo iguala letras sin tilde: se revisa también con casefold
                clave = nombre.casefold()
                f = next((x for x in con.execute(f"SELECT {self._COLS_LISTA} FROM proyectos_usuario")
                          if x["nombre"].casefold() == clave), None)
        return self._fila_lista(f) if f else None

    def obtener_proyecto_usuario(self, proyecto_id: int) -> dict | None:
        with self._con() as con:
            f = con.execute(f"SELECT {self._COLS_LISTA} FROM proyectos_usuario WHERE id = ?", (int(proyecto_id),)).fetchone()
        return self._fila_lista(f) if f else None

    def siguiente_numero(self, persona: str = "") -> int:
        """Siguiente número de proyecto de la persona (1, 2, 3…): uno más que el mayor que ya usa, por su columna numero o por
        los nombres «Proyecto de <persona> <n>». Sin persona, cuenta los «Proyecto <n>»."""
        clave = limpiar_nombre(persona).casefold(); usados = [0]
        with self._con() as con:
            for f in con.execute("SELECT nombre, persona, numero FROM proyectos_usuario"):
                if f["numero"] is not None and limpiar_nombre(f["persona"]).casefold() == clave:
                    usados.append(int(f["numero"]))
                a = leer_nombre_automatico(f["nombre"])
                if a and a[0].casefold() == clave:
                    usados.append(a[1])
        return max(usados) + 1

    def nombre_sugerido(self, persona: str = "") -> str:
        """Nombre automático libre: «Proyecto de <persona> <n>» con el siguiente número de esa persona."""
        n = self.siguiente_numero(persona)
        while self.buscar_proyecto_usuario(nombre_automatico(persona, n)) is not None:
            n += 1
        return nombre_automatico(persona, n)

    def guardar_proyecto_usuario(self, planta, nombre: str | None = None, estado: dict | None = None, resumen: dict | None = None,
                                 persona: str = "", nota: str = "", usuario: str = "", proyecto_id: int | None = None,
                                 sobrescribir: bool = False, dueno: str | None = None) -> dict:
        """Guarda la planta y el estado de la sesión como un proyecto del usuario.
        - proyecto_id: guarda en ese proyecto (una versión más); si además viene un nombre distinto, lo renombra.
        - Sin proyecto_id: crea un proyecto con el nombre (o el automático de la persona si no viene). Si el nombre ya existe,
          lanza NombreRepetido, salvo con sobrescribir=True, que guarda en ese proyecto como una versión más.
        PAT 139: con dueno (usuario con acceso controlado que no es docente) solo se escribe en proyectos de ese usuario: el
        proyecto abierto de otro lanza PermissionError y un nombre de otro usuario es NombreRepetido sin poder sobrescribirlo.
        Devuelve {id, nombre, version, nuevo}."""
        persona = limpiar_nombre(persona)
        actual = self.obtener_proyecto_usuario(proyecto_id) if proyecto_id is not None else None
        if dueno is not None and actual is not None and not self.es_dueno(actual, dueno):
            raise PermissionError(f"El proyecto «{actual['nombre']}» es de otro usuario: guárdelo como un proyecto nuevo")
        if proyecto_id is not None and actual is None:
            proyecto_id = None                          # el proyecto abierto se eliminó: se crea de nuevo
        nombre = limpiar_nombre(nombre) or (actual["nombre"] if actual else self.nombre_sugerido(persona))
        auto = leer_nombre_automatico(nombre)
        otro = self.buscar_proyecto_usuario(nombre)
        if proyecto_id is None and otro is not None:
            if not sobrescribir or (dueno is not None and not self.es_dueno(otro, dueno)):
                raise NombreRepetido(nombre, otro, self.nombre_sugerido(otro["persona"] or (auto[0] if auto else persona)))
            proyecto_id, actual = otro["id"], otro
        elif proyecto_id is not None and otro is not None and otro["id"] != proyecto_id:
            raise NombreRepetido(nombre, otro, self.nombre_sugerido(otro["persona"] or (auto[0] if auto else persona)))
        texto_pl = a_json(planta_completa_a_dict(planta))
        texto_es = a_json(estado or {}); texto_re = a_json(resumen or {})
        rubro = getattr(planta, "rubro", "") or ""
        tipo = (resumen or {}).get("tipo_planta") or ""
        ahora = _ahora()
        with self._con() as con:
            if proyecto_id is None:
                cur = con.execute(
                    "INSERT INTO proyectos_usuario (nombre, persona, numero, usuario, nota, rubro, tipo_planta, creado, modificado, "
                    "n_versiones, planta_json, estado_json, resumen_json) VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)",
                    (nombre, (auto[0] if auto and auto[0] else persona), auto[1] if auto else None, usuario or "", nota or "",
                     rubro, tipo, ahora, ahora, texto_pl, texto_es, texto_re))
                proyecto_id = int(cur.lastrowid); nuevo = True
            else:
                nuevo = False
                if nombre != actual["nombre"]:          # renombrado al guardar
                    con.execute("UPDATE proyectos_usuario SET nombre = ?, numero = ?, persona = CASE WHEN ? <> '' THEN ? ELSE persona END "
                                "WHERE id = ?", (nombre, auto[1] if auto else None, auto[0] if auto else "", auto[0] if auto else "",
                                                 proyecto_id))
                con.execute(
                    "UPDATE proyectos_usuario SET usuario = CASE WHEN ? <> '' THEN ? ELSE usuario END, "
                    "nota = CASE WHEN ? <> '' THEN ? ELSE nota END, rubro = ?, tipo_planta = ?, modificado = ?, planta_json = ?, "
                    "estado_json = ?, resumen_json = ? WHERE id = ?",
                    (usuario or "", usuario or "", nota or "", nota or "", rubro, tipo, ahora, texto_pl, texto_es, texto_re, proyecto_id))
            n = con.execute("SELECT COALESCE(MAX(numero), 0) + 1 FROM proyectos_usuario_versiones WHERE proyecto_id = ?",
                            (proyecto_id,)).fetchone()[0]
            con.execute("INSERT INTO proyectos_usuario_versiones (proyecto_id, numero, fecha, nota, planta_json, estado_json, resumen_json) "
                        "VALUES (?,?,?,?,?,?,?)", (proyecto_id, n, ahora, nota or "", texto_pl, texto_es, texto_re))
            con.execute("UPDATE proyectos_usuario SET n_versiones = (SELECT COUNT(*) FROM proyectos_usuario_versiones "
                        "WHERE proyecto_id = ?) WHERE id = ?", (proyecto_id, proyecto_id))
        return dict(id=int(proyecto_id), nombre=nombre, version=int(n), nuevo=nuevo)

    def listar_proyectos_usuario(self, buscar: str | None = None, persona: str | None = None, usuario: str | None = None) -> list[dict]:
        """Proyectos del usuario, del último modificado al primero, sin la planta ni el estado (para la lista). buscar filtra por
        nombre o persona sin distinguir mayúsculas ni tildes. PAT 139: usuario (el dueño, con acceso controlado) deja solo los
        proyectos de ese usuario; None no filtra (docente o aplicación sin acceso controlado)."""
        with self._con() as con:
            filas = [self._fila_lista(f) for f in con.execute(
                f"SELECT {self._COLS_LISTA} FROM proyectos_usuario ORDER BY modificado DESC, id DESC")]
        if usuario is not None:
            dueno = limpiar_nombre(usuario).casefold()
            filas = [f for f in filas if limpiar_nombre(f.get("usuario") or "").casefold() == dueno]
        if persona is not None:
            clave = limpiar_nombre(persona).casefold()
            filas = [f for f in filas if limpiar_nombre(f["persona"]).casefold() == clave]
        if buscar and buscar.strip():
            b = _sin_tildes(buscar)
            filas = [f for f in filas if b in _sin_tildes(f["nombre"]) or b in _sin_tildes(f["persona"])
                     or b in _sin_tildes(f.get("usuario") or "")]
        return filas

    def listar_versiones_usuario(self, proyecto_id: int) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute(
                "SELECT id, proyecto_id, numero, fecha, nota FROM proyectos_usuario_versiones WHERE proyecto_id = ? ORDER BY numero DESC",
                (int(proyecto_id),))]

    def cargar_proyecto_usuario(self, proyecto_id: int, version: int | None = None, resolver: bool = True) -> dict:
        """{proyecto, version, planta, estado, resumen} de la última versión o de la versión pedida (su número)."""
        p = self.obtener_proyecto_usuario(proyecto_id)
        if p is None:
            raise KeyError(f"No existe el proyecto {proyecto_id}")
        with self._con() as con:
            if version is None:
                f = con.execute("SELECT numero, planta_json, estado_json, resumen_json FROM proyectos_usuario_versiones "
                                "WHERE proyecto_id = ? ORDER BY numero DESC LIMIT 1", (int(proyecto_id),)).fetchone()
            else:
                f = con.execute("SELECT numero, planta_json, estado_json, resumen_json FROM proyectos_usuario_versiones "
                                "WHERE proyecto_id = ? AND numero = ?", (int(proyecto_id), int(version))).fetchone()
            if f is None and version is None:          # sin historial: la copia de la fila del proyecto
                f = con.execute("SELECT 0 AS numero, planta_json, estado_json, resumen_json FROM proyectos_usuario WHERE id = ?",
                                (int(proyecto_id),)).fetchone()
        if f is None:
            raise KeyError(f"El proyecto {proyecto_id} no tiene la versión {version}")
        pl = planta_completa_desde_dict(json.loads(f["planta_json"]), resolver=resolver)
        return dict(proyecto=p, version=int(f["numero"]), planta=pl, estado=json.loads(f["estado_json"] or "{}"),
                    resumen=json.loads(f["resumen_json"] or "{}"))

    @staticmethod
    def es_dueno(proyecto: dict | None, usuario: str | None) -> bool:
        """PAT 139: True si el proyecto es del usuario (usuario None = sin control de dueño, todo vale)."""
        if usuario is None:
            return True
        if not proyecto:
            return False
        return limpiar_nombre(proyecto.get("usuario") or "").casefold() == limpiar_nombre(usuario).casefold() != ""

    def renombrar_proyecto_usuario(self, proyecto_id: int, nuevo: str) -> str:
        nuevo = limpiar_nombre(nuevo)
        if not nuevo:
            raise ValueError("El proyecto necesita un nombre")
        if self.obtener_proyecto_usuario(proyecto_id) is None:
            raise KeyError(f"No existe el proyecto {proyecto_id}")
        otro = self.buscar_proyecto_usuario(nuevo)
        if otro is not None and otro["id"] != int(proyecto_id):
            raise NombreRepetido(nuevo, otro, self.nombre_sugerido(otro["persona"] or (leer_nombre_automatico(nuevo) or ("", 0))[0]))
        auto = leer_nombre_automatico(nuevo)
        with self._con() as con:
            con.execute("UPDATE proyectos_usuario SET nombre = ?, numero = ?, persona = CASE WHEN ? <> '' THEN ? ELSE persona END, "
                        "modificado = ? WHERE id = ?", (nuevo, auto[1] if auto else None, auto[0] if auto else "",
                                                        auto[0] if auto else "", _ahora(), int(proyecto_id)))
        return nuevo

    def eliminar_proyecto_usuario(self, proyecto_id: int):
        with self._con() as con:
            con.execute("DELETE FROM proyectos_usuario_autoguardado WHERE proyecto_id = ?", (int(proyecto_id),))
            con.execute("DELETE FROM proyectos_usuario_versiones WHERE proyecto_id = ?", (int(proyecto_id),))
            con.execute("DELETE FROM proyectos_usuario WHERE id = ?", (int(proyecto_id),))

    def contar_proyectos_usuario(self) -> dict:
        with self._con() as con:
            return dict(proyectos=con.execute("SELECT COUNT(*) FROM proyectos_usuario").fetchone()[0],
                        versiones=con.execute("SELECT COUNT(*) FROM proyectos_usuario_versiones").fetchone()[0])

    # ------------------------------------------------------------------ guardado automático (PAT 140 g)
    def autoguardar_proyecto_usuario(self, planta, estado: dict | None = None, resumen: dict | None = None,
                                     proyecto_id: int | None = None, persona: str = "", usuario: str = "", equipo: str | None = None,
                                     huella: str = "", dueno: str | None = None) -> dict:
        """Guardado automático de la sesión: sobrescribe la ranura de autoguardado del proyecto (no agrega versiones).
        - proyecto_id: el proyecto abierto. Con dueno (acceso controlado) solo si es de ese usuario (si no, PermissionError).
        - Sin proyecto_id (o si se eliminó): crea un proyecto con el nombre automático de la persona, sin versiones numeradas.
        Si el proyecto nació del autoguardado como «Proyecto <n>» y ahora hay nombre de persona, pasa a «Proyecto de <persona> <n>».
        Devuelve {id, nombre, fecha, nuevo}."""
        persona = limpiar_nombre(persona)
        equipo = nombre_equipo() if equipo is None else limpiar_nombre(equipo)
        actual = self.obtener_proyecto_usuario(proyecto_id) if proyecto_id is not None else None
        if dueno is not None and actual is not None and not self.es_dueno(actual, dueno):
            raise PermissionError(f"El proyecto «{actual['nombre']}» es de otro usuario: el guardado automático no lo cambia")
        texto_pl = a_json(planta_completa_a_dict(planta))
        texto_es = a_json(estado or {}); texto_re = a_json(resumen or {})
        huella = huella or hashlib.sha1((texto_pl + texto_es).encode("utf-8")).hexdigest()
        ahora = _ahora(); nuevo = False
        if actual is None:
            nombre = self.nombre_sugerido(persona); auto = leer_nombre_automatico(nombre)
            with self._con() as con:
                cur = con.execute(
                    "INSERT INTO proyectos_usuario (nombre, persona, numero, usuario, nota, rubro, tipo_planta, creado, modificado, "
                    "n_versiones, planta_json, estado_json, resumen_json) VALUES (?,?,?,?,?,?,?,?,?,0,?,?,?)",
                    (nombre, persona, auto[1] if auto else None, usuario or "", "Creado por el guardado automático",
                     getattr(planta, "rubro", "") or "", (resumen or {}).get("tipo_planta") or "", ahora, ahora, texto_pl, texto_es,
                     texto_re))
                proyecto_id = int(cur.lastrowid)
            nuevo = True
        else:
            nombre = actual["nombre"]; auto = leer_nombre_automatico(nombre)
            if persona and not actual.get("n_versiones") and auto and not auto[0]:
                try:                                    # «Proyecto 3» nacido del autoguardado pasa a llevar el nombre de la persona
                    nombre = self.renombrar_proyecto_usuario(proyecto_id, self.nombre_sugerido(persona))
                except Exception:
                    pass
        with self._con() as con:
            con.execute("INSERT OR REPLACE INTO proyectos_usuario_autoguardado (proyecto_id, usuario, equipo, fecha, huella, planta_json, "
                        "estado_json, resumen_json) VALUES (?,?,?,?,?,?,?,?)",
                        (int(proyecto_id), usuario or "", equipo or "", ahora, huella, texto_pl, texto_es, texto_re))
        return dict(id=int(proyecto_id), nombre=nombre, fecha=ahora, nuevo=nuevo)

    def obtener_autoguardado(self, proyecto_id: int) -> dict | None:
        """{proyecto_id, usuario, equipo, fecha, huella} de la ranura de autoguardado del proyecto, o None."""
        with self._con() as con:
            f = con.execute("SELECT proyecto_id, usuario, equipo, fecha, huella FROM proyectos_usuario_autoguardado WHERE proyecto_id = ?",
                            (int(proyecto_id),)).fetchone()
        return dict(f) if f else None

    def fechas_autoguardado(self) -> dict:
        """{proyecto_id: fecha} de todos los autoguardados (para la lista de proyectos)."""
        with self._con() as con:
            return {int(f["proyecto_id"]): f["fecha"] for f in con.execute("SELECT proyecto_id, fecha FROM proyectos_usuario_autoguardado")}

    def ultimo_autoguardado(self, usuario: str | None = None, equipo: str | None = None) -> dict | None:
        """La última partida: el autoguardado más reciente con su proyecto ({proyecto_id, nombre, persona, fecha, usuario, equipo}).
        usuario (acceso controlado) deja solo los del proyecto de ese usuario; equipo, solo los de ese computador. None no filtra."""
        with self._con() as con:
            filas = [dict(f) for f in con.execute(
                "SELECT a.proyecto_id, p.nombre, p.persona, p.usuario AS dueno, a.fecha, a.usuario, a.equipo "
                "FROM proyectos_usuario_autoguardado a JOIN proyectos_usuario p ON p.id = a.proyecto_id "
                "ORDER BY a.fecha DESC, a.proyecto_id DESC")]
        if usuario is not None:
            u = limpiar_nombre(usuario).casefold()
            filas = [f for f in filas if limpiar_nombre(f["dueno"]).casefold() == u and limpiar_nombre(f["usuario"]).casefold() == u]
        if equipo is not None:
            e = limpiar_nombre(equipo).casefold()
            filas = [f for f in filas if limpiar_nombre(f["equipo"]).casefold() == e]
        return filas[0] if filas else None

    def cargar_autoguardado(self, proyecto_id: int, resolver: bool = True) -> dict:
        """{proyecto, version, planta, estado, resumen, fecha, autoguardado=True} de la ranura de autoguardado. version es la
        última versión numerada del proyecto (0 si no tiene)."""
        p = self.obtener_proyecto_usuario(proyecto_id)
        if p is None:
            raise KeyError(f"No existe el proyecto {proyecto_id}")
        with self._con() as con:
            f = con.execute("SELECT fecha, planta_json, estado_json, resumen_json FROM proyectos_usuario_autoguardado WHERE proyecto_id = ?",
                            (int(proyecto_id),)).fetchone()
            v = con.execute("SELECT COALESCE(MAX(numero), 0) FROM proyectos_usuario_versiones WHERE proyecto_id = ?",
                            (int(proyecto_id),)).fetchone()[0]
        if f is None:
            raise KeyError(f"El proyecto «{p['nombre']}» no tiene guardado automático")
        pl = planta_completa_desde_dict(json.loads(f["planta_json"]), resolver=resolver)
        return dict(proyecto=p, version=int(v), planta=pl, estado=json.loads(f["estado_json"] or "{}"),
                    resumen=json.loads(f["resumen_json"] or "{}"), fecha=f["fecha"], autoguardado=True,
                    igual_a_version=self.autoguardado_igual_a_version(proyecto_id))

    def autoguardado_igual_a_version(self, proyecto_id: int) -> bool:
        """True si el autoguardado del proyecto tiene la misma planta y el mismo estado (sin la fecha) que su última versión
        numerada: pasa justo después de «Guardar proyecto»."""
        with self._con() as con:
            a = con.execute("SELECT planta_json, estado_json FROM proyectos_usuario_autoguardado WHERE proyecto_id = ?",
                            (int(proyecto_id),)).fetchone()
            v = con.execute("SELECT planta_json, estado_json FROM proyectos_usuario_versiones WHERE proyecto_id = ? "
                            "ORDER BY numero DESC LIMIT 1", (int(proyecto_id),)).fetchone()
        if a is None or v is None or a["planta_json"] != v["planta_json"]:
            return False
        ea, ev = json.loads(a["estado_json"] or "{}"), json.loads(v["estado_json"] or "{}")
        ea.pop("_meta", None); ev.pop("_meta", None)
        return ea == ev

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
        """Deja listos los proyectos (Agrozzi y los escenarios de pellet, chip, leña y agar), las fuentes y el catálogo de parámetros (idempotente)."""
        from ..escenarios import agrozzi
        from ..motor.resumen import resumen_planta
        out = {}
        if CSV_FUENTES.exists():
            out["fuentes"] = self.cargar_fuentes_csv()
        out["parametros"] = self.sembrar_catalogo()
        if self.obtener_proyecto(NOMBRE_AGROZZI) is None:
            pid = self.crear_proyecto(NOMBRE_AGROZZI, "tomate",
                                      "Línea de pasta de tomate de la planta basada en Agrozzi (Empresas Carozzi S.A., Teno), "
                                      "como en Modelo_PAT_Agrozzi_v2.xlsx.")
            pl = agrozzi.crear()
            v = self.guardar_version(pid, pl, "Línea base de la planta basada en Agrozzi (Modelo_PAT_Agrozzi_v2.xlsx, parámetros del 26-10-2026)")
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
        # PAT 143 b: fuentes y escenario base del agar agar
        if CSV_FUENTES_AGAR.exists():
            out["fuentes_agar"] = self.cargar_fuentes_csv(CSV_FUENTES_AGAR)
        from ..escenarios import agar
        if self.obtener_proyecto(agar.NOMBRE) is None:
            pid = self.crear_proyecto(agar.NOMBRE, "agar", (agar.__doc__ or "").strip().split("\n")[0])
            pl = agar.crear()
            v = self.guardar_version(pid, pl, "Escenario base del agar agar (parámetros con fuente, 20-11-2026)")
            self.guardar_corrida(v["id"], resumen_planta(pl))
            out["proyecto_agar"] = pid
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
