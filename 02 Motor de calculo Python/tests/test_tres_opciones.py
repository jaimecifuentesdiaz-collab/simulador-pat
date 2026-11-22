"""PAT 140 c (pedido de Jaime, 16-11-2026): cada etapa de la Planta real (y cada equipo auxiliar) muestra 3 opciones de instalación de
distinto número de unidades n, con su ficha comparativa en 3 columnas (motor/tres_opciones.py)."""
import math
import pytest
from pat_sim.motor import (tres_opciones as T, seleccion as S, costo_total as CT, lienzo as LZ, eleccion_viva as EV,
                           eleccion_auxiliares as EA, auxiliares as AX)
from pat_sim.escenarios import agrozzi, pellet, chip, lena


def _resuelta(mod):
    pl = mod.crear()
    if not pl.resuelta:
        pl.resolver()
    return pl


# ---------------------------------------------------------------- elegir_tres (función pura)
def test_elegir_tres_toma_la_de_menor_c_de_cada_n_y_las_tres_de_menor_c():
    cs = [dict(id="a", n=1, C=50.0), dict(id="b", n=1, C=40.0), dict(id="c", n=2, C=10.0), dict(id="d", n=3, C=30.0),
          dict(id="e", n=4, C=20.0), dict(id="f", n=2, C=5.0), dict(id="g", n=5, C=None)]
    tres = T.elegir_tres(cs)
    assert [c["id"] for c in tres] == ["f", "d", "e"]                    # n = 2, 3 y 4, ordenadas por n
    assert len({c["n"] for c in tres}) == 3


def test_elegir_tres_con_pocos_candidatos_y_lista_vacia():
    assert T.elegir_tres([]) == [] and T.elegir_tres(None) == []
    assert [c["id"] for c in T.elegir_tres([dict(id="x", n=2, C=1.0), dict(id="y", n=2, C=0.5)])] == ["y"]


# ---------------------------------------------------------------- 3 opciones en cada etapa de los cuatro rubros
@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_cada_etapa_tiene_tres_opciones_de_distinto_n(mod):
    pl = _resuelta(mod)
    reqs = S.requerimientos(pl)
    assert reqs
    for r in reqs:
        res = T.candidatos_tres(pl, r["equipo"], None, False)
        tres = res["tres"]
        assert len(tres) == 3 and len({c["n"] for c in tres}) == 3, (r["equipo"], [(c["n"], c["C"]) for c in tres])
        assert [c["n"] for c in tres] == sorted(c["n"] for c in tres)
        ids = {c["id"] for c in res["candidatos"]}
        assert all(c["id"] in ids for c in tres)                          # las 3 están en la lista completa (aplicables)
        assert len(ids) == len(res["candidatos"])                         # sin repetidos
        # para cada n mostrado, ninguna otra opción con ese n tiene menor C
        for c in tres:
            assert all(o["C"] >= c["C"] - 1e-9 for o in res["candidatos"] if o["n"] == c["n"])
        # la de menor C de toda la etapa está entre las 3 («Generar automáticamente» sigue eligiendo una de ellas)
        assert res["candidatos"][0]["id"] in {c["id"] for c in tres}


def test_divisiones_usan_equipo_real_cercano_o_williams_estimado():
    pl = _resuelta(agrozzi)
    req = next(r for r in S.requerimientos(pl) if r["equipo"] == "F1")
    P = S.parametros(pl, None)
    gen, _av = T.opciones_division(req, [], P)
    assert [g["division"] for g in gen] == [1, 2, 3]
    for g in gen:
        assert g["n"] == g["k"] == g["division"] and g["origen"] == "Williams" and g["estimada"]
        assert math.isclose(g["capacidad"], req["requerida"] / g["k"], rel_tol=1e-9)
        assert g["C"] > 0 and 0 < g["A"] <= 1 and g["id"].startswith("F1|")
    # con un equipo real a +10 % de requerida / 2, la división en 2 usa ese equipo (no Williams)
    real = dict(tipo=req["tipo_catalogo"], modelo="Real de prueba", fabricante="Fabricante X", capacidad=req["requerida"] / 2 * 1.1,
                unidad=req["unidad"], precio_usd=100000.0, anio_precio=2026, fuente_precio="Precio de prueba", origen="Respaldo",
                mtbf_h=None, mttr_h=None, url="https://ejemplo.cl/real")
    gen, _av = T.opciones_division(req, [real], P)
    g2 = next(g for g in gen if g["division"] == 2)
    assert g2["modelo"] == "Real de prueba" and g2["origen"] == "Respaldo" and not g2["estimada"] and g2["url"] == "https://ejemplo.cl/real"
    # uno a +30 % ya no calza: queda Williams
    gen, _av = T.opciones_division(req, [dict(real, capacidad=req["requerida"] / 2 * 1.3)], P)
    assert next(g for g in gen if g["division"] == 2)["origen"] == "Williams"


