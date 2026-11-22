"""PAT 136, T23 (punto 10c de los comentarios del profesor Torres): equipos auxiliares (bombas, válvulas, estanques pulmón, cañerías
y servicios) en los cuatro rubros y con la planta vacía; llaman a hidraulica.py, linea_fluida.py y costeo.py."""
import math
import pytest
from pat_sim.motor import auxiliares as AX, costeo as CO, costos, desafio as D, hidraulica as HID, linea_fluida as LF, seleccion as SEL
from pat_sim.datos import mantenedor as M
from pat_sim.escenarios import agrozzi, pellet, chip, lena

ESC = dict(tomate=agrozzi, pellet=pellet, chip=chip, lena=lena)
CAT = M.semilla_catalogo_comercial()


def _vacia(rubro="pellet"):
    return D.planta_vacia(dict(titulo="V", enunciado="diseñar", producto="X", rubro=rubro,
                               demanda=dict(periodo="mes", unidad="t", valores=[1], fuente="Supuesto"), precios=[]))


@pytest.fixture(scope="module")
def tomate():
    return agrozzi.crear()


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_los_cuatro_rubros_entregan_los_cinco_apartados(rubro):
    pl = ESC[rubro].crear()
    r = AX.auxiliares(pl)
    for k in ("bombas", "valvulas", "estanques", "canerias", "servicios", "resumen", "avisos"):
        assert k in r
    ids, _ = LF.linea_principal(pl)
    assert len(r["estanques"]["filas"]) == len(ids) - 1 > 0                    # un pulmón entre cada par de equipos de la línea
    assert [f["servicio"] for f in r["servicios"]["filas"]] == ["Vapor", "Calor (aire caliente)", "Agua de caldera", "Aire", "Electricidad"]
    assert r["total_usd"] > 0 and r["total_instalado_usd"] == pytest.approx(r["total_usd"] * costos.F_INSTALACION)
    assert r["total_usd"] == pytest.approx(sum(x["costo_usd"] for x in r["resumen"]))
    assert r["total_clp"] == pytest.approx(r["total_usd"] * costos.DOLAR)


def test_tomate_tiene_bombas_canerias_y_servicio_de_vapor(tomate):
    r = AX.auxiliares(tomate)
    b = r["bombas"]
    assert b["filas"] and b["total_kw"] > 0 and r["canerias"]["lineas"] and r["canerias"]["por_dn"]
    red = HID.red_hidraulica(tomate)
    assert 0 < b["total_kw"] <= red["potencia_total_kW"] + 1e-9
    assert b["energia_mwh"] == pytest.approx(b["total_kw"] * red["horas"] / 1000.0)
    vap = next(f for f in r["servicios"]["filas"] if f["servicio"] == "Vapor")
    assert vap["demanda"] == pytest.approx(tomate.servicio_total("vapor_kW")) and vap["costo_usd"] > 0 and "caldera" in vap["genera"].lower()
    ag = next(f for f in r["servicios"]["filas"] if f["servicio"] == "Agua de caldera")
    assert ag["demanda"] == pytest.approx(vap["demanda"] * 3600 / CO.DH_VAPOR / 1000.0)
    assert len(r["valvulas"]["control"]) >= 1 and r["valvulas"]["n_retencion"] == len(b["filas"])
    assert r["valvulas"]["n_bloqueo"] == 2 * len(b["filas"])


@pytest.mark.parametrize("rubro", ["pellet", "chip", "lena"])
def test_biomasa_sin_liquidos_avisa_y_sus_servicios_son_calor_aire_y_electricidad(rubro):
    pl = ESC[rubro].crear()
    r = AX.auxiliares(pl)
    assert r["bombas"]["filas"] == [] and r["canerias"]["lineas"] == []
    assert any("no mueve líquidos" in a for a in r["avisos"]) and any("no tiene líneas de líquido" in a for a in r["avisos"])
    s = {f["servicio"]: f for f in r["servicios"]["filas"]}
    assert s["Calor (aire caliente)"]["demanda"] == pytest.approx(pl.servicio_total("calor_kW")) and pl.servicio_total("calor_kW") > 0
    assert s["Calor (aire caliente)"]["costo_usd"] > 0 and s["Aire"]["demanda"] > 0 and s["Vapor"]["demanda"] == 0
    assert s["Electricidad"]["demanda"] == pytest.approx(pl.servicio_total("electricidad_kW"))


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_planta_vacia_y_sin_resolver_no_falla_y_avisa(rubro):
    pl = _vacia("pellet" if rubro != "tomate" else "tomate")
    r = AX.auxiliares(pl)
    assert r["avisos"] and r["total_usd"] == 0.0 and r["bombas"]["filas"] == [] and r["estanques"]["filas"] == []
    assert r["servicios"]["filas"] == [] and r["canerias"]["lineas"] == [] and r["valvulas"]["control"] == []
    pl2 = ESC[rubro].crear(); pl2.resuelta = False
    r2 = AX.auxiliares(pl2)
    assert "no está resuelta" in r2["avisos"][0] and r2["total_usd"] == 0.0


