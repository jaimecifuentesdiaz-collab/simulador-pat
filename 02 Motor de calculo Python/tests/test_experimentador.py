"""Pruebas del experimentador y el optimizador simple, como el Experimenter de FlexSim (PAT 134): cuantiles t, intervalos de
confianza, números aleatorios comunes, comparación pareada, optimizador y los cuatro rubros."""
import math
import random
import pytest
from pat_sim.escenarios import agrozzi, pellet, chip, lena
from pat_sim.motor import experimentador as EX

ESCENARIOS = {"tomate": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}


@pytest.fixture(scope="module")
def plantas():
    return {k: m.crear() for k, m in ESCENARIOS.items()}


def _sintetico(pl, p, semilla):
    """Modelo de prueba: y = −(x − 3)² + ruido común de la semilla; el óptimo de y está en x = 3."""
    rng = random.Random(semilla); e = rng.gauss(0.0, 0.1)
    return dict(y=-(p["x"] - 3.0) ** 2 + e, x=p["x"], z=p["x"] + rng.gauss(0.0, 1.0) + 0.1 * p["x"] * rng.gauss(0.0, 1.0))


SINT = dict(nombre="Sintético", variables=[dict(clave="x", nombre="x", unidad="—", defecto=0.0, minimo=-10.0, maximo=10.0, entero=False)],
            medidas=[dict(clave="y", nombre="Objetivo y", unidad="—", sentido="max"), dict(clave="x", nombre="Valor de x", unidad="—", sentido="min"),
                     dict(clave="z", nombre="Medida ruidosa z", unidad="—", sentido="max")],
            funcion=_sintetico)


# ----------------------------------------------------------------------------------------------- estadística
@pytest.mark.parametrize("gl, esperado", [(4, 2.776), (9, 2.262), (29, 2.045), (1, 12.706), (60, 2.000)])
def test_cuantil_t_contra_tablas(gl, esperado):
    assert EX.t_cuantil(0.975, gl) == pytest.approx(esperado, abs=1e-3)


def test_cdf_t_y_simetria():
    assert EX.t_cdf(0.0, 5) == pytest.approx(0.5)
    assert EX.t_cdf(2.776445, 4) == pytest.approx(0.975, abs=1e-6)
    assert EX.t_cuantil(0.025, 9) == pytest.approx(-EX.t_cuantil(0.975, 9))
    assert EX.t_cuantil(0.5, 7) == 0.0
    assert EX.beta_inc(1.0, 1.0, 0.3) == pytest.approx(0.3) and EX.beta_inc(2.5, 2.5, 0.5) == pytest.approx(0.5)
    with pytest.raises(ValueError):
        EX.t_cuantil(1.0, 3)


def test_intervalo_de_una_muestra_fija():
    # media 3, s = √2,5 = 1,5811; semiancho = 2,7764 × 1,5811 / √5 = 1,9632
    s = EX.estadisticos([1, 2, 3, 4, 5])
    assert s["n"] == 5 and s["media"] == pytest.approx(3.0) and s["desviacion"] == pytest.approx(math.sqrt(2.5))
    assert s["semiancho"] == pytest.approx(1.96324, abs=1e-4)
    assert (s["ic_inf"], s["ic_sup"]) == pytest.approx((1.03676, 4.96324), abs=1e-4)
    assert (s["minimo"], s["maximo"]) == (1.0, 5.0)
    uno = EX.estadisticos([7.0])
    assert uno["media"] == 7.0 and uno["ic_inf"] is None


# ----------------------------------------------------------------------------------------------- números aleatorios comunes
def test_misma_semilla_mismo_resultado(plantas):
    pl = plantas["pellet"]; esc = EX.escenarios_ejemplo(pl, "temporada")
    a = EX.correr(pl, "temporada", esc, replicas=2, semilla_base=4)
    b = EX.correr(pl, "temporada", esc, replicas=2, semilla_base=4)
    c = EX.correr(pl, "temporada", esc, replicas=2, semilla_base=9)
    # iguales salvo el redondeo de la resolución de la planta (del orden de 1e-15 relativo)
    assert a["crudos"] == pytest.approx(b["crudos"], rel=1e-9) and a["semillas"] == [4, 5]
    assert a["crudos"]["Base"]["espera_media_h"] == b["crudos"]["Base"]["espera_media_h"]
    assert a["crudos"]["Base"]["espera_media_h"] != c["crudos"]["Base"]["espera_media_h"]


