"""PAT 136, T23 (punto 9 y 10b de los comentarios del profesor Torres): ficha de máquina, extractor de texto de Tavily con
expresiones regulares (sin internet), campos «sin dato», guardado en la base, y comparación de combinaciones de máquinas
(una grande contra varias chicas) en costo, disponibilidad k de n, espacio y energía."""
import json
from pathlib import Path
import pytest
from pat_sim.datos.bd import BaseDatos
from pat_sim.datos import genericos as GE, mantenedor as M, precios_web as PW
from pat_sim.motor import fichas as FI, seleccion as S, costeo as CO
from pat_sim.escenarios import pellet, agrozzi

REF = Path(__file__).parent / "referencia"
PAGINAS = json.loads((REF / "fichas_paginas_ejemplo.json").read_text(encoding="utf-8"))
RESPUESTA = (REF / "tavily_respuesta_fichas_ejemplo.json").read_text(encoding="utf-8")
CAT = M.semilla_catalogo_comercial()
HOY = "2026-11-13"


def _ficha(clave, tipo="pelletizadora", unidad=None):
    p = PAGINAS[clave]
    return FI.extraer_ficha(p["content"], tipo, p["url"], HOY, p["title"], unidad)


class _Resp:
    def __init__(self, datos):
        self.datos = datos if isinstance(datos, bytes) else datos.encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self):
        return self.datos


@pytest.fixture()
def g(tmp_path):
    return GE.BaseGenericos(BaseDatos(tmp_path / "f.db"))


# ---------------------------------------------------------------- extractor
def test_ficha_completa_lee_los_16_campos_con_su_fuente():
    f = _ficha("pelletizadora_completa", unidad="t/h")
    assert FI.faltan(f) == [] and FI.completitud(f) == pytest.approx(1.0)
    assert FI.valor(f, "fabricante") == "Zhengfeng Machinery" and FI.valor(f, "modelo") == "GM-550"
    assert FI.valor(f, "capacidad") == pytest.approx(5.0) and f["campos"]["capacidad"]["unidad"] == "t/h"
    p = f["campos"]["precio"]
    assert p["valor"] == pytest.approx(38500.0) and p["moneda"] == "US$" and "extremo menor" in p["nota"]
    assert (FI.valor(f, "mtbf_h"), FI.valor(f, "mttr_h")) == (pytest.approx(1200.0), pytest.approx(6.0))
    assert FI.valor(f, "disponibilidad") == pytest.approx(0.975)
    assert FI.valor(f, "potencia_kw") == pytest.approx(250.0)
    assert (FI.valor(f, "largo_m"), FI.valor(f, "ancho_m"), FI.valor(f, "alto_m")) == (pytest.approx(3.2), pytest.approx(1.8), pytest.approx(2.9))
    assert FI.valor(f, "peso_kg") == pytest.approx(9800.0) and FI.valor(f, "material") == "stainless steel 304"
    assert FI.valor(f, "garantia_meses") == pytest.approx(12.0) and FI.valor(f, "plazo_entrega_semanas") == pytest.approx(6.0)
    for k in FI.CLAVES:                                        # cada dato con URL y fecha de la consulta
        assert f["campos"][k]["url"] == PAGINAS["pelletizadora_completa"]["url"] and f["campos"][k]["fecha"] == HOY


def test_pagina_en_espanol_con_precio_en_pesos_y_unidades_chilenas():
    f = _ficha("evaporador_espanol", "evaporador_multiefecto", "kg/h")
    assert FI.valor(f, "fabricante") == "Industrias Demo" and FI.valor(f, "modelo") == "EV-3E 12000"
    assert FI.valor(f, "capacidad") == pytest.approx(12000.0) and f["campos"]["capacidad"]["unidad"] == "kg/h"
    assert f["campos"]["precio"]["moneda"] == "CLP" and FI.valor(f, "precio") == pytest.approx(485000000.0)
    assert (FI.valor(f, "largo_m"), FI.valor(f, "ancho_m"), FI.valor(f, "alto_m")) == (pytest.approx(9.5), pytest.approx(3.2), pytest.approx(7.8))
    assert FI.valor(f, "peso_kg") == pytest.approx(28000.0)               # 28 t
    assert FI.valor(f, "garantia_meses") == pytest.approx(24.0) and FI.valor(f, "plazo_entrega_semanas") == pytest.approx(20.0)
    assert "inoxidable" in FI.valor(f, "material").lower()


