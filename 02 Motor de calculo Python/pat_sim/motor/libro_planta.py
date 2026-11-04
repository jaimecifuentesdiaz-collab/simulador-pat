"""Excel de ida y vuelta de la planta (PAT 134), como las tablas globales y el Excel Import/Export de FlexSim.

plantilla_xlsx arma un libro con las tablas de la planta (parámetros editables, capacidades, supuestos de temporada,
economía y datos medidos); el usuario lo edita en Excel y lo sube; leer_xlsx lo lee con zipfile y xml.etree (sin
openpyxl, que no está en el entorno), validar compara cada celda con la planta y entrega cambios, errores y avisos en
español, y aplicar pone los cambios en la planta con la fuente «Excel subido por el usuario, fecha». resultados_xlsx
exporta los resultados de las corridas (turnos de Operación, temporada por día, distribuciones ajustadas y recuperación
de calor). Los libros se escriben con motor/exportar.py (SpreadsheetML a mano): texto a la izquierda, números al centro,
dinero a la derecha y sin paneles inmovilizados.
Diseño en 01 Requisitos y diseno/Diseno_FlexSim_PAT134_02nov2026.md."""
from __future__ import annotations
import io, math, re, unicodedata, zipfile
import xml.etree.ElementTree as ET
from datetime import date, datetime
from . import exportar as X
from . import datos_planta as DP
from .equipos import OPCIONALES

# PAT 134: dos estilos más sobre los de exportar.py (número general al centro y dinero general a la derecha), para que
# las cifras editables se vean con todos sus decimales; se agregan al styles.xml del libro sin tocar exportar.py
GEN, GEN_CLP = 16, 17
_XF_EXTRA = ('<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>'
             '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>')

HOJAS = ("Leame", "Parametros", "Capacidades", "Temporada", "Economia", "Datos medidos")
SERIES_BASE = ("descarga_h", "falla_h")
FUENTE_EXCEL = "Excel subido por el usuario"
CATEGORIA_EXCEL = "Usuario"

COLS_PARAM = [("equipo", "Equipo"), ("nombre_equipo", "Nombre del equipo"), ("parametro", "Parámetro"), ("descripcion", "Descripción"),
              ("valor", "Valor"), ("unidad", "Unidad"), ("fuente", "Fuente"), ("categoria", "Categoría actual"), ("rango", "Rango aceptado")]
COLS_CAP = [("equipo", "Equipo"), ("nombre_equipo", "Nombre del equipo"), ("capacidad", "Capacidad"), ("unidad", "Unidad"), ("fuente", "Fuente")]
COLS_TEM = [("parametro", "Parámetro"), ("descripcion", "Descripción"), ("valor", "Valor"), ("unidad", "Unidad"), ("justificacion", "Justificación")]
COLS_ECO = [("parametro", "Parámetro"), ("descripcion", "Descripción"), ("valor", "Valor"), ("unidad", "Unidad"), ("fuente", "Fuente")]
ALIAS = {"id": "equipo", "id del equipo": "equipo", "nombre": "nombre_equipo", "capacidad nominal": "capacidad"}

# Temporada: clave del dict de la sesión (ui/p_temporada.py), nombre, unidad, clave en temporada.SUPUESTOS, factor de la
# sesión respecto del supuesto, mínimo, máximo (los mismos límites de los campos de la pestaña Temporada) y si es entero
TEMPORADA = [
    ("semilla", "Semilla de los números aleatorios", "—", None, 1, 0, 10 ** 6, True),
    ("camion", "Carga de un camión", "t", "camion", 1, 1.0, 60.0, False),
    ("cv", "Coeficiente de variación del tiempo de descarga", "—", "cv_servicio", 1, 0.0, 2.0, False),
    ("pico", "Posición del peak de cosecha", "fracción de la temporada", "pico", 1, 0.0, 1.0, False),
    ("ancho", "Desviación estándar de la campana de llegada", "fracción de la temporada", "ancho", 1, 0.05, 2.0, False),
    ("umbral", "Espera sin pérdida de materia prima", "h", "umbral", 1, 0.0, 72.0, False),
    ("tasa", "Pérdida sobre esa espera", "% por h", "tasa", 100, 0.0, 10.0, False),
    ("arranque", "Duración del arranque", "h", "arranque", 1, 0.0, 240.0, False),
    ("cip_cada", "Horas de producción entre limpiezas", "h", "cip_cada", 1, 0.0, 2000.0, False),
    ("cip_dur", "Duración de una limpieza", "h", "cip_dur", 1, 0.0, 48.0, False),
    ("parada_cada", "Días entre paradas programadas", "d", "parada_cada", 1, 0.0, 366.0, False),
    ("parada_dur", "Duración de una parada programada", "h", "parada_dur", 1, 0.0, 240.0, False),
    ("parada_final", "Duración de la parada final", "h", "parada_final", 1, 0.0, 240.0, False),
]
SOLO_TOMATE = ("pico", "ancho")
BASES = ("recepcion", "linea")

# Economía: los mismos valores de partida y fuentes de ui/comun.py (Modelo_PAT_Agrozzi_v2.xlsx, hoja COMBUSTIBLE)
ECONOMIA = [
    ("precio_gas", "Precio del gas natural (Henry Hub)", "US$/MMBtu", 2.77, "CNE (2026c), Reporte mensual sector energético, septiembre de 2026, p. 12; agosto de 2026", 0.0, 100.0, False),
    ("dolar", "Dólar observado", "$/US$", 990.35, "Banco Central de Chile (2026), indicadores diarios, 26-10-2026", 1.0, 5000.0, False),
    ("tasa", "Tasa de descuento", "fracción (0,10 = 10 %)", 0.10, "Supuesto: valor de partida de la pestaña Economía, se puede cambiar", 0.0, 0.5, False),
    ("inversion", "Inversión", "MM$", 0.0, "La declara el usuario (con 0 la pestaña Economía usa la inversión estimada de la alternativa)", 0.0, 1e7, False),
    ("costo_anual", "Costo anual de operación y mantención", "MM$", 0.0, "Lo declara el usuario", 0.0, 1e6, False),
    ("anios", "Horizonte de evaluación", "años", 20, "Supuesto: valor de partida de la pestaña Economía, se puede cambiar", 1, 50, True),
    ("precio_biomasa", "Precio de la biomasa combustible (astilla de pino con corteza, sin IVA)", "$/m³ estéreo", 6750.0,
     "INFOR (Pardo, 2025), Boletín de precios forestales N.° 193, junio de 2025, pp. 12-13; punto medio de 6.000 a 7.500", 0.0, 1e6, False),
]
DINERO = ("precio_gas", "dolar", "inversion", "costo_anual", "precio_biomasa")
SERIES_DESC = {"descarga_h": "tiempo de descarga de un camión en la recepción (h), lo usa Temporada",
               "falla_h": "tiempos de falla de la línea (h), los usa Operación"}


