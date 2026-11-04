"""Ajuste de distribuciones a datos medidos, como ExpertFit de FlexSim (PAT 134).

Método de Law (2015, cap. 6): se estiman los parámetros de cada distribución candidata por máxima verosimilitud, se compara
el histograma con la densidad ajustada y se aplican tres pruebas de bondad de ajuste (chi-cuadrado con intervalos
equiprobables, Kolmogorov-Smirnov y Anderson-Darling). Si ninguna distribución pasa, se ofrece la distribución empírica
continua lineal por tramos que define Law (2015, cap. 6).

Referencias: Law, A. M. (2015). Simulation modeling and analysis (5.ª ed.). McGraw-Hill Education.
Stephens, M. A. (1974). EDF statistics for goodness of fit and some comparisons. Journal of the American Statistical
Association, 69(347), 730-737 (valores críticos de K-S modificado y de A-D cuando todos los parámetros son conocidos).
Sturges, H. A. (1926). The choice of a class interval. Journal of the American Statistical Association, 21(153), 65-66.

Advertencia (Law, 2015, cap. 6): los valores críticos de K-S y A-D de Stephens (1974) son para parámetros conocidos; con
parámetros estimados de los mismos datos las pruebas son conservadoras (rechazan menos de lo que dice el nivel). En
chi-cuadrado se usan k − 1 grados de libertad, también conservador cuando los parámetros se estiman por máxima verosimilitud.
Una distribución es un dict serializable dict(nombre, etiqueta, parametros, expresion, media, desviacion, nota); las
funciones de este módulo leen solo nombre y parametros.
"""
from __future__ import annotations
import html as _h
import math
import random
import numpy as np
from .operacion import Supuesto

NOMBRES = ["normal", "lognormal", "exponencial", "weibull", "gamma", "triangular", "uniforme"]
ETIQUETA = dict(normal="Normal", lognormal="Lognormal", exponencial="Exponencial", weibull="Weibull", gamma="Gamma",
                triangular="Triangular", uniforme="Uniforme", empirica="Empírica lineal por tramos")
POSITIVAS = {"lognormal", "exponencial", "weibull", "gamma"}
KS_CRITICO = {0.10: 1.224, 0.05: 1.358}      # Stephens (1974): D·(√n + 0,12 + 0,11/√n), todos los parámetros conocidos
AD_CRITICO = {0.10: 1.933, 0.05: 2.492}      # Stephens (1974): A², todos los parámetros conocidos
NIVELES = (0.05, 0.10)
CRITERIO = ("Se ordena por el estadístico de Anderson-Darling (menor es mejor), que pesa más las colas de la distribución "
            "(Law, 2015, cap. 6); en empate decide Kolmogorov-Smirnov. Una distribución pasa a un nivel cuando ninguna de las "
            "tres pruebas la rechaza a ese nivel.")
SUPUESTOS = [
    Supuesto("k_chi2", "Número de intervalos equiprobables de la prueba chi-cuadrado", 0, "intervalos",
             "Law (2015, cap. 6) pide intervalos equiprobables, k ≥ 3 y al menos 5 datos esperados por intervalo (n/k ≥ 5); dentro de "
             "eso se usa k = mín(⌊n/5⌋, ⌈2·n^0,4⌉), regla práctica de PAT 134 para no partir la muestra en intervalos muy chicos"),
    Supuesto("extremos", "Mínimo y máximo de la triangular y la uniforme", 0, "—",
             "Se amplían el mínimo y el máximo de la muestra en (máximo − mínimo)/(n − 1), el estimador insesgado de los extremos de "
             "la uniforme; así ningún dato cae justo en el borde, donde Anderson-Darling no está definido. La moda de la triangular es "
             "la de máxima verosimilitud con esos extremos fijos (se busca entre los datos)"),
]


# ----------------------------------------------------------------------------------------------- funciones especiales
def digamma(x: float) -> float:
    """Función digamma ψ(x) por recurrencia y serie asintótica (x > 0)."""
    if x <= 0:
        raise ValueError("La digamma se usa solo con argumento positivo.")
    r = 0.0
    while x < 6.0:
        r -= 1.0 / x; x += 1.0
    f = 1.0 / (x * x)
    return r + math.log(x) - 0.5 / x - f * (1 / 12 - f * (1 / 120 - f * (1 / 252 - f * (1 / 240 - f * (1 / 132)))))


def trigamma(x: float) -> float:
    """Función trigamma ψ'(x) por recurrencia y serie asintótica (x > 0)."""
    if x <= 0:
        raise ValueError("La trigamma se usa solo con argumento positivo.")
    r = 0.0
    while x < 6.0:
        r += 1.0 / (x * x); x += 1.0
    f = 1.0 / (x * x)
    return r + 1.0 / x + f / 2 + (1.0 / (x * x * x)) * (1 / 6 - f * (1 / 30 - f * (1 / 42 - f * (1 / 30))))


