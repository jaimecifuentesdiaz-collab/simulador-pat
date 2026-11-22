"""PAT 140 g (17-11-2026): guardado automático tipo «partida» en la base. Una sola ranura de autoguardado por proyecto (no agrega
versiones numeradas), proyecto nuevo con el nombre automático, dueño con acceso controlado, la última partida por usuario o por
computador, la base real anterior que recibe la tabla nueva sin perder nada y el archivo de partida (.json) de ida y vuelta."""
import shutil, sqlite3
from pathlib import Path
import pytest
from pat_sim.datos import bd as BD
from pat_sim.datos.bd import BaseDatos, leer_partida, partida_a_json
from pat_sim.datos import estado_sesion as ES
from pat_sim.escenarios import agrozzi
from pat_sim.motor.resumen import resumen_planta

RAIZ_BD = Path(BD.__file__).resolve().parents[3] / "03 Base de datos" / "simulador_pat.db"


@pytest.fixture()
def bd(tmp_path):
    return BaseDatos(tmp_path / "auto.db")


@pytest.fixture(scope="module")
def agro():
    return agrozzi.crear()


def _estado(**k):
    ss = dict(economia=dict(precio_gas=2.77, dolar=990.35, inversion=0.0, costo_anual=0.0, anios=20, tasa=0.10, precio_biomasa=6750.0),
              cop=2.0, **k)
    return ES.capturar(ss, 1)


def test_crea_proyecto_sin_versiones_con_nombre_automatico(bd, agro):
    g = bd.autoguardar_proyecto_usuario(agro, _estado(), persona="Ana Pérez", equipo="PC1")
    assert g["nuevo"] and g["nombre"] == "Proyecto de Ana Pérez 1"
    p = bd.obtener_proyecto_usuario(g["id"])
    assert p["n_versiones"] == 0 and bd.listar_versiones_usuario(g["id"]) == []
    a = bd.obtener_autoguardado(g["id"])
    assert a["equipo"] == "PC1" and a["fecha"] == g["fecha"]


def test_sobrescribe_una_sola_fila_y_no_toca_las_versiones(bd, agro):
    g = bd.guardar_proyecto_usuario(agro, estado=_estado(), persona="Ana")
    for i in range(5):
        bd.autoguardar_proyecto_usuario(agro, _estado(temporada=dict(dias=100 + i)), proyecto_id=g["id"], persona="Ana")
    with sqlite3.connect(bd.ruta) as con:
        assert con.execute("SELECT COUNT(*) FROM proyectos_usuario_autoguardado").fetchone()[0] == 1
    assert bd.contar_proyectos_usuario() == dict(proyectos=1, versiones=1)
    d = bd.cargar_autoguardado(g["id"])
    assert d["estado"]["temporada"] == dict(dias=104) and d["version"] == 1 and d["autoguardado"]
    assert bd.cargar_proyecto_usuario(g["id"])["estado"].get("temporada") is None    # la versión numerada no cambió


def test_cifras_de_agrozzi_vuelven_del_autoguardado(bd, agro):
    g = bd.autoguardar_proyecto_usuario(agro, _estado())
    r0, r1 = resumen_planta(agro.resolver()), resumen_planta(bd.cargar_autoguardado(g["id"])["planta"])
    for k in ("cascada", "pinch", "alt2"):
        assert float(r1[k]) == pytest.approx(float(r0[k]), rel=1e-9)
    assert float(r1["cascada"]) == pytest.approx(9073.8, abs=0.05)


def test_proyecto_sin_persona_toma_el_nombre_despues(bd, agro):
    g = bd.autoguardar_proyecto_usuario(agro, _estado())
    assert g["nombre"] == "Proyecto 1"
    g2 = bd.autoguardar_proyecto_usuario(agro, _estado(), proyecto_id=g["id"], persona="Luis")
    assert g2["id"] == g["id"] and g2["nombre"] == "Proyecto de Luis 1" and not g2["nuevo"]
    bd.guardar_proyecto_usuario(agro, proyecto_id=g["id"], persona="Luis")
    g3 = bd.autoguardar_proyecto_usuario(agro, _estado(), proyecto_id=g["id"], persona="Otro")
    assert g3["nombre"] == "Proyecto de Luis 1"        # con versiones numeradas el nombre ya no cambia solo


def test_dueno_con_acceso_controlado(bd, agro):
    g = bd.guardar_proyecto_usuario(agro, persona="Ana", usuario="ana")
    with pytest.raises(PermissionError):
        bd.autoguardar_proyecto_usuario(agro, _estado(), proyecto_id=g["id"], usuario="luis", dueno="luis")
    assert bd.obtener_autoguardado(g["id"]) is None
    bd.autoguardar_proyecto_usuario(agro, _estado(), proyecto_id=g["id"], usuario="ana", dueno="ana")
    assert bd.obtener_autoguardado(g["id"])["usuario"] == "ana"


