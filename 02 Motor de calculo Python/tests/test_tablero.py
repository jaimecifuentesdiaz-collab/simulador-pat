"""Pruebas de los tableros como los de FlexSim (PAT 134): estados por equipo, OEE, histograma, SVG y exportación."""
import copy
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import operacion as OP
from pat_sim.motor import tablero as TB

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
H = OP.S["horas_turno"]


def _operar(m, n=9):
    pl = m.crear(); op = OP.Operacion(rubro=pl.rubro, semilla=OP.semilla_texto("escenario"))
    for i in range(n):
        OP.correr_turno(op, pl, 0.9, None, "preventivo" if i == 4 else "ninguno")
    return pl, op


@pytest.fixture(scope="module")
def operadas():
    return {k: _operar(m) for k, m in ESCENARIOS.items()}


def test_horas_de_un_turno_a_mano():
    # falla: 8 × (1 − 0,36) = 5,12 h; queda 2,88 h; meta 90 %: 0,288 h programada; producido / capacidad = 0,5
    h = TB.horas_turno(dict(meta=0.9, falla=True, alerta=False, mantenimiento="ninguno", capacidad=100.0, producido=50.0))
    assert h["falla"] == pytest.approx(5.12) and h["programada"] == pytest.approx(0.288)
    assert h["materia_prima"] == pytest.approx(1.296) and h["produccion"] == pytest.approx(1.296)
    assert sum(v for k, v in h.items() if k != "total") == pytest.approx(H)


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_estados_suman_las_horas_del_turno(operadas, rubro):
    pl, op = operadas[rubro]; e = TB.estados_turnos(op.turnos, pl, OP.linea(pl))
    assert e["equipos"] and e["horas"] == pytest.approx(H * len(op.turnos))
    for pt in e["por_turno"]:
        for k in e["equipos"]:
            assert sum(pt["estados"][k].values()) == pytest.approx(H, abs=1e-9)
            assert all(v >= -1e-12 for v in pt["estados"][k].values())
    for k in e["equipos"]:
        assert sum(e["total"][k].values()) == pytest.approx(H * len(op.turnos))
        assert 0 <= e["utilizacion"][k] <= 1


def test_critico_lleva_falla_y_mantenimiento(operadas):
    pl, op = operadas["tomate"]; e = TB.estados_turnos(op.turnos, pl, OP.linea(pl)); c = e["critico"]
    con_falla = [i for i, r in enumerate(op.turnos) if r["falla"] or r["alerta"]]
    con_mant = [i for i, r in enumerate(op.turnos) if r["mantenimiento"] != "ninguno"]
    assert con_falla and con_mant and c == "W4"
    for i in con_falla:
        assert e["por_turno"][i]["estados"][c]["falla"] > 0
    for i in con_mant:
        assert e["por_turno"][i]["estados"][c]["mantenimiento"] == pytest.approx(H * (1 - OP.S["f_mant"]))
    for k in e["equipos"]:
        if k != c:
            assert e["total"][k]["falla"] == 0 and e["total"][k]["mantenimiento"] == 0


def test_bloqueado_aguas_arriba_y_esperando_aguas_abajo(operadas):
    pl, op = operadas["tomate"]; e = TB.estados_turnos(op.turnos, pl, OP.linea(pl))
    arriba = set(e["aguas_arriba"]); abajo = [k for k in e["equipos"] if k not in arriba and k != e["critico"]]
    assert {"F1", "Z1", "W1", "F2", "W2", "W3"} <= arriba and {"W5", "B2", "A1"} <= set(abajo)
    for k in arriba & set(e["equipos"]):
        assert e["total"][k]["bloqueado"] > 0
    for k in abajo:
        assert e["total"][k]["bloqueado"] == 0 and e["total"][k]["esperando"] > 0


def test_falta_de_materia_prima_es_esperando_para_todos():
    pl = agrozzi.crear(); ln = OP.linea(pl)
    reg = dict(turno=1, meta=1.0, falla=False, alerta=False, mantenimiento="ninguno", capacidad=100.0, producido=40.0, critico=ln["critico"])
    e = TB.estados_turnos([reg], pl, ln)
    for k in e["equipos"]:
        assert e["total"][k]["esperando"] >= 0.6 * H - 1e-9


