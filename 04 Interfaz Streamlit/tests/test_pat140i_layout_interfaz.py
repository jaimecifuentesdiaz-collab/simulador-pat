"""PAT 140 i (pedidos de Jaime, 19-11-2026, pantalla Layout): arrastre de equipos superpuestos, leyenda de servicios con color, etiqueta
corta de la bandeja, orientación isométrica sincronizada con la lista y supuestos de la red eléctrica en un desplegable con ⚠."""
import json
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[1]
HTML_PLANO = RAIZ / "ui" / "componentes" / "layout_planta" / "index.html"
HTML_ISO = RAIZ / "ui" / "componentes" / "isometrico" / "index.html"
SRC = (RAIZ / "ui" / "p_layout.py").read_text(encoding="utf-8")

TEXTO_ELEC = ("Supuesto: 380 V trifásico 50 Hz, tensión de baja tensión industrial habitual en Chile; factor de potencia 0,85; caída de "
              "tensión máxima 3 % en el alimentador (criterio usual; verificar con el pliego técnico vigente de la SEC). Supuesto: "
              "capacidades del orden de IEC 60364-5-52, tabla B.52.12, método E (cable multipolar de cobre XLPE en bandeja perforada, "
              "30 °C, tres conductores cargados); verificar con la tabla del fabricante del cable. Los largos quedan en "
              "st.session_state[\"layout\"][\"cables_m\"] y el detalle en [\"cables\"].")


def _datos_superpuestos():
    """Datos del componente del plano para Agrozzi con B1 encima de la sala eléctrica."""
    from pat_sim.escenarios import agrozzi
    from pat_sim.motor import layout as LY, plano_detalle as PD
    from ui import p_layout as PL
    pl = agrozzi.crear().resolver()
    lay = LY.estado_layout(pl)
    lay.update(version=1, seq=0, pasillo=LY.PASILLO_M, h_rack=LY.H_RACK_M, accesorios=LY.ACCESORIOS, overrides={})
    c = lay["red"]["ccm"]
    lay["posiciones"]["B1"] = [c[0] - 1.0, c[1], 0]
    lay.update(LY.estado_layout(pl, lay))
    m = PD.construir(lay, {k: e.nombre for k, e in pl.equipos.items()}, pl, proyecto=pl.nombre)
    return PL._datos_componente(pl, lay, None, m)


def _navegador():
    pw = pytest.importorskip("playwright.sync_api")
    try:
        p = pw.sync_playwright().start()
        return p, p.chromium.launch()
    except Exception as e:                                   # sin Chromium instalado
        pytest.skip(f"sin Chromium para playwright: {e}")


# ------------------------------------------------------------------ 1) arrastre de un equipo superpuesto
def test_capas_sobre_los_equipos_no_capturan_el_puntero():
    t = HTML_PLANO.read_text(encoding="utf-8")
    assert "#mundo > g:not(#g-eq), #sobre, #grilla{pointer-events:none}" in t
    assert "function equipoEn(" in t and "equipoEn(mx, my)" in t
    # donde se superponen manda el equipo seleccionado, que vuelve de Python si el componente se monta de nuevo
    assert "const id = enSel ? sel" in t and "if (primera && D.sel && !sel) sel = D.sel;" in t
    assert 'sel=lay.get("sel"))' in SRC and 'lay["sel"] = valor.get("sel")' in SRC
    assert "aviso_sup = st.empty()" in SRC                                   # aviso en espacio fijo: el plano no se vuelve a montar


def test_equipo_superpuesto_se_arrastra_y_el_aviso_se_actualiza():
    d = _datos_superpuestos()
    p, b = _navegador()
    try:
        pg = b.new_page(viewport={"width": 1400, "height": 820})
        pg.goto(HTML_PLANO.as_uri())
        pg.evaluate("""d => { window.__val = []; window.addEventListener('message', e => {
                           if (e.data && e.data.type === 'streamlit:setComponentValue') window.__val.push(e.data.value); });
                         window.postMessage({type: 'streamlit:render', args: {datos: d}}, '*'); }""", d)
        pg.wait_for_timeout(400)
        assert "B1 con" in pg.inner_text("#estado")                       # B1 marcado en rojo por superposición
        # punto dentro de B1 que no tapa otro equipo (la marca roja sí lo cubre: antes se llevaba el clic y movía la vista)
        x, y = pg.evaluate("""() => { const r = document.querySelector('.eq[data-id="B1"] .toque').getBoundingClientRect();
            for (let fy = 0.5; fy > 0.05; fy -= 0.1) for (const fx of [0.5, 0.3, 0.7, 0.15, 0.85]) {
              const x = r.x + r.width * fx, y = r.y + r.height * fy, g = document.elementFromPoint(x, y).closest('.eq');
              if (!g || g.dataset.id === 'B1') return [x, y]; }
            return [r.x + r.width / 2, r.y + r.height / 2]; }""")
        assert pg.evaluate(f"document.elementFromPoint({x}, {y}).closest('#g-marcas')") is None
        antes = d["posiciones"]["B1"]
        pg.mouse.move(x, y); pg.mouse.down(); pg.mouse.move(x - 90, y + 70, steps=8); pg.mouse.up()
        pg.wait_for_timeout(150)
        val = pg.evaluate("window.__val")
        assert val, "el componente no devolvió posiciones al soltar"
        nuevo = val[-1]["posiciones"]["B1"]
        assert (nuevo[0], nuevo[1]) != (antes[0], antes[1])
        assert nuevo[0] * 2 == round(nuevo[0] * 2) and nuevo[1] * 2 == round(nuevo[1] * 2)   # ajuste a 0,5 m
        assert pg.inner_text("#estado")                                    # el aviso se recalcula al soltar
    finally:
        b.close(); p.stop()


