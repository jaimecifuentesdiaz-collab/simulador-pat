"""Pruebas de la base genérica de la herramienta docente (PAT 136, tarea T20): catálogo de 10 plantas y 10 demandas,
compatibilidad, siembra, esquema único, usuarios con clave PBKDF2 y asignación al azar sin repetir."""
import sqlite3
from pathlib import Path
import pytest
from pat_sim.catalogos import plantas_genericas as PG
from pat_sim.catalogos.registro import TIPOS, RUBROS
from pat_sim.datos.bd import BaseDatos, NOMBRE_AGROZZI
from pat_sim.datos import genericos as GE, mantenedor as M
from pat_sim.motor.precedencia import Precedencia
from pat_sim.simbolos import iso10628 as ISO

IDS_T21 = ("agricola_tomate", "agricola_fruta", "mercado_agar", "mercado_estacional_invierno", "mercado_constante",
           "mercado_tendencia_creciente", "contrato_industrial", "exportacion_ventana", "mercado_impulsos", "mixta_oferta_mercado")
ESQUEMA_SQL = Path(GE.__file__).resolve().parents[3] / "03 Base de datos" / "esquema.sql"   # …/pat_sim/datos → raíz de la aplicación


@pytest.fixture()
def g(tmp_path):
    return GE.BaseGenericos(BaseDatos(tmp_path / "gen.db"))


def _curso(g, n, nombre="PAT 2026-2"):
    cid = g.crear_curso(nombre)
    g.cargar_estudiantes(cid, "\n".join(f"est{i:03d};Estudiante {i}" for i in range(n)))
    return cid


# ---------------------------------------------------------------- catálogo
def test_diez_plantas_y_diez_demandas_con_los_ids_de_t21():
    assert len(PG.PLANTAS) == 10 and len(PG.DEMANDAS) == 10
    assert PG.IDS_DEMANDAS == IDS_T21
    assert {"tomate", "pellet", "chip", "lena", "agar"} <= set(PG.PLANTAS)


def test_cada_planta_tiene_los_campos_pedidos():
    for p in PG.PLANTAS.values():
        for k in ("id", "nombre", "producto", "materia_prima", "unidad", "operaciones", "servicios", "demanda_defecto", "referencias_texto"):
            assert p[k], (p["id"], k)
        assert set(p["servicios"]) == set(PG.SERVICIOS)
        assert p["produccion"]["fuente"]
        assert len(p["operaciones"]) >= 4


def test_operaciones_con_funcion_familia_iso_y_letra_del_anexo_d():
    for p in PG.PLANTAS.values():
        for o in p["operaciones"]:
            assert o["funcion"] in PG.FUNCIONES
            assert o["simbolo"] in ISO.SIMBOLOS, (p["id"], o["codigo"])
            assert o["familia"] in ISO.CATEGORIAS
            assert o["letra"] in ISO.LETRAS_EQUIPO
            assert o["salida"]


def test_tipos_de_equipo_existen_en_el_registro_y_coinciden_su_familia():
    for p in PG.PLANTAS.values():
        tipos = [o["tipo_equipo"] for o in p["operaciones"]]
        assert len(tipos) == len(set(tipos)), p["id"]          # uno por operación: la precedencia es por (rubro, tipo)
        for o in p["operaciones"]:
            c = TIPOS[o["tipo_equipo"]]
            assert (c.iso_categoria, c.iso_letra) == (o["familia"], o["letra"]), o["tipo_equipo"]
            assert all(a in TIPOS for a in o["alternativas"])


def test_simbolo_propio_igual_al_de_cada_clase():
    for tipo, s in PG.SIMBOLO_PROPIO.items():
        assert TIPOS[tipo].simbolo == s


def test_cadena_de_estados_encadenada():
    """El estado que entra a cada operación lo entrega una operación anterior (o es la primera de una rama)."""
    for p in PG.PLANTAS.values():
        codigos = {e["codigo"] for e in PG.estados_material(p["id"])}
        vistos = set()
        for i, o in enumerate(p["operaciones"]):
            assert o["salida"] in codigos, (p["id"], o["salida"])
            if i == 0:
                assert o["entrada"] == ()
            elif not o["rama"]:
                assert set(o["entrada"]) & vistos, (p["id"], o["codigo"])
            assert all(e in codigos for e in o["entrada"])
            vistos.add(o["salida"])


