"""Pruebas de los instrumentos ISA-5.1 y elementos de lazo ISA-5.4 en el lienzo de Diseño (PAT 134, equipo G):
catálogo, eventos del lienzo, líneas de señal, historial, carga de versiones antiguas, diagrama de flujo, lazos para la pestaña
Instrumentación, aviso «Mínimo …» de un parámetro acotado y motivo de una especificación imposible en el diagnóstico."""
import json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import lienzo as LZ, instrumentacion as IN
from pat_sim.motor.diagrama import planta_svg
from pat_sim.simbolos import isa51, isa54
from pat_sim.catalogos.registro import RUBROS, catalogo, planta_desde_dict
from pat_sim.datos.bd import planta_a_dict, a_json, planta_desde_json


@pytest.fixture()
def pl():
    return agrozzi.crear()


def ev(pl, evento, **datos):
    return LZ.aplicar_evento(pl, dict(evento=evento, datos=datos, seq=1))


def test_catalogo_isa_completo():
    cat = LZ.catalogo_lienzo(RUBROS, catalogo)
    assert list(cat)[-1] == "isa" and cat["isa"]["nombre"] == "Instrumentación ISA-5.1 y ISA-5.4" and cat["isa"]["equipos"] == []
    ins = cat["isa"]["instrumentos"]
    burb = [c for c in ins if c["grupo"].startswith("Burbujas")]
    assert len(burb) == 16 and {(c["simbolo"], c["ubicacion"]) for c in burb} == {(f, u) for f in isa51.FUNCIONES for u in isa51.LUGARES}
    claves = {c["clave"] for c in ins}
    for k in ("placa_orificio", "termopozo", "valvula_diafragma", "valvula_piston", "valvula_motor", "transmisor", "controlador",
              "convertidor_ip", "caja_conexiones", "regleta_bornes", "fuente_alimentacion", "tarjeta_ai", "tarjeta_ao"):
        assert k in claves
    assert len({c["grupo"] for c in ins}) == 4
    for c in ins:
        assert c["svg"].startswith("<g>") and c["svg"].endswith("</g>") and c["nombre"] and c["letras"] and c["fuente"]
        if c["isa51"]:
            isa51.interpretar(c["letras"])          # las letras por defecto son válidas en la tabla de ISA-5.1


def test_burbujas_por_tipo_y_ubicacion_son_distintas():
    svgs = {isa51.burbuja("TIC", "1", 0, 0, u, 16, f) for f in isa51.FUNCIONES for u in isa51.LUGARES}
    assert len(svgs) == 16
    assert isa51.burbuja("TIC", "1", 0, 0, "dcs") == isa51.burbuja("TIC", "1", 0, 0, "dcs", 16, None)   # lectura anterior intacta
    assert "<rect" in isa51.burbuja("TIC", "1", 0, 0, "panel", 16, "compartido") and "stroke-dasharray" in isa51.burbuja("TI", "1", 0, 0, "detras_panel", 16, "discreto")


def test_lineas_de_senal_y_codigos():
    assert set(isa51.SENALES) >= {"electrica", "neumatica", "datos", "capilar", "hidraulica", "electromagnetica"}
    assert " Q" in isa51.linea(0, 0, 100, 0, "electromagnetica") and 'stroke-dasharray="6 3"' in isa51.linea(0, 0, 100, 0, "electrica")
    assert isa51.linea(0, 0, 100, 0, "neumatica").count("<path") == 5 and isa51.linea(0, 0, 100, 0, "datos").count("<circle") == 2
    assert isa51.validar_codigo("caja_conexiones", "jb2") == "JB2" and isa51.validar_codigo("", "tic") == "TIC"
    with pytest.raises(ValueError):
        isa51.validar_codigo("caja_conexiones", "J-B")
    with pytest.raises(ValueError):
        isa51.validar_codigo("discreto", "TU")                       # U no es letra sucesiva en la tabla


