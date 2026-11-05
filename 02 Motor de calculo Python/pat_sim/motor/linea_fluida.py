"""Simulación de la línea por *ticks*, como la Fluid Library de FlexSim (PAT 134, 02-11-2026).

Traslado a pat_sim de lo que documenta el manual público de FlexSim (Fluid Library Concepts, Ticker y MTBF/MTTR), en palabras
propias y sin descompilar el programa:
- La materia avanza en intervalos fijos (*ticks*). En cada *tick* cada equipo procesa
  mín(tasa máxima × dt, lo disponible en su tanque de entrada, espacio libre en su tanque de salida convertido a su carga).
  La tasa máxima es la capacidad efectiva del equipo (capacidad × estado, Planta.capacidad_efectiva) en t/h de su carga.
- Entre equipos consecutivos hay tanques pulmón (capacidad por defecto como Supuesto; el usuario la cambia o la anula con
  `tanques`; un tanque anulado es una conexión directa: lo que sale de un equipo entra al siguiente en el mismo *tick*).
- La materia pasa de un equipo al siguiente con la razón de masas carga_siguiente/carga_actual de la planta resuelta (la
  pasta se concentra y la biomasa se seca); la diferencia sale del proceso en ese equipo (agua evaporada, descarte) y se
  cuenta en el balance, que cierra: entrada = producto + salidas del proceso + inventario final − inventario inicial.
- Fallas MTBF/MTTR por equipo con distribuciones de motor/ajuste.py: el tiempo hasta la falla se cuenta desde que el equipo
  volvió a operar, con base «operando» (el reloj de falla avanza solo mientras el equipo procesa, tiempo ocupado) o «todo»
  (tiempo calendario), las dos formas de contar el tiempo hasta la falla que describe Law (2015, cap. 14) y que ofrece FlexSim.
- Las barras del programa de temporada que no son producción detienen toda la línea, como las Time Tables de FlexSim.
- Números aleatorios reproducibles: una corriente random.Random por equipo (semilla e índice del equipo), como recomienda
  FlexSim con corrientes separadas.
Referencias: Law, A. M. (2015). Simulation modeling and analysis (5.ª ed.). McGraw-Hill Education. Nakajima (OEE) a través de
calculadoras.oee. Las cifras sin fuente segura van en SUPUESTOS con su justificación.
"""
from __future__ import annotations
import math
import random
from . import ajuste as AJ
from . import calculadoras as K
from . import lienzo as LZ
from . import operacion as OP
from .operacion import Supuesto, S as S_OP

ESTADOS = ["operando", "bloqueado", "esperando", "en_falla", "en_mantenimiento", "detenido_programado"]
NOMBRE_ESTADO = dict(operando="Operando", bloqueado="Bloqueado", esperando="Esperando", en_falla="En falla",
                     en_mantenimiento="En mantenimiento", detenido_programado="Detenido programado")
COLOR_ESTADO = dict(operando="#1baf7a", bloqueado="#eb6834", esperando="#2a78d6", en_falla="#e34948", en_mantenimiento="#6250d6",
                    detenido_programado="#a3a29c")   # los mismos colores de los estados de motor/tablero.py
BASES = ("operando", "todo")
_SD = "sin dato de la planta ni fuente segura"

# categorías de equipo para las fallas por defecto (Supuesto PAT 134)
CATEGORIAS = {
    "mecanico": ("trituradora", "refinadora", "molino", "pelletizadora", "astilladora", "sierra"),
    "termico": ("hot_break", "evaporador", "esterilizador", "enfriamiento", "secador", "enfriador"),
}
FALLAS_TIPO = {   # (MTBF h, MTTR h)
    "mecanico": (80.0, 1.5),
    "termico": (160.0, 2.0),
    "manejo": (120.0, 1.0),
}
NOMBRE_CATEGORIA = dict(mecanico="Equipo mecánico (corte, molienda, refinado, prensado)",
                        termico="Equipo térmico (calentamiento, evaporación, esterilización, secado, enfriamiento)",
                        manejo="Manejo y envasado (lavado, cribado, llenado, despacho)")
