"""Modo curso: variante reproducible por identificador, clave del profesor y entregas (PAT 133, mejora 16)."""
import shutil, sqlite3
import pytest
from pat_sim.datos.bd import BaseDatos, RUTA_PREDETERMINADA
from pat_sim.motor import curso as CU, operacion as OP
from pat_sim.motor.resumen import resumen_planta


@pytest.fixture()
def bd(tmp_path):
    return BaseDatos(tmp_path / "curso.db")


def test_misma_variante_en_dos_corridas_y_distinta_para_otro():
    a = CU.variante("ana.perez@utalca.cl", "tomate", "PAT UTAL"); b = CU.variante("  Ana.Pérez@utalca.cl ", "tomate", "PAT UTAL")
    c = CU.variante("luis.soto@utalca.cl", "tomate", "PAT UTAL")
    assert a == b and a["planta"] != c["planta"] and a["semilla"] != c["semilla"]
    r1 = resumen_planta(CU.crear_planta(a)); r2 = resumen_planta(CU.crear_planta(b)); r3 = resumen_planta(CU.crear_planta(c))
    assert r1["cascada"] == pytest.approx(r2["cascada"], rel=1e-12) and r1["cascada"] != pytest.approx(r3["cascada"], rel=1e-6)


def test_variante_estable_entre_versiones_de_python():
    # SHA-256 fijo: este número no cambia entre ejecuciones ni computadores (hash() de Python sí cambiaría)
    assert CU.fraccion("12345678-9", "Thb") == CU.fraccion("12345678-9", "Thb")
    assert CU.fraccion("12345678-9", "Thb") == pytest.approx(int.from_bytes(__import__("hashlib").sha256(b"pat133||12345678-9|Thb").digest()[:7], "big") / 2 ** 56)


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_variantes_dentro_de_los_rangos_y_resueltas(rubro):
    for ident in ("a1", "b2", "c3"):
        v = CU.variante(ident, rubro)
        for r in CU.RANGOS[rubro]:
            x = v["planta"].get(r.clave, v["economia"].get(r.clave))
            assert r.minimo <= x <= r.maximo, (r.clave, x)
            assert r.fuente
        pl = CU.crear_planta(v)
        assert pl.resuelta and pl.rubro == rubro


def test_identificador_vacio():
    with pytest.raises(ValueError):
        CU.variante("   ")


def test_clave_del_profesor_con_hash_y_sal():
    h1 = CU.hash_clave("profesor2026"); h2 = CU.hash_clave("profesor2026")
    assert h1 != h2 and "profesor2026" not in h1 and h1.startswith("sha256$")
    assert CU.verificar_clave("profesor2026", h1) and not CU.verificar_clave("otra", h1) and not CU.verificar_clave("x", "")


def test_entregas_y_tabla_del_profesor(bd):
    curso = CU.configurar(bd, "PAT UTAL", "tomate", "clave-segura")
    assert "clave-segura" not in curso["clave_hash"]
    var = CU.ingresar(bd, curso, "ana@utalca.cl", "Ana")
    CU.ingresar(bd, curso, "luis@utalca.cl")
    pl = CU.crear_planta(var); op = CU.operacion_de(var)
    with pytest.raises(ValueError):
        CU.entregar(bd, curso, "ana@utalca.cl", op)
    r = resumen_planta(pl)
    OP.correr_turno(op, pl, 0.9, None, "ninguno", r)
    OP.finalizar(op, pl, inversion=100.0, cascada_kW=r["cascada"])
    CU.entregar(bd, curso, "ana@utalca.cl", op)
    with pytest.raises(PermissionError):
        CU.tabla_profesor(bd, curso, "mala")
    filas = CU.tabla_profesor(bd, curso, "clave-segura")
    ana = next(f for f in filas if f["identificador"] == "ana@utalca.cl")
    assert len(filas) == 2 and ana["entregas"] == 1 and ana["ultimo"] == op.puntaje["total"] and ana["fecha"]
    texto = CU.exportar_csv(filas)
    assert texto.startswith("﻿Identificador;Nombre;Entregas") and "ana@utalca.cl;Ana;1;" in texto


def test_aplicar_economia_dentro_del_rango():
    v = CU.variante("ana", "tomate"); e = CU.aplicar_economia(v, dict(precio_gas=1.0), 2.77, 6750.0)
    assert 2.77 * 0.85 - 1e-9 <= e["precio_gas"] <= 2.77 * 1.15 + 1e-9
    v = CU.variante("ana", "pellet"); e = CU.aplicar_economia(v, dict(), 2.77, 6750.0)
    assert 6000 - 1 <= e["precio_biomasa"] <= 7500 + 1


def test_base_vieja_sigue_abriendo_y_recibe_las_tablas(tmp_path):
    # base creada con el esquema anterior (sin las tablas del curso), con un proyecto guardado
    vieja = tmp_path / "vieja.db"
    if RUTA_PREDETERMINADA.exists():
        shutil.copy(RUTA_PREDETERMINADA, vieja)
        con = sqlite3.connect(vieja)
        for t in ("entregas", "estudiantes", "curso"):
            con.execute(f"DROP TABLE IF EXISTS {t}")
        con.commit(); con.close()
    else:
        con = sqlite3.connect(vieja)
        con.executescript(__import__("pat_sim.datos.bd", fromlist=["ESQUEMA"]).ESQUEMA); con.close()
    con = sqlite3.connect(vieja); antes = con.execute("SELECT COUNT(*) FROM versiones").fetchone()[0]; con.close()
    b = BaseDatos(vieja)
    assert b.contar()["versiones"] == antes
    tablas = {r[0] for r in sqlite3.connect(vieja).execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"curso", "estudiantes", "entregas", "proyectos", "versiones"} <= tablas
    if antes:
        p = b.listar_proyectos()[0]; vid = b.ultima_version(p["id"])
        assert b.cargar_version(vid).resuelta
    BaseDatos(vieja)                                  # abrir otra vez no falla (idempotente)
