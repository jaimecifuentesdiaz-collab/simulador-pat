"""Pruebas de las propiedades de la pasta según °Brix (PAT 133, mejora 9). cp y densidad de Choi y Okos (1986) a mano."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import propiedades as PR


def test_cp_y_densidad_choi_okos_a_mano():
    cpw = 4.1762 - 9.0864e-5 * 25 + 5.4731e-6 * 625; cpc = 1.5488 + 1.9625e-3 * 25 - 5.9399e-6 * 625
    assert PR.cp_pasta(0, 25) == pytest.approx(cpw) and PR.cp_pasta(30, 25) == pytest.approx(0.7 * cpw + 0.3 * cpc)
    assert PR.cp_pasta(30, 25) == pytest.approx(3.4024, abs=1e-4)
    rw = 997.18 + 3.1439e-3 * 25 - 3.7574e-3 * 625; rc = 1599.1 - 0.31046 * 25
    assert PR.densidad_agua(25) == pytest.approx(rw) and PR.densidad_pasta(30, 25) == pytest.approx(1 / (0.7 / rw + 0.3 / rc))
    assert abs(PR.cp_pasta(28, 50) - (PR.CPW - (PR.CPW - 1.5) * 0.28)) < 0.06        # cerca del modelo lineal del motor
    mix = PR.cp_pasta(30, 25, {"carbohidrato": 0.8, "fibra": 0.1, "ceniza": 0.1})
    assert mix != PR.cp_pasta(30, 25)
    with pytest.raises(KeyError):
        PR.cp_pasta(30, 25, {"azucar": 1.0})


def test_reologia_y_viscosidad_aparente():
    K30, n30 = PR.reologia_pasta(30, PR.REO_T0)
    assert K30 == pytest.approx(PR.REO_K30) and 0.35 <= n30 <= 0.45                   # orden de la calculadora de tuberías
    assert PR.reologia_pasta(36, 40)[0] > PR.reologia_pasta(28, 40)[0] > PR.reologia_pasta(8.5, 40)[0]
    assert PR.reologia_pasta(28, 80)[0] < PR.reologia_pasta(28, 25)[0]               # se adelgaza al calentarse
    assert PR.reologia_pasta(36, 40)[1] < PR.reologia_pasta(5, 40)[1]
    K, n = PR.reologia_pasta(28, 40)
    assert PR.viscosidad_aparente_pasta(28, 40, 10) == pytest.approx(K * 10 ** (n - 1))
    assert PR.viscosidad_aparente_pasta(28, 40, 100) < PR.viscosidad_aparente_pasta(28, 40, 10)   # pseudoplástico
    assert PR.viscosidad_agua(25) == pytest.approx(0.00089, rel=0.01)
    p = PR.propiedades_pasta(28, 40)
    assert set(p) >= {"cp", "densidad", "K", "n", "mu_aparente"} and p["cp"] == pytest.approx(PR.cp_pasta(28, 40))