_JF = ("Orden de magnitud del simulador del profesor: una falla cada seis turnos que deja cerca de un tercio del turno "
       "(p_falla = 0,16 y disp_falla = 0,36 de operacion.py), es decir, cerca de 10 % de la capacidad de la línea, repartido "
       "entre los equipos según su tipo; los equipos mecánicos fallan más seguido y los térmicos tardan más en repararse. "
       "Exponencial: tasa de falla constante, la elección usual cuando no hay datos medidos; " + _SD + ". Se reemplaza en "
       "la pestaña Línea o con la distribución ajustada en Datos de entrada")
SUPUESTOS = {s.clave: s for s in [
    Supuesto("tanque_min", "Capacidad por defecto de cada tanque pulmón", 30.0, "min de la carga del equipo siguiente",
             "Pulmón corto entre equipos consecutivos para que una detención breve no pare de inmediato toda la línea; " + _SD),
    Supuesto("nivel_inicial", "Nivel inicial de los tanques", 0.0, "t", "La línea parte vacía, como al inicio de la temporada"),
    Supuesto("mtbf_mecanico", "MTBF de un equipo mecánico", FALLAS_TIPO["mecanico"][0], "h", _JF),
    Supuesto("mttr_mecanico", "MTTR de un equipo mecánico", FALLAS_TIPO["mecanico"][1], "h", _JF),
    Supuesto("mtbf_termico", "MTBF de un equipo térmico", FALLAS_TIPO["termico"][0], "h", _JF),
    Supuesto("mttr_termico", "MTTR de un equipo térmico", FALLAS_TIPO["termico"][1], "h", _JF),
    Supuesto("mtbf_manejo", "MTBF de un equipo de manejo o envasado", FALLAS_TIPO["manejo"][0], "h", _JF),
    Supuesto("mttr_manejo", "MTTR de un equipo de manejo o envasado", FALLAS_TIPO["manejo"][1], "h", _JF),
    Supuesto("sin_capacidad", "Equipo sin capacidad declarada (acopio, despacho)", 0.0, "—",
             "Se simula sin límite de tasa y sin fallas: es una cancha o un despacho que no frena la línea; si se le declara "
             "capacidad en Propiedades, pasa a tener tasa máxima y fallas de su tipo"),
    Supuesto("estado_ref", "Referencia para esperando y bloqueado", 0.0, "—",
             "PAT 134: un equipo está esperando (hambre) o bloqueado cuando procesa menos que mín(tasa máxima, su carga de diseño "
             "escalada por la alimentación) por falta de entrada o de espacio aguas abajo; si procesa eso o más, opera. Así un "
             "equipo con holgura que recibe su carga de diseño cuenta como operando y no como esperando"),
    Supuesto("redondeo", "Inicio y duración de fallas y mantenimientos", 0.0, "ticks",
             "Las fallas parten al inicio del primer tick en que el reloj de falla alcanza el tiempo sorteado y la reparación se "
             "redondea al tick más cercano (mínimo un tick); con ticks de minutos el error es despreciable frente a MTTR de horas"),
    Supuesto("calidad", "Calidad en el OEE", 1.0, "fracción",
             "La simulación de la línea no muestrea calidad: todo lo producido se cuenta como bueno; la calidad está en Operación y Calidad SPC"),
    Supuesto("oee_ideal", "Tasa ideal del OEE", 0.0, "t/h de producto",
             "PAT 134: la producción planificada de la planta (operacion.linea(pl)[\"plan\"]), la misma tasa ideal que usan las "
             "pestañas Temporada y Tableros, para que el OEE de las tres pestañas sea comparable (Nakajima, 1988). Disponibilidad = "
             "horas planificadas en que la salida de la línea produjo / horas planificadas. Como dato adicional, oee_critico usa la "
             "tasa máxima de la línea (capacidad efectiva del recurso crítico referida al producto): con holgura de capacidad su "
             "rendimiento baja de 100 % aunque no haya fallas"),
    Supuesto("alimentacion_parada", "Alimentación durante las paradas programadas", 0.0, "t/h",
             "En las paradas del programa no se alimenta la línea, como la recepción que solo atiende en horas de producción; "
             "con la línea programada para producir, lo que el primer equipo no alcanza a recibir se informa como alimentación rechazada"),
]}


