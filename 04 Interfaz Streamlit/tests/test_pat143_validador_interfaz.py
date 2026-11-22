"""PAT 143 (tarea 6): conexión libre y validador en los cuatro lienzos, con el probador de Streamlit (sin navegador).

La advertencia que no deja avanzar y el botón «Pista» (ui/validacion.py) en Planta ficticia, Planta real, Equipos auxiliares y Lazos
de control; la franja del proceso deja «Etapa siguiente» deshabilitada mientras haya errores. Desde 04 Interfaz Streamlit:
python -m pytest -q tests/test_pat143_validador_interfaz.py
"""
import shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"
CRUZADA = dict(evento="conectar", datos=dict(origen="F1", puerto_origen="descarte", destino="W5", puerto_destino="vapor"))


@pytest.fixture()
def at(tmp_path, monkeypatch):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "ejemplo"); monkeypatch.setenv("PAT_AUTOGUARDADO", "0")
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False)            # solo la pantalla elegida, como en el navegador
    a = AppTest.from_file(APP, default_timeout=300); a.run()
    assert not a.exception
    return a


def _ir(a, pagina):
    a.sidebar.radio(key="pagina").set_value(pagina).run()
    assert not a.exception, [e.value for e in a.exception]


def _eventos(a, clave, evs):
    a.session_state[clave] = dict(eventos=[dict(e, seq=i + 1) for i, e in enumerate(evs)], seq=len(evs))
    a.run()
    assert not a.exception, [e.value for e in a.exception]


def _advertencia(a):
    return [e.value for e in a.error if "no deja" in e.value]


def _botones(a):
    return {b.key for b in a.button}


def test_ejemplo_sin_advertencia_en_los_cuatro_lienzos(at):
    for p, v in (("Diseño", "ficticia"), ("Selección de equipos", "real"), ("Equipos auxiliares", "auxiliares"), ("Lazos de control", "lazos")):
        _ir(at, p)
        assert not _advertencia(at) and f"val_pista_btn_{v}" not in _botones(at)
        assert not at.button(key="flujo_sig").disabled


def test_planta_ficticia_conexion_libre_bloquea_y_pista_progresiva(at):
    _ir(at, "Diseño")
    _eventos(at, "lienzo_planta", [CRUZADA])
    pl = at.session_state.pl
    assert len(pl.incompatibles()) == 1 and not pl.resuelta                  # la conexión entró y el cálculo se detuvo
    adv = _advertencia(at)
    assert adv and "distinto tipo" in adv[0]
    assert at.button(key="flujo_sig").disabled                                # no deja avanzar
    for n in (1, 2, 3):
        at.button(key="val_pista_btn_ficticia").click().run()
        assert len([x for x in at.info if x.value.startswith("**Pista")]) == n
    assert at.button(key="val_pista_btn_ficticia").disabled                  # sin más pistas que la tercera
    _eventos(at, "lienzo_planta", [CRUZADA, dict(evento="quitar_conexion", datos=dict(clave="F1.descarte>W5.vapor"))])
    assert at.session_state.pl.resuelta and not _advertencia(at) and not at.button(key="flujo_sig").disabled


def test_planta_real_candidato_que_no_calza_bloquea(at):
    _ir(at, "Selección de equipos")
    c = at.session_state["sel_cands_vigentes"]["W3"][0]
    _eventos(at, "sel_lienzo", [dict(evento="elegir", datos=dict(objetivo="W3", candidato=c["id"], destino="W2"))])
    adv = _advertencia(at)
    assert adv and "W2" in adv[0] and at.button(key="flujo_sig").disabled
    at.button(key="val_pista_btn_real").click().run()
    assert any(x.value.startswith("**Pista 1.**") for x in at.info)


def test_auxiliares_y_lazos_heredan_el_error_de_la_planta_ficticia(at):
    _ir(at, "Diseño")
    _eventos(at, "lienzo_planta", [CRUZADA])
    for p, v in (("Equipos auxiliares", "auxiliares"), ("Lazos de control", "lazos")):
        _ir(at, p)
        adv = _advertencia(at)
        assert adv and "Planta ficticia" in adv[0] and f"val_pista_btn_{v}" in _botones(at)


def test_lazos_lazo_roto_bloquea_y_se_corrige(at):
    _ir(at, "Lazos de control")
    evs = [dict(evento="agregar_lazo", datos=dict(variable="temperatura", equipo="W1"))]
    _eventos(at, "lazos_lienzo", evs)
    assert not _advertencia(at)
    n = next(i.numero for i in at.session_state.pl.instrumentos if i.letras == "TIC" and i.equipo == "W1" and i.conexiones)
    evs.append(dict(evento="quitar_senal", datos=dict(clave=f"TIC-{n}>instrumento:TY-{n}")))
    _eventos(at, "lazos_lienzo", evs)
    adv = _advertencia(at)
    assert adv and f"TIC-{n}" in adv[0] and at.button(key="flujo_sig").disabled
    at.button(key="val_pista_btn_lazos").click().run()
    at.button(key="val_pista_btn_lazos").click().run()
    assert any(x.value.startswith("**Pista 2.**") and f"El lazo {n} tiene" in x.value for x in at.info)
    evs.append(dict(evento="conectar_senal", datos=dict(origen=f"TIC-{n}", tipo="instrumento", destino=f"TY-{n}", senal="electrica")))
    _eventos(at, "lazos_lienzo", evs)
    assert not _advertencia(at) and not at.button(key="flujo_sig").disabled
