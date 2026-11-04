"""Registro de todos los tipos de equipo por rubro, y guardar o cargar una planta como diccionario (JSON)."""
from __future__ import annotations
from . import tomate, servicios, biomasa, iso_generico
from ..motor.planta import Planta, Conexion, EspecDiseno, Instrumento

RUBROS = {"tomate": "Pasta de tomate", "general": "Equipos generales y servicios",
          "pellet": "Pellet de madera", "chip": "Chip de madera (astilla)", "lena": "Leña"}
_PROPIOS = tomate.CATALOGO + servicios.CATALOGO + biomasa.CATALOGO
# PAT 132: equipos genéricos de la ISO 10628 para los símbolos sin modelo propio (solo en «Todos los equipos»)
ISO = iso_generico.catalogo({c.simbolo for c in _PROPIOS})
TIPOS = {c.tipo: c for c in _PROPIOS + ISO}
TODOS = "todos"; NOMBRE_TODOS = "Todos los equipos (ISO 10628)"


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
