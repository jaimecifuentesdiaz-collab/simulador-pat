"""PAT 142: lazos de control en el lienzo (tarea 5 del plan PAT 141). Lazos típicos de cinco variables en los cuatro rubros, números
consecutivos, señales creadas, datos mínimos de ISA-5.4, relaciones entre lazos (cascada por defecto entre controladores), revisión
de los lazos, eventos de la vista «lazos», planta vacía y guardado y carga (proyectos nuevos y viejos sin los campos nuevos)."""
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import lienzo as LZ, instrumentacion as IN, flujo as FL
from pat_sim.motor.planta import Planta, Instrumento
from pat_sim.simbolos import isa54
from pat_sim.catalogos.registro import planta_desde_dict
from pat_sim.datos.bd import (BaseDatos, planta_a_dict, a_json, planta_completa_a_dict, planta_completa_desde_dict, partida_a_json,
                              leer_partida)

ESCENARIOS = dict(agrozzi=agrozzi, pellet=pellet, chip=chip, lena=lena)
# equipo con corriente de servicio de cada rubro (W1 hot break con vapor; T1 secador con calor)
EQUIPO = dict(agrozzi="W1", pellet="T1", chip="T1", lena="T1")
LETRAS = dict(temperatura=["TE", "TT", "TIC", "TY", "TV"], presion=["PT", "PIC", "PY", "PV"], nivel=["LT", "LIC", "LY", "LV"],
              caudal=["FE", "FT", "FIC", "FY", "FV"], concentracion=["AT", "AIC", "AY", "AV"])


def ev(pl, evento, **datos):
    return LZ.aplicar_evento(pl, dict(evento=evento, datos=datos, seq=1))


def senales(pl):
    return {(IN.ident(i), s["tipo"], s["destino"]): s for i in pl.instrumentos for s in i.conexiones}


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
@pytest.mark.parametrize("variable", list(IN.TIPICOS))
def test_agregar_lazo_cinco_tipos_cuatro_rubros(rubro, variable):
    pl = ESCENARIOS[rubro].crear(); eq = EQUIPO[rubro]; antes = len(pl.instrumentos)
    r = IN.agregar_lazo(pl, variable, eq)
    n = r["numero"]
    assert r["instrumentos"] == [f"{l}-{n}" for l in LETRAS[variable]]
    assert len(pl.instrumentos) == antes + len(LETRAS[variable])
    assert r["mensaje"].startswith(f"Agregado el lazo {n} de control de {IN.NOMBRE_TIPICO[variable]} en {eq} ")
    assert f"{LETRAS[variable][-2]}-{n} y {LETRAS[variable][-1]}-{n}" in r["mensaje"]
    S = senales(pl); le = LETRAS[variable]; v = le[0][0]
    ctl, tr, ip, fin = f"{v}IC-{n}", f"{v}T-{n}", f"{v}Y-{n}", f"{v}V-{n}"
    med = f"{v}E-{n}" if f"{v}E" in le else tr
    assert S[(med, "equipo", eq)]["senal"] == "proceso"
    assert S[(tr, "instrumento", ctl)]["senal"] == "electrica"
    assert S[(ctl, "instrumento", ip)]["senal"] == "electrica"
    assert S[(ip, "instrumento", fin)]["senal"] == "neumatica"
    cor = [k for k in S if k[0] == fin]
    assert len(cor) == 1 and cor[0][1] == "corriente" and S[cor[0]]["senal"] == "proceso"
    c = next(x for x in pl.conexiones if IN.clave_corriente(x) == cor[0][2])
    assert c.destino == eq and pl.es_servicio(c)              # la válvula actúa sobre el servicio del equipo
    I = {IN.ident(i): i for i in pl.instrumentos}
    assert I[ctl].elemento_final == fin and I[ctl].accion == "inversa" and I[fin].accion_falla == "FC"
    assert I[tr].alimentacion == "24 V c.c." and I[ip].alimentacion == "aire AS 20 psig" and I[ctl].alimentacion == "L1, L2, G"
    assert all(I[x].equipo == eq for x in r["instrumentos"])
    assert all(x % 10 == 0 for i in r["instrumentos"] for x in (I[i].x, I[i].y))      # grilla de 10
    # un lazo típico recién puesto no tiene errores de la revisión
    assert not [x for x in IN.revisar_lazos(pl) if x["lazo"] == n and x["nivel"] == "error"]