def test_pagina_sin_datos_deja_todo_en_sin_dato_menos_el_titulo():
    f = _ficha("pagina_sin_datos", "secador_biomasa")
    assert FI.valor(f, "nombre") == "Cómo elegir un secador para biomasa"
    assert len(FI.faltan(f)) == 15 and "precio" in FI.faltan(f) and "capacidad" in FI.faltan(f)
    for k in FI.faltan(f):
        assert FI.texto_campo(f, k) == FI.SIN_DATO and FI.fuente_campo(f, k) == FI.SIN_DATO
    assert all(r["valor"] == "sin dato" for r in FI.tabla_ficha(f) if r["campo"] in ("Precio", "Garantía"))


def test_conversiones_hp_libras_dias_y_anios():
    f = _ficha("bomba_hp", "bomba_centrifuga", "m3/h")
    assert FI.valor(f, "potencia_kw") == pytest.approx(10 * PW.HP_KW)
    assert FI.valor(f, "peso_kg") == pytest.approx(85 * 0.45359237)
    assert FI.valor(f, "plazo_entrega_semanas") == pytest.approx(30 / 7.0)      # 15 a 30 días: extremo mayor
    assert FI.valor(f, "garantia_meses") == pytest.approx(24.0)
    assert FI.valor(f, "capacidad") == pytest.approx(25.0) and FI.valor(f, "fabricante") == "Grundfos"
    assert FI.valor(f, "modelo") == "CR 20-3"


def test_no_inventa_un_numero_sin_etiqueta_ni_unidad_ni_un_precio_fuera_de_banda():
    t = "Pump for sale. 250 kW unit, 12 kg of spare parts, 3 pieces. Special price $ 9 only today. Call us for a quote."
    f = FI.extraer_ficha(t, "bomba_centrifuga", "https://x.test", HOY, "")
    assert not FI.tiene(f, "potencia_kw")        # 250 kW sin etiqueta de potencia
    assert not FI.tiene(f, "peso_kg")            # 12 kg sin etiqueta de peso
    assert not FI.tiene(f, "precio")             # US$ 9 está bajo la banda de un equipo
    assert not FI.tiene(f, "capacidad")          # kW no es capacidad si no se pide
    assert FI.valor(FI.extraer_ficha(t, "hot_break", "", HOY, "", "kW"), "capacidad") == pytest.approx(250.0)


def test_lectores_de_numeros_formato_ingles_y_chileno():
    assert FI._horas("MTBF: 1.250 horas", "MTBF")[0] == pytest.approx(1250.0)
    assert FI._horas("MTBF 1,250 hours", "MTBF")[0] == pytest.approx(1250.0)
    assert FI._horas("MTTR 2,5 h", "MTTR")[0] == pytest.approx(2.5)
    assert FI._horas("sin MTBF aquí", "MTBF") is None
    assert FI.leer_disponibilidad("Disponibilidad: 98,5 %")[0] == pytest.approx(0.985)
    assert FI.leer_disponibilidad("availability 150 %") is None
    assert FI.leer_plazo("Plazo de entrega: 3 meses")[0] == pytest.approx(3 * 52 / 12)
    assert FI.leer_garantia("Garantía de 18 meses")[0] == pytest.approx(18.0)


