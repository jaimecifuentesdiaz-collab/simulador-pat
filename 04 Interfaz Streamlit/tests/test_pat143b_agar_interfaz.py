"""PAT 143 b (tarea 9 del plan PAT 141): rubro agar agar en la interfaz, con el probador de Streamlit (sin navegador).

El escenario base del agar se carga desde Escenario (selector «Rubro») y desde Planta ficticia (ejemplo), y las pantallas que listan
rubros o trabajan con la planta de la sesión corren sin excepción ni error. El validador de la tarea 6 no bloquea ninguno de los
cuatro lienzos. Desde 04 Interfaz Streamlit: python -m pytest -q tests/test_pat143b_agar_interfaz.py
"""
import shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"
PANTALLAS = ("Desafío", "Escenario", "Diseño", "Selección de equipos", "Equipos auxiliares", "Lazos de control", "Balances",
             "Recuperación de calor", "Alternativas", "Layout", "Costeo", "Economía", "Riesgo económico", "Operación", "Calidad SPC",
             "Temporada", "Línea")


def _app(tmp_path, monkeypatch, todas=False):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "ejemplo"); monkeypatch.setenv("PAT_AUTOGUARDADO", "0")
    if todas:
        monkeypatch.setenv("PAT_TODAS_LAS_PAGINAS", "1")
    else:
        monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False)
    a = AppTest.from_file(APP, default_timeout=300); a.run()
    assert not a.exception, [e.value for e in a.exception]
    return a


@pytest.fixture()
def at(tmp_path, monkeypatch):
    return _app(tmp_path, monkeypatch)


def _ir(a, pagina):
    a.sidebar.radio(key="pagina").set_value(pagina).run()
    assert not a.exception, (pagina, [e.value for e in a.exception])


def _cargar_agar(a):
    _ir(a, "Escenario")
    a.selectbox(key="esc_rubro").set_value("agar").run()
    assert not a.exception, [e.value for e in a.exception]
    from pat_sim.escenarios import agar
    pl = a.session_state.pl
    assert pl.rubro == "agar" and pl.nombre == agar.NOMBRE and pl.resuelta


def test_escenario_carga_el_agar_y_muestra_sus_cifras(at):
    _cargar_agar(at)
    m = {x.label: x.value for x in at.metric}
    assert m["Agar en polvo"] == "76,0 kg/h" and m["Rendimiento global"].endswith("%")
    assert m["Calor de proceso (vapor)"].endswith(" kW") and m["Calor recuperable (todas las corrientes)"].endswith(" kW")
    assert not at.error


def test_pantallas_con_el_agar_sin_errores(at):
    _cargar_agar(at)
    for p in PANTALLAS:
        _ir(at, p)
        assert not at.error, (p, [e.value for e in at.error])
        assert at.session_state.pl.rubro == "agar", p


def test_validador_no_bloquea_los_cuatro_lienzos_del_agar(at):
    _cargar_agar(at)
    for p, v in (("Diseño", "ficticia"), ("Selección de equipos", "real"), ("Equipos auxiliares", "auxiliares"), ("Lazos de control", "lazos")):
        _ir(at, p)
        assert not [e.value for e in at.error if "no deja" in e.value], p
        assert f"val_pista_btn_{v}" not in {b.key for b in at.button}
        assert not at.button(key="flujo_sig").disabled


def test_ejemplo_de_agar_desde_planta_ficticia(at):
    _ir(at, "Diseño")
    at.selectbox(key="dis_ejemplo").set_value("agar").run()
    at.button(key="dis_cargar_ejemplo").click().run()
    assert not at.exception, [e.value for e in at.exception]
    assert at.session_state.pl.rubro == "agar" and at.session_state.pl.resuelta


def test_todas_las_pantallas_con_el_agar(tmp_path, monkeypatch):
    a = _app(tmp_path, monkeypatch, todas=True)
    [s for s in a.selectbox if s.label == "Rubro"][0].set_value("agar"); a.run()
    a.button(key="cargar_agar").click(); a.run()
    assert not a.exception, [e.value for e in a.exception]
    assert a.session_state.pl.rubro == "agar" and a.session_state.pl.resuelta and not a.error
