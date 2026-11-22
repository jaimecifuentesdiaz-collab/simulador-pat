"""Catálogo de plantas de agar agar para la pantalla Desafío (PAT 144 a, 20-11-2026).

Igual que catalogos/plantas_tomate.py, la planta se describe con dos elecciones independientes:
- MODELO (10): el proceso, sin tamaño: concentración de NaOH y temperatura del baño alcalino, temperatura de extracción, agar en
  el extracto, agar en el gel prensado y rendimiento del alga. Cada valor es uno de los extremos o el punto medio de los rangos de
  la literatura ya registrada en catalogos/agar.py y datos/fuentes_agar.csv (McHugh, 2003; Armisen y Galatas, 1987; Belattmania
  et al., 2021; Correa Rivas, 2020). Que dos o más valores vayan juntos en un mismo modelo es Supuesto didáctico.
- TAMAÑO (3): chica, mediana y grande: agar en polvo al año, días de operación y horas por día. La mediana es el escenario base
  (602 t de agar al año en 330 días de 24 h, escenarios/agar.py).
La combinación modelo × tamaño (30 plantas) se identifica con la id compuesta «modelo|tamano», por ejemplo «base|mediana», que da
exactamente la planta de agar.crear().

El alga seca del año de cada planta no se fija a mano: sale del rendimiento global del modelo (el escenario se resuelve con la
especificación de producción de agar y se lee el alga que entra), así un modelo de menor rendimiento pide más alga para el mismo
mercado. La llegada de alga seca (motor/demanda.llegada_agar) reparte ese total en los días de operación con una de las 10
distribuciones de motor/demanda.DISTRIBUCIONES.
"""
from __future__ import annotations
from functools import lru_cache

from .agar import MCHUGH, ARMISEN, BELAT, CORREA

FUENTE_GEN = "catalogos/plantas_genericas.py, tipo de planta agar: 602 t de agar al año (Supuesto ilustrativo del desafío de ejemplo de datos/mantenedor.py)"
_SD = "sin dato de una planta chilena de agar en la carpeta del proyecto"
FUENTES = {
    "naoh_35": f"{MCHUGH}: NaOH al 2 a 5 % para Gracilaria; 3,5 % es el punto medio del rango (escenario base)",
    "naoh_2": f"{MCHUGH}: NaOH al 2 a 5 % para Gracilaria; 2 % es el límite inferior del rango",
    "naoh_5": f"{MCHUGH}: NaOH al 2 a 5 % para Gracilaria; 5 % es el límite superior del rango",
    "bano_85": f"{MCHUGH}: baño a 85 a 90 °C; {ARMISEN}: 80 a 90 °C. 85 °C es el límite inferior de McHugh (escenario base)",
    "bano_90": f"{MCHUGH}: baño a 85 a 90 °C; {ARMISEN}: 80 a 90 °C. 90 °C es el límite superior de los dos",
    "ext_95": f"{MCHUGH}: Gracilaria con agua a 95 a 100 °C por 2 a 4 h; 95 °C es el límite inferior (escenario base)",
    "ext_100": f"{MCHUGH}: Gracilaria con agua a 95 a 100 °C por 2 a 4 h; 100 °C es el límite superior, sin presión",
    "cext_10": f"{ARMISEN}, sección 4: extractos de 0,8 a 1,5 %; {MCHUGH}: el gel tiene cerca de 1 % de agar (escenario base)",
    "cext_08": f"{ARMISEN}, sección 4: extractos de 0,8 a 1,5 %; 0,8 % es el extracto más diluido",
    "cext_15": f"{ARMISEN}, sección 4: extractos de 0,8 a 1,5 %; 1,5 % es el extracto más concentrado",
    "gel_20": f"{MCHUGH}: el gel prensado tiene cerca de 20 % de agar; {ARMISEN}, sección 5D: en promedio 20 % (escenario base)",
    "gel_25": f"{ARMISEN}, sección 5D: la sinéresis deja el gel con hasta 25 % de agar",
    "rend_correa": f"{CORREA}: 23,26 % de agar en Agarophyton chilense sin extracción previa de proteínas (escenario base)",
    "rend_belat": f"{BELAT}: 20,5 % de agar en Gracilaria gracilis con tratamiento alcalino",
    "combinacion": ("Supuesto didáctico: cada valor viene de la literatura citada, pero que vayan juntos en un mismo modelo no está "
                    "documentado en una planta; " + _SD),
    # tamaños
    "agar_mediana": FUENTE_GEN,
    "agar_chica": ("Supuesto: cerca de un tercio de las 602 t de agar al año del escenario base (200 t), como el tamaño chico del tomate; "
                   + _SD),
    "agar_grande": ("Supuesto: cerca del doble de las 602 t de agar al año del escenario base (1.200 t), la cota alta didáctica para "
                    "comparar tamaños; " + _SD),
    "dias": ("Supuesto de catalogos/agar.py (recepción del alga): el alga seca se guarda en fardos (Armisen y Galatas, 1987), así que "
             "la planta trabaja todo el año con 35 días de mantención"),
    "hpd_24": "Supuesto de catalogos/agar.py (recepción del alga): tres turnos",
    "hpd_16": ("Supuesto: dos turnos (16 h), porque una planta chica no justifica el tercer turno; " + _SD),
}

