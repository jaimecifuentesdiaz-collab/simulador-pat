"""Ajuste de distribuciones como ExpertFit (PAT 134): máxima verosimilitud, pruebas de bondad de ajuste (Law, 2015, cap. 6),
empírica, histograma, gráfico y series de ejemplo."""
import json
import math
import random
import pytest
from pat_sim.motor import ajuste as A


def _muestra(gen, n=3000, semilla=7):
    rng = random.Random(semilla)
    return [gen(rng) for _ in range(n)]


@pytest.mark.parametrize("nombre, gen, esperado", [
    ("normal", lambda r: r.gauss(10, 2), dict(media=10, desviacion=2)),
    ("lognormal", lambda r: r.lognormvariate(1.0, 0.4), dict(mu=1.0, sigma=0.4)),
    ("exponencial", lambda r: r.expovariate(0.5), dict(escala=2.0)),
    ("weibull", lambda r: r.weibullvariate(3.0, 2.0), dict(escala=3.0, forma=2.0)),
    ("gamma", lambda r: r.gammavariate(3.0, 1.5), dict(forma=3.0, escala=1.5)),
    ("triangular", lambda r: r.triangular(2.0, 10.0, 4.0), dict(minimo=2.0, moda=4.0, maximo=10.0)),
    ("uniforme", lambda r: r.uniform(2.0, 6.0), dict(minimo=2.0, maximo=6.0)),
])
def test_recupera_parametros_conocidos(nombre, gen, esperado):
    d = A.ajustar_dist(nombre, _muestra(gen))
    for k, v in esperado.items():
        assert d["parametros"][k] == pytest.approx(v, rel=0.08, abs=0.25 if nombre == "triangular" and k == "moda" else 1e-9)


def test_newton_de_weibull_y_gamma_cumple_las_ecuaciones():
    x = _muestra(lambda r: r.weibullvariate(2.0, 1.5), 500, 3)
    w = A.ajustar_dist("weibull", x)["parametros"]; a = w["forma"]
    s0 = sum(v ** a for v in x); s1 = sum(v ** a * math.log(v) for v in x)
    assert s1 / s0 - 1 / a - sum(map(math.log, x)) / len(x) == pytest.approx(0, abs=1e-9)
    g = A.ajustar_dist("gamma", x)["parametros"]
    lhs = math.log(g["forma"]) - A.digamma(g["forma"])
    assert lhs == pytest.approx(math.log(sum(x) / len(x)) - sum(map(math.log, x)) / len(x), rel=1e-9)
    assert g["forma"] * g["escala"] == pytest.approx(sum(x) / len(x), rel=1e-12)


def test_funciones_especiales():
    assert A.digamma(1.0) == pytest.approx(-0.5772156649015329, rel=1e-10)
    assert A.trigamma(1.0) == pytest.approx(math.pi ** 2 / 6, rel=1e-9)
    assert A.digamma(0.5) == pytest.approx(-0.5772156649015329 - 2 * math.log(2), rel=1e-10)
    assert A.gamma_inc(1.0, 2.0) == pytest.approx(1 - math.exp(-2), rel=1e-12)
    assert A.chi2_critico(0.05, 1) == pytest.approx(3.8415, abs=1e-3) and A.chi2_critico(0.05, 10) == pytest.approx(18.307, abs=1e-3)


def test_la_mejor_de_una_muestra_weibull_es_weibull_o_gamma():
    r = A.ajustar(_muestra(lambda g: g.weibullvariate(4.0, 1.8), 1500, 11))
    assert r["lista"][0]["nombre"] in ("weibull", "gamma") and r["mejor"]["nombre"] in ("weibull", "gamma")
    assert len(r["lista"]) == 7 and [x["rango"] for x in r["lista"]] == list(range(1, 8))
    ad = [x["ad"]["estadistico"] for x in r["lista"]]
    assert ad == sorted(ad)
    assert r["lista"][0]["expresion"].startswith(("weibull(0, ", "gamma(0, "))
    json.dumps(r["mejor"]); json.dumps(r["lista"][0]["dist"])                  # serializable


def test_estadisticos_contra_calculo_a_mano():
    x = [1.0, 2.0, 3.0, 4.0, 5.0]; d = A.crear("uniforme", minimo=0.0, maximo=6.0)
    pr = A.pruebas(x, d, k=2)
    assert pr["ks"]["estadistico"] == pytest.approx(1 / 6, rel=1e-12)          # D+ = D− = 1/6
    assert pr["ks"]["ajustado"] == pytest.approx((math.sqrt(5) + 0.12 + 0.11 / math.sqrt(5)) / 6, rel=1e-12)
    F = [i / 6 for i in range(1, 6)]
    a2 = -5 - sum((2 * i - 1) * (math.log(F[i - 1]) + math.log(1 - F[5 - i])) for i in range(1, 6)) / 5
    assert pr["ad"]["estadistico"] == pytest.approx(a2, rel=1e-12)
    assert pr["chi2"]["observadas"] == [2, 3] and pr["chi2"]["estadistico"] == pytest.approx(0.2, rel=1e-12)
    assert pr["chi2"]["gl"] == 1 and pr["pasa_5"] and pr["pasa_10"]
    malo = A.pruebas(x, A.crear("exponencial", escala=0.2))
    assert malo["ks"]["rechaza_5"] and malo["ad"]["rechaza_5"] and not malo["pasa_5"]


