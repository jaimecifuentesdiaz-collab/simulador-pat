"""PAT 139 (punto 6): recorrido de la Planta real y de Equipos auxiliares con el probador de Streamlit: elegir un candidato,
generar automáticamente, deshacer dos veces, eventos del lienzo (elegir y mover) y planta vacía, sin excepciones."""
import shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")
BD_ORIGEN = Path(__file__).resolve().parents[2] / "03 Base de datos" / "simulador_pat.db"


def _app(tmp_path, monkeypatch, inicio="ejemplo"):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", inicio)
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False); monkeypatch.delenv("TAVILY_API_KEY", raising=False)   # sin internet
    at = AppTest.from_file(APP, default_timeout=240); at.run()
    assert not at.exception, [e.value for e in at.exception]
    return at


def _ir(at, pagina):
    at.sidebar.radio(key="pagina").set_value(pagina).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def _m(at):
    return {m.label: m.value for m in at.metric}


def _sin_fallas(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def test_planta_real_elegir_generar_y_deshacer_dos_veces(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch); _ir(at, "Selección de equipos")
    assert _m(at)["Etapas elegidas"] == "0 de 10" and any("Tavily" in x.value for x in at.info)
    cands = at.session_state["sel_cands_vigentes"]
    at.selectbox(key="sel_etapa_viva").set_value("W1").run()
    at.selectbox(key="sel_viva_W1").set_value(cands["W1"][-1]["id"]).run(); _sin_fallas(at)
    m = _m(at)
    assert m["Etapas elegidas"] == "1 de 10" and m["Disponibilidad del sistema A_sist"] != "—" and "M/año" in m["C total de la planta"]
    at.button(key="sel_generar").click().run(); _sin_fallas(at)
    assert _m(at)["Etapas elegidas"] == "10 de 10"
    at.button(key="sel_deshacer").click().run(); _sin_fallas(at)
    assert _m(at)["Etapas elegidas"] == "1 de 10" and at.session_state["sel_viva_W1"] == cands["W1"][-1]["id"]
    at.button(key="sel_deshacer").click().run(); _sin_fallas(at)
    assert _m(at)["Etapas elegidas"] == "0 de 10" and at.session_state.pl.resuelta


def test_planta_real_eventos_del_lienzo(tmp_path, monkeypatch):
    """Lo que manda el navegador al soltar un candidato sobre su etapa y al mover un equipo; Ctrl+Z deshace el movimiento."""
    at = _app(tmp_path, monkeypatch); _ir(at, "Selección de equipos")
    cid = at.session_state["sel_cands_vigentes"]["Z1"][0]["id"]
    x0 = at.session_state.pl.equipos["Z1"].x
    evs = [dict(evento="elegir", datos=dict(objetivo="Z1", candidato=cid), seq=1),
           dict(evento="mover", datos=dict(id="Z1", x=x0 + 100, y=at.session_state.pl.equipos["Z1"].y), seq=2)]
    at.session_state["sel_lienzo"] = dict(eventos=evs, seq=2); at.run(); _sin_fallas(at)
    pl = at.session_state.pl
    assert at.session_state["sel_lienzo_seq"] == 2 and pl.equipos["Z1"].x == x0 + 100 and _m(at)["Etapas elegidas"] == "1 de 10"
    at.session_state["sel_lienzo"] = dict(eventos=evs + [dict(evento="deshacer", datos={}, seq=3)], seq=3); at.run(); _sin_fallas(at)
    assert pl.equipos["Z1"].x == x0 and _m(at)["Etapas elegidas"] == "1 de 10"


def test_equipos_auxiliares_elegir_generar_y_deshacer_dos_veces(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch); _ir(at, "Equipos auxiliares")
    objs = at.session_state["aux_objs_vigentes"]
    assert objs and _m(at)["Auxiliares elegidos"] == f"0 de {len(objs)}"
    oid = objs[0]["id"]
    at.selectbox(key="aux_obj_viva").set_value(oid).run()
    at.selectbox(key=f"aux_viva_{oid}").set_value(objs[0]["candidatos"][1]["id"]).run(); _sin_fallas(at)
    assert _m(at)["Auxiliares elegidos"] == f"1 de {len(objs)}"
    at.button(key="aux_generar").click().run(); _sin_fallas(at)
    assert _m(at)["Auxiliares elegidos"] == f"{len(objs)} de {len(objs)}"
    at.button(key="aux_deshacer").click().run(); _sin_fallas(at)
    assert _m(at)["Auxiliares elegidos"] == f"1 de {len(objs)}"
    at.button(key="aux_deshacer").click().run(); _sin_fallas(at)
    assert _m(at)["Auxiliares elegidos"] == f"0 de {len(objs)}"


def test_planta_vacia_avisa_sin_fallar(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, inicio="blanco")
    for p in ("Selección de equipos", "Equipos auxiliares"):
        _ir(at, p)
        assert any("vacía" in x.value for x in at.info)


@pytest.mark.parametrize("rubro", ["pellet", "chip", "lena"])
def test_rubros_de_biomasa(tmp_path, monkeypatch, rubro):
    at = _app(tmp_path, monkeypatch); _ir(at, "Escenario")
    at.selectbox(key="esc_rubro").set_value(rubro).run(); _sin_fallas(at)
    _ir(at, "Selección de equipos")
    at.button(key="sel_generar").click().run(); _sin_fallas(at)
    n = len(at.session_state["sel_cands_vigentes"])
    assert _m(at)["Etapas elegidas"] == f"{n} de {n}"
    _ir(at, "Equipos auxiliares")
    if at.session_state["aux_objs_vigentes"]:
        at.button(key="aux_generar").click().run(); _sin_fallas(at)
        at.button(key="aux_deshacer").click().run(); _sin_fallas(at)