def test_parametro_y_consigna_del_equipo():
    pl = agrozzi.crear()
    r = IN.agregar_lazo(pl, "temperatura", "W1")
    assert r["parametro"] == "T_salida"
    ctl = IN.buscar(pl, r["controlador"])
    assert ctl.parametro == "T_salida" and ctl.consigna.endswith("°C") and "," in ctl.consigna
    r2 = IN.agregar_lazo(pl, "concentracion", "W2")
    assert r2["parametro"] == "brix_salida" and IN.buscar(pl, r2["controlador"]).consigna.endswith("°Brix")
    r3 = IN.agregar_lazo(pl, "nivel", "W1")                          # el hot break no tiene nivel: Propiedades lo pide
    assert r3["parametro"] is None and "Propiedades" in r3["mensaje"]
    with pytest.raises(ValueError):
        IN.agregar_lazo(pl, "temperatura", "W1", parametro="no_existe")


def test_numeros_consecutivos_y_sin_encimarse():
    pl = agrozzi.crear()
    nums = [IN.agregar_lazo(pl, v, "W1")["numero"] for v in ("temperatura", "presion", "temperatura")]
    assert nums == ["502", "503", "504"]                 # la planta basada en Agrozzi llega hasta el lazo 501
    vacia = Planta("x", "tomate"); vacia.agregar(agrozzi.crear().equipos["W1"])
    assert [IN.agregar_lazo(vacia, "caudal", "W1")["numero"] for _ in range(3)] == ["101", "102", "103"]
    pos = [(IN.ident(i), i.x, i.y) for i in pl.instrumentos if IN.lazo_de(i) in nums]
    for a in pos:
        for b in pos:
            if a[0] != b[0]:
                assert abs(a[1] - b[1]) >= 44 or abs(a[2] - b[2]) >= 44, (a, b)
    with pytest.raises(ValueError):
        IN.agregar_lazo(pl, "temperatura", "W1", numero="502")          # TIC-502 ya existe
    with pytest.raises(ValueError):
        IN.agregar_lazo(pl, "viscosidad", "W1")
    with pytest.raises(ValueError):
        IN.agregar_lazo(pl, "temperatura", "")


def test_agregar_lazo_todo_o_nada():
    pl = agrozzi.crear(); antes = a_json(planta_a_dict(pl))
    with pytest.raises(ValueError):
        IN.agregar_lazo(pl, "temperatura", "W1", corriente="no.existe>W1.vapor")
    assert a_json(planta_a_dict(pl)) == antes


