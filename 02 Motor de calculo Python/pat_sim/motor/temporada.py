"""Temporada de la planta (PAT 133, mejoras 6 y 7): llegada de materia prima con su cola de camiones en el patio y
programa de producción (Gantt) con arranque, limpiezas, paradas programadas y parada final.

(6) llegadas_temporada: curva de llegada por día (tomate: campana alrededor del peak de cosecha; pellet, chip y leña:
llegada pareja), camiones de carga declarada y simulación de eventos discretos de la cola frente a la capacidad de
recepción del primer equipo de la línea (la capacidad de partida de escenarios/capacidades.py). La cola se registra hora
a hora. Se compara la espera simulada con la aproximación de Kingman y se comprueba la ley de Little (L = λW).
(7) programa_temporada y gantt_svg: barras del programa, horas efectivas, efecto en la producción y calor recuperable
que no se aprovecha mientras la línea está detenida.
Las cifras sin fuente segura van en SUPUESTOS con su justificación. Los números aleatorios dependen solo de la semilla
(random.Random(semilla)), así que la misma semilla entrega la misma temporada.
"""
from __future__ import annotations
import base64
import html as _h
import math
import random
from . import calculadoras as K
from .operacion import Supuesto, S as S_OP, linea as _linea, _cl

_SD = "sin dato de la planta ni fuente segura"
_CV = Supuesto("cv_servicio", "Coeficiente de variación del tiempo de descarga de un camión", 0.30, "—",
               "Maniobra, pesaje y descarga cambian de un camión a otro; valor didáctico, " + _SD + ". Es el cs de la ecuación de Kingman "
               "(Hopp y Spearman, 2008)")
_SIN_DEG = ("La biomasa leñosa no se degrada en esperas de horas o días: el acopio en cancha es parte normal de su cadena y la pérdida "
            "de materia seca en pilas es un fenómeno de semanas, fuera del alcance de esta simulación")


def _biomasa(materia: str, camion: float, arranque: float, limpieza_cada: float) -> list:
    return [
        Supuesto("camion", f"Carga de un camión de {materia}", camion, "t",
                 f"Carga útil típica de un camión con semirremolque que trae {materia}; {_SD}. Se puede cambiar en la pestaña"),
        _CV,
        Supuesto("umbral", "Espera sobre la cual la materia prima se degrada", 0.0, "h", _SIN_DEG),
        Supuesto("tasa", "Pérdida por hora de espera sobre el umbral", 0.0, "fracción por h", _SIN_DEG),
        Supuesto("arranque", "Duración del arranque de la temporada", arranque, "h",
                 "Encendido del generador de calor y calentamiento del secador antes de recibir carga; " + _SD),
        Supuesto("cip_cada", "Horas de producción entre limpiezas programadas", limpieza_cada, "h",
                 "Limpieza en seco semanal del secador, ductos y ciclones (polvo y riesgo de incendio); " + _SD),
        Supuesto("cip_dur", "Duración de una limpieza programada", 4.0, "h", "Medio turno de detención; " + _SD),
        Supuesto("parada_cada", "Días entre paradas programadas de mantenimiento", 30.0, "d",
                 "Mantenimiento preventivo mensual de la línea; " + _SD),
        Supuesto("parada_dur", "Duración de una parada programada", 24.0, "h", "Un día de mantenimiento preventivo; " + _SD),
        Supuesto("parada_final", "Duración de la parada final", 8.0, "h", "Vaciado de la línea, limpieza y apagado del generador; " + _SD),
    ]


