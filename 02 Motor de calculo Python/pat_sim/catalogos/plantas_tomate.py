"""Catálogo de plantas de pasta de tomate: PAT 138 (13-11-2026) y PAT 139 (14-11-2026, comentarios del profesor Torres).

PAT 139: la planta se describe con dos elecciones independientes.
- MODELO (10): lo que distingue a una planta por su producto y su proceso, sin tamaño: los °Brix de la pasta, el quiebre (hot
  break o cold break), el evaporador con o sin termocompresión del vapor (TVR) y el número de efectos.
- TAMAÑO (3): chica, mediana y grande: tomate por temporada, días de temporada y horas de proceso por día. La mediana es la
  temporada de Agrozzi (450.000 t en 76 días, tres turnos).
La combinación modelo × tamaño (30 plantas) se identifica con una id compuesta «modelo|tamano», por ejemplo «agrozzi|mediana».
El modelo «agrozzi» con el tamaño «mediana» repite exactamente los valores de agrozzi.BASE: crear_escenario("agrozzi|mediana")
da la misma planta que agrozzi.crear() (hot break 15.956,0 kW, cascada 9.073,8 kW y pinch 9.722,9 kW).

Las plantas son variantes de la planta basada en Agrozzi (escenarios/agrozzi.py, el tipo «tomate» de catalogos/plantas_genericas.py):
la misma cadena de operaciones (recepción, lavado, trituración, quiebre, refinado, MVR, múltiple efecto, esterilización,
enfriamiento flash y llenado aséptico) con otra capacidad y otra especificación. Solo se cambian parámetros que el motor ya
soporta en agrozzi.crear:
- season (tomate fresco procesado por temporada), days (días de temporada) y hpd (horas de proceso por día): el tamaño.
- xP (°Brix final de la pasta, que fija la especificación de diseño del evaporador de múltiple efecto): el modelo.
- Thb (temperatura del quiebre: hot break o cold break; el equipo es el mismo calentador de inactivación enzimática): el modelo.
- tvr (termocompresión del vapor en el primer efecto) y N (número de efectos del evaporador de múltiple efecto): el modelo.
  Los dos evaporadores MVR de preconcentración se mantienen en todas.

Compatibilidad con PAT 138: VARIANTES, IDS, tabla(), variante(id), capacidad_media_t_h, fuentes, kw_escenario y crear_escenario
siguen funcionando con las 10 ids viejas (pequena_28, pequena_36cb, mediana_28, mediana_30, mediana_36cb, agrozzi, grande_28,
grande_36cb, muy_grande_30, muy_grande_36cb), con sus mismas toneladas, así los proyectos guardados dan lo mismo. Todas las
funciones aceptan además la id compuesta «modelo|tamano» y el id de un modelo solo (tamaño mediano). traducir(id) lleva una id
vieja a (modelo, tamaño más cercano) y separar_id(id) lleva cualquier id a (modelo, tamaño).

Cada parámetro trae su fuente o la marca «Supuesto» con su justificación (FUENTES). No hay en la carpeta del proyecto datos de
otras plantas chilenas de pasta: las capacidades distintas de Agrozzi son una escala didáctica para comparar tamaños.
"""
from __future__ import annotations

