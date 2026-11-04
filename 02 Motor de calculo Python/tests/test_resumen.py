"""El resumen genérico entrega las cifras del Capítulo 1 y las de la bomba de calor y del precio de equilibrio."""
import math
import pytest
from pat_sim.escenarios import agrozzi
from pat_sim.motor.resumen import resumen_planta
from pat_sim.motor import economia as eco


def test_resumen_generico_igual_a_agrozzi():
    pl = agrozzi.crear(); a = agrozzi.resumen(pl); g = resumen_planta(pl)
    for k_a, k_g in (("cascada", "cascada"), ("pinch", "pinch"), ("alt2", "alt2"), ("Qhb", "Qsumidero"), ("Q_externo_min", "Q_externo_min"),
                     ("cobertura_cascada", "cobertura_cascada"), ("oferta", "oferta")):
        assert math.isclose(float(a[k_a]), float(g[k_g]), rel_tol=1e-12), k_a
    assert a["T_pinch"] == g["T_pinch"]
    assert math.isclose(a["bomba_calor"]["electricidad_kW"], g["bomba_calor"]["electricidad_kW"], rel_tol=1e-12)
    assert [f[0] for f in a["bomba_calor"]["fuentes"]] == [f[0] for f in g["bomba_calor"]["fuentes"]]
    for caso in ("gas_base", "gas_cascada"):
        assert math.isclose(a[caso]["MMBtu"], g[caso]["MMBtu"], rel_tol=1e-12)


def test_sensibilidad_con_las_globales_de_la_planta():
    pl = agrozzi.crear(); base = resumen_planta(pl)["cascada"]
    pl.globales["dT_min"] = 10.0; pl.resolver()
    assert resumen_planta(pl)["cascada"] < base            # más aproximación mínima, menos calor recuperable
    ref = resumen_planta(agrozzi.crear(dT=10.0))["cascada"]
    assert math.isclose(resumen_planta(pl)["cascada"], ref, rel_tol=1e-12)


def test_precio_de_equilibrio_de_la_bomba_de_calor_como_en_el_excel():
    pl = agrozzi.crear(); r = resumen_planta(pl)
    # COMBUSTIBLE!B39:B41 de Modelo_PAT_Agrozzi_v2.xlsx: 22,07 / 24,54 / 28,58 US$/MMBtu con 84,004 / 93,417 / 108,81 $/kWh
    for precio, esperado in ((84.004, 22.0672505), (93.417, 24.5399783), (108.81, 28.5836094)):
        v = eco.equilibrio_bomba_calor(r["cobertura_cascada"], r["eta_pcs"], 2.0, precio, 990.35)
        assert math.isclose(v, esperado, rel_tol=1e-6)


def test_valor_del_gas_al_henry_hub():
    r = resumen_planta(agrozzi.crear())
    assert math.isclose(eco.valor_gas(r["gas_base"]["MMBtu"], 2.77, 990.35), 355.753, abs_tol=0.01)      # MM$, COMBUSTIBLE!H21
    assert math.isclose(eco.valor_gas(r["gas_cascada"]["MMBtu"], 2.77, 990.35), 202.309, abs_tol=0.01)   # COMBUSTIBLE!H22


def test_gas_desplazado_y_remanente_como_en_el_excel():
    r = resumen_planta(agrozzi.crear())
    assert math.isclose(r["gas_desplazado_cascada"]["MMBtu"], 73747.35, abs_tol=0.1)      # COMBUSTIBLE!G22
    assert math.isclose(r["gas_desplazado_cascada"]["co2_t"], 3855.33, abs_tol=0.01)      # COMBUSTIBLE!F22
    assert math.isclose(r["gas_remanente_cascada"]["MMBtu"], 55934.79, abs_tol=0.1)       # COMBUSTIBLE!G24
    assert math.isclose(r["gas_alt2"]["MMBtu"], 53819.34, abs_tol=0.1)                    # COMBUSTIBLE!G23
