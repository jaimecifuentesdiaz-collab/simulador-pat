"""Pruebas de PAT 138 (pedido de Jaime del 13-11-2026): 10 tipos de planta de tomate (catalogos/plantas_tomate.py) y 10
distribuciones de la llegada diaria de tomate (motor/demanda.DISTRIBUCIONES, pesos_distribucion, llegada_tomate y
desafio_tomate), y su paso a la planta automática (motor/sintesis.armar_planta con variante)."""
import math, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.catalogos import plantas_tomate as PT
from pat_sim.motor import demanda as DM, sintesis as SI, desafio as D, temporada as TM
from pat_sim.escenarios import agrozzi

N = 76


def _locales_max(w, tol=1e-12):
    return [i for i in range(1, len(w) - 1) if w[i] > w[i - 1] + tol and w[i] >= w[i + 1]]


# ------------------------------------------------------------------ catálogo de plantas de tomate
def test_catalogo_diez_variantes_con_capacidades_distintas():
    assert len(PT.IDS) == 10 and PT.BASE in PT.IDS
    t = PT.tabla()
    totales = [f["temporada_t"] for f in t]
    assert min(totales) == 30000.0 and max(totales) == 900000.0
    assert len({round(f["media_t_h"], 6) for f in t}) == 10                 # capacidades medias distintas
    assert {f["brix"] for f in t} == {28.0, 30.0, 36.0}
    assert {v["quiebre"] for v in PT.VARIANTES.values()} == {"hot", "cold"}
    assert {v["evaporador"] for v in PT.VARIANTES.values()} == set(PT.EVAPORADORES)
    for k, v in PT.VARIANTES.items():
        assert f"{v['temporada_t']:,.0f}".replace(",", ".") + " t por temporada" in v["nombre"]
        f = PT.fuentes(k)
        assert set(f) == {"temporada_t", "dias", "horas_dia", "brix", "quiebre", "evaporador"} and all(f.values())
        if k != PT.BASE:
            assert "Supuesto" in f["temporada_t"]
        assert "MM" not in v["nombre"] + v["descripcion"]


def test_variante_agrozzi_es_identica():
    v = PT.variante("agrozzi")
    assert (v["temporada_t"], v["dias"], v["horas_dia"], v["brix"], v["T_quiebre"], v["tvr"], v["N"]) == (450000.0, 76, 24.0, 30.0, 90.0, True, 3)
    kw = PT.kw_escenario("agrozzi")
    for k, x in kw.items():
        assert agrozzi.BASE[k] == x
    r0 = agrozzi.resumen(agrozzi.crear()); r1 = agrozzi.resumen(PT.crear_escenario("agrozzi"))
    for k in ("Qhb", "cascada", "pinch"):
        assert r1[k] == pytest.approx(r0[k], abs=1e-9)
    assert round(r1["Qhb"], 1) == 15956.0 and round(r1["cascada"], 1) == 9073.8 and round(r1["pinch"], 1) == 9722.9
    assert PT.variante(None)["id"] == "agrozzi"
    with pytest.raises(KeyError):
        PT.variante("no_existe")


@pytest.mark.parametrize("vid", PT.IDS)
def test_escenario_de_cada_variante(vid):
    v = PT.variante(vid)
    pl = PT.crear_escenario(vid, capacidades=False)
    assert pl.resuelta and not pl.avisos
    assert pl.equipos["B1"].v("temporada_t") == v["temporada_t"] and pl.equipos["B1"].horas() == v["dias"] * v["horas_dia"]
    assert pl.propiedad_entrada("A1", "x") == pytest.approx(v["brix"] / 100, abs=1e-8)
    assert pl.equipos["W1"].v("T_salida") == v["T_quiebre"] and pl.equipos["W4"].v("N") == v["N"] and pl.equipos["W4"].v("tvr") == v["tvr"]
    if v["quiebre"] == "cold":
        assert "Cold break" in pl.equipos["W1"].nombre


