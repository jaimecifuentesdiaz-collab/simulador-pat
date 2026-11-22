"""PAT 140 c (pedido de Jaime, 16-11-2026), con el probador de Streamlit, sin navegador:
- Aviso de carga más grande (cuadro centrado de 420 px, letra de 19 px, círculo de 36 px).
- Planta real y Equipos auxiliares mandan al lienzo exactamente 3 opciones por etapa, de distinto número de unidades n, con su ficha
  comparativa (3 columnas alineadas y la marca del valor más conveniente de cada fila).
- PAT 140 d (17-11-2026, «no repetir información»): la comparación ya no se repite bajo el lienzo; «Ver ficha comparativa» abre la misma
  ficha en un diálogo, con «Elegir esta opción» en cada columna (aplica con un paso de «Deshacer»). La ficha no repite filas del
  encabezado, da la fuente del precio una vez, tiene un solo gráfico de curvas y los encabezados distinguen «sin reserva» y «con reserva».
- PAT 140 e (17-11-2026): el texto bajo el gráfico va en un «ⓘ Cómo leer el gráfico» cerrado; se quitaron la regla de las 3 opciones, la base
  de cálculo y la línea de las conexiones; cada ecuación de «Costo total» lleva un ⓘ con el para qué y el por qué."""
import re
import shutil
import sys
from pathlib import Path
from streamlit.testing.v1 import AppTest

RAIZ = Path(__file__).resolve().parents[1]
APP = str(RAIZ / "app.py")
BD_ORIGEN = RAIZ.parent / "03 Base de datos" / "simulador_pat.db"
HTML = (RAIZ / "ui" / "componentes" / "lienzo_planta" / "index.html").read_text(encoding="utf-8")
if str(RAIZ) not in sys.path:
    sys.path.insert(0, str(RAIZ))
PROHIBIDO = re.compile(r"★|mejor opci[oó]n|\(menor C\)|= menor C|\(recomendada\)|Recomendación:", re.IGNORECASE)


def _app(tmp_path, monkeypatch, capturas):
    bd = tmp_path / "t.db"; shutil.copyfile(BD_ORIGEN, bd)
    monkeypatch.setenv("PAT_SIM_DB", str(bd)); monkeypatch.setenv("PAT_INICIO", "ejemplo")
    monkeypatch.delenv("PAT_TODAS_LAS_PAGINAS", raising=False); monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    at = AppTest.from_file(APP, default_timeout=240); at.run()
    assert not at.exception, [e.value for e in at.exception]
    import ui.lienzo as L
    monkeypatch.setattr(L, "lienzo", lambda datos, key=L.CLAVE: capturas.__setitem__(key, datos))
    return at


def _ir(at, pagina):
    at.sidebar.radio(key="pagina").set_value(pagina).run()
    _sin_fallas(at)


def _sin_fallas(at):
    assert not at.exception, [e.value for e in at.exception]
    assert not at.error, [e.value for e in at.error]


def _m(at):
    return {m.label: m.value for m in at.metric}


def _revisar_objetivos(objs, con_resultados):
    assert objs
    for o in objs:
        cs = o["candidatos"]
        assert len(cs) == 3 and len({c["n"] for c in cs}) == 3, (o["id"], [c["n"] for c in cs])
        assert all("mejor" not in c for c in cs)
        cp = o["comparacion"]
        assert [x["id"] for x in cp["opciones"]] == [c["id"] for c in cs]
        tit = [s["titulo"] for s in cp["secciones"]]
        assert ("Resultados del equipo" in tit) == con_resultados and {"Selección comercial", "Eficiencia en operación", "Costo total"} <= set(tit)
        for s in cp["secciones"]:
            for f in s["filas"]:
                assert len(f["valores"]) == 3 and len(f["conveniente"]) == 3 and "MM" not in " ".join(f["valores"])
        assert len(cp["curva"]["series"]) == 3
        # PAT 140 d: sin filas que repitan el encabezado ni la nota «Fuente del precio: en el encabezado»
        etqs = [f["etq"] for s in cp["secciones"] for f in s["filas"]]
        assert not {"Modelo y fabricante", "Origen del dato", "Unidades en paralelo (n)", "Necesarias (k)"} & set(etqs)
        assert not any(str(s.get("nota") or "").startswith("Fuente del precio") for s in cp["secciones"])
        assert "regla" not in cp and "base" not in cp                      # PAT 140 e: sin la regla ni la base de cálculo
        ic = {f["etq"]: f.get("info") or "" for s in cp["secciones"] if s["titulo"] == "Costo total" for f in s["filas"]}
        assert all("Para qué" in ic[e] and "Fuente" in ic[e] for e in ic if e.startswith(("Inversión instalada", "C_inv", "C_op", "C_inef", "C = ")))
        assert cp["ayuda_curvas"].startswith("Círculo: punto de operación") and "rombo: punto de diseño" in cp["ayuda_curvas"]
        for x in cp["opciones"]:
            assert (f"({x['k']} de {x['n']}, con reserva)" in x["titulo"]) if x["n"] > x["k"] else x["titulo"].endswith("sin reserva")
        assert len({x["titulo"] for x in cp["opciones"]}) == 3


