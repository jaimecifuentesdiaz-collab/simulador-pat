"""PAT 133, mejora 3: red de intercambiadores desde el pinch (Linnhoff y Hindmarsh, 1983; Kemp, 2007, cap. 4)."""
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import recuperacion as rec, red_intercambio as RI
from pat_sim.motor.equipos import Sumidero
from pat_sim.motor.resumen import resumen_planta

ESC = {"agrozzi": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}


def _red(rubro, dT=None):
    pl = ESC[rubro].crear()
    if dT is not None:
        pl.globales["dT_min"] = dT; pl.resolver()
    r = resumen_planta(pl)
    return RI.disenar_red_planta(pl, r), r


def test_agrozzi_con_W1_y_5_grados_alcanza_el_objetivo_pinch():
    pl = agrozzi.crear()
    snk = next(s for s in pl.sumideros() if s.equipo == "W1")
    m = rec.mapa(pl.residuales(), snk, 5.0, 30.0)
    red = RI.disenar_red(m); obj = rec.pinch(m)[0]
    assert red["alcanza_objetivo"] and red["Q_recuperado"] == pytest.approx(obj, rel=1e-6)
    assert red["Q_recuperado"] <= obj + 1e-6
    assert red["servicio_caliente_kW"] == pytest.approx(rec.pinch(m)[1], rel=1e-6)      # calor externo mínimo
    assert red["T_pinch_caliente"] == pytest.approx(55.57, abs=1e-3) and red["T_pinch_fria"] == pytest.approx(50.57, abs=1e-3)
    # sin transferencia a través del pinch: arriba no hay servicio frío y el frío arriba solo recibe calor sobre 50,57 °C
    assert all(e["lado"] == "abajo" for e in red["enfriadores"])
    assert all(a["Tc_in"] >= red["T_pinch_fria"] - 1e-6 for a in red["apareamientos"] if a["lado"] == "arriba")
    assert all(a["Tc_out"] <= red["T_pinch_fria"] + 1e-6 for a in red["apareamientos"] if a["lado"] == "abajo")
    # U de partida del Capítulo 4: líquido 850 W/m2K y condensación 840 W/m2K
    assert {a["tipo"]: a["U"] for a in red["apareamientos"]} == {"líquido": 850.0, "condensación": 840.0}


@pytest.mark.parametrize("rubro", list(ESC))
@pytest.mark.parametrize("dT", [2.0, 5.0, 10.0, 20.0])
def test_el_calor_de_la_red_no_supera_el_objetivo_pinch(rubro, dT):
    red, r = _red(rubro, dT)
    assert red["Q_recuperado"] <= r["pinch"] + 1e-6
    assert red["Q_recuperado"] == pytest.approx(r["pinch"], rel=1e-6, abs=1e-6)        # los cuatro rubros llegan al objetivo
    # balance del sumidero: recuperado más servicio caliente igual a su demanda
    assert red["Q_recuperado"] + red["servicio_caliente_kW"] == pytest.approx(r["Qsumidero"], rel=1e-9)


@pytest.mark.parametrize("rubro", list(ESC))
def test_balance_temperaturas_y_area_de_cada_apareamiento(rubro):
    red, r = _red(rubro)
    dT = red["dT_min"]; usado = {}
    for a in red["apareamientos"]:
        Q = a["Q_kW"]
        assert Q == pytest.approx(a["CP_frio"] * (a["Tc_out"] - a["Tc_in"]), rel=1e-9)            # lado frío
        if a["CP_caliente"] is None:
            assert a["Th_in"] == a["Th_out"]                                                      # latente a T constante
        else:
            assert Q == pytest.approx(a["CP_caliente"] * (a["Th_in"] - a["Th_out"]), rel=1e-9)  # lado caliente
        assert min(a["dT_caliente"], a["dT_fria"]) >= dT - 1e-6                                  # aproximación mínima
        assert a["A_m2"] == pytest.approx(Q * 1000 / (a["U"] * a["LMTD"]), rel=1e-12)
        assert a["U"] == (50.0 if r.get("combustible") == "biomasa" else (840.0 if a["CP_caliente"] is None else 850.0))
        usado[a["corriente"]] = usado.get(a["corriente"], 0.0) + Q
    for c in red["corrientes"]:
        sf = sum(e["Q_kW"] for e in red["enfriadores"] if e["corriente"] == c["nombre"])
        assert usado.get(c["nombre"], 0.0) + sf == pytest.approx(c["Q"], rel=1e-9, abs=1e-6)    # cada caliente cierra
    assert red["area_total_m2"] == pytest.approx(sum(a["A_m2"] for a in red["apareamientos"]))


