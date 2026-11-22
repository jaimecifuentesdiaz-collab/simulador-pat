"""Ficha de máquina comercial (PAT 136, tarea T23; punto 9 de los comentarios del profesor Torres del 13-11-2026).

Una ficha reúne lo que se sabe de una máquina real: nombre, fabricante, modelo, capacidad con su unidad, precio con moneda,
fecha y URL, MTBF y MTTR (o disponibilidad), potencia, dimensiones, peso, material, garantía y plazo de entrega. Cada campo
trae su fuente (URL y fecha de consulta, más la frase de la página de donde se leyó) o queda en «sin dato»: no se inventa nada.

Cómo se arma (sin internet en las pruebas)
- consulta_tavily(tipo, capacidad, unidad): la consulta en inglés para Tavily, a partir de la referencia de costeo.py del tipo.
- extraer_ficha(texto, ...): lee el texto de una página (resultado de Tavily) con expresiones regulares y reglas. Lo que no
  aparece queda en «sin dato». Un número solo se acepta si trae su unidad y, para potencia, peso, garantía y plazo, su etiqueta.
- buscar_fichas(...): llama a Tavily (datos/precios_web.py, clave de st.secrets o de la variable de entorno) y arma una ficha por
  resultado. Sin clave o sin red devuelve el motivo y ninguna ficha: la interfaz usa entonces el catálogo Supuesto de 99 modelos
  (ficha_desde_catalogo).
- guardar_ficha(g, ficha): guarda la ficha con genericos.guardar_modelo y su precio con registrar_precio (historial de precios).
- ficha_a_fila_catalogo(ficha, unidad): convierte la ficha a la fila que entiende motor/seleccion.py (capacidad en la unidad del
  equipo de la planta, precio en US$), para comparar combinaciones con las mismas fórmulas de la selección de equipos.

Supuestos declarados
- Capacidad en t/d: se pasa a t/h con 24 h por día (Supuesto: la página no dice las horas de operación).
- Plazo de entrega en rango (por ejemplo 4 a 6 semanas): se toma el extremo mayor; precio en rango: el extremo menor.
- Dimensiones sin etiqueta «L × A × H»: se supone el orden largo, ancho y alto de las fichas técnicas.
- Disponibilidad dada sin MTBF ni MTTR: se deriva el MTBF con el MTTR Supuesto del tipo (motor/linea_fluida.py).
"""
from __future__ import annotations
import re
from datetime import date

from . import costos
from ..datos import precios_web as PW

SIN_DATO = "sin dato"
HP_KW = PW.HP_KW
H_POR_DIA = 24.0
SEM_POR_MES = 52.0 / 12.0

# campo: (título, unidad que se muestra)
CAMPOS = {
    "nombre": ("Nombre", ""),
    "fabricante": ("Fabricante", ""),
    "modelo": ("Modelo", ""),
    "capacidad": ("Capacidad", ""),
    "precio": ("Precio", ""),
    "mtbf_h": ("MTBF", "h"),
    "mttr_h": ("MTTR", "h"),
    "disponibilidad": ("Disponibilidad", "fracción"),
    "potencia_kw": ("Potencia", "kW"),
    "largo_m": ("Largo", "m"),
    "ancho_m": ("Ancho", "m"),
    "alto_m": ("Alto", "m"),
    "peso_kg": ("Peso", "kg"),
    "material": ("Material", ""),
    "garantia_meses": ("Garantía", "meses"),
    "plazo_entrega_semanas": ("Plazo de entrega", "semanas"),
}
CLAVES = tuple(CAMPOS)

_N = r"(\d{1,3}(?:[.,\s]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"


# ---------------------------------------------------------------- estructura
def _hoy() -> str:
    return date.today().isoformat()


def campo(valor=None, unidad: str = "", url: str = "", fecha: str = "", cita: str = "", nota: str = "", **extra) -> dict:
    """Un campo de la ficha: valor (None = sin dato), unidad, URL y fecha de la fuente y la frase de donde se leyó."""
    return dict(valor=valor, unidad=unidad or "", url=url or "", fecha=fecha or "", cita=(cita or "").strip()[:400], nota=nota or "", **extra)


def ficha_vacia(tipo_equipo: str, url: str = "", fecha: str | None = None, titulo: str = "", origen: str = "Tavily") -> dict:
    """Ficha con todos los campos en «sin dato»."""
    return dict(tipo_equipo=tipo_equipo, url=url or "", fecha=fecha or _hoy(), titulo=titulo or "", origen=origen,
                categoria="Internet" if origen in ("Tavily", "Internet") else origen, campos={k: campo() for k in CAMPOS}, consulta="")


def tiene(ficha: dict, clave: str) -> bool:
    c = (ficha.get("campos") or {}).get(clave)
    return bool(c) and c.get("valor") not in (None, "")


def valor(ficha: dict, clave: str, defecto=None):
    return ficha["campos"][clave]["valor"] if tiene(ficha, clave) else defecto


