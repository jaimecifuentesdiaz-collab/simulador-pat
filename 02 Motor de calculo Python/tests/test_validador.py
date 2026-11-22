"""PAT 143 (tarea 6): conexión libre en los cuatro lienzos y validador del diseño con pistas progresivas (motor/validador.py)."""
import copy
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import (validador as V, lienzo as LZ, precedencia as PR, instrumentacion as IN, seleccion as S,
                           costo_total as CT, eleccion_viva as EV, eleccion_auxiliares as EA, auxiliares as AX)
from pat_sim.motor.planta import Planta, Instrumento, corrientes_compatibles
from pat_sim.catalogos.registro import TIPOS

MODS = {"agrozzi": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
PREC = PR.tabla_plantas(None)


def _planta(r="agrozzi"):
    pl = MODS[r].crear()
    pl.precedencia = PREC
    pl.resolver()
    return pl


def _conectar(pl, o, po, d, pd_, libre=True):
    return LZ.aplicar_evento(pl, dict(evento="conectar", datos=dict(origen=o, puerto_origen=po, destino=d, puerto_destino=pd_)), TIPOS,
                             libre=libre)


def _incompatible(pl):
    """Una salida y una entrada de distinto tipo de equipos distintos (primera que se encuentre)."""
    for a in pl.equipos.values():
        for ps in a.salidas:
            for b in pl.equipos.values():
                if b.id == a.id:
                    continue
                for pe in b.entradas:
                    if not corrientes_compatibles(ps.tipo, pe.tipo) and ps.tipo in ("producto", "biomasa", "subproducto"):
                        return a.id, ps.nombre, b.id, pe.nombre
    raise AssertionError("sin par incompatible")


# ---------------------------------------------------------------- plantas de ejemplo y planta vacía
@pytest.mark.parametrize("r", list(MODS))
@pytest.mark.parametrize("vista", V.VISTAS)
def test_ejemplos_sin_errores_en_las_cuatro_pantallas(r, vista):
    res = V.revisar(_planta(r), vista, precedencia=PREC)
    assert res["errores"] == [] and not res["bloquea"]
    for h in res["hallazgos"]:
        assert h["nivel"] in ("error", "aviso") and h["mensaje"] and h["vista"] in V.VISTAS


@pytest.mark.parametrize("vista", V.VISTAS)
def test_planta_vacia_no_bloquea(vista):
    res = V.revisar(Planta(), vista)
    assert not res["bloquea"]
    if vista == "ficticia":
        assert res["avisos"][0]["regla"] == "P15"


# ---------------------------------------------------------------- conexión libre en la Planta ficticia
def test_conexion_estricta_rechaza_y_libre_acepta_con_aviso():
    pl = _planta()
    r0 = _conectar(pl, "F1", "descarte", "W5", "vapor", libre=False)
    assert not r0["ok"] and "incompatibles" in r0["mensaje"]
    r1 = _conectar(pl, "F1", "descarte", "W5", "vapor")
    assert r1["ok"] and r1["tipo"] == "aviso" and "distinto tipo" in r1["mensaje"]
    assert len(pl.incompatibles()) == 1


def test_atributo_conexion_libre_de_la_planta():
    pl = _planta(); pl.conexion_libre = True
    r = LZ.aplicar_evento(pl, dict(evento="conectar", datos=dict(origen="F1", puerto_origen="descarte", destino="W5", puerto_destino="vapor")))
    assert r["ok"]


def test_siguen_rechazados_el_ciclo_el_mismo_equipo_y_la_repetida():
    pl = _planta()
    assert not _conectar(pl, "F1", "producto", "F1", "entrada")["ok"]
    assert not _conectar(pl, "B1", "producto", "F1", "entrada")["ok"]                 # ya existe
    r = _conectar(pl, "A1", "producto", "F1", "entrada")                               # cierra un ciclo de proceso
    assert not r["ok"] and "ciclo" in r["mensaje"]


def test_corrientes_cruzadas_detienen_el_calculo_y_bloquean():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    sol, motivo = LZ.resolver_parcial(pl)
    assert not pl.resuelta and "distinto tipo" in motivo
    res = V.revisar(pl, "ficticia", motivo, PREC)
    assert res["bloquea"] and res["errores"][0]["regla"] == "P01"
    assert all(e["regla"] != "P00" for e in res["errores"])            # el motivo no se repite como otro error
    assert len(res["errores"][0]["pistas"]) == 3


def test_quitar_la_corriente_cruzada_devuelve_las_cifras_de_agrozzi():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    LZ.resolver_parcial(pl)
    r = LZ.aplicar_evento(pl, dict(evento="quitar_conexion", datos=dict(clave="F1.descarte>W5.vapor")))
    assert r["ok"]
    sol, motivo = LZ.resolver_parcial(pl)
    assert motivo is None and pl.resuelta
    assert not V.revisar(pl, "ficticia", None, PREC)["bloquea"]
    s = agrozzi.resumen(pl)
    assert round(s["Qhb"], 1) == 15956.0 and round(s["cascada"], 1) == 9073.8 and round(s["pinch"], 1) == 9722.9


@pytest.mark.parametrize("r", list(MODS))
def test_corriente_cruzada_en_los_cuatro_rubros(r):
    pl = _planta(r)
    o, po, d, pd_ = _incompatible(pl)
    assert _conectar(pl, o, po, d, pd_)["ok"]
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    assert any(e["regla"] == "P01" for e in res["errores"])


def test_precedencia_libre_queda_como_error_con_tres_pistas():
    pl = _planta()
    LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo=pl.equipos["A1"].tipo, x=100, y=500)), TIPOS)
    r = _conectar(pl, "F1", "producto", "A2", "entrada")
    assert r["ok"]
    LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", None, PREC)
    reglas = [e["regla"] for e in res["errores"]]
    assert "P02" in reglas and "P05" in reglas                          # fuera de orden y reparto de 200 %
    p2 = next(e for e in res["errores"] if e["regla"] == "P02")
    assert "necesita" in p2["pistas"][1] and "Faltan" in p2["pistas"][2] and "Faltan" not in p2["mensaje"]