def test_escenarios_iguales_dan_replicas_iguales(plantas):
    pl = plantas["lena"]; base = EX.escenarios_ejemplo(pl, "operacion")[0]["params"]
    r = EX.correr(pl, "operacion", [dict(nombre="A", params=base), dict(nombre="B", params=dict(base))], replicas=3)
    assert r["crudos"]["A"] == r["crudos"]["B"]
    c = EX.comparar(r, "A", "B", "produccion_conforme_t")
    assert c["media"] == pytest.approx(0.0) and not c["significativa"] and c["mejor"] is None


def test_comparar_diferencia_pareada():
    r = EX.correr(None, SINT, [dict(nombre="x5", params=dict(x=5.0)), dict(nombre="x0", params=dict(x=0.0))], replicas=8)
    c = EX.comparar(r, "x5", "x0", "z")
    d = [a - b for a, b in zip(r["crudos"]["x5"]["z"], r["crudos"]["x0"]["z"])]
    assert c["diferencias"] == pytest.approx(d) and c["n"] == 8
    assert c["significativa"] and c["mejor"] == "x5" and c["ic_inf"] > 0
    assert "significativa" in c["texto"]
    # el pareo quita el ruido común: el IC de la diferencia es más angosto que el que se obtendría sin parear
    sa = EX.estadisticos(r["crudos"]["x5"]["z"]); sb = EX.estadisticos(r["crudos"]["x0"]["z"])
    assert c["semiancho"] < sa["semiancho"] + sb["semiancho"]


# ----------------------------------------------------------------------------------------------- optimizador
def test_optimizar_grilla_encuentra_el_optimo_evidente():
    o = EX.optimizar(None, SINT, {"x": (0.0, 6.0, 1.0)}, ("y", "max"), replicas=3)
    assert o["evaluados"] == 7 and o["mejor"]["params"]["x"] == pytest.approx(3.0)
    assert [c["posicion"] for c in o["candidatos"]] == list(range(1, 8))
    assert "OptQuest" in o["nota"]


def test_optimizar_respeta_restricciones():
    o = EX.optimizar(None, SINT, {"x": (0.0, 6.0, 1.0)}, ("y", "max"), [("x", "<=", 2.0)], replicas=2)
    assert o["mejor"]["params"]["x"] == pytest.approx(2.0) and o["factibles"] == 3
    assert all(not c["factible"] for c in o["candidatos"][3:]) and o["candidatos"][-1]["violaciones"]
    nada = EX.optimizar(None, SINT, {"x": (0.0, 6.0, 1.0)}, ("y", "max"), [("x", ">=", 99.0)], replicas=2)
    assert nada["mejor"] is None and nada["avisos"]


def test_optimizar_aleatorio_y_limites():
    o = EX.optimizar(None, SINT, {"x": (0.0, 10.0, 0.5)}, ("y", "max"), metodo="aleatorio", n=5, replicas=2, semilla_base=3)
    assert o["evaluados"] == 5 and len({c["params"]["x"] for c in o["candidatos"]}) == 5
    todo = EX.optimizar(None, SINT, {"x": (0.0, 2.0, 1.0)}, ("y", "max"), metodo="aleatorio", n=10, replicas=2)
    assert todo["evaluados"] == 3 and todo["avisos"]
    assert EX._valores(0.675, 1.0, 0.081) == pytest.approx([0.675, 0.756, 0.837, 0.918, 0.999, 1.0])
    assert EX._valores(0, 3, 1, entero=True) == [0, 1, 2, 3] and EX._valores(2.0, 2.0, 0.0) == [2.0]
    with pytest.raises(ValueError):
        EX.optimizar(None, SINT, {"x": (0.0, 10.0, 0.001)}, ("y", "max"))
    with pytest.raises(ValueError):
        EX.optimizar(None, SINT, {"x": (0.0, 1.0, 1.0)}, ("no_existe", "max"))


def test_optimizar_operacion_meta(plantas):
    pl = plantas["pellet"]
    o = EX.optimizar(pl, "operacion", {"meta": (0.5, 1.0, 0.25), "turnos": (4, 4, 1)}, ("produccion_conforme_t", "max"), replicas=2)
    assert o["evaluados"] == 3 and o["mejor"]["params"]["meta"] == pytest.approx(1.0) and o["mejor"]["params"]["turnos"] == 4


# ----------------------------------------------------------------------------------------------- los cuatro rubros
@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_temporada_en_los_cuatro_rubros(plantas, rubro):
    pl = plantas[rubro]; esc = EX.escenarios_ejemplo(pl, "temporada")
    r = EX.correr(pl, "temporada", esc, replicas=2)
    assert [e["nombre"] for e in r["escenarios"]] == ["Base", "Recepción +20 %", "Descarga más variable"]
    assert len(r["resumen"]) == 3 * len(r["medidas"])
    for f in r["resumen"]:
        assert f["n"] == 2 and math.isfinite(f["media"]) and f["ic_inf"] <= f["media"] + 1e-9 <= f["ic_sup"] + 2e-9
    # más capacidad de recepción: menos utilización (igual llegada)
    assert EX.fila(r, "Recepción +20 %", "utilizacion_media")["media"] < EX.fila(r, "Base", "utilizacion_media")["media"]
    assert 0 < EX.fila(r, "Base", "disponibilidad")["media"] <= 100