# ================================================================== (a) los 10 modelos
_BASE_P = dict(naoh=0.035, Tbano=85.0, Text=95.0, cext=0.010, xgel=0.20, rend=0.2326)
_FUENTE_DE = {   # (clave, valor) -> fuente
    ("naoh", 0.035): "naoh_35", ("naoh", 0.02): "naoh_2", ("naoh", 0.05): "naoh_5",
    ("Tbano", 85.0): "bano_85", ("Tbano", 90.0): "bano_90", ("Text", 95.0): "ext_95", ("Text", 100.0): "ext_100",
    ("cext", 0.010): "cext_10", ("cext", 0.008): "cext_08", ("cext", 0.015): "cext_15",
    ("xgel", 0.20): "gel_20", ("xgel", 0.25): "gel_25", ("rend", 0.2326): "rend_correa", ("rend", 0.205): "rend_belat",
}
ETIQUETAS = dict(naoh="NaOH del baño alcalino", Tbano="Temperatura del baño alcalino", Text="Temperatura de extracción",
                 cext="Agar en la fase líquida del extracto", xgel="Agar en el gel prensado", rend="Agar extraído por kg de materia seca del alga")
UNIDADES = dict(naoh="%", Tbano="°C", Text="°C", cext="%", xgel="%", rend="%")


def _num(v: float, d: int) -> str:
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _m(id_, etiqueta, descripcion, base=False, **cambios):
    p = dict(_BASE_P, **cambios)
    for k, v in p.items():
        if (k, v) not in _FUENTE_DE:
            raise KeyError(f"Modelo de agar {id_}: el valor {k} = {v} no tiene fuente registrada")
    d_c = 1 if round(100 * p["cext"], 1) != round(100 * p["cext"]) else 0
    corto = (f"NaOH {_num(100 * p['naoh'], 1 if p['naoh'] == 0.035 else 0)} % a {_num(p['Tbano'], 0)} °C, extracción a "
             f"{_num(p['Text'], 0)} °C, extracto de {_num(100 * p['cext'], d_c)} %, gel de {_num(100 * p['xgel'], 0)} %")
    if p["rend"] != _BASE_P["rend"]:
        corto += f", alga de {_num(100 * p['rend'], 1)} %"
    return dict(id=id_, nombre=corto + (" (escenario base)" if base else ""), corto=corto, etiqueta=etiqueta, descripcion=descripcion,
                cambios=tuple(cambios), **p)


_MODELOS = [
    _m("base", "modelo base", "El modelo de referencia: el escenario base del agar, con las temperaturas más bajas de los rangos y los valores típicos del extracto y del gel.", base=True),
    _m("alcali_suave", "álcali suave", "Baño alcalino con la menor concentración de NaOH del rango: menos soda y casi el mismo vapor.", naoh=0.02),
    _m("alcali_fuerte", "álcali fuerte", "Baño alcalino con la mayor concentración de NaOH y la mayor temperatura del rango.", naoh=0.05, Tbano=90.0),
    _m("extraccion_100", "extracción a 100 °C", "Extracción a 100 °C, el límite superior del rango: más vapor en el extractor.", Text=100.0),
    _m("extracto_diluido", "extracto diluido", "Extracto de 0,8 %: más agua de extracción, más vapor y más calor residual del extracto.", cext=0.008),
    _m("extracto_concentrado", "extracto concentrado", "Extracto de 1,5 %: menos agua de extracción y menos vapor.", cext=0.015),
    _m("prensado_intenso", "prensado intenso", "Prensado del gel hasta 25 % de agar: menos agua que evaporar en el secador.", xgel=0.25),
    _m("alga_gracilis", "alga de menor rendimiento", "Alga de menor contenido de agar (20,5 %): pide más alga seca para el mismo agar.", rend=0.205),
    _m("intensivo", "alto consumo de vapor", "Condiciones de alto consumo de vapor: NaOH 5 % a 90 °C, extracción a 100 °C y extracto de 0,8 %.",
       naoh=0.05, Tbano=90.0, Text=100.0, cext=0.008),
    _m("eficiente", "ahorro de soda, agua y vapor", "Condiciones que ahorran soda, agua y vapor: NaOH 2 %, extracto de 1,5 % y gel prensado hasta 25 %.",
       naoh=0.02, cext=0.015, xgel=0.25),
]
MODELOS = {m["id"]: m for m in _MODELOS}
IDS_MODELOS = tuple(MODELOS)
MODELO_BASE = "base"


