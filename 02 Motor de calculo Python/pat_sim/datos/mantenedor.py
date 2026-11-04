"""Mantenedor de la base de datos (PAT 135, tarea T7.4): simbología, catálogo de equipos, parámetros y desafíos.

El profesor Torres pidió (reunión del 04-11-2026, indicaciones 4 y 5) «una base de datos con un mantenedor que modifica cosas
(no puede tener cosas hardcodeadas)». Este módulo agrega cinco tablas a la misma SQLite de BaseDatos, sin editar bd.py:

- simbolos: norma, código, nombre, categoría, letra, dibujo SVG y parámetros de dibujo (ISO 10628 e ISA-5.1).
- catalogo_equipos: rubro, tipo, símbolo y parámetros por defecto de cada tipo de equipo, cada uno con su fuente.
- parametros: clave, valor, unidad, fuente y fecha (CEPCI, dólar, Henry Hub, precios de energía y de biomasa).
- desafios: título, enunciado, producto, rubro, demanda por período con su unidad, precios de venta, autor, fecha y activo.
- usuarios_rol: usuarios con rol (profesor o estudiante) y clave guardada solo como hash con sal (opcional).

sembrar() copia a la base lo que hoy está escrito en catalogos/, simbolos/, motor/calculadoras.py y ui/comun.py, sin borrar
esos archivos (quedan como semilla), y crea dos desafíos de ejemplo. Es idempotente: solo agrega lo que falta y nunca pisa
lo que el profesor ya editó. obtener() lee desde la base y, si la base no responde o no tiene la fila, usa la semilla.
"""
from __future__ import annotations
import ast, hashlib, hmac, json, math, os, sqlite3
from datetime import date, datetime
from pathlib import Path

from .bd import BaseDatos, a_json

AQUI = Path(__file__).resolve().parent
# …/pat_sim/datos → …/Aplicacion simulador/04 Interfaz Streamlit/ui/comun.py (se lee como texto, sin importar Streamlit)
COMUN_UI = AQUI.parents[2] / "04 Interfaz Streamlit" / "ui" / "comun.py"

# PAT 135: clave por defecto del profesor «torres2026», guardada solo como SHA-256. Se usa cuando no hay
# PROFESOR_CLAVE_SHA256 en st.secrets ni en las variables de entorno (o está vacía). Cambiarla en secrets.toml al publicar.
HASH_CLAVE_DEFECTO = "8be258bb45e4e2ab8e9a695f0b3006c018370af62c7a41752e091ee7934b777a"
NOMBRE_SECRETO = "PROFESOR_CLAVE_SHA256"
CLAVE_GAS_CHILE = "precio_gas_industrial_chile"   # PAT 135: US$/MMBtu del gas natural industrial en Chile (sin semilla: falta fuente segura)

ROLES = ("profesor", "estudiante")
TABLAS = ("simbolos", "catalogo_equipos", "parametros", "desafios", "usuarios_rol")

ESQUEMA_MANTENEDOR = """
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
CREATE INDEX IF NOT EXISTS ix_simbolos_norma ON simbolos (norma, codigo);
CREATE INDEX IF NOT EXISTS ix_desafios_activo ON desafios (activo, titulo);
"""


def _ahora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _num(v):
    """Número finito o None (las celdas vacías del editor llegan como None, '' o NaN)."""
    if v is None or isinstance(v, bool):
        return None
    try:
        x = float(str(v).replace(",", ".")) if isinstance(v, str) else float(v)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _txt(v) -> str:
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return ""
    return str(v).strip()