def test_dimensionar_estanque_cilindro_vertical_con_llenado_y_relacion_hd():
    d = AX.dimensionar_estanque(8.0, 1000.0)                     # 8 t de agua = 8 m³ útiles
    assert d["v_util_m3"] == pytest.approx(8.0) and d["v_geo_m3"] == pytest.approx(10.0)         # llenado 80 %
    assert d["D_m"] == pytest.approx((4 * 10.0 / (math.pi * 2.0)) ** (1 / 3)) and d["H_m"] == pytest.approx(2 * d["D_m"])
    assert d["huella_m2"] == pytest.approx(math.pi * d["D_m"] ** 2 / 4)
    assert math.pi * d["D_m"] ** 2 / 4 * d["H_m"] == pytest.approx(10.0)
    assert AX.dimensionar_estanque(0.0, 500.0)["D_m"] == 0.0
    with pytest.raises(ValueError):
        AX.dimensionar_estanque(1.0, 0.0)


def test_precio_del_estanque_escala_con_williams_y_se_actualiza_con_cepci():
    p10, p20 = AX.precio_estanque(10.0), AX.precio_estanque(20.0)
    assert p20["costo_usd"] / p10["costo_usd"] == pytest.approx(2 ** 0.6)
    assert p10["costo_usd"] == pytest.approx(AX.SUPUESTOS["precio_estanque"].valor * CO.CEPCI_HOY / CO.cepci_de(2023))
    assert p10["categoria"] == "Supuesto" and "Supuesto" in p10["fuente"]
    assert AX.precio_estanque(10.0, cepci_hoy=2 * CO.cepci_de(2023))["costo_usd"] == pytest.approx(2 * AX.SUPUESTOS["precio_estanque"].valor)


def test_pulmon_por_residencia_por_falla_y_el_mayor():
    pl = pellet.crear()
    res = AX.estanques(pl, "residencia", minutos=30.0)["filas"]
    fal = AX.estanques(pl, "falla", cobertura=1.0)["filas"]
    may = AX.estanques(pl, "mayor", minutos=30.0, cobertura=1.0)["filas"]
    assert len(res) == len(fal) == len(may) > 0
    for a, b, c in zip(res, fal, may):
        assert a["masa_t"] == pytest.approx(a["carga_t_h"] * 0.5)                              # 30 min de la carga del siguiente
        assert b["masa_t"] == pytest.approx(b["carga_t_h"] * b["mttr_h"])                      # MTTR del anterior por esa carga
        assert c["masa_t"] == pytest.approx(max(a["masa_t"], b["masa_t"]))
        assert a["id"] == f"{a['antes']}-{a['despues']}"
        assert a["v_geo_m3"] == pytest.approx(a["masa_t"] * 1000 / a["rho"] / 0.8)
    # la capacidad en t es la misma magnitud de los tanques de la pestaña Línea (30 min de la carga del equipo siguiente)
    ids, _ = LF.linea_principal(pl)
    assert res[0]["masa_t"] == pytest.approx(LF.SUPUESTOS["tanque_min"].valor / 60 * pl.equipos[ids[1]].resultado.detalle["carga_t_h"])
    with pytest.raises(ValueError):
        AX.estanques(pl, "otro")


def test_cobertura_y_minutos_cambian_el_tamano_proporcionalmente():
    pl = chip.crear()
    a = AX.estanques(pl, "falla", cobertura=1.0)["filas"]; b = AX.estanques(pl, "falla", cobertura=3.0)["filas"]
    assert all(y["masa_t"] == pytest.approx(3 * x["masa_t"]) for x, y in zip(a, b))
    c = AX.estanques(pl, "residencia", minutos=10.0)["filas"]; d = AX.estanques(pl, "residencia", minutos=60.0)["filas"]
    assert all(y["costo_usd"] > x["costo_usd"] for x, y in zip(c, d))


def test_densidad_liquida_del_tomate_y_solida_de_la_biomasa(tomate):
    t = AX.estanques(tomate)["filas"]
    assert any(abs(f["rho"] - AX.SUPUESTOS["densidad_solido"].valor) > 1.0 and "líquida" in f["fuente_rho"] for f in t)
    p = AX.estanques(pellet.crear())["filas"]
    assert all(f["rho"] == AX.SUPUESTOS["densidad_solido"].valor and "Supuesto" in f["fuente_rho"] for f in p)


