"""Demanda de la planta con métodos de ingeniería (PAT 136, tarea T21, 13-11-2026).

Punto 4 de los comentarios del profesor Torres (13-11-2026): «tomate según la producción agrícola; agar agar según el
mercado». Este módulo tiene las dos lógicas y el catálogo de 10 perfiles de demanda que usa la base genérica (T20).

(a) Demanda empujada por la oferta agrícola (oferta_agricola): superficie (ha) × rendimiento (t/ha) = cosecha de la
    temporada; la curva de cosecha la reparte en los días de operación (normal truncada, la misma campana de
    motor/temporada.curva_llegada, o triangular); cada día la planta procesa lo más antiguo primero (FIFO) hasta su
    capacidad de recepción (t/h × horas del día). La materia prima que espera se degrada a una tasa por hora sobre un
    umbral y se descarta si supera la perecibilidad máxima. Cierre de masa: cosechado = procesado + perdido. Entrega la
    serie diaria o semanal que llega, lo procesado, lo perdido y la capacidad necesaria (pico, percentil y la menor
    capacidad que cumple una pérdida máxima).
(b) Demanda tirada por el mercado: pronóstico con series de tiempo en Python puro (Holt-Winters aditivo y multiplicativo,
    descomposición clásica con tendencia lineal y regresión con tendencia), errores MAD, MSE, MAPE, sesgo y señal de
    rastreo (RSFE / MAD), estrategias de capacidad (adelantarse, seguir y rezagarse a la demanda) y plan agregado con
    inventario (nivelación contra persecución) con costos de mantener inventario, de cambiar la tasa y de faltante.
(c) PERFILES: 10 perfiles con identificador fijo, parámetros por defecto con su fuente o «Supuesto» y su generador.
    generar(perfil_id, params, semilla) y listar_perfiles().
(d) Funciones puras: los números aleatorios salen solo de random.Random(semilla) (semilla None = SEMILLA_DEFECTO).

Compatibilidad: con periodo «día» la serie tiene el mismo formato que la demanda de un desafío (motor/desafio.py: lista de t
por período) y, con cv = 0, la curva normal es idéntica a temporada.curva_llegada. a_desafio(resultado) arma un desafío que
pasa desafio.validar, de modo que desafio.serie_demanda y desafio.demanda_t_h funcionan sin cambios.

Referencias (citas genéricas, sin páginas; los capítulos se indican cuando se conocen con seguridad):
- Hyndman, R. J. y Athanasopoulos, G. (2021). Forecasting: principles and practice (3.ª ed.). OTexts. https://otexts.com/fpp3/
  (descomposición clásica y método de Holt-Winters aditivo y multiplicativo).
- Heizer, J., Render, B. y Munson, C. (2017). Operations management: sustainability and supply chain management (12.ª ed.).
  Pearson (pronóstico: MAD, MAPE y señal de rastreo; capacidad: adelantarse, rezagarse o seguir a la demanda; planeación
  agregada: estrategia de nivelación y de persecución, cap. 13, la misma cita de motor/mc_economico.py).
- Jacobs, F. R. y Chase, R. B. Operations and supply chain management. McGraw-Hill Education (planeación estratégica de la
  capacidad y planeación agregada; se cita la obra en general, sin edición ni capítulo, porque no está en la carpeta).
Las cifras sin fuente segura van con «Supuesto» y su justificación en los parámetros de cada perfil.
"""
from __future__ import annotations
import math
import random

SEMILLA_DEFECTO = 136                        # PAT 136: semilla fija cuando no se da una (funciones puras)
LOGICAS = ("agricola", "mercado", "mixta")
HORAS = {"hora": 1.0, "turno": 8.0, "día": 24.0, "semana": 168.0, "mes": 730.0, "año": 8760.0}   # las de desafio.PERIODOS
MESES = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
LIMITE_SENAL = 4.0                           # señal de rastreo: límite habitual de ±4 MAD (Heizer, Render y Munson, 2017)
_SD = "sin dato de una planta ni fuente segura en la carpeta del proyecto"


# ================================================================== utilidades
def _rng(semilla) -> random.Random:
    return random.Random(SEMILLA_DEFECTO if semilla is None else int(semilla))


def _ruido(rng: random.Random, cv: float) -> float:
    """Factor multiplicativo de media 1 y coeficiente de variación cv (gamma: siempre positivo). cv = 0 da 1."""
    if not cv or cv <= 0:
        return 1.0
    k = 1.0 / (cv * cv)
    return rng.gammavariate(k, 1.0 / k)


def percentil(xs, p: float) -> float:
    """Percentil p (0 a 100) con interpolación lineal entre rangos (el mismo criterio por omisión de numpy)."""
    s = sorted(float(x) for x in xs)
    if not s:
        return 0.0
    if len(s) == 1:
        return s[0]
    r = (len(s) - 1) * min(100.0, max(0.0, float(p))) / 100.0
    i = int(math.floor(r)); f = r - i
    return s[i] if i + 1 >= len(s) else s[i] + f * (s[i + 1] - s[i])


def estadisticas(serie, unidad: str = "t", periodo: str = "mes") -> dict:
    """Total, media, mínimo, máximo, percentil 95, desviación y coeficiente de variación de una serie."""
    s = [float(x) for x in serie]; n = len(s)
    if not n:
        return dict(n=0, total=0.0, media=0.0, minimo=0.0, maximo=0.0, p95=0.0, desviacion=0.0, cv=0.0, i_max=None,
                    unidad=unidad, periodo=periodo)
    m = sum(s) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in s) / (n - 1)) if n > 1 else 0.0
    return dict(n=n, total=sum(s), media=m, minimo=min(s), maximo=max(s), p95=percentil(s, 95), desviacion=sd,
                cv=sd / m if m else 0.0, i_max=max(range(n), key=lambda i: s[i]), unidad=unidad, periodo=periodo)


def _pesos_curva(n: int, curva: str, pico: float, ancho: float) -> list[float]:
    """Pesos (suman 1) de la cosecha en n períodos. «normal»: campana truncada a la temporada con media pico·(n − 1) y
    desviación ancho·n (la misma fórmula de temporada.curva_llegada). «triangular»: cero un ancho·n antes y después del pico.
    «pareja»: igual en todos los períodos."""
    if n <= 0:
        return []
    if curva == "pareja":
        return [1.0 / n] * n
    mu = float(pico) * (n - 1)
    if curva == "triangular":
        a = max(1e-6, float(ancho) * n)
        w = [max(0.0, 1.0 - abs(i - mu) / a) for i in range(n)]
    elif curva == "normal":
        sig = max(1e-6, float(ancho) * n)
        w = [math.exp(-0.5 * ((i - mu) / sig) ** 2) for i in range(n)]
    else:
        raise ValueError(f"Curva de cosecha desconocida: {curva!r}. Use normal, triangular o pareja")
    s = sum(w)
    if s <= 0:
        return [1.0 / n] * n
    return [x / s for x in w]


def agrupar(serie, tam: int) -> list[float]:
    """Suma la serie en grupos consecutivos de tam elementos (el último puede quedar incompleto)."""
    tam = max(1, int(tam))
    return [sum(serie[i:i + tam]) for i in range(0, len(serie), tam)]


# ================================================================== (a) oferta agrícola
def oferta_agricola(superficie_ha: float, rendimiento_t_ha: float, dias: int, horas_dia: float = 24.0,
                    curva: str = "normal", pico: float = 0.5, ancho: float = 0.25, cv: float = 0.0,
                    capacidad_t_h: float | None = None, umbral_h: float = 6.0, tasa_perdida_h: float = 0.0,
                    perecibilidad_h: float = 48.0, periodo: str = "día", dias_semana: int = 7,
                    factor_producto: float = 1.0, percentil_cap: float = 95.0, pesos=None, semilla=None) -> dict:
    """Llegada de materia prima empujada por la cosecha y lo que la planta alcanza a procesar.

    Modelo diario con lotes por edad (FIFO): la cosecha del día d llega ese día; cada día se procesa hasta capacidad_t_h ×
    horas_dia, primero lo más antiguo. Un lote que espera k días (24·k h) pierde la fracción tasa_perdida_h × (24·k − umbral_h)
    cuando se procesa, y se descarta entero si 24·k supera perecibilidad_h. Lo cosechado el mismo día se supone procesado sin
    espera relevante. Después del último día de cosecha la planta sigue hasta vaciar el patio (o hasta que lo que queda se
    descarta). Sin capacidad (None) se procesa todo el mismo día.
    cv: variación diaria de la cosecha por el clima (gamma de media 1); la serie se reescala para que la cosecha total siga
    siendo superficie × rendimiento. pesos: lista de dias pesos que reemplaza a la curva (por ejemplo, dos variedades).
    Devuelve las series por período (día de operación, o semana de dias_semana días de operación) en t de materia prima, la
    serie en t/h (t del período / horas de operación del período) y el balance."""
    D = int(round(float(dias)))
    if D < 1 or not 0 < float(horas_dia) <= 24:
        raise ValueError("La temporada necesita al menos 1 día y entre 0 y 24 horas de operación por día")
    if superficie_ha < 0 or rendimiento_t_ha < 0:
        raise ValueError("La superficie y el rendimiento no pueden ser negativos")
    if periodo not in ("día", "semana"):
        raise ValueError("La oferta agrícola se entrega por «día» o por «semana»")
    H = float(horas_dia); total = float(superficie_ha) * float(rendimiento_t_ha)
    if pesos is not None:
        if len(pesos) != D or any(float(x) < 0 for x in pesos) or sum(float(x) for x in pesos) <= 0:
            raise ValueError("Los pesos de la cosecha deben ser uno por día, no negativos y con suma positiva")
        w = [float(x) for x in pesos]
    else:
        w = _pesos_curva(D, curva, pico, ancho)
    rng = _rng(semilla)
    w = [x * _ruido(rng, cv) for x in w]
    s = sum(w) or 1.0
    cosecha = [total * x / s for x in w]
    cap_dia = math.inf if capacidad_t_h is None or capacidad_t_h <= 0 else float(capacidad_t_h) * H
    lotes = []                                   # [edad en días, t]
    proc, perd, patio = [], [], []
    d = 0; dias_max = D + int(math.ceil(max(0.0, perecibilidad_h) / 24.0)) + 2
    while d < D or (lotes and d < dias_max):
        for L in lotes:
            L[0] += 1
        if d < D:
            lotes.append([0, cosecha[d]])
        p_d = 0.0; x_d = 0.0
        vivos = []
        for edad, m in lotes:                    # descarte por perecibilidad
            if 24.0 * edad > perecibilidad_h + 1e-9:
                x_d += m
            else:
                vivos.append([edad, m])
        lotes = sorted(vivos, key=lambda L: -L[0])
        libre = cap_dia
        for L in lotes:
            if libre <= 1e-12:
                break
            q = min(L[1], libre); libre -= q; L[1] -= q
            f = min(1.0, max(0.0, tasa_perdida_h * (24.0 * L[0] - umbral_h))) if L[0] > 0 else 0.0
            p_d += q * (1.0 - f); x_d += q * f
        lotes = [L for L in lotes if L[1] > 1e-9]
        if d >= D and not lotes and p_d <= 0 and x_d <= 0:
            break
        proc.append(p_d); perd.append(x_d); patio.append(sum(L[1] for L in lotes))
        d += 1
    resto = sum(L[1] for L in lotes)             # lo que queda al cortar la simulación se cuenta como perdido
    if resto > 0:
        perd[-1] += resto; patio[-1] = 0.0
    n = len(proc)
    llegada_d = cosecha + [0.0] * (n - D)
    tam = 1 if periodo == "día" else max(1, int(dias_semana))
    ag = (lambda xs: list(xs)) if tam == 1 else (lambda xs: agrupar(xs, tam))
    llegada, procesado, perdido = ag(llegada_d), ag(proc), ag(perd)
    horas_p = [H * min(tam, n - i * tam) for i in range(len(llegada))]
    t_h = [v / h for v, h in zip(llegada, horas_p)]
    tasa_dia = [c / H for c in cosecha]          # t/h que llega cada día de cosecha
    pico_t_h = max(tasa_dia) if tasa_dia else 0.0
    etq = (lambda i: f"Día {i + 1}") if tam == 1 else (lambda i: f"Semana {i + 1}")
    return dict(
        periodo=periodo, unidad="t", horas_dia=H, dias_cosecha=D, dias_semana=tam,
        etiquetas=[etq(i) for i in range(len(llegada))], serie=llegada, serie_t_h=t_h, procesado=procesado, perdido=perdido,
        serie_producto=[v * float(factor_producto) for v in procesado], patio_diario=patio,
        llegada_diaria=llegada_d, procesado_diario=proc, perdido_diario=perd,
        balance=dict(cosechado=total, procesado=sum(proc), perdido=sum(perd), fraccion_perdida=sum(perd) / total if total else 0.0,
                     producto=sum(proc) * float(factor_producto)),
        capacidad=dict(pico_t_h=pico_t_h, percentil_t_h=percentil(tasa_dia, percentil_cap), percentil=percentil_cap,
                       media_t_h=total / (D * H), capacidad_t_h=None if cap_dia == math.inf else float(capacidad_t_h),
                       utilizacion=(sum(proc) / (cap_dia * n)) if cap_dia != math.inf and n else None))


