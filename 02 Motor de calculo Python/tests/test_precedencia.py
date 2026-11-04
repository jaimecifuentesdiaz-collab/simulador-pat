"""Pruebas de la restricción de precedencia al conectar (PAT 135, pedida por Jaime): pat_sim.motor.precedencia, su uso en
pat_sim.motor.lienzo (conectar, «Secuencia sugerida» y «Diagnóstico») y las tablas estados_material y precedencia del
mantenedor (datos/mantenedor.py), en los cuatro rubros."""
import os, sqlite3, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.escenarios import agrozzi, pellet, chip, lena, plantillas
from pat_sim.motor import lienzo as LZ, precedencia as PR
from pat_sim.datos import mantenedor as M
from pat_sim.datos.bd import BaseDatos, planta_desde_json

MODULOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
# rubro: (equipo final, mensaje al conectar la recepción B1 con él, etapa opcional (antes, opcional, después))
CASOS = {
    "tomate": ("A1", "A1 · Llenadora aséptica necesita pasta estéril; B1 · Recepción de tomate entrega tomate fresco. "
                     "Faltan: lavado, trituración, *hot break*, refinado, evaporación y esterilización.", ("W5", "B2", "A1")),
    "pellet": ("A2", "A2 · Ensacado (ISO 17225-2 A1) necesita pellet enfriado; B1 · Recepción de aserrín verde entrega biomasa húmeda. "
                     "Faltan: secado, molienda, pelletizado y enfriamiento.", ("T2", "F1", "A2")),
    "chip": ("A1", "A1 · Acopio de chip (ISO 17225-4) necesita astilla seca; B1 · Recepción de rollizos entrega rollizos verdes. "
                   "Faltan: astillado, cribado (opcional) y secado.", ("Z1", "F1", "T1")),
    "lena": ("A2", "A2 · Acopio de leña seca necesita leña trozada y partida; B1 · Recepción de trozas entrega trozas verdes. "
                   "Faltan: trozado y partido.", ("A1", "T1", "A2")),
}
RUBROS = list(CASOS)


def tabla(libre=False):
    return PR.Precedencia(M.semilla_estados(), M.semilla_precedencia(), libre)


def planta(rubro, libre=False):
    pl = MODULOS[rubro].crear(capacidades=False)
    pl.precedencia = tabla(libre)
    return pl


def conectar(pl, o, po, d, pd_, **kw):
    return LZ.aplicar_evento(pl, dict(evento="conectar", datos=dict(origen=o, puerto_origen=po, destino=d, puerto_destino=pd_), seq=1), **kw)


def proceso(pl):
    return [c for c in pl.conexiones if not pl.es_servicio(c)]


def quitar(pl, pred):
    pl.conexiones = [c for c in pl.conexiones if not pred(c)]


# ------------------------------------------------------------------ la semilla y las plantas guardadas cumplen la regla
def test_semilla_valida_y_cadenas():
    assert M.validar_precedencia(M.semilla_estados(), M.semilla_precedencia()) == []
    t = tabla()
    assert t.cadena("tomate").startswith("tomate fresco → tomate lavado y seleccionado → tomate triturado → jugo caliente")
    assert t.cadena("tomate").endswith("pasta estéril → pasta enfriada → pasta envasada")
    assert t.cadena("pellet") == "biomasa húmeda → biomasa seca → biomasa molida → pellet caliente → pellet enfriado → pellet cribado → pellet ensacado"
    assert t.cadena("chip") == "rollizos verdes → astilla verde → astilla cribada → astilla seca → chip acopiado"
    assert t.cadena("lena") == "trozas verdes → leña trozada y partida → leña seca → leña acopiada"


@pytest.mark.parametrize("rubro", RUBROS)
def test_escenarios_y_plantillas_cumplen(rubro):
    assert PR.violaciones(planta(rubro)) == []
    for p in plantillas.listar(rubro):
        assert PR.violaciones(plantillas.cargar(p.clave), tabla()) == [], p.clave


def test_versiones_guardadas_en_la_base_cumplen():
    ruta = os.path.join(os.path.dirname(__file__), "..", "..", "03 Base de datos", "simulador_pat.db")
    if not os.path.exists(ruta):
        return
    con = sqlite3.connect(f"file:{ruta}?mode=ro", uri=True)
    try:
        filas = con.execute("SELECT planta_json FROM versiones").fetchall()
    finally:
        con.close()
    for (pj,) in filas:
        pl = planta_desde_json(pj, resolver=False)
        assert PR.violaciones(pl, tabla()) == [], pl.nombre


