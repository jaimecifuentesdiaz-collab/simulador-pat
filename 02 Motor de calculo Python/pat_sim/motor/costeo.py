"""Costeo completo de la planta (PAT 135, tarea T7.1, 04-11-2026): lista de equipos desde la planta resuelta, precio de cada
uno (internet con Tavily, último precio guardado o correlación de bibliografía), escalamiento de Williams y actualización con
el CEPCI. Indicación 1 del profesor Torres en la reunión del 04-11-2026 (01 Requisitos y diseno/Reunion_profesor_Torres_04nov2026.md).

Método
- Williams (1947), regla de los seis décimos: C2 = C1·(S2/S1)^n, con n por tipo de equipo (EXPONENTES, diccionario editable).
- Actualización con índice de costos: C_hoy = C_año·(CEPCI_hoy/CEPCI_año). Por defecto CEPCI_hoy = 797,9, promedio anual 2023
  (Chemical Engineering, 25-03-2024), el mismo de motor/calculadoras.py; se cambia en la interfaz con su año. El promedio 2025
  subió 1,6 % sobre el de 2024 (Chemical Engineering, 02-04-2026), pero su valor solo se publica con suscripción.
- Instalación: factor 2,5 de motor/costos.py (1/0,40, fracción de equipo de la Danish Energy Agency, 2026, hoja 2.a; Supuesto).

Pendiente: el PDF «estimación de costo de planta» del profesor (curso PAT) aún no está en PAT/Fuentes. Cuando llegue se
ajustan EXPONENTES y REFERENCIAS con sus tablas; exponentes_profesor() ya mira esa carpeta pero por ahora no lee nada.
Las cifras marcadas Supuesto son órdenes de magnitud para que la planta tenga un costo de partida: se reemplazan al buscar
el precio en internet o con el PDF del profesor.
"""
from __future__ import annotations
import math
from pathlib import Path
from . import costos, hidraulica as HID

# ---------------------------------------------------------------- índices de costos
# Promedios anuales del CEPCI (1957-59 = 100): Chemical Engineering (2024), Economic Indicators, septiembre de 2024, p. 45,
# https://www.chemengonline.com/wp-content/uploads/2024/08/19_CHE_0924_EconInd_p45.pdf
CEPCI_ANUAL = {2016: 541.7, 2017: 567.5, 2018: 603.1, 2019: 607.5, 2020: 596.2, 2021: 708.8, 2022: 816.0, 2023: 797.9}
FUENTE_CEPCI_ANUAL = "Chemical Engineering (2024), Economic Indicators, septiembre de 2024, p. 45"
URL_CEPCI = "https://www.chemengonline.com/wp-content/uploads/2024/08/19_CHE_0924_EconInd_p45.pdf"
CEPCI_HOY = 797.9            # promedio anual 2023 (Chemical Engineering, 25-03-2024); editable en la interfaz
ANIO_CEPCI_HOY = 2023
CEPCI_ENE_2010 = 532.9       # base de Towler y Sinnott (2013), costos de enero de 2010 en la costa del Golfo (cotejar con el libro)

# ---------------------------------------------------------------- exponentes de Williams (editable)
# clave → (n, fuente, categoría). Turton et al. (2018) Tabla 7.3, vía Engineering LibreTexts, «6.2 Purchased Equipment (PE)
# Cost»: intercambiador de tubo y carcasa de acero inoxidable 1,9 a 1.860 m², n = 0,60; bomba centrífuga de acero inoxidable
# 1 a 70 hp, n = 0,67. El resto: regla de los seis décimos (Williams, 1947), Supuesto hasta recibir el PDF del profesor.
N_SEIS_DECIMOS = 0.6
FUENTE_TURTON = "Turton et al. (2018), Analysis, Synthesis and Design of Chemical Processes, 5.a ed., Tabla 7.3 (vía Engineering LibreTexts, 6.2)"
EXPONENTES = {
    "intercambiador": (0.60, FUENTE_TURTON, "Literatura"),
    "bomba_centrifuga": (0.67, FUENTE_TURTON, "Literatura"),
}


def exponente(clave: str, exponentes: dict | None = None) -> tuple[float, str, str]:
    """Exponente de Williams de un tipo de costeo: (n, fuente, categoría). Sin dato: 0,6 Supuesto (regla de los seis décimos)."""
    tabla = dict(EXPONENTES); tabla.update(exponentes or {})
    v = tabla.get(clave)
    if v is None:
        return N_SEIS_DECIMOS, "Regla de los seis décimos (Williams, 1947)", "Supuesto"
    if isinstance(v, (int, float)):
        return float(v), "Usuario", "Usuario"
    return float(v[0]), v[1], v[2]


