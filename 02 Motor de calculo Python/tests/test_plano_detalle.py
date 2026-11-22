"""Pruebas del plano de disposición detallado (PAT 140): símbolos a escala, nave derivada de los equipos, cañerías ortogonales que no
atraviesan equipos, DN, bandeja eléctrica, vistas de plano y a color, capas del DXF y planta vacía."""
import copy, math, os, re, sys
import xml.dom.minidom as md
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import layout as LY, plano_detalle as PD, lamina as LAM
from pat_sim.escenarios import agrozzi, pellet, chip, lena

try:
    import ezdxf
except ImportError:
    ezdxf = None

FORMAS = ["tolva", "estanque", "banda", "transportador", "refinadora", "ciclon", "molienda", "sierra", "intercambiador",
          "intercambiador_placas", "evaporador", "evaporador_mvr", "caldera", "hogar", "secador_rotatorio", "secador_banda",
          "secador_camara", "llenadora", "acopio", "pelletizadora", "enfriador", "bomba", "valvula", "maquina_rotativa", "columna", "general"]


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


@pytest.fixture(scope="module")
def lay(pl):
    return LY.estado_layout(pl)


@pytest.fixture(scope="module")
def mod(pl, lay):
    return PD.construir(lay, {k: e.nombre for k, e in pl.equipos.items()}, pl, proyecto=pl.nombre, autor="Ana Pérez")


def _caja(prims):
    xs, ys = [], []
    for q in prims:
        if "pts" in q:
            xs += [p[0] for p in q["pts"]]; ys += [p[1] for p in q["pts"]]
        if "c" in q:
            xs += [q["c"][0] - q["r"], q["c"][0] + q["r"]]; ys += [q["c"][1] - q["r"], q["c"][1] + q["r"]]
    return min(xs), min(ys), max(xs), max(ys)


@pytest.mark.parametrize("forma", FORMAS)
def test_simbolo_dentro_de_su_huella(forma):
    for L, W in ((8.0, 3.0), (3.0, 3.0), (1.2, 0.5), (30.0, 5.0)):
        x0, y0, x1, y1 = _caja(PD.simbolo(forma, L, W, 3))
        assert x0 >= -L / 2 - 1e-6 and x1 <= L / 2 + 1e-6 and y0 >= -W / 2 - 1e-6 and y1 <= W / 2 + 1e-6, (forma, L, W)


def test_forma_y_efectos_de_los_equipos(pl, lay):
    d = lay["dims"]
    assert d["W4"]["forma"] == "evaporador" and d["W4"]["efectos"] == 3
    assert d["W2"]["forma"] == "evaporador_mvr" and d["W2"]["efectos"] == 1
    assert d["F2"]["forma"] == "refinadora" and d["F1"]["forma"] == "banda" and d["B1"]["forma"] == "tolva"
    assert d["W1"]["forma"] == "intercambiador" and d["D1"]["forma"] == "caldera" and d["A1"]["forma"] == "llenadora"
    assert d["B2"]["forma"] == "estanque" and d["Z1"]["forma"] == "molienda"
    assert LY.estado_layout(chip.crear().resolver())["dims"]["A1"]["forma"] == "acopio"
    # el evaporador de tres efectos dibuja tres cuerpos (y tres separadores) más el condensador
    cuerpos = [q for q in PD.simbolo("evaporador", 10, 6, 3) if q["k"] == "circ" and q["e"] == "gruesa"]
    assert len(cuerpos) == 3


def test_zona_de_mantencion_e_intercambiador():
    z = PD.zona_mantencion("general", 4, 2, 0.75)
    assert _caja(z) == pytest.approx((-2.75, -1.75, 2.75, 1.75))
    zi = PD.zona_mantencion("intercambiador", 6, 1.5, 0.75)
    assert len(zi) == 2 and _caja(zi)[0] == pytest.approx(-3 - 0.75 - 0.84 * 6)      # retiro del haz por el cabezal


def test_nave_envuelve_equipos_y_ejes_cada_6_m(mod, lay):
    nv = mod["nave"]
    for k, h in ((e["id"], e["huella"]) for e in mod["equipos"]):
        assert nv[0] < h[0] and nv[1] < h[1] and h[2] < nv[2] and h[3] < nv[3], k
    dif = [b - a for a, b in zip(mod["ejes_x"], mod["ejes_x"][1:])]
    assert all(v == pytest.approx(PD.VANO_M) for v in dif)
    assert mod["ejes_y"][-1] - mod["ejes_y"][0] <= PD.LUZ_MAX_M + 1e-9
    # pasillo de grúa horquilla y peatonal al sur: la nave deja al menos 3,5 + 1,5 m bajo la zona de equipos
    ymin = min(e["huella"][1] for e in mod["equipos"]) - mod["mant"]
    assert ymin - (nv[1] + PD.MURO_M) >= PD.PASILLO_GRUA_M + LY.PASILLO_M - 1e-6