# ------------------------------------------------------------------ conectar
@pytest.mark.parametrize("rubro", RUBROS)
def test_conexion_valida(rubro):
    pl = planta(rubro); c = proceso(pl)[0]
    quitar(pl, lambda x: x is c)
    r = conectar(pl, c.origen, c.puerto_origen, c.destino, c.puerto_destino)
    assert r["ok"], r["mensaje"]


@pytest.mark.parametrize("rubro", RUBROS)
def test_conexion_invalida_con_mensaje(rubro):
    pl = planta(rubro); fin, msg, _ = CASOS[rubro]
    quitar(pl, lambda x: x.origen == "B1")
    n = len(pl.conexiones)
    r = conectar(pl, "B1", "producto", fin, "entrada")
    assert not r["ok"] and not r["recalcular"] and r["mensaje"] == msg
    assert len(pl.conexiones) == n                       # la planta queda como estaba


@pytest.mark.parametrize("rubro", RUBROS)
def test_etapa_opcional_saltada(rubro):
    pl = planta(rubro); a, opc, b = CASOS[rubro][2]
    quitar(pl, lambda x: opc in (x.origen, x.destino) and not pl.es_servicio(x))
    pa = next(p.nombre for p in pl.equipos[a].salidas if p.tipo in PR.PRODUCTO)
    r = conectar(pl, a, pa, b, "entrada")
    assert r["ok"], r["mensaje"]
    assert PR.violaciones(pl) == []


@pytest.mark.parametrize("rubro", RUBROS)
def test_modo_libre(rubro):
    pl = planta(rubro, libre=True); fin = CASOS[rubro][0]
    quitar(pl, lambda x: x.origen == "B1")
    assert conectar(pl, "B1", "producto", fin, "entrada")["ok"]
    d = LZ.diagnostico(pl, None)
    assert any(x["nivel"] == "aviso" and "no respeta el orden del proceso" in x["texto"] for x in d)


@pytest.mark.parametrize("rubro", RUBROS)
def test_sin_tabla_como_antes(rubro):
    pl = MODULOS[rubro].crear(capacidades=False); fin = CASOS[rubro][0]
    quitar(pl, lambda x: x.origen == "B1")
    assert conectar(pl, "B1", "producto", fin, "entrada")["ok"]
    assert not any("orden del proceso" in x["texto"] for x in LZ.diagnostico(pl, None))


def test_tabla_por_argumento_y_rubro_sin_estados():
    pl = agrozzi.crear(capacidades=False); quitar(pl, lambda x: x.origen == "B1")
    como_dict = dict(estados=M.semilla_estados(), precedencia=M.semilla_precedencia())     # como lo entrega el mantenedor
    assert not conectar(pl, "B1", "producto", "A1", "entrada", precedencia=como_dict)["ok"]
    pl.rubro = "general"                                   # rubro sin estados: sin restricción
    assert conectar(pl, "B1", "producto", "A1", "entrada", precedencia=tabla())["ok"]


def test_equipo_de_paso_lleva_el_estado():
    pl = planta("tomate")
    quitar(pl, lambda x: x.destino == "A1")
    assert LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo="iso_bomba", x=400, y=500)))["ok"]
    bomba = next(k for k, e in pl.equipos.items() if e.tipo == "iso_bomba")
    assert conectar(pl, bomba, "salida", "A1", "entrada")["ok"]          # sin nada aguas arriba: estado desconocido
    r = conectar(pl, "B1", "producto", bomba, "entrada")                 # la bomba llevaría tomate fresco a la llenadora
    assert not r["ok"] and "Faltan: lavado" in r["mensaje"] and f"{bomba} · " in r["mensaje"]
    assert conectar(pl, "B2", "producto", bomba, "entrada")["ok"]        # pasta enfriada por la bomba: cumple
    assert PR.violaciones(pl) == []


def test_material_que_ya_paso_la_etapa():
    pl = planta("tomate"); quitar(pl, lambda x: x.destino == "F1")
    r = conectar(pl, "W5", "producto", "F1", "entrada")
    assert not r["ok"] and "ya pasó por esa etapa" in r["mensaje"]


# ------------------------------------------------------------------ secuencia sugerida y diagnóstico
@pytest.mark.parametrize("rubro", RUBROS)
def test_secuencia_sugerida_respeta_la_precedencia(rubro):
    pl = planta(rubro)
    quitar(pl, lambda x: not pl.es_servicio(x))
    pl.equipos = dict(reversed(list(pl.equipos.items())))                # agregados al revés: el orden no ayuda
    sin = MODULOS[rubro].crear(capacidades=False); quitar(sin, lambda x: not sin.es_servicio(x))
    sin.equipos = dict(reversed(list(sin.equipos.items())))
    LZ.secuencia_sugerida(sin)
    assert PR.violaciones(sin, tabla())                                  # sin tabla, la secuencia queda fuera de orden
    r = LZ.aplicar_evento(pl, dict(evento="secuencia", datos={}))
    assert r["ok"] and PR.violaciones(pl) == []
    for k, e in pl.equipos.items():                                     # toda entrada de producto quedó conectada
        for p in e.entradas:
            if p.tipo in PR.PRODUCTO:
                assert any(c.destino == k and c.puerto_destino == p.nombre for c in pl.conexiones), (k, p.nombre)
    pl.resolver()
    assert pl.resuelta


