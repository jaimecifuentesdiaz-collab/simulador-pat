"""La aplicación debe reproducir el modelo de la planta basada en Agrozzi (results.json y fuel.json de
Modelo_PAT_Agrozzi, 26-10-2026). Tolerancia relativa 1e-6."""
import json, os, sys, pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.escenarios import agrozzi
from pat_sim.motor import recuperacion as rec

REF = json.load(open(os.path.join(os.path.dirname(__file__), "referencia", "results.json")))
FUEL = json.load(open(os.path.join(os.path.dirname(__file__), "referencia", "fuel.json")))
rel = lambda a: pytest.approx(a, rel=1e-6, abs=1e-6)


@pytest.fixture(scope="module")
def base():
    pl = agrozzi.crear(); return pl, agrozzi.resumen(pl)


def test_balance_materia(base):
    pl, r = base; b = REF["base"]
    assert r["M0"] == rel(b["M0"])
    assert pl.salidas[("F1", "producto")].m == rel(b["M2"])
    assert pl.salidas[("F2", "jugo")].m == rel(b["F"])
    assert pl.salidas[("W2", "concentrado")].m == rel(b["A1"])
    assert pl.salidas[("W3", "concentrado")].m == rel(b["A2"])
    assert pl.salidas[("W4", "concentrado")].m == rel(b["PV"])
    assert r["P"] == rel(b["P"])
    assert r["xV"] == rel(b["xV"])


def test_energia_y_servicios(base):
    pl, r = base; b = REF["base"]
    assert r["Qhb"] == rel(b["Qhb"]); assert r["S_vivo"] == rel(b["S"])
    assert pl.equipos["W5"].resultado.detalle["Q_kW"] == rel(b["Qst"])
    assert r["Wc_MVR"] == rel(b["Wc"]); assert r["excedente_MVR"] == rel(b["Qvent"])
    assert pl.equipos["B2"].resultado.detalle["vapor_flash_kgh"] == rel(b["mf"])


def test_corrientes(base):
    pl, r = base
    for nm, Ti, To, CP, Q in REF["hot"]:
        s = r["corrientes"][nm]
        assert s[1] == rel(Ti); assert s[4] == rel(Q)
        if CP is not None: assert s[3] == rel(CP)
    assert r["oferta"] == rel(REF["oferta"])


def test_cascada_y_pinch(base):
    pl, r = base
    assert r["cascada"] == rel(REF["casc"])
    for f, (nm, Q, Ta, Tb) in zip(r["cascada_filas"], REF["casc_rows"]):
        assert f["corriente"] == nm and f["Q_kW"] == rel(Q) and f["T_sale"] == rel(Tb)
    tg, qh, pin = REF["pinch"]
    assert r["pinch"] == rel(tg) and r["Q_externo_min"] == rel(qh) and r["T_pinch"] == pin
    assert r["alt2"] == rel(REF["alt2"])


def test_gas(base):
    pl, r = base
    for k in ("gas_MWh", "kg", "m3", "MMBtu"):
        kk = {"gas_MWh": "fuelMWh"}.get(k, k)
        assert r["gas_base"][k] == rel(FUEL["base"][kk]); assert r["gas_cascada"][k] == rel(FUEL["casc"][kk])
    assert r["gas_linea_kgh"] == rel(FUEL["line"]["kgh"]); assert r["vapor_linea_kW"] == rel(FUEL["line"]["Qheat"])


def test_cierres(base):
    pl, r = base
    for f in pl.cierres():
        assert abs(f["cierre_masa"]) < 1e-6, f
        assert f["cierre_solidos"] is None or abs(f["cierre_solidos"]) < 1e-6, f
        assert abs(f["cierre_energia"]) < 1e-6, f


