"""Pruebas de la simulación de la línea por ticks como la Fluid Library de FlexSim (PAT 134): balance de masa, tasa de la
línea, bloqueo y hambre alrededor del recurso crítico, fallas MTBF/MTTR, paradas programadas, tramos y reproducibilidad."""
import time
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import ajuste as AJ
from pat_sim.motor import linea_fluida as LF
from pat_sim.motor import operacion as OP
from pat_sim.motor import temporada as TM

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
CLAVES = {"equipos", "tanques", "tramos", "tiempo_h", "niveles", "produccion_acumulada_t", "tasas", "por_equipo", "produccion_t",
          "oee", "avisos", "supuestos", "parametros"}


@pytest.fixture(scope="module")
def plantas():
    out = {}
    for k, m in ESCENARIOS.items():
        pl = m.crear(); pl.resolver(); out[k] = pl
    return out


def _exp(media):
    return AJ.crear("exponencial", escala=media)


def _cubren(r):
    H = r["parametros"]["horas"]
    for e in r["equipos"]:
        ts = [t for t in r["tramos"] if t["equipo"] == e["id"]]
        assert ts[0]["inicio_h"] == pytest.approx(0.0) and ts[-1]["fin_h"] == pytest.approx(H)
        for a, b in zip(ts, ts[1:]):
            assert b["inicio_h"] == pytest.approx(a["fin_h"]) and a["estado"] != b["estado"]
        assert all(t["fin_h"] > t["inicio_h"] for t in ts) and all(t["estado"] in LF.ESTADOS for t in ts)
        assert sum(r["por_equipo"][e["id"]]["horas_por_estado"].values()) == pytest.approx(H)


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_contrato_balance_y_tramos_en_los_cuatro_rubros(plantas, rubro):
    pl = plantas[rubro]
    r = LF.simular_linea(pl, horas=72, tick_min=1, semilla=4)
    assert CLAVES <= set(r)
    ids = [e["id"] for e in r["equipos"]]
    assert all(not pl.equipos[k].tipo.startswith(("caldera", "generador", "alimentacion")) for k in ids) and len(ids) >= 3
    assert [t["antes"] for t in r["tanques"]] == ids[:-1] and [t["despues"] for t in r["tanques"]] == ids[1:]
    b = r["balance"]
    assert b["cierra"] and b["entrada_t"] + b["inventario_inicial_t"] == pytest.approx(
        b["producto_t"] + b["salidas_proceso_t"] + b["inventario_final_t"], rel=1e-9)
    assert r["produccion_t"] == pytest.approx(b["producto_t"]) and r["produccion_acumulada_t"][-1] == pytest.approx(r["produccion_t"])
    n = len(r["tiempo_h"])
    assert r["tiempo_h"][-1] == pytest.approx(72.0) and all(len(v) == n for v in r["niveles"].values())
    assert len(r["produccion_acumulada_t"]) == n and all(len(v) == n for v in r["tasas"].values())
    assert all(0 <= x <= t["capacidad_t"] + 1e-9 for t in r["tanques"] for x in r["niveles"][t["id"]])
    _cubren(r)
    assert 0 < r["oee"] <= 1.0 + 1e-9 and all(s["justificacion"] for s in r["supuestos"])


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_sin_fallas_produce_la_tasa_de_la_linea(plantas, rubro):
    pl = plantas[rubro]
    r = LF.simular_linea(pl, horas=72, fallas=False)
    real = OP.linea(pl)["real"]
    assert r["tasa_linea_t_h"] == pytest.approx(real, rel=1e-6)
    assert r["produccion_t"] == pytest.approx(real * 72, rel=0.005)
    assert all(v["fallas"] == 0 and v["horas_por_estado"]["en_falla"] == 0 for v in r["por_equipo"].values())
    primero = r["equipos"][0]["id"]
    assert r["por_equipo"][primero]["horas_por_estado"]["operando"] == pytest.approx(72.0)
    assert r["balance"]["alimentacion_rechazada_t"] == pytest.approx(0.0, abs=1e-6)