def test_existentes_usan_los_estados_y_la_precedencia_del_mantenedor():
    sem = {(f["rubro"], f["tipo"]): f for f in M.semilla_precedencia()}
    for pid in ("tomate", "pellet", "chip", "lena"):
        for f in PG.precedencia(pid):
            s = sem[(f["rubro"], f["tipo"])]
            assert (f["acepta"], f["entrega"], f["opcional"]) == (s["acepta"], s["entrega"], s["opcional"]), f["tipo"]


def test_precedencia_nueva_se_lee_con_el_motor():
    for pid in PG.IDS_PLANTAS:
        t = Precedencia.desde(PG.tabla_precedencia(pid))
        r = PG.PLANTAS[pid]["rubro"]
        assert t.activa(r)
        assert len(t.cadena(r).split(" → ")) == len(PG.estados_material(pid))


def test_existentes_enlazan_su_escenario_sin_cambiarlo():
    assert PG.EXISTENTES == ("tomate", "pellet", "chip", "lena", "agar")      # PAT 143 b: el agar tiene escenario
    for pid in PG.EXISTENTES:
        p = PG.PLANTAS[pid]
        assert p["rubro"] in RUBROS
        assert p["escenario_funcion"].endswith(".crear")
    pl = PG.crear_escenario("pellet")
    assert pl.rubro == "pellet" and pl.resuelta
    pa = PG.crear_escenario("agar")                                             # PAT 143 b: antes devolvía None
    assert pa.rubro == "agar" and pa.resuelta
    assert PG.crear_escenario("vino_granel") is None


def test_produccion_de_referencia_igual_a_los_escenarios():
    from pat_sim.escenarios import agrozzi, pellet, chip, lena
    assert PG.PLANTAS["tomate"]["produccion"]["valor"] == agrozzi.BASE["season"]
    for pid, mod in (("pellet", pellet), ("chip", chip), ("lena", lena)):
        b = mod.BASE
        assert PG.PLANTAS[pid]["produccion"]["valor"] == pytest.approx(b["produccion"] * b["hpd"] * b["dias"])


def test_compatibilidad_niveles_y_demanda_por_defecto_natural():
    m = PG.matriz_compatibilidad()
    assert len(m) == 100
    assert all(f["nivel"] in (0, 1, 2) and f["justificacion"] for f in m)
    for p in PG.PLANTAS.values():
        assert PG.compatibilidad(p["id"], p["demanda_defecto"])[0] == 2, p["id"]
    assert PG.compatibilidad("tomate", "agricola_tomate")[0] == 2
    assert PG.compatibilidad("agar", "mercado_agar")[0] == 2
    assert PG.compatibilidad("lena", "agricola_tomate")[0] == 0
    assert len(PG.combinaciones(0)) == 100 and len(PG.combinaciones(1)) == 70


def test_logicas_de_demanda():
    assert {d["logica"] for d in PG.DEMANDAS.values()} == {"agricola", "mercado", "mixta"}
    assert PG.DEMANDAS["agricola_tomate"]["logica"] == "agricola"
    assert PG.DEMANDAS["mercado_agar"]["logica"] == "mercado"
    with pytest.raises(KeyError):
        PG.demanda("no_existe")


# ---------------------------------------------------------------- base
def test_siembra_10_plantas_10_demandas_y_100_combinaciones(g):
    c = g.contar()
    assert c["tipos_planta"] == 10 and c["tipos_demanda"] == 10 and c["compatibilidad"] == 100
    assert c["operaciones_tipo"] == sum(len(p["operaciones"]) for p in PG.PLANTAS.values())
    assert c["equipos"] >= len(TIPOS)
    assert [p["id"] for p in g.listar_plantas()] == list(PG.IDS_PLANTAS)
    assert g.operaciones("agar")[3]["tipo_equipo"] == "iso_camisa"


def test_siembra_idempotente_y_no_pisa_lo_editado(g):
    g.fijar_compatibilidad("lena", "agricola_tomate", 1, "Decisión del docente para un ejercicio")
    assert all(v == 0 for v in g.sembrar().values())
    assert g.nivel("lena", "agricola_tomate") == 1


