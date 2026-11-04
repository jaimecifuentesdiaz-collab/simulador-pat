"""Experimentos con réplicas y optimizador simple, como el Experimenter de FlexSim (PAT 134, segunda ronda, 02-11-2026).

Lo que hace (en palabras propias, según el manual público de FlexSim): se eligen variables del modelo, se arman escenarios
con un valor para cada variable, se definen medidas de desempeño y se corre cada escenario varias veces (réplicas); los
resultados se resumen por escenario con media, intervalo de confianza, mínimo y máximo, gráfico de réplicas y exportación.
En lugar de OptQuest (búsqueda metaheurística comercial de OptTek que trae FlexSim) se ofrece una búsqueda simple en grilla o
aleatoria con réplicas: evalúa todos los candidatos o una muestra al azar, descarta los que violan las restricciones en la
media y los ordena por el objetivo. No es una metaheurística y se declara así.

Método estadístico: Law, A. M. (2015). Simulation modeling and analysis (5.ª ed.). McGraw-Hill Education, capítulo 9
(análisis de resultados de un sistema: réplicas independientes, intervalo de confianza t de Student, periodo de
calentamiento) y capítulo 10 (comparación de sistemas: números aleatorios comunes y diferencias pareadas). Solo se cita el
método, sin páginas. El cuantil t se calcula sin scipy: bisección de la distribución t, que se escribe con la función beta
incompleta regularizada evaluada por su fracción continua (algoritmo de Lentz modificado).

Calentamiento: en los modelos «temporada» y «operacion» el estado inicial es real (la temporada y la operación parten
vacías, como parte la planta), así que el resultado de interés es de horizonte finito (*terminating simulation* en Law,
2015, cap. 9) y no se descarta nada: el calentamiento por defecto es 0 y, si se pide otro valor, se ignora con un aviso. En
el modelo «linea» (motor/linea_fluida.py, de otro equipo) sí se pueden descartar las primeras horas.
"""
from __future__ import annotations
import copy
import html as _h
import itertools
import math
import random
from . import temporada as TM
from . import operacion as OP
from .operacion import _cl

FUENTE = "Law, A. M. (2015). Simulation modeling and analysis (5.ª ed.). McGraw-Hill Education, cap. 9 y 10 (método)"
NOTA_OPTQUEST = ("Búsqueda simple en grilla o aleatoria con réplicas, en lugar de OptQuest: evalúa candidatos con números aleatorios "
                 "comunes, descarta los que violan las restricciones en la media y los ordena por el objetivo. No es la búsqueda "
                 "metaheurística de OptQuest y no garantiza el óptimo fuera de los puntos evaluados.")
NOTA_CALENTAMIENTO = ("En este modelo el estado inicial es real (inicio de la temporada o de la operación, con la planta partiendo como "
                      "parte en la realidad): es una simulación de horizonte finito y no corresponde descartar un periodo de "
                      "calentamiento (Law, 2015, cap. 9).")
LIMITE_GRILLA = 500


# ----------------------------------------------------------------------------------------------- distribución t de Student
def _betacf(a: float, b: float, x: float) -> float:
    """Fracción continua de la beta incompleta (algoritmo de Lentz modificado)."""
    tiny = 1e-300; qab = a + b; qap = a + 1.0; qam = a - 1.0
    c = 1.0; d = 1.0 - qab * x / qap
    d = tiny if abs(d) < tiny else d; d = 1.0 / d; h = d
    for m in range(1, 400):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d; d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c; c = tiny if abs(c) < tiny else c
        d = 1.0 / d; h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d; d = tiny if abs(d) < tiny else d
        c = 1.0 + aa / c; c = tiny if abs(c) < tiny else c
        d = 1.0 / d; de = d * c; h *= de
        if abs(de - 1.0) < 1e-15:
            break
    return h


