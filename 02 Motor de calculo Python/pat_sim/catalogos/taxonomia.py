"""Taxonomía del catálogo de equipos (PAT 136, tarea T22, punto 7 de los comentarios del profesor Torres del 13-11-2026).

«Catálogo con taxonomía para buscar rápido y ver todos los equipos»: cada tipo de equipo del registro (catalogos/registro.TIPOS)
queda en un árbol por función de proceso y, dentro de ella, por familia de la ISO 10628 (categoría de la Tabla C.1 con su letra
código del Anexo D, UNE-EN ISO 10628:2001; simbolos/iso10628.py), con buscador por texto y filtros por función, familia y tipo de
planta.

De dónde sale la función de cada equipo:
1. Si el tipo aparece en la cadena de operaciones de alguno de los 10 tipos de planta (catalogos/plantas_genericas.py), como equipo
   de la operación o como alternativa, toma la función de esa operación (puede tener varias: el intercambiador de placas pasteuriza
   en una planta y enfría en otra).
2. Si no aparece, se deduce de su familia de la ISO 10628 y de su símbolo (FUNCION_FAMILIA y FUNCION_SIMBOLO): es una
   clasificación del equipo T22 (Supuesto), no de la norma, que solo agrupa símbolos por su forma constructiva.
"""
from __future__ import annotations
import unicodedata

from ..simbolos import iso10628 as ISO

# Funciones del árbol (el orden de la línea de proceso) y las funciones de plantas_genericas.FUNCIONES que agrupa cada una
GRUPOS = [
    ("recepcion", "Recepción, pesaje y almacenamiento", ("recepcion",)),
    ("lavado", "Lavado y selección", ("lavado",)),
    ("reduccion_tamano", "Reducción de tamaño", ("reduccion_tamano",)),
    ("separacion", "Separación sólido-líquido y mecánica", ("separacion_solido_liquido", "separacion_mecanica")),
    ("concentracion", "Concentración y evaporación", ("concentracion",)),
    ("secado", "Secado", ("secado",)),
    ("tratamiento_termico", "Tratamiento térmico", ("tratamiento_termico",)),
    ("reaccion", "Reacción, extracción y fermentación", ("reaccion",)),
    ("mezcla", "Mezcla y acondicionamiento", ("mezcla",)),
    ("conformado", "Conformado", ("conformado",)),
    ("enfriamiento", "Enfriamiento", ("enfriamiento",)),
    ("transporte", "Transporte, bombeo y válvulas", ("transporte",)),
    ("envasado", "Envasado y despacho", ("envasado",)),
    ("servicios", "Servicios (vapor, calor, aire y fuerza)", ("generacion_calor",)),
    ("otros", "Otros equipos de la ISO 10628", ()),
]
NOMBRES = {k: n for k, n, _ in GRUPOS}
_DE_FUNCION = {f: k for k, _n, fs in GRUPOS for f in fs}

# Supuesto del equipo T22: función de un símbolo o de una familia de la Tabla C.1 cuando el tipo no aparece en ninguna planta
FUNCION_SIMBOLO = {
    "caldera": "servicios", "horno": "servicios", "quemador": "servicios", "chimenea": "servicios", "turbina": "servicios",
    "evaporador_pelicula": "concentracion", "evaporador_mvr": "concentracion", "evaporador_multiefecto": "concentracion",
    "condensador": "enfriamiento", "aeroenfriador": "enfriamiento", "torre_enfriamiento": "enfriamiento",
    "enfriador_contracorriente": "enfriamiento", "pelletizadora": "conformado", "extrusora": "conformado",
    "sierra": "reduccion_tamano", "almacenamiento_granel": "recepcion", "compresor": "servicios", "ventilador": "servicios",
    "soplante": "servicios", "eyector": "concentracion", "bomba_vacio": "concentracion", "filtro_mangas": "servicios",
    "dosificador_rotativo": "transporte", "motor": "servicios",
}
FUNCION_FAMILIA = {1: "recepcion", 2: "reaccion", 3: "tratamiento_termico", 4: "tratamiento_termico", 5: "separacion", 6: "separacion",
                   7: "separacion", 8: "separacion", 9: "secado", 10: "reduccion_tamano", 11: "mezcla", 12: "mezcla", 13: "envasado",
                   14: "transporte", 15: "servicios", 16: "transporte", 17: "recepcion", 18: "transporte", 19: "servicios",
                   20: "otros", 21: "transporte", 22: "transporte", 23: "transporte", 24: "transporte"}
FUENTE = ("Funciones: cadenas de operaciones de catalogos/plantas_genericas.py; familias y letras: UNE-EN ISO 10628:2001, Tabla C.1 y "
          "Anexo D (simbolos/iso10628.py); función de los equipos que no están en ninguna planta: Supuesto del equipo T22 (PAT 136)")


def normalizar(t) -> str:
    """Minúsculas y sin tildes, para buscar «cribado» con «CRIBADO» o «cribádo»."""
    t = unicodedata.normalize("NFKD", str(t or "")).encode("ascii", "ignore").decode("ascii")
    return " ".join(t.lower().replace("*", " ").split())