def test_agregar_sobre_equipo_en_el_aire_y_en_una_corriente(pl):
    r = ev(pl, "agregar_instrumento", clave="transmisor", x=None, y=None, equipo="W1")
    assert r["ok"] and r["sel"] == "ins" and r["id"] == "TT-502" and not r["recalcular"]
    t = IN.buscar(pl, "TT-502")
    assert t.equipo == "W1" and t.x is None and t.simbolo == "discreto" and t.ubicacion == "campo"
    x, y, auto = IN.posiciones(pl)["TT-502"]
    assert auto and y == pl.equipos["W1"].y - 30 and x > pl.equipos["W1"].x + 64
    r = ev(pl, "agregar_instrumento", clave="caja_conexiones", x=303, y=47)
    assert r["id"] == "JB-1" and (IN.buscar(pl, "JB-1").x, IN.buscar(pl, "JB-1").y) == (300.0, 50.0)
    assert ev(pl, "agregar_instrumento", clave="caja_conexiones", x=400, y=40)["id"] == "JB-2"
    cor = IN.clave_corriente(pl.conexiones[0])
    r = ev(pl, "agregar_instrumento", clave="placa_orificio", x=100, y=100, corriente=cor)
    assert IN.buscar(pl, r["id"]).conexiones == [dict(senal="proceso", tipo="corriente", destino=cor, parametro=None)]
    assert not ev(pl, "agregar_instrumento", clave="no_existe", x=1, y=1)["ok"]
    assert not ev(pl, "agregar_instrumento", clave="transmisor", x=1, y=1, equipo="Q9")["ok"]


def test_editar_valida_letras_numero_parametro_y_renombra_referencias(pl):
    k = ev(pl, "agregar_instrumento", clave="transmisor", x=None, y=None, equipo="W1")["id"]
    assert ev(pl, "conectar_senal", origen="TIC-101", tipo="instrumento", destino=k, senal="electrica")["ok"]
    r = ev(pl, "instrumento", id=k, letras="tt", numero="101", descripcion="Temperatura de salida", parametro="T_salida")
    assert r["ok"] and r["id"] == "TT-101" and "Temperatura transmisor" in r["mensaje"]
    assert IN.buscar(pl, "TIC-101").conexiones[0]["destino"] == "TT-101"       # la línea sigue llegando con la nueva etiqueta
    assert IN.buscar(pl, "TT-101").parametro == "T_salida" and IN.buscar(pl, "TT-101").descripcion == "Temperatura de salida"
    n = len(pl.instrumentos)
    assert not ev(pl, "instrumento", id="TT-101", letras="T1")["ok"]                      # no es una letra de la tabla
    assert not ev(pl, "instrumento", id="TT-101", letras="TIC")["ok"]                     # TIC-101 ya existe
    assert not ev(pl, "instrumento", id="TT-101", numero="")["ok"]
    assert not ev(pl, "instrumento", id="TT-101", parametro="no_existe")["ok"]
    assert not ev(pl, "instrumento", id="TT-101", ubicacion="luna")["ok"]
    assert len(pl.instrumentos) == n and IN.buscar(pl, "TT-101").letras == "TT"          # todo o nada
    assert ev(pl, "instrumento", id="TT-101", equipo="W4")["ok"] and IN.buscar(pl, "TT-101").parametro is None   # W4 no tiene T_salida
    assert ev(pl, "instrumento", id="TT-101", simbolo="compartido", ubicacion="panel")["ok"]
    assert ev(pl, "instrumento", id="TIC-101", simbolo="plc")["ok"] and IN.buscar(pl, "TIC-101").ubicacion == "panel"   # dcs antiguo → panel
    j = ev(pl, "agregar_instrumento", clave="caja_conexiones", x=10, y=10)["id"]
    assert not ev(pl, "instrumento", id=j, simbolo="discreto")["ok"]                     # una caja no se vuelve burbuja
    assert ev(pl, "instrumento", id=j, letras="jb", numero="7")["ok"] and IN.buscar(pl, "JB-7")


