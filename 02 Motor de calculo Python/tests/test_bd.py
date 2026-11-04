"""Pruebas de la fase 4: guardar, versionar, cargar y volver a obtener las mismas cifras."""
import json, math
import pytest
from pat_sim.datos.bd import BaseDatos, NOMBRE_AGROZZI, copiar_planta, planta_a_dict, a_json
from pat_sim.datos import fuentes_indice
from pat_sim.escenarios import agrozzi
from pat_sim.motor.resumen import resumen_planta
from pat_sim.catalogos.registro import TIPOS


@pytest.fixture()
def bd(tmp_path):
    return BaseDatos(tmp_path / "prueba.db")


def test_tablas_creadas(bd):
    assert set(bd.contar()) == {"proyectos", "versiones", "corridas", "fuentes", "parametros_catalogo"}


def test_guardar_y_cargar_da_las_mismas_cifras(bd):
    pl = agrozzi.crear(); r0 = agrozzi.resumen(pl)
    pid = bd.crear_proyecto("Prueba", "tomate")
    v = bd.guardar_version(pid, pl, "primera")
    pl2 = bd.cargar_version(v["id"]); r1 = agrozzi.resumen(pl2)
    for k in ("cascada", "pinch", "alt2", "Qhb", "Wc_MVR", "P", "vapor_linea_kW"):
        assert math.isclose(float(r0[k]), float(r1[k]), rel_tol=1e-9), k
    assert math.isclose(r0["gas_base"]["MMBtu"], r1["gas_base"]["MMBtu"], rel_tol=1e-9)
    assert math.isclose(r1["cascada"], 9073.8, abs_tol=0.1)       # cifra del Capítulo 1
    assert [c.nombre for c in pl2.conexiones] == [c.nombre for c in pl.conexiones]
    assert [(i.letras, i.numero, i.equipo) for i in pl2.instrumentos] == [(i.letras, i.numero, i.equipo) for i in pl.instrumentos]


def test_versionado_correlativo_y_cada_version_conserva_su_planta(bd):
    pid = bd.crear_proyecto("Versiones", "tomate")
    pl = agrozzi.crear()
    v1 = bd.guardar_version(pid, pl, "base")
    pl.equipos["W1"].set("T_salida", 96.0); pl.resolver()
    v2 = bd.guardar_version(pid, pl, "hot break a 96 °C")
    assert (v1["numero"], v2["numero"]) == (1, 2)
    assert [v["numero"] for v in bd.listar_versiones(pid)] == [2, 1]
    a = bd.cargar_version(v1["id"]); b = bd.cargar_version(v2["id"])
    assert a.equipos["W1"].v("T_salida") == 90.0 and b.equipos["W1"].v("T_salida") == 96.0
    assert resumen_planta(b)["Qsumidero"] > resumen_planta(a)["Qsumidero"]
    assert bd.ultima_version(pid) == v2["id"]


def test_corridas(bd):
    pid = bd.crear_proyecto("Corridas", "tomate"); pl = agrozzi.crear()
    v = bd.guardar_version(pid, pl); res = resumen_planta(pl)
    cid = bd.guardar_corrida(v["id"], res)
    fila = bd.listar_corridas(v["id"])[0]
    assert fila["id"] == cid and math.isclose(fila["cobertura_cascada"], res["cobertura_cascada"])
    assert math.isclose(fila["gas_base_mmbtu"], res["gas_base"]["MMBtu"])
    d = bd.obtener_corrida(cid)["resumen"]
    assert math.isclose(d["cascada"], res["cascada"]) and "cascada_filas" in d


