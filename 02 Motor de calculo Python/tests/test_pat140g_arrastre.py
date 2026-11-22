"""PAT 140 g (pedido de Jaime, 17-11-2026): el candidato se suelta en cualquier lugar libre del lienzo (se aplica a su equipo, que queda
ahí), sobre otro equipo de la misma clase si su capacidad calza (±20 %), y las bombas se reconectan a otra línea
(motor/eleccion_viva.py, motor/eleccion_auxiliares.py y motor/lienzo.capa_auxiliares)."""
import json
import pytest
from pat_sim.motor import (lienzo as LZ, seleccion as S, costo_total as CT, auxiliares as AX, eleccion_viva as EV,
                           eleccion_auxiliares as EA, tres_opciones as T3)
from pat_sim.escenarios import agrozzi


def _agrozzi():
    pl = agrozzi.crear()
    if not pl.resuelta:
        pl.resolver()
    return pl


def _objs(pl):
    return EA.objetivos(pl, EA.aplicar_lineas(pl, AX.auxiliares(pl)), buscar_en_linea=False)["objetivos"]


def _bombas(objs):
    return [o for o in objs if o["clase"] == "bomba"]


def test_calza_mas_menos_20_por_ciento():
    assert EV.calza(243, 219, "m³/h")[0] and EV.calza(100, 120)[0] and EV.calza(120, 100)[0]
    ok, motivo = EV.calza(243, 123.4, "m³/h")
    assert not ok and "sobredimensionado" in motivo and "20 %" in motivo and "m³/h" in motivo
    ok, motivo = EV.calza(70, 100)
    assert not ok and "le falta" in motivo


def test_nombre_largo_de_cada_auxiliar():
    pl = _agrozzi()
    b = _bombas(_objs(pl))[0]
    assert b["nombre_largo"] == "Bomba P-101 de la línea 1, de B1 Recepción de tomate a F1 Lavado y selección"
    assert b["con"] and b["ctx"]["horas"] > 0
    assert EA.con_articulo(b["nombre_largo"]).startswith("la bomba P-101")


def test_soltar_en_lugar_libre_aplica_y_deja_el_simbolo_ahi_en_un_paso():
    pl = _agrozzi(); h = LZ.Historial(30); o = _objs(pl); b = _bombas(o)[0]; c = b["candidatos"][0]
    r = EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=b["id"], candidato=c["id"], pos=dict(x=310.4, y=505), diana=b["id"])), o)
    assert r["ok"] and "Bomba P-101".lower() in r["mensaje"].lower() and "B1 Recepción de tomate" in r["mensaje"] and "donde lo soltó" in r["mensaje"]
    assert EA.posiciones(pl) == {b["id"]: dict(x=310.4, y=505.0)} and EA.elecciones(pl)[b["id"]]["id"] == c["id"]
    assert h.resumen()["deshacer"] == 1
    capa = LZ.capa_auxiliares(pl, AX.auxiliares(pl))
    assert next(x for x in capa["bombas"] if x["id"] == b["id"])["pos"] == dict(x=310.4, y=505.0)
    EV.deshacer(pl, h); pl.resolver()
    assert EA.posiciones(pl) == {} and EA.elecciones(pl) == {}


def test_mover_auxiliar_y_volver_a_su_linea():
    pl = _agrozzi(); h = LZ.Historial(30); o = _objs(pl); v = next(x for x in o if x["clase"] == "valvula")
    assert EA.procesar_evento(pl, h, dict(evento="mover_aux", datos=dict(id=v["id"], pos=dict(x=40, y=60))), o)["ok"]
    assert EA.posiciones(pl)[v["id"]] == dict(x=40.0, y=60.0)
    r = EA.procesar_evento(pl, h, dict(evento="mover_aux", datos=dict(id=v["id"], pos=None)), o)
    assert r["ok"] and EA.posiciones(pl) == {} and h.resumen()["deshacer"] == 2


def test_soltar_sobre_otra_bomba_que_calza_y_sobre_una_que_no():
    pl = _agrozzi(); h = LZ.Historial(30); o = _objs(pl); bs = _bombas(o)
    c = next(x for x in bs[0]["candidatos"] if x["n"] == 2 and x["k"] == 1)          # 243 m³/h
    calza = next(x for x in bs[1:] if abs(c["capacidad"] / x["requerida"] - 1) <= 0.2)
    r = EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=bs[0]["id"], candidato=c["id"], destino=calza["id"])), o)
    assert r["ok"] and calza["id"] in r["mensaje"] and bs[0]["id"] not in EA.elecciones(pl)
    g = EA.elecciones(pl)[calza["id"]]
    assert g["modelo"] == c["modelo"] and g["n"] == c["n"] and g["C"] != pytest.approx(c["C"])   # el mismo equipo, evaluado en su nueva línea
    no = next(x for x in bs if c["capacidad"] / x["requerida"] > 1.2)
    r = EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=bs[0]["id"], candidato=c["id"], destino=no["id"])), o)
    assert not r["ok"] and "sobredimensionado" in r["mensaje"] and no["id"] not in EA.elecciones(pl)
    tk = next(x for x in o if x["clase"] == "estanque")
    r = EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=bs[0]["id"], candidato=c["id"], destino=tk["id"])), o)
    assert not r["ok"] and "otro tipo" in r["mensaje"]


