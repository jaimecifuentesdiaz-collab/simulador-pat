"""PAT 135, T14: selección de equipos comerciales, disponibilidad k de n, línea en serie, redundancia, aplicar y costeo."""
import math
import pytest
from pat_sim.datos.bd import BaseDatos
from pat_sim.datos import mantenedor as M
from pat_sim.motor import seleccion as S, costeo as CO, linea_fluida as LF, desafio as D
from pat_sim.escenarios import agrozzi, pellet, chip, lena

CAT = M.semilla_catalogo_comercial()
ESC = dict(tomate=agrozzi, pellet=pellet, chip=chip, lena=lena)


def test_disponibilidad_y_k_de_n_valores_conocidos():
    assert S.disponibilidad(90, 10) == pytest.approx(0.9)
    assert S.k_de_n(0.9, 1, 1) == pytest.approx(0.9)
    assert S.k_de_n(0.9, 2, 1) == pytest.approx(0.99)            # 1 − 0,1²
    assert S.k_de_n(0.9, 2, 2) == pytest.approx(0.81)
    assert S.k_de_n(0.9, 3, 2) == pytest.approx(0.972)           # 0,9³ + 3·0,9²·0,1
    assert S.k_de_n(0.9, 3, 4) == 0.0 and S.k_de_n(0.5, 3, 0) == 1.0
    assert sum(S.prob_disponibles(5, 0.7)) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        S.disponibilidad(0, 1)


def test_serie_y_capacidades_esperadas():
    assert S.serie([0.9, 0.95, 0.99]) == pytest.approx(0.9 * 0.95 * 0.99)
    assert S.capacidad_esperada(10, 3, 0.9) == pytest.approx(27.0)
    # dos unidades de 10 t/h con D = 15: P(2) = 0,81 → 15; P(1) = 0,18 → 10; P(0) → 0
    assert S.capacidad_util(10, 2, 0.9, 15) == pytest.approx(0.81 * 15 + 0.18 * 10)
    assert S.capacidad_ociosa(10, 2, 0.9, 15) == pytest.approx(0.81 * 5)
    assert S.capacidad_ociosa(10, 3, 0.9, 15, k=2) == pytest.approx(S.k_de_n(0.9, 3, 2) * 5)   # la reserva no opera
    assert S.crf(0.0, 10) == pytest.approx(0.1)
    assert S.crf(0.10, 20) == pytest.approx(0.1 * 1.1 ** 20 / (1.1 ** 20 - 1))


def test_catalogo_semilla_con_fuentes_y_unidades_de_costeo():
    tipos = {f["tipo"] for f in CAT}
    for t in ("evaporador_mvr", "evaporador_multiefecto", "esterilizador", "pelletizadora", "secador_biomasa", "secador_banda", "generico"):
        assert t in tipos and 3 <= sum(1 for f in CAT if f["tipo"] == t) <= 9
    for f in CAT:
        assert f["capacidad"] > 0 and f["mtbf_h"] > 0 and f["mttr_h"] >= 0
        assert "Supuesto" in f["fuente_capacidad"] and "Supuesto" in f["fuente_confiabilidad"] and "Supuesto" in f["fuente_precio"]
        if f["tipo"] != "generico":
            assert f["unidad"] == CO._LINEA[f["tipo"]][4]


def test_catalogo_en_la_base_idempotente_y_editable(tmp_path):
    m = M.Mantenedor(BaseDatos(tmp_path / "c.db"))
    assert m.sembrar_comercial()["catalogo_comercial"] == len(CAT)
    assert m.sembrar_comercial()["catalogo_comercial"] == 0
    f = dict(m.listar_comercial("pelletizadora")[0]); f["precio_usd"] = 12345.0
    m.guardar_comercial(f); m.sembrar_comercial()
    assert m.listar_comercial("pelletizadora")[0]["precio_usd"] == pytest.approx(12345.0)
    with pytest.raises(ValueError):
        m.guardar_comercial(dict(f, fuente_capacidad=""))
    m.eliminar_comercial(f["tipo"], f["modelo"])
    assert len(M.catalogo_comercial(m, "pelletizadora")) == sum(1 for x in CAT if x["tipo"] == "pelletizadora") - 1