# ------------------------------------------------------------------------------------------------ utilidades
def _n(s) -> str:
    """Texto normalizado para comparar encabezados y nombres de hoja (sin tildes, minúsculas, espacios simples)."""
    s = unicodedata.normalize("NFKD", "" if s is None else str(s)).encode("ascii", "ignore").decode().lower()
    return " ".join(s.replace("_", " ").split())


def _vacio(x) -> bool:
    return x is None or (isinstance(x, str) and not x.strip())


def _num(x):
    """Número de una celda: número de Excel o texto con coma decimal chilena. None si está vacía; ValueError si no es número."""
    if _vacio(x):
        return None
    if isinstance(x, bool):
        raise ValueError("es un valor lógico, no un número")
    if isinstance(x, (int, float)):
        v = float(x)
        if not math.isfinite(v):
            raise ValueError("valor no finito")
        return v
    return DP.numero_cl(x)


def _t(v, d: int | None = None) -> str:
    if v is None:
        return "sin valor"
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, (int, float)):
        return DP.texto_cl(v) if d is None else X._cl(v, d)
    if isinstance(v, (list, tuple)):
        return f"{len(v)} valores"
    return str(v)


def _igual(a, b) -> bool:
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b), rel_tol=1e-9, abs_tol=1e-12)   # Excel guarda 15 cifras significativas
    return a == b


def _libro(hojas: list) -> bytes:
    """Libro de exportar.libro_xlsx con los dos estilos extra agregados a styles.xml."""
    b = X.libro_xlsx(hojas)
    zin = zipfile.ZipFile(io.BytesIO(b)); out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for it in zin.infolist():
            datos = zin.read(it.filename)
            if it.filename == "xl/styles.xml":
                s = datos.decode()
                s = s.replace('<cellXfs count="16">', '<cellXfs count="18">', 1).replace("</cellXfs>", _XF_EXTRA + "</cellXfs>", 1)
                datos = s.encode()
            z.writestr(it.filename, datos)
    return out.getvalue()


def _hoy(fecha) -> str:
    if isinstance(fecha, date):
        return fecha.strftime("%d-%m-%Y")
    return fecha or datetime.now().strftime("%d-%m-%Y")


def _encabezado(h: X.Hoja, titulo: str, nota: str, cols: list, estilos: list, fila: int = 4):
    h.poner(1, 1, titulo, X.TIT); h.poner(2, 1, nota, X.NOTA)
    h.fila(fila, [t for _k, t in cols], estilos)


# ------------------------------------------------------------------------------------------------ valores base
def temporada_base(pl) -> dict:
    """Parámetros de temporada de partida del rubro, con la misma forma del dict de ui/p_temporada.py."""
    from . import temporada as TM
    sp = TM.supuestos(pl)
    return dict(semilla=1, camion=sp["camion"], cv=sp["cv_servicio"], umbral=sp["umbral"], tasa=100 * sp["tasa"], base="recepcion",
                con_programa=True, arranque=sp["arranque"], cip_cada=sp["cip_cada"], cip_dur=sp["cip_dur"], parada_cada=sp["parada_cada"],
                parada_dur=sp["parada_dur"], parada_final=sp["parada_final"], pico=sp.get("pico", 0.5), ancho=sp.get("ancho", 0.25))


def economia_base() -> dict:
    return {k: v for k, _n_, _u, v, _f, _a, _b, _e in ECONOMIA}


def _filas_temporada(pl) -> list:
    return [t for t in TEMPORADA if pl.rubro == "tomate" or t[0] not in SOLO_TOMATE]


def _justificacion_temporada(pl, clave_sup) -> str:
    from . import temporada as TM
    if clave_sup is None:
        return "random.Random(semilla): la misma semilla entrega la misma temporada; se puede cambiar para ver otra corrida"
    for s in TM.SUPUESTOS.get(pl.rubro, TM.SUPUESTOS["pellet"]):
        if s.clave == clave_sup:
            return f"Supuesto: {s.justificacion}"
    return "Supuesto del simulador"


def parametros_editables(pl) -> list:
    """(equipo, parámetro) numéricos que se pueden editar: los de datos_planta.es_numerico, sin los que ajusta una
    especificación de diseño. La capacidad va en su propia hoja."""
    fijos = DP.ajustados_por_especificacion(pl); out = []
    for e in pl.equipos.values():
        for p in e.params.values():
            if DP.es_numerico(p) and (e.id, p.clave) not in fijos and p.clave != "capacidad":
                out.append((e, p))
    return out


def _rango(p) -> str:
    if p.minimo is None and p.maximo is None:
        return "sin límites declarados; no negativo" if p.unidad != "°C" else "sin límites declarados"
    return f"{DP.texto_cl(p.minimo) if p.minimo is not None else '−∞'} a {DP.texto_cl(p.maximo) if p.maximo is not None else '∞'}"


