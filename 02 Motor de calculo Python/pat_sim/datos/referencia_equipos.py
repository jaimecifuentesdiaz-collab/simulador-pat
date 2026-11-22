"""Base de respaldo de equipos reales por tipo y su ajuste de Williams (PAT 139, equipo E2, 14-11-2026; puntos 2 y 3 de los
comentarios del profesor Torres).

Qué hace
- Tabla equipos_referencia en la misma SQLite de BaseDatos (sin editar bd.py, con el patrón de precios_web.py y genericos.py): cada fila es
  un equipo real con fabricante, modelo, capacidad, precio, fecha, URL, potencia, medidas, peso, material y lo que la página dice de
  confiabilidad. Se siembra sola e idempotente (INSERT OR IGNORE: no pisa lo que el docente edite) desde referencia_equipos_datos.py. El
  mismo contenido queda en «03 Base de datos/equipos_referencia_PAT139.csv» (exportar_csv).
- Por tipo hay tres puntos («minimo», «medio», «maximo»); además hay filas «adicional». Lo que la página no dice queda «sin dato» (NULL).
- ajustar_williams: regresión log-log C = C1·(S/S1)^n con los puntos de precio puntual y creíble (usar_en_ajuste = 1). Con menos de dos
  puntos usa el exponente de motor/costeo.py (EXPONENTES, o 0,6 Supuesto) y lo dice.
- precio_williams: precio de cualquier tamaño con ese ajuste, actualizado con el CEPCI cuando hay índice del año del precio, y con aviso
  si extrapola fuera del rango de los puntos. Sin ningún punto con precio usa la correlación de bibliografía de costeo.py (Supuesto).
- candidatos: lo que se puede comprar para una etapa: fichas de Tavily en vivo (motor/fichas.buscar_fichas) cuando hay clave y red, las
  referencias de la base y, si ninguna calza con el tamaño pedido, una opción «Williams» del tamaño justo. Cada una con su origen y fuente.
- estado_tavily: prueba la clave con GET /usage de Tavily (consulta de uso: no es una búsqueda) y guarda el resultado 10 minutos.

Supuestos declarados
- Conversión de t/h de producto a kW térmicos (hot break y esterilizador) con las temperaturas y el calor específico de la base de
  escenarios/agrozzi.py; t/h de vapor a kW con el calor de vaporización de costeo.DH_VAPOR; litros por hora a t/h con densidad 1.
- Una referencia «calza» si su capacidad está a ±20 % de la pedida (CALZA).
- Precio puntual: la página ata un precio a un modelo con su capacidad. Un rango de la serie o el mismo precio para tamaños distintos
  no es puntual y no entra al ajuste ni al precio del candidato (se estima con Williams y se marca).
Nunca se guardan claves en archivos: la clave viene de st.secrets, del argumento secretos o de la variable TAVILY_API_KEY.
"""
from __future__ import annotations
import csv, hashlib, json, math, time, urllib.error, urllib.request
from datetime import datetime
from pathlib import Path

from . import precios_web as PW
from . import referencia_equipos_datos as DAT
from ..motor import costeo as CO, fichas as FI

TABLA = "equipos_referencia"
PUNTOS = ("minimo", "medio", "maximo", "adicional")
CALZA = 0.20                     # Supuesto: una referencia calza si su capacidad está a ±20 % de la pedida
N_MIN, N_MAX = 0.05, 1.5         # un n fuera de esta banda no es físico: se descarta el ajuste y se usa el de costeo.py
URL_USO_TAVILY = "https://api.tavily.com/usage"
TTL_ESTADO_S = 600.0             # caché de 10 minutos del estado de Tavily
TTL_BUSQUEDA_S = 600.0           # caché de 10 minutos de las búsquedas de fichas (cada búsqueda gasta un crédito)
TIMEOUT_USO_S = 10.0
RUTA_CSV = Path(__file__).resolve().parents[3] / "03 Base de datos" / "equipos_referencia_PAT139.csv"

UNIDAD_TIPO = DAT.UNIDAD_TIPO
NOMBRE_TIPO = DAT.NOMBRE_TIPO

COLUMNAS = ("tipo", "punto", "fabricante", "modelo", "nombre_pagina", "proveedor", "capacidad", "unidad", "cap_original", "unidad_original",
            "nota_conversion", "precio_texto", "precio_usd", "moneda", "precio_puntual", "usar_en_ajuste", "anio_precio",
            "fecha_consulta", "url", "potencia_kw", "largo_m", "ancho_m", "alto_m", "peso_kg", "material", "garantia_meses",
            "plazo_entrega_semanas", "mtbf_h", "mttr_h", "confiabilidad_texto", "categoria", "nota")