def gamma_inc(a: float, x: float) -> float:
    """Función gamma incompleta regularizada inferior P(a, x): serie si x < a + 1 y fracción continua si no."""
    if x <= 0:
        return 0.0
    lg = a * math.log(x) - x - math.lgamma(a)
    if x < a + 1:
        s = t = 1.0 / a; ap = a
        for _ in range(10000):
            ap += 1; t *= x / ap; s += t
            if abs(t) < abs(s) * 1e-15:
                break
        return min(1.0, s * math.exp(lg))
    b = x + 1 - a; c = 1e300; d = 1 / b; hh = d
    for i in range(1, 10000):
        an = -i * (i - a); b += 2
        d = an * d + b; d = 1e-300 if abs(d) < 1e-300 else d
        c = b + an / c; c = 1e-300 if abs(c) < 1e-300 else c
        d = 1 / d; de = d * c; hh *= de
        if abs(de - 1) < 1e-15:
            break
    return max(0.0, 1.0 - math.exp(lg) * hh)


def chi2_sf(x: float, gl: int) -> float:
    """Probabilidad de superar x en una chi-cuadrado con gl grados de libertad."""
    return 1.0 - gamma_inc(gl / 2, x / 2) if x > 0 else 1.0


def chi2_critico(alfa: float, gl: int) -> float:
    """Valor crítico de la chi-cuadrado: x con P(χ² > x) = alfa (bisección sobre la gamma incompleta)."""
    lo, hi = 0.0, max(10.0, gl * 10.0)
    while chi2_sf(hi, gl) > alfa:
        hi *= 2
    for _ in range(200):
        m = (lo + hi) / 2
        lo, hi = (m, hi) if chi2_sf(m, gl) > alfa else (lo, m)
    return (lo + hi) / 2


def _phi(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))


# ----------------------------------------------------------------------------------------------- validación y lectura
def validar(valores, positivos: bool = False) -> list[float]:
    """Lista de floats finitos; ValueError en español si hay menos de 5, si todos son iguales o, con positivos, si hay
    valores negativos (o cero, que tampoco admiten la lognormal, Weibull y gamma)."""
    try:
        x = [float(v) for v in valores]
    except (TypeError, ValueError):
        raise ValueError("Los datos deben ser números.")
    if any(not math.isfinite(v) for v in x):
        raise ValueError("Hay datos vacíos o no numéricos (NaN o infinito).")
    if len(x) < 5:
        raise ValueError(f"Se necesitan al menos 5 valores para ajustar una distribución; hay {len(x)}.")
    if max(x) - min(x) <= 1e-12 * max(1.0, abs(max(x))):
        raise ValueError("Todos los valores son iguales: no hay variabilidad que ajustar (use un valor constante).")
    if positivos and min(x) <= 0:
        raise ValueError("Hay valores negativos o cero: esta distribución solo admite valores positivos.")
    return x


def _numero(tok: str) -> float:
    t = tok.strip().replace(" ", "").replace(" ", "")
    if "," in t and "." in t:                     # 1.234,5 (miles con punto) o 1,234.5
        t = t.replace(".", "").replace(",", ".") if t.rfind(",") > t.rfind(".") else t.replace(",", "")
    elif "," in t:
        t = t.replace(",", ".")
    return float(t)


def leer_valores(texto: str) -> list[float]:
    """Lee valores pegados: uno por línea o separados por punto y coma, tabulación o espacio; acepta coma decimal chilena."""
    import re
    toks = [t for t in re.split(r"[\n\r;\t ]+", texto or "") if t.strip()]
    out = []
    for t in toks:
        try:
            out.append(_numero(t))
        except ValueError:
            raise ValueError(f"No se pudo leer «{t}» como número.")
    return out


def leer_csv(texto: str) -> dict:
    """Columnas numéricas de un CSV (separador punto y coma, tabulación o coma; coma decimal aceptada).
    Devuelve {nombre de columna: [valores]}; la primera fila es encabezado si no es numérica."""
    import re
    lineas = [l for l in (texto or "").replace("\r", "").split("\n") if l.strip()]
    if not lineas:
        raise ValueError("El archivo está vacío.")
    if any(";" in l for l in lineas):
        sep = ";"
    elif any("\t" in l for l in lineas):
        sep = "\t"
    elif all(re.fullmatch(r"\s*-?\d+(,\d+)?\s*", l) for l in lineas[1:] or lineas):
        sep = None                                 # una columna con coma decimal
    else:
        sep = ","
    filas = [[c.strip().strip('"') for c in (l.split(sep) if sep else [l])] for l in lineas]
    def es_num(c):
        try:
            _numero(c); return True
        except ValueError:
            return False
    enc = filas[0] if not all(es_num(c) for c in filas[0] if c) else [f"Columna {i + 1}" for i in range(len(filas[0]))]
    datos = filas[1:] if enc is filas[0] else filas
    out = {}
    for i, nombre in enumerate(enc):
        vals = [_numero(f[i]) for f in datos if i < len(f) and f[i] and es_num(f[i])]
        if vals:
            out[nombre or f"Columna {i + 1}"] = vals
    if not out:
        raise ValueError("El archivo no tiene columnas numéricas.")
    return out


