"""Pruebas de la temporada (PAT 133, mejoras 6 y 7): llegada de materia prima, cola de camiones y programa de producción."""
import math
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import temporada as TM
from pat_sim.motor import calculadoras as K

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}


@pytest.fixture(scope="module")
def plantas():
    return {k: m.crear() for k, m in ESCENARIOS.items()}


def test_llegada_reproducible_con_la_misma_semilla(plantas):
    pl = plantas["tomate"]
    a = TM.llegadas_temporada(pl, semilla=11); b = TM.llegadas_temporada(pl, semilla=11); c = TM.llegadas_temporada(pl, semilla=12)
    assert [x["camiones"] for x in a["dias"]] == [x["camiones"] for x in b["dias"]] and a["por_hora"] == b["por_hora"]
    assert a["espera_media_h"] == b["espera_media_h"] and a["espera_media_h"] != c["espera_media_h"]


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_curva_suma_lo_que_procesa_la_planta(plantas, rubro):
    pl = plantas[rubro]; d = TM.datos_planta(pl); curva = TM.curva_llegada(pl)
    assert len(curva) == d["D"] and sum(curva) == pytest.approx(d["carga"] * d["D"] * d["H"], rel=1e-9)
    if rubro == "tomate":                          # campana: el peak queda a mitad de la temporada y es mayor que los extremos
        i = max(range(len(curva)), key=curva.__getitem__)
        assert abs(i - (d["D"] - 1) / 2) <= 1 and curva[i] > 3 * curva[0]
    else:
        assert max(curva) == pytest.approx(min(curva))


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
@pytest.mark.parametrize("con_programa", [False, True])
def test_conservacion_de_masa(plantas, rubro, con_programa):
    pl = plantas[rubro]; pr = TM.programa_temporada(pl) if con_programa else None
    r = TM.llegadas_temporada(pl, semilla=5, base="linea" if con_programa else "recepcion", programa=pr)
    assert r["total_llegada_t"] == pytest.approx(TM.datos_planta(pl)["total"], rel=1e-9)
    assert r["total_llegada_t"] == pytest.approx(r["total_procesado_t"] + r["cola_final_t"] + r["total_degradado_t"], rel=1e-9)
    assert sum(x["llegada_t"] for x in r["dias"]) == pytest.approx(r["total_llegada_t"], rel=1e-9)
    assert r["dias"][-1]["cola_t"] == pytest.approx(r["cola_final_t"], abs=1e-6) and r["cola_final_t"] >= -1e-6
    if rubro != "tomate":
        assert r["total_degradado_t"] == 0


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_ley_de_little(plantas, rubro):
    r = TM.llegadas_temporada(plantas[rubro], semilla=3); L = r["little"]
    assert L["L_integrada"] == pytest.approx(K.little(L["lambda_por_h"], L["W_h"]), rel=1e-9)   # L = λW es exacta en el periodo
    assert L["L_horaria"] == pytest.approx(L["L_integrada"], rel=0.10, abs=0.05)                # muestreo hora a hora


def test_espera_simulada_cerca_de_kingman(plantas):
    pl = plantas["pellet"]; cap = TM.datos_planta(pl)["carga"] / 0.65          # utilización de 65 %, régimen estable
    ws = [TM.llegadas_temporada(pl, semilla=s, capacidad_t_h=cap)["espera_media_h"] for s in range(5)]
    r = TM.llegadas_temporada(pl, semilla=0, capacidad_t_h=cap)
    assert r["utilizacion_media"] == pytest.approx(0.65, rel=1e-6)
    assert r["espera_kingman_h"] == pytest.approx(K.kingman(0.65, 1.0, r["parametros"]["cv_servicio"], r["servicio_medio_h"]))
    assert sum(ws) / len(ws) == pytest.approx(r["espera_kingman_h"], rel=0.25)