@pytest.mark.parametrize("senal", ["electrica", "neumatica", "datos", "capilar", "hidraulica", "electromagnetica", "proceso"])
def test_conectar_cada_tipo_de_senal(pl, senal):
    r = ev(pl, "conectar_senal", origen="TIC-101", tipo="equipo", destino="W1", senal=senal, parametro="T_salida")
    assert r["ok"] and r["sel"] == "ins"
    s = IN.buscar(pl, "TIC-101").conexiones[-1]
    assert s == dict(senal=senal, tipo="equipo", destino="W1", parametro="T_salida")
    d = LZ.datos_lienzo(pl, pl, None, {})
    c = next(i for i in d["instrumentos"] if i["id"] == "TIC-101")["conexiones"][-1]
    assert c["senal_nombre"] == isa51.SENALES[senal][0] and c["parametro_nombre"] == pl.equipos["W1"].params["T_salida"].nombre


def test_conectar_rechaza_lo_que_no_existe(pl):
    cor = IN.clave_corriente(pl.conexiones[0])
    assert ev(pl, "conectar_senal", origen="FIC-201", tipo="corriente", destino=cor, senal="electrica")["ok"]
    assert "la corriente 1" in ev(pl, "conectar_senal", origen="PIC-301", tipo="corriente", destino=cor, senal="datos")["mensaje"]
    assert ev(pl, "conectar_senal", origen="TIC-101", tipo="instrumento", destino="FIC-201", senal="datos")["ok"]
    for datos in [dict(origen="TIC-101", tipo="instrumento", destino="TIC-101"), dict(origen="TIC-101", tipo="instrumento", destino="FIC-201"),
                  dict(origen="FIC-201", tipo="instrumento", destino="TIC-101"), dict(origen="TIC-101", tipo="equipo", destino="W1", senal="laser"),
                  dict(origen="TIC-101", tipo="equipo", destino="W1", parametro="no_existe"), dict(origen="TIC-101", tipo="corriente", destino="X.a>Y.b"),
                  dict(origen="TIC-101", tipo="corriente", destino=cor, parametro="T_salida"), dict(origen="XX-1", tipo="equipo", destino="W1"),
                  dict(origen="TIC-101", tipo="planeta", destino="W1")]:
        assert not ev(pl, "conectar_senal", **datos)["ok"], datos


def test_editar_y_quitar_senal(pl):
    assert ev(pl, "conectar_senal", origen="TIC-101", tipo="equipo", destino="W1", senal="electrica")["ok"]
    k = IN.clave_senal("TIC-101", IN.buscar(pl, "TIC-101").conexiones[0])
    assert ev(pl, "senal", clave=k, senal="neumatica", parametro="T_salida")["ok"]
    assert IN.buscar(pl, "TIC-101").conexiones[0]["senal"] == "neumatica" and IN.buscar(pl, "TIC-101").conexiones[0]["parametro"] == "T_salida"
    assert not ev(pl, "senal", clave=k, senal="humo")["ok"] and not ev(pl, "senal", clave="no>existe", senal="datos")["ok"]
    assert ev(pl, "quitar_senal", clave=k)["ok"] and IN.buscar(pl, "TIC-101").conexiones == []


def test_quitar_corriente_equipo_o_instrumento_limpia_las_senales(pl):
    c0 = pl.conexiones[0]; cor = IN.clave_corriente(c0)
    ev(pl, "conectar_senal", origen="FIC-201", tipo="corriente", destino=cor, senal="electrica")
    ev(pl, "conectar_senal", origen="FIC-201", tipo="instrumento", destino="PIC-301", senal="datos")
    ev(pl, "conectar_senal", origen="TIC-401", tipo="equipo", destino="W1", senal="electrica")
    assert ev(pl, "quitar_conexion", clave=cor)["ok"]
    assert [s["destino"] for s in IN.buscar(pl, "FIC-201").conexiones] == ["PIC-301"]
    assert ev(pl, "quitar_instrumento", id="PIC-301")["ok"] and IN.buscar(pl, "FIC-201").conexiones == []
    assert ev(pl, "quitar_equipo", id="W1")["ok"] and IN.buscar(pl, "TIC-401").conexiones == []
    assert all(i.equipo != "W1" for i in pl.instrumentos)
    assert not ev(pl, "quitar_instrumento", id="PIC-301")["ok"]


