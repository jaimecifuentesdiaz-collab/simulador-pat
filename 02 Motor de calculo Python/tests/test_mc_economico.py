"""Pruebas del Montecarlo económico con confiabilidad y demanda (PAT 135, tarea T7.2)."""
import math
import numpy as np
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import mc_economico as M
from pat_sim.motor import riesgo as R
from pat_sim.motor import economia as eco
from pat_sim.motor import temporada as TM
from pat_sim.motor.resumen import resumen_planta

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
E = dict(precio_gas=2.77, dolar=990.35, inversion=1000.0, costo_anual=20.0, anios=10, tasa=0.10, precio_biomasa=6750.0)


@pytest.fixture(scope="module")
def plantas():
    out = {}
    for k, m in ESCENARIOS.items():
        pl = m.crear(); pl.resolver(); out[k] = (pl, resumen_planta(pl))
    return out


def _ctx(plantas, rubro, **kw):
    pl, r = plantas[rubro]
    return M.contexto(pl, r, E, **kw)


# PAT 135: margen_defecto
def test_margen_defecto_por_rubro():
    assert M.margen_defecto("tomate") == M.MARGEN["tomate"]
    assert M.margen_defecto("otro") == M.MARGEN["pellet"]
    assert all(v > 0 for v in M.MARGEN.values())


# PAT 135: disponibilidad
def test_disponibilidad_mtbf_mttr():
    assert M.disponibilidad(80.0, 1.5) == pytest.approx(80 / 81.5)
    assert M.disponibilidad(10.0, 0.0) == 1.0
    with pytest.raises(ValueError):
        M.disponibilidad(0.0, 1.0)


# PAT 135: equipos
@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_equipos_de_la_linea_con_fallas(plantas, rubro):
    pl, _r = plantas[rubro]
    eqs, _av = M.equipos(pl)
    assert eqs and all(0 < e["disponibilidad"] < 1 and e["tasa_mp"] > 0 for e in eqs)
    assert min(e["tasa_mp"] for e in eqs) == pytest.approx(TM.capacidad_linea(pl), rel=1e-9)   # el cuello es el de Temporada
    k = eqs[0]["id"]; eqs2, _ = M.equipos(pl, {k: (50.0, 5.0)})
    assert eqs2[0]["mtbf"] == 50.0 and eqs2[0]["disponibilidad"] == pytest.approx(50 / 55) and eqs2[0]["origen"] == "Pestaña Línea"
    eqs3, _ = M.equipos(pl, {k: None})
    assert len(eqs3) == len(eqs) - 1


# PAT 135: capacidad_fallas
def test_capacidad_fallas_tiempo_caido_medio_es_h_por_uno_menos_a():
    rng = np.random.default_rng(1); h = np.array([168.0, 168.0])
    eq = dict(tasa_mp=10.0, mtbf=80.0, mttr=1.5)
    cap, caidas = M.capacidad_fallas(rng, h, [eq], (20000, 1, 2))
    A = 80 / 81.5
    assert caidas[0].mean() == pytest.approx(168 * (1 - A), rel=0.03)
    assert cap.mean() == pytest.approx(10 * 168 * A, rel=0.002) and cap.max() <= 1680 + 1e-9
    cap0, _ = M.capacidad_fallas(np.random.default_rng(1), h, [], (3, 1, 2))
    assert np.isinf(cap0).all()
    _c, c_pm = M.capacidad_fallas(np.random.default_rng(1), h, [eq], (20000, 1, 2), reduccion_pm=0.5)
    assert c_pm[0].mean() < 0.6 * caidas[0].mean()         # con preventivo baja la tasa de falla


# PAT 135: estacional
def test_estacional_conserva_el_total():
    v = np.full(12, 10.0); w = M.estacional(v, 0.35)
    assert w.sum() == pytest.approx(120.0) and w.max() > 12 and w.min() < 8
    assert np.argmax(w) in (5, 6)                          # peak a mitad
    assert np.allclose(M.estacional(v, 0.0), v)


# PAT 135: periodos
@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_periodos_desde_temporada(plantas, rubro):
    pl, _r = plantas[rubro]; d = TM.datos_planta(pl)
    p = M.periodos(pl, "semana")
    assert len(p["demanda"]) == math.ceil(d["D"] / 7) and p["dias"].sum() == d["D"]
    assert p["demanda"].sum() == pytest.approx(d["total"], rel=1e-9)
    assert p["horas"].sum() == pytest.approx(d["D"] * d["H"])
    pm = M.periodos(pl, "mes", disp_programa=0.9)
    assert pm["horas"].sum() == pytest.approx(0.9 * d["D"] * d["H"]) and pm["demanda"].sum() == pytest.approx(d["total"], rel=1e-9)


