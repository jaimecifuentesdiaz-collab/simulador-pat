"""Plantillas mínimas por rubro y biblioteca de proyectos de ejemplo (PAT 133, mejora 14)."""
import pytest
from pat_sim.escenarios import plantillas as PLT
from pat_sim.motor.resumen import resumen_planta


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_plantilla_sin_capacidades_ni_fuente_de_calor(rubro):
    p = PLT.listar(rubro, ejemplos=False)[0]
    pl = PLT.cargar(p.clave)
    assert pl.rubro == rubro and pl.resuelta and len(pl.equipos) >= 4 and pl.conexiones
    assert not any(e.tipo.startswith(("caldera", "generador")) for e in pl.equipos.values())
    assert not any(e.params["capacidad"].valor for e in pl.equipos.values() if "capacidad" in e.params)
    assert pl.instrumentos == []
    assert p.pendientes


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_biblioteca_tiene_un_ejemplo_por_rubro_que_recupera_calor(rubro):
    ej = PLT.listar(rubro, ejemplos=True)
    assert ej and all(e.nombre and e.descripcion for e in ej)
    pl = PLT.cargar(ej[0].clave)
    assert pl.resuelta and resumen_planta(pl)["cascada"] > 0


def test_variante_de_ejemplo_cambia_la_planta():
    base = resumen_planta(PLT.cargar("ejemplo_agrozzi"))
    sin_tvr = PLT.cargar("ejemplo_agrozzi_sin_tvr")
    assert sin_tvr.nombre == "Planta basada en Agrozzi sin termocompresor"
    assert resumen_planta(sin_tvr)["servicios"]["vapor_kW"] != base["servicios"]["vapor_kW"]


def test_clave_desconocida():
    with pytest.raises(KeyError):
        PLT.obtener("no_existe")
