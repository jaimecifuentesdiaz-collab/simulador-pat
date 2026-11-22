"""PAT 136, T24: sistemas de costeo con factores de literatura (motor/factores_costo.py) y su integración en motor/costeo.py.
Valores de tabla reproducidos a mano: Lang (Brown, 2006, Tabla 3.1; Peters y Timmerhaus, 1991, Tabla 18), Hand (Brown, 2006,
Tabla 3.2), desglose (Peters y Timmerhaus, 1991, Tabla 17), módulo desnudo (Turton et al., 2003, ejemplo del intercambiador de
100 m²) y costos fijos de operación (Peters y Timmerhaus, 1991, Tabla 25 y pp. 204 y 205)."""
import math, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import costeo as CT, factores_costo as FC, costos
from pat_sim.motor.planta import Planta
from pat_sim.escenarios import agrozzi, pellet, chip, lena

RUBROS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


def _filas():
    """Filas mínimas de costeo: un intercambiador, una bomba, un secador, una cañería y un cable."""
    return [dict(equipo="E-101", clave="intercambiador", costo_usd=100000.0), dict(equipo="P-101", clave="bomba_centrifuga", costo_usd=10000.0),
            dict(equipo="S-1", clave="secador_rotatorio", costo_usd=50000.0), dict(equipo="DN 50", clave="caneria", costo_usd=3000.0),
            dict(equipo="CAB", clave="cable_electrico", costo_usd=2000.0)]


# ---------------------------------------------------------------- valores de tabla
def test_lang_valores_de_tabla():
    L = FC.LANG
    assert (L["original"]["solidos"], L["original"]["mixta"], L["original"]["fluidos"]) == (3.10, 3.63, 4.74)
    assert (L["brown_nueva"]["solidos"], L["brown_nueva"]["mixta"], L["brown_nueva"]["fluidos"]) == (3.2, 3.5, 4.5)
    assert (L["ptw_capital_fijo"]["solidos"], L["ptw_capital_fijo"]["mixta"], L["ptw_capital_fijo"]["fluidos"]) == (3.9, 4.1, 4.8)
    assert (L["ptw_capital_total"]["solidos"], L["ptw_capital_total"]["mixta"], L["ptw_capital_total"]["fluidos"]) == (4.6, 4.9, 5.7)
    assert all("Tabla" in v["fuente"] and v["categoria"] == FC.LIT for v in L.values())


def test_hand_valores_de_tabla():
    esperado = dict(columna=4.0, recipiente=4.0, intercambiador=3.5, horno=2.0, bomba=4.0, compresor=2.5, instrumento=4.0, otros=2.5)
    assert {k: v[0] for k, v in FC.HAND.items()} == esperado
    assert all("Brown (2006), Tabla 3.2, p. 50" in v[2] for v in FC.HAND.values())


def test_desglose_tabla_17_suma_capital_fijo():
    """Tabla 17: capital fijo 387, 413 y 483 % de los equipos entregados; capital de trabajo 68, 74 y 86 %."""
    for col, tot in ((2, 387), (3, 413), (4, 483)):
        assert 100 + sum(f[col] for f in FC.DESGLOSE_PTW) == tot
    directos = [100 + sum(f[c] for f in FC.DESGLOSE_PTW if f[5] == "directo") for c in (2, 3, 4)]
    assert directos == [264, 293, 346]
    assert FC.CAPITAL_TRABAJO_PTW == dict(solidos=68, mixta=74, fluidos=86)


def test_om_rangos_de_literatura():
    assert FC.MANTENCION_PCT == pytest.approx(6.0)
    assert FC.MANTENCION_POR_PROCESO == {"simple": (2.0, 6.0), "promedio": (5.0, 9.0), "complejo": (7.0, 11.0)}
    assert FC.OM["suministros"][0] == pytest.approx(15.0) and FC.OM["seguros"][0] == pytest.approx(1.0)
    assert FC.OM["impuestos"][1] == (1.0, 4.0) and "p. 205" in FC.OM["impuestos"][3]


# ---------------------------------------------------------------- módulo desnudo (Turton)
def test_fbm_ejemplo_turton_intercambiador_100_m2():
    """Turton et al. (2003), ejemplo del cap. 5: Cp0 = 25 kUS$; C_BM0 = 82,3; inoxidable a 1 bar 154; acero al carbono a
    100 bar 98,1; inoxidable a 100 bar 197,4 kUS$ (precios de acero al carbono: precio_en_material=False)."""
    cp0 = 25.0
    b = FC.f_bm("hx_tubo_carcasa", "carbono", 0.0, precio_en_material=False)
    assert b["F_BM"] == pytest.approx(3.29) and cp0 * b["F_BM"] == pytest.approx(82.3, abs=0.1)
    assert cp0 * FC.f_bm("hx_tubo_carcasa", "inoxidable", 0.0, False)["F_BM"] == pytest.approx(154.0, abs=0.5)
    assert cp0 * FC.f_bm("hx_tubo_carcasa", "carbono", 100.0, False)["F_BM"] == pytest.approx(98.1, abs=0.2)
    assert cp0 * FC.f_bm("hx_tubo_carcasa", "inoxidable", 100.0, False)["F_BM"] == pytest.approx(197.4, abs=0.5)