def test_una_division_se_aplica_y_se_deshace_como_cualquier_candidato():
    pl = _resuelta(agrozzi); h = LZ.Historial(30)
    res = T.candidatos_tres(pl, "F1", None, False)
    c = next(x for x in res["tres"] if x["n"] == 3)
    r = EV.aplicar_candidato(pl, h, c)
    assert r["ok"] and r["cambio"]
    act = S.seleccion_actual(pl.equipos["F1"])
    assert act["n"] == 3 and act["modelo"] == c["modelo"]
    assert EV.deshacer(pl, h)["ok"]; pl.resolver()
    assert S.seleccion_actual(pl.equipos["F1"]) is None


def test_planta_vacia_o_etapa_inexistente_no_falla():
    from pat_sim.motor.planta import Planta
    pl = Planta("vacía", "tomate")
    res = T.candidatos_tres(pl, "F1", None, False)
    assert res["candidatos"] == [] and res["tres"] == [] and res["avisos"]
    pl = _resuelta(agrozzi)
    assert T.candidatos_tres(pl, "NO_EXISTE", None, False)["tres"] == []
    assert T.ficha_etapa(pl, "F1", []) is None and T.resultados_etapa(pl, "NO_EXISTE") is None


# ---------------------------------------------------------------- ficha comparativa
def _ficha(pl, eid="F1"):
    res = T.candidatos_tres(pl, eid, None, False)
    return res, T.ficha_etapa(pl, eid, res["tres"])


def test_ficha_tiene_tres_columnas_alineadas_y_todas_las_secciones():
    pl = _resuelta(agrozzi)
    res, f = _ficha(pl)
    assert len(f["opciones"]) == 3 and [o["id"] for o in f["opciones"]] == [c["id"] for c in res["tres"]]
    assert [s["titulo"] for s in f["secciones"]] == ["Resultados del equipo", "Selección comercial", "Eficiencia en operación", "Costo total"]
    etqs = {x["etq"] for s in f["secciones"] for x in s["filas"]}
    for e in ["Carga demandada", "Carga procesada", "Salida de proceso", "Capacidad efectiva", "Utilización", "Cierre de energía",
              "Modelo y fabricante", "Unidades en paralelo (n)", "Necesarias (k)", "Capacidad por unidad", "Capacidad instalada",
              "MTBF de una unidad", "MTTR de una unidad", "Disponibilidad de una unidad", "Disponibilidad de la etapa (k de n)",
              "Carga por unidad en operación", "Eficiencia relativa η/η_max", "Punto de diseño por unidad",
              "C_inv (inversión anualizada)", "C_op (energía y mantenimiento)", "C_inef (producción perdida)", "C = C_inv + C_op + C_inef"]:
        assert e in etqs, e
    for s in f["secciones"]:
        for x in s["filas"]:
            assert len(x["valores"]) == 3 and len(x["conveniente"]) == 3
    assert f["base"].startswith("Base de cálculo") and "CRF" in f["base"]
    assert "MM" not in str(f) and "★" not in str(f) and " don " not in str(f)


def test_ficha_costo_total_tiene_info_con_las_cifras_vigentes():
    """PAT 140 e: cada ecuación de «Costo total» lleva su texto del ⓘ (para qué y por qué), con las cifras del detalle del costo."""
    pl = _resuelta(agrozzi)
    res, f = _ficha(pl)
    filas = {x["etq"]: x for s in f["secciones"] if s["titulo"] == "Costo total" for x in s["filas"]}
    d = res["tres"][0]["detalle_costo"]
    ets = ["Inversión instalada (n × precio × factor)", "C_inv (inversión anualizada)", "C_op (energía y mantenimiento)",
           "C_inef (producción perdida)", "C = C_inv + C_op + C_inef"]
    for e in ets:
        t = filas[e]["info"]
        assert "Para qué" in t and "Fuente" in t and "MM" not in t and " don " not in t and "—" not in t
    assert f"{d['f_inst']:.2f}".replace(".", ",") in filas[ets[0]]["info"] and "motor/costos.py" in filas[ets[0]]["info"]
    assert f"{d['crf']:.4f}".replace(".", ",") in filas[ets[1]]["info"] and "(1+i)^N" in filas[ets[1]]["info"]
    assert f"{d['mantencion_pct']:.1f}".replace(".", ",") + " %" in filas[ets[2]]["info"]
    assert f"{d['dolar']:.2f}".replace(".", ",") in filas[ets[2]]["info"]
    assert "t_MP" in filas[ets[3]]["info"] and "reserva" in filas[ets[3]]["info"]
    assert filas["Precio de una unidad"]["info"] == ""


