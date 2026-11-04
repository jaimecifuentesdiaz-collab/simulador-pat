"""Desafío en blanco (PAT 135, tarea T7.4): validar el desafío que carga el profesor, convertir su demanda a la serie que
usa el Montecarlo y crear la planta vacía del rubro elegido con los precios de venta del desafío.

Un desafío es un diccionario (así se guarda en la tabla desafios de datos/mantenedor.py):
    titulo, enunciado («diseñar una planta de…», se lee después de «don Jaime Cifuentes, su desafío es»), producto, rubro,
    demanda = {periodo, unidad, valores, etiquetas (opcional), fuente}, precios = [{producto, precio, moneda, unidad, fuente}],
    autor, fecha, activo.
Idea de la reunión del 04-11-2026 con el profesor Torres (indicación 4): la herramienta parte de un desafío en blanco.
"""
from __future__ import annotations
import math
from .planta import Planta

# Horas de cada período, para pasar la demanda a t/h. «mes» = 8.760 h / 12 = 730 h (año de 365 días, sin bisiesto).
PERIODOS = {"hora": 1.0, "turno": 8.0, "día": 24.0, "semana": 168.0, "mes": 730.0, "temporada": None, "año": 8760.0}
# Unidades de masa con su factor a toneladas; las otras unidades (m³ estéreo, unidades) no se convierten.
A_TONELADAS = {"kg": 0.001, "t": 1.0}
UNIDADES = tuple(A_TONELADAS) + ("m³ estéreo", "m³", "unidades")
MONEDAS = ("US$", "$", "UF", "€")
RUBROS_EXTRA = ("todos",)


def _rubros() -> tuple:
    from ..catalogos.registro import RUBROS
    return tuple(RUBROS) + RUBROS_EXTRA


def _finito(v) -> bool:
    try:
        return v is not None and not isinstance(v, bool) and math.isfinite(float(v))
    except (TypeError, ValueError):
        return False


def validar(d: dict) -> list[str]:
    """Lista de errores en español (vacía si el desafío está bien)."""
    if not isinstance(d, dict):
        return ["El desafío debe ser un diccionario"]
    err = []
    for k, nombre in (("titulo", "título"), ("enunciado", "enunciado"), ("producto", "producto")):
        if not str(d.get(k) or "").strip():
            err.append(f"Falta el {nombre} del desafío")
    if d.get("rubro") not in _rubros():
        err.append(f"Rubro desconocido: {d.get('rubro')!r}. Use uno de: {', '.join(_rubros())}")
    dem = d.get("demanda")
    if not isinstance(dem, dict):
        err.append("Falta la demanda (periodo, unidad y valores)")
    else:
        vals = dem.get("valores")
        if not isinstance(vals, (list, tuple)) or not vals:
            err.append("La demanda necesita al menos un valor por período")
        elif not all(_finito(v) and float(v) >= 0 for v in vals):
            err.append("Cada valor de la demanda debe ser un número mayor o igual a cero")
        elif sum(float(v) for v in vals) <= 0:
            err.append("La demanda total debe ser mayor que cero")
        if dem.get("periodo") not in PERIODOS:
            err.append(f"Período desconocido: {dem.get('periodo')!r}. Use uno de: {', '.join(PERIODOS)}")
        if dem.get("unidad") not in UNIDADES:
            err.append(f"Unidad desconocida: {dem.get('unidad')!r}. Use una de: {', '.join(UNIDADES)}")
        et = dem.get("etiquetas")
        if et and isinstance(vals, (list, tuple)) and len(et) != len(vals):
            err.append(f"Hay {len(et)} etiquetas para {len(vals)} valores de demanda")
        if not str(dem.get("fuente") or "").strip():
            err.append("La demanda necesita su fuente (o «Supuesto» con su justificación)")
    precios = d.get("precios") or []
    if not isinstance(precios, (list, tuple)):
        err.append("Los precios de venta deben ser una lista")
    else:
        for i, p in enumerate(precios, 1):
            if not isinstance(p, dict):
                err.append(f"Precio {i}: debe ser un diccionario"); continue
            if not str(p.get("producto") or "").strip():
                err.append(f"Precio {i}: falta el producto")
            if not _finito(p.get("precio")) or float(p.get("precio")) <= 0:
                err.append(f"Precio {i}: el precio debe ser un número mayor que cero")
            if p.get("moneda") not in MONEDAS:
                err.append(f"Precio {i}: moneda desconocida {p.get('moneda')!r}. Use una de: {', '.join(MONEDAS)}")
            if not str(p.get("unidad") or "").strip():
                err.append(f"Precio {i}: falta la unidad (por ejemplo t o kg)")
            if not str(p.get("fuente") or "").strip():
                err.append(f"Precio {i}: falta la fuente (o «Supuesto» con su justificación)")
    return err