def _cl(v: float, d: int = 1) -> str:
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def categoria(tipo: str) -> str:
    for k, claves in CATEGORIAS.items():
        if any(c in tipo for c in claves):
            return k
    return "manejo"


def fallas_defecto(eq) -> dict | None:
    """Fallas por defecto de un equipo según su tipo (Supuesto PAT 134). None si el equipo no tiene capacidad declarada."""
    if eq.capacidad_efectiva() is None:
        return None
    cat = categoria(eq.tipo)
    # PAT 135, T14: si la selección de equipos comerciales dejó MTBF y MTTR en el equipo, se usan esos (con n unidades en
    # paralelo, los de una etapa equivalente que entrega la misma capacidad esperada; motor/seleccion.fallas_equivalentes)
    from . import seleccion as SEL
    eqv = SEL.fallas_equivalentes(eq)
    if eqv is not None:
        mtbf, mttr, nota = eqv
        if mttr <= 0:
            return None                       # reparación instantánea: el equipo elegido no detiene la línea
        return dict(mtbf=AJ.crear("exponencial", nota=nota, escala=mtbf), mttr=AJ.crear("exponencial", nota=nota, escala=mttr),
                    base="operando", origen="Selección de equipos", categoria=cat)
    mtbf, mttr = FALLAS_TIPO[cat]
    nota = f"Supuesto PAT 134 ({NOMBRE_CATEGORIA[cat].lower()})"
    return dict(mtbf=AJ.crear("exponencial", nota=nota, escala=mtbf), mttr=AJ.crear("exponencial", nota=nota, escala=mttr),
                base="operando", origen="Supuesto", categoria=cat)


# ----------------------------------------------------------------------------------------------- línea principal
def _sol(pl):
    if pl.resuelta and getattr(pl, "salidas", None):
        return pl
    sol, motivo = LZ.resolver_parcial(pl)
    if motivo is not None or sol is None:
        raise ValueError(f"La planta no está resuelta: {motivo or 'sin alimentación'}. Revise la pestaña Diseño.")
    return sol


def _excluido(eq) -> bool:
    return eq.tipo.startswith(("caldera", "generador", "alimentacion"))


def linea_principal(pl, sol=None) -> tuple[list, list]:
    """Equipos de proceso de la línea principal en orden (sin alimentación, calderas, generadores ni servicios).
    Parte de la alimentación de mayor carga y sigue, en cada equipo, la corriente de proceso de mayor flujo."""
    sol = sol or _sol(pl); avisos = []
    def carga(k):
        r = sol.equipos[k].resultado
        return _num(r.detalle.get("carga_t_h")) if r is not None else None
    proc = [c for c in sol.conexiones if not sol.es_servicio(c)]
    fuentes = [k for k, e in sol.equipos.items() if e.tipo.startswith("alimentacion") and e.resultado is not None]
    if fuentes:
        actual = max(fuentes, key=lambda k: carga(k) or 0.0); ids = []
    else:
        orden = [k for k in sol.orden() if not _excluido(sol.equipos[k]) and carga(k)]
        if not orden:
            raise ValueError("La planta no tiene equipos de proceso con carga.")
        actual = orden[0]; ids = [actual]
    visto = {actual}
    while True:
        cands = []
        for c in proc:
            if c.origen != actual or c.destino in visto:
                continue
            e = sol.equipos[c.destino]
            if e.tipo.startswith(("caldera", "generador")):
                continue
            s = sol.salidas.get((c.origen, c.puerto_origen))
            cands.append(((s.m if s is not None else 0.0) * c.reparto, c.destino))
        if not cands:
            break
        cands.sort(key=lambda x: -x[0]); sig = cands[0][1]
        if len(cands) > 1:
            avisos.append(f"{actual}: la línea sigue por {sig} (mayor flujo); las otras salidas de proceso no se simulan.")
        if not carga(sig):
            avisos.append(f"{sig} no tiene carga en la planta resuelta: la línea simulada termina en {actual}.")
            break
        ids.append(sig); visto.add(sig); actual = sig
    if not ids:
        raise ValueError("La planta no tiene equipos de proceso después de la alimentación.")
    return ids, avisos


