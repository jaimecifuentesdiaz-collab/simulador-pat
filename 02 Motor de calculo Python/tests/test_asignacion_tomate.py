"""PAT 139: el docente asigna el desafío de tomate (tipo de planta de tomate × distribución de la llegada).

Comprueba la siembra de las tablas variantes_tomate, distribuciones_llegada y compatibilidad_tomate, el reparto al azar sin
repetir, la asignación manual, el detalle que ve el estudiante, que el catálogo genérico (10 × 10) no cambia y la migración de
una base creada antes de PAT 139.
"""
import pytest
from pat_sim.catalogos import plantas_tomate as PT
from pat_sim.catalogos import plantas_genericas as PG
from pat_sim.datos import genericos as GE
from pat_sim.datos.bd import BaseDatos
from pat_sim.motor import demanda as DM


@pytest.fixture
def g(tmp_path):
    return GE.BaseGenericos(BaseDatos(str(tmp_path / "t.db")))


def _curso(g, n):
    cid = g.crear_curso("PAT 2026-2")
    g.cargar_estudiantes(cid, "\n".join(f"Estudiante {i:03d}" for i in range(n)))
    return cid


def test_siembra_tomate_y_generico_sin_cambios(g):
    c = g.contar()
    assert c["variantes_tomate"] == len(PT.IDS) == 10 and c["distribuciones_llegada"] == len(DM.IDS_DISTRIBUCIONES) == 10
    assert c["compatibilidad_tomate"] == 100
    assert c["tipos_planta"] == 10 and c["tipos_demanda"] == 10 and c["compatibilidad"] == 100
    assert len(g.combinaciones(0)) == 100 and len(g.combinaciones(1)) == 70          # genérico igual que en PAT 136
    # PAT 139 (14-11): la combinación de tomate es modelo × tamaño × distribución, 10 × 3 × 10 = 300 (antes 100); las tablas de 10 × 10
    # de ayer siguen sembradas y las 300 filas nuevas están en compatibilidad_modelo_tomate
    assert len(g.combinaciones(1, "tomate")) == 300 and all(f["nivel"] == 2 for f in g.compatibilidad_tomate())
    assert c["modelos_tomate"] == 10 and c["tamanos_tomate"] == 3 and c["compatibilidad_modelo_tomate"] == 300
    assert g.sembrar_tomate() == {"variantes_tomate": 0, "distribuciones_llegada": 0, "compatibilidad_tomate": 0}   # idempotente


def test_reparto_tomate_sin_repetir_y_reproducible(g):
    cid = _curso(g, 30)
    r = g.asignar_al_azar(cid, 11, familia="tomate")
    a = r["asignaciones"]
    assert len(a) == 30 and not r["avisos"] and r["combinaciones"] == 300         # PAT 139 (14-11): 300 en vez de 100
    assert len({(x["variante_tomate"], x["tamano_tomate"], x["distribucion_tomate"]) for x in a}) == 30   # PAT 139 (14-11): con el tamaño
    assert all(x["familia"] == "tomate" and x["planta_id"] == GE.PLANTA_TOMATE for x in a)
    assert all(x["variante_tomate"] in PT.VARIANTES and x["distribucion_tomate"] in DM.DISTRIBUCIONES for x in a)
    primeras = sorted(a, key=lambda x: x["id"])[:10]
    assert len({x["variante_tomate"] for x in primeras}) == 10                         # intercaladas por tipo de planta
    antes = {x["nombre_usuario"]: (x["variante_tomate"], x["distribucion_tomate"]) for x in a}
    r2 = g.asignar_al_azar(cid, 11, familia="tomate")
    assert {x["nombre_usuario"]: (x["variante_tomate"], x["distribucion_tomate"]) for x in r2["asignaciones"]} == antes


def test_reparto_tomate_con_mas_estudiantes_que_combinaciones(g):
    cid = _curso(g, 305)                                  # PAT 139 (14-11): 305 estudiantes para 300 combinaciones (antes 105 para 100)
    r = g.asignar_al_azar(cid, 3, familia="tomate")
    assert r["repetidas"] == 5 and r["avisos"]
    assert len({(x["variante_tomate"], x["tamano_tomate"], x["distribucion_tomate"]) for x in r["asignaciones"]}) == 300