SUPUESTOS = {
    "tomate": [
        Supuesto("camion", "Carga de un camión de tomate", 25.0, "t",
                 "Carga útil típica de un camión con batea o bins de tomate de industria; " + _SD + ". Se puede cambiar en la pestaña"),
        _CV,
        Supuesto("pico", "Posición del peak de cosecha en la temporada", 0.50, "fracción de la temporada",
                 "La temporada va de febrero a abril (Balance de Masa_Rev0.pdf, p. 6): el peak se pone a mitad, en marzo. La forma de "
                 "campana es un supuesto: no hay registro diario de la recepción de la planta"),
        Supuesto("ancho", "Desviación estándar de la campana", 0.25, "fracción de la temporada",
                 "Con este ancho los extremos de la temporada reciben cerca de 14 % del peak, de modo que el arranque y el cierre "
                 "tienen tomate; " + _SD),
        Supuesto("umbral", "Espera sobre la cual el tomate se degrada", 6.0, "h",
                 "El tomate de industria se procesa el mismo día de la cosecha; sobre 6 h en el patio se considera que empieza a "
                 "ablandarse. " + _SD.capitalize()),
        Supuesto("tasa", "Pérdida de tomate por hora de espera sobre el umbral", S_OP["merma_patio"] / S_OP["horas_turno"], "fracción por h",
                 "La misma pérdida del tomate que espera en la pestaña Operación (5 % por turno de 8 h, supuesto didáctico de PAT 130), "
                 "expresada por hora"),
        Supuesto("arranque", "Duración del arranque de la temporada", 12.0, "h",
                 "Circulación con agua, vacío y calentamiento de los evaporadores y esterilización de la llenadora aséptica antes del "
                 "primer producto; " + _SD),
        Supuesto("cip_cada", "Horas de producción entre limpiezas CIP de los evaporadores", 120.0, "h",
                 "La pasta ensucia las superficies de calefacción y el coeficiente global baja; se supone una limpieza CIP cada cinco "
                 "días de producción. " + _SD.capitalize()),
        Supuesto("cip_dur", "Duración de una limpieza CIP", 8.0, "h", "Un turno: soda, enjuague, ácido y enjuague final; " + _SD),
        Supuesto("parada_cada", "Días entre paradas programadas de mantenimiento", 38.0, "d",
                 "Una parada de mantenimiento a mitad de la temporada de 76 días; " + _SD),
        Supuesto("parada_dur", "Duración de una parada programada", 12.0, "h", "Mantenimiento preventivo del equipo crítico; " + _SD),
        Supuesto("parada_final", "Duración de la parada final", 24.0, "h",
                 "Vaciado de la línea, limpieza CIP de cierre de todos los equipos y apagado de las calderas; " + _SD),
    ],
    "pellet": _biomasa("aserrín verde", 25.0, 4.0, 168.0),
    "chip": _biomasa("rollizos", 28.0, 2.0, 96.0),
    "lena": _biomasa("trozas", 25.0, 2.0, 168.0),
}
TIPOS = [("arranque", "Arranque", "#8a9aa3"), ("produccion", "Producción", "#4f7f6a"), ("limpieza", "Limpieza", "#5b84a8"),
         ("parada", "Parada programada", "#b08a4a"), ("fuera_turno", "Fuera de turno", "#d3d9dc"), ("parada_final", "Parada final", "#8b5e5e")]
NOMBRE_TIPO = {k: n for k, n, _c in TIPOS}
COLOR_TIPO = {k: c for k, _n, c in TIPOS}


def supuestos(pl) -> dict:
    """Valores por defecto del rubro de la planta (los rubros que no están usan los de pellet)."""
    return {s.clave: s.valor for s in SUPUESTOS.get(pl.rubro, SUPUESTOS["pellet"])}


# ----------------------------------------------------------------------------------------------- datos de la planta
def datos_planta(pl) -> dict:
    """Días, horas por día, alimentación (t/h) y el primer equipo de la línea con su capacidad efectiva."""
    if not pl.resuelta:
        pl.resolver()
    alim = next((pl.equipos[k] for k in pl.orden() if pl.equipos[k].tipo.startswith("alimentacion")
                 and pl.equipos[k].resultado is not None), None)
    if alim is None:
        raise ValueError("La planta no tiene un equipo de alimentación resuelto: revise la pestaña Diseño.")
    D = int(round(float(alim.v("dias")))); H = float(alim.v("horas_dia"))
    carga = float(alim.resultado.detalle.get("carga_t_h") or 0.0)
    if D < 1 or not 0 < H <= 24 or carga <= 0:
        raise ValueError("La alimentación debe tener días, horas por día y carga positivos.")
    sig = [c.destino for c in pl.conexiones if c.origen == alim.id and not pl.es_servicio(c)]
    primero = pl.equipos[sig[0]] if sig else None
    return dict(alimentacion=alim.id, D=D, H=H, carga=carga, total=carga * D * H, primero=primero.id if primero else None,
                nombre_primero=primero.nombre if primero else None, cap_primero=primero.capacidad_efectiva() if primero else None)


