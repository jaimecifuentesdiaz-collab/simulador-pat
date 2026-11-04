"""Optimización de variables de diseño de la planta (mejora 10, PAT 133, 02-11-2026).

Busca, sobre copias de la planta (datos.bd.copiar_planta), los valores de una o dos variables numéricas que maximizan
un objetivo: el VAN de la cascada con los precios de la sesión (por defecto), el calor recuperado por la cascada, el
objetivo pinch o una función propia. Una variable se busca en una grilla y se refina con sección dorada alrededor del
mejor punto; dos variables, en una grilla. La planta original no se toca.

Variables: "dT_min" o "T_final_residual" (globales de la planta) o (id_equipo, parámetro), por ejemplo ("W2", "T_condensado").
Como en la pestaña Recuperación de calor, al cambiar T_final_residual también se fija T_condensacion de los secadores.
"""
from __future__ import annotations
import math
from ..datos.bd import copiar_planta
from .resumen import resumen_planta
from . import riesgo

GLOBALES = {"dT_min": ("Aproximación mínima de temperatura", "°C", 1.0, 20.0),
            "T_final_residual": ("Temperatura final de los residuales", "°C", 15.0, 45.0)}   # rangos de los deslizadores de p_calor.py
EXCLUIR = ("capacidad", "estado", "costo", "consumo_especifico")
OBJETIVOS = {"van": "VAN de la cascada (MM$)", "van_area": "VAN de la cascada con inversión según el área (MM$)",
             "calor": "Calor recuperado por la cascada (kW)", "pinch": "Objetivo pinch (kW)"}
# Coeficientes globales U (W/m²·K) para el objetivo van_area, valores centrales del Capítulo 4 (calc_cap234.py):
U_CONDENSACION = 840.0   # vapor que condensa contra pulpa de tomate (Sangrame et al., 2000, p. 205)
U_LIQUIDO = 850.0        # líquido contra tomate (Amon et al., 2015, Tabla 1, p. 528)
U_GAS = 50.0             # Supuesto: escape húmedo o aire contra aire de secado; orden de magnitud de los equipos gas a gas,
                         # sin fuente en el informe; se debe reemplazar por el dato del fabricante
PHI = (math.sqrt(5) - 1) / 2


def _ref(v):
    return v if isinstance(v, str) else tuple(v)


def leer(pl, ref):
    ref = _ref(ref)
    if isinstance(ref, str):
        return pl.globales.get(ref, GLOBALES.get(ref, (None, None, None))[2])
    return pl.equipos[ref[0]].v(ref[1])


def fijar(pl, ref, valor):
    """Fija una variable en la planta (global o parámetro de un equipo)."""
    ref = _ref(ref)
    if isinstance(ref, str):
        pl.globales[ref] = float(valor)
        if ref == "T_final_residual":
            for e in pl.equipos.values():
                if "T_condensacion" in e.params:
                    e.set("T_condensacion", float(valor))
    else:
        e = pl.equipos[ref[0]]; actual = e.v(ref[1])
        e.set(ref[1], int(round(valor)) if isinstance(actual, int) and not isinstance(actual, bool) else float(valor))


def nombre(pl, ref) -> str:
    ref = _ref(ref)
    if isinstance(ref, str):
        return GLOBALES.get(ref, (ref,))[0]
    e = pl.equipos[ref[0]]
    return f"{e.id} {e.nombre}: {e.params[ref[1]].nombre}"


def candidatos(pl) -> list:
    """Variables que se pueden optimizar: las dos globales y los parámetros numéricos de los equipos con mínimo y máximo."""
    out = [dict(ref=k, nombre=n, unidad=u, minimo=lo, maximo=hi, valor=float(pl.globales.get(k, lo)), entero=False)
           for k, (n, u, lo, hi) in GLOBALES.items()]
    for e in pl.equipos.values():
        for k, p in e.params.items():
            if k in EXCLUIR or k == "T_condensacion" or isinstance(p.valor, bool) or not isinstance(p.valor, (int, float)):
                continue
            if p.minimo is None or p.maximo is None or float(p.maximo) <= float(p.minimo):
                continue
            out.append(dict(ref=(e.id, k), nombre=f"{e.id} {e.nombre}: {p.nombre}", unidad=p.unidad, minimo=float(p.minimo),
                            maximo=float(p.maximo), valor=float(p.valor), entero=isinstance(p.valor, int)))
    return out