# ================================================================== semilla (lo que hoy está escrito en el código)
def _constantes_comun() -> dict:
    """Constantes de ui/comun.py leídas como texto (ast), para no importar Streamlit desde el motor. {} si no está."""
    try:
        arbol = ast.parse(COMUN_UI.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return {}
    out = {}
    for n in arbol.body:
        if isinstance(n, ast.Assign) and len(n.targets) == 1 and isinstance(n.targets[0], ast.Name):
            try:
                out[n.targets[0].id] = ast.literal_eval(n.value)
            except (ValueError, SyntaxError, TypeError):
                pass
    return out


def semilla_parametros() -> list[dict]:
    """Parámetros económicos y de energía que hoy están fijos en motor/calculadoras.py y ui/comun.py, con su fuente y fecha."""
    from ..motor import calculadoras as K
    F = []
    F.append(dict(clave="cepci", nombre="Índice de costos de plantas químicas (CEPCI)", valor=K.CEPCI_ACTUAL, unidad="—",
                  categoria="Literatura", fuente=K.FUENTE_CEPCI, fecha="2024-03-25"))
    F.append(dict(clave="factor_red_sen", nombre="Factor de emisión del Sistema Eléctrico Nacional", valor=K.FACTOR_RED_SEN,
                  unidad="t CO2e/MWh", categoria="Oficial", fuente=K.FUENTE_FACTOR_RED, fecha="2024-01-11"))
    for tipo, f in K.LANG.items():
        F.append(dict(clave="lang_" + tipo.lower().replace(" y ", "_").replace(" ", "_").replace("ó", "o"),
                      nombre=f"Factor de Lang, planta de {tipo.lower()}", valor=f, unidad="—", categoria="Literatura",
                      fuente="Lang (1948), factor por tipo de planta (motor/calculadoras.py)", fecha="1948-01-01"))
    c = _constantes_comun()
    if "HENRY_HUB" in c:
        F.append(dict(clave="henry_hub", nombre="Precio del gas natural Henry Hub", valor=c["HENRY_HUB"], unidad="US$/MMBtu",
                      categoria="Oficial", fuente=c.get("FUENTE_HH", ""), fecha="2026-08-31"))
    if "DOLAR" in c:
        F.append(dict(clave="dolar", nombre="Dólar observado", valor=c["DOLAR"], unidad="$/US$", categoria="Oficial",
                      fuente=c.get("FUENTE_DOLAR", ""), fecha="2026-10-26"))
    for nombre, v in c.get("PMM", ()):
        clave = "pmm_" + nombre.lower().replace(" de ", "_").replace(" ", "_")
        F.append(dict(clave=clave, nombre=f"Precio medio de mercado de la electricidad, {nombre.lower()}", valor=v, unidad="$/kWh",
                      categoria="Oficial", fuente=c.get("FUENTE_PMM", ""), fecha="2026-08-07"))
    if "PRECIO_BIOMASA" in c:
        F.append(dict(clave="precio_biomasa", nombre="Astilla de pino con corteza puesta en planta, sin IVA", valor=c["PRECIO_BIOMASA"],
                      unidad="$/m³ estéreo", categoria="Oficial", fuente=c.get("FUENTE_BIOMASA", ""), fecha="2025-06-30"))
    # PAT 135: parámetros de evaluación que estaban fijos en ui/comun.iniciar_estado (tasa y horizonte). Son Supuesto.
    F.append(dict(clave="tasa_descuento", nombre="Tasa de descuento de la evaluación económica", valor=0.10, unidad="fracción",
                  categoria="Supuesto", fuente="Supuesto: 10 % real anual, valor de partida del simulador (ui/comun.py); el profesor lo ajusta según el proyecto",
                  fecha="2026-11-04"))
    F.append(dict(clave="anios_evaluacion", nombre="Horizonte de la evaluación económica", valor=20, unidad="años", categoria="Supuesto",
                  fuente="Supuesto: 20 años, valor de partida del simulador (ui/comun.py); el profesor lo ajusta según la vida útil del proyecto",
                  fecha="2026-11-04"))
    # No se siembra «precio_gas_industrial_chile» (US$/MMBtu): no hay un valor con fuente segura en la carpeta del proyecto.
    # Si el profesor lo agrega en el mantenedor, Economía lo usa en lugar del Henry Hub (clave en CLAVE_GAS_CHILE).
    return F


def semilla_simbolos() -> list[dict]:
    """Símbolos de equipos ISO 10628, elementos ISA-5.1 y ISA-5.4, letras código y señales, tal como están en simbolos/."""
    from ..simbolos import iso10628 as ISO, isa51 as ISA
    F = []
    f_iso = "UNE-EN ISO 10628:2001, Tabla C.1 y Anexo D (simbolos/iso10628.py)"
    for sid, (nombre, cat, letra, dib) in ISO.SIMBOLOS.items():
        F.append(dict(norma="ISO 10628", codigo=sid, nombre=nombre, categoria=f"{cat}. {ISO.CATEGORIAS.get(cat, '')}".strip(),
                      letra=letra, svg=dib, parametros=dict(caja="60 x 60", modulo="1 módulo = 5 unidades", categoria_tabla_c1=cat), fuente=f_iso))
    for k, e in ISA.ELEMENTOS.items():
        try:
            svg = ISA.simbolo_svg(e["simbolo"], e["letras"], "", 30, 30, e["ubicacion"])
        except Exception:
            svg = ""
        F.append(dict(norma="ISA-5.1", codigo=k, nombre=e["nombre"], categoria=e["grupo"], letra=e["letras"], svg=svg,
                      parametros={x: e[x] for x in ("simbolo", "ubicacion", "isa51")}, fuente=e["fuente"]))
    f_tab3 = "ISA-5.1 (Carballo y Romero, 2011, Tabla 3, p. 18)"
    for letra, sig in ISA.PRIMERA_LETRA.items():
        F.append(dict(norma="ISA-5.1 primera letra", codigo=letra, nombre=sig, categoria="Variable medida", letra=letra, svg="", parametros={}, fuente=f_tab3))
    for letra, sig in ISA.LETRAS_SUCESIVAS.items():
        F.append(dict(norma="ISA-5.1 letra sucesiva", codigo=letra, nombre=sig, categoria="Función", letra=letra, svg="", parametros={}, fuente=f_tab3))
    for letra, sig in ISA.MODIFICADORES.items():
        F.append(dict(norma="ISA-5.1 modificador", codigo=letra, nombre=sig, categoria="Modificador de la primera letra", letra=letra, svg="",
                      parametros={}, fuente=f_tab3))
    for k, (nombre, trazo, marca) in ISA.SENALES.items():
        F.append(dict(norma="ISA-5.1 señal", codigo=k, nombre=nombre, categoria="Línea de conexión", letra="", svg="",
                      parametros=dict(trazo=trazo, marca=marca), fuente="ISA-5.1 (Carballo y Romero, 2011, Tabla 15, p. 34)"))
    for letra, sig in ISO.LETRAS_EQUIPO.items():
        F.append(dict(norma="ISO 10628 letra de equipo", codigo=letra, nombre=sig, categoria="Anexo D.2", letra=letra, svg="", parametros={},
                      fuente="UNE-EN ISO 10628:2001, Anexo D.2"))
    for letra, sig in ISO.LETRAS_VALVULA.items():
        F.append(dict(norma="ISO 10628 letra de válvula", codigo=letra, nombre=sig, categoria="Anexo D.3", letra=letra, svg="", parametros={},
                      fuente="UNE-EN ISO 10628:2001, Anexo D.3"))
    return F


def semilla_catalogo() -> list[dict]:
    """Cada tipo de equipo de catalogos/ con sus parámetros por defecto (valor, unidad, categoría, fuente, justificación, rango)."""
    from ..catalogos.registro import TIPOS
    F = []
    for tipo, cls in TIPOS.items():
        mod = cls.__module__.rsplit(".", 1)[-1]
        F.append(dict(tipo=tipo, rubro=cls.rubro, rubros=list(getattr(cls, "rubros", ()) or ()), nombre=cls.nombre_tipo, simbolo=cls.simbolo,
                      iso_categoria=int(cls.iso_categoria), iso_letra=cls.iso_letra,
                      parametros=[p.a_dict() for p in cls.params_base], fuente=f"catalogos/{mod}.py (semilla del 04-11-2026)"))
    return F


# Desafío de ejemplo en blanco: secado de agar agar. Todas sus cifras son Supuesto ilustrativo (no hay fuente en la carpeta PAT).
_SUP_AGAR = ("Supuesto ilustrativo para el desafío de ejemplo: no hay dato de una planta ni fuente segura en la carpeta del "
             "proyecto. El profesor lo reemplaza en el mantenedor")
AGAR_MESES = ("Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio", "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre")
AGAR_DEMANDA_T = (42.0, 40.0, 45.0, 50.0, 55.0, 58.0, 60.0, 58.0, 54.0, 50.0, 46.0, 44.0)   # Supuesto: 602 t al año, peak en invierno


def desafio_agrozzi() -> dict:
    """Desafío de la planta basada en Agrozzi: la pasta que sale cada día de la temporada, derivada del modelo del simulador."""
    from ..escenarios import agrozzi
    from ..motor import temporada as T
    pl = agrozzi.crear(capacidades=False)
    B = agrozzi.BASE; tomate = float(B["season"]); dias = int(B["days"])
    pasta_t = pl.salidas[("A1", "producto")].m * pl.equipos["B1"].horas() / 1000.0
    llegada = T.curva_llegada(pl)
    serie = [round(x * pasta_t / tomate, 3) for x in llegada]
    sp = {s.clave: s for s in T.SUPUESTOS["tomate"]}
    fmt = lambda v, d=0: f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    enunciado = (f"diseñar la línea de pasta de tomate de una planta basada en Agrozzi (Teno) que procese la temporada de febrero a abril: "
                 f"{fmt(tomate)} t de tomate fresco en {dias} días, con pasta de {fmt(100 * B['xP'])} °Brix envasada en forma aséptica. "
                 f"La demanda de pasta sigue la llegada del tomate durante la temporada ({fmt(pasta_t)} t en total). Ponga los equipos, "
                 "revise las restricciones, decida si incorpora recuperación de calor y evalúe si conviene: si la inversión es muy alta "
                 "o la energía muy barata, quizás no se justifica el recuperador.")
    return dict(
        titulo="Planta basada en Agrozzi: pasta de tomate", producto=f"Pasta de tomate de {fmt(100 * B['xP'])} °Brix en envase aséptico",
        rubro="tomate", enunciado=enunciado, autor="Semilla del simulador (PAT 135)", activo=True,
        demanda=dict(periodo="día", unidad="t", valores=serie, etiquetas=[f"Día {i + 1}" for i in range(len(serie))],
                     fuente=("Derivado: 450.000 t de tomate en 76 días (DIA_Agrozzi_rev0.pdf, p. 47; Balance de Masa_Rev0.pdf, p. 6) por el "
                             "balance de la línea a pasta de 30 °Brix (Modelo_PAT_Agrozzi_v2.xlsx). La forma de campana de la temporada es "
                             f"Supuesto de motor/temporada.py: peak a {fmt(100 * sp['pico'].valor)} % de la temporada y ancho "
                             f"{fmt(100 * sp['ancho'].valor)} %, sin registro diario de la recepción")),
        precios=[dict(producto="Pasta de tomate 28 a 30 °Brix, tambor aséptico", precio=1000.0, moneda="US$", unidad="t",
                      fuente=("Supuesto: orden de magnitud del precio internacional de la pasta de tomate en tambor aséptico; no hay "
                              "precio de venta de Agrozzi ni fuente segura en la carpeta del proyecto. Reemplazarlo en el mantenedor"))])


def desafio_agar() -> dict:
    return dict(
        titulo="Secado de agar agar (desafío en blanco)", producto="Agar agar en polvo, grado alimentario", rubro="general",
        enunciado=("diseñar una planta de secado de agar agar a partir del gel prensado que llega de la extracción de algas rojas. "
                   "Su demanda tiene el comportamiento mensual del gráfico. Parta en blanco: elija los equipos (por ejemplo prensa, "
                   "secador, molino, tamiz y envasado), dimensione los servicios, revise las restricciones y decida si incorpora "
                   "recuperación de calor; la evaluación económica dirá si conviene."),
        autor="Semilla del simulador (PAT 135)", activo=True,
        demanda=dict(periodo="mes", unidad="t", valores=list(AGAR_DEMANDA_T), etiquetas=list(AGAR_MESES),
                     fuente="Supuesto ilustrativo: demanda mensual de ejemplo con peak en invierno; " + _SUP_AGAR),
        precios=[dict(producto="Agar agar en polvo, grado alimentario", precio=18.0, moneda="US$", unidad="kg", fuente="Supuesto: " + _SUP_AGAR),
                 dict(producto="Agar agar bacteriológico", precio=35.0, moneda="US$", unidad="kg", fuente="Supuesto: " + _SUP_AGAR)])


def semilla_desafios() -> list[dict]:
    return [desafio_agrozzi(), desafio_agar()]


# ================================================================== acceso a las tablas
class Mantenedor:
    """CRUD de las tablas del mantenedor sobre la misma SQLite (y la misma conexión) de una instancia de BaseDatos."""

    def __init__(self, bd: BaseDatos | str | os.PathLike | None = None):
        self.bd = bd if isinstance(bd, BaseDatos) else BaseDatos(bd)
        self.ruta = self.bd.ruta
        with self.bd._con() as con:
            con.executescript(ESQUEMA_MANTENEDOR)

    def _con(self):
        return self.bd._con()

    def contar(self) -> dict:
        with self._con() as con:
            return {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in TABLAS}

    # ------------------------------------------------------------------ parámetros
    def guardar_parametro(self, clave: str, valor, unidad: str = "", fuente: str = "", fecha: str = "", nombre: str = "",
                          categoria: str = "") -> None:
        clave = _txt(clave)
        if not clave:
            raise ValueError("El parámetro necesita una clave")
        x = _num(valor)
        if x is None:
            raise ValueError(f"El valor de «{clave}» debe ser un número")
        with self._con() as con:
            con.execute("INSERT INTO parametros (clave, nombre, valor, unidad, categoria, fuente, fecha, modificado) VALUES (?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(clave) DO UPDATE SET nombre=excluded.nombre, valor=excluded.valor, unidad=excluded.unidad, "
                        "categoria=excluded.categoria, fuente=excluded.fuente, fecha=excluded.fecha, modificado=excluded.modificado",
                        (clave, _txt(nombre), x, _txt(unidad), _txt(categoria), _txt(fuente), _txt(fecha) or date.today().isoformat(), _ahora()))

    def obtener_parametro(self, clave: str) -> dict | None:
        with self._con() as con:
            f = con.execute("SELECT * FROM parametros WHERE clave = ?", (clave,)).fetchone()
        return dict(f) if f else None

    def listar_parametros(self) -> list[dict]:
        with self._con() as con:
            return [dict(f) for f in con.execute("SELECT * FROM parametros ORDER BY clave")]

    def eliminar_parametro(self, clave: str) -> None:
        with self._con() as con:
            con.execute("DELETE FROM parametros WHERE clave = ?", (clave,))

    # ------------------------------------------------------------------ símbolos
    def guardar_simbolo(self, norma: str, codigo: str, nombre: str = "", categoria: str = "", letra: str = "", svg: str = "",
                        parametros: dict | None = None, fuente: str = "") -> int:
        norma, codigo = _txt(norma), _txt(codigo)
        if not norma or not codigo:
            raise ValueError("El símbolo necesita norma y código")
        if "<script" in (svg or "").lower():
            raise ValueError("El dibujo SVG no puede traer código <script>")
        with self._con() as con:
            con.execute("INSERT INTO simbolos (norma, codigo, nombre, categoria, letra, svg, parametros_json, fuente, modificado) "
                        "VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(norma, codigo) DO UPDATE SET nombre=excluded.nombre, "
                        "categoria=excluded.categoria, letra=excluded.letra, svg=excluded.svg, parametros_json=excluded.parametros_json, "
                        "fuente=excluded.fuente, modificado=excluded.modificado",
                        (norma, codigo, _txt(nombre), _txt(categoria), _txt(letra), svg or "", a_json(parametros or {}), _txt(fuente), _ahora()))
            return int(con.execute("SELECT id FROM simbolos WHERE norma = ? AND codigo = ?", (norma, codigo)).fetchone()["id"])

    @staticmethod
    def _simbolo(f) -> dict:
        d = dict(f); d["parametros"] = json.loads(d.pop("parametros_json") or "{}"); return d

    def obtener_simbolo(self, codigo: str, norma: str = "ISO 10628") -> dict | None:
        with self._con() as con:
            f = con.execute("SELECT * FROM simbolos WHERE norma = ? AND codigo = ?", (norma, codigo)).fetchone()
        return self._simbolo(f) if f else None

    def listar_simbolos(self, norma: str | None = None) -> list[dict]:
        sql, args = "SELECT * FROM simbolos", ()
        if norma:
            sql += " WHERE norma = ?"; args = (norma,)
        with self._con() as con:
            return [self._simbolo(f) for f in con.execute(sql + " ORDER BY norma, id", args)]

    def normas(self) -> list[str]:
        with self._con() as con:
            return [f[0] for f in con.execute("SELECT DISTINCT norma FROM simbolos ORDER BY norma")]

    def eliminar_simbolo(self, codigo: str, norma: str) -> None:
        with self._con() as con:
            con.execute("DELETE FROM simbolos WHERE norma = ? AND codigo = ?", (norma, codigo))

    # ------------------------------------------------------------------ catálogo de equipos
    def guardar_equipo(self, tipo: str, rubro: str = "general", nombre: str = "", simbolo: str = "", parametros: list | None = None,
                       fuente: str = "", rubros: list | None = None, iso_categoria: int | None = None, iso_letra: str = "") -> None:
        tipo = _txt(tipo)
        if not tipo:
            raise ValueError("El tipo de equipo necesita un código")
        ps = []
        for p in parametros or []:
            if not _txt(p.get("clave")):
                continue
            q = dict(p); q["clave"] = _txt(p["clave"])
            for k in ("minimo", "maximo"):
                q[k] = _num(p.get(k))
            ps.append(q)
        with self._con() as con:
            con.execute("INSERT INTO catalogo_equipos (tipo, rubro, rubros_json, nombre, simbolo, iso_categoria, iso_letra, parametros_json, fuente, modificado) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?) ON CONFLICT(tipo) DO UPDATE SET rubro=excluded.rubro, rubros_json=excluded.rubros_json, "
                        "nombre=excluded.nombre, simbolo=excluded.simbolo, iso_categoria=excluded.iso_categoria, iso_letra=excluded.iso_letra, "
                        "parametros_json=excluded.parametros_json, fuente=excluded.fuente, modificado=excluded.modificado",
                        (tipo, _txt(rubro) or "general", a_json(list(rubros or [])), _txt(nombre), _txt(simbolo),
                         None if iso_categoria is None or _num(iso_categoria) is None else int(_num(iso_categoria)), _txt(iso_letra),
                         a_json(ps), _txt(fuente), _ahora()))

    @staticmethod
    def _equipo(f) -> dict:
        d = dict(f); d["rubros"] = json.loads(d.pop("rubros_json") or "[]"); d["parametros"] = json.loads(d.pop("parametros_json") or "[]")
        return d

    def obtener_equipo(self, tipo: str) -> dict | None:
        with self._con() as con:
            f = con.execute("SELECT * FROM catalogo_equipos WHERE tipo = ?", (tipo,)).fetchone()
        return self._equipo(f) if f else None

    def listar_catalogo(self, rubro: str | None = None) -> list[dict]:
        with self._con() as con:
            filas = [self._equipo(f) for f in con.execute("SELECT * FROM catalogo_equipos ORDER BY rubro, tipo")]
        if rubro:
            filas = [f for f in filas if f["rubro"] in (rubro, "general") or rubro in f["rubros"]]
        return filas

    def eliminar_equipo(self, tipo: str) -> None:
        with self._con() as con:
            con.execute("DELETE FROM catalogo_equipos WHERE tipo = ?", (tipo,))

    # ------------------------------------------------------------------ desafíos
    @staticmethod
    def _desafio(f) -> dict:
        d = dict(f); d["demanda"] = json.loads(d.pop("demanda_json") or "{}"); d["precios"] = json.loads(d.pop("precios_json") or "[]")
        d["activo"] = bool(d["activo"]); return d

    def guardar_desafio(self, d: dict) -> int:
        """Crea el desafío (sin id) o actualiza el que tiene ese id. Valida antes con motor/desafio.py. Devuelve el id."""
        from ..motor.desafio import exigir_valido
        exigir_valido(d)
        args = (_txt(d["titulo"]), _txt(d.get("enunciado")), _txt(d.get("producto")), _txt(d.get("rubro")) or "general",
                a_json(d.get("demanda") or {}), a_json(d.get("precios") or []), _txt(d.get("autor")),
                _txt(d.get("fecha")) or date.today().isoformat(), 1 if d.get("activo", True) else 0, _ahora())
        with self._con() as con:
            try:
                if d.get("id"):
                    cur = con.execute("UPDATE desafios SET titulo=?, enunciado=?, producto=?, rubro=?, demanda_json=?, precios_json=?, autor=?, "
                                      "fecha=?, activo=?, modificado=? WHERE id = ?", args + (int(d["id"]),))
                    if cur.rowcount == 0:
                        raise KeyError(f"No existe el desafío {d['id']}")
                    return int(d["id"])
                cur = con.execute("INSERT INTO desafios (titulo, enunciado, producto, rubro, demanda_json, precios_json, autor, fecha, activo, modificado) "
                                  "VALUES (?,?,?,?,?,?,?,?,?,?)", args)
                return int(cur.lastrowid)
            except sqlite3.IntegrityError:
                raise ValueError(f"Ya existe un desafío llamado «{_txt(d['titulo'])}»") from None

    def obtener_desafio(self, ref: int | str) -> dict | None:
        col = "id" if isinstance(ref, int) else "titulo"
        with self._con() as con:
            f = con.execute(f"SELECT * FROM desafios WHERE {col} = ?", (ref,)).fetchone()
        return self._desafio(f) if f else None

    def listar_desafios(self, solo_activos: bool = False) -> list[dict]:
        sql = "SELECT * FROM desafios" + (" WHERE activo = 1" if solo_activos else "") + " ORDER BY id"
        with self._con() as con:
            return [self._desafio(f) for f in con.execute(sql)]

    def activar_desafio(self, desafio_id: int, activo: bool = True) -> None:
        with self._con() as con:
            con.execute("UPDATE desafios SET activo = ?, modificado = ? WHERE id = ?", (1 if activo else 0, _ahora(), int(desafio_id)))

    def eliminar_desafio(self, desafio_id: int) -> None:
        with self._con() as con:
            con.execute("DELETE FROM desafios WHERE id = ?", (int(desafio_id),))

    # ------------------------------------------------------------------ usuarios con rol (opcional)
    def guardar_usuario(self, usuario: str, rol: str = "estudiante", clave: str | None = None) -> None:
        from ..motor.curso import hash_clave
        usuario = _txt(usuario).lower()
        if not usuario:
            raise ValueError("El usuario necesita un identificador")
        if rol not in ROLES:
            raise ValueError(f"Rol desconocido: {rol}. Use {', '.join(ROLES)}")
        h = hash_clave(clave) if clave else ""
        with self._con() as con:
            con.execute("INSERT INTO usuarios_rol (usuario, rol, clave_hash, creado) VALUES (?,?,?,?) ON CONFLICT(usuario) DO UPDATE SET "
                        "rol=excluded.rol, clave_hash=CASE WHEN excluded.clave_hash = '' THEN usuarios_rol.clave_hash ELSE excluded.clave_hash END",
                        (usuario, rol, h, _ahora()))

    def rol_de(self, usuario: str, clave: str) -> str | None:
        """Rol del usuario si la clave coincide con su hash; None si no existe o la clave no coincide."""
        from ..motor.curso import verificar_clave
        with self._con() as con:
            f = con.execute("SELECT rol, clave_hash FROM usuarios_rol WHERE usuario = ?", (_txt(usuario).lower(),)).fetchone()
        return f["rol"] if f and verificar_clave(clave, f["clave_hash"]) else None

    def listar_usuarios(self) -> list[dict]:
        with self._con() as con:
            return [dict(usuario=f["usuario"], rol=f["rol"], con_clave=bool(f["clave_hash"]), creado=f["creado"])
                    for f in con.execute("SELECT * FROM usuarios_rol ORDER BY rol, usuario")]

    # ------------------------------------------------------------------ semilla
    def sembrar(self, desafios: bool = True) -> dict:
        """Copia la semilla a la base sin pisar lo editado (INSERT OR IGNORE). Devuelve cuántas filas agregó en cada tabla."""
        out = dict(parametros=0, simbolos=0, catalogo_equipos=0, desafios=0)
        ahora = _ahora()
        with self._con() as con:
            for p in semilla_parametros():
                out["parametros"] += con.execute(
                    "INSERT OR IGNORE INTO parametros (clave, nombre, valor, unidad, categoria, fuente, fecha, modificado) VALUES (?,?,?,?,?,?,?,?)",
                    (p["clave"], p["nombre"], float(p["valor"]), p["unidad"], p["categoria"], p["fuente"], p["fecha"], ahora)).rowcount
            for s in semilla_simbolos():
                out["simbolos"] += con.execute(
                    "INSERT OR IGNORE INTO simbolos (norma, codigo, nombre, categoria, letra, svg, parametros_json, fuente, modificado) VALUES (?,?,?,?,?,?,?,?,?)",
                    (s["norma"], s["codigo"], s["nombre"], s["categoria"], s["letra"], s["svg"], a_json(s["parametros"]), s["fuente"], ahora)).rowcount
            for e in semilla_catalogo():
                out["catalogo_equipos"] += con.execute(
                    "INSERT OR IGNORE INTO catalogo_equipos (tipo, rubro, rubros_json, nombre, simbolo, iso_categoria, iso_letra, parametros_json, fuente, modificado) "
                    "VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (e["tipo"], e["rubro"], a_json(e["rubros"]), e["nombre"], e["simbolo"], e["iso_categoria"], e["iso_letra"],
                     a_json(e["parametros"]), e["fuente"], ahora)).rowcount
            titulos = {f[0] for f in con.execute("SELECT titulo FROM desafios")}
        if desafios:
            for fn in (desafio_agrozzi, desafio_agar):
                # el título se conoce sin calcular la planta: se arma la semilla solo si falta (Agrozzi tarda cerca de 1 s)
                titulo = "Planta basada en Agrozzi: pasta de tomate" if fn is desafio_agrozzi else "Secado de agar agar (desafío en blanco)"
                if titulo in titulos:
                    continue
                d = fn(); d["fecha"] = date.today().isoformat()
                self.guardar_desafio(d); out["desafios"] += 1
        return out