def test_precedencia_estricta_sigue_rechazando():
    pl = _planta()
    LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo=pl.equipos["A1"].tipo, x=100, y=500)), TIPOS)
    r = LZ.aplicar_evento(pl, dict(evento="conectar", datos=dict(origen="F1", puerto_origen="producto", destino="A2", puerto_destino="entrada")),
                          TIPOS, PREC, libre=False)
    assert not r["ok"]


def test_secuencia_sugerida_no_usa_la_conexion_libre():
    pl = _planta(); pl.conexion_libre = True
    pl.conexiones = [c for c in pl.conexiones if not (c.origen == "Z1" and c.destino == "W1")]
    LZ.aplicar_evento(pl, dict(evento="secuencia", datos={}), TIPOS, PREC)
    assert pl.incompatibles() == [] and PR.violaciones(pl, PREC) == []


def test_equipo_suelto_servicio_sin_conectar_y_caldera_sin_destino():
    pl = _planta()
    LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo=pl.equipos["D1"].tipo, x=100, y=500)), TIPOS)
    pl.conexiones = [c for c in pl.conexiones if not (c.destino == "W1" and c.puerto_destino == "vapor")]
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    reglas = {e["regla"]: e for e in res["errores"]}
    assert "P04" in reglas and reglas["P04"]["objeto"] == "D2"
    assert "P06" in reglas and reglas["P06"]["objeto"] == "W1.vapor"
    assert not any(e["regla"] == "P07" and e["objeto"] == "D2" for e in res["errores"])   # el suelto no se repite


def test_caldera_conectada_sin_consumidores_es_servicio_sin_destino():
    pl = _planta()
    pl.conexiones = [c for c in pl.conexiones if c.origen != "D1"]
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    regl = [e["regla"] for e in res["errores"]]
    assert "P04" in regl or "P07" in regl


def test_reparto_que_no_suma_cien_es_error():
    pl = _planta()
    c = next(c for c in pl.conexiones if c.origen == "F1" and c.puerto_origen == "producto")
    c.reparto = 60.0
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    e = next(e for e in res["errores"] if e["regla"] == "P05")
    assert "60,0" in e["mensaje"] and "falta 40,0 %" in e["pistas"][2]