def faltan(ficha: dict) -> list[str]:
    """Claves de los campos que quedaron en «sin dato»."""
    return [k for k in CAMPOS if not tiene(ficha, k)]


def completitud(ficha: dict) -> float:
    """Fracción de los 16 campos con dato."""
    return 1.0 - len(faltan(ficha)) / len(CAMPOS)


def _fmt(v, d: int = 2) -> str:
    if isinstance(v, float):
        if abs(v - round(v)) < 1e-9 or abs(v) >= 1000:
            d = 0
        return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if isinstance(v, int):
        return f"{v:,}".replace(",", ".")
    return str(v)


def texto_campo(ficha: dict, clave: str) -> str:
    """Valor del campo escrito para mostrar («sin dato» si falta). Precio con su moneda; capacidad con su unidad."""
    if not tiene(ficha, clave):
        return SIN_DATO
    c = ficha["campos"][clave]; v = c["valor"]
    if clave == "precio":
        return f"{c.get('moneda', 'US$')} {_fmt(float(v), 0)}"
    if isinstance(v, str):
        return v
    u = c.get("unidad") or CAMPOS[clave][1]
    if clave == "disponibilidad":
        return _fmt(100 * float(v), 2) + " %"
    return f"{_fmt(float(v))} {u}".strip()


def fuente_campo(ficha: dict, clave: str) -> str:
    """Fuente del campo: URL y fecha de consulta, o la fuente escrita (catálogo Supuesto); «sin dato» si falta."""
    if not tiene(ficha, clave):
        return SIN_DATO
    c = ficha["campos"][clave]
    if ficha.get("origen") == "Supuesto":        # catálogo del mantenedor: la fuente es el texto que lo justifica
        return c.get("cita") or "Supuesto"
    partes = [p for p in (c.get("url"), ("consultado el " + c["fecha"]) if c.get("fecha") else "") if p]
    return ", ".join(partes) if partes else (c.get("cita") or "Supuesto")


def tabla_ficha(ficha: dict) -> list[dict]:
    """Filas para mostrar la ficha: campo, valor, fuente y la frase de la página."""
    return [dict(campo=CAMPOS[k][0], valor=texto_campo(ficha, k), fuente=fuente_campo(ficha, k),
                 cita=(ficha["campos"][k].get("cita") or "") if tiene(ficha, k) else "") for k in CAMPOS]


# ---------------------------------------------------------------- consulta a Tavily
SUFIJO_FICHA = "manufacturer model specifications capacity power weight dimensions warranty lead time"


def consulta_tavily(tipo_equipo: str, capacidad: float | None = None, unidad: str | None = None, nombre: str | None = None) -> str:
    """Consulta en inglés para Tavily de un tipo de equipo y una capacidad: la de referencia de motor/costeo.py (la misma que usa el
    precio) más las palabras que traen la ficha técnica. Tipo sin referencia: consulta genérica con el nombre del equipo."""
    from . import costeo as CO
    ref = None
    if tipo_equipo in CO._LINEA:
        ref = CO.REFERENCIAS.get(CO._LINEA[tipo_equipo][0])
    elif tipo_equipo in CO.REFERENCIAS:
        ref = CO.REFERENCIAS[tipo_equipo]
    cap = f"{capacidad:.3g}" if capacidad else ""
    if ref is not None:
        q = ref["consulta"].format(s=cap).replace("  ", " ").strip()
    else:
        base = (nombre or tipo_equipo.replace("_", " ")).strip()
        q = f"industrial {base} price {cap} {unidad or ''}".replace("  ", " ").strip()
    return f"{q} {SUFIJO_FICHA}"[:390]


# ---------------------------------------------------------------- conversión de capacidades
_CAP_UNIDADES = [
    ("t/h", re.compile(r"(?:t/h|t/hr|tph|ton/h|tons?\s+per\s+hour|tonnes?\s+per\s+hour|toneladas\s+por\s+hora)\b", re.I)),
    ("kg/h", re.compile(r"(?:kg/h|kgs/h|kg/hr|kg\s+per\s+hour|kilogramos\s+por\s+hora)\b", re.I)),
    ("t/d", re.compile(r"(?:t/d|tpd|tons?/day|tons?\s+per\s+day|tonnes?\s+per\s+day|toneladas\s+por\s+d[ií]a)\b", re.I)),
    ("m3/h", re.compile(r"(?:m3/h|m³/h|m3/hr|m³/hr|cubic\s+met(?:er|re)s?\s+per\s+hour)", re.I)),
    ("L/h", re.compile(r"(?:l/h|l/hr|lph|lit(?:er|re)s?\s+per\s+hour|litros\s+por\s+hora)\b", re.I)),
    ("kW", re.compile(r"kW\b", re.I)),
    ("m2", re.compile(r"(?:m2|m²|sq\.?\s?m|square\s+met(?:er|re)s?)\b", re.I)),
]
_FAMILIA = {"t/h": "masa", "kg/h": "masa", "t/d": "masa", "m3/h": "volumen", "L/h": "volumen", "kW": "potencia", "m2": "area"}
_FACTOR = {("kg/h", "t/h"): 1e-3, ("t/h", "kg/h"): 1e3, ("t/d", "t/h"): 1.0 / H_POR_DIA, ("t/h", "t/d"): H_POR_DIA,
           ("t/d", "kg/h"): 1e3 / H_POR_DIA, ("kg/h", "t/d"): 1e-3 * H_POR_DIA, ("L/h", "m3/h"): 1e-3, ("m3/h", "L/h"): 1e3}