def _producto_final(sol, k) -> float:
    eq = sol.equipos[k]; tot = 0.0
    for p in eq.salidas:
        if p.tipo in ("producto", "biomasa") and not any(c.origen == k and c.puerto_origen == p.nombre for c in sol.conexiones):
            s = sol.salidas.get((k, p.nombre))
            if s is not None:
                tot += float(s.m) / 1000
    return float(tot)


def _barras(programa) -> list:
    if programa is None:
        return []
    barras = programa.get("barras", []) if isinstance(programa, dict) else list(programa)
    out = []
    for b in barras:
        if b.get("tipo") == "produccion":
            continue
        est = "en_mantenimiento" if "mantenimiento" in (str(b.get("tipo", "")) + " " + str(b.get("actividad", ""))).lower() else "detenido_programado"
        out.append((float(b["inicio_h"]), float(b["fin_h"]), est))
    return sorted(out)


def _cfg_fallas(fallas, eqs, avisos) -> dict:
    """Configuración de fallas por equipo: None (sin dato) o dict(mtbf, mttr, base, primera, mantenimiento, origen)."""
    out = {}
    sin = fallas is False or (isinstance(fallas, str) and fallas.lower() in ("ninguna", "sin fallas"))
    for e in eqs:
        if sin:
            out[e.id] = None; continue
        d = fallas_defecto(e)
        if isinstance(fallas, dict) and e.id in fallas:
            u = fallas[e.id]
            if not u:
                out[e.id] = None; continue
            d = dict(d or dict(base="operando", categoria=categoria(e.tipo)))
            for k in ("mtbf", "mttr", "primera", "base", "mantenimiento"):
                if u.get(k) is not None:
                    d[k] = u[k]
            d["origen"] = "Usuario"
            if "mtbf" not in d or "mttr" not in d:
                cat = categoria(e.tipo); m1, m2 = FALLAS_TIPO[cat]
                d.setdefault("mtbf", AJ.crear("exponencial", nota="Supuesto PAT 134", escala=m1))
                d.setdefault("mttr", AJ.crear("exponencial", nota="Supuesto PAT 134", escala=m2))
        if d is not None:
            if d.get("base", "operando") not in BASES:
                raise ValueError(f"{e.id}: la base de las fallas debe ser «operando» o «todo».")
            if AJ.media(d["mtbf"]) <= 0 or AJ.media(d["mttr"]) < 0:
                raise ValueError(f"{e.id}: MTBF debe ser positivo y MTTR no negativo.")
        out[e.id] = d
    return out


def _cfg_tanques(tanques, ids, cargas, avisos) -> list:
    out = []
    for i in range(len(ids) - 1):
        a, b = ids[i], ids[i + 1]; tid = f"{a}-{b}"
        cap = SUPUESTOS["tanque_min"].valor / 60.0 * cargas[i + 1]; ini = SUPUESTOS["nivel_inicial"].valor; origen = "Supuesto"
        u = None
        if isinstance(tanques, dict):
            u = tanques.get(tid, tanques.get(a, tanques.get((a, b))))
        if u is not None or (isinstance(tanques, dict) and (tid in tanques or a in tanques)):
            origen = "Usuario"
            if isinstance(u, dict):
                cap = u.get("capacidad_t", cap); ini = float(u.get("nivel_inicial_t", ini) or 0.0)
            else:
                cap = u
        cap = _num(cap)
        if cap is None or cap <= 0:
            cap = 0.0
            if ini:
                avisos.append(f"El tanque {tid} está anulado: se ignora su nivel inicial."); ini = 0.0
        if cap > 0 and ini > cap:
            avisos.append(f"El nivel inicial del tanque {tid} supera su capacidad: se deja lleno."); ini = cap
        out.append(dict(id=tid, antes=a, despues=b, capacidad_t=cap, nivel_inicial_t=max(0.0, ini), anulado=cap <= 0, origen=origen))
    return out