def test_precio_en_euros_y_pesos_se_lleva_a_dolares():
    f = FI.extraer_ficha("Price: EUR 20,000. Capacity 2 t/h", "pelletizadora", "u", HOY, "", "t/h")
    assert f["campos"]["precio"]["moneda"] == "EUR" and FI.usd_de_precio(f, 1000.0, 1100.0) == pytest.approx(22000.0)
    f2 = FI.extraer_ficha("Precio: CLP 9.900.000", "pelletizadora", "u", HOY, "")
    assert FI.usd_de_precio(f2, 990.0, 1100.0) == pytest.approx(10000.0)
    assert FI.usd_de_precio(FI.ficha_vacia("x"), 990.0, 1100.0) is None


def test_capacidad_prefiere_la_unidad_pedida_y_la_etiqueta():
    t = "Motor 1500 kg/h of feed, Capacity: 3 t/h, output 40 m3/h"
    assert FI.extraer_capacidad(t, "t/h")[:2] == (3.0, "t/h")
    assert FI.extraer_capacidad(t, "m3/h")[:2] == (40.0, "m3/h")
    assert FI.extraer_capacidad(t, "kg/h")[:2] == (1500.0, "kg/h")      # la unidad pedida gana a una unidad convertible con etiqueta
    assert FI.extraer_capacidad("Rated capacity 8 tons per hour", None)[:2] == (8.0, "t/h")
    assert FI.extraer_capacidad("sin cifras", "t/h") is None


def test_convertir_capacidad():
    assert FI.convertir_capacidad(12000, "kg/h", "t/h") == pytest.approx(12.0)
    assert FI.convertir_capacidad(48, "t/d", "t/h") == pytest.approx(2.0)
    assert FI.convertir_capacidad(5000, "L/h", "m3/h") == pytest.approx(5.0)
    assert FI.convertir_capacidad(3, "t/h", "t/h") == 3.0
    assert FI.convertir_capacidad(3, "t/h", "m3/h") is None and FI.convertir_capacidad(3, "kW", "t/h") is None


# ---------------------------------------------------------------- consulta y Tavily sin internet
def test_consulta_tavily_por_tipo_y_capacidad():
    q = FI.consulta_tavily("pelletizadora", 5.15464, "t/h")
    assert q.startswith("ring die pellet mill price 5.15 t/h") and q.endswith(FI.SUFIJO_FICHA) and len(q) <= 400
    assert "MVR evaporator" in FI.consulta_tavily("evaporador_mvr", 20000, "kg/h")
    assert FI.consulta_tavily("mezclador_x", 3, "t/h", "paddle mixer").startswith("industrial paddle mixer price 3 t/h")


def test_buscar_fichas_sin_clave_avisa_y_no_trae_fichas():
    r = FI.buscar_fichas("pelletizadora", 5, "t/h", None)
    assert r["fichas"] == [] and r["origen"] == "catálogo" and "Sin clave de Tavily" in r["avisos"][0]


def test_buscar_fichas_con_respuesta_de_ejemplo_arma_una_ficha_por_pagina():
    visto = {}

    def abrir(req, timeout=None):
        visto["cuerpo"] = json.loads(req.data.decode("utf-8")); visto["timeout"] = timeout
        return _Resp(RESPUESTA)
    r = FI.buscar_fichas("pelletizadora", 5, "t/h", "tvly-prueba", _abrir=abrir)
    assert visto["cuerpo"]["include_raw_content"] is True and visto["cuerpo"]["max_results"] == 5
    assert visto["cuerpo"]["query"] == r["consulta"] and r["origen"] == "Tavily" and r["avisos"] == []
    assert len(r["fichas"]) == 4
    f = r["fichas"][0]
    assert f["url"] == PAGINAS["pelletizadora_completa"]["url"] and f["campos"]["precio"]["url"] == f["url"]
    assert f["tipo_equipo"] == "pelletizadora" and f["consulta"] == r["consulta"]


def test_buscar_fichas_sin_red_avisa_y_usa_el_catalogo():
    def abrir(req, timeout=None):
        raise OSError("sin red")
    r = FI.buscar_fichas("pelletizadora", 5, "t/h", "tvly-prueba", _abrir=abrir)
    assert r["fichas"] == [] and r["origen"] == "catálogo" and "Sin conexión" in r["avisos"][0]
    r2 = FI.buscar_fichas("pelletizadora", 5, "t/h", "k", _abrir=lambda req, timeout=None: _Resp(json.dumps({"results": []})))
    assert r2["fichas"] == [] and "no devolvió páginas" in r2["avisos"][0]