def test_mover_instrumento_y_seguir_al_equipo(pl):
    k = ev(pl, "agregar_instrumento", clave="valvula_diafragma", x=500, y=40, equipo=None)["id"]
    assert ev(pl, "instrumento", id=k, equipo="W5")["ok"]
    assert ev(pl, "mover_instrumento", id=k, x=612, y=244)["ok"] and (IN.buscar(pl, k).x, IN.buscar(pl, k).y) == (610.0, 240.0)
    x0, y0 = pl.equipos["W5"].x, pl.equipos["W5"].y
    a0 = IN.posiciones(pl)["TIC-401"]
    assert ev(pl, "mover", id="W5", x=x0 + 100, y=y0 + 40)["ok"]
    assert (IN.buscar(pl, k).x, IN.buscar(pl, k).y) == (710.0, 280.0)                    # con posición propia: se desplaza
    a1 = IN.posiciones(pl)["TIC-401"]
    assert (a1[0] - a0[0], a1[1] - a0[1]) == (100, 40)                                    # junto al equipo: lo sigue
    d = next(i for i in LZ.datos_lienzo(pl, pl, None, {})["instrumentos"] if i["id"] == k)
    assert (d["dx"], d["dy"]) == (710.0 - pl.equipos["W5"].x, 280.0 - pl.equipos["W5"].y) and not d["auto"]


def test_deshacer_y_rehacer_instrumentos(pl):
    h = LZ.Historial(); A = lambda e, **d: LZ.aplicar_con_historial(pl, dict(evento=e, datos=d), h)
    n = len(pl.instrumentos)
    k = A("agregar_instrumento", clave="transmisor", x=None, y=None, equipo="W1")["id"]
    assert A("conectar_senal", origen=k, tipo="instrumento", destino="TIC-101", senal="electrica")["ok"]
    assert A("instrumento", id=k, letras="TT", numero="101")["ok"]
    assert h.resumen()["etiqueta_deshacer"] == f"cambiar el instrumento {k}"
    assert A("deshacer")["ok"] and IN.buscar(pl, k).letras == "TT" and len(IN.buscar(pl, k).conexiones) == 1
    assert A("deshacer")["ok"] and IN.buscar(pl, k).conexiones == []
    assert A("deshacer")["ok"] and len(pl.instrumentos) == n
    assert A("rehacer")["ok"] and A("rehacer")["ok"] and len(IN.buscar(pl, k).conexiones) == 1
    clave = IN.clave_senal(k, IN.buscar(pl, k).conexiones[0])
    assert A("quitar_senal", clave=clave)["ok"] and A("deshacer")["ok"] and IN.buscar(pl, k).conexiones[0]["destino"] == "TIC-101"


def test_version_antigua_sin_posicion_se_carga(pl):
    d = json.loads(a_json(planta_a_dict(pl)))
    for i in d["instrumentos"]:                       # así se guardaban antes de PAT 134
        for c in ("x", "y", "simbolo", "conexiones"):
            i.pop(c)
    nueva = planta_desde_dict(d)
    assert len(nueva.instrumentos) == 6 and all(i.x is None and i.simbolo == "" and i.conexiones == [] for i in nueva.instrumentos)
    t = nueva.instrumentos[0]
    assert "TIC" in isa54.lazo_svg(t.letras, t.numero, t.descripcion, t.equipo, t.ubicacion)
    assert planta_svg(nueva).count("<circle") >= 6 and len(LZ.datos_lienzo(nueva, None, None, {})["instrumentos"]) == 6
    # y lo nuevo se guarda y se vuelve a leer igual
    ev(pl, "agregar_instrumento", clave="valvula_motor", x=520, y=60)
    ev(pl, "conectar_senal", origen="TIC-101", tipo="instrumento", destino="FV-502", senal="electromagnetica")
    otra = planta_desde_json(a_json(planta_a_dict(pl)), resolver=False)
    assert IN.buscar(otra, "FV-502").simbolo == "valvula_motor" and IN.buscar(otra, "FV-502").x == 520.0
    assert IN.buscar(otra, "TIC-101").conexiones == [dict(senal="electromagnetica", tipo="instrumento", destino="FV-502", parametro=None)]