def beta_inc(a: float, b: float, x: float) -> float:
    """Función beta incompleta regularizada I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    bt = math.exp(math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b) + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return bt * _betacf(a, b, x) / a
    return 1.0 - bt * _betacf(b, a, 1.0 - x) / b


def t_cdf(t: float, gl: float) -> float:
    """Distribución acumulada de la t de Student con gl grados de libertad."""
    if gl <= 0:
        raise ValueError("Los grados de libertad deben ser positivos.")
    x = gl / (gl + t * t)
    cola = 0.5 * beta_inc(gl / 2.0, 0.5, x)
    return 1.0 - cola if t > 0 else cola


def t_cuantil(p: float, gl: float) -> float:
    """Cuantil p de la t de Student por bisección de t_cdf (sin scipy)."""
    if not 0.0 < p < 1.0:
        raise ValueError("La probabilidad debe estar entre 0 y 1.")
    if abs(p - 0.5) < 1e-15:
        return 0.0
    if p < 0.5:
        return -t_cuantil(1.0 - p, gl)
    lo, hi = 0.0, 1.0
    while t_cdf(hi, gl) < p:
        lo, hi = hi, hi * 2.0
        if hi > 1e12:
            break
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if t_cdf(mid, gl) < p:
            lo = mid
        else:
            hi = mid
        if hi - lo < 1e-12 * max(1.0, hi):
            break
    return 0.5 * (lo + hi)


def estadisticos(valores: list, confianza: float = 0.95) -> dict:
    """Media, desviación estándar muestral, intervalo de confianza t de Student, mínimo y máximo (Law, 2015, cap. 9)."""
    x = [float(v) for v in valores if v is not None and not (isinstance(v, float) and math.isnan(v))]
    n = len(x)
    if n == 0:
        return dict(n=0, media=None, desviacion=None, ic_inf=None, ic_sup=None, semiancho=None, minimo=None, maximo=None, t=None)
    m = sum(x) / n
    if n < 2:
        return dict(n=1, media=m, desviacion=None, ic_inf=None, ic_sup=None, semiancho=None, minimo=m, maximo=m, t=None)
    s = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    t = t_cuantil(1.0 - (1.0 - confianza) / 2.0, n - 1)
    h = t * s / math.sqrt(n)
    return dict(n=n, media=m, desviacion=s, ic_inf=m - h, ic_sup=m + h, semiancho=h, minimo=min(x), maximo=max(x), t=t)


# ----------------------------------------------------------------------------------------------- modelos
def _var(clave, nombre, unidad, defecto, minimo, maximo, entero=False, ayuda=""):
    return dict(clave=clave, nombre=nombre, unidad=unidad, defecto=defecto, minimo=minimo, maximo=maximo, entero=entero, ayuda=ayuda)


def _med(clave, nombre, unidad, sentido, decimales=2):
    return dict(clave=clave, nombre=nombre, unidad=unidad, sentido=sentido, decimales=decimales)


def _cap_recepcion(pl) -> float:
    """Capacidad de recepción por defecto de llegadas_temporada (base «recepcion»)."""
    d = TM.datos_planta(pl)
    return float(d["cap_primero"]) if d["cap_primero"] else d["carga"] * 1.10


def _modelo_temporada(pl, p: dict, semilla: int) -> dict:
    pr = TM.programa_temporada(pl, arranque_h=p["arranque_h"], cip_cada_h=p["cip_cada_h"], cip_duracion_h=p["cip_duracion_h"],
                               parada_cada_d=p["parada_cada_d"], resumen={})
    ll = TM.llegadas_temporada(pl, semilla=int(semilla), camion_t=p["camion_t"], cv_servicio=p["cv_servicio"],
                               capacidad_t_h=p["capacidad_t_h"] or None, base="recepcion", programa=pr)
    return dict(espera_media_h=ll["espera_media_h"], espera_max_h=ll["espera_max_h"], cola_final_t=max(0.0, ll["cola_final_t"]),
                total_degradado_t=ll["total_degradado_t"], utilizacion_media=100.0 * ll["utilizacion_media"],
                produccion_programa_t=pr["produccion_programa_t"] or 0.0, disponibilidad=100.0 * pr["disponibilidad"])


def _modelo_operacion(pl, p: dict, semilla: int) -> dict:
    c = copy.deepcopy(pl)                      # correr_turno desgasta los equipos: cada réplica parte de la misma planta
    op = OP.Operacion(rubro=c.rubro, semilla=int(semilla))
    ln = OP.linea(c)
    if ln is None:
        raise ValueError("La planta no tiene producción: resuélvala en la pestaña Diseño.")
    n = int(p["turnos"]); k = int(p["mant_cada"]); h = OP.S["horas_turno"]
    regs = [OP.correr_turno(op, c, p["meta"], None, "preventivo" if k > 0 and t % k == 0 else "ninguno", None) for t in range(1, n + 1)]
    conforme = sum(r["conforme"] for r in regs); producido = sum(r["producido"] for r in regs)
    demanda = sum(r["demanda"] for r in regs); vendido = sum(r["vendido"] for r in regs)
    plan = ln["plan"] * h * n
    return dict(produccion_conforme_t=conforme, faltante_t=sum(r["faltante"] for r in regs),
                conformidad_media=100.0 * sum(r["conformidad"] for r in regs) / n, oee=100.0 * conforme / plan if plan else 0.0,
                nivel_servicio=100.0 * vendido / demanda if demanda else 100.0, producido_t=producido)


_SONDA: dict = {}


def _pct(v):
    if isinstance(v, dict):
        v = v.get("oee", v.get("valor"))
    if v is None:
        return None
    v = float(v)
    return 100.0 * v if v <= 1.0 + 1e-9 else v


def _modelo_linea(pl, p: dict, semilla: int, calentamiento: float = 0.0, simular=None) -> dict:
    """Corre motor/linea_fluida.simular_linea (contrato del diseño PAT 134) con fallas exponenciales comunes y tanques en minutos."""
    if simular is None:
        from .linea_fluida import simular_linea as simular
    horas = float(p["horas"]); fallas = tanques = None
    if (p["mtbf_h"] > 0 and p["mttr_h"] > 0) or p["tanque_min"] > 0:
        clave = (id(pl), getattr(pl, "rubro", ""), tuple(sorted(getattr(pl, "equipos", {}))))
        if clave not in _SONDA:                  # ids de equipos y tanques de la línea, con una corrida corta
            s = simular(pl, horas=1.0, semilla=0)
            _SONDA[clave] = (copy.deepcopy(s["equipos"]), copy.deepcopy(s["tanques"]))
        equipos, tq = _SONDA[clave]
        if p["mtbf_h"] > 0 and p["mttr_h"] > 0:
            from . import ajuste as AJ
            # PAT 134: los equipos sin capacidad declarada (acopio, despacho) no fallan, como el Supuesto «sin_capacidad» de la línea
            fallas = {e["id"]: dict(mtbf=AJ.crear("exponencial", nota="Experimentos: MTBF común", escala=p["mtbf_h"]),
                                    mttr=AJ.crear("exponencial", nota="Experimentos: MTTR común", escala=p["mttr_h"]), base="operando")
                      for e in equipos if e.get("capacidad_t_h") is not None}
        if p["tanque_min"] > 0:
            # PAT 134: simular_linea recibe los tanques como dict {id del tanque: dict(capacidad_t, nivel_inicial_t)}; una lista
            # se ignoraba y quedaban los tanques por defecto. La capacidad va en minutos de la carga del equipo siguiente, la
            # misma base del Supuesto «tanque_min» de la línea: el tanque guarda lo que entra a ese equipo.
            carga = {e["id"]: float(e.get("carga_t_h") or 0.0) for e in equipos}
            tanques = {}
            for t in tq:
                cap = p["tanque_min"] / 60.0 * carga.get(t["despues"], 0.0)
                f0 = (float(t["nivel_inicial_t"]) / float(t["capacidad_t"])) if t.get("capacidad_t") else 0.0
                tanques[t["id"]] = dict(capacidad_t=cap, nivel_inicial_t=cap * f0)
    r = simular(pl, horas=horas, semilla=int(semilla), fallas=fallas, tanques=tanques)
    eqs = r["equipos"]
    crit = max(eqs, key=lambda e: (float(e.get("carga_t_h") or 0) / float(e["capacidad_t_h"]) if e.get("capacidad_t_h") else 0.0))["id"] if eqs else None
    cal = max(0.0, min(float(calentamiento), horas))
    prod = float(r["produccion_t"]); util = _pct((r["por_equipo"].get(crit) or {}).get("utilizacion")) if crit else None
    if cal > 0:
        T = r["tiempo_h"]; A = r["produccion_acumulada_t"]
        a0 = A[0] if T and cal <= T[0] else next((A[i - 1] + (A[i] - A[i - 1]) * (cal - T[i - 1]) / (T[i] - T[i - 1])
                                                  for i in range(1, len(T)) if T[i] >= cal and T[i] > T[i - 1]), A[-1] if A else 0.0)
        prod = (A[-1] if A else prod) - a0
        if crit and horas > cal:
            op = sum(max(0.0, min(x["fin_h"], horas) - max(x["inicio_h"], cal)) for x in r["tramos"]
                     if x["equipo"] == crit and x["estado"] == "operando")
            util = 100.0 * op / (horas - cal)
    return dict(produccion_t=prod, oee=_pct(r.get("oee")) or 0.0, utilizacion_critico=util or 0.0,
                fallas=float(sum(float(v.get("fallas") or 0) for v in r["por_equipo"].values())))


MODELOS = {
    "temporada": dict(
        nombre="Temporada: cola de camiones y programa de producción", calentamiento=False,
        nota="motor/temporada.py: llegadas_temporada con el programa de la temporada (la recepción atiende en las horas de producción)",
        variables=[
            _var("camion_t", "Carga de un camión", "t", lambda pl: TM.supuestos(pl)["camion"], 5.0, 60.0),
            _var("cv_servicio", "Variación de la descarga (coeficiente de variación)", "—", lambda pl: TM.supuestos(pl)["cv_servicio"], 0.0, 2.0),
            _var("capacidad_t_h", "Capacidad de recepción", "t/h", _cap_recepcion, lambda pl: 0.25 * _cap_recepcion(pl),
                 lambda pl: 4.0 * _cap_recepcion(pl), ayuda="Por defecto, la capacidad efectiva del primer equipo de la línea"),
            _var("cip_cada_h", "Limpieza cada", "h de producción", lambda pl: TM.supuestos(pl)["cip_cada"], 0.0, 2000.0),
            _var("cip_duracion_h", "Duración de la limpieza", "h", lambda pl: TM.supuestos(pl)["cip_dur"], 0.0, 48.0),
            _var("parada_cada_d", "Parada programada cada", "d", lambda pl: TM.supuestos(pl)["parada_cada"], 0.0, 366.0),
            _var("arranque_h", "Arranque de la temporada", "h", lambda pl: TM.supuestos(pl)["arranque"], 0.0, 240.0),
        ],
        medidas=[
            _med("espera_media_h", "Espera media de un camión", "h", "min", 2),
            _med("espera_max_h", "Espera máxima de un camión", "h", "min", 1),
            _med("cola_final_t", "Materia prima en el patio al cierre", "t", "min", 1),
            _med("total_degradado_t", "Materia prima degradada", "t", "min", 1),
            _med("utilizacion_media", "Utilización media de la recepción", "%", "max", 1),
            _med("produccion_programa_t", "Producción del programa", "t", "max", 0),
            _med("disponibilidad", "Disponibilidad del programa", "%", "max", 1),
        ],
        funcion=_modelo_temporada),
    "operacion": dict(
        nombre="Operación por turnos", calentamiento=False,
        nota="motor/operacion.py: correr_turno sobre una copia de la planta y una Operacion nueva con la semilla de la réplica",
        variables=[
            _var("meta", "Utilización objetivo (meta)", "fracción", 0.90, 0.30, 1.0),
            _var("mant_cada", "Mantenimiento preventivo cada", "turnos (0 = sin mantenimiento)", 0, 0, 30, entero=True),
            _var("turnos", "Turnos simulados", "turnos de 8 h", 21, 1, 300, entero=True, ayuda="21 turnos son una semana de 3 turnos diarios"),
        ],
        medidas=[
            _med("produccion_conforme_t", "Producción conforme", "t", "max", 1),
            _med("faltante_t", "Demanda no atendida (faltante)", "t", "min", 1),
            _med("conformidad_media", "Conformidad media", "%", "max", 1),
            _med("oee", "OEE (producto conforme / producción planificada)", "%", "max", 1),
            _med("nivel_servicio", "Nivel de servicio (vendido / demanda)", "%", "max", 1),
            _med("producido_t", "Producción total", "t", "max", 1),
        ],
        funcion=_modelo_operacion),
}

_LINEA = dict(
    nombre="Línea por ticks (fallas MTBF/MTTR y tanques pulmón)", calentamiento=True,
    nota=("motor/linea_fluida.py: simular_linea. MTBF y MTTR comunes a todos los equipos con distribución exponencial (Supuesto: forma "
          "simple con la media indicada; para otra distribución use la pestaña Línea). Con 0 se usan los valores por tipo de equipo del "
          "motor de la línea. Capacidad de los tanques en minutos de la carga del equipo siguiente; con 0, la del motor de la línea"),
    variables=[
        _var("horas", "Horas simuladas", "h", 72.0, 1.0, 2000.0),
        _var("mtbf_h", "Tiempo medio entre fallas (MTBF), común", "h (0 = del motor)", 0.0, 0.0, 10000.0),
        _var("mttr_h", "Tiempo medio de reparación (MTTR), común", "h (0 = del motor)", 0.0, 0.0, 200.0),
        _var("tanque_min", "Capacidad de los tanques pulmón", "min de carga (0 = del motor)", 0.0, 0.0, 600.0),
    ],
    medidas=[
        _med("produccion_t", "Producción de la línea", "t", "max", 1),
        _med("oee", "OEE de la línea", "%", "max", 1),
        _med("utilizacion_critico", "Utilización del equipo crítico", "%", "max", 1),
        _med("fallas", "Fallas de todos los equipos", "fallas", "min", 1),
    ],
    funcion=_modelo_linea)


def registrar_linea(simular=None) -> bool:
    """Registra el modelo «linea» si existe pat_sim.motor.linea_fluida.simular_linea (o con la función dada, para pruebas)."""
    if simular is None:
        try:
            from .linea_fluida import simular_linea as simular
        except Exception:
            MODELOS.pop("linea", None)
            return False
    MODELOS["linea"] = dict(_LINEA, funcion=lambda pl, p, s, cal=0.0, _f=simular: _modelo_linea(pl, p, s, cal, _f))
    return True


registrar_linea()


def disponibles() -> dict:
    """Modelos registrados (vuelve a buscar la línea, que otro equipo puede agregar después)."""
    if "linea" not in MODELOS:
        registrar_linea()
    return MODELOS


def _modelo(modelo):
    if isinstance(modelo, dict):
        return modelo
    m = disponibles().get(modelo)
    if m is None:
        raise ValueError(f"Modelo desconocido: {modelo}. Disponibles: {', '.join(disponibles())}.")
    return m


def _resolver(v, pl):
    return v(pl) if callable(v) else v


def variables(pl, modelo) -> list[dict]:
    """Variables del modelo con su valor por defecto, mínimo y máximo para la planta."""
    out = []
    for v in _modelo(modelo)["variables"]:
        d = dict(v); d["defecto"] = _resolver(v["defecto"], pl); d["minimo"] = _resolver(v["minimo"], pl); d["maximo"] = _resolver(v["maximo"], pl)
        out.append(d)
    return out


def medidas(modelo) -> list[dict]:
    return [dict(m) for m in _modelo(modelo)["medidas"]]


def escenarios_ejemplo(pl, modelo) -> list[dict]:
    """«Base» y dos escenarios de ejemplo para empezar la tabla de escenarios."""
    vs = {v["clave"]: v for v in variables(pl, modelo)}; base = {k: v["defecto"] for k, v in vs.items()}
    out = [dict(nombre="Base", params=dict(base))]
    if modelo == "temporada":
        out += [dict(nombre="Recepción +20 %", params=dict(base, capacidad_t_h=round(1.2 * base["capacidad_t_h"], 3))),
                dict(nombre="Descarga más variable", params=dict(base, cv_servicio=round(2 * base["cv_servicio"], 3)))]
    elif modelo == "operacion":
        out += [dict(nombre="Meta 100 %", params=dict(base, meta=1.0)),
                dict(nombre="Mantenimiento cada 3 turnos", params=dict(base, mant_cada=3))]
    elif modelo == "linea":
        out += [dict(nombre="Tanques de 60 min", params=dict(base, tanque_min=60.0)),
                dict(nombre="Tanques de 10 min", params=dict(base, tanque_min=10.0))]
    return out


def completar(pl, modelo, params: dict) -> tuple[dict, list]:
    """Parámetros completos (los que faltan van con su valor por defecto) acotados a mínimo y máximo, con avisos."""
    vs = variables(pl, modelo); claves = {v["clave"] for v in vs}; avisos = []
    extra = [k for k in (params or {}) if k not in claves]
    if extra:
        raise ValueError(f"Variables desconocidas para el modelo: {', '.join(extra)}.")
    out = {}
    for v in vs:
        x = (params or {}).get(v["clave"])
        x = v["defecto"] if x is None or (isinstance(x, float) and math.isnan(x)) else float(x)
        if x < v["minimo"] - 1e-12 or x > v["maximo"] + 1e-12:
            y = min(max(x, v["minimo"]), v["maximo"])
            avisos.append(f"{v['nombre']}: {_cl(x, 3)} queda fuera del rango; se usó {_cl(y, 3)}.")
            x = y
        out[v["clave"]] = int(round(x)) if v["entero"] else float(x)
    return out, avisos


# ----------------------------------------------------------------------------------------------- experimento
def correr(pl, modelo, escenarios: list, replicas: int = 5, semilla_base: int = 1, calentamiento: float = 0.0) -> dict:
    """Corre cada escenario con las mismas réplicas (números aleatorios comunes: la réplica r usa la semilla semilla_base + r en
    todos los escenarios, Law, 2015, cap. 10) y resume cada medida con media, desviación, IC t al 95 %, mínimo y máximo."""
    M = _modelo(modelo); clave_modelo = modelo if isinstance(modelo, str) else M.get("clave", "personalizado")
    replicas = int(replicas)
    if replicas < 1:
        raise ValueError("Se necesita al menos una réplica.")
    if not escenarios:
        raise ValueError("Se necesita al menos un escenario.")
    nombres = [str(e.get("nombre") or "").strip() for e in escenarios]
    if any(not n for n in nombres) or len(set(nombres)) != len(nombres):
        raise ValueError("Cada escenario necesita un nombre propio (sin repetir).")
    semillas = [int(semilla_base) + r for r in range(replicas)]
    avisos = []; cal = max(0.0, float(calentamiento or 0.0))
    if cal > 0 and not M.get("calentamiento"):
        avisos.append("Se pidió un calentamiento de " + _cl(cal, 1) + " h, pero se ignora. " + NOTA_CALENTAMIENTO); cal = 0.0
    meds = M["medidas"]; crudos = {}; esc_out = []
    for nom, e in zip(nombres, escenarios):
        p, av = completar(pl, modelo, e.get("params") or {}) if not isinstance(modelo, dict) else (dict(e.get("params") or {}), [])
        avisos += [f"{nom}: {a}" for a in av]
        crudos[nom] = {m["clave"]: [] for m in meds}
        for s in semillas:
            try:
                r = M["funcion"](pl, p, s, cal) if M.get("calentamiento") and cal > 0 else M["funcion"](pl, p, s)
            except ValueError as ex:
                raise ValueError(f"Escenario «{nom}», semilla {s}: {ex}") from ex
            for m in meds:
                v = r.get(m["clave"])
                crudos[nom][m["clave"]].append(None if v is None else float(v))
        esc_out.append(dict(nombre=nom, params=p))
    resumen = []
    for e in esc_out:
        for m in meds:
            st = estadisticos(crudos[e["nombre"]][m["clave"]])
            resumen.append(dict(escenario=e["nombre"], medida=m["clave"], nombre=m["nombre"], unidad=m["unidad"], **st))
    if replicas < 2:
        avisos.append("Con una réplica no hay intervalo de confianza: use dos o más (Law, 2015, cap. 9).")
    nota_cal = ("Se descartan las primeras " + _cl(cal, 1) + " h de cada réplica (periodo de calentamiento).") if cal > 0 else (
        NOTA_CALENTAMIENTO if not M.get("calentamiento") else "Sin calentamiento: se cuenta desde la hora 0.")
    return dict(tipo="experimento", modelo=clave_modelo, nombre_modelo=M["nombre"], rubro=getattr(pl, "rubro", ""), escenarios=esc_out,
                medidas=[dict(m) for m in meds], replicas=replicas, semillas=semillas, calentamiento_h=cal, nota_calentamiento=nota_cal,
                crudos=crudos, resumen=resumen, confianza=0.95, avisos=avisos,
                metodo=("Réplicas independientes con números aleatorios comunes (la réplica r usa la misma semilla en todos los escenarios); "
                        "intervalo de confianza al 95 % con la t de Student de n − 1 grados de libertad: media ± t·s/√n."),
                fuente=FUENTE, nota_modelo=M.get("nota", ""))


def fila(resultado: dict, escenario: str, medida: str) -> dict:
    return next(f for f in resultado["resumen"] if f["escenario"] == escenario and f["medida"] == medida)


def comparar(resultado: dict, a: str, b: str, medida: str, confianza: float = 0.95) -> dict:
    """Diferencia pareada a − b por réplica (válida porque ambas usan las mismas semillas) con su IC t (Law, 2015, cap. 10).
    La diferencia es significativa si el intervalo no contiene el cero."""
    xa = resultado["crudos"][a][medida]; xb = resultado["crudos"][b][medida]
    d = [x - y for x, y in zip(xa, xb) if x is not None and y is not None]
    st = estadisticos(d, confianza)
    sig = st["ic_inf"] is not None and (st["ic_inf"] > 0 or st["ic_sup"] < 0)
    m = next((x for x in resultado["medidas"] if x["clave"] == medida), {"nombre": medida, "unidad": "", "sentido": "max"})
    mejor = None
    if sig:
        mejor = a if (st["media"] > 0) == (m.get("sentido") == "max") else b
    if st["n"] < 2:
        txt = "Con menos de dos réplicas no se puede decir si la diferencia es significativa."
    elif sig:
        txt = (f"La diferencia {a} − {b} en {m['nombre'].lower()} es {_cl(st['media'], 3)} {m['unidad']} con IC al {_cl(100 * confianza, 0)} % "
               f"de {_cl(st['ic_inf'], 3)} a {_cl(st['ic_sup'], 3)}: no contiene el cero, es significativa. Mejor: {mejor}.")
    else:
        txt = (f"La diferencia {a} − {b} en {m['nombre'].lower()} es {_cl(st['media'], 3)} {m['unidad']} con IC al {_cl(100 * confianza, 0)} % "
               f"de {_cl(st['ic_inf'], 3)} a {_cl(st['ic_sup'], 3)}: contiene el cero, no es significativa con {st['n']} réplicas.")
    return dict(a=a, b=b, medida=medida, diferencias=d, significativa=sig, mejor=mejor, texto=txt, **st)


# ----------------------------------------------------------------------------------------------- optimizador
def _valores(lo: float, hi: float, paso: float, entero: bool = False) -> list:
    lo, hi = float(min(lo, hi)), float(max(lo, hi))
    if paso is None or paso <= 0:
        vals = [lo] if hi - lo < 1e-12 else [lo, hi]
    else:
        n = int(math.floor((hi - lo) / paso + 1e-9))
        vals = [round(lo + i * paso, 10) for i in range(n + 1)]
        if hi - vals[-1] > 1e-9 * max(1.0, abs(hi)):     # el máximo siempre se evalúa aunque el paso no calce justo
            vals.append(hi)
    if entero:
        vals = sorted(set(int(round(v)) for v in vals))
    return vals


def optimizar(pl, modelo, variables: dict, objetivo: tuple, restricciones: list | None = None, replicas: int = 3,
              metodo: str = "grilla", n: int = 20, semilla_base: int = 1) -> dict:
    """Busca la mejor configuración: variables = {clave: (mínimo, máximo, paso)}, objetivo = (medida, "max"|"min"),
    restricciones = [(medida, "<="|">=", valor)] sobre la media de las réplicas. «grilla» evalúa todas las combinaciones
    (hasta 500); «aleatorio» evalúa n combinaciones distintas de la grilla al azar. Las demás variables quedan en su valor
    por defecto. Todos los candidatos usan las mismas semillas (números aleatorios comunes). """
    M = _modelo(modelo); restricciones = list(restricciones or [])
    if not variables:
        raise ValueError("Elija al menos una variable de diseño.")
    meds = {m["clave"]: m for m in M["medidas"]}
    med_obj, sentido = objetivo
    if med_obj not in meds:
        raise ValueError(f"Medida objetivo desconocida: {med_obj}.")
    if sentido not in ("max", "min"):
        raise ValueError("El sentido del objetivo debe ser «max» o «min».")
    for r in restricciones:
        if r[0] not in meds or r[1] not in ("<=", ">="):
            raise ValueError(f"Restricción mal escrita: {r}.")
    info = {v["clave"]: v for v in (variables_modelo(pl, modelo))}
    ejes = []
    for k, (lo, hi, paso) in variables.items():
        if not isinstance(modelo, dict) and k not in info:
            raise ValueError(f"Variable desconocida: {k}.")
        ejes.append((k, _valores(lo, hi, paso, info.get(k, {}).get("entero", False))))
    total = 1
    for _k, vals in ejes:
        total *= len(vals)
    avisos = []
    if metodo == "grilla":
        if total > LIMITE_GRILLA:
            raise ValueError(f"La grilla tiene {total} combinaciones y el máximo es {LIMITE_GRILLA}: aumente el paso o use el método aleatorio.")
        combos = list(itertools.product(*[v for _k, v in ejes]))
    elif metodo == "aleatorio":
        n = max(1, int(n))
        if total <= n:
            combos = list(itertools.product(*[v for _k, v in ejes]))
            avisos.append(f"La grilla tiene {total} combinaciones, no más que n = {n}: se evaluaron todas.")
        else:
            rng = random.Random(f"optimizar:{semilla_base}"); vistos = set(); combos = []
            while len(combos) < n:
                c = tuple(rng.choice(v) for _k, v in ejes)
                if c not in vistos:
                    vistos.add(c); combos.append(c)
    else:
        raise ValueError("El método debe ser «grilla» o «aleatorio».")
    claves = [k for k, _v in ejes]
    esc = [dict(nombre="C" + str(i + 1), params=dict(zip(claves, c))) for i, c in enumerate(combos)]
    if isinstance(modelo, dict):                 # modelo personalizado (pruebas): sin valores por defecto que completar
        base = {v["clave"]: _resolver(v["defecto"], pl) for v in M.get("variables", [])}
        esc = [dict(nombre=e["nombre"], params=dict(base, **e["params"])) for e in esc]
    res = correr(pl, modelo, esc, replicas=replicas, semilla_base=semilla_base)
    cand = []
    for e in res["escenarios"]:
        medias = {m: fila(res, e["nombre"], m)["media"] for m in meds}
        ic = {m: (fila(res, e["nombre"], m)["ic_inf"], fila(res, e["nombre"], m)["ic_sup"]) for m in meds}
        viol = []
        for mk, opr, val in restricciones:
            x = medias[mk]
            if x is None or (opr == "<=" and x > val + 1e-12) or (opr == ">=" and x < val - 1e-12):
                viol.append(f"{meds[mk]['nombre']} = {_cl(x if x is not None else float('nan'), 3)} no cumple {opr} {_cl(val, 3)}")
        cand.append(dict(candidato=e["nombre"], params={k: e["params"][k] for k in claves}, medias=medias, ic=ic,
                         objetivo=medias[med_obj], factible=not viol, violaciones=viol))
    sg = -1.0 if sentido == "max" else 1.0
    cand.sort(key=lambda c: (not c["factible"], math.inf if c["objetivo"] is None else sg * c["objetivo"]))
    for i, c in enumerate(cand):
        c["posicion"] = i + 1
    mejor = cand[0] if cand and cand[0]["factible"] else None
    if mejor is None:
        avisos.append("Ningún candidato cumple todas las restricciones en la media: relaje las restricciones o amplíe los rangos.")
    return dict(tipo="optimizacion", modelo=res["modelo"], nombre_modelo=res["nombre_modelo"], rubro=res["rubro"], metodo=metodo,
                variables={k: list(v) for k, v in variables.items()}, objetivo=dict(medida=med_obj, sentido=sentido, nombre=meds[med_obj]["nombre"],
                unidad=meds[med_obj]["unidad"]), restricciones=[list(r) for r in restricciones], replicas=res["replicas"],
                semillas=res["semillas"], evaluados=len(cand), factibles=sum(c["factible"] for c in cand), candidatos=cand,
                mejor=mejor, experimento=res, avisos=avisos + res["avisos"], nota=NOTA_OPTQUEST, fuente=FUENTE)


def variables_modelo(pl, modelo) -> list[dict]:
    if isinstance(modelo, dict):
        return [dict(v, defecto=_resolver(v["defecto"], pl), minimo=_resolver(v.get("minimo", -math.inf), pl),
                     maximo=_resolver(v.get("maximo", math.inf), pl)) for v in modelo.get("variables", [])]
    return variables(pl, modelo)


# ----------------------------------------------------------------------------------------------- salidas
def a_filas(resultado: dict) -> list[dict]:
    """Filas planas para CSV o Excel: experimento, una fila por escenario y medida con las réplicas; optimización, una por candidato."""
    if resultado.get("tipo") == "optimizacion":
        out = []
        for c in resultado["candidatos"]:
            f = dict(posicion=c["posicion"], candidato=c["candidato"], **{f"var_{k}": v for k, v in c["params"].items()})
            f.update({f"media_{k}": v for k, v in c["medias"].items()})
            f.update(factible="sí" if c["factible"] else "no", violaciones="; ".join(c["violaciones"]))
            out.append(f)
        return out
    out = []
    for f in resultado["resumen"]:
        g = dict(escenario=f["escenario"], medida=f["medida"], nombre=f["nombre"], unidad=f["unidad"], n=f["n"], media=f["media"],
                 desviacion=f["desviacion"], ic_inf=f["ic_inf"], ic_sup=f["ic_sup"], minimo=f["minimo"], maximo=f["maximo"])
        for i, v in enumerate(resultado["crudos"][f["escenario"]][f["medida"]]):
            g[f"replica_{i + 1}"] = v
        out.append(g)
    return out


def a_csv(resultado: dict) -> str:
    """CSV con punto y coma y coma decimal (Excel en español de Chile)."""
    filas = a_filas(resultado)
    cols = []
    for f in filas:
        cols += [k for k in f if k not in cols]

    def celda(v):
        if v is None:
            return ""
        if isinstance(v, bool):
            return "sí" if v else "no"
        if isinstance(v, (int, float)):
            return repr(float(v)).replace(".", ",") if isinstance(v, float) else str(v)
        s = str(v)
        return '"' + s.replace('"', '""') + '"' if any(c in s for c in ';"\n') else s
    return "\n".join([";".join(cols)] + [";".join(celda(f.get(k)) for k in cols) for f in filas]) + "\n"


def grafico_replicas_svg(resultado: dict, medida: str, ancho: int = 720) -> str:
    """Gráfico de réplicas: una fila por escenario con cada réplica (punto), la media (raya) y el IC al 95 % (barra)."""
    res = resultado["experimento"] if resultado.get("tipo") == "optimizacion" else resultado
    m = next(x for x in res["medidas"] if x["clave"] == medida)
    esc = [e["nombre"] for e in res["escenarios"]]
    vals = [v for e in esc for v in res["crudos"][e][medida] if v is not None]
    ics = [x for e in esc for x in (fila(res, e, medida)["ic_inf"], fila(res, e, medida)["ic_sup"]) if x is not None]
    lo = min(vals + ics) if vals else 0.0; hi = max(vals + ics) if vals else 1.0
    if hi - lo < 1e-12:
        lo, hi = lo - (abs(lo) * 0.05 + 1), hi + (abs(hi) * 0.05 + 1)
    pad = 0.05 * (hi - lo); lo -= pad; hi += pad
    izq, der, arriba, af = 170, 24, 30, 30
    alto = arriba + af * len(esc) + 44
    X = lambda v: izq + (v - lo) / (hi - lo) * (ancho - izq - der)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img" '
         f'aria-label="Réplicas de {_h.escape(m["nombre"])}" style="font-family:sans-serif;background:#fff">',
         f'<rect width="{ancho}" height="{alto}" fill="#fff"/>',
         f'<text x="{izq}" y="18" font-size="13" fill="#36586c">{_h.escape(m["nombre"])} ({_h.escape(m["unidad"])}): réplicas, media e IC al 95 %</text>']
    y1 = arriba + af * len(esc)
    for i in range(6):
        v = lo + i * (hi - lo) / 5; x = X(v)
        p.append(f'<path d="M{x:.1f} {arriba}V{y1}" stroke="#e6eaec"/><text x="{x:.1f}" y="{y1 + 14}" font-size="10" text-anchor="middle" fill="#555">{_cl(v, m.get("decimales", 2))}</text>')
    for i, e in enumerate(esc):
        y = arriba + i * af + af / 2; f = fila(res, e, medida)
        p.append(f'<text x="{izq - 8}" y="{y + 4:.1f}" font-size="11" text-anchor="end" fill="#333">{_h.escape(e[:26])}</text>')
        if f["ic_inf"] is not None:
            p.append(f'<path d="M{X(f["ic_inf"]):.1f} {y:.1f}H{X(f["ic_sup"]):.1f}" stroke="#5b84a8" stroke-width="6" stroke-opacity="0.35"/>')
        for j, v in enumerate(res["crudos"][e][medida]):
            if v is not None:
                p.append(f'<circle cx="{X(v):.1f}" cy="{y:.1f}" r="3.5" fill="#4f7f6a" fill-opacity="0.8"><title>Réplica {j + 1} '
                         f'(semilla {res["semillas"][j]}): {_cl(v, 3)}</title></circle>')
        if f["media"] is not None:
            p.append(f'<path d="M{X(f["media"]):.1f} {y - 9:.1f}V{y + 9:.1f}" stroke="#8b5e5e" stroke-width="2"><title>Media {_cl(f["media"], 3)}</title></path>')
    p.append(f'<path d="M{izq} {arriba}V{y1}H{ancho - der}" fill="none" stroke="#9bacb3"/>'
             f'<text x="{(izq + ancho - der) / 2:.0f}" y="{y1 + 32}" font-size="11" text-anchor="middle" fill="#555">{_h.escape(m["unidad"])}</text></svg>')
    return "".join(p)


def _tabla_html(cab: list, filas: list, alin: list) -> str:
    h = ['<div class="desliz"><table><thead><tr>'] + [f'<th style="text-align:{a}">{_h.escape(c)}</th>' for c, a in zip(cab, alin)] + ["</tr></thead><tbody>"]
    for f in filas:
        h.append("<tr>" + "".join(f'<td style="text-align:{a}">{_h.escape(str(v))}</td>' for v, a in zip(f, alin)) + "</tr>")
    return "".join(h) + "</tbody></table></div>"


def _n(v, d=2):
    return "—" if v is None else _cl(v, d)


def exportar_html(resultado: dict) -> str:
    """Un HTML con el resumen, el gráfico de réplicas de cada medida y, en una optimización, la tabla de candidatos."""
    opt = resultado.get("tipo") == "optimizacion"
    res = resultado["experimento"] if opt else resultado
    titulo = ("Optimizador" if opt else "Experimento") + f": {res['nombre_modelo']}"
    css = (":root{--fondo:#f4f5f3;--tarjeta:#fff;--tinta:#1f1f1e;--tinta2:#5f5e5a;--borde:#dcdedb;--acento:#1b7a5a}"
           "@media (prefers-color-scheme: dark){:root:not([data-theme=\"light\"]){--fondo:#1a1a19;--tarjeta:#262624;--tinta:#f0efec;--tinta2:#c3c2b7;--borde:#3a3a37;--acento:#4fbf94}}"
           ":root[data-theme=\"dark\"]{--fondo:#1a1a19;--tarjeta:#262624;--tinta:#f0efec;--tinta2:#c3c2b7;--borde:#3a3a37;--acento:#4fbf94}"
           "body{margin:0;background:var(--fondo);color:var(--tinta);font-family:system-ui,-apple-system,'Segoe UI',sans-serif}"
           "main{max-width:1100px;margin:0 auto;padding:20px 16px 48px}h1{font-size:1.4rem}h2{font-size:1.1rem;color:var(--acento);margin-top:26px}"
           "section{background:var(--tarjeta);border:1px solid var(--borde);border-radius:10px;padding:12px;margin:10px 0}"
           "svg{display:block;max-width:100%;height:auto;border-radius:6px}.nota{color:var(--tinta2);font-size:0.85rem}"
           ".aviso{background:#fff4dc;color:#5b4300;border-radius:6px;padding:6px 8px;font-size:0.85rem}"
           "table{border-collapse:collapse;width:100%;font-size:0.85rem}th{border-bottom:2px solid var(--acento);padding:4px 6px}"
           "td{border-bottom:1px solid var(--borde);padding:3px 6px;font-variant-numeric:tabular-nums}.desliz{overflow-x:auto}")
    p = ['<!doctype html><html lang="es-CL"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">',
         f"<title>{_h.escape(titulo)}</title><style>{css}</style></head><body><main><h1>{_h.escape(titulo)}</h1>",
         f'<p class="nota">Exportado desde la pestaña Experimentos de pat_sim (PAT 134). Rubro: {_h.escape(str(res["rubro"]))}. '
         f'{res["replicas"]} réplicas por escenario, semillas {_h.escape(", ".join(map(str, res["semillas"])))}. {_h.escape(res["metodo"])} '
         f'{_h.escape(res["nota_calentamiento"])} Método: {_h.escape(res["fuente"])}. Modelo: {_h.escape(res["nota_modelo"])}.</p>']
    p += [f'<p class="aviso">{_h.escape(a)}</p>' for a in (resultado.get("avisos") or [])]
    if opt:
        o = resultado["objetivo"]; mj = resultado["mejor"]
        p.append(f'<h2>Mejor configuración</h2><p class="nota">{_h.escape(resultado["nota"])}</p>')
        if mj:
            p.append("<section><p>" + _h.escape(", ".join(f"{k} = {_cl(v, 3)}" for k, v in mj["params"].items())) +
                     f" con {_h.escape(o['nombre'].lower())} de {_n(mj['objetivo'], 3)} {_h.escape(o['unidad'])} (media de {res['replicas']} réplicas).</p></section>")
        claves = list(resultado["variables"])
        cab = ["Posición", "Candidato"] + claves + [o["nombre"] + " (media)", "Factible", "Restricciones no cumplidas"]
        filas = [[c["posicion"], c["candidato"]] + [_cl(c["params"][k], 3) for k in claves] + [_n(c["objetivo"], 3), "sí" if c["factible"] else "no", "; ".join(c["violaciones"])]
                 for c in resultado["candidatos"]]
        p.append("<h2>Candidatos evaluados</h2><section>" + _tabla_html(cab, filas, ["center", "left"] + ["center"] * len(claves) + ["center", "left", "left"]) + "</section>")
    else:
        vs = list(res["escenarios"][0]["params"]) if res["escenarios"] else []
        filas = [[e["nombre"]] + [_cl(e["params"][k], 3) for k in vs] for e in res["escenarios"]]
        p.append("<h2>Escenarios</h2><section>" + _tabla_html(["Escenario"] + vs, filas, ["left"] + ["center"] * len(vs)) + "</section>")
        p.append("<h2>Resultados por escenario y medida</h2>")
        for m in res["medidas"]:
            d = m.get("decimales", 2)
            filas = [[f["escenario"], _n(f["media"], d), _n(f["ic_inf"], d), _n(f["ic_sup"], d), _n(f["desviacion"], d), _n(f["minimo"], d), _n(f["maximo"], d)]
                     for f in res["resumen"] if f["medida"] == m["clave"]]
            p.append(f'<section><h3>{_h.escape(m["nombre"])} ({_h.escape(m["unidad"])})</h3>' + grafico_replicas_svg(res, m["clave"]) +
                     _tabla_html(["Escenario", "Media", "IC 95 % inferior", "IC 95 % superior", "Desviación", "Mínimo", "Máximo"], filas,
                                 ["left"] + ["center"] * 6) + "</section>")
    p.append("</main></body></html>")
    return "".join(p)