_SD = "sin dato de otra planta chilena en la carpeta del proyecto"
_ODEPA = "contrastar con ODEPA, 2013, «La industria de la pasta de tomate»"
FUENTES = {
    "season_agrozzi": "DIA_Agrozzi_rev0.pdf, p. 47: 450.000 t de tomate por temporada",
    "season_sup": ("Supuesto: escala didáctica de 30.000 t a 900.000 t por temporada (de una planta pequeña al doble de Agrozzi) "
                   "para comparar tamaños; " + _SD + " (" + _ODEPA + ")"),
    # PAT 139: tamaños chica y grande (la mediana es Agrozzi)
    "season_chica": ("Supuesto: un tercio de la temporada de Agrozzi (150.000 t de 450.000 t), una planta de una sola línea que recibe "
                     "la cosecha de menos superficie; " + _SD + " (" + _ODEPA + ")"),
    "season_grande": ("Supuesto: el doble de la temporada de Agrozzi (900.000 t), la cota alta didáctica para comparar tamaños; "
                      + _SD + " (" + _ODEPA + ")"),
    "days_agrozzi": "Balance de Masa_Rev0.pdf, p. 6: febrero a abril, lunes a sábado (76 días)",
    "days_sup": ("Supuesto: una planta pequeña recibe la cosecha de menos superficie y opera menos días; una grande estira la "
                 "temporada de enero a abril (lunes a sábado, como Agrozzi); " + _SD),
    "days_chica": ("Supuesto: 60 días, menos que los 76 de Agrozzi (Balance de Masa_Rev0.pdf, p. 6), porque una planta chica recibe la "
                   "cosecha de menos superficie; " + _SD),
    "days_grande": ("Supuesto: 95 días, más que los 76 de Agrozzi (Balance de Masa_Rev0.pdf, p. 6), porque una planta grande estira la "
                    "temporada de enero a abril (lunes a sábado); " + _SD),
    "hpd_agrozzi": "Tres turnos, Balance de Masa_Rev0.pdf, p. 6",
    "hpd_sup": ("Supuesto: 20 h de proceso y 4 h de limpieza diaria en una planta pequeña sin línea de respaldo; " + _SD),
    "xP_agrozzi": "Pasta de 30 °Brix de la planta basada en Agrozzi (escenarios/agrozzi.py)",
    "xP_sup": ("Supuesto: grados comerciales habituales de la pasta, 28 a 30 °Brix (hot break) y 36 a 38 °Brix (cold break); "
               "sin documento revisado en la carpeta del proyecto"),
    "hot": "Hot break a 90 °C, dentro de 75 a 96 °C (DIA_Agrozzi_rev0.pdf, p. 48)",
    "cold": ("Supuesto: el cold break calienta el tomate triturado a menor temperatura que el hot break para conservar color y "
             "sabor, con una pasta menos viscosa (Fito, Clemente y Sanz, 1983, comparan concentrados hot break y cold break, "
             "Fito_1983.pdf). Se usa 70 °C, la cota alta del cold break, para que el jugo llegue a la ebullición del MVR (70 °C) "
             "sin calor externo; la temperatura es Supuesto"),
    "tvr": "Venus T1500 de triple efecto con termocompresión (TVR), CFT (2024a), como en la planta basada en Agrozzi",
    "sin_tvr": ("Supuesto: múltiple efecto sin termocompresión, como una línea más antigua o más simple; el motor ya lo calcula "
                "(parámetro tvr del evaporador de múltiple efecto)"),
    "n4": ("Supuesto: una planta muy grande justifica un cuarto efecto para bajar el vapor por t evaporada; el motor calcula N "
           "efectos entre las mismas temperaturas del primero y el último efecto (75 °C y 55,57 °C)"),
    "n4_modelo": ("Supuesto: un cuarto efecto baja el vapor por t evaporada a cambio de más equipo; el motor calcula N efectos entre "
                  "las mismas temperaturas del primero y el último efecto (75 °C y 55,57 °C)"),
}

QUIEBRES = {"hot": "Hot break", "cold": "Cold break"}
EVAPORADORES = {
    "tvr3": "Dos MVR y triple efecto con termocompresión (TVR)",
    "me3": "Dos MVR y triple efecto sin termocompresión",
    "tvr4": "Dos MVR y cuádruple efecto con termocompresión (TVR)",
}
_EVAP_CORTO = {"tvr3": "3 efectos con TVR", "me3": "3 efectos sin TVR", "tvr4": "4 efectos con TVR"}