_ETIQUETA_CAP = re.compile(r"(capacity|capacidad|output|throughput|production|producci[oó]n|evaporation|evaporaci[oó]n|rated|nominal|"
                           r"processing|procesamiento|flow|caudal)", re.I)


def convertir_capacidad(v: float, de: str, a: str) -> float | None:
    """Convierte una capacidad entre unidades compatibles (kg/h, t/h, t/d con 24 h por día, L/h, m3/h); None si no se puede."""
    if de == a:
        return float(v)
    f = _FACTOR.get((de, a))
    return None if f is None else float(v) * f


def _norm_ud(u: str) -> str:
    return {"l/h": "L/h", "kw": "kW", "m²": "m2"}.get((u or "").lower(), u)


def extraer_capacidad(texto: str, unidad_pref: str | None = None):
    """(valor, unidad, frase) de la capacidad: primero un número con unidad cerca de una etiqueta de capacidad; si no, el primero
    en la unidad pedida (o en cualquier unidad de flujo). La potencia en kW solo cuenta como capacidad si se pide kW."""
    t = texto or ""
    pref = _norm_ud(unidad_pref) if unidad_pref else None
    cands = []
    for u, pat in _CAP_UNIDADES:
        for m in re.finditer(_N + r"\s*(?:\+\s*)?" + pat.pattern, t, re.I):
            try:
                v = PW.leer_numero(m.group(1))
            except ValueError:
                continue
            if v <= 0:
                continue
            antes = t[max(0, m.start() - 45):m.start()]
            etiqueta = bool(_ETIQUETA_CAP.search(antes))
            cands.append(dict(v=v, u=u, pos=m.start(), etiqueta=etiqueta, frase=t[max(0, m.start() - 30):m.end() + 5].strip()))
    if pref is not None:
        fam = _FAMILIA.get(pref)
        cands = [c for c in cands if c["u"] == pref or (fam in ("masa", "volumen") and _FAMILIA.get(c["u"]) == fam
                                                           and convertir_capacidad(1.0, c["u"], pref) is not None)]
    else:
        cands = [c for c in cands if c["u"] not in ("kW",)]
    if not cands:
        return None
    mejor = sorted(cands, key=lambda c: (pref is not None and c["u"] != pref, not c["etiqueta"], c["pos"]))[0]
    return mejor["v"], mejor["u"], mejor["frase"]


# ---------------------------------------------------------------- lectores de cada campo
def _frase(t: str, m, antes: int = 30, despues: int = 12) -> str:
    return re.sub(r"\s+", " ", t[max(0, m.start() - antes):m.end() + despues]).strip()


def _num(txt):
    try:
        return PW.leer_numero(txt)
    except ValueError:
        return None


_PARAR = re.compile(r"\b(?:model|modelo|price|precio|type|tipo|capacity|capacidad|power|potencia|origin|brand|marca|moq|supplier|"
                    r"manufacturer|fabricante|min)\b|[,;|\n(]|\.(?:\s|$)", re.I)
_MARCAS = ("Alfa Laval", "GEA", "Tetra Pak", "Bühler", "Buhler", "Andritz", "SPX Flow", "Sulzer", "Grundfos", "KSB", "Flowserve",
           "Spirax Sarco", "Kahl", "CPM", "Amandus Kahl", "Münch", "Vecoplan", "Bruks", "Salvadori", "Siemens", "ABB", "WEG")


def leer_fabricante(t: str):
    m = re.search(r"\b(?i:manufacturer|fabricante|brand|marca|made by|fabricado por)\s*[:：]\s*([A-ZÁÉÍÓÚÑ0-9][\w&.\-áéíóúñÁÉÍÓÚÑ ]{1,40})", t)
    if m:
        v = _PARAR.split(m.group(1))[0].strip(" .-")
        if len(v) >= 2:
            return v, _frase(t, m, 5, 0)
    for marca in _MARCAS:
        m = re.search(r"(?<![\w])" + re.escape(marca) + r"(?![\w])", t)
        if m:
            return marca, _frase(t, m, 20, 20)
    return None


def leer_modelo(t: str):
    m = re.search(r"\b(?:model(?:\s+(?:number|no\.?))?|modelo|item\s+no\.?|part\s+number|type|tipo)\s*[:：#]\s*"
                  r"([A-Za-z0-9][A-Za-z0-9\-_/.]*(?:\s[A-Za-z0-9\-_/.]+){0,2})", t, re.I)
    if m:
        v = _PARAR.split(m.group(1))[0].strip(" .-")
        if v and re.search(r"\d", v):
            return v[:40], _frase(t, m, 5, 0)
    return None


