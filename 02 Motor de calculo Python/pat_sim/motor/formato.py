"""Formato chileno de números (PAT 133, mejora 21): miles con punto y decimales con coma, para mostrar y para leer lo que
el usuario escribe en los campos de la aplicación."""
from __future__ import annotations
import re

_MILES = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+$")


def escribir(v, d: int = 2, miles: bool = True) -> str:
    s = f"{float(v):,.{d}f}" if miles else f"{float(v):.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")


def leer(texto) -> float:
    """Lee '1.234,5', '1234,5', '1234.5', '1.234.567' o '-0,25'. Con coma, los puntos son de miles; sin coma, un punto
    es decimal salvo que agrupe de a tres cifras ('1.234' = mil doscientos treinta y cuatro). Lanza ValueError si no es número."""
    t = str(texto).strip().replace(" ", "").replace(" ", "").replace("$", "").replace("%", "")
    if not t:
        raise ValueError("campo vacío")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif _MILES.match(t):
        t = t.replace(".", "")
    return float(t)


def decimales(fmt: str | None, paso, es_entero: bool) -> int:
    if es_entero:
        return 0
    m = re.search(r"%\.(\d+)f", fmt or "")
    if m:
        return int(m.group(1))
    if paso:
        s = f"{float(paso):.6f}".rstrip("0")
        return max(0, len(s.split(".")[1])) if "." in s else 0
    return 2


def decimales_valor(v, tope: int = 6) -> int:
    """Menor número de decimales que muestra el valor sin redondearlo (hasta 'tope')."""
    try:
        v = float(v)
    except (TypeError, ValueError):
        return 0
    for k in range(tope + 1):
        if abs(round(v, k) - v) < 1e-9 * max(1.0, abs(v)):
            return k
    return tope
