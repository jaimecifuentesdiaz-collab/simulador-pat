"""PAT 140 g (17-11-2026): guardado automático tipo «partida» con el probador de Streamlit (sin navegador).
Recorrer pantallas no crea proyectos; el primer cambio crea uno con el nombre automático y lo guarda solo (sin versiones numeradas);
una sesión nueva ofrece «Continuar con el último proyecto» y la carga como se dejó (también la planta basada en Agrozzi con sus cifras);
«Empezar de nuevo» la descarta; un error del guardado no bota la aplicación; con acceso controlado cada estudiante ve solo su
partida. Desde 04 Interfaz Streamlit: python -m pytest -q tests/test_autoguardado_app.py"""
import shutil, sqlite3
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"


@pytest.fixture()
def base(tmp_path, monkeypatch):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    with sqlite3.connect(bd) as con:                # PAT 140 h: la base real ya puede traer partidas guardadas; cada prueba parte sin ellas
        if con.execute("SELECT name FROM sqlite_master WHERE name = 'proyectos_usuario_autoguardado'").fetchone():
            con.execute("DELETE FROM proyectos_usuario_autoguardado")
        con.execute("DELETE FROM proyectos_usuario_versiones"); con.execute("DELETE FROM proyectos_usuario")   # y sin proyectos de usuario
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "blanco")
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False)
    for k in ("PAT_ACCESO", "PAT_USUARIOS", "PAT_AUTOGUARDADO"):
        monkeypatch.delenv(k, raising=False)
    import streamlit as st
    st.cache_resource.clear()                       # obtener_bd() abre la base de esta prueba
    yield bd
    st.cache_resource.clear()


def _abrir(pagina="Proyectos"):
    at = AppTest.from_file(APP, default_timeout=240)
    at.query_params["p"] = pagina
    at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _n(bd, tabla):
    with sqlite3.connect(bd) as con:
        return con.execute(f"SELECT COUNT(*) FROM {tabla}").fetchone()[0]


def _textos(at):
    return [m.value for m in at.markdown] + [c.value for c in at.caption] + [c.value for c in at.sidebar.caption]


def _con_oferta(at):
    return any(b.key == "partida_continuar" for b in at.button)


def test_recorrer_pantallas_no_crea_proyectos(base):
    n0 = _n(base, "proyectos_usuario")
    at = _abrir("Desafío")
    for p in ("Proyectos", "Temporada", "Alternativas", "Economía"):
        at.sidebar.radio(key="pagina").set_value(p); at.run()
        assert not at.exception, [e.value for e in at.exception]
    assert _n(base, "proyectos_usuario") == n0 and _n(base, "proyectos_usuario_autoguardado") == 0
    assert not _con_oferta(at)


def test_primer_cambio_crea_la_partida_y_otra_sesion_la_retoma(base):
    n0, v0 = _n(base, "proyectos_usuario"), _n(base, "proyectos_usuario_versiones")
    at = _abrir()
    at.session_state["persona_nombre"] = "Ana Pérez"
    at.run()
    assert not at.exception
    assert _n(base, "proyectos_usuario") == n0 + 1 and _n(base, "proyectos_usuario_autoguardado") == 1
    assert _n(base, "proyectos_usuario_versiones") == v0          # el guardado automático no agrega versiones numeradas
    lat = [c.value for c in at.sidebar.caption]
    assert any("Proyecto de Ana Pérez 1" in c for c in lat) and any(c.startswith(":green[Guardado automático: ") for c in lat)
    assert not any("Hay cambios sin guardar" in c for c in lat)
    # el botón «Guardar proyecto» sigue creando una versión numerada
    at.sidebar.button(key="pry_guardar_lateral").click(); at.run()
    assert _n(base, "proyectos_usuario_versiones") == v0 + 1 and _n(base, "proyectos_usuario") == n0 + 1
    # sesión nueva: ofrece continuar y la carga
    at2 = _abrir("Desafío")
    assert _con_oferta(at2) and any("Proyecto de Ana Pérez 1" in t for t in _textos(at2))
    at2.button(key="partida_continuar").click(); at2.run()
    assert not at2.exception
    assert at2.session_state["persona_nombre"] == "Ana Pérez" and at2.session_state["proyecto_abierto"]["nombre"] == "Proyecto de Ana Pérez 1"
    assert not _con_oferta(at2)