def test_diagrama_de_flujo_con_instrumentos_del_lienzo(pl):
    base = planta_svg(pl)
    k = ev(pl, "agregar_instrumento", clave="valvula_diafragma", x=600, y=30)["id"]
    ev(pl, "conectar_senal", origen="TIC-101", tipo="instrumento", destino=k, senal="neumatica")
    ev(pl, "conectar_senal", origen=k, tipo="corriente", destino=IN.clave_corriente(pl.conexiones[3]), senal="proceso")
    svg = planta_svg(pl)
    assert f"{k}: Válvula de control" in svg and svg.count("<path") > base.count("<path") + 5
    assert k not in planta_svg(pl, instrumentos=False)


def test_lazos_para_la_pestana_instrumentacion(pl):
    ev(pl, "instrumento", id=ev(pl, "agregar_instrumento", clave="transmisor", x=None, y=None, equipo="W1")["id"], letras="TT", numero="101")
    j = ev(pl, "agregar_instrumento", clave="caja_conexiones", x=300, y=40)["id"]
    ev(pl, "conectar_senal", origen="TT-101", tipo="instrumento", destino=j, senal="electrica")
    lz = {L["numero"]: L for L in IN.lazos(pl)}
    assert set(lz) == {"101", "201", "301", "302", "401", "501"}
    assert IN.ident(lz["101"]["representante"]) == "TIC-101" and len(lz["101"]["miembros"]) == 2 and lz["101"]["caja"] == "JB-1"
    assert lz["101"]["senales"][0]["origen"] == "TT-101" and IN.lectura(IN.buscar(pl, j)).startswith("Caja de conexiones")


@pytest.mark.parametrize("modulo", [pellet, chip, lena])
def test_instrumentos_en_los_rubros_de_biomasa(modulo):
    p = modulo.crear(); eq = next(iter(p.equipos))
    k = ev(p, "agregar_instrumento", clave="controlador", x=None, y=None, equipo=eq)["id"]
    assert ev(p, "conectar_senal", origen=k, tipo="equipo", destino=eq, senal="datos")["ok"]
    assert len(LZ.datos_lienzo(p, p, None, {})["instrumentos"]) == len(p.instrumentos) and k in planta_svg(p)


def test_parametro_bajo_el_minimo_avisa_y_muestra_lo_que_uso_el_motor(pl):
    r = ev(pl, "parametro", id="F2", clave="brix_jugo", valor=0)
    assert r["ok"] and r["tipo"] == "aviso" and "Mínimo 0,03" in r["mensaje"] and pl.equipos["F2"].v("brix_jugo") == 0.03
    p = next(x for x in LZ.datos_lienzo(pl, pl, None, {})["equipos"] if x["id"] == "F2")["params"]
    f = next(x for x in p if x["clave"] == "brix_jugo")
    assert f["valor"] == 0.03 and f["minimo"] == 0.03 and f["maximo"] == 0.08
    assert "Máximo 0,08" in ev(pl, "parametro", id="F2", clave="brix_jugo", valor=0.5)["mensaje"]
    assert ev(pl, "parametro", id="F2", clave="brix_jugo", valor=0.05)["mensaje"] is None


def test_especificacion_imposible_en_el_diagnostico_y_se_recupera(pl):
    v0 = pl.especs[0].valor
    assert ev(pl, "espec", indice=0, valor=0.0)["ok"]
    sol, motivo = LZ.resolver_parcial(pl)
    diag = LZ.datos_lienzo(pl, sol, motivo, {})["diagnostico"]
    assert "no se puede alcanzar" in diag[0]["texto"] and diag[0]["nivel"] == "error" and "°Brix de la pasta envasada" in diag[0]["texto"]
    assert ev(pl, "espec", indice=0, valor=v0)["ok"]
    sol, motivo = LZ.resolver_parcial(pl)
    assert motivo is None and pl.resuelta
