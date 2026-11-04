"""Precios de equipos desde internet con Tavily y caché en SQLite (PAT 135, tarea T7.1, 04-11-2026).

Indicación 1 del profesor Torres (reunión del 04-11-2026): el precio de cada equipo se busca en internet con Tavily, se escala
con Williams y se actualiza con un índice de costos (motor/costeo.py hace esas dos cuentas).

- Tavily: POST https://api.tavily.com/search con JSON {api_key, query, search_depth "basic", max_results 5, include_answer true}
  y 15 s de espera máxima. Clave en st.secrets["TAVILY_API_KEY"] (archivo .streamlit/secrets.toml, fuera de GitHub) o en la
  variable de entorno TAVILY_API_KEY. Plan gratuito: 1.000 créditos al mes; una búsqueda «basic» gasta uno.
- Del texto que devuelve se sacan con expresiones regulares los precios (US$, CLP o EUR, convertidos a US$ con el dólar y el
  euro de motor/costos.py, Banco Central de Chile, 26-10-2026) y el tamaño si aparece (HP, kW, m², m³/h, t/h, kg/h, pulgadas).
- Caché: tabla propia precios_equipos en la misma base SQLite de BaseDatos (la ruta se toma de la instancia; bd.py no se toca).
- Sin clave o sin red: se usa el último precio guardado y se marca; si no hay ninguno, la función de respaldo (correlación de
  bibliografía de motor/costeo.py) y se marca «bibliografía». Nada de esto levanta errores hacia la interfaz.
"""
from __future__ import annotations
import json, os, re, sqlite3, urllib.request
from contextlib import contextmanager
from datetime import datetime

URL_TAVILY = "https://api.tavily.com/search"
TIMEOUT_S = 15
MAX_RESULTADOS = 5
HP_KW = 0.7457              # kW por HP (1 hp mecánico = 745,7 W)
PULGADA_MM = 25.4
PRECIO_MIN_USD, PRECIO_MAX_USD = 50.0, 5e7   # PAT 135, Supuesto: fuera de esa banda la cifra no es el precio de un equipo

ESQUEMA_PRECIOS = """
CREATE TABLE IF NOT EXISTS precios_equipos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    equipo TEXT NOT NULL,
    tamano REAL,
    unidad TEXT NOT NULL DEFAULT '',
    precio REAL NOT NULL,
    moneda TEXT NOT NULL DEFAULT 'USD',
    fuente TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    fecha_consulta TEXT NOT NULL,
    origen TEXT NOT NULL DEFAULT 'internet'
);
CREATE INDEX IF NOT EXISTS ix_precios_equipo ON precios_equipos(equipo, fecha_consulta);
"""


# ---------------------------------------------------------------- clave
def obtener_clave(secretos=None) -> str | None:
    """Clave de Tavily: st.secrets["TAVILY_API_KEY"] (o el diccionario secretos de las pruebas) y, si no está, la variable de
    entorno TAVILY_API_KEY. None si no hay."""
    clave = None
    try:
        if secretos is None:
            import streamlit as st
            secretos = st.secrets
        clave = secretos["TAVILY_API_KEY"]
    except Exception:                       # sin Streamlit, sin secrets.toml o sin la clave
        clave = None
    clave = (str(clave).strip() if clave else "") or os.environ.get("TAVILY_API_KEY", "").strip()
    return clave or None


# ---------------------------------------------------------------- llamada a Tavily
def buscar_tavily(consulta: str, clave: str, timeout: float = TIMEOUT_S, _abrir=None) -> dict:
    """Llama a Tavily y devuelve el JSON de respuesta. _abrir reemplaza a urllib.request.urlopen en las pruebas.
    Levanta la excepción de red o de formato: quien llama decide el respaldo."""
    if not clave:
        raise ValueError("No hay clave de Tavily")
    cuerpo = json.dumps(dict(api_key=clave, query=consulta, search_depth="basic", max_results=MAX_RESULTADOS,
                             include_answer=True)).encode("utf-8")
    req = urllib.request.Request(URL_TAVILY, data=cuerpo, method="POST",
                                 headers={"Content-Type": "application/json", "Accept": "application/json"})
    abrir = _abrir or urllib.request.urlopen
    with abrir(req, timeout=timeout) as resp:
        datos = resp.read()
    return json.loads(datos.decode("utf-8") if isinstance(datos, bytes) else datos)