def test_buscar_tavily_sigue_igual_sin_los_parametros_nuevos():
    visto = {}

    def abrir(req, timeout=None):
        visto["c"] = json.loads(req.data.decode("utf-8")); return _Resp("{}")
    PW.buscar_tavily("q", "k", _abrir=abrir)
    assert visto["c"]["max_results"] == PW.MAX_RESULTADOS and "include_raw_content" not in visto["c"]
    PW.buscar_tavily("q", "k", _abrir=abrir, max_resultados=3, texto_completo=True)
    assert visto["c"]["max_results"] == 3 and visto["c"]["include_raw_content"] is True


def test_clave_de_tavily_de_secrets_o_del_entorno():
    assert PW.obtener_clave({"TAVILY_API_KEY": " abc "}) == "abc"


# ---------------------------------------------------------------- base de datos
def test_guardar_ficha_con_guardar_modelo_y_registrar_precio(g):
    f = _ficha("pelletizadora_completa", unidad="t/h")
    r = FI.guardar_ficha(g, f)
    assert r["nuevo"] == 1 and r["precio_registrado"]
    m = g.listar_modelos("pelletizadora")
    m = next(x for x in m if x["fabricante"] == "Zhengfeng Machinery")
    assert m["modelo"] == "GM-550" and m["precio"] == pytest.approx(38500.0) and m["moneda"] == "US$" and m["fecha_precio"] == HOY
    assert m["url"] == f["url"] and m["categoria"] == "Internet" and m["peso_kg"] == pytest.approx(9800.0)
    assert m["plazo_entrega_semanas"] == pytest.approx(6.0) and m["potencia_kw"] == pytest.approx(250.0) and "Tavily" in m["fuente"]
    assert len(g.historial_precios(r["id"])) == 1
    # un precio nuevo del mismo modelo queda en el historial y pasa a ser el vigente
    f2 = FI.extraer_ficha("Manufacturer: Zhengfeng Machinery. Model: GM-550. Capacity: 5 t/h. Price: US$ 41,000", "pelletizadora", f["url"],
                          "2026-12-01", "x", "t/h")
    r2 = FI.guardar_ficha(g, f2)
    assert r2["id"] == r["id"] and r2["nuevo"] == 0 and len(g.historial_precios(r["id"])) == 2
    vigente = next(x for x in g.listar_modelos("pelletizadora") if x["id"] == r["id"])
    assert vigente["precio"] == pytest.approx(41000.0) and vigente["fecha_precio"] == "2026-12-01"
    # una ficha sin precio del mismo modelo no borra el precio vigente
    f3 = FI.extraer_ficha("Manufacturer: Zhengfeng Machinery. Model: GM-550. Capacity: 5 t/h", "pelletizadora", f["url"], "2027-01-05", "x", "t/h")
    FI.guardar_ficha(g, f3)
    assert next(x for x in g.listar_modelos("pelletizadora") if x["id"] == r["id"])["precio"] == pytest.approx(41000.0)


def test_ficha_sin_modelo_usa_el_titulo_y_anota_los_campos_sin_dato(g):
    f = FI.extraer_ficha("Capacity 4 t/h. Price US$ 30,000", "pelletizadora", "https://x.test/a", HOY, "Pellet mill generic", "t/h")
    m = FI.ficha_a_modelo(f)
    assert m["modelo"] == "Pellet mill generic" and "no informa el modelo" in m["nota"] and "Sin dato" in m["nota"] and m["fabricante"] == ""
    FI.guardar_ficha(g, f)
    assert any(x["modelo"] == "Pellet mill generic" for x in g.listar_modelos("pelletizadora"))