ESQUEMA = f"""
CREATE TABLE IF NOT EXISTS {TABLA} (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,
    punto TEXT NOT NULL CHECK (punto IN ('minimo', 'medio', 'maximo', 'adicional')),
    fabricante TEXT NOT NULL DEFAULT '',
    modelo TEXT NOT NULL,
    nombre_pagina TEXT,
    proveedor TEXT,
    capacidad REAL,
    unidad TEXT NOT NULL DEFAULT '',
    cap_original REAL,
    unidad_original TEXT NOT NULL DEFAULT '',
    nota_conversion TEXT NOT NULL DEFAULT '',
    precio_texto TEXT,
    precio_usd REAL,
    moneda TEXT NOT NULL DEFAULT 'US$',
    precio_puntual INTEGER NOT NULL DEFAULT 0,
    usar_en_ajuste INTEGER NOT NULL DEFAULT 0,
    anio_precio INTEGER,
    fecha_consulta TEXT NOT NULL DEFAULT '',
    url TEXT NOT NULL DEFAULT '',
    potencia_kw REAL,
    largo_m REAL,
    ancho_m REAL,
    alto_m REAL,
    peso_kg REAL,
    material TEXT,
    garantia_meses REAL,
    plazo_entrega_semanas REAL,
    mtbf_h REAL,
    mttr_h REAL,
    confiabilidad_texto TEXT,
    categoria TEXT NOT NULL DEFAULT 'Internet',
    nota TEXT,
    modificado TEXT NOT NULL DEFAULT '',
    UNIQUE (tipo, fabricante, modelo)
);
CREATE INDEX IF NOT EXISTS ix_equipos_ref_tipo ON {TABLA}(tipo, punto);
"""


# ---------------------------------------------------------------- formato chileno
def _cl(v, d: int = 2, g: bool = False) -> str:
    """Número con coma decimal (y punto de miles si g): _cl(0.6) = «0,60»; _cl(12345.6, 0, True) = «12.346»."""
    t = f"{float(v):,.{d}f}" if g else f"{float(v):.{d}f}"
    return t.replace(",", "X").replace(".", ",").replace("X", ".")


def _cg(v, d: int = 4) -> str:
    """Número con cifras significativas y coma decimal: _cg(62.64) = «62,64»; sin notación científica y con punto de miles
    (PAT 139: _cg(15956) = «15.956»)."""
    v = float(v)
    if v == 0:
        return "0"
    import math
    dec = max(0, d - 1 - int(math.floor(math.log10(abs(v)))))
    t = f"{round(v, dec):,.{dec}f}"
    if "." in t:
        t = t.rstrip("0").rstrip(".")
    return t.replace(",", "§").replace(".", ",").replace("§", ".")


# ---------------------------------------------------------------- conversión de unidades
def _norm(u: str | None) -> str:
    t = (u or "").strip()
    bajo = t.lower().replace("³", "3").replace("²", "2")
    return {"l/h": "L/h", "kw": "kW", "hp": "hp", "t/h": "t/h", "tph": "t/h", "kg/h": "kg/h", "m3/h": "m3/h", "m2": "m2", "sq ft": "sq ft",
            "l": "L", "m3": "m3", "t/h vapor": "t/h vapor", "kg/h vapor": "kg/h vapor"}.get(bajo, t)


def kw_por_t_h(tipo: str) -> float | None:
    """kW térmicos por cada t/h de producto (Supuesto, con las cifras de la base de escenarios/agrozzi.py):
    hot break = cp·ΔT con cp = 3,98 kJ/(kg·K) del tomate y ΔT = 90 − 25 °C; esterilizador = cp·ΔT con el cp de la pasta de 30 °Brix
    ((1 − xP)·4,18 + xP·1,5) y ΔT = 103 − 55,57 °C (salida del esterilizador menos salida del último efecto). Caldera: t/h de vapor
    por el calor de vaporización costeo.DH_VAPOR (2.360 kJ/kg). None si el tipo no se mide en kW."""
    from ..escenarios import agrozzi as AG
    B = AG.BASE
    if tipo == "hot_break":
        return 1000.0 / 3600.0 * B["cpt"] * (B["Thb"] - B["Tin"])
    if tipo == "esterilizador":
        cp = (1 - B["xP"]) * 4.18 + B["xP"] * B["cps"]
        return 1000.0 / 3600.0 * cp * (B["Tst"] - B["TN"])
    if tipo == "caldera_gas":
        return 1000.0 * CO.DH_VAPOR / 3600.0
    return None