# ================================================================== (b) los 3 tamaños
def _t(id_, nombre, agar_t, dias, hpd, descripcion, f_agar, f_hpd):
    return dict(id=id_, nombre=nombre, agar_t_ano=float(agar_t), dias=int(dias), horas_dia=float(hpd), descripcion=descripcion,
                fuentes=dict(agar_t_ano=FUENTES[f_agar], dias=FUENTES["dias"], horas_dia=FUENTES[f_hpd]))


_TAMANOS = [
    _t("chica", "Chica", 200, 330, 16, "Cerca de un tercio del agar del escenario base, 330 días y dos turnos (16 h).", "agar_chica", "hpd_16"),
    _t("mediana", "Mediana", 602, 330, 24, "El escenario base: 602 t de agar al año en 330 días y tres turnos.", "agar_mediana", "hpd_24"),
    _t("grande", "Grande", 1200, 330, 24, "Cerca del doble del agar del escenario base, 330 días y tres turnos.", "agar_grande", "hpd_24"),
]
TAMANOS = {t["id"]: t for t in _TAMANOS}
IDS_TAMANOS = tuple(TAMANOS)
TAMANO_BASE = "mediana"
SEP = "|"


def modelo(modelo_id: str | None) -> dict:
    k = MODELO_BASE if modelo_id is None else modelo_id
    if k not in MODELOS:
        raise KeyError(f"No existe el modelo de planta de agar «{modelo_id}». Use uno de: {', '.join(IDS_MODELOS)}")
    return MODELOS[k]


def tamano(tamano_id: str | None) -> dict:
    k = TAMANO_BASE if tamano_id is None else tamano_id
    if k not in TAMANOS:
        raise KeyError(f"No existe el tamaño de planta de agar «{tamano_id}». Use uno de: {', '.join(IDS_TAMANOS)}")
    return TAMANOS[k]


def id_compuesta(modelo_id: str | None, tamano_id: str | None = None) -> str:
    return f"{modelo(modelo_id)['id']}{SEP}{tamano(tamano_id)['id']}"


def separar_id(variante_id: str | None, tamano_id: str | None = None) -> tuple[str, str]:
    """(modelo, tamaño) de una id compuesta, de un modelo solo (con tamano_id o el mediano) o de None (escenario base)."""
    if variante_id is None:
        return MODELO_BASE, tamano(tamano_id)["id"]
    if isinstance(variante_id, str) and SEP in variante_id:
        m, t = variante_id.split(SEP, 1)
        return modelo(m)["id"], tamano(t)["id"]
    return modelo(variante_id)["id"], tamano(tamano_id)["id"]


def es_variante(variante_id) -> bool:
    """True si la id es un modelo de agar o una id compuesta de agar válida."""
    try:
        return isinstance(variante_id, str) and bool(separar_id(variante_id))
    except KeyError:
        return False


def kw_escenario(variante_id: str | None) -> dict:
    """Argumentos de escenarios/agar.crear (los nombres de agar.BASE). El modelo base con el tamaño mediano da agar.BASE."""
    from ..escenarios import agar as EA
    m, t = separar_id(variante_id)
    M, T = MODELOS[m], TAMANOS[t]
    prod = EA.AGAR_T_ANO / (330 * 24) if (m, t) == (MODELO_BASE, TAMANO_BASE) else T["agar_t_ano"] / (T["dias"] * T["horas_dia"])
    return dict(produccion=prod, dias=T["dias"], hpd=T["horas_dia"], naoh=M["naoh"], Tbano=M["Tbano"], Text=M["Text"],
                cext=M["cext"], xgel=M["xgel"], rend=M["rend"])


@lru_cache(maxsize=None)
def alga_por_agar(modelo_id: str) -> float:
    """t de alga seca recibida por t de agar en polvo del modelo (el escenario resuelto con la especificación de producción)."""
    from ..escenarios import agar as EA
    pl = EA.crear(capacidades=False, **kw_escenario(id_compuesta(modelo_id, TAMANO_BASE)))
    r = EA.resumen_corto(pl)
    return float(r["alga_t_h"]) / float(r["producto_t_h"])


