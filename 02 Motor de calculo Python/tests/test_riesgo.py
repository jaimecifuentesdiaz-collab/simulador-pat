"""Pruebas del análisis de riesgo de la cascada (mejora 5, PAT 133)."""
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor.resumen import resumen_planta
from pat_sim.motor import economia as eco, riesgo as R

E = dict(precio_gas=2.77, dolar=990.35, inversion=1000.0, costo_anual=20.0, anios=20, tasa=0.10, precio_biomasa=6750.0)


@pytest.fixture
def s_tomate():
    return R.supuestos(resumen_planta(agrozzi.crear()), E)


def test_van_base_coincide_con_economia_evaluacion(s_tomate):
    r = resumen_planta(agrozzi.crear())
    ahorro = eco.valor_gas(r["gas_desplazado_cascada"]["MMBtu"], E["precio_gas"], E["dolar"])
    ev = eco.evaluacion(E["inversion"], ahorro, E["costo_anual"], E["anios"], E["tasa"])
    assert s_tomate["van_base"] == pytest.approx(ev["VAN"], rel=1e-12)
    assert R.evaluacion_cascada(s_tomate["base"], s_tomate["desplazado"], "gas")["flujos"] == ev["flujos"]


def test_van_base_biomasa_coincide_con_economia_evaluacion():
    r = resumen_planta(pellet.crear()); s = R.supuestos(r, E)
    ahorro = r["biomasa_cascada"]["m3"] * E["precio_biomasa"] / 1e6        # como p_economia.mostrar_biomasa
    assert s["van_base"] == pytest.approx(eco.evaluacion(E["inversion"], ahorro, E["costo_anual"], E["anios"], E["tasa"])["VAN"], rel=1e-12)
    assert "dolar" not in s["rangos"]                                       # la biomasa ya está en pesos


def test_tornado_ordena_por_amplitud(s_tomate):
    t = R.tornado(s_tomate["base"], s_tomate["rangos"], s_tomate["fn"])
    amp = [f["amplitud"] for f in t]
    assert amp == sorted(amp, reverse=True)
    assert {f["clave"] for f in t} == set(s_tomate["rangos"])
    assert t[0]["clave"] == "precio"                       # de 2,77 a 12 US$/MMBtu: la variable que más mueve (Capítulo 4)
    for f in t:
        assert f["van_min"] <= f["van_base"] + 1e-9 <= f["van_max"] + 2e-9


def test_tornado_funcion_de_prueba():
    fn = lambda p: 3 * p["a"] - 10 * p["b"] + p["c"]
    t = R.tornado(dict(a=0, b=0, c=0), dict(a=(-1, 1), b=(-1, 1), c=(0, 1)), fn)
    assert [f["clave"] for f in t] == ["b", "a", "c"]
    assert t[0]["amplitud"] == pytest.approx(20) and t[0]["van_bajo"] == pytest.approx(10)


def test_monte_carlo_reproducible_con_la_semilla(s_tomate):
    a = R.monte_carlo(s_tomate["base"], s_tomate["distribuciones"], s_tomate["fn"], n=300, semilla=133)
    b = R.monte_carlo(s_tomate["base"], s_tomate["distribuciones"], s_tomate["fn"], n=300, semilla=133)
    c = R.monte_carlo(s_tomate["base"], s_tomate["distribuciones"], s_tomate["fn"], n=300, semilla=7)
    assert a["valores"] == b["valores"] and a["media"] == b["media"]
    assert a["valores"] != c["valores"]
    assert a["p5"] <= a["p50"] <= a["p95"] and 0 <= a["prob_positivo"] <= 1


def test_monte_carlo_triangular_conocida():
    # media de una triangular (0, 1, 2) = 1; desviación = raíz(1/6)
    mc = R.monte_carlo(dict(x=0), dict(x=(0.0, 1.0, 2.0)), lambda p: p["x"], n=4000, semilla=133)
    assert mc["media"] == pytest.approx(1.0, abs=0.03)
    assert mc["desviacion"] == pytest.approx((1 / 6) ** 0.5, abs=0.02)
    assert mc["p50"] == pytest.approx(1.0, abs=0.05)
    assert mc["prob_positivo"] == pytest.approx(1.0)


def test_inversion_cero_usa_la_inversion_maxima_con_van_cero():
    r = resumen_planta(agrozzi.crear()); s = R.supuestos(r, dict(E, inversion=0.0))
    assert s["van_base"] == pytest.approx(0.0, abs=1e-6)
    assert s["avisos"] and "inversión máxima con VAN cero" in s["avisos"][0]
    lo, hi = s["rangos"]["inversion"]
    assert lo == pytest.approx(0.7 * s["base"]["inversion"]) and hi == pytest.approx(1.3 * s["base"]["inversion"])


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_riesgo_en_los_cuatro_rubros(mod):
    s = R.supuestos(resumen_planta(mod.crear()), E)
    assert s is not None
    t = R.tornado(s["base"], s["rangos"], s["fn"]); mc = R.monte_carlo(s["base"], s["distribuciones"], s["fn"], n=200)
    assert len(t) == len(s["rangos"]) and mc["n"] == 200
    assert sum(c for _a, _b, c in R.histograma(mc["valores"], 20)) == 200


def test_percentil_como_numpy():
    assert R.percentil([1.0, 2.0, 3.0, 4.0], 50) == pytest.approx(2.5)
    assert R.percentil([1.0, 2.0, 3.0, 4.0, 5.0], 5) == pytest.approx(1.2)
