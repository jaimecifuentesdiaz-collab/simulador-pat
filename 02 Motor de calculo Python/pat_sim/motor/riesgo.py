"""Análisis de riesgo de la cascada (mejora 5, PAT 133, 02-11-2026): tornado y Monte Carlo sobre el VAN.

El VAN se arma con economia.evaluacion a partir del combustible que desplaza la cascada en serie del resumen
(gas natural en el tomate, en MMBtu; biomasa en pellet, chip y leña, en m³ estéreo) y de los supuestos económicos.

Rangos de partida (PAT 133):
- Precio del gas: de 2,77 US$/MMBtu, Henry Hub de agosto de 2026 (CNE, 2026c, p. 12), a 12 US$/MMBtu
  (Supuesto: techo del rango de sensibilidad del precio del gas del Capítulo 4, sección 4.7.7).
- Precio de la biomasa: de 6.000 a 7.500 $/m³ estéreo, astilla de pino con corteza puesta en planta, sin IVA
  (INFOR, Pardo, 2025, Boletín de precios forestales N.° 193, pp. 12-13).
- Tasa de descuento: de 6 a 14 % (Capítulo 4, Tabla 47 y sección 4.7.7).
- Inversión: ±30 % (Capítulo 4, sección 4.7.7, sensibilidad de la inversión).
- Fracción de recuperación, calor efectivamente recuperado sobre el de diseño: 0,8 a 1,0 (Supuesto: el diseño es el
  máximo termodinámico; ensuciamiento, paradas y control lo rebajan).
- Dólar: ±10 % (Supuesto; solo en el gas, porque el precio de la biomasa ya está en pesos).
El costo anual y el horizonte quedan fijos en su valor de la sesión. Si un valor de la sesión cae fuera de un rango,
el rango se ensancha hasta contenerlo.
"""
from __future__ import annotations
import math
import random
from . import economia as eco

GAS_MIN, GAS_MAX = 2.77, 12.0             # US$/MMBtu: CNE (2026c, p. 12) y Supuesto (techo del Capítulo 4)
BIOMASA_MIN, BIOMASA_MAX = 6000.0, 7500.0  # $/m³ estéreo: INFOR (Pardo, 2025, pp. 12-13)
TASA_MIN, TASA_MAX = 0.06, 0.14            # Capítulo 4, sección 4.7.7
INVERSION_BANDA = 0.30                     # Capítulo 4, sección 4.7.7
FRACCION_MIN, FRACCION_MAX = 0.8, 1.0      # Supuesto
DOLAR_BANDA = 0.10                         # Supuesto

NOMBRES = dict(precio="Precio del combustible", dolar="Dólar observado", inversion="Inversión", tasa="Tasa de descuento",
               fraccion="Fracción de recuperación", costo_anual="Costo anual", anios="Horizonte")


# ---------------------------------------------------------------- VAN de la cascada
def ahorro_anual(params: dict, desplazado: float, combustible: str = "gas") -> float:
    """Ahorro por temporada en millones de pesos. desplazado: MMBtu de gas o m³ estéreo de biomasa por temporada."""
    q = desplazado * float(params.get("fraccion", 1.0))
    if combustible == "biomasa":
        return q * float(params["precio"]) / 1e6
    return eco.valor_gas(q, float(params["precio"]), float(params["dolar"]))


def evaluacion_cascada(params: dict, desplazado: float, combustible: str = "gas") -> dict:
    """economia.evaluacion con el ahorro de la cascada (VAN, TIR, flujos y recuperación)."""
    return eco.evaluacion(float(params["inversion"]), ahorro_anual(params, desplazado, combustible), float(params.get("costo_anual", 0.0)),
                          int(params["anios"]), float(params["tasa"]))


def van_cascada(params: dict, desplazado: float, combustible: str = "gas") -> float:
    """VAN (MM$) de la cascada con los supuestos de params: precio, dolar, inversion, costo_anual, tasa, anios y fraccion."""
    return evaluacion_cascada(params, desplazado, combustible)["VAN"]


def factor_anualidad(tasa: float, anios: int) -> float:
    return sum(1 / (1 + tasa) ** i for i in range(1, int(anios) + 1))


def _banda(base: float, lo: float, hi: float) -> tuple:
    return (min(lo, base), max(hi, base))