# ------------------------------------------------------------------ 2) leyenda con color
def test_leyenda_del_plano_con_color_en_las_dos_vistas():
    t = HTML_PLANO.read_text(encoding="utf-8")
    assert "c = it.color || tinta" in t and '<tspan fill="${c}"' in t


# ------------------------------------------------------------------ 3), 6) y 7) textos de la pantalla
def test_etiqueta_corta_de_la_bandeja_y_textos_de_canerias_y_red():
    assert '"Altura bandeja eléctrica (m)"' in SRC and '"Altura de la bandeja eléctrica (m)"' not in SRC
    assert "st.caption(\"Diámetro: red hidráulica" not in SRC
    from ui import p_layout as PL
    assert PL.EXP_SUPUESTOS_ELEC.startswith("⚠ ")
    assert PL.texto_supuestos_red() == TEXTO_ELEC
    assert "with st.expander(EXP_SUPUESTOS_ELEC, expanded=False)" in SRC


# ------------------------------------------------------------------ 5) isométrica sincronizada
def test_sincronizar_rot_iso_en_los_dos_sentidos():
    from ui import p_layout as PL
    ss = {}
    assert PL.sincronizar_rot_iso(ss) == (0, "")
    ss["lay_iso"] = {"rot": 90, "marca": "a1"}                             # botón NE del dibujo
    assert PL.sincronizar_rot_iso(ss) == (90, "a1") and ss["lay_iso_rot"] == 90
    ss["lay_iso_rot"] = 180                                                # la lista cambia; el valor viejo del dibujo no la pisa
    assert PL.sincronizar_rot_iso(ss) == (180, "a1")
    ss["lay_iso"] = {"rot": 270, "marca": "b2"}
    assert PL.sincronizar_rot_iso(ss) == (270, "b2")
    ss["lay_iso"] = {"rot": 45, "marca": "c3"}                             # orientación inválida: se ignora
    assert PL.sincronizar_rot_iso(ss)[0] == 270


def test_componente_isometrico_devuelve_y_recibe_la_orientacion():
    vistas = {str(r): f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 60"><text x="5" y="30">vista {r}</text></svg>'
              for r in (0, 90, 180, 270)}
    datos = dict(vistas=vistas, info={}, rot=0, marca="", alto=300, firma="f")
    p, b = _navegador()
    try:
        pg = b.new_page()
        pg.goto(HTML_ISO.as_uri())
        enviar = "d => window.postMessage({type: 'streamlit:render', args: {datos: d}}, '*')"
        pg.evaluate("""() => { window.__val = []; window.addEventListener('message', e => {
                         if (e.data && e.data.type === 'streamlit:setComponentValue') window.__val.push(e.data.value); }); }""")
        pg.evaluate(enviar, datos); pg.wait_for_timeout(150)
        activo = "() => document.querySelector('button[data-rot].activo').dataset.rot"
        assert pg.evaluate(activo) == "0"
        pg.click("button[data-rot='90']"); pg.wait_for_timeout(100)        # arriba: NE
        val = pg.evaluate("window.__val")
        assert val and val[-1]["rot"] == 90 and val[-1]["marca"]
        marca = val[-1]["marca"]
        pg.evaluate(enviar, dict(datos, rot=0, marca="")); pg.wait_for_timeout(100)   # una recarga vieja no deshace el giro en viaje
        assert pg.evaluate(activo) == "90"
        pg.evaluate(enviar, dict(datos, rot=90, marca=marca)); pg.wait_for_timeout(100)   # Python confirmó
        assert pg.evaluate(activo) == "90" and len(pg.evaluate("window.__val")) == 1      # sin bucle: no vuelve a enviar
        pg.evaluate(enviar, dict(datos, rot=270, marca=marca)); pg.wait_for_timeout(100)  # la lista eligió suroeste
        assert pg.evaluate(activo) == "270" and "vista 270" in pg.inner_text("#vista")
        assert len(pg.evaluate("window.__val")) == 1
    finally:
        b.close(); p.stop()