def leer_precio(t: str, dolar: float, euro: float):
    """(precio, moneda, usd, frase, nota): el primer precio con etiqueta de precio cerca o, si no, el primero del texto."""
    ps = PW.extraer_precios(t, dolar, euro)
    if not ps:
        return None
    et = re.compile(r"(price|precio|cost|costo|valor|fob|from|desde|starting|a partir)", re.I)
    p = next((x for x in ps if et.search(t[max(0, x["pos"] - 40):x["pos"]])), ps[0])
    resto = t[p["pos"]:p["pos"] + 70]
    rango = bool(re.match(r"^[^\d]{0,6}\d[\d.,\s]*(?:k|mil)?\s*(?:USD|US\$|CLP|EUR|€)?\s*(?:-|–|—|to|a)\s*(?:US\s?\$|\$|USD|EUR|€|CLP)?\s*\d", resto, re.I))
    mon = {"USD": "US$", "CLP": "CLP", "EUR": "EUR"}[p["moneda"]]
    nota = "Rango de precios en la página: se toma el extremo menor" if rango else ""
    return p["precio"], mon, p["precio_usd"], re.sub(r"\s+", " ", t[max(0, p["pos"] - 25):p["pos"] + 30]).strip(), nota


def _horas(t: str, clave: str):
    m = re.search(clave + r"\b[^0-9\n]{0,25}" + _N + r"\s*(?:h\b|hrs?\b|hours?\b|horas?\b)", t, re.I)
    if m:
        v = _num(m.group(1))
        if v is not None and v >= 0:
            return v, _frase(t, m, 4, 0)
    return None


def leer_disponibilidad(t: str):
    m = re.search(r"(?:availability|disponibilidad|uptime)\b[^0-9\n]{0,25}" + _N + r"\s*%", t, re.I)
    if m:
        v = _num(m.group(1))
        if v is not None and 0 < v <= 100:
            return v / 100.0, _frase(t, m, 4, 0)
    return None


def leer_potencia(t: str):
    m = re.search(r"(?:installed power|total power|rated power|motor power|main motor|power consumption|power|potencia(?: instalada| total| nominal)?|"
                  r"motor)\b[^0-9\n]{0,25}" + _N + r"\s*(kW|HP|hp|CV|W)\b", t, re.I)
    if not m:
        return None
    v = _num(m.group(1)); u = m.group(2).lower()
    if v is None or v <= 0:
        return None
    kw = v if u == "kw" else (v * HP_KW if u in ("hp", "cv") else v / 1000.0)
    return kw, _frase(t, m, 4, 0)


_A_M = {"mm": 0.001, "cm": 0.01, "m": 1.0}
_ROT = {"largo": ("length", "largo", "long"), "ancho": ("width", "ancho"), "alto": ("height", "alto", "altura")}


def leer_dimensiones(t: str) -> dict:
    """Largo, ancho y alto en m: la tripleta «L x A x H unidad» (orden largo, ancho, alto: Supuesto) o cada medida con su etiqueta."""
    out = {}
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*[x×X*]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*[x×X*]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b", t)
    if m:
        u_fin = m.group(6); fr = _frase(t, m, 14, 0)
        for k, i in zip(("largo_m", "ancho_m", "alto_m"), (1, 3, 5)):
            v = _num(m.group(i)); u = m.group(i + 1) or u_fin
            if v:
                out[k] = (v * _A_M[u], fr + " (orden largo, ancho, alto: Supuesto)")
    for k, nombres in (("largo_m", _ROT["largo"]), ("ancho_m", _ROT["ancho"]), ("alto_m", _ROT["alto"])):
        if k in out:
            continue
        mm = re.search(r"\b(?:" + "|".join(nombres) + r")\b[^0-9\n]{0,15}" + _N + r"\s*(mm|cm|m)\b", t, re.I)
        if mm:
            v = _num(mm.group(1))
            if v:
                out[k] = (v * _A_M[mm.group(2).lower()], _frase(t, mm, 4, 0))
    return {k: v for k, v in out.items() if 0.05 <= v[0] <= 100.0}


def leer_peso(t: str):
    m = re.search(r"(?:net weight|gross weight|machine weight|weight|peso(?: neto| bruto)?)\b[^0-9\n]{0,20}" + _N +
                  r"\s*(kgs?|t|tons?|tonnes?|toneladas?|lbs?)\b", t, re.I)
    if not m:
        return None
    v = _num(m.group(1)); u = m.group(2).lower()
    if v is None or v <= 0:
        return None
    f = 1.0 if u.startswith("kg") else (0.45359237 if u.startswith("lb") else 1000.0)
    return v * f, _frase(t, m, 4, 0)


