"""PAT 141 (pedido de Jaime, 19-11-2026): lo que se mueve en la pestaña Plano de Layout cambia también Lámina, Elevaciones,
Isométrica, Cañerías y Red eléctrica, en el dibujo y en las longitudes de las corrientes. Se mueve un equipo con el mismo valor
que manda el plano del navegador (_aplicar_plano) y se compara cada vista antes y después. También revisa que las pestañas
se vean como botones grandes (CSS en ui/comun.py)."""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]


def _vistas(pl, lay):
    """Lo que dibuja o calcula cada pestaña de Layout, con las mismas funciones que usa ui/p_layout.py."""
    from pat_sim.motor import layout as LY, isometrico as ISO, lamina as LAM, plano_detalle as PD
    nombres = {k: e.nombre for k, e in pl.equipos.items()}
    red = lay["red"]
    modelo = PD.construir(lay, nombres, pl, proyecto=pl.nombre)
    lam = LAM.generar_lamina(lay, nombres, list(LAM.FORMATOS)[0], None, proyecto=pl.nombre, plano=modelo)
    y = float(lay["posiciones"]["W2"][1])
    return dict(
        plano=PD.a_svg(modelo, "plano", {c for g in PD.GRUPOS.values() for c in g}),
        lamina=LAM.a_svg(lam),
        elev_frontal=LY.elevacion_svg(lay["posiciones"], lay["dims"], "frontal", lay["h_rack"], red),
        elev_lateral=LY.elevacion_svg(lay["posiciones"], lay["dims"], "lateral", lay["h_rack"], red),
        corte=LY.corte_svg(lay["posiciones"], lay["dims"], y, lay["h_rack"]),
        isometrica=ISO.vistas_isometricas(lay["posiciones"], lay["dims"], lay["filas"], red, h_rack=lay["h_rack"], nombres=nombres),
        canerias={f["id"]: round(f["total"], 3) for f in lay["filas"]},
        flujo_distancia=round(lay["costo"], 3),
        red_electrica={c["id"]: round(c["total"], 3) for c in red["cables"]},
    )


def test_mover_un_equipo_en_plano_cambia_todas_las_pestanas():
    from pat_sim.escenarios import agrozzi
    from pat_sim.motor import layout as LY
    from ui import p_layout as PL
    pl = agrozzi.crear().resolver()
    lay = LY.estado_layout(pl)
    lay.update(version=1, seq=0, pasillo=LY.PASILLO_M, h_rack=LY.H_RACK_M, accesorios=LY.ACCESORIOS, overrides={})
    lay.update(LY.estado_layout(pl, lay))
    antes = _vistas(pl, lay)
    x, y, r = lay["posiciones"]["W2"]
    # el mismo valor que devuelve el plano del navegador al soltar W2 doce metros más allá
    assert PL._aplicar_plano(lay, dict(version=1, seq=1, posiciones={"W2": [x + 12.0, y + 6.0, r]}))
    lay.update(LY.estado_layout(pl, lay, lay.get("overrides"), lay["pasillo"], lay["h_rack"], lay["accesorios"]))
    despues = _vistas(pl, lay)
    iguales = [k for k in antes if antes[k] == despues[k]]
    assert not iguales, f"Estas pestañas no cambiaron al mover W2 en Plano: {iguales}"


def test_pestanas_con_aspecto_de_boton():
    css = (RAIZ / "ui" / "comun.py").read_text(encoding="utf-8")
    assert '[data-testid="stTab"]{padding:9px 20px' in css
    assert '[data-testid="stTab"][aria-selected="true"]{background:#0d3b2e' in css
    assert '[data-testid="stTab"] .react-aria-SelectionIndicator{display:none}' in css


def test_layout_dice_que_las_vistas_estan_enlazadas():
    src = (RAIZ / "ui" / "p_layout.py").read_text(encoding="utf-8")
    assert "Las seis pestañas usan la misma disposición" in src