def test_oee_de_los_turnos(operadas):
    pl, op = operadas["pellet"]; ln = OP.linea(pl); o = TB.oee_operacion(op.turnos, ln)
    hs = [TB.horas_turno(r) for r in op.turnos]
    A = sum(h["produccion"] for h in hs) / sum(h["total"] - h["programada"] for h in hs)
    Q = sum(r["conforme"] for r in op.turnos) / sum(r["producido"] for r in op.turnos)
    assert o["disponibilidad"] == pytest.approx(A) and o["calidad"] == pytest.approx(Q)
    assert o["oee"] == pytest.approx(o["disponibilidad"] * o["rendimiento"] * o["calidad"])
    assert 0 < o["oee"] <= 1 and TB.oee_operacion([], ln) is None


def test_histograma_y_permanencia():
    h = TB.histograma([0, 1, 2, 3, 4, 5, 6, 7], clases=4)
    assert h["conteos"] == [2, 2, 2, 2] and h["bordes"][0] == 0 and h["bordes"][-1] == 7 and h["media"] == pytest.approx(3.5)
    assert len(TB.histograma(list(range(16)))["conteos"]) == 5          # Sturges: 1 + log2(16) = 5
    hp = TB.histograma([1.0, 3.0], pesos=[3, 1], clases=2)
    assert hp["conteos"] == [3, 1] and hp["media"] == pytest.approx(1.5)
    p = TB.permanencia([2.0, 4.0, 6.0])
    assert p["media"] == pytest.approx(4) and p["minimo"] == 2 and p["maximo"] == 6 and p["desviacion"] == pytest.approx(2)


def test_esperas_con_y_sin_esperas_h():
    ll = dict(dias=[dict(camiones=2, espera_media_h=1.0), dict(camiones=0, espera_media_h=0.0), dict(camiones=1, espera_media_h=4.0)])
    v, w, aviso = TB.esperas(ll)
    assert v == [1.0, 4.0] and w == [2.0, 1.0] and aviso
    v, w, aviso = TB.esperas(dict(ll, esperas_h=[0.5, 1.5]))
    assert v == [0.5, 1.5] and w is None and aviso is None


def test_svg_validos():
    filas = [("A", dict(operando=5, bloqueado=2, detenido=1)), ("B", dict(operando=3, esperando=5))]
    svgs = [TB.barras_apiladas_svg(filas, "Prueba"), TB.torta_svg(dict(operando=6, falla=2), "Torta"), TB.torta_svg({}, "Vacía"),
            TB.gantt_svg([("A", [(0, 4, "operando"), (4, 8, "falla")])], 8, "Gantt", escala=8, eje="Turno"),
            TB.histograma_svg(TB.histograma([1, 2, 2, 3]), "Histograma"), TB.lineas_svg([1, 2, 3], {"x": [1, 4, 9]}, "Líneas", "a", "b"),
            TB.barras_svg(["A", "B"], [0.5, 0.9], "Utilización", resaltar="B")]
    for s in svgs:
        assert s.startswith("<svg") and s.endswith("</svg>") and s.count("<svg") == 1
    assert TB.COLOR_ESTADO["falla"] in svgs[0] or TB.COLOR_ESTADO["falla"] in svgs[1]
    assert "Bloqueado" in svgs[0] and "Operando" in svgs[0]                  # leyenda


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_todos_los_graficos_y_exportacion(operadas, rubro):
    pl, op = operadas[rubro]
    ctx = TB.contexto(pl, op.turnos)
    ws = TB.construir_todos([i for i, *_ in TB.CATALOGO], ctx)
    assert len(ws) == len(TB.CATALOGO)
    for w in ws:
        svgs = [w["svg"]] if isinstance(w["svg"], str) else (w["svg"] or [])
        assert svgs or w["tabla"] or w["tarjetas"] or w["avisos"], w["id"]
        for s in svgs:
            assert s.startswith("<svg") and s.endswith("</svg>")
    sin = [w["id"] for w in ws if w["avisos"] and not (w["svg"] or w["tabla"] or w["tarjetas"])]
    assert sin == ([] if rubro != "tomate" else ["din_secado"])
    h = TB.exportar_html(ws)
    assert h.startswith("<!doctype html>") and h.endswith("</html>") and h.count("<svg") >= len(TB.CATALOGO) - 3
    assert "Tiempo en cada estado por equipo" in h and "Reglas de los estados" in h
    c = TB.exportar_csv(ws)
    assert "Estados por equipo (h)" in c and ";" in c