# ------------------------------------------------------------------------------------------------ plantilla
def plantilla_xlsx(pl, temporada: dict | None = None, economia: dict | None = None, datos_medidos: dict | None = None,
                   fecha=None) -> bytes:
    """Libro para editar en Excel con las hojas Leame, Parametros, Capacidades, Temporada, Economia y Datos medidos."""
    hoy = _hoy(fecha)
    T = dict(temporada_base(pl), **(temporada or {}))
    E = dict(economia_base(), **{k: v for k, v in (economia or {}).items() if k in economia_base()})
    base_E = economia_base()
    hojas = []

    # Leame
    h = X.Hoja("Leame", [24, 110])
    h.poner(1, 1, f"Excel de ida y vuelta de la planta: {pl.nombre}", X.TIT)
    h.poner(2, 1, f"Generado por el simulador del PAT (pat_sim, PAT 134) el {hoy}. Como las tablas globales y el Excel Import/Export de "
                  "FlexSim: se edita en Excel y se sube en la pestaña Datos de entrada.", X.NOTA)
    filas = [("Planta", pl.nombre), ("Rubro", pl.rubro), ("Fecha", hoy), ("", ""),
             ("Hoja", "Qué se puede editar"),
             ("Parametros", "Solo las columnas Valor y Fuente. Una fila por parámetro numérico de cada equipo; no cambie Equipo ni Parámetro."),
             ("Capacidades", "Solo la columna Capacidad (t/h de carga de entrada). Vacía = sin capacidad declarada."),
             ("Temporada", "Solo la columna Valor. Supuestos de la temporada del rubro con su justificación."),
             ("Economia", "Solo la columna Valor. La tasa va como fracción (0,10 = 10 %)."),
             ("Datos medidos", "Todas las columnas: un dato por celda bajo el nombre de la serie. Se puede agregar una serie nueva en "
                               "una columna libre con su nombre en la fila de encabezados. Cada serie necesita al menos 5 valores."),
             ("", ""), ("Reglas", "Se acepta coma decimal (0,85) o punto decimal (0.85). No cambie el nombre de las hojas ni de los encabezados."),
             ("", "No hay valores negativos, salvo temperaturas con mínimo declarado; las fracciones van de 0 a 1 y las horas por día hasta 24."),
             ("", "Las filas con error no se aplican; el resto sí. Los cambios quedan con la fuente «Excel subido por el usuario» y la fecha.")]
    for i, (a, b) in enumerate(filas, start=4):
        h.poner(i, 1, a, X.TOT_TXT if a in ("Hoja", "Reglas") or i < 7 else X.TXT); h.poner(i, 2, b, X.TOT_TXT if a == "Hoja" else X.TXT)
    hojas.append(h)

    # Parametros
    h = X.Hoja("Parametros", [9, 30, 22, 40, 13, 12, 50, 14, 22])
    _encabezado(h, f"Parámetros de los equipos: {pl.nombre}", "Editable: Valor y Fuente. Fuente de cada valor de partida en la columna Fuente.",
                COLS_PARAM, [X.ENC_TXT] * 4 + [X.ENC_NUM] + [X.ENC_TXT] * 4)
    for i, (e, p) in enumerate(parametros_editables(pl), start=5):
        h.fila(i, [e.id, e.nombre, p.clave, p.nombre, None if p.valor is None else float(p.valor), p.unidad or "—", p.fuente or "",
                   p.categoria, _rango(p)], [X.TXT, X.TXT, X.TXT, X.TXT, GEN, X.TXT, X.TXT, X.TXT, X.TXT])
    hojas.append(h)

    # Capacidades
    h = X.Hoja("Capacidades", [9, 30, 13, 9, 60])
    _encabezado(h, f"Capacidades de los equipos: {pl.nombre}", "Editable: Capacidad (carga de entrada nominal). Capacidad efectiva = capacidad × estado.",
                COLS_CAP, [X.ENC_TXT, X.ENC_TXT, X.ENC_NUM, X.ENC_TXT, X.ENC_TXT])
    i = 5
    for e in pl.equipos.values():
        if "capacidad" in e.params:
            p = e.params["capacidad"]
            h.fila(i, [e.id, e.nombre, None if p.valor is None else float(p.valor), p.unidad or "t/h", p.fuente or ""],
                   [X.TXT, X.TXT, GEN, X.TXT, X.TXT]); i += 1
    hojas.append(h)

    # Temporada
    h = X.Hoja("Temporada", [14, 44, 13, 22, 90])
    _encabezado(h, f"Supuestos de la temporada: rubro {pl.rubro}", "Editable: Valor. Son los parámetros de la pestaña Temporada; sin dato de la "
                "planta, cada uno es un Supuesto con su justificación (motor/temporada.py).", COLS_TEM,
                [X.ENC_TXT, X.ENC_TXT, X.ENC_NUM, X.ENC_TXT, X.ENC_TXT])
    i = 5
    for k, nom, u, ks, _f, lo, hi, _e in _filas_temporada(pl):
        h.fila(i, [k, nom, float(T[k]), u, _justificacion_temporada(pl, ks) + f" Rango aceptado: {DP.texto_cl(lo)} a {DP.texto_cl(hi)}."],
               [X.TXT, X.TXT, GEN, X.TXT, X.TXT]); i += 1
    h.fila(i, ["base", "Capacidad de recepción de la cola", T["base"], "recepcion o linea",
               "recepcion: primer equipo de la línea (capacidad de partida); linea: recurso crítico de la línea"], [X.TXT] * 5); i += 1
    h.fila(i, ["con_programa", "La recepción solo atiende en las horas de producción", "sí" if T["con_programa"] else "no", "sí o no",
               "sí: los camiones esperan durante limpiezas y paradas del programa"], [X.TXT] * 5)
    hojas.append(h)

    # Economia
    h = X.Hoja("Economia", [15, 46, 15, 22, 80])
    _encabezado(h, "Parámetros económicos", "Editable: Valor. Dinero a la derecha; la tasa en fracción.", COLS_ECO,
                [X.ENC_TXT, X.ENC_TXT, X.ENC_CLP, X.ENC_TXT, X.ENC_TXT])
    for i, (k, nom, u, v0, fu, _a, _b, ent) in enumerate(ECONOMIA, start=5):
        v = E[k]
        fuente = fu if _igual(v, base_E[k]) else f"Valor de la sesión de la aplicación al descargar, {hoy}"
        est = X.PCT if k == "tasa" else X.NUM0 if ent else GEN_CLP
        h.fila(i, [k, nom, float(v) if not ent else int(v), u, fuente], [X.TXT, X.TXT, est, X.TXT, X.TXT])
    hojas.append(h)

    # Datos medidos
    dm = {k: list(v) for k, v in (datos_medidos or {}).items()}
    series = list(SERIES_BASE) + [k for k in dm if k not in SERIES_BASE]
    h = X.Hoja("Datos medidos", [14] * max(len(series), 2))
    h.poner(1, 1, "Datos medidos (para el ajuste de distribuciones)", X.TIT)
    h.poner(2, 1, "Un dato por celda bajo el nombre de la serie, al menos 5 por serie. " +
            "; ".join(f"{k}: {SERIES_DESC[k]}" for k in SERIES_BASE) + ". Se pueden agregar series en columnas nuevas.", X.NOTA)
    h.fila(4, series, [X.ENC_NUM] * len(series))
    for j, s in enumerate(series, start=1):
        for i, v in enumerate(dm.get(s, []), start=5):
            h.poner(i, j, float(v), GEN)
    hojas.append(h)
    return _libro(hojas)


# ------------------------------------------------------------------------------------------------ lectura
def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hijos(el, nombre):
    return [c for c in el if _local(c.tag) == nombre]


def _texto_si(el) -> str:
    """Texto de un elemento <si> o <is>: <t> directo o la suma de los <r><t> del texto enriquecido (sin la fonética <rPh>)."""
    partes = []
    for c in el:
        n = _local(c.tag)
        if n == "t":
            partes.append(c.text or "")
        elif n == "r":
            partes += [(t.text or "") for t in c if _local(t.tag) == "t"]
    return "".join(partes)


def _col(ref: str) -> int:
    n = 0
    for ch in ref:
        n = n * 26 + (ord(ch) - 64)
    return n


