"""Pruebas de la lámina de ingeniería del layout (PAT 136, T19): formato ISO 5457, cajetín ISO 7200, escala ISO 5455, SVG, PDF y DXF."""
import os, sys, tempfile
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import layout as LY, lamina as LAM
from pat_sim.escenarios import agrozzi, pellet, chip, lena

try:
    import ezdxf
except ImportError:
    ezdxf = None


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


@pytest.fixture(scope="module")
def lay(pl):
    return LY.estado_layout(pl)


def _nombres(p):
    return {k: e.nombre for k, e in p.equipos.items()}


def test_cajetin_trae_todos_los_campos():
    c = LAM.cajetin()
    for k in LAM.CAMPOS_CAJETIN:
        assert c.get(k), k
    # PAT 140: el autor no es un nombre fijo; sin nombre en Desafío queda «(nombre del estudiante)»
    assert c["autor"] == "(nombre del estudiante)" and c["revisor"] == "Docente del curso"
    assert LAM.cajetin(autor="  Ana   Pérez ")["autor"] == "Ana Pérez"
    assert c["institucion"] == "Universidad de Talca" and c["unidad"] == "m"


def test_cajetin_ancho_180_y_textos_en_la_lamina(pl, lay):
    m = LAM.generar_lamina(lay, _nombres(pl), "A3", fecha="13-11-2026", autor="Ana Pérez")
    textos = " ".join(p["s"] for p in m["prims"] if p["k"] == "text")
    assert "Jaime" not in textos
    for v in ("Ana Pérez", "Docente del curso", "Universidad de Talca", "13-11-2026", "PAT136-LAY-001"):
        assert v in textos
    assert LAM.ANCHO_CAJETIN == 180.0 and sum(w for _, _, w in LAM._FILAS_CAJETIN[0][1]) == 180.0


@pytest.mark.parametrize("fmt,dim", [("A3", (420, 297)), ("A1", (841, 594))])
def test_formato_iso5457_marco_y_margenes(pl, lay, fmt, dim):
    m = LAM.generar_lamina(lay, _nombres(pl), fmt)
    assert (m["ancho_mm"], m["alto_mm"]) == dim
    assert m["marco"] == (20.0, 10.0, dim[0] - 10.0, dim[1] - 10.0)
    marcos = [p for p in m["prims"] if p["capa"] == "MARCO" and p["k"] == "poly" and p["tl"] == "marco"]
    assert len(marcos) >= 6        # marco, cajetín y cuatro marcas de centrado


@pytest.mark.parametrize("fmt,n", [("A3", (8, 6)), ("A1", (16, 12))])
def test_zonas_de_referencia(pl, lay, fmt, n):
    m = LAM.generar_lamina(lay, _nombres(pl), fmt)
    nums = [p["s"] for p in m["prims"] if p["capa"] == "MARCO" and p["k"] == "text" and p["s"].isdigit() and p["y"] > m["alto_mm"] - 10]
    letras = [p["s"] for p in m["prims"] if p["capa"] == "MARCO" and p["k"] == "text" and p["s"].isalpha() and len(p["s"]) == 1 and p["x"] < 20 and p["s"] != fmt]
    assert len(nums) == n[0] and len(letras) == n[1]
    assert "I" not in letras and "O" not in letras


@pytest.mark.parametrize("fmt", ["A3", "A1"])
def test_escala_elegida_hace_caber_la_planta(pl, lay, fmt):
    m = LAM.generar_lamina(lay, _nombres(pl), fmt)
    assert m["escala"] in LAM.ESCALAS and m["cabe"]
    assert LAM.fuera_del_marco(m) == []
    # una escala menor (de la serie) con la que no cabría no fue la elegida: es la mayor escala que cabe
    g = LAM._geom_hoja(fmt); ext = LAM._extension(lay)
    menores = [e for e in LAM.ESCALAS if e < m["escala"]]
    assert all(not LAM._caja_grilla(ext, e, g)["cabe"] for e in menores)


def test_escala_a1_es_mayor_o_igual_que_a3(lay):
    e3, _ = LAM.escala_automatica(lay, "A3"); e1, _ = LAM.escala_automatica(lay, "A1")
    assert e1 <= e3


def test_escala_pedida_y_escala_invalida(pl, lay):
    m = LAM.generar_lamina(lay, _nombres(pl), "A1", "1:200")
    assert m["escala"] == 200 and m["cajetin"]["escala"] == "1:200"
    m2 = LAM.generar_lamina(lay, _nombres(pl), "A3", 77)
    assert m2["escala"] in LAM.ESCALAS and any("serie" in a for a in m2["avisos"])
    m3 = LAM.generar_lamina(lay, _nombres(pl), "A3", "1:50")          # no cabe en A3: aviso y automática
    assert m3["escala"] != 50 and any("no cabe" in a for a in m3["avisos"])


def test_cotas_ejes_y_tipos_de_linea(pl, lay):
    m = LAM.generar_lamina(lay, _nombres(pl), "A1")
    capas = {p["capa"] for p in m["prims"]}
    assert capas == set(LAM.CAPAS)
    tipos = {p["tl"] for p in m["prims"] if p["k"] in ("poly", "circle")}
    assert {"gruesa", "fina", "trazos", "puntoraya", "bandeja", "marco"} <= tipos
    burbujas = [p for p in m["prims"] if p["k"] == "circle" and p["capa"] == "EJES"]
    assert len(burbujas) == len(m["grilla"]["xs"]) + len(m["grilla"]["ys"])
    cotas = [p["s"] for p in m["prims"] if p["capa"] == "COTAS" and p["k"] == "text"]
    ext = LAM._extension(lay)
    assert LAM._txt(ext["x1"] - ext["x0"], 1) in cotas          # cota general en x