# ================================================================== (a) los 10 modelos (PAT 139)
def _m(id_, brix, quiebre, evap, descripcion, agrozzi=False):
    corto = f"{brix:.0f} °Brix {quiebre} break, {_EVAP_CORTO[evap]}"
    return dict(id=id_, nombre=f"Pasta {brix:.0f} °Brix, {quiebre} break, {_EVAP_CORTO[evap]}" + (" (como Agrozzi)" if agrozzi else ""),
                corto=corto, brix=float(brix), quiebre=quiebre, T_quiebre=90.0 if quiebre == "hot" else 70.0, evaporador=evap,
                tvr=evap != "me3", N=4 if evap == "tvr4" else 3, descripcion=descripcion)


_MODELOS = [
    _m("hot28_me3", 28, "hot", "me3", "Pasta hot break de 28 °Brix con un evaporador simple, sin termocompresión."),
    _m("hot28_tvr3", 28, "hot", "tvr3", "Pasta hot break de 28 °Brix con triple efecto y termocompresión del vapor."),
    _m("hot30_me3", 30, "hot", "me3", "Pasta hot break de 30 °Brix con triple efecto sin termocompresión."),
    _m("agrozzi", 30, "hot", "tvr3", "El modelo de referencia: pasta hot break de 30 °Brix con triple efecto y termocompresión, como Agrozzi.",
       agrozzi=True),
    _m("hot30_tvr4", 30, "hot", "tvr4", "Pasta hot break de 30 °Brix con un cuarto efecto en el evaporador."),
    _m("cold36_me3", 36, "cold", "me3", "Pasta cold break de 36 °Brix para salsas y kétchup, sin termocompresión."),
    _m("cold36_tvr3", 36, "cold", "tvr3", "Pasta cold break de 36 °Brix con triple efecto y termocompresión."),
    _m("cold36_tvr4", 36, "cold", "tvr4", "Pasta cold break de 36 °Brix con un cuarto efecto en el evaporador."),
    _m("cold38_me3", 38, "cold", "me3", "Pasta cold break de 38 °Brix, la más concentrada, sin termocompresión."),
    _m("cold38_tvr3", 38, "cold", "tvr3", "Pasta cold break de 38 °Brix con triple efecto y termocompresión."),
]
MODELOS = {m["id"]: m for m in _MODELOS}
IDS_MODELOS = tuple(MODELOS)
MODELO_BASE = "agrozzi"


# ================================================================== (b) los 3 tamaños (PAT 139)
def _t(id_, nombre, season, days, hpd, descripcion, fuente_season, fuente_days, fuente_hpd):
    return dict(id=id_, nombre=nombre, temporada_t=float(season), dias=int(days), horas_dia=float(hpd), descripcion=descripcion,
                media_t_h=float(season) / (int(days) * float(hpd)),
                fuentes=dict(temporada_t=FUENTES[fuente_season], dias=FUENTES[fuente_days], horas_dia=FUENTES[fuente_hpd]))


_TAMANOS = [
    _t("chica", "Chica", 150000, 60, 20, "Un tercio de la temporada de Agrozzi, 60 días y dos turnos y medio (20 h).",
       "season_chica", "days_chica", "hpd_sup"),
    _t("mediana", "Mediana", 450000, 76, 24, "La temporada de Agrozzi: 450.000 t en 76 días y tres turnos.",
       "season_agrozzi", "days_agrozzi", "hpd_agrozzi"),
    _t("grande", "Grande", 900000, 95, 24, "El doble de la temporada de Agrozzi, 95 días y tres turnos.",
       "season_grande", "days_grande", "hpd_agrozzi"),
]
TAMANOS = {t["id"]: t for t in _TAMANOS}
IDS_TAMANOS = tuple(TAMANOS)
TAMANO_BASE = "mediana"
SEP = "|"


def modelo(modelo_id: str | None) -> dict:
    """El modelo (None da el modelo Agrozzi)."""
    k = MODELO_BASE if modelo_id is None else modelo_id
    if k not in MODELOS:
        raise KeyError(f"No existe el modelo de planta de tomate «{modelo_id}». Use uno de: {', '.join(IDS_MODELOS)}")
    return MODELOS[k]