def test_paralelo_suma_al_menos_la_capacidad():
    pl = pellet.crear(); r = S.seleccionar(pl, CAT)
    a1 = next(e for e in r["etapas"] if e["equipo"] == "A1")      # pelletizadora de 5,15 t/h, modelos de 0,5 a 3 t/h
    for a in a1["alternativas"]:
        assert a["k"] * a["capacidad_modelo"] >= a1["requerida"] - 1e-9
        assert (a["k"] - 1) * a["capacidad_modelo"] < a1["requerida"]
        assert a["n"] in (a["k"], a["k"] + 1)
    assert any(a["k"] > 1 for a in a1["alternativas"])


def test_recomendacion_de_redundancia():
    base = dict(ineficiencia_clp=100.0, anual_clp=10.0, modelo="X", n=2, A_etapa=0.8)
    assert S.decidir_redundancia(base, dict(base, ineficiencia_clp=40.0, anual_clp=30.0, n=3, A_etapa=0.97))["recomendar"]
    assert not S.decidir_redundancia(base, dict(base, ineficiencia_clp=90.0, anual_clp=30.0, n=3, A_etapa=0.97))["recomendar"]
    pl = agrozzi.crear(); r = S.seleccionar(pl, CAT)
    for e in r["etapas"]:
        d = e["redundancia"]
        assert d["recomendar"] == (d["ahorro_clp"] > d["costo_clp"])
        assert e["recomendada"]["redundante"] == d["recomendar"]


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_seleccion_en_cada_rubro_y_cuello(rubro):
    pl = ESC[rubro].crear(); r = S.seleccionar(pl, CAT)
    assert r["etapas"] and all(e["recomendada"] for e in r["etapas"])
    L = S.analizar_linea([e["recomendada"] for e in r["etapas"]], r["parametros"]["plan"])
    assert L["cuello"] in {e["equipo"] for e in r["etapas"]}
    assert 0 < L["A_linea"] <= 1
    assert L["A_linea"] == pytest.approx(S.serie(e["recomendada"]["A_etapa"] for e in r["etapas"]))


def test_planta_vacia_sin_etapas():
    pl = D.planta_vacia(dict(titulo="V", enunciado="diseñar", producto="X", rubro="pellet",
                             demanda=dict(periodo="mes", unidad="t", valores=[1], fuente="Supuesto"), precios=[]))
    r = S.seleccionar(pl, CAT)
    assert r["etapas"] == [] and S.analizar_linea([])["cuello"] is None


def test_aplicar_a_la_planta_no_cambia_el_balance_y_la_linea_usa_lo_elegido():
    pl = agrozzi.crear()
    Q_hb = pl.equipos["W1"].resultado.detalle["Q_kW"]
    vapor = pl.servicio_total("vapor_kW")
    r = S.seleccionar(pl, CAT)
    e = next(x for x in r["etapas"] if x["equipo"] == "Z1")
    a = next(x for x in e["alternativas"] if x["n"] == 6 and x["k"] == 5)
    assert S.aplicar(pl, {"Z1": a}) == 1
    eq = pl.equipos["Z1"]
    assert eq.v("unidades") == 6 and eq.v("unidades_requeridas") == 5 and eq.v("modelo") == a["modelo"]
    assert eq.v("capacidad") == pytest.approx(a["instalada_t_h"])
    pl.resolver()
    assert pl.equipos["W1"].resultado.detalle["Q_kW"] == pytest.approx(Q_hb)          # R9: el balance no cambia
    assert pl.servicio_total("vapor_kW") == pytest.approx(vapor)
    f = LF.fallas_defecto(eq)
    assert f["origen"] == "Selección de equipos"
    mtbf, mttr, _n = S.fallas_equivalentes(eq)
    assert mttr == pytest.approx(a["mttr_h"])
    A_eq = mtbf / (mtbf + mttr)
    assert A_eq == pytest.approx(a["cap_util_t_h"] / min(a["instalada_t_h"], e["carga_t_h"]))
    # un solo equipo: la Línea usa el MTBF y el MTTR del modelo
    e2 = next(x for x in r["etapas"] if x["equipo"] == "W2"); b = e2["mejor"]
    S.aplicar(pl, {"W2": b}); mt, mr, _n = S.fallas_equivalentes(pl.equipos["W2"])
    assert (mt, mr) == (pytest.approx(b["mtbf_h"]), pytest.approx(b["mttr_h"]))
    assert S.elegida_actual(dict(e2, actual=S.seleccion_actual(pl.equipos["W2"])))["n"] == b["n"]
    assert S.quitar(pl) == 2 and LF.fallas_defecto(pl.equipos["Z1"])["origen"] == "Supuesto"