def test_ficha_leida_de_la_base_conserva_url_fecha_y_valores(g):
    f = _ficha("pelletizadora_completa", unidad="t/h")
    FI.guardar_ficha(g, f)
    fila = next(x for x in g.listar_modelos("pelletizadora") if x["modelo"] == "GM-550")
    h = FI.ficha_desde_modelo(fila)
    assert h["url"] == f["url"] and h["fecha"] == HOY and h["origen"] == "Tavily"
    assert FI.valor(h, "capacidad") == pytest.approx(5.0) and FI.valor(h, "precio") == pytest.approx(38500.0)
    assert FI.valor(h, "garantia_meses") == pytest.approx(12.0) and FI.valor(h, "material") == "stainless steel 304"
    assert "fabricante" not in FI.faltan(h) and h["campos"]["precio"]["fecha"] == HOY


def test_catalogo_supuesto_como_ficha_trae_fuente_y_sin_dato():
    fila = next(x for x in CAT if x["tipo"] == "pelletizadora")
    f = FI.ficha_desde_catalogo(fila)
    assert f["origen"] == "Supuesto" and "Supuesto" in FI.fuente_campo(f, "capacidad")
    assert FI.valor(f, "mtbf_h") == pytest.approx(fila["mtbf_h"]) and "Supuesto" in FI.fuente_campo(f, "precio")
    for k in ("fabricante", "peso_kg", "garantia_meses", "plazo_entrega_semanas", "potencia_kw"):
        assert FI.texto_campo(f, k) == "sin dato"


# ---------------------------------------------------------------- hacia la selección
def test_ficha_a_fila_convierte_unidad_deriva_mtbf_y_descarta_lo_inservible():
    f = FI.extraer_ficha("Model: EV-1. Capacity 12,000 kg/h. Price US$ 500,000. Availability 98 %", "evaporador_mvr", "u", HOY, "", "kg/h")
    fila = FI.ficha_a_fila_catalogo(f, "t/h", "evaporador_mvr")
    assert fila["capacidad"] == pytest.approx(12.0) and fila["unidad"] == "t/h" and fila["precio_usd"] == pytest.approx(500000.0)
    assert fila["mtbf_h"] / (fila["mtbf_h"] + fila["mttr_h"]) == pytest.approx(0.98) and "MTTR Supuesto" in fila["fuente_confiabilidad"]
    assert FI.ficha_a_fila_catalogo(f, "m2") is None                      # kg/h no se pasa a m2
    assert FI.ficha_a_fila_catalogo(FI.ficha_vacia("x"), "t/h") is None   # sin capacidad
    filas, malas = FI.filas_de_fichas([f, f, FI.ficha_vacia("evaporador_mvr")], "t/h", "evaporador_mvr")
    assert [x["modelo"] for x in filas] == ["EV-1", "EV-1 (2)"] and malas[0]["motivo"] == "sin capacidad"


# ---------------------------------------------------------------- comparación: una grande contra varias chicas
def _req_y_fichas():
    pl = pellet.crear()
    req = next(r for r in S.requerimientos(pl) if r["equipo"] == "A1")
    c = req["requerida"]                                     # 5,15 t/h
    grande = FI.extraer_ficha(f"Model: GRANDE-6. Capacity: {c + 0.85:.2f} t/h. Price: US$ 100,000. Installed power: 300 kW. "
                              "Dimensions: 4000x2200x3000 mm. MTBF 300 hours. MTTR 6 hours", "pelletizadora", "https://x.test/g", HOY, "", "t/h")
    chica = FI.extraer_ficha(f"Model: CHICA-2. Capacity: {c / 3 + 0.01:.2f} t/h. Price: US$ 40,000. Installed power: 110 kW. "
                             "Dimensions: 2500x1500x2000 mm. MTBF 300 hours. MTTR 6 hours", "pelletizadora", "https://x.test/c", HOY, "", "t/h")
    filas, _ = FI.filas_de_fichas([grande, chica], "t/h", "pelletizadora")
    return pl, req, filas