_MATERIAL = re.compile(r"(stainless\s+steel(?:\s+(?:AISI\s*)?(?:304L?|316L?))?|acero\s+inoxidable(?:\s+(?:AISI\s*)?(?:304L?|316L?))?|SUS\s?3(?:04|16)L?|"
                       r"AISI\s?3(?:04|16)L?|carbon\s+steel|acero\s+al\s+carbono|cast\s+iron|hierro\s+fundido|galvani[sz]ed\s+steel|"
                       r"acero\s+galvanizado|aluminum|aluminium|aluminio)", re.I)


def leer_material(t: str):
    m = _MATERIAL.search(t)
    if not m:
        return None
    return re.sub(r"\s+", " ", m.group(1)).strip(), _frase(t, m, 12, 8)


def leer_garantia(t: str):
    for pat in (r"(?:warranty|garant[ií]a)\b[^0-9\n]{0,25}" + _N + r"\s*(years?|yrs?|months?|meses|a[ñn]os?)\b",
                _N + r"[\s-]*(years?|yrs?|months?|meses|a[ñn]os?)\s+(?:limited\s+)?warranty\b",
                _N + r"\s*(a[ñn]os?|meses)\s+de\s+garant[ií]a\b"):
        m = re.search(pat, t, re.I)
        if m:
            v = _num(m.group(1)); u = m.group(2).lower()
            if v and v > 0:
                return (v * 12.0 if u[0] in "ya" else v), _frase(t, m, 4, 0)
    return None


def leer_plazo(t: str):
    m = re.search(r"(?:lead time|delivery(?: time)?|plazo de entrega|tiempo de entrega|entrega)\b[^0-9\n]{0,25}" + _N +
                  r"(?:\s*(?:-|–|—|to|a)\s*" + _N + r")?\s*(weeks?|semanas?|days?|d[ií]as?|months?|meses)\b", t, re.I)
    if not m:
        return None
    a = _num(m.group(1)); b = _num(m.group(2)) if m.group(2) else None
    v = max(x for x in (a, b) if x is not None) if (a or b) else None
    if not v or v <= 0:
        return None
    u = m.group(3).lower()
    sem = v if u.startswith(("w", "sem")) else (v / 7.0 if u.startswith(("d")) else v * SEM_POR_MES)
    return sem, _frase(t, m, 4, 0) + (" (extremo mayor del rango)" if b is not None else "")


# ---------------------------------------------------------------- extractor
def extraer_ficha(texto: str, tipo_equipo: str, url: str = "", fecha: str | None = None, titulo: str = "",
                  unidad_capacidad: str | None = None, dolar: float = costos.DOLAR, euro: float = costos.EURO) -> dict:
    """Ficha leída del texto de una página (resultado de Tavily). Solo con expresiones regulares y reglas: lo que el texto no
    dice queda en «sin dato». Cada dato lleva la URL, la fecha de consulta y la frase de donde se leyó."""
    t = f"{titulo}. {texto}" if titulo else (texto or "")
    t = t.replace(" ", " ")
    f = ficha_vacia(tipo_equipo, url, fecha, titulo)
    c = f["campos"]; fe = f["fecha"]

    def poner(k, v, u="", cita="", nota="", **ex):
        c[k] = campo(v, u or CAMPOS[k][1], url, fe, cita, nota, **ex)

    if titulo.strip():
        poner("nombre", re.sub(r"\s+", " ", titulo).strip()[:120], cita=titulo)
    r = leer_fabricante(t)
    if r:
        poner("fabricante", r[0], cita=r[1])
    r = leer_modelo(t)
    if r:
        poner("modelo", r[0], cita=r[1])
    r = extraer_capacidad(t, unidad_capacidad)
    if r:
        poner("capacidad", r[0], r[1], r[2])
    r = leer_precio(t, dolar, euro)
    if r:
        poner("precio", r[0], r[1], r[3], r[4], moneda=r[1], usd=r[2])
    for k, clave in (("mtbf_h", "MTBF"), ("mttr_h", "MTTR")):
        r = _horas(t, clave)
        if r:
            poner(k, r[0], "h", r[1])
    r = leer_disponibilidad(t)
    if r:
        poner("disponibilidad", r[0], "fracción", r[1])
    r = leer_potencia(t)
    if r:
        poner("potencia_kw", r[0], "kW", r[1])
    for k, (v, cita) in leer_dimensiones(t).items():
        poner(k, v, "m", cita)
    r = leer_peso(t)
    if r:
        poner("peso_kg", r[0], "kg", r[1])
    r = leer_material(t)
    if r:
        poner("material", r[0], cita=r[1])
    r = leer_garantia(t)
    if r:
        poner("garantia_meses", r[0], "meses", r[1])
    r = leer_plazo(t)
    if r:
        poner("plazo_entrega_semanas", r[0], "semanas", r[1])
    return f


# ---------------------------------------------------------------- Tavily
def texto_resultado(r: dict, maximo: int = 30000) -> str:
    """Texto de un resultado de Tavily: contenido resumido y, si vino, el texto completo de la página."""
    partes = [str(r.get("content") or ""), str(r.get("raw_content") or "")[:maximo]]
    return "\n".join(p for p in partes if p)


