"""Pruebas del simulador de planta de la pestaña Diseño (pat_sim.motor.lienzo, PAT 128): eventos del lienzo,
resolución tolerante y teoría de restricciones (capacidad efectiva, recurso crítico y acumulación)."""
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.escenarios import agrozzi, pellet
from pat_sim.motor import lienzo as LZ
from pat_sim.catalogos.registro import RUBROS, catalogo


@pytest.fixture()
def pl():
    p = agrozzi.crear(); p.resolver(); return p


def ev(pl, evento, **datos):
    return LZ.aplicar_evento(pl, dict(evento=evento, datos=datos, seq=1))


def test_agregar_con_letra_iso_y_grilla(pl):
    r = ev(pl, "agregar", tipo="trituradora", x=333, y=507)
    assert r["ok"] and r["id"] == "Z2" and r["recalcular"]
    assert (pl.equipos["Z2"].x, pl.equipos["Z2"].y) == (340, 500)


def test_mover_no_recalcula(pl):
    r = ev(pl, "mover", id="W1", x=611, y=95)
    assert r["ok"] and not r["recalcular"] and (pl.equipos["W1"].x, pl.equipos["W1"].y) == (620, 100)


def test_conectar_tipos_ciclo_y_numero(pl):
    ev(pl, "agregar", tipo="trituradora", x=300, y=500)
    r = ev(pl, "conectar", origen="F1", puerto_origen="descarte", destino="Z2", puerto_destino="entrada")
    assert r["ok"] and pl.conexiones[-1].nombre == "17" and pl.conexiones[-1].reparto == 100
    assert not ev(pl, "conectar", origen="D1", puerto_origen="vapor", destino="Z2", puerto_destino="entrada")["ok"]     # incompatible
    assert not ev(pl, "conectar", origen="F1", puerto_origen="descarte", destino="Z2", puerto_destino="entrada")["ok"]  # repetida
    n = len(pl.conexiones)
    assert not ev(pl, "conectar", origen="A1", puerto_origen="producto", destino="F1", puerto_destino="entrada")["ok"]  # ciclo
    assert len(pl.conexiones) == n
    sol, motivo = LZ.resolver_parcial(pl)
    assert motivo is None and pl.equipos["Z2"].resultado.detalle["carga_t_h"] == pytest.approx(pl.equipos["B1"].resultado.detalle["carga_t_h"] * 0.1)


def test_parametro_y_capacidad_opcional(pl):
    assert ev(pl, "parametro", id="W1", clave="T_salida", valor=96)["ok"]
    pl.resolver()
    assert pl.equipos["W1"].resultado.detalle["Q_kW"] == pytest.approx(17428.9, abs=0.05)   # la misma cifra que la prueba de la interfaz
    assert ev(pl, "parametro", id="W1", clave="T_salida", valor=500)["ok"] and pl.equipos["W1"].v("T_salida") == 100   # se acota al rango
    assert ev(pl, "parametro", id="W3", clave="capacidad", valor=100)["ok"] and pl.equipos["W3"].v("capacidad") == 100
    assert ev(pl, "parametro", id="W3", clave="capacidad", valor=None)["ok"] and pl.equipos["W3"].v("capacidad") is None
    assert not ev(pl, "parametro", id="W4", clave="brix_salida", valor=0.2)["ok"]          # lo calcula la especificación


def test_quitar_conexion_y_equipo(pl):
    clave = "W5.producto>B2.entrada"
    assert ev(pl, "quitar_conexion", clave=clave)["ok"]
    sol, motivo = LZ.resolver_parcial(pl)
    assert "no tiene alimentación" in motivo and not pl.resuelta and sol is not None
    assert "W1" in sol.equipos and "A1" not in sol.equipos and pl.equipos["W1"].resultado is not None   # la parte alimentada sigue
    n = len(pl.instrumentos)
    assert ev(pl, "quitar_equipo", id="W5")["ok"] and "W5" not in pl.equipos
    assert all(c.origen != "W5" and c.destino != "W5" for c in pl.conexiones) and len(pl.instrumentos) <= n


