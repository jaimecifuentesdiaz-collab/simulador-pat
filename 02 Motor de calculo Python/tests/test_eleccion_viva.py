"""PAT 139 (punto 6): elección en vivo de la Planta real y de Equipos auxiliares, con «Generar automáticamente» y «Deshacer»
(motor/eleccion_viva.py y motor/eleccion_auxiliares.py)."""
import sys
import types
import pytest
from pat_sim.motor import (lienzo as LZ, seleccion as S, costo_total as CT, auxiliares as AX, eleccion_viva as EV,
                           eleccion_auxiliares as EA)
from pat_sim.motor.planta import Planta
from pat_sim.escenarios import agrozzi, pellet, chip, lena


def _cands(pl):
    return {r["equipo"]: CT.candidatos_etapa(pl, r["equipo"], None, False) for r in S.requerimientos(pl)}


def _agrozzi():
    pl = agrozzi.crear()
    if not pl.resuelta:
        pl.resolver()
    return pl


def _n_elegidas(pl):
    return sum(1 for r in S.requerimientos(pl) if r["actual"])


# ---------------------------------------------------------------- pila de cambios
def test_elegir_de_uno_en_uno_y_deshacer_dos_veces():
    pl = _agrozzi(); h = LZ.Historial(30); c = _cands(pl)
    # PAT 139 (14-11): con la base de respaldo, W1 trae solo opciones de Williams; se usa el último candidato (no el cuarto)
    r1 = EV.aplicar_candidato(pl, h, c["W1"][-1])
    r2 = EV.aplicar_candidato(pl, h, c["Z1"][0])
    assert r1["cambio"] and r2["cambio"] and h.resumen()["deshacer"] == 2 and _n_elegidas(pl) == 2
    assert S.seleccion_actual(pl.equipos["W1"])["modelo"] == c["W1"][-1]["modelo"]
    assert EV.deshacer(pl, h)["ok"]; pl.resolver()
    assert _n_elegidas(pl) == 1 and S.seleccion_actual(pl.equipos["Z1"]) is None
    assert EV.deshacer(pl, h)["ok"]; pl.resolver()
    assert _n_elegidas(pl) == 0 and not EV.deshacer(pl, h)["ok"]          # sin más pasos: avisa, no falla
    assert EV.rehacer(pl, h)["ok"]; pl.resolver()
    assert S.seleccion_actual(pl.equipos["W1"])["modelo"] == c["W1"][-1]["modelo"]


def test_el_mismo_candidato_dos_veces_no_gasta_un_paso():
    pl = _agrozzi(); h = LZ.Historial(30); c = _cands(pl)
    EV.aplicar_candidato(pl, h, c["F1"][0])
    r = EV.aplicar_candidato(pl, h, c["F1"][0])
    assert not r["cambio"] and h.resumen()["deshacer"] == 1


def test_generar_automaticamente_es_un_solo_paso_y_usa_el_menor_c():
    pl = _agrozzi(); h = LZ.Historial(30); c = _cands(pl)
    r = EV.generar_automaticamente(pl, h, c)
    assert r["cambio"] and r["n"] == len(c) and h.resumen()["deshacer"] == 1
    for eid, cs in c.items():
        assert cs == sorted(cs, key=lambda x: x["C"])                       # lista ordenada por C
        best = CT.mejor_opcion(pl, eid, None, False)
        act = S.seleccion_actual(pl.equipos[eid])
        assert (act["modelo"], act["n"]) == (best["modelo"], best["n"])
    EV.deshacer(pl, h); pl.resolver()
    assert _n_elegidas(pl) == 0


def test_estado_recalcula_a_sist_capacidad_y_c_total():
    pl = _agrozzi(); h = LZ.Historial(30); c = _cands(pl)
    e0 = EV.estado_planta_real(pl, c)
    assert e0["n_elegidas"] == 0 and e0["A_sist"] is None and e0["C"] is None and e0["n_etapas"] == len(c)
    EV.aplicar_candidato(pl, h, c["W1"][0]); EV.aplicar_candidato(pl, h, c["W2"][1])
    e = EV.estado_planta_real(pl, c)
    el = [c["W1"][0], c["W2"][1]]
    assert e["n_elegidas"] == 2
    assert e["A_sist"] == pytest.approx(el[0]["A"] * el[1]["A"])
    assert e["C"] == pytest.approx(el[0]["C"] + el[1]["C"])
    assert e["C"] == pytest.approx(e["C_inv"] + e["C_op"] + e["C_inef"])
    assert e["capacidad_t_h"] == pytest.approx(min(x["cap_esperada_producto"] for x in el))
    fW1 = next(f for f in e["filas"] if f["equipo"] == "W1")
    assert fW1["es_mejor"] and fW1["elegido"]["id"] == c["W1"][0]["id"]
    assert e["C_min"] == pytest.approx(sum(cs[0]["C"] for cs in c.values()))


