"""Pruebas de la interfaz con el probador de Streamlit (sin navegador). Desde 04 Interfaz Streamlit: python -m pytest -q tests"""
import math, os, shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"


@pytest.fixture()
def app(tmp_path, monkeypatch):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd))
    monkeypatch.setenv("PAT_TODAS_LAS_PAGINAS", "1")      # PAT 134: con el índice lateral se ejecutan todas las pantallas
    at = AppTest.from_file(APP, default_timeout=170); at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _metricas(at):
    return {m.label: m.value for m in at.metric}


def test_cifras_del_capitulo_1(app):
    m = _metricas(app)
    assert m["Cascada en serie"] == "9.073,8 kW" and m["Objetivo pinch"] == "9.722,9 kW" and m["Solo condensados (alt. 2)"] == "6.621,9 kW"
    # PAT 133: Economía evalúa la alternativa ganadora del multicriterio del Capítulo 3 (A3), ya no la cascada
    assert m["Gas desplazado por A3 (colector común de condensados)"] == "79.023 MMBtu" and m["CO2 evitado por temporada"] == "4.131 t"


def test_veinticinco_pantallas_sin_errores(app):
    # PAT 135: veinticinco pantallas en el índice lateral (se suman Desafío, Selección de equipos, Layout, Costeo, Riesgo económico y Mantenedor);
    # las únicas pestañas que quedan son las diez de Calculadoras
    assert len(app.tabs) == 10 and not app.error
    assert len(app.sidebar.radio(key="pagina").options) == 25


def test_indice_lateral_muestra_solo_la_pantalla_elegida(tmp_path, monkeypatch):
    """PAT 134: sin PAT_TODAS_LAS_PAGINAS se ejecuta solo la pantalla elegida en el índice de la barra lateral."""
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False)
    at = AppTest.from_file(APP, default_timeout=170); at.run()
    assert not at.exception and at.session_state.pagina == "Desafío" and len(at.tabs) == 0   # PAT 135: se abre en Desafío
    at.sidebar.radio(key="pagina").set_value("Calculadoras").run()
    assert not at.exception and len(at.tabs) == 10


def test_rubro_elegido_en_escenario_vale_para_todas_las_pestanas(app):
    """PAT 132: al elegir pellet en Escenario se carga su planta sin botón y Operación y Calidad SPC trabajan con ella."""
    from pat_sim.escenarios import pellet
    app.selectbox(key="esc_rubro").set_value("pellet").run()
    assert app.session_state.pl.nombre == pellet.NOMBRE and app.session_state.op.rubro == "pellet" and not app.exception


def test_operacion_calidad_y_evaluacion(app):
    """PAT 130: turnos de 8 h, muestra con resultado diferido y evaluación que se revela al finalizar."""
    app.button(key="op_muestra").click(); app.run()
    for _ in range(3):
        app.button(key="op_turno").click(); app.run()
    op = app.session_state.op
    assert not app.exception and op.turno == 3 and len(op.lab) == 1 and not op.pendientes
    app.button(key="ev_finalizar").click(); app.run()
    assert not app.exception and app.session_state.op.finalizada and "Evaluación automática revelada" in _metricas(app)


def test_lazo_isa51_valida_las_letras(app):
    def agregar(letras, num):
        [w for w in app.text_input if w.label.startswith("Letras de identificación")][0].set_value(letras)
        [w for w in app.text_input if w.label == "Número de lazo"][0].set_value(num)
        [b for b in app.button if b.label == "Agregar lazo"][0].click(); app.run()
    n0 = len(app.session_state.pl.instrumentos)
    agregar("XYZQ9", "999"); assert app.error and len(app.session_state.pl.instrumentos) == n0
    agregar("tic", "102"); assert len(app.session_state.pl.instrumentos) == n0 + 1
    agregar("TIC", "102"); assert len(app.session_state.pl.instrumentos) == n0 + 1      # repetido


def test_cambiar_parametro_recalcula(app):
    app.selectbox(key="par_eq").set_value("W1"); app.run()
    app.text_input(key="par_W1_T_salida__cl").set_value("96,0")   # PAT 133: campos con coma decimal
    [b for b in app.button if b.label.startswith("Aplicar parámetros")][0].click(); app.run()
    assert not app.exception and _metricas(app)["Sumidero: Hot break"] == "17.428,9 kW"


def test_guardar_version_y_corrida(app):
    [b for b in app.button if b.label.startswith("Guardar versión")][0].click(); app.run()
    assert "Guardada la versión 2 con su corrida." in [s.value for s in app.success]


def _cargar_rubro(at, rubro):
    [s for s in at.selectbox if s.label == "Rubro"][0].set_value(rubro); at.run()
    at.button(key=f"cargar_{rubro}").click(); at.run()
    assert not at.exception, [e.value for e in at.exception]


@pytest.mark.parametrize("rubro", ["pellet", "chip", "lena"])
def test_rubros_de_biomasa_cargan_su_escenario(app, rubro):
    from pat_sim.escenarios import pellet, chip, lena
    mod = {"pellet": pellet, "chip": chip, "lena": lena}[rubro]
    _cargar_rubro(app, rubro)
    assert app.session_state.pl.nombre == mod.NOMBRE and app.session_state.pl.resuelta
    m = _metricas(app)
    assert m["Producto"] == C_fmt(mod.BASE["produccion"]) + " t/h" and "Biomasa desplazada por la cascada" in m
    assert len(app.tabs) == 10 and not app.error


def C_fmt(v):
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def test_lienzo_de_diseno_aplica_eventos(app):
    """El simulador de Diseño recibe los eventos del lienzo (como los manda el navegador) y recalcula (PAT 128)."""
    evs = [dict(evento="agregar", datos=dict(tipo="trituradora", x=300, y=500), seq=1),
           dict(evento="conectar", datos=dict(origen="F1", puerto_origen="descarte", destino="Z2", puerto_destino="entrada"), seq=2),
           dict(evento="parametro", datos=dict(id="Z2", clave="capacidad", valor=10), seq=3)]
    app.session_state["lienzo_planta"] = dict(eventos=evs, seq=3); app.run()
    pl = app.session_state.pl
    assert not app.exception and "Z2" in pl.equipos and pl.resuelta and app.session_state["lienzo_seq"] == 3
    assert pl.equipos["Z2"].utilizacion() > 1                       # sobrecarga: recibe el descarte de F1
    app.session_state["lienzo_planta"] = dict(eventos=evs, seq=3); app.run()   # los eventos repetidos se ignoran
    assert len([e for e in pl.equipos if e.startswith("Z")]) == 2