def test_mas_tomate_mas_calor_de_quiebre():
    q = {k: agrozzi.resumen(PT.crear_escenario(k, capacidades=False))["Qhb"] for k in ("pequena_28", "mediana_30", "agrozzi")}
    assert q["pequena_28"] < q["mediana_30"] < q["agrozzi"]


# ------------------------------------------------------------------ 10 distribuciones
def test_diez_distribuciones_con_parametros_y_fuentes():
    assert len(DM.IDS_DISTRIBUCIONES) == 10
    assert set(DM.IDS_DISTRIBUCIONES) == {"normal", "lognormal", "beta", "media_normal", "uniforme", "normal_truncada", "triangular",
                                          "weibull", "gamma", "bimodal"}
    for k, d in DM.DISTRIBUCIONES.items():
        assert d["nombre"] and d["explicacion"] and d["forma"] and d["parametros"]
        for q in d["parametros"].values():
            assert q["fuente"] and q["significado"] and q["nombre"]


@pytest.mark.parametrize("dist", DM.IDS_DISTRIBUCIONES)
@pytest.mark.parametrize("n", [1, 7, 60, 76, 95])
def test_pesos_suman_uno_y_no_negativos(dist, n):
    w = DM.pesos_distribucion(n, dist)
    assert len(w) == n and sum(w) == pytest.approx(1.0, abs=1e-12) and min(w) >= 0