# ----------------------------------------------------------------------------------------------- simulación
def simular_linea(pl, horas=72.0, tick_min=1.0, semilla=0, fallas=None, tanques=None, programa=None, muestra_min=10.0,
                  alimentacion_t_h=None) -> dict:
    """Simula la línea principal de la planta por *ticks* de tick_min minutos durante `horas` h.

    fallas: None = valores por tipo de equipo (Supuesto); dict {equipo_id: dict(mtbf=dist, mttr=dist, base="operando"|"todo",
    primera=dist opcional, mantenimiento=dict(cada_h, duracion_h, inicio_h) opcional)} con dist de ajuste.crear; un equipo con
    valor None o {} no falla; los que no están usan el valor por defecto. False o "ninguna": sin fallas en toda la línea.
    tanques: {tanque_id ("A-B") o id del equipo de antes: capacidad_t o dict(capacidad_t, nivel_inicial_t)}; capacidad 0 o
    None anula el tanque (conexión directa). programa: dict de temporada.programa_temporada o lista de sus barras (horas
    desde el inicio de la simulación). alimentacion_t_h: alimentación al primer equipo (por defecto, su carga de diseño)."""
    horas = float(horas); tick_min = float(tick_min); muestra_min = float(muestra_min)
    if horas <= 0 or tick_min <= 0:
        raise ValueError("Las horas y el tick deben ser positivos.")
    dt = tick_min / 60.0; N = int(round(horas / dt))
    if N < 1:
        raise ValueError("El horizonte debe tener al menos un tick.")
    if N > 2_000_000:
        raise ValueError("Demasiados ticks: aumente el tick o acorte el horizonte.")
    horas = N * dt
    sol = _sol(pl)
    ids, avisos = linea_principal(pl, sol)
    eqs = [sol.equipos[k] for k in ids]; n = len(ids)
    cargas = [float(e.resultado.detalle.get("carga_t_h")) for e in eqs]
    tasas_max = [None if e.capacidad_efectiva() is None else float(e.capacidad_efectiva()) for e in eqs]
    for e, c in zip(eqs, tasas_max):
        if c is None:
            avisos.append(f"{e.id} ({e.nombre}) no tiene capacidad declarada: se simula sin límite de tasa y sin fallas por defecto.")
    razon = [cargas[i + 1] / cargas[i] for i in range(n - 1)]
    pf = _producto_final(sol, ids[-1])
    razon.append(pf / cargas[-1] if pf > 0 else 1.0)
    if pf <= 0:
        avisos.append(f"{ids[-1]} no entrega producto final en la planta resuelta: se cuenta como producto todo lo que procesa.")
    alim = cargas[0] if alimentacion_t_h is None else max(0.0, float(alimentacion_t_h))
    f_alim = alim / cargas[0] if cargas[0] else 0.0
    tr = LZ.restricciones(pl, sol, f_alim)
    tasa_linea = None
    # tasa de la línea simulada sin fallas: la menor tasa máxima referida al producto, o la alimentación
    lim = alim
    acum = 1.0
    for i in range(n):
        if tasas_max[i] is not None:
            lim = min(lim, tasas_max[i] / acum)
        acum *= razon[i] if i < n - 1 else 1.0
    prod_por_alim = 1.0
    for r in razon:
        prod_por_alim *= r
    tasa_linea = float(lim * prod_por_alim)
    caps = [tasas_max[i] / (cargas[i] / cargas[0]) for i in range(n) if tasas_max[i] is not None]
    tasa_max_linea = float(min(caps) * prod_por_alim) if caps else tasa_linea     # recurso crítico referido al producto
    if tr and tr.get("produccion_real") and abs(tr["produccion_real"] - tasa_linea) > 1e-6 * max(1.0, tasa_linea):
        avisos.append(f"La tasa de la línea simulada ({_cl(tasa_linea, 2)} t/h) difiere de la teoría de restricciones de la planta "
                      f"({_cl(tr['produccion_real'], 2)} t/h): la planta tiene ramas que esta simulación de una sola línea no sigue.")
    # referencia de estado: mín(tasa máxima, carga de diseño × factor de alimentación) × dt
    ref = [min(tasas_max[i] if tasas_max[i] is not None else math.inf, cargas[i] * f_alim) * dt for i in range(n)]
    cap_tick = [(tasas_max[i] * dt) if tasas_max[i] is not None else math.inf for i in range(n)]
    cfg = _cfg_fallas(fallas, eqs, avisos)
    tks = _cfg_tanques(tanques, ids, cargas, avisos)
    capT = [t["capacidad_t"] for t in tks]; directo = [t["anulado"] for t in tks]
    nivel = [t["nivel_inicial_t"] for t in tks]
    inv_ini = sum(nivel)
    paradas = _barras(programa)

    # estado por tick de las paradas programadas (punto medio del tick)
    parada_tick = [None] * N
    for a, b, est in paradas:
        k0 = max(0, int(math.ceil(a / dt - 0.5 - 1e-9))); k1 = min(N, int(math.ceil(b / dt - 0.5 - 1e-9)))
        for k in range(k0, k1):
            if parada_tick[k] is None:
                parada_tick[k] = est

    # fallas: una corriente por equipo
    rngs = [random.Random(f"linea:{semilla}:{i}") for i in range(n)]
    reloj = [0.0] * n; ttf = [math.inf] * n; fin_rep = [-1] * n; nfallas = [0] * n
    fin_mant = [-1] * n; prox_mant = [math.inf] * n
    for i, e in enumerate(eqs):
        c = cfg[e.id]
        if c is None:
            continue
        ttf[i] = max(0.0, AJ.muestrear(c.get("primera") or c["mtbf"], rngs[i]))
        m = c.get("mantenimiento")
        if m and _num(m.get("cada_h")) and _num(m.get("duracion_h")):
            prox_mant[i] = float(m.get("inicio_h", m["cada_h"]))

    def ticks_de(h):
        return max(1, int(round(h / dt)))

    estados = [[None] * N for _ in range(n)]
    proc = [0.0] * n; horas_est = [{s: 0.0 for s in ESTADOS} for _ in range(n)]
    entrada = rechazo = producto = mermas = 0.0
    paso_m = max(1, int(round(muestra_min / tick_min)))
    tiempo_h = [0.0]; niveles = {t["id"]: [nivel[j]] for j, t in enumerate(tks)}; prod_acum = [0.0]
    tasas = {k: [0.0] for k in ids}; ventana = [0.0] * n
    salida_operada = 0     # ticks planificados en que la salida de la línea produjo
    planificados = 0
    INF = math.inf

    for k in range(N):
        t = k * dt; pk = parada_tick[k]
        disp = [True] * n; est_fijo = [None] * n
        for i in range(n):
            c = cfg[ids[i]]
            if c is None:
                if pk is not None:
                    disp[i] = False; est_fijo[i] = pk
                continue
            if fin_rep[i] >= 0 and k >= fin_rep[i]:          # volvió a operar: el reloj de falla parte de cero
                fin_rep[i] = -1; reloj[i] = 0.0; ttf[i] = max(0.0, AJ.muestrear(c["mtbf"], rngs[i]))
            if fin_mant[i] >= 0 and k >= fin_mant[i]:
                fin_mant[i] = -1
            if fin_rep[i] < 0 and reloj[i] >= ttf[i] and (c.get("base", "operando") == "todo" or pk is None) and fin_mant[i] < 0:
                d = max(0.0, AJ.muestrear(c["mttr"], rngs[i]))
                fin_rep[i] = k + ticks_de(d); nfallas[i] += 1
            if fin_rep[i] < 0 and fin_mant[i] < 0 and t + 1e-9 >= prox_mant[i]:
                m = c["mantenimiento"]; fin_mant[i] = k + ticks_de(float(m["duracion_h"])); prox_mant[i] += float(m["cada_h"])
            if fin_rep[i] >= 0:
                disp[i] = False; est_fijo[i] = "en_falla"
            elif fin_mant[i] >= 0:
                disp[i] = False; est_fijo[i] = "en_mantenimiento"
            elif pk is not None:
                disp[i] = False; est_fijo[i] = pk
        feed = alim * dt if pk is None else 0.0
        q = [0.0] * n; cap_left = [cap_tick[i] if disp[i] else 0.0 for i in range(n)]

        def espacio(j):
            """Lo que el equipo j aún puede procesar por espacio aguas abajo (t de su carga)."""
            if j == n - 1:
                return INF
            if directo[j]:
                return min(cap_left[j + 1], espacio(j + 1)) / razon[j]
            return max(0.0, capT[j] - nivel[j]) / razon[j]

        def empujar(j, x):
            """El equipo j procesa x (t de su carga) y entrega aguas abajo."""
            q[j] += x; cap_left[j] -= x
            if j == n - 1:
                return
            y = x * razon[j]
            if directo[j]:
                empujar(j + 1, y)
            else:
                nivel[j] += y

        for i in range(n - 1, -1, -1):
            if not disp[i]:
                continue
            if i == 0:
                disponible = feed
            elif directo[i - 1]:
                continue                  # recibe por conexión directa cuando procesa el equipo de antes
            else:
                disponible = nivel[i - 1]
            x = min(cap_left[i], disponible, espacio(i))
            if x > 0:
                if i > 0:
                    nivel[i - 1] -= x
                    if nivel[i - 1] < 0:
                        nivel[i - 1] = 0.0 if nivel[i - 1] > -1e-9 else nivel[i - 1]
                empujar(i, x)
        entrada += q[0]; rechazo += feed - q[0]
        for i in range(n):
            mermas += q[i] * (1 - razon[i])
        producto += q[n - 1] * razon[n - 1]
        # estados del tick
        for i in range(n):
            if est_fijo[i] is not None:
                s = est_fijo[i]
            else:
                falta = ref[i] - q[i]
                if falta > 1e-6 * max(ref[i], 1e-12) + 1e-12:
                    s = "bloqueado" if espacio(i) <= 1e-9 * max(ref[i], 1e-12) else "esperando"
                else:
                    s = "operando"
            estados[i][k] = s; horas_est[i][s] += dt; proc[i] += q[i]; ventana[i] += q[i]
            c = cfg[ids[i]]
            if c is not None and fin_rep[i] < 0 and fin_mant[i] < 0:
                if c.get("base", "operando") == "todo" or q[i] > 0:
                    reloj[i] += dt
        if pk is None:
            planificados += 1
            if q[n - 1] > 0:
                salida_operada += 1
        if (k + 1) % paso_m == 0 or k == N - 1:
            nt = (k + 1) % paso_m or paso_m
            tiempo_h.append((k + 1) * dt)
            for j, tk in enumerate(tks):
                niveles[tk["id"]].append(nivel[j])
            prod_acum.append(producto)
            for i in range(n):
                tasas[ids[i]].append(ventana[i] / (nt * dt)); ventana[i] = 0.0

    # tramos comprimidos
    tramos = []
    for i in range(n):
        ini = 0
        for k in range(1, N + 1):
            if k == N or estados[i][k] != estados[i][ini]:
                tramos.append(dict(equipo=ids[i], estado=estados[i][ini], inicio_h=ini * dt, fin_h=k * dt)); ini = k
    inv_fin = sum(nivel)
    bal = dict(entrada_t=entrada, producto_t=producto, salidas_proceso_t=mermas, inventario_inicial_t=inv_ini, inventario_final_t=inv_fin,
               alimentacion_rechazada_t=rechazo, alimentacion_ofrecida_t=entrada + rechazo)
    bal["cierre_t"] = entrada + inv_ini - producto - mermas - inv_fin
    bal = {kk: float(v) for kk, v in bal.items()}
    bal["cierra"] = bool(abs(bal["cierre_t"]) <= 1e-6 * max(1.0, entrada + inv_ini))
    if not bal["cierra"]:
        avisos.append(f"El balance de masa no cierra: diferencia de {_cl(bal['cierre_t'], 6)} t.")
    if rechazo > 1e-6 * max(1.0, entrada + rechazo):
        avisos.append(f"El primer equipo no alcanzó a recibir {_cl(rechazo, 1)} t de la alimentación ofrecida (fuente bloqueada).")

    h_plan = planificados * dt
    por_equipo = {}
    for i, k in enumerate(ids):
        he = horas_est[i]; abajo = he["en_falla"] + he["en_mantenimiento"]
        abajo_plan = sum(dt for kk in range(N) if parada_tick[kk] is None and estados[i][kk] in ("en_falla", "en_mantenimiento"))
        c = cfg[k]
        por_equipo[k] = dict(horas_por_estado=he, utilizacion=(proc[i] / (tasas_max[i] * horas)) if tasas_max[i] else None,
                             fallas=nfallas[i], disponibilidad=(h_plan - abajo_plan) / h_plan if h_plan > 0 else None,
                             procesado_t=proc[i], tasa_media_t_h=proc[i] / horas, horas_abajo=abajo,
                             mtbf_h=AJ.media(c["mtbf"]) if c else None, mttr_h=AJ.media(c["mttr"]) if c else None,
                             base=c.get("base", "operando") if c else None,
                             disponibilidad_teorica=(AJ.media(c["mtbf"]) / (AJ.media(c["mtbf"]) + AJ.media(c["mttr"]))) if c else None)
    h_oper = salida_operada * dt
    # PAT 134: tasa ideal del OEE = producción planificada de la planta, la misma de Temporada y Tableros
    try:
        ln_op = OP.linea(pl, sol)
    except Exception:              # planta sin restricciones calculables
        ln_op = None
    tasa_plan = float(ln_op["plan"]) if ln_op and ln_op.get("plan") else None
    if tasa_plan is None:
        tasa_plan = tasa_max_linea
        avisos.append("La planta no entrega su producción planificada: el OEE usa la tasa máxima de la línea (recurso crítico).")

    def _oee(ideal):
        if h_plan > 0 and h_oper > 0 and ideal > 0:
            d = {kk: float(v) for kk, v in K.oee(h_plan, h_oper, ideal, producto, producto).items()}
        elif h_plan > 0:
            d = dict(disponibilidad=h_oper / h_plan, rendimiento=0.0, calidad=0.0, oee=0.0)
        else:
            return None
        d["tasa_ideal_t_h"] = float(ideal)
        return d
    oee_det = _oee(tasa_plan); oee_crit_det = _oee(tasa_max_linea)
    oee = oee_det["oee"] if oee_det else None
    oee_critico = oee_crit_det["oee"] if oee_crit_det else None

    equipos = [dict(id=e.id, nombre=e.nombre, tipo=e.tipo, capacidad_t_h=tasas_max[i], carga_t_h=cargas[i], razon_masa=razon[i])
               for i, e in enumerate(eqs)]
    tanques_out = [{kk: v for kk, v in t.items() if kk != "origen"} | dict(origen=t["origen"]) for t in tks]
    sup = [dict(clave=s.clave, nombre=s.nombre, valor=s.valor, unidad=s.unidad, justificacion=s.justificacion) for s in SUPUESTOS.values()]
    return dict(equipos=equipos, tanques=tanques_out, tramos=tramos, tiempo_h=tiempo_h, niveles=niveles, produccion_acumulada_t=prod_acum,
                tasas=tasas, por_equipo=por_equipo, produccion_t=producto, oee=oee, oee_detalle=oee_det, oee_critico=oee_critico,
                oee_critico_detalle=oee_crit_det, tasa_planificada_t_h=tasa_plan,
                disponibilidad=oee_det["disponibilidad"] if oee_det else None, balance=bal, tasa_linea_t_h=tasa_linea, tasa_maxima_linea_t_h=tasa_max_linea,
                produccion_sin_fallas_t=tasa_linea * h_plan, horas_planificadas=h_plan, avisos=avisos, supuestos=sup,
                parametros=dict(horas=horas, tick_min=tick_min, semilla=semilla, muestra_min=muestra_min, alimentacion_t_h=alim,
                                ticks=N, rubro=getattr(pl, "rubro", ""), paradas=[dict(inicio_h=a, fin_h=b, estado=s) for a, b, s in paradas],
                                fallas={k: (None if v is None else dict(mtbf=v["mtbf"], mttr=v["mttr"], base=v.get("base", "operando"),
                                                                        origen=v.get("origen", "Supuesto"), mantenimiento=v.get("mantenimiento")))
                                        for k, v in cfg.items()}))