# ----------------------------------------------------------------------------------------------- distribuciones
def _g(v: float) -> str:
    return f"{v:.6g}"


def expresion(dist: dict) -> str:
    """Expresión al estilo de FlexSim (sin el argumento de la secuencia de números aleatorios)."""
    n, p = dist["nombre"], dist["parametros"]
    if n == "normal":
        return f"normal({_g(p['media'])}, {_g(p['desviacion'])})"
    if n == "lognormal":
        return f"lognormal2(0, {_g(math.exp(p['mu']))}, {_g(p['sigma'])})"
    if n == "exponencial":
        return f"exponential(0, {_g(p['escala'])})"
    if n == "weibull":
        return f"weibull(0, {_g(p['escala'])}, {_g(p['forma'])})"
    if n == "gamma":
        return f"gamma(0, {_g(p['escala'])}, {_g(p['forma'])})"
    if n == "triangular":
        return f"triangular({_g(p['minimo'])}, {_g(p['maximo'])}, {_g(p['moda'])})"
    if n == "uniforme":
        return f"uniform({_g(p['minimo'])}, {_g(p['maximo'])})"
    if n == "empirica":
        return 'cempirical("Tabla_ajuste")'
    raise ValueError(f"Distribución desconocida: {n}.")


def texto_parametros(dist: dict) -> str:
    """Parámetros en formato chileno para las tablas."""
    p = dist["parametros"]; f = lambda v: f"{v:,.4g}".replace(",", "X").replace(".", ",").replace("X", ".")
    t = {"normal": lambda: f"media {f(p['media'])}; desviación {f(p['desviacion'])}",
         "lognormal": lambda: f"μ del logaritmo {f(p['mu'])}; σ del logaritmo {f(p['sigma'])}",
         "exponencial": lambda: f"media {f(p['escala'])}",
         "weibull": lambda: f"forma {f(p['forma'])}; escala {f(p['escala'])}",
         "gamma": lambda: f"forma {f(p['forma'])}; escala {f(p['escala'])}",
         "triangular": lambda: f"mínimo {f(p['minimo'])}; moda {f(p['moda'])}; máximo {f(p['maximo'])}",
         "uniforme": lambda: f"mínimo {f(p['minimo'])}; máximo {f(p['maximo'])}",
         "empirica": lambda: f"{len(p['puntos'])} puntos de {f(p['puntos'][0])} a {f(p['puntos'][-1])}"}
    return t[dist["nombre"]]()


def crear(nombre: str, nota: str = "", **parametros) -> dict:
    """Arma el dict serializable de una distribución con su expresión, media y desviación."""
    if nombre not in ETIQUETA:
        raise ValueError(f"Distribución desconocida: {nombre}.")
    d = dict(nombre=nombre, etiqueta=ETIQUETA[nombre], parametros={k: (list(map(float, v)) if isinstance(v, (list, tuple)) else float(v))
                                                                    for k, v in parametros.items()}, nota=nota)
    d["expresion"] = expresion(d); d["media"] = media(d); d["desviacion"] = desviacion(d)
    return d


def cdf(dist: dict, x: float) -> float:
    n, p = dist["nombre"], dist["parametros"]
    if n == "normal":
        return _phi((x - p["media"]) / p["desviacion"])
    if n in POSITIVAS and x <= 0:
        return 0.0
    if n == "lognormal":
        return _phi((math.log(x) - p["mu"]) / p["sigma"])
    if n == "exponencial":
        return 1 - math.exp(-x / p["escala"])
    if n == "weibull":
        return 1 - math.exp(-(x / p["escala"]) ** p["forma"])
    if n == "gamma":
        return gamma_inc(p["forma"], x / p["escala"])
    if n == "triangular":
        a, c, b = p["minimo"], p["moda"], p["maximo"]
        if x <= a:
            return 0.0
        if x >= b:
            return 1.0
        return (x - a) ** 2 / ((b - a) * (c - a)) if x <= c and c > a else 1 - (b - x) ** 2 / ((b - a) * (b - c))
    if n == "uniforme":
        return min(1.0, max(0.0, (x - p["minimo"]) / (p["maximo"] - p["minimo"])))
    if n == "empirica":
        X = p["puntos"]; m = len(X) - 1
        if x <= X[0]:
            return 0.0
        if x >= X[-1]:
            return 1.0
        import bisect
        i = bisect.bisect_right(X, x) - 1
        w = X[i + 1] - X[i]
        return (i + ((x - X[i]) / w if w > 0 else 1.0)) / m
    raise ValueError(f"Distribución desconocida: {n}.")


