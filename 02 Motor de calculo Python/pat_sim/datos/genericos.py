"""Base de datos genérica para la herramienta docente (PAT 136, tarea T20; puntos 2, 3 y 13 de los comentarios del profesor Torres
del 13-11-2026).

Agrega a la misma SQLite de BaseDatos (sin editar bd.py) las tablas del esquema relacional único:

- tipos_planta y operaciones_tipo: los 10 tipos de planta de catalogos/plantas_genericas.py con su cadena de operaciones
  unitarias (función de proceso, familia ISO 10628 con su letra del Anexo D, estados del material de entrada y salida).
- equipos: el tipo genérico de cada equipo (catalogos/registro.TIPOS) con su familia ISO.
- modelos_comerciales: fichas de máquinas reales (fabricante, modelo, capacidad, precio con moneda, fecha y URL, MTBF, MTTR,
  potencia, dimensiones, peso, material, garantía y plazo de entrega), listas para las fichas de Tavily de la tarea T23. Se
  siembra con los tamaños Supuesto del catalogo_comercial del mantenedor (PAT 135, T14).
- precios: historial de precios de cada modelo comercial.
- tipos_demanda y compatibilidad: los 10 tipos de demanda del equipo T21 (motor/demanda.py, solo como texto) y la matriz
  planta × demanda con su nivel (2 natural, 1 adaptable, 0 sin sentido).
- usuarios (rol docente o estudiante, clave con PBKDF2-HMAC-SHA256 y sal, nunca en claro), cursos y asignaciones
  (usuario × planta × demanda × curso, con fecha).

Compatibilidad con lo que ya existe: el rol «profesor» del mantenedor (usuarios_rol) y la clave única del profesor
(PROFESOR_CLAVE_SHA256, datos/mantenedor.verificar_profesor) siguen valiendo: el profesor entra como docente. Las tablas
curso, estudiantes y entregas del modo curso (PAT 133) no se tocan; la tabla nueva se llama «cursos» (plural).

PAT 139 (13-11-2026): el docente también asigna el desafío de tomate (pantalla Desafío, PAT 138): uno de los 10 tipos de planta de
pasta de tomate (catalogos/plantas_tomate.py) × una de las 10 distribuciones de la llegada de tomate (motor/demanda.DISTRIBUCIONES).
Tablas nuevas variantes_tomate, distribuciones_llegada y compatibilidad_tomate (100 combinaciones, todas naturales: la llegada de
tomate es empujada por la cosecha) y columnas variante_tomate y distribucion_tomate en asignaciones. Una asignación de tomate
guarda planta_id «tomate» (el tipo genérico de la planta basada en Agrozzi) y la demanda por defecto de ese tipo, así las tablas
genéricas (10 plantas, 10 demandas, 100 combinaciones) no cambian. Las bases que ya existen se migran solas (ALTER TABLE).

PAT 139 (14-11-2026, comentarios del profesor Torres): la combinación del desafío de tomate pasa a ser modelo de planta (10, por
°Brix y proceso) × distribución de la llegada (10) × tamaño (chica, mediana y grande), 300 combinaciones (catalogos/plantas_tomate.py:
MODELOS y TAMANOS). Tablas nuevas modelos_tomate, tamanos_tomate y compatibilidad_modelo_tomate (300 filas, todas naturales) y columna
tamano_tomate en asignaciones; variante_tomate guarda ahora el modelo. Las tablas variantes_tomate y compatibilidad_tomate (10 ×
10 de PAT 139 de ayer) se conservan: una asignación guardada con una de las 10 ids viejas (tamano_tomate vacío) sigue mostrándose con
su planta y su nivel de antes. Las combinaciones de tomate se escriben como par (planta, distribución) con la planta en la id
compuesta «modelo|tamano» (PT.id_compuesta); asignar y asignar_al_azar también reciben un modelo solo con tamano_id (por omisión,
el mediano). Las bases anteriores se migran solas (ALTER TABLE y siembra).

PAT 144 a (20-11-2026): tercera familia, «agar»: el desafío de agar agar de la pantalla Desafío (catalogos/plantas_agar.py: 10
modelos de proceso × 3 tamaños × las 10 distribuciones de la llegada de alga seca, 300 combinaciones). Sin tablas ni columnas
nuevas (la base no cambia): la asignación guarda planta_id «agar» (el tipo genérico de plantas_genericas.py), su demanda por defecto
(mercado_agar) y, en las mismas columnas del desafío de tomate, el modelo (variante_tomate), la distribución (distribucion_tomate)
y el tamaño (tamano_tomate). Lo que distingue la familia es planta_id. Las 300 combinaciones son naturales (Supuesto, como en el
tomate: la llegada de alga seca es empujada por la oferta) y se calculan aquí, sin tabla que el docente pueda editar.
"""
from __future__ import annotations
import csv, hashlib, hmac, io, os, random, re, sqlite3
from datetime import datetime

from .bd import BaseDatos, a_json
from ..catalogos import plantas_genericas as PG

ROLES = ("docente", "estudiante")
FAMILIAS = {"tomate": "Planta de tomate × distribución de la llegada (Desafío)", "generica": "Planta genérica × demanda (10 rubros)",
            "agar": "Planta de agar agar × distribución de la llegada (Desafío)"}          # PAT 144 a
PLANTA_TOMATE = "tomate"          # tipo genérico de catalogos/plantas_genericas.py que agrupa las 10 variantes de tomate
PLANTA_AGAR = "agar"              # PAT 144 a: tipo genérico que agrupa las 30 plantas de agar de catalogos/plantas_agar.py
JUSTIFICACION_AGAR = ("Natural (Supuesto del equipo PAT 144 a, como en el tomate): la planta de agar procesa el alga seca que le "
                      "entregan los proveedores y toda distribución de la llegada describe una forma posible de esas entregas")
ALIAS_ROL = {"profesor": "docente", "docente": "docente", "estudiante": "estudiante", "alumno": "estudiante"}
ITERACIONES = 120_000          # PAT 136: PBKDF2-HMAC-SHA256; OWASP recomienda 600.000, se baja para que la carga de un curso sea rápida
TABLAS = ("tipos_planta", "operaciones_tipo", "equipos", "modelos_comerciales", "precios", "tipos_demanda", "compatibilidad",
          "usuarios", "cursos", "asignaciones", "variantes_tomate", "distribuciones_llegada", "compatibilidad_tomate",
          "modelos_tomate", "tamanos_tomate", "compatibilidad_modelo_tomate")