def exponentes_profesor(carpeta: str | Path | None = None) -> dict:
    """PAT 135: lugar para leer los exponentes del PDF «estimación de costo de planta» del profesor en PAT/Fuentes.
    Por ahora no lee nada (el PDF no ha llegado) y devuelve {}; informa si el archivo ya está en la carpeta."""
    carpeta = Path(carpeta) if carpeta else Path(__file__).resolve().parents[4] / "Fuentes"
    try:
        hay = any("costo" in p.name.lower() and p.suffix.lower() == ".pdf" for p in carpeta.glob("*"))
    except Exception:
        hay = False
    return dict(_pdf_encontrado=hay) if hay else {}


# ---------------------------------------------------------------- funciones básicas
def williams(C1: float, S1: float, S2: float, n: float) -> float:
    """C2 = C1·(S2/S1)^n (Williams, 1947)."""
    if S1 is None or S2 is None or S1 <= 0 or S2 <= 0:
        raise ValueError("Los tamaños de Williams deben ser positivos")
    return C1 * (S2 / S1) ** n


def cepci_de(anio) -> float | None:
    """CEPCI promedio del año (None si no hay valor publicado de acceso libre)."""
    try:
        return CEPCI_ANUAL.get(int(anio))
    except (TypeError, ValueError):
        return None


def actualizar(C: float, cepci_anio: float | None, cepci_hoy: float = CEPCI_HOY) -> tuple[float, float]:
    """C_hoy = C·(CEPCI_hoy/CEPCI_año); sin índice del año, factor 1. Devuelve (costo, factor)."""
    if not cepci_anio or cepci_anio <= 0:
        return C, 1.0
    f = cepci_hoy / cepci_anio
    return C * f, f


# ---------------------------------------------------------------- correlaciones de bibliografía
DH_VAPOR = 2360.0       # kJ/kg; Supuesto: vapor saturado a 10 bar (2.778 kJ/kg) desde agua de alimentación a 100 °C (419 kJ/kg)


def _caldera_towler(Q_kW: float) -> float:
    """Caldera empaquetada de 15 a 40 bar, 5.000 a 200.000 kg/h de vapor: Ce = 124.000 + 10·S (US$ de enero de 2010).
    Towler y Sinnott (2013), Tabla 7.2, transcrita en openpytea 3.2.1 (cotejar con el libro)."""
    return 124000.0 + 10.0 * (Q_kW * 3600.0 / DH_VAPOR)


def _hx_shamoushaki(area_m2: float) -> float:
    return costos.costo_equipo_partido_usd2020(area_m2)


