"""PAT 133, mejora 20: modo dinámico simplificado (arranque y parada de primer orden, secado por cargas de Mujumdar, 2014)."""
import math
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import dinamico as D
from pat_sim.motor.resumen import resumen_planta


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_el_estado_final_tiende_al_estacionario_del_motor(mod):
    pl = mod.crear(); r = resumen_planta(pl); a = D.arranque_parada(pl, r)
    f = a["estado_final"]
    assert f["T"] == pytest.approx(r["sumidero"]["T_out"], rel=1e-6)
    assert f["Q"] == pytest.approx(r["Qsumidero"], rel=1e-6)
    assert f["Q_rec"] == pytest.approx(r["cascada"], rel=1e-3)        # el calor recuperable llega a la cascada del motor
    assert a["series"]["T"][-1] < r["sumidero"]["T_in"] + 0.01 * (r["sumidero"]["T_out"] - r["sumidero"]["T_in"])   # parada: se enfría


@pytest.mark.parametrize("mod", [agrozzi, pellet])
def test_el_balance_de_energia_integrado_cierra(mod):
    a = D.arranque_parada(mod.crear()); b = a["balance"]
    assert abs(b["cierre_kWh"]) <= 1e-9 * b["calor_kWh"]
    assert b["calor_kWh"] == pytest.approx(b["producto_kWh"] + b["acumulado_kWh"], rel=1e-12)
    assert b["recuperado_kWh"] + b["externo_kWh"] == pytest.approx(b["calor_kWh"], rel=1e-12)


def test_primer_orden_contra_la_solucion_exacta():
    # sin control (ganancia 0) y sin límite, la respuesta es T = T0 + (Tsp − T0)(1 − e^(−t/τ)); t95 = τ ln 20
    C, K = 6000.0, 50.0; tau = C / K
    o = D.primer_orden(C, K, 25.0, 90.0, 0.05, 1e9, 6 * tau, ganancia=0.0, sobrecapacidad=1.0)
    S = o["series"]; i = min(range(len(S["t"])), key=lambda j: abs(S["t"][j] - tau))
    assert S["T"][i] == pytest.approx(25 + 65 * (1 - math.exp(-S["t"][i] / tau)), rel=1e-3)
    t95 = next(t for t, y in zip(S["t"], S["y"]) if y >= 0.95)
    assert t95 == pytest.approx(tau * math.log(20), rel=1e-3)


def test_metricas_del_arranque_y_paso_inestable():
    pl = agrozzi.crear(); a = D.arranque_parada(pl)
    assert 0 < a["t95_min"] < a["t_parada_min"]
    assert a["energia_arranque_kWh"] > a["energia_masa_kWh"] > 0
    assert a["energia_masa_kWh"] == pytest.approx(a["C_kJ_K"] * 0.95 * (a["Tsp"] - a["T0"]) / 3600, rel=0.01)
    lento = D.arranque_parada(pl, masa_acero_t=24.0)
    assert lento["t95_min"] > a["t95_min"] and lento["energia_masa_kWh"] > a["energia_masa_kWh"]
    with pytest.raises(ValueError):
        D.arranque_parada(pl, dt_s=a["tau_lazo_min"] * 60 * 1.5)       # paso mayor que el límite del método explícito
    with pytest.raises(KeyError):
        D.arranque_parada(pl, masa=3)


def test_secado_por_cargas_contra_la_solucion_de_mujumdar():
    o = D.secado_cargas(X0=1.2, Xf=0.11, Xc=0.30, Xe=0.03, Nc=1.0, dt_h=0.0005)
    t1 = 1.2 - 0.30; t2 = (0.30 - 0.03) / 1.0 * math.log((0.30 - 0.03) / (0.11 - 0.03))
    assert o["t_constante_h"] == pytest.approx(t1) and o["t_decreciente_h"] == pytest.approx(t2)
    assert o["t_euler_h"] == pytest.approx(t1 + t2, rel=2e-3)
    assert o["agua_kg"] == pytest.approx((1.2 - 0.11) * 1000, rel=1e-9)
    v = o["series"]["velocidad"]
    assert v[0] == pytest.approx(1.0) and v[-2] < v[0] and all(a >= b - 1e-12 for a, b in zip(v, v[1:]))
    with pytest.raises(ValueError):
        D.secado_cargas(X0=0.1, Xf=0.2, Xc=0.3, Xe=0.03, Nc=1.0, dt_h=0.01)


@pytest.mark.parametrize("mod", [pellet, chip, lena])
def test_secado_por_cargas_con_el_secador_de_la_planta(mod):
    pl = mod.crear(); o = D.secado_cargas_planta(pl)
    assert o["agua_kg"] == pytest.approx(o["agua_continuo_kg"], rel=1e-9)      # la carga evapora la misma agua que una hora continua
    assert o["t_euler_h"] == pytest.approx(o["t_exacto_h"], rel=5e-3)
    assert o["t_exacto_h"] >= o["t_continuo_h"] * 0.9                        # el periodo decreciente alarga el secado
    with pytest.raises(ValueError):
        D.secado_cargas_planta(agrozzi.crear())