def test_ficha_marca_el_valor_mas_conveniente_de_cada_fila():
    pl = _resuelta(agrozzi)
    res, f = _ficha(pl)
    filas = {x["etq"]: x for s in f["secciones"] for x in s["filas"]}
    c = filas["C = C_inv + C_op + C_inef"]
    i = min(range(3), key=lambda j: res["tres"][j]["C"])
    assert c["conveniente"][i] and sum(c["conveniente"]) == 1
    a = filas["Disponibilidad de la etapa (k de n)"]
    j = max(range(3), key=lambda j: res["tres"][j]["A"])
    assert a["conveniente"][j]
    assert not any(filas["Carga demandada"]["conveniente"])               # igual en las 3: sin marca


def test_ficha_dice_sin_dato_y_supuesto_cuando_falta_mtbf():
    pl = _resuelta(agrozzi)
    _res, f = _ficha(pl)
    filas = {x["etq"]: x for s in f["secciones"] for x in s["filas"]}
    assert all(v.startswith("sin dato; se usa") and v.endswith("(Supuesto)") for v in filas["MTBF de una unidad"]["valores"])
    assert all("Williams" in o["origen"] for o in f["opciones"])          # F1 no tiene equipos reales: todas estimadas


def test_resultados_de_la_opcion_salen_de_la_planta():
    pl = _resuelta(agrozzi)
    res, f = _ficha(pl)
    r = T.resultados_etapa(pl, "F1")
    filas = {x["etq"]: x for s in f["secciones"] for x in s["filas"]}
    assert r["demanda"] and r["demanda"] > 0 and r["cierre_kW"] is not None
    for c, v in zip(res["tres"], filas["Capacidad efectiva"]["valores"]):
        assert v.endswith("t/h")
    u = [c["instalada_t_h"] for c in res["tres"]]
    assert filas["Utilización"]["valores"][u.index(max(u))].endswith("%")


def test_curva_misma_escala_y_punto_de_operacion():
    pl = _resuelta(agrozzi)
    res, f = _ficha(pl, "W4")
    cu = f["curva"]
    assert len(cu["series"]) == 3 and all(len(s["eta"]) == len(cu["x"]) for s in cu["series"])
    assert cu["x"][0] == 0 and cu["x"][-1] >= f["requerida"]
    for s, c in zip(cu["series"], res["tres"]):
        assert math.isclose(s["op"]["x"], f["requerida"], rel_tol=1e-6)
        assert math.isclose(s["op"]["eta"], c["eta_relativa"], rel_tol=1e-4)
        assert all(cu["y_min"] <= e <= 1.0 + 1e-9 for e in s["eta"])


# ---------------------------------------------------------------- equipos auxiliares
def test_auxiliares_tienen_tres_opciones_de_distinto_n_y_su_ficha():
    pl = _resuelta(agrozzi)
    aux = AX.auxiliares(pl)
    o = EA.objetivos(pl, aux, None, False)
    assert o["objetivos"]
    for ob in o["objetivos"]:
        tres = T.elegir_tres(ob["candidatos"])
        assert len(tres) == 3 and len({c["n"] for c in tres}) == 3, (ob["id"], [c["n"] for c in ob["candidatos"]])
        f = T.comparativa(tres, dict(equipo=ob["id"], nombre=ob["nombre"], requerida=ob["requerida"], unidad=ob["unidad"]))
        assert [s["titulo"] for s in f["secciones"]] == ["Selección comercial", "Eficiencia en operación", "Costo total"]
        assert f["curva"] and len(f["curva"]["series"]) == 3


def test_cifras_de_agrozzi_intactas():
    pl = _resuelta(agrozzi)
    res = T.candidatos_tres(pl, "W1", None, False)
    assert res["requerimiento"]["unidad"] == "kW" and math.isclose(res["requerimiento"]["requerida"], 15956.0, abs_tol=0.05)   # hot break
    assert all(math.isclose(c["q_unidad"] * c["k"], 15956.0, abs_tol=0.05) for c in res["tres"])
