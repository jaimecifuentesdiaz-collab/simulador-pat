"""Operación por turnos de 8 h, laboratorio con resultado diferido, control estadístico (SPC) y evaluación automática.

Adaptación al PAT de las funciones runShift, sampleLab, deliverLab, drawSPC y grade del simulador del profesor
(Scorm_pellet_profesor.html), sobre la planta del simulador (cualquier rubro):
- la capacidad del turno es la producción real de la planta limitada por la restricción (teoría de restricciones de
  la pestaña Diseño), así que el desgaste del «estado» de cada equipo y el mantenimiento cambian lo que se produce;
- la calidad sale de la planta resuelta (catalogos/calidad.py) y el desgaste del equipo de control aumenta su variabilidad;
- en el tomate, el tomate fresco que espera en el patio se pierde y el gas que la cascada evita se cuenta por turno.
Todas las cifras didácticas están en SUPUESTOS, con su justificación. Los números aleatorios son reproducibles: dependen
solo de la semilla y del número de turno, como en el simulador del profesor.
"""
from __future__ import annotations
import math
import random
from dataclasses import dataclass, field, asdict
from . import lienzo as LZ
from ..catalogos import calidad as Q


@dataclass(frozen=True)
class Supuesto:
    clave: str
    nombre: str
    valor: float
    unidad: str
    justificacion: str


_P = "Valor del simulador del profesor (Scorm_pellet_profesor.html, función runShift)"
SUPUESTOS = {s.clave: s for s in [
    Supuesto("horas_turno", "Duración de un turno", 8.0, "h",
             "Como el simulador del profesor; la planta basada en Agrozzi opera 24 h al día (DIA_Agrozzi_rev0.pdf), es decir, tres turnos de 8 h"),
    Supuesto("p_falla", "Probabilidad de una falla no programada en un turno", 0.16, "—",
             _P + "; una falla cada seis turnos, para que se vea en pocas corridas"),
    Supuesto("disp_falla", "Capacidad disponible en un turno con falla", 0.36, "fracción", _P + ": la detención correctiva deja cerca de un tercio del turno"),
    Supuesto("p_alerta", "Probabilidad de una alerta de seguridad en un turno", 0.07, "—", _P),
    Supuesto("f_alerta", "Capacidad disponible con parada parcial por seguridad", 0.70, "fracción", _P),
    Supuesto("p_causa", "Probabilidad de una causa especial en la materia prima", 0.21, "—",
             _P + " (desviación de humedad en recepción); en el tomate es una desviación del °Brix del tomate que llega"),
    Supuesto("k_causa", "Corrimiento de la primera variable de calidad en un turno con causa especial", 3.0, "desviaciones estándar",
             "PAT, didáctico: en el profesor la causa especial solo se anuncia; aquí corre la media de las muestras de ese turno para que el gráfico de control la muestre"),
    Supuesto("merma_recepcion", "Merma máxima de la materia prima comprada", 0.015, "fracción", _P + ": llega hasta 1,5 % menos de lo comprado"),
    Supuesto("merma_patio", "Pérdida por turno del tomate que espera en el patio", 0.05, "fracción",
             "PAT, didáctico: el tomate fresco se procesa el mismo día de la cosecha y el que espera se ablanda y se descarta; sin dato de la planta"),
    Supuesto("f_mant", "Capacidad disponible en un turno con mantenimiento", 0.88, "fracción", _P + ": cerca de 1 h de detención en 8 h"),
    Supuesto("mejora_prev", "Mejora del estado del equipo crítico con mantenimiento preventivo", 0.06, "—", _P),
    Supuesto("mejora_corr", "Mejora del estado del equipo crítico con mantenimiento correctivo", 0.14, "—", _P),
    Supuesto("desgaste_min", "Desgaste mínimo del estado de cada equipo por turno", 0.002, "—", _P + ": el estado baja entre 0,002 y 0,004 por turno"),
    Supuesto("desgaste_var", "Desgaste aleatorio adicional por turno (máximo)", 0.002, "—", _P),
    Supuesto("estado_min", "Estado mínimo al que lleva el desgaste", 0.65, "—", _P),
    Supuesto("k_var_estado", "Aumento de la variabilidad de calidad por desgaste", 2.0, "—",
             "PAT, didáctico: la desviación estándar se multiplica por 1 + 2 × (1 − estado del equipo de control), 1,7 veces con el estado mínimo de 0,65; así el mantenimiento se ve en el control estadístico"),
    Supuesto("dem_media", "Demanda media por turno", 0.80, "fracción de la producción planificada del turno",
             "El profesor usa 12,5 t por turno con ±4,5 t de variación periódica y ±2 t de ruido para su planta de pellet; aquí se expresa como fracción de la producción planificada para que sirva a cualquier planta: queda bajo la capacidad para formar inventario, pero algunos turnos la superan"),
    Supuesto("dem_amp", "Amplitud de la variación periódica de la demanda", 0.28, "fracción de la producción planificada del turno", "Ver la demanda media"),
    Supuesto("dem_ruido", "Desviación estándar del ruido de la demanda", 0.12, "fracción de la producción planificada del turno", "Ver la demanda media"),
    Supuesto("stock_inicial", "Materia prima en el patio al partir", 0.5, "turnos de alimentación",
             "El profesor parte con 65 t de biomasa; aquí medio turno de alimentación de la planta"),
    Supuesto("conf_max", "Fracción conforme máxima", 0.99, "—", "El profesor limita la conformidad a 0,985 a 0,99: siempre hay pérdidas de llenado y reproceso"),
    Supuesto("min_muestras_spc", "Muestras mínimas para estimar los límites de control", 8, "muestras", "Valor del simulador del profesor (función drawSPC)"),
    Supuesto("min_muestras_cp", "Muestras mínimas para informar Cp y Cpk", 12, "muestras", "Valor del simulador del profesor (función drawSPC)"),
    Supuesto("racha", "Puntos seguidos al mismo lado de la línea central que se consideran señal", 8, "puntos",
             "PAT: segunda regla de las reglas de Western Electric (Montgomery, 2020); el profesor revisa solo los puntos fuera de 3σ"),
]}
S = {k: s.valor for k, s in SUPUESTOS.items()}
D2 = 1.128   # constante d2 para rangos móviles de 2 observaciones (Montgomery, 2020, tabla de constantes de cartas de control)
MANTENIMIENTOS = {"ninguno": "Ninguno", "preventivo": "Preventivo en el equipo crítico", "correctivo": "Correctivo"}


