"""PAT 139 (14-11-2026): al cambiar la distribución de la llegada en Desafío y en Demanda, la serie del gráfico y las métricas cambian.
Error que se corrigió: el servidor mandaba la serie nueva, pero el navegador de Streamlit 1.65 dejaba dibujadas las barras anteriores
cuando el gráfico vega-lite tenía la misma especificación y la misma forma de datos. La corrección es que la especificación lleve una
huella de la serie (usermeta), así que aquí se comprueba la serie que recibe el gráfico y también que su especificación cambie."""
import json
import shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"


@pytest.fixture()
def abrir(tmp_path, monkeypatch):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "blanco")
    import streamlit as st
    st.cache_resource.clear()

    def _abrir(pagina):
        at = AppTest.from_file(APP, default_timeout=170); at.run()
        at.sidebar.radio(key="pagina").set_value(pagina).run()
        assert not at.exception, [e.value for e in at.exception]
        return at
    return _abrir


def _barras(at):
    """(serie dibujada, especificación) del primer gráfico vega-lite de la pantalla; la serie sale de los datos que recibe el navegador."""
    import pyarrow as pa
    pr = at.get("vega_lite_chart")[0].proto
    tabla = pa.ipc.open_stream(pr.data.data).read_all().to_pandas()
    col = [c for c in tabla.columns if c in ("Llegada", "Demanda")][0]
    return tuple(round(float(x), 6) for x in tabla[col]), pr.spec


def _numero(texto):
    return float(texto.replace(" t/h", "").replace(".", "").replace(",", "."))


def test_desafio_el_grafico_y_las_metricas_cambian_con_cada_distribucion(abrir):
    at = abrir("Desafío")
    sel = at.selectbox(key="des_distribucion")
    assert len(sel.options) == 10
    vistos = {}
    for d in ("normal_truncada", "normal", "lognormal", "beta", "media_normal", "uniforme", "triangular", "weibull", "gamma", "bimodal"):
        at.selectbox(key="des_distribucion").set_value(d).run()
        assert not at.exception, [e.value for e in at.exception]
        serie, spec = _barras(at)
        m = {x.label: x.value for x in at.metric}
        # el gráfico muestra la misma serie de la que salen las métricas
        assert max(serie) == pytest.approx(_numero(m["Pico de la llegada"]), abs=0.06)
        vistos[d] = (serie, spec, m["Pico de la llegada"], m["Percentil 95"])
    assert len({v[0] for v in vistos.values()}) == 10, "dos distribuciones dibujan la misma serie"
    assert len({v[1] for v in vistos.values()}) == 10, "el gráfico no cambia de especificación: el navegador no lo redibujaría"
    assert len({v[2] for v in vistos.values()}) == 10 and len({v[3] for v in vistos.values()}) == 10
    assert json.loads(vistos["gamma"][1])["usermeta"]["huella"] != json.loads(vistos["normal"][1])["usermeta"]["huella"]


def test_desafio_las_tres_listas_son_desplegables_con_las_mismas_claves(abrir):
    at = abrir("Desafío")
    assert {x.key for x in at.selectbox} >= {"des_modelo", "des_distribucion", "des_tamano"}
    # PAT 144 a: el rubro del desafío (tomate o agar agar) es un botón de opción con la clave des_rubro, que no es una de las tres
    # listas; las tres listas siguen siendo desplegables y ninguna otra clave del Desafío es un botón de opción
    assert not [x for x in at.radio if x.key and x.key.startswith("des_") and x.key != "des_rubro"]


def test_demanda_el_grafico_cambia_con_la_distribucion_del_tomate(abrir):
    at = abrir("Demanda")
    at.radio(key="dem_origen").set_value("tomate").run()
    assert not at.exception, [e.value for e in at.exception]
    series, specs = set(), set()
    for d in ("normal_truncada", "normal", "gamma", "uniforme", "bimodal"):
        at.selectbox(key="dem_tom_dist").set_value(d).run()
        assert not at.exception, [e.value for e in at.exception]
        serie, spec = _barras(at)
        series.add(serie); specs.add(spec)
    assert len(series) == 5 and len(specs) == 5