def test_lista_de_equipos_en_la_lamina(pl, lay):
    m = LAM.generar_lamina(lay, _nombres(pl), "A3")
    tags = {e["tag"] for e in m["equipos"]}
    assert set(lay["posiciones"]) <= tags and "CCM" in tags
    textos = {p["s"] for p in m["prims"] if p["k"] == "text"}
    assert "W2" in textos and "Apollo 40 (MVR)" in textos


def test_sin_textos_superpuestos_ni_fuera_del_marco(pl, lay):
    for fmt in ("A3", "A1"):
        m = LAM.generar_lamina(lay, _nombres(pl), fmt)
        assert LAM.textos_superpuestos(m) == [] and LAM.fuera_del_marco(m) == []


def test_svg_valido(pl, lay):
    import xml.dom.minidom as md
    s = LAM.a_svg(LAM.generar_lamina(lay, _nombres(pl), "A3"))
    md.parseString(s)
    assert "viewBox=\"0 0 420 297\"" in s and "Universidad de Talca" in s


def test_pdf_existe_y_no_esta_vacio(pl, lay, tmp_path):
    b = LAM.a_pdf(LAM.generar_lamina(lay, _nombres(pl), "A3"))
    p = tmp_path / "l.pdf"; p.write_bytes(b)
    assert p.stat().st_size > 3000 and b[:5] == b"%PDF-"


@pytest.mark.skipif(ezdxf is None, reason="ezdxf no está instalado en este entorno (pip install ezdxf)")
def test_dxf_se_abre_y_tiene_las_capas(pl, lay, tmp_path):
    if ezdxf is None:   # PAT 136: el banco no respeta skipif; sin ezdxf la prueba se salta
        return
    b, aviso = LAM.a_dxf(LAM.generar_lamina(lay, _nombres(pl), "A3"))
    assert b and aviso == ""
    p = tmp_path / "l.dxf"; p.write_bytes(b)
    doc = ezdxf.readfile(str(p))
    nombres = {l.dxf.name for l in doc.layers}
    assert {"EQUIPOS", "CANERIAS", "ELECTRICO", "COTAS", "TEXTOS", "MARCO", "EJES"} <= nombres
    usadas = {e.dxf.layer for e in doc.modelspace()}
    assert {"EQUIPOS", "CANERIAS", "ELECTRICO", "COTAS", "TEXTOS", "MARCO", "EJES"} <= usadas
    assert doc.units == 6                                        # metros


@pytest.mark.skipif(ezdxf is None, reason="ezdxf no está instalado en este entorno (pip install ezdxf)")
def test_dxf_en_metros_de_modelo(pl, lay, tmp_path):
    if ezdxf is None:   # PAT 136: el banco no respeta skipif; sin ezdxf la prueba se salta
        return
    m = LAM.generar_lamina(lay, _nombres(pl), "A3")
    b, _ = LAM.a_dxf(m)
    p = tmp_path / "l.dxf"; p.write_bytes(b)
    msp = ezdxf.readfile(str(p)).modelspace()
    xs = [v[0] for e in msp if e.dxftype() == "LWPOLYLINE" for v in e.get_points()]
    assert max(xs) == pytest.approx(420 * m["escala"] / 1000, rel=1e-6)


def test_dxf_sin_ezdxf_avisa_sin_romper(pl, lay):
    m = LAM.generar_lamina(lay, _nombres(pl), "A3")
    previos = {k: v for k, v in sys.modules.items() if k == "ezdxf" or k.startswith("ezdxf.")}
    for k in previos:
        del sys.modules[k]
    sys.modules["ezdxf"] = None                       # import ezdxf lanza ImportError
    try:
        b, aviso = LAM.a_dxf(m)
    finally:
        del sys.modules["ezdxf"]
        sys.modules.update(previos)
    assert b is None and "ezdxf" in aviso


@pytest.mark.parametrize("modulo", [agrozzi, pellet, chip, lena])
@pytest.mark.parametrize("fmt", ["A3", "A1"])
def test_los_cuatro_rubros(modulo, fmt):
    p = modulo.crear().resolver(); ly = LY.estado_layout(p)
    m = LAM.generar_lamina(ly, _nombres(p), fmt, proyecto=p.nombre)
    assert m["escala"] in LAM.ESCALAS + (LAM.ESCALA_RESPALDO,) and len(m["equipos"]) >= len(ly["posiciones"])
    assert LAM.fuera_del_marco(m) == [] and LAM.textos_superpuestos(m) == []
    assert len(LAM.a_pdf(m)) > 3000 and "<svg" in LAM.a_svg(m)


@pytest.mark.parametrize("vacio", [None, {}, {"posiciones": {}, "dims": {}}])
def test_planta_vacia_avisa_sin_fallar(vacio):
    m = LAM.generar_lamina(vacio, {}, "A3")
    assert m["vacia"] and any("vacía" in a for a in m["avisos"])
    assert len(LAM.a_pdf(m)) > 1000 and "<svg" in LAM.a_svg(m)
    assert m["cajetin"]["escala"] == "Sin escala"