def test_relacion_por_defecto_y_editar_relacion():
    pl = agrozzi.crear()
    a = IN.agregar_lazo(pl, "temperatura", "W1"); b = IN.agregar_lazo(pl, "presion", "W4")
    clave = IN.conectar(pl, a["controlador"], "instrumento", b["controlador"], "electrica")
    s = senales(pl)[(a["controlador"], "instrumento", b["controlador"])]
    assert s["relacion"] == "cascada"                                   # controlador a controlador
    pre = IN.conectar(pl, f"TT-{a['numero']}", "instrumento", b["controlador"], "electrica")
    assert senales(pl)[(f"TT-{a['numero']}", "instrumento", b["controlador"])]["relacion"] == "prealimentacion"
    IN.conectar(pl, f"TY-{a['numero']}", "instrumento", f"PV-{b['numero']}", "neumatica")
    assert "relacion" not in senales(pl)[(f"TY-{a['numero']}", "instrumento", f"PV-{b['numero']}")]     # resto: sin relación (campo opcional)
    assert "relacion" not in senales(pl)[(f"TT-{a['numero']}", "instrumento", a["controlador"])]          # mismo lazo
    IN.editar_senal(pl, clave, {"relacion": "razon"})
    assert senales(pl)[(a["controlador"], "instrumento", b["controlador"])]["relacion"] == "razon"
    r = ev(pl, "senal", clave=pre, relacion="enclavamiento")
    assert r["ok"] and senales(pl)[(f"TT-{a['numero']}", "instrumento", b["controlador"])]["relacion"] == "enclavamiento"
    assert not ev(pl, "senal", clave=clave, relacion="otra")["ok"]
    interna = IN.clave_senal(f"TT-{a['numero']}", dict(tipo="instrumento", destino=a["controlador"]))
    with pytest.raises(ValueError):
        IN.editar_senal(pl, interna, {"relacion": "cascada"})
    IN.editar_senal(pl, clave, {"relacion": None})
    assert "relacion" not in senales(pl)[(a["controlador"], "instrumento", b["controlador"])]
    assert [r["tipo"] for r in IN.relaciones(pl) if r["senal"] == clave] == [None]


def test_relaciones_y_lazos_lienzo():
    pl = agrozzi.crear()
    a = IN.agregar_lazo(pl, "temperatura", "W1"); b = IN.agregar_lazo(pl, "presion", "W4")
    assert IN.relaciones(pl) == []
    clave = IN.conectar(pl, a["controlador"], "instrumento", b["controlador"])
    rel = IN.relaciones(pl)
    assert rel == [dict(lazo_origen=a["numero"], lazo_destino=b["numero"], tipo="cascada", nombre="cascada", senal=clave,
                        origen=a["controlador"], destino=b["controlador"])]
    L = {x["numero"]: x for x in IN.lazos_lienzo(pl)}
    la = L[a["numero"]]
    assert la["titulo"] == f"Lazo {a['numero']} · control de temperatura" and la["controlador"] == "TIC"
    assert la["miembros"] == a["instrumentos"] and la["relaciones"][0]["lazo"] == b["numero"] and la["relaciones"][0]["sentido"] == "sale"
    assert L[b["numero"]]["relaciones"][0]["sentido"] == "llega"
    pos = IN.posiciones(pl)
    cj = la["caja"]
    for i in la["miembros"]:                          # la caja encierra a sus miembros
        x, y, _ = pos[i]
        assert cj["x"] < x < cj["x"] + cj["ancho"] and cj["y"] < y < cj["y"] + cj["alto"]
    assert len({x["color"] for x in L.values()}) > 1
    assert L["101"]["titulo"] == "Lazo 101 · control de temperatura"          # lazos resumidos de la planta basada en Agrozzi
    # datos del lienzo: relación en la línea
    d = {x["id"]: x for x in IN.datos(pl)}
    s = next(x for x in d[a["controlador"]]["conexiones"] if x["destino"] == b["controlador"])
    assert s["entre_lazos"] and s["relacion"] == "cascada" and s["relacion_nombre"] == "cascada"
    assert d[f"TV-{a['numero']}"]["es_final"] and d[a["controlador"]]["es_controlador"] and d[a["controlador"]]["lazo"] == a["numero"]