def test_entrada_sin_alimentacion():
    pl = _planta()
    pl.conexiones = [c for c in pl.conexiones if not (c.origen == "Z1" and c.destino == "W1")]
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    assert any(e["regla"] == "P03" and e["objeto"] == "W1" for e in res["errores"])
    assert not any(e["regla"] == "P00" for e in res["errores"])


def test_balance_que_no_cierra(monkeypatch):
    pl = _planta()
    filas = pl.cierres()
    filas[0] = dict(filas[0], cierre_masa=0.05 * max(filas[0]["masa_entra"], 1.0) + 10)
    monkeypatch.setattr(pl, "cierres", lambda: filas)
    res = V.revisar(pl, "ficticia", None, PREC)
    assert any(e["regla"] == "P08" for e in res["errores"])


def test_salida_de_producto_libre_en_equipo_intermedio_es_aviso():
    pl = _planta()
    pl.conexiones = [c for c in pl.conexiones if not (c.origen == "F1" and c.puerto_origen == "producto")]
    LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo="trituradora", x=300, y=500)), TIPOS)
    _conectar(pl, "F1", "descarte", "Z2", "entrada")
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    assert any(a["regla"] == "P09" and a["objeto"] == "F1.producto" for a in res["avisos"])
    assert any(e["regla"] == "P03" and e["objeto"] == "Z1" for e in res["errores"])


def test_instantanea_conserva_la_conexion_cruzada():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    texto = LZ.instantanea(pl)
    otra = LZ.restaurar(_planta(), texto)
    assert len(otra.incompatibles()) == 1


# ---------------------------------------------------------------- pistas progresivas
def test_pista_progresiva_y_acotada():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    res = V.revisar(pl, "ficticia", None, PREC)
    assert V.pista(res, 0)["pistas"] == []
    p1, p2, p3 = (V.pista(res, n) for n in (1, 2, 3))
    assert len(p1["pistas"]) == 1 and len(p2["pistas"]) == 2 and len(p3["pistas"]) == 3
    assert V.pista(res, 9)["nivel"] == 3 == p3["total"]
    assert p1["pistas"][0] != p3["pistas"][2]                         # la primera es general, la última concreta
    assert "W5" not in p1["pistas"][0] and "W5" in p3["pistas"][2]
    assert V.pista(V.revisar(_planta(), "ficticia", None, PREC), 1) is None


def test_mensaje_no_da_la_solucion():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    e = V.revisar(pl, "ficticia", None, PREC)["errores"][0]
    assert "Quite" not in e["mensaje"] and "Quite" in e["pistas"][2]


# ---------------------------------------------------------------- Planta real
def _cands(pl):
    return {r["equipo"]: CT.candidatos_etapa(pl, r["equipo"], None, False) for r in S.requerimientos(pl)}


def test_planta_real_estricta_rechaza_y_libre_aplica_y_bloquea():
    pl = _planta(); h = LZ.Historial(30); c = _cands(pl)
    ev = dict(evento="elegir", datos=dict(objetivo="W3", candidato=c["W3"][0]["id"], destino="W2"))
    assert not EV.procesar_evento(pl, h, ev, c)["ok"]
    r = EV.procesar_evento(pl, h, ev, c, libre=True)
    assert r["ok"] and "No calza" in r["mensaje"]
    pl.resolver()
    res = V.revisar(pl, "real", precedencia=PREC)
    e = next(e for e in res["errores"] if e["regla"] == "R02")
    assert e["objeto"] == "W2" and len(e["pistas"]) == 3 and "le falta" in e["pistas"][1]


def test_planta_real_generada_sin_errores():
    pl = _planta(); h = LZ.Historial(30); c = _cands(pl)
    EV.generar_automaticamente(pl, h, c); pl.resolver()
    assert not V.revisar(pl, "real", precedencia=PREC)["bloquea"]


def test_planta_real_con_capacidad_algo_menor_es_aviso():
    pl = _planta(); h = LZ.Historial(30); c = _cands(pl)
    EV.aplicar_candidato(pl, h, c["W2"][0]); pl.resolver()
    eq = pl.equipos["W2"]
    eq.set("capacidad", float(eq.params["capacidad"].valor) * 0.9)
    pl.resolver()
    res = V.revisar(pl, "real", precedencia=PREC)
    assert any(a["regla"] == "R03" and a["objeto"] == "W2" for a in res["avisos"]) and not res["bloquea"]


