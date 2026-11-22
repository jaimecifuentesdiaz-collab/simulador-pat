"""PAT 142: internación de equipos importados y flujo de caja con impuestos (motor/internacion.py).
Ejemplo numérico de la sección 5.4 de la investigación docs/costo_internacion.md (equipo de US$ 500.000 FOB desde China y desde
Alemania, contenedor de 40', 20 t, seguro presunto 2 %, tratado con arancel 0 %, montaje 20 %, tipo de cambio 981,08 $/US$)."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import costeo as CT, internacion as INT, economia as eco
from pat_sim.motor.planta import Planta
from pat_sim.escenarios import agrozzi, pellet, chip, lena

RUBROS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
CFG_54 = dict(incoterm="FOB", carga="40'", n_cont=1, peso_t=20.0, prueba_origen=True)


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


@pytest.fixture(scope="module")
def res(pl):
    return CT.costear(pl)


# ---------------------------------------------------------------- ejemplo numérico de la sección 5.4
@pytest.mark.parametrize("pais,flete,cif,agente,puesto,montaje,activo,iva_imp,iva_loc,desembolso,dep_n,dep_a", [
    ("China", 5600.0, 515600.0, 2578.0, 519225.33, 103845.07, 623070.40, 97964.0, 688.81, 721723.21, 41538.03, 124614.08),
    ("Alemania", 4000.0, 514000.0, 2570.0, 517617.33, 103523.47, 621140.80, 97660.0, 687.29, 719488.09, 41409.39, 124228.16),
])
def test_ejemplo_5_4(pais, flete, cif, agente, puesto, montaje, activo, iva_imp, iva_loc, desembolso, dep_n, dep_a):
    r = INT.costo_equipo(500000.0, dict(CFG_54, pais=pais), None, 0.20)
    assert r["fob"] == pytest.approx(500000.0)
    assert r["flete"] == pytest.approx(flete)
    assert r["seguro"] == pytest.approx(10000.0)
    assert r["cif"] == pytest.approx(cif)
    assert r["arancel"] == 0.0
    assert r["agente"] == pytest.approx(agente)
    assert r["puerto"] == pytest.approx(175.0 + 130.0 + 91.74 + 147.80, abs=0.01)   # DHC, CMD, gate y almacenaje
    assert r["transporte"] == pytest.approx(502.80)
    assert r["puesto_planta"] == pytest.approx(puesto, abs=0.01)
    assert r["montaje"] == pytest.approx(montaje, abs=0.01)
    assert r["activo"] == pytest.approx(activo, abs=0.01)
    assert r["iva_importacion"] == pytest.approx(iva_imp, abs=0.01)
    assert r["iva_locales"] == pytest.approx(iva_loc, abs=0.01)
    assert r["activo"] + r["iva_importacion"] + r["iva_locales"] == pytest.approx(desembolso, abs=0.01)
    assert r["activo"] / 15 == pytest.approx(dep_n, abs=0.01)
    assert r["activo"] / 5 == pytest.approx(dep_a, abs=0.01)


@pytest.mark.parametrize("pais,arancel,activo,iva", [("China", 30936.0, 660193.60, 103841.84), ("Alemania", 30840.0, 658148.80, 103519.60)])
def test_sensibilidad_sin_prueba_de_origen(pais, arancel, activo, iva):
    r = INT.costo_equipo(500000.0, dict(CFG_54, pais=pais, prueba_origen=False), None, 0.20)
    assert r["t_arancel"] == pytest.approx(0.06)
    assert r["arancel"] == pytest.approx(arancel, abs=0.01)
    assert r["activo"] == pytest.approx(activo, abs=0.01)
    assert r["iva_importacion"] == pytest.approx(iva, abs=0.01)


# ---------------------------------------------------------------- tratados y casos de arancel
@pytest.mark.parametrize("pais", ["China", "Alemania", "Italia", "Otro país de la Unión Europea", "EE. UU.", "Brasil", "Argentina"])
def test_tratado_con_prueba_de_origen_deja_arancel_cero(pais):
    r = INT.costo_equipo(100000.0, dict(pais=pais), None)
    assert r["importado"] and r["arancel"] == 0.0 and r["t_arancel"] == 0.0


def test_sin_tratado_arancel_general_y_usado_con_recargo():
    r = INT.costo_equipo(100000.0, dict(pais="Otro país sin tratado"), None)
    assert r["arancel"] == pytest.approx(0.06 * r["cif"])
    u = INT.costo_equipo(100000.0, dict(pais="Otro país sin tratado", usado=True), None)
    assert u["arancel"] == pytest.approx(0.06 * 1.5 * u["cif"])
    b = INT.costo_equipo(100000.0, dict(pais="Otro país sin tratado", bien_capital=True), None)
    assert b["arancel"] == 0.0


def test_incoterms_y_flete_presunto():
    fob = INT.costo_equipo(100000.0, dict(pais="Italia"), None)          # Italia sin tarifa publicada: 5 % del FOB
    assert fob["flete"] == pytest.approx(5000.0) and fob["seguro"] == pytest.approx(2000.0)
    cfr = INT.costo_equipo(100000.0, dict(pais="China", incoterm="CFR"), None)
    assert cfr["flete"] == 0.0 and cfr["seguro"] == pytest.approx(2000.0)
    cif = INT.costo_equipo(100000.0, dict(pais="China", incoterm="CIF"), None)
    assert cif["flete"] == 0.0 and cif["seguro"] == 0.0 and cif["cif"] == pytest.approx(100000.0)
    exw = INT.costo_equipo(100000.0, dict(pais="China", incoterm="EXW", gastos_origen_usd=3000.0), None)
    assert exw["fob"] == pytest.approx(103000.0)
    bb = INT.costo_equipo(100000.0, dict(pais="China", carga="break bulk"), None)
    assert bb["flete"] == pytest.approx(5000.0) and bb["puerto"] == 0.0 and bb["avisos"]
    q = INT.costo_equipo(100000.0, dict(pais="China", flete_usd=7000.0), None)
    assert q["flete"] == pytest.approx(7000.0)


# ---------------------------------------------------------------- IVA como crédito fiscal
def test_iva_no_entra_al_activo():
    r = INT.costo_equipo(200000.0, dict(pais="China"), None)
    assert r["activo"] == pytest.approx(r["cif"] + r["arancel"] + r["gastos"])
    assert r["iva_importacion"] == pytest.approx(0.19 * (r["cif"] + r["arancel"]))
    assert r["iva_importacion"] > 0 and r["activo"] < r["cif"] + r["arancel"] + r["gastos"] + r["iva_importacion"]


@pytest.mark.parametrize("caso,anio", [("A", 0), ("B", 1)])
def test_flujo_iva_pagado_y_recuperado(caso, anio):
    f = INT.flujo_caja(1000.0, 300.0, 50.0, 10, 0.10, caso_iva=caso)
    assert f["iva"] == pytest.approx(190.0)
    assert f["filas"][0]["iva_pagado"] == pytest.approx(-190.0)
    assert f["filas"][anio]["iva_recuperado"] == pytest.approx(190.0)
    assert sum(x["iva_pagado"] + x["iva_recuperado"] for x in f["filas"]) == pytest.approx(0.0)
    assert f["anio_recuperacion_iva"] == anio


def test_flujo_caso_a_iva_neutro_y_caso_b_cuesta_un_anio():
    a = INT.flujo_caja(1000.0, 300.0, 50.0, 10, 0.10, caso_iva="A")
    b = INT.flujo_caja(1000.0, 300.0, 50.0, 10, 0.10, caso_iva="B")
    assert a["VAN"] - b["VAN"] == pytest.approx(190.0 - 190.0 / 1.1)


# ---------------------------------------------------------------- flujo de caja con impuestos
def test_flujo_reproduce_van_sin_impuestos():
    f = INT.flujo_caja(1000.0, 300.0, 50.0, 10, 0.10, tasa_renta_modo="fija", tasa_renta_fija=0.0, valor_desecho=False)
    assert f["VAN"] == pytest.approx(eco.evaluacion(1000.0, 300.0, 50.0, 10, 0.10)["VAN"])
    assert f["TIR"] == pytest.approx(eco.evaluacion(1000.0, 300.0, 50.0, 10, 0.10)["TIR"], abs=1e-6)


def test_flujo_impuesto_y_depreciacion_a_mano():
    f = INT.flujo_caja(1000.0, 300.0, 50.0, 10, 0.10, tasa_renta_modo="fija", tasa_renta_fija=0.27, regimen_dep="acelerada",
                       valor_desecho=False)
    x = f["filas"][1]
    assert x["depreciacion"] == pytest.approx(-200.0)
    assert x["uai"] == pytest.approx(50.0) and x["impuesto"] == pytest.approx(-13.5)
    assert x["flujo"] == pytest.approx(250.0 - 13.5)
    y = f["filas"][6]                                   # después de la vida tributaria de 5 años
    assert y["depreciacion"] == 0.0 and y["impuesto"] == pytest.approx(-0.27 * 250.0)
    assert f["depreciacion_total"] == pytest.approx(1000.0)


def test_tasa_renta_ley_21850():
    assert INT.tasa_renta(2026) == 0.27            # año tributario 2027
    assert INT.tasa_renta(2027) == 0.255           # AT 2028
    assert INT.tasa_renta(2028) == 0.24            # AT 2029
    assert INT.tasa_renta(2029) == 0.23 and INT.tasa_renta(2040) == 0.23
    assert INT.tasa_renta(2029, "fija", 0.30) == 0.30


def test_valor_desecho_terreno_y_perdidas():
    f = INT.flujo_caja(1000.0, 300.0, 50.0, 3, 0.10, terreno=100.0, regimen_dep="normal", tasa_renta_modo="fija")
    assert f["filas"][1]["depreciacion"] == pytest.approx(-60.0)                    # (1000 − 100) / 15
    assert f["iva"] == pytest.approx(0.19 * 900.0)
    assert f["filas"][3]["valor_desecho"] == pytest.approx(900.0 - 180.0 + 100.0)
    con = INT.flujo_caja(1000.0, 0.0, 0.0, 5, 0.10, tasa_renta_modo="fija", otras_utilidades=True)
    sin = INT.flujo_caja(1000.0, 0.0, 0.0, 5, 0.10, tasa_renta_modo="fija", otras_utilidades=False)
    assert con["filas"][1]["impuesto"] == pytest.approx(0.27 * 200.0)               # ahorro tributario de la empresa
    assert sin["filas"][1]["impuesto"] == 0.0 and con["VAN"] > sin["VAN"]


def test_flujo_reusa_van_y_tir_de_economia():
    f = INT.flujo_caja(500.0, 120.0, 10.0, 15, 0.08)
    assert f["VAN"] == pytest.approx(eco.van(f["flujos"], 0.08))
    assert f["TIR"] == pytest.approx(eco.tir(f["flujos"]))
    assert INT.flujo_caja(0.0, 10.0, 0.0, 5, 0.1)["TIR"] is None


def test_opciones_de_economia_vieja_con_valores_por_defecto():
    viejo = dict(precio_gas=3.0, dolar=990.0, inversion=100.0, costo_anual=0.0, anios=20, tasa=0.10, precio_biomasa=6750.0)
    assert INT.opciones_flujo(viejo) == INT.FLUJO_DEF
    r = INT.flujo_desde_economia(viejo, 100.0, 30.0)
    assert r["desde_costeo"] is False and r["internacion"] == 0.0 and r["terreno"] == 0.0
    assert r["VAN_banda"][0] < r["VAN"] < r["VAN_banda"][1]
    E = dict(viejo, inv_auto=False, inv_costeo_m=100.0, internacion_m=4.0, terreno_m=6.0)
    r2 = INT.flujo_desde_economia(E, 100.0, 30.0)
    assert r2["desde_costeo"] and r2["internacion"] == 4.0 and r2["terreno"] == 6.0


# ---------------------------------------------------------------- banda de la clase de estimación
def test_banda_de_estimacion():
    b = INT.banda(1000.0)
    assert b["nombre"] == "Estudio" and (b["error_min"], b["error_max"]) == (0.25, 0.40)
    assert (b["bajo"], b["alto"]) == (pytest.approx(600.0), pytest.approx(1400.0))
    assert INT.banda(1000.0, "detallada")["alto"] == pytest.approx(1100.0)
    assert {k: v[1:] for k, v in INT.CLASES.items()} == dict(orden_magnitud=(0.40, 0.50), estudio=(0.25, 0.40), preliminar=(0.15, 0.25),
                                                            definitiva=(0.10, 0.15), detallada=(0.05, 0.10))


# ---------------------------------------------------------------- integración con el costeo
def test_internacion_apagada_deja_el_costeo_igual(pl, res):
    assert INT.agregar(res, None, pl) is res
    assert INT.agregar(res, dict(activa=False, equipos={"W2": {"pais": "China"}}), pl) is res
    otro = CT.costear(pl)
    assert otro["totales"] == res["totales"]


def test_pais_por_defecto_del_fabricante(pl):
    assert INT.pais_por_defecto(pl.equipos["W2"])[0] == "Italia"                     # Apollo de CFT
    assert INT.pais_por_defecto(pl.equipos["W4"])[0] == "Italia"                     # Venus de CFT
    assert INT.pais_por_defecto(pl.equipos["F2"])[0] == "Chile"                      # la fuente cita a CFT, pero no como fabricante
    assert INT.pais_por_defecto(None)[0] == "Chile"


def test_internacion_encendida_suma_una_vez(pl, res):
    r = INT.agregar(res, dict(activa=True), pl)
    I = r["internacion"]; t = r["totales"]
    assert I["n_importados"] >= 3
    assert t["total_usd"] == pytest.approx(res["totales"]["total_usd"] + I["totales"]["extra"])
    assert t["total_clp"] == pytest.approx(t["total_usd"] * res["dolar"])
    assert t["equipos_usd"] == res["totales"]["equipos_usd"]                         # el precio de los equipos no cambia
    assert res["totales"].get("internacion_usd") is None                              # el resultado original no se toca
    nac = [f for f in I["filas"] if f["pais"] == "Chile"]
    assert all(f["extra"] == 0.0 and f["iva_importacion"] == 0.0 for f in nac)
    ll = INT.resumen_llevar(r, "planta")
    assert ll["extra_m"] == pytest.approx(I["totales"]["extra"] * res["dolar"] / 1e6)


def test_internacion_de_los_recuperadores(pl, res):
    eid = next(f["equipo"] for f in res["filas"] if f["clave"] == "intercambiador")
    r = INT.agregar(res, dict(activa=True, equipos={eid: {"pais": "China"}}), pl)
    assert r["totales"]["recuperacion_usd"] > res["totales"]["recuperacion_usd"]
    assert INT.resumen_llevar(r, "recuperacion")["n_importados"] == 1


@pytest.mark.parametrize("rubro", list(RUBROS))
def test_cuatro_rubros(rubro):
    p = RUBROS[rubro].crear().resolver()
    base = CT.costear(p)
    primero = base["filas"][0]["equipo"]
    r = INT.agregar(base, dict(activa=True, equipos={primero: {"pais": "China"}}), p)
    assert r["internacion"]["n_importados"] >= 1
    assert r["totales"]["total_usd"] > base["totales"]["total_usd"]
    assert INT.agregar(base, dict(activa=False), p) is base


def test_planta_vacia():
    I = INT.internacion([], {}, None)
    assert I["n_importados"] == 0 and I["totales"]["extra"] == 0.0
    vacio = dict(filas=[], totales=dict(total_usd=0.0, recuperacion_usd=0.0), dolar=990.0, avisos=[])
    r = INT.agregar(vacio, dict(activa=True), Planta(nombre="vacía"))
    assert r["totales"]["total_usd"] == 0.0 and r["totales"]["internacion_usd"] == 0.0
    assert INT.resumen_llevar(vacio)["extra_m"] == 0.0


def test_parametros_con_fuente_y_estado():
    for k, p in INT.PARAMETROS.items():
        assert p["fuente"] and p["estado"] in (INT.NORMA, INT.SUP, INT.NOV), k
    assert INT.parametros({"agente": 0.01, "no_existe": 3})["agente"] == 0.01


def test_lectura_de_la_tabla_editada():
    """La tabla editable de la pantalla Costeo guarda solo lo que difiere del valor por defecto."""
    ui = os.path.join(os.path.dirname(__file__), "..", "..", "04 Interfaz Streamlit")
    sys.path.insert(0, os.path.abspath(ui))
    from ui import p_costeo as PC              # con Streamlit o con el sustituto del banco de pruebas
    d = {"E-1": dict(INT.EQUIPO_DEF)}
    fila = PC._fila_editor(dict(equipo="E-1", nombre="x"), dict(INT.EQUIPO_DEF, pais="China", flete_usd=float("nan")))
    assert PC._desde_editor([fila], d) == {"E-1": {"pais": "China"}}
    assert PC._desde_editor([PC._fila_editor(dict(equipo="E-1", nombre="x"), dict(INT.EQUIPO_DEF))], d) == {}