def test_una_grande_contra_tres_chicas_costo_disponibilidad_espacio_energia():
    pl, req, filas = _req_y_fichas()
    P = S.parametros(pl)
    r = S.comparar_combinaciones(req, filas, P, S.referencias_equipo(pl, "A1"))
    por = {(a["modelo"], a["n"]): a for a in r["alternativas"]}
    g1, c3 = por[("GRANDE-6", 1)], por[("CHICA-2", 3)]
    assert (g1["k"], c3["k"]) == (1, 3) and c3["instalada"] >= req["requerida"]
    A = S.disponibilidad(300, 6)
    assert g1["A_etapa"] == pytest.approx(A) and c3["A_etapa"] == pytest.approx(A ** 3)            # 3 de 3: todas deben operar
    assert por[("CHICA-2", 4)]["A_etapa"] == pytest.approx(S.k_de_n(A, 4, 3)) and por[("CHICA-2", 4)]["A_etapa"] > c3["A_etapa"]
    assert g1["inversion_clp"] < c3["inversion_clp"]                                                  # 100.000 contra 3 × 40.000
    assert g1["area_total_m2"] == pytest.approx((4.0 + 1.5) * (2.2 + 1.5))
    assert c3["area_total_m2"] == pytest.approx(3 * (2.5 + 1.5) * (1.5 + 1.5)) and c3["area_total_m2"] > g1["area_total_m2"]
    assert g1["potencia_operando_kw"] == pytest.approx(300.0 * min(1.0, req["carga_t_h"] / g1["capacidad_modelo_t_h"]))
    assert c3["potencia_operando_kw"] == pytest.approx(3 * 110.0 * min(1.0, req["carga_t_h"] / (3 * c3["capacidad_modelo_t_h"])))
    assert g1["costo_energia_clp"] == pytest.approx(g1["energia_kwh_anio"] * S.PRECIO_KWH)
    assert g1["total_con_energia_clp"] == pytest.approx(g1["total_clp"] + g1["costo_energia_clp"])
    gc = r["grande_chicas"]
    assert gc["grande"]["modelo"] == "GRANDE-6" and gc["chicas"]["modelo"] == "CHICA-2" and gc["chicas"]["k"] >= 2
    assert gc["ganadores"]["costo"] == "grande" and gc["ganadores"]["area"] == "grande" and gc["ganadores"]["disp"] == "grande"
    assert r["recomendacion"]["recomendada"] in r["alternativas"] and {"costo", "disponibilidad", "espacio", "energia", "total"} <= set(r["mejores"])


def test_recomendacion_respeta_el_area_maxima_y_la_disponibilidad_minima():
    pl, req, filas = _req_y_fichas()
    P = S.parametros(pl); ref = S.referencias_equipo(pl, "A1")
    libre = S.comparar_combinaciones(req, filas, P, ref)
    chico = S.comparar_combinaciones(req, filas, P, ref, area_max=25.0)
    assert all(a["area_total_m2"] <= 25.0 for a in chico["recomendacion"]["candidatas"]) and chico["recomendacion"]["candidatas"]
    assert chico["recomendacion"]["recomendada"]["total_con_energia_clp"] >= libre["recomendacion"]["recomendada"]["total_con_energia_clp"] - 1e-6
    disp = S.comparar_combinaciones(req, filas, P, ref, disp_min=0.99)
    assert disp["recomendacion"]["recomendada"] is None or disp["recomendacion"]["recomendada"]["A_etapa"] >= 0.99
    nada = S.comparar_combinaciones(req, filas, P, ref, area_max=1.0)
    assert nada["recomendacion"]["recomendada"] is None and "Ninguna combinación" in nada["recomendacion"]["motivo"]