def convertir(tipo: str, valor: float, de: str, a: str) -> float | None:
    """Pasa una capacidad entre unidades (kg/h, t/h, L/h, m3/h con densidad 1 Supuesto; hp a kW; sq ft a m2; L a m3; t/h de producto o
    de vapor a kW según el tipo). None si no se puede."""
    de, a = _norm(de), _norm(a)
    if valor is None:
        return None
    v = float(valor)
    if de == a:
        return v
    # unidades simples
    simple = {("hp", "kW"): 0.7457, ("kW", "hp"): 1 / 0.7457, ("sq ft", "m2"): 0.09290304, ("m2", "sq ft"): 1 / 0.09290304,
              ("L", "m3"): 1e-3, ("m3", "L"): 1e3}
    if (de, a) in simple:
        return v * simple[(de, a)]
    # flujos a t/h (densidad 1 para L/h y m3/h: Supuesto)
    a_th = {"t/h": 1.0, "kg/h": 1e-3, "L/h": 1e-3, "m3/h": 1.0, "t/h vapor": 1.0, "kg/h vapor": 1e-3}
    if de in a_th and a in a_th and (de.endswith("vapor")) == (a.endswith("vapor")):
        return v * a_th[de] / a_th[a]
    f = kw_por_t_h(tipo)
    if f is not None:
        if a == "kW" and de in a_th and (tipo == "caldera_gas") == de.endswith("vapor"):
            return v * a_th[de] * f
        if de == "kW" and a in a_th and (tipo == "caldera_gas") == a.endswith("vapor"):
            return v / f / a_th[a]
    return None


def _nota_conversion(tipo: str, v0, de: str, a: str) -> str:
    de, a = _norm(de), _norm(a)
    if de == a:
        return ""
    f = kw_por_t_h(tipo)
    if a == "kW" and f is not None:
        base = ("t/h de vapor × 2.360 kJ/kg (costeo.DH_VAPOR)" if tipo == "caldera_gas" else
                f"t/h de producto × {_cl(f, 1)} kW por t/h (Supuesto con las cifras de escenarios/agrozzi.py)")
        extra = "; L/h a t/h con densidad 1 (Supuesto)" if de in ("L/h", "m3/h") else ""
        return f"{_cg(v0)} {de} pasan a kW: {base}{extra}"
    if de in ("L/h", "m3/h") and a == "t/h":
        return f"{_cg(v0)} {de} pasan a t/h con densidad 1 (Supuesto)"
    return f"{_cg(v0)} {de} pasan a {a}"


# ---------------------------------------------------------------- base de datos
def _bd(bd):
    from .bd import BaseDatos
    if bd is None or isinstance(bd, (str, Path)):
        return BaseDatos(bd) if bd else BaseDatos()
    return bd


def _filas_semilla() -> list[dict]:
    """Filas de referencia_equipos_datos.py con la capacidad pasada a la unidad de trabajo del tipo."""
    out = []
    for r in DAT.FILAS:
        tipo = r["tipo"]; u = UNIDAD_TIPO[tipo]
        cap = convertir(tipo, r["cap_original"], r["unidad_original"], u) if r["cap_original"] is not None else None
        d = {k: r.get(k) for k in COLUMNAS if k in r}
        d.update(capacidad=cap, unidad=u, nota_conversion=_nota_conversion(tipo, r["cap_original"], r["unidad_original"], u)
                 if r["cap_original"] is not None else "")
        out.append({k: d.get(k) for k in COLUMNAS})
    return out


def sembrar(bd=None) -> int:
    """Crea la tabla y siembra las referencias que falten (INSERT OR IGNORE: es idempotente y no pisa lo que se edite).
    Devuelve cuántas filas nuevas agregó."""
    base = _bd(bd)
    filas = _filas_semilla()
    n = 0
    with PW._conexion(base) as con:
        con.executescript(ESQUEMA)
        antes = con.execute(f"SELECT COUNT(*) FROM {TABLA}").fetchone()[0]
        if antes >= len(filas):
            return 0
        ahora = datetime.now().isoformat(timespec="seconds")
        cols = list(COLUMNAS) + ["modificado"]
        sql = f"INSERT OR IGNORE INTO {TABLA} ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})"
        for f in filas:
            n += con.execute(sql, [f[c] if c in f else None for c in COLUMNAS] + [ahora]).rowcount
    return n


def referencias(tipo: str, bd=None, solo_puntos: bool = False) -> list[dict]:
    """Referencias de un tipo, ordenadas por capacidad (las sin capacidad al final). Cada dict trae todas las columnas de la tabla.
    solo_puntos=True deja solo «minimo», «medio» y «maximo»."""
    base = _bd(bd)
    sembrar(base)
    with PW._conexion(base) as con:
        cur = con.execute(f"SELECT * FROM {TABLA} WHERE tipo = ?" + (" AND punto != 'adicional'" if solo_puntos else ""), (tipo,))
        nombres = [d[0] for d in cur.description]
        filas = [dict(zip(nombres, tuple(f))) for f in cur.fetchall()]
    filas.sort(key=lambda r: (r["capacidad"] is None, r["capacidad"] or 0.0, r["id"]))
    return filas


def tipos(bd=None) -> list[str]:
    """Tipos con referencias en la base."""
    base = _bd(bd)
    sembrar(base)
    with PW._conexion(base) as con:
        return [r[0] for r in con.execute(f"SELECT DISTINCT tipo FROM {TABLA} ORDER BY tipo")]