def capacidad_para_perdida(perdida_max: float = 0.01, tol: float = 1e-3, **kw) -> float:
    """Menor capacidad de recepción (t/h) con la que la fracción perdida de la temporada no supera perdida_max (bisección
    entre 0 y el pico de llegada). kw: los mismos parámetros de oferta_agricola, salvo capacidad_t_h."""
    kw = dict(kw); kw.pop("capacidad_t_h", None)
    base = oferta_agricola(capacidad_t_h=None, **kw)
    hi = base["capacidad"]["pico_t_h"]
    if hi <= 0:
        return 0.0
    lo = 0.0
    if oferta_agricola(capacidad_t_h=hi, **kw)["balance"]["fraccion_perdida"] > perdida_max:
        return hi                                # ni con el pico se cumple (la degradación por espera lo impide)
    for _ in range(60):
        mid = 0.5 * (lo + hi)
        if oferta_agricola(capacidad_t_h=mid, **kw)["balance"]["fraccion_perdida"] <= perdida_max:
            hi = mid
        else:
            lo = mid
        if hi - lo <= tol * max(1.0, hi):
            break
    return hi


def desde_planta(pl) -> dict:
    """Parámetros de oferta_agricola tomados de la planta (días, horas por día y total de la temporada de su alimentación) y
    de motor/temporada.SUPUESTOS (pico y ancho de la campana en tomate). La superficie queda en 1 ha con un rendimiento igual
    al total: así la cosecha de la temporada es la que procesa la planta."""
    from . import temporada as TM
    d = TM.datos_planta(pl); sp = TM.supuestos(pl)
    curva = "normal" if pl.rubro == "tomate" else "pareja"
    return dict(superficie_ha=1.0, rendimiento_t_ha=d["total"], dias=d["D"], horas_dia=d["H"], curva=curva,
                pico=sp.get("pico", 0.5), ancho=sp.get("ancho", 0.25), cv=0.0, capacidad_t_h=None)


# ================================================================== (b) mercado: pronóstico
def regresion_lineal(y, x=None) -> tuple[float, float]:
    """Mínimos cuadrados de y = a + b·x (x = 0, 1, 2, … si no se da). Devuelve (a, b)."""
    y = [float(v) for v in y]; n = len(y)
    x = list(range(n)) if x is None else [float(v) for v in x]
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return y[0], 0.0
    mx = sum(x) / n; my = sum(y) / n
    sxx = sum((a - mx) ** 2 for a in x)
    b = sum((a - mx) * (c - my) for a, c in zip(x, y)) / sxx if sxx else 0.0
    return my - b * mx, b


def descomposicion_clasica(y, m: int, tipo: str = "multiplicativo") -> dict:
    """Descomposición clásica (Hyndman y Athanasopoulos, 2021): tendencia-ciclo con media móvil centrada 2×m (m par) o m
    (impar), índices estacionales promedio por posición normalizados (suman 0 en aditivo, promedian 1 en multiplicativo) y
    recta de tendencia ajustada por mínimos cuadrados a la serie desestacionalizada. Necesita al menos 2·m datos."""
    y = [float(v) for v in y]; n = len(y); m = int(m)
    if m < 2 or n < 2 * m:
        raise ValueError(f"La descomposición necesita al menos {2 * m} datos (dos estaciones completas de {m})")
    mult = tipo.startswith("mult")
    if mult and min(y) <= 0:
        raise ValueError("La descomposición multiplicativa necesita datos mayores que cero")
    tc = [None] * n
    if m % 2 == 0:
        k = m // 2
        for t in range(k, n - k):
            tc[t] = (0.5 * y[t - k] + sum(y[t - k + 1:t + k]) + 0.5 * y[t + k]) / m
    else:
        k = m // 2
        for t in range(k, n - k):
            tc[t] = sum(y[t - k:t + k + 1]) / m
    por_pos = [[] for _ in range(m)]
    for t in range(n):
        if tc[t] is not None:
            por_pos[t % m].append(y[t] / tc[t] if mult else y[t] - tc[t])
    s = [sum(v) / len(v) if v else (1.0 if mult else 0.0) for v in por_pos]
    if mult:
        f = m / sum(s); s = [v * f for v in s]
    else:
        c = sum(s) / m; s = [v - c for v in s]
    desest = [y[t] / s[t % m] if mult else y[t] - s[t % m] for t in range(n)]
    a, b = regresion_lineal(desest)
    ajuste = [(a + b * t) * s[t % m] if mult else a + b * t + s[t % m] for t in range(n)]
    return dict(tipo="multiplicativo" if mult else "aditivo", m=m, tendencia_ciclo=tc, estacional=s, desestacionalizada=desest,
                a=a, b=b, ajuste=ajuste)


def pronostico_descomposicion(y, m: int, h: int, tipo: str = "multiplicativo") -> dict:
    """Pronóstico con la descomposición clásica: recta de tendencia extendida × (o +) el índice estacional del período."""
    dc = descomposicion_clasica(y, m, tipo); n = len(y); mult = dc["tipo"] == "multiplicativo"
    fc = []
    for j in range(1, int(h) + 1):
        t = n - 1 + j; base = dc["a"] + dc["b"] * t; s = dc["estacional"][t % m]
        fc.append(max(0.0, base * s if mult else base + s))
    return dict(dc, metodo=f"Descomposición clásica {dc['tipo']}", pronostico=fc)


def pronostico_regresion(y, h: int, m: int | None = None) -> dict:
    """Regresión con tendencia lineal (sin estacionalidad): y = a + b·t extendida h períodos."""
    a, b = regresion_lineal(y); n = len(y)
    return dict(metodo="Regresión con tendencia", a=a, b=b, ajuste=[a + b * t for t in range(n)],
                pronostico=[max(0.0, a + b * (n - 1 + j)) for j in range(1, int(h) + 1)])


def _inicio_hw(y, m: int, tipo: str) -> tuple[float, float, list]:
    """Valores iniciales de Holt-Winters con la descomposición clásica de las primeras estaciones (como recomienda Hyndman y
    Athanasopoulos, 2021): nivel y tendencia de la recta en t = −1 e índices estacionales normalizados."""
    n_ini = min(len(y), max(2 * m, min(len(y), 4 * m)))
    dc = descomposicion_clasica(y[:n_ini], m, tipo)
    l0 = dc["a"] - dc["b"]; b0 = dc["b"]
    return l0, b0, list(dc["estacional"])


def holt_winters(y, m: int, alfa: float = 0.3, beta: float = 0.1, gamma: float = 0.2, tipo: str = "aditivo",
                 h: int = 12) -> dict:
    """Suavizamiento exponencial de Holt-Winters con tendencia aditiva y estacionalidad aditiva o multiplicativa
    (Hyndman y Athanasopoulos, 2021, forma de componentes). Devuelve el ajuste un paso adelante (el pronóstico de cada
    período hecho con los datos hasta el anterior), el pronóstico de h períodos y los componentes finales.
    Necesita al menos 2·m datos (el arranque usa la descomposición clásica)."""
    y = [float(v) for v in y]; n = len(y); m = int(m)
    mult = tipo.startswith("mult")
    if mult and min(y) <= 0:
        raise ValueError("Holt-Winters multiplicativo necesita datos mayores que cero")
    for nom, v in (("alfa", alfa), ("beta", beta), ("gamma", gamma)):
        if not 0 <= v <= 1:
            raise ValueError(f"{nom} debe estar entre 0 y 1")
    l, b, s0 = _inicio_hw(y, m, "multiplicativo" if mult else "aditivo")
    s = list(s0)                                 # s[t % m] es el índice vigente de la posición
    ajuste = []
    for t in range(n):
        st_ = s[t % m] if not mult else max(1e-12, s[t % m])
        yhat = (l + b) * st_ if mult else l + b + st_
        ajuste.append(yhat)
        l_ant, b_ant = l, b
        if mult:
            l = alfa * (y[t] / st_) + (1 - alfa) * (l_ant + b_ant)
            s[t % m] = gamma * (y[t] / max(1e-12, l_ant + b_ant)) + (1 - gamma) * st_
        else:
            l = alfa * (y[t] - st_) + (1 - alfa) * (l_ant + b_ant)
            s[t % m] = gamma * (y[t] - l_ant - b_ant) + (1 - gamma) * st_
        b = beta * (l - l_ant) + (1 - beta) * b_ant
    fc = []
    for j in range(1, int(h) + 1):
        st_ = s[(n - 1 + j) % m]
        fc.append(max(0.0, (l + j * b) * st_ if mult else l + j * b + st_))
    return dict(metodo=f"Holt-Winters {'multiplicativo' if mult else 'aditivo'}", tipo="multiplicativo" if mult else "aditivo",
                m=m, alfa=alfa, beta=beta, gamma=gamma, nivel=l, tendencia=b, estacional=list(s), estacional_inicial=s0,
                ajuste=ajuste, pronostico=fc)


def croston(y, alfa: float = 0.1, h: int = 12) -> dict:
    """Método de Croston para demanda intermitente: suaviza por separado el tamaño de los pedidos (z) y el intervalo entre
    pedidos (p); el pronóstico por período es z / p (Hyndman y Athanasopoulos, 2021, demanda intermitente)."""
    y = [float(v) for v in y]; n = len(y)
    if not 0 < alfa <= 1:
        raise ValueError("alfa debe estar entre 0 y 1")
    nz = [i for i, v in enumerate(y) if v > 0]
    if not nz:
        return dict(metodo="Croston", ajuste=[0.0] * n, pronostico=[0.0] * int(h), z=0.0, p=1.0, alfa=alfa)
    z = y[nz[0]]; p = float(nz[0] + 1); q = 1; ajuste = []
    for t in range(n):
        ajuste.append(z / p if t > nz[0] else 0.0)
        if t > nz[0]:
            if y[t] > 0:
                z = alfa * y[t] + (1 - alfa) * z; p = alfa * q + (1 - alfa) * p; q = 1
            else:
                q += 1
    return dict(metodo="Croston", z=z, p=p, alfa=alfa, ajuste=ajuste, pronostico=[z / p] * int(h))