def _cl(v: float, d: int = 1) -> str:
    """Número con formato chileno (miles con punto y decimales con coma)."""
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def semilla_texto(texto: str) -> int:
    """FNV-1a de 32 bits, como randomSeed del profesor: el nombre del estudiante fija su escenario."""
    h = 2166136261
    for c in texto:
        h = ((h ^ ord(c)) * 16777619) & 0xFFFFFFFF
    return h


def azar(semilla: int, i: float) -> float:
    """Número uniforme reproducible en [0, 1) para la semilla y el índice i (rnd del profesor)."""
    return random.Random(f"{semilla}:{i:.4f}").random()


def normal(semilla: int, i: float) -> float:
    """Normal estándar por Box-Muller, como normal(i) del profesor."""
    return math.sqrt(-2 * math.log(max(1e-8, azar(semilla, i)))) * math.cos(2 * math.pi * azar(semilla, i + 911))


@dataclass
class Operacion:
    rubro: str = ""
    semilla: int = 0
    estudiante: str = ""
    turno: int = 0
    stock: float | None = None          # materia prima en el patio (t)
    terminado: float = 0.0              # producto conforme en bodega (t)
    turnos: list = field(default_factory=list)
    lab: list = field(default_factory=list)
    pendientes: list = field(default_factory=list)
    eventos: list = field(default_factory=list)
    mantenimientos: int = 0
    acciones: int = 0                   # acciones correctivas de calidad aplicadas
    finalizada: bool = False
    puntaje: dict | None = None
    justificaciones: dict = field(default_factory=dict)

    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def desde_dict(cls, d: dict) -> "Operacion":
        campos = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in campos})


# ----------------------------------------------------------------------------------------------- planta
def _estados(pl) -> dict:
    out = {}
    for k, e in pl.equipos.items():
        if "estado" in e.params and not e.tipo.startswith(("alimentacion", "caldera", "generador")):
            v = e.params["estado"].valor
            out[k] = 1.0 if v is None else float(v)
    return out


