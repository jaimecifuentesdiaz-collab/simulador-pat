"""PAT 133: alternativas, multicriterio, ΔTmin óptimo (mejoras 1, 2 y 4) y valores de partida citables (mejora 11)."""
import json, os
import pytest
from pat_sim.escenarios import agrozzi, pellet
from pat_sim.motor.resumen import resumen_planta
from pat_sim.motor import alternativas as AL, costos, calculadoras as K

JSON = os.path.join(os.path.dirname(__file__), "..", "..", "..", "Capitulos 2 a 4 Agrozzi", "scripts", "resultados_cap234.json")


@pytest.fixture
def agz():
    pl = agrozzi.crear(); r = resumen_planta(pl)
    return pl, r, AL.alternativas(pl, r, 2.77)


def test_reproduce_el_capitulo_3(agz):
    _, _, x = agz
    ref = json.load(open(JSON, encoding="utf-8"))
    for k in ("A1", "A2", "A3", "A4"):
        a, b = x["alts"][k], ref["alts"][k]
        assert a["Q"] == pytest.approx(b["Q"], rel=1e-5)
        assert a["inv"]["medio"] == pytest.approx(b["inv"]["MMclp_medio"], rel=1e-5)
        peq = b["p_eq"][0] if isinstance(b["p_eq"], list) else b["p_eq"]
        assert a["p_eq"] == pytest.approx(peq, rel=1e-4)
    for k, v in ref["cap3"]["base_con_A4"].items():
        assert x["puntajes"][k] == pytest.approx(v, abs=1e-5)
    assert x["ganador"] == "A3"
    for k, v in ref["cap3"]["barrido_con_A4"].items():
        assert x["barrido"][k] == pytest.approx(v, abs=1e-5)


def test_pesos_cambian_el_ganador(agz):
    pl, r, _ = agz
    solo_precio = AL.alternativas(pl, r, 2.77, pesos=(0, 1, 0))
    assert solo_precio["ganador"] == "A1"
    solo_cob = AL.alternativas(pl, r, 2.77, pesos=(1, 0, 0))
    assert solo_cob["ganador"] == "A4"


def test_van_cero_en_el_precio_de_equilibrio(agz):
    _, _, x = agz
    a = x["alts"]["A3"]
    ev = AL.evaluar(a["inv"]["medio"], a["cantidad"], a["p_eq"], a["om"], 0.10)
    assert abs(ev["VAN"]) < 1e-3 * a["inv"]["medio"]


def test_dtmin_optimo_minimiza_el_costo_total(agz):
    pl, r, _ = agz
    o = AL.dTmin_optimo(pl, r, 10.0, dTs=[2.0, 5.0, 10.0, 15.0, 20.0])
    assert o["optimo"]["total"] == min(f["total"] for f in o["filas"])
    q = [f["Q"] for f in o["filas"]]
    assert q == sorted(q, reverse=True)          # más ΔTmin, menos calor recuperado
    assert AL.crf(0.10, 15) == pytest.approx(0.131474, rel=1e-5)


def test_biomasa_y_correlacion_partida():
    pl = pellet.crear(); r = resumen_planta(pl)
    x = AL.alternativas(pl, r, 6750.0)
    assert x["biomasa"] and x["unidad_precio"].startswith("$")
    assert all(a["inv"]["medio"] > 0 for a in x["alts"].values() if a["Q"] > 0)
    assert costos.costo_equipo_partido_usd2020(7000.0) == pytest.approx(2 * costos.costo_equipo_usd2020(3500.0))
    assert costos.costo_equipo_partido_usd2020(500.0) == pytest.approx(costos.costo_equipo_usd2020(500.0))


def test_valores_de_partida_citables():
    assert K.FACTOR_RED_SEN == pytest.approx(0.2384)
    assert "Coordinador" in K.FUENTE_FACTOR_RED and "2024" in K.FUENTE_FACTOR_RED
    assert K.CEPCI_ACTUAL == pytest.approx(797.9) and "2023" in K.FUENTE_CEPCI
