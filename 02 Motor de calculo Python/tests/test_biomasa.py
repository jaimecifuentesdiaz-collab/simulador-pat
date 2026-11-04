"""Pruebas de la fase 6: catálogo de biomasa (pellet, chip de madera y leña) y sus escenarios base."""
import json, math
import pytest
from pat_sim.escenarios import pellet, chip, lena
from pat_sim.escenarios.biomasa_comun import resumen_corto
from pat_sim.catalogos import biomasa as B
from pat_sim.catalogos.registro import TIPOS, catalogo, planta_desde_dict
from pat_sim.motor.resumen import resumen_planta

ESCENARIOS = {"pellet": pellet, "chip": chip, "lena": lena}


@pytest.fixture(scope="module")
def plantas():
    return {k: m.crear() for k, m in ESCENARIOS.items()}


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_cierres_de_masa_solidos_y_energia(plantas, rubro):
    for f in plantas[rubro].cierres():
        assert abs(f["cierre_masa"]) < 1e-6, f
        assert f["cierre_solidos"] is None or abs(f["cierre_solidos"]) < 1e-6, f
        assert abs(f["cierre_energia"]) < 1e-6, f


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_especificacion_de_produccion_y_norma(plantas, rubro):
    pl = plantas[rubro]; m = ESCENARIOS[rubro]
    r = resumen_corto(pl)
    assert r["producto_t_h"] == pytest.approx(m.BASE["produccion"], rel=1e-8)
    desp = next(e for e in pl.equipos.values() if e.tipo == "despacho_biomasa").resultado.detalle
    assert desp["cumple_humedad"] and desp["cumple_pci"] and not pl.avisos


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_materia_seca_se_conserva_hasta_el_producto(plantas, rubro):
    pl = plantas[rubro]
    seca_in = pl.salidas[("B1", "producto")].s
    rechazos = sum(c.s for (k, pn), c in pl.salidas.items() if pn in ("rechazo", "aserrin"))
    prod = next(e for e in pl.equipos.values() if e.tipo == "despacho_biomasa")
    assert seca_in == pytest.approx(pl.corriente_entrada(prod.id).s + rechazos, rel=1e-10)


def test_secador_balance_de_agua_y_aire():
    pl = pellet.crear(); d = pl.equipos["T1"].resultado.detalle
    e = pl.salidas[("B1", "producto")]; p = pl.salidas[("T1", "producto")]
    assert d["agua_evaporada_kgh"] == pytest.approx(e.m - p.m, rel=1e-12)
    assert B.humedad_bh(p) == pytest.approx(pellet.BASE["Mseco"], rel=1e-12)
    # el sumidero es el calor para llevar el aire de secado del ambiente a la entrada, y lo entrega el generador
    snk = pl.sumideros()[0]
    assert snk.Q == pytest.approx(pl.equipos["T1"].resultado.servicios["calor_kW"], rel=1e-12)
    assert pl.equipos["D1"].resultado.detalle["Q_calor_kW"] == pytest.approx(snk.Q, rel=1e-12)


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_consumo_especifico_del_secador_en_rango_de_literatura(plantas, rubro):
    c = resumen_corto(plantas[rubro])["consumo_MJ_kg_agua"]
    assert 2.5 <= c <= 12.0, c   # de secadores continuos (~3 MJ/kg) a hornos de leña (~11,8 MJ/kg, Kofman, 2013)


def test_recuperacion_de_calor_del_escape(plantas):
    for rubro, pl in plantas.items():
        r = resumen_planta(pl)
        assert r["combustible"] == "biomasa" and 0 < r["cascada"] <= r["pinch"] + 1e-9 <= r["Qsumidero"] + 1e-9
        assert r["biomasa_cascada"]["t"] > 0 and r["biomasa_cascada"]["t"] < r["biomasa_base"]["t"]
    assert any(n.startswith("Aire del enfriador") for n in resumen_planta(plantas["pellet"])["corrientes"])


def test_pci_iso_18125():
    assert B.pci_humedo(19.2, 0.10) == pytest.approx(19.2 * 0.9 - 0.2443, rel=1e-12)
    assert B.pci_humedo(19.2, 0.0) == 19.2


def test_mas_humedad_mas_calor_de_secado():
    a = resumen_corto(pellet.crear(M0=0.45)); b = resumen_corto(pellet.crear(M0=0.55))
    assert b["calor_secado_kW"] > a["calor_secado_kW"] and b["carga_t_h"] > a["carga_t_h"]


def test_aviso_si_el_producto_no_cumple_la_norma():
    pl = lena.crear(Mseco=0.25)              # 25 % base húmeda = 33 % base seca > 25 % base seca
    assert any("supera el máximo" in a for a in pl.avisos)


def test_guardar_y_cargar_en_json(plantas):
    for pl in plantas.values():
        d = json.loads(json.dumps(pl.a_dict()))
        p2 = planta_desde_dict(d).resolver()
        assert resumen_planta(p2)["cascada"] == pytest.approx(resumen_planta(pl)["cascada"], rel=1e-9)


def test_catalogo_por_rubro():
    tp = {c.tipo for c in catalogo("pellet")}; tc = {c.tipo for c in catalogo("chip")}; tl = {c.tipo for c in catalogo("lena")}
    assert {"pelletizadora", "enfriador_pellet", "molino_martillos", "secador_biomasa", "criba_biomasa"} <= tp
    assert "astilladora" in tc and "astilladora" not in tp and "sierra_lena" in tl and "sierra_lena" not in tc
    assert "hot_break" not in tp and "caldera_gas" in tp            # los equipos generales están en todos los rubros
    for c in B.CATALOGO:
        assert c.tipo in TIPOS
        for p in c.params_base:
            assert p.categoria and (p.fuente or p.categoria in ("Supuesto", "Usuario")), (c.tipo, p.clave)


def test_pellet_contra_la_literatura(plantas):
    r = resumen_corto(plantas["pellet"])
    kwh_t = r["electricidad_kW"] / r["producto_t_h"]
    assert 90.1 <= kwh_t <= 194.7, kwh_t                        # Thek y Obernberger (2009, Tablas I y III)
    assert 4.0 <= r["consumo_MJ_kg_agua"] <= 6.0                 # secadores directos (Havlík y Dlouhý, 2020, Tabla 1)
    assert r["PCI_producto"] >= 16.5                             # ENplus A1 (EPC, 2022, Tabla 4)