@pytest.mark.parametrize("rubro", list(ESCENARIOS))
def test_operacion_en_los_cuatro_rubros(plantas, rubro):
    pl = plantas[rubro]; estado0 = {k: e.params["estado"].valor for k, e in pl.equipos.items() if "estado" in e.params}
    esc = [dict(e, params=dict(e["params"], turnos=3)) for e in EX.escenarios_ejemplo(pl, "operacion")]
    r = EX.correr(pl, "operacion", esc, replicas=2)
    for f in r["resumen"]:
        assert f["n"] == 2 and math.isfinite(f["media"]) and f["media"] >= 0
    assert EX.fila(r, "Base", "conformidad_media")["media"] <= 100
    assert {k: e.params["estado"].valor for k, e in pl.equipos.items() if "estado" in e.params} == estado0   # la planta no se desgasta


def test_calentamiento_y_rangos(plantas):
    pl = plantas["chip"]
    r = EX.correr(pl, "temporada", [dict(nombre="Base", params={}), dict(nombre="Fuera", params=dict(camion_t=500.0))], replicas=1, calentamiento=24)
    assert r["calentamiento_h"] == 0.0 and any("calentamiento" in a for a in r["avisos"])
    assert r["escenarios"][1]["params"]["camion_t"] == 60.0 and any("fuera del rango" in a for a in r["avisos"])
    assert r["resumen"][0]["ic_inf"] is None
    with pytest.raises(ValueError):
        EX.correr(pl, "temporada", [dict(nombre="X", params=dict(no_existe=1.0))], replicas=1)
    with pytest.raises(ValueError):
        EX.correr(pl, "temporada", [dict(nombre="A", params={}), dict(nombre="A", params={})], replicas=1)
    v = {x["clave"]: x for x in EX.variables(pl, "temporada")}
    assert v["capacidad_t_h"]["minimo"] < v["capacidad_t_h"]["defecto"] < v["capacidad_t_h"]["maximo"]


# ----------------------------------------------------------------------------------------------- salidas
def test_filas_csv_y_html():
    r = EX.correr(None, SINT, [dict(nombre="x1", params=dict(x=1.0)), dict(nombre="x2", params=dict(x=2.5))], replicas=3)
    filas = EX.a_filas(r)
    assert len(filas) == 2 * 3 and filas[0]["replica_3"] == r["crudos"]["x1"]["y"][2]
    csv = EX.a_csv(r).splitlines()
    assert csv[0].startswith("escenario;medida;") and len(csv) == 7
    assert csv[5].startswith("x2;x;Valor de x;") and ";2,5;" in csv[5]
    h = EX.exportar_html(r)
    assert h.startswith("<!doctype html>") and h.count("<svg") == 3 and "Law" in h
    o = EX.optimizar(None, SINT, {"x": (0.0, 4.0, 2.0)}, ("y", "max"), replicas=2)
    assert len(EX.a_filas(o)) == 3 and EX.a_filas(o)[0]["var_x"] == 2.0
    assert "Mejor configuración" in EX.exportar_html(o) and "<svg" in EX.grafico_replicas_svg(o, "y")


