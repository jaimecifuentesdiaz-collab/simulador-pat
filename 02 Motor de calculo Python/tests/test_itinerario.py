"""Itinerario guiado (PAT 133, mejora 17): etapas, condiciones y pista de la siguiente."""
import pytest
from pat_sim.escenarios import agrozzi, plantillas as PLT, pellet, chip, lena
from pat_sim.motor import itinerario as IT, operacion as OP, flujo as FL
from pat_sim.motor.resumen import resumen_planta


def _ss(pl):
    return dict(pl=pl, cop=2.0, economia=dict(inversion=0.0), op=OP.Operacion(rubro=pl.rubro, semilla=OP.semilla_texto("x")))


def test_doce_etapas_nueve_de_flujo_mas_tres_del_curso():
    assert [e.clave for e in IT.ETAPAS] == ["desafio", "diseno", "seleccion", "restricciones", "balances", "instrumentacion",
                                            "costeo", "economia", "layout", "operacion", "calidad", "evaluacion"]
    assert [e.nombre for e in IT.ETAPAS[:9]] == [e.nombre for e in FL.ETAPAS]       # PAT 135: una sola guía de diseño
    assert all(e.pista and e.meta for e in IT.ETAPAS)


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_planta_nueva_cumple_diseno_balances_e_instrumentacion(mod):
    pl = mod.crear(); est = IT.evaluar(_ss(pl), pl)
    ok = {e["clave"] for e in est if e["cumplida"]}
    assert ok == {"diseno", "balances"} | ({"instrumentacion"} if pl.instrumentos else set())
    assert IT.siguiente(est)["clave"] == "desafio" and IT.avance(est) == pytest.approx(len(ok) / 12)


def test_cambiar_el_diseno_deja_etapas_por_revisar():
    pl = agrozzi.crear(); ss = _ss(pl); ss["costeo"] = dict(total_clp=10.0)
    FL.sincronizar(ss)
    assert next(e for e in IT.evaluar(ss, pl) if e["clave"] == "costeo")["cumplida"]
    pl.globales["dT_min"] = 9.0
    e = next(e for e in IT.evaluar(ss, pl) if e["clave"] == "costeo")
    assert not e["cumplida"] and e["por_revisar"]


def test_plantilla_sin_capacidades_no_cumple_restricciones():
    pl = PLT.cargar("plantilla_tomate"); ss = _ss(pl)
    ss["seleccion"] = dict(redundancias=[1]); FL.registrar_huella(ss, 4)
    est = IT.evaluar(ss, pl)
    assert not next(e for e in est if e["clave"] == "restricciones")["cumplida"]    # falta declarar la capacidad nominal


def test_avance_completo_con_turnos_laboratorio_inversion_y_evaluacion():
    pl = agrozzi.crear(); ss = _ss(pl); r = resumen_planta(pl); op = ss["op"]
    for _ in range(12):
        OP.tomar_muestra(op, pl); OP.correr_turno(op, pl, 0.9, None, "ninguno", r)
    ss["economia"]["inversion"] = 500.0
    est = IT.evaluar(ss, pl, r)
    ss["desafio"] = dict(titulo="x", rubro=pl.rubro, demanda=[1], precios=[])
    ss["seleccion"] = dict(redundancias=[1]); ss["costeo"] = dict(total_clp=1.0); ss["mce_resultado"] = (1, 2)
    ss["layout"] = dict(posiciones={"a": (0, 0)})
    FL.registrar_huella(ss, 4)
    assert len(op.lab) >= 8 and IT.siguiente(est)["clave"] != "evaluacion"
    OP.finalizar(op, pl, inversion=500.0, cascada_kW=r["cascada"])
    est = IT.evaluar(ss, pl, r)
    assert IT.siguiente(est) is None and IT.avance(est) == 1.0


def test_planta_sin_resolver_no_rompe():
    pl = agrozzi.crear(); pl.resuelta = False
    est = IT.evaluar(_ss(pl), pl)
    assert not next(e for e in est if e["clave"] == "diseno")["cumplida"]