def supuestos(r: dict, E: dict) -> dict | None:
    """Arma, desde el resumen de la planta y la economía de la sesión, los supuestos base, los rangos del tornado y las
    distribuciones triangulares del Monte Carlo. None si la planta no tiene caldera con horas declaradas."""
    avisos = []
    if "gas_desplazado_cascada" in r:
        comb, desplazado = "gas", float(r["gas_desplazado_cascada"]["MMBtu"]); precio = float(E["precio_gas"])
        rango_precio = _banda(precio, GAS_MIN, GAS_MAX)
    elif "biomasa_cascada" in r:
        comb, desplazado = "biomasa", float(r["biomasa_cascada"]["m3"]); precio = float(E.get("precio_biomasa", 6750.0))
        rango_precio = _banda(precio, BIOMASA_MIN, BIOMASA_MAX)
    else:
        return None
    base = dict(precio=precio, dolar=float(E["dolar"]), inversion=float(E["inversion"]), costo_anual=float(E["costo_anual"]),
                tasa=float(E["tasa"]), anios=int(E["anios"]), fraccion=1.0)
    if base["inversion"] <= 0:
        neto = ahorro_anual(base, desplazado, comb) - base["costo_anual"]
        inv_max = neto * factor_anualidad(base["tasa"], base["anios"])
        if inv_max > 0:
            base["inversion"] = inv_max
            txt = f"{inv_max:,.1f}".replace(",", "X").replace(".", ",").replace("X", ".")
            avisos.append(f"La inversión de la sesión es 0: se usa como base la inversión máxima con VAN cero ({txt} MM$), de modo "
                          "que el VAN base es 0 y el riesgo se lee como la probabilidad de que esa inversión no se pague.")
        else:
            avisos.append("La inversión de la sesión es 0 y el ahorro no cubre el costo anual: no hay inversión que dé VAN positivo.")
    rangos = dict(precio=rango_precio,
                  tasa=_banda(base["tasa"], TASA_MIN, TASA_MAX),
                  inversion=(base["inversion"] * (1 - INVERSION_BANDA), base["inversion"] * (1 + INVERSION_BANDA)),
                  fraccion=(FRACCION_MIN, FRACCION_MAX))
    if comb == "gas":
        rangos["dolar"] = (base["dolar"] * (1 - DOLAR_BANDA), base["dolar"] * (1 + DOLAR_BANDA))
    distribuciones = {k: (lo, base[k], hi) for k, (lo, hi) in rangos.items()}
    fn = lambda p: van_cascada(p, desplazado, comb)
    return dict(combustible=comb, desplazado=desplazado, base=base, rangos=rangos, distribuciones=distribuciones, fn=fn,
                van_base=fn(base), avisos=avisos)


# ---------------------------------------------------------------- tornado
def tornado(base: dict, rangos: dict, fn) -> list:
    """Varía cada supuesto entre su mínimo y su máximo con los demás en el valor base. Devuelve una fila por supuesto,
    ordenadas de mayor a menor amplitud: clave, nombre, valor bajo y alto, VAN bajo y alto, amplitud y VAN base."""
    v0 = fn(dict(base)); filas = []
    for k, (lo, hi) in rangos.items():
        p_lo = dict(base); p_lo[k] = lo; p_hi = dict(base); p_hi[k] = hi
        a, b = fn(p_lo), fn(p_hi)
        filas.append(dict(clave=k, nombre=NOMBRES.get(k, k), valor_bajo=lo, valor_alto=hi, van_bajo=a, van_alto=b,
                          van_min=min(a, b), van_max=max(a, b), amplitud=abs(b - a), van_base=v0))
    return sorted(filas, key=lambda f: -f["amplitud"])


# ---------------------------------------------------------------- Monte Carlo
def percentil(ordenados: list, q: float) -> float:
    """Percentil q (0 a 100) por interpolación lineal sobre una lista ordenada (mismo criterio que numpy por defecto)."""
    if not ordenados:
        return float("nan")
    x = (len(ordenados) - 1) * q / 100.0; i = int(math.floor(x)); j = min(i + 1, len(ordenados) - 1)
    return ordenados[i] + (ordenados[j] - ordenados[i]) * (x - i)


def monte_carlo(base: dict, distribuciones: dict, fn, n: int = 2000, semilla: int = 133) -> dict:
    """Muestrea cada supuesto de una triangular (mínimo, moda, máximo) con random.Random(semilla), reproducible;
    los supuestos sin distribución quedan en su valor base. Entrega media, desviación estándar muestral, percentiles 5,
    50 y 95, probabilidad de VAN positivo y los valores."""
    rng = random.Random(semilla); vals = []
    claves = list(distribuciones)
    for _ in range(int(n)):
        p = dict(base)
        for k in claves:
            lo, moda, hi = distribuciones[k]
            p[k] = lo if hi <= lo else rng.triangular(lo, hi, min(max(moda, lo), hi))
        vals.append(float(fn(p)))
    m = len(vals); media = sum(vals) / m if m else float("nan")
    desv = math.sqrt(sum((v - media) ** 2 for v in vals) / (m - 1)) if m > 1 else 0.0
    orden = sorted(vals)
    return dict(n=m, semilla=semilla, media=media, desviacion=desv, p5=percentil(orden, 5), p50=percentil(orden, 50),
                p95=percentil(orden, 95), prob_positivo=sum(1 for v in vals if v > 0) / m if m else float("nan"), valores=vals)


def histograma(valores: list, n_clases: int = 30) -> list:
    """Clases de igual ancho: lista de (desde, hasta, frecuencia)."""
    if not valores:
        return []
    lo, hi = min(valores), max(valores)
    if hi - lo < 1e-12:
        return [(lo, hi, len(valores))]
    w = (hi - lo) / n_clases; cuenta = [0] * n_clases
    for v in valores:
        cuenta[min(int((v - lo) / w), n_clases - 1)] += 1
    return [(lo + i * w, lo + (i + 1) * w, c) for i, c in enumerate(cuenta)]