def test_revisar_lazo_correcto_y_roto():
    pl = agrozzi.crear()
    a = IN.agregar_lazo(pl, "temperatura", "W1"); n = a["numero"]
    assert not [x for x in IN.revisar_lazos(pl) if x["nivel"] == "error"]
    # lazos resumidos de la planta basada en Agrozzi (un solo instrumento sin líneas): solo avisos
    assert {x["nivel"] for x in IN.revisar_lazos(agrozzi.crear())} == {"aviso"}
    # se rompe: sin la señal del controlador al I/P, sin la válvula sobre la corriente, I/P con señal eléctrica a la válvula
    IN.quitar_senal(pl, IN.clave_senal(f"TIC-{n}", dict(tipo="instrumento", destino=f"TY-{n}")))
    tv = IN.buscar(pl, f"TV-{n}"); tv.conexiones.clear(); tv.accion_falla = ""
    IN.editar_senal(pl, IN.clave_senal(f"TY-{n}", dict(tipo="instrumento", destino=f"TV-{n}")), {"senal": "electrica"})
    rev = [x for x in IN.revisar_lazos(pl) if x["lazo"] == n]
    err = [x for x in rev if x["nivel"] == "error"]
    assert {x["objeto"] for x in err} >= {f"TV-{n}", f"TY-{n}"}
    assert all(x["pista"] and x["mensaje"] and x["fuente"] for x in rev)
    assert any("no llega con una señal al elemento final" in x["mensaje"] for x in err)
    assert any("no actúa sobre ninguna corriente" in x["mensaje"] for x in err)
    assert any("debe recibir señal eléctrica y entregar señal neumática" in x["mensaje"] for x in err)
    assert any(x["nivel"] == "aviso" and "acción en falla" in x["mensaje"] for x in rev)
    # sin medición y con primera letra distinta
    pl2 = agrozzi.crear(); b = IN.agregar_lazo(pl2, "presion", "W4"); m = b["numero"]
    IN.quitar(pl2, f"PT-{m}")
    IN.editar(pl2, f"PV-{m}", {"letras": "FV"})
    rev2 = [x for x in IN.revisar_lazos(pl2) if x["lazo"] == m]
    assert any(x["nivel"] == "error" and "no tiene medición" in x["mensaje"] for x in rev2)
    assert any(x["nivel"] == "aviso" and "distintas primeras letras" in x["mensaje"] for x in rev2)
    # un elemento final con dos señales de mando: aviso
    pl3 = agrozzi.crear(); c = IN.agregar_lazo(pl3, "temperatura", "W1"); k = c["numero"]
    IN.conectar(pl3, f"TIC-{k}", "instrumento", f"TV-{k}", "electrica")
    assert any(x["nivel"] == "aviso" and "señales de mando" in x["mensaje"] for x in IN.revisar_lazos(pl3))


def test_planta_vacia_aviso_y_no_falla():
    pl = Planta("vacía", "tomate")
    rev = IN.revisar_lazos(pl)
    assert len(rev) == 1 and rev[0]["nivel"] == "aviso" and rev[0]["pista"]
    assert IN.relaciones(pl) == [] and IN.lazos_lienzo(pl) == []
    r = ev(pl, "agregar_lazo", variable="temperatura", equipo="W1")
    assert not r["ok"] and "No existe el equipo W1" in r["mensaje"]
    r = ev(pl, "agregar_lazo", variable="temperatura", equipo="")
    assert not r["ok"] and "Suelte el lazo típico sobre un equipo" in r["mensaje"]
    d = LZ.datos_lienzo(pl, None, None, LZ.catalogo_lazos(), vista="lazos")
    assert d["lazos"] == [] and d["solo_lectura"] and d["editar_instrumentos"]


