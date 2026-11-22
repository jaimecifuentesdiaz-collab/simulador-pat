"""PAT 144 a (20-11-2026): pantalla Desafío con el rubro agar agar, con el probador de Streamlit (sin navegador).

El rubro se elige arriba (des_rubro); el agar tiene las mismas tres listas que el tomate (des_agar_modelo, des_agar_distribucion y
des_agar_tamano), arma la planta ideal y la planta en blanco, y las pantallas que siguen trabajan con esa planta. Una asignación
del docente de la familia «agar» deja todo fijo. Desde 04 Interfaz Streamlit: python -m pytest -q tests/test_pat144a_desafio_agar_interfaz.py
"""
import shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"
SIGUEN = ("Diseño", "Selección de equipos", "Equipos auxiliares", "Lazos de control", "Recuperación de calor", "Costeo", "Economía")


@pytest.fixture()
def at(tmp_path, monkeypatch):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "blanco"); monkeypatch.setenv("PAT_AUTOGUARDADO", "0")
    import streamlit as st
    st.cache_resource.clear()
    a = AppTest.from_file(APP, default_timeout=300); a.run()
    a.sidebar.radio(key="pagina").set_value("Desafío").run()
    assert not a.exception, [e.value for e in a.exception]
    return a


def _listas(a):
    return {x.key: x for x in a.selectbox if x.key and x.key.startswith("des_")}


def test_rubro_por_omision_tomate_y_listas_del_agar_iguales(at):
    r = at.radio(key="des_rubro")
    assert r.label == "Rubro del desafío" and r.value == "tomate" and list(r.options) == ["Pasta de tomate", "Agar agar"]
    assert set(_listas(at)) == {"des_modelo", "des_distribucion", "des_tamano"}            # el tomate como antes
    r.set_value("agar").run()
    assert not at.exception and not at.error
    L = _listas(at)
    assert set(L) == {"des_agar_modelo", "des_agar_distribucion", "des_agar_tamano"}
    assert (L["des_agar_modelo"].label, L["des_agar_distribucion"].label, L["des_agar_tamano"].label) == \
        ("Modelo de planta", "Distribución de la llegada", "Tamaño de la demanda")
    assert (len(L["des_agar_modelo"].options), len(L["des_agar_distribucion"].options), len(L["des_agar_tamano"].options)) == (10, 10, 3)
    assert (L["des_agar_modelo"].value, L["des_agar_tamano"].value, L["des_agar_distribucion"].value) == ("base", "mediana", "uniforme")
    m = {x.label: x.value for x in at.metric}
    assert m["Alga seca del año"] == "2.979 t" and m["Días de operación"] == "330" and m["Percentil 95"].endswith(" kg/h")
    textos = " ".join([o for x in L.values() for o in x.options] + [x.value for x in at.markdown if "Cómo se usa" not in x.value]
                      + [x.value for x in at.caption] + list(m))
    assert "tomate" not in textos.lower() and "MM" not in textos and "peak" not in textos and "variedad" not in textos
    assert any("Perfil de la demanda" in x.value for x in at.markdown)


def test_agar_arma_la_planta_ideal_y_en_blanco_y_siguen_las_pantallas(at):
    at.radio(key="des_rubro").set_value("agar").run()
    at.selectbox(key="des_agar_modelo").set_value("prensado_intenso"); at.selectbox(key="des_agar_tamano").set_value("chica")
    at.selectbox(key="des_agar_distribucion").set_value("weibull"); at.run()
    assert not at.exception
    next(b for b in at.button if b.label == "Partir en blanco").click().run()
    assert not at.exception and not at.error
    d = at.session_state["desafio"]
    assert (d["tipo_planta"], d["variante_agar"], d["distribucion_agar"]) == ("agar", "prensado_intenso|chica", "weibull")
    pl = at.session_state["pl"]
    assert not pl.equipos and pl.rubro == "agar" and "prensado intenso" in pl.nombre
    next(b for b in at.button if b.label == "Armar la planta ideal automáticamente").click().run()
    assert not at.exception and not at.error
    pl = at.session_state["pl"]
    assert len(pl.equipos) == 12 and pl.rubro == "agar" and pl._p["variante_agar"] == "prensado_intenso|chica"
    for p in SIGUEN:
        at.sidebar.radio(key="pagina").set_value(p).run()
        assert not at.exception, (p, [e.value for e in at.exception])
    at.sidebar.radio(key="pagina").set_value("Desafío").run()
    assert not at.exception and at.radio(key="des_rubro").value == "agar"                   # vuelve con el desafío en curso
    assert at.selectbox(key="des_agar_modelo").value == "prensado_intenso"


def test_asignacion_de_agar_del_docente_deja_todo_fijo(at):
    at.session_state["asignacion_docente"] = dict(familia="agar", planta_id="agar", curso="PAT", usuario="ana", modelo_agar="intensivo",
                                                  tamano_agar="grande", distribucion_agar="gamma", variante_agar="intensivo|grande")
    at.run()
    assert not at.exception
    assert at.radio(key="des_rubro").value == "agar" and at.radio(key="des_rubro").disabled
    L = _listas(at)
    assert (L["des_agar_modelo"].value, L["des_agar_tamano"].value, L["des_agar_distribucion"].value) == ("intensivo", "grande", "gamma")
    assert all(x.disabled for x in L.values())
    assert any("quedan fijos" in i.value for i in at.info)