def test_modelos_comerciales_y_historial_de_precios(g):
    assert g.contar()["modelos_comerciales"] > 0               # semilla Supuesto del mantenedor
    r = g.guardar_modelo(dict(tipo_equipo="iso_secador_pulverizacion", fabricante="Fabricante de prueba", modelo="SD-100",
                              capacidad=100.0, unidad_capacidad="kg/h de agua evaporada", precio=250000.0, moneda="US$",
                              fecha_precio="2026-11-13", url="https://ejemplo.cl/sd100", mtbf_h=4000.0, mttr_h=8.0, potencia_kw=55.0,
                              largo_m=6.0, ancho_m=4.0, alto_m=9.0, peso_kg=12000.0, material="AISI 316L", garantia_meses=12.0,
                              plazo_entrega_semanas=20.0, categoria="Prueba", fuente="Ficha de prueba"))
    assert r["nuevo"] == 1
    g.registrar_precio(r["id"], 260000.0, "US$", "2027-01-10", fuente="Cotización de prueba")
    h = g.historial_precios(r["id"])
    assert [x["precio"] for x in h] == [250000.0, 260000.0]
    m = next(x for x in g.listar_modelos("iso_secador_pulverizacion") if x["modelo"] == "SD-100")
    assert m["precio"] == 260000.0 and m["fecha_precio"] == "2027-01-10" and m["material"] == "AISI 316L"
    with pytest.raises(ValueError):
        g.guardar_modelo(dict(tipo_equipo="iso_bomba", modelo="X", precio=10.0))   # precio sin fecha


def test_esquema_sql_unico_contiene_todas_las_tablas():
    texto = ESQUEMA_SQL.read_text(encoding="utf-8")
    con = sqlite3.connect(":memory:"); con.executescript(texto)
    tablas = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert set(GE.TABLAS) <= tablas
    assert {"proyectos", "versiones", "corridas", "fuentes", "parametros_catalogo", "curso", "usuarios_rol"} <= tablas
    con2 = sqlite3.connect(":memory:"); con2.executescript(GE.esquema_sql())
    assert {r[0] for r in con2.execute("SELECT name FROM sqlite_master WHERE type = 'table'")} == tablas


def test_base_vieja_sigue_funcionando(tmp_path):
    bd = BaseDatos(tmp_path / "vieja.db")
    pid = bd.crear_proyecto("Proyecto previo", "tomate")
    GE.BaseGenericos(bd)
    assert set(bd.contar()) == {"proyectos", "versiones", "corridas", "fuentes", "parametros_catalogo"}
    assert bd.obtener_proyecto(pid)["nombre"] == "Proyecto previo"
    assert bd.obtener_proyecto(NOMBRE_AGROZZI) is None
    bd2 = BaseDatos(tmp_path / "vieja.db")                      # se vuelve a abrir sin errores y conserva todo
    assert GE.BaseGenericos(bd2).contar()["tipos_planta"] == 10


# ---------------------------------------------------------------- usuarios y claves
def test_hash_de_clave_pbkdf2_verificable_y_sin_clave_en_claro(g):
    h = GE.hash_clave("clave-segura-1")
    assert h.startswith("pbkdf2_sha256$") and "clave-segura-1" not in h
    assert GE.verificar_clave("clave-segura-1", h) and not GE.verificar_clave("otra", h)
    assert GE.hash_clave("x", "00" * 16) == GE.hash_clave("x", "00" * 16)       # misma sal, mismo hash
    assert GE.hash_clave("x") != GE.hash_clave("x")                              # sal aleatoria
    g.crear_usuario("Carlos Torres", "Carlos Torres", "docente", "clave-segura-1")
    u = g.obtener_usuario("carlos.torres")
    assert u["rol"] == "docente" and "clave-segura-1" not in u["clave_hash"]
    assert g.autenticar("carlos.torres", "clave-segura-1")["rol"] == "docente"
    assert g.autenticar("carlos.torres", "mala") is None


def test_rol_profesor_compatible(g):
    assert g.crear_usuario("profe", rol="profesor") and g.obtener_usuario("profe")["rol"] == "docente"
    with pytest.raises(ValueError):
        g.crear_usuario("x", rol="administrador")
    assert g.es_docente("", "torres2026", secretos={}, entorno={})                 # clave única del profesor (mantenedor)
    assert not g.es_docente("", "otra", secretos={}, entorno={})
    M.mantenedor(g.bd).guardar_usuario("jefa", "profesor", "clave-jefa")           # usuarios_rol del mantenedor (sha256 con sal)
    assert g.es_docente("jefa", "clave-jefa", secretos={}, entorno={})
    assert g.importar_usuarios_rol() == 1 and g.autenticar("jefa", "clave-jefa")["rol"] == "docente"