def test_aviso_de_carga_grande():
    from ui import comun as C
    e = C.ESTILO
    assert "width:420px" in e and "font-size:19px" in e and "36px" in e and "box-shadow:0 12px 36px" in e
    assert 'data-test-script-state="running"' in e and "pointer-events:none" in e and '[data-testid="stSpinnerIcon"]' in e


def test_planta_real_tres_opciones_ficha_y_elegir(tmp_path, monkeypatch):
    cap = {}
    at = _app(tmp_path, monkeypatch, cap); _ir(at, "Selección de equipos")
    _revisar_objetivos(cap["sel_lienzo"]["eleccion"]["objetivos"], True)
    t = "\n".join(str(x.proto) for x in at.main) + "\n".join(str(getattr(x, "proto", "")) for x in at.get("html"))
    assert not PROHIBIDO.findall(t)
    # PAT 140 d: la tabla comparativa no se repite en la página; se abre con «Ver ficha comparativa»
    assert not any("Comparación de las 3 opciones" in x.value for x in at.markdown)
    assert not [b for b in at.button if b.key == "sel_cmp_2"]
    assert _m(at)["Etapas elegidas"] == "0 de 10"
    eid = at.session_state["sel_etapa_viva"]
    tres = {o["id"]: o for o in cap["sel_lienzo"]["eleccion"]["objetivos"]}[eid]["candidatos"]
    at.button(key="sel_ficha_ver").click().run(); _sin_fallas(at)
    assert at.session_state["sel_ficha_abierta"] == eid
    assert len([x for x in at.get("vega_lite_chart")]) <= 2          # un solo gráfico de curvas en la ficha
    # PAT 140 e: «ⓘ Cómo leer el gráfico» cerrado por defecto; sin la regla ni la base de cálculo; cada ecuación de costo con su ⓘ
    ex = [e for e in at.expander if "Cómo leer el gráfico" in str(e.label)]
    assert len(ex) == 1 and ex[0].label.startswith("ⓘ") and not ex[0].proto.expanded
    t = "\n".join(str(getattr(x, "proto", "")) for x in at.get("html")) + "\n".join(str(x.proto) for x in at.caption)
    assert "Tres opciones de distinto número" not in t and "Base de cálculo (US$ por año)" not in t and "Las conexiones se cambian" not in t
    assert t.count("ⓘ") >= 5 and "Para qué" in t and "CRF" in t
    at.button(key="sel_cmp_2").click().run(); _sin_fallas(at)
    assert _m(at)["Etapas elegidas"] == "1 de 10"
    o = {o["id"]: o for o in cap["sel_lienzo"]["eleccion"]["objetivos"]}[eid]
    assert o["elegido"] == tres[2]["id"]
    assert "sel_ficha_abierta" not in at.session_state                   # elegir cierra la ficha
    at.button(key="sel_ficha_ver").click().run(); _sin_fallas(at)
    assert at.button(key="sel_cmp_2").disabled
    at.button(key="sel_deshacer").click().run(); _sin_fallas(at)
    assert _m(at)["Etapas elegidas"] == "0 de 10"


def test_equipos_auxiliares_tres_opciones_y_elegir(tmp_path, monkeypatch):
    cap = {}
    at = _app(tmp_path, monkeypatch, cap); _ir(at, "Equipos auxiliares")
    objs = cap["aux_lienzo"]["eleccion"]["objetivos"]
    _revisar_objetivos(objs, False)
    n = len(objs)
    assert _m(at)["Auxiliares elegidos"] == f"0 de {n}"
    assert not [b for b in at.button if b.key == "aux_cmp_0"]
    at.button(key="aux_ficha_ver").click().run(); _sin_fallas(at)
    at.button(key="aux_cmp_0").click().run(); _sin_fallas(at)
    assert _m(at)["Auxiliares elegidos"] == f"1 de {n}"
    at.button(key="aux_deshacer").click().run(); _sin_fallas(at)
    assert _m(at)["Auxiliares elegidos"] == f"0 de {n}"