def test_exportar_html_varios_tableros_y_csv():
    h = TB.exportar_html({"Uno": [dict(id="x", grupo="Estado", titulo="Gráfico <a>", svg="<svg></svg>", avisos=["ojo"])], "Dos": []})
    assert "<h2>Uno</h2>" in h and "<h2>Dos</h2>" in h and "Gráfico &lt;a&gt;" in h and "ojo" in h
    c = TB.exportar_csv({"Tabla": [dict(a=1.5, b="x;y", c=None, d=True)]})
    assert c.splitlines()[:3] == ["Tabla", "a;b;c;d", '1,5;"x;y";;sí']


def test_sin_turnos_avisa(operadas):
    pl = agrozzi.crear(); ctx = TB.contexto(pl, [], necesita={"operacion"})
    w = TB.construir("estado_barras", ctx)
    assert w["svg"] is None and w["avisos"]
    with pytest.raises(KeyError):
        TB.construir("no_existe", ctx)


def test_temporada_gantt_y_produccion():
    pl = pellet.crear(); pr, ll = TB.simular_temporada(pl)
    g = TB.gantt_linea(pr); hl = TB.horas_linea(pr)
    assert sum(hl.values()) == pytest.approx(pr["horas_totales"]) and hl["produccion"] == pytest.approx(pr["horas_efectivas"])
    assert all(b <= c + 1e-9 for (_a, b, _s), (c, _d, _t) in zip(g, g[1:]))
    d = TB.produccion_temporada(pr)
    assert d[-1]["acumulada_t"] == pytest.approx(pr["produccion_programa_t"]) and len(ll["por_hora"]) == 24 * pr["dias"]
    pr2, _ = TB.simular_temporada(pl, extra_llegadas=dict(argumento_que_no_existe=1))   # se ignora si la función no lo acepta
    assert pr2["horas_efectivas"] == pr["horas_efectivas"]


# ----------------------------------------------------------------------------------------------- PAT 134: línea con estados reales
from pat_sim.motor import linea_fluida as LF

LINEA_IDS = [i for i, g, _t, _f in TB.CATALOGO if g == TB.GRUPO_LINEA]


@pytest.fixture(scope="module")
def lineas():
    out = {}
    for k, m in ESCENARIOS.items():
        pl = m.crear(); pl.resolver(); out[k] = (pl, LF.simular_linea(pl, horas=72, semilla=3))
    return out


def test_grupo_linea_en_la_biblioteca():
    assert TB.GRUPO_LINEA in TB.GRUPOS and len(LINEA_IDS) == 6
    assert set(LINEA_IDS) == set(TB.catalogo_por_grupo()[TB.GRUPO_LINEA]) and all(TB.FUENTE[i] == "linea" for i in LINEA_IDS)
    # los colores de los estados de la línea son los mismos de los tableros
    assert all(LF.COLOR_ESTADO[k] == TB.COLOR_ESTADO[v] for k, v in TB.MAPA_LINEA.items()) and set(TB.MAPA_LINEA) == set(LF.ESTADOS)


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_estados_linea_con_horas_reales(lineas, rubro):
    pl, r = lineas[rubro]; e = TB.estados_linea(r)
    assert e["equipos"] == [x["id"] for x in r["equipos"]] and e["horas"] == pytest.approx(72.0)
    for k in e["equipos"]:
        assert sum(e["total"][k].values()) == pytest.approx(72.0)
        for s_l, s_t in TB.MAPA_LINEA.items():
            assert e["total"][k][s_t] == pytest.approx(r["por_equipo"][k]["horas_por_estado"][s_l])
        tr = e["tramos"][k]
        assert tr[0][0] == pytest.approx(0.0) and tr[-1][1] == pytest.approx(72.0)
        assert all(b[0] == pytest.approx(a[1]) for a, b in zip(tr, tr[1:]))
    uno = e["equipos"][:1]
    assert TB.estados_linea(r, uno)["equipos"] == uno and TB.estados_linea(r, ["no_existe"])["equipos"] == e["equipos"]