SUP = "Supuesto"
J_SUP = "orden de magnitud de partida; se reemplaza con el precio de internet (Tavily) o con el PDF del profesor"
# clave → nombre, consulta en inglés para Tavily, magnitud, unidad, tamaño y precio de referencia (US$ de equipo comprado),
# año, fuente, categoría y, si existe, correlación f(S) → US$ del año con su rango de validez en S.
REFERENCIAS = {
    "intercambiador": dict(nombre="Recuperador de calor (tubo y carcasa)", consulta="stainless steel shell and tube heat exchanger price {s} m2",
                           magnitud="Área", unidad="m2", S=100.0, C=None, anio=2020, correlacion=_hx_shamoushaki, rango=(1.0, 1e9),
                           fuente="Shamoushaki et al. (2021), Energies 14(9), 2665, ec. 4 y Tabla 6 (motor/costos.py)", categoria="Literatura",
                           url="https://doi.org/10.3390/en14092665"),
    "caldera_gas": dict(nombre="Caldera a gas (empaquetada)", consulta="packaged steam boiler natural gas price {s} kW",
                        magnitud="Potencia térmica", unidad="kW", S=None, C=None, anio=2010, cepci=CEPCI_ENE_2010, correlacion=_caldera_towler,
                        rango=(5000 * DH_VAPOR / 3600, 200000 * DH_VAPOR / 3600),
                        fuente="Towler y Sinnott (2013), Tabla 7.2, caldera empaquetada (transcrita en openpytea 3.2.1; cotejar)", categoria="Literatura"),
    "generador_biomasa": dict(nombre="Generador de calor a biomasa", consulta="biomass hot air furnace wood chip burner price {s} kW",
                              magnitud="Potencia térmica", unidad="kW", S=None, C=None, anio=2010, cepci=CEPCI_ENE_2010, correlacion=_caldera_towler,
                              rango=(5000 * DH_VAPOR / 3600, 200000 * DH_VAPOR / 3600),
                              fuente="Towler y Sinnott (2013), Tabla 7.2, caldera empaquetada con el vapor equivalente al calor (Supuesto)", categoria=SUP),
    "bomba_centrifuga": dict(nombre="Bomba centrífuga sanitaria", consulta="stainless steel sanitary centrifugal pump price {s} kW",
                             magnitud="Potencia", unidad="kW", S=7.5, C=8000.0, anio=2023, fuente=f"Supuesto: {J_SUP}", categoria=SUP),
    "valvula_control": dict(nombre="Válvula de control", consulta="control valve with pneumatic actuator price Cv {s}",
                            magnitud="Cv", unidad="Cv", S=50.0, C=6000.0, anio=2023, fuente=f"Supuesto: {J_SUP}", categoria=SUP),
    "caneria": dict(nombre="Cañería de acero inoxidable 304", consulta="stainless steel 304 sanitary pipe price per meter {s} inch",
                    magnitud="Diámetro nominal", unidad="mm", S=50.0, C=60.0, anio=2023, por_metro=True,
                    fuente=f"Supuesto: US$ por metro de DN 50, {J_SUP}", categoria=SUP),
    "bomba_calor": dict(nombre="Bomba de calor industrial", consulta="industrial heat pump price {s} kW",
                        magnitud="Potencia térmica", unidad="kW", S=1000.0, C=None, anio=2025, correlacion=None,
                        fuente="Danish Energy Agency (2026), hoja 2.a, 1,20 MEUR/MW instalado por 0,40 de fracción de equipo (motor/costos.py)",
                        categoria="Literatura"),
}
# equipos de la línea: tipo del catálogo → (clave de costeo, nombre, consulta, magnitud, unidad, detalle, S_ref, C_ref)
_LINEA = {
    "alimentacion_tomate": ("recepcion_tomate", "Recepción de tomate", "tomato receiving hopper flume system price {s} t/h", "Capacidad", "t/h", "carga_t_h", 50.0, 150000.0),
    "recepcion_seleccion": ("lavado_seleccion", "Lavado y selección", "tomato washing and sorting line price {s} t/h", "Capacidad", "t/h", "carga_t_h", 50.0, 250000.0),
    "trituradora": ("trituradora", "Trituradora", "tomato chopper crusher price {s} t/h", "Capacidad", "t/h", "carga_t_h", 50.0, 80000.0),
    "hot_break": ("hot_break", "Hot break", "tomato hot break system price {s} kW", "Potencia térmica", "kW", "Q_kW", 5000.0, 400000.0),
    "refinadora": ("refinadora", "Refinadora", "tomato pulper refiner finisher price {s} t/h", "Capacidad", "t/h", "carga_t_h", 50.0, 200000.0),
    "evaporador_mvr": ("evaporador_mvr", "Evaporador MVR", "MVR evaporator tomato paste price {s} kg/h water evaporation", "Evaporación", "kg/h", "agua_evaporada_kgh", 20000.0, 3000000.0),
    "evaporador_multiefecto": ("evaporador_multiefecto", "Evaporador de múltiple efecto", "multiple effect evaporator tomato paste price {s} kg/h evaporation", "Evaporación", "kg/h", "agua_evaporada_kgh", 20000.0, 2500000.0),
    "esterilizador": ("esterilizador", "Esterilizador", "tube in tube sterilizer tomato paste price {s} kW", "Potencia térmica", "kW", "Q_kW", 2000.0, 250000.0),
    "enfriamiento_flash": ("enfriamiento_flash", "Enfriamiento flash", "vacuum flash cooler price {s} t/h", "Capacidad", "t/h", "carga_t_h", 50.0, 150000.0),
    "llenadora_aseptica": ("llenadora_aseptica", "Llenadora aséptica", "aseptic bag in drum filler price {s} t/h", "Capacidad", "t/h", "carga_t_h", 10.0, 600000.0),
    "alimentacion_biomasa": ("recepcion_biomasa", "Recepción de biomasa", "biomass receiving hopper conveyor price {s} t/h", "Capacidad", "t/h", "carga_t_h", 10.0, 120000.0),
    "secador_biomasa": ("secador_rotatorio", "Secador rotatorio", "rotary drum dryer sawdust price {s} kg/h water evaporation", "Evaporación", "kg/h", "agua_evaporada_kgh", 5000.0, 1200000.0),
    "secador_banda": ("secador_banda", "Secador de banda", "belt dryer wood chips price {s} kg/h water evaporation", "Evaporación", "kg/h", "agua_evaporada_kgh", 5000.0, 1500000.0),
    "secador_lena": ("secador_lena", "Secador de leña", "firewood kiln dryer price {s} kg/h", "Evaporación", "kg/h", "agua_evaporada_kgh", 1500.0, 300000.0),
    "molino_martillos": ("molino_martillos", "Molino de martillos", "hammer mill biomass price {s} t/h", "Capacidad", "t/h", "carga_t_h", 5.0, 120000.0),
    "astilladora": ("astilladora", "Astilladora de disco", "disc wood chipper price {s} t/h", "Capacidad", "t/h", "carga_t_h", 20.0, 250000.0),
    "pelletizadora": ("pelletizadora", "Pelletizadora", "ring die pellet mill price {s} t/h", "Capacidad", "t/h", "carga_t_h", 5.0, 400000.0),
    "enfriador_pellet": ("enfriador_pellet", "Enfriador de pellet", "counterflow pellet cooler price {s} t/h", "Capacidad", "t/h", "carga_t_h", 5.0, 80000.0),
    "criba_biomasa": ("criba", "Criba", "vibrating screen biomass price {s} t/h", "Capacidad", "t/h", "carga_t_h", 10.0, 40000.0),
    "sierra_lena": ("sierra_lena", "Procesadora de leña", "firewood processor price {s} t/h", "Capacidad", "t/h", "carga_t_h", 4.0, 90000.0),
    "despacho_biomasa": ("ensacado_acopio", "Ensacado o acopio", "pellet bagging machine price {s} t/h", "Capacidad", "t/h", "producto_t_h", 5.0, 150000.0),
}
for _t, (_k, _n, _q, _m, _u, _d, _s, _c) in _LINEA.items():
    REFERENCIAS.setdefault(_k, dict(nombre=_n, consulta=_q, magnitud=_m, unidad=_u, S=_s, C=_c, anio=2023, fuente=f"Supuesto: {J_SUP}",
                                    categoria=SUP))