# ================================================================== funciones de módulo para el resto de la aplicación
_CACHE: dict = {}


def mantenedor(bd=None) -> Mantenedor:
    """Mantenedor de una BaseDatos (o de una ruta). Sin argumento, la base predeterminada (o PAT_SIM_DB). Se reutiliza por ruta."""
    if isinstance(bd, Mantenedor):
        return bd
    if isinstance(bd, BaseDatos):
        m = _CACHE.get(id(bd))
        if m is None or m.bd is not bd:
            m = _CACHE[id(bd)] = Mantenedor(bd)
        return m
    clave = str(bd or os.environ.get("PAT_SIM_DB") or "")
    if clave not in _CACHE:
        _CACHE[clave] = Mantenedor(bd)
    return _CACHE[clave]


def sembrar(bd=None, desafios: bool = True) -> dict:
    """Llamar una vez al iniciar la aplicación (después de BaseDatos.precargar). Idempotente."""
    return mantenedor(bd).sembrar(desafios)


def _de_semilla(tipo: str, clave, norma: str | None):
    if tipo == "parametro":
        return next((p for p in semilla_parametros() if p["clave"] == clave), None)
    if tipo == "simbolo":
        norma = norma or "ISO 10628"
        return next((s for s in semilla_simbolos() if s["norma"] == norma and s["codigo"] == clave), None)
    if tipo == "equipo":
        return next((e for e in semilla_catalogo() if e["tipo"] == clave), None)
    if tipo == "desafio":
        return next((d for d in semilla_desafios() if d["titulo"] == clave), None)
    raise ValueError(f"Tipo desconocido: {tipo}. Use parametro, simbolo, equipo o desafio")