def test_factor_presion_rangos():
    assert FC.factor_presion("bomba_centrifuga", 5.0)[0] == pytest.approx(1.0)            # bajo 10 barg
    lp = math.log10(50.0)
    assert FC.factor_presion("bomba_centrifuga", 50.0)[0] == pytest.approx(10 ** (-0.3935 + 0.3957 * lp - 0.00226 * lp * lp))
    fp_max, nota = FC.factor_presion("hx_tubo_carcasa", 500.0)
    assert fp_max == pytest.approx(FC.factor_presion("hx_tubo_carcasa", 140.0)[0]) and "sobre el rango" in nota
    assert FC.factor_presion("recipiente_vertical", 50.0)[0] == pytest.approx(1.0)


def test_fbm_precio_ya_en_material_y_compresor():
    b = FC.f_bm("hx_tubo_carcasa", "inoxidable", 0.0, precio_en_material=True)
    assert b["factor_sobre_precio"] == pytest.approx((1.63 + 1.66 * 2.73) / 2.73)
    c = FC.f_bm("compresor", "inoxidable", 0.0, precio_en_material=False)
    assert c["F_BM"] == pytest.approx(5.8)                                               # 2,8 en carbono, 5,8 en inoxidable
    assert FC.f_bm("compresor", "inoxidable", 0.0, True)["factor_sobre_precio"] == pytest.approx(2.8)


def test_modulo_desnudo_totales_a_mano():
    filas = _filas()
    r = FC.aplicar("modulo_desnudo", filas, material="carbono", precio_en_material=False)
    cbm = 100000 * 3.29 + 10000 * (1.89 + 1.35 * 1.6) + 50000 * 1.38
    cbm0 = 100000 * 3.29 + 10000 * (1.89 + 1.35) + 50000 * 1.38
    assert r["total_usd"] == pytest.approx(1.18 * cbm + 0.50 * cbm0)
    assert r["excluidos_usd"] == pytest.approx(5000.0) and r["base_usd"] == pytest.approx(160000.0)
    r2 = FC.aplicar("modulo_desnudo", filas, material="carbono", precio_en_material=False, ampliacion=True)
    assert r2["total_usd"] == pytest.approx(1.18 * cbm)
    assert r["recuperacion_usd"] == pytest.approx(1.18 * 100000 * 3.29 + 0.5 * 100000 * 3.29)


# ---------------------------------------------------------------- otros métodos sobre filas
def test_lang_hand_y_desglose_a_mano():
    filas = _filas()
    lang = FC.aplicar("lang", filas, tipo="mixta")
    assert lang["total_usd"] == pytest.approx(160000 * 3.63) and lang["factor_efectivo"] == pytest.approx(3.63)
    assert FC.aplicar("lang", filas, tipo="fluidos", lang_fuente="ptw_capital_fijo")["total_usd"] == pytest.approx(160000 * 4.8)
    hand = FC.aplicar("hand", filas)
    assert hand["total_usd"] == pytest.approx(100000 * 3.5 + 10000 * 4.0 + 50000 * 2.5)
    assert hand["recuperacion_usd"] == pytest.approx(350000.0)
    d = FC.aplicar("desglose", filas, tipo="solidos")
    assert d["total_usd"] == pytest.approx(160000 * 3.87)
    assert FC.aplicar("desglose", filas, tipo="solidos", incluir_terreno=False)["total_usd"] == pytest.approx(160000 * 3.81)
    assert FC.aplicar("desglose", filas, tipo="solidos", entrega_pct=10.0)["total_usd"] == pytest.approx(176000 * 3.87)


def test_factor_unico_incluye_granel_y_metodo_desconocido():
    filas = _filas()
    r = FC.aplicar("factor_unico", filas)
    assert r["total_usd"] == pytest.approx(165000 * costos.F_INSTALACION) and r["excluidos_usd"] == 0.0
    assert r["recuperacion_usd"] == pytest.approx(100000 * costos.F_INSTALACION)
    with pytest.raises(ValueError):
        FC.aplicar("guthrie_inventado", filas)


def test_tipo_planta_regla_y_eleccion():
    assert FC.tipo_planta(_filas())["tipo"] == "mixta"                                 # 110/160 = 69 % de fluidos
    assert FC.tipo_planta([dict(clave="secador_rotatorio", costo_usd=1.0)])["tipo"] == "solidos"
    assert FC.tipo_planta([dict(clave="evaporador_mvr", costo_usd=1.0)])["tipo"] == "fluidos"
    assert FC.tipo_planta([], None)["tipo"] == "mixta"
    assert FC.tipo_planta(_filas(), "fluidos")["justificacion"] == "Elegido por el usuario"