def areas_cascada(r: dict, U: dict | None = None) -> list:
    """Área (m²) de cada etapa de la cascada en serie, en contracorriente: A = Q / (U · LMTD). Una corriente latente cede
    a temperatura constante. U por tipo: condensacion, liquido o gas (gas en los rubros de biomasa)."""
    U = dict(dict(condensacion=U_CONDENSACION, liquido=U_LIQUIDO, gas=U_GAS), **(U or {}))
    biomasa = r.get("combustible") == "biomasa"; areas = []
    for f in r.get("cascada_filas", []):
        Q = float(f["Q_kW"])
        if Q <= 1e-6:
            continue
        s = r["corrientes"][f["corriente"]]
        if s[3] is None:
            Th_in = Th_out = float(s[1]); u = U["gas"] if biomasa else U["condensacion"]
        else:
            Th_in = float(s[1]); Th_out = Th_in - Q / float(s[3]); u = U["gas"] if biomasa else U["liquido"]
        d1, d2 = Th_in - float(f["T_sale"]), Th_out - float(f["T_entra"])
        if d1 <= 0 or d2 <= 0:
            raise ValueError(f"La etapa {f['corriente']} cruza temperaturas")
        L = d1 if abs(d1 - d2) < 1e-9 else (d1 - d2) / math.log(d1 / d2)
        areas.append(Q * 1000 / (u * L))
    return areas


def valor_objetivo(r: dict, objetivo, pl=None, E: dict | None = None):
    """Valor del objetivo para un resumen de planta. None si no se puede calcular."""
    if callable(objetivo):
        return objetivo(pl, r)
    if r.get("sin_sumidero"):
        return None
    if objetivo == "calor":
        return float(r["cascada"])
    if objetivo == "pinch":
        return float(r["pinch"])
    if objetivo in ("van", "van_area"):
        if E is None:
            raise ValueError("El objetivo VAN necesita la economía de la sesión (E)")
        if "gas_desplazado_cascada" in r:
            comb, des, precio = "gas", r["gas_desplazado_cascada"]["MMBtu"], E["precio_gas"]
        elif "biomasa_cascada" in r:
            comb, des, precio = "biomasa", r["biomasa_cascada"]["m3"], E.get("precio_biomasa", 6750.0)
        else:
            return None
        inv = E["inversion"]
        if objetivo == "van_area":     # inversión de los intercambiadores de la cascada (costos.py, Capítulo 4)
            from .costos import inversion_hx_mmclp
            inv = inversion_hx_mmclp(areas_cascada(r), dolar=E["dolar"])
        p = dict(precio=precio, dolar=E["dolar"], inversion=inv, costo_anual=E["costo_anual"], tasa=E["tasa"],
                 anios=E["anios"], fraccion=1.0)
        return float(riesgo.van_cascada(p, float(des), comb))
    raise ValueError(f"Objetivo desconocido: {objetivo}")


# ---------------------------------------------------------------- búsqueda pura (sirve para cualquier función)
def seccion_dorada(f, a: float, b: float, tol: float = 1e-4, max_iter: int = 60):
    """Máximo de f en [a, b] por sección dorada. f puede devolver None (punto que no resuelve: se trata como −∞)."""
    g = lambda x: (lambda y: -math.inf if y is None else y)(f(x))
    c = b - PHI * (b - a); d = a + PHI * (b - a); fc, fd = g(c), g(d); it = 0
    while abs(b - a) > tol and it < max_iter:
        if fc >= fd:
            b, d, fd = d, c, fc; c = b - PHI * (b - a); fc = g(c)
        else:
            a, c, fc = c, d, fd; d = a + PHI * (b - a); fd = g(d)
        it += 1
    return (c, fc) if fc >= fd else (d, fd)


def _malla(lo, hi, n, entero):
    if entero:
        lo_i, hi_i = int(math.ceil(lo)), int(math.floor(hi)); paso = max(1, int(math.ceil((hi_i - lo_i + 1) / n)))
        xs = list(range(lo_i, hi_i + 1, paso))
        return xs if xs[-1] == hi_i else xs + [hi_i]
    return [lo + (hi - lo) * i / (n - 1) for i in range(n)] if n > 1 else [lo]