def exportar_csv(ruta: str | Path | None = None, bd=None) -> Path:
    """Escribe todas las referencias en un CSV legible (UTF-8 con BOM para Excel, separador «;», coma decimal). Lo que la página no dice
    sale como «sin dato»."""
    ruta = Path(ruta) if ruta else RUTA_CSV
    ruta.parent.mkdir(parents=True, exist_ok=True)
    cols = ("id",) + COLUMNAS
    with open(ruta, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh, delimiter=";", quoting=csv.QUOTE_MINIMAL)
        w.writerow(cols)
        for t in tipos(bd):
            for r in referencias(t, bd):
                w.writerow([r[c] if c == "id" else ("sin dato" if r[c] in (None, "") else
                                                    (_cl(r[c], 6).rstrip("0").rstrip(",") if isinstance(r[c], float) else r[c])) for c in cols])
    return ruta


# ---------------------------------------------------------------- exponente y ajuste de Williams
def _n_costeo(tipo: str) -> tuple[float, str, str]:
    """Exponente de motor/costeo.py del tipo: (n, fuente, categoría). Sin dato, 0,6 Supuesto."""
    return CO.exponente(DAT.CLAVE_COSTEO.get(tipo, tipo))


def _puntos_ajuste(tipo: str, bd=None) -> list[dict]:
    return [r for r in referencias(tipo, bd) if r["usar_en_ajuste"] and r["precio_usd"] and r["capacidad"] and r["capacidad"] > 0]


def _regresion(puntos: list[tuple[float, float]]) -> dict | None:
    """Regresión log-log ln C = a + n·ln S por mínimos cuadrados. puntos: [(S, C)]. Devuelve {n, C1, S1, r2} con S1 el tamaño medio
    geométrico y C1 el precio del ajuste en S1 (C = C1·(S/S1)^n); None si no hay variación de tamaño o hay menos de dos puntos."""
    pts = [(float(s), float(c)) for s, c in puntos if s and c and s > 0 and c > 0]
    if len(pts) < 2:
        return None
    x = [math.log(s) for s, _ in pts]; y = [math.log(c) for _, c in pts]
    mx, my = sum(x) / len(x), sum(y) / len(y)
    sxx = sum((xi - mx) ** 2 for xi in x)
    if sxx < 1e-12:
        return None
    n = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) / sxx
    syy = sum((yi - my) ** 2 for yi in y)
    r2 = 1.0 if syy < 1e-15 else (sum((xi - mx) * (yi - my) for xi, yi in zip(x, y)) ** 2) / (sxx * syy)
    return dict(n=n, C1=math.exp(my), S1=math.exp(mx), r2=r2)


def ajustar_williams(tipo: str, bd=None, puntos: list | None = None) -> dict:
    """Ajuste del exponente n de Williams del tipo: {n, C1, S1, r2, puntos, metodo, fuente_n, aviso}.
    Con dos o más puntos de precio puntual (capacidad y precio en US$) hace la regresión log-log (r2 = 1 con dos puntos). Con menos de
    dos, o con un ajuste no físico (n fuera de 0,05 a 1,5), usa el n de motor/costeo.py y lo dice en «aviso» (metodo «costeo»).
    puntos (opcional, para pruebas): [(capacidad, precio_usd)] en lugar de los de la base."""
    n_c, fuente_c, cat_c = _n_costeo(tipo)
    if puntos is None:
        filas = _puntos_ajuste(tipo, bd)
        pts = [(r["capacidad"], r["precio_usd"]) for r in filas]
        det = [dict(modelo=r["modelo"], fabricante=r["fabricante"], capacidad=r["capacidad"], precio_usd=r["precio_usd"], url=r["url"])
               for r in filas]
    else:
        pts = [(float(s), float(c)) for s, c in puntos]
        det = [dict(modelo="", fabricante="", capacidad=s, precio_usd=c, url="") for s, c in pts]
    rg = _regresion(pts)
    if rg is not None and N_MIN <= rg["n"] <= N_MAX:
        return dict(n=rg["n"], C1=rg["C1"], S1=rg["S1"], r2=rg["r2"], puntos=det, metodo="regresión",
                    fuente_n=f"Regresión log-log con {len(pts)} equipos reales con precio ({UNIDAD_TIPO.get(tipo, '')})", aviso="")
    if rg is not None:
        aviso = (f"El ajuste con {len(pts)} puntos dio n = {_cl(rg['n'])}, fuera de la banda física ({_cl(N_MIN)} a {_cl(N_MAX)}): se usa el "
                 f"exponente de costeo.py (n = {_cl(n_c)}, {cat_c}).")
    elif len(pts) == 1:
        aviso = (f"Hay un solo equipo real con precio puntual para «{tipo}»: no alcanza para una regresión; se usa el exponente de "
                 f"costeo.py (n = {_cl(n_c)}, {cat_c}).")
    else:
        aviso = (f"No hay equipos reales con precio puntual para «{tipo}»: se usa el exponente de costeo.py (n = {n_c:.2f}, {cat_c}) "
                 "y el precio de bibliografía.")
    C1, S1 = (pts[0][1], pts[0][0]) if len(pts) == 1 else (None, None)
    return dict(n=n_c, C1=C1, S1=S1, r2=None, puntos=det, metodo="costeo", fuente_n=f"{fuente_c} ({cat_c})", aviso=aviso)


