"""PAT 140 (16-11-2026, pedido de Jaime): el cuadro «Propiedades» del lienzo trae todos los parámetros del equipo (también las etiquetas de
texto), se eliminan el formulario «Todos los parámetros de un equipo», el diagrama ISO 10628 y la tabla de balance por equipo de Planta
ficticia, y mientras la página se vuelve a ejecutar se ve un círculo que gira con el motivo. Desde 04 Interfaz Streamlit: python -m pytest -q tests"""
import importlib, shutil
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]
APP = str(RAIZ / "app.py")
BD_ORIGEN = RAIZ.parent / "03 Base de datos" / "simulador_pat.db"
HTML = (RAIZ / "ui" / "componentes" / "lienzo_planta" / "index.html").read_text(encoding="utf-8")


def _app(tmp_path, monkeypatch, capturas=None, spinners=None):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "ejemplo")
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False); monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=240); at.run()
    assert not at.exception, [e.value for e in at.exception]
    import streamlit as st
    import ui.lienzo as L
    if capturas is not None:                       # lo que el componente recibe (el navegador no existe en AppTest)
        monkeypatch.setattr(L, "lienzo", lambda datos, key=L.CLAVE: capturas.__setitem__(key, datos))
    if spinners is not None:                       # los textos de carga (st.spinner no aparece en el árbol de AppTest)
        from contextlib import nullcontext
        monkeypatch.setattr(st, "spinner", lambda texto="", **kw: (spinners.append(texto), nullcontext())[1])
    return at


def _ir(at, pagina):
    at.sidebar.radio(key="pagina").set_value(pagina).run()
    assert not at.exception, [e.value for e in at.exception]


def _todo_el_texto(at) -> str:
    """Todo lo que la pantalla muestra en el cuerpo (cada elemento del árbol, también las tablas HTML y las ayudas)."""
    partes = []

    def recorrer(n):
        p = getattr(n, "proto", None)
        if p is not None:
            partes.append(str(p))
        for h in getattr(n, "children", {}).values() if isinstance(getattr(n, "children", None), dict) else []:
            recorrer(h)
    recorrer(at.main)
    partes += [e.label for e in at.expander]
    return "\n".join(map(str, partes))