def test_salas_y_sitio(mod):
    textos = {q["s"] for q in mod["mundo"] if q["k"] == "text"}
    for t in ("Oficinas", "Baños y vestidores", "Bodega de producto terminado", "Sala de calderas", "Patio de camiones", "Acceso",
              "Portón de recepción"):
        assert t in textos, t
    assert any(t.startswith("Estacionamientos (") for t in textos)
    est = [q for q in mod["mundo"] if q.get("f") == "estac"]
    assert est and all(_caja([q])[2] - _caja([q])[0] == pytest.approx(PD.ESTAC_A) for q in est)
    s = mod["sitio"]; n = mod["nave"]
    assert s[0] < n[0] and s[1] < n[1] and n[2] < s[2] and n[3] < s[3]


def _cruza_segmento(a, b, h, tol=0.05):
    x0, x1 = sorted((a[0], b[0])); y0, y1 = sorted((a[1], b[1]))
    return x0 < h[2] - tol and h[0] + tol < x1 + 1e-9 and y0 < h[3] - tol and h[1] + tol < y1 + 1e-9 if (x1 > x0 or y1 > y0) else False


@pytest.mark.parametrize("modulo", [agrozzi, pellet, chip, lena])
def test_canerias_ortogonales_sin_atravesar_equipos(modulo):
    p = modulo.crear().resolver(); ly = LY.estado_layout(p)
    m = PD.construir(ly, {k: e.nombre for k, e in p.equipos.items()}, p)
    assert len(m["lineas"]) == len(ly["filas"])
    hs = {e["id"]: e["huella"] for e in m["equipos"]}
    for li in m["lineas"]:
        for a, b in zip(li["pts"], li["pts"][1:]):
            assert abs(a[0] - b[0]) < 1e-6 or abs(a[1] - b[1]) < 1e-6, li["id"]          # solo tramos ortogonales
            for k, h in hs.items():
                if k not in (li["origen"], li["destino"]):
                    assert not _cruza_segmento(a, b, h), (li["id"], k)


def test_dn_y_codigo_de_linea(mod, lay):
    from pat_sim.motor.costeo import diametro_nominal
    por_id = {f["id"]: f for f in lay["filas"]}
    for li in mod["lineas"]:
        f = por_id[li["id"]]
        if f.get("D_mm"):
            assert li["dn"] == diametro_nominal(f["D_mm"]) and li["codigo"] == f"{li['id']}-DN{li['dn']}-PR"
    v1 = next(li for li in mod["lineas"] if li["id"] == "V1")
    m = por_id["V1"]["peso"] * 1000 / 3600
    D = math.sqrt(4 * m / (PD.RHO_VAPOR * PD.V_VAPOR * math.pi)) * 1000
    assert v1["srv"] == "vapor" and v1["dn"] == diametro_nominal(D) and v1["codigo"].endswith("-VA")
    assert PD.ancho_linea(dict(medio="cañería", tipo="producto"), 300) == pytest.approx(0.33)
    assert PD.ancho_linea(dict(medio="transportador"), None) == 0.8


def test_bombas_de_linea_y_bandeja(mod, pl):
    ids = {b["id"] for b in mod["bombas"]}
    assert ids and all(i.startswith("P-1") for i in ids)
    bandeja = [q for q in mod["mundo"] if q["capa"] == "ELECTRICO" and q.get("e") == "bandeja"]
    assert bandeja
    assert any(it["srv"] == "electricidad" and it["presente"] for it in mod["leyenda"])
    assert [it["srv"] for it in mod["leyenda"]] == ["producto", "agua", "vapor", "condensado", "aire", "electricidad"]


def test_no_cambia_el_layout_ni_las_cifras(pl):
    ly = LY.estado_layout(pl); antes = copy.deepcopy({k: ly[k] for k in ("posiciones", "longitudes_m", "cables_m", "costo")})
    PD._CACHE.clear(); PD.construir(ly, {}, pl)
    assert {k: ly[k] for k in antes} == antes