def test_periodos_desde_el_desafio(plantas):
    pl, _r = plantas["pellet"]
    p = M.periodos(pl, demanda=[100.0, 200.0, {"valor": 300.0}])
    assert p["origen"] == "desafío" and len(p["demanda"]) == 3
    assert p["demanda"][1] == pytest.approx(200.0 * p["mp_por_t"])
    with pytest.raises(ValueError):
        M.periodos(pl, demanda=[1.0, -2.0])


# PAT 135: capacidad_estrategia
def test_capacidad_estrategias():
    dem = np.array([10.0, 30.0, 50.0, 10.0]); h = np.full(4, 10.0)
    seg = M.capacidad_estrategia(dem, h, 100.0, "seguimiento")
    uno = M.capacidad_estrategia(dem, h, 100.0, "un_nivel")
    dos = M.capacidad_estrategia(dem, h, 100.0, "dos_niveles")
    assert np.allclose(seg, dem) and np.allclose(uno, 25.0)
    assert np.allclose(dos, [10.0, 40.0, 40.0, 10.0])        # alta: períodos 2 y 3; baja: 1 y 4
    assert dos.sum() == pytest.approx(dem.sum()) and uno.sum() == pytest.approx(dem.sum())
    assert np.allclose(M.capacidad_estrategia(dem, h, 100.0, "seguimiento", 0.1), dem * 1.1)
    assert M.capacidad_estrategia(dem, h, 3.0, "seguimiento").max() == pytest.approx(30.0)   # tope de la línea
    with pytest.raises(ValueError):
        M.capacidad_estrategia(dem, h, 100.0, "otra")


# PAT 135: cambios_capacidad
def test_cambios_capacidad():
    h = np.full(4, 10.0)
    assert M.cambios_capacidad([25.0] * 4, h) == 0.0
    assert M.cambios_capacidad([10.0, 40.0, 40.0, 10.0], h) == pytest.approx(60.0)


# PAT 135: contexto
@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_contexto_en_los_cuatro_rubros(plantas, rubro):
    c = _ctx(plantas, rubro)
    assert c["combustible"] == ("gas" if rubro == "tomate" else "biomasa")
    assert c["base"]["alcance"] == "recuperador" and c["base"]["inversion"] == E["inversion"]
    assert 0 < c["disp_programa"] <= 1 and c["cap_t_h"] > 0
    c2 = _ctx(plantas, rubro, costeo={"total_clp": 2.5e9})
    assert c2["base"]["inversion_planta"] == pytest.approx(2500.0) and c2["base"]["alcance"] == "planta"
    assert c2["base"]["inversion"] == E["inversion"]                 # el recuperador sigue con la inversión de Economía
    assert c["recuperador"]["disponibilidad"] == pytest.approx(160 / 162)


# PAT 135: simular
def test_simular_sin_variacion_coincide_con_economia(plantas):
    """Sin variación, sin fallas y con capacidad sobrada en seguimiento, el VAN es el de economia.evaluacion menos el ajuste."""
    c = _ctx(plantas, "chip", aplicar_programa=False, estacionalidad=0.0)
    c = dict(c, equipos=[], cap_t_h=1e9, recuperador=None)
    s = M.simular(c, dict(cv_demanda=0.0, holgura=0.0), n=50, semilla=1)
    v = s["estrategias"]["seguimiento"]
    ahorro = R.ahorro_anual(c["base"], c["desplazado"], "biomasa")
    van_ref = eco.evaluacion(E["inversion"], ahorro, E["costo_anual"], E["anios"], E["tasa"])["VAN"]
    assert v["deficit_t"] == pytest.approx(0.0, abs=1e-6) and v["exceso_t"] == pytest.approx(0.0, abs=1e-6)
    assert v["media"] == pytest.approx(van_ref, rel=1e-9) and v["desviacion"] == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_simular_reproducible_y_coherente(plantas, rubro):
    c = _ctx(plantas, rubro)
    a = M.simular(c, n=300, semilla=7); b = M.simular(c, n=300, semilla=7); d = M.simular(c, n=300, semilla=8)
    for k in M.ESTRATEGIAS:
        x = a["estrategias"][k]
        assert np.array_equal(x["van"], b["estrategias"][k]["van"]) and not np.array_equal(x["van"], d["estrategias"][k]["van"])
        assert x["p5"] <= x["p50"] <= x["p95"] and 0 <= x["prob_negativo"] <= 1
        assert x["produccion_t"] + x["deficit_t"] == pytest.approx(x["demanda_t"], rel=1e-9)
        pp = x["por_periodo"]
        assert np.all(pp["produccion"] <= pp["demanda_media"] + 1e-9) and np.all(pp["produccion"] <= pp["disponible"] + 1e-9)
    assert a["estrategias"]["un_nivel"]["componentes"]["ajuste"] == 0.0