def errores(real, pronostico, limite: float = LIMITE_SENAL) -> dict:
    """Errores de pronóstico (error = real − pronóstico): MAD, MSE, MAPE (%, solo en los períodos con real distinto de cero),
    sesgo (error medio), RSFE (suma acumulada de errores) y señal de rastreo RSFE / MAD acumulado de cada período, con el
    límite habitual de ±4 MAD (Heizer, Render y Munson, 2017). fuera_de_control: algún período sale del límite."""
    r = [float(v) for v in real]; f = [float(v) for v in pronostico]
    if len(r) != len(f):
        raise ValueError(f"Hay {len(r)} valores reales y {len(f)} pronósticos")
    n = len(r)
    if not n:
        return dict(n=0, mad=0.0, mse=0.0, mape=0.0, sesgo=0.0, rsfe=0.0, senal=[], senal_max=0.0, fuera_de_control=False, limite=limite)
    e = [a - b for a, b in zip(r, f)]
    pares = [(abs(x) / abs(a)) for x, a in zip(e, r) if a != 0]
    senal = []; acum = 0.0; abs_acum = 0.0
    for i, x in enumerate(e, 1):
        acum += x; abs_acum += abs(x); mad_i = abs_acum / i
        senal.append(acum / mad_i if mad_i > 1e-12 else 0.0)
    smax = max((abs(v) for v in senal), default=0.0)
    return dict(n=n, mad=sum(abs(x) for x in e) / n, mse=sum(x * x for x in e) / n,
                mape=100.0 * sum(pares) / len(pares) if pares else 0.0, sesgo=sum(e) / n, rsfe=sum(e), senal=senal,
                senal_max=smax, fuera_de_control=smax > limite, limite=limite)


METODOS = {"hw_aditivo": "Holt-Winters aditivo", "hw_multiplicativo": "Holt-Winters multiplicativo",
           "descomposicion": "Descomposición clásica multiplicativa", "regresion": "Regresión con tendencia", "croston": "Croston (intermitente)"}
_REJ_A = (0.05, 0.1, 0.2, 0.3, 0.5, 0.7, 0.9)
_REJ_B = (0.01, 0.05, 0.1, 0.2, 0.3)
_REJ_G = (0.05, 0.1, 0.2, 0.3, 0.5)


def optimizar_hw(y, m: int, tipo: str = "aditivo", h: int = 12) -> dict:
    """Holt-Winters con alfa, beta y gamma elegidos en una rejilla (175 combinaciones) que minimiza el error cuadrático medio
    del ajuste un paso adelante desde la segunda estación (la primera la fija el arranque)."""
    y = [float(v) for v in y]; mejor = None
    for a in _REJ_A:
        for b in _REJ_B:
            for g in _REJ_G:
                r = holt_winters(y, m, a, b, g, tipo, h)
                ecm = sum((y[t] - r["ajuste"][t]) ** 2 for t in range(m, len(y))) / max(1, len(y) - m)
                if mejor is None or ecm < mejor[0] - 1e-12:
                    mejor = (ecm, r)
    r = dict(mejor[1]); r["ecm"] = mejor[0]
    return r


def pronosticar(y, m: int, metodo: str = "hw_multiplicativo", h: int = 12, optimizar: bool = True, alfa: float = 0.3,
                beta: float = 0.1, gamma: float = 0.2) -> dict:
    """Pronóstico de h períodos con el método elegido (claves de METODOS). Devuelve ajuste, pronóstico y método."""
    if metodo not in METODOS:
        raise ValueError(f"Método desconocido: {metodo!r}. Use uno de: {', '.join(METODOS)}")
    y = [float(v) for v in y]
    if metodo.startswith("hw_"):
        tipo = "aditivo" if metodo == "hw_aditivo" else "multiplicativo"
        r = optimizar_hw(y, m, tipo, h) if optimizar else holt_winters(y, m, alfa, beta, gamma, tipo, h)
    elif metodo == "descomposicion":
        r = pronostico_descomposicion(y, m, h, "multiplicativo")
    elif metodo == "regresion":
        r = pronostico_regresion(y, h)
    else:
        r = croston(y, alfa if not optimizar else 0.1, h)
    r = dict(r); r["clave"] = metodo; r["nombre"] = METODOS[metodo]
    return r


def metodos_validos(y, m: int) -> list[str]:
    """Métodos que se pueden usar con la serie: los estacionales piden 2·m datos y los multiplicativos datos positivos."""
    y = [float(v) for v in y]; out = []
    est = m >= 2 and len(y) >= 2 * m
    pos = bool(y) and min(y) > 0
    if est:
        out.append("hw_aditivo")
        if pos:
            out += ["hw_multiplicativo", "descomposicion"]
    if len(y) >= 2:
        out.append("regresion")
    if y and any(v == 0 for v in y):
        out.append("croston")
    return out


def evaluar_metodos(y, m: int, n_prueba: int | None = None, metodos=None) -> list[dict]:
    """Compara los métodos con una partición de prueba: ajusta con los primeros datos, pronostica los últimos n_prueba (por
    omisión una estación) y mide los errores contra lo real. Ordenado de menor a mayor MAD."""
    y = [float(v) for v in y]
    n_prueba = int(n_prueba or m)
    ent = y[:-n_prueba] if 0 < n_prueba < len(y) else y
    prueba = y[len(ent):]
    out = []
    for k in (metodos or metodos_validos(ent, m)):
        if k not in metodos_validos(ent, m):
            continue
        r = pronosticar(ent, m, k, len(prueba))
        e = errores(prueba, r["pronostico"]) if prueba else errores([], [])
        out.append(dict(clave=k, nombre=METODOS[k], errores=e, pronostico=r["pronostico"], parametros={x: r[x] for x in ("alfa", "beta", "gamma") if x in r}))
    out.sort(key=lambda d: (d["errores"]["mad"], d["clave"]))
    return out


# ================================================================== (b) mercado: capacidad y plan agregado
ESTRATEGIAS = {"adelantarse": "Adelantarse a la demanda", "seguir": "Seguir a la demanda (capacidad promedio)",
               "rezagarse": "Rezagarse a la demanda"}


def estrategias_capacidad(demanda, capacidad_inicial: float | None = None, bloque: float | None = None, adelanto: int = 1,
                          costo_capacidad: float = 0.0, costo_expansion: float = 0.0, margen: float = 0.0) -> dict:
    """Las tres estrategias clásicas de expansión de capacidad en bloques (Heizer, Render y Munson, 2017; Jacobs y Chase):
    adelantarse (la capacidad del período cubre la demanda del período y de los «adelanto» siguientes), seguir (la capacidad
    es el múltiplo del bloque más cercano a la demanda, a veces sobre y a veces bajo) y rezagarse (se agrega un bloque solo
    después de que la demanda observada superó la capacidad; la capacidad no pasa de la mayor demanda ya vista). La
    capacidad no baja (la expansión no se revierte). Capacidad en las mismas unidades por período que la demanda.
    Costos: costo_capacidad por unidad de capacidad y período, costo_expansion por bloque agregado y margen perdido por
    unidad de demanda no atendida. Devuelve, por estrategia, la serie de capacidad, producción, faltante y ocioso y el costo."""
    d = [max(0.0, float(v)) for v in demanda]; n = len(d)
    if not n:
        raise ValueError("La demanda está vacía")
    c0 = float(d[0] if capacidad_inicial is None else capacidad_inicial)
    q = float(bloque) if bloque and bloque > 0 else max(1e-9, 0.1 * max(d))
    pasos = lambda x, f: c0 + q * max(0, f((x - c0) / q - 1e-9) if f is math.ceil else f((x - c0) / q + 1e-9))
    out = {}
    for k in ESTRATEGIAS:
        cap = []; prev = c0
        for t in range(n):
            if k == "adelantarse":
                obj = pasos(max(d[t:t + int(adelanto) + 1]), math.ceil)
            elif k == "seguir":
                obj = pasos(d[t], round)
            else:
                obj = pasos(max(d[:t]), math.floor) if t > 0 else c0
            prev = max(prev, obj); cap.append(prev)
        prod = [min(a, b) for a, b in zip(d, cap)]
        falt = [a - p for a, p in zip(d, prod)]; ocio = [c - p for c, p in zip(cap, prod)]
        bloques = int(round((cap[-1] - c0) / q))
        costo = costo_capacidad * sum(cap) + costo_expansion * bloques + margen * sum(falt)
        out[k] = dict(nombre=ESTRATEGIAS[k], capacidad=cap, produccion=prod, faltante=falt, ocioso=ocio, bloques=bloques,
                      capacidad_final=cap[-1], faltante_total=sum(falt), ocioso_total=sum(ocio),
                      utilizacion=sum(prod) / sum(cap) if sum(cap) else 0.0, nivel_servicio=sum(prod) / sum(d) if sum(d) else 1.0,
                      costo_capacidad=costo_capacidad * sum(cap), costo_expansion=costo_expansion * bloques,
                      costo_faltante=margen * sum(falt), costo_total=costo)
    return dict(estrategias=out, bloque=q, capacidad_inicial=c0, adelanto=int(adelanto))


PLANES = {"nivelacion": "Nivelación (tasa constante con inventario)", "persecucion": "Persecución (la producción sigue a la demanda)"}


def plan_agregado(demanda, inventario_inicial: float = 0.0, costo_mantener: float = 0.0, costo_cambio: float = 0.0,
                  costo_faltante: float = 0.0, capacidad_max: float | None = None, tasa_inicial: float | None = None) -> dict:
    """Plan agregado (Heizer, Render y Munson, 2017, cap. 13): nivelación, una tasa constante que no deja faltantes (la mayor
    entre la demanda media neta del inventario inicial y la que exige la demanda acumulada de cada período), y persecución,
    la producción de cada período igual a su demanda neta del inventario disponible. capacidad_max limita la tasa (lo que no
    se alcanza a producir es faltante, venta perdida). Costos: mantener por unidad de inventario al final de cada período,
    cambio por unidad de variación de la tasa entre períodos (contratar, despedir, encender o apagar líneas) y faltante por
    unidad no atendida. tasa_inicial: la tasa del período anterior al plan (por omisión, la del primer período)."""
    d = [max(0.0, float(v)) for v in demanda]; n = len(d)
    if not n:
        raise ValueError("La demanda está vacía")
    I0 = max(0.0, float(inventario_inicial))
    cap = math.inf if capacidad_max is None or capacidad_max <= 0 else float(capacidad_max)
    acum = 0.0; req = 0.0
    for t, x in enumerate(d, 1):
        acum += x; req = max(req, (acum - I0) / t)
    nivel = max(0.0, req)
    out = {}
    for k in PLANES:
        inv = I0; P, I, F = [], [], []
        for t in range(n):
            p = nivel if k == "nivelacion" else max(0.0, d[t] - inv)
            p = min(p, cap)
            disp = inv + p
            f = max(0.0, d[t] - disp); inv = disp - d[t] + f
            P.append(p); I.append(inv); F.append(f)
        p_prev = P[0] if tasa_inicial is None else float(tasa_inicial)
        cambios = abs(P[0] - p_prev) + sum(abs(P[t] - P[t - 1]) for t in range(1, n))
        c_m = costo_mantener * sum(I); c_c = costo_cambio * cambios; c_f = costo_faltante * sum(F)
        out[k] = dict(nombre=PLANES[k], produccion=P, inventario=I, faltante=F, cambios=cambios, inventario_medio=sum(I) / n,
                      inventario_max=max(I), faltante_total=sum(F), costo_mantener=c_m, costo_cambio=c_c, costo_faltante=c_f,
                      costo_total=c_m + c_c + c_f, tasa_max=max(P))
    mejor = min(out, key=lambda k: out[k]["costo_total"])
    return dict(planes=out, mejor=mejor, inventario_inicial=I0)


# ================================================================== (c) perfiles
def _par(valor, unidad, fuente, nombre, opciones=None):
    return dict(valor=valor, unidad=unidad, fuente=fuente, nombre=nombre, opciones=opciones)


def _serie_mercado(n: int, m: int, base: float, indices, tendencia_anual: float, cv: float, semilla) -> list[float]:
    """y_t = base × (1 + tendencia_anual)^(t / períodos por año) × índice estacional × ruido gamma de media 1."""
    rng = _rng(semilla); por_anio = 12 if m in (12, 1) else 52
    return [max(0.0, base * (1 + tendencia_anual) ** (t / por_anio) * indices[t % len(indices)] * _ruido(rng, cv)) for t in range(n)]


def _coseno(m: int, amplitud: float, pico: int) -> list[float]:
    """Índices estacionales 1 + amplitud·cos(2π(t − pico)/m): promedian 1 y tienen el máximo en la posición pico."""
    return [1.0 + amplitud * math.cos(2 * math.pi * (t - pico) / m) for t in range(m)]