def buscar_fichas(tipo_equipo: str, capacidad: float | None, unidad: str | None, clave: str | None, nombre: str | None = None,
                  dolar: float = costos.DOLAR, euro: float = costos.EURO, max_resultados: int = 5, _abrir=None) -> dict:
    """Busca fichas de un tipo de equipo con Tavily. Devuelve {fichas, avisos, consulta, origen}. Sin clave, sin red o sin
    resultados legibles: ninguna ficha y el motivo en avisos (la interfaz usa entonces el catálogo Supuesto). No guarda nada."""
    consulta = consulta_tavily(tipo_equipo, capacidad, unidad, nombre)
    out = dict(fichas=[], avisos=[], consulta=consulta, origen="Tavily")
    if not clave:
        out["avisos"].append("Sin clave de Tavily (TAVILY_API_KEY en .streamlit/secrets.toml o en el entorno): se usa el catálogo Supuesto.")
        out["origen"] = "catálogo"
        return out
    try:
        resp = PW.buscar_tavily(consulta, clave, _abrir=_abrir, max_resultados=max_resultados, texto_completo=True)
    except Exception as e:
        out["avisos"].append(f"Sin conexión con Tavily ({type(e).__name__}): se usa el catálogo Supuesto.")
        out["origen"] = "catálogo"
        return out
    fecha = _hoy(); vistas = set()
    for r in (resp.get("results") or []):
        u = r.get("url", "") or ""
        if u and u in vistas:
            continue
        vistas.add(u)
        f = extraer_ficha(texto_resultado(r), tipo_equipo, u, fecha, str(r.get("title") or ""), unidad, dolar, euro)
        f["consulta"] = consulta
        out["fichas"].append(f)
    if not out["fichas"]:
        out["avisos"].append("Tavily no devolvió páginas para esa consulta: se usa el catálogo Supuesto.")
        out["origen"] = "catálogo"
    return out


# ---------------------------------------------------------------- catálogo Supuesto como ficha
def ficha_desde_catalogo(fila: dict) -> dict:
    """Ficha de una fila del catálogo comercial del mantenedor (99 modelos Supuesto): cada campo trae su fuente escrita."""
    f = ficha_vacia(fila["tipo"], fila.get("url") or "", str(fila.get("anio_precio") or ""), fila["modelo"], origen="Supuesto")
    f["categoria"] = fila.get("categoria") or "Supuesto"
    c = f["campos"]
    c["nombre"] = campo(fila["modelo"], cita="Catálogo comercial del mantenedor")
    c["modelo"] = campo(fila["modelo"], cita="Catálogo comercial del mantenedor")
    c["capacidad"] = campo(float(fila["capacidad"]), fila.get("unidad") or "", cita=fila.get("fuente_capacidad") or "Supuesto")
    if fila.get("precio_usd") is not None:
        c["precio"] = campo(float(fila["precio_usd"]), "US$", fila.get("url") or "", str(fila.get("anio_precio") or ""),
                            fila.get("fuente_precio") or "Supuesto", moneda="US$", usd=float(fila["precio_usd"]))
    for k in ("mtbf_h", "mttr_h"):
        if fila.get(k) is not None:
            c[k] = campo(float(fila[k]), "h", cita=fila.get("fuente_confiabilidad") or "Supuesto")
    for k in ("largo_m", "ancho_m", "alto_m"):
        if fila.get(k) is not None:
            c[k] = campo(float(fila[k]), "m", cita=fila.get("fuente_dimensiones") or "Supuesto")
    return f


# ---------------------------------------------------------------- base de datos
def ficha_a_modelo(ficha: dict) -> dict:
    """Ficha → dict para genericos.guardar_modelo. Sin modelo escrito en la página se usa el nombre (título) con una nota."""
    c = ficha["campos"]
    nota = []
    fab = valor(ficha, "fabricante", "")
    modelo = valor(ficha, "modelo")
    if not modelo:
        modelo = valor(ficha, "nombre") or f"Sin modelo ({ficha.get('url') or ficha['tipo_equipo']})"
        nota.append("La página no informa el modelo: se usa el título")
    fecha = ficha.get("fecha") or _hoy()
    citas = "; ".join(f"{CAMPOS[k][0]}: «{c[k]['cita']}»" for k in CAMPOS if tiene(ficha, k) and c[k].get("cita") and k not in ("nombre",))
    sin = [CAMPOS[k][0] for k in faltan(ficha)]
    if sin:
        nota.append("Sin dato: " + ", ".join(sin))
    if citas:
        nota.append("Frases de la página: " + citas)
    m = dict(tipo_equipo=ficha["tipo_equipo"], fabricante=fab or "", modelo=str(modelo)[:120],
             capacidad=valor(ficha, "capacidad"), unidad_capacidad=(c["capacidad"].get("unidad") if tiene(ficha, "capacidad") else ""),
             precio=None, moneda="US$", fecha_precio="", url=ficha.get("url") or "",
             mtbf_h=valor(ficha, "mtbf_h"), mttr_h=valor(ficha, "mttr_h"), disponibilidad=valor(ficha, "disponibilidad"),
             potencia_kw=valor(ficha, "potencia_kw"), largo_m=valor(ficha, "largo_m"), ancho_m=valor(ficha, "ancho_m"),
             alto_m=valor(ficha, "alto_m"), peso_kg=valor(ficha, "peso_kg"), material=valor(ficha, "material", ""),
             garantia_meses=valor(ficha, "garantia_meses"), plazo_entrega_semanas=valor(ficha, "plazo_entrega_semanas"),
             categoria=ficha.get("categoria") or "Internet",
             fuente=f"{ficha.get('origen', 'Tavily')}, {ficha.get('url') or 'sin URL'}, consultado el {fecha}",
             nota=". ".join(nota)[:3000])
    if tiene(ficha, "precio"):
        p = c["precio"]
        m.update(precio=float(p["valor"]), moneda=p.get("moneda") or "US$", fecha_precio=p.get("fecha") or fecha)
    return m