# ---------------------------------------------------------------- lectura de números, precios y tamaños
def leer_numero(txt: str) -> float:
    """Número escrito en formato inglés (12,345.67) o chileno (12.345,67); también 12 345 y 1.5."""
    t = txt.strip().replace(" ", "").replace(" ", "")
    if "," in t and "." in t:
        t = t.replace(",", "") if t.rfind(".") > t.rfind(",") else t.replace(".", "").replace(",", ".")
    elif "," in t:
        partes = t.split(",")
        t = t.replace(",", "") if all(len(p) == 3 for p in partes[1:]) else t.replace(",", ".")
    elif "." in t:
        partes = t.split(".")
        if len(partes) > 2 or (len(partes) == 2 and len(partes[1]) == 3 and len(partes[0]) <= 3 and partes[0] != "0"):
            t = t.replace(".", "")          # 12.345 o 1.234.567: punto de miles
    return float(t)


_NUM = r"(\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)"
_MULT = r"(?:\s*(k|mil|million|millones|mm|m)\b)?"
_PATRONES = [
    ("CLP", re.compile(r"(?:CLP\s*\$?|\$\s*CLP)\s*" + _NUM + _MULT, re.I)),
    ("CLP", re.compile(_NUM + _MULT + r"\s*(?:CLP|pesos chilenos)\b", re.I)),
    ("USD", re.compile(r"(?:US\s?\$|USD\s*\$?|U\$S)\s*" + _NUM + _MULT, re.I)),
    ("USD", re.compile(_NUM + _MULT + r"\s*(?:USD|US\$|dólares|dollars)\b", re.I)),
    ("EUR", re.compile(r"(?:€|EUR)\s*" + _NUM + _MULT, re.I)),
    ("EUR", re.compile(_NUM + _MULT + r"\s*(?:€|EUR|euros)\b", re.I)),
    ("USD", re.compile(r"(?<![A-Za-z])\$\s*" + _NUM + _MULT)),          # signo $ solo: dólar (páginas en inglés)
]
_FACTOR_MULT = {"k": 1e3, "mil": 1e3, "million": 1e6, "millones": 1e6, "mm": 1e6, "m": 1e6}


def a_usd(valor: float, moneda: str, dolar: float, euro: float) -> float:
    """Convierte a US$ con el dólar y el euro en pesos ($/US$ y $/EUR)."""
    m = (moneda or "USD").upper()
    if m == "USD":
        return float(valor)
    if m == "CLP":
        return float(valor) / dolar
    if m == "EUR":
        return float(valor) * euro / dolar
    raise ValueError(f"Moneda desconocida: {moneda}")


def extraer_precios(texto: str, dolar: float, euro: float) -> list[dict]:
    """Precios del texto en el orden en que aparecen: {precio, moneda, precio_usd, pos}. Se descartan los que, convertidos,
    quedan fuera de la banda de un equipo (Supuesto PRECIO_MIN_USD a PRECIO_MAX_USD)."""
    out, usados = [], []
    for moneda, pat in _PATRONES:
        for m in pat.finditer(texto or ""):
            if any(a < m.end() and m.start() < b for a, b in usados):
                continue
            try:
                v = leer_numero(m.group(1))
            except ValueError:
                continue
            mult = (m.group(2) or "").lower()
            v *= _FACTOR_MULT.get(mult, 1.0)
            usd = a_usd(v, moneda, dolar, euro)
            usados.append((m.start(), m.end()))
            if PRECIO_MIN_USD <= usd <= PRECIO_MAX_USD:
                out.append(dict(precio=v, moneda=moneda, precio_usd=usd, pos=m.start()))
    return sorted(out, key=lambda d: d["pos"])


