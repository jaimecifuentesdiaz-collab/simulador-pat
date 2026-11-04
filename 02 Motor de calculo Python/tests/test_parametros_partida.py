"""PAT 135: parámetros económicos de partida desde el mantenedor, defectos de equipos nuevos y planta vacía en todos los rubros."""
import pytest
from pat_sim.datos.bd import BaseDatos
from pat_sim.datos import mantenedor as M
from pat_sim.motor import desafio as D
from pat_sim.motor import lienzo as LZ


@pytest.fixture()
def man(tmp_path):
    m = M.Mantenedor(BaseDatos(tmp_path / "p.db")); m.sembrar(desafios=False); return m


def test_semilla_trae_tasa_horizonte_dolar_y_biomasa(man):
    for k in ("tasa_descuento", "anios_evaluacion", "dolar", "henry_hub", "precio_biomasa", "cepci"):
        assert man.obtener_parametro(k) is not None, k
    assert M.parametro("tasa_descuento", bd=man) == pytest.approx(0.10)
    assert M.parametro("anios_evaluacion", bd=man) == pytest.approx(20)
    assert "Supuesto" in man.obtener_parametro("tasa_descuento")["fuente"]


def test_gas_chile_sin_semilla_y_con_respaldo(man):
    assert man.obtener_parametro(M.CLAVE_GAS_CHILE) is None
    assert M.parametro(M.CLAVE_GAS_CHILE, None, bd=man) is None
    man.guardar_parametro(M.CLAVE_GAS_CHILE, 9.5, "US$/MMBtu", "fuente de prueba")
    assert M.parametro(M.CLAVE_GAS_CHILE, None, bd=man) == pytest.approx(9.5)


def test_aplicar_defectos_a_equipo_nuevo(man):
    from pat_sim.catalogos.registro import TIPOS
    tipo = next(iter(TIPOS)); e = man.obtener_equipo(tipo)
    p = next(q for q in e["parametros"] if isinstance(q.get("valor"), (int, float)) and not isinstance(q.get("valor"), bool))
    p["valor"] = p["valor"] + 1.0
    man.guardar_equipo(tipo, e["rubro"], e["nombre"], e["simbolo"], e["parametros"], "prueba", e["rubros"], e["iso_categoria"], e["iso_letra"])
    pl = D.planta_vacia(dict(titulo="V", enunciado="diseñar", producto="X", rubro="pellet",
                             demanda=dict(periodo="mes", unidad="t", valores=[1], fuente="Supuesto"), precios=[]))
    r = LZ.aplicar_evento(pl, dict(evento="agregar", datos=dict(tipo=tipo, x=40, y=40)))
    assert r["ok"]
    n = M.aplicar_defectos(pl.equipos[r["id"]], man)
    assert n >= 1 and pl.equipos[r["id"]].params[p["clave"]].valor == pytest.approx(p["valor"])


@pytest.mark.parametrize("rubro", ["tomate", "pellet", "chip", "lena"])
def test_planta_vacia_en_cada_rubro(rubro):
    pl = D.planta_vacia(dict(titulo="V " + rubro, enunciado="diseñar", producto="X", rubro=rubro,
                             demanda=dict(periodo="mes", unidad="t", valores=[1, 2], fuente="Supuesto"), precios=[]))
    assert pl.resuelta and not pl.equipos and pl.cierres() == []