def _uso_en_plantas() -> dict:
    """tipo → {funciones: [...], plantas: [...]} según las cadenas de los 10 tipos de planta (con alternativas y versiones simples)."""
    from . import plantas_genericas as PG
    uso: dict = {}
    for pid, p in PG.PLANTAS.items():
        for o in p["operaciones"]:
            for t in (o["tipo_equipo"],) + tuple(o.get("alternativas") or ()):
                for tt in (t, "simple_" + t):
                    u = uso.setdefault(tt, dict(funciones=[], plantas=[]))
                    f = _DE_FUNCION.get(o["funcion"], "otros")
                    if f not in u["funciones"]:
                        u["funciones"].append(f)
                    if pid not in u["plantas"]:
                        u["plantas"].append(pid)
        for t in p.get("equipos_servicio") or ():
            u = uso.setdefault(t, dict(funciones=[], plantas=[]))
            if "servicios" not in u["funciones"]:
                u["funciones"].append("servicios")
            if pid not in u["plantas"]:
                u["plantas"].append(pid)
    return uso


def ficha(cls, uso: dict | None = None) -> dict:
    """Ficha de taxonomía de una clase de equipo del registro."""
    from . import plantas_genericas as PG
    uso = _uso_en_plantas() if uso is None else uso
    u = uso.get(cls.tipo) or {}
    funciones = list(u.get("funciones") or [])
    origen = "plantas"
    if not funciones:
        origen = "supuesto"
        if cls.tipo.startswith("alimentacion"):
            funciones = ["recepcion"]
        else:
            funciones = [FUNCION_SIMBOLO.get(cls.simbolo) or FUNCION_FAMILIA.get(int(cls.iso_categoria), "otros")]
    cat = int(cls.iso_categoria)
    plantas = list(u.get("plantas") or [])
    return dict(tipo=cls.tipo, nombre=cls.nombre_tipo, funciones=funciones, funcion_nombres=[NOMBRES[f] for f in funciones],
                origen_funcion=origen, familia=cat, familia_nombre=ISO.CATEGORIAS.get(cat, ""), letra=cls.iso_letra, simbolo=cls.simbolo,
                simbolo_nombre=ISO.SIMBOLOS.get(cls.simbolo, ("",))[0], plantas=plantas,
                plantas_nombres=[PG.PLANTAS[p]["nombre"] for p in plantas], rubro=getattr(cls, "rubro", "general"),
                simplificado=cls.tipo.startswith("simple_"), descripcion=getattr(cls, "descripcion", "") or "")


def fichas(tipos: dict | None = None) -> list[dict]:
    """Fichas de todos los tipos del registro (o de los dados), en el orden del árbol: función, familia y nombre."""
    if tipos is None:
        from .registro import TIPOS as tipos
    uso = _uso_en_plantas()
    orden = {k: i for i, (k, _n, _f) in enumerate(GRUPOS)}
    out = [ficha(c, uso) for c in tipos.values()]
    return sorted(out, key=lambda f: (orden[f["funciones"][0]], f["familia"], normalizar(f["nombre"])))


def buscar(texto: str = "", funcion: str | None = None, familia: int | None = None, planta: str | None = None,
           fichas_: list[dict] | None = None, simplificados: bool = True) -> list[dict]:
    """Fichas que cumplen todos los filtros. texto: todas sus palabras deben aparecer en el nombre, el tipo, la letra, el símbolo,
    la función, la familia o el nombre de una planta (sin distinguir mayúsculas ni tildes)."""
    fs = fichas() if fichas_ is None else fichas_
    palabras = normalizar(texto).split()
    out = []
    for f in fs:
        if funcion and funcion not in f["funciones"]:
            continue
        if familia is not None and int(familia) != f["familia"]:
            continue
        if planta and planta not in f["plantas"]:
            continue
        if not simplificados and f["simplificado"]:
            continue
        if palabras:
            texto_f = normalizar(" ".join([f["nombre"], f["tipo"], f["letra"], f["simbolo_nombre"], f["familia_nombre"], str(f["familia"])]
                                          + f["funcion_nombres"] + f["plantas_nombres"]))
            if not all(p in texto_f for p in palabras):
                continue
        out.append(f)
    return out


def arbol(fs: list[dict] | None = None) -> list[dict]:
    """Árbol función → familia ISO 10628 → equipos. Un equipo con varias funciones aparece en cada una."""
    fs = fichas() if fs is None else fs
    out = []
    for k, nombre, _f in GRUPOS:
        fam: dict = {}
        for f in fs:
            if k in f["funciones"]:
                fam.setdefault(f["familia"], []).append(f)
        if fam:
            out.append(dict(funcion=k, nombre=nombre, n=sum(len(v) for v in fam.values()),
                            familias=[dict(familia=c, nombre=ISO.CATEGORIAS.get(c, ""), letras=sorted({e["letra"] for e in v}), equipos=v)
                                      for c, v in sorted(fam.items())]))
    return out


def resumen_plantas(fs: list[dict] | None = None) -> list[dict]:
    """Por tipo de planta: cuántos tipos de equipo usa y sus nombres (para ver todos los equipos de las 10 plantas)."""
    from . import plantas_genericas as PG
    fs = fichas() if fs is None else fs
    return [dict(planta_id=pid, planta=p["nombre"], equipos=[f for f in fs if pid in f["plantas"] and not f["simplificado"]])
            for pid, p in PG.PLANTAS.items()]
