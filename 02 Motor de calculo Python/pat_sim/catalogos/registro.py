"""Registro de todos los tipos de equipo por rubro, y guardar o cargar una planta como diccionario (JSON)."""
from __future__ import annotations
from . import tomate, servicios, biomasa, iso_generico, agar
from ..motor.planta import Planta, Conexion, EspecDiseno, Instrumento

RUBROS = {"tomate": "Pasta de tomate", "general": "Equipos generales y servicios",
          "pellet": "Pellet de madera", "chip": "Chip de madera (astilla)", "lena": "Leña",
          "agar": "Agar agar"}                      # PAT 143 b (tarea 9): rubro agar agar desde alga Gracilaria (catalogos/agar.py)
_PROPIOS = tomate.CATALOGO + servicios.CATALOGO + biomasa.CATALOGO + agar.CATALOGO
# PAT 132: equipos genéricos de la ISO 10628 para los símbolos sin modelo propio (solo en «Todos los equipos»)
# PAT 143 b: los equipos del agar usan símbolos (reactor, camisa, filtro prensa, placas) que también tienen su genérico «iso_<símbolo>»,
# que usan los tipos de planta de catalogos/plantas_genericas.py: los genéricos se siguen armando con los símbolos de antes del agar
ISO = iso_generico.catalogo({c.simbolo for c in tomate.CATALOGO + servicios.CATALOGO + biomasa.CATALOGO})
# PAT 136 (T22): alimentación genérica y versiones de balance simplificado (puertos de producto) de los equipos de biomasa y del
# secador por pulverización, para la planta automática de los tipos de planta nuevos (motor/sintesis.py). Solo se agregan tipos.
_BIOMASA_PROCESO = [c for c in biomasa.CATALOGO if c.entradas and not c.tipo.startswith(("caldera", "generador", "alimentacion"))]
_ISO_SECADO = [c for c in ISO if c.simbolo in ("secador_pulverizacion",)]
SIMPLES = iso_generico.simplificados(_BIOMASA_PROCESO + _ISO_SECADO)
EXTRA = [iso_generico.AlimentacionGenerica] + SIMPLES
TIPOS = {c.tipo: c for c in _PROPIOS + ISO + EXTRA}
TODOS = "todos"; NOMBRE_TODOS = "Todos los equipos (ISO 10628)"


def nombre_rubro(rubro: str) -> str:
    """PAT 136: nombre del rubro, también para los seis tipos de planta nuevos (catalogos/plantas_genericas.py)."""
    if rubro in RUBROS:
        return RUBROS[rubro]
    try:
        from .plantas_genericas import PLANTAS
        p = next((x for x in PLANTAS.values() if x["rubro"] == rubro), None)
        return p["nombre"] if p else str(rubro)
    except Exception:
        return str(rubro)


def catalogo(rubro: str | None = None) -> list[type]:
    """Tipos de equipo de un rubro más los generales; los equipos de biomasa declaran en «rubros» a cuáles sirven."""
    if rubro in (None, TODOS):                 # todos, ordenados por la categoría de la Tabla C.1 y por nombre
        return sorted(TIPOS.values(), key=lambda c: (c.iso_categoria, c.nombre_tipo))
    return [c for c in TIPOS.values() if c.rubro in (rubro, "general") or rubro in getattr(c, "rubros", ())]


def planta_desde_dict(d: dict) -> Planta:
    pl = Planta(d.get("nombre", "Planta"), d.get("rubro", "general"))
    pl.globales.update(d.get("globales", {}))
    for e in d["equipos"]:
        cls = TIPOS[e["tipo"]]
        eq = cls(e["id"], e.get("nombre"), e.get("x", 0), e.get("y", 0))
        for k, v in e.get("params", {}).items():
            if k in eq.params: eq.set(k, v)
        pl.agregar(eq)
    pl.conexiones = [Conexion(**c) for c in d.get("conexiones", [])]
    pl.especs = [EspecDiseno(**x) for x in d.get("especs", [])]
    pl.instrumentos = [Instrumento(**x) for x in d.get("instrumentos", [])]
    pl._p = d.get("_p")
    return pl