def test_restriccion_y_acumulacion(pl):
    assert ev(pl, "capacidades", holgura=10, solo_vacias=False)["ok"]   # reemplaza las de partida (PAT 132)
    assert pl.equipos["W1"].v("capacidad") == pytest.approx(244.3)
    ev(pl, "parametro", id="W3", clave="capacidad", valor=100)
    sol, _ = LZ.resolver_parcial(pl)
    tr = LZ.restricciones(pl, sol)
    assert tr["restrictivo"] == "W3" and tr["limitantes"] == ["W3"]
    w3 = tr["equipos"]["W3"]
    assert w3["procesado"] == pytest.approx(100) and w3["sobrecarga"] == pytest.approx(w3["demanda"] - 100)
    assert tr["produccion_real"] == pytest.approx(tr["produccion_plan"] * 100 / w3["demanda"])
    ev(pl, "parametro", id="W3", clave="estado", valor=0.5)           # capacidad efectiva = nominal × estado
    tr = LZ.restricciones(pl, LZ.resolver_parcial(pl)[0])
    assert tr["equipos"]["W3"]["efectiva"] == pytest.approx(50)
    curva = LZ.curva_linea(pl, pl)
    assert curva[-1][1] == pytest.approx(curva[25][1])                 # sobre el cuello de botella la producción se aplana


def test_secuencia_sugerida_conecta_lo_que_falta(pl):
    pl.conexiones = [c for c in pl.conexiones if c.destino not in ("W2", "W5")]
    assert ev(pl, "secuencia")["ok"]
    assert any(c.origen == "F2" and c.puerto_origen == "jugo" and c.destino == "W2" for c in pl.conexiones)
    assert any(c.origen == "D1" and c.destino == "W5" for c in pl.conexiones)
    LZ.resolver_parcial(pl); assert pl.resuelta


def test_datos_lienzo_serializables_y_rubros():
    cat = LZ.catalogo_lienzo(RUBROS, catalogo)
    for p in (agrozzi.crear(), pellet.crear()):
        sol, motivo = LZ.resolver_parcial(p)
        d = LZ.datos_lienzo(p, sol, motivo, cat)
        json.dumps(d)
        assert d["resuelta"] and len(d["equipos"]) == len(p.equipos) and d["kpis"]["produccion_t_h"] > 0
        assert d["diagnostico"][0]["nivel"] in ("ok", "aviso")


def test_consumo_especifico_suma_electricidad(pl):
    e0 = pl.servicio_total("electricidad_kW")
    ev(pl, "parametro", id="Z1", clave="consumo_especifico", valor=2.0)
    pl.resolver()
    assert pl.servicio_total("electricidad_kW") == pytest.approx(e0 + 2.0 * pl.equipos["Z1"].resultado.detalle["carga_t_h"])


def test_escenarios_traen_capacidad_de_partida_con_semaforo():
    """PAT 132: cada escenario base trae capacidad nominal, la barra se llena con la utilización y el recurso crítico es el
    equipo más caro (evaporador Venus en la pasta, secador en la biomasa); sin capacidades el balance es el mismo."""
    from pat_sim.escenarios import chip, lena, capacidades as CAP
    for mod, critico in ((agrozzi, "W4"), (pellet, "T1"), (chip, "T1"), (lena, "T1")):
        p = mod.crear(); sol, _ = LZ.resolver_parcial(p); tr = LZ.restricciones(p, sol)
        assert set(CAP.HOLGURAS[p.rubro]) <= set(p.equipos)
        con = {k: v for k, v in tr["equipos"].items() if v["util_demanda"] is not None}
        assert set(con) == {k for k in CAP.HOLGURAS[p.rubro] if "capacidad" in p.equipos[k].params}
        assert tr["restrictivo"] == critico and tr["limitantes"] == []
        for k, v in con.items():
            assert 0 < v["util_real"] <= 1 and v["util_real"] == pytest.approx(v["util_demanda"])
            assert v["util_demanda"] == pytest.approx(1 / (1 + CAP.HOLGURAS[p.rubro][k]), rel=0.03)   # redondeo a 0,1 t/h
            assert p.equipos[k].params["capacidad"].categoria == "Supuesto"
        assert tr["produccion_real"] == pytest.approx(tr["produccion_plan"])
        q = mod.crear(capacidades=False)
        assert all(not e.params["capacidad"].valor for e in q.equipos.values() if "capacidad" in e.params)
        assert q.servicio_total("electricidad_kW") == pytest.approx(p.servicio_total("electricidad_kW"))