def test_asignacion_manual_tomate_y_detalle_del_estudiante(g):
    cid = _curso(g, 3)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    r = g.asignar(cid, est[0], "agrozzi", "bimodal", familia="tomate", asignado_por="profesor")
    assert r["avisos"] == []
    r = g.asignar(cid, est[1], "agrozzi", "bimodal", familia="tomate")
    assert r["avisos"] and est[0] in r["avisos"][0]
    a = g.asignacion_de(est[0])
    assert a["familia"] == "tomate" and a["variante_tomate"] == "agrozzi" and a["distribucion_tomate"] == "bimodal"
    assert a["detalle_planta"]["temporada_t"] == 450000.0 and a["detalle_demanda"]["nombre"] == DM.DISTRIBUCIONES["bimodal"]["nombre"]
    assert a["nivel"] == 2 and a["justificacion"]
    with pytest.raises(KeyError):
        g.asignar(cid, est[2], "no_existe", "bimodal", familia="tomate")
    with pytest.raises(KeyError):
        g.asignar(cid, est[2], "agrozzi", "no_existe", familia="tomate")


def test_nivel_cero_tomate_exige_forzar(g):
    cid = _curso(g, 1)
    est = g.listar_usuarios(cid, "estudiante")[0]["nombre_usuario"]
    g.fijar_compatibilidad_tomate("agrozzi", "uniforme", 0, "El docente no la quiere este semestre")
    assert len(g.combinaciones(1, "tomate")) == 299       # PAT 139 (14-11): un modelo solo es su tamaño mediano; quedan 299 de 300
    with pytest.raises(ValueError):
        g.asignar(cid, est, "agrozzi", "uniforme", familia="tomate")
    r = g.asignar(cid, est, "agrozzi", "uniforme", forzar=True, familia="tomate")
    assert r["avisos"]


def test_familias_no_se_mezclan_y_manual_generica_se_conserva(g):
    cid = _curso(g, 4)
    est = [u["nombre_usuario"] for u in g.listar_usuarios(cid, "estudiante")]
    pid, did = PG.combinaciones(2)[0]
    g.asignar(cid, est[0], pid, did)                                                    # manual genérica
    r = g.asignar_al_azar(cid, 5, familia="tomate")
    fila = {x["nombre_usuario"]: x for x in r["asignaciones"]}
    assert fila[est[0]]["familia"] == "generica" and fila[est[0]]["planta_id"] == pid
    assert all(fila[e]["familia"] == "tomate" for e in est[1:])
    r = g.asignar_al_azar(cid, 5)                                                       # genérico: sin tomate
    assert all(x["familia"] == "generica" and not x["variante_tomate"] for x in r["asignaciones"])
    with pytest.raises(ValueError):
        g.asignar_al_azar(cid, 5, familia="otra")


def test_migra_base_anterior_a_pat139(tmp_path):
    bd = BaseDatos(str(tmp_path / "vieja.db"))
    viejo = GE.ESQUEMA_GENERICOS.replace("    variante_tomate TEXT,\n    distribucion_tomate TEXT,\n", "")
    viejo = viejo[:viejo.index("CREATE TABLE IF NOT EXISTS variantes_tomate")] + viejo[viejo.index("CREATE INDEX"):]
    with bd._con() as con:
        con.executescript(viejo)
        assert "variante_tomate" not in {f[1] for f in con.execute("PRAGMA table_info(asignaciones)")}
    g = GE.BaseGenericos(bd)
    with bd._con() as con:
        cols = {f[1] for f in con.execute("PRAGMA table_info(asignaciones)")}
    assert {"variante_tomate", "distribucion_tomate"} <= cols
    assert g.contar()["compatibilidad_tomate"] == 100
    cid = _curso(g, 2)
    assert len(g.asignar_al_azar(cid, 1, familia="tomate")["asignaciones"]) == 2