def guardar_ficha(g, ficha: dict) -> dict:
    """Guarda la ficha con guardar_modelo y su precio con registrar_precio. Si la ficha no trae precio y el modelo ya existía, se
    conserva el precio vigente. Devuelve {id, nuevo, precio_registrado}. g: BaseGenericos (datos/genericos.py)."""
    m = ficha_a_modelo(ficha)
    precio = None
    if m["precio"] is not None:
        precio = dict(precio=m["precio"], moneda=m["moneda"], fecha=m["fecha_precio"], url=m["url"], fuente=m["fuente"])
    previo = next((x for x in g.listar_modelos(m["tipo_equipo"]) if x["fabricante"] == m["fabricante"] and x["modelo"] == m["modelo"]), None)
    guardado = dict(m, precio=None, fecha_precio="")
    if previo is not None and precio is None:
        guardado.update(precio=previo["precio"], moneda=previo["moneda"], fecha_precio=previo["fecha_precio"])
    r = g.guardar_modelo(guardado)
    if precio is not None:
        g.registrar_precio(r["id"], precio["precio"], precio["moneda"], precio["fecha"], precio["url"], precio["fuente"],
                           "Precio leído de la página con Tavily")
    return dict(id=r["id"], nuevo=r["nuevo"], precio_registrado=precio is not None)


def ficha_desde_modelo(row: dict) -> dict:
    """Ficha leída de una fila de modelos_comerciales (por ejemplo, una guardada antes con Tavily). Cada dato lleva la URL del
    modelo y la fecha de consulta que quedó en «fuente»."""
    mm = re.search(r"consultado el (\d{4}-\d{2}-\d{2})", row.get("fuente") or "")
    fecha = mm.group(1) if mm else (row.get("fecha_precio") or "")
    origen = "Tavily" if (row.get("categoria") == "Internet") else (row.get("categoria") or "Supuesto")
    f = ficha_vacia(row["tipo_equipo"], row.get("url") or "", fecha, row["modelo"], origen=origen)
    f["categoria"] = row.get("categoria") or "Supuesto"
    c = f["campos"]; url = row.get("url") or ""
    cita = (row.get("fuente") or "")[:160]
    c["nombre"] = campo(row["modelo"], url=url, fecha=fecha, cita=cita)
    c["modelo"] = campo(row["modelo"], url=url, fecha=fecha, cita=cita)
    if row.get("fabricante"):
        c["fabricante"] = campo(row["fabricante"], url=url, fecha=fecha, cita=cita)
    if row.get("capacidad") is not None:
        c["capacidad"] = campo(float(row["capacidad"]), row.get("unidad_capacidad") or "", url, fecha, cita)
    if row.get("precio") is not None:
        c["precio"] = campo(float(row["precio"]), row.get("moneda") or "US$", url, row.get("fecha_precio") or fecha, cita,
                            moneda=row.get("moneda") or "US$")
    for k in ("mtbf_h", "mttr_h", "disponibilidad", "potencia_kw", "largo_m", "ancho_m", "alto_m", "peso_kg", "garantia_meses",
              "plazo_entrega_semanas"):
        if row.get(k) is not None:
            c[k] = campo(float(row[k]), CAMPOS[k][1], url, fecha, cita)
    if row.get("material"):
        c["material"] = campo(row["material"], url=url, fecha=fecha, cita=cita)
    return f


# ---------------------------------------------------------------- hacia motor/seleccion.py
def usd_de_precio(ficha: dict, dolar: float = costos.DOLAR, euro: float = costos.EURO) -> float | None:
    """Precio de la ficha en US$ (None sin precio o con una moneda desconocida)."""
    if not tiene(ficha, "precio"):
        return None
    p = ficha["campos"][("precio")]
    mon = {"US$": "USD", "USD": "USD", "CLP": "CLP", "$": "CLP", "EUR": "EUR", "€": "EUR"}.get(str(p.get("moneda") or "US$").upper())
    if mon is None:
        return None
    return PW.a_usd(float(p["valor"]), mon, dolar, euro)