def linea(pl, sol=None) -> dict | None:
    """Producción planificada y real de la planta (t/h), materia prima por t de producto y equipo crítico.

    Con capacidades declaradas, la producción real es la de la teoría de restricciones (capacidad nominal × estado);
    sin capacidades, la producción planificada × el menor estado (disponibilidad del equipo más gastado)."""
    if sol is None:
        sol, _motivo = LZ.resolver_parcial(pl)
    tr = LZ.restricciones(pl, sol)
    if not tr or not tr.get("produccion_plan"):
        return None
    plan = float(tr["produccion_plan"]); est = _estados(pl)
    con_cap = any(e.capacidad_efectiva() for e in pl.equipos.values() if not e.tipo.startswith(("caldera", "generador")))
    if con_cap:
        real = float(tr["produccion_real"]); critico = tr.get("restrictivo")
    else:
        critico = min(est, key=lambda k: (est[k], k)) if est else None
        real = plan * (min(est.values()) if est else 1.0)
    alim = sum(float(e.resultado.detalle.get("carga_t_h") or 0) for e in sol.equipos.values()
               if e.tipo.startswith("alimentacion") and e.resultado is not None)
    return dict(plan=plan, real=real, critico=critico, con_capacidades=con_cap, alimentacion=alim,
                mp_por_t=alim / plan if plan else 0.0, estados=est, util=tr["equipos"])


# ----------------------------------------------------------------------------------------------- calidad
def factor_variabilidad(pl, var: Q.Variable) -> float:
    eq = pl.equipos.get(var.equipo_control) if var.equipo_control else None
    if eq is None or "estado" not in eq.params or eq.params["estado"].valor is None:
        return 1.0
    return 1.0 + S["k_var_estado"] * (1.0 - float(eq.params["estado"].valor))


def _fi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


def prob_conforme(media: float, sd: float, lo, hi) -> float:
    p = 1.0
    if hi is not None:
        p = _fi((hi - media) / sd) if sd > 0 else float(media <= hi)
    if lo is not None:
        p -= _fi((lo - media) / sd) if sd > 0 else float(media < lo)
    return max(0.0, p)


def conformidad(pl, desplazamiento: float = 0.0) -> float:
    """Fracción de producto conforme: probabilidad de que todas las variables queden dentro de especificación."""
    vs = Q.variables(pl)
    if not vs:
        return S["conf_max"]
    p = 1.0
    for j, v in enumerate(vs):
        sd = v.sd * factor_variabilidad(pl, v)
        p *= prob_conforme(v.media + (desplazamiento * sd if j == 0 else 0.0), sd, v.lo, v.hi)
    return max(0.0, min(S["conf_max"], p))


# ----------------------------------------------------------------------------------------------- turnos
def demanda(op: Operacion, t: int, plan_turno: float) -> float:
    """Demanda del turno t (t de producto), como demandAt del profesor escalada a la planta."""
    f = S["dem_media"] + S["dem_amp"] * math.sin(t * 0.77 + op.semilla % 13) + S["dem_ruido"] * normal(op.semilla, t * 20 + 51)
    return max(0.05, f) * plan_turno


def compra_sugerida(ln: dict, meta: float = 0.90) -> float:
    return ln["real"] * S["horas_turno"] * meta * ln["mp_por_t"]