CASOS = {"TcMVR_65": dict(TcMVR=65), "TcMVR_85": dict(TcMVR=85), "N_4": dict(N=4), "N_5": dict(N=5),
         "tom_0.03": dict(tom=0.03), "tom_0.05": dict(tom=0.05), "rej_0.0": dict(rej=0.0), "Thb_96": dict(Thb=96),
         "xP_0.28": dict(xP=0.28), "xP_0.32": dict(xP=0.32), "xB_0.14": dict(xB=0.14), "xB_0.16": dict(xB=0.16),
         "Ra_0.5": dict(Ra=0.5), "Ra_1.5": dict(Ra=1.5), "tvr_off": dict(tvr=False), "flash_off": dict(flash=False),
         "xF_0.045": dict(xF=0.045), "xF_0.055": dict(xF=0.055)}


@pytest.mark.parametrize("caso", list(CASOS))
def test_sensibilidades(caso):
    pl = agrozzi.crear(**CASOS[caso]); r = agrozzi.resumen(pl); ref = REF["sens"][caso]
    assert r["cascada"] == rel(ref["casc"]); assert r["pinch"] == rel(ref["tg"]); assert r["Qhb"] == rel(ref["Qhb"])


@pytest.mark.parametrize("dT", [7.5, 10])
def test_aproximacion(dT):
    pl = agrozzi.crear(dT=dT); r = agrozzi.resumen(pl); ref = REF["sens"][f"dT_{dT}"]
    assert r["cascada"] == rel(ref["casc"]); assert r["pinch"] == rel(ref["tg"])


def test_F6():
    pl = agrozzi.crear(); snk = pl.sumideros()[0]
    res = pl.residuales(solo_mapa=False)
    # en model.py F6 es todo el excedente de los dos MVR, latente a la temperatura de ebullición
    exc = sum(x.Q for x in res if x.nombre.startswith("F6"))
    m = rec.mapa(pl.residuales(), snk, 5, 30); m.corrientes.append(("F6", 70.0, None, None, exc))
    assert rec.cascada(m)[0] == rel(REF["sens"]["F6_on"]["casc"]); assert rec.pinch(m)[0] == rel(REF["sens"]["F6_on"]["tg"])


def test_guardar_y_cargar():
    import json
    from pat_sim.catalogos.registro import planta_desde_dict
    pl = agrozzi.crear(); d = json.loads(json.dumps(pl.a_dict() | {"_p": pl._p}, default=float))
    pl2 = planta_desde_dict(d).resolver(); r2 = agrozzi.resumen(pl2)
    assert r2["cascada"] == rel(REF["casc"]) and r2["pinch"] == rel(REF["pinch"][0])


def test_simbolos_e_isa():
    from pat_sim.simbolos import iso10628, isa51, isa54
    from pat_sim.catalogos.registro import TIPOS
    for c in TIPOS.values(): assert c.simbolo in iso10628.SIMBOLOS and c.iso_letra in iso10628.LETRAS_EQUIPO
    assert isa51.interpretar("TIC")["funciones"] == ["Indicador", "Controlador"]
    assert "<svg" in isa54.lazo_svg("PIC", "301")


# PAT 134: un °Brix imposible no deja la planta «resuelta» con caudales negativos (antes la pantalla quedaba con datos absurdos)
@pytest.mark.parametrize("valor", [0.0, 0.10])
def test_brix_de_la_pasta_imposible_se_rechaza(valor):
    from pat_sim.escenarios import agrozzi
    pl = agrozzi.crear()
    i = [n for n, s in enumerate(pl.especs) if s.param == "brix_salida"][0]
    pl.especs[i].valor = valor
    with pytest.raises(ValueError):
        pl.resolver()


def test_brix_cero_en_el_venus_tiene_mensaje_claro():
    from pat_sim.escenarios import agrozzi
    pl = agrozzi.crear(); pl.especs = []; pl.equipos["W4"].params["brix_salida"].valor = 0.0
    with pytest.raises(ValueError, match="concentración de salida"):
        pl.resolver()