def obtener(tipo: str, clave, bd=None, norma: str | None = None, defecto=None, fila: bool = False):
    """Lee desde la base con respaldo a la semilla (y al final a «defecto»).

    tipo: "parametro" (devuelve el valor numérico, o la fila completa con fila=True), "simbolo" (dict con svg; norma por
    defecto ISO 10628), "equipo" (dict del tipo con sus parámetros) o "desafio" (por id o por título).
    bd: BaseDatos, Mantenedor, ruta o None (base predeterminada). Si la base falla, se usa la semilla sin detener la aplicación."""
    if tipo not in ("parametro", "simbolo", "equipo", "desafio"):
        raise ValueError(f"Tipo desconocido: {tipo}. Use parametro, simbolo, equipo o desafio")
    r = None
    try:
        m = mantenedor(bd)
        if tipo == "parametro":
            r = m.obtener_parametro(clave)
        elif tipo == "simbolo":
            r = m.obtener_simbolo(clave, norma or "ISO 10628")
        elif tipo == "equipo":
            r = m.obtener_equipo(clave)
        else:
            r = m.obtener_desafio(clave)
    except (sqlite3.Error, OSError):
        r = None
    if r is None and not (tipo == "desafio" and isinstance(clave, int)):
        r = _de_semilla(tipo, clave, norma)
    if r is None:
        return defecto
    if tipo == "parametro" and not fila:
        return float(r["valor"])
    return r


