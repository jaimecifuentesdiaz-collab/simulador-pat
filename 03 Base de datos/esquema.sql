-- Esquema de simulador_pat.db (fase 4, 29-10-2026). Generado desde pat_sim/datos/bd.py

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
    gas_cascada_mmbtu REAL,
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