def test_degradacion_del_tomate_sobre_el_umbral(plantas):
    pl = plantas["tomate"]; cap = TM.datos_planta(pl)["carga"] * 0.9           # recepción insuficiente: el tomate espera
    r = TM.llegadas_temporada(pl, semilla=1, capacidad_t_h=cap)
    assert r["total_degradado_t"] > 0 and r["espera_max_h"] > r["parametros"]["umbral_h"]
    sin = TM.llegadas_temporada(pl, semilla=1, capacidad_t_h=cap, umbral_h=1e6)
    assert sin["total_degradado_t"] == 0


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_programa_sin_traslapes_y_cubre_la_temporada(plantas, rubro):
    pr = TM.programa_temporada(plantas[rubro]); b = pr["barras"]
    assert b[0]["inicio_h"] == 0 and b[-1]["fin_h"] == pytest.approx(pr["horas_totales"])
    for x, y in zip(b, b[1:]):
        assert x["fin_h"] <= y["inicio_h"] + 1e-9 and x["fin_h"] > x["inicio_h"]
    assert sum(x["fin_h"] - x["inicio_h"] for x in b) == pytest.approx(pr["horas_totales"])
    assert {x["tipo"] for x in b} >= {"arranque", "produccion", "limpieza", "parada", "parada_final"}
    p = pr["parametros"]; prod = 0.0                # nunca se producen más de N horas seguidas sin limpieza o parada
    for x in b:
        prod = prod + x["fin_h"] - x["inicio_h"] if x["tipo"] == "produccion" else (prod if x["tipo"] == "fuera_turno" else 0.0)
        assert prod <= p["cip_cada_h"] + 1e-6


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_horas_efectivas_menores_y_calor_perdido(plantas, rubro):
    pr = TM.programa_temporada(plantas[rubro]); h = pr["horas_por_tipo"]
    assert 0 < pr["horas_efectivas"] < pr["horas_diseno"] <= pr["horas_totales"]
    assert pr["horas_efectivas"] == pytest.approx(pr["horas_diseno"] - h["arranque"] - h["limpieza"] - h["parada"] - h["parada_final"])
    assert pr["disponibilidad"] == pytest.approx(pr["oee"]["disponibilidad"]) and pr["produccion_programa_t"] < pr["produccion_diseno_t"]
    assert pr["calor_no_recuperado_MWh"] == pytest.approx(pr["cascada_kW"] * pr["horas_detenida"] / 1000)
    assert pr["calor_no_recuperado_MWh"] == pytest.approx(sum(pr["calor_no_recuperado_por_tipo_MWh"].values()))
    sin = TM.programa_temporada(plantas[rubro], arranque_h=0, cip_cada_h=0, parada_cada_d=0, parada_final_h=0)
    assert sin["horas_efectivas"] == pytest.approx(sin["horas_diseno"]) and sin["calor_no_recuperado_MWh"] == pytest.approx(0)


def test_gantt_svg(plantas):
    pr = TM.programa_temporada(plantas["chip"]); svg = TM.gantt_svg(pr)
    assert svg.startswith("<svg") and svg.endswith("</svg>") and "Fuera de turno" in svg and "Limpieza" in svg
    assert TM.svg_como_img(svg).startswith("<img")


# ----------------------------------------------------------------------------------------------- PAT 134: descarga ajustada
def test_sin_distribucion_de_descarga_no_cambia_y_entrega_esperas(plantas):
    from pat_sim.motor import ajuste as AJ
    pl = plantas["pellet"]; r = TM.llegadas_temporada(pl, semilla=1)
    assert r["espera_media_h"] == pytest.approx(10.69805761072496, rel=1e-12)       # valor previo a PAT 134
    assert len(r["esperas_h"]) == r["camiones"] and sum(r["esperas_h"]) / r["camiones"] == pytest.approx(r["espera_media_h"])
    cv = r["parametros"]["cv_servicio"]; te = r["servicio_medio_h"]          # la gamma equivalente reproduce la misma temporada
    g = AJ.crear("gamma", forma=1 / cv ** 2, escala=cv ** 2 * te)
    r2 = TM.llegadas_temporada(pl, semilla=1, dist_descarga=g)
    assert r2["espera_media_h"] == pytest.approx(r["espera_media_h"], rel=1e-9) and r2["capacidad_t_h"] == pytest.approx(r["capacidad_t_h"])


def test_descarga_con_distribucion_ajustada(plantas):
    from pat_sim.motor import ajuste as AJ
    pl = plantas["chip"]; base = TM.llegadas_temporada(pl, semilla=3)
    d = AJ.crear("weibull", forma=3.0, escala=1.5 * base["servicio_medio_h"] / math.gamma(1 + 1 / 3))   # descarga 50 % más lenta
    a = TM.llegadas_temporada(pl, semilla=3, dist_descarga=d); b = TM.llegadas_temporada(pl, semilla=3, dist_descarga=d)
    assert a["esperas_h"] == b["esperas_h"] and a["servicio_medio_h"] == pytest.approx(AJ.media(d))
    assert a["parametros"]["cv_servicio"] == pytest.approx(AJ.desviacion(d) / AJ.media(d)) and "weibull(0, " in a["origen_capacidad"]
    assert a["espera_media_h"] > base["espera_media_h"] and a["parametros"]["dist_descarga"].startswith("weibull")