def test_eventos_en_la_vista_lazos():
    pl = agrozzi.crear(); h = LZ.Historial(30)
    r = LZ.aplicar_con_historial(pl, dict(evento="agregar_lazo", datos=dict(variable="temperatura", equipo="W5"), seq=1), h)
    assert r["ok"] and r["id"] == f"TIC-{r['numero']}" and r["sel"] == "ins" and h.puede_deshacer
    assert r["mensaje"] == (f"Agregado el lazo {r['numero']} de control de temperatura en W5 {pl.equipos['W5'].nombre}: "
                            f"TE-{r['numero']}, TT-{r['numero']}, TIC-{r['numero']}, TY-{r['numero']} y TV-{r['numero']}.")
    assert LZ.etiqueta_evento(dict(evento="agregar_lazo", datos=dict(variable="temperatura", equipo="W5"))) == "agregar el lazo típico de temperatura en W5"
    r2 = ev(pl, "agregar_lazo", variable="presion", equipo="W4")
    c = ev(pl, "conectar_senal", origen=r["id"], tipo="instrumento", destino=r2["id"], senal="electrica")
    assert c["ok"] and IN.relaciones(pl)[0]["tipo"] == "cascada"
    e = ev(pl, "instrumento", id=f"TV-{r['numero']}", accion_falla="fo", alimentacion="aire AS 20 psig")
    assert e["ok"] and IN.buscar(pl, f"TV-{r['numero']}").accion_falla == "FO"
    e = ev(pl, "instrumento", id=r["id"], accion="directa", consigna="95 °C")
    assert e["ok"] and IN.buscar(pl, r["id"]).accion == "directa" and IN.buscar(pl, r["id"]).consigna == "95 °C"
    antes = IN.buscar(pl, r["id"]).letras
    assert not ev(pl, "instrumento", id=r["id"], letras="TRC", accion="lateral")["ok"]               # todo o nada
    assert IN.buscar(pl, r["id"]).letras == antes
    assert not ev(pl, "instrumento", id=f"TV-{r['numero']}", accion_falla="XX")["ok"]
    assert not ev(pl, "instrumento", id=r["id"], consigna="x" * 41)["ok"]
    # deshacer vuelve atrás el lazo típico
    LZ.aplicar_con_historial(pl, dict(evento="deshacer", datos={}, seq=9), h)
    assert not any(IN.lazo_de(i) == r["numero"] and i.letras == "TE" for i in pl.instrumentos)
    # datos del lienzo en la vista «lazos»
    pl = agrozzi.crear(); IN.agregar_lazo(pl, "temperatura", "W1")
    cat = LZ.catalogo_lazos()
    assert list(cat) == ["lazos"] and [t["variable"] for t in cat["lazos"]["tipicos"]] == list(IN.TIPICOS)
    assert cat["lazos"]["equipos"] == [] and len({c["grupo"] for c in cat["lazos"]["instrumentos"]}) == 4
    d = LZ.datos_lienzo(pl, pl, None, cat, vista="lazos")
    assert d["vista"] == "lazos" and d["solo_lectura"] is True and d["editar_instrumentos"] is True
    assert "real" not in d and "auxiliares" not in d and len(d["lazos"]) == 7
    assert set(d["isa"]["relaciones"]) == {"cascada", "razon", "prealimentacion", "enclavamiento"}
    assert set(d["isa"]["acciones_falla"]) == {"FC", "FO", "FL", "FI"}
    f = LZ.datos_lienzo(pl, pl, None, cat, vista="ficticia")
    assert f["editar_instrumentos"] is True and "lazos" not in f and f["solo_lectura"] is False
    assert "lazos" in LZ.VISTAS and set(LZ.EVENTOS_LAZOS) >= {"agregar_lazo", "conectar_senal", "senal", "mover_instrumento"}


def test_diagrama_isa54_rotula_datos_minimos():
    svg = isa54.lazo_svg("TIC", "502", "Control de temperatura de W1", "W1", "dcs", "JB-1", "4-20 mA", accion_falla="FC",
                         alimentacion={"transmisor": "24 V c.c.", "controlador": "L1, L2, G", "convertidor": "aire AS 20 psig"},
                         accion="inversa", consigna="95,0 °C", relaciones=["Cascada con el lazo 503 (TIC-502 → PIC-503)"], final="TV-502")
    for t in ("FC", "24 V c.c.", "L1, L2, G", "aire AS 20 psig", "Acción inversa", "Consigna 95,0 °C", "Relación con otros lazos",
              "Cascada con el lazo 503 (TIC-502 → PIC-503)", "Control de temperatura de W1", "TV-502"):
        assert t in svg
    assert 'height="416"' in svg
    assert isa54.lazo_svg("TIC", "101") == isa54.lazo_svg("TIC", "101", accion_falla="", alimentacion={}, relaciones=[])


def _comparable(pl):
    return [(IN.ident(i), i.accion_falla, i.alimentacion, i.accion, i.consigna, i.x, i.y,
             sorted(json.dumps(s, sort_keys=True) for s in i.conexiones)) for i in pl.instrumentos]