def precio_williams(tipo: str, capacidad: float, bd=None, cepci_hoy: float = CO.CEPCI_HOY, puntos: list | None = None) -> dict:
    """Precio en US$ de un equipo del tipo y la capacidad pedida (en la unidad de trabajo del tipo, UNIDAD_TIPO):
    {precio_usd, n, fuente, metodo, extrapola, rango, avisos, ...}.
    Con dos o más puntos reales: C1·(S/S1)^n de la regresión (interpola dentro del rango y avisa si extrapola). Con un punto: Williams
    desde ese punto con el n de costeo.py. Sin puntos: correlación de bibliografía de costeo.py (Supuesto). La actualización con el CEPCI
    se hace cuando existe el índice del año del precio (CEPCI_ANUAL llega a 2023): los precios de 2026 de las referencias no tienen
    índice público y se usan sin actualizar, con aviso."""
    if capacidad is None or capacidad <= 0:
        raise ValueError("La capacidad debe ser positiva")
    aj = ajustar_williams(tipo, bd, puntos)
    avisos = [aj["aviso"]] if aj["aviso"] else []
    caps = [p["capacidad"] for p in aj["puntos"]]
    rango = (min(caps), max(caps)) if caps else None
    extrapola = bool(rango) and (capacidad < rango[0] * (1 - 1e-9) or capacidad > rango[1] * (1 + 1e-9))
    if extrapola:
        lo, hi = rango
        razon = capacidad / hi if capacidad > hi else capacidad / lo
        avisos.append(f"Extrapola: {_cg(capacidad)} {UNIDAD_TIPO.get(tipo, '')} está fuera del rango de los equipos reales "
                      f"({_cg(lo)} a {_cg(hi)}), a {_cg(razon, 3)} veces el borde más cercano; el precio es menos confiable.")
    if aj["C1"] is not None and aj["S1"]:
        C = CO.williams(aj["C1"], aj["S1"], capacidad, aj["n"])
        anio = ANIO_PRECIO_REFERENCIAS
        cepci_ref = CO.cepci_de(anio)
        C_hoy, f = CO.actualizar(C, cepci_ref, cepci_hoy)
        if not cepci_ref:
            avisos.append(f"Precios de {anio}: sin CEPCI público de ese año; se usan sin actualizar (factor 1).")
        fuente = (f"Williams con n = {_cl(aj['n'], 3)} ({aj['fuente_n']}); precio de referencia US$ {_cl(aj['C1'], 0, True)} a "
                  f"{_cg(aj['S1'])} {UNIDAD_TIPO.get(tipo, '')}")
        return dict(precio_usd=float(C_hoy), n=aj["n"], fuente=fuente, metodo=aj["metodo"], extrapola=extrapola, rango=rango, avisos=avisos,
                    factor_cepci=f, r2=aj["r2"], puntos=len(aj["puntos"]), url="", fecha=ANIO_PRECIO_REFERENCIAS)
    # sin ningún punto con precio: correlación de bibliografía de costeo.py
    clave = DAT.CLAVE_COSTEO.get(tipo, tipo)
    b = _bibliografia(tipo, clave, capacidad, aj["n"])
    if b is None:
        avisos.append(f"Sin precio para «{tipo}»: no hay equipo real con precio ni correlación de bibliografía.")
        return dict(precio_usd=None, n=aj["n"], fuente="sin dato", metodo="sin dato", extrapola=False, rango=None, avisos=avisos,
                    factor_cepci=1.0, r2=None, puntos=0, url="", fecha="")
    return dict(b, n=aj["n"], extrapola=False, rango=None, avisos=[a for a in avisos if a], r2=None, puntos=0)


ANIO_PRECIO_REFERENCIAS = DAT.ANIO


def _bibliografia(tipo: str, clave: str, capacidad: float, n: float) -> dict | None:
    """Precio de bibliografía de costeo.py (REFERENCIAS) escalado al tamaño pedido con Williams y actualizado con el CEPCI."""
    ref = CO.REFERENCIAS.get(clave)
    ud_ref = ref["unidad"] if ref else None
    if ref is not None and ud_ref == UNIDAD_TIPO.get(tipo):
        b = CO.precio_bibliografia(clave, capacidad)
        S1, C1 = b["tamano"], b["precio_usd"]
        C2 = CO.williams(C1, S1, capacidad, n) if not b.get("exacto") else C1
        C_hoy, f = CO.actualizar(C2, b.get("cepci_ref"), CO.CEPCI_HOY)
        return dict(precio_usd=float(C_hoy), fuente=f"Bibliografía de costeo.py ({b['fuente']}), {b['categoria']}; n = {_cl(n)}",
                    metodo="bibliografía", factor_cepci=f, url=b.get("url", ""), fecha=b.get("fecha", ""))
    if tipo == "estanque_pulmon":              # Supuesto de motor/auxiliares.py: US$ 20.000 por un estanque de 10 m3 (año 2023)
        C2 = CO.williams(20000.0, 10.0, capacidad, n)
        C_hoy, f = CO.actualizar(C2, CO.cepci_de(2023), CO.CEPCI_HOY)
        return dict(precio_usd=float(C_hoy), fuente=f"Supuesto de motor/auxiliares.py: US$ 20.000 por 10 m3 (2023), Williams n = {_cl(n)}",
                    metodo="bibliografía", factor_cepci=f, url="", fecha="2023")
    return None


