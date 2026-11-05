"""Pruebas de la vista isométrica del layout (PAT 135, T15): cámara y proyección, tonos, algoritmo del pintor, recorridos,
sólidos, gancho a las figuras de Anatomy del mantenedor, escena, SVG en las cuatro orientaciones y datos de interacción."""
import json, math, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import layout as LY, isometrico as ISO
from pat_sim.escenarios import agrozzi, pellet, chip, lena


@pytest.fixture(scope="module")
def lay():
    p = agrozzi.crear().resolver()
    return p, LY.estado_layout(p)


def test_camara_cuatro_orientaciones():
    assert ISO.camara(1, 0, 0) == (0, 1) and ISO.camara(0, 1, 0) == (-1, 0)      # desde el sureste: el este y el sur se acercan
    assert ISO.camara(1, 0, 90) == (1, 0) and ISO.camara(0, 1, 90) == (0, 1)     # desde el noreste: el este y el norte se acercan
    assert ISO.camara(1, 0, 180) == (0, -1) and ISO.camara(1, 0, 270) == (-1, 0)
    assert ISO.camara(3, 5, 360) == ISO.camara(3, 5, 0) and ISO.camara(12, 10, 0, 10, 10) == (0, 2)


def test_proyectar_a_mano():
    assert ISO.proyectar(0, 0, 0) == (0, 0)
    sx, sy = ISO.proyectar(1, 2, 3)
    assert sx == pytest.approx(math.cos(math.radians(30))) and sy == pytest.approx(1.5 - 3)


def test_caja_camara():
    c = ISO.caja_camara((0, 0, 4, 2), 0, 3, 0, 0, 0)          # a = −y, b = x
    assert c == (-2, 0, 0, 4, 0, 3)
    c2 = ISO.caja_camara((0, 0, 4, 2), 0, 3, 90, 0, 0)        # a = x, b = y
    assert c2 == (0, 4, 0, 2, 0, 3)


def test_mezcla_tonos_y_forma():
    assert ISO.mezcla("#000000", "#ffffff", 0.5) == "#808080" and ISO.mezcla("#123456", "#ffffff", 0) == "#123456"
    t = ISO.tonos("#808080")
    assert set(t) == {"superior", "izquierda", "derecha", "contorno"} and t["izquierda"] == "#808080"
    assert t["superior"] > t["izquierda"] > t["derecha"] > t["contorno"]         # de claro a oscuro
    assert ISO.forma("evaporador") == "cilindro_v" and ISO.forma("intercambiador") == "cilindro_h" and ISO.forma("tolva") == "prisma"


def test_orden_pintor_lejano_primero_y_abajo_primero():
    lejos = dict(id="l", caja=(0, 1, 0, 1, 0, 3)); cerca = dict(id="c", caja=(2, 3, 0, 1, 0, 3))   # cerca: mayor a
    assert [i["id"] for i in ISO.orden_pintor([cerca, lejos])] == ["l", "c"]
    bajo = dict(id="b", caja=(0, 4, 0, 4, 0, 2)); tubo = dict(id="t", caja=(1, 3, 2, 2, 5, 5))      # tubo sobre el equipo
    assert [i["id"] for i in ISO.orden_pintor([tubo, bajo])] == ["b", "t"]
    assert len(ISO.orden_pintor([dict(caja=(0, 1, 0, 1, 0, 1)) for _ in range(5)])) == 5


def test_ruta_tubo():
    r = ISO.ruta_tubo((0, 0, 1), (5, 3, 2), 6)
    assert r == [(0, 0, 1), (0, 0, 6), (5, 0, 6), (5, 3, 6), (5, 3, 2)]
    assert ISO.ruta_tubo((0, 0, 1), (5, 0, 1), 6, por_rack=False) == [(0, 0, 1), (5, 0, 1)]


def test_convexa_y_recorte():
    h = ISO._convexa([(0, 0), (2, 0), (2, 2), (0, 2), (1, 1)])
    assert sorted(h) == [(0, 0), (0, 2), (2, 0), (2, 2)]
    izq = ISO.recortar_x([(0, 0), (2, 0), (2, 2), (0, 2)], 1.0, True)
    assert max(p[0] for p in izq) == pytest.approx(1.0) and len(izq) == 4
    assert min(p[0] for p in ISO.recortar_x([(0, 0), (2, 0), (2, 2), (0, 2)], 1.0, False)) == pytest.approx(1.0)


def test_solidos_con_cuatro_tonos():
    P = lambda a, b, z: (10 * ISO.proyectar(a, b, z)[0] + 100, 10 * ISO.proyectar(a, b, z)[1] + 100)
    t = ISO.tonos("#9cc3cf")
    pr = ISO.prisma(P, (0, 2, 0, 3, 0, 1), t)
    assert pr.count("<polygon") == 3 and all(t[k] in pr for k in t)
    cv = ISO.cilindro_v(P, (0, 2, 0, 3, 0, 4), t)
    assert all(t[k] in cv for k in t) and cv.count("<polygon") == 4
    ch = ISO.cilindro_h(P, (0, 6, 0, 1.5, 0, 2.5), t)
    assert all(t[k] in ch for k in t) and ch.count("<polygon") >= 4 + 6    # manto, franja, tapa, contorno y dos silletas
    tb = ISO.tubo(P, [(0, 0, 5), (3, 0, 5)], "#c0392b", 4)
    assert tb.count("<polyline") == 3 and "#c0392b" in tb