def _ruta(base: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    partes = base.split("/")[:-1] + target.split("/")
    out = []
    for p in partes:
        if p == "..":
            out and out.pop()
        elif p and p != ".":
            out.append(p)
    return "/".join(out)


def leer_xlsx(contenido: bytes) -> dict:
    """Lee un .xlsx: {nombre de hoja: filas}, donde filas[i] es la fila i + 1 de Excel como lista (None en las celdas
    vacías o saltadas). Usa los nombres reales de workbook.xml y sus relaciones, así que acepta libros guardados por Excel."""
    try:
        z = zipfile.ZipFile(io.BytesIO(contenido))
    except zipfile.BadZipFile:
        raise ValueError("El archivo no es un libro .xlsx (no es un zip válido)") from None
    nombres = set(z.namelist())
    # libro principal desde _rels/.rels (normalmente xl/workbook.xml)
    wb = "xl/workbook.xml"
    if "_rels/.rels" in nombres:
        for r in ET.fromstring(z.read("_rels/.rels")):
            if r.get("Type", "").endswith("/officeDocument"):
                wb = _ruta("", r.get("Target", wb)); break
    if wb not in nombres:
        raise ValueError("El libro no tiene xl/workbook.xml")
    rels_wb = _ruta(wb, "_rels/" + wb.rsplit("/", 1)[-1] + ".rels")
    destino = {}
    if rels_wb in nombres:
        for r in ET.fromstring(z.read(rels_wb)):
            destino[r.get("Id")] = (r.get("Type", ""), _ruta(wb, r.get("Target", "")))
    compartidos = []
    ss = next((d for t, d in destino.values() if t.endswith("/sharedStrings")), None) or ("xl/sharedStrings.xml" if "xl/sharedStrings.xml" in nombres else None)
    if ss and ss in nombres:
        compartidos = [_texto_si(si) for si in ET.fromstring(z.read(ss)) if _local(si.tag) == "si"]
    raiz = ET.fromstring(z.read(wb)); out = {}
    hojas = next((c for c in raiz if _local(c.tag) == "sheets"), [])
    for k, sh in enumerate(_hijos(hojas, "sheet"), start=1):
        rid = next((v for a, v in sh.attrib.items() if _local(a) == "id"), None)
        ruta = destino.get(rid, ("", f"xl/worksheets/sheet{k}.xml"))[1]
        if ruta not in nombres:
            continue
        out[sh.get("name")] = _leer_hoja(z.read(ruta), compartidos)
    return out


def _leer_hoja(xml: bytes, compartidos: list) -> list:
    raiz = ET.fromstring(xml); filas = {}
    datos = next((c for c in raiz if _local(c.tag) == "sheetData"), None)
    if datos is None:
        return []
    nf = 0
    for row in _hijos(datos, "row"):
        nf = int(row.get("r")) if row.get("r") else nf + 1
        celdas = {}; nc = 0
        for c in _hijos(row, "c"):
            ref = c.get("r")
            if ref:
                m = re.match(r"([A-Za-z]+)(\d*)", ref); nc = _col(m.group(1).upper())
            else:
                nc += 1
            t = c.get("t", "n"); v = next((x.text for x in c if _local(x.tag) == "v"), None)
            if t == "s":
                val = compartidos[int(v)] if v is not None and int(v) < len(compartidos) else None
            elif t == "inlineStr":
                is_ = next((x for x in c if _local(x.tag) == "is"), None)
                val = _texto_si(is_) if is_ is not None else None
            elif t in ("str", "e"):
                val = v
            elif t == "b":
                val = None if v is None else v.strip() in ("1", "true")
            else:
                try:
                    val = None if v is None or v == "" else float(v)
                except ValueError:
                    val = v
            celdas[nc] = val
        if celdas:
            fila = [None] * max(celdas)
            for j, val in celdas.items():
                fila[j - 1] = val
            filas[nf] = fila
    return [filas.get(i, []) for i in range(1, max(filas, default=0) + 1)]


# ------------------------------------------------------------------------------------------------ validación
def _clave_col(texto, cols) -> str | None:
    t = _n(texto)
    for k, tit in cols:
        if t in (_n(k), _n(tit)):
            return k
    a = ALIAS.get(t)
    return a if a in [k for k, _ in cols] else None


def _tabla(filas: list, cols: list, requeridas: tuple):
    """Busca la fila de encabezados y devuelve (índice de esa fila, {clave: columna}) o None."""
    for i, f in enumerate(filas[:40]):
        m = {}
        for j, x in enumerate(f):
            k = _clave_col(x, cols) if isinstance(x, str) else None
            if k and k not in m:
                m[k] = j
        if all(r in m for r in requeridas):
            return i, m
    return None


def _hoja(tablas: dict, nombre: str, cols=None, requeridas=(), usados: set | None = None):
    """Hoja por su nombre (sin tildes ni mayúsculas); si el usuario la renombró, la primera hoja no usada por otra tabla
    que tenga los encabezados."""
    usados = set() if usados is None else usados
    for k, v in tablas.items():
        if _n(k) == _n(nombre):
            usados.add(k); return k, v
    if cols:
        for k, v in tablas.items():
            if k not in usados and _n(k) not in [_n(x) for x in HOJAS] and _tabla(v, cols, requeridas):
                usados.add(k); return k, v
    return None, None


def _celda(f, m, k):
    j = m.get(k)
    return f[j] if j is not None and j < len(f) else None


def _rango_param(p, v) -> str | None:
    """Motivo de rechazo del valor v para el parámetro p, o None si está en rango."""
    u = DP.norm_unidad(p.unidad)
    if p.minimo is not None and v < float(p.minimo) - 1e-12:
        return f"bajo el mínimo del parámetro ({DP.texto_cl(p.minimo)} {p.unidad})"
    if p.maximo is not None and v > float(p.maximo) + 1e-12:
        return f"sobre el máximo del parámetro ({DP.texto_cl(p.maximo)} {p.unidad})"
    if p.minimo is None and v < 0 and u != "°c":
        return "no puede ser negativo"
    fraccion = p.maximo is not None and float(p.maximo) <= 1 or (p.maximo is None and isinstance(p.valor, float) and 0 <= p.valor <= 1)
    if u in ("kg/kg", "—", "fraccion", "fracción") and fraccion and not 0 <= v <= 1:
        return "es una fracción: debe estar entre 0 y 1"
    if (u == "h/d" or p.clave == "horas_dia") and not 0 < v <= 24:
        return "las horas por día deben estar entre 0 y 24"
    if p.clave == "capacidad" and v <= 0:
        return "la capacidad debe ser positiva (deje la celda vacía para no declararla)"
    if isinstance(p.valor, int) and not isinstance(p.valor, bool) and abs(v - round(v)) > 1e-9:
        return "debe ser un número entero"
    return None


def _validar_param(pl, out, vistos, hoja, fila, eqid, clave, celda, unidad, fuente):
    lugar = f"{hoja}, fila {fila}"
    eqid = "" if eqid is None else str(eqid).strip(); clave = "" if clave is None else str(clave).strip()
    eq = pl.equipos.get(eqid)
    if eq is None:
        out["errores"].append(f"{lugar}: el equipo «{eqid}» no existe en la planta {pl.nombre}."); return
    p = eq.params.get(clave)
    if p is None:
        out["errores"].append(f"{lugar}: el equipo {eqid} ({eq.nombre}) no tiene el parámetro «{clave}»."); return
    if not DP.es_numerico(p):
        out["errores"].append(f"{lugar}: {eqid}.{clave} no es un parámetro numérico; no se cambia desde el Excel."); return
    if (eqid, clave) in DP.ajustados_por_especificacion(pl):
        out["errores"].append(f"{lugar}: {eqid}.{clave} lo ajusta una especificación de diseño; cambie la especificación en la pestaña Diseño."); return
    try:
        v = _num(celda)
    except ValueError as e:
        out["errores"].append(f"{lugar}: {eqid}.{clave}: el valor «{celda}» no es un número ({e})."); return
    nota = ""
    if v is not None and not _vacio(unidad):
        ua, up = DP.norm_unidad(str(unidad)), DP.norm_unidad(p.unidad)
        if ua != up:
            k = DP.CONVERSIONES.get((ua, up))
            if k is None:
                out["errores"].append(f"{lugar}: {eqid}.{clave}: la unidad «{unidad}» no es la del parámetro ({p.unidad or '—'}) y no hay conversión conocida."); return
            v = v * k; nota = f"convertido de {unidad} a {p.unidad}"
            out["avisos"].append(f"{lugar}: {eqid}.{clave} {nota}.")
    previo = vistos.get((eqid, clave))
    if previo is not None:
        if not _igual(previo[1], v):
            out["errores"].append(f"{lugar}: {eqid}.{clave} ya viene en {previo[0]} con otro valor; se deja el primero.")
        return
    vistos[(eqid, clave)] = (lugar, v)
    if v is None:
        if p.valor is not None:
            out["avisos"].append(f"{lugar}: {eqid}.{clave} está vacío; se mantiene el valor {_t(p.valor)} {p.unidad}.")
        return
    fuente = "" if _vacio(fuente) else str(fuente).strip()
    if _igual(p.valor, v):                  # sin cambio: no se valida el rango del valor que ya tiene la planta
        if fuente and fuente != (p.fuente or ""):
            out["avisos"].append(f"{lugar}: {eqid}.{clave} cambió solo la fuente; la fuente se cambia junto con el valor.")
        return
    motivo = _rango_param(p, v)
    if motivo:
        out["errores"].append(f"{lugar}: {eqid}.{clave} = {_t(v)}: {motivo}."); return
    if isinstance(p.valor, int) and not isinstance(p.valor, bool):
        v = int(round(v))
    c = dict(destino="planta", hoja=hoja, fila=fila, equipo=eqid, nombre_equipo=eq.nombre, parametro=clave, nombre=p.nombre,
             objeto=f"{eqid} · {eq.nombre}", antes=p.valor, despues=v, unidad=p.unidad, categoria_antes=p.categoria, fuente_antes=p.fuente,
             fuente=fuente if fuente and fuente != (p.fuente or "") else "", nota=nota)
    out["planta"].append(c); out["cambios"].append(c)


def _si_no(x):
    if isinstance(x, bool):
        return x
    if isinstance(x, (int, float)):
        return bool(x)
    t = _n(x)
    if t in ("si", "s", "1", "verdadero", "true", "x"):
        return True
    if t in ("no", "n", "0", "falso", "false"):
        return False
    raise ValueError("escriba sí o no")


def validar(pl, tablas: dict, temporada: dict | None = None, economia: dict | None = None, datos_medidos: dict | None = None) -> dict:
    """Compara el libro leído con la planta. Devuelve cambios (todos, con su destino), errores y avisos en español, y lo que
    va a cada destino: planta (lista de cambios), temporada y economia (dict completo, o None si el libro no trae la hoja)
    y datos_medidos (series válidas, o None). temporada, economia y datos_medidos son los valores actuales de la sesión."""
    out = dict(cambios=[], errores=[], avisos=[], planta=[], temporada=None, economia=None, datos_medidos=None, rubro=pl.rubro)
    # rubro del libro
    _k, le = _hoja(tablas, "Leame")
    if le:
        r = next((f[1] for f in le if len(f) > 1 and _n(f[0]) == "rubro"), None)
        if r and _n(r) != _n(pl.rubro):
            out["avisos"].append(f"El libro es de una planta del rubro {r} y la planta actual es del rubro {pl.rubro}: revise los equipos.")
    vistos = {}; usados = {k for k in tablas if _n(k) in [_n(x) for x in HOJAS]}
    # Parametros y Capacidades
    for nombre, cols, req, colv in (("Parametros", COLS_PARAM, ("equipo", "parametro", "valor"), "valor"),
                                    ("Capacidades", COLS_CAP, ("equipo", "capacidad"), "capacidad")):
        hn, filas = _hoja(tablas, nombre, cols, req, usados)
        if filas is None:
            out["avisos"].append(f"El libro no trae la hoja {nombre}: no se cambia nada de ella."); continue
        t = _tabla(filas, cols, req)
        if t is None:
            out["errores"].append(f"Hoja {hn}: no se encontró la fila de encabezados ({', '.join(req)})."); continue
        i0, m = t
        for i in range(i0 + 1, len(filas)):
            f = filas[i]
            if all(_vacio(x) for x in f):
                continue
            eqid = _celda(f, m, "equipo")
            clave = _celda(f, m, "parametro") if colv == "valor" else "capacidad"
            if _vacio(eqid) or _vacio(clave):
                out["avisos"].append(f"{hn}, fila {i + 1}: sin equipo o parámetro; se ignora."); continue
            _validar_param(pl, out, vistos, hn, i + 1, eqid, clave, _celda(f, m, colv), _celda(f, m, "unidad"), _celda(f, m, "fuente"))
    # Temporada
    hn, filas = _hoja(tablas, "Temporada", COLS_TEM, ("parametro", "valor"), usados)
    t = _tabla(filas, COLS_TEM, ("parametro", "valor")) if filas is not None else None
    if filas is None:
        out["avisos"].append("El libro no trae la hoja Temporada: los supuestos de temporada no cambian.")
    elif t is None:
        out["errores"].append(f"Hoja {hn}: no se encontró la fila de encabezados (Parámetro, Valor).")
    else:
        base = dict(temporada_base(pl), **(temporada or {})); nuevo = dict(base); i0, m = t
        defs = {x[0]: x for x in TEMPORADA}
        for i in range(i0 + 1, len(filas)):
            f = filas[i]; lugar = f"{hn}, fila {i + 1}"
            if all(_vacio(x) for x in f):
                continue
            k = "" if _celda(f, m, "parametro") is None else str(_celda(f, m, "parametro")).strip(); x = _celda(f, m, "valor")
            try:
                if k == "base":
                    v = _n(x).replace(" ", "")
                    if v not in BASES:
                        raise ValueError("escriba recepcion o linea")
                elif k == "con_programa":
                    v = _si_no(x)
                elif k in defs:
                    _k2, nom, u, _ks, _fa, lo, hi, ent = defs[k]
                    v = _num(x)
                    if v is None:
                        out["avisos"].append(f"{lugar}: {k} está vacío; se mantiene {_t(base[k])} {u}."); continue
                    if not lo - 1e-12 <= v <= hi + 1e-12:
                        raise ValueError(f"fuera de rango ({DP.texto_cl(lo)} a {DP.texto_cl(hi)} {u})")
                    if ent:
                        if abs(v - round(v)) > 1e-9:
                            raise ValueError("debe ser un número entero")
                        v = int(round(v))
                else:
                    out["errores"].append(f"{lugar}: parámetro de temporada desconocido «{k}»."); continue
            except ValueError as e:
                out["errores"].append(f"{lugar}: {k} = «{x}»: {e}."); continue
            nuevo[k] = v
            if not _igual(base.get(k), v):
                d = defs.get(k)
                c = dict(destino="temporada", hoja=hn, fila=i + 1, equipo=None, parametro=k, nombre=d[1] if d else k, objeto="Temporada",
                         antes=base.get(k), despues=v, unidad=d[2] if d else "", nota="")
                out["cambios"].append(c)
        out["temporada"] = nuevo
    # Economia
    hn, filas = _hoja(tablas, "Economia", COLS_ECO, ("parametro", "valor"), usados)
    t = _tabla(filas, COLS_ECO, ("parametro", "valor")) if filas is not None else None
    if filas is None:
        out["avisos"].append("El libro no trae la hoja Economia: la economía no cambia.")
    elif t is None:
        out["errores"].append(f"Hoja {hn}: no se encontró la fila de encabezados (Parámetro, Valor).")
    else:
        base = dict(economia_base(), **(economia or {})); nuevo = {}; i0, m = t
        defs = {x[0]: x for x in ECONOMIA}
        for i in range(i0 + 1, len(filas)):
            f = filas[i]; lugar = f"{hn}, fila {i + 1}"
            if all(_vacio(x) for x in f):
                continue
            k = "" if _celda(f, m, "parametro") is None else str(_celda(f, m, "parametro")).strip(); x = _celda(f, m, "valor")
            if k not in defs:
                out["errores"].append(f"{lugar}: parámetro económico desconocido «{k}»."); continue
            _k2, nom, u, _v0, _fu, lo, hi, ent = defs[k]
            try:
                v = _num(x)
            except ValueError as e:
                out["errores"].append(f"{lugar}: {k} = «{x}» no es un número ({e})."); continue
            if v is None:
                out["avisos"].append(f"{lugar}: {k} está vacío; se mantiene {_t(base.get(k))} {u}."); continue
            if k == "tasa" and 1 < v <= 50:
                out["avisos"].append(f"{lugar}: la tasa {_t(v)} se leyó como porcentaje ({_t(v / 100)} en fracción)."); v = v / 100
            if not lo - 1e-12 <= v <= hi + 1e-12:
                out["errores"].append(f"{lugar}: {k} = {_t(v)} fuera de rango ({DP.texto_cl(lo)} a {DP.texto_cl(hi)} {u})."); continue
            if ent:
                if abs(v - round(v)) > 1e-9:
                    out["errores"].append(f"{lugar}: {k} debe ser un número entero."); continue
                v = int(round(v))
            nuevo[k] = v
            if not _igual(base.get(k), v):
                out["cambios"].append(dict(destino="economia", hoja=hn, fila=i + 1, equipo=None, parametro=k, nombre=nom, objeto="Economía",
                                           antes=base.get(k), despues=v, unidad=u, nota=""))
        out["economia"] = dict(base, **nuevo)
    # Datos medidos
    hn, filas = _hoja(tablas, "Datos medidos")
    if filas is None:
        for k, v in tablas.items():
            if k not in usados and any(_n(x) in [_n(s) for s in SERIES_BASE] for f in v[:40] for x in f if isinstance(x, str)):
                hn, filas = k, v; break
    if filas is None:
        out["avisos"].append("El libro no trae la hoja Datos medidos: los datos medidos no cambian.")
    else:
        out["datos_medidos"] = dict(datos_medidos or {}, **_validar_series(hn, filas, datos_medidos or {}, out))
    return out


def _validar_series(hn, filas, base, out) -> dict:
    i0 = next((i for i, f in enumerate(filas[:40]) if any(isinstance(x, str) and _n(x) in [_n(s) for s in SERIES_BASE] for x in f)), None)
    if i0 is None:      # encabezados nuevos: la primera fila de solo textos seguida de una fila con números
        i0 = next((i for i, f in enumerate(filas[:-1]) if f and all(isinstance(x, str) or x is None for x in f) and any(isinstance(x, str) for x in f)
                   and any(isinstance(y, float) for y in filas[i + 1])), None)
    if i0 is None:
        out["errores"].append(f"Hoja {hn}: no se encontró la fila con los nombres de las series (descarga_h, falla_h)."); return {}
    series = {}
    for j, nom in enumerate(filas[i0]):
        if _vacio(nom):
            continue
        s = str(nom).strip(); vals = []; malos = 0
        for i in range(i0 + 1, len(filas)):
            x = filas[i][j] if j < len(filas[i]) else None
            if _vacio(x):
                continue
            ref = f"{X.columna(j + 1)}{i + 1}"
            try:
                v = _num(x)
            except ValueError:
                out["errores"].append(f"{hn}, celda {ref}: «{x}» no es un número (serie {s})."); malos += 1; continue
            if v < 0 and s.endswith("_h"):
                out["errores"].append(f"{hn}, celda {ref}: {_t(v)} es negativo; un tiempo no puede ser negativo (serie {s})."); malos += 1; continue
            vals.append(v)
        if not vals and not malos:
            if base.get(s):
                out["avisos"].append(f"{hn}: la serie {s} viene vacía; se mantienen sus {len(base[s])} valores de la sesión.")
            continue
        if malos:
            out["errores"].append(f"{hn}: la serie {s} tiene celdas con error y no se carga."); continue
        if len(vals) < 5:
            out["errores"].append(f"{hn}: la serie {s} tiene {len(vals)} valores; se necesitan al menos 5 para ajustar una distribución."); continue
        if s in series:
            out["errores"].append(f"{hn}: la serie {s} está repetida; se usa la primera columna."); continue
        series[s] = vals
        ant = base.get(s)
        if ant is None or len(ant) != len(vals) or not all(_igual(a, b) for a, b in zip(ant, vals)):
            out["cambios"].append(dict(destino="datos_medidos", hoja=hn, fila=i0 + 1, equipo=None, parametro=s, nombre=SERIES_DESC.get(s, "serie medida"),
                                       objeto="Datos medidos", antes=list(ant) if ant else None, despues=vals, unidad="h" if s.endswith("_h") else "",
                                       nota=f"media {X._cl(sum(vals) / len(vals), 3)}"))
    return series


# ------------------------------------------------------------------------------------------------ aplicar
def aplicar(pl, validacion: dict, hoy: date | None = None) -> list[str]:
    """Aplica a la planta los cambios válidos (categoría «Usuario», fuente «Excel subido por el usuario, fecha») y devuelve
    el detalle, una línea por cambio con su destino. La temporada, la economía y los datos medidos no son de la planta: la
    interfaz los guarda desde validacion["temporada"], ["economia"] y ["datos_medidos"]. La planta queda sin resolver si
    cambió algo (se resuelve después; deshacer(pl, validacion) vuelve atrás)."""
    fecha = (hoy or date.today()).strftime("%d-%m-%Y"); out = []; respaldo = []
    for c in validacion.get("planta", []):
        eq = pl.equipos.get(c["equipo"]); p = eq.params.get(c["parametro"]) if eq else None
        if p is None:
            continue
        respaldo.append((eq.id, p.clave, p.valor, p.categoria, p.fuente, p.justificacion))
        fuente = f"{FUENTE_EXCEL}, {fecha}" + (f"; fuente declarada: {c['fuente']}" if c.get("fuente") else "")
        ant = f"{_t(p.valor)} {p.unidad}".strip()
        eq.set(p.clave, c["despues"], categoria=CATEGORIA_EXCEL, fuente=fuente,
               justificacion=f"Excel de ida y vuelta (PAT 134): reemplaza el valor {ant} ({p.categoria}{', ' + p.fuente if p.fuente else ''})")
        out.append(f"Planta: {eq.id} · {eq.nombre}, {p.nombre}: {ant} → {_t(c['despues'])} {p.unidad}".rstrip())
    validacion["respaldo"] = respaldo
    if respaldo:
        pl.resuelta = False
    nombres = {"temporada": "Temporada", "economia": "Economía", "datos_medidos": "Datos medidos"}
    for c in validacion.get("cambios", []):
        if c["destino"] in nombres:
            out.append(f"{nombres[c['destino']]}: {c['nombre']} ({c['parametro']}): {_t(c['antes'])} → {_t(c['despues'])} {c['unidad']}".rstrip())
    return out


def deshacer(pl, validacion: dict) -> int:
    """Devuelve a la planta los valores, categorías y fuentes que tenía antes de aplicar(). Devuelve cuántos repuso."""
    n = 0
    for eqid, clave, v, cat, fu, ju in reversed(validacion.get("respaldo", [])):
        p = pl.equipos[eqid].params[clave]; p.valor, p.categoria, p.fuente, p.justificacion = v, cat, fu, ju; n += 1
    if n:
        pl.resuelta = False
    return n


def separar(validacion: dict) -> dict:
    """Cambios agrupados por destino: planta, temporada, economia y datos_medidos."""
    g = {k: [] for k in ("planta", "temporada", "economia", "datos_medidos")}
    for c in validacion.get("cambios", []):
        g[c["destino"]].append(c)
    return g


# ------------------------------------------------------------------------------------------------ resultados
def _turnos(op) -> list:
    if op is None:
        return []
    if hasattr(op, "turnos"):
        return list(op.turnos)
    if isinstance(op, dict):
        return list(op.get("turnos", []))
    return list(op)


def _f(v):
    try:
        return None if v is None or isinstance(v, bool) else float(v)
    except (TypeError, ValueError):
        return None


def _hoja_operacion(turnos: list, hoy: str) -> X.Hoja:
    cols = [("turno", "Turno", X.NUM0), ("meta", "Meta de utilización", X.PCT), ("compra", "Compra (t)", X.NUM1), ("recibido", "Recibido (t)", X.NUM1),
            ("mantenimiento", "Mantenimiento", X.TXT), ("falla", "Falla", X.TXT), ("alerta", "Alerta", X.TXT), ("causa", "Causa especial", X.TXT),
            ("capacidad", "Capacidad del turno (t)", X.NUM1), ("producido", "Producido (t)", X.NUM1), ("conformidad", "Conformidad", X.PCT),
            ("conforme", "Conforme (t)", X.NUM1), ("demanda", "Demanda (t)", X.NUM1), ("vendido", "Vendido (t)", X.NUM1),
            ("faltante", "Faltante (t)", X.NUM1), ("stock", "Materia prima en patio (t)", X.NUM1), ("terminado", "Producto en bodega (t)", X.NUM1),
            ("gas_evitado_MMBtu", "Gas evitado (MMBtu)", X.NUM1), ("biomasa_evitada_t", "Biomasa evitada (t)", X.NUM1)]
    h = X.Hoja("Operación", [8, 12, 11, 11, 15, 8, 8, 10, 13, 12, 12, 12, 12, 12, 12, 14, 14, 13, 13])
    h.poner(1, 1, "Turnos de la pestaña Operación", X.TIT)
    h.poner(2, 1, f"Fuente: motor/operacion.py (correr_turno, adaptación de runShift de Scorm_pellet_profesor.html), exportado el {hoy}.", X.NOTA)
    if not turnos:
        h.poner(4, 1, "Sin turnos corridos en la sesión.", X.TXT); return h
    h.fila(4, [t for _k, t, _e in cols], [X.ENC_NUM if e != X.TXT else X.ENC_TXT for _k, _t2, e in cols])
    for i, r in enumerate(turnos, start=5):
        for j, (k, _t2, e) in enumerate(cols, start=1):
            v = r.get(k)
            if e == X.TXT:
                v = ("sí" if v else "no") if isinstance(v, bool) or k in ("falla", "alerta", "causa") else ("" if v is None else str(v))
            else:
                v = _f(v)
            h.poner(i, j, v, e)
    return h


def _temporada_resultado(pl, temporada, resumen):
    """(llegadas, programa, nota): usa el resultado si ya viene; si vienen los parámetros de la sesión, simula."""
    if isinstance(temporada, dict) and "dias" in temporada:
        return temporada, temporada.get("programa"), ""
    from . import temporada as TM
    P = dict(temporada_base(pl), **(temporada or {}))
    pr = TM.programa_temporada(pl, arranque_h=P["arranque"], cip_cada_h=P["cip_cada"], cip_duracion_h=P["cip_dur"], parada_cada_d=P["parada_cada"],
                               parada_duracion_h=P["parada_dur"], parada_final_h=P["parada_final"], resumen=resumen)
    ll = TM.llegadas_temporada(pl, semilla=int(P["semilla"]), camion_t=P["camion"], cv_servicio=P["cv"], pico=P["pico"], ancho=P["ancho"],
                               umbral_h=P["umbral"], tasa_h=P["tasa"] / 100, base=P["base"], programa=pr if P["con_programa"] else None)
    return ll, pr, f"Semilla {P['semilla']}, camión de {X._cl(P['camion'])} t, coeficiente de variación {X._cl(P['cv'], 2)}."


def _hoja_temporada(pl, temporada, resumen, hoy: str) -> X.Hoja:
    h = X.Hoja("Temporada por día", [8, 11, 12, 13, 13, 13, 16, 16, 14, 13, 13])
    h.poner(1, 1, f"Temporada por día: {pl.nombre}", X.TIT)
    try:
        ll, pr, nota = _temporada_resultado(pl, temporada, resumen)
    except Exception as e:                        # planta sin resolver o temporada que no se puede simular
        h.poner(2, 1, f"No se pudo simular la temporada: {e}", X.NOTA); return h
    h.poner(2, 1, "Fuente: motor/temporada.py (simulación de eventos discretos de la cola de camiones; Kingman según Hopp y Spearman, 2008; "
                  f"Little, 1961), exportado el {hoy}. {nota}", X.NOTA)
    res = [("Camiones de la temporada", ll.get("camiones"), X.NUM0), ("Capacidad de recepción (t/h)", ll.get("capacidad_t_h"), X.NUM1),
           ("Espera media simulada (h)", ll.get("espera_media_h"), X.NUM2), ("Espera media de Kingman (h)", ll.get("espera_kingman_h"), X.NUM2),
           ("Materia prima degradada (t)", ll.get("total_degradado_t"), X.NUM1), ("En el patio al cierre (t)", ll.get("cola_final_t"), X.NUM1)]
    if pr:
        res += [("Horas efectivas del programa (h)", pr.get("horas_efectivas"), X.NUM0), ("Disponibilidad del programa", pr.get("disponibilidad"), X.PCT),
                ("Producción de la temporada (t)", pr.get("produccion_programa_t"), X.NUM0),
                ("Calor recuperable perdido en las paradas (MWh)", pr.get("calor_no_recuperado_MWh"), X.NUM0)]
    f = 4
    h.fila(f, ["Resumen", "", "", "Valor"], [X.ENC_TXT, X.ENC_TXT, X.ENC_TXT, X.ENC_NUM]); f += 1
    for nom, v, e in res:
        h.poner(f, 1, nom, X.TXT); h.poner(f, 4, _f(v), e); f += 1
    f += 1
    cols = [("dia", "Día", X.NUM0), ("camiones", "Camiones", X.NUM0), ("llegada_t", "Llegada (t)", X.NUM1), ("procesado_t", "Procesado (t)", X.NUM1),
            ("degradado_t", "Degradado (t)", X.NUM2), ("cola_t", "En cola (t)", X.NUM1), ("camiones_espera_prom", "Camiones en espera, promedio", X.NUM2),
            ("camiones_espera_max", "Camiones en espera, máximo", X.NUM0), ("espera_media_h", "Espera media (h)", X.NUM2),
            ("kingman_h", "Kingman (h)", X.NUM2), ("utilizacion", "Utilización esperada", X.PCT)]
    h.fila(f, [t for _k, t, _e in cols], [X.ENC_NUM] * len(cols)); f += 1
    for d in ll.get("dias", []):
        for j, (k, _t2, e) in enumerate(cols, start=1):
            v = _f(d.get(k))
            h.poner(f, j, v if v is None or math.isfinite(v) else None, e)
        f += 1
    return h


def _texto_parametros(par) -> str:
    if isinstance(par, dict):
        return "; ".join(f"{k} = {_t(v) if isinstance(v, (int, float)) else v}" for k, v in par.items())
    if isinstance(par, (list, tuple)):
        return "; ".join(_t(v) if isinstance(v, (int, float)) else str(v) for v in par)
    return "" if par is None else str(par)


def _expresion(d: dict) -> str:
    for k in ("expresion", "flexsim", "formula"):
        if d.get(k):
            return str(d[k])
    par = d.get("parametros")
    vals = list(par.values()) if isinstance(par, dict) else list(par or [])
    return f"{d.get('nombre', '')}({', '.join(f'{float(v):.6g}' for v in vals if isinstance(v, (int, float)))})"


def _hoja_distribuciones(dist: dict | None, hoy: str) -> X.Hoja:
    h = X.Hoja("Distribuciones", [14, 18, 50, 40, 60])
    h.poner(1, 1, "Distribuciones ajustadas elegidas", X.TIT)
    h.poner(2, 1, f"Fuente: motor/ajuste.py (método de Law, 2015, cap. 6, como ExpertFit de FlexSim), exportado el {hoy}.", X.NOTA)
    if not dist:
        h.poner(4, 1, "Sin distribuciones ajustadas en la sesión.", X.TXT); return h
    h.fila(4, ["Serie", "Distribución", "Parámetros", "Expresión", "Otros datos del ajuste"], [X.ENC_TXT] * 5)
    for i, (s, d) in enumerate(dist.items(), start=5):
        d = d if isinstance(d, dict) else dict(nombre=str(d))
        otros = "; ".join(f"{k} = {_t(v) if isinstance(v, (int, float)) and not isinstance(v, bool) else v}" for k, v in d.items()
                          if k not in ("nombre", "parametros", "expresion", "flexsim", "formula") and isinstance(v, (int, float, str, bool)))
        h.fila(i, [s, str(d.get("nombre", "")), _texto_parametros(d.get("parametros")), _expresion(d), otros], [X.TXT] * 5)
    return h


def resultados_xlsx(pl, op=None, temporada=None, economia=None, distribuciones=None, resumen=None, fecha=None) -> bytes:
    """Resultados de las corridas: turnos de Operación, resumen de temporada por día (temporada: resultado de
    llegadas_temporada o los parámetros de la sesión), distribuciones elegidas y recuperación de calor si viene el resumen."""
    hoy = _hoy(fecha)
    le = X.Hoja("Leame", [26, 100])
    le.poner(1, 1, f"Resultados de las corridas: {pl.nombre}", X.TIT)
    le.poner(2, 1, f"Generado por el simulador del PAT (pat_sim, PAT 134) el {hoy}. Cada hoja indica su fuente.", X.NOTA)
    turnos = _turnos(op)
    for i, (a, b) in enumerate([("Planta", pl.nombre), ("Rubro", pl.rubro), ("Turnos de Operación", str(len(turnos))),
                                ("Distribuciones", ", ".join(distribuciones) if distribuciones else "ninguna")], start=4):
        le.poner(i, 1, a, X.TOT_TXT); le.poner(i, 2, b, X.TXT)
    hojas = [le, _hoja_operacion(turnos, hoy), _hoja_temporada(pl, temporada, resumen, hoy), _hoja_distribuciones(distribuciones, hoy)]
    if resumen:
        try:
            hojas.append(X._hoja_recuperacion(pl, resumen, economia, hoy))
        except Exception as e:                    # resumen incompleto: se informa en vez de cortar la exportación
            h = X.Hoja("Recuperación", [100]); h.poner(1, 1, f"No se pudo exportar la recuperación de calor: {e}", X.NOTA); hojas.append(h)
    return _libro(hojas)