# ---------------------------------------------------------------- estado de Tavily
_ESTADO: dict = {}
_BUSQUEDAS: dict = {}


def _huella(clave: str) -> str:
    return hashlib.sha256(clave.encode("utf-8")).hexdigest()[:16]


def estado_tavily(secretos=None, forzar: bool = False, _abrir=None, _ahora=time.time) -> dict:
    """¿Tavily está en línea? Prueba la clave con GET https://api.tavily.com/usage (consulta de uso de la cuenta: no es una búsqueda, así
    que no gasta créditos de búsqueda; la documentación no declara cobro) y guarda el resultado 10 minutos en memoria (solo una huella de
    la clave, nunca la clave ni archivos). Devuelve {en_linea, motivo, creditos_usados, limite, plan, verificado, desde_cache}.
    Sin clave, sin red, clave rechazada (401), límite de tasa (429) o créditos agotados: en_linea False con el motivo."""
    clave = PW.obtener_clave(secretos)
    if not clave:
        return dict(en_linea=False, motivo="Sin clave de Tavily: falta TAVILY_API_KEY en .streamlit/secrets.toml o en el entorno. Se usa el respaldo de equipos de referencia y el índice de Williams.",
                    creditos_usados=None, limite=None, plan=None, verificado=None, desde_cache=False)
    h = _huella(clave)
    ahora = _ahora()
    previo = _ESTADO.get(h)
    if previo and not forzar and ahora - previo["t"] < TTL_ESTADO_S and _abrir is None:
        return dict(previo["estado"], desde_cache=True)
    estado = _consultar_uso(clave, _abrir)
    estado["verificado"] = datetime.fromtimestamp(ahora).isoformat(timespec="seconds")
    estado["desde_cache"] = False
    if _abrir is None:
        _ESTADO[h] = dict(t=ahora, estado=estado)
    return estado


def _consultar_uso(clave: str, _abrir=None) -> dict:
    base = dict(en_linea=False, motivo="", creditos_usados=None, limite=None, plan=None)
    req = urllib.request.Request(URL_USO_TAVILY, method="GET", headers={"Authorization": f"Bearer {clave}", "Accept": "application/json"})
    abrir = _abrir or urllib.request.urlopen
    try:
        with abrir(req, timeout=TIMEOUT_USO_S) as resp:
            datos = resp.read()
        j = json.loads(datos.decode("utf-8") if isinstance(datos, bytes) else datos)
    except urllib.error.HTTPError as e:
        if e.code == 401:
            base["motivo"] = "Tavily rechazó la clave (401): está mal escrita o vencida."
        elif e.code == 429:
            base["motivo"] = "Tavily respondió 429 (demasiadas consultas): se reintenta más tarde."
        else:
            base["motivo"] = f"Tavily respondió con error HTTP {e.code}."
        return base
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        base["motivo"] = f"Sin conexión con Tavily ({type(e).__name__}): se usa el respaldo."
        return base
    except Exception as e:               # respuesta que no es JSON u otro fallo: no se levanta hacia la interfaz
        base["motivo"] = f"Respuesta ilegible de Tavily ({type(e).__name__})."
        return base
    key = j.get("key") or {}; cuenta = j.get("account") or {}
    usado = key.get("usage", cuenta.get("plan_usage")); limite = key.get("limit", cuenta.get("plan_limit"))
    base.update(creditos_usados=usado, limite=limite, plan=cuenta.get("current_plan"))
    if usado is not None and limite not in (None, 0) and usado >= limite:
        base["motivo"] = f"Créditos de Tavily agotados ({usado:g} de {limite:g}): se usa el respaldo."
        return base
    base.update(en_linea=True, motivo="Conectado con Tavily" + (f": {usado:g} de {limite:g} créditos usados" if usado is not None and limite else
                                                              (f": {usado:g} créditos usados, sin límite" if usado is not None else "")) + ".")
    return base


# ---------------------------------------------------------------- candidatos
def _num(v):
    return None if v is None else float(v)