def test_el_componente_pinta_la_ficha_comparativa():
    assert "function fichaComparativa(o)" in HTML and "data-elegir-op" in HTML and "Elegir esta opción" in HTML
    assert ".comp .c-v.conv{background:#e3f4ec" in HTML and ".cajon.largo{bottom:auto" in HTML and "svgCurvas(" in HTML
    # PAT 140 d: un solo gráfico de curvas en la ficha (sin las mini curvas) y la presentación de la regla una sola vez
    assert "Curva η/η_max de cada opción" not in HTML and HTML.count("svgCurvas(cp.curva") == 1
    assert "Tres opciones de instalación de distinto número de unidades" not in HTML and "cp.nota_curvas" in HTML
    # PAT 140 e: ⓘ del gráfico y de cada ecuación; sin la regla, la base de cálculo ni la línea de las conexiones
    assert "cp.ayuda_curvas" in HTML and "f.info" in HTML and "ⓘ" in HTML and "<details class=\"ayuda\"><summary><b" in HTML
    assert "cp.regla" not in HTML and "cp.base" not in HTML and "Las conexiones se cambian en Planta ficticia (Diseño). Aquí se eligen" not in HTML


def test_ficha_sin_repeticiones_y_curvas_que_coinciden():
    from ui import eleccion_comun as EC
    serie = lambda i, k: dict(id=f"o{i}", etq=f"o{i}", eta=[0.4, 0.8, 1.0, 0.9], op=dict(x=10.0, eta=1.0), diseno_x=10.0)
    comp = dict(equipo="F1", unidad="t/h", requerida=10.0, regla="Regla. Ordenadas por n; las demás quedan en la tabla «Elegir por etapa».",
                base="Base.", opciones=[dict(id="o0", titulo="1 × Eq", n=1, k=1, fabricante="f", origen="Williams (estimado)", fuente="F"),
                                        dict(id="o1", titulo="2 × Eq", n=2, k=1, fabricante="f", origen="Williams (estimado)", fuente="F")],
                secciones=[dict(titulo="Selección comercial", filas=[dict(etq="Modelo y fabricante", valores=["a", "b"], conveniente=[0, 0]),
                                                                     dict(etq="Capacidad por unidad", valores=["1", "2"], conveniente=[0, 0])]),
                           dict(titulo="Costo total", filas=[], nota="Fuente del precio: en el encabezado de cada columna.")],
                curva=dict(x=[0, 5, 10, 15], series=[serie(0, 1), serie(1, 1)], y_min=0.25, y_max=1.02, fuente="Curva."))
    d = EC.depurar_ficha(comp)
    assert [o["titulo"] for o in d["opciones"]] == ["1 × Eq sin reserva", "2 × Eq (1 de 2, con reserva)"]
    assert [f["etq"] for s in d["secciones"] for f in s["filas"]] == ["Capacidad por unidad"]
    assert d["secciones"][1]["nota"] == "" and d["regla"] == "Regla. Ordenadas por n."
    assert d["nota_curvas"].startswith("Las 2 curvas coinciden") and EC.depurar_ficha(d) is d
    h = EC.html_comparativa(comp)
    assert h.count("Fuente del precio") == 0 and "Modelo y fabricante" not in h and "con reserva" in h
    assert EC.para_lienzo_ficha(comp)["nota_curvas"]
    # PAT 140 e: texto único del «ⓘ Cómo leer el gráfico» y ⓘ en la etiqueta de las ecuaciones de costo
    pl = EC.para_lienzo_ficha(comp)
    assert pl["ayuda_curvas"].startswith("Círculo: punto de operación") and "Curva." in pl["ayuda_curvas"] and "coinciden" in pl["ayuda_curvas"]
    assert "regla" not in pl and "base" not in pl
    comp["secciones"][1]["filas"] = [dict(etq="C_inv (inversión anualizada)", valores=["US$ 1", "US$ 2"], conveniente=[1, 0], info="Para qué: x. Fuente: y.")]
    h = EC.html_comparativa(comp)
    assert "<details" in h and "ⓘ" in h and "Para qué: x. Fuente: y." in h