def test_empezar_de_nuevo_descarta_la_oferta(base):
    at = _abrir()
    at.session_state["persona_nombre"] = "Luis"; at.run()
    at2 = _abrir()
    assert _con_oferta(at2)
    at2.button(key="partida_nueva").click(); at2.run()
    assert not _con_oferta(at2) and "proyecto_abierto" not in at2.session_state


def test_cargar_proyecto_abre_la_pantalla_proyectos(base):
    """PAT 140 h: la oferta dice «Continuar con el último proyecto», tiene tres botones y la explicación va en un ⓘ desplegable."""
    at = _abrir()
    at.session_state["persona_nombre"] = "Eva"; at.run()
    at2 = _abrir("Desafío")
    assert _con_oferta(at2) and any(b.key == "partida_cargar" for b in at2.button) and any(b.key == "partida_nueva" for b in at2.button)
    assert any("Continuar con el último proyecto" in t for t in _textos(at2))
    assert any(e.label == "ⓘ Cómo funciona" for e in at2.expander)
    at2.button(key="partida_cargar").click(); at2.run()
    assert not at2.exception and at2.session_state["pagina"] == "Proyectos" and not _con_oferta(at2)


def test_agrozzi_vuelve_con_sus_cifras(base, monkeypatch):
    monkeypatch.setenv("PAT_INICIO", "ejemplo")
    at = _abrir()
    at.session_state["persona_nombre"] = "Ana"; at.run()
    assert _n(base, "proyectos_usuario_autoguardado") == 1
    monkeypatch.setenv("PAT_INICIO", "blanco")
    at2 = _abrir()
    at2.button(key="partida_continuar").click(); at2.run()
    from pat_sim.motor.resumen import resumen_planta
    r = resumen_planta(at2.session_state["pl"])
    assert round(r["cascada"], 1) == 9073.8 and round(r["pinch"], 1) == 9722.9


def test_proyectos_muestra_el_guardado_automatico_y_lo_abre(base):
    at = _abrir()
    at.session_state["persona_nombre"] = "Ana"; at.run()
    pid = at.session_state["proyecto_abierto"]["id"]
    at.run()
    sel = at.selectbox(key=f"pys_ver_{pid}")
    assert sel.options[0].startswith("Guardado automático")
    html = "".join(h.proto.body for h in at.get("html"))
    assert "Guardado automático" in html                            # columna de la tabla de proyectos
    assert any(b.label == "Descargar proyecto (.json)" for b in at.get("download_button"))
    at.button(key="pys_cargar").click(); at.run()
    assert not at.exception and any("Retomado el proyecto" in s.value for s in at.success)


def test_un_error_del_guardado_no_bota_la_aplicacion(base, monkeypatch):
    from pat_sim.datos import bd as BD

    def falla(*a, **k):
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(BD.BaseDatos, "autoguardar_proyecto_usuario", falla)
    at = _abrir()
    at.session_state["persona_nombre"] = "Ana"; at.run()
    assert not at.exception and not at.error
    assert any("No se pudo guardar automáticamente" in c.value for c in at.sidebar.caption)


def test_sin_autoguardado_con_la_variable(base, monkeypatch):
    monkeypatch.setenv("PAT_AUTOGUARDADO", "0")
    at = _abrir()
    at.session_state["persona_nombre"] = "Ana"; at.run()
    assert _n(base, "proyectos_usuario_autoguardado") == 0


def _entrar(usuario, clave):
    at = AppTest.from_file(APP, default_timeout=240)
    at.query_params["p"] = "Proyectos"
    at.run()
    at.text_input(key="acc_usuario").set_value(usuario); at.text_input(key="acc_clave").set_value(clave)
    next(b for b in at.button if b.label == "Entrar").click(); at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def test_acceso_controlado_cada_uno_su_partida(base, monkeypatch):
    monkeypatch.setenv("PAT_ACCESO", "usuarios")
    monkeypatch.setenv("PAT_USUARIOS", "ana.perez;estudiante;Clave123;Ana Pérez\nluis.soto;estudiante;Clave456;Luis Soto")
    at = _entrar("ana.perez", "Clave123")
    at.session_state["persona_nombre"] = "Ana María Pérez"; at.run()     # el nombre del usuario ya estaba al entrar
    with sqlite3.connect(base) as con:
        assert con.execute("SELECT usuario FROM proyectos_usuario_autoguardado").fetchall() == [("ana.perez",)]
    luis = _entrar("luis.soto", "Clave456")
    assert not _con_oferta(luis)
    ana = _entrar("ana.perez", "Clave123")
    assert _con_oferta(ana)