def test_planta_ficticia_sin_formulario_diagrama_ni_balance(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    _ir(at, "Diseño")
    texto = _todo_el_texto(at)
    assert "Todos los parámetros de un equipo" not in texto and "Diagrama de flujo ISO 10628" not in texto
    assert "Balance por equipo y capacidad efectiva" not in texto
    assert not [w for w in at.selectbox if w.key == "par_eq"] and not [d for d in at.get("download_button")]   # ni formulario ni SVG
    assert "Tabla de corrientes" in texto          # lo demás de la pantalla sigue
    assert any(e.label.startswith("Catálogo de equipos por función") for e in at.expander)


def test_restricciones_y_resto_no_dependian_de_la_tabla(tmp_path, monkeypatch):
    from ui import p_diseno
    assert not hasattr(p_diseno, "tabla_capacidad") and not hasattr(p_diseno, "COLS_CAPACIDAD")
    at = _app(tmp_path, monkeypatch)
    for pagina in ("Operación", "Selección de equipos", "Equipos auxiliares", "Costeo"):
        _ir(at, pagina)
        assert not at.error, (pagina, [e.value for e in at.error])


@pytest.mark.parametrize("rubro,modulo", [("tomate", "agrozzi"), ("pellet", "pellet"), ("chip", "chip"), ("lena", "lena")])
def test_el_cuadro_propiedades_recibe_todos_los_parametros(rubro, modulo, tmp_path, monkeypatch):
    """Los cuatro rubros: cada parámetro de cada equipo (lo que mostraba el formulario) llega al componente con nombre, unidad, categoría
    (Agrozzi, Supuesto, Literatura, Usuario…), fuente y justificación; las etiquetas de texto llegan como tipo «texto»."""
    from pat_sim.motor import lienzo as LZ
    pl = importlib.import_module(f"pat_sim.escenarios.{modulo}").crear()
    sol, motivo = LZ.resolver_parcial(pl)
    datos = LZ.datos_lienzo(pl, sol, motivo, {"todos": dict(nombre="x", equipos=[])})
    n_texto = 0
    for e in datos["equipos"]:
        eq = pl.equipos[e["id"]]
        por_clave = {p["clave"]: p for p in e["params"]}
        assert list(por_clave) == list(eq.params), f"{e['id']}: faltan parámetros en el cuadro"
        for clave, p in eq.params.items():
            q = por_clave[clave]
            assert q["nombre"] == p.nombre and q["unidad"] == p.unidad and q["categoria"] == p.categoria
            assert q["fuente"] == p.fuente and q["justificacion"] == p.justificacion
            if isinstance(p.valor, str):
                n_texto += 1
                assert q["tipo"] == "texto" and q["valor"] == p.valor and not q["deslizador"]
    assert n_texto > 0


def test_la_pantalla_manda_los_parametros_nuevos_al_componente(tmp_path, monkeypatch):
    capturas = {}
    at = _app(tmp_path, monkeypatch, capturas)
    _ir(at, "Diseño")
    eqs = {e["id"]: e for e in capturas["lienzo_planta"]["equipos"]}
    w3 = next(e for e in eqs.values() if e["tipo"] == "evaporador_multiefecto")
    textos = {p["clave"]: p for p in w3["params"] if p["tipo"] == "texto"}
    assert {"modelo", "etiqueta_vapor", "etiquetas_condensados"} <= set(textos)
    assert textos["etiquetas_condensados"]["valor"] and textos["modelo"]["categoria"] == "Usuario"
    assert all(p["categoria"] for e in eqs.values() for p in e["params"])


def test_un_texto_editado_en_el_cuadro_cambia_el_parametro(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch)
    _ir(at, "Diseño")
    evs = [dict(evento="parametro", datos=dict(id="W3", clave="modelo", valor="Modelo de prueba 7"), seq=1)]
    at.session_state["lienzo_planta"] = dict(eventos=evs, seq=1); at.run()
    assert not at.exception and at.session_state.pl.equipos["W3"].params["modelo"].valor == "Modelo de prueba 7"
    evs.append(dict(evento="parametro", datos=dict(id="W3", clave="modelo", valor=""), seq=2))
    at.session_state["lienzo_planta"] = dict(eventos=evs, seq=2); at.run()
    assert not at.exception and at.session_state.pl.equipos["W3"].params["modelo"].valor == ""


def test_el_componente_pinta_texto_ayuda_y_fuente(tmp_path):
    assert 'p.tipo === "texto"' in HTML and 'type="text" data-k="${k}" data-ev="parametro"' in HTML and "Modelo y etiquetas" in HTML
    assert "const marca = " in HTML and "${et} ${marca}" in HTML            # ayuda «i» y categoría también en los de verdad o falso y fijados
    assert "formulario de abajo" not in HTML and "arrastrándolo en el lienzo" in HTML          # la posición se cambia arrastrando
    assert 'e.params.map(p => [p.clave, p.nombre])' not in HTML              # los textos no se ofrecen como parámetro que mide un instrumento


def test_texto_de_carga_en_el_estilo_y_en_los_pasos_lentos(tmp_path, monkeypatch):
    from ui import comun as C
    assert 'data-test-script-state="running"' in C.ESTILO and C.TXT_ACTUALIZANDO in C.ESTILO and "animateTransform" in C.ESTILO
    assert '[data-stale="true"]{opacity:0.85' in C.ESTILO and "[data-testid=\"stSpinner\"]" in C.ESTILO
    spinners = []
    at = _app(tmp_path, monkeypatch, spinners=spinners)
    _ir(at, "Diseño")
    assert C.TXT_RECALCULANDO in spinners and C.TXT_RECALCULANDO == "Recalculando la planta…"
    spinners.clear()
    _ir(at, "Selección de equipos")
    assert any(t.startswith("Buscando equipos reales (") and t.endswith("base de respaldo)…") for t in spinners), spinners
    assert C.TXT_BUSCANDO_EQUIPOS == "Buscando equipos reales (Tavily y base de respaldo)…"
    for t in (C.TXT_RECALCULANDO, C.TXT_BUSCANDO_EQUIPOS, C.TXT_BUSCANDO_RESPALDO, C.TXT_BUSCANDO_FICHAS, C.TXT_ACTUALIZANDO):
        assert "MM" not in t and "—" not in t and " don " not in t