def correr_turno(op: Operacion, pl, meta: float = 0.90, compra: float | None = None, mantenimiento: str = "ninguno",
                 resumen: dict | None = None, dist_falla_h: dict | None = None) -> dict:
    """Ejecuta un turno de 8 h (runShift del profesor). meta: utilización objetivo (0 a 1); compra: t de materia prima.
    PAT 134: con dist_falla_h (dict de motor/ajuste.py, duración de una detención correctiva en h), un turno con falla conserva
    max(0, 1 − duración/8) de su capacidad, con la duración muestreada de random.Random(semilla y turno), como azar()."""
    if op.finalizada:
        raise ValueError("La evaluación ya fue finalizada: reinicie la práctica o importe un proyecto para seguir operando.")
    ln = linea(pl)
    if ln is None:
        raise ValueError("La planta no tiene producción: resuélvala en la pestaña Diseño.")
    t = op.turno + 1; sem = op.semilla; h = S["horas_turno"]; meta = max(0.0, min(1.0, float(meta)))
    compra = compra_sugerida(ln, meta) if compra is None else max(0.0, float(compra))
    eventos = []
    if op.stock is None:
        op.stock = S["stock_inicial"] * ln["alimentacion"] * h
    if pl.rubro == "tomate" and op.stock > 0:                       # el tomate que esperó un turno se pierde en parte
        perdida = op.stock * S["merma_patio"]; op.stock -= perdida
        eventos.append(f"Se descartaron {_cl(perdida)} t de tomate que esperó un turno en el patio.")
    recibido = compra * (1 - S["merma_recepcion"] * azar(sem, t * 13)); op.stock += recibido
    critico = ln["critico"]
    if mantenimiento != "ninguno":
        op.mantenimientos += 1
        if critico and critico in pl.equipos and "estado" in pl.equipos[critico].params:
            p = pl.equipos[critico].params["estado"]
            p.valor = max(0.35, min(1.0, float(p.valor if p.valor is not None else 1.0) + S["mejora_prev" if mantenimiento == "preventivo" else "mejora_corr"]))
        eventos.append(f"Mantenimiento {mantenimiento} en {critico or 'la línea'}; horas de detención incluidas.")
        ln = linea(pl)
    falla = azar(sem, t * 31 + 17) < S["p_falla"]; alerta = azar(sem, t * 27 + 12) < S["p_alerta"]
    causa = azar(sem, t * 43 + 17) < S["p_causa"]
    falla_h = None; disp_f = S["disp_falla"]
    if falla and dist_falla_h is not None:          # PAT 134: duración de la falla ajustada a datos medidos
        from . import ajuste as AJ
        falla_h = max(0.0, AJ.muestrear(dist_falla_h, random.Random(f"{sem}:falla:{t}")))
        disp_f = max(0.0, 1.0 - falla_h / h)
    if falla:
        eventos.append("Detención correctiva no programada en la línea (disponibilidad reducida)." if falla_h is None else
                       f"Detención correctiva no programada de {_cl(falla_h, 1)} h (distribución ajustada; disponibilidad del turno {_cl(100 * disp_f, 0)} %).")
    if alerta:
        eventos.append("Alerta de seguridad: " + ("presión o fuga de vapor en el esterilizador" if pl.rubro == "tomate" else "polvo o temperatura en el secador")
                       + "; parada parcial.")
    signo = 1.0 if azar(sem, t * 43 + 99) < 0.5 else -1.0
    if causa:
        eventos.append(("Desviación del °Brix del tomate en recepción" if pl.rubro == "tomate" else "Desviación de humedad de la materia prima en recepción")
                       + " (causa especial de variación).")
    capacidad = ln["real"] * h * meta * (disp_f if falla else 1.0) * (S["f_alerta"] if alerta else 1.0) * (S["f_mant"] if mantenimiento != "ninguno" else 1.0)
    necesidad = capacidad * ln["mp_por_t"]
    limite = min(1.0, op.stock / necesidad) if necesidad > 1e-9 else 1.0
    if limite < 1.0:
        eventos.append("Faltó materia prima: la línea paró antes de completar el turno.")
    producido = capacidad * limite; usado = necesidad * limite
    op.stock = max(0.0, op.stock - usado)
    conf = conformidad(pl, signo * S["k_causa"] if causa else 0.0)
    conforme = producido * conf
    pedido = demanda(op, t, ln["plan"] * h)
    vendido = min(pedido, op.terminado + conforme)
    op.terminado = max(0.0, op.terminado + conforme - vendido)
    energia = energia_turno(resumen, producido / (ln["plan"] * h) if ln["plan"] else 0.0)
    reg = dict(turno=t, meta=meta, compra=compra, recibido=recibido, mantenimiento=mantenimiento, critico=critico, falla=falla, falla_h=falla_h, alerta=alerta,
               causa=causa, desplazamiento=signo * S["k_causa"] if causa else 0.0, capacidad=capacidad, producido=producido,
               conformidad=conf, conforme=conforme, no_conforme=producido - conforme, demanda=pedido, vendido=vendido,
               faltante=max(0.0, pedido - vendido), stock=op.stock, terminado=op.terminado, materia_prima=usado, eventos=eventos, **energia)
    if not eventos:
        eventos.append("Sin evento especial observado: persiste la variabilidad común.")
    op.turno = t; op.turnos.append(reg); op.eventos += [dict(turno=t, texto=e) for e in eventos]
    entregar_muestras(op)
    for n, (k, v) in enumerate(sorted(_estados(pl).items())):         # desgaste con el uso
        p = pl.equipos[k].params["estado"]
        p.valor = max(S["estado_min"], min(1.0, v - S["desgaste_min"] - azar(sem, t + (n + 1) * 7) * S["desgaste_var"])) if v > S["estado_min"] else v
    return reg