def capacidad_linea(pl) -> float | None:
    """Materia prima máxima que acepta la línea (t/h): alimentación × menor razón capacidad efectiva / carga (el recurso crítico)."""
    d = datos_planta(pl); r = None
    for e in pl.equipos.values():
        if e.tipo.startswith(("alimentacion", "caldera", "generador")) or e.resultado is None:
            continue
        cap = e.capacidad_efectiva(); carga = e.resultado.detalle.get("carga_t_h")
        if cap and carga:
            r = cap / float(carga) if r is None else min(r, cap / float(carga))
    return d["carga"] * r if r is not None else None


def curva_llegada(pl, pico: float | None = None, ancho: float | None = None) -> list[float]:
    """Materia prima que llega cada día (t). Tomate: campana normal alrededor del peak; otros rubros: pareja.
    En ambos casos la suma de la temporada es lo que procesa la planta (carga × días × horas por día)."""
    d = datos_planta(pl); D = d["D"]; sp = supuestos(pl)
    if pl.rubro != "tomate":
        return [d["total"] / D] * D
    pico = sp["pico"] if pico is None else float(pico); ancho = sp["ancho"] if ancho is None else float(ancho)
    mu = pico * (D - 1); sig = max(1e-6, ancho * D)
    w = [math.exp(-0.5 * ((i - mu) / sig) ** 2) for i in range(D)]
    s = sum(w)
    return [d["total"] * x / s for x in w]


def _restar(a: float, b: float, ocupados: list) -> list:
    """Partes de [a, b] que no tocan los intervalos ocupados (lista de (ini, fin))."""
    partes = [(a, b)]
    for x, y in ocupados:
        nuevas = []
        for p, q in partes:
            if y <= p or x >= q:
                nuevas.append((p, q)); continue
            if x > p:
                nuevas.append((p, x))
            if y < q:
                nuevas.append((y, q))
        partes = nuevas
    return [(p, q) for p, q in partes if q - p > 1e-9]