def test_reconectar_bomba_intercambia_lineas_y_recalcula():
    pl = _agrozzi(); h = LZ.Historial(30); o = _objs(pl); bs = _bombas(o)
    a, b = bs[0], bs[2]
    assert EA.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo=a["id"], candidato=a["candidatos"][0]["id"])), o)["ok"]
    C0 = EA.elecciones(pl)[a["id"]]["C"]
    tot0 = AX.auxiliares(pl)
    r = EA.procesar_evento(pl, h, dict(evento="conectar_aux", datos=dict(id=a["id"], con=b["con"], pos=dict(x=500, y=300))), o)
    assert r["ok"] and f"{a['id']} ahora sirve la línea {b['linea']}" in r["mensaje"] and f"{b['id']} pasa a la línea {a['linea']}" in r["mensaje"]
    assert EA.lineas(pl) == {a["id"]: b["con"]}
    aux = EA.aplicar_lineas(pl, AX.auxiliares(pl))
    fa = next(f for f in aux["bombas"]["filas"] if f["id"] == a["id"])
    fb = next(f for f in aux["bombas"]["filas"] if f["id"] == b["id"])
    assert fa["linea"] == b["linea"] and fb["linea"] == a["linea"]
    assert fa["Q_m3h"] == pytest.approx(b["requerida"]) and fb["Q_m3h"] == pytest.approx(a["requerida"])
    assert aux["bombas"]["total_kw"] == pytest.approx(tot0["bombas"]["total_kw"]) and aux["total_usd"] == pytest.approx(tot0["total_usd"])
    o2 = EA.objetivos(pl, aux, buscar_en_linea=False)["objetivos"]
    na = next(x for x in o2 if x["id"] == a["id"])
    assert na["con"] == b["con"] and na["requerida"] == pytest.approx(b["requerida"])
    assert EA.elecciones(pl)[a["id"]]["C"] != pytest.approx(C0)             # la elección se evaluó otra vez con la nueva línea
    capa = LZ.capa_auxiliares(pl, aux)
    assert next(x for x in capa["bombas"] if x["id"] == a["id"])["con"] == b["con"]
    # y de vuelta: cada bomba en su línea original
    o3 = EA.objetivos(pl, aux, buscar_en_linea=False)["objetivos"]
    assert EA.procesar_evento(pl, h, dict(evento="conectar_aux", datos=dict(id=a["id"], con=a["con"])), o3)["ok"]
    aux2 = EA.aplicar_lineas(pl, AX.auxiliares(pl))
    assert [f["id"] for f in aux2["bombas"]["filas"]] == [f["id"] for f in tot0["bombas"]["filas"]]
    EV.deshacer(pl, h); EV.deshacer(pl, h); pl.resolver()
    assert EA.lineas(pl) == {} and EA.posiciones(pl) == {}


def test_reconectar_valvula_o_linea_sin_bomba_avisa():
    pl = _agrozzi(); h = LZ.Historial(30); o = _objs(pl)
    v = next(x for x in o if x["clase"] == "valvula"); b = _bombas(o)[0]
    r = EA.procesar_evento(pl, h, dict(evento="conectar_aux", datos=dict(id=v["id"], con=b["con"], pos=dict(x=1, y=2))), o)
    assert not r["ok"] and "Solo las bombas" in r["mensaje"] and EA.posiciones(pl)[v["id"]] == dict(x=1.0, y=2.0)
    r = EA.procesar_evento(pl, h, dict(evento="conectar_aux", datos=dict(id=b["id"], con="no.existe>X.y")), o)
    assert not r["ok"] and "no lleva bomba" in r["mensaje"] and EA.lineas(pl) == {}


def test_planta_real_soltar_en_lugar_libre_mueve_la_etapa_en_un_paso():
    pl = _agrozzi(); h = LZ.Historial(30)
    c = {r["equipo"]: CT.candidatos_etapa(pl, r["equipo"], None, False) for r in S.requerimientos(pl)}
    cid = c["F1"][0]["id"]
    r = EV.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo="F1", candidato=cid, pos=dict(x=413, y=618))), c)
    assert r["ok"] and "etapa F1 Lavado y selección" in r["mensaje"] and (pl.equipos["F1"].x, pl.equipos["F1"].y) == (420, 620)
    assert h.resumen()["deshacer"] == 1 and S.seleccion_actual(pl.equipos["F1"]) is not None
    r = EV.procesar_evento(pl, h, dict(evento="elegir", datos=dict(objetivo="F1", candidato=cid, destino="W1")), c)
    assert not r["ok"] and "otro tipo de equipo" in r["mensaje"]


def test_planta_real_adaptar_a_otra_etapa_del_mismo_tipo():
    pl = _agrozzi()
    c = {r["equipo"]: CT.candidatos_etapa(pl, r["equipo"], None, False) for r in S.requerimientos(pl)}
    reqs = {r["equipo"]: r for r in S.requerimientos(pl)}
    base = dict(c["W3"][0])
    base["equipo"] = "W2"                                        # un candidato de W2 que calza en W3 (mismo tipo, misma capacidad)
    base["modelo"] = base["modelo"] + " (copia)"                 # no está en la lista de W3: se evalúa con seleccion.evaluar
    c2, motivo = EV.adaptar_candidato(pl, base, "W3", c)
    assert c2 is not None and motivo == "" and c2["equipo"] == "W3" and c2["n"] == base["n"] and c2["C"] > 0
    assert c2["id"].startswith("W3|")
    grande = dict(base, capacidad=reqs["W3"]["requerida"] * 2 / max(1, base["k"]))
    assert EV.adaptar_candidato(pl, grande, "W3", c)[0] is None


def test_ficha_sin_referencias_al_curso():
    pl = _agrozzi()
    res = T3.candidatos_tres(pl, "F1", None, False)
    f = T3.ficha_etapa(pl, "F1", res["tres"], None)
    txt = json.dumps(f, ensure_ascii=False).lower()
    assert "profesor" not in txt and "torres" not in txt