def test_planta_real_hereda_los_errores_de_la_ficticia():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    LZ.resolver_parcial(pl)
    res = V.revisar(pl, "real", precedencia=PREC)
    assert res["errores"][0]["regla"] == "R00" and "Planta ficticia" in res["errores"][0]["mensaje"]


# ---------------------------------------------------------------- Equipos auxiliares
def test_auxiliar_forzado_que_no_alcanza_bloquea():
    pl = _planta(); h = LZ.Historial(30)
    aux = AX.auxiliares(pl)
    objs = EA.objetivos(pl, aux, {}, False)["objetivos"]
    bombas = [o for o in objs if o.get("clase") == "bomba" and o.get("candidatos")]
    grande = max(bombas, key=lambda o: o["requerida"]); chica = min(bombas, key=lambda o: o["requerida"])
    c = chica["candidatos"][0]
    ev = dict(evento="elegir", datos=dict(objetivo=chica["id"], candidato=c["id"], destino=grande["id"]))
    assert not EA.procesar_evento(pl, h, ev, objs)["ok"]
    r = EA.procesar_evento(pl, h, ev, objs, libre=True)
    assert r["ok"] and "No calza" in r["mensaje"]
    res = V.revisar(pl, "auxiliares", precedencia=PREC, aux=aux, objetivos=objs)
    assert any(e["regla"] == "A01" and e["objeto"] == grande["id"] for e in res["errores"])


def test_auxiliares_generados_sin_errores():
    pl = _planta(); h = LZ.Historial(30)
    aux = AX.auxiliares(pl)
    objs = EA.objetivos(pl, aux, {}, False)["objetivos"]
    EA.generar_automaticamente(pl, h, objs)
    assert not V.revisar(pl, "auxiliares", precedencia=PREC, aux=aux, objetivos=objs)["bloquea"]


def test_servicio_sin_destino_y_demanda_sin_generador():
    pl = _planta()
    aux = dict(servicios=dict(filas=[dict(servicio="Vapor", demanda=0.0), dict(servicio="Calor (aire caliente)", demanda=0.0)]),
               bombas=dict(filas=[dict(id="P-101", linea="2", origen="F1", destino="Z1", Q_m3h=0.0)]))
    res = V.revisar_auxiliares(pl, aux, [])
    assert any(h["regla"] == "A04" and h["objeto"] == "D1" for h in res)
    assert any(h["regla"] == "A05" for h in res)
    sin = _planta()
    sin.quitar("D1")
    aux2 = dict(servicios=dict(filas=[dict(servicio="Vapor", demanda=1000.0)]))
    assert any(h["regla"] == "A03" for h in V.revisar_auxiliares(sin, aux2, []))


def test_auxiliares_heredan_errores_de_las_pantallas_anteriores():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    LZ.resolver_parcial(pl)
    res = V.revisar(pl, "auxiliares", precedencia=PREC)
    assert res["bloquea"] and res["errores"][0]["regla"] == "A00"


# ---------------------------------------------------------------- Lazos de control
def test_lazo_tipico_sin_errores_y_reglas_isa_numeradas():
    pl = _planta()
    IN.agregar_lazo(pl, "temperatura", "W1")
    res = V.revisar(pl, "lazos", precedencia=PREC)
    assert not res["bloquea"]
    for r in IN.revisar_lazos(pl):
        assert isinstance(r["regla"], int) and 1 <= r["regla"] <= 15


def test_lazo_roto_bloquea_con_pistas_progresivas():
    pl = _planta()
    r = IN.agregar_lazo(pl, "temperatura", "W1")
    tic = r["controlador"]
    for s in list(IN.buscar(pl, tic).conexiones):
        IN.quitar_senal(pl, IN.clave_senal(tic, s))
    res = V.revisar(pl, "lazos", precedencia=PREC)
    e = res["errores"][0]
    assert e["regla"] == "ISA5" and len(e["pistas"]) == 3
    assert "ISA" in e["pistas"][0] and f"El lazo {r['numero']} tiene" in e["pistas"][1] and tic in e["pistas"][2]