def test_planta_vacia_no_falla():
    pl = Planta("Vacía", "tomate"); h = LZ.Historial(30)
    assert EV.estado_planta_real(pl, {})["n_etapas"] == 0
    r = EV.generar_automaticamente(pl, h, {})
    assert not r["ok"] and "vacía" in r["mensaje"] and h.resumen()["deshacer"] == 0
    assert not EV.aplicar_candidato(pl, h, {"equipo": "W1"})["ok"]
    o = EA.objetivos(pl, None)
    assert o["objetivos"] == [] and "vacía" in o["avisos"][0]
    assert EA.estado(pl, [])["n_objetivos"] == 0
    assert not EA.generar_automaticamente(pl, h, [])["ok"]


def test_deshacer_tambien_vuelve_atras_el_layout_en_orden():
    pl = _agrozzi(); h = LZ.Historial(30); c = _cands(pl)
    x0 = pl.equipos["W1"].x
    EV.aplicar_candidato(pl, h, c["W1"][0])
    assert EV.procesar_evento(pl, h, dict(evento="mover", datos=dict(id="W1", x=x0 + 200, y=pl.equipos["W1"].y)), c)["ok"]
    assert pl.equipos["W1"].x == x0 + 200 and h.resumen()["etiqueta_deshacer"] == "mover W1"
    EV.deshacer(pl, h); pl.resolver()
    assert pl.equipos["W1"].x == x0 and S.seleccion_actual(pl.equipos["W1"]) is not None   # primero el movimiento
    EV.deshacer(pl, h); pl.resolver()
    assert S.seleccion_actual(pl.equipos["W1"]) is None                                       # después la elección


def test_eventos_del_lienzo():
    pl = _agrozzi(); h = LZ.Historial(30); c = _cands(pl)
    cid = c["W1"][1]["id"]
    r = EV.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo="Z1", candidato=cid)), c)
    assert not r["ok"] and "W1" in r["mensaje"] and _n_elegidas(pl) == 0       # soltado sobre otra etapa: no se aplica
    assert EV.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo="W1", candidato=cid)), c)["ok"]
    assert not EV.procesar_evento(pl, h, dict(evento="elegir", datos=dict(candidato="no existe")), c)["ok"]
    assert EV.procesar_evento(pl, h, dict(evento="generar", datos={}), c)["ok"] and _n_elegidas(pl) == len(c)
    assert EV.procesar_evento(pl, h, dict(evento="quitar", datos={}), c)["ok"] and _n_elegidas(pl) == 0
    assert EV.procesar_evento(pl, h, dict(evento="deshacer", datos={}), c)["ok"]
    pl.resolver(); assert _n_elegidas(pl) == len(c)
    assert not EV.procesar_evento(pl, h, dict(evento="otro", datos={}), c)["ok"]


@pytest.mark.parametrize("mod", [agrozzi, pellet, chip, lena])
def test_cuatro_rubros_generar_y_deshacer(mod):
    pl = mod.crear()
    if not pl.resuelta:
        pl.resolver()
    h = LZ.Historial(30); c = _cands(pl)
    assert c and all(c.values())
    EV.generar_automaticamente(pl, h, c)
    e = EV.estado_planta_real(pl, c)
    assert e["n_elegidas"] == e["n_etapas"] == len(c) and 0 < e["A_sist"] <= 1 and e["C"] > 0
    r = AX.auxiliares(pl)
    o = EA.objetivos(pl, r, buscar_en_linea=False)
    assert all(ob["candidatos"] == sorted(ob["candidatos"], key=lambda x: (x["C"], x["n"])) for ob in o["objetivos"])
    EA.generar_automaticamente(pl, h, o["objetivos"])
    EV.deshacer(pl, h); pl.resolver()
    assert EA.estado(pl, o["objetivos"])["n_elegidos"] == 0 and _n_elegidas(pl) == len(c)
    EV.deshacer(pl, h); pl.resolver()
    assert _n_elegidas(pl) == 0


