"""Pruebas del costeo de la planta (PAT 135, tarea T7.1): Williams, CEPCI, lista de equipos en los cuatro rubros, precios de
internet con respuestas simuladas de Tavily (sin red), caché SQLite y modo sin clave. Valores recalculados a mano."""
import io, json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import costeo as CT, costos, hidraulica as HID
from pat_sim.datos import precios_web as PW
from pat_sim.datos.bd import BaseDatos
from pat_sim.escenarios import agrozzi, pellet, chip, lena


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


class _Resp(io.BytesIO):
    def __enter__(self): return self
    def __exit__(self, *a): self.close(); return False


def _abridor(respuesta, registro=None):
    """Sustituto de urllib.request.urlopen: guarda la petición y devuelve la respuesta simulada."""
    def abrir(req, timeout=None):
        if registro is not None:
            registro.append(dict(url=req.full_url, metodo=req.get_method(), cuerpo=json.loads(req.data.decode()), timeout=timeout))
        if isinstance(respuesta, Exception):
            raise respuesta
        return _Resp(json.dumps(respuesta).encode())
    return abrir


RESP_BOMBA = {"answer": "A 10 HP stainless centrifugal pump costs about US$ 9,500.",
              "results": [{"title": "Pump 5 HP", "url": "https://ejemplo.cl/bomba5", "content": "Sanitary pump 5 HP price $4,200.00"},
                          {"title": "Bomba 7,5 kW", "url": "https://ejemplo.cl/bomba75", "content": "Bomba sanitaria 7,5 kW CLP $ 7.500.000"}]}


# ---------------------------------------------------------------- Williams y CEPCI
def test_williams_a_mano():
    assert CT.williams(10000, 6, 7, 0.6) == pytest.approx(10000 * (7 / 6) ** 0.6)      # bomba de 6 HP → 7 HP (ejemplo del profesor)
    assert CT.williams(10000, 6, 6, 0.6) == pytest.approx(10000)
    with pytest.raises(ValueError):
        CT.williams(10000, 0, 7, 0.6)


def test_exponente_tabla_y_seis_decimos():
    assert CT.exponente("bomba_centrifuga")[0] == pytest.approx(0.67)
    assert CT.exponente("intercambiador")[0] == pytest.approx(0.60)
    n, fuente, cat = CT.exponente("pelletizadora")
    assert n == pytest.approx(0.6) and cat == "Supuesto"
    assert CT.exponente("pelletizadora", {"pelletizadora": 0.8})[0] == pytest.approx(0.8)          # editable


def test_exponentes_profesor_sin_pdf():
    import tempfile
    d = tempfile.mkdtemp()
    assert CT.exponentes_profesor(d) == {}
    open(os.path.join(d, "Estimacion de costo de planta.pdf"), "wb").close()
    assert CT.exponentes_profesor(d) == {"_pdf_encontrado": True}


def test_cepci_y_actualizacion():
    assert CT.cepci_de(2020) == pytest.approx(596.2) and CT.cepci_de(2023) == pytest.approx(797.9) and CT.cepci_de(2026) is None
    c, f = CT.actualizar(1000, 596.2, 797.9)
    assert c == pytest.approx(1000 * 797.9 / 596.2) and f == pytest.approx(797.9 / 596.2)
    assert CT.actualizar(1000, None, 797.9) == (1000, 1.0)


def test_diametro_nominal_y_pulgadas():
    assert CT.diametro_nominal(48.0) == 50 and CT.diametro_nominal(50.0) == 50 and CT.diametro_nominal(51.0) == 65
    assert CT.diametro_nominal(293.4) == 300 and CT.diametro_nominal(700) == 700
    assert CT.pulgadas(50) == "2" and CT.pulgadas(300) == "12"