REFERENCIAS.setdefault("generico", dict(nombre="Equipo genérico", consulta="industrial process equipment price {s} t/h", magnitud="Capacidad",
                                        unidad="t/h", S=10.0, C=30000.0, anio=2023, fuente=f"Supuesto: {J_SUP}", categoria=SUP))

# diámetros nominales (mm) y su equivalente en pulgadas (ASME B36.19M para acero inoxidable)
DN_PULG = {15: "1/2", 20: "3/4", 25: "1", 32: "1 1/4", 40: "1 1/2", 50: "2", 65: "2 1/2", 80: "3", 100: "4", 125: "5", 150: "6",
           200: "8", 250: "10", 300: "12", 350: "14", 400: "16", 450: "18", 500: "20", 600: "24"}


def diametro_nominal(D_mm: float) -> int:
    """Menor diámetro nominal que no baja del diámetro interno calculado (Supuesto: DN ≈ diámetro interno); sobre DN 600, múltiplo de 50."""
    for dn in DN_PULG:
        if dn >= D_mm - 1e-9:
            return dn
    return int(math.ceil(D_mm / 50.0) * 50)


def pulgadas(dn: int) -> str:
    return DN_PULG.get(dn, f"{dn / 25.4:.0f}".replace(".", ","))


# ---------------------------------------------------------------- lista de equipos
def _det(eq, clave):
    r = eq.resultado
    v = r.detalle.get(clave) if r is not None else None
    return float(v) if v is not None else None


def _alternativas(pl):
    from .resumen import resumen_planta
    from . import alternativas as AL
    r = resumen_planta(pl)
    if r.get("sin_sumidero"):
        return None
    return AL.alternativas(pl, r, 1.0)


def _item(equipo, nombre, clave, tamano, unidad, cantidad=1.0, nota="", tipo=None, magnitud=None):
    ref = REFERENCIAS.get(clave, REFERENCIAS["generico"])
    return dict(equipo=equipo, nombre=nombre, clave=clave, tipo=tipo or ref["nombre"], magnitud=magnitud or ref["magnitud"],
                tamano=tamano, unidad=unidad or ref["unidad"], cantidad=cantidad, nota=nota)