def pdf(dist: dict, x: float) -> float:
    n, p = dist["nombre"], dist["parametros"]
    if n == "normal":
        s = p["desviacion"]; return math.exp(-0.5 * ((x - p["media"]) / s) ** 2) / (s * math.sqrt(2 * math.pi))
    if n in POSITIVAS and x <= 0:
        return 0.0
    if n == "lognormal":
        s = p["sigma"]; return math.exp(-0.5 * ((math.log(x) - p["mu"]) / s) ** 2) / (x * s * math.sqrt(2 * math.pi))
    if n == "exponencial":
        return math.exp(-x / p["escala"]) / p["escala"]
    if n == "weibull":
        a, b = p["forma"], p["escala"]; return a / b * (x / b) ** (a - 1) * math.exp(-(x / b) ** a)
    if n == "gamma":
        a, b = p["forma"], p["escala"]
        return math.exp((a - 1) * math.log(x) - x / b - math.lgamma(a) - a * math.log(b))
    if n == "triangular":
        a, c, b = p["minimo"], p["moda"], p["maximo"]
        if x < a or x > b:
            return 0.0
        return 2 * (x - a) / ((b - a) * (c - a)) if x <= c and c > a else 2 * (b - x) / ((b - a) * (b - c)) if b > c else 0.0
    if n == "uniforme":
        a, b = p["minimo"], p["maximo"]; return 1 / (b - a) if a <= x <= b else 0.0
    if n == "empirica":
        X = p["puntos"]; m = len(X) - 1
        if x < X[0] or x > X[-1]:
            return 0.0
        import bisect
        i = min(m - 1, bisect.bisect_right(X, x) - 1); w = X[i + 1] - X[i]
        return 1 / (m * w) if w > 0 else 0.0
    raise ValueError(f"Distribución desconocida: {n}.")


def _momentos(dist: dict) -> tuple:
    n, p = dist["nombre"], dist["parametros"]
    if n == "normal":
        return p["media"], p["desviacion"] ** 2
    if n == "lognormal":
        s2 = p["sigma"] ** 2; return math.exp(p["mu"] + s2 / 2), (math.exp(s2) - 1) * math.exp(2 * p["mu"] + s2)
    if n == "exponencial":
        return p["escala"], p["escala"] ** 2
    if n == "weibull":
        a, b = p["forma"], p["escala"]; g1 = math.gamma(1 + 1 / a); g2 = math.gamma(1 + 2 / a)
        return b * g1, b * b * (g2 - g1 * g1)
    if n == "gamma":
        return p["forma"] * p["escala"], p["forma"] * p["escala"] ** 2
    if n == "triangular":
        a, c, b = p["minimo"], p["moda"], p["maximo"]
        return (a + b + c) / 3, (a * a + b * b + c * c - a * b - a * c - b * c) / 18
    if n == "uniforme":
        a, b = p["minimo"], p["maximo"]; return (a + b) / 2, (b - a) ** 2 / 12
    if n == "empirica":
        X = p["puntos"]; m = len(X) - 1
        e1 = sum((X[i] + X[i + 1]) / 2 for i in range(m)) / m
        e2 = sum((X[i] ** 2 + X[i] * X[i + 1] + X[i + 1] ** 2) / 3 for i in range(m)) / m
        return e1, max(0.0, e2 - e1 * e1)
    raise ValueError(f"Distribución desconocida: {n}.")


def media(dist: dict) -> float:
    """Media de la distribución."""
    return _momentos(dist)[0]


def desviacion(dist: dict) -> float:
    """Desviación estándar de la distribución."""
    return math.sqrt(_momentos(dist)[1])