def test_k_de_chi_cuadrado():
    assert A.k_chi2(5) == 3 and A.k_chi2(50) == 10 and A.k_chi2(1000) == math.ceil(2 * 1000 ** 0.4)
    assert all(n / A.k_chi2(n) >= 5 for n in range(15, 2000, 37))


@pytest.mark.parametrize("valores, texto", [([1, 2, 3, 4], "al menos 5"), ([2, 2, 2, 2, 2, 2], "iguales"), ([1, 2, "x", 4, 5], "números"),
                                            ([1, 2, float("nan"), 4, 5], "NaN")])
def test_datos_invalidos(valores, texto):
    try:
        A.ajustar(valores)
    except ValueError as e:
        assert texto in str(e)
    else:
        raise AssertionError("debía rechazar los datos")


def test_negativos_solo_en_las_de_soporte_positivo():
    x = _muestra(lambda r: r.gauss(0.5, 1.0), 200, 2)
    with pytest.raises(ValueError):
        A.ajustar_dist("weibull", x)
    r = A.ajustar(x)
    assert {z["nombre"] for z in r["lista"]} == {"normal", "triangular", "uniforme"} and any("positivos" in a for a in r["avisos"])


def test_muestreo_reproducible_y_momentos():
    for nombre in A.NOMBRES:
        d = A.ajustar_dist(nombre, _muestra(lambda r: r.gammavariate(4.0, 0.5), 400, 5))
        a = [A.muestrear(d, random.Random(9)) for _ in range(3)]; b = [A.muestrear(d, random.Random(9)) for _ in range(3)]
        assert a == b
        rng = random.Random(1); m = [A.muestrear(d, rng) for _ in range(20000)]
        assert sum(m) / len(m) == pytest.approx(A.media(d), rel=0.03)
        mu = sum(m) / len(m)
        assert math.sqrt(sum((v - mu) ** 2 for v in m) / len(m)) == pytest.approx(A.desviacion(d), rel=0.05)
        assert d["expresion"] and A.cdf(d, A.media(d) + 50 * A.desviacion(d)) == pytest.approx(1.0, abs=1e-6)


def test_empirica_cuando_ninguna_pasa():
    x = _muestra(lambda r: r.gauss(2, 0.2) if r.random() < 0.5 else r.gauss(8, 0.3), 1000, 4)    # bimodal
    r = A.ajustar(x)
    assert not any(z["pasa_5"] for z in r["lista"]) and r["mejor"]["nombre"] == "empirica"
    e = r["mejor"]; X = e["parametros"]["puntos"]
    assert A.cdf(e, X[0]) == 0 and A.cdf(e, X[-1]) == 1 and A.cdf(e, X[499]) == pytest.approx(499 / 999)
    v = [A.muestrear(e, random.Random(3)) for _ in range(50)]
    assert all(X[0] <= z <= X[-1] for z in v) and A.media(e) == pytest.approx(sum(x) / len(x), rel=0.01)


def test_histograma_y_grafico():
    x = _muestra(lambda r: r.weibullvariate(3.0, 2.0), 300, 8); d = A.ajustar_dist("weibull", x)
    h = A.histograma(x, d, 12)
    assert h["k"] == 12 and sum(h["frecuencias"]) == 300 and len(h["bordes"]) == 13
    assert sum(f * h["ancho"] for f in h["densidad"]) == pytest.approx(1.0)
    assert sum(h["esperadas"]) == pytest.approx(300 * (A.cdf(d, h["bordes"][-1]) - A.cdf(d, h["bordes"][0])))
    svg = A.grafico_svg(x, d)
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "polyline" in svg and "weibull(0, " in svg


def test_leer_valores_con_coma_decimal():
    assert A.leer_valores("1,5\n2,25; 3\t4.5\n\n1.234,5") == [1.5, 2.25, 3.0, 4.5, 1234.5]
    assert A.leer_csv("Descarga;Falla\n1,5;2\n2,5;3\n")["Falla"] == [2.0, 3.0]
    assert A.leer_csv("h\n1,5\n2,5\n") == {"h": [1.5, 2.5]}
    with pytest.raises(ValueError):
        A.leer_valores("1; dos; 3")


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_series_de_ejemplo(rubro):
    for serie in A.SERIES:
        a = A.ejemplo(rubro, serie); b = A.ejemplo(rubro, serie)
        assert a["valores"] == b["valores"] and len(a["valores"]) >= 80 and min(a["valores"]) > 0
        assert "Supuesto" not in a["supuesto"].nombre and str(a["semilla"]) in a["supuesto"].justificacion
        r = A.ajustar(a["valores"])
        assert r["mejor"]["nombre"] in A.NOMBRES + ["empirica"]
        assert r["resumen"]["media"] == pytest.approx(A.media(a["generadora"]), rel=0.2)