def _etq_meses(n: int, mes_inicio: int = 1) -> list[str]:
    return [f"{MESES[(mes_inicio - 1 + t) % 12]} año {(mes_inicio - 1 + t) // 12 + 1}" for t in range(n)]


def _etq_semanas(n: int) -> list[str]:
    return [f"Sem {t % 52 + 1} año {t // 52 + 1}" for t in range(n)]


def _gen_agricola(p, semilla, pesos=None):
    r = oferta_agricola(p["superficie_ha"], p["rendimiento_t_ha"], int(p["dias"]), p["horas_dia"], p.get("curva", "normal"),
                        p.get("pico", 0.5), p.get("ancho", 0.25), p["cv"], p["capacidad_t_h"], p["umbral_h"], p["tasa_perdida_h"],
                        p["perecibilidad_h"], p["periodo"], int(p["dias_semana"]), p.get("factor_producto", 1.0), 95.0, pesos, semilla)
    kw = dict(superficie_ha=p["superficie_ha"], rendimiento_t_ha=p["rendimiento_t_ha"], dias=int(p["dias"]), horas_dia=p["horas_dia"],
              curva=p.get("curva", "normal"), pico=p.get("pico", 0.5), ancho=p.get("ancho", 0.25), cv=p["cv"], umbral_h=p["umbral_h"],
              tasa_perdida_h=p["tasa_perdida_h"], perecibilidad_h=p["perecibilidad_h"], pesos=pesos, semilla=semilla)
    r["capacidad"]["para_perdida_1pct_t_h"] = capacidad_para_perdida(0.01, **kw)
    return dict(serie=r["serie"], etiquetas=r["etiquetas"], periodo=r["periodo"], serie_t_h=r["serie_t_h"], extra=r)


def _gen_fruta(p, semilla):
    D = int(p["dias"])
    t1 = _pesos_curva(D, "triangular", p["pico_temprana"], p["ancho"])
    t2 = _pesos_curva(D, "triangular", p["pico_tardia"], p["ancho"])
    f = min(1.0, max(0.0, p["fraccion_temprana"]))
    return _gen_agricola(p, semilla, [f * a + (1 - f) * b for a, b in zip(t1, t2)])


def _gen_mercado(p, semilla, indices, m=12, etq=None):
    n = int(p["n_periodos"])
    s = _serie_mercado(n, m, p["base"], indices, p.get("tendencia_anual", 0.0), p["cv"], semilla)
    return dict(serie=s, etiquetas=(etq or _etq_meses)(n), periodo="mes" if m == 12 else "semana", extra=dict(m=m, indices=list(indices)))


def _gen_agar(p, semilla):
    from ..datos.mantenedor import AGAR_DEMANDA_T
    med = sum(AGAR_DEMANDA_T) / 12.0
    base = p["demanda_anual_t"] / 12.0
    return _gen_mercado(p | dict(base=base), semilla, [v / med for v in AGAR_DEMANDA_T])


def _gen_invierno(p, semilla):
    return _gen_mercado(p, semilla, _coseno(12, p["amplitud"], int(p["mes_pico"]) - 1))


def _gen_constante(p, semilla):
    return _gen_mercado(p, semilla, [1.0] * 12)


def _gen_tendencia(p, semilla):
    return _gen_mercado(p, semilla, _coseno(12, p["amplitud"], int(p["mes_pico"]) - 1))