def muestrear(dist: dict, rng: random.Random) -> float:
    """Un valor al azar de la distribución con el generador rng (reproducible con su semilla)."""
    n, p = dist["nombre"], dist["parametros"]
    if n == "normal":
        return rng.gauss(p["media"], p["desviacion"])
    if n == "lognormal":
        return rng.lognormvariate(p["mu"], p["sigma"])
    if n == "exponencial":
        return rng.expovariate(1 / p["escala"])
    if n == "weibull":
        return rng.weibullvariate(p["escala"], p["forma"])
    if n == "gamma":
        return rng.gammavariate(p["forma"], p["escala"])
    if n == "triangular":
        return rng.triangular(p["minimo"], p["maximo"], p["moda"])
    if n == "uniforme":
        return rng.uniform(p["minimo"], p["maximo"])
    if n == "empirica":                          # inversa de la empírica lineal por tramos (Law, 2015, cap. 6)
        X = p["puntos"]; m = len(X) - 1; P = m * rng.random(); i = min(m - 1, int(P))
        return X[i] + (P - i) * (X[i + 1] - X[i])
    raise ValueError(f"Distribución desconocida: {n}.")


# ----------------------------------------------------------------------------------------------- máxima verosimilitud
def _weibull(x: np.ndarray) -> tuple:
    """Forma y escala de Weibull por máxima verosimilitud (Newton sobre la ecuación de la forma; Law, 2015, cap. 6)."""
    y = x / x.max(); ly = np.log(y); mly = ly.mean(); n = len(x)
    a = ((6 / math.pi ** 2) * (np.sum(ly ** 2) - np.sum(ly) ** 2 / n) / (n - 1)) ** -0.5   # valor de partida
    for _ in range(200):
        ya = y ** a; s0 = ya.sum(); s1 = (ya * ly).sum(); s2 = (ya * ly * ly).sum()
        f = s1 / s0 - 1 / a - mly
        fp = (s2 * s0 - s1 * s1) / (s0 * s0) + 1 / (a * a)
        nuevo = a - f / fp
        if nuevo <= 0:
            nuevo = a / 2
        if abs(nuevo - a) < 1e-12 * a:
            a = nuevo; break
        a = nuevo
    return a, float(x.max() * (np.mean(y ** a)) ** (1 / a))


def _gamma(x: np.ndarray) -> tuple:
    """Forma y escala de gamma por máxima verosimilitud: ln α − ψ(α) = ln(media) − media(ln x), Newton con trigamma."""
    A = math.log(x.mean()) - float(np.log(x).mean())
    a = (3 - A + math.sqrt((A - 3) ** 2 + 24 * A)) / (12 * A)         # valor de partida cercano
    for _ in range(200):
        f = math.log(a) - digamma(a) - A; fp = 1 / a - trigamma(a)
        nuevo = a - f / fp
        if nuevo <= 0:
            nuevo = a / 2
        if abs(nuevo - a) < 1e-12 * a:
            a = nuevo; break
        a = nuevo
    return a, float(x.mean()) / a


def _triangular(x: np.ndarray) -> tuple:
    """Extremos ampliados (Supuesto «extremos») y moda de máxima verosimilitud entre los datos con esos extremos fijos."""
    xs = np.sort(x); n = len(xs); r = xs[-1] - xs[0]
    a = xs[0] - r / (n - 1); b = xs[-1] + r / (n - 1)
    pre = np.concatenate([[0.0], np.cumsum(np.log(xs - a))])          # suma de ln(x − a) de los datos bajo la moda
    suf = np.concatenate([np.cumsum(np.log(b - xs)[::-1])[::-1], [0.0]])
    r_ = np.arange(n); c = xs
    L = pre[r_] - r_ * np.log(c - a) + suf[r_] - (n - r_) * np.log(b - c)
    return float(a), float(c[int(np.argmax(L))]), float(b)


def ajustar_dist(nombre: str, valores) -> dict:
    """Ajusta una distribución por máxima verosimilitud. ValueError si los datos no sirven para ella."""
    x = np.array(validar(valores, positivos=nombre in POSITIVAS), dtype=float); n = len(x)
    if nombre == "normal":
        return crear("normal", media=x.mean(), desviacion=x.std())
    if nombre == "lognormal":
        lx = np.log(x); return crear("lognormal", mu=lx.mean(), sigma=lx.std())
    if nombre == "exponencial":
        return crear("exponencial", escala=x.mean())
    if nombre == "weibull":
        a, b = _weibull(x); return crear("weibull", forma=a, escala=b)
    if nombre == "gamma":
        a, b = _gamma(x); return crear("gamma", forma=a, escala=b)
    if nombre == "triangular":
        a, c, b = _triangular(x)
        return crear("triangular", nota=SUPUESTOS[1].justificacion, minimo=a, moda=c, maximo=b)
    if nombre == "uniforme":
        r = x.max() - x.min()
        return crear("uniforme", nota=SUPUESTOS[1].justificacion, minimo=x.min() - r / (n - 1), maximo=x.max() + r / (n - 1))
    if nombre == "empirica":
        return empirica(valores)
    raise ValueError(f"Distribución desconocida: {nombre}.")


