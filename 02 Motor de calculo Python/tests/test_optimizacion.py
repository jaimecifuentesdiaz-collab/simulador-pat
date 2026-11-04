"""Pruebas de la optimización sobre copias de la planta (mejora 10, PAT 133)."""
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor.resumen import resumen_planta
from pat_sim.motor import optimizacion as O
from pat_sim.datos.bd import planta_a_dict, a_json

E = dict(precio_gas=8.0, dolar=990.35, inversion=1000.0, costo_anual=0.0, anios=20, tasa=0.10, precio_biomasa=6750.0)


def test_seccion_dorada_maximo_conocido():
    x, v = O.seccion_dorada(lambda x: -(x - 3.7) ** 2 + 5, 0.0, 10.0, tol=1e-6)
    assert x == pytest.approx(3.7, abs=1e-5) and v == pytest.approx(5.0)


def test_buscar_una_variable_grilla_y_refinamiento():
    r = O.buscar(lambda x: -(x - 2.345) ** 2, [(0.0, 10.0)], n_grilla=11)
    assert r["optimo"][0] == pytest.approx(2.345, abs=1e-2)
    assert len(r["curva"]) >= 11


def test_buscar_dos_variables_en_la_grilla():
    r = O.buscar(lambda x, y: -(x - 4) ** 2 - (y + 1) ** 2, [(0.0, 10.0), (-5.0, 5.0)], n_grilla=11)
    assert r["optimo"] == [pytest.approx(4.0), pytest.approx(-1.0)] and r["valor"] == pytest.approx(0.0)


def test_buscar_registra_los_puntos_que_no_resuelven():
    def f(x):
        if x > 5:
            raise ValueError("no converge")
        return x
    r = O.buscar(f, [(0.0, 10.0)], n_grilla=11)
    assert r["optimo"][0] == pytest.approx(5.0, abs=1e-2) and len(r["fallidos"]) >= 5


def test_no_modifica_la_planta_original():
    pl = agrozzi.crear(); antes = a_json(planta_a_dict(pl)); r0 = resumen_planta(pl)["cascada"]
    O.optimizar(pl, [("dT_min", 1.0, 20.0)], "van", E, n_grilla=7)
    O.optimizar(pl, [(("W2", "T_condensado"), 65.0, 85.0)], "calor", n_grilla=5)
    assert a_json(planta_a_dict(pl)) == antes
    assert resumen_planta(pl)["cascada"] == r0 and pl.globales["dT_min"] == 5.0


def test_menor_aproximacion_da_mas_calor():
    o = O.optimizar(agrozzi.crear(), [("dT_min", 2.0, 10.0)], "calor", n_grilla=9)
    assert o["optimo_lista"][0] == pytest.approx(2.0) and o["valor_optimo"] >= o["valor_base"]
    assert any("borde" in a for a in o["avisos"])


def test_objetivo_propio_con_maximo_conocido():
    # función de prueba sobre la planta: máximo en dT_min = 7,3 °C
    f = lambda p, r: -(p.globales["dT_min"] - 7.3) ** 2
    o = O.optimizar(agrozzi.crear(), [("dT_min", 1.0, 20.0)], f, n_grilla=11)
    assert o["optimo_lista"][0] == pytest.approx(7.3, abs=0.03)


def test_van_area_tiene_maximo_interior_en_tomate():
    o = O.optimizar(agrozzi.crear(), [("dT_min", 1.0, 20.0)], "van_area", E, n_grilla=11)
    assert 2.0 < o["optimo_lista"][0] < 19.0 and o["valor_optimo"] >= o["valor_base"]


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_optimizar_en_los_cuatro_rubros(mod):
    pl = mod.crear()
    o = O.optimizar(pl, [("T_final_residual", 20.0, 40.0)], "van", E, n_grilla=5)
    assert o["valor_optimo"] is not None and len(o["curva"]) >= 5
    assert pl.globales["T_final_residual"] == 30.0
    assert len(O.candidatos(pl)) > 2
