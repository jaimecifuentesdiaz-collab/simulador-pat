"""Operación por turnos, laboratorio, control estadístico y evaluación (PAT 130): adaptación de runShift, sampleLab,
deliverLab, drawSPC y grade del simulador del profesor."""
import math
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import operacion as OP
from pat_sim.motor.resumen import resumen_planta
from pat_sim.catalogos import calidad as Q


def _op(pl, nombre="escenario"):
    return OP.Operacion(rubro=pl.rubro, semilla=OP.semilla_texto(nombre))


def _correr(n=6, nombre="escenario", **kw):
    pl = agrozzi.crear(); r = resumen_planta(pl); op = _op(pl, nombre)
    for i in range(n):
        OP.tomar_muestra(op, pl)
        OP.correr_turno(op, pl, 0.9, None, "ninguno", r, **kw)
    return pl, op


def test_semilla_como_el_profesor():
    assert OP.semilla_texto("escenario") == OP.semilla_texto("escenario") and OP.semilla_texto("Ana") != OP.semilla_texto("Luis")
    assert OP.semilla_texto("") == 2166136261                     # base de FNV-1a, la misma del randomSeed del profesor
    assert 0 <= OP.azar(1, 2.5) < 1 and OP.azar(1, 2.5) == OP.azar(1, 2.5)


def test_turnos_reproducibles_con_la_misma_semilla():
    _p1, a = _correr(6); _p2, b = _correr(6)
    assert [x["producido"] for x in a.turnos] == [x["producido"] for x in b.turnos]
    assert [m["valores"] for m in a.lab] == [m["valores"] for m in b.lab]
    _p3, c = _correr(6, "otro estudiante")
    assert [x["demanda"] for x in a.turnos] != [x["demanda"] for x in c.turnos]


def test_balance_de_materia_prima_y_producto():
    pl = agrozzi.crear(); op = _op(pl); ln = OP.linea(pl)
    assert math.isclose(ln["mp_por_t"], ln["alimentacion"] / ln["plan"])
    stock0 = OP.S["stock_inicial"] * ln["alimentacion"] * 8
    reg = OP.correr_turno(op, pl, 0.9, 2000.0, "ninguno", resumen_planta(pl))
    merma = stock0 * OP.S["merma_patio"]                             # tomate que esperó un turno
    assert math.isclose(op.stock, stock0 - merma + reg["recibido"] - reg["materia_prima"], rel_tol=1e-9)
    assert reg["producido"] <= ln["real"] * 8 * 0.9 + 1e-9 and math.isclose(reg["materia_prima"], reg["producido"] * ln["mp_por_t"])
    assert math.isclose(reg["conforme"] + reg["no_conforme"], reg["producido"]) and reg["vendido"] <= reg["demanda"] + 1e-9
    assert 2000 * (1 - OP.S["merma_recepcion"]) <= reg["recibido"] <= 2000


def test_sin_materia_prima_la_linea_para():
    pl = agrozzi.crear(); op = _op(pl); op.stock = 0.0
    reg = OP.correr_turno(op, pl, 0.9, 0.0, "ninguno")
    assert reg["producido"] == 0 and any("Faltó materia prima" in e for e in reg["eventos"])


def test_desgaste_y_mantenimiento_preventivo():
    pl = agrozzi.crear(); op = _op(pl)
    OP.correr_turno(op, pl, 0.9, None, "ninguno")
    est = OP.linea(pl)["estados"]
    assert all(0.996 - 1e-9 <= v <= 0.998 + 1e-9 for v in est.values())     # baja entre 0,002 y 0,004
    crit = OP.linea(pl)["critico"]; antes = est[crit]
    OP.correr_turno(op, pl, 0.9, None, "preventivo")
    assert op.mantenimientos == 1 and OP.linea(pl)["estados"][crit] > antes


def test_capacidades_limitan_la_produccion_del_turno():
    from pat_sim.motor import lienzo as LZ
    pl = agrozzi.crear(); LZ.asignar_capacidades(pl, 0.5); pl.equipos["W3"].set("capacidad", 100.0); pl.resolver()
    ln = OP.linea(pl)
    assert ln["con_capacidades"] and ln["critico"] == "W3" and ln["real"] < ln["plan"]


def test_laboratorio_entrega_con_demora():
    pl = agrozzi.crear(); op = _op(pl)
    tk = OP.tomar_muestra(op, pl)
    assert tk["entrega"] in (1, 2) and not op.lab
    OP.correr_turno(op, pl); OP.correr_turno(op, pl)
    assert len(op.lab) == 1 and set(op.lab[0]["valores"]) == {v.id for v in Q.variables(pl)}


def test_variables_de_la_pasta_siguen_a_la_planta():
    pl = agrozzi.crear(); v = {x.id: x for x in Q.variables(pl)}
    assert math.isclose(v["brix"].media, 30.0, abs_tol=1e-6) and v["t_est"].media == 103.0 and v["t_est"].lo == 103.0
    assert v["howard"].hi == 50.0 and v["ph"].hi == 4.5
    # la DIA exige más de 103 °C: con la consigna en 103 °C la mitad de las muestras queda bajo el mínimo
    assert math.isclose(OP.prob_conforme(103.0, 0.6, 103.0, 110.0), 0.5, abs_tol=1e-9)
    c0 = OP.conformidad(pl)
    acc = [a for a in Q.acciones(pl) if a["variable"] == "t_est"][0]
    assert Q.aplicar_accion(pl, acc, 105.0); pl.resolver()
    assert OP.conformidad(pl) > c0 + 0.3