# ----------------------------------------------------------------------------------------------- (7) programa
def programa_temporada(pl, arranque_h=None, cip_cada_h=None, cip_duracion_h=None, parada_cada_d=None, parada_duracion_h=None,
                       parada_final_h=None, paradas: list | None = None, resumen: dict | None = None) -> dict:
    """Programa de producción de la temporada en horas corridas (el día d va de 24·d a 24·d + 24 h).

    paradas: lista de (inicio_h, duración_h, nombre) que reemplaza a las paradas periódicas. Las limpiezas se programan cada
    cip_cada_h horas de producción; una parada programada o la parada final reinician la cuenta (se limpia en ellas).
    Devuelve las barras (actividad, inicio_h, fin_h, tipo), sin traslapes y cubriendo toda la temporada, y sus efectos."""
    d = datos_planta(pl); sp = supuestos(pl); D, H = d["D"], d["H"]
    a = sp["arranque"] if arranque_h is None else float(arranque_h)
    N = sp["cip_cada"] if cip_cada_h is None else float(cip_cada_h)
    c = sp["cip_dur"] if cip_duracion_h is None else float(cip_duracion_h)
    pc = sp["parada_cada"] if parada_cada_d is None else float(parada_cada_d)
    pd = sp["parada_dur"] if parada_duracion_h is None else float(parada_duracion_h)
    f = sp["parada_final"] if parada_final_h is None else float(parada_final_h)
    T = 24.0 * D; fin_op = 24.0 * (D - 1) + H
    limpieza = "Limpieza CIP" if pl.rubro == "tomate" else "Limpieza programada"
    if paradas is None:
        paradas = []
        if pc and pc > 0 and pd > 0:
            k = 1
            while k * pc < D - 1:
                paradas.append((24.0 * int(round(k * pc)), pd, f"Parada programada {k}")); k += 1
    candidatos = [(0.0, min(a, fin_op), "arranque", "Arranque de la temporada")]
    candidatos += [(24.0 * k + H, 24.0 * k + 24.0, "fuera_turno", "Fuera de turno") for k in range(D) if H < 24]
    candidatos += [(max(0.0, fin_op - f), fin_op, "parada_final", "Parada final y limpieza de cierre")]
    candidatos += [(float(i), float(i) + float(du), "parada", n) for i, du, n in paradas if du > 0]
    fijos = []                                   # se pintan en orden de prioridad para que no se traslapen
    for i, j, tipo, act in candidatos:
        for p, q in _restar(max(0.0, i), min(T, j), [(x[1], x[2]) for x in fijos]):
            fijos.append((act, p, q, tipo))
    fijos.sort(key=lambda x: x[1])
    libres = _restar(0.0, T, [(x[1], x[2]) for x in fijos])
    barras = [dict(actividad=x[0], inicio_h=x[1], fin_h=x[2], tipo=x[3]) for x in fijos]
    cuenta = 0.0
    for s, e in libres:
        t = s
        while t < e - 1e-9:
            falta = N - cuenta if N and N > 0 and c > 0 else math.inf
            if t + falta >= e:
                barras.append(dict(actividad="Producción", inicio_h=t, fin_h=e, tipo="produccion")); cuenta += e - t; t = e
            else:
                if falta > 1e-9:
                    barras.append(dict(actividad="Producción", inicio_h=t, fin_h=t + falta, tipo="produccion"))
                ini = t + falta; fin = min(ini + c, e)
                barras.append(dict(actividad=limpieza, inicio_h=ini, fin_h=fin, tipo="limpieza")); cuenta = 0.0; t = fin
        sigue = next((x for x in fijos if abs(x[1] - e) < 1e-9), None)
        if sigue is not None and sigue[3] in ("parada", "parada_final"):
            cuenta = 0.0
    barras.sort(key=lambda b: b["inicio_h"])
    horas = {k: 0.0 for k, _n, _c in TIPOS}
    for b in barras:
        horas[b["tipo"]] += b["fin_h"] - b["inicio_h"]
    h_diseno = D * H; h_ef = horas["produccion"]
    ln = _linea(pl)
    plan = ln["plan"] if ln else None; real = ln["real"] if ln else None
    cap_mp = capacidad_linea(pl)
    mp_t = ln["mp_por_t"] if ln and ln["mp_por_t"] else None
    o = K.oee(h_diseno, h_ef, plan, real * h_ef, real * h_ef) if ln and plan else None
    prod_max = min(d["total"], cap_mp * h_ef) / mp_t if cap_mp and mp_t else None
    if resumen is None:
        from .resumen import resumen_planta
        try:
            resumen = resumen_planta(pl)
        except Exception:                       # planta sin sumidero o sin caldera: el programa igual sirve
            resumen = {}
    casc = float(resumen.get("cascada") or 0.0)
    detenida = h_diseno - h_ef                   # horas de diseño en que la línea no produce
    perdida_tipo = {k: casc * horas[k] / 1000 for k in ("arranque", "limpieza", "parada", "parada_final")}
    frac = detenida / h_diseno if h_diseno else 0.0
    comb = {}
    if resumen.get("gas_cascada"):
        g = resumen["gas_cascada"]; comb = dict(combustible="gas", MMBtu=g["MMBtu"] * frac, m3=g["m3"] * frac, co2_t=g["co2_t"] * frac)
    elif resumen.get("biomasa_cascada"):
        g = resumen["biomasa_cascada"]; comb = dict(combustible="biomasa", t=float(g["t"]) * frac, m3=float(g["m3"]) * frac)
    return dict(barras=barras, horas_totales=T, horas_diseno=h_diseno, horas_efectivas=h_ef, horas_por_tipo=horas,
                horas_detenida=detenida, disponibilidad=h_ef / h_diseno if h_diseno else 0.0, oee=o, dias=D, horas_dia=H,
                produccion_t_h=real, produccion_diseno_t=plan * h_diseno if plan else None,
                produccion_programa_t=real * h_ef if real is not None else None,
                produccion_perdida_t=(plan * h_diseno - real * h_ef) if plan else None,
                produccion_maxima_t=prod_max, produccion_no_alcanzada_t=(plan * h_diseno - prod_max) if plan and prod_max is not None else None,
                materia_prima_t=d["total"], ritmo_necesario_t_h=d["total"] / h_ef if h_ef else math.inf, capacidad_linea_t_h=cap_mp,
                alcanza=(cap_mp is not None and h_ef > 0 and d["total"] / h_ef <= cap_mp + 1e-9),
                cascada_kW=casc, calor_no_recuperado_MWh=casc * detenida / 1000, calor_no_recuperado_por_tipo_MWh=perdida_tipo,
                combustible_no_evitado=comb,
                parametros=dict(arranque_h=a, cip_cada_h=N, cip_duracion_h=c, parada_cada_d=pc, parada_duracion_h=pd, parada_final_h=f))