def test_sin_ficha_con_dimensiones_ni_potencia_el_espacio_y_la_energia_se_escalan_desde_la_planta():
    pl = pellet.crear()
    req = next(r for r in S.requerimientos(pl) if r["equipo"] == "A1")
    ref = S.referencias_equipo(pl, "A1")
    assert ref["area_m2"] > 0 and ref["potencia_kw"] > 0
    f = FI.extraer_ficha(f"Model: SIN-DIM. Capacity: {req['requerida'] + 0.05:.2f} t/h. Price: US$ 80,000", "pelletizadora", "u", HOY, "", "t/h")
    filas, _ = FI.filas_de_fichas([f], "t/h", "pelletizadora")
    a = next(x for x in S.comparar_combinaciones(req, filas, S.parametros(pl), ref, redundancia=False)["alternativas"] if x["n"] == 1)
    razon = a["capacidad_modelo"] / req["requerida"]             # lados con la capacidad a la 1/3; potencia proporcional
    assert a["area_unidad_m2"] == pytest.approx((ref["largo"] * razon ** (1 / 3) + 1.5) * (ref["ancho"] * razon ** (1 / 3) + 1.5)) and "Supuesto" in a["fuente_area"]
    assert a["potencia_unidad_kw"] == pytest.approx(ref["potencia_kw"] * razon) and "Supuesto" in a["fuente_potencia"]
    sin = S.comparar_combinaciones(req, filas, S.parametros(pl), dict(largo=None, ancho=None, area_m2=None, potencia_kw=None))
    assert sin["avisos"] and a["area_total_m2"] is not None


def test_aplicar_la_combinacion_elegida_deja_el_modelo_en_la_planta():
    pl, req, filas = _req_y_fichas()
    r = S.comparar_combinaciones(req, filas, S.parametros(pl), S.referencias_equipo(pl, "A1"))
    a = next(x for x in r["alternativas"] if x["modelo"] == "CHICA-2" and x["n"] == 3)
    assert S.aplicar(pl, {"A1": a}) == 1
    eq = pl.equipos["A1"]
    assert eq.v("modelo") == "CHICA-2" and eq.v("unidades") == 3 and eq.v("unidades_requeridas") == 3
    assert eq.v("mtbf_h") == pytest.approx(300.0) and eq.v("mttr_h") == pytest.approx(6.0)
    it = next(i for i in CO.lista_equipos(pl, X={}) if i["equipo"] == "A1")
    assert it["unidades"] == 3


def test_seleccionar_con_fichas_suma_o_reemplaza_el_catalogo_y_sin_fichas_queda_igual():
    pl, req, filas = _req_y_fichas()
    base = S.seleccionar(pl, CAT)
    assert S.seleccionar(pl, CAT, fichas=None)["etapas"][0]["alternativas"] == base["etapas"][0]["alternativas"]
    mezcla = S.seleccionar(pl, CAT, fichas={"A1": filas})
    solo = S.seleccionar(pl, CAT, fichas={"A1": filas}, solo_fichas={"A1"})
    e0 = next(e for e in base["etapas"] if e["equipo"] == "A1"); em = next(e for e in mezcla["etapas"] if e["equipo"] == "A1")
    es = next(e for e in solo["etapas"] if e["equipo"] == "A1")
    assert len(em["alternativas"]) == len(e0["alternativas"]) + 4 and em["n_fichas"] == 2
    assert {a["modelo"] for a in es["alternativas"]} == {"GRANDE-6", "CHICA-2"} and es["recomendada"]["modelo"] in ("GRANDE-6", "CHICA-2")
    otro = next(e for e in solo["etapas"] if e["equipo"] != "A1")
    assert otro["n_fichas"] == 0 and len(otro["alternativas"]) == len(next(e for e in base["etapas"] if e["equipo"] == otro["equipo"])["alternativas"])


def test_comparacion_en_los_cuatro_rubros_con_el_catalogo_supuesto_como_fichas():
    for m in (agrozzi, pellet):
        pl = m.crear(); P = S.parametros(pl)
        for req in S.requerimientos(pl)[:3]:
            filas = S.filas_catalogo(req, CAT)
            r = S.comparar_combinaciones(req, filas, P, S.referencias_equipo(pl, req["equipo"]))
            assert r["alternativas"] and r["recomendacion"]["recomendada"] is not None
            assert all(a["total_con_energia_clp"] >= a["total_clp"] for a in r["alternativas"])