_TAMANOS = [
    ("kW", HP_KW, re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:hp|HP|Hp|cv\b|CV\b)")),
    ("kW", 1.0, re.compile(r"(\d+(?:[.,]\d+)?)\s*kW\b", re.I)),
    ("m3/h", 1.0, re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m3/h|m³/h|m3/hr|m³/hr|m3 per hour)", re.I)),
    ("m2", 1.0, re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:m2|m²|sq\.? ?m|square met(?:er|re)s?)\b", re.I)),
    ("t/h", 1.0, re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:t/h|tph|ton/h|tons? per hour|toneladas por hora)", re.I)),
    ("kg/h", 1.0, re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:kg/h|kg/hr|kg per hour)", re.I)),
    ("pulgadas", 1.0, re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:\"|”|''|in\b|inch(?:es)?\b|pulgadas?\b|pulg\b)", re.I)),
]


def extraer_tamano(texto: str, unidad: str | None = None) -> tuple[float, str] | None:
    """Primer tamaño del texto (HP pasa a kW). Con unidad, solo se busca esa unidad (kW, m2, m3/h, t/h, kg/h, pulgadas)."""
    mejor = None
    for u, f, pat in _TAMANOS:
        if unidad and u != unidad:
            continue
        m = pat.search(texto or "")
        if m:
            try:
                v = leer_numero(m.group(1)) * f
            except ValueError:
                continue
            if v > 0 and (mejor is None or m.start() < mejor[2]):
                mejor = (v, u, m.start())
    return (mejor[0], mejor[1]) if mejor else None


# ---------------------------------------------------------------- caché SQLite
def ruta_bd(bd) -> str:
    """Ruta de la base de una instancia de BaseDatos (o la ruta misma si se pasa un texto)."""
    return str(getattr(bd, "ruta", bd))


@contextmanager
def _conexion(bd):
    """Conexión a la base de BaseDatos sin tocar bd.py: la base en memoria usa su conexión persistente."""
    persistente = getattr(bd, "_persistente", None)
    if persistente is not None:
        con = persistente
        try:
            yield con; con.commit()
        except Exception:
            con.rollback(); raise
        return
    con = sqlite3.connect(ruta_bd(bd), timeout=15)
    con.row_factory = sqlite3.Row
    try:
        yield con; con.commit()
    except Exception:
        con.rollback(); raise
    finally:
        con.close()


def crear_tabla(bd) -> None:
    with _conexion(bd) as con:
        con.executescript(ESQUEMA_PRECIOS)


def guardar_precio(bd, equipo: str, tamano: float | None, unidad: str, precio: float, moneda: str, fuente: str, url: str,
                   origen: str = "internet", fecha: str | None = None) -> int:
    """Guarda un precio en precios_equipos y devuelve su id."""
    crear_tabla(bd)
    fecha = fecha or datetime.now().strftime("%Y-%m-%d %H:%M")
    with _conexion(bd) as con:
        cur = con.execute("INSERT INTO precios_equipos (equipo, tamano, unidad, precio, moneda, fuente, url, fecha_consulta, origen) "
                          "VALUES (?,?,?,?,?,?,?,?,?)", (equipo, tamano, unidad or "", float(precio), moneda, fuente or "", url or "",
                                                         fecha, origen))
        return int(cur.lastrowid)


def ultimo_precio(bd, equipo: str, origen: str | None = None) -> dict | None:
    """Último precio guardado de un equipo (opcionalmente de un origen)."""
    try:
        crear_tabla(bd)
        with _conexion(bd) as con:
            sql = "SELECT * FROM precios_equipos WHERE equipo = ?" + (" AND origen = ?" if origen else "") + \
                  " ORDER BY fecha_consulta DESC, id DESC LIMIT 1"
            fila = con.execute(sql, (equipo, origen) if origen else (equipo,)).fetchone()
        if fila is None:
            return None
        cols = ("id", "equipo", "tamano", "unidad", "precio", "moneda", "fuente", "url", "fecha_consulta", "origen")
        return {k: fila[i] for i, k in enumerate(cols)} if not isinstance(fila, sqlite3.Row) else dict(fila)
    except Exception:
        return None


def listar_precios(bd, equipo: str | None = None) -> list[dict]:
    try:
        crear_tabla(bd)
        with _conexion(bd) as con:
            cur = con.execute("SELECT * FROM precios_equipos" + (" WHERE equipo = ?" if equipo else "") + " ORDER BY id DESC",
                              (equipo,) if equipo else ())
            nombres = [d[0] for d in cur.description]
            return [dict(zip(nombres, tuple(f))) for f in cur.fetchall()]
    except Exception:
        return []


