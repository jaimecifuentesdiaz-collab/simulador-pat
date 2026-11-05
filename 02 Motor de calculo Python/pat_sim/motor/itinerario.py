"""Itinerario guiado (PAT 133, mejora 17): etapas de la práctica con su condición de cumplimiento y una pista.

Cada condición se evalúa sobre la sesión (un diccionario o st.session_state) y la planta, sin tocar ninguna de las dos.
PAT 135 (T16): las nueve etapas del proceso de diseño iterativo vienen de motor/flujo.py (la misma guía de la franja de
arriba de cada pantalla) y se suman las tres propias del curso: Operación, Calidad SPC y Evaluación. Una etapa de diseño con
un cambio en una anterior queda «por revisar» y no cuenta como cumplida. El orden es una recomendación."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

from . import flujo as FL

TOL_CIERRE = 1e-3       # cierre relativo de materia y energía aceptado por equipo (0,1 %); Supuesto: el motor cierra en 1e-10


def _g(ss, k, defecto=None):
    try:
        return ss.get(k, defecto)
    except AttributeError:
        return getattr(ss, k, defecto)


def _con_capacidades(pl) -> bool:
    return any(e.params["capacidad"].valor for e in pl.equipos.values() if "capacidad" in e.params)


def _cierra(pl) -> bool:
    if not pl.resuelta:
        return False
    for f in pl.cierres():
        if abs(f["cierre_masa"]) > TOL_CIERRE * max(abs(f["masa_entra"]), 1.0):
            return False
        ce = f.get("cierre_energia")
        if ce is not None and abs(ce) > TOL_CIERRE * max(abs(f["energia_entra"]), 1.0):
            return False
    return True


def _spc_con_datos(op) -> bool:
    from .operacion import S
    return op is not None and len(op.lab) >= int(S["min_muestras_spc"])


@dataclass(frozen=True)
class Etapa:
    clave: str
    nombre: str
    pestana: str
    meta: str
    pista: str
    condicion: Callable


class _Vista:
    """La sesión con la planta indicada, para evaluar las condiciones de flujo.py con la planta recibida."""
    def __init__(self, ss, pl):
        self.ss, self.pl = ss, pl

    def get(self, k, defecto=None):
        return self.pl if k == "pl" else _g(self.ss, k, defecto)

    def __setitem__(self, k, v):
        self.ss[k] = v


_PISTAS = {
    1: "En Desafío, elija el desafío y presione «Partir en blanco», o siga con el escenario cargado.",
    2: "En Diseño, conecte los equipos hasta que la planta quede resuelta.",
    3: "En Selección de equipos, elija equipos comerciales (si hace falta en paralelo) y revise su confiabilidad.",
    4: "En Selección de equipos, revise la teoría de restricciones y el costo de ineficiencia para decidir las redundancias; declare también la capacidad nominal de los equipos.",
    5: "En Balances, revise el cierre de cada equipo; después vea Recuperación de calor y Alternativas.",
    6: "En Instrumentación, defina los lazos de control ISA-5.1.",
    7: "En Costeo, calcule la inversión de la planta.",
    8: "En Economía y Riesgo económico, calcule el VAN con su incertidumbre.",
    9: "En Layout, proponga y ajuste la disposición, con cañerías y red eléctrica.",
}


def _etapa_flujo(e):
    return Etapa(clave=_CLAVES_FLUJO[e.num], nombre=e.nombre, pestana=e.paginas[0],
                 meta=e.nombre + (" completada" if e.num != 1 else " elegido"), pista=_PISTAS[e.num],
                 condicion=lambda ss, pl, r, n=e.num: FL.estado_etapa(n, _Vista(ss, pl)) == FL.HECHA)


_CLAVES_FLUJO = {1: "desafio", 2: "diseno", 3: "seleccion", 4: "restricciones", 5: "balances", 6: "instrumentacion",
                 7: "costeo", 8: "economia", 9: "layout"}

ETAPAS = [_etapa_flujo(e) for e in FL.ETAPAS] + [
    Etapa("operacion", "Operación", "Operación", "Al menos un turno ejecutado",
          "En Operación, fije la meta de utilización y ejecute un turno de 8 h.",
          lambda ss, pl, r: bool(_g(ss, "op") is not None and _g(ss, "op").turnos)),
    Etapa("calidad", "Calidad SPC", "Calidad SPC", "Carta de control con datos (8 resultados de laboratorio o más)",
          "En Calidad SPC, tome una muestra por turno: los resultados llegan uno o dos turnos después y la carta necesita 8.",
          lambda ss, pl, r: _spc_con_datos(_g(ss, "op"))),
    Etapa("evaluacion", "Evaluación", "Evaluación", "Evaluación finalizada",
          "En Evaluación, escriba las justificaciones y presione «Finalizar y revelar evaluación».",
          lambda ss, pl, r: bool(_g(ss, "op") is not None and _g(ss, "op").finalizada)),
]


def _resumen(ss, pl):
    if pl is None or not pl.resuelta:
        return None
    try:
        from .resumen import resumen_planta
        return resumen_planta(pl, cop=float(_g(ss, "cop", 2.0) or 2.0))
    except Exception:
        return None


def evaluar(ss, pl, resumen: dict | None = None) -> list[dict]:
    """Estado de cada etapa: clave, nombre, pestaña, meta, pista y cumplida. resumen: el de motor/resumen.py si ya se calculó."""
    r = resumen if resumen is not None else _resumen(ss, pl)
    out = []
    for e in ETAPAS:
        try:
            ok = bool(e.condicion(ss, pl, r))
        except Exception:                  # una condición que no se puede evaluar cuenta como pendiente
            ok = False
        revisar = False
        if e.clave in _CLAVES_FLUJO.values():                      # PAT 135: una etapa de diseño puede estar por revisar
            n = next(k for k, c in _CLAVES_FLUJO.items() if c == e.clave)
            revisar = FL.estado_etapa(n, _Vista(ss, pl)) == FL.POR_REVISAR
        out.append(dict(clave=e.clave, nombre=e.nombre, pestana=e.pestana, meta=e.meta, pista=e.pista, cumplida=ok,
                        por_revisar=revisar))
    return out


def avance(estado: list[dict]) -> float:
    return sum(1 for e in estado if e["cumplida"]) / len(estado) if estado else 0.0


def siguiente(estado: list[dict]) -> dict | None:
    """Primera etapa pendiente en el orden recomendado (None si todas están cumplidas)."""
    return next((e for e in estado if not e["cumplida"]), None)