def test_formas_esperadas():
    w = {d: DM.pesos_distribucion(N, d) for d in DM.IDS_DISTRIBUCIONES}
    arg = {d: max(range(N), key=lambda i: w[d][i]) for d in w}
    assert max(w["uniforme"]) == pytest.approx(min(w["uniforme"]), abs=1e-15)                     # plana
    assert all(a > b for a, b in zip(w["media_normal"], w["media_normal"][1:]))                    # decreciente
    assert len(_locales_max(w["bimodal"])) == 2                                                     # dos peaks
    a, b = _locales_max(w["bimodal"])
    assert min(w["bimodal"][a:b + 1]) < 0.8 * min(w["bimodal"][a], w["bimodal"][b])                 # valle entre ambas cosechas
    for d in ("normal", "normal_truncada"):                                                         # simétricas al centro
        assert all(x == pytest.approx(y, rel=1e-9) for x, y in zip(w[d], reversed(w[d])))
        assert arg[d] in (N // 2 - 1, N // 2)
    assert w["normal"][0] < 0.1 * w["normal_truncada"][0]                                           # la truncada se corta, la normal cabe
    assert w["normal_truncada"] == pytest.approx(DM._pesos_curva(N, "normal", 0.5, 0.25), rel=1e-12)   # la curva de Agrozzi
    for d in ("lognormal", "gamma", "triangular"):                                                  # peak antes de la mitad
        assert arg[d] < N / 2
    for d in ("beta", "weibull"):                                                                   # peak después de la mitad
        assert arg[d] > N / 2
    for d in ("lognormal", "gamma"):                                                                # asimetría positiva: media después del peak
        media = sum(i * x for i, x in enumerate(w[d]))
        assert media > arg[d]
    for d in ("beta", "weibull"):                                                                   # asimetría negativa
        media = sum(i * x for i, x in enumerate(w[d]))
        assert media < arg[d]
    assert abs(arg["triangular"] - 0.35 * N) <= 1                                                  # moda de la triangular
    tri = w["triangular"]; dif = [tri[i + 1] - tri[i] for i in range(arg["triangular"] - 1)]       # tramo recto
    assert max(dif) == pytest.approx(min(dif), rel=1e-9)
    for d in DM.IDS_DISTRIBUCIONES:                                                                 # una sola moda salvo uniforme y bimodal
        if d not in ("uniforme", "bimodal", "media_normal"):
            assert len(_locales_max(w[d])) == 1, d


def test_parametros_cambiados_y_errores():
    w = DM.pesos_distribucion(N, "normal", dict(media=0.3))
    assert max(range(N), key=lambda i: w[i]) < N / 2
    with pytest.raises(ValueError):
        DM.pesos_distribucion(N, "no_existe")
    with pytest.raises(ValueError):
        DM.parametros_distribucion("normal", dict(otro=1))
    with pytest.raises(ValueError):
        DM.pesos_distribucion(N, "uniforme", dict(inicio=2.0, fin=3.0))     # sin llegada en la temporada
    assert DM.pesos_distribucion(0, "normal") == []


# ------------------------------------------------------------------ serie de llegada de cada combinación
@pytest.mark.parametrize("vid", PT.IDS)
@pytest.mark.parametrize("dist", DM.IDS_DISTRIBUCIONES)
def test_llegada_suma_el_total_y_cierra_el_balance(vid, dist):
    v = PT.variante(vid)
    r = DM.llegada_tomate(vid, dist, perdida_1pct=False)
    assert r["perfil"] == DM.PERFIL_TOMATE and r["logica"] == "agricola" and r["periodo"] == "día"
    assert len(r["serie"]) == v["dias"] == len(r["serie_t_h"]) == len(r["etiquetas"])
    assert sum(r["serie"]) == pytest.approx(v["temporada_t"], rel=1e-12)
    assert all(x >= 0 for x in r["serie"])
    assert r["serie_t_h"] == pytest.approx([x / v["horas_dia"] for x in r["serie"]])
    b = r["extra"]["balance"]
    assert b["cosechado"] == pytest.approx(b["procesado"] + b["perdido"], rel=1e-12) and b["cosechado"] == pytest.approx(v["temporada_t"])


def test_llegada_sin_ruido_sigue_la_forma_y_con_capacidad_pierde():
    r = DM.llegada_tomate("mediana_30", "uniforme", cv=0.0, perdida_1pct=False)
    assert max(r["serie"]) == pytest.approx(min(r["serie"])) and r["serie"][0] == pytest.approx(200000.0 / 70)
    a = DM.llegada_tomate("mediana_30", "normal", semilla=5); b = DM.llegada_tomate("mediana_30", "normal", semilla=5)
    assert a["serie"] == b["serie"]                                                              # determinista con la semilla
    c = DM.llegada_tomate("mediana_30", "normal", semilla=6)
    assert c["serie"] != a["serie"] and sum(c["serie"]) == pytest.approx(sum(a["serie"]))
    cap = PT.capacidad_media_t_h("mediana_30")
    p = DM.llegada_tomate("mediana_30", "normal", capacidad_t_h=cap, perdida_1pct=False)["extra"]["balance"]
    assert p["perdido"] > 0 and p["cosechado"] == pytest.approx(p["procesado"] + p["perdido"], rel=1e-9)
    assert a["extra"]["capacidad"]["para_perdida_1pct_t_h"] <= a["extra"]["capacidad"]["pico_t_h"] + 1e-9
    m = DM.resumen_llegada(a)
    assert m["total_t"] == pytest.approx(200000.0) and m["pico_t_h"] >= m["p95_t_h"] >= m["media_t_h"] and m["dias"] == 70


def test_normal_truncada_sin_ruido_es_la_curva_de_temporada():
    r = DM.llegada_tomate("agrozzi", "normal_truncada", cv=0.0, perdida_1pct=False)
    curva = TM.curva_llegada(agrozzi.crear())
    assert r["serie"] == pytest.approx(curva, rel=1e-12)


def test_desafio_tomate_en_la_sesion():
    r = DM.llegada_tomate("pequena_28", "bimodal")
    d = DM.desafio_tomate(r, "Ana Pérez")
    assert d["tipo_planta"] == "tomate" and d["variante_tomate"] == "pequena_28" and d["distribucion_tomate"] == "bimodal"
    assert d["rubro"] == "tomate" and d["logica"] == "agricola" and d["perfil_demanda"] == DM.PERFIL_TOMATE
    assert d["demanda"] == pytest.approx(r["serie"]) and d["demanda_t_h"] == pytest.approx(r["serie_t_h"])    # 20 h por día, no 24
    assert d["demanda_t_h"][0] == pytest.approx(d["demanda"][0] / 20.0)
    assert "don" not in d["enunciado"].split() and "MM" not in d["titulo"]
    assert not D.validar(DM.a_desafio(r, "serie", rubro="tomate"))


# ------------------------------------------------------------------ planta automática con la variante
def test_armar_planta_con_variante_y_distribucion():
    r = DM.llegada_tomate("grande_36cb", "beta", perdida_1pct=False)
    pl = SI.armar_planta("tomate", r)
    inf = SI.informe(pl)
    assert SI.variante_de(pl) == "grande_36cb" and inf["variante_tomate"] == "grande_36cb" and inf["distribucion_tomate"] == "beta"
    assert "650.000 t" in pl.nombre and inf["nombre"] == PT.variante("grande_36cb")["nombre"]
    ali = next(e for e in pl.equipos.values() if e.tipo == "alimentacion_tomate")
    assert ali.v("dias") == 85 and ali.v("temporada_t") == pytest.approx(650000.0, rel=1e-9)        # operación = media de la serie
    d = inf["dimensionamiento"]
    assert d["materia_prima_diseno_t_h"] == pytest.approx(1.10 * DM.percentil(r["serie_t_h"], 95))
    assert pl.propiedad_entrada(next(e.id for e in pl.equipos.values() if e.tipo == "llenadora_aseptica"), "x") == pytest.approx(0.36, abs=0.01)
    assert any("Cold break" in e.nombre for e in pl.equipos.values())


def test_armar_planta_desde_el_desafio_y_carta_en_blanco():
    r = DM.llegada_tomate("pequena_36cb", "weibull")
    des = DM.desafio_tomate(r)
    pl = SI.armar_planta("tomate", des, desafio=des)
    assert SI.variante_de(pl) == "pequena_36cb" and SI.informe(pl)["demanda"]["logica"] == "agricola"
    assert SI.informe(pl)["dimensionamiento"]["materia_prima_diseno_t_h"] == pytest.approx(1.10 * DM.percentil(r["serie_t_h"], 95))
    b = SI.planta_en_blanco("tomate", des, des)
    assert SI.es_carta_en_blanco(b) and SI.variante_de(b) == "pequena_36cb" and b._p["distribucion_tomate"] == "weibull"
    assert b._p["demanda_perfil"] == DM.PERFIL_TOMATE and "60.000 t" in b.nombre
    v = SI.armar_planta("tomate", variante="mediana_28")                                   # sin demanda: normal truncada
    assert SI.informe(v)["distribucion_tomate"] == DM.DISTRIBUCION_DEFECTO


def test_sin_variante_sigue_igual():
    pl = SI.armar_planta("tomate")
    assert SI.variante_de(pl) is None and SI.informe(pl)["nombre"] == "Pasta de tomate"
    assert SI.planta_en_blanco("agar")._p.get("variante_tomate") is None
    assert SI._variante("agar", DM.llegada_tomate("agrozzi", "normal"), None) == (None, None)


def test_cien_combinaciones_dan_capacidades_distintas():
    caps = set()
    for vid in PT.IDS:
        for dist in DM.IDS_DISTRIBUCIONES:
            r = DM.llegada_tomate(vid, dist, perdida_1pct=False)
            dim = SI.dimensionar(SI.leer_demanda(r), PT.variante(vid)["dias"] * PT.variante(vid)["horas_dia"])
            caps.add(round(dim["diseno_t_h"], 6))
            assert dim["de"] == "materia prima" and math.isfinite(dim["diseno_t_h"])
    assert len(caps) == 100