def tamano(tamano_id: str | None) -> dict:
    """El tamaño (None da el mediano, el de Agrozzi)."""
    k = TAMANO_BASE if tamano_id is None else tamano_id
    if k not in TAMANOS:
        raise KeyError(f"No existe el tamaño de planta de tomate «{tamano_id}». Use uno de: {', '.join(IDS_TAMANOS)}")
    return TAMANOS[k]


def id_compuesta(modelo_id: str | None, tamano_id: str | None = None) -> str:
    """«modelo|tamano» (valida los dos; sin tamaño, el mediano)."""
    return f"{modelo(modelo_id)['id']}{SEP}{tamano(tamano_id)['id']}"


# ================================================================== (c) las 10 ids de PAT 138 (compatibilidad)
def _v(id_, nombre, corto, season, days, hpd, brix, quiebre, evap, descripcion):
    return dict(id=id_, nombre=nombre, corto=corto, temporada_t=float(season), dias=int(days), horas_dia=float(hpd),
                brix=float(brix), quiebre=quiebre, T_quiebre=90.0 if quiebre == "hot" else 70.0, evaporador=evap,
                tvr=evap != "me3", N=4 if evap == "tvr4" else 3, descripcion=descripcion)


_VARIANTES = [
    _v("pequena_28", "Planta pequeña de pasta 28 °Brix (30.000 t por temporada)", "Pequeña 28 °Brix", 30000, 60, 20, 28, "hot", "me3",
       "Planta pequeña de dos turnos y medio, pasta hot break de 28 °Brix y evaporador sin termocompresión."),
    _v("pequena_36cb", "Planta pequeña de pasta 36 °Brix cold break (60.000 t por temporada)", "Pequeña 36 °Brix cold break",
       60000, 65, 20, 36, "cold", "me3", "Planta pequeña de pasta cold break de 36 °Brix para salsas y kétchup."),
    _v("mediana_28", "Planta mediana de pasta 28 °Brix (120.000 t por temporada)", "Mediana 28 °Brix", 120000, 70, 24, 28, "hot", "me3",
       "Planta mediana de tres turnos, pasta hot break de 28 °Brix, sin termocompresión."),
    _v("mediana_30", "Planta mediana de pasta 30 °Brix (200.000 t por temporada)", "Mediana 30 °Brix", 200000, 70, 24, 30, "hot", "tvr3",
       "Planta mediana con la misma tecnología de Agrozzi y menos de la mitad de su capacidad."),
    _v("mediana_36cb", "Planta mediana de pasta 36 °Brix cold break (300.000 t por temporada)", "Mediana 36 °Brix cold break",
       300000, 72, 24, 36, "cold", "tvr3", "Planta mediana de pasta cold break de 36 °Brix con termocompresión."),
    _v("agrozzi", "Planta basada en Agrozzi, pasta 30 °Brix (450.000 t por temporada)", "Basada en Agrozzi 30 °Brix",
       450000, 76, 24, 30, "hot", "tvr3", "La planta de referencia: Agrozzi en Teno, con las cifras de Modelo_PAT_Agrozzi_v2.xlsx."),
    _v("grande_28", "Planta grande de pasta 28 °Brix (550.000 t por temporada)", "Grande 28 °Brix", 550000, 80, 24, 28, "hot", "me3",
       "Planta grande de pasta hot break de 28 °Brix con evaporador sin termocompresión."),
    _v("grande_36cb", "Planta grande de pasta 36 °Brix cold break (650.000 t por temporada)", "Grande 36 °Brix cold break",
       650000, 85, 24, 36, "cold", "tvr3", "Planta grande de pasta cold break de 36 °Brix con termocompresión."),
    _v("muy_grande_30", "Planta muy grande de pasta 30 °Brix, cuádruple efecto (750.000 t por temporada)", "Muy grande 30 °Brix",
       750000, 90, 24, 30, "hot", "tvr4", "Planta muy grande de pasta hot break con un cuarto efecto en el evaporador."),
    _v("muy_grande_36cb", "Planta muy grande de pasta 36 °Brix cold break, cuádruple efecto (900.000 t por temporada)",
       "Muy grande 36 °Brix cold break", 900000, 95, 24, 36, "cold", "tvr4",
       "Planta muy grande de pasta cold break con un cuarto efecto: el doble de la capacidad de Agrozzi."),
]
_LEGADAS = {v["id"]: v for v in _VARIANTES}
IDS = tuple(_LEGADAS)
BASE = "agrozzi"