def energia_turno(r: dict | None, fraccion: float) -> dict:
    """Energía del turno: gas (o biomasa) del sumidero sin recuperación y lo que evita la cascada, a la producción del turno."""
    out = dict(gas_sumidero_MMBtu=None, gas_evitado_MMBtu=None, co2_evitado_t=None, biomasa_evitada_t=None)
    if not r or not r.get("horas"):
        return out
    k = S["horas_turno"] * max(0.0, fraccion) / float(r["horas"])
    if "gas_base" in r:
        out.update(gas_sumidero_MMBtu=r["gas_base"]["MMBtu"] * k, gas_evitado_MMBtu=r["gas_cascada"]["MMBtu"] * k, co2_evitado_t=r["gas_cascada"]["co2_t"] * k)
    elif "biomasa_cascada" in r and "t" in r["biomasa_cascada"]:
        out.update(biomasa_evitada_t=r["biomasa_cascada"]["t"] * k)
    return out


# ----------------------------------------------------------------------------------------------- laboratorio
def tomar_muestra(op: Operacion, pl) -> dict:
    """Toma una muestra (sampleLab del profesor): el resultado llega uno o dos turnos después."""
    if op.finalizada:
        raise ValueError("La evaluación ya fue finalizada.")
    t = op.turno; n = len(op.lab) + len(op.pendientes)
    desp = op.turnos[-1]["desplazamiento"] if op.turnos else 0.0
    vs = Q.variables(pl); medias, sds = {}, {}
    for j, v in enumerate(vs):
        sd = v.sd * factor_variabilidad(pl, v); sds[v.id] = sd
        medias[v.id] = v.media + (desp * sd if j == 0 else 0.0)
    tk = dict(id=n + 1, tomada=t, entrega=t + 1 + int(azar(op.semilla, t * 7 + n + 3) * 2), medias=medias, sd=sds,
              semilla=op.semilla + t * 101 + n * 53)
    op.pendientes.append(tk)
    return tk


def entregar_muestras(op: Operacion):
    """Entrega los resultados cuyo turno de entrega ya llegó (deliverLab del profesor)."""
    quedan = []
    for tk in op.pendientes:
        if tk["entrega"] > op.turno:
            quedan.append(tk); continue
        valores = {k: tk["medias"][k] + tk["sd"][k] * normal(tk["semilla"], j * 27) for j, k in enumerate(tk["medias"])}
        op.lab.append(dict(id=tk["id"], turno=op.turno, tomada=tk["tomada"], valores=valores))
    op.pendientes = quedan


# ----------------------------------------------------------------------------------------------- SPC
def spc(valores: list[float], lo=None, hi=None) -> dict:
    """Carta de individuos con rango móvil (Montgomery, 2020): límites con MR/1,128; Cp, Cpk, Pp y Ppk.

    Como en el profesor: límites de control desde 8 muestras y capacidad solo con 12 o más y sin señales."""
    n = len(valores)
    out = dict(n=n, media=None, s=None, sigma=None, lc=None, fuera=[], racha=False, estable=None, cp=None, cpk=None, pp=None, ppk=None,
               reportable=False, estado="Sin datos")
    if n == 0:
        return out
    mu = sum(valores) / n
    s = math.sqrt(sum((v - mu) ** 2 for v in valores) / (n - 1)) if n > 1 else 0.0
    mr = [abs(b - a) for a, b in zip(valores, valores[1:])]
    sig = (sum(mr) / len(mr)) / D2 if mr else 0.0
    out.update(media=mu, s=s, sigma=sig)
    if n < S["min_muestras_spc"]:
        out["estado"] = "Datos insuficientes"
        return out
    lc = (mu - 3 * sig, mu + 3 * sig)
    fuera = [i for i, v in enumerate(valores) if v < lc[0] or v > lc[1]]
    racha = larga = 0; lado_prev = 0
    for v in valores:
        lado = 1 if v > mu else -1 if v < mu else 0
        racha = racha + 1 if lado != 0 and lado == lado_prev else (1 if lado != 0 else 0)
        lado_prev = lado; larga = max(larga, racha)
    hay_racha = larga >= S["racha"]
    estable = not fuera and not hay_racha
    out.update(lc=lc, fuera=fuera, racha=hay_racha, estable=estable,
               estado="Sin señales" if estable else ("Puntos fuera de 3σ" if fuera else f"Racha de {int(S['racha'])} puntos a un lado"))

    def cap(sd):
        if sd <= 0:
            return None, None
        cp = (hi - lo) / (6 * sd) if lo is not None and hi is not None else None
        ks = [x for x in ((hi - mu) / (3 * sd) if hi is not None else None, (mu - lo) / (3 * sd) if lo is not None else None) if x is not None]
        return cp, (min(ks) if ks else None)
    out["cp"], out["cpk"] = cap(sig)
    out["pp"], out["ppk"] = cap(s)
    out["reportable"] = n >= S["min_muestras_cp"] and estable
    return out