def ficha_a_fila_catalogo(ficha: dict, unidad: str, tipo_catalogo: str | None = None, dolar: float = costos.DOLAR,
                          euro: float = costos.EURO) -> dict | None:
    """Fila con el formato del catálogo comercial (las claves que lee motor/seleccion.py) o None si la ficha no sirve: sin capacidad
    o con una capacidad que no se puede pasar a la unidad del equipo de la planta. La capacidad se convierte a esa unidad."""
    if not tiene(ficha, "capacidad"):
        return None
    cap = ficha["campos"]["capacidad"]
    v = convertir_capacidad(float(cap["valor"]), _norm_ud(cap.get("unidad") or unidad), unidad)
    if v is None or v <= 0:
        return None
    from . import linea_fluida as LF
    tipo = tipo_catalogo or ficha["tipo_equipo"]
    fab = valor(ficha, "fabricante", "")
    base = valor(ficha, "modelo") or valor(ficha, "nombre") or "Sin modelo"
    modelo = (f"{fab} {base}".strip() if fab and fab.lower() not in str(base).lower() else str(base))[:80]
    mtbf, mttr = valor(ficha, "mtbf_h"), valor(ficha, "mttr_h")
    f_conf = ""
    if mtbf is not None or mttr is not None:
        f_conf = f"{fuente_campo(ficha, 'mtbf_h' if mtbf is not None else 'mttr_h')}"
    A = valor(ficha, "disponibilidad")
    if mtbf is None and mttr is None and A is not None and 0 < A < 1:
        mttr = LF.FALLAS_TIPO[LF.categoria(tipo)][1]
        mtbf = mttr * A / (1.0 - A)
        f_conf = (f"Disponibilidad de la página ({fuente_campo(ficha, 'disponibilidad')}) con el MTTR Supuesto de "
                  f"motor/linea_fluida.py ({str(mttr).replace('.', ',')} h)")
    elif mtbf is not None and mttr is None:
        mttr = LF.FALLAS_TIPO[LF.categoria(tipo)][1]
        f_conf += f"; MTTR Supuesto de motor/linea_fluida.py ({str(mttr).replace('.', ',')} h)"
    elif mtbf is None and mttr is not None:
        mtbf = None; mttr = None; f_conf = ""      # solo el MTTR no define la disponibilidad: se usa el Supuesto por tipo
    usd = usd_de_precio(ficha, dolar, euro)
    anio = None
    if tiene(ficha, "precio"):
        try:
            anio = int(str(ficha["campos"]["precio"].get("fecha") or ficha.get("fecha") or "")[:4])
        except ValueError:
            anio = None
    cat = ficha.get("categoria") or "Internet"
    return dict(tipo=tipo, modelo=modelo, magnitud="Capacidad", capacidad=float(v), unidad=unidad,
                fuente_capacidad=f"{fuente_campo(ficha, 'capacidad')}", mtbf_h=mtbf, mttr_h=mttr, fuente_confiabilidad=f_conf,
                precio_usd=usd, anio_precio=anio, fuente_precio=fuente_campo(ficha, "precio") if usd is not None else "",
                largo_m=valor(ficha, "largo_m"), ancho_m=valor(ficha, "ancho_m"), alto_m=valor(ficha, "alto_m"),
                fuente_dimensiones=fuente_campo(ficha, "largo_m") if tiene(ficha, "largo_m") else "Sin dato en la ficha",
                potencia_kw=valor(ficha, "potencia_kw"), peso_kg=valor(ficha, "peso_kg"), material=valor(ficha, "material", ""),
                garantia_meses=valor(ficha, "garantia_meses"), plazo_entrega_semanas=valor(ficha, "plazo_entrega_semanas"),
                fuente_potencia=fuente_campo(ficha, "potencia_kw") if tiene(ficha, "potencia_kw") else "Sin dato en la ficha",
                categoria=cat, url=ficha.get("url") or "", origen_ficha=ficha.get("origen", ""))


def filas_de_fichas(fichas: list[dict], unidad: str, tipo_catalogo: str | None = None, dolar: float = costos.DOLAR,
                    euro: float = costos.EURO) -> tuple[list[dict], list[dict]]:
    """Fichas → filas del catálogo para motor/seleccion.py, con nombres de modelo únicos. Devuelve (filas, descartadas); una ficha se
    descarta si no trae capacidad o si su unidad no se puede pasar a la del equipo (se dice por qué)."""
    filas, malas, vistos = [], [], {}
    for f in fichas:
        r = ficha_a_fila_catalogo(f, unidad, tipo_catalogo, dolar, euro)
        if r is None:
            motivo = "sin capacidad" if not tiene(f, "capacidad") else \
                f"la capacidad ({texto_campo(f, 'capacidad')}) no se puede pasar a {unidad}"
            malas.append(dict(ficha=f, motivo=motivo))
            continue
        n = vistos.get(r["modelo"], 0) + 1
        vistos[r["modelo"]] = n
        if n > 1:
            r["modelo"] = f"{r['modelo']} ({n})"
        filas.append(r)
    return filas, malas