def empirica(valores) -> dict:
    """Distribución empírica continua lineal por tramos de Law (2015, cap. 6) sobre los datos ordenados."""
    x = sorted(validar(valores))
    return crear("empirica", nota="Empírica continua lineal por tramos (Law, 2015, cap. 6): no extrapola fuera del mínimo y el "
                                  "máximo medidos", puntos=x)


# ----------------------------------------------------------------------------------------------- pruebas de bondad de ajuste
def k_chi2(n: int) -> int:
    """Intervalos equiprobables de la prueba chi-cuadrado (Supuesto «k_chi2»)."""
    return max(3, min(n // 5, math.ceil(2 * n ** 0.4)))


def pruebas(valores, dist: dict, k: int | None = None) -> dict:
    """Chi-cuadrado con k intervalos equiprobables, Kolmogorov-Smirnov y Anderson-Darling, con decisión al 5 % y 10 %."""
    x = sorted(float(v) for v in valores); n = len(x)
    F = [min(1 - 1e-15, max(1e-15, cdf(dist, v))) for v in x]
    k = k_chi2(n) if k is None else max(2, int(k))
    N = [0] * k
    for u in F:
        N[min(k - 1, int(u * k))] += 1
    e = n / k; chi = sum((o - e) ** 2 / e for o in N); gl = k - 1
    chi_r = dict(estadistico=chi, k=k, gl=gl, observadas=N, esperada=e, p=chi2_sf(chi, gl),
                 **{f"critico_{int(100 * a)}": chi2_critico(a, gl) for a in NIVELES})
    dp = max((i + 1) / n - F[i] for i in range(n)); dm = max(F[i] - i / n for i in range(n)); D = max(dp, dm)
    Dm = (math.sqrt(n) + 0.12 + 0.11 / math.sqrt(n)) * D
    p_ks = max(0.0, min(1.0, 2 * sum((-1) ** (j - 1) * math.exp(-2 * j * j * Dm * Dm) for j in range(1, 101)))) if Dm > 0 else 1.0
    ks_r = dict(estadistico=D, ajustado=Dm, p=p_ks, **{f"critico_{int(100 * a)}": KS_CRITICO[a] for a in NIVELES})
    A2 = -n - sum((2 * i + 1) * (math.log(F[i]) + math.log(1 - F[n - 1 - i])) for i in range(n)) / n
    ad_r = dict(estadistico=A2, **{f"critico_{int(100 * a)}": AD_CRITICO[a] for a in NIVELES})
    for r, val in ((chi_r, chi), (ks_r, Dm), (ad_r, A2)):
        for a in NIVELES:
            r[f"rechaza_{int(100 * a)}"] = val > r[f"critico_{int(100 * a)}"]
    pasa = {f"pasa_{int(100 * a)}": not any(r[f"rechaza_{int(100 * a)}"] for r in (chi_r, ks_r, ad_r)) for a in NIVELES}
    return dict(chi2=chi_r, ks=ks_r, ad=ad_r, **pasa)


def log_verosimilitud(valores, dist: dict) -> float:
    s = 0.0
    for v in valores:
        f = pdf(dist, float(v))
        s += math.log(f) if f > 0 else -1e300
    return s


def ajustar(valores) -> dict:
    """Ajusta las siete distribuciones, las prueba y las ordena (CRITERIO). Si ninguna pasa al 5 %, la mejor es la empírica."""
    x = validar(valores); n = len(x); avisos = []
    lista = []
    for nom in NOMBRES:
        try:
            d = ajustar_dist(nom, x)
        except ValueError:
            avisos.append(f"{ETIQUETA[nom]}: no se ajusta porque hay valores negativos o cero (solo admite valores positivos).")
            continue
        pr = pruebas(x, d)
        lista.append(dict(dist=d, nombre=nom, etiqueta=d["etiqueta"], parametros=texto_parametros(d), expresion=d["expresion"],
                          log_verosimilitud=log_verosimilitud(x, d), **pr))
    lista.sort(key=lambda r: (r["ad"]["estadistico"], r["ks"]["estadistico"]))
    for i, r in enumerate(lista):
        r["rango"] = i + 1
    emp = empirica(x)
    mejor_p = lista[0] if lista else None
    if mejor_p and mejor_p["pasa_5"]:
        mejor = mejor_p["dist"]
    else:
        mejor = emp
        avisos.append("Ninguna distribución pasa las tres pruebas al 5 %: se recomienda la empírica lineal por tramos (Law, 2015, cap. 6), "
                      "que no extrapola fuera de lo medido.")
    if n < 30:
        avisos.append(f"Con {n} datos las pruebas tienen poca potencia y casi nunca rechazan; con muchos datos rechazan diferencias "
                      "pequeñas sin importancia práctica (Law, 2015, cap. 6). Mire también el histograma.")
    if n // 5 < 3:
        avisos.append("Hay menos de 5 datos esperados por intervalo en la prueba chi-cuadrado: tómela solo como referencia.")
    m = sum(x) / n; s = math.sqrt(sum((v - m) ** 2 for v in x) / (n - 1))
    asim = sum((v - m) ** 3 for v in x) / n / (s ** 3) if s > 0 else 0.0
    resumen = dict(n=n, media=m, desviacion=s, minimo=min(x), maximo=max(x), cv=s / m if m else None, asimetria=asim,
                   mediana=float(np.median(x)))
    return dict(n=n, resumen=resumen, lista=lista, mejor=mejor, mejor_parametrica=mejor_p["dist"] if mejor_p else None, empirica=emp,
                criterio=CRITERIO, k_chi2=k_chi2(n), avisos=avisos,
                nota=("Valores críticos de K-S y A-D de Stephens (1974) para parámetros conocidos y chi-cuadrado con k − 1 grados de "
                      "libertad: con parámetros estimados las pruebas son conservadoras (Law, 2015, cap. 6)."))


# ----------------------------------------------------------------------------------------------- histograma y gráfico
def histograma(valores, dist: dict | None = None, k: int | None = None) -> dict:
    """Histograma de k clases iguales (por defecto la regla de Sturges, 1926) con la densidad de la distribución escalada a
    frecuencia (n × ancho × f(x)) y la frecuencia esperada de cada clase (n × (F(b) − F(a)))."""
    x = validar(valores); n = len(x)
    k = int(k) if k else max(5, math.ceil(1 + math.log2(n)))
    lo, hi = min(x), max(x); w = (hi - lo) / k
    bordes = [lo + i * w for i in range(k + 1)]
    frec = [0] * k
    for v in x:
        frec[min(k - 1, int((v - lo) / w))] += 1
    out = dict(k=k, ancho=w, bordes=bordes, frecuencias=frec, densidad=[f / (n * w) for f in frec], n=n)
    if dist is not None:
        a = lo - w; b = hi + w
        if dist["nombre"] in POSITIVAS:
            a = max(a, 1e-9 * max(1.0, hi))
        xs = [a + (b - a) * i / 200 for i in range(201)]
        out["curva"] = [(v, n * w * pdf(dist, v)) for v in xs]
        out["esperadas"] = [n * (cdf(dist, bordes[i + 1]) - cdf(dist, bordes[i])) for i in range(k)]
    return out


def _cl(v: float, d: int = 1) -> str:
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def grafico_svg(valores, dist: dict | None = None, k: int | None = None, ancho: int = 760, alto: int = 300, titulo: str | None = None,
                unidad: str = "h") -> str:
    """Histograma de los datos con la curva de la distribución en SVG, sin dependencias (estilo de temporada.gantt_svg)."""
    hg = histograma(valores, dist, k)
    izq, der, arriba, abajo = 56, 20, 34, 46
    curva = hg.get("curva", [])
    x0 = min([hg["bordes"][0]] + [p[0] for p in curva]); x1 = max([hg["bordes"][-1]] + [p[0] for p in curva])
    ymax = max([max(hg["frecuencias"])] + [p[1] for p in curva if math.isfinite(p[1])]) * 1.08 or 1.0
    X = lambda v: izq + (v - x0) / (x1 - x0) * (ancho - izq - der)
    Y = lambda v: alto - abajo - min(v, ymax) / ymax * (alto - abajo - arriba)
    tit = titulo or ("Histograma de los datos" + (f" y {dist['etiqueta'].lower()} ajustada" if dist else ""))
    p = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {ancho} {alto}" width="{ancho}" height="{alto}" role="img" '
         f'aria-label="{_h.escape(tit)}" style="font-family:sans-serif;background:#fff">',
         f'<rect x="0" y="0" width="{ancho}" height="{alto}" fill="#fff"/>',
         f'<text x="{izq}" y="20" font-size="13" fill="#36586c">{_h.escape(tit)} (n = {hg["n"]}, {hg["k"]} clases)</text>']
    for i in range(5):                                   # líneas de frecuencia
        v = ymax * i / 4; y = Y(v)
        p.append(f'<path d="M{izq} {y:.1f}H{ancho - der}" stroke="#eef1f2"/><text x="{izq - 6}" y="{y + 4:.1f}" font-size="10" '
                 f'text-anchor="end" fill="#555">{_cl(v, 0 if ymax > 8 else 1)}</text>')
    for i, f in enumerate(hg["frecuencias"]):
        xa, xb = X(hg["bordes"][i]), X(hg["bordes"][i + 1])
        t = f'{_cl(hg["bordes"][i], 3)} a {_cl(hg["bordes"][i + 1], 3)} {unidad}: {f} datos'
        p.append(f'<rect x="{xa:.2f}" y="{Y(f):.2f}" width="{max(0.5, xb - xa - 1):.2f}" height="{Y(0) - Y(f):.2f}" fill="#b9cdd6" '
                 f'stroke="#7f9cab"><title>{_h.escape(t)}</title></rect>')
    if curva:
        pts = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in curva if math.isfinite(b))
        p.append(f'<polyline points="{pts}" fill="none" stroke="#8b3a3a" stroke-width="2"/>')
        p.append(f'<text x="{ancho - der}" y="20" font-size="11" text-anchor="end" fill="#8b3a3a">{_h.escape(dist["expresion"])}</text>')
    for i in range(6):
        v = x0 + (x1 - x0) * i / 5; x = X(v)
        p.append(f'<text x="{x:.1f}" y="{alto - abajo + 14}" font-size="10" text-anchor="middle" fill="#555">{_cl(v, 2 if x1 - x0 < 20 else 0)}</text>')
    p.append(f'<text x="{(izq + ancho - der) / 2:.0f}" y="{alto - 10}" font-size="11" text-anchor="middle" fill="#555">Valor ({_h.escape(unidad)})</text>')
    p.append(f'<path d="M{izq} {arriba}V{Y(0):.1f}H{ancho - der}" fill="none" stroke="#9bacb3"/></svg>')
    return "".join(p)