def grafico_control(valores: list[float], var: Q.Variable, r: dict, ancho: int = 640, alto: int = 250) -> str:
    """SVG de la carta de individuos: especificación (naranjo, trazos largos) y control (azul, trazos cortos), como lineChart del profesor."""
    import html as _h
    p = 46
    ref = [v for v in (var.lo, var.hi) if v is not None] + list(r["lc"] or [])
    lo_y = min(valores + ref) - var.sd * 2; hi_y = max(valores + ref) + var.sd * 2
    if hi_y - lo_y < 1e-9:
        hi_y = lo_y + 1
    X = lambda i: p + i * (ancho - 2 * p) / max(1, len(valores) - 1)
    Y = lambda v: alto - p - (v - lo_y) / (hi_y - lo_y) * (alto - 2 * p)
    f = lambda v: f"{v:,.{var.decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    linea_ref = lambda y, color, dash, et: (f'<path d="M{p} {Y(y):.1f}H{ancho - p}" stroke="{color}" stroke-dasharray="{dash}" fill="none"/>'
                                            f'<text x="{ancho - p + 3}" y="{Y(y) + 4:.1f}" font-size="10" fill="{color}">{et}</text>')
    partes = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%" role="img" aria-label="{_h.escape(var.nombre)}" '
              f'style="font-family:sans-serif;background:#fff">',
              f'<path d="M{p} {p}V{alto - p}H{ancho - p}" fill="none" stroke="#9bacb3"/>']
    if var.lo is not None:
        partes.append(linea_ref(var.lo, "#c37d31", "7 3", "LIE"))
    if var.hi is not None:
        partes.append(linea_ref(var.hi, "#c37d31", "7 3", "LSE"))
    if r["lc"]:
        partes += [linea_ref(r["lc"][0], "#3f7fb0", "3 3", "LIC"), linea_ref(r["lc"][1], "#3f7fb0", "3 3", "LSC"),
                   linea_ref(r["media"], "#7a8a90", "1 0", "LC")]
    d = " ".join(f"{'L' if i else 'M'}{X(i):.1f} {Y(v):.1f}" for i, v in enumerate(valores))
    partes.append(f'<path d="{d}" fill="none" stroke="#147d82" stroke-width="2.2"/>')
    for i, v in enumerate(valores):
        fuera_esp = (var.lo is not None and v < var.lo) or (var.hi is not None and v > var.hi)
        color = "#b54043" if fuera_esp else "#167b83"
        borde = ' stroke="#f0a020" stroke-width="2"' if i in r["fuera"] else ""
        partes.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3.6" fill="{color}"{borde}/>')
    partes += [f'<text x="{p}" y="16" font-size="13" fill="#36586c">{_h.escape(var.nombre)} ({_h.escape(var.unidad)})</text>',
               f'<text x="4" y="{p + 4}" font-size="10">{f(hi_y)}</text><text x="4" y="{alto - p}" font-size="10">{f(lo_y)}</text>',
               f'<text x="{ancho - p}" y="{alto - 12}" text-anchor="end" font-size="10">Muestra</text></svg>']
    return "".join(partes)