def lista_equipos(pl, longitudes: dict | None = None, alternativa: str | None = None, X: dict | None = None) -> list[dict]:
    """Lista completa de equipos de la planta resuelta: línea, recuperadores de calor (de la alternativa elegida o la ganadora),
    caldera o generador a biomasa, bombas (una por línea de líquido sin bomba dibujada, potencia de motor/hidraulica.py),
    válvulas de control (una por lazo con válvula como elemento final, Cv por ISA-75.01) y cañerías por diámetro nominal.
    longitudes: {id de corriente: m} del layout; sin dato, L_LINEA de motor/hidraulica.py marcado «Supuesto: sin layout»."""
    if not pl.resuelta:
        raise ValueError("Resuelva la planta antes del costeo")
    items = []
    for k, eq in pl.equipos.items():
        t = eq.tipo
        if t.startswith("caldera"):
            bio = getattr(eq, "combustible", "gas") == "biomasa"
            Q = _det(eq, "Q_calor_kW" if bio else "Q_vapor_kW") or 0.0
            items.append(_item(k, eq.nombre, "generador_biomasa" if bio else "caldera_gas", Q, "kW"))
        elif getattr(eq, "es_bomba", False):
            items.append(_item(k, eq.nombre, "bomba_centrifuga", _det(eq, "W_kW") or 0.0, "kW"))
        elif t.startswith("iso_valvula"):
            items.append(_item(k, eq.nombre, "valvula_control", _det(eq, "Cv"), "Cv",
                               nota="" if _det(eq, "Cv") else "Sin líquido: Cv de referencia (Supuesto)"))
        elif t in _LINEA:
            clave, _n, _q, _m, unidad, det, _s, _c = _LINEA[t]
            v = _det(eq, det)
            if v is None and det != "carga_t_h":
                v = _det(eq, "carga_t_h"); unidad = "t/h"
            items.append(_item(k, eq.nombre, clave, v or 0.0, unidad))
        else:
            items.append(_item(k, eq.nombre, "generico", _det(eq, "carga_t_h") or 0.0, "t/h", nota="Equipo sin referencia propia (Supuesto)"))
    # recuperadores de calor
    try:
        X = X if X is not None else _alternativas(pl)
    except Exception:
        X = None
    if X and X.get("alts"):
        k_alt = alternativa if alternativa in X["alts"] else (X.get("ganador") or "A2")
        a = X["alts"].get(k_alt)
        if a is not None:
            for i, e in enumerate(a["etapas"], 1):
                items.append(_item(f"E-{100 + i}", f"Recuperador {e['corriente']} ({X['alts'][k_alt]['nombre'].lower()}, {k_alt})",
                                   "intercambiador", e["A_medio"], "m2", nota=f"{e['Q']:.0f} kW recuperados, U medio".replace(".", ",")))
            if k_alt == "A4" and a["Q"] > 0:
                items.append(_item("HP-1", f"Bomba de calor ({k_alt})", "bomba_calor", a["Q"], "kW"))
    # red hidráulica: bombas y cañerías
    lineas = []
    try:
        lineas = HID.red_hidraulica(pl)["lineas"]
    except Exception:
        lineas = []
    longitudes = longitudes or {}
    tramos = {}
    for i, ln in enumerate(lineas, 1):
        if ln["bomba_diagrama"] is None and ln["potencia_kW"] > 0:
            items.append(_item(f"P-{100 + i}", f"Bomba de la línea {ln['linea']}", "bomba_centrifuga", ln["potencia_kW"], "kW",
                               nota=f"{ln['Q_m3h']:.1f} m³/h y {ln['H_m']:.1f} m (motor/hidraulica.py)".replace(".", ",")))
        dn = diametro_nominal(ln["D_mm"])
        L = longitudes.get(str(ln["linea"]), longitudes.get(ln["linea"]))
        sin = L is None
        L = float(L) if L is not None else HID.L_LINEA
        tr = tramos.setdefault(dn, dict(L=0.0, lineas=[], sin_layout=False))
        tr["L"] += L; tr["lineas"].append(str(ln["linea"])); tr["sin_layout"] |= sin
    for dn in sorted(tramos):
        tr = tramos[dn]
        nota = f"Líneas {', '.join(tr['lineas'])}" + (f". Supuesto: sin layout, {HID.L_LINEA:.0f} m por línea (motor/hidraulica.py)"
                                                        if tr["sin_layout"] else ". Largo del layout")
        items.append(_item(f"DN {dn}", f"Cañería DN {dn} ({pulgadas(dn)}\")", "caneria", float(dn), "mm", tr["L"], nota))
    # válvulas de control: una por lazo cuyo elemento final es una válvula (letra V en el rótulo, ISA-5.1)
    import re
    for ins in pl.instrumentos:
        ef = (ins.elemento_final or "").strip()
        if not re.match(r"^[A-Z]{1,3}V-?\d", ef):
            continue
        ln = next((x for x in lineas if x["destino"] == ins.equipo), None) or next((x for x in lineas if x["origen"] == ins.equipo), None)
        Cv, nota = None, "Sin línea de líquido: Cv de referencia (Supuesto)"
        if ln is not None:
            Cv = HID.cv_requerido(ln["Q_m3h"], 50.0, ln["rho"] / 1000.0)
            nota = f"Cv con {ln['Q_m3h']:.1f} m³/h de la línea {ln['linea']} y 50 kPa de caída (Supuesto de catalogos/iso_generico.py)".replace(".", ",")
        items.append(_item(ef, f"Válvula {ef} del lazo {ins.letras}-{ins.numero} ({ins.equipo})", "valvula_control", Cv, "Cv", nota=nota))
    return items