def test_operacion_fija_a_mano():
    op = FC.operacion_fija(1e6)
    assert op["mantencion"] == pytest.approx(60000.0)
    assert op["total"] == pytest.approx(60000 + 0.15 * 60000 + 10000 + 10000)
    op2 = FC.operacion_fija(1e6, mantencion_pct=15.0)
    m = next(f for f in op2["filas"] if f["clave"] == "mantencion")
    assert m["fuera_de_rango"] and m["categoria"] == "Usuario" and "4.a ed." in m["fuente"]
    assert FC.operacion_fija(0.0)["total"] == 0.0


def test_fuentes_completas():
    claves = {f["clave"] for f in FC.FUENTES_FACTORES}
    assert {"ptw1991", "brown2006", "hand1958", "lang1947", "turton2003", "turton2018", "smith2005"} <= claves
    for f in FC.FUENTES_FACTORES:
        assert f["referencia"] and f["verificado"] and ("isbn" in f and "doi" in f)
    for fam in FC.TURTON_BM.values():
        assert fam["fuente"] and fam["categoria"] in (FC.LIT, FC.LIT_T, FC.SUP)
    assert set(FC.METODOS) == {"factor_unico", "lang", "hand", "modulo_desnudo", "desglose"}


# ---------------------------------------------------------------- integración con costeo.py
def test_factor_unico_deja_costear_igual(pl):
    """El método por defecto deja los totales exactamente como antes de T24."""
    a = CT.costear(pl)
    b = CT.costear(pl, metodo="factor_unico")
    t = a["totales"]
    assert t["total_usd"] == pytest.approx(t["equipos_usd"] * costos.F_INSTALACION)
    assert t["instalacion_usd"] == pytest.approx(t["equipos_usd"] * (costos.F_INSTALACION - 1))
    assert set(b["totales"]) == set(t)
    for k in t:
        assert b["totales"][k] == pytest.approx(t[k])
    rec = sum(f["costo_usd"] for f in a["filas"] if f["clave"] in FC.CLAVES_RECUPERACION)
    assert t["recuperacion_usd"] == pytest.approx(rec * costos.F_INSTALACION)
    assert a["metodo"] == "factor_unico" and a["operacion"]["mantencion"] == pytest.approx(0.06 * t["total_usd"])


def test_costear_con_metodo_de_literatura(pl):
    r = CT.costear(pl, metodo="hand", mantencion_pct=4.0)
    t = r["totales"]; mc = r["metodo_costeo"]
    assert t["total_usd"] == pytest.approx(mc["total_usd"]) and t["total_usd"] == pytest.approx(t["equipos_usd"] + t["instalacion_usd"])
    assert t["f_inst"] == pytest.approx(t["total_usd"] / t["equipos_usd"]) and t["total_clp"] == pytest.approx(t["total_usd"] * costos.DOLAR)
    assert r["operacion"]["mantencion"] == pytest.approx(0.04 * t["total_usd"])
    assert mc["desglose"] and all(d["fuente"] for d in mc["desglose"])
    md = CT.costear(pl, metodo="modulo_desnudo", opciones_metodo=dict(material="carbono", precio_en_material=False, ampliacion=True))
    assert md["metodo_costeo"]["total_usd"] == pytest.approx(1.18 * sum(p.get("C_BM", 0.0) for p in md["metodo_costeo"]["por_equipo"]))


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_comparar_metodos_cuatro_rubros(rubro):
    p = RUBROS[rubro].crear().resolver()
    c = CT.comparar_metodos(p)
    assert [f["metodo"] for f in c["filas"]] == list(FC.METODOS)
    fu = c["filas"][0]
    assert fu["total_usd"] == pytest.approx(CT.costear(p)["totales"]["total_usd"]) and fu["diferencia_pct"] == pytest.approx(0.0)
    assert all(f["total_usd"] > 0 and f["fuente"] and f["mantencion_usd"] == pytest.approx(0.06 * f["total_usd"]) for f in c["filas"])
    assert c["tipo_planta"]["tipo"] == ("fluidos" if rubro == "tomate" else "solidos")


def test_comparar_metodos_planta_vacia_y_sin_resolver():
    c = CT.comparar_metodos(Planta())
    assert len(c["filas"]) == 5 and all(f["total_usd"] == 0.0 for f in c["filas"])
    assert any("vacía" in a for a in c["avisos"])
    p = agrozzi.crear(); p.resuelta = False                        # sin resolver
    assert any("Resuelva" in a for a in CT.comparar_metodos(p)["avisos"])