def test_sin_seleccion_la_linea_y_el_costeo_quedan_iguales():
    pl = pellet.crear()
    assert LF.fallas_defecto(pl.equipos["A1"])["origen"] == "Supuesto"
    assert all(it.get("unidades") is None for it in CO.lista_equipos(pl, X={}))


def test_costeo_cuenta_unidades_y_redundancia():
    pl = pellet.crear(); r = S.seleccionar(pl, CAT)
    e = next(x for x in r["etapas"] if x["equipo"] == "A1")
    a = next(x for x in e["alternativas"] if x["redundante"])
    c0 = next(f for f in CO.costear(pl, X={})["filas"] if f["equipo"] == "A1")
    S.aplicar(pl, {"A1": a})
    it = next(i for i in CO.lista_equipos(pl, X={}) if i["equipo"] == "A1")
    assert it["unidades"] == a["n"] and it["tamano"] == pytest.approx(a["capacidad_modelo"])
    c1 = next(f for f in CO.costear(pl, X={})["filas"] if f["equipo"] == "A1")
    unit = CO.williams(c0["precio_ref_usd"], c0["tamano_ref"], a["capacidad_modelo"], 0.6)
    assert c1["costo_usd"] == pytest.approx(a["n"] * unit * c1["factor_cepci"])
    assert c1["unidades"] == a["n"]


def test_costeo_con_cables_del_layout():
    pl = lena.crear()
    sin = CO.costear(pl, X={})["totales"]["equipos_usd"]
    res = CO.costear(pl, X={}, cables_m={"MCC-1 a A1": 40.0, "MCC-1 a T1": 60.0, "malo": "x"})
    cab = next(f for f in res["filas"] if f["equipo"] == "CAB")
    assert cab["cantidad"] == pytest.approx(100.0) and "Supuesto" in cab["fuente"]
    assert cab["costo_usd"] == pytest.approx(100.0 * CO.REFERENCIAS["cable_electrico"]["C"] * cab["factor_cepci"])
    assert res["totales"]["equipos_usd"] == pytest.approx(sin + cab["costo_usd"])


def test_margen_del_desafio_y_de_economia():
    assert S.margen("tomate", dict(margen=123.0))[0] == 123.0
    m, f = S.margen("tomate", dict(dolar=1000.0), dict(precios=[dict(producto="P", precio=100.0, moneda="US$", unidad="t", fuente="Supuesto")]))
    assert m == pytest.approx(100000.0) and "desafío" in f
    assert S.margen("pellet")[0] == pytest.approx(60000.0)


def test_gancho_tavily_sin_clave_y_con_respuesta_simulada():
    assert S.tamanos_web("pelletizadora", None) == []
    import io, json
    class R(io.BytesIO):
        def __enter__(s): return s
        def __exit__(s, *a): return False
    datos = dict(results=[dict(title="Ring die pellet mill 2 t/h", url="https://ejemplo.cl/p", content="Model X, 2 t/h, price US$ 45,000")])
    out = S.tamanos_web("pelletizadora", "clave", _abrir=lambda req, timeout=0: R(json.dumps(datos).encode()))
    assert len(out) == 1 and out[0]["capacidad"] == pytest.approx(2.0) and out[0]["precio_usd"] == pytest.approx(45000.0)
    assert out[0]["categoria"] == "Internet" and out[0]["url"]