def test_permanencia_linea_a_mano():
    r = dict(equipos=[dict(id="E1", nombre="Uno", capacidad_t_h=10.0)], parametros=dict(horas=10.0, rubro="x"),
             tramos=[dict(equipo="E1", estado="operando", inicio_h=0.0, fin_h=2.0), dict(equipo="E1", estado="en_falla", inicio_h=2.0, fin_h=3.0),
                     dict(equipo="E1", estado="operando", inicio_h=3.0, fin_h=7.0), dict(equipo="E1", estado="en_falla", inicio_h=7.0, fin_h=10.0)],
             tiempo_h=[0.0, 10.0], por_equipo={})
    f = {x["estado"]: x for x in TB.permanencia_linea(r)}
    assert f["Operando"]["tramos"] == 2 and f["Operando"]["media"] == pytest.approx(3.0)
    assert f["Operando"]["minimo"] == pytest.approx(2.0) and f["Operando"]["maximo"] == pytest.approx(4.0)
    assert f["En falla"]["media"] == pytest.approx(2.0) and f["En falla"]["horas"] == pytest.approx(4.0)
    assert f["Operando"]["desviacion"] == pytest.approx(2 ** 0.5)
    assert set(f) == {"Operando", "En falla"}


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_graficos_de_la_linea_en_los_cuatro_rubros(lineas, rubro):
    pl, r = lineas[rubro]
    ctx = TB.contexto(pl, [], necesita={"linea"}, linea=r)
    assert ctx["linea"] is r
    ws = TB.construir_todos(LINEA_IDS, ctx)
    for w in ws:
        svgs = [w["svg"]] if isinstance(w["svg"], str) else (w["svg"] or [])
        assert (svgs or w["tabla"] or w["tarjetas"]) and not [a for a in w["avisos"] if "No se pudo" in a], w["id"]
        assert all(s.startswith("<svg") and s.endswith("</svg>") for s in svgs) and w["datos"]
    w = {x["id"]: x for x in ws}
    assert len(w["linea_tasas"]["svg"]) == len(r["equipos"])
    assert len(w["linea_niveles"]["svg"]) == len([t for t in r["tanques"] if not t["anulado"]])
    assert "horas son reales" in w["linea_barras"]["nota"] and "reglas" in w["linea_barras"]["nota"]
    tj = {t["nombre"]: t["valor"] for t in w["linea_oee"]["tarjetas"]}
    assert tj["OEE de la línea"] == pytest.approx(r["oee"]) and tj["OEE respecto del recurso crítico"] == pytest.approx(r["oee_critico"])
    h = TB.exportar_html(ws)
    assert h.count("<svg") >= 3 + len(r["equipos"]) and "<i>ticks</i>" in h and "Staytime" in h
    assert "Tramos de estado de la línea" in TB.exportar_csv(ws)


def test_oee_de_la_linea_comparable_con_los_turnos(operadas, lineas):
    pl_t, op = operadas["tomate"]; pl, r = lineas["tomate"]
    o = TB.oee_operacion(op.turnos, OP.linea(pl_t))
    # misma tasa ideal: la producción planificada de la planta
    assert r["tasa_planificada_t_h"] == pytest.approx(OP.linea(pl)["plan"]) and o is not None
    assert r["oee_detalle"]["tasa_ideal_t_h"] == pytest.approx(OP.linea(pl_t)["plan"])


def test_contexto_linea_sin_resultado_otro_rubro_o_simulada():
    pl = pellet.crear(); pl.resolver()
    ctx = TB.contexto(pl, [], necesita={"linea"}, simular_linea=False)
    assert ctx["linea"] is None and "Línea" in ctx["avisos"]["linea"]
    w = TB.construir("linea_gantt", ctx)
    assert w["svg"] is None and w["avisos"]
    otro = chip.crear(); otro.resolver(); r_otro = LF.simular_linea(otro, horas=4, fallas=False)
    ctx = TB.contexto(pl, [], necesita={"linea"}, linea=r_otro, simular_linea=False)
    assert ctx["linea"] is None and "otro rubro" in ctx["avisos"]["linea"]
    ctx = TB.contexto(pl, [], necesita={"linea"})            # sin resultado: 72 h con los valores por defecto
    assert ctx["linea"]["parametros"]["horas"] == pytest.approx(72.0) and ctx["linea"]["parametros"]["rubro"] == "pellet"


# ----------------------------------------------------------------------------------------------- PAT 134 (04-11-2026): biblioteca visual
def test_miniaturas_svg_validas_para_toda_la_biblioteca():
    import xml.dom.minidom as M
    assert set(TB.FICHA) == set(TB.TITULO)
    for i in TB.TITULO:
        s = TB.miniatura_svg(i)
        assert s.startswith("<svg") and s.endswith("</svg>") and s.count("<svg") == 1
        M.parseString(s)                                     # XML bien formado
        assert 'viewBox="0 0 160 100"' in s and "<text" not in s       # dibujo sin cifras
        assert TB.descripcion(i) and TB.ayuda_grafico(i)
    assert TB.COLOR_ESTADO["falla"] in TB.miniatura_svg("estado_gantt_turnos")
    assert TB.COLOR_LINEA["limpieza"] in TB.miniatura_svg("estado_gantt_temporada")
    with pytest.raises(KeyError):
        TB.miniatura_svg("no_existe")


