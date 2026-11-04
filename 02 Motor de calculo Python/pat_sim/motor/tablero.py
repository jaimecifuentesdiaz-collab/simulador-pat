"""Tableros como los de FlexSim (PAT 134): estados por equipo, Gantt, producción, contenido, permanencia, OEE y dinámica.

Traslado a pat_sim, en palabras propias, de los tableros (*dashboards*) de FlexSim descritos en
01 Requisitos y diseno/Diseno_FlexSim_PAT134_02nov2026.md: una biblioteca de gráficos agrupada en Estado, Producción,
Contenido, Permanencia, Indicadores y Dinámica, que mira los datos de las pestañas Operación (motor/operacion.py),
Temporada (motor/temporada.py) y Dinámica (motor/dinamico.py). Los gráficos son SVG propios, sin dependencias, con un
color fijo por estado y leyenda; exportar_html junta todos los gráficos y tablas en un archivo (como «Export All
Dashboards to HTML» de FlexSim) y exportar_csv entrega sus datos.

Estados por equipo (estados_turnos): Operación registra por turno la meta, la falla, la alerta, el mantenimiento, la
capacidad y lo producido, pero no la hora de cada evento; por eso las horas de cada turno se reparten con las reglas
declaradas en REGLAS (Supuesto con justificación) y el orden de los tramos dentro del turno en el Gantt es
representativo, no cronológico.

Grupo «Línea (estados reales)» (PAT 134, segunda ronda): mira el resultado de motor/linea_fluida.simular_linea (pestaña Línea,
st.session_state.linea_resultado), que simula la línea por *ticks* y registra cada cambio de estado con su hora. Ahí los estados
no se reparten con reglas: el Gantt, las barras y la tabla de permanencia (como la Staytime Table de FlexSim) usan horas reales.
"""
from __future__ import annotations
import html as _h
import inspect
import math
import re
from . import calculadoras as K
from . import operacion as OP
from . import temporada as TM
from .operacion import Supuesto, _cl

# ----------------------------------------------------------------------------------------------- estados y colores
# PAT 134: colores fijos por estado (paleta categórica validada con el validador de daltonismo y contraste de la guía de
# visualización: orden operando, bloqueado, esperando, en falla y en mantenimiento sin pares vecinos confundibles; el gris
# queda para lo detenido por programa, que no es un dato de desempeño).
ESTADOS = [("operando", "Operando", "#1baf7a"), ("bloqueado", "Bloqueado", "#eb6834"), ("esperando", "Esperando", "#2a78d6"),
           ("falla", "En falla", "#e34948"), ("mantenimiento", "En mantenimiento", "#6250d6"),
           ("detenido", "Detenido programado", "#a3a29c")]
NOMBRE_ESTADO = {k: n for k, n, _c in ESTADOS}
COLOR_ESTADO = {k: c for k, _n, c in ESTADOS}
ORDEN_ESTADO = [k for k, _n, _c in ESTADOS]

ESTADOS_LINEA = [("produccion", "Producción", "#1baf7a"), ("arranque", "Arranque", "#2a78d6"), ("limpieza", "Limpieza", "#6250d6"),
                 ("parada", "Parada", "#a3a29c")]
NOMBRE_LINEA = {k: n for k, n, _c in ESTADOS_LINEA}
COLOR_LINEA = {k: c for k, _n, c in ESTADOS_LINEA}
ORDEN_LINEA = [k for k, _n, _c in ESTADOS_LINEA]
TIPO_A_LINEA = {"produccion": "produccion", "arranque": "arranque", "limpieza": "limpieza", "parada": "parada",
                "parada_final": "parada", "fuera_turno": "parada"}
SERIES = ["#2a78d6", "#eb6834", "#1baf7a", "#6250d6"]      # orden fijo de las series de los gráficos de líneas
TINTA, TINTA2, EJE, GRILLA = "#2b2b2b", "#5f5e5a", "#9bacb3", "#e9ecee"

_BH = ("Concepto de bloqueo y hambre de las estaciones de una línea en serie (Hopp y Spearman, 2008): una estación "
       "bloqueada no puede entregar porque la siguiente no recibe y una estación con hambre no tiene qué procesar")
REGLAS = {s.clave: s for s in [
    Supuesto("reparto", "Horas de cada turno repartidas en estados", OP.S["horas_turno"], "h por turno",
             "Operación no registra la hora de cada evento: las horas del turno se reparten con los mismos factores de "
             "capacidad del motor (mantenimiento, falla, alerta, meta y materia prima), en ese orden; Supuesto PAT"),
    Supuesto("critico_falla", "La falla, la alerta y el mantenimiento detienen al equipo crítico", 1.0, "regla",
             "El motor de Operación aplica la falla, la alerta de seguridad y el mantenimiento a la capacidad de toda la línea "
             "a través de su restricción, y el mantenimiento se hace en el equipo crítico; la alerta se cuenta como falla porque "
             "es una detención no programada. Supuesto PAT"),
    Supuesto("bloqueado", "Aguas arriba de la restricción, la capacidad no usada es «bloqueado»", 1.0, "regla",
             _BH + ". Sin pulmones entre equipos (Supuesto PAT), lo que no procesa un equipo anterior a la restricción es "
             "tiempo bloqueado, también mientras la restricción está en falla o en mantenimiento"),
    Supuesto("esperando", "Aguas abajo de la restricción, y en la restricción, la capacidad no usada es «esperando»", 1.0, "regla",
             _BH + ". Lo que no procesa un equipo posterior a la restricción es tiempo con hambre (esperando material)"),
    Supuesto("materia_prima", "La falta de materia prima es «esperando» para todos", 1.0, "regla",
             "Cuando el patio se vacía la línea completa queda sin material; Supuesto PAT con el mismo concepto de hambre"),
    Supuesto("meta", "La meta de utilización bajo 100 % es «detenido programado»", 1.0, "regla",
             "La meta es una decisión de planificación: la parte del turno que no se usa se cuenta como detención programada "
             "y no entra al tiempo planificado del OEE; Supuesto PAT (la alternativa, menor velocidad, bajaría el rendimiento)"),
    Supuesto("sin_capacidad", "Equipo sin capacidad declarada opera todo el tiempo productivo", 1.0, "fracción",
             "Sin capacidad nominal no hay utilización que calcular (por ejemplo, el despacho); sin ninguna capacidad en la planta "
             "se usa la razón entre el estado del equipo crítico y el del equipo, como la producción real de Operación. Supuesto PAT"),
    Supuesto("estado_actual", "La utilización de cada equipo usa el estado actual de la planta", 1.0, "regla",
             "Operación no guarda el estado de cada equipo en cada turno; Supuesto PAT"),
]}
FUENTE_OEE = "OEE = disponibilidad × rendimiento × calidad (Nakajima, 1988), con calculadoras.oee del motor"

# ----------------------------------------------------------------------------------------------- biblioteca
GRUPO_LINEA = "Línea (estados reales)"
GRUPOS = ["Estado", "Producción", "Contenido", "Permanencia", "Indicadores", "Dinámica", GRUPO_LINEA]
CATALOGO = [
    ("estado_barras", "Estado", "Tiempo en cada estado por equipo", "operacion"),
    ("estado_torta", "Estado", "Torta de estados por equipo", "operacion"),
    ("estado_gantt_turnos", "Estado", "Gantt de estados por equipo en los turnos", "operacion"),
    ("estado_gantt_temporada", "Estado", "Gantt de estados de la línea en la temporada", "temporada"),
    ("prod_acum_turnos", "Producción", "Producción acumulada en los turnos", "operacion"),
    ("prod_por_turno", "Producción", "Producción, demanda y ventas por turno", "operacion"),
    ("prod_acum_temporada", "Producción", "Producción acumulada en la temporada", "temporada"),
    ("cont_cola_hora", "Contenido", "Camiones en espera hora a hora", "temporada"),
    ("cont_patio_temporada", "Contenido", "Materia prima en el patio por día", "temporada"),
    ("cont_patio_turnos", "Contenido", "Patio y bodega en los turnos", "operacion"),
    ("perm_histograma", "Permanencia", "Histograma de esperas de los camiones", "temporada"),
    ("perm_tabla", "Permanencia", "Tabla de permanencia", "temporada"),
    ("ind_oee", "Indicadores", "Tarjetas de OEE", "operacion"),
    ("ind_utilizacion", "Indicadores", "Utilización por equipo", "operacion"),
    ("din_temperatura", "Dinámica", "Temperatura en el arranque y la parada", "dinamica"),
    ("din_calor", "Dinámica", "Calor entregado y calor recuperable", "dinamica"),
    ("din_secado", "Dinámica", "Humedad de la carga en el secado por cargas", "dinamica"),
    # PAT 134: estados simulados por ticks en la pestaña Línea (motor/linea_fluida.py), con horas reales
    ("linea_barras", GRUPO_LINEA, "Tiempo en cada estado por equipo en la línea simulada", "linea"),
    ("linea_gantt", GRUPO_LINEA, "Gantt de estados por equipo con horas reales", "linea"),
    ("linea_niveles", GRUPO_LINEA, "Niveles de los tanques pulmón en el tiempo", "linea"),
    ("linea_tasas", GRUPO_LINEA, "Tasa de proceso por equipo en el tiempo", "linea"),
    ("linea_permanencia", GRUPO_LINEA, "Tabla de permanencia en cada estado", "linea"),
    ("linea_oee", GRUPO_LINEA, "Tarjetas de OEE de la línea", "linea"),
]
TITULO = {i: t for i, _g, t, _f in CATALOGO}
GRUPO = {i: g for i, g, _t, _f in CATALOGO}
FUENTE = {i: f for i, _g, _t, f in CATALOGO}
POR_DEFECTO = ["estado_barras", "estado_torta", "ind_oee", "ind_utilizacion", "prod_acum_turnos", "estado_gantt_temporada"]
MULTIPLES = {"estado_torta", "linea_niveles", "linea_tasas"}     # gráficos pequeños repetidos (uno por equipo o tanque) en grilla
NOTA_LINEA = ("Estados simulados por *ticks* en la pestaña Línea (motor/linea_fluida.py): cada cambio de estado queda con su hora, "
              "así que estas horas son reales. La vista de turnos de Operación (grupo Estado) no simula: reparte las horas de cada "
              "turno en estados con las reglas declaradas al final.")


def catalogo_por_grupo() -> dict:
    return {g: [i for i, gg, _t, _f in CATALOGO if gg == g] for g in GRUPOS}


# ----------------------------------------------------------------------------------------------- línea de equipos
def equipos_linea(pl, ln: dict) -> list:
    """Equipos de proceso de la línea en orden de flujo (sin alimentación, calderas ni generadores)."""
    util = ln.get("util") or {}
    try:
        orden = pl.orden()
    except ValueError:
        orden = list(pl.equipos)
    return [k for k in orden if k in util and k in pl.equipos and not pl.equipos[k].tipo.startswith(("alimentacion", "caldera", "generador"))]


def ancestros(pl, k: str) -> set:
    """Equipos aguas arriba de k por las conexiones de proceso (sin servicios)."""
    padres = {}
    for c in pl.conexiones:
        if not pl.es_servicio(c):
            padres.setdefault(c.destino, set()).add(c.origen)
    vistos, pila = set(), [k]
    while pila:
        for p in padres.get(pila.pop(), ()):
            if p not in vistos:
                vistos.add(p); pila.append(p)
    return vistos


def ritmos(pl, ln: dict, eqs: list | None = None) -> dict:
    """Fracción del tiempo productivo de la línea en que cada equipo opera (0 a 1), con el estado actual de la planta."""
    eqs = eqs if eqs is not None else equipos_linea(pl, ln)
    util = ln.get("util") or {}; c = ln.get("critico"); out = {}
    if ln.get("con_capacidades") and c in util:
        dc, pc = float(util[c]["demanda"] or 0), float(util[c]["procesado"] or 0)
        s = pc / dc if dc > 0 else 1.0              # razón con que la restricción frena lo que viene de arriba
        arriba = ancestros(pl, c)
        for k in eqs:
            v = util.get(k) or {}; cap = v.get("efectiva")
            if not cap:
                out[k] = REGLAS["sin_capacidad"].valor; continue
            ritmo = float(v["demanda"]) * s if k in arriba else float(v["procesado"])
            out[k] = max(0.0, min(1.0, ritmo / float(cap)))
    else:
        est = ln.get("estados") or {}; ec = est.get(c, 1.0) if c else 1.0
        for k in eqs:
            ek = est.get(k)
            out[k] = 1.0 if not ek else max(0.0, min(1.0, ec / ek))
    return out


def _vacio() -> dict:
    return {k: 0.0 for k in ORDEN_ESTADO}


def horas_turno(reg: dict) -> dict:
    """Horas del turno según sus factores: mantenimiento, falla, alerta, detención por la meta, falta de materia prima y producción."""
    H = OP.S["horas_turno"]; disp = H
    h_m = disp * (1 - OP.S["f_mant"]) if reg.get("mantenimiento", "ninguno") != "ninguno" else 0.0; disp -= h_m
    h_f = disp * (1 - OP.S["disp_falla"]) if reg.get("falla") else 0.0; disp -= h_f
    h_a = disp * (1 - OP.S["f_alerta"]) if reg.get("alerta") else 0.0; disp -= h_a
    meta = max(0.0, min(1.0, float(reg.get("meta", 1.0))))
    h_p = disp * (1 - meta); disp *= meta
    cap = float(reg.get("capacidad") or 0.0)
    lim = max(0.0, min(1.0, float(reg.get("producido") or 0.0) / cap)) if cap > 1e-12 else 1.0
    return dict(total=H, mantenimiento=h_m, falla=h_f, alerta=h_a, programada=h_p, materia_prima=disp * (1 - lim), produccion=disp * lim)


