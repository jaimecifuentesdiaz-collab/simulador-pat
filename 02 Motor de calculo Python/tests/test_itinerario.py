"""Itinerario guiado (PAT 133, mejora 17): etapas, condiciones y pista de la siguiente."""
import pytest
from pat_sim.escenarios import agrozzi, plantillas as PLT, pellet, chip, lena
from pat_sim.motor import itinerario as IT, operacion as OP
from pat_sim.motor.resumen import resumen_planta


def _ss(pl):
    return dict(pl=pl, cop=2.0, economia=dict(inversion=0.0), op=OP.Operacion(rubro=pl.rubro, semilla=OP.semilla_texto("x")))


def test_ocho_etapas_en_el_orden_de_las_pestanas():
    assert [e.nombre for e in IT.ETAPAS] == ["Escenario", "Diseño", "Operación", "Calidad SPC", "Balances", "Recuperación de calor",
                                              "Economía", "Evaluación"]
    assert all(e.pista and e.meta for e in IT.ETAPAS)


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_planta_nueva_cumple_escenario_diseno_balances_y_recuperacion(mod):
    pl = mod.crear(); est = IT.evaluar(_ss(pl), pl)
    ok = {e["clave"] for e in est if e["cumplida"]}
    assert ok == {"escenario", "diseno", "balances", "recuperacion"}
    assert IT.siguiente(est)["clave"] == "operacion" and IT.avance(est) == pytest.approx(0.5)


def test_plantilla_sin_capacidades_pide_el_diseno():
    pl = PLT.cargar("plantilla_tomate"); est = IT.evaluar(_ss(pl), pl)
    assert IT.siguiente(est)["clave"] == "diseno"


def test_avance_completo_con_turnos_laboratorio_inversion_y_evaluacion():
    pl = agrozzi.crear(); ss = _ss(pl); r = resumen_planta(pl); op = ss["op"]
    for _ in range(12):
        OP.tomar_muestra(op, pl); OP.correr_turno(op, pl, 0.9, None, "ninguno", r)
    ss["economia"]["inversion"] = 500.0
    est = IT.evaluar(ss, pl, r)
    assert len(op.lab) >= 8 and IT.siguiente(est)["clave"] == "evaluacion"
    OP.finalizar(op, pl, inversion=500.0, cascada_kW=r["cascada"])
    est = IT.evaluar(ss, pl, r)
    assert IT.siguiente(est) is None and IT.avance(est) == 1.0


def test_planta_sin_resolver_no_rompe():
    pl = agrozzi.crear(); pl.resuelta = False
    est = IT.evaluar(_ss(pl), pl)
    assert not next(e for e in est if e["clave"] == "diseno")["cumplida"]
