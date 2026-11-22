"""Pruebas de la base de respaldo de equipos reales y del ajuste de Williams (PAT 139, equipo E2, 14-11-2026): siembra idempotente,
tres puntos por tipo, regresión log-log con un caso conocido, precio por interpolación y por extrapolación, candidatos sin red y con
Tavily simulado, estado de Tavily (sin clave, clave rechazada, sin red, créditos agotados y caché) y conversiones. Sin internet."""
import csv, re, json, urllib.error
from pathlib import Path
import pytest
from pat_sim.datos.bd import BaseDatos
from pat_sim.datos import referencia_equipos as RE, referencia_equipos_datos as DAT, precios_web as PW
from pat_sim.motor import costeo as CO


@pytest.fixture(autouse=True)
def _sin_clave_ni_cache(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    RE._ESTADO.clear(); RE._BUSQUEDAS.clear()
    yield
    RE._ESTADO.clear(); RE._BUSQUEDAS.clear()


@pytest.fixture()
def bd(tmp_path):
    return BaseDatos(tmp_path / "ref.db")


class _Resp:
    def __init__(self, datos):
        self.datos = datos if isinstance(datos, bytes) else json.dumps(datos).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.datos


USO_OK = {"key": {"usage": 12, "limit": 1000}, "account": {"current_plan": "Researcher", "plan_usage": 12, "plan_limit": 1000}}
PAGINA = {"title": "Sanitary centrifugal pump 4 kW stainless steel", "url": "https://ejemplo.test/bomba-4kw",
          "content": "Manufacturer: Acme Pumps. Model: AP-40. Price: US$ 1,500. Capacity 4 kW. Weight: 35 kg. Material: stainless steel 304.",
          "raw_content": ""}


def _tavily_falso(uso=USO_OK, paginas=(PAGINA,)):
    llamadas = []

    def abrir(req, timeout=None):
        llamadas.append(req.get_method())
        if req.get_method() == "GET":
            return _Resp(uso)
        return _Resp({"results": list(paginas), "answer": ""})
    abrir.llamadas = llamadas
    return abrir


# ---------------------------------------------------------------- siembra
def test_siembra_idempotente(bd):
    n1 = RE.sembrar(bd)
    assert n1 == len(DAT.FILAS) > 40
    assert RE.sembrar(bd) == 0
    # una base nueva sobre el mismo archivo no duplica
    assert RE.sembrar(BaseDatos(bd.ruta)) == 0
    total = sum(len(RE.referencias(t, bd)) for t in RE.tipos(bd))
    assert total == len(DAT.FILAS)


def test_siembra_no_pisa_lo_editado(bd):
    RE.sembrar(bd)
    with PW._conexion(bd) as con:
        con.execute(f"UPDATE {RE.TABLA} SET precio_usd = 123.0 WHERE tipo = 'bomba_centrifuga' AND punto = 'minimo'")
    RE.sembrar(bd)
    assert RE.referencias("bomba_centrifuga", bd, solo_puntos=True)[0]["precio_usd"] == 123.0


def test_la_tabla_vive_en_la_misma_sqlite(bd):
    RE.sembrar(bd)
    with PW._conexion(bd) as con:
        nombres = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    assert {"equipos_referencia", "proyectos", "fuentes"} <= nombres


# ---------------------------------------------------------------- tres puntos por tipo
def test_tres_puntos_por_tipo_los_que_tienen_tres(bd):
    completos = []
    for t in RE.tipos(bd):
        pts = {r["punto"]: r for r in RE.referencias(t, bd, solo_puntos=True)}
        assert set(pts) <= {"minimo", "medio", "maximo"}
        if len(pts) == 3:
            completos.append(t)
            a, b, c = (pts[k]["capacidad"] for k in ("minimo", "medio", "maximo"))
            assert a < b < c, t
    assert len(completos) >= 10
    assert len(RE.tipos(bd)) >= 12


def test_cada_dato_trae_su_fuente_y_nada_inventado(bd):
    for t in RE.tipos(bd):
        assert t in RE.UNIDAD_TIPO
        for r in RE.referencias(t, bd):
            assert r["url"].startswith("http"), r["modelo"]
            assert r["fecha_consulta"] in ("2026-11-14", "2026-11-16")   # PAT 140: filas nuevas del 16-11
            assert r["fabricante"] and r["modelo"]
            for k in ("mtbf_h", "mttr_h"):   # PAT 140: de literatura con su fuente, o «sin dato»
                assert r[k] is None or r[k] > 0, (r["modelo"], k)
            if r["mtbf_h"] or r["mttr_h"]:
                assert re.search(r"(19|20)\d\d", r["confiabilidad_texto"] or ""), r["modelo"]   # cita con autor y año
            if r["precio_puntual"]:
                assert r["precio_usd"] and r["precio_texto"]
            if r["usar_en_ajuste"]:
                assert r["precio_puntual"]


def test_equipos_reales_con_precio_puntual_y_url(bd):
    con_precio = [r for t in RE.tipos(bd) for r in RE.referencias(t, bd) if r["precio_puntual"]]
    assert len(con_precio) >= 10
    assert all(r["url"] for r in con_precio)


def test_unidades_de_trabajo_coinciden_con_costeo():
    for tipo, clave in DAT.CLAVE_COSTEO.items():
        ref = CO.REFERENCIAS.get(clave)
        if ref is not None:
            assert ref["unidad"] == DAT.UNIDAD_TIPO[tipo], tipo


# ---------------------------------------------------------------- Williams
def test_n_exacto_con_precios_de_una_potencia():
    pts = [(10.0, 5000.0 * 10 ** 0.55), (40.0, 5000.0 * 40 ** 0.55), (250.0, 5000.0 * 250 ** 0.55)]
    a = RE.ajustar_williams("trituradora", puntos=pts)
    assert a["metodo"] == "regresión"
    assert a["n"] == pytest.approx(0.55, abs=1e-12)
    assert a["r2"] == pytest.approx(1.0, abs=1e-12)
    assert a["C1"] * (100.0 / a["S1"]) ** a["n"] == pytest.approx(5000.0 * 100 ** 0.55, rel=1e-9)
    assert len(a["puntos"]) == 3


def test_dos_puntos_dan_ajuste_exacto():
    a = RE.ajustar_williams("trituradora", puntos=[(2.0, 100.0), (8.0, 100.0 * 4 ** 0.7)])
    assert a["n"] == pytest.approx(0.7) and a["r2"] == pytest.approx(1.0)


def test_menos_de_dos_puntos_usa_el_n_de_costeo_y_lo_dice():
    a = RE.ajustar_williams("bomba_centrifuga", puntos=[(1.0, 700.0)])
    assert a["metodo"] == "costeo" and a["n"] == CO.EXPONENTES["bomba_centrifuga"][0] == 0.67
    assert "costeo.py" in a["aviso"] and "un solo equipo" in a["aviso"]
    b = RE.ajustar_williams("trituradora", puntos=[])
    assert b["n"] == CO.N_SEIS_DECIMOS and "No hay equipos reales" in b["aviso"] and b["C1"] is None
    c = RE.ajustar_williams("intercambiador", puntos=[(5.0, 100.0)])
    assert c["n"] == 0.60                                                # Turton et al. (2018)


def test_ajuste_no_fisico_se_descarta():
    a = RE.ajustar_williams("trituradora", puntos=[(1.0, 1000.0), (2.0, 100.0)])     # n negativo
    assert a["metodo"] == "costeo" and "fuera de la banda" in a["aviso"]


def test_ajuste_de_la_serie_ato_con_la_base(bd):
    a = RE.ajustar_williams("bomba_centrifuga", bd)
    assert a["metodo"] == "regresión" and len(a["puntos"]) == 3
    assert 0.3 < a["n"] < 0.7 and a["r2"] > 0.9
    assert all(p["fabricante"].startswith("ATO") for p in a["puntos"])   # las Alfa Laval (serie premium) no entran


def test_precio_williams_interpola(bd):
    pts = {r["punto"]: r for r in RE.referencias("bomba_centrifuga", bd, solo_puntos=True)}
    w = RE.precio_williams("bomba_centrifuga", 2.0, bd)
    assert w["metodo"] == "regresión" and not w["extrapola"]
    assert pts["medio"]["precio_usd"] < w["precio_usd"] < pts["maximo"]["precio_usd"]
    assert w["rango"] == (0.55, 3.0) and w["n"] == pytest.approx(RE.ajustar_williams("bomba_centrifuga", bd)["n"])
    assert "Williams" in w["fuente"] and "Regresión log-log" in w["fuente"]
    # en un punto de la base devuelve algo cercano a su precio (ajuste por mínimos cuadrados)
    w1 = RE.precio_williams("bomba_centrifuga", pts["medio"]["capacidad"], bd)
    assert w1["precio_usd"] == pytest.approx(pts["medio"]["precio_usd"], rel=0.15)


def test_precio_williams_avisa_si_extrapola(bd):
    w = RE.precio_williams("bomba_centrifuga", 30.0, bd)
    assert w["extrapola"] and any("Extrapola" in a for a in w["avisos"])
    assert w["precio_usd"] > RE.precio_williams("bomba_centrifuga", 3.0, bd)["precio_usd"]


def test_precio_williams_actualiza_con_cepci_si_hay_indice(bd, monkeypatch):
    base = RE.precio_williams("bomba_centrifuga", 1.0, bd)
    assert base["factor_cepci"] == 1.0 and any("sin CEPCI" in a for a in base["avisos"])    # 2026 no tiene índice público
    monkeypatch.setattr(RE, "ANIO_PRECIO_REFERENCIAS", 2020)
    w = RE.precio_williams("bomba_centrifuga", 1.0, bd, cepci_hoy=797.9)
    assert w["factor_cepci"] == pytest.approx(797.9 / CO.CEPCI_ANUAL[2020])
    assert w["precio_usd"] == pytest.approx(base["precio_usd"] * 797.9 / CO.CEPCI_ANUAL[2020])


def test_sin_puntos_usa_la_bibliografia_de_costeo(bd):
    w = RE.precio_williams("caldera_gas", 3000.0, bd)
    assert w["metodo"] == "bibliografía" and w["precio_usd"] > 0 and "Towler" in w["fuente"]
    e = RE.precio_williams("evaporador_multiefecto", 20000.0, bd)         # 20.000 kg/h: el tamaño de referencia de costeo.py
    assert e["metodo"] == "bibliografía" and e["precio_usd"] > 1e5
    est = RE.precio_williams("estanque_pulmon", 10.0, bd)                 # un punto real (0,3 m3) y n de costeo
    assert est["metodo"] == "costeo" and est["extrapola"]


def test_precio_williams_rechaza_capacidad_no_positiva(bd):
    with pytest.raises(ValueError):
        RE.precio_williams("bomba_centrifuga", 0.0, bd)


# ---------------------------------------------------------------- conversiones
def test_conversiones():
    assert RE.convertir("caldera_gas", 1.0, "t/h vapor", "kW") == pytest.approx(1000 * CO.DH_VAPOR / 3600)
    assert RE.convertir("caldera_gas", 655.5555, "kW", "t/h vapor") == pytest.approx(1.0, rel=1e-5)
    assert RE.convertir("hot_break", 2.0, "t/h", "kW") == pytest.approx(2 * RE.kw_por_t_h("hot_break"))
    assert RE.convertir("esterilizador", 3000.0, "L/h", "kW") == pytest.approx(3 * RE.kw_por_t_h("esterilizador"))
    assert RE.convertir("intercambiador", 100.0, "sq ft", "m2") == pytest.approx(9.290304)
    assert RE.convertir("bomba_centrifuga", 7.5, "hp", "kW") == pytest.approx(5.593, abs=1e-3)
    assert RE.convertir("estanque_pulmon", 5000.0, "L", "m3") == 5.0
    assert RE.convertir("trituradora", 500.0, "kg/h", "t/h") == 0.5
    assert RE.convertir("trituradora", 1.0, "kW", "t/h") is None
    assert 60 < RE.kw_por_t_h("hot_break") < 80 and 40 < RE.kw_por_t_h("esterilizador") < 50


# ---------------------------------------------------------------- candidatos sin red
def test_candidatos_sin_red_devuelven_respaldo_y_williams(bd):
    r = RE.candidatos_con_avisos("trituradora", 100.0, "t/h", en_linea=True, secretos={}, bd=bd)
    c = r["candidatos"]
    assert not r["tavily"]["en_linea"] and any("Sin clave" in a for a in r["avisos"])
    assert {x["origen"] for x in c} == {"Respaldo", "Williams"}
    w = [x for x in c if x["origen"] == "Williams"]
    assert len(w) == 1 and w[0]["capacidad"] == 100.0 and w[0]["precio_usd"] > 0 and w[0]["precio_estimado"]
    assert len([x for x in c if x["origen"] == "Respaldo"]) == len(RE.referencias("trituradora", bd))
    for x in c:
        assert x["fuente"] and x["precio_usd"] > 0 and x["n"] == 1 and x["unidad"] == "t/h" and "id" in x and "modelo" in x
    assert [x["precio_usd"] for x in c] == sorted(x["precio_usd"] for x in c)


def test_si_una_referencia_calza_no_se_agrega_williams(bd):
    c = RE.candidatos("bomba_centrifuga", 1.1, "kW", en_linea=False, bd=bd)
    assert not any(x["origen"] == "Williams" for x in c)
    exacto = next(x for x in c if x["modelo"] == "ATO-50SF6-18-1.1")
    assert exacto["precio_usd"] == 730.21 and not exacto["precio_estimado"] and exacto["url"].startswith("https://www.ato.com")
    assert exacto["material"] == "Acero inoxidable 304" and exacto["peso_kg"] == 24.0 and (exacto["mtbf_h"] is None or exacto["mtbf_h"] > 0)


def test_candidatos_convierte_la_unidad_pedida(bd):
    c = RE.candidatos("hot_break", 143.7, "kW", en_linea=False, bd=bd)
    assert not any(x["origen"] == "Williams" for x in c)
    assert next(x for x in c if x["origen"] == "Respaldo")["precio_usd"] == 14000.0
    c2 = RE.candidatos("caldera_gas", 2.0, "t/h vapor", en_linea=False, bd=bd)
    assert c2 and all(x["unidad"] == "t/h vapor" for x in c2)
    assert all(x["precio_estimado"] or x["precio_usd"] for x in c2)   # PAT 140: calderas usadas con precio puntual


def test_referencias_sin_precio_puntual_se_estiman_y_se_marcan(bd):
    c = RE.candidatos("evaporador_multiefecto", 20000.0, "kg/h", en_linea=False, bd=bd)
    ref = next(x for x in c if x["modelo"].startswith("MKFE-20"))
    assert ref["precio_estimado"] and "100.000-650.000" in ref["fuente"] and ref["origen"] == "Respaldo"


def test_candidatos_con_capacidad_invalida(bd):
    assert RE.candidatos("bomba_centrifuga", 0.0, "kW", bd=bd) == []


def test_tipo_desconocido_no_falla(bd):
    r = RE.candidatos_con_avisos("tipo_que_no_existe", 10.0, "t/h", en_linea=False, bd=bd)
    assert r["candidatos"] == [] and r["avisos"]


# ---------------------------------------------------------------- candidatos con Tavily simulado
def test_candidatos_con_tavily_en_vivo_simulado(bd):
    abrir = _tavily_falso()
    r = RE.candidatos_con_avisos("bomba_centrifuga", 4.0, "kW", en_linea=True, secretos={"TAVILY_API_KEY": "tvly-prueba"}, bd=bd, _abrir=abrir)
    assert r["tavily"]["en_linea"] and abrir.llamadas[0] == "GET" and "POST" in abrir.llamadas
    t = [x for x in r["candidatos"] if x["origen"] == "Tavily"]
    assert len(t) == 1
    assert t[0]["fabricante"] == "Acme Pumps" and t[0]["modelo"] == "AP-40" and t[0]["capacidad"] == pytest.approx(4.0)
    assert t[0]["precio_usd"] == pytest.approx(1500.0) and not t[0]["precio_estimado"] and t[0]["url"] == PAGINA["url"]
    assert "ejemplo.test" in t[0]["fuente"] and t[0]["peso_kg"] == 35.0
    assert any(x["origen"] == "Respaldo" for x in r["candidatos"])
    assert "tvly-prueba" not in json.dumps(r, default=str)                     # la clave no se filtra al resultado


def test_tavily_sin_precio_en_la_pagina_se_estima_con_williams(bd):
    pag = dict(PAGINA, content="Manufacturer: Acme Pumps. Model: AP-40. Capacity 4 kW. Material: stainless steel 304.")
    abrir = _tavily_falso(paginas=(pag,))
    c = RE.candidatos_con_avisos("bomba_centrifuga", 4.0, "kW", secretos={"TAVILY_API_KEY": "x"}, bd=bd, _abrir=abrir)["candidatos"]
    t = next(x for x in c if x["origen"] == "Tavily")
    assert t["precio_estimado"] and t["precio_usd"] > 0 and "no trae precio" in t["fuente"]


def test_tavily_que_falla_cae_al_respaldo(bd):
    def abrir(req, timeout=None):
        raise urllib.error.URLError("sin red")
    r = RE.candidatos_con_avisos("bomba_centrifuga", 1.1, "kW", secretos={"TAVILY_API_KEY": "x"}, bd=bd, _abrir=abrir)
    assert not r["tavily"]["en_linea"] and "Sin conexión" in r["tavily"]["motivo"]
    assert r["candidatos"] and {x["origen"] for x in r["candidatos"]} == {"Respaldo"}


# ---------------------------------------------------------------- estado de Tavily
def test_estado_sin_clave_dice_por_que():
    e = RE.estado_tavily(secretos={})
    assert e["en_linea"] is False and "Sin clave" in e["motivo"] and "TAVILY_API_KEY" in e["motivo"]


def test_estado_con_clave_valida():
    abrir = _tavily_falso()
    e = RE.estado_tavily(secretos={"TAVILY_API_KEY": "tvly-x"}, _abrir=abrir)
    assert e["en_linea"] is True and "Conectado" in e["motivo"] and e["creditos_usados"] == 12 and e["limite"] == 1000
    assert abrir.llamadas == ["GET"]                                    # solo la consulta de uso: ninguna búsqueda


def test_estado_clave_rechazada_y_sin_red_y_creditos_agotados():
    def r401(req, timeout=None):
        raise urllib.error.HTTPError("u", 401, "no", {}, None)
    assert "rechazó" in RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _abrir=r401)["motivo"]

    def r429(req, timeout=None):
        raise urllib.error.HTTPError("u", 429, "mucho", {}, None)
    assert "429" in RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _abrir=r429)["motivo"]

    def sinred(req, timeout=None):
        raise urllib.error.URLError("sin red")
    e = RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _abrir=sinred)
    assert not e["en_linea"] and "Sin conexión" in e["motivo"]

    agotado = _tavily_falso(uso={"key": {"usage": 1000, "limit": 1000}})
    e = RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _abrir=agotado)
    assert not e["en_linea"] and "agotados" in e["motivo"]

    basura = lambda req, timeout=None: _Resp(b"<html>no es json</html>")
    assert not RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _abrir=basura)["en_linea"]