def _candidato_de_referencia(r: dict, unidad: str, tipo: str, bd) -> dict | None:
    cap = convertir(tipo, r["capacidad"], r["unidad"], unidad) if r["capacidad"] is not None else None
    if cap is None or cap <= 0:
        return None
    if r["precio_puntual"] and r["precio_usd"]:
        precio, estimado = float(r["precio_usd"]), False
        fuente_precio = f"{r['precio_texto']}, {r['url']}, consultado el {r['fecha_consulta']}"
    else:
        pwr = precio_williams(tipo, r["capacidad"], bd)
        precio, estimado = pwr.get("precio_usd"), True
        motivo = r["precio_texto"] or "sin precio puntual en la página"
        fuente_precio = (f"Precio estimado con Williams ({pwr.get('fuente', 'sin dato')}); la página dice: {motivo}; {r['url']}, "
                         f"consultado el {r['fecha_consulta']}")
    if precio is None:
        return None
    return dict(
        id=f"ref:{r['id']}", modelo=r["modelo"], fabricante=r["fabricante"], n=1, k=1, capacidad=float(cap), unidad=unidad,
        precio_usd=float(precio), precio_estimado=estimado, origen="Respaldo", url=r["url"],
        fuente=f"Equipo real de referencia ({r['punto']}), {fuente_precio}", fecha=r["fecha_consulta"], potencia_kw=_num(r["potencia_kw"]),
        largo_m=_num(r["largo_m"]), ancho_m=_num(r["ancho_m"]), alto_m=_num(r["alto_m"]), peso_kg=_num(r["peso_kg"]), material=r["material"],
        garantia_meses=_num(r["garantia_meses"]), plazo_entrega_semanas=_num(r["plazo_entrega_semanas"]), mtbf_h=_num(r["mtbf_h"]),
        mttr_h=_num(r["mttr_h"]), confiabilidad=r["confiabilidad_texto"], nota=r["nota"] or "", punto=r["punto"],
        usar_en_ajuste=bool(r["usar_en_ajuste"]))


def _candidato_de_ficha(f: dict, tipo: str, cap_req: float, unidad: str, bd) -> dict | None:
    """Candidato desde una ficha de Tavily (motor/fichas.py). Sin capacidad legible en la unidad pedida, la ficha no sirve."""
    if not FI.tiene(f, "capacidad"):
        return None
    c = f["campos"]["capacidad"]
    ud0 = _norm(c.get("unidad") or unidad)
    cap = convertir(tipo, float(c["valor"]), ud0, unidad)
    if cap is None:
        cap = FI.convertir_capacidad(float(c["valor"]), FI._norm_ud(ud0), unidad)
    if cap is None or cap <= 0:
        return None
    usd = FI.usd_de_precio(f)
    estimado = usd is None
    if estimado:
        pwr = precio_williams(tipo, cap, bd)
        usd = pwr.get("precio_usd")
        if usd is None:
            return None
        fuente_precio = f"La página no trae precio legible; precio estimado con Williams ({pwr['fuente']})"
    else:
        fuente_precio = f"Precio de la página: {FI.texto_campo(f, 'precio')}"
    fab = FI.valor(f, "fabricante", "") or "sin dato"
    modelo = FI.valor(f, "modelo") or FI.valor(f, "nombre") or "sin dato"
    return dict(
        id=f"tavily:{hashlib.sha1((f.get('url') or str(modelo)).encode()).hexdigest()[:10]}", modelo=str(modelo)[:120], fabricante=fab,
        n=1, k=1, capacidad=float(cap), unidad=unidad, precio_usd=float(usd), precio_estimado=estimado, origen="Tavily", url=f.get("url", ""),
        fuente=f"Tavily, {f.get('url') or 'sin URL'}, consultado el {f.get('fecha')}. {fuente_precio}", fecha=f.get("fecha", ""),
        potencia_kw=FI.valor(f, "potencia_kw"), largo_m=FI.valor(f, "largo_m"), ancho_m=FI.valor(f, "ancho_m"), alto_m=FI.valor(f, "alto_m"),
        peso_kg=FI.valor(f, "peso_kg"), material=FI.valor(f, "material"), garantia_meses=FI.valor(f, "garantia_meses"),
        plazo_entrega_semanas=FI.valor(f, "plazo_entrega_semanas"), mtbf_h=FI.valor(f, "mtbf_h"), mttr_h=FI.valor(f, "mttr_h"),
        confiabilidad=None, nota=f"Ficha leída de la página con expresiones regulares; campos sin dato: {', '.join(FI.faltan(f)) or 'ninguno'}",
        punto="tavily", usar_en_ajuste=False)


def _buscar(tipo: str, cap: float, unidad: str, clave: str, _abrir=None, _ahora=time.time) -> dict:
    """Búsqueda de fichas con caché de 10 minutos (cada búsqueda real gasta un crédito)."""
    k = (tipo, round(cap, 3), unidad)
    previo = _BUSQUEDAS.get(k)
    if previo and _ahora() - previo[0] < TTL_BUSQUEDA_S and _abrir is None:
        return previo[1]
    r = FI.buscar_fichas(tipo, cap, unidad, clave, nombre=NOMBRE_TIPO.get(tipo), max_resultados=5, _abrir=_abrir)
    if _abrir is None and r.get("fichas"):
        _BUSQUEDAS[k] = (_ahora(), r)
    return r