def test_plantillas_solo_usan_graficos_existentes():
    assert list(TB.PLANTILLAS)[0] == "Vacío" and TB.PLANTILLAS["Vacío"][1] == []
    for nombre, (desc, ids) in TB.PLANTILLAS.items():
        assert desc and all(i in TB.TITULO for i in ids) and len(ids) == len(set(ids))
        t = TB.tablero_nuevo(nombre)
        assert TB.ids_tablero(t) == ids and t["columnas"] == 2
    assert any(TB.FUENTE[i] == "linea" for i in TB.PLANTILLAS["Línea"][1])


def test_biblioteca_por_categoria_y_buscador():
    cats = TB.biblioteca_por_categoria()
    assert list(cats) == ["Estado", "Producción", "Contenido", "Permanencia", "Indicadores", "Dinámica", "Línea"]
    assert sum(len(v) for v in cats.values()) == len(TB.CATALOGO)
    assert TB.buscar_graficos("torta") == ["estado_torta", "estado_gantt_temporada"]
    assert set(TB.buscar_graficos("OEE")) == {"ind_oee", "linea_oee"}
    assert TB.buscar_graficos("linea gantt") == TB.buscar_graficos("LÍNEA  Gantt")        # sin tildes ni mayúsculas
    assert "linea_niveles" in TB.buscar_graficos("tanque") and TB.buscar_graficos("xyz") == []
    assert len(TB.buscar_graficos("")) == len(TB.CATALOGO)


def test_migracion_del_formato_anterior():
    T = TB.normalizar_tableros({"Viejo": ["estado_barras", "no_existe", "estado_barras", "estado_gantt_turnos"], "Otro": []})
    assert list(T) == ["Viejo", "Otro"]
    assert T["Viejo"] == dict(graficos=[dict(id="estado_barras", ancho="medio"), dict(id="estado_gantt_turnos", ancho="completo")], columnas=2)
    assert TB.normalizar_tableros(None) == {TB.TABLERO_INICIAL: TB.tablero_nuevo(TB.POR_DEFECTO)}
    assert TB.normalizar_tablero(dict(graficos=[dict(id="ind_oee", ancho="raro")], columnas="1")) == dict(
        graficos=[dict(id="ind_oee", ancho="medio")], columnas=1)
    assert TB.normalizar_tableros(T) == T                    # idempotente


def test_agregar_mover_ancho_quitar_y_grilla():
    t = TB.tablero_nuevo(["ind_oee", "ind_utilizacion", "estado_gantt_turnos", "prod_acum_turnos"])
    assert [[g["id"] for g in f] for f in TB.filas_grilla(t)] == [["ind_oee", "ind_utilizacion"], ["estado_gantt_turnos"], ["prod_acum_turnos"]]
    assert TB.agregar_grafico(t, "estado_barras") and not TB.agregar_grafico(t, "estado_barras") and not TB.agregar_grafico(t, "x")
    assert [[g["id"] for g in f] for f in TB.filas_grilla(t)][-1] == ["prod_acum_turnos", "estado_barras"]
    assert TB.mover_grafico(t, "estado_barras", -1) and TB.ids_tablero(t)[-2:] == ["estado_barras", "prod_acum_turnos"]
    assert not TB.mover_grafico(t, "ind_oee", -1) and not TB.mover_grafico(t, "prod_acum_turnos", 1)
    assert TB.alternar_ancho(t, "ind_oee") == "completo" and TB.alternar_ancho(t, "ind_oee") == "medio"
    assert len(TB.filas_grilla(t, 1)) == len(t["graficos"])
    assert TB.quitar_grafico(t, "estado_gantt_turnos") and not TB.quitar_grafico(t, "estado_gantt_turnos")
    assert TB.nombre_libre("Tablero", ["Tablero", "Tablero (2)"]) == "Tablero (3)" and TB.nombre_libre("  ", []) == "Tablero"


def test_exportar_html_respeta_el_ancho():
    w = [dict(TB._w("ind_oee", avisos=["a"]), ancho="completo"), TB._w("ind_utilizacion", avisos=["b"])]
    h = TB.exportar_html({"T": w}, "Prueba", 2)
    assert h.count('style="grid-column:1/-1"') == 1