def estados_turno(reg: dict, eqs: list, critico: str, arriba: set, u: dict) -> dict:
    """Horas de cada estado de cada equipo en un turno (las de cada equipo suman las horas del turno)."""
    h = horas_turno(reg); det = h["mantenimiento"] + h["falla"] + h["alerta"]; out = {}
    for k in eqs:
        e = _vacio(); uk = u.get(k, 1.0)
        e["detenido"] = h["programada"]; e["esperando"] = h["materia_prima"]
        e["operando"] = h["produccion"] * uk
        libre = h["produccion"] * (1 - uk)
        if k == critico:
            e["mantenimiento"] = h["mantenimiento"]; e["falla"] = h["falla"] + h["alerta"]; e["esperando"] += libre
        elif k in arriba:
            e["bloqueado"] = det + libre
        else:
            e["esperando"] += det + libre
        out[k] = e
    return out


def estados_turnos(turnos: list, pl, ln: dict, equipos: list | None = None) -> dict:
    """Estados por equipo como FlexSim desde los turnos de Operación: por turno y en total, con la utilización."""
    todos = equipos_linea(pl, ln)
    eqs = [k for k in (equipos or todos) if k in todos] or todos
    u = ritmos(pl, ln, todos)
    c0 = ln.get("critico") if ln.get("critico") in todos else (todos[0] if todos else None)
    cache, por_turno = {}, []
    total = {k: _vacio() for k in eqs}
    for reg in turnos:
        c = reg.get("critico") if reg.get("critico") in todos else c0
        if c not in cache:
            cache[c] = ancestros(pl, c) if c else set()
        e = estados_turno(reg, eqs, c, cache[c], u)
        por_turno.append(dict(turno=reg.get("turno"), critico=c, estados=e))
        for k in eqs:
            for s in ORDEN_ESTADO:
                total[k][s] += e[k][s]
    H = OP.S["horas_turno"] * len(turnos)
    util = {k: (total[k]["operando"] / H if H else 0.0) for k in eqs}
    return dict(equipos=eqs, nombres={k: pl.equipos[k].nombre for k in eqs}, critico=c0, por_turno=por_turno, total=total,
                horas=H, utilizacion=util, ritmos={k: u.get(k) for k in eqs}, aguas_arriba=[k for k in todos if k in cache.get(c0, set())] if c0 else [])


def oee_operacion(turnos: list, ln: dict) -> dict | None:
    """OEE de los turnos (Nakajima, 1988): tiempo planificado = horas de los turnos menos la detención por la meta;
    tiempo operado = horas de producción; capacidad ideal = producción planificada de la planta (t/h)."""
    if not turnos or not ln or not ln.get("plan"):
        return None
    hs = [horas_turno(r) for r in turnos]
    plan_h = sum(h["total"] - h["programada"] for h in hs); op_h = sum(h["produccion"] for h in hs)
    prod = sum(float(r["producido"]) for r in turnos); bueno = sum(float(r["conforme"]) for r in turnos)
    if plan_h <= 0:
        return dict(disponibilidad=0.0, rendimiento=0.0, calidad=0.0, oee=0.0, tiempo_planificado_h=0.0, tiempo_operado_h=0.0,
                    producido_t=prod, conforme_t=bueno)
    if op_h <= 0:
        o = dict(disponibilidad=0.0, rendimiento=0.0, calidad=0.0, oee=0.0)
    else:
        o = K.oee(plan_h, op_h, float(ln["plan"]), prod, bueno)
    o.update(tiempo_planificado_h=plan_h, tiempo_operado_h=op_h, producido_t=prod, conforme_t=bueno)
    return o


# ----------------------------------------------------------------------------------------------- temporada
def gantt_linea(programa: dict) -> list:
    """Tramos (inicio_h, fin_h, estado) de la línea en la temporada: producción, arranque, limpieza y parada."""
    out = []
    for b in sorted(programa["barras"], key=lambda x: x["inicio_h"]):
        s = TIPO_A_LINEA.get(b["tipo"], "parada")
        if out and out[-1][2] == s and abs(out[-1][1] - b["inicio_h"]) < 1e-9:
            out[-1] = (out[-1][0], b["fin_h"], s)
        else:
            out.append((b["inicio_h"], b["fin_h"], s))
    return out


def horas_linea(programa: dict) -> dict:
    h = {k: 0.0 for k in ORDEN_LINEA}
    for i, f, s in gantt_linea(programa):
        h[s] += f - i
    return h