def _modelo_de(v: dict) -> str:
    """Modelo con los mismos °Brix, quiebre, evaporador y efectos de una variante vieja."""
    return next(m["id"] for m in _MODELOS if (m["brix"], m["quiebre"], m["tvr"], m["N"]) == (v["brix"], v["quiebre"], v["tvr"], v["N"]))


def _tamano_cercano(toneladas: float) -> str:
    import math
    return min(_TAMANOS, key=lambda t: abs(math.log(t["temporada_t"] / toneladas)))["id"]


# id vieja -> (modelo, tamaño más cercano en toneladas); los valores propios de cada id vieja no cambian (_LEGADAS)
LEGADAS = {k: (_modelo_de(v), _tamano_cercano(v["temporada_t"])) for k, v in _LEGADAS.items()}
LEGADAS["agrozzi"] = (MODELO_BASE, TAMANO_BASE)


class _Variantes(dict):
    """Las 10 variantes de PAT 138 (iteración, len e items); además reconoce con [] y con «in» la id compuesta «modelo|tamano» y el
    id de un modelo solo (tamaño mediano), para que el código de PAT 138 (ui/comun.tomate_sesion, p_proyectos, pruebas) siga
    funcionando con las ids de PAT 139."""

    def __contains__(self, k):
        if dict.__contains__(self, k):
            return True
        try:
            return isinstance(k, str) and bool(_compuesta(k))
        except KeyError:
            return False

    def __missing__(self, k):
        return variante(k)

    def get(self, k, defecto=None):
        try:
            return self[k]
        except (KeyError, TypeError):
            return defecto


VARIANTES = _Variantes(_LEGADAS)


def es_legada(variante_id: str | None) -> bool:
    """True si es una de las 10 ids de PAT 138 (el id «agrozzi» cuenta como vieja y como modelo)."""
    return variante_id in _LEGADAS


def es_solo_legada(variante_id: str | None) -> bool:
    """True si es una de las 10 ids de PAT 138 que no es un modelo (todas menos «agrozzi»): solo existe con las toneladas de antes."""
    return variante_id in _LEGADAS and variante_id not in MODELOS


def separar_id(variante_id: str | None, tamano_id: str | None = None) -> tuple[str, str]:
    """(modelo, tamaño) de cualquier id: compuesta «modelo|tamano», un modelo solo (con tamano_id o el mediano), una id vieja
    (traducción al tamaño más cercano, ver LEGADAS) o None (Agrozzi mediana)."""
    if variante_id is None:
        return MODELO_BASE, tamano(tamano_id)["id"]
    if isinstance(variante_id, str) and SEP in variante_id:
        m, t = variante_id.split(SEP, 1)
        return modelo(m)["id"], tamano(t)["id"]
    if variante_id in MODELOS:
        return variante_id, tamano(tamano_id)["id"]
    if variante_id in LEGADAS:
        m, t = LEGADAS[variante_id]
        return m, tamano(tamano_id)["id"] if tamano_id else t
    raise KeyError(f"No existe el tipo de planta de tomate «{variante_id}». Use un modelo ({', '.join(IDS_MODELOS)}), "
                   f"«modelo{SEP}tamano» o una de las ids de PAT 138 ({', '.join(IDS)})")


def traducir(variante_id: str | None) -> tuple[str, str]:
    """Id vieja de PAT 138 (o cualquier id) -> (modelo, tamaño más cercano). Solo es aproximada en las toneladas: la id vieja
    sigue dando su planta exacta en variante() y crear_escenario()."""
    return separar_id(variante_id)