def test_precio_bibliografia():
    p = CT.precio_bibliografia("intercambiador", 296.12)
    assert p["precio_usd"] == pytest.approx(costos.costo_equipo_partido_usd2020(296.12)) and p["cepci_ref"] == pytest.approx(596.2)
    assert p["exacto"]
    q = CT.precio_bibliografia("caldera_gas", 22280.0)               # 124.000 + 10·(22.280·3.600/2.360)
    assert q["precio_usd"] == pytest.approx(124000 + 10 * 22280 * 3600 / 2360) and q["cepci_ref"] == pytest.approx(532.9)
    r = CT.precio_bibliografia("bomba_centrifuga", 5.0)
    assert r["precio_usd"] == pytest.approx(8000) and r["tamano"] == pytest.approx(7.5) and not r["exacto"]


# ---------------------------------------------------------------- lista de equipos
@pytest.mark.parametrize("modulo", [agrozzi, pellet, chip, lena])
def test_lista_equipos_cuatro_rubros(modulo):
    p = modulo.crear().resolver()
    items = CT.lista_equipos(p)
    claves = {i["clave"] for i in items}
    assert all(k in [i["equipo"] for i in items] for k in p.equipos)                 # cada equipo de la línea
    assert claves & {"caldera_gas", "generador_biomasa"}                              # caldera o generador
    assert claves & {"intercambiador", "bomba_calor"}                                 # recuperación de calor
    assert any(i["clave"] == "valvula_control" for i in items)


def test_lista_agrozzi_bombas_canerias_y_valvulas(pl):
    items = CT.lista_equipos(pl)
    red = HID.red_hidraulica(pl)["lineas"]
    bombas = [i for i in items if i["clave"] == "bomba_centrifuga"]
    assert len(bombas) == len(red) and bombas[0]["tamano"] == pytest.approx(red[0]["potencia_kW"])
    can = [i for i in items if i["clave"] == "caneria"]
    assert sum(i["cantidad"] for i in can) == pytest.approx(HID.L_LINEA * len(red))     # sin layout: 30 m por línea
    assert all("sin layout" in i["nota"] for i in can)
    assert len([i for i in items if i["clave"] == "valvula_control"]) == 6             # TV-101 … PV-501
    assert len([i for i in items if i["clave"] == "intercambiador"]) == 3              # A3 con U medio


def test_lista_con_longitudes_del_layout(pl):
    items = CT.lista_equipos(pl, longitudes={"1": 12.0, "2": 8.0})
    red = HID.red_hidraulica(pl)["lineas"]
    total = sum(i["cantidad"] for i in items if i["clave"] == "caneria")
    assert total == pytest.approx(12 + 8 + HID.L_LINEA * (len(red) - 2))


# ---------------------------------------------------------------- costeo
def test_costear_totales_y_filas(pl):
    res = CT.costear(pl)
    t = res["totales"]
    assert t["equipos_usd"] == pytest.approx(sum(f["costo_usd"] for f in res["filas"]))
    assert t["total_usd"] == pytest.approx(t["equipos_usd"] * costos.F_INSTALACION)
    assert t["instalacion_usd"] == pytest.approx(t["equipos_usd"] * (costos.F_INSTALACION - 1))
    assert t["total_clp"] == pytest.approx(t["total_usd"] * costos.DOLAR)
    f = next(x for x in res["filas"] if x["equipo"] == "E-101")
    assert f["costo_usd"] == pytest.approx(costos.costo_equipo_partido_usd2020(f["tamano"]) * 797.9 / 596.2)
    assert all(x["origen"] == "bibliografía" for x in res["filas"])
    b = next(x for x in res["filas"] if x["equipo"] == "P-101")
    assert b["n"] == pytest.approx(0.67) and b["costo_usd"] == pytest.approx(8000 * (b["tamano"] / 7.5) ** 0.67)
    c = next(x for x in res["filas"] if x["equipo"] == "DN 300")
    assert c["costo_usd"] == pytest.approx(60 * (300 / 50) ** 0.6 * c["cantidad"])
    assert CT.costear(pl, cepci_hoy=2 * 797.9)["totales"]["equipos_usd"] == pytest.approx(2 * t["equipos_usd"])