# ----------------------------------------------------------------------------------------------- series de ejemplo
SERIES = {"descarga_h": "Tiempo de descarga de un camión (h)", "falla_h": "Duración de una detención correctiva (h)"}
_EJ = "Serie didáctica generada al azar, sin datos medidos de la planta"
_DESC = ("La media es cercana al tiempo de descarga de la pestaña Temporada (carga del camión dividida por la capacidad de recepción "
         "de partida del rubro, escenarios/capacidades.py), para que al usarla la temporada siga comparable; la forma asimétrica a la "
         "derecha es la habitual de los tiempos de servicio")
_FALLA = ("La media es cercana a la detención del simulador del profesor (Scorm_pellet_profesor.html, runShift: un turno con falla "
          "conserva 0,36 de su capacidad, es decir, unas 5,1 h detenidas de 8 h)")
EJEMPLOS = {   # rubro -> serie -> (distribución que la genera, parámetros, semilla, n, decimales)
    "tomate": {"descarga_h": ("lognormal", dict(mu=math.log(0.048) - 0.5 * 0.35 ** 2, sigma=0.35), 134001, 120, 4),
               "falla_h": ("weibull", dict(forma=1.6, escala=5.1 / math.gamma(1 + 1 / 1.6)), 134002, 80, 2)},
    "pellet": {"descarga_h": ("gamma", dict(forma=9.0, escala=2.2 / 9.0), 134011, 120, 3),
               "falla_h": ("lognormal", dict(mu=math.log(5.1) - 0.5 * 0.55 ** 2, sigma=0.55), 134012, 80, 2)},
    "chip": {"descarga_h": ("weibull", dict(forma=3.0, escala=1.2 / math.gamma(1 + 1 / 3.0)), 134021, 120, 3),
             "falla_h": ("gamma", dict(forma=2.5, escala=5.1 / 2.5), 134022, 80, 2)},
    "lena": {"descarga_h": ("lognormal", dict(mu=math.log(5.8) - 0.5 * 0.30 ** 2, sigma=0.30), 134031, 120, 3),
             "falla_h": ("weibull", dict(forma=1.4, escala=5.1 / math.gamma(1 + 1 / 1.4)), 134032, 80, 2)},
}


def ejemplo(rubro: str, serie: str) -> dict:
    """Serie de ejemplo del rubro (Supuesto didáctico con su semilla) para que el ajuste funcione sin datos medidos."""
    if serie not in SERIES:
        raise ValueError(f"Serie desconocida: {serie}.")
    nom, par, sem, n, dec = EJEMPLOS.get(rubro, EJEMPLOS["pellet"])[serie]
    g = crear(nom, **par); rng = random.Random(sem)
    vals = [round(max(10 ** -dec, muestrear(g, rng)), dec) for _ in range(n)]
    sup = Supuesto(serie, SERIES[serie], n, "datos",
                   f"{_EJ}: {n} valores de {expresion(g)} con random.Random({sem}). " + (_DESC if serie == "descarga_h" else _FALLA))
    return dict(valores=vals, supuesto=sup, generadora=g, semilla=sem)