def _compuesta(k: str) -> dict:
    """Variante armada con un modelo y un tamaño (id compuesta o modelo solo). KeyError si no existe."""
    m, t = separar_id(k)
    if k not in MODELOS and SEP not in k:
        raise KeyError(k)
    M, T = modelo(m), tamano(t)
    toneladas = f"{T['temporada_t']:,.0f}".replace(",", ".")
    return dict(id=id_compuesta(m, t), modelo=m, tamano=t, legada=False, nombre=f"Planta {T['nombre'].lower()} de pasta {M['corto']} ({toneladas} t por temporada)",
                corto=f"{T['nombre']} {M['corto']}", temporada_t=T["temporada_t"], dias=T["dias"], horas_dia=T["horas_dia"], brix=M["brix"],
                quiebre=M["quiebre"], T_quiebre=M["T_quiebre"], evaporador=M["evaporador"], tvr=M["tvr"], N=M["N"],
                descripcion=f"{M['descripcion']} Tamaño {T['nombre'].lower()}: {T['descripcion']}")


def variante(variante_id: str | None) -> dict:
    """La planta de tomate de una id: una de las 10 ids de PAT 138, la id compuesta «modelo|tamano» o un modelo solo (tamaño
    mediano). None da la planta basada en Agrozzi. El dict trae temporada_t, dias, horas_dia, brix, quiebre, T_quiebre, evaporador,
    tvr, N, nombre, corto y descripcion, más modelo y tamano (en una id vieja, el tamaño más cercano)."""
    k = BASE if variante_id is None else variante_id
    if isinstance(k, str) and k in _LEGADAS:
        return dict(_LEGADAS[k], modelo=LEGADAS[k][0], tamano=LEGADAS[k][1], legada=True)
    try:
        if isinstance(k, str) and (k in MODELOS or SEP in k):
            return _compuesta(k)
    except KeyError as e:
        raise KeyError(f"No existe el tipo de planta de tomate «{variante_id}»: {e.args[0]}") from None
    raise KeyError(f"No existe el tipo de planta de tomate «{variante_id}». Use un modelo ({', '.join(IDS_MODELOS)}), "
                   f"«modelo{SEP}tamano» o una de las ids de PAT 138 ({', '.join(IDS)})")


def es_base(variante_id: str | None) -> bool:
    """True si la planta es exactamente la de Agrozzi (id «agrozzi» o «agrozzi|mediana»)."""
    v = variante(variante_id)
    return v["id"] in (BASE, id_compuesta(MODELO_BASE, TAMANO_BASE))


def capacidad_media_t_h(variante_id: str | None) -> float:
    """t/h de tomate fresco en promedio de la temporada = temporada / (días × horas por día)."""
    v = variante(variante_id)
    return v["temporada_t"] / (v["dias"] * v["horas_dia"])


def fuentes_modelo(modelo_id: str | None) -> dict:
    """Fuente o Supuesto de cada parámetro del modelo: °Brix, quiebre y evaporador."""
    m = modelo(modelo_id)
    return dict(brix=FUENTES["xP_agrozzi" if m["brix"] == 30 else "xP_sup"], quiebre=FUENTES[m["quiebre"]],
                evaporador=FUENTES["tvr" if m["evaporador"] == "tvr3" else "sin_tvr" if m["evaporador"] == "me3" else "n4_modelo"])


def fuentes_tamano(tamano_id: str | None) -> dict:
    """Fuente o Supuesto de cada parámetro del tamaño: tomate por temporada, días y horas por día."""
    return dict(tamano(tamano_id)["fuentes"])


