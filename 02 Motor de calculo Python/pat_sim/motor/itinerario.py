"""Itinerario guiado (PAT 133, mejora 17): etapas de la práctica con su condición de cumplimiento y una pista.

Cada condición se evalúa sobre la sesión (un diccionario o st.session_state) y la planta, sin tocar ninguna de las dos.
Las etapas siguen el orden de las pestañas: Escenario, Diseño, Operación, Calidad SPC, Balances, Recuperación de calor,
Economía y Evaluación. El orden es una recomendación: una etapa puede cumplirse antes que la anterior."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable

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


ETAPAS = [
    Etapa("escenario", "Escenario", "Escenario", "Planta cargada con su línea de proceso",
          "Elija el rubro en la pestaña Escenario y cargue el escenario base, una plantilla o un proyecto de ejemplo.",
          lambda ss, pl, r: pl is not None and len(pl.equipos) >= 2 and len(pl.conexiones) >= 1),
    Etapa("diseno", "Diseño", "Diseño", "Planta resuelta y con capacidades declaradas",
          "En Diseño, resuelva la planta y declare la capacidad nominal de los equipos (o use «Asignar capacidades»).",
          lambda ss, pl, r: bool(pl is not None and pl.resuelta and _con_capacidades(pl))),
    Etapa("operacion", "Operación", "Operación", "Al menos un turno ejecutado",
          "En Operación, fije la meta de utilización y ejecute un turno de 8 h.",
          lambda ss, pl, r: bool(_g(ss, "op") is not None and _g(ss, "op").turnos)),
    Etapa("calidad", "Calidad SPC", "Calidad SPC", "Carta de control con datos (8 resultados de laboratorio o más)",
          "En Calidad SPC, tome una muestra por turno: los resultados llegan uno o dos turnos después y la carta necesita 8.",
          lambda ss, pl, r: _spc_con_datos(_g(ss, "op"))),
    Etapa("balances", "Balances", "Balances", "Balances de materia y energía cerrados en cada equipo",
          "En Balances, revise el cierre de cada equipo; si no cierra, corrija las conexiones en Diseño.",
          lambda ss, pl, r: bool(pl is not None and _cierra(pl))),
    Etapa("recuperacion", "Recuperación de calor", "Recuperación de calor", "Cascada con calor recuperado",
          "En Recuperación de calor, revise el mapa de residuales y ajuste la aproximación mínima hasta que la cascada recupere calor.",
          lambda ss, pl, r: bool(r and not r.get("sin_sumidero") and (r.get("cascada") or 0) > 0)),
    Etapa("economia", "Economía", "Economía", "Inversión ingresada",
          "En Economía, ingrese o acepte la inversión de la alternativa para calcular el VAN y la TIR.",
          lambda ss, pl, r: float((_g(ss, "economia") or {}).get("inversion") or 0) > 0),
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
        out.append(dict(clave=e.clave, nombre=e.nombre, pestana=e.pestana, meta=e.meta, pista=e.pista, cumplida=ok))
    return out


def avance(estado: list[dict]) -> float:
    return sum(1 for e in estado if e["cumplida"]) / len(estado) if estado else 0.0


def siguiente(estado: list[dict]) -> dict | None:
    """Primera etapa pendiente en el orden recomendado (None si todas están cumplidas)."""
    return next((e for e in estado if not e["cumplida"]), None)