def test_recurso_critico_bloquea_aguas_arriba_y_deja_con_hambre_aguas_abajo():
    pl = agrozzi.crear(); pl.resolver()
    c = OP.linea(pl)["critico"]; e = pl.equipos[c]
    e.set("capacidad", 0.8 * float(e.resultado.detalle["carga_t_h"])); pl.resolver()
    real = OP.linea(pl)["real"]
    r = LF.simular_linea(pl, horas=72, fallas=False)
    ids = [x["id"] for x in r["equipos"]]; i = ids.index(c); pe = r["por_equipo"]
    assert r["produccion_t"] == pytest.approx(real * 72, rel=0.01)
    assert all(pe[k]["horas_por_estado"]["bloqueado"] > 1.0 for k in ids[:i])
    assert all(pe[k]["horas_por_estado"]["esperando"] > 60.0 for k in ids[i + 1:])
    assert pe[c]["horas_por_estado"]["operando"] > 70.0
    t = next(t for t in r["tanques"] if t["despues"] == c)
    assert r["niveles"][t["id"]][-1] == pytest.approx(t["capacidad_t"], rel=1e-6)
    assert r["balance"]["alimentacion_rechazada_t"] > 0 and r["balance"]["cierra"]
    # el bloqueo aparece recién cuando el tanque del recurso crítico se llena
    antes = ids[i - 1]
    prim = next(x for x in r["tramos"] if x["equipo"] == antes and x["estado"] == "bloqueado")
    exceso = float(pl.equipos[antes].resultado.detalle["carga_t_h"]) * (float(e.resultado.detalle["carga_t_h"]) / float(pl.equipos[antes].resultado.detalle["carga_t_h"])) - e.capacidad_efectiva()
    assert prim["inicio_h"] == pytest.approx(t["capacidad_t"] / exceso, rel=0.05)


@pytest.mark.parametrize("base", ["todo", "operando"])
def test_disponibilidad_tiende_a_mtbf_sobre_mtbf_mas_mttr(plantas, base):
    pl = plantas["lena"]; ids = [e["id"] for e in LF.simular_linea(pl, horas=1, fallas=False)["equipos"]]
    f = {k: None for k in ids}; f[ids[0]] = dict(mtbf=_exp(20.0), mttr=_exp(2.0), base=base)
    r = LF.simular_linea(pl, horas=4000, tick_min=6, semilla=7, fallas=f)
    pe = r["por_equipo"][ids[0]]
    assert pe["fallas"] > 120 and pe["disponibilidad_teorica"] == pytest.approx(20 / 22)
    assert pe["disponibilidad"] == pytest.approx(20 / 22, abs=0.03)
    assert all(r["por_equipo"][k]["fallas"] == 0 for k in ids[1:])
    assert r["balance"]["cierra"]


def test_base_operando_no_cuenta_el_tiempo_detenido(plantas):
    pl = plantas["lena"]; ids = [e["id"] for e in LF.simular_linea(pl, horas=1, fallas=False)["equipos"]]
    pr = [dict(actividad="Parada", inicio_h=24.0 * d + 12, fin_h=24.0 * d + 24, tipo="parada") for d in range(100)]
    f = {k: None for k in ids}
    res = {}
    for base in ("todo", "operando"):
        f[ids[0]] = dict(mtbf=_exp(10.0), mttr=_exp(1.0), base=base)
        res[base] = LF.simular_linea(pl, horas=2400, tick_min=6, semilla=3, fallas=f, programa=pr)["por_equipo"][ids[0]]["fallas"]
    assert res["operando"] < 0.75 * res["todo"]


def test_paradas_programadas_detienen_toda_la_linea(plantas):
    pl = plantas["pellet"]
    pr = [dict(actividad="Limpieza programada", inicio_h=10.0, fin_h=14.0, tipo="limpieza"),
          dict(actividad="Producción", inicio_h=14.0, fin_h=48.0, tipo="produccion")]
    r = LF.simular_linea(pl, horas=48, fallas=False, programa=pr)
    for e in r["equipos"]:
        assert r["por_equipo"][e["id"]]["horas_por_estado"]["detenido_programado"] == pytest.approx(4.0)
        en12 = next(t for t in r["tramos"] if t["equipo"] == e["id"] and t["inicio_h"] <= 12 < t["fin_h"])
        assert en12["estado"] == "detenido_programado"
    assert r["horas_planificadas"] == pytest.approx(44.0)
    assert r["produccion_t"] == pytest.approx(r["tasa_linea_t_h"] * 44.0, rel=0.01)
    _cubren(r)


def test_programa_de_temporada_como_time_table(plantas):
    pl = plantas["tomate"]; pr = TM.programa_temporada(pl)
    r = LF.simular_linea(pl, horas=72, fallas=False, programa=pr)
    arr = next(b for b in pr["barras"] if b["tipo"] == "arranque")
    h = arr["fin_h"] - arr["inicio_h"]
    assert r["por_equipo"][r["equipos"][0]["id"]]["horas_por_estado"]["detenido_programado"] >= h - 1e-6
    assert r["parametros"]["paradas"] and r["balance"]["cierra"]