def test_todos_los_equipos_iso_10628_primero_en_el_catalogo(pl):
    """PAT 132: la opción «Todos los equipos (ISO 10628)» va primera, tiene un equipo por símbolo de la norma (las 24
    categorías de la Tabla C.1) y los genéricos dejan pasar la corriente con su electricidad y cierran el balance."""
    from pat_sim.catalogos.registro import TIPOS
    from pat_sim.simbolos import iso10628
    cat = LZ.catalogo_lienzo(RUBROS, catalogo)
    assert list(cat)[0] == "todos" and len(cat["todos"]["equipos"]) == len(TIPOS)
    assert {e["simbolo_nombre"] for e in cat["todos"]["equipos"]} >= {v[0] for v in iso10628.SIMBOLOS.values()} - {""}
    assert {e["categoria"] for e in cat["todos"]["equipos"]} == set(range(1, 25))
    assert all(not k.startswith("iso_") for r in RUBROS for k in [e["tipo"] for e in cat[r]["equipos"]])   # no ensucia los rubros
    eq = TIPOS["iso_bomba_centrifuga"]("P1"); eq.set("energia_especifica", 2.0)
    e = pl.salidas[("A1", "producto")]
    r = eq.calcular({"entrada": e})
    assert r.salidas["salida"].m == pytest.approx(e.m) and r.servicios["electricidad_kW"] == pytest.approx(2.0 * e.m / 1000)
    assert abs(r.cierre_energia()) < 1e-9
    r = ev(pl, "agregar", tipo="iso_valvula_control", x=100, y=500)
    assert r["ok"] and r["id"] in pl.equipos and r["id"].startswith("H")          # letra de la válvula de control (Anexo D.3)


# ---------------------------------------------------------------- PAT 133: deshacer, rehacer y copiar en el lienzo

def test_historial_tope_y_rehacer_se_vacia():
    h = LZ.Historial(tope=3)
    for i in range(5):
        assert h.apilar(f"e{i}", f"cambio {i}", ahora=10.0 * i)
    assert len(h.atras) == 3 and h.atras[0][0] == "e2"                      # el tope descarta los más antiguos
    assert h.deshacer("actual") == ("e4", "cambio 4") and h.puede_rehacer
    assert h.rehacer("e4") == ("actual", "cambio 4") and not h.puede_rehacer
    h.deshacer("actual"); assert h.puede_rehacer
    h.apilar("otro", "cambio nuevo", ahora=100.0)
    assert not h.puede_rehacer                                               # un cambio nuevo vacía rehacer
    assert h.resumen()["deshacer"] == 3 and h.resumen()["etiqueta_deshacer"] == "cambio nuevo"
    vacio = LZ.Historial()
    assert vacio.deshacer("x") is None and vacio.rehacer("x") is None


def test_historial_agrupa_un_deslizador():
    h = LZ.Historial(tope=30, ventana=2.0)
    assert h.apilar("a", "T", grupo=("parametro", "W1", "T"), ahora=0.0)
    assert not h.apilar("b", "T", grupo=("parametro", "W1", "T"), ahora=1.0)    # mismo deslizador: un solo paso
    assert h.apilar("c", "T", grupo=("parametro", "W1", "T"), ahora=10.0)       # pasó la ventana: paso nuevo
    assert h.apilar("d", "x", grupo=("parametro", "W2", "x"), ahora=10.5)
    assert [e for e, _ in h.atras] == ["a", "c", "d"]


def test_deshacer_y_rehacer_eventos_en_la_planta(pl):
    h = LZ.Historial(tope=30)
    t0 = pl.equipos["W1"].v("T_salida"); n0 = len(pl.equipos); c0 = len(pl.conexiones)
    hp = lambda evento, **d: LZ.aplicar_con_historial(pl, dict(evento=evento, datos=d, seq=1), h)
    assert hp("parametro", id="W1", clave="T_salida", valor=96)["ok"]
    assert hp("agregar", tipo="trituradora", x=300, y=500)["ok"]
    assert hp("conectar", origen="F1", puerto_origen="descarte", destino="Z2", puerto_destino="entrada")["ok"]
    assert hp("mover", id="W1", x=pl.equipos["W1"].x, y=pl.equipos["W1"].y)["ok"]       # no cambia nada: no se apila
    assert not hp("conectar", origen="D1", puerto_origen="vapor", destino="Z2", puerto_destino="entrada")["ok"]   # error: no se apila
    assert len(h.atras) == 3
    w1 = pl.equipos["W1"]
    r = hp("deshacer"); assert r["ok"] and r["recalcular"] and "conectar" in r["mensaje"]
    assert len(pl.conexiones) == c0 and "Z2" in pl.equipos and pl.equipos["W1"] is not w1
    hp("deshacer"); hp("deshacer")
    assert len(pl.equipos) == n0 and pl.equipos["W1"].v("T_salida") == t0 and not hp("deshacer")["ok"]
    LZ.resolver_parcial(pl); assert pl.resuelta
    hp("rehacer"); hp("rehacer"); hp("rehacer")
    assert pl.equipos["W1"].v("T_salida") == 96 and len(pl.conexiones) == c0 + 1 and not hp("rehacer")["ok"]
    hp("deshacer"); hp("quitar_equipo", id="Z2")
    assert not h.puede_rehacer                                                # el cambio nuevo vació rehacer