def test_figura_incrustada_y_limpieza():
    f = ISO.figura_incrustada('<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" viewBox="0 0 20 10" '
                              'onload="x()"><script>alert(1)</script><rect width="20" height="10"/></svg>', 5, 6, 40, 30)
    assert 'viewBox="0 0 20 10"' in f and 'x="5.0"' in f and 'width="40.0"' in f and "<script" not in f and "onload" not in f
    assert '<?xml' not in f and 'width="200"' not in f
    g = ISO.figura_incrustada('<svg width="50" height="80"><circle r="3"/></svg>', 0, 0, 10, 10)
    assert 'viewBox="0 0 50 80"' in g
    assert ISO.figura_incrustada("no es svg", 0, 0, 1, 1) == ""


def test_figuras_isometricas_desde_el_mantenedor():
    class Mant:
        def listar_simbolos(self, norma):
            assert norma == "ISO-ISOMETRICO"
            return [dict(codigo="evaporador_mvr", svg="<svg><g id='anatomy'/></svg>"), dict(codigo="vacio", svg="")]
    class Falla:
        def listar_simbolos(self, norma):
            raise RuntimeError("sin base")
    assert ISO.figuras_isometricas(Mant()) == {"evaporador_mvr": "<svg><g id='anatomy'/></svg>"}
    assert ISO.figuras_isometricas(Falla()) == {} and ISO.figuras_isometricas(None) == {}


def test_escena_ordenada_y_con_todas_las_piezas(lay):
    p, L = lay
    e = ISO.escena(L["posiciones"], L["dims"], L["filas"], L["red"], 0, LY.H_RACK_M)
    clases = {i["clase"] for i in e["items"]}
    assert {"eq", "ccm", "co", "rack", "ba", "ca"} <= clases
    assert sum(1 for i in e["items"] if i["clase"] == "eq") == len(p.equipos) and e["titulo"] == "Vista desde el sureste"
    w2 = next(i for i in e["items"] if i.get("id") == "W2"); assert w2["forma"] == "cilindro_v"


def test_isometrico_svg_cuatro_orientaciones_y_cuatro_rubros():
    for m in (agrozzi, pellet, chip, lena):
        p = m.crear().resolver(); L = LY.estado_layout(p)
        v = ISO.vistas_isometricas(L["posiciones"], L["dims"], L["filas"], L["red"], h_rack=LY.H_RACK_M,
                                   nombres={k: x.nombre for k, x in p.equipos.items()})
        assert set(v) == {"0", "90", "180", "270"}
        for r, s in v.items():
            assert s.startswith("<svg") and f'data-rot="{r}"' in s and ISO.VISTAS[int(r)].lower() in s
            assert all(f'data-id="{k}"' in s for k in p.equipos) and 'data-id="CCM"' in s and "Rack de cañerías" in s
            assert 'class="it co"' in s and 'class="it ca"' in s and ">N</text>" in s
    assert "sin equipos" in ISO.isometrico_svg({}, {})


def test_colores_de_corriente_de_la_leyenda_de_diseno(lay):
    p, L = lay
    s = ISO.isometrico_svg(L["posiciones"], L["dims"], L["filas"], L["red"])
    from pat_sim.motor.corrientes import TIPOS
    assert TIPOS["producto"][1] in s and TIPOS["vapor"][1] in s and "Vapor de agua" in s


def test_gancho_figura_del_mantenedor_reemplaza_al_solido(lay):
    p, L = lay
    fig = {"evaporador_mvr": '<svg viewBox="0 0 10 10"><g id="figura_anatomy"/></svg>'}
    cod = {k: [x.simbolo, x.tipo, L["dims"][k]["familia"]] for k, x in p.equipos.items()}
    s = ISO.isometrico_svg(L["posiciones"], L["dims"], L["filas"], L["red"], codigos=cod, figuras=fig)
    assert s.count('id="figura_anatomy"') == 2                          # W2 y W3 son evaporador_mvr


def test_norte_en_pantalla():
    nx, ny = ISO._norte(0)
    assert nx > 0 and ny < 0                                            # desde el sureste el norte va arriba a la derecha
    nx2, ny2 = ISO._norte(180)
    assert nx2 < 0 and ny2 > 0


def test_datos_interaccion(lay):
    p, L = lay
    d = ISO.datos_interaccion(L["posiciones"], L["dims"], L["filas"], L["red"], {k: x.nombre for k, x in p.equipos.items()})
    json.dumps(d)
    assert d["equipos"]["W2"]["alimentador"] == "AL-W2" and d["equipos"]["W2"]["P_kW"] > 0 and d["equipos"]["B1"]["P_kW"] is None
    assert "CCM" in d["equipos"] and set(d["cables"]) == set(L["cables_m"]) and set(d["corrientes"]) == set(L["longitudes_m"])
    assert "6" in d["equipos"]["W2"]["conexiones"] or d["equipos"]["W2"]["conexiones"]