def fuentes(variante_id: str | None) -> dict:
    """Fuente o Supuesto de cada parámetro de la planta (id vieja, compuesta o modelo solo)."""
    v = variante(variante_id)
    if not v["legada"]:
        return dict(fuentes_tamano(v["tamano"]), **fuentes_modelo(v["modelo"]))
    base = v["id"] == BASE
    return dict(temporada_t=FUENTES["season_agrozzi" if base else "season_sup"],
                dias=FUENTES["days_agrozzi" if base else "days_sup"],
                horas_dia=FUENTES["hpd_agrozzi" if v["horas_dia"] == 24 else "hpd_sup"],
                brix=FUENTES["xP_agrozzi" if v["brix"] == 30 else "xP_sup"],
                quiebre=FUENTES[v["quiebre"]],
                evaporador=FUENTES["tvr" if v["evaporador"] == "tvr3" else "sin_tvr" if v["evaporador"] == "me3" else "n4"])


def kw_escenario(variante_id: str | None) -> dict:
    """Argumentos de escenarios/agrozzi.crear para la planta (los nombres de agrozzi.BASE)."""
    v = variante(variante_id)
    return dict(season=v["temporada_t"], days=v["dias"], hpd=v["horas_dia"], xP=v["brix"] / 100.0, Thb=v["T_quiebre"],
                tvr=v["tvr"], N=v["N"])


def crear_escenario(variante_id: str | None = None, capacidades: bool = True):
    """Planta calculada: escenarios/agrozzi.crear con los parámetros de la planta (id vieja, compuesta o modelo solo). El modelo
    «agrozzi» con el tamaño «mediana» es exactamente agrozzi.crear()."""
    from ..escenarios import agrozzi as A
    v = variante(variante_id)
    pl = A.crear(capacidades=capacidades, **kw_escenario(variante_id))
    if not es_base(v["id"]):
        pl.nombre = v["nombre"]
    ajustar_nombres(pl, variante_id)
    return pl


def ajustar_nombres(pl, variante_id: str | None) -> None:
    """En las plantas cold break, el calentador de inactivación enzimática se llama «cold break» (el equipo es el mismo)."""
    v = variante(variante_id)
    if v["quiebre"] != "cold":
        return
    for e in pl.equipos.values():
        if e.tipo == "hot_break":
            e.nombre = f"Cold break ({v['T_quiebre']:.0f} °C)"


def tabla() -> list[dict]:
    """Las 10 ids de PAT 138 con su capacidad (para el informe y la pantalla)."""
    return [dict(id=k, nombre=v["nombre"], temporada_t=v["temporada_t"], dias=v["dias"], horas_dia=v["horas_dia"],
                 media_t_h=capacidad_media_t_h(k), brix=v["brix"], quiebre=QUIEBRES[v["quiebre"]], T_quiebre=v["T_quiebre"],
                 evaporador=EVAPORADORES[v["evaporador"]]) for k, v in _LEGADAS.items()]


def tabla_modelos() -> list[dict]:
    """Los 10 modelos con sus °Brix, quiebre, evaporador y la fuente de cada parámetro (PAT 139)."""
    return [dict(id=m["id"], nombre=m["nombre"], brix=m["brix"], quiebre=QUIEBRES[m["quiebre"]], T_quiebre=m["T_quiebre"],
                 evaporador=EVAPORADORES[m["evaporador"]], efectos=m["N"], tvr=m["tvr"], fuentes=fuentes_modelo(m["id"]))
            for m in _MODELOS]


def tabla_tamanos() -> list[dict]:
    """Los 3 tamaños con su tomate por temporada, días, horas por día, t/h media y la fuente de cada parámetro (PAT 139)."""
    return [dict(id=t["id"], nombre=t["nombre"], temporada_t=t["temporada_t"], dias=t["dias"], horas_dia=t["horas_dia"],
                 media_t_h=t["media_t_h"], fuentes=dict(t["fuentes"])) for t in _TAMANOS]


def combinaciones() -> list[str]:
    """Las 30 plantas modelo × tamaño como ids compuestas, en el orden del catálogo."""
    return [id_compuesta(m, t) for m in IDS_MODELOS for t in IDS_TAMANOS]
