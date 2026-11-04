"""Pruebas de las herramientas de cálculo (PAT 132) con los ejemplos resueltos de la literatura y recalculados a mano."""
import math, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import calculadoras as K


def test_pinch_cuatro_corrientes_de_kemp():
    r = K.tabla_problema([("1", 20, 135, 2.0), ("2", 170, 60, 3.0), ("3", 80, 140, 4.0), ("4", 150, 30, 1.5)], 10)
    assert r["QH_min"] == pytest.approx(20) and r["QC_min"] == pytest.approx(60)
    assert r["T_pinch_desplazada"] == pytest.approx(85) and (r["T_pinch_caliente"], r["T_pinch_fria"]) == (90, 80)
    assert r["compuestas"]["caliente"][-1][0] == pytest.approx(3 * 110 + 1.5 * 120)


def test_intercambiador_lmtd_F_y_efectividad():
    r = K.intercambiador(10, 3.9, 25, 70, 95, 60, 1500)
    assert r["Q_kW"] == pytest.approx(1755) and r["LMTD"] == pytest.approx(29.72, abs=0.01)
    assert r["A_contracorriente_m2"] == pytest.approx(39.37, abs=0.05) and r["NTU"] == pytest.approx(1.514, abs=0.005)
    assert r["efectividad"] == pytest.approx(0.643, abs=0.001) and r["avisos"]          # F de 1-2 bajo 0,75
    assert K.factor_F_12(150, 100, 30, 60) == pytest.approx(0.96, abs=0.02)            # caso holgado: F cercano a 1


def test_vapor_evaporador_y_caldera():
    assert K.vapor_saturado(100)["p_kPa"] == pytest.approx(101.42, rel=0.01)
    e = K.evaporador(50, 0.05, 0.28, efectos=3, factor_economia=0.85)
    assert e["agua_t_h"] == pytest.approx(41.07, abs=0.01) and e["vapor_t_h"] == pytest.approx(e["agua_t_h"] / 2.55)
    assert 0 < e["mvr_kJ_kg"] < 0.1 * e["latente_kJ_kg"]
    c = K.caldera(10, 184.1, 80, 0.85, 48.0, precio_comb_por_GJ=12)
    assert c["Q_kW"] == pytest.approx(6794, rel=0.01) and c["combustible_kgh"] == pytest.approx(600, rel=0.01)
    assert c["co2_kgh"] == pytest.approx(1614, rel=0.01) and c["costo_por_t_vapor"] == pytest.approx(34.5, rel=0.01)
    assert K.pci_humedo(19, 0.40) == pytest.approx(10.42, abs=0.01)
    em = K.emisiones(1000, 112000, biogenico=True)
    assert em["total_t"] == 0 and em["biogenico_t"] == pytest.approx(112)


def test_secador_letalidad_y_tuberia():
    s = K.secador(3, 0.5, 0.1)
    assert s["agua_t_h"] == pytest.approx(4 / 3) and s["Q_kW"] == pytest.approx(1185, rel=0.001)
    assert K.letalidad([(0, 110), (3, 110)])["F_min"] == pytest.approx(0.2327, abs=0.0005)
    assert K.letalidad([(0, 110), (3, 110)], T_ref=100, z=10, D_ref=5)["reducciones"] == pytest.approx(6)
    t = K.tuberia(50, 100, 100)
    assert t["Re"] == pytest.approx(176800, rel=0.01) and t["f"] == pytest.approx(0.0189, abs=0.0003) and t["dp_kPa"] == pytest.approx(29.5, rel=0.02)
    assert K.tuberia(50, 100, 0, dz_m=30)["potencia_kW"] == pytest.approx(6.29, abs=0.02)
    p = K.tuberia(10, 50, 20, rho=1150, K=15, n=0.35)                                   # pasta de tomate: laminar
    assert p["regimen"] == "laminar" and p["f"] == pytest.approx(64 / p["Re"])


def test_costos_oee_y_variabilidad():
    c = K.costo_escalado(1.2e6, 20, 40, 0.6, 397, 797.9, f_lang=K.LANG["Fluidos"])
    assert c["equipo"] == pytest.approx(3.656e6, rel=0.002) and c["planta"] == pytest.approx(c["equipo"] * 4.74)
    o = K.oee(24, 22, 2, 38, 37)
    assert o["oee"] == pytest.approx(0.771, abs=0.001)
    assert [round(K.kingman(u), 6) for u in (0.8, 0.9, 0.95)] == [4, 9, 19] and math.isinf(K.kingman(1))
    assert K.little(120, 3) == 360