def test_mantenimiento_preventivo(plantas):
    pl = plantas["lena"]; ids = [e["id"] for e in LF.simular_linea(pl, horas=1, fallas=False)["equipos"]]
    f = {k: None for k in ids}
    f[ids[0]] = dict(mtbf=_exp(1e9), mttr=_exp(1.0), mantenimiento=dict(cada_h=24.0, duracion_h=2.0))
    r = LF.simular_linea(pl, horas=72, fallas=f)
    assert r["por_equipo"][ids[0]]["horas_por_estado"]["en_mantenimiento"] == pytest.approx(4.0)
    assert r["por_equipo"][ids[0]]["disponibilidad"] == pytest.approx(68 / 72)


def test_reproducible_con_la_misma_semilla(plantas):
    pl = plantas["tomate"]
    a = LF.simular_linea(pl, horas=300, semilla=11); b = LF.simular_linea(pl, horas=300, semilla=11)
    c = LF.simular_linea(pl, horas=300, semilla=12)
    assert a["tramos"] == b["tramos"] and a["produccion_t"] == b["produccion_t"]
    assert a["tramos"] != c["tramos"]


def test_corriente_por_equipo_no_cambia_con_las_fallas_de_otro(plantas):
    pl = plantas["chip"]; ids = [e["id"] for e in LF.simular_linea(pl, horas=1, fallas=False)["equipos"]]
    f1 = {ids[0]: dict(mtbf=_exp(30.0), mttr=_exp(2.0), base="todo"), ids[1]: dict(mtbf=_exp(50.0), mttr=_exp(1.0), base="todo")}
    f2 = dict(f1); f2[ids[1]] = dict(mtbf=_exp(5.0), mttr=_exp(3.0), base="todo")
    a = LF.simular_linea(pl, horas=500, semilla=2, fallas=f1); b = LF.simular_linea(pl, horas=500, semilla=2, fallas=f2)
    fa = [t for t in a["tramos"] if t["equipo"] == ids[0] and t["estado"] == "en_falla"]
    fb = [t for t in b["tramos"] if t["equipo"] == ids[0] and t["estado"] == "en_falla"]
    assert fa == fb and fa


def test_tanques_del_usuario_y_conexion_directa(plantas):
    pl = plantas["pellet"]; ids = [e["id"] for e in LF.simular_linea(pl, horas=1, fallas=False)["equipos"]]
    t0 = f"{ids[0]}-{ids[1]}"; t2 = f"{ids[2]}-{ids[3]}"
    r = LF.simular_linea(pl, horas=24, fallas=False, tanques={t0: 0, t2: dict(capacidad_t=5.0, nivel_inicial_t=2.0)})
    tk = {t["id"]: t for t in r["tanques"]}
    assert tk[t0]["anulado"] and tk[t0]["capacidad_t"] == 0 and tk[t2]["capacidad_t"] == 5.0
    assert all(x == 0 for x in r["niveles"][t0]) and r["niveles"][t2][0] == 2.0
    assert r["balance"]["inventario_inicial_t"] == pytest.approx(2.0) and r["balance"]["cierra"]
    # con conexión directa el segundo equipo recibe en el mismo tick: no espera al partir
    assert r["por_equipo"][ids[1]]["horas_por_estado"]["esperando"] == pytest.approx(0.0)
    # una falla del segundo equipo bloquea al primero de inmediato si no hay pulmón
    f = {k: None for k in ids}; f[ids[1]] = dict(mtbf=_exp(10.0), mttr=_exp(2.0), base="todo")
    r = LF.simular_linea(pl, horas=200, semilla=5, fallas=f, tanques={t0: 0})
    pe = r["por_equipo"]
    assert pe[ids[0]]["horas_por_estado"]["bloqueado"] == pytest.approx(pe[ids[1]]["horas_por_estado"]["en_falla"], rel=1e-6)