def test_ultima_partida_por_usuario_y_por_computador(bd, agro):
    a = bd.autoguardar_proyecto_usuario(agro, _estado(), persona="Ana", usuario="ana", equipo="PC1")
    b = bd.autoguardar_proyecto_usuario(agro, _estado(), persona="Luis", usuario="luis", equipo="PC2")
    with sqlite3.connect(bd.ruta) as con:           # fechas distintas (en la misma segunda quedan iguales)
        con.execute("UPDATE proyectos_usuario_autoguardado SET fecha = '2026-11-17T10:00:00' WHERE proyecto_id = ?", (a["id"],))
        con.execute("UPDATE proyectos_usuario_autoguardado SET fecha = '2026-11-17T11:00:00' WHERE proyecto_id = ?", (b["id"],))
    assert bd.ultimo_autoguardado()["proyecto_id"] == b["id"]
    assert bd.ultimo_autoguardado(usuario="ana")["proyecto_id"] == a["id"]
    assert bd.ultimo_autoguardado(usuario="ANA ")["nombre"] == "Proyecto de Ana 1"
    assert bd.ultimo_autoguardado(equipo="PC1")["proyecto_id"] == a["id"]
    assert bd.ultimo_autoguardado(usuario="pedro") is None and bd.ultimo_autoguardado(equipo="PC9") is None
    assert set(bd.fechas_autoguardado()) == {a["id"], b["id"]}


def test_eliminar_borra_el_autoguardado(bd, agro):
    g = bd.autoguardar_proyecto_usuario(agro, _estado())
    bd.eliminar_proyecto_usuario(g["id"])
    assert bd.obtener_autoguardado(g["id"]) is None and bd.ultimo_autoguardado() is None
    with pytest.raises(KeyError):
        bd.cargar_autoguardado(g["id"])


def test_proyecto_sin_autoguardado_no_se_carga_como_tal(bd, agro):
    g = bd.guardar_proyecto_usuario(agro)
    with pytest.raises(KeyError):
        bd.cargar_autoguardado(g["id"])


def test_base_real_anterior_recibe_la_tabla_sin_perder_nada(tmp_path, agro):
    if not RAIZ_BD.exists():
        pytest.skip("sin la base real")
    copia = tmp_path / "real.db"; shutil.copyfile(RAIZ_BD, copia)
    with sqlite3.connect(copia) as con:
        tablas0 = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        n0 = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in tablas0 if t != "sqlite_sequence"}
    b = BaseDatos(copia)
    with sqlite3.connect(copia) as con:
        tablas1 = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        n1 = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in n0}
    assert "proyectos_usuario_autoguardado" in tablas1 and n1 == n0
    for p in b.listar_proyectos_usuario():          # los proyectos que ya estaban siguen cargando
        assert b.cargar_proyecto_usuario(p["id"])["planta"] is not None
    g = b.autoguardar_proyecto_usuario(agro, _estado())
    assert b.cargar_autoguardado(g["id"])["planta"].equipos.keys() == agro.equipos.keys()
    BaseDatos(copia)                                # abrirla de nuevo no cambia nada
    assert b.obtener_autoguardado(g["id"]) is not None


def test_archivo_de_partida_ida_y_vuelta(agro):
    est = _estado(persona_nombre="Ana", temporada=dict(dias=120))
    d = leer_partida(partida_a_json(agro, est, "Proyecto de Ana 3").encode("utf-8"))
    assert d["nombre"] == "Proyecto de Ana 3" and d["estado"]["temporada"] == dict(dias=120)
    assert float(resumen_planta(d["planta"])["cascada"]) == pytest.approx(float(resumen_planta(agro.resolver())["cascada"]), rel=1e-9)


@pytest.mark.parametrize("texto", [b"no es json", b'{"formato": "otro"}', b'[1, 2]', b'{"formato": "partida_simulador_pat"}'])
def test_archivo_que_no_es_partida(texto):
    with pytest.raises(ValueError):
        leer_partida(texto)


def test_autoguardado_igual_a_la_ultima_version(bd, agro):
    g = bd.guardar_proyecto_usuario(agro, estado=_estado(), persona="Ana")
    bd.autoguardar_proyecto_usuario(agro, _estado(), proyecto_id=g["id"])
    assert bd.autoguardado_igual_a_version(g["id"]) and bd.cargar_autoguardado(g["id"])["igual_a_version"]
    bd.autoguardar_proyecto_usuario(agro, _estado(temporada=dict(dias=90)), proyecto_id=g["id"])
    assert not bd.autoguardado_igual_a_version(g["id"])
