"""PAT 139b (14-11-2026): con el probador de Streamlit, sin navegador.
- Planta real y Equipos auxiliares no muestran marca de «mejor opción» (★, «mejor», «menor C» como recomendación) y los candidatos que
  van al lienzo no traen la clave «mejor», pero sí C_inv, C_op, C_inef, C, A, η en operación, origen y fuente.
- Lo que se manda al lienzo trae, por etapa, el dibujo de sus n unidades en paralelo (n símbolos, tope 6) y la curva de eficiencia
  de la línea con su punto de operación.
- La lista de candidatos se puede ordenar por otra columna."""
import re
import shutil
import sys
from pathlib import Path
import pytest
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]
APP = str(RAIZ / "app.py")
BD_ORIGEN = RAIZ.parent / "03 Base de datos" / "simulador_pat.db"
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))

PROHIBIDO = re.compile(r"★|mejor opci[oó]n|\(menor C\)|= menor C|es la de menor C|menor C posible|\(recomendada\)|Recomendación:|la primera es la mejor",
                       re.IGNORECASE)


def _app(tmp_path, monkeypatch, capturas):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "ejemplo")
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False); monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=240); at.run()
    assert not at.exception, [e.value for e in at.exception]
    # después de la primera ejecución (app.py recarga ui/* la primera vez): el mismo módulo que usa la aplicación
    import ui.lienzo as L
    monkeypatch.setattr(L, "lienzo", lambda datos, key=L.CLAVE: capturas.__setitem__(key, datos))
    return at


def _ir(at, pagina):
    at.sidebar.radio(key="pagina").set_value(pagina).run()
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def _textos(at) -> str:
    """Todo lo que la pantalla muestra en el cuerpo: textos, tablas HTML, ayudas y opciones de las listas."""
    partes = []

    def recorrer(n):
        p = getattr(n, "proto", None)
        if p is not None:
            partes.append(str(p))
        for h in getattr(n, "children", {}).values() if isinstance(getattr(n, "children", None), dict) else []:
            recorrer(h)
    recorrer(at.main)
    for s in at.selectbox:
        partes += [str(o) for o in s.options]
    return "\n".join(partes)


def _sin_marcas(at):
    t = _textos(at)
    assert "C_inv" in t and "Generar automáticamente" in t           # se leyó la pantalla de verdad
    hallados = sorted(set(m.group(0) for m in PROHIBIDO.finditer(t)))
    assert not hallados, hallados


def test_planta_real_sin_mejor_con_paralelo_y_curva(tmp_path, monkeypatch):
    cap = {}
    at = _app(tmp_path, monkeypatch, cap); _ir(at, "Selección de equipos")
    _sin_marcas(at)
    at.button(key="sel_generar").click().run()
    assert not at.exception and not at.error
    _sin_marcas(at)
    d = cap["sel_lienzo"]
    for o in d["eleccion"]["objetivos"]:
        for c in o["candidatos"]:
            assert "mejor" not in c and {"C", "Ci", "Co", "Cf", "A", "eta", "org", "fuente"} <= set(c)
    eqs = {k: v for k, v in d["real"]["equipos"].items() if v["seleccion"]}
    assert len(eqs) == 10
    for v in eqs.values():
        assert v["dibujo"]["n"] == v["n"] and v["dibujo"]["n_dibujados"] == min(v["n"], 6)
    assert any(v["n"] > 1 for v in eqs.values())
    ce = d["curva_eficiencia"]
    assert ce and ce["operacion"]["produccion"] > 0 and 0 < ce["operacion"]["eta_linea"] <= 1 and ce["critico"] in d["real"]["equipos"]
    assert len(ce["x"]) == len(ce["eta_linea"]) and ce["zona"]


def test_planta_real_ordenar_por_otra_columna(tmp_path, monkeypatch):
    at = _app(tmp_path, monkeypatch, {}); _ir(at, "Selección de equipos")
    at.selectbox(key="sel_etapa_viva").set_value("W1").run()
    at.selectbox(key="sel_orden_cand").set_value("A").run()
    assert not at.exception and not at.error
    ops = [o for o in at.selectbox(key="sel_viva_W1").options if o != "(sin elegir)"]
    As = [float(re.search(r"· A ([\d.,]+) %$", o).group(1).replace(".", "").replace(",", ".")) for o in ops]
    assert len(As) > 1 and As == sorted(As, reverse=True)
    _sin_marcas(at)


def test_equipos_auxiliares_sin_mejor_y_paralelo_de_los_elegidos(tmp_path, monkeypatch):
    cap = {}
    at = _app(tmp_path, monkeypatch, cap); _ir(at, "Equipos auxiliares")
    _sin_marcas(at)
    at.button(key="aux_generar").click().run()
    assert not at.exception and not at.error
    _sin_marcas(at)
    d = cap["aux_lienzo"]
    objs = at.session_state["aux_objs_vigentes"]
    for o in d["eleccion"]["objetivos"]:
        assert all("mejor" not in c for c in o["candidatos"])
    par = d["eleccion"]["paralelo"]
    el = {o["id"]: o for o in d["eleccion"]["objetivos"]}
    for ob in objs:
        e = next((c for c in ob["candidatos"] if c["id"] == el[ob["id"]]["elegido"]), None)
        for di in ob["dianas"]:
            if e is not None and e["n"] > 1:
                assert par[di]["n"] == e["n"] and par[di]["n_dibujados"] == min(e["n"], 6)
            else:
                assert di not in par