# ----------------------------------------------------------------------------------------------- modelo «linea» (contrato del diseño)
def test_linea_con_simulador_de_prueba():
    llamadas = []

    def falso(pl, horas=72.0, tick_min=1.0, semilla=0, fallas=None, tanques=None, programa=None, muestra_min=10.0):
        llamadas.append(dict(horas=horas, semilla=semilla, fallas=fallas, tanques=tanques))
        T = [float(t) for t in range(int(horas) + 1)]
        return dict(equipos=[dict(id="E1", nombre="A", tipo="x", capacidad_t_h=10.0, carga_t_h=8.0),
                             dict(id="E2", nombre="B", tipo="x", capacidad_t_h=10.0, carga_t_h=9.0)],
                    tanques=[dict(id="T1", antes="E1", despues="E2", capacidad_t=4.0, nivel_inicial_t=2.0)],
                    tramos=[dict(equipo="E2", estado="esperando", inicio_h=0.0, fin_h=min(10.0, horas)),
                            dict(equipo="E2", estado="operando", inicio_h=min(10.0, horas), fin_h=horas)],
                    tiempo_h=T, niveles={"T1": [2.0] * len(T)}, produccion_acumulada_t=[5.0 * t for t in T], tasas={},
                    por_equipo={"E1": dict(utilizacion=0.8, fallas=1), "E2": dict(utilizacion=0.5, fallas=2)},
                    produccion_t=5.0 * horas, oee=0.8, avisos=[], supuestos=[], parametros={})
    previo = EX.MODELOS.get("linea")
    try:
        EX.registrar_linea(falso); EX._SONDA.clear()
        p = dict(horas=20.0, mtbf_h=50.0, mttr_h=2.0, tanque_min=30.0)
        r = EX.correr(None, "linea", [dict(nombre="L", params=p)], replicas=2, calentamiento=10.0)
        assert r["calentamiento_h"] == 10.0
        assert EX.fila(r, "L", "produccion_t")["media"] == pytest.approx(50.0)
        assert EX.fila(r, "L", "utilizacion_critico")["media"] == pytest.approx(100.0)
        assert EX.fila(r, "L", "oee")["media"] == pytest.approx(80.0) and EX.fila(r, "L", "fallas")["media"] == 3.0
        ultima = llamadas[-1]
        assert set(ultima["fallas"]) == {"E1", "E2"} and ultima["fallas"]["E1"]["mtbf"]["media"] == pytest.approx(50.0)
        # PAT 134: tanques como los recibe simular_linea, {id: dict(capacidad_t, nivel_inicial_t)}, en minutos de la carga del equipo siguiente
        assert ultima["tanques"]["T1"]["capacidad_t"] == pytest.approx(4.5) and ultima["tanques"]["T1"]["nivel_inicial_t"] == pytest.approx(2.25)
        assert [x["semilla"] for x in llamadas[-2:]] == [1, 2]
        s = EX.correr(None, "linea", [dict(nombre="L", params=dict(horas=20.0))], replicas=1)
        assert EX.fila(s, "L", "produccion_t")["media"] == pytest.approx(100.0) and EX.fila(s, "L", "utilizacion_critico")["media"] == pytest.approx(50.0)
        assert llamadas[-1]["fallas"] is None and llamadas[-1]["tanques"] is None
    finally:
        EX._SONDA.clear()
        if previo is not None:
            EX.MODELOS["linea"] = previo
        else:
            EX.registrar_linea()


def test_linea_real_si_existe(plantas):
    if not EX.registrar_linea():
        assert "linea" not in EX.MODELOS            # el otro equipo aún no entrega motor/linea_fluida.py
        return
    pl = plantas["tomate"]
    r = EX.correr(pl, "linea", [dict(nombre="Base", params=dict(horas=8.0))], replicas=2)
    assert all(math.isfinite(f["media"]) for f in r["resumen"])


# PAT 134: el formato de los tanques del experimentador calza con el que acepta simular_linea
def test_linea_tanques_en_el_formato_de_simular_linea(plantas):
    from pat_sim.motor import linea_fluida as LF
    pl = plantas["pellet"]
    if not EX.registrar_linea():
        return
    EX._SONDA.clear()
    try:
        llamadas = []

        def espia(pl_, **kw):
            r = LF.simular_linea(pl_, **kw); llamadas.append((kw, r)); return r
        EX.registrar_linea(espia)
        EX.correr(pl, "linea", [dict(nombre="T", params=dict(horas=4.0, mtbf_h=0.0, mttr_h=0.0, tanque_min=90.0))], replicas=1)
        kw, r = llamadas[-1]
        assert isinstance(kw["tanques"], dict)
        carga = {e["id"]: e["carga_t_h"] for e in r["equipos"]}
        for t in r["tanques"]:
            assert t["origen"] == "Usuario" and t["capacidad_t"] == pytest.approx(1.5 * carga[t["despues"]])
        # sin pedir tanques quedan los del motor, y los equipos sin capacidad no reciben fallas comunes
        EX.correr(pl, "linea", [dict(nombre="F", params=dict(horas=4.0, mtbf_h=50.0, mttr_h=1.0, tanque_min=0.0))], replicas=1)
        kw, r = llamadas[-1]
        assert kw["tanques"] is None and all(t["origen"] == "Supuesto" for t in r["tanques"])
        sin_cap = [e["id"] for e in r["equipos"] if e["capacidad_t_h"] is None]
        assert sin_cap and all(k not in kw["fallas"] for k in sin_cap)
        assert all(r["parametros"]["fallas"][k] is None for k in sin_cap)
    finally:
        EX._SONDA.clear(); EX.registrar_linea()