def gantt_svg(programa: dict, ancho: int = 900) -> str:
    """Gantt del programa en SVG: una fila por tipo de actividad, eje en días de la temporada, colores sobrios."""
    barras = programa["barras"]; T = float(programa["horas_totales"]) or 1.0; D = int(programa.get("dias") or round(T / 24))
    filas = [k for k, _n, _c in TIPOS if any(b["tipo"] == k for b in barras)]
    izq, der, arriba, alto_fila = 150, 20, 34, 26
    alto = arriba + alto_fila * len(filas) + 40
    X = lambda h: izq + h / T * (ancho - izq - der)
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img" '
         f'aria-label="Programa de producción de la temporada" style="font-family:sans-serif;background:#fff">',
         f'<rect x="0" y="0" width="{ancho}" height="{alto}" fill="#fff"/>',
         f'<text x="{izq}" y="20" font-size="13" fill="#36586c">Programa de producción de la temporada '
         f'({_cl(programa["horas_efectivas"], 0)} h efectivas de {_cl(programa["horas_diseno"], 0)} h de diseño)</text>']
    paso = next((s for s in (1, 2, 5, 7, 10, 14, 15, 20, 30, 50, 60, 100) if D / s <= 12), max(1, D // 10))
    y0 = arriba; y1 = arriba + alto_fila * len(filas)
    for dd in range(0, D + 1, paso):
        x = X(24.0 * dd)
        p.append(f'<path d="M{x:.1f} {y0}V{y1}" stroke="#e6eaec"/><text x="{x:.1f}" y="{y1 + 14}" font-size="10" text-anchor="middle" '
                 f'fill="#555">{dd}</text>')
    p.append(f'<text x="{(izq + ancho - der) / 2:.0f}" y="{y1 + 30}" font-size="11" text-anchor="middle" fill="#555">Día de la temporada</text>')
    for i, k in enumerate(filas):
        y = arriba + i * alto_fila
        p.append(f'<rect x="{izq}" y="{y}" width="{ancho - izq - der}" height="{alto_fila}" fill="{"#f7f9f9" if i % 2 else "#fff"}"/>'
                 f'<text x="{izq - 8}" y="{y + alto_fila / 2 + 4:.1f}" font-size="11" text-anchor="end" fill="#333">{_h.escape(NOMBRE_TIPO[k])}</text>')
        for b in barras:
            if b["tipo"] != k:
                continue
            x = X(b["inicio_h"]); w = max(1.0, X(b["fin_h"]) - x)
            tit = f'{b["actividad"]}: {_cl(b["inicio_h"], 1)} a {_cl(b["fin_h"], 1)} h'
            p.append(f'<rect x="{x:.2f}" y="{y + 5}" width="{w:.2f}" height="{alto_fila - 10}" fill="{COLOR_TIPO[k]}"><title>{_h.escape(tit)}</title></rect>')
    p.append(f'<path d="M{izq} {y0}V{y1}H{ancho - der}" fill="none" stroke="#9bacb3"/></svg>')
    return "".join(p)


def svg_como_img(svg: str) -> str:
    """Etiqueta img con el SVG en base64, para mostrarlo con st.html (que no dibuja un SVG suelto)."""
    return ('<img alt="Programa de producción" style="width:100%;height:auto" src="data:image/svg+xml;base64,'
            + base64.b64encode(svg.encode("utf-8")).decode("ascii") + '">')


# ----------------------------------------------------------------------------------------------- (6) llegadas y cola
def _ventanas(pl, d: dict, programa: dict | None) -> list:
    """Horas en que la recepción atiende: las de producción del programa o, sin programa, las horas de operación de cada día."""
    if programa is not None:
        return [(b["inicio_h"], b["fin_h"]) for b in programa["barras"] if b["tipo"] == "produccion"]
    return [(24.0 * k, 24.0 * k + d["H"]) for k in range(d["D"])]


def _repartir(acum: list, x: float, y: float, valor_por_h: float):
    """Suma valor_por_h × (horas de [x, y] dentro de cada día) en acum."""
    D = len(acum)
    k = max(0, int(x // 24))
    while k < D and 24.0 * k < y:
        tr = min(y, 24.0 * k + 24) - max(x, 24.0 * k)
        if tr > 0:
            acum[k] += valor_por_h * tr
        k += 1


def llegadas_temporada(pl, semilla: int = 0, camion_t=None, cv_servicio=None, pico=None, ancho=None, umbral_h=None, tasa_h=None,
                       capacidad_t_h=None, base: str = "recepcion", programa: dict | None = None, dist_descarga: dict | None = None) -> dict:
    """Simulación de eventos discretos de la cola de camiones en el patio durante la temporada.

    La temporada trae un número entero de camiones de carga igual (la carga declarada, ajustada para que el total calce con lo
    que procesa la planta). Cada camión elige su día con probabilidad proporcional a la curva y su hora al azar dentro de las
    horas de operación: es un proceso de Poisson no homogéneo condicionado al total, así que el número de camiones de cada día
    varía alrededor de la curva y, localmente, las llegadas son de Poisson (ca = 1 en la ecuación de Kingman).
    Se atienden en orden de llegada con la capacidad de recepción: la del primer equipo de la línea (base «recepcion») o la de
    la restricción de la línea expresada en materia prima (base «linea»); capacidad_t_h la reemplaza. El tiempo de descarga
    tiene media carga/capacidad y coeficiente de variación cv_servicio. Con programa, la recepción solo atiende en las horas
    de producción. El tomate que espera más que el umbral pierde tasa_h por hora sobre el umbral (se descarta al descargar).
    Al cierre de la temporada, lo que no se alcanzó a descargar queda en cola.
    PAT 134: dist_descarga (dict de motor/ajuste.py, en h para la carga media del camión) reemplaza la gamma con cv_servicio:
    el tiempo de cada camión se muestrea de ella y se escala por la carga neta; la capacidad de recepción pasa a ser la carga
    media dividida por la media de la distribución y cs su coeficiente de variación. esperas_h trae la espera de cada camión."""
    d = datos_planta(pl); sp = supuestos(pl); D, H = d["D"], d["H"]; T = 24.0 * D
    rng = random.Random(semilla)
    camion = sp["camion"] if camion_t is None else float(camion_t)
    cv = sp["cv_servicio"] if cv_servicio is None else max(0.0, float(cv_servicio))
    umbral = sp["umbral"] if umbral_h is None else float(umbral_h)
    tasa = sp["tasa"] if tasa_h is None else max(0.0, float(tasa_h))
    avisos = []
    if capacidad_t_h:
        cap = float(capacidad_t_h); origen = "Capacidad ingresada por el usuario"
    elif base == "linea" and capacidad_linea(pl):
        cap = capacidad_linea(pl); ln = _linea(pl)
        origen = f"Recurso crítico de la línea ({(ln or {}).get('critico') or 'sin dato'}) expresado en materia prima"
    elif d["cap_primero"]:
        cap = float(d["cap_primero"]); origen = f"Capacidad efectiva de {d['nombre_primero']} ({d['primero']}), escenarios/capacidades.py"
    else:
        cap = d["carga"] * 1.10
        origen = "Supuesto: el primer equipo no tiene capacidad declarada; se usa la carga de diseño × 1,10 (holgura de lienzo.asignar_capacidades)"
        avisos.append("El primer equipo de la línea no tiene capacidad: se usó la carga de diseño con 10 % de holgura.")
    if cap <= 0 or camion <= 0:
        raise ValueError("La capacidad de recepción y la carga del camión deben ser positivas.")
    curva = curva_llegada(pl, pico, ancho)
    n_tot = max(1, int(round(d["total"] / camion))); m = d["total"] / n_tot
    if dist_descarga is not None:                # PAT 134: tiempo de descarga ajustado a datos medidos
        from . import ajuste as AJ
        te_d = AJ.media(dist_descarga)
        if not te_d or te_d <= 0:
            raise ValueError("La distribución del tiempo de descarga debe tener media positiva.")
        cap = m / te_d; cv = AJ.desviacion(dist_descarga) / te_d
        origen = (f"Distribución ajustada del tiempo de descarga ({AJ.expresion(dist_descarga)}): media de {_cl(te_d, 3)} h por camión de "
                  f"{_cl(m, 1)} t")
    dia_camion = rng.choices(range(D), weights=curva, k=n_tot)
    llegadas = sorted(24.0 * k + rng.random() * H for k in dia_camion)
    n_dia = [0] * D
    for k in dia_camion:
        n_dia[k] += 1
    w = _ventanas(pl, d, programa)
    te = m / cap
    proc = [0.0] * D; deg = [0.0] * D; esperas = []; ev = []; j = 0; libre = 0.0
    for a in llegadas:
        if dist_descarga is None:
            factor = rng.gammavariate(1 / cv ** 2, cv ** 2) if cv > 0 else 1.0
        else:
            factor = max(0.0, AJ.muestrear(dist_descarga, rng)) / te_d
        t = max(a, libre)
        while j < len(w) and w[j][1] <= t + 1e-12:
            j += 1
        inicio = max(t, w[j][0]) if j < len(w) else math.inf
        if inicio >= T:                          # no alcanza a descargar en la temporada
            fr = min(1.0, tasa * max(0.0, T - a - umbral)); deg[D - 1] += m * fr
            esperas.append(T - a); ev += [(a, 1), (T, -1)]
            libre = math.inf; continue
        espera = inicio - a; esperas.append(espera)
        if espera > 1e-12:
            ev += [(a, 1), (inicio, -1)]
        fr = min(1.0, tasa * max(0.0, espera - umbral))
        deg[min(D - 1, int(inicio // 24))] += m * fr
        neto = m * (1 - fr); s = neto / cap * factor
        if s <= 1e-12 or neto <= 0:
            proc[min(D - 1, int(inicio // 24))] += max(0.0, neto)
            libre = inicio; continue
        tasa_proc = neto / s; resto = s; k = j; x = inicio
        while resto > 1e-12 and k < len(w):
            x = max(x, w[k][0]); y = min(w[k][1], x + resto)
            if y > x:
                _repartir(proc, x, y, tasa_proc); resto -= y - x
            if resto > 1e-12:
                k += 1
            x = y
        if resto > 1e-12:                        # la temporada terminó durante la descarga: lo no descargado sigue en el patio
            libre = math.inf
        else:
            libre = x
    # barrido de la cola (camiones esperando, sin contar el que descarga): promedio y máximo por día y muestra hora a hora
    ev.sort(key=lambda e: (e[0], e[1]))
    integ = [0.0] * D; maxd = [0] * D; hor = [0] * int(round(T)); n = 0; p = 0.0; ih = 0
    for t, dl in ev + [(T, 0)]:
        t = min(t, T)
        if t > p:                                # n camiones esperan en [p, t)
            _repartir(integ, p, t, n)
            for k in range(int(p // 24), min(D, int(math.ceil(t / 24)))):
                maxd[k] = max(maxd[k], n)
            while ih < len(hor) and ih < t:      # muestra hora a hora (al inicio de cada hora)
                hor[ih] = n; ih += 1
        n += dl; p = t
    # resultado por día
    dias, cola, i0 = [], 0.0, 0
    disp = [0.0] * D
    for x, y in w:
        _repartir(disp, x, y, 1.0)
    for k in range(D):
        nk = n_dia[k]; esp_k = esperas[i0:i0 + nk]; i0 += nk
        lleg = nk * m; cola += lleg - proc[k] - deg[k]
        u = curva[k] / cap / disp[k] if disp[k] > 0 else math.inf      # utilización esperada del día (con la curva)
        wk = K.kingman(u, 1.0, cv, te) if nk else 0.0
        dias.append(dict(dia=k + 1, camiones=nk, esperada_t=curva[k], llegada_t=lleg, procesado_t=proc[k], degradado_t=deg[k],
                         cola_t=max(0.0, cola),
                         camiones_espera_prom=integ[k] / 24.0, camiones_espera_max=maxd[k], espera_media_h=sum(esp_k) / nk if nk else 0.0,
                         kingman_h=None if math.isinf(wk) else wk, utilizacion=u))
    tot_l = n_tot * m; tot_p = sum(proc); tot_d = sum(deg)
    W = sum(esperas) / len(esperas) if esperas else 0.0
    lam = len(llegadas) / T; L = sum(integ) / T
    u_med = tot_l / cap / sum(disp) if sum(disp) else math.inf
    if pl.rubro != "tomate" or len(set(round(x, 9) for x in curva)) == 1:
        wk = K.kingman(u_med, 1.0, cv, te)            # llegada pareja: Kingman con la utilización de la temporada
        wk = None if math.isinf(wk) else wk
    else:                                             # curva variable: Kingman de cada día, ponderado por los camiones
        estables = [x for x in dias if x["kingman_h"] is not None and x["camiones"]]
        wk = sum(x["kingman_h"] * x["camiones"] for x in estables) / sum(x["camiones"] for x in estables) if estables else None
    con_rec = [x for x, dk in zip(dias, disp) if dk > 0]
    u_pk = max((x["utilizacion"] for x in con_rec), default=0.0)
    sin_rec = sum(1 for x, dk in zip(dias, disp) if dk <= 0 and x["camiones"])
    if u_pk >= 1:
        avisos.append(f"En el día de más llegada la utilización esperada de la recepción es {_cl(100 * u_pk, 0)} %: ese día la cola crece "
                      "sin límite y la ecuación de Kingman no aplica.")
    if sin_rec:
        avisos.append(("Un día con llegada de camiones no tiene" if sin_rec == 1 else f"{sin_rec} días con llegada de camiones no tienen")
                      + " horas de recepción en el programa (paradas): los camiones esperan al día siguiente.")
    cola_fin = tot_l - tot_p - tot_d
    if cola_fin > 1e-6:
        avisos.append(f"Al cierre de la temporada quedan {_cl(cola_fin, 1)} t sin descargar en el patio.")
    return dict(dias=dias, por_hora=hor, camiones=n_tot, carga_camion_t=m, capacidad_t_h=cap, origen_capacidad=origen,
                servicio_medio_h=te, total_llegada_t=tot_l, total_procesado_t=tot_p, total_degradado_t=tot_d, cola_final_t=cola_fin,
                espera_media_h=W, espera_max_h=max(esperas) if esperas else 0.0, espera_kingman_h=wk, esperas_h=list(esperas),
                utilizacion_media=u_med, utilizacion_peak=u_pk,
                little=dict(lambda_por_h=lam, W_h=W, L_integrada=L, L_horaria=sum(hor) / len(hor) if hor else 0.0, L_little=K.little(lam, W)),
                parametros=dict(semilla=semilla, camion_t=camion, cv_servicio=cv, umbral_h=umbral, tasa_h=tasa, base=base,
                                con_programa=programa is not None,
                                dist_descarga=None if dist_descarga is None else dist_descarga.get("expresion") or dist_descarga["nombre"]),
                avisos=avisos)
