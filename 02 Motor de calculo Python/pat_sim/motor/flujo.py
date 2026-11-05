"""Proceso de diseño iterativo en nueve etapas (PAT 135, tarea T16; correo del profesor Torres del 04-11-2026: «en todo
momento se puede volver atrás»).

Cada etapa tiene su nombre, las pantallas del índice que la componen, un criterio para darla por hecha y una huella (hash)
de sus datos de entrada. Al completar una etapa se guarda su huella y la de todas las anteriores (registrar). Si después
cambia la huella de una etapa anterior, la etapa posterior pasa a «por revisar». Todo trabaja sobre un diccionario con lo que
hay en la sesión (st.session_state sirve tal cual), sin importar Streamlit.

Claves de la sesión que se leen: pl (planta), desafio, seleccion (selección de equipos, de otro equipo), costeo, economia,
mce_parametros, mce_resultado, layout, flujo_registro (lo escribe registrar) y flujo_etapa (etapa elegida cuando dos etapas
comparten pantalla).
"""
from __future__ import annotations
import hashlib
import json
from dataclasses import dataclass

PENDIENTE, HECHA, POR_REVISAR = "pendiente", "hecha", "por revisar"
CLAVE_REGISTRO = "flujo_registro"
CLAVE_ETAPA = "flujo_etapa"


@dataclass(frozen=True)
class Etapa:
    num: int
    nombre: str
    corto: str
    paginas: tuple


# Pantallas según el índice de app.py (GRUPOS); «Selección de equipos» la construye otro equipo.
ETAPAS = (
    Etapa(1, "Desafío", "Desafío", ("Desafío", "Escenario")),
    Etapa(2, "Diseño del diagrama de flujo", "Diagrama", ("Diseño",)),
    Etapa(3, "Selección de equipos comerciales y confiabilidad", "Selección", ("Selección de equipos",)),
    Etapa(4, "Teoría de restricciones y redundancias", "Restricciones", ("Selección de equipos",)),
    Etapa(5, "Balances y equipos auxiliares", "Balances", ("Balances", "Recuperación de calor", "Alternativas")),
    Etapa(6, "Instrumentación", "Instrumentación", ("Instrumentación",)),
    Etapa(7, "Costeo", "Costeo", ("Costeo",)),
    Etapa(8, "Evaluación económica con riesgo", "Economía", ("Economía", "Riesgo económico")),
    Etapa(9, "Layout con cañerías y red eléctrica, isométrica y elevaciones", "Layout", ("Layout",)),
)
NUMEROS = tuple(e.num for e in ETAPAS)
_POR_NUM = {e.num: e for e in ETAPAS}

# Parámetros de los equipos que pertenecen a otras etapas que la de balances
_CLAVES_UNIDADES = ("unidades", "n_unidades", "en_paralelo", "paralelo")
_CLAVES_RESTRICCION = ("capacidad", "estado")
_CLAVES_COSTO = ("costo", "consumo_especifico")


def etapa(num: int) -> Etapa:
    return _POR_NUM[num]


def _hash(obj) -> str:
    texto = json.dumps(obj, sort_keys=True, default=str, ensure_ascii=False)
    return hashlib.sha1(texto.encode("utf-8")).hexdigest()[:12]


def _planta(s):
    return s.get("pl")


def _params(pl, claves=None, excluir=()):
    """Valores de los parámetros de los equipos, filtrados por clave."""
    sal = {}
    for id_, eq in (getattr(pl, "equipos", None) or {}).items():
        for k, p in (getattr(eq, "params", None) or {}).items():
            if claves is not None and k not in claves:
                continue
            if k in excluir:
                continue
            sal[f"{id_}.{k}"] = getattr(p, "valor", p)
    return sal


def _es_unidades(k: str) -> bool:
    return k in _CLAVES_UNIDADES


def _unidades_planta(pl) -> dict:
    return {f"{i}.{k}": getattr(p, "valor", p) for i, eq in (getattr(pl, "equipos", None) or {}).items()
            for k, p in (getattr(eq, "params", None) or {}).items() if _es_unidades(k)}


def seleccion_aplicada(s) -> bool:
    """Selección de equipos aplicada: un registro de selección en la sesión o algún equipo con más de una unidad."""
    if s.get("seleccion"):
        return True
    for v in _unidades_planta(_planta(s)).values():
        try:
            if v is not None and float(v) > 1:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _restricciones_revisadas(s) -> bool:
    sel = s.get("seleccion")
    if isinstance(sel, dict) and any(sel.get(k) for k in ("restricciones", "redundancias", "teoria_restricciones")):
        return True
    return bool(s.get("redundancias"))


def criterio_hecha(n: int, s) -> bool:
    """Si los datos de la sesión permiten dar la etapa por hecha (aparte de que se haya registrado)."""
    from .itinerario import _con_capacidades, _cierra      # PAT 135: condiciones del itinerario del Curso, sin duplicarlas
    pl = _planta(s)
    equipos = getattr(pl, "equipos", None) or {}
    resuelta = bool(getattr(pl, "resuelta", False))
    if n == 1:
        return bool(s.get("desafio"))
    if n == 2:
        return bool(equipos) and bool(getattr(pl, "conexiones", None)) and resuelta
    if n == 3:
        return seleccion_aplicada(s)
    if n == 4:
        return seleccion_aplicada(s) and _restricciones_revisadas(s) and _con_capacidades(pl)
    if n == 5:
        return bool(equipos) and _cierra(pl)          # balances de materia y energía cerrados en cada equipo
    if n == 6:
        return bool(getattr(pl, "instrumentos", None))
    if n == 7:
        c = s.get("costeo")
        return isinstance(c, dict) and bool(c.get("total_clp"))
    if n == 8:
        return s.get("mce_resultado") is not None
    if n == 9:
        lay = s.get("layout")
        return isinstance(lay, dict) and bool(lay.get("posiciones"))
    raise KeyError(n)