def test_precarga_agrozzi_y_es_idempotente(bd):
    r1 = bd.precargar(); n1 = bd.contar()
    bd.precargar(); n2 = bd.contar()
    assert n1 == n2
    p = bd.obtener_proyecto(NOMBRE_AGROZZI); assert p and p["rubro"] == "tomate"
    pl = bd.cargar_version(bd.ultima_version(p["id"]))
    assert math.isclose(resumen_planta(pl)["cascada"], 9073.8, abs_tol=0.1)
    from pat_sim.datos.bd import CSV_FUENTES_BIOMASA
    import csv
    n_bio = len(list(csv.DictReader(open(CSV_FUENTES_BIOMASA, encoding="utf-8"))))
    assert n1["fuentes"] == 55 + n_bio and n1["corridas"] == 4 and n1["proyectos"] == 4     # Agrozzi y los tres rubros de biomasa
    for nombre, rubro in (("Planta de pellet de madera (escenario base)", "pellet"), ("Planta de chip de madera (escenario base)", "chip"),
                          ("Planta de leña seca (escenario base)", "lena")):
        q = bd.obtener_proyecto(nombre); assert q and q["rubro"] == rubro
        assert bd.cargar_version(bd.ultima_version(q["id"])).resuelta
    assert n1["parametros_catalogo"] == sum(len(c.params_base) for c in TIPOS.values())


def test_fuentes(bd):
    bd.precargar()
    f = bd.listar_fuentes("Amon")
    assert f and f[0]["archivo"] == "Amon_2015_V-02.pdf" and f[0]["doi"].startswith("10.1016/")
    assert f[0]["fecha_consulta"] == "2026-09-24"
    bd.agregar_fuente("Prueba (2026)", "Prueba_2026.pdf", url="https://ejemplo.cl", fecha_consulta="2026-10-29")
    bd.agregar_fuente("Prueba (2026) corregida", "Prueba_2026.pdf")      # mismo archivo: actualiza, no duplica
    assert len(bd.listar_fuentes("Prueba")) == 1


def test_catalogo_de_parametros(bd):
    bd.sembrar_catalogo()
    filas = bd.parametros_catalogo("hot_break")
    claves = {f["clave"] for f in filas}
    assert "T_salida" in claves
    t = next(f for f in filas if f["clave"] == "T_salida")
    assert t["valor_defecto"] == 90.0 and t["unidad"] and t["categoria"]


def test_proyecto_repetido_y_borrado_en_cascada(bd):
    pid = bd.crear_proyecto("Uno", "general")
    with pytest.raises(ValueError):
        bd.crear_proyecto("Uno", "general")
    v = bd.guardar_version(pid, agrozzi.crear()); bd.guardar_corrida(v["id"], {"cascada": 1.0})
    bd.eliminar_proyecto(pid)
    assert bd.contar()["versiones"] == 0 and bd.contar()["corridas"] == 0


def test_archivo_en_disco_persiste(tmp_path):
    ruta = tmp_path / "x.db"
    b1 = BaseDatos(ruta); pid = b1.crear_proyecto("Persistente", "tomate"); b1.guardar_version(pid, agrozzi.crear(), "n")
    b2 = BaseDatos(ruta)
    assert b2.obtener_proyecto("Persistente")["id"] == pid and b2.listar_versiones(pid)[0]["nota"] == "n"


def test_copiar_planta_es_independiente():
    pl = agrozzi.crear(); cp = copiar_planta(pl)
    cp.equipos["W1"].set("T_salida", 80.0); cp.resolver()
    assert pl.equipos["W1"].v("T_salida") == 90.0
    assert resumen_planta(cp)["Qsumidero"] < resumen_planta(pl)["Qsumidero"]


def test_indice_de_fuentes_lee_45_filas(tmp_path):
    md = tmp_path / "idx.md"
    md.write_text("| Nombre nuevo | a | b | c | d |\n|---|---|---|---|---|\n"
                  "| `A_2020.pdf` | viejo.pdf | Autor (2020). Rev., 1, 2. https://doi.org/10.1/abc.def. | nota | `123abc` |\n", encoding="utf-8")
    filas = fuentes_indice.leer_indice(md)
    assert len(filas) == 1 and filas[0]["doi"] == "10.1/abc.def" and filas[0]["sha1"] == "123abc"