def test_guardado_y_carga_con_relaciones():
    pl = agrozzi.crear()
    a = IN.agregar_lazo(pl, "temperatura", "W1"); b = IN.agregar_lazo(pl, "presion", "W4")
    IN.conectar(pl, a["controlador"], "instrumento", b["controlador"])
    ref, rel = _comparable(pl), IN.relaciones(pl)
    # instantánea y restaurar (deshacer y rehacer)
    otra = agrozzi.crear(); LZ.restaurar(otra, LZ.instantanea(pl))
    assert _comparable(otra) == ref and IN.relaciones(otra) == rel
    # planta completa (guardado automático y versiones) y partida .json
    pc = planta_completa_desde_dict(json.loads(a_json(planta_completa_a_dict(pl))))
    assert _comparable(pc) == ref and IN.relaciones(pc) == rel
    pj = leer_partida(partida_a_json(pl, {"pagina": "Lazos de control"}, "prueba"))["planta"]
    assert _comparable(pj) == ref and IN.relaciones(pj) == rel
    # base de datos: proyecto del usuario
    bd = BaseDatos(":memory:")
    g = bd.guardar_proyecto_usuario(pl, "Proyecto de prueba de lazos")
    pb = bd.cargar_proyecto_usuario(g["id"])["planta"]
    assert _comparable(pb) == ref and IN.relaciones(pb) == rel


def test_proyectos_viejos_sin_campos_nuevos():
    pl = agrozzi.crear(); IN.agregar_lazo(pl, "temperatura", "W1"); a = IN.agregar_lazo(pl, "presion", "W4")
    IN.conectar(pl, "TIC-502", "instrumento", a["controlador"])
    d = json.loads(a_json(planta_a_dict(pl)))
    for i in d["instrumentos"]:                      # como se guardaban antes de PAT 142
        for c in ("accion_falla", "alimentacion", "accion", "consigna"):
            i.pop(c)
        for s in i["conexiones"]:
            s.pop("relacion", None)
    viejo = planta_desde_dict(d)
    assert all(i.accion_falla == "" and i.alimentacion == "" and i.accion == "" and i.consigna == "" for i in viejo.instrumentos)
    assert [r["tipo"] for r in IN.relaciones(viejo)] == [None] and IN.relaciones(viejo)[0]["nombre"] == "sin relación"
    IN.datos(viejo); IN.lazos_lienzo(viejo); IN.revisar_lazos(viejo)          # no fallan
    LZ.datos_lienzo(viejo, None, None, LZ.catalogo_lazos(), vista="lazos")
    # un instrumento de PAT 133 (sin x, y, símbolo ni conexiones) también
    v = Instrumento(**dict(letras="TIC", numero="101", equipo="W1", ubicacion="dcs", descripcion="", parametro=None, elemento_final="TV-101"))
    assert v.accion_falla == "" and v.conexiones == []


def test_cifras_de_agrozzi_intactas_con_lazos():
    p0 = agrozzi.crear(); p0.resolver(); r0 = agrozzi.resumen(p0)      # misma cantidad de resoluciones en las dos plantas
    pl = agrozzi.crear()
    for v in IN.TIPICOS:
        IN.agregar_lazo(pl, v, "W1")
    pl.resolver(); r1 = agrozzi.resumen(pl)
    for k in ("M0", "P", "xV"):
        assert r1[k] == r0[k]


def test_pantalla_renombrada_en_el_flujo():
    assert FL.etapa(6).nombre == "Lazos de control"
    assert FL.pagina_de_etapa(6, {"Lazos de control", "Costeo"}) == "Lazos de control"
    assert FL.pagina_de_etapa(6, {"Instrumentación", "Costeo"}) == "Instrumentación"      # índice antiguo
    assert FL.etapa_de_pagina("Lazos de control") == 6 == FL.etapa_de_pagina("Instrumentación")