def test_simular_mas_fallas_baja_el_van(plantas):
    c = _ctx(plantas, "tomate")
    a = M.simular(c, n=400, semilla=3, estrategias=("seguimiento",))["estrategias"]["seguimiento"]
    b = M.simular(c, dict(f_mttr=3.0), n=400, semilla=3, estrategias=("seguimiento",))["estrategias"]["seguimiento"]
    assert b["deficit_t"] > a["deficit_t"] and b["media"] < a["media"]


def test_van_incremental_del_recuperador_no_depende_del_margen(plantas):
    """PAT 135 (corrección del coordinador): el margen perdido ocurre con y sin recuperador y se cancela."""
    for rubro in ("tomate", "pellet"):
        c = _ctx(plantas, rubro)
        a = M.simular(c, dict(margen=1.0, frac_ocioso=0.0), n=300, semilla=4)
        b = M.simular(c, dict(margen=5e6, frac_ocioso=0.9, frac_ajuste=0.9, reduccion_pm=0.0), n=300, semilla=4)
        for k in M.ESTRATEGIAS:
            assert np.array_equal(a["estrategias"][k]["van"], b["estrategias"][k]["van"])
            cp = a["estrategias"][k]["componentes"]
            assert cp["flujo"] == pytest.approx(cp["ahorro"] - cp["costo_anual"], rel=1e-12)
        assert a["inversion"] == E["inversion"]


def test_paradas_del_recuperador_bajan_el_ahorro(plantas):
    c = _ctx(plantas, "chip")
    sin = M.simular(dict(c, recuperador=None), n=500, semilla=2, estrategias=("un_nivel",))["estrategias"]["un_nivel"]
    con = M.simular(c, dict(f_mttr=5.0), n=500, semilla=2, estrategias=("un_nivel",))["estrategias"]["un_nivel"]
    assert con["componentes"]["ahorro"] < sin["componentes"]["ahorro"]


def test_simular_alcance_planta_suma_el_margen(plantas):
    c = _ctx(plantas, "pellet", costeo={"total_clp": 3e9})
    s = M.simular(c, n=200, semilla=1)
    x = s["estrategias"]["seguimiento"]; comp = x["componentes"]
    assert s["alcance"] == "planta" and comp["margen_produccion"] > 0 and s["inversion"] == pytest.approx(3000.0)
    assert comp["flujo"] == pytest.approx(comp["margen_produccion"] + comp["ahorro"] - comp["costo_anual"] - comp["preventivo"]
                                          - comp["ocioso"] - comp["ajuste"], rel=1e-9)
    with pytest.raises(ValueError):
        M.simular(c, dict(alcance="otro"), n=10)


def test_simular_rapido_con_miles_de_replicas(plantas):
    c = _ctx(plantas, "tomate")
    s = M.simular(c, n=5000, semilla=135)
    assert s["n"] == 5000 and s["segundos"] < 20


# PAT 135: rangos_tornado y tornado
def test_rangos_tornado_contienen_la_base(plantas):
    c = _ctx(plantas, "lena"); rg = M.rangos_tornado(c)
    for k, (lo, hi) in rg.items():
        assert lo <= c["base"][k] <= hi, k


def test_tornado_ordenado(plantas):
    c = _ctx(plantas, "chip")
    assert "margen" not in M.rangos_tornado(c)                        # en el recuperador el margen se cancela
    cp = _ctx(plantas, "chip", costeo={"total_clp": 2e9})
    assert {"margen", "inversion_planta"} <= set(M.rangos_tornado(cp))
    t = M.tornado(c, "dos_niveles", n=100)
    amp = [f["amplitud"] for f in t]
    assert amp == sorted(amp, reverse=True) and {f["clave"] for f in t} == set(M.rangos_tornado(c))
    assert all(f["nombre"] == M.NOMBRES[f["clave"]] for f in t)


# PAT 135: histograma
def test_histograma_cuenta_todo():
    v = np.arange(100.0)
    h = M.histograma(v, 10)
    assert len(h) == 10 and sum(c for _a, _b, c in h) == 100 and h[0][0] == 0.0
    assert M.histograma([5.0, 5.0], 10) == [(5.0, 5.0, 2)] and M.histograma([], 5) == []
    h2 = M.histograma(v, 5, desde=-100, hasta=200)
    assert sum(c for _a, _b, c in h2) == 100 and h2[0][0] == -100