def test_carga_de_estudiantes_por_linea_y_csv(g):
    cid = g.crear_curso("Curso CSV")
    r = g.cargar_estudiantes(cid, "nombre,usuario\nAna Pérez,ana.perez\nJuan Soto,jsoto\n")
    assert r["creados"] == 2 and r["errores"] == []
    r = g.cargar_estudiantes(cid, "Ana Pérez\nMaría José Díaz\nana.perez\n")
    assert r["creados"] == 1 and r["existentes"] == 2
    assert g.obtener_usuario("maria.jose.diaz")["nombre"] == "María José Díaz"
    assert len(g.listar_usuarios(cid, "estudiante")) == 3


# ---------------------------------------------------------------- asignación
def test_asignacion_al_azar_sin_repetir(g):
    cid = _curso(g, 40)
    r = g.asignar_al_azar(cid, 11)
    combos = [(a["planta_id"], a["demanda_id"]) for a in r["asignaciones"]]
    assert len(combos) == 40 and len(set(combos)) == 40 and r["avisos"] == [] and r["repetidas"] == 0
    assert all(g.nivel(p, d) >= 1 for p, d in combos)
    assert len({a["planta_id"] for a in r["asignaciones"]}) == 10         # con 40 estudiantes salen las 10 plantas


def test_primeros_diez_reciben_plantas_distintas():
    import random
    orden = GE._intercalar(PG.combinaciones(1), random.Random(3))
    assert len({p for p, _d in orden[:10]}) == 10 and len(orden) == 70


def test_asignacion_determinista_con_semilla(tmp_path):
    def repartir(nombre, semilla):
        g = GE.BaseGenericos(BaseDatos(tmp_path / nombre))
        cid = _curso(g, 25)
        return [(a["nombre_usuario"], a["planta_id"], a["demanda_id"]) for a in g.asignar_al_azar(cid, semilla)["asignaciones"]]
    assert repartir("a.db", 42) == repartir("b.db", 42)
    assert repartir("c.db", 42) != repartir("d.db", 43)


def test_mas_estudiantes_que_combinaciones_repite_lo_minimo_y_avisa(g):
    cid = _curso(g, 75)
    r = g.asignar_al_azar(cid, 5)
    assert r["combinaciones"] == 70 and r["repetidas"] == 5 and r["avisos"]
    from collections import Counter
    usos = Counter((a["planta_id"], a["demanda_id"]) for a in r["asignaciones"])
    assert len(usos) == 70 and max(usos.values()) == 2


def test_solo_natural_y_todas(g):
    cid = _curso(g, 14)
    r = g.asignar_al_azar(cid, 1, minimo_nivel=2)
    assert r["combinaciones"] == 14 and all(a["nivel"] == 2 for a in r["asignaciones"])
    assert g.asignar_al_azar(cid, 1, minimo_nivel=0)["combinaciones"] == 100


def test_asignacion_manual_y_consulta(g):
    cid = _curso(g, 3)
    r = g.asignar(cid, "est000", "agar", "mercado_agar", asignado_por="docente")
    assert r["avisos"] == [] and r["asignacion"]["modo"] == "manual"
    with pytest.raises(ValueError):
        g.asignar(cid, "est001", "lena", "agricola_tomate")
    assert g.asignar(cid, "est001", "lena", "agricola_tomate", forzar=True)["avisos"]
    assert g.asignar(cid, "est002", "agar", "mercado_agar")["avisos"]          # combinación repetida: avisa
    a = g.asignacion_de("est000")
    assert (a["planta_id"], a["demanda_id"], a["curso"]) == ("agar", "mercado_agar", "PAT 2026-2")
    assert a["detalle_planta"]["nombre"] == "Agar agar" and a["detalle_demanda"]["logica"] == "mercado" and a["nivel"] == 2
    assert g.asignacion_de("nadie") is None


def test_reparto_conserva_las_manuales(g):
    cid = _curso(g, 20)
    g.asignar(cid, "est005", "agar", "mercado_agar")
    r = g.asignar_al_azar(cid, 9)
    fila = next(a for a in r["asignaciones"] if a["nombre_usuario"] == "est005")
    assert (fila["planta_id"], fila["demanda_id"], fila["modo"]) == ("agar", "mercado_agar", "manual")
    assert len({(a["planta_id"], a["demanda_id"]) for a in r["asignaciones"]}) == 20


def test_curso_sin_estudiantes_avisa_sin_fallar(g):
    cid = g.crear_curso("Vacío")
    r = g.asignar_al_azar(cid, 1)
    assert r["asignaciones"] == [] and r["avisos"]
    with pytest.raises(KeyError):
        g.asignar_al_azar("No existe", 1)
