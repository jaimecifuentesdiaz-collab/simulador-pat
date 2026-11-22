"""Precedencia de estados en los equipos de las 10 plantas (PAT 136, tarea T22, punto 8 de los comentarios del profesor Torres):
motor/precedencia.tabla_plantas, cobertura y mensaje_claro, y su uso al conectar en el lienzo de una planta de cada tipo nuevo."""
import os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import precedencia as PR, lienzo as LZ, sintesis as SI
from pat_sim.catalogos import plantas_genericas as PG
from pat_sim.datos import mantenedor as M

# PAT 143 b: el agar ya tiene escenario, pero su planta automática sigue armándose con los tipos genéricos de su cadena
NUEVAS = [p for p in PG.IDS_PLANTAS if not PG.PLANTAS[p]["escenario"] or p == "agar"]


def test_cobertura_de_las_10_plantas():
    cob = PR.cobertura()
    assert len(cob) == 10
    for f in cob:
        assert f["activa"] and f["faltan"] == [] and f["con_fila"] == f["operaciones"], f["planta_id"]
        assert " → " in f["cadena"]


def test_la_tabla_del_mantenedor_no_cambia():
    base = dict(estados=M.semilla_estados(), precedencia=M.semilla_precedencia(), libre=False)
    t = PR.tabla_plantas(base)
    viejas = {(f["rubro"], f["tipo"]): f for f in base["precedencia"]}
    nuevas = {(f["rubro"], f["tipo"]): f for f in t["precedencia"]}
    assert all(nuevas[k] == v for k, v in viejas.items())            # las filas de PAT 135 quedan iguales
    assert len(t["estados"]) > len(base["estados"]) and not t["libre"]
    assert PR.tabla_plantas(dict(base, libre=True))["libre"]
    assert PR.tabla_plantas(PR.Precedencia.desde(base))["precedencia"]   # también desde un objeto Precedencia


@pytest.mark.parametrize("pid", NUEVAS)
def test_recepcion_directo_al_final_se_rechaza(pid):
    """En una planta automática de cada tipo nuevo, conectar la recepción con un equipo nuevo de la última operación se rechaza
    con un mensaje que nombra el estado que necesita y las etapas que faltan."""
    pl = SI.armar_planta(pid, alternativas=False)
    pl.precedencia = PR.tabla_plantas()
    p = PG.PLANTAS[pid]
    rec = next(e for e in pl.equipos.values() if e.tipo == p["operaciones"][0]["tipo_equipo"])
    r = LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo=SI.clase_para(p["operaciones"][-1]["tipo_equipo"], "producto").tipo)))
    nuevo = pl.equipos[r["id"]]
    pe = SI._puerto_prod(nuevo.entradas)
    ps = SI._puerto_prod(rec.salidas)
    r = LZ.aplicar_evento(pl, dict(evento="conectar", datos=dict(origen=rec.id, puerto_origen=ps.nombre, destino=nuevo.id, puerto_destino=pe.nombre)))
    assert not r["ok"] and "necesita" in r["mensaje"] and "Faltan:" in r["mensaje"]
    claro = PR.mensaje_claro(r["mensaje"])
    assert claro.startswith("No se conectó.") and r["mensaje"] in claro


def test_rama_del_licor_de_prensa_de_la_harina():
    t = PR.de_planta("harina_pescado")
    assert {"licor_prensa", "torta_prensa"} <= t.acepta("harina_pescado", "iso_decantador")
    assert t.acepta("harina_pescado", "iso_mezclador") >= {"torta_prensa", "agua_cola_concentrada"}


def test_versiones_simplificadas_y_alternativas_tienen_fila():
    t = PR.de_planta("agar")
    assert t.entrega("agar", "simple_secador_banda") == t.entrega("agar", "secador_banda") == "agar_seco"
    t2 = PR.de_planta("jugo_manzana")
    assert t2.entrega("jugo_manzana", "evaporador_mvr") == "jugo_concentrado"          # alternativa del evaporador
    assert t2.entrega("pellet", "simple_secador_biomasa") == t2.entrega("pellet", "secador_biomasa")


def test_diagnostico_muestra_la_conexion_fuera_de_orden():
    pl = SI.armar_planta("vino_granel", alternativas=False)
    tabla = PR.tabla_plantas()
    rec = next(e for e in pl.equipos.values() if e.tipo == "iso_bascula")
    fin = next(e for e in pl.equipos.values() if e.tipo == "iso_bomba_desplazamiento")
    pl.conexiones = [c for c in pl.conexiones if c.destino != fin.id]
    pl.conectar(rec.id, "salida", fin.id, "entrada", 50.0)             # forzada sin pasar por el lienzo
    v = PR.violaciones(pl, tabla)
    assert len(v) == 1 and "necesita" in v[0][2]
    d = LZ.diagnostico(pl, None, None, tabla)
    assert any("no respeta el orden del proceso" in x["texto"] for x in d)
    assert PR.mensaje_claro(None) is None