def test_estado_se_guarda_diez_minutos(monkeypatch):
    llamadas = []

    def falso(req, timeout=None):
        llamadas.append(1)
        return _Resp(USO_OK)
    monkeypatch.setattr(RE.urllib.request, "urlopen", falso)
    t = [1000.0]
    e1 = RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _ahora=lambda: t[0])
    e2 = RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _ahora=lambda: t[0] + 300)
    assert len(llamadas) == 1 and e1["desde_cache"] is False and e2["desde_cache"] is True and e2["en_linea"]
    RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, _ahora=lambda: t[0] + 601)
    assert len(llamadas) == 2                                            # pasados 10 minutos se vuelve a probar
    RE.estado_tavily(secretos={"TAVILY_API_KEY": "x"}, forzar=True, _ahora=lambda: t[0] + 602)
    assert len(llamadas) == 3


def test_la_clave_nunca_se_guarda_en_archivos(bd, tmp_path, monkeypatch):
    monkeypatch.setattr(RE.urllib.request, "urlopen", lambda req, timeout=None: _Resp(USO_OK))
    RE.estado_tavily(secretos={"TAVILY_API_KEY": "tvly-SECRETA-123"})
    assert "tvly-SECRETA-123" not in json.dumps(RE._ESTADO, default=str)
    RE.sembrar(bd)
    assert b"tvly-SECRETA-123" not in Path(bd.ruta).read_bytes()


# ---------------------------------------------------------------- CSV
def test_csv_legible_con_todo_y_sin_dato(bd, tmp_path):
    ruta = RE.exportar_csv(tmp_path / "ref.csv", bd)
    with open(ruta, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    assert len(filas) == len(DAT.FILAS)
    assert all(f["url"].startswith("http") for f in filas)
    assert any(f["mtbf_h"] == "sin dato" for f in filas)
    assert all(f["mtbf_h"] == "sin dato" or float(f["mtbf_h"].replace(".", "").replace(",", ".")) > 0 for f in filas)   # PAT 140
    assert next(f for f in filas if f["modelo"] == "ATO-50SF6-18-1,1" or f["modelo"] == "ATO-50SF6-18-1.1")["precio_usd"] == "730,21"


def test_csv_entregado_coincide_con_la_base(bd):
    entregado = RE.RUTA_CSV
    if not entregado.exists():
        pytest.skip("El CSV de «03 Base de datos» no está en esta copia")
    with open(entregado, encoding="utf-8-sig", newline="") as fh:
        filas = list(csv.DictReader(fh, delimiter=";"))
    assert len(filas) == len(DAT.FILAS)
    assert {f["url"] for f in filas} == {r["url"] for r in DAT.FILAS}