# ---------------------------------------------------------------- equipos auxiliares
def test_auxiliares_candidatos_con_c_y_esquemas():
    pl = _agrozzi()
    o = EA.objetivos(pl, AX.auxiliares(pl), buscar_en_linea=False)
    grupos = {ob["grupo"] for ob in o["objetivos"]}
    assert {"Bombas", "Válvulas de control", "Estanques pulmón", "Servicios"} <= grupos
    for ob in o["objetivos"]:
        assert ob["dianas"] and ob["candidatos"]
        for c in ob["candidatos"]:
            assert c["C"] == pytest.approx(c["C_inv"] + c["C_op"] + c["C_inef"]) and 0 <= c["A"] <= 1 and c["n"] >= c["k"] >= 1
            assert c["origen"] in ("Tavily", "Respaldo", "Williams") and c["capacidad"] * c["k"] >= ob["requerida"] * (1 - 1e-9)
    b = next(ob for ob in o["objetivos"] if ob["clase"] == "bomba")
    uno = next(c for c in b["candidatos"] if c["n"] == 1 and c["k"] == 1)
    dos = next(c for c in b["candidatos"] if c["n"] == 2 and c["k"] == 2)
    assert dos["precio_usd"] == pytest.approx(uno["precio_usd"] * 0.5 ** 0.67)       # Williams con n = 0,67 de la bomba (Turton)
    v = next(ob for ob in o["objetivos"] if ob["clase"] == "estanque")
    assert v["dianas"][0].startswith("TK ")


def test_auxiliares_eleccion_queda_en_la_planta_y_se_deshace():
    pl = _agrozzi(); h = LZ.Historial(30)
    o = EA.objetivos(pl, AX.auxiliares(pl), buscar_en_linea=False)["objetivos"]
    c = o[0]["candidatos"][1]
    assert EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=o[0]["id"], candidato=c["id"])), o)["ok"]
    assert EA.elecciones(pl)[o[0]["id"]]["id"] == c["id"]
    est = EA.estado(pl, o)
    assert est["n_elegidos"] == 1 and est["C"] == pytest.approx(c["C"]) and est["A_sist"] == pytest.approx(c["A"])
    assert not EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=o[1]["id"], candidato=c["id"])), o)["ok"]
    r = EA.generar_automaticamente(pl, h, o)
    assert r["cambio"] and EA.estado(pl, o)["n_elegidos"] == len(o)
    assert EA.estado(pl, o)["C"] == pytest.approx(EA.estado(pl, o)["C_min"])
    copia = LZ.restaurar(agrozzi.crear(), LZ.instantanea(pl))                 # la elección viaja con la planta guardada
    assert len(EA.elecciones(copia)) == len(o)
    EV.deshacer(pl, h); EV.deshacer(pl, h); pl.resolver()
    assert EA.elecciones(pl) == {} and pl.resuelta


def test_auxiliares_usan_referencia_equipos_si_existe(monkeypatch):
    falso = types.ModuleType("pat_sim.datos.referencia_equipos")

    def candidatos(tipo, capacidad, unidad, en_linea=True, secretos=None):
        if tipo != "bomba_centrifuga":
            return []
        return [dict(modelo="Modelo de prueba", fabricante="Fabricante de prueba", capacidad=150.0, unidad=unidad, precio_usd=9000.0,
                     origen="Respaldo", url="https://ejemplo.cl/ficha", fuente="Ficha de prueba")]
    falso.candidatos = candidatos
    monkeypatch.setitem(sys.modules, "pat_sim.datos.referencia_equipos", falso)
    import pat_sim.datos as D
    monkeypatch.setattr(D, "referencia_equipos", falso, raising=False)
    pl = _agrozzi()
    o = EA.objetivos(pl, AX.auxiliares(pl), buscar_en_linea=False)["objetivos"]
    b = next(ob for ob in o if ob["clase"] == "bomba" and ob["requerida"] > 150)
    reales = [c for c in b["candidatos"] if c["modelo"] == "Modelo de prueba"]
    assert {c["n"] for c in reales} == {2, 3} and all(c["k"] == 2 and c["origen"] == "Respaldo" for c in reales)


def test_auxiliares_sin_resolver_avisan():
    pl = agrozzi.crear(); pl.resuelta = False
    o = EA.objetivos(pl, None)
    assert o["objetivos"] == [] and "Resuelva" in o["avisos"][0]
