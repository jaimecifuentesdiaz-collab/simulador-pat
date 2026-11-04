"""Pruebas de la hidráulica (PAT 133, mejora 8): curva de bomba, punto de operación, válvula con Cv (ISA-75.01), red de la planta
y bombas y válvulas genéricas de la ISO 10628. Valores recalculados a mano."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import hidraulica as H
from pat_sim.escenarios import agrozzi, pellet, chip, lena


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


def test_curva_eficiencia_y_potencia_a_mano():
    assert H.curva_bomba(50, 40, 0.004) == pytest.approx(30)
    assert H.eficiencia_bomba(50, 0.75, 50) == pytest.approx(0.75) and H.eficiencia_bomba(100, 0.75, 50) == 0
    assert H.eficiencia_bomba(25, 0.8, 50) == pytest.approx(0.6)
    assert H.potencia_bombeo(50, 30, 1000, 0.75) == pytest.approx(5.45, abs=1e-6)       # 1000·9,81·(50/3600)·30/0,75
    assert H.k_por_punto(40, 50, 30) == pytest.approx(0.004)
    with pytest.raises(ValueError):
        H.k_por_punto(40, 50, 45)


def test_punto_de_operacion_contra_sistema_cuadratico_y_tuberia():
    po = H.punto_operacion(40, 0.004, lambda q: 10 + 0.002 * q * q)                  # 40 − 0,004Q² = 10 + 0,002Q²
    assert po["existe"] and po["Q_m3h"] == pytest.approx(5000 ** 0.5, abs=1e-6) and po["H_m"] == pytest.approx(20, abs=1e-6)
    assert not H.punto_operacion(10, 0.004, lambda q: 15.0)["existe"]                 # la bomba no vence la altura estática
    b = H.bomba_en_linea(50, 1000, 40, 0.004, 0.75, 50, 10, 100, 100)
    assert b["H_sistema_m"] == pytest.approx(H.altura_sistema(50, 10, 100, 100)) and b["exceso_valvula_m"] == pytest.approx(30 - b["H_sistema_m"])
    assert b["Q_natural_m3h"] > 50 and b["potencia_kW"] == pytest.approx(5.45, abs=1e-6)
    assert H.bomba_en_linea(50, 1000, 15, 0.004, 0.75, 50, 10, 100, 100)["avisos"]   # 5 m a 50 m³/h: no alcanza


def test_valvula_cv_isa_75_01():
    assert H.caudal_valvula(10, 100) == pytest.approx(8.65)                            # 1 bar, agua
    assert H.caudal_valvula(10, 6.894757) == pytest.approx(10 * 0.2271247, rel=1e-3)   # 1 psi: 10 gpm = 2,2712 m³/h
    cv = H.cv_requerido(50, 50, 1.1)
    assert H.dp_valvula(cv, 50, 1.1) == pytest.approx(50) and H.caudal_valvula(cv, 50, 1.1) == pytest.approx(50)


def test_red_hidraulica_en_los_cuatro_rubros(pl):
    r = H.red_hidraulica(pl)
    assert len(r["lineas"]) == 10 and r["potencia_total_kW"] == pytest.approx(sum(f["potencia_kW"] for f in r["lineas"]))
    assert all(f["potencia_kW"] > 0 and f["dp_kPa"] > 0 for f in r["lineas"]) and r["energia_MWh"] == pytest.approx(r["potencia_total_kW"] * 1824 / 1000)
    f = r["lineas"][-1]                                                                 # pasta a 30 °Brix: laminar, v de diseño 1 m/s
    assert f["regimen"] == "laminar" and f["v"] == pytest.approx(H.V_DISENO_PASTA) and f["brix"] == pytest.approx(30, abs=0.1)
    assert r["avisos"]                                                                  # tomate sin °Brix: Supuesto declarado
    for mod in (pellet, chip, lena):                                                    # biomasa: no hay líneas de líquido
        rb = H.red_hidraulica(mod.crear().resolver())
        assert rb["lineas"] == [] and rb["potencia_total_kW"] == 0 and rb["omitidas"] > 0


def test_bomba_y_valvula_genericas_iso(pl):
    from pat_sim.catalogos.registro import TIPOS
    e = pl.salidas[("W4", "concentrado")]
    b = TIPOS["iso_bomba_centrifuga"]("P9"); r = b.calcular({"entrada": e})
    assert r.servicios["electricidad_kW"] == pytest.approx(r.detalle["W_kW"]) and r.detalle["origen_electricidad"] == "punto de operación"
    assert r.detalle["H_m"] == pytest.approx(1.1 * r.detalle["H_sistema_m"]) and abs(r.cierre_energia()) < 1e-9
    b.set("energia_especifica", 2.0)                                                    # el consumo del fabricante manda
    assert b.calcular({"entrada": e}).servicios["electricidad_kW"] == pytest.approx(2.0 * e.m / 1000)
    t = TIPOS["iso_bomba_tornillo"]("P8").calcular({"entrada": e})
    assert "H0" not in TIPOS["iso_bomba_tornillo"]("P8").params and t.servicios["electricidad_kW"] > 0
    v = TIPOS["iso_valvula_control"]("H9"); v.set("Cv", 40.0); rv = v.calcular({"entrada": e})
    assert rv.detalle["dp_kPa"] == pytest.approx(H.dp_valvula(40, rv.detalle["Q_m3h"], rv.detalle["G"])) and not rv.servicios
    g = next(c for k, c in TIPOS.items() if k.startswith("iso_") and "bomba" not in k and "valvula" not in k)   # los demás no cambian
    assert "H0" not in g("X").params and "Cv" not in g("X").params