def test_tanque_pulmon_absorbe_una_falla_corta(plantas):
    pl = plantas["pellet"]; ids = [e["id"] for e in LF.simular_linea(pl, horas=1, fallas=False)["equipos"]]
    f = {k: None for k in ids}; f[ids[1]] = dict(mtbf=_exp(10.0), mttr=AJ.crear("uniforme", minimo=0.2, maximo=0.4), base="todo")
    r = LF.simular_linea(pl, horas=200, semilla=5, fallas=f, tanques={f"{ids[0]}-{ids[1]}": 100.0})
    assert r["por_equipo"][ids[1]]["fallas"] > 5 and r["por_equipo"][ids[0]]["horas_por_estado"]["bloqueado"] == pytest.approx(0.0)


def test_alimentacion_del_usuario(plantas):
    pl = plantas["chip"]
    r = LF.simular_linea(pl, horas=48, fallas=False, alimentacion_t_h=0.5 * LF.simular_linea(pl, horas=1, fallas=False)["equipos"][0]["carga_t_h"])
    assert r["produccion_t"] == pytest.approx(0.5 * OP.linea(pl)["real"] * 48, rel=0.01)
    assert r["tasa_linea_t_h"] == pytest.approx(0.5 * OP.linea(pl)["real"], rel=1e-6)


def test_fallas_por_defecto_son_supuesto(plantas):
    pl = plantas["tomate"]
    r = LF.simular_linea(pl, horas=2000, tick_min=5, semilla=1)
    fa = r["parametros"]["fallas"]
    con = [k for k, v in fa.items() if v is not None]
    assert con and all(fa[k]["origen"] == "Supuesto" for k in con)
    assert sum(r["por_equipo"][k]["fallas"] for k in con) > 50
    assert all(r["por_equipo"][k]["disponibilidad"] < 1.0 for k in con)
    assert {s["clave"] for s in r["supuestos"]} >= {"tanque_min", "mtbf_mecanico", "mttr_termico"}


def test_errores_de_entrada(plantas):
    pl = plantas["lena"]
    with pytest.raises(ValueError):
        LF.simular_linea(pl, horas=0)
    with pytest.raises(ValueError):
        LF.simular_linea(pl, horas=10, fallas={"A1": dict(mtbf=_exp(10.0), mttr=_exp(1.0), base="nunca")})


def test_tiempo_de_calculo(plantas):
    t = time.time()
    LF.simular_linea(plantas["tomate"], horas=72, tick_min=1, semilla=1)
    assert time.time() - t < 3.0


# PAT 134: el OEE usa la tasa planificada de Temporada y Tableros; el del recurso crítico queda como dato adicional
@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_oee_con_la_tasa_planificada_como_temporada_y_tableros(plantas, rubro):
    pl = plantas[rubro]; plan = OP.linea(pl)["plan"]
    r = LF.simular_linea(pl, horas=72, semilla=4)
    o, oc = r["oee_detalle"], r["oee_critico_detalle"]
    assert r["tasa_planificada_t_h"] == pytest.approx(plan) and o["tasa_ideal_t_h"] == pytest.approx(plan)
    assert oc["tasa_ideal_t_h"] == pytest.approx(r["tasa_maxima_linea_t_h"])
    # OEE = disponibilidad × rendimiento = producción / (tasa ideal × horas planificadas)
    assert r["oee"] == pytest.approx(r["produccion_t"] / (plan * r["horas_planificadas"]), rel=1e-9)
    assert r["oee_critico"] == pytest.approx(r["produccion_t"] / (r["tasa_maxima_linea_t_h"] * r["horas_planificadas"]), rel=1e-9)
    assert o["disponibilidad"] == pytest.approx(oc["disponibilidad"]) and r["oee_critico"] <= r["oee"] + 1e-12


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_sin_fallas_el_oee_planificado_es_casi_100(plantas, rubro):
    pl = plantas[rubro]
    r = LF.simular_linea(pl, horas=72, fallas=False)
    # la línea parte vacía: los tanques se llenan en las primeras horas y el OEE queda algo bajo 100 %
    assert 0.95 < r["oee"] <= 1.0 + 1e-9 and r["oee_critico"] < r["oee"]


def test_oee_comparable_con_la_temporada(plantas):
    pl = plantas["tomate"]; ln = OP.linea(pl)
    r = LF.simular_linea(pl, horas=72, fallas=False)
    # la misma tasa ideal: con la producción real a la tasa planificada el rendimiento de las dos pestañas coincide
    pr = TM.programa_temporada(pl)
    if pr.get("oee"):
        assert pr["oee"]["rendimiento"] == pytest.approx(ln["real"] / ln["plan"], rel=1e-6)
    assert r["oee_detalle"]["rendimiento"] == pytest.approx(ln["real"] / ln["plan"], rel=0.02)