ESQUEMA_GENERICOS = """
CREATE TABLE IF NOT EXISTS tipos_planta (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    producto TEXT NOT NULL DEFAULT '',
    materia_prima TEXT NOT NULL DEFAULT '',
    unidad TEXT NOT NULL DEFAULT '',
    region TEXT NOT NULL DEFAULT '',
    rubro TEXT NOT NULL DEFAULT '',
    escenario TEXT,
    demanda_defecto TEXT,
    produccion_valor REAL,
    produccion_unidad TEXT NOT NULL DEFAULT '',
    produccion_fuente TEXT NOT NULL DEFAULT '',
    servicios_json TEXT NOT NULL DEFAULT '{}',
    referencias_json TEXT NOT NULL DEFAULT '[]',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS equipos (
    tipo TEXT PRIMARY KEY,
    nombre TEXT NOT NULL DEFAULT '',
    rubro TEXT NOT NULL DEFAULT 'general',
    simbolo TEXT NOT NULL DEFAULT '',
    familia INTEGER,
    familia_nombre TEXT NOT NULL DEFAULT '',
    letra TEXT NOT NULL DEFAULT '',
    funciones TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS operaciones_tipo (
    planta_id TEXT NOT NULL REFERENCES tipos_planta(id) ON DELETE CASCADE,
    orden INTEGER NOT NULL,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL,
    funcion TEXT NOT NULL,
    tipo_equipo TEXT NOT NULL REFERENCES equipos(tipo),
    simbolo TEXT NOT NULL DEFAULT '',
    familia INTEGER,
    familia_nombre TEXT NOT NULL DEFAULT '',
    letra TEXT NOT NULL DEFAULT '',
    estado_entrada TEXT NOT NULL DEFAULT '',
    estado_salida TEXT NOT NULL DEFAULT '',
    opcional INTEGER NOT NULL DEFAULT 0,
    rama TEXT NOT NULL DEFAULT '',
    servicios TEXT NOT NULL DEFAULT '',
    alternativas TEXT NOT NULL DEFAULT '',
    nota TEXT NOT NULL DEFAULT '',
    PRIMARY KEY (planta_id, orden),
    UNIQUE (planta_id, codigo)
);
CREATE TABLE IF NOT EXISTS modelos_comerciales (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo_equipo TEXT NOT NULL REFERENCES equipos(tipo),
    fabricante TEXT NOT NULL DEFAULT '',
    modelo TEXT NOT NULL,
    capacidad REAL,
    unidad_capacidad TEXT NOT NULL DEFAULT '',
    precio REAL,
    moneda TEXT NOT NULL DEFAULT 'US$',
    fecha_precio TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    mtbf_h REAL,
    mttr_h REAL,
    disponibilidad REAL,
    potencia_kw REAL,
    largo_m REAL,
    ancho_m REAL,
    alto_m REAL,
    peso_kg REAL,
    material TEXT NOT NULL DEFAULT '',
    garantia_meses REAL,
    plazo_entrega_semanas REAL,
    categoria TEXT NOT NULL DEFAULT 'Supuesto',
    fuente TEXT NOT NULL DEFAULT '',
    nota TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    UNIQUE (tipo_equipo, fabricante, modelo)
);
CREATE TABLE IF NOT EXISTS precios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    modelo_id INTEGER NOT NULL REFERENCES modelos_comerciales(id) ON DELETE CASCADE,
    precio REAL NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'US$',
    fecha TEXT NOT NULL,
    url TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    nota TEXT NOT NULL DEFAULT '',
    registrado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tipos_demanda (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    logica TEXT NOT NULL CHECK (logica IN ('agricola', 'mercado', 'mixta')),
    descripcion TEXT NOT NULL DEFAULT '',
    modulo TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compatibilidad (
    planta_id TEXT NOT NULL REFERENCES tipos_planta(id) ON DELETE CASCADE,
    demanda_id TEXT NOT NULL REFERENCES tipos_demanda(id) ON DELETE CASCADE,
    nivel INTEGER NOT NULL DEFAULT 0 CHECK (nivel IN (0, 1, 2)),
    justificacion TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    PRIMARY KEY (planta_id, demanda_id)
);
CREATE TABLE IF NOT EXISTS cursos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre TEXT NOT NULL UNIQUE,
    periodo TEXT NOT NULL DEFAULT '',
    docente_id INTEGER REFERENCES usuarios(id) ON DELETE SET NULL,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nombre_usuario TEXT NOT NULL UNIQUE,
    nombre TEXT NOT NULL DEFAULT '',
    rol TEXT NOT NULL DEFAULT 'estudiante' CHECK (rol IN ('docente', 'estudiante')),
    curso_id INTEGER REFERENCES cursos(id) ON DELETE SET NULL,
    clave_hash TEXT NOT NULL DEFAULT '',
    activo INTEGER NOT NULL DEFAULT 1,
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS asignaciones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    curso_id INTEGER NOT NULL REFERENCES cursos(id) ON DELETE CASCADE,
    usuario_id INTEGER NOT NULL REFERENCES usuarios(id) ON DELETE CASCADE,
    planta_id TEXT NOT NULL REFERENCES tipos_planta(id),
    demanda_id TEXT NOT NULL REFERENCES tipos_demanda(id),
    modo TEXT NOT NULL DEFAULT 'azar' CHECK (modo IN ('azar', 'manual')),
    semilla INTEGER,
    asignado_por TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL,
    variante_tomate TEXT,
    distribucion_tomate TEXT,
    tamano_tomate TEXT,
    UNIQUE (curso_id, usuario_id)
);
CREATE TABLE IF NOT EXISTS variantes_tomate (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    corto TEXT NOT NULL DEFAULT '',
    temporada_t REAL NOT NULL,
    dias INTEGER NOT NULL,
    horas_dia REAL NOT NULL,
    brix REAL NOT NULL,
    quiebre TEXT NOT NULL CHECK (quiebre IN ('hot', 'cold')),
    T_quiebre REAL NOT NULL,
    evaporador TEXT NOT NULL DEFAULT '',
    descripcion TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS distribuciones_llegada (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    forma TEXT NOT NULL DEFAULT '',
    explicacion TEXT NOT NULL DEFAULT '',
    modulo TEXT NOT NULL DEFAULT 'motor/demanda.py',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compatibilidad_tomate (
    variante_id TEXT NOT NULL REFERENCES variantes_tomate(id) ON DELETE CASCADE,
    distribucion_id TEXT NOT NULL REFERENCES distribuciones_llegada(id) ON DELETE CASCADE,
    nivel INTEGER NOT NULL DEFAULT 2 CHECK (nivel IN (0, 1, 2)),
    justificacion TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    PRIMARY KEY (variante_id, distribucion_id)
);
CREATE TABLE IF NOT EXISTS modelos_tomate (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    corto TEXT NOT NULL DEFAULT '',
    brix REAL NOT NULL,
    quiebre TEXT NOT NULL CHECK (quiebre IN ('hot', 'cold')),
    T_quiebre REAL NOT NULL,
    evaporador TEXT NOT NULL DEFAULT '',
    tvr INTEGER NOT NULL DEFAULT 0,
    efectos INTEGER NOT NULL DEFAULT 3,
    descripcion TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS tamanos_tomate (
    id TEXT PRIMARY KEY,
    nombre TEXT NOT NULL,
    temporada_t REAL NOT NULL,
    dias INTEGER NOT NULL,
    horas_dia REAL NOT NULL,
    media_t_h REAL NOT NULL DEFAULT 0,
    descripcion TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS compatibilidad_modelo_tomate (
    modelo_id TEXT NOT NULL REFERENCES modelos_tomate(id) ON DELETE CASCADE,
    distribucion_id TEXT NOT NULL REFERENCES distribuciones_llegada(id) ON DELETE CASCADE,
    tamano_id TEXT NOT NULL REFERENCES tamanos_tomate(id) ON DELETE CASCADE,
    nivel INTEGER NOT NULL DEFAULT 2 CHECK (nivel IN (0, 1, 2)),
    justificacion TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    PRIMARY KEY (modelo_id, tamano_id, distribucion_id)
);
CREATE INDEX IF NOT EXISTS ix_operaciones_tipo_equipo ON operaciones_tipo (tipo_equipo);
CREATE INDEX IF NOT EXISTS ix_modelos_tipo ON modelos_comerciales (tipo_equipo);
CREATE INDEX IF NOT EXISTS ix_precios_modelo ON precios (modelo_id, fecha);
CREATE INDEX IF NOT EXISTS ix_usuarios_curso ON usuarios (curso_id, rol);
CREATE INDEX IF NOT EXISTS ix_asignaciones_curso ON asignaciones (curso_id, planta_id, demanda_id);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalizar_usuario(texto: str) -> str:
    """«  Ana Pérez » → «ana.perez»: sin tildes, minúsculas y con punto entre palabras (mismo criterio de motor/curso.normalizar)."""
    import unicodedata
    t = unicodedata.normalize("NFKD", (texto or "").strip().lower())
    t = "".join(c for c in t if not unicodedata.combining(c))
    t = re.sub(r"\s+", ".", t)
    return re.sub(r"[^a-z0-9._@-]", "", t).strip(".")


# ================================================================== claves (PBKDF2-HMAC-SHA256 con sal)
def hash_clave(clave: str, sal: str | None = None, iteraciones: int = ITERACIONES) -> str:
    """«pbkdf2_sha256$iteraciones$sal$hash». La clave nunca se guarda en claro."""
    if not clave:
        raise ValueError("La clave no puede quedar vacía")
    sal = sal or os.urandom(16).hex()
    h = hashlib.pbkdf2_hmac("sha256", clave.encode("utf-8"), bytes.fromhex(sal), int(iteraciones)).hex()
    return f"pbkdf2_sha256${int(iteraciones)}${sal}${h}"


def verificar_clave(clave: str, guardado: str) -> bool:
    """Compara en tiempo constante. Acepta también el formato «sha256$sal$hash» de motor/curso.py (usuarios_rol, PAT 133 y 135)."""
    if not clave or not guardado:
        return False
    partes = guardado.split("$")
    if partes[0] == "pbkdf2_sha256" and len(partes) == 4:
        try:
            return hmac.compare_digest(hash_clave(clave, partes[2], int(partes[1])), guardado)
        except (ValueError, TypeError):
            return False
    if partes[0] == "sha256":
        from ..motor.curso import verificar_clave as v_antigua
        return v_antigua(clave, guardado)
    return False


# ================================================================== acceso a las tablas
class BaseGenericos:
    """Tablas genéricas sobre la misma SQLite (y la misma conexión) de una instancia de BaseDatos."""

    def __init__(self, bd: BaseDatos | str | os.PathLike | None = None, sembrar: bool = True):
        self.bd = bd if isinstance(bd, BaseDatos) else BaseDatos(bd)
        self.ruta = self.bd.ruta
        with self.bd._con() as con:
            con.executescript(ESQUEMA_GENERICOS)
            cols = {f[1] for f in con.execute("PRAGMA table_info(asignaciones)")}
            for c in ("variante_tomate", "distribucion_tomate", "tamano_tomate"):    # PAT 139: bases anteriores a la asignación de tomate y al tamaño
                if c not in cols:
                    con.execute(f"ALTER TABLE asignaciones ADD COLUMN {c} TEXT")
            vacio = con.execute("SELECT COUNT(*) FROM tipos_planta").fetchone()[0] == 0
            sin_tomate = con.execute("SELECT COUNT(*) FROM compatibilidad_tomate").fetchone()[0] == 0
            sin_modelos = con.execute("SELECT COUNT(*) FROM compatibilidad_modelo_tomate").fetchone()[0] == 0
        if sembrar and vacio:
            self.sembrar()
        elif sembrar and (sin_tomate or sin_modelos):
            self.sembrar_tomate()
            self.sembrar_modelos_tomate()

    def _con(self):
        return self.bd._con()

    def contar(self) -> dict:
        with self._con() as con:
            return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLAS}

    # ------------------------------------------------------------------ siembra de los catálogos
    def sembrar(self) -> dict:
        """Copia a la base las 10 plantas, sus operaciones, los equipos, las 10 demandas, la compatibilidad y los modelos
        comerciales Supuesto. Idempotente: INSERT OR IGNORE, nunca pisa lo que el docente editó. Devuelve las filas agregadas."""
        out = {t: 0 for t in ("tipos_planta", "equipos", "operaciones_tipo", "tipos_demanda", "compatibilidad", "modelos_comerciales")}
        ahora = _ahora()
        funciones: dict[str, set] = {}
        for p in PG.PLANTAS.values():
            for o in p["operaciones"]:
                funciones.setdefault(o["tipo_equipo"], set()).add(o["funcion"])
        with self._con() as con:
            for fila in _semilla_equipos():
                fila["funciones"] = ", ".join(sorted(funciones.get(fila["tipo"], ())))
                out["equipos"] += con.execute(
                    "INSERT OR IGNORE INTO equipos (tipo, nombre, rubro, simbolo, familia, familia_nombre, letra, funciones, fuente, modificado) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (fila["tipo"], fila["nombre"], fila["rubro"], fila["simbolo"], fila["familia"], fila["familia_nombre"], fila["letra"],
                     fila["funciones"], fila["fuente"], ahora)).rowcount
            for p in PG.PLANTAS.values():
                pr = p["produccion"]
                out["tipos_planta"] += con.execute(
                    "INSERT OR IGNORE INTO tipos_planta (id, nombre, producto, materia_prima, unidad, region, rubro, escenario, demanda_defecto, "
                    "produccion_valor, produccion_unidad, produccion_fuente, servicios_json, referencias_json, modificado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (p["id"], p["nombre"], p["producto"], p["materia_prima"], p["unidad"], p["region"], p["rubro"],
                     p.get("escenario_funcion"), p["demanda_defecto"], pr["valor"], pr["unidad"], pr["fuente"], a_json(p["servicios"]),
                     a_json(p["referencias_texto"]), ahora)).rowcount
                for o in p["operaciones"]:
                    out["operaciones_tipo"] += con.execute(
                        "INSERT OR IGNORE INTO operaciones_tipo (planta_id, orden, codigo, nombre, funcion, tipo_equipo, simbolo, familia, "
                        "familia_nombre, letra, estado_entrada, estado_salida, opcional, rama, servicios, alternativas, nota) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (p["id"], o["orden"], o["codigo"], o["nombre"], o["funcion"], o["tipo_equipo"], o["simbolo"], o["familia"],
                         o["familia_nombre"], o["letra"], ", ".join(o["entrada"]), o["salida"], int(o["opcional"]), o["rama"],
                         ", ".join(o["servicios"]), ", ".join(o["alternativas"]), o["nota"])).rowcount
            for d in PG.DEMANDAS.values():
                out["tipos_demanda"] += con.execute(
                    "INSERT OR IGNORE INTO tipos_demanda (id, nombre, logica, descripcion, modulo, fuente, modificado) VALUES (?,?,?,?,?,?,?)",
                    (d["id"], d["nombre"], d["logica"], d["descripcion"], d["modulo"], d["fuente"], ahora)).rowcount
            for f in PG.matriz_compatibilidad():
                out["compatibilidad"] += con.execute(
                    "INSERT OR IGNORE INTO compatibilidad (planta_id, demanda_id, nivel, justificacion, fuente, modificado) VALUES (?,?,?,?,?,?)",
                    (f["planta_id"], f["demanda_id"], f["nivel"], f["justificacion"], f["fuente"], ahora)).rowcount
        out["modelos_comerciales"] = self._sembrar_modelos()
        out.update(self.sembrar_tomate())
        out.update(self.sembrar_modelos_tomate())
        return out

    def sembrar_tomate(self) -> dict:
        """PAT 139: copia a la base los 10 tipos de planta de tomate, las 10 distribuciones de la llegada y sus 100 combinaciones
        (nivel 2, natural). Idempotente (INSERT OR IGNORE): no pisa lo que el docente cambió."""
        from ..catalogos import plantas_tomate as PT
        from ..motor import demanda as DM
        out = {"variantes_tomate": 0, "distribuciones_llegada": 0, "compatibilidad_tomate": 0}
        ahora = _ahora()
        just = ("Natural: la demanda de una planta de tomate es empujada por la cosecha y toda distribución de la llegada describe "
                "una forma posible de esa cosecha en la temporada (Supuesto del equipo PAT 139; el docente puede cambiar el nivel)")
        with self._con() as con:
            for v in PT.VARIANTES.values():
                out["variantes_tomate"] += con.execute(
                    "INSERT OR IGNORE INTO variantes_tomate (id, nombre, corto, temporada_t, dias, horas_dia, brix, quiebre, T_quiebre, "
                    "evaporador, descripcion, fuente, modificado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (v["id"], v["nombre"], v["corto"], v["temporada_t"], v["dias"], v["horas_dia"], v["brix"], v["quiebre"], v["T_quiebre"],
                     v["evaporador"], v["descripcion"], PT.fuentes(v["id"]).get("temporada_t", ""), ahora)).rowcount
            for k, d in DM.DISTRIBUCIONES.items():
                fuentes = sorted({p["fuente"] for p in d["parametros"].values()})
                out["distribuciones_llegada"] += con.execute(
                    "INSERT OR IGNORE INTO distribuciones_llegada (id, nombre, forma, explicacion, modulo, fuente, modificado) VALUES (?,?,?,?,?,?,?)",
                    (k, d["nombre"], d.get("forma", ""), d.get("explicacion", ""), "motor/demanda.py", " · ".join(fuentes), ahora)).rowcount
            for v in PT.IDS:
                for k in DM.IDS_DISTRIBUCIONES:
                    out["compatibilidad_tomate"] += con.execute(
                        "INSERT OR IGNORE INTO compatibilidad_tomate (variante_id, distribucion_id, nivel, justificacion, fuente, modificado) "
                        "VALUES (?,?,?,?,?,?)", (v, k, 2, just, "Supuesto PAT 139", ahora)).rowcount
        return out

    def sembrar_modelos_tomate(self) -> dict:
        """PAT 139 (14-11): copia a la base los 10 modelos de planta de tomate, los 3 tamaños y las 300 combinaciones modelo ×
        tamaño × distribución (nivel 2, natural). Idempotente (INSERT OR IGNORE): no pisa lo que el docente cambió."""
        from ..catalogos import plantas_tomate as PT
        from ..motor import demanda as DM
        out = {"modelos_tomate": 0, "tamanos_tomate": 0, "compatibilidad_modelo_tomate": 0}
        ahora = _ahora()
        just = ("Natural: la demanda de una planta de tomate es empujada por la cosecha y toda distribución de la llegada describe "
                "una forma posible de esa cosecha en la temporada, de cualquier tamaño y modelo (Supuesto del equipo PAT 139, 14-11; "
                "el docente puede cambiar el nivel)")
        with self._con() as con:
            for m in PT.MODELOS.values():
                f = PT.fuentes_modelo(m["id"])
                out["modelos_tomate"] += con.execute(
                    "INSERT OR IGNORE INTO modelos_tomate (id, nombre, corto, brix, quiebre, T_quiebre, evaporador, tvr, efectos, descripcion, "
                    "fuente, modificado) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    (m["id"], m["nombre"], m["corto"], m["brix"], m["quiebre"], m["T_quiebre"], m["evaporador"], int(m["tvr"]), m["N"],
                     m["descripcion"], f"°Brix: {f['brix']} | Quiebre: {f['quiebre']} | Evaporador: {f['evaporador']}", ahora)).rowcount
            for t in PT.TAMANOS.values():
                f = t["fuentes"]
                out["tamanos_tomate"] += con.execute(
                    "INSERT OR IGNORE INTO tamanos_tomate (id, nombre, temporada_t, dias, horas_dia, media_t_h, descripcion, fuente, modificado) "
                    "VALUES (?,?,?,?,?,?,?,?,?)",
                    (t["id"], t["nombre"], t["temporada_t"], t["dias"], t["horas_dia"], t["media_t_h"], t["descripcion"],
                     f"Tomate: {f['temporada_t']} | Días: {f['dias']} | Horas: {f['horas_dia']}", ahora)).rowcount
            for m in PT.IDS_MODELOS:
                for t in PT.IDS_TAMANOS:
                    for k in DM.IDS_DISTRIBUCIONES:
                        out["compatibilidad_modelo_tomate"] += con.execute(
                            "INSERT OR IGNORE INTO compatibilidad_modelo_tomate (modelo_id, distribucion_id, tamano_id, nivel, justificacion, "
                            "fuente, modificado) VALUES (?,?,?,?,?,?,?)", (m, k, t, 2, just, "Supuesto PAT 139 (14-11)", ahora)).rowcount
        return out

    def _sembrar_modelos(self) -> int:
        try:
            from .mantenedor import semilla_catalogo_comercial
            filas = semilla_catalogo_comercial()
        except Exception:                      # la semilla depende de motor/costeo.py; si falla, la tabla queda vacía para T23
            return 0
        n = 0
        for f in filas:
            n += self.guardar_modelo(dict(
                tipo_equipo=f["tipo"], fabricante="Genérico (Supuesto)", modelo=f["modelo"], capacidad=f["capacidad"],
                unidad_capacidad=f["unidad"], precio=f["precio_usd"], moneda="US$", fecha_precio=f"{f['anio_precio']}-01-01" if f.get("anio_precio") else "",
                url=f.get("url") or "", mtbf_h=f["mtbf_h"], mttr_h=f["mttr_h"], largo_m=f["largo_m"], ancho_m=f["ancho_m"], alto_m=f["alto_m"],
                categoria="Supuesto", fuente=f"Capacidad: {f['fuente_capacidad']}. Confiabilidad: {f['fuente_confiabilidad']}. Precio: {f['fuente_precio']}",
                nota="Sembrado desde catalogo_comercial del mantenedor (PAT 135, T14)"), pisar=False)["nuevo"]
        return n

    # ------------------------------------------------------------------ catálogos
    def listar_plantas(self) -> list[dict]:
        with self._con() as con:
            filas = [dict(f) for f in con.execute("SELECT * FROM tipos_planta ORDER BY rowid")]
        import json
        for f in filas:
            f["servicios"] = json.loads(f.pop("servicios_json") or "{}"); f["referencias"] = json.loads(f.pop("referencias_json") or "[]")
        return filas

    def obtener_planta(self, planta_id: str) -> dict | None:
        return next((p for p in self.listar_plantas() if p["id"] == planta_id), None)

    def operaciones(self, planta_id: str) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM operaciones_tipo WHERE planta_id = ? ORDER BY orden", (planta_id,))]

    def listar_equipos(self) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM equipos ORDER BY familia, nombre")]

    def listar_demandas(self) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM tipos_demanda ORDER BY rowid")]

    def compatibilidad(self, planta_id: str | None = None, demanda_id: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM compatibilidad WHERE 1 = 1", []
        if planta_id:
            sql += " AND planta_id = ?"; args.append(planta_id)
        if demanda_id:
            sql += " AND demanda_id = ?"; args.append(demanda_id)
        with self._con() as con:
            return [dict(f) for f in con.execute(sql + " ORDER BY planta_id, demanda_id", args)]

    def nivel(self, planta_id: str, demanda_id: str) -> int | None:
        with self._con() as con:
            f = con.execute("SELECT nivel FROM compatibilidad WHERE planta_id = ? AND demanda_id = ?", (planta_id, demanda_id)).fetchone()
        return int(f["nivel"]) if f else None

    def fijar_compatibilidad(self, planta_id: str, demanda_id: str, nivel: int, justificacion: str) -> None:
        """El docente cambia el nivel de una combinación (con su justificación)."""
        if int(nivel) not in PG.NIVELES:
            raise ValueError("El nivel debe ser 0, 1 o 2")
        if not (justificacion or "").strip():
            raise ValueError("Escriba la justificación del nivel")
        with self._con() as con:
            con.execute("INSERT INTO compatibilidad (planta_id, demanda_id, nivel, justificacion, fuente, modificado) VALUES (?,?,?,?,?,?) "
                        "ON CONFLICT(planta_id, demanda_id) DO UPDATE SET nivel=excluded.nivel, justificacion=excluded.justificacion, "
                        "fuente=excluded.fuente, modificado=excluded.modificado",
                        (planta_id, demanda_id, int(nivel), justificacion.strip(), "Docente", _ahora()))

    def combinaciones(self, minimo_nivel: int = 1, familia: str = "generica") -> list[tuple[str, str]]:
        """Pares (planta, demanda) de la base con nivel ≥ minimo_nivel, en el orden del catálogo. Con familia «tomate» (PAT 139),
        pares (planta de tomate, distribución de la llegada) con la planta en la id compuesta «modelo|tamano» (PAT 139, 14-11:
        10 modelos × 3 tamaños × 10 distribuciones, 300 combinaciones)."""
        if familia == "tomate":
            return [(f["compuesta"], f["distribucion_id"]) for f in self.compatibilidad_tomate() if f["nivel"] >= minimo_nivel]
        if familia == "agar":                                              # PAT 144 a
            return [(f["compuesta"], f["distribucion_id"]) for f in self.compatibilidad_agar() if f["nivel"] >= minimo_nivel]
        orden_p = {p: i for i, p in enumerate(PG.IDS_PLANTAS)}; orden_d = {d: i for i, d in enumerate(PG.IDS_DEMANDAS)}
        filas = [f for f in self.compatibilidad() if f["nivel"] >= minimo_nivel]
        filas.sort(key=lambda f: (orden_p.get(f["planta_id"], 99), f["planta_id"], orden_d.get(f["demanda_id"], 99), f["demanda_id"]))
        return [(f["planta_id"], f["demanda_id"]) for f in filas]

    # ------------------------------------------------------------------ tomate: modelo × tamaño × distribución de la llegada (PAT 139)
    def compatibilidad_tomate(self, variante_id: str | None = None, distribucion_id: str | None = None,
                              tamano_id: str | None = None) -> list[dict]:
        """Filas de compatibilidad del desafío de tomate, con las claves variante_id (el modelo), tamano_id, distribucion_id,
        compuesta («modelo|tamano»), nivel y justificacion. variante_id puede ser un modelo, una id compuesta o una de las 10 ids
        viejas de PAT 139 (solo estas últimas leen la tabla compatibilidad_tomate de 10 × 10, con tamano_id None). Sin filtros, las
        300 filas modelo × tamaño × distribución."""
        from ..catalogos import plantas_tomate as PT
        from ..motor import demanda as DM
        if variante_id and PT.es_solo_legada(variante_id) and tamano_id is None:
            sql, args = "SELECT * FROM compatibilidad_tomate WHERE variante_id = ?", [variante_id]
            if distribucion_id:
                sql += " AND distribucion_id = ?"; args.append(distribucion_id)
            with self._con() as con:
                filas = [dict(f, tamano_id=None, compuesta=f["variante_id"]) for f in con.execute(sql, args)]
            od = {d: i for i, d in enumerate(DM.IDS_DISTRIBUCIONES)}
            return sorted(filas, key=lambda f: od.get(f["distribucion_id"], 99))
        sql, args = "SELECT * FROM compatibilidad_modelo_tomate WHERE 1 = 1", []
        if variante_id:
            if PT.SEP in variante_id:
                variante_id, t = variante_id.split(PT.SEP, 1)
                tamano_id = tamano_id or t
            sql += " AND modelo_id = ?"; args.append(variante_id)
        if tamano_id:
            sql += " AND tamano_id = ?"; args.append(tamano_id)
        if distribucion_id:
            sql += " AND distribucion_id = ?"; args.append(distribucion_id)
        with self._con() as con:
            filas = [dict(f) for f in con.execute(sql, args)]
        for f in filas:
            f["variante_id"] = f["modelo_id"]; f["compuesta"] = f"{f['modelo_id']}{PT.SEP}{f['tamano_id']}"
        om = {v: i for i, v in enumerate(PT.IDS_MODELOS)}; ot = {t: i for i, t in enumerate(PT.IDS_TAMANOS)}
        od = {d: i for i, d in enumerate(DM.IDS_DISTRIBUCIONES)}
        filas.sort(key=lambda f: (om.get(f["modelo_id"], 99), f["modelo_id"], ot.get(f["tamano_id"], 99), f["tamano_id"],
                                  od.get(f["distribucion_id"], 99), f["distribucion_id"]))
        return filas

    # ------------------------------------------------------------------ agar: modelo × tamaño × distribución de la llegada (PAT 144 a)
    def compatibilidad_agar(self, variante_id: str | None = None, distribucion_id: str | None = None,
                            tamano_id: str | None = None) -> list[dict]:
        """Filas de compatibilidad del desafío de agar (calculadas, no hay tabla): variante_id (el modelo), tamano_id, distribucion_id,
        compuesta, nivel (2, natural) y justificacion. variante_id puede ser un modelo o una id compuesta «modelo|tamano»."""
        from ..catalogos import plantas_agar as PA
        from ..motor import demanda as DM
        if variante_id and PA.SEP in variante_id:
            variante_id, t = variante_id.split(PA.SEP, 1)
            tamano_id = tamano_id or t
        return [dict(variante_id=m, modelo_id=m, tamano_id=t, distribucion_id=d, compuesta=PA.id_compuesta(m, t), nivel=2,
                     justificacion=JUSTIFICACION_AGAR, fuente="Supuesto PAT 144 a")
                for m in PA.IDS_MODELOS if variante_id in (None, m) for t in PA.IDS_TAMANOS if tamano_id in (None, t)
                for d in DM.IDS_DISTRIBUCIONES if distribucion_id in (None, d)]

    def nivel_agar(self, variante_id: str, distribucion_id: str, tamano_id: str | None = None) -> int | None:
        k = self.compatibilidad_agar(variante_id, distribucion_id, tamano_id)
        return int(k[0]["nivel"]) if k else None

    def nivel_tomate(self, variante_id: str, distribucion_id: str, tamano_id: str | None = None) -> int | None:
        """Nivel de la combinación. variante_id: un modelo (con tamano_id; sin él, el mediano), una id compuesta «modelo|tamano» o
        una de las 10 ids viejas de PAT 139 (tabla compatibilidad_tomate)."""
        k = self.compatibilidad_tomate(*_clave_tomate(variante_id, distribucion_id, tamano_id))
        return int(k[0]["nivel"]) if k else None

    def fijar_compatibilidad_tomate(self, variante_id: str, distribucion_id: str, nivel: int, justificacion: str,
                                    tamano_id: str | None = None) -> None:
        """El docente cambia el nivel de una combinación (con su justificación). variante_id como en nivel_tomate: un modelo solo
        cambia su tamaño mediano; con tamano_id, ese tamaño."""
        from ..catalogos import plantas_tomate as PT
        if int(nivel) not in PG.NIVELES:
            raise ValueError("El nivel debe ser 0, 1 o 2")
        if not (justificacion or "").strip():
            raise ValueError("Escriba la justificación del nivel")
        _validar_tomate(variante_id, distribucion_id, tamano_id)
        v, d, t = _clave_tomate(variante_id, distribucion_id, tamano_id)
        with self._con() as con:
            if t is None:                                         # una de las 10 ids viejas de PAT 139
                con.execute("INSERT INTO compatibilidad_tomate (variante_id, distribucion_id, nivel, justificacion, fuente, modificado) "
                            "VALUES (?,?,?,?,?,?) ON CONFLICT(variante_id, distribucion_id) DO UPDATE SET nivel=excluded.nivel, "
                            "justificacion=excluded.justificacion, fuente=excluded.fuente, modificado=excluded.modificado",
                            (v, d, int(nivel), justificacion.strip(), "Docente", _ahora()))
            else:
                con.execute("INSERT INTO compatibilidad_modelo_tomate (modelo_id, distribucion_id, tamano_id, nivel, justificacion, fuente, "
                            "modificado) VALUES (?,?,?,?,?,?,?) ON CONFLICT(modelo_id, tamano_id, distribucion_id) DO UPDATE SET "
                            "nivel=excluded.nivel, justificacion=excluded.justificacion, fuente=excluded.fuente, "
                            "modificado=excluded.modificado", (v, d, t, int(nivel), justificacion.strip(), "Docente", _ahora()))

    # ------------------------------------------------------------------ modelos comerciales y precios (para T23)
    COLUMNAS_MODELO = ("tipo_equipo", "fabricante", "modelo", "capacidad", "unidad_capacidad", "precio", "moneda", "fecha_precio", "url",
                       "mtbf_h", "mttr_h", "disponibilidad", "potencia_kw", "largo_m", "ancho_m", "alto_m", "peso_kg", "material",
                       "garantia_meses", "plazo_entrega_semanas", "categoria", "fuente", "nota")

    def guardar_modelo(self, ficha: dict, pisar: bool = True) -> dict:
        """Guarda la ficha de un modelo comercial (por ejemplo, la que arma T23 con Tavily). Si trae precio, queda también en el
        historial de precios. Devuelve {id, nuevo}. El tipo de equipo debe existir en la tabla equipos (se crea si falta)."""
        f = {k: ficha.get(k) for k in self.COLUMNAS_MODELO}
        if not f["tipo_equipo"] or not (f["modelo"] or "").strip():
            raise ValueError("La ficha necesita tipo de equipo y modelo")
        for k in ("fabricante", "unidad_capacidad", "fecha_precio", "url", "material", "fuente", "nota"):
            f[k] = (f[k] or "").strip() if isinstance(f[k], str) or f[k] is None else str(f[k])
        f["moneda"] = f["moneda"] or "US$"; f["categoria"] = f["categoria"] or "Supuesto"
        if f["precio"] is not None and not f["fecha_precio"]:
            raise ValueError("El precio necesita su fecha")
        ahora = _ahora()
        with self._con() as con:
            con.execute("INSERT OR IGNORE INTO equipos (tipo, nombre, fuente, modificado) VALUES (?,?,?,?)",
                        (f["tipo_equipo"], f["tipo_equipo"], "Creado al guardar un modelo comercial", ahora))
            previo = con.execute("SELECT id FROM modelos_comerciales WHERE tipo_equipo = ? AND fabricante = ? AND modelo = ?",
                                 (f["tipo_equipo"], f["fabricante"], f["modelo"])).fetchone()
            if previo is not None and not pisar:
                return dict(id=int(previo["id"]), nuevo=0)
            cols = ", ".join(self.COLUMNAS_MODELO)
            marcas = ", ".join("?" for _ in self.COLUMNAS_MODELO)
            act = ", ".join(f"{k}=excluded.{k}" for k in self.COLUMNAS_MODELO if k not in ("tipo_equipo", "fabricante", "modelo"))
            con.execute(f"INSERT INTO modelos_comerciales ({cols}, modificado) VALUES ({marcas}, ?) "
                        f"ON CONFLICT(tipo_equipo, fabricante, modelo) DO UPDATE SET {act}, modificado=excluded.modificado",
                        tuple(f[k] for k in self.COLUMNAS_MODELO) + (ahora,))
            mid = int(con.execute("SELECT id FROM modelos_comerciales WHERE tipo_equipo = ? AND fabricante = ? AND modelo = ?",
                                  (f["tipo_equipo"], f["fabricante"], f["modelo"])).fetchone()["id"])
            if f["precio"] is not None:
                ya = con.execute("SELECT 1 FROM precios WHERE modelo_id = ? AND precio = ? AND moneda = ? AND fecha = ?",
                                 (mid, float(f["precio"]), f["moneda"], f["fecha_precio"])).fetchone()
                if ya is None:
                    con.execute("INSERT INTO precios (modelo_id, precio, moneda, fecha, url, fuente, nota, registrado) VALUES (?,?,?,?,?,?,?,?)",
                                (mid, float(f["precio"]), f["moneda"], f["fecha_precio"], f["url"], f["fuente"], f["nota"], ahora))
        return dict(id=mid, nuevo=int(previo is None))

    def registrar_precio(self, modelo_id: int, precio: float, moneda: str, fecha: str, url: str = "", fuente: str = "", nota: str = "") -> None:
        """Agrega un precio al historial y lo deja como precio vigente del modelo si es el más reciente."""
        if not fecha:
            raise ValueError("El precio necesita su fecha")
        with self._con() as con:
            m = con.execute("SELECT fecha_precio FROM modelos_comerciales WHERE id = ?", (int(modelo_id),)).fetchone()
            if m is None:
                raise KeyError(f"No existe el modelo {modelo_id}")
            con.execute("INSERT INTO precios (modelo_id, precio, moneda, fecha, url, fuente, nota, registrado) VALUES (?,?,?,?,?,?,?,?)",
                        (int(modelo_id), float(precio), moneda, fecha, url, fuente, nota, _ahora()))
            if fecha >= (m["fecha_precio"] or ""):
                con.execute("UPDATE modelos_comerciales SET precio = ?, moneda = ?, fecha_precio = ?, url = CASE WHEN ? = '' THEN url ELSE ? END, "
                            "modificado = ? WHERE id = ?", (float(precio), moneda, fecha, url, url, _ahora(), int(modelo_id)))

    def listar_modelos(self, tipo_equipo: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM modelos_comerciales", ()
        if tipo_equipo:
            sql += " WHERE tipo_equipo = ?"; args = (tipo_equipo,)
        with self._con() as con:
            return [dict(f) for f in con.execute(sql + " ORDER BY tipo_equipo, capacidad, modelo", args)]

    def historial_precios(self, modelo_id: int) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM precios WHERE modelo_id = ? ORDER BY fecha, id", (int(modelo_id),))]

    # ------------------------------------------------------------------ usuarios
    def crear_usuario(self, nombre_usuario: str, nombre: str = "", rol: str = "estudiante", clave: str | None = None,
                      curso: int | str | None = None) -> int:
        """Crea el usuario o actualiza su nombre, rol, curso y clave (si vienen). «profesor» se guarda como «docente»."""
        u = normalizar_usuario(nombre_usuario)
        if not u:
            raise ValueError("El usuario necesita un nombre de usuario")
        r = ALIAS_ROL.get((rol or "").strip().lower())
        if r is None:
            raise ValueError(f"Rol desconocido: {rol}. Use docente o estudiante")
        cid = self._curso_id(curso) if curso is not None else None
        h = hash_clave(clave) if clave else ""
        with self._con() as con:
            con.execute("INSERT OR IGNORE INTO usuarios (nombre_usuario, nombre, rol, curso_id, clave_hash, creado) VALUES (?,?,?,?,?,?)",
                        (u, (nombre or "").strip(), r, cid, h, _ahora()))
            con.execute("UPDATE usuarios SET rol = ?, nombre = CASE WHEN ? = '' THEN nombre ELSE ? END, "
                        "curso_id = COALESCE(?, curso_id), clave_hash = CASE WHEN ? = '' THEN clave_hash ELSE ? END WHERE nombre_usuario = ?",
                        (r, (nombre or "").strip(), (nombre or "").strip(), cid, h, h, u))
            return int(con.execute("SELECT id FROM usuarios WHERE nombre_usuario = ?", (u,)).fetchone()["id"])

    def obtener_usuario(self, ref: int | str) -> dict | None:
        with self._con() as con:
            if isinstance(ref, int):
                f = con.execute("SELECT * FROM usuarios WHERE id = ?", (ref,)).fetchone()
            else:
                f = con.execute("SELECT * FROM usuarios WHERE nombre_usuario = ?", (normalizar_usuario(ref),)).fetchone()
        return dict(f) if f else None

    def fijar_clave(self, usuario: int | str, clave: str) -> None:
        u = self.obtener_usuario(usuario)
        if u is None:
            raise KeyError(f"No existe el usuario «{usuario}»")
        with self._con() as con:
            con.execute("UPDATE usuarios SET clave_hash = ? WHERE id = ?", (hash_clave(clave), u["id"]))

    def autenticar(self, usuario: str, clave: str) -> dict | None:
        """Usuario (sin el hash) si la clave coincide; None si no existe, está inactivo o la clave no coincide."""
        u = self.obtener_usuario(usuario or "")
        if u is None or not u["activo"] or not verificar_clave(clave, u["clave_hash"]):
            return None
        u.pop("clave_hash", None)
        return u

    def es_docente(self, usuario: str, clave: str, secretos=None, entorno=None) -> bool:
        """Docente con usuario y clave propios, o (compatibilidad PAT 135) la clave única del profesor del mantenedor, o un
        usuario «profesor» de la tabla usuarios_rol del mantenedor."""
        u = self.autenticar(usuario, clave) if usuario else None
        if u is not None and u["rol"] == "docente":
            return True
        from . import mantenedor as M
        esperado, _origen = M.hash_esperado(secretos, entorno)
        if M.verificar_profesor(clave, esperado):
            return True
        if usuario:
            try:
                return M.mantenedor(self.bd).rol_de(usuario, clave) == "profesor"
            except sqlite3.Error:
                return False
        return False

    def importar_usuarios_rol(self) -> int:
        """Copia los usuarios de la tabla usuarios_rol del mantenedor (profesor → docente) con su hash, sin pisar los que ya están."""
        from . import mantenedor as M
        n = 0
        for f in M.mantenedor(self.bd).listar_usuarios():
            with self._con() as con:
                h = con.execute("SELECT clave_hash FROM usuarios_rol WHERE usuario = ?", (f["usuario"],)).fetchone()["clave_hash"]
                n += con.execute("INSERT OR IGNORE INTO usuarios (nombre_usuario, nombre, rol, clave_hash, creado) VALUES (?,?,?,?,?)",
                                 (normalizar_usuario(f["usuario"]), "", ALIAS_ROL.get(f["rol"], "estudiante"), h, _ahora())).rowcount
        return n

    def listar_usuarios(self, curso: int | str | None = None, rol: str | None = None) -> list[dict]:
        sql, args = "SELECT id, nombre_usuario, nombre, rol, curso_id, activo, creado, clave_hash != '' AS con_clave FROM usuarios WHERE 1 = 1", []
        if curso is not None:
            sql += " AND curso_id = ?"; args.append(self._curso_id(curso))
        if rol:
            sql += " AND rol = ?"; args.append(ALIAS_ROL.get(rol, rol))
        with self._con() as con:
            return [dict(f) for f in con.execute(sql + " ORDER BY nombre_usuario", args)]

    # ------------------------------------------------------------------ cursos
    def crear_curso(self, nombre: str, docente: int | str | None = None, periodo: str = "") -> int:
        nombre = (nombre or "").strip()
        if not nombre:
            raise ValueError("El curso necesita un nombre")
        did = None
        if docente is not None:
            d = self.obtener_usuario(docente)
            if d is None:
                raise KeyError(f"No existe el docente «{docente}»")
            did = d["id"]
        with self._con() as con:
            con.execute("INSERT OR IGNORE INTO cursos (nombre, periodo, docente_id, creado) VALUES (?,?,?,?)", (nombre, periodo, did, _ahora()))
            if did is not None or periodo:
                con.execute("UPDATE cursos SET docente_id = COALESCE(?, docente_id), periodo = CASE WHEN ? = '' THEN periodo ELSE ? END "
                            "WHERE nombre = ?", (did, periodo, periodo, nombre))
            return int(con.execute("SELECT id FROM cursos WHERE nombre = ?", (nombre,)).fetchone()["id"])

    def obtener_curso(self, ref: int | str) -> dict | None:
        with self._con() as con:
            col = "id" if isinstance(ref, int) else "nombre"
            f = con.execute(f"SELECT * FROM cursos WHERE {col} = ?", (ref if isinstance(ref, int) else str(ref).strip(),)).fetchone()
        return dict(f) if f else None

    def listar_cursos(self) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute(
                "SELECT c.*, (SELECT COUNT(*) FROM usuarios u WHERE u.curso_id = c.id AND u.rol = 'estudiante') AS n_estudiantes, "
                "(SELECT COUNT(*) FROM asignaciones a WHERE a.curso_id = c.id) AS n_asignaciones FROM cursos c ORDER BY c.nombre")]

    def _curso_id(self, curso: int | str) -> int:
        c = self.obtener_curso(curso)
        if c is None:
            raise KeyError(f"No existe el curso «{curso}»")
        return int(c["id"])

    def cargar_estudiantes(self, curso: int | str, texto: str) -> dict:
        """Estudiantes uno por línea o en CSV (coma, punto y coma o tabulador). Columnas reconocidas por encabezado: usuario y
        nombre; sin encabezado, «usuario;nombre» o solo el nombre (el usuario sale del nombre: «Ana Pérez» → «ana.perez»).
        Devuelve {creados, existentes, errores, usuarios}."""
        cid = self._curso_id(curso)
        out = dict(creados=0, existentes=0, errores=[], usuarios=[])
        lineas = [l for l in (texto or "").replace("﻿", "").splitlines() if l.strip()]
        if not lineas:
            return out
        sep = max((";", ",", "\t"), key=lambda s: lineas[0].count(s))
        filas = list(csv.reader(io.StringIO("\n".join(lineas)), delimiter=sep)) if lineas[0].count(sep) else [[l] for l in lineas]
        enc = [normalizar_usuario(c) for c in filas[0]]
        iu = next((i for i, c in enumerate(enc) if c in ("usuario", "nombre.de.usuario", "nombre_usuario", "identificador", "correo", "rut")), None)
        inn = next((i for i, c in enumerate(enc) if c in ("nombre", "nombre.completo", "estudiante", "alumno")), None)
        if iu is not None or inn is not None:
            filas = filas[1:]
        for n, f in enumerate(filas, start=1):
            f = [c.strip() for c in f]
            if not any(f):
                continue
            if iu is not None or inn is not None:
                usuario = f[iu] if iu is not None and iu < len(f) else ""
                nombre = f[inn] if inn is not None and inn < len(f) else ""
            elif len(f) >= 2:
                usuario, nombre = f[0], f[1]
            else:
                usuario, nombre = ("", f[0]) if " " in f[0] else (f[0], "")
            usuario = usuario or nombre
            if not normalizar_usuario(usuario):
                out["errores"].append(f"Línea {n}: falta el usuario o el nombre"); continue
            ya = self.obtener_usuario(usuario)
            if ya is not None and ya["rol"] == "docente":
                out["errores"].append(f"Línea {n}: «{ya['nombre_usuario']}» es docente y no se inscribe como estudiante"); continue
            uid = self.crear_usuario(usuario, nombre, "estudiante", curso=cid)
            out["existentes" if ya else "creados"] += 1
            out["usuarios"].append(self.obtener_usuario(uid)["nombre_usuario"])
        return out

    # ------------------------------------------------------------------ asignaciones
    def _estudiantes(self, cid: int) -> list[dict]:
        return [u for u in self.listar_usuarios(cid, "estudiante") if u["activo"]]

    def asignar_al_azar(self, curso: int | str, semilla: int | None = None, minimo_nivel: int = 1,
                        conservar_manuales: bool = True, asignado_por: str = "", familia: str = "generica") -> dict:
        """Reparte a cada estudiante del curso una combinación planta × demanda compatible (nivel ≥ minimo_nivel) distinta.

        Las combinaciones se barajan con random.Random(semilla) y se intercalan por planta, así los primeros estudiantes
        reciben plantas distintas. Si hay más estudiantes que combinaciones, se vuelve a recorrer la lista barajada: cada
        combinación se repite a lo más una vez más que las demás (repetición mínima) y se avisa. Las asignaciones manuales se
        conservan (y sus combinaciones salen del reparto) salvo conservar_manuales=False. Misma semilla y mismos estudiantes,
        mismo reparto. Sin semilla, se sortea una y queda guardada para repetirlo. PAT 139: familia «tomate» reparte modelo de
        planta de tomate × distribución de la llegada × tamaño (las 300 combinaciones de compatibilidad_modelo_tomate, PAT 139 del
        14-11); la ronda intercala los modelos, así los primeros 10 estudiantes reciben 10 modelos distintos."""
        if familia not in FAMILIAS:
            raise ValueError(f"Familia desconocida: {familia!r}. Use una de: {', '.join(FAMILIAS)}")
        cid = self._curso_id(curso)
        if semilla is None:
            semilla = int.from_bytes(os.urandom(4), "big")
        semilla = int(semilla)
        avisos: list[str] = []
        estudiantes = self._estudiantes(cid)
        if not estudiantes:
            return dict(asignaciones=[], avisos=["El curso no tiene estudiantes: cárguelos antes de repartir."], semilla=semilla,
                        combinaciones=0, estudiantes=0, repetidas=0)
        actuales = {a["usuario_id"]: a for a in self.asignaciones(cid)}
        fijos = {uid: a for uid, a in actuales.items() if conservar_manuales and a["modo"] == "manual"}
        usadas = {_combo(a)[1:] for a in fijos.values() if _combo(a)[0] == familia}
        todas = self.combinaciones(minimo_nivel, familia)
        if not todas:
            return dict(asignaciones=[], avisos=["No hay combinaciones compatibles con ese nivel."], semilla=semilla, combinaciones=0,
                        estudiantes=len(estudiantes), repetidas=0)
        libres = [c for c in todas if c not in usadas]
        rng = random.Random(semilla)
        orden = _intercalar(libres or todas, rng, (lambda c: c[0].split("|")[0]) if familia in ("tomate", "agar") else None)
        por_repartir = [u for u in estudiantes if u["id"] not in fijos]
        repetidas = 0
        if len(por_repartir) > len(orden):
            repetidas = len(por_repartir) - len(orden)
            avisos.append(f"Hay {len(por_repartir)} estudiantes por repartir y {len(orden)} combinaciones libres compatibles: "
                          f"{repetidas} combinaciones se repiten (cada una a lo más {-(-len(por_repartir) // len(orden))} veces).")
        if not libres and por_repartir:
            avisos.append("Las asignaciones manuales ocupan todas las combinaciones compatibles: el reparto vuelve a usarlas.")
        ahora = _ahora()
        with self._con() as con:
            for i, u in enumerate(por_repartir):
                p, d = orden[i % len(orden)]
                planta, demanda, vt, dt, tt = _columnas(familia, p, d)
                con.execute("INSERT INTO asignaciones (curso_id, usuario_id, planta_id, demanda_id, modo, semilla, asignado_por, fecha, "
                            "variante_tomate, distribucion_tomate, tamano_tomate) VALUES (?,?,?,?,?,?,?,?,?,?,?) "
                            "ON CONFLICT(curso_id, usuario_id) DO UPDATE SET "
                            "planta_id=excluded.planta_id, demanda_id=excluded.demanda_id, modo=excluded.modo, semilla=excluded.semilla, "
                            "asignado_por=excluded.asignado_por, fecha=excluded.fecha, variante_tomate=excluded.variante_tomate, "
                            "distribucion_tomate=excluded.distribucion_tomate, tamano_tomate=excluded.tamano_tomate",
                            (cid, u["id"], planta, demanda, "azar", semilla, asignado_por, ahora, vt, dt, tt))
        return dict(asignaciones=self.asignaciones(cid), avisos=avisos, semilla=semilla, combinaciones=len(todas),
                    estudiantes=len(estudiantes), repetidas=repetidas)

    def asignar(self, curso: int | str, usuario: int | str, planta_id: str, demanda_id: str, forzar: bool = False,
                asignado_por: str = "", familia: str = "generica", tamano_id: str | None = None) -> dict:
        """Asignación manual. Exige una combinación compatible (nivel ≥ 1) salvo forzar=True. Avisa si otro estudiante del
        curso ya tiene la misma combinación (no lo impide). Devuelve {asignacion, avisos}. PAT 139: con familia «tomate»,
        planta_id es el modelo de planta de tomate (o la id compuesta «modelo|tamano», o una de las 10 ids viejas de PAT 139),
        tamano_id el tamaño (por omisión, el mediano) y demanda_id la distribución de la llegada."""
        cid = self._curso_id(curso)
        u = self.obtener_usuario(usuario)
        if u is None:
            raise KeyError(f"No existe el usuario «{usuario}»")
        if familia == "tomate":
            _validar_tomate(planta_id, demanda_id, tamano_id)
            planta_id = _compuesta_tomate(planta_id, tamano_id)
            n = self.nivel_tomate(planta_id, demanda_id)
        elif familia == "agar":                                            # PAT 144 a
            planta_id = _compuesta_agar(planta_id, demanda_id, tamano_id)
            n = self.nivel_agar(planta_id, demanda_id)
        else:
            PG.planta(planta_id); PG.demanda(demanda_id)
            n = self.nivel(planta_id, demanda_id)
        avisos = []
        if not n:
            if not forzar:
                raise ValueError(f"La combinación {planta_id} × {demanda_id} no tiene sentido según la base "
                                 "(nivel 0). Use forzar=True si el docente la quiere igual.")
            avisos.append("Combinación forzada por el docente: la base la marca sin sentido.")
        combo = (familia if familia in ("tomate", "agar") else "generica", planta_id, demanda_id)
        otros = [a["nombre_usuario"] for a in self.asignaciones(cid) if _combo(a) == combo and a["usuario_id"] != u["id"]]
        planta, demanda, vt, dt, tt = _columnas(familia, planta_id, demanda_id)
        if otros:
            avisos.append("La misma combinación ya la tiene: " + ", ".join(otros) + ".")
        with self._con() as con:
            if u["curso_id"] is None:
                con.execute("UPDATE usuarios SET curso_id = ? WHERE id = ?", (cid, u["id"]))
            con.execute("INSERT INTO asignaciones (curso_id, usuario_id, planta_id, demanda_id, modo, semilla, asignado_por, fecha, "
                        "variante_tomate, distribucion_tomate, tamano_tomate) VALUES (?,?,?,?,?,NULL,?,?,?,?,?) "
                        "ON CONFLICT(curso_id, usuario_id) DO UPDATE SET "
                        "planta_id=excluded.planta_id, demanda_id=excluded.demanda_id, modo=excluded.modo, semilla=NULL, "
                        "asignado_por=excluded.asignado_por, fecha=excluded.fecha, variante_tomate=excluded.variante_tomate, "
                        "distribucion_tomate=excluded.distribucion_tomate, tamano_tomate=excluded.tamano_tomate",
                        (cid, u["id"], planta, demanda, "manual", asignado_por, _ahora(), vt, dt, tt))
        return dict(asignacion=self.asignacion_de(u["id"], cid), avisos=avisos)

    def asignaciones(self, curso: int | str) -> list[dict]:
        """Tabla de asignaciones del curso con los nombres de la planta y de la demanda."""
        cid = self._curso_id(curso)
        with self._con() as con:
            filas = [dict(f) for f in con.execute(
                "SELECT a.*, u.nombre_usuario, u.nombre, p.nombre AS planta, d.nombre AS demanda, d.logica, "
                "COALESCE(k.nivel, 0) AS nivel FROM asignaciones a JOIN usuarios u ON u.id = a.usuario_id "
                "JOIN tipos_planta p ON p.id = a.planta_id JOIN tipos_demanda d ON d.id = a.demanda_id "
                "LEFT JOIN compatibilidad k ON k.planta_id = a.planta_id AND k.demanda_id = a.demanda_id "
                "WHERE a.curso_id = ? ORDER BY u.nombre_usuario", (cid,))]
        return [self._enriquecer(a) for a in filas]

    def _enriquecer(self, a: dict) -> dict:
        """PAT 139: familia, nombres y nivel de una asignación de tomate (modelo de planta, tamaño y distribución de la llegada).
        PAT 139 (14-11): variante_tomate es el modelo y tamano_tomate el tamaño; una asignación vieja (una de las 10 ids de PAT 139
        de ayer, sin tamaño) sigue mostrando su planta y su nivel de antes. Agrega modelo_tomate, tamano_tomate y variante_compuesta.
        PAT 144 a: con planta_id «agar», la asignación es del desafío de agar (familia «agar», modelo_agar, tamano_agar,
        distribucion_agar y variante_agar)."""
        if a.get("variante_tomate") and a.get("planta_id") == PLANTA_AGAR:
            from ..catalogos import plantas_agar as PA
            from ..motor import demanda as DM
            d = a.get("distribucion_tomate")
            a["familia"] = "agar"
            try:
                c = PA.id_compuesta(a["variante_tomate"], a.get("tamano_tomate"))
                a["planta"] = PA.variante(c)["nombre"]
            except KeyError:
                c = a["variante_tomate"]; a["planta"] = c
            a["variante_compuesta"] = a["variante_agar"] = c
            a["modelo_agar"] = a["variante_tomate"]; a["tamano_agar"] = a.get("tamano_tomate"); a["distribucion_agar"] = d
            a["demanda"] = DM.nombre_distribucion(d, "agar") if d in DM.DISTRIBUCIONES else (d or "")
            a["logica"] = "agricola"
            a["nivel"] = self.nivel_agar(c, d) or 0
        elif a.get("variante_tomate"):
            from ..catalogos import plantas_tomate as PT
            from ..motor import demanda as DM
            v, d = a["variante_tomate"], a.get("distribucion_tomate")
            c = _compuesta_de(v, a.get("tamano_tomate"))
            a["familia"] = "tomate"
            try:
                var = PT.variante(c)
                a["planta"] = var["nombre"]; a["modelo_tomate"] = var["modelo"]; a["tamano_tomate"] = None if var["legada"] else var["tamano"]
            except KeyError:
                a["planta"] = v; a["modelo_tomate"] = v
            a["variante_compuesta"] = c
            a["demanda"] = DM.DISTRIBUCIONES[d]["nombre"] if d in DM.DISTRIBUCIONES else (d or "")
            a["logica"] = "agricola"
            a["nivel"] = self.nivel_tomate(c, d) or 0
        else:
            a["familia"] = "generica"
        return a

    def asignacion_de(self, usuario: int | str, curso: int | str | None = None) -> dict | None:
        """Asignación del usuario (en el curso indicado o, si no se indica, la más reciente) con el detalle de la planta y de la
        demanda del catálogo. None si no tiene."""
        u = self.obtener_usuario(usuario)
        if u is None:
            return None
        sql = ("SELECT a.*, c.nombre AS curso, p.nombre AS planta, d.nombre AS demanda, d.logica FROM asignaciones a "
               "JOIN cursos c ON c.id = a.curso_id JOIN tipos_planta p ON p.id = a.planta_id JOIN tipos_demanda d ON d.id = a.demanda_id "
               "WHERE a.usuario_id = ?")
        args: list = [u["id"]]
        if curso is not None:
            sql += " AND a.curso_id = ?"; args.append(self._curso_id(curso))
        with self._con() as con:
            f = con.execute(sql + " ORDER BY a.fecha DESC, a.id DESC LIMIT 1", args).fetchone()
        if f is None:
            return None
        a = dict(f)
        a["nombre_usuario"] = u["nombre_usuario"]; a["nombre"] = u["nombre"]
        if a.get("variante_tomate") and a.get("planta_id") == PLANTA_AGAR:     # PAT 144 a: desafío de agar asignado por el docente
            from ..catalogos import plantas_agar as PA
            from ..motor import demanda as DM
            self._enriquecer(a)
            try:
                a["detalle_planta"] = PA.variante(a["variante_compuesta"])
            except KeyError:
                a["detalle_planta"] = None
            a["detalle_demanda"] = DM.DISTRIBUCIONES.get(a["distribucion_agar"])
            a["justificacion"] = JUSTIFICACION_AGAR
            return a
        if a.get("variante_tomate"):                       # PAT 139: desafío de tomate asignado por el docente
            from ..catalogos import plantas_tomate as PT
            from ..motor import demanda as DM
            self._enriquecer(a)
            c = a["variante_compuesta"]
            a["detalle_planta"] = PT.VARIANTES.get(c); a["detalle_demanda"] = DM.DISTRIBUCIONES.get(a["distribucion_tomate"])
            k = self.compatibilidad_tomate(*_clave_tomate(c, a["distribucion_tomate"], None))
            a["justificacion"] = k[0]["justificacion"] if k else ""
            return a
        a["familia"] = "generica"
        a["detalle_planta"] = PG.PLANTAS.get(a["planta_id"]); a["detalle_demanda"] = PG.DEMANDAS.get(a["demanda_id"])
        n, j = (self.nivel(a["planta_id"], a["demanda_id"]) or 0), ""
        k = self.compatibilidad(a["planta_id"], a["demanda_id"])
        a["nivel"] = n; a["justificacion"] = k[0]["justificacion"] if k else j
        return a

    def quitar_asignacion(self, curso: int | str, usuario: int | str) -> None:
        cid = self._curso_id(curso); u = self.obtener_usuario(usuario)
        if u is not None:
            with self._con() as con:
                con.execute("DELETE FROM asignaciones WHERE curso_id = ? AND usuario_id = ?", (cid, u["id"]))


# ================================================================== funciones de apoyo
def _validar_tomate(variante_id: str, distribucion_id: str, tamano_id: str | None = None) -> None:
    """KeyError si no existe el modelo (o la id compuesta o vieja), el tamaño o la distribución."""
    from ..catalogos import plantas_tomate as PT
    from ..motor import demanda as DM
    if variante_id not in PT.VARIANTES:
        raise KeyError(f"No existe el tipo de planta de tomate «{variante_id}»")
    if tamano_id is not None and tamano_id not in PT.TAMANOS:
        raise KeyError(f"No existe el tamaño de planta de tomate «{tamano_id}»")
    if distribucion_id not in DM.DISTRIBUCIONES:
        raise KeyError(f"No existe la distribución de la llegada «{distribucion_id}»")


def _compuesta_de(variante_id: str, tamano_id: str | None) -> str:
    """Id de la planta de una asignación: «modelo|tamano»; sin tamaño, una de las 10 ids viejas queda como está y un modelo solo
    (también «agrozzi», que es los dos) toma el tamaño mediano."""
    from ..catalogos import plantas_tomate as PT
    if tamano_id:
        return f"{variante_id}{PT.SEP}{tamano_id}"
    if PT.es_solo_legada(variante_id) or PT.SEP in variante_id:
        return variante_id
    return PT.id_compuesta(variante_id, None)


def _compuesta_tomate(variante_id: str, tamano_id: str | None) -> str:
    """Como _compuesta_de, pero con tamano_id explícito sobre una id compuesta o vieja lo traduce (modelo del dato + tamaño dado)."""
    from ..catalogos import plantas_tomate as PT
    if tamano_id is None:
        return _compuesta_de(variante_id, None)
    return PT.id_compuesta(PT.separar_id(variante_id)[0], tamano_id)


def _clave_tomate(variante_id: str, distribucion_id: str, tamano_id: str | None) -> tuple:
    """(variante_id, distribucion_id, tamano_id) que lee la tabla correcta: con una id vieja de PAT 139 de ayer (sin tamaño), la
    de 10 × 10; con un modelo solo, su tamaño mediano; con una id compuesta, su modelo y su tamaño."""
    from ..catalogos import plantas_tomate as PT
    if tamano_id is None and PT.es_solo_legada(variante_id):
        return variante_id, distribucion_id, None
    m, t = PT.separar_id(variante_id, tamano_id)
    return m, distribucion_id, t


def _compuesta_agar(variante_id: str, distribucion_id: str, tamano_id: str | None) -> str:
    """PAT 144 a: id compuesta «modelo|tamano» de la planta de agar (un modelo solo toma tamano_id o el mediano). KeyError si no
    existe el modelo, el tamaño o la distribución."""
    from ..catalogos import plantas_agar as PA
    from ..motor import demanda as DM
    if not PA.es_variante(variante_id):
        raise KeyError(f"No existe el modelo de planta de agar «{variante_id}»")
    if tamano_id is not None and tamano_id not in PA.TAMANOS:
        raise KeyError(f"No existe el tamaño de planta de agar «{tamano_id}»")
    if distribucion_id not in DM.DISTRIBUCIONES:
        raise KeyError(f"No existe la distribución de la llegada «{distribucion_id}»")
    m, t = PA.separar_id(variante_id)
    return PA.id_compuesta(m, tamano_id or t)


def _columnas(familia: str, p: str, d: str) -> tuple:
    """(planta_id, demanda_id, variante_tomate, distribucion_tomate, tamano_tomate) que se guardan en asignaciones. En el tomate,
    p es la id compuesta «modelo|tamano» (variante_tomate guarda el modelo) o una de las 10 ids viejas (sin tamaño)."""
    if familia == "tomate":
        from ..catalogos import plantas_tomate as PT
        base = PG.PLANTAS[PLANTA_TOMATE]["demanda_defecto"]
        if PT.es_solo_legada(p):
            return PLANTA_TOMATE, base, p, d, None
        m, t = PT.separar_id(p)
        return PLANTA_TOMATE, base, m, d, t
    if familia == "agar":                                                  # PAT 144 a: mismas columnas, planta_id «agar»
        from ..catalogos import plantas_agar as PA
        m, t = PA.separar_id(p)
        return PLANTA_AGAR, PG.PLANTAS[PLANTA_AGAR]["demanda_defecto"], m, d, t
    return p, d, None, None, None


def combinacion(a: dict) -> tuple:
    """Combinación de una asignación, para no repetir: (familia, planta o «modelo|tamano» del tomate, demanda o distribución)."""
    if a.get("variante_tomate") and a.get("planta_id") == PLANTA_AGAR:      # PAT 144 a
        from ..catalogos import plantas_agar as PA
        try:
            c = PA.id_compuesta(a["variante_tomate"], a.get("tamano_tomate"))
        except KeyError:
            c = a["variante_tomate"]
        return ("agar", c, a.get("distribucion_tomate"))
    if a.get("variante_tomate"):
        return ("tomate", _compuesta_de(a["variante_tomate"], a.get("tamano_tomate")), a.get("distribucion_tomate"))
    return ("generica", a["planta_id"], a["demanda_id"])


_combo = combinacion


def _intercalar(combos: list[tuple[str, str]], rng: random.Random, clave=None) -> list[tuple[str, str]]:
    """Baraja las combinaciones y las ordena en ronda por planta (planta A, B, C…, luego otra demanda de A, B, C…). clave: cómo
    se agrupa (por omisión, la planta; en el tomate, el modelo)."""
    clave = clave or (lambda c: c[0])
    grupos: dict[str, list] = {}
    for c in combos:
        grupos.setdefault(clave(c), []).append(c)
    plantas = sorted(grupos)
    rng.shuffle(plantas)
    for p in plantas:
        rng.shuffle(grupos[p])
    out = []
    while any(grupos[p] for p in plantas):
        for p in plantas:
            if grupos[p]:
                out.append(grupos[p].pop())
    return out


def _semilla_equipos() -> list[dict]:
    """Un tipo genérico por cada clase de catalogos/registro.TIPOS, más «generico» del catálogo comercial."""
    from ..catalogos.registro import TIPOS
    from ..simbolos import iso10628 as ISO
    out = []
    for tipo, c in TIPOS.items():
        cat = getattr(c, "iso_categoria", None)
        out.append(dict(tipo=tipo, nombre=getattr(c, "nombre_tipo", tipo), rubro=getattr(c, "rubro", "general"), simbolo=getattr(c, "simbolo", ""),
                        familia=cat, familia_nombre=ISO.CATEGORIAS.get(cat, ""), letra=getattr(c, "iso_letra", ""),
                        fuente="catalogos/registro.py; familias de UNE-EN ISO 10628:2001, Tabla C.1 y Anexo D (simbolos/iso10628.py)"))
    out.append(dict(tipo="generico", nombre="Equipo genérico", rubro="general", simbolo="equipo_general", familia=20,
                    familia_nombre=ISO.CATEGORIAS[20], letra="A", fuente="catalogo_comercial del mantenedor (PAT 135, T14)"))
    return out


_CACHE: dict = {}


def genericos(bd=None) -> BaseGenericos:
    """BaseGenericos de una BaseDatos (o de una ruta). Sin argumento, la base predeterminada (o PAT_SIM_DB). Se reutiliza."""
    if isinstance(bd, BaseGenericos):
        return bd
    if isinstance(bd, BaseDatos):
        g = _CACHE.get(id(bd))
        if g is None or g.bd is not bd:
            g = _CACHE[id(bd)] = BaseGenericos(bd)
        return g
    clave = str(bd or os.environ.get("PAT_SIM_DB") or "")
    if clave not in _CACHE:
        _CACHE[clave] = BaseGenericos(bd)
    return _CACHE[clave]


def sembrar(bd=None) -> dict:
    """Para construir_bd.py y para el inicio de la aplicación. Idempotente."""
    g = genericos(bd)
    return g.sembrar()


def esquema_sql() -> str:
    """Esquema relacional único (para 03 Base de datos/esquema.sql): bd.py, modo curso, mantenedor y tablas genéricas."""
    from .bd import ESQUEMA, ESQUEMA_CURSO, ESQUEMA_PROYECTOS_USUARIO, ESQUEMA_AUTOGUARDADO
    from .mantenedor import ESQUEMA_MANTENEDOR
    return "\n".join(s.strip() + "\n" for s in (ESQUEMA, ESQUEMA_CURSO, ESQUEMA_MANTENEDOR, ESQUEMA_GENERICOS, ESQUEMA_PROYECTOS_USUARIO, ESQUEMA_AUTOGUARDADO))