def huella_etapa(n: int, s) -> str:
    """Huella de los datos de entrada propios de la etapa n (no incluye los de las etapas anteriores)."""
    pl = _planta(s)
    if n == 1:
        d = s.get("desafio") or {}
        return _hash(dict(titulo=d.get("titulo"), producto=d.get("producto"), rubro=d.get("rubro") or getattr(pl, "rubro", None),
                          demanda=d.get("demanda"), precios=d.get("precios")))
    if n == 2:
        return _hash(dict(equipos={i: getattr(e, "tipo", "") for i, e in (getattr(pl, "equipos", None) or {}).items()},
                          conexiones=[[c.origen, c.puerto_origen, c.destino, c.puerto_destino]
                                      for c in (getattr(pl, "conexiones", None) or [])]))
    if n == 3:
        return _hash(dict(seleccion=s.get("seleccion"), unidades=_unidades_planta(pl)))
    if n == 4:
        return _hash(dict(restricciones=_params(pl, claves=_CLAVES_RESTRICCION), redundancias=s.get("redundancias"),
                          sel=(s.get("seleccion") or {}).get("redundancias") if isinstance(s.get("seleccion"), dict) else None))
    if n == 5:
        ex = _CLAVES_RESTRICCION + _CLAVES_COSTO + _CLAVES_UNIDADES
        return _hash(dict(params=_params(pl, excluir=ex), globales=getattr(pl, "globales", None),
                          especs=[e.__dict__ for e in (getattr(pl, "especs", None) or [])]))
    if n == 6:
        return _hash([i.__dict__ for i in (getattr(pl, "instrumentos", None) or [])])
    if n == 7:
        c = s.get("costeo") if isinstance(s.get("costeo"), dict) else {}
        return _hash(dict(total=c.get("total_clp"), costos=_params(pl, claves=_CLAVES_COSTO)))
    if n == 8:
        return _hash(dict(economia=s.get("economia"), parametros=s.get("mce_parametros")))
    if n == 9:
        lay = s.get("layout") if isinstance(s.get("layout"), dict) else {}
        return _hash({k: lay.get(k) for k in ("posiciones", "dims", "overrides", "longitudes_m")})
    raise KeyError(n)


def registrar_huella(s, n: int) -> dict:
    """Da la etapa n por completada: guarda su huella y la de todas las anteriores (con lo que hay ahora en la sesión)."""
    reg = dict(s.get(CLAVE_REGISTRO) or {})
    reg[n] = dict(propia=huella_etapa(n, s), previas={k: huella_etapa(k, s) for k in NUMEROS if k < n})
    s[CLAVE_REGISTRO] = reg
    return reg[n]


def etapas_cambiadas(n: int, s) -> list:
    """Etapas anteriores a n cuya huella ya no es la que había cuando se registró n."""
    r = (s.get(CLAVE_REGISTRO) or {}).get(n)
    if not r:
        return []
    return [k for k, h in r["previas"].items() if huella_etapa(k, s) != h]


def dada_por_hecha(n: int, s) -> bool:
    """Criterio de los datos o, para la etapa 4 (redundancias), el registro manual mientras siga aplicada la selección."""
    if criterio_hecha(n, s):
        return True
    pl = _planta(s)
    from .itinerario import _con_capacidades
    return n == 4 and n in (s.get(CLAVE_REGISTRO) or {}) and seleccion_aplicada(s) and bool(getattr(pl, 'equipos', None)) and _con_capacidades(pl)


def estado_etapa(n: int, s) -> str:
    if not dada_por_hecha(n, s):
        return PENDIENTE
    return POR_REVISAR if etapas_cambiadas(n, s) else HECHA


def sincronizar(s) -> None:
    """Registra las etapas que ya están hechas y aún no tienen huella, y borra la huella de las que dejaron de estarlo
    (por ejemplo al partir un desafío en blanco, que borra el costeo y el layout). Las que están por revisar no se tocan."""
    for n in NUMEROS:
        reg = s.get(CLAVE_REGISTRO) or {}
        hecha = dada_por_hecha(n, s)
        if hecha and n not in reg:
            registrar_huella(s, n)
        elif not hecha and n in reg:
            reg = dict(reg); reg.pop(n); s[CLAVE_REGISTRO] = reg


def estados(s) -> dict:
    """Estado de cada etapa: pendiente, hecha o por revisar. s es un diccionario (o st.session_state)."""
    return {n: estado_etapa(n, s) for n in NUMEROS}


# ---------------------------------------------------------------- navegación
def etapa_de_pagina(pagina, preferida=None):
    """Etapa a la que pertenece una pantalla (None si no es parte del proceso). Con dos candidatas (Selección de equipos)
    gana la preferida si es una de ellas, y si no la primera."""
    cand = [e.num for e in ETAPAS if pagina in e.paginas]
    if not cand:
        return None
    return preferida if preferida in cand else cand[0]


def pagina_de_etapa(n: int, validas=None):
    """Primera pantalla de la etapa que exista en el índice (validas); None si ninguna existe."""
    for p in etapa(n).paginas:
        if validas is None or p in validas:
            return p
    return None


def etapa_vecina(n, delta: int, validas=None):
    """Etapa anterior (delta=-1) o siguiente (+1) a n que tenga alguna pantalla en el índice; None si no hay."""
    if n is None:
        return None
    k = n + delta
    while 1 <= k <= len(ETAPAS):
        if pagina_de_etapa(k, validas) is not None:
            return k
        k += delta
    return None


def por_revisar(s) -> list:
    return [n for n, e in estados(s).items() if e == POR_REVISAR]