def _gen_contrato(p, semilla):
    rng = _rng(semilla); n = int(p["n_periodos"]); s = []
    for t in range(n):
        vol = p["base"] * (1 + p["aumento_renovacion"]) ** (t // int(p["meses_contrato"]))
        x = vol * _ruido(rng, p["cv"])
        s.append(min(vol * p["tope_sobre_contrato"], max(vol * p["minimo_take_or_pay"], x)))
    return dict(serie=s, etiquetas=_etq_meses(n), periodo="mes", extra=dict(m=12))


def _gen_exportacion(p, semilla):
    rng = _rng(semilla); n = int(p["n_periodos"]); s = []
    a, b, k = int(p["semana_inicio"]), int(p["semana_fin"]), max(1, int(p["embarque_cada"]))
    for t in range(n):
        w = t % 52 + 1
        dentro = (a <= w <= b) if a <= b else (w >= a or w <= b)
        rel = (w - a) % 52
        s.append(p["toneladas_embarque"] * _ruido(rng, p["cv"]) if dentro and rel % k == 0 else 0.0)
    return dict(serie=s, etiquetas=_etq_semanas(n), periodo="semana", extra=dict(m=52))


def _gen_impulsos(p, semilla):
    rng = _rng(semilla); n = int(p["n_periodos"]); s = []
    for _ in range(n):
        s.append(p["tamano_medio"] * _ruido(rng, p["cv_tamano"]) if rng.random() < p["probabilidad"] else 0.0)
    return dict(serie=s, etiquetas=_etq_semanas(n), periodo="semana", extra=dict(m=52))


def _gen_mixta(p, semilla):
    """Oferta agrícola en los meses de cosecha y demanda del mercado todo el año: la planta procesa en la cosecha lo que pide
    el mercado del año (limitado por la oferta) y el inventario de producto cubre los meses sin cosecha."""
    rng = _rng(semilla); meses = max(1, min(12, int(p["meses_cosecha"]))); m0 = int(p["mes_inicio_cosecha"])
    oferta_mp = p["superficie_ha"] * p["rendimiento_t_ha"]
    w = _pesos_curva(meses, "triangular", 0.5, 0.75)
    ind = _coseno(12, p["amplitud_mercado"], int(p["mes_pico_mercado"]) - 1)
    venta = [p["demanda_anual_t"] / 12.0 * ind[t] * _ruido(rng, p["cv"]) for t in range(12)]
    f = max(1e-9, p["factor_producto"])
    prod_total = min(sum(venta), oferta_mp * f)
    prod = [0.0] * 12
    for j in range(meses):
        prod[(m0 - 1 + j) % 12] = prod_total * w[j]
    orden = [(m0 - 1 + t) % 12 for t in range(12)]          # el año parte con la cosecha
    P = [prod[i] for i in orden]; V = [venta[i] for i in orden]
    acum = 0.0; peor = 0.0
    for a, b in zip(P, V):
        acum += a - b; peor = min(peor, acum)
    I0 = max(0.0, -peor); inv = []; x = I0
    for a, b in zip(P, V):
        x += a - b; inv.append(x)
    return dict(serie=P, etiquetas=[MESES[i] for i in orden], periodo="mes",
                extra=dict(m=12, demanda_mercado=V, oferta_materia_prima_t=oferta_mp, materia_prima_usada_t=prod_total / f,
                           materia_prima_sobrante_t=oferta_mp - prod_total / f, inventario=inv, inventario_inicial=I0,
                           venta_no_cubierta_t=sum(V) - prod_total, factor_producto=f))


_TOM = "Balance de Masa_Rev0.pdf, p. 6"
_SUP_T = "Supuesto de motor/temporada.py (SUPUESTOS del tomate)"
_SUP_AGAR = ("Supuesto ilustrativo, como la demanda del desafío de agar de datos/mantenedor.py (602 t al año con peak en invierno); "
             + _SD)
PERFILES = {
    "agricola_tomate": dict(
        nombre="Tomate de industria (oferta agrícola)", logica="agricola", unidad="t", periodo="día", inventariable=False,
        descripcion="La cosecha de la temporada (superficie × rendimiento) empuja la llegada diaria de tomate fresco; lo que la "
                    "recepción no alcanza a procesar espera, se degrada y se pierde si supera la perecibilidad.",
        parametros=dict(
            superficie_ha=_par(5000.0, "ha", "Derivado: 450.000 t de tomate de la temporada (DIA_Agrozzi_rev0.pdf, p. 47) / 90 t/ha", "Superficie cosechada"),
            rendimiento_t_ha=_par(90.0, "t/ha", "Supuesto: orden de magnitud del tomate de industria con riego tecnificado en la zona "
                                  "central; " + _SD + " (verificar con las estadísticas de ODEPA)", "Rendimiento"),
            dias=_par(76, "d", "Balance de Masa_Rev0.pdf, p. 6: febrero a abril, lunes a sábado", "Días de cosecha y operación"),
            horas_dia=_par(24.0, "h/d", "Tres turnos, " + _TOM, "Horas de operación por día"),
            curva=_par("normal", "", _SUP_T + ": campana normal truncada a la temporada", "Curva de cosecha", ("normal", "triangular", "pareja")),
            pico=_par(0.5, "fracción", _SUP_T + ": peak en marzo, a mitad de la temporada", "Posición del peak"),
            ancho=_par(0.25, "fracción", _SUP_T + ": desviación de la campana", "Ancho de la curva"),
            cv=_par(0.10, "", "Supuesto: variación diaria de la cosecha por clima y logística; " + _SD, "Variación diaria de la cosecha (cv)"),
            capacidad_t_h=_par(416.7, "t/h", "Derivado: 10.000 t/d de recepción (Balance de Masa_Rev0.pdf, Tabla 2, p. 11) / 24 h", "Capacidad de recepción"),
            umbral_h=_par(6.0, "h", _SUP_T + ": sobre 6 h en el patio el tomate empieza a ablandarse", "Espera sin pérdida"),
            tasa_perdida_h=_par(0.05 / 8.0, "fracción por h", _SUP_T + ": 5 % por turno de 8 h", "Pérdida por hora de espera"),
            perecibilidad_h=_par(48.0, "h", "Supuesto: sobre dos días en el patio el tomate maduro se descarta; " + _SD, "Perecibilidad máxima"),
            periodo=_par("día", "", "Supuesto: el mismo período diario del desafío de Agrozzi (datos/mantenedor.py)", "Período de la serie", ("día", "semana")),
            dias_semana=_par(6, "d", "Lunes a sábado, " + _TOM, "Días de operación por semana"),
            factor_producto=_par(1.0, "t/t", "Supuesto: la serie queda en t de tomate fresco; el paso a pasta lo hace el balance de la planta", "Factor a producto")),
        generador=_gen_agricola),
    "agricola_fruta": dict(
        nombre="Fruta para proceso, dos variedades (oferta agrícola)", logica="agricola", unidad="t", periodo="semana", inventariable=False,
        descripcion="Cosecha de una variedad temprana y una tardía (curvas triangulares) que empuja la llegada semanal de fruta a "
                    "una planta de jugo, pulpa o deshidratado; la fruta resiste más espera que el tomate.",
        parametros=dict(
            superficie_ha=_par(1200.0, "ha", "Supuesto: huertos que abastecen una planta mediana; " + _SD, "Superficie cosechada"),
            rendimiento_t_ha=_par(35.0, "t/ha", "Supuesto: orden de magnitud de frutales de carozo o pomáceas; " + _SD, "Rendimiento"),
            dias=_par(90, "d", "Supuesto: temporada de tres meses de cosecha; " + _SD, "Días de cosecha y operación"),
            horas_dia=_par(20.0, "h/d", "Supuesto: dos turnos y medio con limpieza diaria; " + _SD, "Horas de operación por día"),
            pico_temprana=_par(0.30, "fracción", "Supuesto: peak de la variedad temprana en el primer tercio", "Peak de la variedad temprana"),
            pico_tardia=_par(0.70, "fracción", "Supuesto: peak de la variedad tardía en el último tercio", "Peak de la variedad tardía"),
            ancho=_par(0.25, "fracción", "Supuesto: cada variedad se cosecha en cerca de la mitad de la temporada", "Semiancho de cada triángulo"),
            fraccion_temprana=_par(0.40, "fracción", "Supuesto: 40 % de la superficie es de la variedad temprana", "Fracción de la variedad temprana"),
            cv=_par(0.10, "", "Supuesto: variación diaria por clima y logística; " + _SD, "Variación diaria de la cosecha (cv)"),
            capacidad_t_h=_par(35.0, "t/h", "Supuesto: 1,5 veces la llegada media de la temporada (42.000 t / 1.800 h)", "Capacidad de recepción"),
            umbral_h=_par(24.0, "h", "Supuesto: la fruta en bins aguanta un día sin pérdida apreciable; " + _SD, "Espera sin pérdida"),
            tasa_perdida_h=_par(0.002, "fracción por h", "Supuesto: 4,8 % por día de espera adicional; " + _SD, "Pérdida por hora de espera"),
            perecibilidad_h=_par(96.0, "h", "Supuesto: sobre cuatro días sin frío la fruta se descarta; " + _SD, "Perecibilidad máxima"),
            periodo=_par("semana", "", "Supuesto: la planificación de la cosecha de fruta se hace por semana", "Período de la serie", ("día", "semana")),
            dias_semana=_par(6, "d", "Supuesto: lunes a sábado, como la temporada del tomate", "Días de operación por semana")),
        generador=_gen_fruta),
    "mercado_agar": dict(
        nombre="Agar agar (tirada por el mercado)", logica="mercado", unidad="t", periodo="mes", inventariable=True,
        descripcion="Demanda mensual de agar agar en polvo con estacionalidad (peak en invierno), crecimiento anual y ruido; se "
                    "pronostica con series de tiempo y el producto seco se puede guardar en inventario.",
        parametros=dict(
            demanda_anual_t=_par(602.0, "t/año", _SUP_AGAR, "Demanda del primer año"),
            tendencia_anual=_par(0.04, "fracción por año", "Supuesto: crecimiento moderado del mercado de hidrocoloides; " + _SD, "Crecimiento anual"),
            cv=_par(0.05, "", "Supuesto: variación mensual de pedidos; " + _SD, "Variación mensual (cv)"),
            n_periodos=_par(36, "meses", "Supuesto: tres años de historia, lo mínimo cómodo para Holt-Winters con estacionalidad anual", "Meses de historia")),
        generador=_gen_agar, metodo="hw_multiplicativo"),
    "mercado_estacional_invierno": dict(
        nombre="Combustible de calefacción con peak de invierno", logica="mercado", unidad="t", periodo="mes", inventariable=True,
        descripcion="Demanda mensual de pellet o leña para calefacción, concentrada en los meses fríos (coseno con peak en julio).",
        parametros=dict(
            base=_par(1000.0, "t/mes", "Supuesto: planta mediana de pellet; " + _SD, "Demanda media mensual"),
            amplitud=_par(0.60, "fracción", "Supuesto: la calefacción residencial del centro y sur de Chile se concentra de mayo a septiembre; " + _SD, "Amplitud estacional"),
            mes_pico=_par(7, "mes", "Supuesto: julio, el mes más frío del año en la zona central", "Mes del peak"),
            tendencia_anual=_par(0.0, "fracción por año", "Supuesto: mercado estable", "Crecimiento anual"),
            cv=_par(0.08, "", "Supuesto: inviernos más o menos fríos; " + _SD, "Variación mensual (cv)"),
            n_periodos=_par(36, "meses", "Supuesto: tres años de historia", "Meses de historia")),
        generador=_gen_invierno),
    "mercado_constante": dict(
        nombre="Demanda constante (cliente industrial)", logica="mercado", unidad="t", periodo="mes", inventariable=True,
        descripcion="Demanda mensual pareja con ruido, como el chip que consume una caldera industrial todo el año.",
        parametros=dict(
            base=_par(2000.0, "t/mes", "Supuesto: caldera industrial abastecida por la planta de chip; " + _SD, "Demanda media mensual"),
            cv=_par(0.05, "", "Supuesto: variación de la carga de la caldera; " + _SD, "Variación mensual (cv)"),
            n_periodos=_par(36, "meses", "Supuesto: tres años de historia", "Meses de historia")),
        generador=_gen_constante),
    "mercado_tendencia_creciente": dict(
        nombre="Mercado en crecimiento", logica="mercado", unidad="t", periodo="mes", inventariable=True,
        descripcion="Demanda mensual con tendencia creciente y estacionalidad suave, el caso típico para comparar adelantarse, "
                    "seguir o rezagarse a la demanda.",
        parametros=dict(
            base=_par(500.0, "t/mes", "Supuesto: producto nuevo en un mercado en expansión; " + _SD, "Demanda media del primer año"),
            tendencia_anual=_par(0.12, "fracción por año", "Supuesto: crecimiento de dos dígitos de un producto nuevo; " + _SD, "Crecimiento anual"),
            amplitud=_par(0.10, "fracción", "Supuesto: estacionalidad suave", "Amplitud estacional"),
            mes_pico=_par(12, "mes", "Supuesto: peak en diciembre por las ventas de fin de año", "Mes del peak"),
            cv=_par(0.05, "", "Supuesto: variación mensual; " + _SD, "Variación mensual (cv)"),
            n_periodos=_par(36, "meses", "Supuesto: tres años de historia", "Meses de historia")),
        generador=_gen_tendencia),
    "contrato_industrial": dict(
        nombre="Contrato industrial con renovaciones", logica="mercado", unidad="t", periodo="mes", inventariable=True,
        descripcion="Volumen mensual fijado por contrato, con un mínimo de compra (take or pay), un tope y un aumento en cada renovación.",
        parametros=dict(
            base=_par(800.0, "t/mes", "Supuesto: volumen del primer contrato; " + _SD, "Volumen del contrato"),
            meses_contrato=_par(12, "meses", "Supuesto: contratos anuales", "Duración de cada contrato"),
            aumento_renovacion=_par(0.10, "fracción", "Supuesto: el cliente amplía 10 % el volumen en cada renovación; " + _SD, "Aumento en cada renovación"),
            minimo_take_or_pay=_par(0.90, "fracción", "Supuesto: cláusula de compra mínima de 90 % del volumen; " + _SD, "Compra mínima"),
            tope_sobre_contrato=_par(1.10, "fracción", "Supuesto: el proveedor atiende hasta 110 % del volumen; " + _SD, "Tope de entrega"),
            cv=_par(0.05, "", "Supuesto: variación de los pedidos dentro de la banda; " + _SD, "Variación mensual (cv)"),
            n_periodos=_par(36, "meses", "Supuesto: tres años, tres contratos", "Meses de historia")),
        generador=_gen_contrato),
    "exportacion_ventana": dict(
        nombre="Exportación en ventana de embarques", logica="mercado", unidad="t", periodo="semana", inventariable=True,
        descripcion="Embarques semanales de exportación concentrados en una ventana del año (contraestación del hemisferio norte), "
                    "con un embarque cada cierto número de semanas y cero fuera de la ventana.",
        parametros=dict(
            semana_inicio=_par(10, "semana", "Supuesto: la ventana parte en marzo; " + _SD, "Semana de inicio de la ventana"),
            semana_fin=_par(30, "semana", "Supuesto: la ventana termina en julio; " + _SD, "Semana de fin de la ventana"),
            embarque_cada=_par(2, "semanas", "Supuesto: una nave cada dos semanas; " + _SD, "Semanas entre embarques"),
            toneladas_embarque=_par(250.0, "t", "Supuesto: diez contenedores de 25 t por embarque; " + _SD, "Toneladas por embarque"),
            cv=_par(0.10, "", "Supuesto: variación del tamaño de cada embarque; " + _SD, "Variación del embarque (cv)"),
            n_periodos=_par(156, "semanas", "Supuesto: tres años de historia: dos para arrancar la estacionalidad semanal y uno de prueba", "Semanas de historia")),
        generador=_gen_exportacion, metodo="hw_aditivo"),
    "mercado_impulsos": dict(
        nombre="Demanda por pedidos esporádicos (intermitente)", logica="mercado", unidad="t", periodo="semana", inventariable=True,
        descripcion="Pedidos grandes y esporádicos: muchas semanas sin pedidos y otras con un pedido de tamaño variable; se "
                    "pronostica con el método de Croston.",
        parametros=dict(
            probabilidad=_par(0.30, "fracción", "Supuesto: hay pedido en cerca de una de cada tres semanas; " + _SD, "Probabilidad de pedido por semana"),
            tamano_medio=_par(60.0, "t", "Supuesto: pedido medio de un distribuidor; " + _SD, "Tamaño medio del pedido"),
            cv_tamano=_par(0.50, "", "Supuesto: pedidos muy distintos entre sí; " + _SD, "Variación del tamaño (cv)"),
            n_periodos=_par(104, "semanas", "Supuesto: dos años de historia", "Semanas de historia")),
        generador=_gen_impulsos, metodo="croston"),
    "mixta_oferta_mercado": dict(
        nombre="Mixta: cosecha estacional y venta todo el año", logica="mixta", unidad="t", periodo="mes", inventariable=True,
        descripcion="La materia prima llega solo en los meses de cosecha (empujada por la oferta) y el mercado compra todo el año "
                    "(tirada por la demanda): la planta procesa en la cosecha y el inventario de producto cubre el resto del año.",
        parametros=dict(
            superficie_ha=_par(300.0, "ha", "Supuesto: huertos que abastecen la planta; " + _SD, "Superficie cosechada"),
            rendimiento_t_ha=_par(30.0, "t/ha", "Supuesto: orden de magnitud de un frutal o una hortaliza de proceso; " + _SD, "Rendimiento"),
            mes_inicio_cosecha=_par(1, "mes", "Supuesto: la cosecha parte en enero", "Mes de inicio de la cosecha"),
            meses_cosecha=_par(4, "meses", "Supuesto: cuatro meses de cosecha, de enero a abril", "Meses de cosecha"),
            factor_producto=_par(0.85, "t/t", "Supuesto: rendimiento de materia prima a producto (congelado o pulpa); " + _SD, "Factor a producto"),
            demanda_anual_t=_par(6000.0, "t/año", "Supuesto: ventas anuales de producto; " + _SD, "Demanda anual de producto"),
            amplitud_mercado=_par(0.15, "fracción", "Supuesto: estacionalidad suave de las ventas", "Amplitud estacional del mercado"),
            mes_pico_mercado=_par(12, "mes", "Supuesto: peak de ventas en diciembre", "Mes del peak de ventas"),
            cv=_par(0.05, "", "Supuesto: variación mensual de las ventas; " + _SD, "Variación mensual (cv)")),
        generador=_gen_mixta),
}


def listar_perfiles() -> list[dict]:
    """Los 10 perfiles con su identificador, nombre, lógica, unidad, período y descripción (sin el generador)."""
    return [dict(id=k, nombre=v["nombre"], logica=v["logica"], unidad=v["unidad"], periodo=v["periodo"], descripcion=v["descripcion"],
                 inventariable=v["inventariable"], parametros={c: dict(p) for c, p in v["parametros"].items()}) for k, v in PERFILES.items()]


def parametros_defecto(perfil_id: str) -> dict:
    if perfil_id not in PERFILES:
        raise ValueError(f"Perfil de demanda desconocido: {perfil_id!r}. Use uno de: {', '.join(PERFILES)}")
    return {c: p["valor"] for c, p in PERFILES[perfil_id]["parametros"].items()}


def generar(perfil_id: str, params: dict | None = None, semilla=None, pronostico_h: int | None = None) -> dict:
    """Serie de demanda del perfil con los parámetros por defecto, reemplazados por los de params (solo claves conocidas).
    Devuelve perfil, nombre, lógica, unidad, período, serie, etiquetas, serie_t_h, estadísticas, supuestos (cada parámetro con
    su valor, unidad y fuente), parámetros usados, semilla y extra (balance agrícola, inventario de la mixta o pronóstico del
    mercado con su método y errores en la última estación). Determinista: la misma semilla da la misma serie."""
    base = parametros_defecto(perfil_id); P = PERFILES[perfil_id]
    for k, v in (params or {}).items():
        if k not in base:
            raise ValueError(f"El perfil {perfil_id} no tiene el parámetro {k!r}")
        op = P["parametros"][k]["opciones"]
        if op and v not in op:
            raise ValueError(f"{k}: use una de {', '.join(op)}")
        if not op:
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise ValueError(f"{k}: debe ser un número")
            if not math.isfinite(v) or v < 0:
                raise ValueError(f"{k}: debe ser un número mayor o igual a cero")
        base[k] = v
    sem = SEMILLA_DEFECTO if semilla is None else int(semilla)
    g = P["generador"](base, sem)
    serie = [max(0.0, float(x)) for x in g["serie"]]
    periodo = g["periodo"]
    t_h = g.get("serie_t_h") or ([v / HORAS[periodo] for v in serie] if periodo in HORAS else None)
    extra = dict(g.get("extra") or {})
    m = int(extra.get("m") or 12)
    if P["logica"] == "mercado":
        h = int(pronostico_h or (12 if m == 12 else 52 if m == 52 else m))
        val = metodos_validos(serie, m)
        clave = P.get("metodo") if P.get("metodo") in val else "croston" if "croston" in val else ("hw_multiplicativo" if "hw_multiplicativo" in val else
                                                    "hw_aditivo" if "hw_aditivo" in val else "regresion")
        r = pronosticar(serie, m, clave, h)
        ev = evaluar_metodos(serie, m, m, [clave])
        extra.update(pronostico=r["pronostico"], metodo=clave, nombre_metodo=METODOS[clave],
                     errores_prueba=ev[0]["errores"] if ev else None)
    sup = [dict(clave=c, nombre=p["nombre"], valor=base[c], unidad=p["unidad"], fuente=p["fuente"]) for c, p in P["parametros"].items()]
    return dict(perfil=perfil_id, nombre=P["nombre"], descripcion=P["descripcion"], logica=P["logica"], unidad=P["unidad"],
                periodo=periodo, inventariable=P["inventariable"], serie=serie, etiquetas=list(g["etiquetas"]), serie_t_h=t_h,
                estadisticas=estadisticas(serie, P["unidad"], periodo), supuestos=sup, parametros=base, semilla=sem, extra=extra)


# ================================================================== (d) PAT 138: tomate, 10 distribuciones de la llegada
# Pedido de Jaime del 13-11-2026: la demanda de la planta de tomate es empujada por la producción agrícola; la distribución da
# la forma de la llegada diaria de tomate a lo largo de la temporada (curva de cosecha) y se escala al total de la temporada
# del tipo de planta (catalogos/plantas_tomate.py). Formas de la lámina de «distribuciones a priori» (normal, log-normal, beta,
# media normal, uniforme y normal truncada) más triangular, Weibull, gamma y bimodal (mezcla de dos normales: variedad temprana
# y tardía). x es la fracción de la temporada (0 = primer día, 1 = último); cada día pesa la densidad en su punto medio
# (i + 0,5) / n, así que la forma no depende de la duración. Las densidades son las de Law (2015), Simulation modeling and
# analysis, 5.ª ed., McGraw-Hill, cap. 6 (cita general de la obra, no está en la carpeta del proyecto); los parámetros son
# Supuestos didácticos con su significado, salvo la normal truncada, que es la curva de la planta basada en Agrozzi.
PERFIL_TOMATE = "tomate_llegada"
_FRAC = "fracción de la temporada"
_SUP_D = "Supuesto didáctico (PAT 138): "
_SD_LLEGADA = "sin datos de llegada diaria de tomate de una planta chilena en la carpeta del proyecto"


def _pd(valor, nombre, significado, fuente, unidad=_FRAC):
    return dict(valor=float(valor), nombre=nombre, significado=significado, unidad=unidad, fuente=fuente)


def _f_normal(x, p):
    return math.exp(-0.5 * ((x - p["media"]) / max(1e-9, p["desviacion"])) ** 2)


def _f_lognormal(x, p):
    s = max(1e-9, p["sigma_log"])
    return math.exp(-0.5 * ((math.log(x) - math.log(max(1e-9, p["mediana"]))) / s) ** 2) / x


def _f_beta(x, p):
    return x ** (p["alfa"] - 1.0) * (1.0 - x) ** (p["beta"] - 1.0)


def _f_media_normal(x, p):
    return math.exp(-0.5 * (x / max(1e-9, p["escala"])) ** 2)


def _f_uniforme(x, p):
    return 1.0 if p["inicio"] <= x <= p["fin"] else 0.0


def _f_triangular(x, p):
    a, c, b = p["minimo"], p["moda"], p["maximo"]
    if x < a or x > b:
        return 0.0
    if x <= c:
        return (x - a) / (c - a) if c > a else 1.0
    return (b - x) / (b - c) if b > c else 1.0


def _f_weibull(x, p):
    k, lam = p["forma"], max(1e-9, p["escala"])
    return (x / lam) ** (k - 1.0) * math.exp(-((x / lam) ** k))


def _f_gamma(x, p):
    k, th = p["forma"], max(1e-9, p["escala"])
    return math.exp((k - 1.0) * math.log(x) - x / th)


def _f_bimodal(x, p):
    w = min(1.0, max(0.0, p["fraccion_temprana"]))
    n1 = math.exp(-0.5 * ((x - p["media_temprana"]) / max(1e-9, p["desv_temprana"])) ** 2) / p["desv_temprana"]
    n2 = math.exp(-0.5 * ((x - p["media_tardia"]) / max(1e-9, p["desv_tardia"])) ** 2) / p["desv_tardia"]
    return w * n1 + (1.0 - w) * n2


DISTRIBUCIONES = {
    "normal": dict(
        nombre="Normal", densidad=_f_normal, forma="simétrica, peak al centro",
        explicacion="La llegada sube y baja en forma simétrica alrededor de la mitad de la temporada; casi no llega tomate el primer "
                    "y el último día (la campana cabe completa en la temporada).",
        parametros=dict(media=_pd(0.5, "Media (posición del peak)", "posición", _SUP_D + "peak a mitad de la temporada; " + _SD_LLEGADA),
                        desviacion=_pd(0.15, "Desviación estándar", "dispersión",
                                       _SUP_D + "±3,3 desviaciones caben en la temporada (la campana no se corta); " + _SD_LLEGADA))),
    "lognormal": dict(
        nombre="Log-normal", densidad=_f_lognormal, forma="asimétrica a la derecha, peak temprano y cola larga",
        explicacion="La cosecha parte fuerte al inicio de la temporada y se alarga con una cola de tomate tardío (asimetría positiva).",
        parametros=dict(mediana=_pd(0.30, "Mediana (la mitad del tomate llega antes)", "posición",
                                    _SUP_D + "el grueso de la cosecha en el primer tercio de la temporada; " + _SD_LLEGADA),
                        sigma_log=_pd(0.55, "Desviación del logaritmo", "dispersión y asimetría",
                                      _SUP_D + "cola visible hasta el final de la temporada; " + _SD_LLEGADA, unidad="—"))),
    "beta": dict(
        nombre="Beta", densidad=_f_beta, forma="asimétrica a la izquierda, peak tardío",
        explicacion="Definida justo entre el inicio y el fin de la temporada: con alfa mayor que beta el peak queda al final "
                    "(cosecha tardía) y la llegada crece de a poco desde el inicio.",
        parametros=dict(alfa=_pd(5.0, "Alfa", "forma: empuja el peak hacia el final", _SUP_D + "peak en el 80 % de la temporada; " + _SD_LLEGADA, unidad="—"),
                        beta=_pd(2.0, "Beta", "forma: empuja el peak hacia el inicio", _SUP_D + "con alfa 5 da la moda (alfa − 1) / (alfa + beta − 2) = 0,8; "
                                 + _SD_LLEGADA, unidad="—"))),
    "media_normal": dict(
        nombre="Media normal (half-normal)", densidad=_f_media_normal, forma="decreciente desde el primer día",
        explicacion="La temporada parte en plena cosecha (el tomate ya estaba maduro cuando abre la planta) y la llegada solo baja.",
        parametros=dict(escala=_pd(0.40, "Escala (desviación de la normal de origen)", "dispersión: qué tan rápido decae",
                                   _SUP_D + "al final de la temporada llega cerca del 4 % del primer día; " + _SD_LLEGADA))),
    "uniforme": dict(
        nombre="Uniforme", densidad=_f_uniforme, forma="plana",
        explicacion="Llega lo mismo todos los días: el caso de una cosecha programada por contrato, sin peak.",
        parametros=dict(inicio=_pd(0.0, "Inicio", "posición del primer día con llegada", _SUP_D + "toda la temporada"),
                        fin=_pd(1.0, "Fin", "posición del último día con llegada", _SUP_D + "toda la temporada"))),
    "normal_truncada": dict(
        nombre="Normal truncada", densidad=_f_normal, forma="simétrica y ancha, cortada en el inicio y el fin",
        explicacion="Campana ancha cortada por el inicio y el fin de la temporada: la planta recibe tomate desde el primer día. Es la "
                    "curva de la planta basada en Agrozzi (motor/temporada.py).",
        parametros=dict(media=_pd(0.5, "Media (posición del peak)", "posición", _SUP_T + ": peak en marzo, a mitad de la temporada"),
                        desviacion=_pd(0.25, "Desviación estándar", "dispersión", _SUP_T + ": desviación de la campana"))),
    "triangular": dict(
        nombre="Triangular", densidad=_f_triangular, forma="sube en línea recta hasta la moda y baja en línea recta",
        explicacion="La forma más simple cuando solo se conoce el inicio, el día de más cosecha y el fin: sube rápido hasta el peak "
                    "y baja más lento hasta el cierre.",
        parametros=dict(minimo=_pd(0.0, "Mínimo", "posición del inicio", _SUP_D + "toda la temporada"),
                        moda=_pd(0.35, "Moda (peak)", "posición del peak", _SUP_D + "peak en el primer tercio; " + _SD_LLEGADA),
                        maximo=_pd(1.0, "Máximo", "posición del fin", _SUP_D + "toda la temporada"))),
    "weibull": dict(
        nombre="Weibull", densidad=_f_weibull, forma="peak después de la mitad y caída rápida al final",
        explicacion="Con forma 5 la llegada crece de a poco hasta los dos tercios de la temporada y cae más rápido que como subió "
                    "(asimetría negativa).",
        parametros=dict(forma=_pd(5.0, "Forma (k)", "asimetría: sobre 3,6 la cola queda al inicio", _SUP_D + _SD_LLEGADA, unidad="—"),
                        escala=_pd(0.70, "Escala (lambda)", "posición y dispersión", _SUP_D + "moda lambda·((k − 1) / k)^(1/k) = 0,67 de la "
                                   "temporada; " + _SD_LLEGADA))),
    "gamma": dict(
        nombre="Gamma", densidad=_f_gamma, forma="asimétrica a la derecha, peak antes de la mitad",
        explicacion="Suma de etapas de maduración: la llegada sube hasta antes de la mitad de la temporada y baja con una cola suave.",
        parametros=dict(forma=_pd(9.0, "Forma (k)", "asimetría: más alta, más simétrica", _SUP_D + _SD_LLEGADA, unidad="—"),
                        escala=_pd(0.05, "Escala (theta)", "dispersión", _SUP_D + "moda (k − 1)·theta = 0,40 y media k·theta = 0,45; " + _SD_LLEGADA))),
    "bimodal": dict(
        nombre="Bimodal (variedad temprana y tardía)", densidad=_f_bimodal, forma="dos peaks",
        explicacion="Mezcla de dos normales: una variedad temprana y una tardía, con un valle entre ambas cosechas (como el perfil "
                    "de fruta de dos variedades).",
        parametros=dict(fraccion_temprana=_pd(0.45, "Fracción de la variedad temprana", "peso de la primera cosecha",
                                              _SUP_D + "algo menos de la mitad del tomate es temprano; " + _SD_LLEGADA, unidad="—"),
                        media_temprana=_pd(0.28, "Media de la variedad temprana", "posición del primer peak", _SUP_D + _SD_LLEGADA),
                        desv_temprana=_pd(0.09, "Desviación de la variedad temprana", "dispersión del primer peak", _SUP_D + _SD_LLEGADA),
                        media_tardia=_pd(0.72, "Media de la variedad tardía", "posición del segundo peak", _SUP_D + _SD_LLEGADA),
                        desv_tardia=_pd(0.11, "Desviación de la variedad tardía", "dispersión del segundo peak", _SUP_D + _SD_LLEGADA))),
}
IDS_DISTRIBUCIONES = tuple(DISTRIBUCIONES)
DISTRIBUCION_DEFECTO = "normal_truncada"


def parametros_distribucion(dist_id: str, params: dict | None = None) -> dict:
    """Parámetros de la distribución (los por defecto, reemplazados por los de params; solo claves conocidas)."""
    if dist_id not in DISTRIBUCIONES:
        raise ValueError(f"Distribución desconocida: {dist_id!r}. Use una de: {', '.join(DISTRIBUCIONES)}")
    base = {k: p["valor"] for k, p in DISTRIBUCIONES[dist_id]["parametros"].items()}
    for k, v in (params or {}).items():
        if k not in base:
            raise ValueError(f"La distribución {dist_id} no tiene el parámetro {k!r}")
        v = float(v)
        if not math.isfinite(v) or v < 0:
            raise ValueError(f"{k}: debe ser un número mayor o igual a cero")
        base[k] = v
    return base


def pesos_distribucion(n: int, dist_id: str, params: dict | None = None) -> list[float]:
    """Pesos (suman 1) de los n días de la temporada con la forma de la distribución (densidad en el punto medio de cada día)."""
    n = int(n)
    if n <= 0:
        return []
    p = parametros_distribucion(dist_id, params); f = DISTRIBUCIONES[dist_id]["densidad"]
    w = [max(0.0, f((i + 0.5) / n, p)) for i in range(n)]
    s = sum(w)
    if not s > 0 or not math.isfinite(s):
        raise ValueError(f"Con estos parámetros la distribución {dist_id} no deja llegada en la temporada")
    return [x / s for x in w]


def llegada_tomate(variante_id: str | None = None, dist_id: str = DISTRIBUCION_DEFECTO, semilla=None, params: dict | None = None,
                   cv: float = 0.10, capacidad_t_h: float | None = None, perdida_1pct: bool = True, modelo: str | None = None,
                   tamano: str | None = None) -> dict:
    """Serie diaria de llegada de tomate fresco a la planta de tomate con la forma de la distribución dist_id.
    PAT 139: la planta se arma con modelo (°Brix y proceso), distribución y tamaño (tomate de la temporada, días y horas por día):
    llegada_tomate(modelo="agrozzi", tamano="chica", dist_id="normal"). Sin tamaño, el mediano (el de Agrozzi). variante_id sigue
    valiendo (PAT 138): una de las 10 ids viejas, «modelo|tamano» o un modelo solo; si se da modelo, manda sobre variante_id.
    La planta es la de catalogos/plantas_tomate.py. Mismo formato que generar() (perfil «tomate_llegada», lógica agrícola, período día):
    serie en t por día, serie_t_h en t/h (t del día / horas de proceso del día de la variante), estadísticas, supuestos y extra
    con el balance de oferta_agricola (cosechado = procesado + perdido) y la capacidad de recepción necesaria. La suma de la serie
    es el tomate de la temporada de la variante. cv: variación diaria por el clima (gamma de media 1, la serie se reescala al
    total); capacidad_t_h: recepción con la que se calcula lo perdido (None: se procesa todo el mismo día)."""
    from ..catalogos import plantas_tomate as PT
    if modelo is not None:
        variante_id = PT.id_compuesta(modelo, tamano)
    elif tamano is not None:
        variante_id = PT.id_compuesta(PT.separar_id(variante_id)[0], tamano)
    v = PT.variante(variante_id); P = DISTRIBUCIONES.get(dist_id)
    if P is None:
        raise ValueError(f"Distribución desconocida: {dist_id!r}. Use una de: {', '.join(DISTRIBUCIONES)}")
    par = parametros_distribucion(dist_id, params)
    D = int(v["dias"]); H = float(v["horas_dia"]); total = float(v["temporada_t"])
    w = pesos_distribucion(D, dist_id, par)
    sem = SEMILLA_DEFECTO if semilla is None else int(semilla)
    kw = dict(superficie_ha=1.0, rendimiento_t_ha=total, dias=D, horas_dia=H, cv=float(cv), umbral_h=6.0, tasa_perdida_h=0.05 / 8.0,
              perecibilidad_h=48.0, pesos=w, semilla=sem)
    r = oferta_agricola(capacidad_t_h=capacidad_t_h, **kw)
    if perdida_1pct:
        r["capacidad"]["para_perdida_1pct_t_h"] = capacidad_para_perdida(0.01, **kw)
    serie = list(r["llegada_diaria"]); t_h = [x / H for x in serie]
    nombre = f"Tomate: llegada {P['nombre'].lower()} a la planta {v['corto']}"
    fv = PT.fuentes(v["id"])
    sup = [dict(clave="variante", nombre="Planta de tomate (modelo y tamaño)", valor=v["nombre"], unidad="", fuente="catalogos/plantas_tomate.py"),
           dict(clave="brix", nombre="°Brix de la pasta", valor=v["brix"], unidad="°Brix", fuente=fv["brix"]),
           dict(clave="quiebre", nombre=PT.QUIEBRES[v["quiebre"]], valor=v["T_quiebre"], unidad="°C", fuente=fv["quiebre"]),
           dict(clave="evaporador", nombre="Evaporación", valor=PT.EVAPORADORES[v["evaporador"]], unidad="", fuente=fv["evaporador"]),
           dict(clave="temporada_t", nombre="Tomate de la temporada", valor=total, unidad="t", fuente=fv["temporada_t"]),
           dict(clave="dias", nombre="Días de la temporada", valor=D, unidad="d", fuente=fv["dias"]),
           dict(clave="horas_dia", nombre="Horas de proceso por día", valor=H, unidad="h/d", fuente=fv["horas_dia"]),
           dict(clave="distribucion", nombre="Distribución de la llegada", valor=P["nombre"], unidad="",
                fuente="Lámina de distribuciones a priori (pedido del 13-11-2026); densidades de Law (2015, cap. 6)")]
    sup += [dict(clave=k, nombre=q["nombre"], valor=par[k], unidad=q["unidad"], fuente=q["fuente"]) for k, q in P["parametros"].items()]
    sup += [dict(clave="cv", nombre="Variación diaria de la cosecha (cv)", valor=float(cv), unidad="",
                 fuente="Supuesto: variación diaria por clima y logística, el mismo del perfil de tomate; " + _SD)]
    extra = dict(r, variante=v["id"], modelo=v["modelo"], tamano=v["tamano"], distribucion=dist_id, pesos=w, parametros_distribucion=par)
    return dict(perfil=PERFIL_TOMATE, nombre=nombre, descripcion=P["explicacion"], logica="agricola", unidad="t", periodo="día",
                inventariable=False, serie=serie, etiquetas=[f"Día {i + 1}" for i in range(D)], serie_t_h=t_h,
                estadisticas=estadisticas(serie, "t", "día"), supuestos=sup, parametros=dict(par, cv=float(cv)), semilla=sem,
                extra=extra, variante=v["id"], modelo=v["modelo"], tamano=v["tamano"], distribucion=dist_id, horas_dia=H, dias=D, total_t=total)


def resumen_llegada(res: dict) -> dict:
    """Métricas de la serie de llegada: total (t), pico y percentil 95 en t/h, media en t/h y días."""
    th = res["serie_t_h"]
    return dict(total_t=sum(res["serie"]), pico_t_h=max(th) if th else 0.0, p95_t_h=percentil(th, 95), media_t_h=sum(th) / len(th) if th else 0.0,
                dias=len(th), horas_dia=res.get("horas_dia"))


def desafio_tomate(res: dict, nombre: str = "", precios: list | None = None) -> dict:
    """Lo que queda en st.session_state["desafio"] con la llegada de tomate: el desafío de motor/desafio.py con la serie diaria,
    más tipo_planta «tomate», el modelo (modelo_tomate), el tamaño (tamano_tomate), la distribución (distribucion_tomate), la
    variante compuesta «modelo|tamano» (variante_tomate, para compatibilidad con PAT 138) y la lógica agrícola. demanda_t_h es la
    de la planta (t del día / horas de proceso del día), no t / 24 h. PAT 139: en una id vieja de PAT 138, modelo_tomate y
    tamano_tomate son la traducción (modelo y tamaño más cercano) y variante_tomate sigue siendo la id vieja."""
    from . import desafio as D
    from ..catalogos import plantas_tomate as PT
    v = PT.variante(res["variante"]); dn = DISTRIBUCIONES[res["distribucion"]]["nombre"]
    enunciado = (f"diseñar una {v['nombre'][0].lower() + v['nombre'][1:]}. La llegada de tomate es empujada por la cosecha y sigue una "
                 f"distribución {dn.lower()} a lo largo de {v['dias']} días.")
    d = a_desafio(res, "serie", titulo=f"{v['nombre']} con llegada {dn.lower()}", rubro="tomate",
                  producto=f"Pasta de tomate de {v['brix']:.0f} °Brix en envase aséptico", enunciado=enunciado, precios=precios)
    out = D.estado_sesion(d, nombre, "")
    out.update(tipo_planta="tomate", variante_tomate=v["id"], modelo_tomate=v["modelo"], tamano_tomate=v["tamano"],
               distribucion_tomate=res["distribucion"], perfil_demanda=PERFIL_TOMATE,
               logica="agricola", demanda_t_h=list(res["serie_t_h"]), semilla_demanda=res.get("semilla"),
               parametros_distribucion=dict((res.get("extra") or {}).get("parametros_distribucion") or {}),
               cv_demanda=(res.get("parametros") or {}).get("cv"))
    return out


# ================================================================== (e) PAT 144 a: agar agar, llegada del alga seca
# La pantalla Desafío también arma la planta de agar agar (catalogos/plantas_agar.py: modelo de proceso × tamaño). La materia
# prima es el alga roja seca en fardos que entregan los proveedores en los días de operación del año; la distribución da la forma
# de esa llegada (las mismas 10 formas y los mismos parámetros del tomate) y se escala al alga seca del año que pide el modelo
# para producir el agar del tamaño. El alga seca se guarda (Armisen y Galatas, 1987: se seca hasta cerca de 20 % de humedad para
# guardarla), así que la espera en bodega no la degrada: sin pérdida por espera, a diferencia del tomate.
PERFIL_AGAR = "agar_llegada"
DISTRIBUCION_DEFECTO_AGAR = "uniforme"
_SD_ALGA = "sin datos de llegada diaria de alga seca a una planta chilena de agar en la carpeta del proyecto"
_SUP_ALGA = ("Supuesto didáctico (PAT 144 a): la misma forma y los mismos parámetros de la distribución que en el desafío de tomate, "
             "aplicados a los días de operación del año; " + _SD_ALGA)
SUPUESTO_FORMA_AGAR = _SUP_ALGA
EXPLICACION_AGAR = {
    "normal": ("Las entregas de alga seca suben y bajan en forma simétrica alrededor de la mitad del año de operación; casi no llega "
               "alga el primer y el último día."),
    "lognormal": "Las entregas parten fuertes al inicio del año de operación y se alargan con una cola de alga que llega tarde (asimetría positiva).",
    "beta": "Las entregas crecen de a poco desde el inicio y tienen su máximo cerca del final del año de operación.",
    "media_normal": "La planta abre con las bodegas de los proveedores llenas y las entregas solo bajan a lo largo del año.",
    "uniforme": ("Llega la misma alga todos los días: compra programada con los proveedores, sin un máximo. Es la llegada del escenario "
                 "base, que procesa la misma alga cada día."),
    "normal_truncada": ("Campana ancha cortada por el inicio y el fin del año de operación: llega alga desde el primer día, con más "
                        "entregas a mitad de año."),
    "triangular": ("La forma más simple cuando solo se conoce el inicio, el día de más entregas y el fin: sube rápido hasta el máximo y "
                   "baja más lento hasta el cierre."),
    "weibull": "Las entregas crecen de a poco hasta los dos tercios del año de operación y caen más rápido que como subieron.",
    "gamma": "Las entregas suben hasta antes de la mitad del año de operación y bajan con una cola suave.",
    "bimodal": ("Dos máximos de entregas con un valle entre ellos, por ejemplo si el alga se cosechara y secara en dos épocas distintas "
                "del año."),
}
_TEXTO_AGAR = (("la mitad del tomate", "la mitad del alga"), ("de la variedad temprana", "de la primera época de entrega"),
               ("de la variedad tardía", "de la segunda época de entrega"), ("variedad temprana y tardía", "dos épocas de entrega"),
               ("primera cosecha", "primera época de entrega"), ("de la temporada", "del año de operación"),
               ("temporada", "año de operación"), ("peaks", "máximos"), ("peak", "máximo"))


def texto_agar(t: str) -> str:
    """Nombre o significado de una distribución (o de su parámetro) dicho para el alga seca: sin variedades ni cosecha de tomate."""
    for a, b in _TEXTO_AGAR:
        t = t.replace(a, b)
    return t


def nombre_distribucion(dist_id: str, rubro: str = "tomate") -> str:
    """Nombre de la distribución; en el agar, con texto_agar (por ejemplo «Bimodal (dos épocas de entrega)»)."""
    n = DISTRIBUCIONES[dist_id]["nombre"]
    return texto_agar(n) if rubro == "agar" else n


PERECIBILIDAD_ALGA_H = 8760.0     # Supuesto: el alga seca en fardos se guarda más de un año de operación sin descartarse


def llegada_agar(variante_id: str | None = None, dist_id: str = DISTRIBUCION_DEFECTO_AGAR, semilla=None, params: dict | None = None,
                 cv: float = 0.10, capacidad_t_h: float | None = None, modelo: str | None = None, tamano: str | None = None) -> dict:
    """Serie diaria de llegada de alga seca a la planta de agar (catalogos/plantas_agar.py) con la forma de la distribución dist_id,
    en los días de operación del año del tamaño. Mismo formato que llegada_tomate (lógica agrícola, período día): serie en t de
    alga seca por día, serie_t_h (t del día / horas de operación del día), estadísticas, supuestos y extra con el balance de
    oferta_agricola. La suma de la serie es el alga seca del año del modelo y del tamaño. Sin pérdida por espera (el alga seca se
    guarda). modelo y tamano mandan sobre variante_id (id compuesta «modelo|tamano» o un modelo solo)."""
    from ..catalogos import plantas_agar as PA
    if modelo is not None:
        variante_id = PA.id_compuesta(modelo, tamano)
    elif tamano is not None:
        variante_id = PA.id_compuesta(PA.separar_id(variante_id)[0], tamano)
    v = PA.variante(variante_id); P = DISTRIBUCIONES.get(dist_id)
    if P is None:
        raise ValueError(f"Distribución desconocida: {dist_id!r}. Use una de: {', '.join(DISTRIBUCIONES)}")
    par = parametros_distribucion(dist_id, params)
    D = int(v["dias"]); H = float(v["horas_dia"]); total = float(v["alga_t_ano"])
    w = pesos_distribucion(D, dist_id, par)
    sem = SEMILLA_DEFECTO if semilla is None else int(semilla)
    kw = dict(superficie_ha=1.0, rendimiento_t_ha=total, dias=D, horas_dia=H, cv=float(cv), umbral_h=PERECIBILIDAD_ALGA_H,
              tasa_perdida_h=0.0, perecibilidad_h=PERECIBILIDAD_ALGA_H, pesos=w, semilla=sem)
    r = oferta_agricola(capacidad_t_h=capacidad_t_h, **kw)
    serie = list(r["llegada_diaria"]); t_h = [x / H for x in serie]
    nombre = f"Agar agar: llegada {nombre_distribucion(dist_id, 'agar').lower()} de alga seca a la planta {v['corto']}"
    fv = PA.fuentes(v["id"])
    sup = [dict(clave="variante", nombre="Planta de agar (modelo y tamaño)", valor=v["nombre"], unidad="", fuente="catalogos/plantas_agar.py")]
    sup += [dict(clave=k, nombre=PA.ETIQUETAS[k], valor=v[k] * (100.0 if PA.UNIDADES[k] == "%" else 1.0), unidad=PA.UNIDADES[k],
                 fuente=fv[k]) for k in PA.ETIQUETAS]
    sup += [dict(clave="agar_t_ano", nombre="Agar en polvo al año", valor=v["agar_t_ano"], unidad="t", fuente=fv["agar_t_ano"]),
            dict(clave="alga_t_ano", nombre="Alga seca del año", valor=total, unidad="t", fuente=fv["alga_t_ano"]),
            dict(clave="dias", nombre="Días de operación al año", valor=D, unidad="d", fuente=fv["dias"]),
            dict(clave="horas_dia", nombre="Horas de operación por día", valor=H, unidad="h/d", fuente=fv["horas_dia"]),
            dict(clave="distribucion", nombre="Distribución de la llegada", valor=nombre_distribucion(dist_id, "agar"), unidad="",
                 fuente="Lámina de distribuciones a priori (pedido del 13-11-2026); densidades de Law (2015, cap. 6)")]
    sup += [dict(clave=k, nombre=texto_agar(q["nombre"]), valor=par[k], unidad=texto_agar(q["unidad"]), fuente=_SUP_ALGA)
            for k, q in P["parametros"].items()]
    sup += [dict(clave="cv", nombre="Variación diaria de las entregas (cv)", valor=float(cv), unidad="",
                 fuente="Supuesto: variación diaria de las entregas de los proveedores, el mismo valor del tomate; " + _SD_ALGA),
            dict(clave="perecibilidad", nombre="Espera sin pérdida del alga seca", valor=PERECIBILIDAD_ALGA_H, unidad="h",
                 fuente=("Supuesto: el alga seca hasta cerca de 20 % de humedad se guarda en fardos (Armisen y Galatas, 1987); no se "
                         "degrada por la espera en bodega"))]
    extra = dict(r, variante=v["id"], modelo=v["modelo"], tamano=v["tamano"], distribucion=dist_id, pesos=w, parametros_distribucion=par)
    return dict(perfil=PERFIL_AGAR, rubro="agar", nombre=nombre, descripcion=EXPLICACION_AGAR.get(dist_id, P["explicacion"]),
                logica="agricola", unidad="t", periodo="día", inventariable=False, serie=serie,
                etiquetas=[f"Día {i + 1}" for i in range(D)], serie_t_h=t_h, estadisticas=estadisticas(serie, "t", "día"),
                supuestos=sup, parametros=dict(par, cv=float(cv)), semilla=sem, extra=extra, variante=v["id"], modelo=v["modelo"],
                tamano=v["tamano"], distribucion=dist_id, horas_dia=H, dias=D, total_t=total)


def desafio_agar(res: dict, nombre: str = "", precios: list | None = None) -> dict:
    """Lo que queda en st.session_state["desafio"] con la llegada de alga seca: el desafío de motor/desafio.py con la serie diaria,
    más tipo_planta y rubro «agar», el modelo (modelo_agar), el tamaño (tamano_agar), la distribución (distribucion_agar), la id
    compuesta «modelo|tamano» (variante_agar) y la lógica agrícola. No lleva las claves del tomate (variante_tomate y las otras),
    así las pantallas que leen el desafío de tomate no lo confunden con este."""
    from . import desafio as D
    from ..catalogos import plantas_agar as PA
    v = PA.variante(res["variante"]); dn = nombre_distribucion(res["distribucion"], "agar")
    enunciado = (f"diseñar una {v['nombre'][0].lower() + v['nombre'][1:]}. La llegada de alga seca sigue una distribución "
                 f"{dn.lower()} a lo largo de {v['dias']} días de operación.")
    d = a_desafio(res, "serie", titulo=f"{v['nombre']} con llegada {dn.lower()}", rubro="agar",
                  producto="Agar agar en polvo, grado alimentario", enunciado=enunciado, precios=precios)
    out = D.estado_sesion(d, nombre, "")
    out.update(tipo_planta="agar", variante_agar=v["id"], modelo_agar=v["modelo"], tamano_agar=v["tamano"],
               distribucion_agar=res["distribucion"], perfil_demanda=PERFIL_AGAR, logica="agricola",
               demanda_t_h=list(res["serie_t_h"]), semilla_demanda=res.get("semilla"),
               parametros_distribucion=dict((res.get("extra") or {}).get("parametros_distribucion") or {}),
               cv_demanda=(res.get("parametros") or {}).get("cv"))
    return out


def llegada(rubro: str, variante_id: str | None = None, dist_id: str | None = None, **kw) -> dict:
    """PAT 144 a: llegada de materia prima del desafío según el rubro: «tomate» (llegada_tomate) o «agar» (llegada_agar)."""
    if rubro == "agar":
        return llegada_agar(variante_id, dist_id or DISTRIBUCION_DEFECTO_AGAR, **kw)
    if rubro == "tomate":
        return llegada_tomate(variante_id, dist_id or DISTRIBUCION_DEFECTO, **kw)
    raise ValueError(f"El desafío con llegada de materia prima es de tomate o de agar, no {rubro!r}")


def desafio_de_llegada(res: dict, nombre: str = "", precios: list | None = None) -> dict:
    """desafio_agar o desafio_tomate según el perfil de la serie."""
    return desafio_agar(res, nombre, precios) if res.get("perfil") == PERFIL_AGAR else desafio_tomate(res, nombre, precios)


# ================================================================== compatibilidad con el desafío
def a_desafio(res: dict, usar: str = "serie", titulo: str | None = None, rubro: str = "todos", producto: str | None = None,
              enunciado: str | None = None, precios: list | None = None) -> dict:
    """Desafío (formato de motor/desafio.py) con la serie del perfil (usar «serie») o su pronóstico (usar «pronostico»).
    Pasa desafio.validar si la serie suma más que cero."""
    if usar == "pronostico":
        vals = list((res.get("extra") or {}).get("pronostico") or [])
        if not vals:
            raise ValueError("Este perfil no tiene pronóstico")
        et = [f"Pronóstico {i + 1}" for i in range(len(vals))]
    else:
        vals = list(res["serie"]); et = list(res["etiquetas"])
    fuente = (f"Perfil de demanda «{res['nombre']}» ({res['perfil']}, motor/demanda.py, PAT 136, semilla {res['semilla']}"
              + (", pronóstico " + str((res.get('extra') or {}).get('nombre_metodo', '')) if usar == "pronostico" else "") + "). "
              + "; ".join(f"{s['nombre']}: {s['valor']} {s['unidad']} ({s['fuente']})".replace("  ", " ") for s in res["supuestos"]))
    return dict(titulo=titulo or f"Demanda: {res['nombre']}", producto=producto or res["nombre"], rubro=rubro,
                enunciado=enunciado or f"diseñar una planta que atienda la demanda del perfil «{res['nombre']}».",
                autor="Perfil de demanda (PAT 136)", activo=True,
                demanda=dict(periodo=res["periodo"], unidad=res["unidad"], valores=[float(v) for v in vals], etiquetas=et, fuente=fuente),
                precios=[dict(p) for p in (precios or [])])


def estado_desafio(res: dict, actual: dict | None = None, usar: str = "serie", nombre: str = "", tratamiento: str = "",
                   rubro: str = "todos") -> dict:
    """Lo que queda en st.session_state["desafio"] al llevar la serie al desafío. Con un desafío en curso (actual) se reemplaza
    solo su demanda (periodo, unidad, valores, etiquetas, t/h y fuente) y se conserva todo lo demás; sin él se arma uno nuevo
    con desafio.estado_sesion. Siempre pasa por desafio.validar."""
    from . import desafio as D
    if actual:
        d = a_desafio(res, usar, titulo=actual.get("titulo"), rubro=actual.get("rubro") or rubro, producto=actual.get("producto"),
                      enunciado=actual.get("enunciado"), precios=actual.get("precios"))
        nuevo = D.estado_sesion(d, actual.get("nombre", nombre), actual.get("tratamiento", tratamiento))
        out = dict(actual)
        for k in ("periodo", "unidad", "demanda", "etiquetas", "demanda_t_h", "fuente_demanda"):
            out[k] = nuevo[k]
    else:
        out = D.estado_sesion(a_desafio(res, usar, rubro=rubro), nombre, tratamiento)
    out["perfil_demanda"] = res["perfil"]
    return out