def variante(variante_id: str | None) -> dict:
    """La planta de agar de una id compuesta «modelo|tamano» o de un modelo solo (tamaño mediano); None da el escenario base. Trae
    modelo, tamano, nombre, corto, descripción, los parámetros del proceso, agar_t_ano, dias, horas_dia y alga_t_ano (Derivado)."""
    m, t = separar_id(variante_id)
    M, T = MODELOS[m], TAMANOS[t]
    alga = T["agar_t_ano"] * alga_por_agar(m)
    ton = _num(T["agar_t_ano"], 0)
    return dict(id=id_compuesta(m, t), modelo=m, tamano=t, rubro="agar",
                nombre=f"Planta {T['nombre'].lower()} de agar agar en polvo, {M['etiqueta']} ({ton} t de agar al año)",
                corto=f"{T['nombre']}, {M['corto']}", descripcion=f"{M['descripcion']} Tamaño {T['nombre'].lower()}: {T['descripcion']}",
                agar_t_ano=T["agar_t_ano"], dias=T["dias"], horas_dia=T["horas_dia"], alga_t_ano=alga,
                **{k: M[k] for k in _BASE_P})


def es_base(variante_id: str | None) -> bool:
    return separar_id(variante_id) == (MODELO_BASE, TAMANO_BASE)


def fuentes_modelo(modelo_id: str | None) -> dict:
    M = modelo(modelo_id)
    out = {k: FUENTES[_FUENTE_DE[(k, M[k])]] for k in _BASE_P}
    if len(M["cambios"]) > 1:
        out["combinacion"] = FUENTES["combinacion"]
    return out


def fuentes_tamano(tamano_id: str | None) -> dict:
    return dict(tamano(tamano_id)["fuentes"])


def fuentes(variante_id: str | None) -> dict:
    m, t = separar_id(variante_id)
    return dict(fuentes_tamano(t), alga_t_ano=("Derivado: agar del año × alga seca por kg de agar del modelo (escenario resuelto con "
                                                "escenarios/agar.py)"), **fuentes_modelo(m))


# parámetro del escenario -> (tipo de equipo, clave del parámetro del equipo)
_PARAM_EQUIPO = dict(naoh=("tratamiento_alcalino_agar", "conc_naoh"), Tbano=("tratamiento_alcalino_agar", "T_bano"),
                     Text=("extractor_agar", "T_extraccion"), cext=("extractor_agar", "conc_extracto"),
                     xgel=("prensa_gel_agar", "solidos_salida"), rend=("extractor_agar", "rendimiento"))


def ajustar_fuentes(pl, variante_id: str | None) -> None:
    """En los parámetros que el modelo cambia, la fuente y la justificación del valor del modelo (catalogos/agar.py trae las del
    escenario base, por ejemplo «punto medio del rango»)."""
    m, _t_ = separar_id(variante_id)
    M = MODELOS[m]
    for k in M["cambios"]:
        tipo, clave = _PARAM_EQUIPO[k]
        for e in pl.equipos.values():
            if e.tipo == tipo and clave in e.params:
                e.set(clave, e.v(clave), categoria="Literatura", fuente=FUENTES[_FUENTE_DE[(k, M[k])]],
                      justificacion=f"Modelo de planta de agar «{M['corto']}» (catalogos/plantas_agar.py)")


def crear_escenario(variante_id: str | None = None, capacidades: bool = True):
    """Planta calculada: escenarios/agar.crear con los parámetros del modelo y del tamaño. «base|mediana» es exactamente agar.crear()."""
    from ..escenarios import agar as EA
    v = variante(variante_id)
    pl = EA.crear(capacidades=capacidades, **kw_escenario(v["id"]))
    if not es_base(v["id"]):
        pl.nombre = v["nombre"]
    ajustar_fuentes(pl, v["id"])
    return pl


def tabla_modelos() -> list[dict]:
    return [dict(id=m["id"], nombre=m["nombre"], fuentes=fuentes_modelo(m["id"]), **{k: m[k] for k in _BASE_P}) for m in _MODELOS]


def tabla_tamanos() -> list[dict]:
    return [dict(id=t["id"], nombre=t["nombre"], agar_t_ano=t["agar_t_ano"], dias=t["dias"], horas_dia=t["horas_dia"],
                 fuentes=dict(t["fuentes"])) for t in _TAMANOS]


def combinaciones() -> list[str]:
    return [id_compuesta(m, t) for m in IDS_MODELOS for t in IDS_TAMANOS]