# ---------------------------------------------------------------- precio de bibliografía de un ítem
def precio_bibliografia(clave: str, tamano: float | None, exponentes: dict | None = None, dolar: float = costos.DOLAR,
                        euro: float = costos.EURO) -> dict:
    """Precio de referencia de bibliografía (o Supuesto): {precio_usd, tamano, unidad, anio, cepci_ref, fuente, url, categoria, n}.
    Con correlación, se evalúa en el tamaño requerido dentro de su rango (sin Williams); fuera del rango, en el borde y luego Williams."""
    ref = REFERENCIAS.get(clave, REFERENCIAS["generico"])
    n = exponente(clave, exponentes)[0]
    base = dict(unidad=ref["unidad"], anio=ref["anio"], cepci_ref=ref.get("cepci") or cepci_de(ref["anio"]), fuente=ref["fuente"],
                url=ref.get("url", ""), categoria=ref["categoria"], fecha=str(ref["anio"]))
    if clave == "bomba_calor":
        S = tamano or ref["S"]
        usd = costos.BOMBA_CALOR_MEUR_MW[1] * 1e6 * S / 1000 * euro / dolar / costos.F_INSTALACION
        return dict(base, precio_usd=usd, tamano=S, exacto=True)
    f = ref.get("correlacion")
    if f is not None:
        lo, hi = ref.get("rango", (0, 1e18))
        S = tamano if tamano and tamano > 0 else (lo if lo > 0 else 1.0)
        Sr = min(max(S, lo), hi)
        return dict(base, precio_usd=f(Sr), tamano=Sr, exacto=abs(Sr - S) < 1e-9)
    return dict(base, precio_usd=ref["C"], tamano=ref["S"], exacto=False)