def grafico_demanda(valores: list[float], titulo: str, ancho: int = 520, alto: int = 190) -> str:
    p = 42; hi = max(valores) * 1.15 if valores else 1.0
    X = lambda i: p + i * (ancho - 2 * p) / max(1, len(valores) - 1)
    Y = lambda v: alto - p - v / hi * (alto - 2 * p)
    d = " ".join(f"{'L' if i else 'M'}{X(i):.1f} {Y(v):.1f}" for i, v in enumerate(valores))
    f = lambda v: f"{v:,.0f}".replace(",", ".")
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="100%" style="font-family:sans-serif;background:#fff">'
            f'<path d="M{p} {p}V{alto - p}H{ancho - p}" fill="none" stroke="#9bacb3"/><path d="{d}" fill="none" stroke="#147d82" stroke-width="2.2"/>'
            + "".join(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="3" fill="#167b83"/>' for i, v in enumerate(valores))
            + f'<text x="{p}" y="15" font-size="13" fill="#36586c">{titulo}</text><text x="4" y="{p + 4}" font-size="10">{f(hi)}</text>'
              f'<text x="4" y="{alto - p}" font-size="10">0</text><text x="{ancho - p}" y="{alto - 10}" text-anchor="end" font-size="10">Turno</text></svg>')


# ----------------------------------------------------------------------------------------------- evaluación
CRITERIOS = [("diseno", "Diseño y balances", 15), ("restricciones", "Teoría de restricciones", 20), ("economia", "Dimensionamiento y economía", 15),
             ("calidad", "Control estadístico y calidad", 20), ("operacion", "Operación y perturbaciones", 15),
             ("recuperacion", "Recuperación de calor (aporte del PAT)", 15)]
MIN_JUSTIFICACION = 150     # caracteres; indicador de actividad, como el profesor no interpreta el texto


def evaluar(op: Operacion, pl, inversion: float = 0.0, cascada_kW: float | None = None) -> dict:
    """Puntaje automático por criterios (grade del profesor): sus 85 puntos más 15 de la recuperación de calor = 100.

    Usa indicadores de actividad y logros; no interpreta el contenido de las justificaciones."""
    ln = linea(pl) if pl.resuelta else None
    sobre = any((v.get("util_demanda") or 0) > 1.0 + 1e-9 for v in (ln or {}).get("util", {}).values())
    valida = bool(pl.resuelta and ln and ln["real"] > 0 and not sobre)
    J = op.justificaciones or {}
    escrita = lambda k: len((J.get(k) or "").strip()) >= MIN_JUSTIFICACION
    vs = Q.variables(pl) if pl.resuelta else []
    reportable = False
    for v in vs:
        vals = [m["valores"][v.id] for m in op.lab if v.id in m["valores"]]
        if spc(vals, v.lo, v.hi)["reportable"]:
            reportable = True; break
    conforme_total = any(all((v.lo is None or m["valores"].get(v.id, v.lo) >= v.lo) and (v.hi is None or m["valores"].get(v.id, v.hi) <= v.hi) for v in vs)
                         for m in op.lab) if vs else False
    d = dict(
        diseno=15 if valida else 5,
        restricciones=(10 if ln and ln["con_capacidades"] and ln["critico"] else 0) + (5 if escrita("restricciones") else 0) + (5 if len(pl.equipos) >= 8 else 0),
        economia=(10 if inversion and inversion > 0 else 0) + (5 if pl.resuelta and cascada_kW is not None else 0),
        calidad=(10 if len(op.lab) >= 8 else 5 if op.lab else 0) + (5 if conforme_total else 0) + (5 if reportable else 0),
        operacion=(10 if len(op.turnos) >= 5 else 5 if op.turnos else 0) + (5 if op.mantenimientos > 0 else 0),
        recuperacion=(10 if cascada_kW and cascada_kW > 0 else 0) + (5 if escrita("recuperacion") else 0),
    )
    d["total"] = sum(d[k] for k, _n, _m in CRITERIOS)
    return d


def finalizar(op: Operacion, pl, **kw) -> dict:
    if not op.turnos:
        raise ValueError("Ejecute al menos un turno antes de finalizar.")
    op.puntaje = evaluar(op, pl, **kw); op.finalizada = True
    return op.puntaje