def test_variables_de_biomasa():
    for mod, n in ((pellet, 6), (chip, 2), (lena, 2)):
        pl = mod.crear(); vs = Q.variables(pl)
        assert len(vs) == n and vs[0].id == "humedad" and vs[0].hi is not None
    assert Q.variables(lena.crear())[0].hi == 25.0                    # NCh2907, leña seca bajo 25 % en base seca


def test_spc_rango_movil_y_capacidad():
    vals = [10.0, 10.2, 9.9, 10.1, 10.0, 9.8, 10.1, 10.0, 10.2, 9.9, 10.0, 10.1]
    r = OP.spc(vals, 9.0, 11.0)
    mr = sum(abs(b - a) for a, b in zip(vals, vals[1:])) / 11
    assert math.isclose(r["sigma"], mr / 1.128) and r["estable"] and r["reportable"]
    assert math.isclose(r["cp"], 2.0 / (6 * r["sigma"])) and r["cpk"] <= r["cp"]
    assert OP.spc(vals[:7])["estado"] == "Datos insuficientes" and OP.spc(vals[:7])["lc"] is None
    assert OP.spc(vals + [14.0], 9, 11)["fuera"] == [12]
    racha = [10.0, 9.0, 10.0, 9.0] + [10.2] * 8 + [9.0, 10.0]
    assert OP.spc(racha)["racha"] and not OP.spc(racha)["estable"]


def test_grafico_de_control_svg():
    vals = [10.0, 10.2, 9.9, 10.1, 10.0, 9.8, 10.1, 10.0, 10.2]
    v = Q.Variable("x", "Prueba", "%", 9.0, 11.0, 0.1, 10.0, "", "")
    svg = OP.grafico_control(vals, v, OP.spc(vals, 9, 11))
    assert svg.startswith("<svg") and svg.count("<circle") == 9 and "LSC" in svg and "LSE" in svg


def test_gas_evitado_por_turno():
    pl = agrozzi.crear(); r = resumen_planta(pl); op = _op(pl)
    reg = OP.correr_turno(op, pl, 1.0, None, "ninguno", r)
    f = reg["producido"] / (OP.linea(pl)["plan"] * 8)
    assert math.isclose(reg["gas_evitado_MMBtu"], r["gas_cascada"]["MMBtu"] * 8 * f / r["horas"], rel_tol=1e-6)


def test_evaluacion_100_puntos_con_todo():
    from pat_sim.motor import lienzo as LZ
    pl = agrozzi.crear(); LZ.asignar_capacidades(pl, 0.5); pl.resolver(); r = resumen_planta(pl); op = _op(pl)
    for i in range(14):
        OP.tomar_muestra(op, pl)
        OP.correr_turno(op, pl, 0.9, None, "preventivo" if i == 2 else "ninguno", r)
    op.justificaciones = {k: "x" * 200 for k in ("restricciones", "recuperacion")}
    g = OP.evaluar(op, pl, inversion=1000.0, cascada_kW=r["cascada"])
    assert g["diseno"] == 15 and g["restricciones"] == 20 and g["economia"] == 15 and g["operacion"] == 15 and g["recuperacion"] == 15
    assert g["calidad"] >= 15 and g["total"] == sum(g[k] for k, _n, _m in OP.CRITERIOS) and sum(m for *_x, m in OP.CRITERIOS) == 100
    OP.finalizar(op, pl, inversion=1000.0, cascada_kW=r["cascada"])
    with pytest.raises(ValueError):
        OP.correr_turno(op, pl)


def test_proyecto_json_ida_y_vuelta():
    import json
    _pl, op = _correr(3)
    op2 = OP.Operacion.desde_dict(json.loads(json.dumps(op.a_dict())))
    assert op2.turnos == json.loads(json.dumps(op.turnos)) and op2.semilla == op.semilla


def test_supuestos_con_justificacion():
    assert all(s.justificacion and s.unidad for s in OP.SUPUESTOS.values())


# ----------------------------------------------------------------------------------------------- PAT 134: duración de fallas ajustada
def test_falla_con_distribucion_ajustada():
    from pat_sim.motor import ajuste as AJ
    d = AJ.crear("weibull", forma=1.6, escala=4.0)
    _p, sin = _correr(12); _p, con = _correr(12, dist_falla_h=d); _p, otra = _correr(12, dist_falla_h=d)
    assert any(x["falla"] for x in sin.turnos)                                       # la semilla trae al menos una falla
    for a, b, c in zip(sin.turnos, con.turnos, otra.turnos):
        assert a["falla"] == b["falla"] and a["falla_h"] is None and b["falla_h"] == c["falla_h"]
        if b["falla"]:
            assert b["falla_h"] >= 0 and b["capacidad"] == pytest.approx(a["capacidad"] / OP.S["disp_falla"] * max(0.0, 1 - b["falla_h"] / 8), rel=1e-9)
        else:
            assert b["falla_h"] is None and b["capacidad"] == pytest.approx(a["capacidad"], rel=1e-12)


def test_falla_larga_deja_el_turno_sin_capacidad():
    from pat_sim.motor import ajuste as AJ
    d = AJ.crear("uniforme", minimo=9.0, maximo=10.0)                             # toda falla dura más que el turno
    _p, op = _correr(12, dist_falla_h=d)
    f = [x for x in op.turnos if x["falla"]]
    assert f and all(x["capacidad"] == 0 and 9 <= x["falla_h"] <= 10 for x in f)