def parametro(clave: str, defecto: float | None = None, bd=None) -> float | None:
    """Atajo: valor de un parámetro (CEPCI, dólar, henry_hub, pmm_sen, precio_biomasa…)."""
    return obtener("parametro", clave, bd=bd, defecto=defecto)


def svg_equipo(codigo: str, x: float = 0, y: float = 0, ancho: float = 60, alto: float | None = None, bd=None) -> str:
    """Como simbolos/iso10628.svg, pero con el dibujo que está en la base (editable en el mantenedor)."""
    s = obtener("simbolo", codigo, bd=bd, norma="ISO 10628") or obtener("simbolo", "equipo_general", bd=bd, norma="ISO 10628")
    alto = alto or ancho
    t = f"{s['nombre']} (ISO 10628, categoría {s['categoria'].split('.')[0]}, letra {s['letra']})"
    t = t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return f'<g transform="translate({x},{y}) scale({ancho / 60},{alto / 60})"><title>{t}</title>{s["svg"]}</g>'


def defectos_equipo(tipo: str, bd=None) -> dict:
    """{clave: valor} de los parámetros por defecto de un tipo de equipo según la base (o la semilla)."""
    e = obtener("equipo", tipo, bd=bd)
    return {p["clave"]: p.get("valor") for p in (e or {}).get("parametros", [])}