def test_etiqueta_no_valida_repetida_ubicacion_senal_y_equipo():
    pl = _planta()
    IN.agregar_lazo(pl, "presion", "W4")
    ins = pl.instrumentos
    ins.append(Instrumento("QQQ", "900", "W1"))                      # letras no válidas
    ins.append(copy.deepcopy(ins[0]))                                 # etiqueta repetida
    ins.append(Instrumento("TI", "901", "W1", ubicacion="luna"))      # ubicación que no existe
    ins.append(Instrumento("TI", "902", "ZZ9"))                       # equipo que no existe
    ins.append(Instrumento("TI", "903", "W1", conexiones=[dict(senal="telepatia", tipo="equipo", destino="W1", parametro=None)]))
    reglas = {e["regla"] for e in V.revisar(pl, "lazos", precedencia=PREC)["errores"]}
    assert {"I01", "I04", "I09", "I16", "I07"} <= reglas


def test_avisos_isa_de_titulo_letra_x_y_elemento_primario():
    pl = _planta()
    r = IN.agregar_lazo(pl, "temperatura", "W1")
    ms = [i for i in pl.instrumentos if i.numero == r["numero"]]
    for i in ms:
        i.descripcion = ""                                               # sin título (regla 11)
    te = next(i for i in ms if i.letras == "TE")
    te.conexiones = [s for s in te.conexiones if s.get("tipo") != "instrumento"]   # TE sin capilar al TT (regla 8)
    pl.instrumentos.append(Instrumento("TX", "950", "W1"))               # X sin significado (regla 13)
    res = V.revisar(pl, "lazos", precedencia=PREC)
    assert {"I11", "I13", "I08"} <= {a["regla"] for a in res["avisos"]}


def test_controlador_con_dos_mediciones_es_aviso():
    pl = _planta()
    r = IN.agregar_lazo(pl, "temperatura", "W1")
    t2 = Instrumento("TIT", r["numero"], "W1")
    t2.conexiones.append(dict(senal="electrica", tipo="instrumento", destino=r["controlador"], parametro=None))
    pl.instrumentos.append(t2)
    res = V.revisar(pl, "lazos", precedencia=PREC)
    assert any(a["regla"] == "I15" and a["objeto"] == r["controlador"] for a in res["avisos"])


def test_lazos_heredan_los_auxiliares_guardados():
    pl = _planta()
    res = V.revisar(pl, "lazos", precedencia=PREC, previas={"auxiliares": 2})
    assert res["bloquea"] and res["errores"][0]["regla"] == "L00" and "2 errores" in res["errores"][0]["mensaje"]


# ---------------------------------------------------------------- datos del lienzo
def test_datos_del_lienzo_con_validacion_y_conexion_libre():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    sol, motivo = LZ.resolver_parcial(pl)
    res = V.revisar(pl, "ficticia", motivo, PREC)
    d = LZ.datos_lienzo(pl, sol, motivo, {}, libre=True, validacion=res)
    assert d["libre"] is True and d["validacion"]["errores"] == len(res["errores"])
    assert d["diagnostico"][0]["nivel"] == "error" and "advertencia" in d["diagnostico"][0]["texto"]
    d0 = LZ.datos_lienzo(_planta(), _planta(), None, {})
    assert d0["libre"] is False and "validacion" not in d0


def test_resolver_parcial_dibuja_la_parte_alimentada_sin_la_cruzada():
    pl = _planta()
    _conectar(pl, "F1", "descarte", "W5", "vapor")
    sol, motivo = LZ.resolver_parcial(pl)
    assert sol is not None and "W1" in sol.equipos and all(c not in sol.conexiones for c in pl.incompatibles())


def test_tabla_de_reglas_completa():
    for k, (vista, nivel, nombre, origen) in V.REGLAS.items():
        assert vista in V.VISTAS and nivel in ("error", "aviso") and nombre and origen
    assert set(V.ISA_GENERAL) >= {1, 2, 4, 5, 7, 8, 9, 10, 11, 13, 14, 15}