def buscar(f, rangos: list, n_grilla: int | None = None, refinar: bool = True, enteros: list | None = None, tol_rel: float = 1e-3) -> dict:
    """Maximiza f(x) (una variable) o f(x, y) (dos) en rangos [(lo, hi), ...]: grilla y, en una variable, sección dorada en el
    tramo de la grilla alrededor del mejor punto. Devuelve optimo (lista de valores), valor, curva y fallidos."""
    enteros = enteros or [False] * len(rangos); cache = {}; fallidos = []

    def ev(*x):
        k = tuple(round(v, 10) for v in x)
        if k not in cache:
            try:
                cache[k] = f(*x)
            except Exception as e:                       # punto que no resuelve
                cache[k] = None; fallidos.append((x, str(e)))
            if cache[k] is not None and (isinstance(cache[k], float) and math.isnan(cache[k])):
                cache[k] = None
        return cache[k]

    if len(rangos) == 1:
        n = n_grilla or 21; (lo, hi), ent = rangos[0], enteros[0]
        xs = _malla(lo, hi, n, ent); curva = [dict(x=x, valor=ev(x)) for x in xs]
        ok = [i for i, c in enumerate(curva) if c["valor"] is not None]
        if not ok:
            return dict(optimo=None, valor=None, curva=curva, fallidos=fallidos)
        i = max(ok, key=lambda j: curva[j]["valor"]); xb, vb = curva[i]["x"], curva[i]["valor"]
        if refinar and not ent and len(xs) > 1:
            a, b = xs[max(i - 1, 0)], xs[min(i + 1, len(xs) - 1)]
            xr, vr = seccion_dorada(lambda x: ev(x), a, b, tol=tol_rel * (hi - lo))
            if vr is not None and vr > vb:
                xb, vb = xr, vr
                curva = sorted(curva + [dict(x=xr, valor=vr)], key=lambda c: c["x"])
        return dict(optimo=[xb], valor=vb, curva=curva, fallidos=fallidos)
    if len(rangos) == 2:
        n = n_grilla or 11
        xs = _malla(*rangos[0], n, enteros[0]); ys = _malla(*rangos[1], n, enteros[1])
        curva = [dict(x=x, y=y, valor=ev(x, y)) for x in xs for y in ys]
        ok = [c for c in curva if c["valor"] is not None]
        if not ok:
            return dict(optimo=None, valor=None, curva=curva, fallidos=fallidos)
        b = max(ok, key=lambda c: c["valor"])
        return dict(optimo=[b["x"], b["y"]], valor=b["valor"], curva=curva, fallidos=fallidos)
    raise ValueError("Se optimizan una o dos variables")


# ---------------------------------------------------------------- sobre la planta
def optimizar(pl, variables: list, objetivo="van", E: dict | None = None, cop: float = 2.0, n_grilla: int | None = None,
              refinar: bool = True) -> dict:
    """variables: lista de una o dos (ref, mínimo, máximo), con ref = "dT_min", "T_final_residual" o (id_equipo, parámetro).
    objetivo: "van" (con E, la economía de la sesión y su inversión fija), "van_area" (la inversión sale del área de la
    cascada con U medio y la correlación de costos.py), "calor", "pinch" o una función f(planta, resumen) -> número.
    Devuelve el óptimo, el valor base, la curva evaluada y los avisos. No modifica pl."""
    if not 1 <= len(variables) <= 2:
        raise ValueError("Se optimizan una o dos variables")
    refs = [_ref(v[0]) for v in variables]; rangos = [(float(v[1]), float(v[2])) for v in variables]
    for (lo, hi) in rangos:
        if hi <= lo:
            raise ValueError("El máximo de cada variable debe ser mayor que su mínimo")
    enteros = []
    for ref in refs:
        x = leer(pl, ref); enteros.append(isinstance(x, int) and not isinstance(x, bool) and not isinstance(ref, str))
    avisos = []

    def f(*x):
        p2 = copiar_planta(pl, resolver=False)
        for ref, v in zip(refs, x):
            fijar(p2, ref, v)
        p2.resolver()
        r = resumen_planta(p2, cop=cop)
        return valor_objetivo(r, objetivo, p2, E)

    base_x = [float(leer(pl, ref)) for ref in refs]
    try:
        base_v = f(*base_x)
    except Exception as e:
        base_v = None; avisos.append(f"La planta con sus valores actuales no resuelve: {e}")
    res = buscar(f, rangos, n_grilla=n_grilla, refinar=refinar, enteros=enteros)
    for x, msg in res["fallidos"]:
        avisos.append("No resuelve con " + ", ".join(f"{nombre(pl, r)} = {v:.4g}".replace(".", ",") for r, v in zip(refs, x)) + f": {msg}")
    sin_valor = sum(1 for c in res["curva"] if c["valor"] is None) - len(res["fallidos"])
    if sin_valor > 0:
        avisos.append(f"{sin_valor} puntos resuelven pero no tienen objetivo (sin sumidero o sin caldera con horas declaradas).")
    if res["optimo"] is None:
        avisos.append("Ningún punto de la grilla entregó un valor del objetivo.")
    else:
        for ref, (lo, hi), x in zip(refs, rangos, res["optimo"]):
            if abs(x - lo) < 1e-6 * (hi - lo) or abs(x - hi) < 1e-6 * (hi - lo):
                avisos.append(f"El óptimo de {nombre(pl, ref)} queda en el borde del rango: el máximo puede estar fuera de él.")
    nom = OBJETIVOS.get(objetivo, "Objetivo") if not callable(objetivo) else "Objetivo"
    return dict(variables=[dict(ref=r, nombre=nombre(pl, r), minimo=lo, maximo=hi) for r, (lo, hi) in zip(refs, rangos)],
                objetivo=nom, optimo=None if res["optimo"] is None else dict(zip([str(r) for r in refs], res["optimo"])),
                optimo_lista=res["optimo"], valor_optimo=res["valor"], base_lista=base_x, valor_base=base_v,
                mejora=None if res["valor"] is None or base_v is None else res["valor"] - base_v,
                curva=res["curva"], evaluaciones=len(res["curva"]), avisos=avisos)