def test_costear_con_internet_simulado_y_cache(pl):
    bd = BaseDatos(":memory:"); reg = []
    items = [i for i in CT.lista_equipos(pl) if i["equipo"] == "P-101"]
    res = CT.costear(pl, bd=bd, buscar=True, clave="tvly-prueba", items=items, _abrir=_abridor(RESP_BOMBA, reg))
    f = res["filas"][0]
    assert f["origen"] == "internet" and f["url"] == "https://ejemplo.cl/bomba75"           # 7,5 kW: más cercano a 5,4 kW que 5 HP (3,7 kW)
    usd = 7500000 / costos.DOLAR
    assert f["tamano_ref"] == pytest.approx(7.5) and f["precio_ref_usd"] == pytest.approx(usd)
    assert f["costo_usd"] == pytest.approx(usd * (f["tamano"] / 7.5) ** 0.67) and f["factor_cepci"] == pytest.approx(1.0)
    assert reg and reg[0]["cuerpo"]["search_depth"] == "basic" and reg[0]["cuerpo"]["max_results"] == 5 and reg[0]["timeout"] == 15
    # sin clave: usa el último precio guardado y lo marca
    g = CT.costear(pl, bd=bd, buscar=True, clave=None, items=items)["filas"][0]
    assert g["origen"] == "internet (guardado)" and g["precio_ref_usd"] == pytest.approx(usd) and "Sin clave" in g["nota"]


def test_costear_sin_red_no_insiste(pl):
    reg = []
    res = CT.costear(pl, buscar=True, clave="k", _abrir=_abridor(OSError("sin red"), reg))
    assert len(reg) == 1 and all(f["origen"] == "bibliografía" for f in res["filas"])
    assert any("Sin conexión" in a for a in res["avisos"])


# ---------------------------------------------------------------- precios_web
def test_leer_numero_formatos():
    assert PW.leer_numero("12,345.67") == pytest.approx(12345.67) and PW.leer_numero("12.345,67") == pytest.approx(12345.67)
    assert PW.leer_numero("1.234.567") == pytest.approx(1234567) and PW.leer_numero("7,5") == pytest.approx(7.5)
    assert PW.leer_numero("4,200") == pytest.approx(4200) and PW.leer_numero("1.5") == pytest.approx(1.5)


def test_extraer_precios_monedas():
    d, e = 1000.0, 1100.0
    p = PW.extraer_precios("Pump US$ 9,500 or EUR 8.000 and CLP $ 7.500.000; also 2.5k USD", d, e)
    assert [x["moneda"] for x in p] == ["USD", "EUR", "CLP", "USD"]
    assert p[1]["precio_usd"] == pytest.approx(8000 * 1100 / 1000) and p[2]["precio_usd"] == pytest.approx(7500)
    assert p[3]["precio_usd"] == pytest.approx(2500)
    assert PW.extraer_precios("only $5 shipping", d, e) == []                    # bajo la banda de un equipo
    assert PW.a_usd(990.35, "CLP", 990.35, 1108.39) == pytest.approx(1.0)
    with pytest.raises(ValueError):
        PW.a_usd(1, "JPY", 1, 1)


def test_extraer_tamano_unidades():
    assert PW.extraer_tamano("Bomba 10 HP acero") == (pytest.approx(7.457), "kW")
    assert PW.extraer_tamano("motor 7,5 kW") == (pytest.approx(7.5), "kW")
    assert PW.extraer_tamano("area 120 m²")[1] == "m2" and PW.extraer_tamano("caudal 35 m3/h")[1] == "m3/h"
    assert PW.extraer_tamano('pipe 2" sch 10', "pulgadas") == (pytest.approx(2.0), "pulgadas")
    assert PW.extraer_tamano("sin tamaño") is None and PW.extraer_tamano("10 HP", "m2") is None


