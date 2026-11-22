"""PAT 139 (14-11-2026, comentarios del profesor Torres, puntos 1 y 7): pantalla Desafío con «Modelo de planta» a la izquierda y
«Perfil de la demanda» (distribución de la llegada y tamaño de la demanda) a la derecha, y pantalla Docente con la combinación
modelo × distribución × tamaño. Prueba con el probador de Streamlit, sin navegador."""
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
    st.cache_resource.clear()                  # la base abierta (comun.obtener_bd) se guarda en caché: cada prueba abre la suya

    def _abrir(pagina):
        at = AppTest.from_file(APP, default_timeout=170); at.run()
        at.sidebar.radio(key="pagina").set_value(pagina).run()
        assert not at.exception, [e.value for e in at.exception]
        return at
    _abrir.bd = str(bd)
    return _abrir


def test_desafio_modelo_a_la_izquierda_perfil_a_la_derecha(abrir):
    at = abrir("Desafío")
    r = {x.key: x for x in at.selectbox if x.key and x.key.startswith("des_")}
    assert set(r) == {"des_modelo", "des_distribucion", "des_tamano"}
    assert r["des_modelo"].label == "Modelo de planta" and len(r["des_modelo"].options) == 10
    assert r["des_distribucion"].label == "Distribución de la llegada" and len(r["des_distribucion"].options) == 10
    assert r["des_tamano"].label == "Tamaño de la demanda" and len(r["des_tamano"].options) == 3
    assert (r["des_modelo"].value, r["des_tamano"].value) == ("agrozzi", "mediana")                 # por omisión, Agrozzi
    assert any("Perfil de la demanda" in m.value for m in at.markdown)
    m = {x.label: x.value for x in at.metric}
    assert m["Tomate de la temporada"] == "450.000 t" and m["Días de temporada"] == "76"
    textos = " ".join(o for o in r["des_modelo"].options)
    assert "𝘩𝘰𝘵 𝘣𝘳𝘦𝘢𝘬" in textos and "𝘤𝘰𝘭𝘥 𝘣𝘳𝘦𝘢𝘬" in textos and "*" not in textos and "MM" not in textos and " don " not in textos
    labels = [b.label for b in at.button]
    assert "Armar la planta ideal automáticamente" in labels and "Partir en blanco" in labels


def test_desafio_cambia_el_tamano_y_guarda_modelo_tamano_y_distribucion(abrir):
    at = abrir("Desafío")
    at.selectbox(key="des_modelo").set_value("cold36_tvr3"); at.selectbox(key="des_tamano").set_value("grande")
    at.selectbox(key="des_distribucion").set_value("weibull"); at.run()
    assert not at.exception
    m = {x.label: x.value for x in at.metric}
    assert m["Tomate de la temporada"] == "900.000 t" and m["Días de temporada"] == "95"
    next(b for b in at.button if b.label == "Partir en blanco").click().run()
    assert not at.exception and not at.error
    d = at.session_state["desafio"]
    assert (d["modelo_tomate"], d["tamano_tomate"], d["distribucion_tomate"], d["variante_tomate"]) == \
        ("cold36_tvr3", "grande", "weibull", "cold36_tvr3|grande")
    assert "900.000 t" in at.session_state["pl"].nombre
    next(b for b in at.button if b.label == "Armar la planta ideal automáticamente").click().run()
    assert not at.exception and not at.error and len(at.session_state["pl"].equipos) > 0
    # el desafío (con la variante compuesta) lo leen las demás pantallas
    at.sidebar.radio(key="pagina").set_value("Demanda").run()
    at.radio(key="dem_origen").set_value("tomate").run()
    assert not at.exception
    assert (at.radio(key="dem_tom_modelo").value, at.radio(key="dem_tom_tamano").value) == ("cold36_tvr3", "grande")


@pytest.mark.parametrize("asig,esperado", [
    (dict(variante_tomate="cold38_tvr3", tamano_tomate="grande", distribucion_tomate="gamma"), ("cold38_tvr3", "grande", "gamma")),
    (dict(variante_tomate="pequena_28", distribucion_tomate="beta"), ("hot28_me3", "chica", "beta")),      # asignación vieja de PAT 138
])
def test_asignacion_del_docente_deja_los_tres_fijos(abrir, asig, esperado):
    at = abrir("Desafío")
    at.session_state["asignacion_docente"] = dict(asig, familia="tomate", planta_id="tomate", curso="PAT", usuario="ana")
    at.run()
    assert not at.exception
    r = {x.key: x for x in at.selectbox if x.key and x.key.startswith("des_")}
    assert (r["des_modelo"].value, r["des_tamano"].value, r["des_distribucion"].value) == esperado
    assert all(x.disabled for x in r.values())
    assert any("quedan fijos" in i.value for i in at.info)


def test_docente_reparte_300_asigna_a_mano_con_tres_listas_y_exporta(abrir):
    at = abrir("Docente")
    from pat_sim.datos import genericos as GE          # app.py ya puso pat_sim en el camino de importación
    g = GE.genericos(abrir.bd)
    g.crear_usuario("doc1", "Docente Uno", "docente", "clavedocente1")
    at.text_input(key="doc_usuario").set_value("doc1"); at.text_input(key="doc_clave").set_value("clavedocente1").run()
    at.text_input(key="doc_curso_nuevo").set_value("PAT 2026-2").run()
    next(b for b in at.button if b.label == "Crear el curso").click().run()
    at.text_area(key="doc_estudiantes").set_value("\n".join(f"Estudiante {i:03d}" for i in range(12))).run()
    next(b for b in at.button if b.label == "Cargar estudiantes").click().run()
    assert any("300 de 300" in c.value for c in at.caption)
    next(b for b in at.button if b.label == "Repartir al azar").click().run()
    assert not at.exception and any("12 asignaciones, 12 combinaciones distintas" in c.value for c in at.caption)
    r = {x.key: x for x in at.radio if x.key and x.key.startswith("doc_man_")}
    assert len(r["doc_man_modelo"].options) == 10 and len(r["doc_man_tamano"].options) == 3
    assert at.selectbox(key="doc_man_distribucion").label == "Distribución de la llegada"
    at.radio(key="doc_man_modelo").set_value("cold38_tvr3"); at.radio(key="doc_man_tamano").set_value("grande")
    at.selectbox(key="doc_man_distribucion").set_value("gamma"); at.run()
    next(b for b in at.button if b.label == "Asignar").click().run()
    assert not at.exception and not at.error
    curso = g.obtener_curso("PAT 2026-2")
    filas = g.asignaciones(curso["id"])
    assert any((f["variante_tomate"], f["tamano_tomate"], f["distribucion_tomate"]) == ("cold38_tvr3", "grande", "gamma") for f in filas)
    est = [f["nombre_usuario"] for f in filas if f["variante_tomate"] == "cold38_tvr3" and f["tamano_tomate"] == "grande"][0]
    # la tabla, el CSV y la matriz salen con modelo y tamaño
    from ui import p_docente
    csv = p_docente._csv(filas)
    assert "Modelo;Tamaño" in csv.splitlines()[0] and "Grande" in csv and "MM" not in csv
    at.text_input(key="doc_usuario_est").set_value(est).run()
    a = at.session_state["asignacion_docente"]
    assert (a["variante_tomate"], a["tamano_tomate"], a["distribucion_tomate"]) == ("cold38_tvr3", "grande", "gamma")