def candidatos_con_avisos(tipo: str, capacidad_requerida: float, unidad: str | None = None, en_linea: bool = True, secretos=None, bd=None,
                          _abrir=None) -> dict:
    """Igual que candidatos pero devuelve {candidatos, avisos, tavily}: avisos dice por qué no hubo búsqueda en línea (sin clave, sin red)
    y si la opción Williams se agregó."""
    base = _bd(bd)
    sembrar(base)
    unidad = unidad or UNIDAD_TIPO.get(tipo, "")
    avisos, cands = [], []
    if capacidad_requerida is None or capacidad_requerida <= 0:
        return dict(candidatos=[], avisos=["La capacidad requerida debe ser positiva."], tavily=estado_tavily(secretos))
    tav = dict(en_linea=False, motivo="Búsqueda en línea no pedida.")
    if en_linea:
        tav = estado_tavily(secretos, _abrir=_abrir) if _abrir is not None else estado_tavily(secretos)
        if tav["en_linea"]:
            clave = PW.obtener_clave(secretos)
            try:
                res = _buscar(tipo, capacidad_requerida, unidad, clave, _abrir=_abrir)
                avisos += list(res.get("avisos", []))
                for f in res.get("fichas", []):
                    c = _candidato_de_ficha(f, tipo, capacidad_requerida, unidad, base)
                    if c is not None:
                        cands.append(c)
                if not cands and not res.get("avisos"):
                    avisos.append("Tavily no trajo páginas con capacidad legible en la unidad pedida: se usa el respaldo.")
            except Exception as e:                         # nada de esto levanta errores hacia la interfaz
                avisos.append(f"Falló la búsqueda en Tavily ({type(e).__name__}): se usa el respaldo.")
        else:
            avisos.append(tav["motivo"])
    for r in referencias(tipo, base):
        c = _candidato_de_referencia(r, unidad, tipo, base)
        if c is not None:
            cands.append(c)
    calza = any(abs(math.log(c["capacidad"] / capacidad_requerida)) <= math.log(1 + CALZA) for c in cands)
    if not calza:
        w = precio_williams(tipo, convertir(tipo, capacidad_requerida, unidad, UNIDAD_TIPO.get(tipo, unidad)) or capacidad_requerida, base)
        if w.get("precio_usd") is not None:
            cands.append(dict(
                id=f"williams:{tipo}:{capacidad_requerida:.6g}", modelo=f"Equipo de {_cg(capacidad_requerida)} {unidad} (índice de Williams)",
                fabricante="sin dato (equipo hipotético del tamaño justo)", n=1, k=1, capacidad=float(capacidad_requerida), unidad=unidad,
                precio_usd=float(w["precio_usd"]), precio_estimado=True, origen="Williams", url=w.get("url", ""),
                fuente=w["fuente"], fecha=str(w.get("fecha", "")), potencia_kw=None, largo_m=None, ancho_m=None, alto_m=None, peso_kg=None,
                material=None, garantia_meses=None, plazo_entrega_semanas=None, mtbf_h=None, mttr_h=None, confiabilidad=None,
                nota=" ".join(w["avisos"]), punto="williams", usar_en_ajuste=False))
            avisos.append("Ningún equipo real calza con el tamaño pedido (±20 %): se agregó la opción Williams del tamaño justo.")
        else:
            avisos.append("Ningún equipo real calza con el tamaño pedido y no hay forma de estimar su precio con Williams.")
    cands.sort(key=lambda c: (c["precio_usd"], c["capacidad"]))
    return dict(candidatos=cands, avisos=avisos, tavily=tav)


def candidatos(tipo: str, capacidad_requerida: float, unidad: str | None = None, en_linea: bool = True, secretos=None, bd=None) -> list[dict]:
    """Candidatos para una etapa que pide capacidad_requerida (en «unidad»; por omisión la de trabajo del tipo): fichas de Tavily en vivo
    (con clave y red), las referencias de la base (equipos reales) y, si ninguna calza dentro de ±20 %, una opción «Williams» del tamaño
    justo. Cada dict: id, modelo, fabricante, n, k, capacidad, unidad, precio_usd, precio_estimado, origen («Tavily», «Respaldo» o
    «Williams»), url, fuente y, de lo que la página dice, potencia_kw, medidas, peso_kg, material, garantía, plazo, mtbf_h, mttr_h,
    confiabilidad y nota. Sin red ni clave todo sigue funcionando con el respaldo. Ordenados por precio."""
    return candidatos_con_avisos(tipo, capacidad_requerida, unidad, en_linea, secretos, bd)["candidatos"]
