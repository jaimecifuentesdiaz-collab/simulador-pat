"""Pruebas del agua recuperable de los condensados (PAT 133, mejora 12) en los cuatro rubros."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import agua as A
from pat_sim.escenarios import agrozzi, pellet, chip, lena


def test_agua_de_los_condensados_de_agrozzi_igual_al_agua_evaporada():
    pl = agrozzi.crear().resolver(); a = A.agua_recuperada(pl)
    ev = sum(pl.equipos[k].resultado.detalle["agua_evaporada_kgh"] for k in ("W2", "W3", "W4"))
    flash = pl.equipos["B2"].resultado.detalle["vapor_flash_kgh"]
    Se = pl.equipos["W4"].resultado.detalle["Se"]                                     # vapor aspirado por el termocompresor: va al condensado del vapor vivo
    assert a["total_kgh"] == pytest.approx(ev - Se + flash, rel=1e-6)                 # F3 no se cuenta dos veces con F1c
    f3 = next(f for f in a["filas"] if f["corriente"] == "F3")
    assert not f3["cuenta"] and f3["m_kgh"] == pytest.approx(next(f for f in a["filas"] if f["corriente"] == "F1c")["m_kgh"], rel=1e-6)
    f4 = next(f for f in a["filas"] if f["corriente"] == "F4")
    assert f4["m_kgh"] == pytest.approx(pl.equipos["W2"].resultado.detalle["agua_evaporada_kgh"])
    assert a["horas"] == 1824 and a["total_m3_temporada"] == pytest.approx(a["total_kgh"] * 1824 / 1000)
    assert A.agua_recuperada(pl, {"horas": 1000})["total_m3_temporada"] == pytest.approx(a["total_kgh"])


def test_agua_del_escape_del_secador_en_la_biomasa():
    pl = pellet.crear().resolver(); a = A.agua_recuperada(pl); d = pl.equipos["T1"].resultado.detalle
    assert len(a["filas"]) == 1 and a["total_kgh"] == pytest.approx(A.agua_escape_secador(d["agua_evaporada_kgh"], d["aire_kgh"], d["T_rocio"], 30.0))
    assert 0 < a["total_kgh"] < d["agua_evaporada_kgh"] and a["total_m3_temporada"] == pytest.approx(a["total_kgh"] * 7920 / 1000)
    assert A.agua_recuperada(pl, T_escape=20.0)["total_kgh"] > a["total_kgh"]           # más frío, más condensado
    assert A.agua_recuperada(pl, T_escape=50.0)["total_kgh"] == 0                       # sobre el punto de rocío no condensa
    for mod in (chip, lena):
        pb = mod.crear().resolver()
        assert A.agua_recuperada(pb)["total_kgh"] == 0 and A.agua_recuperada(pb, T_escape=10.0)["total_kgh"] > 0
    assert A.agua_escape_secador(100, 0, 40, 30) == 0
