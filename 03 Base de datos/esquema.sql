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

-- PAT 136 (T20, 13-11-2026): esquema relacional único. Se agregan, sin cambiar lo anterior, las tablas que la aplicación ya
-- crea al abrir la base (modo curso de bd.py y mantenedor de datos/mantenedor.py) y las tablas genéricas de datos/genericos.py.

-- Modo curso (PAT 133, pat_sim/datos/bd.py, ESQUEMA_CURSO)
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

-- Mantenedor (PAT 135, pat_sim/datos/mantenedor.py, ESQUEMA_MANTENEDOR)
CREATE TABLE IF NOT EXISTS simbolos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    norma TEXT NOT NULL,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT '',
    letra TEXT NOT NULL DEFAULT '',
    svg TEXT NOT NULL DEFAULT '',
    parametros_json TEXT NOT NULL DEFAULT '{}',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    UNIQUE (norma, codigo)
);
CREATE TABLE IF NOT EXISTS catalogo_equipos (
    tipo TEXT PRIMARY KEY,
    rubro TEXT NOT NULL DEFAULT 'general',
    rubros_json TEXT NOT NULL DEFAULT '[]',
    nombre TEXT NOT NULL DEFAULT '',
    simbolo TEXT NOT NULL DEFAULT '',
    iso_categoria INTEGER,
    iso_letra TEXT NOT NULL DEFAULT '',
    parametros_json TEXT NOT NULL DEFAULT '[]',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS parametros (
    clave TEXT PRIMARY KEY,
    nombre TEXT NOT NULL DEFAULT '',
    valor REAL,
    unidad TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS desafios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL UNIQUE,
    enunciado TEXT NOT NULL DEFAULT '',
    producto TEXT NOT NULL DEFAULT '',
    rubro TEXT NOT NULL DEFAULT 'general',
    demanda_json TEXT NOT NULL DEFAULT '{}',
    precios_json TEXT NOT NULL DEFAULT '[]',
    autor TEXT NOT NULL DEFAULT '',
    fecha TEXT NOT NULL,
    activo INTEGER NOT NULL DEFAULT 1,
    modificado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS usuarios_rol (
    usuario TEXT PRIMARY KEY,
    rol TEXT NOT NULL DEFAULT 'estudiante',
    clave_hash TEXT NOT NULL DEFAULT '',
    creado TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS estados_material (
    rubro TEXT NOT NULL,
    orden REAL NOT NULL DEFAULT 0,
    codigo TEXT NOT NULL,
    nombre TEXT NOT NULL DEFAULT '',
    etapa TEXT NOT NULL DEFAULT '',
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    PRIMARY KEY (rubro, codigo)
);
CREATE TABLE IF NOT EXISTS precedencia (
    rubro TEXT NOT NULL,
    tipo TEXT NOT NULL,
    acepta TEXT NOT NULL DEFAULT '',
    entrega TEXT NOT NULL DEFAULT '',
    opcional INTEGER NOT NULL DEFAULT 0,
    fuente TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    PRIMARY KEY (rubro, tipo)
);
CREATE TABLE IF NOT EXISTS catalogo_comercial (
    tipo TEXT NOT NULL,
    modelo TEXT NOT NULL,
    magnitud TEXT NOT NULL DEFAULT '',
    capacidad REAL NOT NULL,
    unidad TEXT NOT NULL DEFAULT '',
    fuente_capacidad TEXT NOT NULL DEFAULT '',
    mtbf_h REAL,
    mttr_h REAL,
    fuente_confiabilidad TEXT NOT NULL DEFAULT '',
    precio_usd REAL,
    anio_precio INTEGER,
    fuente_precio TEXT NOT NULL DEFAULT '',
    largo_m REAL,
    ancho_m REAL,
    alto_m REAL,
    fuente_dimensiones TEXT NOT NULL DEFAULT '',
    categoria TEXT NOT NULL DEFAULT 'Supuesto',
    url TEXT NOT NULL DEFAULT '',
    modificado TEXT NOT NULL,
    PRIMARY KEY (tipo, modelo)
);
CREATE INDEX IF NOT EXISTS ix_simbolos_norma ON simbolos (norma, codigo);
CREATE INDEX IF NOT EXISTS ix_desafios_activo ON desafios (activo, titulo);

-- Base genérica para la herramienta docente (PAT 136, T20, pat_sim/datos/genericos.py, ESQUEMA_GENERICOS): 10 tipos de planta con sus
-- operaciones unitarias, equipos genéricos, modelos comerciales con historial de precios (fichas de T23), 10 tipos de demanda,
-- compatibilidad planta × demanda, usuarios (clave PBKDF2-HMAC-SHA256 con sal), cursos y asignaciones
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
-- PAT 139 (13-11-2026): asignación del desafío de tomate (tipo de planta de tomate × distribución de la llegada)
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
-- PAT 139 (14-11-2026, comentarios del profesor Torres): la combinación del desafío de tomate pasa a ser modelo de planta (10, por
-- °Brix y proceso) × distribución de la llegada (10) × tamaño (chica, mediana y grande) = 300. asignaciones.variante_tomate guarda el
-- modelo y asignaciones.tamano_tomate el tamaño (vacío en una asignación hecha con una de las 10 ids viejas de variantes_tomate, que
-- sigue mostrándose con compatibilidad_tomate). Las bases anteriores reciben la columna con ALTER TABLE al abrirse.
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

-- Proyectos del usuario (PAT 138, 13-11-2026, pat_sim/datos/bd.py, ESQUEMA_PROYECTOS_USUARIO): cada proyecto se llama
-- «Proyecto de <persona> <n>» (o el nombre que se escriba, sin repetir), sin límite de cantidad. La fila guarda la última versión
-- (planta, estado de la sesión y cifras clave) y proyectos_usuario_versiones el historial de cada «Guardar». Se crean solas al
-- abrir una base anterior.
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

-- PAT 140 g (17-11-2026): guardado automático de la partida (una fila por proyecto; la crea bd.py sola)
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