@pytest.mark.parametrize("modo", ["plano", "color"])
def test_svg_de_descarga(mod, modo):
    s = PD.a_svg(mod, modo, y_corte=10.0)
    md.parseString(s)
    assert "Ana Pérez" in s and "Plano de disposición en planta" in s and "Jaime" not in s
    assert "Producto (PR)" in s and "Electricidad (bandeja) (EL)" in s
    css = PD.css(modo)
    assert (".tubo.s-vapor{stroke:#c0392b}" in css) == (modo == "color")   # el trazo del vapor va en rojo solo en la vista a color
    # PAT 140 i: el código de línea y la muestra de la leyenda van con el color del servicio en las dos vistas
    assert ".t.k-CANERIAS.s-vapor{fill:#c0392b}" in css and ".t.k-CANERIAS.s-producto{fill:#1b7a5a}" in css
    assert 'stroke="#1b7a5a" stroke-width="4"' in s and 'stroke="#c9a10a" stroke-width="4"' in s


def test_codigos_de_linea_con_su_servicio(mod):
    """PAT 140 i: cada código de línea lleva su servicio (clase s-<servicio>) para pintarse con el color de la leyenda."""
    cod = [q for q in mod["mundo"] if q["k"] == "text" and q["capa"] == "CANERIAS" and q.get("srv")]
    assert cod and all(q["srv"] in PD.SERVICIOS for q in cod)
    assert all(q["s"].endswith(PD.SERVICIOS[q["srv"]][2]) or q["s"].endswith(("CT", "DU")) for q in cod)
    svg = PD.fragmentos(mod)["capas"]["CANERIAS"]
    assert re.search(r'class="t k-CANERIAS s-(producto|agua|vapor|condensado|aire)"', svg)


def test_capas_apagadas_no_salen(mod):
    solo = PD.primitivas_mundo(mod, {"EQUIPOS"})
    assert solo and {q["capa"] for q in solo} == {"EQUIPOS"}
    assert 'class="tubo' not in PD.a_svg(mod, "plano", {"EQUIPOS", "EDIFICIO"})


def test_fragmentos_para_el_componente(mod):
    f = PD.fragmentos(mod)
    assert set(f["capas"]) == set(PD.CAPAS)
    assert {s["id"] for s in f["simbolos"]} == {e["id"] for e in mod["equipos"]} | {"CCM"}
    for s in f["simbolos"]:
        md.parseString(f'<svg xmlns="http://www.w3.org/2000/svg">{s["svg"]}{s["mant"]}</svg>')
        assert s["etiqueta"]["s"].startswith(s["id"])
    assert f["ext_nave"][0] >= f["ext"][0] - 1e-9


@pytest.mark.parametrize("vacio", [None, {}, {"posiciones": {}, "dims": {}}])
def test_planta_vacia(vacio):
    m = PD.construir(vacio)
    assert m["vacio"] and m["avisos"] and PD.primitivas_mundo(m) == []
    assert "vacía" in PD.a_svg(m) and PD.fragmentos(m)["simbolos"] == []


def test_lamina_con_plano_detallado_y_capas(pl, lay, mod):
    m = LAM.generar_lamina(lay, {k: e.nombre for k, e in pl.equipos.items()}, "A1", plano=mod, modo="color", autor="Ana Pérez")
    capas = {p["capa"] for p in m["prims"]}
    assert {"EDIFICIO", "SITIO", "PASILLOS", "MANTENCION"} <= capas
    assert any(p.get("col") == PD.SERVICIOS["vapor"][1] for p in m["prims"])
    assert LAM.textos_superpuestos(m) == [] and LAM.fuera_del_marco(m) == []
    assert m["cajetin"]["autor"] == "Ana Pérez"
    sin = LAM.generar_lamina(lay, {}, "A3", plano=mod, capas={"EQUIPOS", "MARCO"})
    assert not any(p["capa"] in ("EDIFICIO", "SITIO", "PASILLOS") for p in sin["prims"])
    for c in ("CANERIAS", "MANTENCION"):
        assert sum(p["capa"] == c for p in sin["prims"]) == 1                 # solo la muestra de la leyenda


@pytest.mark.skipif(ezdxf is None, reason="ezdxf no está instalado en este entorno (pip install ezdxf)")
def test_dxf_con_capas_del_edificio(pl, lay, mod, tmp_path):
    if ezdxf is None:   # el banco no respeta skipif
        return
    b, _ = LAM.a_dxf(LAM.generar_lamina(lay, {}, "A3", plano=mod))
    p = tmp_path / "p.dxf"; p.write_bytes(b)
    usadas = {e.dxf.layer for e in ezdxf.readfile(str(p)).modelspace()}
    assert {"EDIFICIO", "SITIO", "MANTENCION", "CANERIAS", "ELECTRICO", "EQUIPOS"} <= usadas