def test_buscar_tavily_peticion_y_errores():
    reg = []
    r = PW.buscar_tavily("pump price", "tvly-x", _abrir=_abridor({"results": []}, reg))
    assert r == {"results": []} and reg[0]["url"] == PW.URL_TAVILY and reg[0]["metodo"] == "POST"
    assert reg[0]["cuerpo"] == dict(api_key="tvly-x", query="pump price", search_depth="basic", max_results=5, include_answer=True)
    with pytest.raises(ValueError):
        PW.buscar_tavily("x", "")
    with pytest.raises(OSError):
        PW.buscar_tavily("x", "k", _abrir=_abridor(OSError("sin red")))


def test_obtener_clave_secretos_y_entorno():
    viejo = os.environ.pop("TAVILY_API_KEY", None)
    try:
        assert PW.obtener_clave({}) is None and PW.obtener_clave({"TAVILY_API_KEY": ""}) is None
        assert PW.obtener_clave({"TAVILY_API_KEY": " tvly-s "}) == "tvly-s"
        os.environ["TAVILY_API_KEY"] = "tvly-entorno"
        assert PW.obtener_clave({}) == "tvly-entorno" and PW.obtener_clave({"TAVILY_API_KEY": "tvly-s"}) == "tvly-s"
    finally:
        os.environ.pop("TAVILY_API_KEY", None)
        if viejo is not None:
            os.environ["TAVILY_API_KEY"] = viejo


def test_cache_guardar_ultimo_y_listar():
    bd = BaseDatos(":memory:")
    assert PW.ruta_bd(bd) == ":memory:" and PW.ultimo_precio(bd, "bomba_centrifuga") is None
    PW.guardar_precio(bd, "bomba_centrifuga", 3.7, "kW", 4200, "USD", "a", "u1", fecha="2026-11-01 10:00")
    PW.guardar_precio(bd, "bomba_centrifuga", 7.5, "kW", 7500000, "CLP", "b", "u2", fecha="2026-11-04 10:00")
    u = PW.ultimo_precio(bd, "bomba_centrifuga")
    assert u["moneda"] == "CLP" and u["url"] == "u2" and u["origen"] == "internet"
    assert len(PW.listar_precios(bd)) == 2 and len(PW.listar_precios(bd, "otro")) == 0


def test_elegir_precio_tamano_mas_cercano():
    c = PW.elegir_precio(RESP_BOMBA, "kW", 7.0, 990.35, 1108.39)
    assert c["url"] == "https://ejemplo.cl/bomba75" and c["moneda"] == "CLP"                       # 7,5 kW, el más cercano a 7
    assert PW.elegir_precio({"results": [{"content": "sin cifras"}]}, "kW", 7, 1, 1) is None
    d = PW.elegir_precio({"answer": "about US$ 9,500 for 10 HP", "results": [{"content": "sin cifras"}]}, "kW", 7, 1, 1)
    assert d["url"] == "" and d["precio_usd"] == pytest.approx(9500)                              # respuesta resumida solo de respaldo


def test_obtener_precio_sin_red_ni_clave_nunca_se_cae():
    bd = BaseDatos(":memory:")
    resp = lambda: dict(precio_usd=100.0, tamano=1.0, unidad="kW", fuente="libro", url="", fecha="2023", anio=2023, cepci_ref=797.9)
    p = PW.obtener_precio("x", "q", "kW", 1.0, 990.35, 1108.39, bd=bd, clave="k", buscar=True, respaldo=resp,
                          _abrir=_abridor(OSError("sin red")))
    assert p["origen"] == "bibliografía" and "Sin conexión" in p["nota"]
    assert PW.obtener_precio("x", "q", "kW", 1.0, 1, 1, bd=None, clave=None, buscar=True) is None
    PW.guardar_precio(bd, "x", 2.0, "kW", 300, "USD", "web", "u")
    q = PW.obtener_precio("x", "q", "kW", 1.0, 990.35, 1108.39, bd=bd, clave=None, buscar=False, respaldo=resp)
    assert q["origen"] == "internet (guardado)" and q["precio_usd"] == pytest.approx(300)