def test_pulmon_por_falla_usa_el_mttr_de_la_seleccion_aplicada():
    pl = pellet.crear()
    antes = {f["id"]: f for f in AX.estanques(pl, "falla")["filas"]}
    ids, _ = LF.linea_principal(pl)
    primero = ids[0]
    etapa = next(e for e in SEL.seleccionar(pl, CAT)["etapas"] if e["equipo"] == primero)
    a = etapa["alternativas"][0]
    SEL.aplicar(pl, {primero: a})
    despues = {f["id"]: f for f in AX.estanques(pl, "falla")["filas"]}
    k = f"{primero}-{ids[1]}"
    assert despues[k]["mttr_h"] == pytest.approx(a["mttr_h"]) and "Selección" in despues[k]["fuente_mttr"] and "Supuesto" in antes[k]["fuente_mttr"]


def test_canerias_usan_el_largo_del_layout_si_hay(tomate):
    lineas = HID.red_hidraulica(tomate)["lineas"]
    nombre = str(lineas[0]["linea"])
    sin = AX.canerias(tomate, None, CO.costear(tomate, X={})["filas"])
    con = AX.canerias(tomate, {nombre: 77.0}, CO.costear(tomate, X={}, longitudes={nombre: 77.0})["filas"])
    f0 = next(x for x in con["lineas"] if x["linea"] == nombre)
    assert f0["largo_m"] == pytest.approx(77.0) and f0["fuente_largo"] == "Layout"
    assert all(x["largo_m"] == HID.L_LINEA and "Supuesto" in x["fuente_largo"] for x in sin["lineas"])
    assert con["total_m"] == pytest.approx(sin["total_m"] - HID.L_LINEA + 77.0)
    assert sum(x["largo_m"] for x in con["por_dn"]) == pytest.approx(con["total_m"])        # el costeo cuenta los mismos metros
    assert all(x["DN"] == CO.diametro_nominal(next(l for l in lineas if str(l["linea"]) == x["linea"])["D_mm"]) for x in con["lineas"])


def test_servicio_electrico_suma_equipos_y_bombas_y_el_cable_del_layout(tomate):
    cables = {"AL-W2": 120.0, "AL-F2": 80.0}
    r = AX.auxiliares(tomate, cables_m=cables, precio_kwh=100.0)
    el = next(f for f in r["servicios"]["filas"] if f["servicio"] == "Electricidad")
    assert el["demanda"] == pytest.approx(tomate.servicio_total("electricidad_kW") + r["bombas"]["total_kw"])
    assert el["costo_usd"] > 0 and "cable" in el["fuente"].lower()
    assert r["servicios"]["energia_kwh"] == pytest.approx(el["demanda"] * r["servicios"]["horas"])
    assert r["servicios"]["energia_clp"] == pytest.approx(r["servicios"]["energia_kwh"] * 100.0)
    assert next(x for x in r["resumen"] if x["rubro"] == "Cable eléctrico")["costo_usd"] == pytest.approx(el["costo_usd"])
    sin_cable = AX.auxiliares(tomate)
    assert next(f for f in sin_cable["servicios"]["filas"] if f["servicio"] == "Electricidad")["costo_usd"] is None


def test_el_costo_viene_del_costeo_y_se_puede_reutilizar_su_resultado(tomate):
    res = CO.costear(tomate, X={})
    r1 = AX.auxiliares(tomate); r2 = AX.auxiliares(tomate, costeo_res=res)
    assert r1["total_usd"] == pytest.approx(r2["total_usd"])
    bombas_costeo = sum(f["costo_usd"] for f in res["filas"] if f["clave"] == "bomba_centrifuga")
    assert next(x for x in r1["resumen"] if x["rubro"] == "Bombas")["costo_usd"] == pytest.approx(bombas_costeo)
    gen = sum(f["costo_usd"] for f in res["filas"] if f["clave"] in ("caldera_gas", "generador_biomasa"))
    assert next(x for x in r1["resumen"] if x["rubro"] == "Generación de vapor o calor")["costo_usd"] == pytest.approx(gen)


def test_factor_de_instalacion_y_dolar_se_aplican_al_total(tomate):
    r = AX.auxiliares(tomate, f_inst=3.0, dolar=1000.0)
    assert r["total_instalado_usd"] == pytest.approx(3.0 * r["total_usd"]) and r["total_clp"] == pytest.approx(1000.0 * r["total_usd"])
    assert all(x["instalado_usd"] == pytest.approx(3.0 * x["costo_usd"]) for x in r["resumen"])