# ---------------------------------------------------------------- costeo
def costear(pl, cepci_hoy: float = CEPCI_HOY, anio_cepci: int = ANIO_CEPCI_HOY, dolar: float = costos.DOLAR, euro: float = costos.EURO,
            bd=None, buscar: bool = False, clave: str | None = None, longitudes: dict | None = None, alternativa: str | None = None,
            X: dict | None = None, exponentes: dict | None = None, f_inst: float = costos.F_INSTALACION, items: list | None = None,
            _abrir=None) -> dict:
    """Costo de cada equipo y de la planta. Cada fila: equipo, tipo, tamaño requerido, tamaño y precio de referencia, año,
    exponente de Williams aplicado, factor CEPCI, costo actualizado en US$ y $, fuente, fecha, URL y origen (internet,
    guardado o bibliografía). Totales: equipos, instalación (factor f_inst de motor/costos.py) y total de la planta."""
    from ..datos import precios_web as PW
    items = items if items is not None else lista_equipos(pl, longitudes, alternativa, X)
    filas, avisos = [], []
    exps = dict(exponentes_profesor()); exps.pop("_pdf_encontrado", None); exps.update(exponentes or {})
    for it in items:
        ref = REFERENCIAS.get(it["clave"], REFERENCIAS["generico"])
        n, fuente_n, cat_n = exponente(it["clave"], exps)
        S2 = it["tamano"]
        tam_txt = (f"{pulgadas(int(S2))}" if it["clave"] == "caneria" and S2 else (f"{S2:g}" if S2 else ""))
        consulta = ref["consulta"].format(s=tam_txt).strip()
        unidad_web = {"kW": "kW", "m2": "m2", "t/h": "t/h", "kg/h": "kg/h", "mm": "pulgadas"}.get(it["unidad"])
        tam_web = (S2 / 25.4 if it["unidad"] == "mm" and S2 else S2)
        p = PW.obtener_precio(it["clave"], consulta, unidad_web, tam_web, dolar, euro, bd=bd, clave=clave, buscar=buscar,
                              respaldo=lambda: precio_bibliografia(it["clave"], S2, exps, dolar, euro), _abrir=_abrir)
        if p is None:
            avisos.append(f"{it['equipo']}: sin precio"); continue
        if buscar and "Sin conexión" in p.get("nota", ""):    # PAT 135: sin red no se insiste equipo por equipo (15 s cada uno)
            buscar = False
            avisos.append("Sin conexión con Tavily: el resto de los equipos usa los precios guardados o la bibliografía")
        origen = p["origen"]
        if origen == "bibliografía":
            S1, C1 = p["tamano"], p["precio_usd"]; anio = p["anio"]; cepci_ref = p["cepci_ref"]
            exacto = p.get("exacto", False)
        else:
            S1 = p.get("tamano"); C1 = p["precio_usd"]
            if S1 and it["unidad"] == "mm":
                S1 = S1 * 25.4                    # pulgadas de la página → mm
            anio = int(str(p.get("fecha", ""))[:4] or 0) or None; cepci_ref = cepci_de(anio); exacto = False
        if S2 and S2 > 0 and S1 and S1 > 0 and not exacto:
            C2 = williams(C1, S1, S2, n); n_apl = n
        else:
            C2 = C1; n_apl = None
            if not S1 and origen != "bibliografía":
                avisos.append(f"{it['equipo']}: la página no informa el tamaño; se supone el requerido")
        C_hoy, fc = actualizar(C2, cepci_ref, cepci_hoy)
        if not cepci_ref:
            avisos.append(f"{it['equipo']}: precio de {anio}, año sin CEPCI público; se usa sin actualizar")
        cant = it["cantidad"] if it["clave"] == "caneria" else 1.0
        usd = float(C_hoy * cant)
        S2 = None if S2 is None else float(S2)
        filas.append(dict(equipo=it["equipo"], nombre=it["nombre"], tipo=it["tipo"], magnitud=it["magnitud"], tamano=S2, unidad=it["unidad"],
                          cantidad=float(cant), tamano_ref=None if S1 is None else float(S1), precio_ref_usd=float(C1), anio=anio, n=n_apl, fuente_n=f"{fuente_n} ({cat_n})",
                          cepci_ref=cepci_ref, factor_cepci=float(fc), costo_usd=usd, costo_clp=usd * dolar, fuente=p.get("fuente", ""),
                          fecha=p.get("fecha", ""), url=p.get("url", ""), origen=origen, categoria=p.get("categoria", "Internet"),
                          nota=" ".join(x for x in (it.get("nota", ""), p.get("nota", "")) if x)))
    eq_usd = float(sum(f["costo_usd"] for f in filas))
    rec_usd = float(sum(f["costo_usd"] for f in filas if f["tipo"] in (REFERENCIAS["intercambiador"]["nombre"], REFERENCIAS["bomba_calor"]["nombre"])))
    tot = dict(equipos_usd=eq_usd, instalacion_usd=eq_usd * (f_inst - 1), total_usd=eq_usd * f_inst, f_inst=f_inst,
               recuperacion_usd=rec_usd * f_inst)
    tot.update({k.replace("_usd", "_clp"): v * dolar for k, v in list(tot.items()) if k.endswith("_usd")})
    return dict(filas=filas, totales=tot, avisos=avisos, cepci_hoy=cepci_hoy, anio_cepci=anio_cepci, dolar=dolar, euro=euro,
                n_internet=sum(1 for f in filas if f["origen"].startswith("internet")),
                n_bibliografia=sum(1 for f in filas if f["origen"] == "bibliografía"))