def produccion_temporada(programa: dict) -> list:
    """Producción por día y acumulada de la temporada (t): ritmo real de la línea × horas de producción de cada día."""
    D = int(programa.get("dias") or round(programa["horas_totales"] / 24)); r = float(programa.get("produccion_t_h") or 0.0)
    horas = [0.0] * D
    for b in programa["barras"]:
        if b["tipo"] != "produccion":
            continue
        k = max(0, int(b["inicio_h"] // 24))
        while k < D and 24.0 * k < b["fin_h"]:
            horas[k] += max(0.0, min(b["fin_h"], 24.0 * k + 24) - max(b["inicio_h"], 24.0 * k)); k += 1
    acum, out = 0.0, []
    for k, hk in enumerate(horas):
        acum += r * hk
        out.append(dict(dia=k + 1, horas_produccion=hk, produccion_t=r * hk, acumulada_t=acum))
    return out


def esperas(llegadas: dict) -> tuple:
    """Esperas de los camiones (h): las de cada camión si la temporada las entrega (esperas_h); si no, la espera media de
    cada día con los camiones de ese día como pesos, con un aviso."""
    if llegadas.get("esperas_h") is not None:
        return [float(x) for x in llegadas["esperas_h"]], None, None
    v = [float(x["espera_media_h"]) for x in llegadas["dias"] if x["camiones"]]
    w = [float(x["camiones"]) for x in llegadas["dias"] if x["camiones"]]
    return v, w, ("La temporada no entrega la espera de cada camión: el histograma usa la espera media de cada día, "
                  "ponderada por sus camiones, y el mínimo y el máximo son los de esas medias diarias.")


def histograma(valores: list, pesos: list | None = None, clases: int | None = None) -> dict:
    """Histograma de frecuencias. Número de clases de Sturges, 1 + log2(n) (Sturges, 1926), si no se indica."""
    v = [float(x) for x in valores]; w = [1.0] * len(v) if pesos is None else [float(x) for x in pesos]
    n = sum(w)
    if not v or n <= 0:
        return dict(bordes=[0.0, 1.0], conteos=[0.0], n=0.0, media=None, minimo=None, maximo=None)
    lo, hi = min(v), max(v)
    k = clases or max(1, int(math.ceil(1 + math.log2(max(1.0, n)))))
    if hi - lo < 1e-12:
        hi = lo + 1.0; k = 1
    ancho = (hi - lo) / k
    bordes = [lo + i * ancho for i in range(k + 1)]; conteos = [0.0] * k
    for x, wi in zip(v, w):
        conteos[min(k - 1, int((x - lo) / ancho))] += wi
    return dict(bordes=bordes, conteos=conteos, n=n, media=sum(x * wi for x, wi in zip(v, w)) / n, minimo=min(v), maximo=max(v))


def permanencia(valores: list, pesos: list | None = None) -> dict:
    """Media, mínimo, máximo y desviación estándar de los tiempos de permanencia (Staytime de FlexSim)."""
    if not valores:
        return dict(n=0, media=None, minimo=None, maximo=None, desviacion=None)
    w = [1.0] * len(valores) if pesos is None else [float(x) for x in pesos]; n = sum(w)
    m = sum(x * wi for x, wi in zip(valores, w)) / n
    var = sum(wi * (x - m) ** 2 for x, wi in zip(valores, w)) / (n - 1) if n > 1 else 0.0
    return dict(n=n, media=m, minimo=min(valores), maximo=max(valores), desviacion=math.sqrt(max(0.0, var)))


def parametros_temporada(pl, P: dict | None = None) -> dict:
    """Parámetros de la temporada como los guarda la pestaña Temporada (st.session_state.temporada[rubro]) o, sin ellos,
    los supuestos del rubro."""
    sp = TM.supuestos(pl)
    base = dict(semilla=1, camion=sp["camion"], cv=sp["cv_servicio"], umbral=sp["umbral"], tasa=100 * sp["tasa"], base="recepcion",
                con_programa=True, arranque=sp["arranque"], cip_cada=sp["cip_cada"], cip_dur=sp["cip_dur"], parada_cada=sp["parada_cada"],
                parada_dur=sp["parada_dur"], parada_final=sp["parada_final"], pico=sp.get("pico", 0.5), ancho=sp.get("ancho", 0.25))
    base.update(P or {})
    return base


def acepta(fn, nombre: str) -> bool:
    try:
        return nombre in inspect.signature(fn).parameters
    except (TypeError, ValueError):
        return False


def simular_temporada(pl, P: dict | None = None, resumen: dict | None = None, extra_llegadas: dict | None = None) -> tuple:
    """Programa y llegadas de la temporada con los mismos parámetros de la pestaña Temporada. extra_llegadas: argumentos
    adicionales de llegadas_temporada (por ejemplo dist_descarga), que solo se pasan si la función los acepta."""
    P = parametros_temporada(pl, P)
    pr = TM.programa_temporada(pl, arranque_h=P["arranque"], cip_cada_h=P["cip_cada"], cip_duracion_h=P["cip_dur"],
                               parada_cada_d=P["parada_cada"], parada_duracion_h=P["parada_dur"], parada_final_h=P["parada_final"],
                               resumen=resumen if resumen is not None else {})
    extra = {k: v for k, v in (extra_llegadas or {}).items() if v is not None and acepta(TM.llegadas_temporada, k)}
    ll = TM.llegadas_temporada(pl, semilla=int(P["semilla"]), camion_t=P["camion"], cv_servicio=P["cv"], pico=P["pico"], ancho=P["ancho"],
                               umbral_h=P["umbral"], tasa_h=P["tasa"] / 100, base=P["base"], programa=pr if P["con_programa"] else None, **extra)
    return pr, ll


# ----------------------------------------------------------------------------------------------- línea simulada (PAT 134)
MAPA_LINEA = {"operando": "operando", "bloqueado": "bloqueado", "esperando": "esperando", "en_falla": "falla",
              "en_mantenimiento": "mantenimiento", "detenido_programado": "detenido"}


def simular_linea_defecto(pl, horas: float = 72.0, semilla: int = 1) -> dict:
    """Simula la línea con los valores por defecto de motor/linea_fluida.py (fallas y tanques Supuesto) durante `horas` h."""
    from .linea_fluida import simular_linea
    return simular_linea(pl, horas=horas, semilla=semilla)


def linea_vale(res, pl) -> bool:
    """True si el resultado de la Línea es un resultado de simular_linea del mismo rubro de la planta."""
    return (isinstance(res, dict) and bool(res.get("tramos")) and bool(res.get("equipos"))
            and (res.get("parametros") or {}).get("rubro", getattr(pl, "rubro", "")) == getattr(pl, "rubro", ""))


def estados_linea(res: dict, equipos: list | None = None) -> dict:
    """Estados de la línea simulada con las claves de los tableros: horas por estado, tramos (inicio_h, fin_h, estado) y
    utilización por equipo. equipos: filtro opcional (si no calza ninguno, se usan todos)."""
    todos = [e["id"] for e in res["equipos"]]
    eqs = [k for k in todos if k in (equipos or [])] or todos
    nombres = {e["id"]: e["nombre"] for e in res["equipos"]}
    total = {k: _vacio() for k in eqs}; tramos = {k: [] for k in eqs}
    for t in res["tramos"]:
        k = t["equipo"]
        if k not in total:
            continue
        s = MAPA_LINEA.get(t["estado"], t["estado"]); h = float(t["fin_h"]) - float(t["inicio_h"])
        total[k][s] = total[k].get(s, 0.0) + h
        tramos[k].append((float(t["inicio_h"]), float(t["fin_h"]), s))
    H = float((res.get("parametros") or {}).get("horas") or (res["tiempo_h"][-1] if res.get("tiempo_h") else 0.0))
    pe = res.get("por_equipo") or {}
    return dict(equipos=eqs, nombres=nombres, total=total, tramos=tramos, horas=H,
                utilizacion={k: (pe.get(k) or {}).get("utilizacion") for k in eqs})


def permanencia_linea(res: dict, equipos: list | None = None) -> list:
    """Tabla de permanencia en cada estado (como la Staytime Table de FlexSim): por equipo y estado, número de tramos y media,
    mínimo, máximo y desviación estándar de su duración (h). Los tramos del inicio y del final quedan cortados por el horizonte."""
    est = estados_linea(res, equipos); filas = []
    for k in est["equipos"]:
        for s in ORDEN_ESTADO:
            d = [b - a for a, b, ss in est["tramos"][k] if ss == s]
            if not d:
                continue
            pm = permanencia(d)
            filas.append(dict(equipo=k, nombre=est["nombres"][k], estado=NOMBRE_ESTADO[s], tramos=len(d), horas=sum(d), media=pm["media"],
                              minimo=pm["minimo"], maximo=pm["maximo"], desviacion=pm["desviacion"]))
    return filas


def tarjetas_oee_linea(res: dict) -> list:
    """Tarjetas de OEE de la línea simulada: OEE con la tasa planificada (como Temporada y Tableros), sus tres factores, el OEE
    respecto del recurso crítico (oee_critico) y la producción."""
    o = res.get("oee_detalle") or {}; oc = res.get("oee_critico_detalle") or {}
    plan = res.get("tasa_planificada_t_h", o.get("tasa_ideal_t_h")); H = float((res.get("parametros") or {}).get("horas") or 0.0)
    tj = [dict(nombre="OEE de la línea", valor=res.get("oee"), tipo="pct",
               nota=(f"tasa ideal {_cl(plan, 2)} t/h planificadas, como Temporada y Tableros" if plan else "tasa planificada")),
          dict(nombre="Disponibilidad", valor=o.get("disponibilidad"), tipo="pct", nota=f"{_cl(float(res.get('horas_planificadas') or 0.0), 1)} h planificadas"),
          dict(nombre="Rendimiento", valor=o.get("rendimiento"), tipo="pct", nota="producción / (tasa ideal × horas en que produjo)"),
          dict(nombre="Calidad", valor=o.get("calidad"), tipo="pct", nota="Supuesto: la línea no muestrea calidad")]
    if res.get("oee_critico") is not None:
        tj.append(dict(nombre="OEE respecto del recurso crítico", valor=res["oee_critico"], tipo="pct",
                       nota=f"tasa ideal {_cl(float(oc.get('tasa_ideal_t_h') or res.get('tasa_maxima_linea_t_h') or 0.0), 2)} t/h del recurso crítico"))
    tj.append(dict(nombre="Producción de la línea", valor=float(res.get("produccion_t") or 0.0), tipo="num", nota=f"t de producto en {_cl(H, 0)} h"))
    return tj


# ----------------------------------------------------------------------------------------------- contexto
def contexto(pl, turnos: list | None = None, ln: dict | None = None, equipos: list | None = None, temporada: dict | None = None,
             resumen: dict | None = None, extra_llegadas: dict | None = None, necesita: set | None = None,
             linea: dict | None = None, simular_linea: bool = True) -> dict:
    """Datos de los tableros. necesita: fuentes que se calculan ('operacion', 'temporada', 'dinamica', 'linea'); por defecto
    todas. linea: resultado de linea_fluida.simular_linea (st.session_state.linea_resultado); sin él, se simulan 72 h con los
    valores por defecto si simular_linea es True. Los errores de cada fuente quedan en avisos y no detienen a las demás."""
    necesita = {"operacion", "temporada", "dinamica", "linea"} if necesita is None else set(necesita)
    ctx = dict(pl=pl, rubro=pl.rubro, turnos=list(turnos or []), ln=None, estados=None, oee=None, programa=None, llegadas=None,
               dinamica=None, secado=None, linea=None, linea_equipos=list(equipos or []), avisos={})
    if "operacion" in necesita:
        try:
            ctx["ln"] = ln if ln is not None else OP.linea(pl)
            if ctx["ln"] is None:
                ctx["avisos"]["operacion"] = "La planta no entrega producto: no hay línea que mirar."
            else:
                ctx["estados"] = estados_turnos(ctx["turnos"], pl, ctx["ln"], equipos)
                ctx["oee"] = oee_operacion(ctx["turnos"], ctx["ln"])
                if not ctx["turnos"]:
                    ctx["avisos"]["operacion"] = "Todavía no hay turnos de Operación."
        except Exception as e:                  # planta sin resolver o sin restricciones
            ctx["avisos"]["operacion"] = f"No se pudo leer la Operación: {e}"
    if "temporada" in necesita:
        try:
            ctx["programa"], ctx["llegadas"] = simular_temporada(pl, temporada, resumen, extra_llegadas)
        except Exception as e:
            ctx["avisos"]["temporada"] = f"No se pudo simular la temporada: {e}"
    if "dinamica" in necesita:
        from . import dinamico as DN
        try:
            ctx["dinamica"] = DN.arranque_parada(pl, resumen)
        except Exception as e:
            ctx["avisos"]["dinamica"] = f"No se pudo simular el arranque y la parada: {e}"
        if pl.rubro != "tomate":
            try:
                ctx["secado"] = DN.secado_cargas_planta(pl)
            except Exception as e:
                ctx["avisos"]["secado"] = f"No se pudo simular el secado por cargas: {e}"
    if "linea" in necesita:
        if linea is not None and linea_vale(linea, pl):
            ctx["linea"] = linea
        elif simular_linea:
            try:
                ctx["linea"] = simular_linea_defecto(pl)
            except Exception as e:
                ctx["avisos"]["linea"] = f"No se pudo simular la línea: {e}"
        else:
            ctx["avisos"]["linea"] = ("El resultado de la Línea es de otro rubro: vuelva a simularla." if linea is not None else
                                      "Todavía no hay simulación de la Línea: simúlela en la pestaña Línea o con el botón de 72 h.")
    return ctx


# ----------------------------------------------------------------------------------------------- SVG
def _t(x, y, s, tam=11, color=TINTA, anc="start", peso="normal") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" font-size="{tam}" fill="{color}" text-anchor="{anc}" font-weight="{peso}">'
            f'{_h.escape(str(s))}</text>')


def _abrir(ancho, alto, titulo, max_ancho: int | None = None) -> list:
    tope = f";max-width:{max_ancho}px" if max_ancho else ""
    return [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%" role="img" aria-label="{_h.escape(titulo)}" '
            f'style="font-family:sans-serif;background:#fff{tope}">', f'<rect x="0" y="0" width="{ancho}" height="{alto}" fill="#fff"/>',
            _t(12, 20, titulo, 13, "#36586c", peso="600")]


def _leyenda(claves, nombres, colores, x0, y0, ancho) -> tuple:
    """Leyenda en filas: cuadro de color y nombre. Devuelve (partes, alto ocupado)."""
    p, x, y = [], x0, y0
    for k in claves:
        w = 22 + 6.4 * len(nombres[k])
        if x + w > ancho - 8 and x > x0:
            x = x0; y += 18
        p.append(f'<rect x="{x:.1f}" y="{y - 9:.1f}" width="11" height="11" rx="2" fill="{colores[k]}"/>' + _t(x + 15, y, nombres[k], 11, TINTA2))
        x += w + 10
    return p, (y - y0) + 18


def _ticks(lo: float, hi: float, n: int = 5) -> list:
    if hi - lo < 1e-12:
        return [lo]
    paso = (hi - lo) / n; m = 10 ** math.floor(math.log10(paso)); r = paso / m
    paso = (1 if r <= 1 else 2 if r <= 2 else 2.5 if r <= 2.5 else 5 if r <= 5 else 10) * m
    t = math.ceil(lo / paso - 1e-9) * paso; out = []
    while t <= hi + 1e-9 * paso:
        out.append(t); t += paso
    return out


def _dec(paso: float) -> int:
    return 0 if paso >= 1 or paso <= 0 else min(4, int(math.ceil(-math.log10(paso) - 1e-9)))


def barras_apiladas_svg(filas: list, titulo: str, orden: list | None = None, colores: dict | None = None, nombres: dict | None = None,
                        ancho: int = 680) -> str:
    """Barras horizontales apiladas en % del tiempo. filas: [(etiqueta, {estado: horas})]."""
    orden = orden or ORDEN_ESTADO; colores = colores or COLOR_ESTADO; nombres = nombres or NOMBRE_ESTADO
    usados = [k for k in orden if any(v.get(k, 0) > 1e-9 for _e, v in filas)] or orden[:1]
    izq, der, fila = 170, 24, 26
    ley, h_ley = _leyenda(usados, nombres, colores, izq, 42, ancho)
    arriba = 42 + h_ley + 4; alto = arriba + fila * len(filas) + 44
    p = _abrir(ancho, alto, titulo) + ley
    X = lambda f: izq + f * (ancho - izq - der)
    y1 = arriba + fila * len(filas)
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        p.append(f'<path d="M{X(t):.1f} {arriba}V{y1}" stroke="{GRILLA}"/>' + _t(X(t), y1 + 14, f"{int(100 * t)} %", 10, TINTA2, "middle"))
    p.append(_t((izq + ancho - der) / 2, y1 + 32, "Porcentaje del tiempo", 11, TINTA2, "middle"))
    for i, (et, v) in enumerate(filas):
        y = arriba + i * fila; tot = sum(v.get(k, 0.0) for k in orden)
        p.append(_t(izq - 8, y + fila / 2 + 4, et, 11, TINTA, "end"))
        x = 0.0
        for k in orden:
            hk = v.get(k, 0.0)
            if hk <= 1e-9 or tot <= 0:
                continue
            f = hk / tot; xa, xb = X(x), X(x + f)
            w = max(0.5, xb - xa - (2 if xb - xa > 3 else 0))
            p.append(f'<rect x="{xa:.2f}" y="{y + 5}" width="{w:.2f}" height="{fila - 10}" rx="2" fill="{colores[k]}">'
                     f'<title>{_h.escape(f"{et}: {nombres[k]} {_cl(hk, 1)} h ({_cl(100 * f, 1)} %)")}</title></rect>')
            x += f
    p.append(f'<path d="M{izq} {arriba}V{y1}" stroke="{EJE}"/></svg>')
    return "".join(p)


def torta_svg(valores: dict, titulo: str, orden: list | None = None, colores: dict | None = None, nombres: dict | None = None,
              ancho: int = 300) -> str:
    """Torta de estados (en FlexSim las tortas solo existen para datos de estado), con el % de cada parte rotulado."""
    orden = orden or ORDEN_ESTADO; colores = colores or COLOR_ESTADO; nombres = nombres or NOMBRE_ESTADO
    usados = [k for k in orden if valores.get(k, 0) > 1e-9]
    tot = sum(valores.get(k, 0.0) for k in usados)
    ley, h_ley = _leyenda(usados or orden[:1], nombres, colores, 12, 42, ancho)
    r = 72; cx = ancho / 2; cy = 42 + h_ley + 22 + r; alto = int(cy + r + 30)
    p = _abrir(ancho, alto, titulo, 340) + ley
    if tot <= 0:
        p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{GRILLA}"/>' + _t(cx, cy + 4, "Sin datos", 12, TINTA2, "middle") + "</svg>")
        return "".join(p)
    a = -math.pi / 2
    for k in usados:
        f = valores[k] / tot; b = a + 2 * math.pi * f
        tit = f"{nombres[k]}: {_cl(valores[k], 1)} h ({_cl(100 * f, 1)} %)"
        if f > 0.9999:
            p.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{colores[k]}"><title>{_h.escape(tit)}</title></circle>')
        else:
            x1, y1 = cx + r * math.cos(a), cy + r * math.sin(a); x2, y2 = cx + r * math.cos(b), cy + r * math.sin(b)
            p.append(f'<path d="M{cx:.1f} {cy:.1f}L{x1:.2f} {y1:.2f}A{r} {r} 0 {1 if f > 0.5 else 0} 1 {x2:.2f} {y2:.2f}Z" '
                     f'fill="{colores[k]}" stroke="#fff" stroke-width="2"><title>{_h.escape(tit)}</title></path>')
        if f >= 0.04:
            m = (a + b) / 2; xr, yr = cx + (r + 14) * math.cos(m), cy + (r + 14) * math.sin(m) + 4
            p.append(_t(xr, yr, f"{_cl(100 * f, 0)} %", 10, TINTA, "start" if math.cos(m) > 0.2 else "end" if math.cos(m) < -0.2 else "middle"))
        a = b
    p.append("</svg>")
    return "".join(p)


def gantt_svg(filas: list, T: float, titulo: str, orden: list | None = None, colores: dict | None = None, nombres: dict | None = None,
              escala: float = 24.0, eje: str = "Día", ancho: int = 760, marca: float | None = None) -> str:
    """Gantt de estados: una fila por objeto con sus tramos de color. filas: [(etiqueta, [(inicio_h, fin_h, estado)])];
    el eje se rotula en unidades de escala horas (24 = días, 8 = turnos); marca: separación de las rayas verticales."""
    orden = orden or ORDEN_ESTADO; colores = colores or COLOR_ESTADO; nombres = nombres or NOMBRE_ESTADO
    usados = [k for k in orden if any(s == k for _e, tr in filas for _a, _b, s in tr)] or orden[:1]
    izq, der, fila = 150, 20, 24
    ley, h_ley = _leyenda(usados, nombres, colores, izq, 42, ancho)
    arriba = 42 + h_ley + 4; y1 = arriba + fila * len(filas); alto = y1 + 44
    T = float(T) or 1.0
    X = lambda h: izq + h / T * (ancho - izq - der)
    p = _abrir(ancho, alto, titulo) + ley
    U = T / escala
    paso = next((s for s in (1, 2, 5, 7, 10, 14, 15, 20, 30, 50, 60, 100, 200, 500) if U / s <= 12), max(1, int(U // 10)))
    u = 0
    while u <= U + 1e-9:
        x = X(u * escala)
        p.append(f'<path d="M{x:.1f} {arriba}V{y1}" stroke="{GRILLA}"/>' + _t(x, y1 + 14, _cl(u, 0), 10, TINTA2, "middle"))
        u += paso
    p.append(_t((izq + ancho - der) / 2, y1 + 32, eje, 11, TINTA2, "middle"))
    for i, (et, tramos) in enumerate(filas):
        y = arriba + i * fila
        p.append(f'<rect x="{izq}" y="{y}" width="{ancho - izq - der}" height="{fila}" fill="{"#f7f9f9" if i % 2 else "#fff"}"/>'
                 + _t(izq - 8, y + fila / 2 + 4, et, 11, TINTA, "end"))
        for a, b, s in tramos:
            if b - a <= 1e-9:
                continue
            x = X(a); w = max(0.6, X(b) - x)
            tit = f"{et}: {nombres.get(s, s)} de {_cl(a / escala, 2)} a {_cl(b / escala, 2)} ({_cl(b - a, 1)} h)"
            p.append(f'<rect x="{x:.2f}" y="{y + 4}" width="{w:.2f}" height="{fila - 8}" fill="{colores.get(s, "#999")}">'
                     f'<title>{_h.escape(tit)}</title></rect>')
    p.append(f'<path d="M{izq} {arriba}V{y1}H{ancho - der}" fill="none" stroke="{EJE}"/></svg>')
    return "".join(p)


def histograma_svg(hist: dict, titulo: str, eje_x: str = "Espera (h)", eje_y: str = "Camiones", ancho: int = 680, alto: int = 280,
                   decimales: int = 1) -> str:
    """Histograma de frecuencias con barras contiguas separadas por 2 px y la media marcada."""
    b, c = hist["bordes"], hist["conteos"]
    izq, der, arriba, abajo = 56, 20, 40, 46
    p = _abrir(ancho, alto, titulo)
    hi = max(c) if c and max(c) > 0 else 1.0
    tk = _ticks(0, hi * 1.05, 4); top = max(tk[-1], hi)
    X = lambda v: izq + (v - b[0]) / ((b[-1] - b[0]) or 1) * (ancho - izq - der)
    Y = lambda v: alto - abajo - v / top * (alto - arriba - abajo)
    d = _dec(tk[1] - tk[0]) if len(tk) > 1 else 0
    for t in tk:
        p.append(f'<path d="M{izq} {Y(t):.1f}H{ancho - der}" stroke="{GRILLA}"/>' + _t(izq - 6, Y(t) + 4, _cl(t, d), 10, TINTA2, "end"))
    for i, n in enumerate(c):
        xa, xb = X(b[i]), X(b[i + 1])
        if n > 0:
            p.append(f'<rect x="{xa + 1:.2f}" y="{Y(n):.2f}" width="{max(0.5, xb - xa - 2):.2f}" height="{Y(0) - Y(n):.2f}" rx="2" fill="{SERIES[0]}">'
                     f'<title>{_h.escape(f"{_cl(b[i], decimales)} a {_cl(b[i + 1], decimales)}: {_cl(n, 1 if n % 1 else 0)}")}</title></rect>')
    paso = max(1, len(b) // 8)
    for i in range(0, len(b), paso):
        p.append(_t(X(b[i]), alto - abajo + 14, _cl(b[i], decimales), 10, TINTA2, "middle"))
    if hist.get("media") is not None:
        xm = X(hist["media"])
        p.append(f'<path d="M{xm:.1f} {arriba}V{alto - abajo}" stroke="{TINTA}" stroke-dasharray="4 3"/>'
                 + _t(xm + 4, arriba + 10, f"media {_cl(hist['media'], 2)}", 10, TINTA))
    p += [f'<path d="M{izq} {arriba}V{alto - abajo}H{ancho - der}" fill="none" stroke="{EJE}"/>',
          _t((izq + ancho - der) / 2, alto - 12, eje_x, 11, TINTA2, "middle"), _t(12, 34, eje_y, 10, TINTA2), "</svg>"]
    return "".join(p)


def _reducir(x: list, ys: dict, n: int = 1500) -> tuple:
    """Reduce series largas tomando el máximo de cada grupo (así no se esconden los peaks)."""
    if len(x) <= n:
        return x, ys
    paso = int(math.ceil(len(x) / n))
    return x[::paso], {k: [max(v[i:i + paso]) for i in range(0, len(v), paso)] for k, v in ys.items()}


def lineas_svg(x: list, series: dict, titulo: str, eje_x: str, eje_y: str, ancho: int = 680, alto: int = 280,
               escalon: bool = False, desde_cero: bool = True) -> str:
    """Gráfico de líneas de 2 px con un solo eje; series: {nombre: valores} (hasta cuatro, colores en orden fijo)."""
    x, series = _reducir(list(x), {k: list(v) for k, v in series.items()})
    nombres = {k: k for k in series}; colores = {k: SERIES[i % len(SERIES)] for i, k in enumerate(series)}
    izq, der, abajo = 64, 20, 46
    ley, h_ley = _leyenda(list(series), nombres, colores, izq, 42, ancho) if len(series) > 1 else ([], 0)
    arriba = 42 + h_ley + 6
    p = _abrir(ancho, alto + h_ley, titulo) + ley; alto += h_ley
    vals = [float(v) for s in series.values() for v in s if v is not None]
    if not x or not vals:
        p.append(_t(ancho / 2, alto / 2, "Sin datos", 12, TINTA2, "middle") + "</svg>")
        return "".join(p)
    lo = min(0.0, min(vals)) if desde_cero else min(vals); hi = max(vals)
    if hi - lo < 1e-12:
        hi = lo + 1.0
    tk = _ticks(lo, hi, 4); lo, hi = min(lo, tk[0]), max(hi, tk[-1])
    x0, x1 = float(x[0]), float(x[-1]) if float(x[-1]) > float(x[0]) else float(x[0]) + 1
    X = lambda v: izq + (float(v) - x0) / (x1 - x0) * (ancho - izq - der)
    Y = lambda v: alto - abajo - (float(v) - lo) / (hi - lo) * (alto - arriba - abajo)
    d = _dec(tk[1] - tk[0]) if len(tk) > 1 else 1
    for t in tk:
        p.append(f'<path d="M{izq} {Y(t):.1f}H{ancho - der}" stroke="{GRILLA}"/>' + _t(izq - 6, Y(t) + 4, _cl(t, d), 10, TINTA2, "end"))
    tx = _ticks(x0, x1, 6); dx = _dec(tx[1] - tx[0]) if len(tx) > 1 else 0
    for t in tx:
        p.append(_t(X(t), alto - abajo + 14, _cl(t, dx), 10, TINTA2, "middle"))
    for k, v in series.items():
        pts = [(X(a), Y(b)) for a, b in zip(x, v) if b is not None]
        if not pts:
            continue
        if escalon:
            dd = f"M{pts[0][0]:.1f} {pts[0][1]:.1f}" + "".join(f"H{a:.1f}V{b:.1f}" for a, b in pts[1:])
        else:
            dd = "M" + "L".join(f"{a:.1f} {b:.1f}" for a, b in pts)
        p.append(f'<path d="{dd}" fill="none" stroke="{colores[k]}" stroke-width="2" stroke-linejoin="round"><title>{_h.escape(k)}</title></path>')
        if len(pts) <= 40:
            p += [f'<circle cx="{a:.1f}" cy="{b:.1f}" r="4" fill="{colores[k]}" stroke="#fff" stroke-width="2"><title>{_h.escape(f"{k}: {_cl(val, 2)}")}</title></circle>'
                  for (a, b), val in zip(pts, [vv for vv in v if vv is not None])]
    p += [f'<path d="M{izq} {arriba}V{alto - abajo}H{ancho - der}" fill="none" stroke="{EJE}"/>',
          _t((izq + ancho - der) / 2, alto - 12, eje_x, 11, TINTA2, "middle"), _t(12, arriba - 8 if h_ley else 34, eje_y, 10, TINTA2), "</svg>"]
    return "".join(p)


def barras_svg(etiquetas: list, valores: list, titulo: str, maximo: float = 1.0, ancho: int = 680, resaltar: str | None = None) -> str:
    """Barras horizontales de un valor en % (utilización por equipo); la barra resaltada es el equipo crítico."""
    izq, der, fila = 170, 60, 24
    arriba = 44; y1 = arriba + fila * len(etiquetas); alto = y1 + 40
    p = _abrir(ancho, alto, titulo)
    X = lambda f: izq + max(0.0, min(f, maximo)) / maximo * (ancho - izq - der)
    for t in (0, 0.25, 0.5, 0.75, 1.0):
        p.append(f'<path d="M{X(t * maximo):.1f} {arriba}V{y1}" stroke="{GRILLA}"/>' + _t(X(t * maximo), y1 + 14, f"{int(100 * t * maximo)} %", 10, TINTA2, "middle"))
    for i, (et, v) in enumerate(zip(etiquetas, valores)):
        y = arriba + i * fila; col = SERIES[1] if et == resaltar else SERIES[0]
        p.append(_t(izq - 8, y + fila / 2 + 4, et, 11, TINTA, "end")
                 + f'<rect x="{izq}" y="{y + 5}" width="{max(0.5, X(v) - izq):.2f}" height="{fila - 10}" rx="2" fill="{col}"><title>{_h.escape(f"{et}: {_cl(100 * v, 1)} %")}</title></rect>'
                 + _t(X(v) + 6, y + fila / 2 + 4, f"{_cl(100 * v, 1)} %", 10, TINTA))
    p.append(f'<path d="M{izq} {arriba}V{y1}" stroke="{EJE}"/>' + _t((izq + ancho - der) / 2, y1 + 32, "Tiempo operando / tiempo total", 11, TINTA2, "middle") + "</svg>")
    return "".join(p)


# ----------------------------------------------------------------------------------------------- widgets
def _w(i: str, **kw) -> dict:
    w = dict(id=i, grupo=GRUPO.get(i, ""), titulo=TITULO.get(i, i), svg=None, tabla=None, tarjetas=None, avisos=[], nota=None, datos={})
    w.update(kw)
    return w


def _etq(est: dict, k: str) -> str:
    t = f"{k} · {est['nombres'][k]}"
    return t if len(t) <= 26 else t[:25] + "…"


def _sin(i, ctx, fuente) -> dict | None:
    if fuente == "operacion":
        if ctx.get("estados") is None or not ctx["turnos"]:
            return _w(i, avisos=[ctx["avisos"].get("operacion") or "Todavía no hay turnos de Operación: ejecute turnos o simule los de demostración."])
    elif ctx.get(fuente) is None:
        return _w(i, avisos=[ctx["avisos"].get(fuente) or "Sin datos."])
    return None


def construir(i: str, ctx: dict) -> dict:
    """Arma el gráfico i del catálogo con el contexto: dict(id, grupo, titulo, svg, tabla, tarjetas, avisos, nota, datos)."""
    f = FUENTE.get(i)
    if f is None:
        raise KeyError(f"Gráfico desconocido: {i}")
    vacio = _sin(i, ctx, {"operacion": "operacion", "temporada": "programa", "dinamica": "dinamica", "linea": "linea"}[f])
    if vacio is not None:
        return vacio
    if f == "linea":
        return _construir_linea(i, ctx)
    est, T = ctx.get("estados"), ctx.get("turnos")
    if i == "estado_barras":
        filas = [(_etq(est, k), est["total"][k]) for k in est["equipos"]]
        datos = [dict(equipo=k, nombre=est["nombres"][k], **{NOMBRE_ESTADO[s]: est["total"][k][s] for s in ORDEN_ESTADO}) for k in est["equipos"]]
        return _w(i, svg=barras_apiladas_svg(filas, f"Tiempo en cada estado por equipo ({len(T)} turnos)"), datos={"Estados por equipo (h)": datos},
                  nota=f"Equipo crítico: {est['critico']}. Aguas arriba: {', '.join(est['aguas_arriba']) or 'ninguno'}.")
    if i == "estado_torta":
        svgs = [torta_svg(est["total"][k], _etq(est, k)) for k in est["equipos"][:8]]
        av = [] if len(est["equipos"]) <= 8 else ["Se muestran las tortas de los ocho primeros equipos elegidos."]
        return _w(i, svg=svgs, avisos=av, datos={"Estados por equipo (h)": [dict(equipo=k, **{NOMBRE_ESTADO[s]: est["total"][k][s] for s in ORDEN_ESTADO}) for k in est["equipos"]]})
    if i == "estado_gantt_turnos":
        H = OP.S["horas_turno"]; filas = []
        orden_tramo = ["mantenimiento", "falla", "operando", "bloqueado", "esperando", "detenido"]
        for k in est["equipos"]:
            tr = []
            for n, pt in enumerate(est["por_turno"]):
                t0 = n * H
                for s in orden_tramo:
                    hs = pt["estados"][k][s]
                    if hs > 1e-9:
                        tr.append((t0, t0 + hs, s)); t0 += hs
            filas.append((_etq(est, k), tr))
        return _w(i, svg=gantt_svg(filas, H * len(T), "Gantt de estados por equipo", escala=H, eje="Turno"),
                  nota="Operación no registra la hora de cada evento: dentro de cada turno el orden de los tramos es representativo.",
                  datos={"Estados por turno (h)": [dict(turno=pt["turno"], equipo=k, **{NOMBRE_ESTADO[s]: pt["estados"][k][s] for s in ORDEN_ESTADO})
                                                   for pt in est["por_turno"] for k in est["equipos"]]})
    if i == "estado_gantt_temporada":
        pr = ctx["programa"]; g = gantt_linea(pr); h = horas_linea(pr)
        svg = gantt_svg([("Línea", g)], pr["horas_totales"], "Estados de la línea en la temporada", ORDEN_LINEA, COLOR_LINEA, NOMBRE_LINEA)
        filas = [dict(estado=NOMBRE_LINEA[k], horas=h[k], fraccion=h[k] / pr["horas_totales"] if pr["horas_totales"] else 0.0) for k in ORDEN_LINEA if h[k] > 0]
        return _w(i, svg=[svg, torta_svg(h, "Estados de la línea", ORDEN_LINEA, COLOR_LINEA, NOMBRE_LINEA)],
                  tabla=(filas, [("estado", "Estado", "txt", 0), ("horas", "Horas", "num", 0), ("fraccion", "Fracción", "pct", 1)]),
                  datos={"Gantt de la línea": [dict(inicio_h=a, fin_h=b, estado=NOMBRE_LINEA[s]) for a, b, s in g]})
    if i == "prod_acum_turnos":
        x = [r["turno"] for r in T]; a = b = 0.0; pa, ca = [], []
        for r in T:
            a += r["producido"]; b += r["conforme"]; pa.append(a); ca.append(b)
        return _w(i, svg=lineas_svg(x, {"Producido (t)": pa, "Conforme (t)": ca}, "Producción acumulada en los turnos", "Turno", "t"),
                  datos={"Producción acumulada": [dict(turno=t, producido_acumulado_t=p, conforme_acumulado_t=c) for t, p, c in zip(x, pa, ca)]})
    if i == "prod_por_turno":
        x = [r["turno"] for r in T]
        s = {"Producido (t)": [r["producido"] for r in T], "Demanda (t)": [r["demanda"] for r in T], "Vendido (t)": [r["vendido"] for r in T]}
        return _w(i, svg=lineas_svg(x, s, "Producción, demanda y ventas por turno", "Turno", "t por turno"),
                  datos={"Producción por turno": [dict(turno=r["turno"], producido_t=r["producido"], conforme_t=r["conforme"], demanda_t=r["demanda"],
                                                       vendido_t=r["vendido"], faltante_t=r["faltante"]) for r in T]})
    if i == "prod_acum_temporada":
        d = produccion_temporada(ctx["programa"])
        return _w(i, svg=lineas_svg([x["dia"] for x in d], {"Producción acumulada (t)": [x["acumulada_t"] for x in d]},
                                    "Producción acumulada en la temporada", "Día de la temporada", "t"),
                  nota="Ritmo real de la línea (t/h) × horas de producción de cada día del programa.", datos={"Producción de la temporada": d})
    if i in ("cont_cola_hora", "cont_patio_temporada", "perm_histograma", "perm_tabla") and ctx.get("llegadas") is None:
        return _w(i, avisos=[ctx["avisos"].get("temporada") or "Sin llegadas de la temporada."])
    if i == "cont_cola_hora":
        ph = ctx["llegadas"]["por_hora"]
        return _w(i, svg=lineas_svg([h / 24 for h in range(len(ph))], {"Camiones en espera": ph}, "Camiones en espera hora a hora",
                                    "Día de la temporada", "camiones", escalon=True),
                  nota="Camiones que esperan en el patio, sin contar el que descarga. Con más de 1.500 horas se muestra el máximo de cada grupo de horas.",
                  datos={"Cola hora a hora": [dict(hora=h, camiones_en_espera=v) for h, v in enumerate(ph)]})
    if i == "cont_patio_temporada":
        D = ctx["llegadas"]["dias"]
        return _w(i, svg=lineas_svg([x["dia"] for x in D], {"En el patio al cierre del día (t)": [x["cola_t"] for x in D],
                                                            "Llegada del día (t)": [x["llegada_t"] for x in D]},
                                    "Materia prima en el patio por día", "Día de la temporada", "t"),
                  datos={"Patio por día": [dict(dia=x["dia"], llegada_t=x["llegada_t"], procesado_t=x["procesado_t"], en_patio_t=x["cola_t"]) for x in D]})
    if i == "cont_patio_turnos":
        x = [r["turno"] for r in T]
        return _w(i, svg=lineas_svg(x, {"Materia prima en el patio (t)": [r["stock"] for r in T], "Producto en bodega (t)": [r["terminado"] for r in T]},
                                    "Patio y bodega al cierre de cada turno", "Turno", "t"),
                  datos={"Patio y bodega": [dict(turno=r["turno"], patio_t=r["stock"], bodega_t=r["terminado"]) for r in T]})
    if i in ("perm_histograma", "perm_tabla"):
        v, w, aviso = esperas(ctx["llegadas"]); av = [aviso] if aviso else []
        if i == "perm_histograma":
            hs = histograma(v, w)
            filas = [dict(desde_h=a, hasta_h=b, camiones=c) for a, b, c in zip(hs["bordes"], hs["bordes"][1:], hs["conteos"])]
            return _w(i, svg=histograma_svg(hs, "Esperas de los camiones en el patio"), avisos=av,
                      nota="Clases de Sturges (1926): 1 + log2(n).", datos={"Histograma de esperas": filas})
        pm = permanencia(v, w); ll = ctx["llegadas"]
        filas = [dict(objeto="Camiones en el patio (espera)", n=pm["n"], media=pm["media"], minimo=pm["minimo"], maximo=pm["maximo"], desviacion=pm["desviacion"])]
        return _w(i, avisos=av, tabla=(filas, [("objeto", "Objeto", "txt", 0), ("n", "Camiones", "num", 0), ("media", "Media (h)", "num", 2),
                                               ("minimo", "Mínimo (h)", "num", 2), ("maximo", "Máximo (h)", "num", 2), ("desviacion", "Desviación estándar (h)", "num", 2)]),
                  nota=f"Espera media de la simulación {_cl(ll['espera_media_h'], 2)} h; máxima {_cl(ll['espera_max_h'], 2)} h.",
                  datos={"Permanencia": filas})
    if i == "ind_oee":
        o = ctx.get("oee"); pr = ctx.get("programa"); tj = []
        if o:
            tj += [dict(nombre="OEE de los turnos", valor=o["oee"], tipo="pct", nota="clase mundial 85 % (Nakajima, 1988)"),
                   dict(nombre="Disponibilidad", valor=o["disponibilidad"], tipo="pct", nota=f"{_cl(o['tiempo_operado_h'], 1)} h de {_cl(o['tiempo_planificado_h'], 1)} h"),
                   dict(nombre="Rendimiento", valor=o["rendimiento"], tipo="pct", nota="producción real / planificada"),
                   dict(nombre="Calidad", valor=o["calidad"], tipo="pct", nota=f"{_cl(o['conforme_t'], 1)} t conformes de {_cl(o['producido_t'], 1)} t")]
        if pr and pr.get("oee"):
            tj.append(dict(nombre="OEE del programa de la temporada", valor=pr["oee"]["oee"], tipo="pct", nota="disponibilidad del programa"))
        return _w(i, tarjetas=tj, nota=FUENTE_OEE + "; el tiempo planificado no incluye la detención por la meta de utilización.",
                  datos={"OEE": [dict(indicador=t["nombre"], valor=t["valor"]) for t in tj]})
    if i == "ind_utilizacion":
        eqs = est["equipos"]
        return _w(i, svg=barras_svg([_etq(est, k) for k in eqs], [est["utilizacion"][k] for k in eqs], "Utilización por equipo",
                                    resaltar=_etq(est, est["critico"]) if est["critico"] in eqs else None),
                  nota="La barra naranja es el equipo crítico.",
                  datos={"Utilización": [dict(equipo=k, utilizacion=est["utilizacion"][k], ritmo_en_produccion=est["ritmos"][k]) for k in eqs]})
    if i in ("din_temperatura", "din_calor"):
        a = ctx["dinamica"]; S = a["series"]
        if i == "din_temperatura":
            return _w(i, svg=lineas_svg(S["t_min"], {"Temperatura (°C)": S["T"]}, f"Temperatura de salida de {a['equipo']}", "Tiempo (min)", "°C",
                                        desde_cero=False),
                      nota=f"Parada a los {_cl(a['t_parada_min'], 1)} min; constante de tiempo {_cl(a['tau_min'], 1)} min.",
                      datos={"Arranque y parada": [dict(t_min=t, T=v) for t, v in zip(S["t_min"][::10], S["T"][::10])]})
        s = {"Calor entregado (kW)": S["Q"], "Calor recuperable disponible (kW)": S["Q_rec_disp"], "Calor externo (kW)": S["Q_ext"]}
        return _w(i, svg=lineas_svg(S["t_min"], s, "Calor entregado y calor recuperable", "Tiempo (min)", "kW"),
                  datos={"Calor en el arranque": [dict(t_min=S["t_min"][j], Q_kW=S["Q"][j], Q_rec_disp_kW=S["Q_rec_disp"][j], Q_ext_kW=S["Q_ext"][j])
                                                  for j in range(0, len(S["t_min"]), 10)]})
    if i == "din_secado":
        s = ctx.get("secado")
        if s is None:
            return _w(i, avisos=[ctx["avisos"].get("secado") or "El secado por cargas solo existe en los rubros de biomasa."])
        S = s["series"]
        return _w(i, svg=lineas_svg([60 * t for t in S["t_h"]], {"Humedad (base húmeda, %)": [100 * v for v in S["M_bh"]]},
                                    "Humedad de la carga en el secado por cargas", "Tiempo (min)", "%", desde_cero=False),
                  nota=f"Tiempo de secado {_cl(s['t_euler_h'], 2)} h (exacto {_cl(s['t_exacto_h'], 2)} h).",
                  datos={"Secado por cargas": [dict(t_min=60 * S["t_h"][j], humedad_bh=S["M_bh"][j]) for j in range(0, len(S["t_h"]), 10)]})
    raise KeyError(i)


def _construir_linea(i: str, ctx: dict) -> dict:
    """Gráficos del grupo «Línea (estados reales)» con el resultado de simular_linea."""
    res = ctx["linea"]; est = estados_linea(res, ctx.get("linea_equipos")); H = est["horas"] or 1.0
    eqs = est["equipos"]; th = list(res.get("tiempo_h") or [])
    etq = {k: _etq(est, k) for k in eqs}
    if i == "linea_barras":
        filas = [(etq[k], est["total"][k]) for k in eqs]
        datos = [dict(equipo=k, nombre=est["nombres"][k], **{NOMBRE_ESTADO[s]: est["total"][k][s] for s in ORDEN_ESTADO}) for k in eqs]
        return _w(i, svg=barras_apiladas_svg(filas, f"Tiempo en cada estado por equipo (línea simulada, {_cl(H, 0)} h)"),
                  nota=NOTA_LINEA, datos={"Estados de la línea simulada (h)": datos})
    if i == "linea_gantt":
        escala, eje = (1.0, "Hora de la simulación") if H <= 96 else (24.0, "Día de la simulación")
        svg = gantt_svg([(etq[k], est["tramos"][k]) for k in eqs], H, "Gantt de estados por equipo (horas reales)", escala=escala, eje=eje)
        return _w(i, svg=svg, nota=NOTA_LINEA,
                  datos={"Tramos de estado de la línea": [dict(equipo=k, estado=NOMBRE_ESTADO[s], inicio_h=a, fin_h=b, duracion_h=b - a)
                                                          for k in eqs for a, b, s in est["tramos"][k]]})
    if i == "linea_niveles":
        tks = [t for t in res.get("tanques") or [] if not t.get("anulado") and t["id"] in (res.get("niveles") or {})]
        if not tks:
            return _w(i, avisos=["La línea simulada no tiene tanques pulmón (todos anulados o un solo equipo)."])
        svgs = [lineas_svg(th, {"Nivel (t)": res["niveles"][t["id"]], "Capacidad (t)": [float(t["capacidad_t"])] * len(th)},
                           f"Tanque {t['id']}", "Hora de la simulación", "t", ancho=520, alto=240) for t in tks]
        filas = [dict(hora_h=h, **{t["id"]: res["niveles"][t["id"]][j] for t in tks}) for j, h in enumerate(th)]
        an = [t["id"] for t in res.get("tanques") or [] if t.get("anulado")]
        return _w(i, svg=svgs, avisos=[f"Tanques anulados (conexión directa): {', '.join(an)}."] if an else [],
                  nota="Nivel de cada tanque pulmón (t) en cada muestra, como el indicador de nivel de la *Fluid Library* de FlexSim; "
                       "la segunda línea es su capacidad.", datos={"Niveles de los tanques (t)": filas})
    if i == "linea_tasas":
        cap = {e["id"]: e.get("capacidad_t_h") for e in res["equipos"]}; svgs = []
        for k in eqs:
            ser = {"Tasa (t/h)": res["tasas"][k]}
            if cap.get(k):
                ser["Tasa máxima (t/h)"] = [float(cap[k])] * len(th)
            svgs.append(lineas_svg(th, ser, etq[k], "Hora de la simulación", "t/h", ancho=520, alto=240))
        filas = [dict(hora_h=h, **{k: res["tasas"][k][j] for k in eqs}) for j, h in enumerate(th)]
        return _w(i, svg=svgs, nota="Tasa media de proceso de cada equipo en cada intervalo de muestra (t/h de su carga) y su tasa máxima "
                                    "(capacidad efectiva).", datos={"Tasa por equipo (t/h)": filas})
    if i == "linea_permanencia":
        filas = permanencia_linea(res, ctx.get("linea_equipos"))
        cols = [("equipo", "Equipo", "txt", 0), ("estado", "Estado", "txt", 0), ("tramos", "Tramos", "num", 0), ("horas", "Horas", "num", 1),
                ("media", "Media (h)", "num", 2), ("minimo", "Mínimo (h)", "num", 2), ("maximo", "Máximo (h)", "num", 2),
                ("desviacion", "Desviación estándar (h)", "num", 2)]
        return _w(i, tabla=(filas, cols), datos={"Permanencia en cada estado": filas},
                  nota="Duración de cada tramo continuo en un estado, como la *Staytime Table* de FlexSim. El primer y el último tramo de "
                       "cada equipo quedan cortados por el inicio y el fin del horizonte. " + NOTA_LINEA)
    if i == "linea_oee":
        tj = tarjetas_oee_linea(res)
        return _w(i, tarjetas=tj, nota=FUENTE_OEE + ". La tasa ideal es la producción planificada de la planta, la misma de Temporada "
                                     "y de la tarjeta de OEE de los turnos, para que sean comparables; el OEE respecto del recurso crítico "
                                     "es un dato adicional.", datos={"OEE de la línea": [dict(indicador=t["nombre"], valor=t["valor"]) for t in tj]})
    raise KeyError(i)


def construir_todos(ids: list, ctx: dict) -> list:
    return [construir(i, ctx) for i in ids if i in TITULO]


# ----------------------------------------------------------------------------------------------- exportar
def _fmt_tabla(v, tipo, d) -> str:
    if v is None:
        return "—"
    if tipo == "pct":
        return _cl(100 * float(v), d) + " %"
    if tipo in ("num", "cen"):
        return _cl(float(v), d) if tipo == "num" else str(v)
    if tipo == "clp":
        return "$" + _cl(float(v), d)
    return str(v)


def tabla_html(filas: list, cols: list) -> str:
    """Tabla con el estilo del informe: texto a la izquierda, números al centro y plata a la derecha."""
    al = {"txt": "left", "cen": "center", "num": "center", "pct": "center", "clp": "right", "mm": "right"}
    h = ["<table><thead><tr>"] + [f'<th style="text-align:{al[t]}">{_h.escape(n)}</th>' for _k, n, t, _d in cols] + ["</tr></thead><tbody>"]
    for f in filas:
        h.append("<tr>" + "".join(f'<td style="text-align:{al[t]}">{_h.escape(_fmt_tabla(f.get(k), t, d))}</td>' for k, _n, t, d in cols) + "</tr>")
    return "".join(h) + "</tbody></table>"


def exportar_html(widgets: list, titulo: str = "Tableros de la planta", columnas: int = 2) -> str:
    """Un HTML con todos los gráficos, tarjetas y tablas de los tableros (como «Export All Dashboards to HTML» de FlexSim).
    widgets: lista de dict de construir, o dict {nombre del tablero: lista de widgets}."""
    tableros = widgets if isinstance(widgets, dict) else {titulo: widgets}
    css = ("""
:root{--fondo:#f4f5f3;--tarjeta:#ffffff;--tinta:#1f1f1e;--tinta2:#5f5e5a;--borde:#dcdedb;--acento:#1b7a5a}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){--fondo:#1a1a19;--tarjeta:#262624;--tinta:#f0efec;--tinta2:#c3c2b7;--borde:#3a3a37;--acento:#4fbf94}}
:root[data-theme="dark"]{--fondo:#1a1a19;--tarjeta:#262624;--tinta:#f0efec;--tinta2:#c3c2b7;--borde:#3a3a37;--acento:#4fbf94}
*{box-sizing:border-box}body{margin:0;background:var(--fondo);color:var(--tinta);font-family:system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1280px;margin:0 auto;padding:20px 16px 48px}h1{font-size:1.4rem;margin:0 0 4px}h2{font-size:1.15rem;margin:28px 0 10px;color:var(--acento)}
h3{font-size:0.98rem;margin:0 0 8px}.grilla{display:grid;grid-template-columns:repeat(COLS,minmax(0,1fr));gap:14px;align-items:start}
.multi{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
.w{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:12px;min-width:0}
.w svg{display:block;max-width:100%;height:auto;border-radius:6px;margin:4px 0}.grupo{color:var(--tinta2);font-size:0.78rem;margin-bottom:2px}
.aviso{background:#fff4dc;color:#5b4300;border-radius:6px;padding:6px 8px;font-size:0.85rem}.nota{color:var(--tinta2);font-size:0.8rem}
.tj{display:flex;flex-wrap:wrap;gap:10px}.tj div{flex:1 1 140px;border:1px solid var(--borde);border-radius:8px;padding:8px 10px}
.tj b{display:block;font-size:1.5rem;font-variant-numeric:tabular-nums}.tj span{color:var(--tinta2);font-size:0.8rem}
table{border-collapse:collapse;width:100%;font-size:0.85rem;margin:6px 0}th{border-bottom:2px solid var(--acento);padding:4px 6px}
td{border-bottom:1px solid var(--borde);padding:3px 6px;font-variant-numeric:tabular-nums}.desliz{overflow-x:auto}
@media (max-width:760px){.grilla{grid-template-columns:1fr}}
""").replace("COLS", str(max(1, min(2, int(columnas)))))
    p = ['<!doctype html><html lang="es-CL"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
         f"<title>{_h.escape(titulo)}</title><style>{css}</style></head><body><main>", f"<h1>{_h.escape(titulo)}</h1>",
         '<p class="nota">Exportado desde la pestaña Tableros de la aplicación pat_sim (PAT 134). Pase el cursor sobre las barras y los tramos para ver sus horas.</p>']
    for nombre, ws in tableros.items():
        if len(tableros) > 1 or nombre != titulo:
            p.append(f"<h2>{_h.escape(nombre)}</h2>")
        p.append('<div class="grilla">')
        for w in ws:
            ancho = ' style="grid-column:1/-1"' if w.get("ancho") == "completo" else ""      # PAT 134: ancho completo en la grilla
            p.append(f'<section class="w"{ancho}><div class="grupo">{_h.escape(w.get("grupo", ""))}</div><h3>{_h.escape(w["titulo"])}</h3>')
            p += [f'<p class="aviso">{_h.escape(a)}</p>' for a in w.get("avisos") or []]
            if w.get("tarjetas"):
                p.append('<div class="tj">' + "".join(
                    f'<div><span>{_h.escape(t["nombre"])}</span><b>{_h.escape(_fmt_tabla(t["valor"], t.get("tipo", "num"), 1))}</b>'
                    f'<span>{_h.escape(t.get("nota") or "")}</span></div>' for t in w["tarjetas"]) + "</div>")
            svgs = w.get("svg"); svgs = [svgs] if isinstance(svgs, str) else (svgs or [])
            if w["id"] in MULTIPLES and len(svgs) > 1:
                p.append('<div class="multi">' + "".join(svgs) + "</div>")
            else:
                p += svgs
            if w.get("tabla"):
                p.append('<div class="desliz">' + tabla_html(*w["tabla"]) + "</div>")
            if w.get("nota"):      # PAT 134: las palabras en inglés en *cursiva* de markdown pasan a <i>
                p.append('<p class="nota">' + re.sub(r"\*([^*]+)\*", r"<i>\1</i>", _h.escape(w["nota"])) + "</p>")
            p.append("</section>")
        p.append("</div>")
    p.append('<h2>Reglas de los estados</h2><div class="w desliz">'
             + tabla_html([dict(n=s.nombre, j=s.justificacion) for s in REGLAS.values()], [("n", "Regla", "txt", 0), ("j", "Justificación", "txt", 0)])
             + "</div></main></body></html>")
    return "".join(p)


def _csv_celda(v) -> str:
    if v is None:
        return ""
    if isinstance(v, bool):
        return "sí" if v else "no"
    if isinstance(v, (int, float)) or type(v).__name__.startswith(("float", "int")):
        x = float(v)
        s = (str(int(x)) if x.is_integer() and abs(x) < 1e15 else repr(round(x, 6))).replace(".", ",")
        return s
    s = str(v)
    return '"' + s.replace('"', '""') + '"' if any(c in s for c in ';"\n') else s


def exportar_csv(datos) -> str:
    """Datos de los tableros en CSV para Excel en Chile (separador punto y coma, coma decimal). datos: {tabla: [filas]} o una
    lista de widgets (se juntan sus datos). Cada tabla va precedida de su nombre y separada por una línea en blanco."""
    if isinstance(datos, list):
        junto = {}
        for w in datos:
            for k, v in (w.get("datos") or {}).items():
                nombre = f"{w['titulo']}: {k}" if k in junto else k
                junto[nombre] = v
        datos = junto
    out = []
    for nombre, filas in datos.items():
        out.append(_csv_celda(nombre))
        if not filas:
            out.append(""); continue
        cols = list(dict.fromkeys(c for f in filas for c in f))
        out.append(";".join(_csv_celda(c) for c in cols))
        out += [";".join(_csv_celda(f.get(c)) for c in cols) for f in filas]
        out.append("")
    return "\n".join(out)


def svg_como_img(svg: str, alt: str = "Gráfico del tablero") -> str:
    """Etiqueta img con el SVG en base64 (st.html no dibuja un SVG suelto)."""
    import base64
    return (f'<img alt="{_h.escape(alt)}" style="width:100%;height:auto" src="data:image/svg+xml;base64,'
            + base64.b64encode(svg.encode("utf-8")).decode("ascii") + '">')


# ----------------------------------------------------------------------------------------------- biblioteca visual (PAT 134, 04-11-2026)
# Pedido de Jaime (04-11-2026): armar los tableros como la biblioteca de FlexSim, con una miniatura de cada gráfico agrupada por
# categoría, plantillas de tablero y gráficos que se suben, bajan, ensanchan y quitan. Aquí queda la parte sin Streamlit: fichas de
# la biblioteca, miniaturas SVG propias (dibujos esquemáticos con los colores de estado, sin datos), plantillas y el modelo de cada
# tablero, dict(graficos=[dict(id, ancho)], columnas), con la migración del formato anterior (nombre -> lista de gráficos).
ETIQUETA_GRUPO = {g: ("Línea" if g == GRUPO_LINEA else g) for g in GRUPOS}
NOMBRE_FUENTE = {"operacion": "Operación", "temporada": "Temporada", "dinamica": "Dinámica", "linea": "Línea"}
NOMBRE_FORMA = {"barras_apiladas": "barras apiladas", "torta": "torta", "gantt": "Gantt", "gantt_linea": "Gantt y torta",
                "acumulada": "línea acumulada", "lineas": "líneas", "escalon": "escalones", "histograma": "histograma",
                "tabla": "tabla", "tarjetas": "tarjetas", "barras": "barras", "curva": "curva", "calor": "líneas",
                "decaimiento": "curva", "nivel": "nivel", "multiples": "gráficos pequeños"}
# id: (forma de la miniatura, para qué sirve en una línea, qué muestra y cómo leerlo para el «?»)
FICHA = {
    "estado_barras": ("barras_apiladas", "Qué parte del tiempo pasó cada equipo en cada estado.",
                      "Una barra por equipo, de 0 a 100 % del tiempo de los turnos, partida en los seis estados con su color. "
                      "Busque el equipo con más verde (operando): suele ser el crítico; mucho naranjo (bloqueado) antes de él y mucho azul "
                      "(esperando) después indican un cuello de botella. Pase el cursor sobre un tramo para ver sus horas."),
    "estado_torta": ("torta", "Reparto de los estados de cada equipo, una torta por equipo.",
                     "Una torta por equipo con el porcentaje del tiempo en cada estado (en FlexSim las tortas solo existen para datos de "
                     "estado). Sirve para comparar equipos de un vistazo; para leer horas exactas use las barras o la tabla del CSV."),
    "estado_gantt_turnos": ("gantt", "Secuencia de estados de cada equipo turno a turno.",
                            "Una fila por equipo y el tiempo hacia la derecha, en turnos. Cada tramo de color es un estado. Muestra en qué "
                            "turno hubo fallas o mantenimiento; dentro de un turno el orden de los tramos es representativo, porque "
                            "Operación no registra la hora de cada evento."),
    "estado_gantt_temporada": ("gantt_linea", "Producción, arranques, limpiezas y paradas de la línea en la temporada.",
                               "Barra de tiempo de toda la temporada con los estados del programa de la pestaña Temporada, una torta con "
                               "su reparto y una tabla con las horas. Mientras más verde, más horas de producción."),
    "prod_acum_turnos": ("acumulada", "Toneladas producidas y conformes acumuladas turno a turno.",
                         "Dos líneas que suben turno a turno: lo producido y lo conforme. Una pendiente más baja indica un turno con "
                         "menos producción (falla, mantenimiento o falta de materia prima); la distancia entre las líneas es el producto "
                         "no conforme."),
    "prod_por_turno": ("lineas", "Producción, demanda y ventas de cada turno.",
                       "Tres líneas en t por turno. Si la demanda queda sobre lo vendido hay venta perdida; si lo producido queda sobre "
                       "lo vendido, el producto se acumula en bodega."),
    "prod_acum_temporada": ("acumulada", "Toneladas acumuladas día a día en la temporada.",
                            "Ritmo real de la línea por las horas de producción de cada día del programa. Los tramos planos son días sin "
                            "producción (limpiezas o paradas); la altura final es la producción de la temporada."),
    "cont_cola_hora": ("escalon", "Camiones esperando para descargar, hora a hora.",
                       "Escalones con el número de camiones en el patio sin contar el que descarga, como el gráfico de contenido "
                       "(*Content*) de FlexSim. Picos altos y largos indican que la recepción no da abasto en esas horas."),
    "cont_patio_temporada": ("lineas", "Materia prima que llega y queda en el patio cada día.",
                             "Dos líneas por día: lo que llegó y lo que quedó en el patio al cierre. Si lo que queda crece varios días "
                             "seguidos, la línea procesa menos de lo que llega."),
    "cont_patio_turnos": ("lineas", "Materia prima en el patio y producto en bodega al cierre de cada turno.",
                          "Contenido al cierre de cada turno: el patio baja cuando la línea procesa y la bodega sube con lo producido "
                          "no vendido."),
    "perm_histograma": ("histograma", "Distribución de las esperas de los camiones.",
                        "Cuántos camiones esperaron cada rango de horas (clases de Sturges). Una cola larga a la derecha indica pocos "
                        "camiones con esperas muy largas, que son los que deterioran la materia prima."),
    "perm_tabla": ("tabla", "Espera media, mínima y máxima de los camiones.",
                   "Tabla de permanencia como la *Staytime Table* de FlexSim: número de camiones, media, mínimo, máximo y desviación "
                   "estándar de la espera en el patio."),
    "ind_oee": ("tarjetas", "OEE y sus tres factores en tarjetas.",
                "Tarjetas con el OEE de los turnos (disponibilidad × rendimiento × calidad) y el OEE del programa de la temporada. "
                "Compare cada factor: el más bajo es la pérdida que conviene atacar primero."),
    "ind_utilizacion": ("barras", "Fracción del tiempo que opera cada equipo.",
                        "Una barra por equipo con su utilización (tiempo operando sobre tiempo total). La barra naranja es el equipo "
                        "crítico, que limita a la línea."),
    "din_temperatura": ("curva", "Temperatura del equipo en el arranque y la parada.",
                        "Curva de la temperatura de salida en el tiempo de la pestaña Dinámica: sube en el arranque hasta la operación "
                        "y baja después de la parada. Mientras más lenta la subida, más energía se pierde en el arranque."),
    "din_calor": ("calor", "Calor entregado, recuperable y externo en el arranque.",
                  "Tres líneas en kW: el calor que pide el equipo, el recuperable disponible y el que falta y se compra afuera. El área "
                  "entre las dos primeras es el calor que no se puede recuperar mientras la planta arranca."),
    "din_secado": ("decaimiento", "Humedad de la carga durante el secado por cargas.",
                   "La humedad en base húmeda baja con el tiempo hasta la meta; el tiempo en que la cruza es el tiempo de secado. "
                   "Solo existe en los rubros de biomasa."),
    "linea_barras": ("barras_apiladas", "Qué parte del tiempo pasó cada equipo en cada estado, con horas reales.",
                     "Como el gráfico de estados por equipo, pero con la línea simulada por *ticks* en la pestaña Línea: las horas "
                     "son reales, con bloqueo y hambre que dependen de los tanques pulmón y de las fallas."),
    "linea_gantt": ("gantt", "Secuencia real de estados de cada equipo en la línea simulada.",
                    "Una fila por equipo y el tiempo hacia la derecha. Cada tramo es un estado con su hora real de inicio y fin; las "
                    "fallas (rojo) de un equipo se ven propagarse como bloqueo aguas arriba y como espera aguas abajo."),
    "linea_niveles": ("nivel", "Nivel de cada tanque pulmón en el tiempo.",
                      "Un gráfico por tanque con su nivel y su capacidad. Un tanque lleno bloquea al equipo anterior y uno vacío deja "
                      "sin material al siguiente; un nivel que oscila en el medio está amortiguando las fallas."),
    "linea_tasas": ("multiples", "Tasa de proceso de cada equipo frente a su máximo.",
                    "Un gráfico por equipo con su tasa (t/h) y su tasa máxima. El equipo que pasa más tiempo pegado a su máximo es "
                    "la restricción; las caídas a cero son fallas, bloqueo o espera."),
    "linea_permanencia": ("tabla", "Cuánto dura cada tramo en cada estado, por equipo.",
                          "Tabla de permanencia como la *Staytime Table* de FlexSim: por equipo y estado, el número de tramos, las "
                          "horas y la duración media, mínima y máxima de cada tramo."),
    "linea_oee": ("tarjetas", "OEE de la línea simulada y sus factores.",
                  "Tarjetas con el OEE de la línea simulada, comparable con el de los turnos y la temporada porque usa la misma "
                  "producción planificada."),
}
ANCHO_COMPLETO = {"estado_torta", "estado_gantt_turnos", "estado_gantt_temporada", "cont_cola_hora", "perm_tabla",
                  "linea_gantt", "linea_niveles", "linea_tasas", "linea_permanencia"}
ANCHOS = ("medio", "completo")
PLANTILLAS = {
    "Vacío": ("Un tablero sin gráficos, para armarlo desde la biblioteca.", []),
    "Resumen de planta": ("OEE, estados por equipo y producción de los turnos.",
                          ["ind_oee", "ind_utilizacion", "estado_barras", "prod_acum_turnos", "estado_torta"]),
    "Cuellos de botella": ("Estados por equipo, utilización, Gantt y permanencia en cada estado.",
                           ["estado_barras", "ind_utilizacion", "estado_gantt_turnos", "linea_gantt", "linea_permanencia"]),
    "Temporada": ("Cola de camiones, esperas y producción acumulada de la temporada.",
                  ["cont_cola_hora", "perm_histograma", "perm_tabla", "prod_acum_temporada", "estado_gantt_temporada"]),
    "Línea": ("Estados reales, niveles de los tanques y OEE de la línea simulada.",
              ["linea_oee", "linea_barras", "linea_gantt", "linea_niveles", "linea_tasas"]),
}
TABLERO_INICIAL = "Tablero principal"


def descripcion(i: str) -> str:
    return FICHA.get(i, ("", "", ""))[1]


def ayuda_grafico(i: str) -> str:
    """Texto del «?» de un gráfico: qué muestra, cómo leerlo y de dónde salen sus datos."""
    f = FICHA.get(i)
    if f is None:
        return ""
    return f"{f[2]}\n\nGrupo {ETIQUETA_GRUPO.get(GRUPO.get(i), '')}; datos de la pestaña {NOMBRE_FUENTE.get(FUENTE.get(i), '')}."


def biblioteca_por_categoria() -> dict:
    """Pestañas de la biblioteca: {etiqueta de la categoría: [ids]} en el orden del catálogo."""
    return {ETIQUETA_GRUPO[g]: ids for g, ids in catalogo_por_grupo().items()}


def _sin_tildes(t: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFD", str(t).lower()) if unicodedata.category(c) != "Mn")


def buscar_graficos(texto: str) -> list:
    """Ids del catálogo cuyo nombre, descripción, categoría, forma o fuente contienen todas las palabras (sin tildes ni mayúsculas)."""
    palabras = _sin_tildes(texto).split()
    if not palabras:
        return [i for i, *_x in CATALOGO]
    out = []
    for i, g, t, f in CATALOGO:
        forma, desc, _a = FICHA[i]
        pajar = _sin_tildes(" ".join([t, desc, g, ETIQUETA_GRUPO[g], NOMBRE_FORMA.get(forma, ""), NOMBRE_FUENTE.get(f, ""), i.replace("_", " ")]))
        if all(p in pajar for p in palabras):
            out.append(i)
    return out


# miniaturas: 160 × 100, sin texto ni cifras (son dibujos de la forma del gráfico, no datos)
_MW, _MH, _MX0, _MX1, _MY0, _MY1 = 160, 100, 16, 150, 12, 86
_FONDO_MINI = "#f6f7f5"


def _poli(puntos, color, ancho=2.0, extra="") -> str:
    d = " ".join(f"{x:.1f},{y:.1f}" for x, y in puntos)
    return f'<polyline points="{d}" fill="none" stroke="{color}" stroke-width="{ancho}" stroke-linejoin="round" stroke-linecap="round"{extra}/>'


def _ejes() -> str:
    return f'<path d="M{_MX0} {_MY0}V{_MY1}H{_MX1}" fill="none" stroke="{EJE}" stroke-width="1.2"/>'


def _curva(fn, n=40) -> list:
    """Puntos de fn(u) con u de 0 a 1 (0 abajo, 1 arriba) dentro de los ejes."""
    return [(_MX0 + 4 + (_MX1 - _MX0 - 6) * k / n, _MY1 - 4 - (_MY1 - _MY0 - 8) * max(0.0, min(1.0, fn(k / n)))) for k in range(n + 1)]


def _mini_barras_apiladas() -> list:
    filas = [[0.62, 0.18, 0.08, 0.0, 0.07, 0.05], [0.80, 0.0, 0.05, 0.08, 0.07, 0.0], [0.55, 0.0, 0.30, 0.0, 0.0, 0.15],
             [0.48, 0.0, 0.37, 0.05, 0.0, 0.10]]
    p = []
    for n, fr in enumerate(filas):
        y = 14 + n * 19
        p.append(f'<rect x="12" y="{y + 3}" width="20" height="6" rx="2" fill="{GRILLA}"/>')
        x = 38.0
        for k, f in zip(ORDEN_ESTADO, fr):
            if f > 0:
                w = 112 * f
                p.append(f'<rect x="{x:.1f}" y="{y}" width="{max(0.5, w - 1.2):.1f}" height="12" rx="2" fill="{COLOR_ESTADO[k]}"/>')
                x += w
    p.append(f'<path d="M38 10V90" stroke="{EJE}" stroke-width="1"/>')
    return p


def _mini_torta(cx=80.0, cy=50.0, r=36.0, partes=None) -> list:
    partes = partes or [("operando", 0.56), ("bloqueado", 0.14), ("esperando", 0.13), ("falla", 0.07), ("mantenimiento", 0.06), ("detenido", 0.04)]
    colores = dict(COLOR_ESTADO, **COLOR_LINEA)
    p, a = [], -math.pi / 2
    for k, f in partes:
        b = a + 2 * math.pi * f
        x1, y1, x2, y2 = cx + r * math.cos(a), cy + r * math.sin(a), cx + r * math.cos(b), cy + r * math.sin(b)
        p.append(f'<path d="M{cx:.1f} {cy:.1f}L{x1:.1f} {y1:.1f}A{r} {r} 0 {1 if f > 0.5 else 0} 1 {x2:.1f} {y2:.1f}Z" '
                 f'fill="{colores[k]}" stroke="{_FONDO_MINI}" stroke-width="1.5"/>')
        a = b
    return p


def _mini_gantt() -> list:
    filas = [[(0.30, "operando"), (0.08, "falla"), (0.32, "operando"), (0.10, "mantenimiento"), (0.20, "operando")],
             [(0.25, "operando"), (0.13, "bloqueado"), (0.30, "operando"), (0.12, "bloqueado"), (0.20, "operando")],
             [(0.22, "operando"), (0.16, "esperando"), (0.34, "operando"), (0.14, "esperando"), (0.14, "detenido")],
             [(0.20, "operando"), (0.18, "esperando"), (0.36, "operando"), (0.12, "esperando"), (0.14, "operando")]]
    p = []
    for n, fila in enumerate(filas):
        y = 13 + n * 17; x = 38.0
        p.append(f'<rect x="12" y="{y + 3}" width="20" height="6" rx="2" fill="{GRILLA}"/>')
        for f, k in fila:
            p.append(f'<rect x="{x:.1f}" y="{y}" width="{112 * f - 0.8:.1f}" height="12" fill="{COLOR_ESTADO[k]}"/>')
            x += 112 * f
    p.append(f'<path d="M38 84H150" stroke="{EJE}" stroke-width="1"/>' + "".join(
        f'<path d="M{38 + 112 * t / 4:.1f} 84v4" stroke="{EJE}" stroke-width="1"/>' for t in range(5)))
    return p


def _mini_gantt_linea() -> list:
    tramos = [(0.04, "arranque"), (0.20, "produccion"), (0.03, "limpieza"), (0.22, "produccion"), (0.05, "parada"), (0.18, "produccion"),
              (0.03, "limpieza"), (0.21, "produccion"), (0.04, "parada")]
    p, x = [], 12.0
    for f, k in tramos:
        p.append(f'<rect x="{x:.1f}" y="16" width="{136 * f - 0.6:.1f}" height="20" fill="{COLOR_LINEA[k]}"/>')
        x += 136 * f
    p.append(f'<path d="M12 40H148" stroke="{EJE}" stroke-width="1"/>')
    p += _mini_torta(48, 70, 22, [("produccion", 0.81), ("arranque", 0.04), ("limpieza", 0.06), ("parada", 0.09)])
    p += [f'<rect x="84" y="{56 + 9 * n}" width="{w}" height="5" rx="2" fill="{GRILLA}"/>' for n, w in enumerate((56, 40, 48, 30))]
    return p


def _mini_tabla() -> list:
    p = [f'<rect x="12" y="12" width="136" height="12" rx="2" fill="#e3eee9"/>',
         f'<path d="M12 24H148" stroke="#1b7a5a" stroke-width="1.6"/>']
    for n in range(5):
        y = 30 + n * 11.5
        p.append(f'<rect x="16" y="{y}" width="{38 - 6 * (n % 3)}" height="5" rx="2" fill="#c9cfd2"/>')
        for c, x in enumerate((70, 98, 124)):
            p.append(f'<rect x="{x}" y="{y}" width="{16 + 4 * ((n + c) % 2)}" height="5" rx="2" fill="#dde2e4"/>')
        p.append(f'<path d="M12 {y + 8.5:.1f}H148" stroke="{GRILLA}" stroke-width="1"/>')
    return p


def _mini_tarjetas() -> list:
    p = []
    for n, (f, col) in enumerate(((0.74, "#1b7a5a"), (0.88, SERIES[0]), (0.83, SERIES[0]), (0.97, SERIES[0]))):
        x, y = 10 + (n % 2) * 72, 8 + (n // 2) * 44
        p.append(f'<rect x="{x}" y="{y}" width="68" height="40" rx="6" fill="#fff" stroke="#dcdedb"/>')
        p.append(f'<rect x="{x + 6}" y="{y + 6}" width="{26 if n else 34}" height="4" rx="2" fill="#c9cfd2"/>')
        cx, cy, r = x + 34, y + 34, 15
        a = math.pi * (1 - f)
        p.append(f'<path d="M{cx - r} {cy}A{r} {r} 0 0 1 {cx + r} {cy}" fill="none" stroke="{GRILLA}" stroke-width="5"/>')
        p.append(f'<path d="M{cx - r} {cy}A{r} {r} 0 0 1 {cx + r * math.cos(a):.1f} {cy - r * math.sin(a):.1f}" fill="none" '
                 f'stroke="{col}" stroke-width="5" stroke-linecap="round"/>')
    return p


def _mini_barras() -> list:
    p = []
    for n, f in enumerate((0.62, 0.71, 0.95, 0.55, 0.48)):
        y = 12 + n * 15
        p.append(f'<rect x="12" y="{y + 3}" width="20" height="6" rx="2" fill="{GRILLA}"/>')
        p.append(f'<rect x="38" y="{y}" width="{108 * f:.1f}" height="11" rx="2" fill="{SERIES[1] if n == 2 else SERIES[0]}"/>')
    p.append(f'<path d="M38 8V88" stroke="{EJE}" stroke-width="1"/>')
    return p


def _mini_histograma() -> list:
    p = [_ejes()]
    for n, f in enumerate((0.95, 0.78, 0.52, 0.33, 0.2, 0.11, 0.06, 0.03)):
        h = (_MY1 - _MY0 - 6) * f; x = _MX0 + 3 + n * 16.5
        p.append(f'<rect x="{x:.1f}" y="{_MY1 - h:.1f}" width="15.5" height="{h:.1f}" fill="{SERIES[0]}"/>')
    return p


def _mini_multiples() -> list:
    p = []
    for n in range(4):
        x0, y0 = 10 + (n % 2) * 72, 8 + (n // 2) * 44
        p.append(f'<rect x="{x0}" y="{y0}" width="68" height="40" rx="4" fill="#fff" stroke="#dcdedb"/>')
        p.append(f'<path d="M{x0 + 5} {y0 + 9}H{x0 + 63}" stroke="{SERIES[1]}" stroke-width="1.2" stroke-dasharray="3 2"/>')
        pts = [(x0 + 5 + 58 * k / 20, y0 + 34 - 22 * (0.75 + 0.2 * math.sin(k * 0.9 + n) if (k + 3 * n) % 9 else 0.0)) for k in range(21)]
        p.append(_poli(pts, SERIES[0], 1.4))
    return p


def miniatura_svg(i: str) -> str:
    """Miniatura esquemática (160 × 100) de la forma del gráfico i del catálogo, con los colores de estado y de series del tablero.
    No lleva cifras: es un dibujo de cómo se ve el gráfico, para la biblioteca. KeyError si el gráfico no existe."""
    if i not in FICHA:
        raise KeyError(f"Gráfico desconocido: {i}")
    forma = FICHA[i][0]
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_MW} {_MH}" width="100%" role="img" '
         f'aria-label="{_h.escape("Miniatura: " + TITULO[i])}">', f'<rect x="0" y="0" width="{_MW}" height="{_MH}" rx="8" fill="{_FONDO_MINI}"/>']
    if forma == "barras_apiladas":
        p += _mini_barras_apiladas()
    elif forma == "torta":
        p += _mini_torta(44, 50, 30) + _mini_torta(116, 50, 30, [("operando", 0.72), ("esperando", 0.16), ("falla", 0.07), ("detenido", 0.05)])
    elif forma == "gantt":
        p += _mini_gantt()
    elif forma == "gantt_linea":
        p += _mini_gantt_linea()
    elif forma == "acumulada":
        p += [_ejes(), _poli(_curva(lambda u: u * (0.95 - 0.1 * math.sin(6 * u) * u)), SERIES[0], 2.2)]
        if FUENTE[i] == "operacion":
            p.append(_poli(_curva(lambda u: 0.88 * u * (0.95 - 0.1 * math.sin(6 * u) * u)), SERIES[1], 2.2))
    elif forma == "lineas":
        p += [_ejes(), _poli(_curva(lambda u: 0.62 + 0.18 * math.sin(9 * u)), SERIES[0], 1.8),
              _poli(_curva(lambda u: 0.45 + 0.12 * math.sin(7 * u + 1.2)), SERIES[1], 1.8)]
        if i == "prod_por_turno":
            p.append(_poli(_curva(lambda u: 0.25 + 0.1 * math.cos(11 * u)), SERIES[2], 1.8))
    elif forma == "escalon":
        alturas = [0, 1, 3, 2, 4, 5, 3, 2, 1, 0, 0, 2, 3, 1, 0, 0]
        pts = []
        for k, a in enumerate(alturas):
            x0 = _MX0 + 3 + k * 8.2; y = _MY1 - 3 - 12 * a
            pts += [(x0, y), (x0 + 8.2, y)]
        p += [_ejes(), _poli(pts, SERIES[0], 1.8)]
    elif forma == "histograma":
        p += _mini_histograma()
    elif forma == "tabla":
        p += _mini_tabla()
    elif forma == "tarjetas":
        p += _mini_tarjetas()
    elif forma == "barras":
        p += _mini_barras()
    elif forma == "curva":
        p += [_ejes(), _poli(_curva(lambda u: (1 - math.exp(-u / 0.12)) if u < 0.6 else (1 - math.exp(-0.6 / 0.12)) * math.exp(-(u - 0.6) / 0.15)),
                             SERIES[1], 2.2)]
    elif forma == "calor":
        p += [_ejes(), _poli(_curva(lambda u: 0.9), SERIES[0], 1.8),
              _poli(_curva(lambda u: 0.85 * (1 - math.exp(-u / 0.3))), SERIES[1], 1.8),
              _poli(_curva(lambda u: 0.9 - 0.85 * (1 - math.exp(-u / 0.3))), SERIES[2], 1.8)]
    elif forma == "decaimiento":
        p += [_ejes(), f'<path d="M{_MX0} 66H{_MX1}" stroke="{EJE}" stroke-width="1" stroke-dasharray="4 3"/>',
              _poli(_curva(lambda u: 0.08 + 0.88 * math.exp(-u / 0.35)), SERIES[2], 2.2)]
    elif forma == "nivel":
        pts = _curva(lambda u: 0.45 + 0.3 * math.sin(7 * u) + 0.12 * math.sin(19 * u))
        area = f'M{pts[0][0]:.1f} {_MY1}' + "".join(f'L{x:.1f} {y:.1f}' for x, y in pts) + f'L{pts[-1][0]:.1f} {_MY1}Z'
        p += [_ejes(), f'<path d="{area}" fill="{SERIES[0]}" fill-opacity="0.18"/>', _poli(pts, SERIES[0], 1.8),
              f'<path d="M{_MX0} 18H{_MX1}" stroke="{SERIES[1]}" stroke-width="1.4" stroke-dasharray="4 3"/>']
    elif forma == "multiples":
        p += _mini_multiples()
    p.append("</svg>")
    return "".join(p)


# ----------------------------------------------------------------------------------------------- modelo de cada tablero
def ancho_defecto(i: str) -> str:
    return "completo" if i in ANCHO_COMPLETO else "medio"


def tablero_nuevo(plantilla="Vacío", columnas: int = 2) -> dict:
    """Tablero dict(graficos=[dict(id, ancho)], columnas) desde el nombre de una plantilla o una lista de ids."""
    ids = PLANTILLAS[plantilla][1] if isinstance(plantilla, str) else list(plantilla or [])
    return normalizar_tablero(dict(graficos=[dict(id=i, ancho=ancho_defecto(i)) for i in ids], columnas=columnas))


def normalizar_tablero(v) -> dict:
    """Acepta el formato anterior (lista de ids), una lista de dict o un dict; quita ids desconocidos y repetidos."""
    if isinstance(v, dict):
        crudos, columnas = v.get("graficos") or [], v.get("columnas", 2)
    else:
        crudos, columnas = (v or []), 2
    vistos, graficos = set(), []
    for g in crudos:
        i = g.get("id") if isinstance(g, dict) else g
        if i in TITULO and i not in vistos:
            vistos.add(i)
            a = g.get("ancho") if isinstance(g, dict) else None
            graficos.append(dict(id=i, ancho=a if a in ANCHOS else ancho_defecto(i)))
    try:
        columnas = 1 if int(columnas) == 1 else 2
    except (TypeError, ValueError):
        columnas = 2
    return dict(graficos=graficos, columnas=columnas)


def normalizar_tableros(T) -> dict:
    """Migra st.session_state.tableros del formato anterior (nombre -> lista de ids) al nuevo, sin perder el orden ni los nombres.
    Sin tableros, entrega el «Tablero principal» con los gráficos por defecto."""
    if not isinstance(T, dict) or not T:
        return {TABLERO_INICIAL: tablero_nuevo(POR_DEFECTO)}
    return {str(n): normalizar_tablero(v) for n, v in T.items()}


def ids_tablero(t) -> list:
    return [g["id"] for g in normalizar_tablero(t)["graficos"]]


def _pos(t: dict, i: str) -> int:
    return next((n for n, g in enumerate(t["graficos"]) if g["id"] == i), -1)


def agregar_grafico(t: dict, i: str, ancho: str | None = None) -> bool:
    """Agrega i al final del tablero t (dict normalizado). False si no existe o ya está."""
    if i not in TITULO or _pos(t, i) >= 0:
        return False
    t["graficos"].append(dict(id=i, ancho=ancho if ancho in ANCHOS else ancho_defecto(i)))
    return True


def quitar_grafico(t: dict, i: str) -> bool:
    n = _pos(t, i)
    if n < 0:
        return False
    t["graficos"].pop(n)
    return True


def mover_grafico(t: dict, i: str, paso: int) -> bool:
    """Sube (paso −1) o baja (paso +1) el gráfico i. False si no se puede mover."""
    n = _pos(t, i); m = n + int(paso)
    if n < 0 or m < 0 or m >= len(t["graficos"]) or m == n:
        return False
    g = t["graficos"]; g[n], g[m] = g[m], g[n]
    return True


def alternar_ancho(t: dict, i: str) -> str | None:
    """Cambia el gráfico i entre medio ancho y ancho completo; devuelve el ancho nuevo."""
    n = _pos(t, i)
    if n < 0:
        return None
    g = t["graficos"][n]; g["ancho"] = "medio" if g["ancho"] == "completo" else "completo"
    return g["ancho"]


def filas_grilla(t: dict, columnas: int | None = None) -> list:
    """Filas de la grilla: con una columna, un gráfico por fila; con dos, los de ancho completo van solos y los de medio ancho se
    juntan de a dos en el orden del tablero (uno de medio ancho seguido de uno completo queda solo, en la mitad izquierda)."""
    columnas = t.get("columnas", 2) if columnas is None else columnas
    filas, par = [], []
    for g in t["graficos"]:
        if columnas == 1:
            filas.append([g]); continue
        if g["ancho"] == "completo":
            if par:
                filas.append(par); par = []
            filas.append([g])
        else:
            par.append(g)
            if len(par) == 2:
                filas.append(par); par = []
    if par:
        filas.append(par)
    return filas


def nombre_libre(base: str, existentes) -> str:
    base = (base or "").strip() or "Tablero"
    nombre, n = base, 2
    while nombre in existentes:
        nombre = f"{base} ({n})"; n += 1
    return nombre