@pytest.mark.parametrize("rubro", list(ESC))
def test_numero_de_equipos_y_minimo_de_euler(rubro):
    red, _ = _red(rubro)
    assert red["equipos"]["total"] >= red["euler"]["total"]
    assert red["equipos"]["arriba"] >= red["euler"]["arriba"] and red["equipos"]["abajo"] >= red["euler"]["abajo"]
    assert red["euler"]["total"] >= red["euler_sin_dividir"]               # dividir en el pinch no baja el mínimo
    if rubro == "agrozzi":
        # arriba: F4, F5, F1a, F1b, sumidero y servicio caliente (6 - 1); abajo: 7 calientes, sumidero y servicio frío (9 - 1)
        assert (red["euler"]["arriba"], red["euler"]["abajo"]) == (5, 8)
        assert red["equipos"]["total"] == 13 and red["equipos"]["recuperacion"] == 6


def test_corrientes_sinteticas_latentes_sensibles_y_division():
    casos = [
        ([("V", 80.0, None, None, 500.0), ("L", 120.0, 30.0, 5.0, 450.0)], (20.0, 110.0, 6.0)),
        ([("A", 100.0, 40.0, 1.0, 60.0), ("B", 100.0, 40.0, 1.5, 90.0)], (20.0, 90.0, 4.0)),    # regla de CP: el frío se divide
        ([("A", 150.0, 60.0, 3.0, 270.0), ("B", 120.0, 40.0, 1.0, 80.0)], (30.0, 140.0, 2.0)),
    ]
    for st, (ti, to, cp) in casos:
        m = rec.Mapa(st, Sumidero("S", "X", ti, to, cp), 10.0, 30.0)
        red = RI.disenar_red(m); obj = RI.objetivo_pinch(m)[0]
        assert red["alcanza_objetivo"] and red["Q_recuperado"] == pytest.approx(obj, rel=1e-9)
        assert sum(a["fraccion"] for a in red["apareamientos"] if a["grupo"] == "arriba") in (0, pytest.approx(1.0))
    red = RI.disenar_red(rec.Mapa(casos[1][0], Sumidero("S", "X", 20.0, 90.0, 4.0), 10.0, 30.0))
    assert len([a for a in red["apareamientos"] if a["rama"] is not None]) == 2


def test_objetivo_corrige_el_latente_en_la_cima():
    # vapor que condensa a 129 °C sobre todo el sumidero: rec.pinch no suma ese calor y da 0 kW (PAT 133)
    m = rec.Mapa([("V", 129.0, None, None, 178.0)], Sumidero("S", "X", 36.0, 58.8, 5.7), 5.0, 30.0)
    assert RI.objetivo_pinch(m)[0] == pytest.approx(5.7 * 22.8, rel=1e-9)
    red = RI.disenar_red(m)
    assert red["Q_recuperado"] == pytest.approx(5.7 * 22.8, rel=1e-9) and red["avisos"]


def test_diagrama_de_rejilla_svg():
    red, _ = _red("agrozzi")
    s = RI.diagrama_rejilla_svg(red)
    assert s.startswith("<svg") and s.endswith("</svg>")
    n = 2 * len(red["apareamientos"]) + len(red["calentadores"]) + len(red["enfriadores"])
    assert s.count("<circle") == n
    assert "Pinch" in s and "Hot break" in s and "5.524 kW" in s
    for rubro in ("pellet", "chip", "lena"):
        assert RI.diagrama_rejilla_svg(_red(rubro)[0]).count("<svg") == 1