@pytest.mark.parametrize("rubro", RUBROS)
def test_diagnostico_marca_conexiones_existentes(rubro):
    pl = planta(rubro); fin = CASOS[rubro][0]
    assert not any("orden del proceso" in x["texto"] for x in LZ.diagnostico(pl, None))
    pl.conectar("B1", "producto", fin, "entrada", 0.0, "99")            # guardada antes de la regla, sin pasar por el lienzo
    d = [x for x in LZ.diagnostico(pl, None) if "orden del proceso" in x["texto"]]
    assert len(d) == 1 and d[0]["nivel"] == "error" and d[0]["equipo"] == fin and "Faltan:" in d[0]["texto"]
    datos = LZ.datos_lienzo(pl, None, None, {}, precedencia=tabla())
    assert any("orden del proceso" in x["texto"] for x in datos["diagnostico"])


# ------------------------------------------------------------------ mantenedor: tablas, siembra y opción libre
@pytest.fixture()
def man(tmp_path):
    return M.Mantenedor(BaseDatos(tmp_path / "p.db"))


def test_sembrar_idempotente_sin_pisar(man):
    r = man.sembrar_precedencia()
    assert r == dict(estados_material=len(M.semilla_estados()), precedencia=len(M.semilla_precedencia()))
    man.guardar_precedencia("tomate", "enfriamiento_flash", "pasta_esteril", "pasta_enfriada", False, "Editado por el profesor")
    assert man.sembrar_precedencia() == dict(estados_material=0, precedencia=0)
    f = next(x for x in man.listar_precedencia("tomate") if x["tipo"] == "enfriamiento_flash")
    assert f["opcional"] is False and f["fuente"] == "Editado por el profesor"
    pl = agrozzi.crear(capacidades=False); pl.precedencia = man.tabla_precedencia()
    quitar(pl, lambda x: x.destino == "A1")
    r = conectar(pl, "W5", "producto", "A1", "entrada")                 # sin la etapa opcional ya no se puede saltar
    assert not r["ok"] and "Faltan: enfriamiento" in r["mensaje"]


def test_sembrar_general_incluye_precedencia(man):
    r = man.sembrar(desafios=False)
    assert r["estados_material"] == len(M.semilla_estados()) and r["precedencia"] == len(M.semilla_precedencia())
    assert man.sembrar(desafios=False) == dict(parametros=0, simbolos=0, catalogo_equipos=0, desafios=0)
    assert man.contar()["estados_material"] == len(M.semilla_estados())


def test_conexiones_libres_en_parametros(man):
    assert man.conexiones_libres() is False and man.tabla_precedencia()["libre"] is False
    man.fijar_conexiones_libres(True)
    assert man.obtener_parametro(M.CLAVE_LIBRE)["valor"] == 1 and man.tabla_precedencia()["libre"] is True
    man.fijar_conexiones_libres(False)
    assert man.conexiones_libres() is False


def test_crud_estados_y_validacion(man):
    man.guardar_estado("tomate", "3,5", "tomate_pelado", "tomate pelado", "pelado", "Supuesto: prueba")
    assert any(e["codigo"] == "tomate_pelado" and e["orden"] == 3.5 for e in man.listar_estados("tomate"))
    man.eliminar_estado("tomate", "tomate_pelado")
    assert not any(e["codigo"] == "tomate_pelado" for e in man.listar_estados("tomate"))
    with pytest.raises(ValueError):
        man.guardar_estado("tomate", "x", "malo")
    err = M.validar_precedencia([dict(rubro="tomate", orden=1, codigo="a")],
                                [dict(rubro="tomate", tipo="t", acepta="a, b", entrega="c", fuente="")])
    assert len(err) == 3 and "«b»" in err[0] and "«c»" in err[1] and "fuente" in err[2]


def test_tabla_precedencia_siembra_si_esta_vacia(tmp_path):
    bd = BaseDatos(tmp_path / "v.db")
    t = M.tabla_precedencia(bd)
    assert len(t["estados"]) == len(M.semilla_estados()) and t["libre"] is False
    assert PR.Precedencia.desde(t).activa("pellet")