def aplicar_defectos(eq, bd=None) -> int:
    """Aplica a un equipo recién creado los valores por defecto que el profesor cambió en el mantenedor (con su fuente).
    Devuelve cuántos parámetros cambió. Para usar donde se agrega un equipo nuevo (lienzo de Diseño)."""
    e = obtener("equipo", eq.tipo, bd=bd)
    n = 0
    for p in (e or {}).get("parametros", []):
        k = p.get("clave")
        if k in eq.params and p.get("valor") is not None and eq.params[k].valor != p["valor"]:
            eq.set(k, p["valor"], categoria=p.get("categoria") or "Usuario", fuente=p.get("fuente") or "", justificacion=p.get("justificacion") or "")
            n += 1
    return n


# ================================================================== clave del profesor
def hash_sha256(texto: str) -> str:
    return hashlib.sha256((texto or "").encode("utf-8")).hexdigest()


def hash_esperado(secretos=None, entorno=None) -> tuple[str, str]:
    """(hash SHA-256 esperado, origen): st.secrets, variable de entorno o la clave por defecto del código. Vacío cuenta como ausente."""
    for origen, fuente in (("secrets", secretos), ("entorno", os.environ if entorno is None else entorno)):
        try:
            v = fuente.get(NOMBRE_SECRETO) if fuente is not None else None
        except Exception:                      # st.secrets sin archivo de secretos lanza un error al leerlo
            v = None
        v = _txt(v).lower()
        if v:
            return v, origen
    return HASH_CLAVE_DEFECTO, "defecto"


def verificar_profesor(clave: str, esperado: str | None = None) -> bool:
    if not clave:
        return False
    esperado = (esperado or HASH_CLAVE_DEFECTO).strip().lower()
    return hmac.compare_digest(hash_sha256(clave), esperado)