# ---------------------------------------------------------------- elección del precio en la respuesta
def elegir_precio(respuesta: dict, unidad: str | None, tamano_req: float | None, dolar: float, euro: float) -> dict | None:
    """Recorre la respuesta de Tavily (answer y cada resultado). Prefiere el precio cuyo texto trae el tamaño en la unidad
    pedida y más cercano al requerido (en razón); si ninguno trae tamaño, el primer precio encontrado."""
    res = respuesta.get("results") or []
    textos = [(f"{r.get('title', '')}. {r.get('content', '')}", r.get("title", "") or "Tavily", r.get("url", "")) for r in res]
    cand = _candidatos(textos, unidad, dolar, euro)
    if not cand and respuesta.get("answer"):      # PAT 135: la respuesta resumida no trae URL propia; solo si ninguna página sirve
        cand = _candidatos([(str(respuesta["answer"]), "Tavily (respuesta resumida, sin página propia)", "")], unidad, dolar, euro)
    if not cand:
        return None
    con_tam = [c for c in cand if c["tamano"]]
    if con_tam and tamano_req:
        import math
        return min(con_tam, key=lambda c: abs(math.log(c["tamano"] / tamano_req)))
    return con_tam[0] if con_tam else cand[0]


def _candidatos(textos, unidad, dolar, euro) -> list[dict]:
    cand = []
    for txt, fuente, url in textos:
        precios = extraer_precios(txt, dolar, euro)
        if not precios:
            continue
        tam = extraer_tamano(txt, unidad) if unidad else None
        cand.append(dict(precios[0], tamano=tam[0] if tam else None, unidad=tam[1] if tam else (unidad or ""), fuente=fuente,
                         url=url, texto=txt[:300]))
    return cand


def obtener_precio(equipo: str, consulta: str, unidad: str | None, tamano_req: float | None, dolar: float, euro: float,
                   bd=None, clave: str | None = None, buscar: bool = False, respaldo=None, _abrir=None) -> dict:
    """Precio de un equipo con su origen. Orden: búsqueda en internet (si buscar y hay clave), último precio guardado,
    respaldo de bibliografía. Nunca levanta errores: el motivo queda en «nota».
    Devuelve {precio_usd, tamano, unidad, fuente, url, fecha, origen, nota} o None si no hay respaldo."""
    nota = ""
    if buscar and clave:
        try:
            resp = buscar_tavily(consulta, clave, _abrir=_abrir)
            c = elegir_precio(resp, unidad, tamano_req, dolar, euro)
            if c is not None:
                fecha = datetime.now().strftime("%Y-%m-%d %H:%M")
                if bd is not None:
                    try:
                        guardar_precio(bd, equipo, c["tamano"], c["unidad"], c["precio"], c["moneda"], c["fuente"], c["url"],
                                       "internet", fecha)
                    except Exception as e:      # la caché falla, el precio igual sirve
                        nota = f"No se pudo guardar en la caché: {e}. "
                return dict(precio_usd=c["precio_usd"], tamano=c["tamano"], unidad=c["unidad"], fuente=c["fuente"], url=c["url"],
                            fecha=fecha, origen="internet", nota=nota + f"Búsqueda: «{consulta}»")
            nota = "La búsqueda no trajo precios legibles. "
        except Exception as e:
            nota = f"Sin conexión con Tavily ({type(e).__name__}). "
    elif buscar:
        nota = "Sin clave de Tavily. "
    if bd is not None:
        u = ultimo_precio(bd, equipo)
        if u is not None:
            try:
                usd = a_usd(u["precio"], u["moneda"], dolar, euro)
                guardado = u["origen"] == "internet"
                return dict(precio_usd=usd, tamano=u["tamano"], unidad=u["unidad"], fuente=u["fuente"], url=u["url"],
                            fecha=u["fecha_consulta"], origen=u["origen"] + (" (guardado)" if guardado else ""),
                            nota=nota + "Último precio guardado en la base")
            except Exception:
                pass
    if respaldo is not None:
        r = respaldo()
        if r is not None:
            r = dict(r); r["origen"] = "bibliografía"; r["nota"] = (nota + r.get("nota", "")).strip()
            return r
    return None