def exigir_valido(d: dict) -> dict:
    err = validar(d)
    if err:
        raise ValueError("Desafío no válido: " + "; ".join(err))
    return d


def serie_demanda(d: dict, unidad: str | None = None) -> list[float]:
    """Demanda por período como lista de floats, la serie que recibe el Montecarlo. unidad: «t» o «kg» para convertir
    entre unidades de masa; None deja la unidad del desafío."""
    dem = exigir_valido(d)["demanda"]
    vals = [float(v) for v in dem["valores"]]
    u = dem["unidad"]
    if unidad is None or unidad == u:
        return vals
    if u not in A_TONELADAS or unidad not in A_TONELADAS:
        raise ValueError(f"No se puede pasar la demanda de {u} a {unidad}")
    f = A_TONELADAS[u] / A_TONELADAS[unidad]
    return [v * f for v in vals]


def horas_periodo(d: dict, horas_temporada: float | None = None) -> float:
    """Horas de cada período. «temporada» necesita las horas de la temporada (por ejemplo días × horas por día)."""
    p = d["demanda"]["periodo"]; h = PERIODOS[p]
    if h is None:
        if not horas_temporada or horas_temporada <= 0:
            raise ValueError("Para una demanda por temporada indique las horas de la temporada")
        return float(horas_temporada)
    return h


def demanda_t_h(d: dict, horas_temporada: float | None = None) -> list[float]:
    """Demanda de cada período en t/h (masa del período / horas del período), para compararla con la capacidad de la línea."""
    h = horas_periodo(d, horas_temporada)
    return [v / h for v in serie_demanda(d, "t")]


def estadisticas(d: dict) -> dict:
    """Total, media, mínimo, máximo y coeficiente de variación de la demanda (en la unidad del desafío)."""
    s = serie_demanda(d); n = len(s); m = sum(s) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / (n - 1)) if n > 1 else 0.0
    i_max = max(range(n), key=lambda i: s[i])
    et = d["demanda"].get("etiquetas") or [str(i + 1) for i in range(n)]
    return dict(n=n, total=sum(s), media=m, minimo=min(s), maximo=s[i_max], periodo_maximo=et[i_max], cv=sd / m if m else 0.0,
                unidad=d["demanda"]["unidad"], periodo=d["demanda"]["periodo"])


def planta_vacia(d: dict) -> Planta:
    """Planta sin equipos del rubro del desafío. Lleva el desafío (producto, demanda y precios) en pl._p, que se guarda
    con la versión (datos/bd.py guarda _p). Queda resuelta (sin equipos no hay nada que calcular)."""
    exigir_valido(d)
    rubro = "general" if d["rubro"] == "todos" else d["rubro"]
    pl = Planta(f"Desafío: {str(d['titulo']).strip()}", rubro)
    dem = d["demanda"]
    pl._p = dict(desafio=dict(id=d.get("id"), titulo=d["titulo"], producto=d["producto"], rubro=d["rubro"],
                              demanda=dict(periodo=dem["periodo"], unidad=dem["unidad"], valores=serie_demanda(d),
                                           etiquetas=list(dem.get("etiquetas") or []), fuente=dem.get("fuente", "")),
                              precios=[dict(p) for p in d.get("precios") or []]))
    pl.resolver()
    return pl


def desafio_de_planta(pl) -> dict | None:
    """El desafío guardado en la planta (o None si la planta no viene de un desafío)."""
    p = getattr(pl, "_p", None)
    return p.get("desafio") if isinstance(p, dict) else None


def saludo(nombre: str, tratamiento: str = "don") -> str:
    """«don Jaime Cifuentes, su desafío es». Sin nombre: «Su desafío es»."""
    nombre = " ".join(str(nombre or "").split())
    if not nombre:
        return "Su desafío es"
    trato = str(tratamiento or "").strip()
    return f"{trato + ' ' if trato else ''}{nombre}, su desafío es"


def estado_sesion(d: dict, nombre: str = "", tratamiento: str = "don") -> dict:
    """Lo que la pantalla Desafío deja en st.session_state["desafio"]: datos del desafío y la serie de demanda."""
    exigir_valido(d)
    dem = d["demanda"]
    return dict(id=d.get("id"), titulo=d["titulo"], producto=d["producto"], rubro=d["rubro"], enunciado=d["enunciado"],
                periodo=dem["periodo"], unidad=dem["unidad"], demanda=serie_demanda(d), etiquetas=list(dem.get("etiquetas") or []),
                demanda_t_h=demanda_t_h(d) if dem["unidad"] in A_TONELADAS and PERIODOS[dem["periodo"]] else None,
                precios=[dict(p) for p in d.get("precios") or []], fuente_demanda=dem.get("fuente", ""),
                nombre=nombre, tratamiento=tratamiento)
