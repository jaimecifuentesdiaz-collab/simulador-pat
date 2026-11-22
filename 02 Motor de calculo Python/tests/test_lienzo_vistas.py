"""PAT 138: el mismo lienzo en las tres pantallas de construcción (vistas «ficticia», «real» y «auxiliares» de datos_lienzo)."""
import json
import pytest
from pat_sim.motor import lienzo as LZ, seleccion as S, auxiliares as AX, sintesis as SI
from pat_sim.escenarios import agrozzi

CAT = {"todos": dict(nombre="Todos", equipos=[])}


def _tomate():
    pl = SI.armar_planta("tomate")
    sel = S.seleccionar(pl)
    S.aplicar(pl, {e["equipo"]: e["recomendada"] for e in sel["etapas"] if e["recomendada"]})
    return pl


def test_vista_ficticia_no_cambia_lo_de_antes():
    pl = agrozzi.crear(); pl.resolver()
    d = LZ.datos_lienzo(pl, pl, None, CAT)
    assert d["vista"] == "ficticia" and d["solo_lectura"] is False and "real" not in d and "auxiliares" not in d


def test_vista_real_con_seleccion_unidades_y_disponibilidad():
    pl = _tomate()
    r = LZ.capa_real(pl)
    con = [v for v in r["equipos"].values() if v["seleccion"]]
    assert con and r["aviso"] is None and r["con_seleccion"] == len(con)
    for v in con:
        assert v["modelo"] and v["n"] >= v["k"] >= 1
        assert v["capacidad_instalada"] == pytest.approx(v["capacidad_unidad"] * v["n"])
        assert v["A_etapa"] == pytest.approx(S.k_de_n(S.disponibilidad(v["mtbf_h"], v["mttr_h"]), v["n"], v["k"]))
    assert r["A_linea"] == pytest.approx(S.serie(v["A_etapa"] for v in con))


def test_vista_real_sin_seleccion_avisa():
    pl = _tomate(); S.quitar(pl)
    r = LZ.datos_lienzo(pl, pl, None, CAT, vista="real")["real"]
    assert r["con_seleccion"] == 0 and r["seleccionables"] > 0 and "Sin selección" in r["aviso"]


def test_vista_auxiliares_sobre_las_lineas():
    pl = _tomate(); a = AX.auxiliares(pl)
    d = LZ.datos_lienzo(pl, pl, None, CAT, vista="auxiliares", aux=a)
    x = d["auxiliares"]; claves = {c["clave"] for c in d["conexiones"]}
    assert len(x["bombas"]) == len(a["bombas"]["filas"]) > 0
    assert all(b["con"] in claves for b in x["bombas"] if not b["en_diagrama"])
    assert len(x["estanques"]) == len(a["estanques"]["filas"]) > 0 and all(e["con"] in claves for e in x["estanques"])
    assert x["n_bloqueo"] == a["valvulas"]["n_bloqueo"] and x["totales"]["bombeo_kW"] == pytest.approx(a["bombas"]["total_kw"])
    assert d["kpis"]["aux_total_clp"] == pytest.approx(a["total_clp"]) and d["solo_lectura"] and "real" in d
    json.dumps(d)


def test_vista_auxiliares_sin_resultado_y_vista_desconocida():
    pl = _tomate()
    assert LZ.capa_auxiliares(pl, None)["bombas"] == []
    with pytest.raises(ValueError):
        LZ.datos_lienzo(pl, pl, None, CAT, vista="otra")


def test_las_cifras_de_agrozzi_no_cambian_con_las_vistas():
    pl = agrozzi.crear(); pl.resolver()
    antes = pl.servicio_total("vapor_kW")
    for v in LZ.VISTAS:
        LZ.datos_lienzo(pl, pl, None, CAT, vista=v, aux=AX.auxiliares(pl) if v == "auxiliares" else None)
    assert pl.servicio_total("vapor_kW") == pytest.approx(antes)