def test_deshacer_conserva_categoria_y_fuente(pl):
    h = LZ.Historial()
    LZ.aplicar_con_historial(pl, dict(evento="capacidades", datos=dict(holgura=10, solo_vacias=False)), h)
    cat = pl.equipos["W1"].params["capacidad"].categoria; fte = pl.equipos["W1"].params["capacidad"].fuente
    LZ.aplicar_con_historial(pl, dict(evento="parametro", datos=dict(id="W1", clave="T_salida", valor=96)), h)
    LZ.aplicar_con_historial(pl, dict(evento="deshacer", datos={}), h)
    p = pl.equipos["W1"].params["capacidad"]
    assert p.categoria == cat and p.fuente == fte and p.valor == pytest.approx(244.3)


def test_duplicar_equipos_letra_iso_parametros_sin_conexiones_externas(pl):
    pl.equipos["W1"].set("T_salida", 93.0); pl.equipos["W1"].set("capacidad", 300.0, categoria="Supuesto", fuente="prueba PAT 133")
    c0 = len(pl.conexiones)
    mapa = LZ.duplicar_equipos(pl, ["W1"], 100, 90)
    nid = mapa["W1"]
    assert nid == "W6"                                                        # letra ISO del evaporador, número siguiente
    a, b = pl.equipos["W1"], pl.equipos[nid]
    assert type(a) is type(b) and b.nombre == a.nombre and (b.x, b.y) == (round((a.x + 100) / 20) * 20, round((a.y + 90) / 20) * 20)
    assert b.v("T_salida") == 93.0 and b.params["capacidad"].fuente == "prueba PAT 133" and b.params is not a.params
    b.set("T_salida", 80.0); assert a.v("T_salida") == 93.0                   # copia independiente
    assert len(pl.conexiones) == c0                                           # sin conexiones externas
    # dos equipos conectados entre sí: la conexión interna sí se copia, con número nuevo
    m2 = LZ.duplicar_equipos(pl, ["F2", "W2"], 0, 400)
    internas = [c for c in pl.conexiones if c.origen == m2["F2"] and c.destino == m2["W2"]]
    assert len(internas) == 1 and internas[0].nombre not in {c.nombre for c in pl.conexiones if c is not internas[0]}
    assert all(c.destino not in m2.values() or c.origen in m2.values() for c in pl.conexiones)
    with pytest.raises(ValueError):
        LZ.duplicar_equipos(pl, ["NO_EXISTE"])
    r = ev(pl, "duplicar", ids=["A1"], dx=100, dy=100)
    assert r["ok"] and r["recalcular"] and r["id"].startswith("A") and r["ids"] == [r["id"]]


@pytest.mark.parametrize("modulo", ["agrozzi", "pellet", "chip", "lena"])
def test_instantanea_restaurar_y_duplicar_en_los_cuatro_rubros(modulo):
    import importlib
    mod = importlib.import_module(f"pat_sim.escenarios.{modulo}")
    p = mod.crear(); LZ.resolver_parcial(p)
    s0 = LZ.instantanea(p); json.loads(s0)
    k = next(iter(p.equipos))
    h = LZ.Historial()
    assert LZ.aplicar_con_historial(p, dict(evento="duplicar", datos=dict(ids=[k])), h)["ok"]
    assert len(h.atras) == 1 and LZ.instantanea(p) != s0
    LZ.aplicar_con_historial(p, dict(evento="deshacer", datos={}), h)
    assert LZ.instantanea(p) == s0
    sol, motivo = LZ.resolver_parcial(p)
    assert motivo is None and p.resuelta
