"""PAT 139: elección de equipos por costo total C = C_inv + C_op + C_inef (motor/costo_total.py y su integración en seleccion.py).

Incluye el ejemplo del profesor Torres (hoja manuscrita del 14-11-2026): etapa que pide 200 u/h, opción a de 3 × 70 u a 200 US$
cada una (se necesitan los 3, A_sist ≈ 93 %), opción b de 1 × 300 u a 300 US$ (A ≈ 97 %, opera a 200/300 bajo su peak de η) y opción c
de 200 u con el precio de Williams ajustado con las otras dos."""
import math
import sys
import types
import pytest
from pat_sim.datos import mantenedor as M
from pat_sim.escenarios import agrozzi, pellet
from pat_sim.motor import costo_total as CT, seleccion as S, desafio as D, sintesis as SI

CAT = M.semilla_catalogo_comercial()


# ---------------------------------------------------------------- disponibilidad de un equipo
def test_disponibilidad_equipo_formula_del_profesor():
    assert CT.disponibilidad_equipo(90, 10, 0.0) == pytest.approx(0.90)
    assert CT.disponibilidad_equipo(90, 10, 0.02) == pytest.approx(1 - (0.10 + 0.02))
    assert CT.disponibilidad_equipo(90, 10) == pytest.approx(0.88)                   # t_MP por omisión: Supuesto de 2 %
    assert CT.T_MP == pytest.approx(0.02) and "Supuesto" in CT.SUPUESTOS["t_mp"].justificacion
    assert CT.disponibilidad_equipo(1000, 0, 0.0) == 1.0
    assert CT.disponibilidad_equipo(10, 10, 0.9) == 0.0                              # acotada a [0, 1]
    assert CT.disponibilidad_equipo(1e9, 0.0, 0.0) <= 1.0


@pytest.mark.parametrize("mtbf,mttr,t", [(None, 5, 0.0), (5, None, 0.0), (0, 5, 0.0), (-3, 5, 0.0), (10, -1, 0.0), (10, 1, -0.1)])
def test_disponibilidad_equipo_datos_malos_avisan(mtbf, mttr, t):
    with pytest.raises(ValueError):
        CT.disponibilidad_equipo(mtbf, mttr, t)


# ---------------------------------------------------------------- curva de eficiencia
def test_curva_parabolica_con_maximo_en_el_peak():
    assert CT.curva_eficiencia(100, 100, 0.8) == pytest.approx(0.8)
    a = CT.A_CURVA
    assert CT.curva_eficiencia(50, 100, 0.8) == pytest.approx(0.8 * (1 - a * 0.25))
    assert CT.curva_eficiencia(150, 100, 0.8) == pytest.approx(CT.curva_eficiencia(50, 100, 0.8))     # simétrica
    assert CT.curva_eficiencia(2 / 3 * 300, 300) == pytest.approx(1 - a * (1 / 3) ** 2)
    assert CT.eta_relativa(50, 100) == pytest.approx(1 - a * 0.25)
    assert CT.eta_relativa(100, 100) == 1.0
    assert "Supuesto" in CT.SUPUESTOS["a_curva"].justificacion and "https://" in CT.SUPUESTOS["a_curva"].justificacion


def test_eta_nunca_negativa_ni_sobre_el_maximo():
    for q in (0, 1e-9, 0.1, 1, 5, 100, 1e6, -5):
        for a in (None, 0.0, 0.6, 5.0, 100.0):
            e = CT.curva_eficiencia(q, 10.0, 0.9, a)
            assert 0 < e <= 0.9 + 1e-12
            r = CT.eta_relativa(q, 10.0, a)
            assert CT.ETA_MIN_REL - 1e-12 <= r <= 1.0 + 1e-12
    assert CT.curva_eficiencia(1e6, 10.0, 0.9) == pytest.approx(CT.ETA_MIN_REL * 0.9)                   # el piso
    assert CT.curva_eficiencia(1e6, 10.0, 0.9, eta_min=0.5) == pytest.approx(0.5)
    assert CT.curva_eficiencia(7, 10.0, 0.9, a=0.0) == pytest.approx(0.9)                                # sin caída
    with pytest.raises(ValueError):
        CT.curva_eficiencia(1, 0.0)
    with pytest.raises(ValueError):
        CT.curva_eficiencia(1, 10.0, eta_max=0.0)


def test_curva_se_ajusta_a_los_puntos_de_una_ficha():
    verdad = lambda q: 0.82 * (1 - 0.9 * (q / 40.0 - 1) ** 2)
    pts = [(q, verdad(q)) for q in (10, 20, 30, 40, 50, 60)]
    aj = CT.ajustar_curva(pts)
    assert aj["q_peak"] == pytest.approx(40.0) and aj["eta_max"] == pytest.approx(0.82) and aj["a"] == pytest.approx(0.9) and aj["r2"] == pytest.approx(1.0)
    assert CT.curva_eficiencia(25, 999, 9.9, puntos=pts) == pytest.approx(verdad(25))                   # con puntos mandan los puntos
    assert CT.eta_relativa(25, 999, puntos=pts) == pytest.approx(verdad(25) / 0.82)
    # dos puntos: peak y máximo del mejor punto, a por mínimos cuadrados
    dos = CT.ajustar_curva([(40, 0.82), (20, verdad(20))])
    assert dos["q_peak"] == 40 and dos["a"] == pytest.approx(0.9)
    # un solo punto: queda el Supuesto
    uno = CT.ajustar_curva([(40, 0.82)])
    assert uno["a"] == CT.A_CURVA and uno["q_peak"] == 40 and "Supuesto" in uno["metodo"]
    with pytest.raises(ValueError):
        CT.ajustar_curva([])
    with pytest.raises(ValueError):
        CT.ajustar_curva([(10, -1), ("x", 2)])


def test_exponente_de_williams_con_las_referencias():
    r = CT.exponente_williams([(70, 200), (300, 300)])
    assert r["n"] == pytest.approx(math.log(1.5) / math.log(300 / 70)) and r["C1"] == pytest.approx(200.0) and r["S1"] == 70
    r3 = CT.exponente_williams([(1, 10), (10, 10 * 10 ** 0.6), (100, 10 * 100 ** 0.6)])
    assert r3["n"] == pytest.approx(0.6) and r3["r2"] == pytest.approx(1.0)
    assert CT.exponente_williams([(5, 100)])["n"] == pytest.approx(0.6)                                  # seis décimos


# ---------------------------------------------------------------- ejemplo del profesor Torres
ECO = dict(dolar=1.0, tasa=0.10, anios=20, f_inst=2.5, precio_kwh=0.01, valor_unitario_usd=0.01, mantencion_pct=6.0)
REQ, HORAS, KW_POR_U = 200.0, 500.0, 0.1


def _mtbf_para(A_eq, mttr, t_mp):
    """MTBF con el que un equipo de ese MTTR y t_MP tiene la disponibilidad A_eq (fórmula del profesor)."""
    falla = 1.0 - A_eq - t_mp
    return mttr * (1.0 / falla - 1.0)


def _opcion_a():
    A_eq = 0.93 ** (1 / 3)
    return dict(modelo="a: 3 × 70 u", n=3, capacidad=70.0, precio_usd=200.0, potencia_kw=70 * KW_POR_U, mtbf_h=_mtbf_para(A_eq, 8.0, 0.02), mttr_h=8.0,
                t_mp_frac=0.02)


def _opcion_b():
    return dict(modelo="b: 1 × 300 u", n=1, capacidad=300.0, precio_usd=300.0, potencia_kw=300 * KW_POR_U, mtbf_h=_mtbf_para(0.97, 8.0, 0.02), mttr_h=8.0,
                t_mp_frac=0.02)


def _opcion_c():
    w = CT.exponente_williams([(70, 200.0), (300, 300.0)])               # Williams con las referencias de a y b
    precio = 200.0 * (200.0 / 70.0) ** w["n"]
    return dict(modelo="c: 1 × 200 u (Williams)", n=1, capacidad=200.0, precio_usd=precio, potencia_kw=200 * KW_POR_U, mtbf_h=_mtbf_para(0.97, 8.0, 0.02),
                mttr_h=8.0, t_mp_frac=0.02), w


def test_ejemplo_del_profesor_reproduce_93_y_97_por_ciento():
    a = CT.costo_total_opcion(_opcion_a(), REQ, HORAS, ECO)
    b = CT.costo_total_opcion(_opcion_b(), REQ, HORAS, ECO)
    assert (a["k"], a["n"]) == (3, 3) and (b["k"], b["n"]) == (1, 1)
    assert a["A"] == pytest.approx(0.93, abs=0.005)                       # se necesitan los 3: A_etapa = A_equipo³
    assert a["A"] == pytest.approx(a["A_equipo"] ** 3)
    assert b["A"] == pytest.approx(0.97, abs=0.005)
    assert a["A_equipo"] == pytest.approx(CT.disponibilidad_equipo(a["detalle"]["mtbf_h"], 8.0, 0.02))
    # la etapa k de n sale de seleccion.k_de_n
    assert a["A"] == pytest.approx(S.k_de_n(a["A_equipo"], 3, 3))


def test_ejemplo_del_profesor_componentes_de_c():
    a = CT.costo_total_opcion(_opcion_a(), REQ, HORAS, ECO)
    b = CT.costo_total_opcion(_opcion_b(), REQ, HORAS, ECO)
    crf = S.crf(0.10, 20)
    # C_inv = precio × n × factor de instalación × CRF (600 US$ contra 300 US$)
    assert a["C_inv"] == pytest.approx(600.0 * 2.5 * crf) and b["C_inv"] == pytest.approx(300.0 * 2.5 * crf)
    assert a["C_inv"] > b["C_inv"]                                         # a tiene mayor C_inv
    # C_inef = (1 − A_sist) × producción anual × valor unitario: b, más disponible, pierde menos
    prod = REQ * HORAS
    assert a["C_inef"] == pytest.approx((1 - a["A"]) * prod * 0.01) and b["C_inef"] == pytest.approx((1 - b["A"]) * prod * 0.01)
    assert b["C_inef"] < a["C_inef"]                                       # b tiene menor C_inef
    # b opera a 200/300 del peak: η menor y más energía por la misma producción
    assert b["q_unidad"] == pytest.approx(200.0) and b["eta_relativa"] == pytest.approx(1 - CT.A_CURVA * (1 / 3) ** 2)
    assert a["q_unidad"] == pytest.approx(200.0 / 3) and a["eta_relativa"] > b["eta_relativa"] > 0.9
    ea, eb = a["detalle"], b["detalle"]
    assert ea["energia_kwh_anio_sin_curva"] == pytest.approx(eb["energia_kwh_anio_sin_curva"])      # misma carga: 20 kW
    assert eb["energia_kwh_anio"] > ea["energia_kwh_anio"] and eb["energia_usd"] > ea["energia_usd"]
    assert eb["energia_kwh_anio"] == pytest.approx(eb["energia_kwh_anio_sin_curva"] / b["eta_relativa"])
    # C_op = energía + mantenimiento (6 % del capital fijo); C = suma de las tres
    assert a["C_op"] == pytest.approx(ea["energia_usd"] + 0.06 * 600.0 * 2.5)
    for r in (a, b):
        assert r["C"] == pytest.approx(r["C_inv"] + r["C_op"] + r["C_inef"]) and r["C_clp"] == pytest.approx(r["C"])      # dólar = 1
        assert r["fuentes"] and r["moneda"] == "US$/año" and not r["avisos"]


def test_ejemplo_del_profesor_opcion_c_con_williams():
    c_op, w = _opcion_c()
    assert w["n"] == pytest.approx(0.2787, abs=1e-3)                                        # exponente ajustado con las dos referencias
    assert 200.0 < c_op["precio_usd"] < 300.0 and c_op["precio_usd"] == pytest.approx(300.0 * (200 / 300) ** w["n"])
    a = CT.costo_total_opcion(_opcion_a(), REQ, HORAS, ECO)
    b = CT.costo_total_opcion(_opcion_b(), REQ, HORAS, ECO)
    c = CT.costo_total_opcion(c_op, REQ, HORAS, ECO)
    assert (c["k"], c["n"]) == (1, 1) and c["eta_relativa"] == pytest.approx(1.0)           # justo en su peak
    assert c["detalle"]["energia_kwh_anio"] == pytest.approx(c["detalle"]["energia_kwh_anio_sin_curva"])
    assert c["C_inv"] < b["C_inv"] and c["C_inv"] < a["C_inv"]
    assert c["C_inef"] == pytest.approx(b["C_inef"], rel=0.01) and c["C_inef"] < a["C_inef"]
    assert c["C"] < b["C"] < a["C"] or c["C"] < a["C"]                                      # la que calza con la etapa gana


def test_ejemplo_del_profesor_se_elige_la_de_menor_c():
    ops = {"a": _opcion_a(), "b": _opcion_b(), "c": _opcion_c()[0]}
    res = {k: CT.costo_total_opcion(o, REQ, HORAS, ECO) for k, o in ops.items()}
    mejor = min(res, key=lambda k: res[k]["C"])
    assert res[mejor]["C"] == min(r["C"] for r in res.values()) and mejor in ("b", "c")
    # con redundancia la opción b (n = 2, k = 1) gana disponibilidad: A = 1 − (1 − A)²
    b2 = CT.costo_total_opcion(dict(_opcion_b(), n=2), REQ, HORAS, ECO)
    assert b2["A"] == pytest.approx(1 - (1 - res["b"]["A_equipo"]) ** 2) and b2["C_inef"] < res["b"]["C_inef"] and b2["C_inv"] == pytest.approx(2 * res["b"]["C_inv"])


def test_disponibilidad_dada_manda_sobre_mtbf_y_mttr():
    r = CT.costo_total_opcion(dict(n=3, capacidad=70.0, precio_usd=200.0, A_equipo=0.93 ** (1 / 3)), REQ, HORAS, ECO)
    assert r["A"] == pytest.approx(0.93) and not any("MTBF" in a for a in r["avisos"])


# ---------------------------------------------------------------- bordes de costo_total_opcion
def test_requerida_cero_no_pierde_produccion_ni_gasta_energia():
    r = CT.costo_total_opcion(dict(n=1, capacidad=10.0, precio_usd=1000.0, potencia_kw=5.0, mtbf_h=100, mttr_h=5), 0.0, 1000.0, ECO)
    assert r["k"] == 0 and r["A"] == 1.0 and r["C_inef"] == 0.0 and r["detalle"]["energia_kwh_anio"] == 0.0
    assert r["C_inv"] > 0 and r["C"] == pytest.approx(r["C_inv"] + r["C_op"]) and r["eta"] > 0


def test_sin_equipos_n_cero():
    r = CT.costo_total_opcion(dict(n=0, capacidad=10.0, precio_usd=1000.0), 25.0, 1000.0, ECO)
    assert r["A"] == 0.0 and r["C_inv"] == 0.0 and r["C_inef"] == pytest.approx(25.0 * 1000.0 * 0.01) and r["avisos"]
    assert CT.costo_total_opcion(dict(n=0, capacidad=10.0, precio_usd=1000.0), 0.0, 1000.0, ECO)["A"] == 1.0


def test_mtbf_faltante_usa_el_supuesto_por_tipo_y_avisa():
    r = CT.costo_total_opcion(dict(n=1, capacidad=10.0, precio_usd=1000.0, tipo="trituradora"), 8.0, 1000.0, ECO)
    mtbf, mttr = CT.LF.FALLAS_TIPO[CT.LF.categoria("trituradora")]
    assert r["A_equipo"] == pytest.approx(CT.disponibilidad_equipo(mtbf, mttr, CT.T_MP))
    assert any("MTBF" in a for a in r["avisos"]) and any("Supuesto" in f["fuente"] for f in r["fuentes"] if f["concepto"] == "Disponibilidad")
    r2 = CT.costo_total_opcion(dict(n=1, capacidad=10.0, precio_usd=1000.0, mtbf_h=None, mttr_h=3.0), 8.0, 1000.0, ECO)
    assert any("MTBF" in a for a in r2["avisos"]) and 0 < r2["A"] < 1


def test_sin_potencia_avisa_y_sin_horas_usa_el_supuesto():
    r = CT.costo_total_opcion(dict(n=1, capacidad=10.0, precio_usd=1000.0, mtbf_h=100, mttr_h=2), 8.0, None, ECO)
    assert r["detalle"]["energia_usd"] == 0.0 and r["detalle"]["horas"] == S.SUPUESTOS["horas"].valor
    assert any("potencia" in a for a in r["avisos"]) and any("horas" in a for a in r["avisos"])


def test_datos_obligatorios_y_k_insuficiente():
    with pytest.raises(ValueError):
        CT.costo_total_opcion(dict(n=1, precio_usd=10.0), 5.0, 100.0, ECO)               # sin capacidad
    with pytest.raises(ValueError):
        CT.costo_total_opcion(dict(n=1, capacidad=10.0), 5.0, 100.0, ECO)                # sin precio
    r = CT.costo_total_opcion(dict(n=2, k=1, capacidad=10.0, precio_usd=100.0, A_equipo=0.9), 25.0, 100.0, ECO)
    assert r["k"] == 3 and r["A"] == 0.0 and r["avisos"]                                 # k sube a ⌈25/10⌉ y con n = 2 no alcanza
    r = CT.costo_total_opcion(dict(n=1, capacidad=10.0, precio_usd=100.0, A_equipo=0.9), 10.0, 100.0, ECO)
    assert r["k"] == 1 and r["q_unidad"] == pytest.approx(10.0) and r["eta_relativa"] == pytest.approx(1.0)


def test_eta_nunca_negativa_en_una_opcion_sobredimensionada():
    r = CT.costo_total_opcion(dict(n=1, capacidad=1e6, precio_usd=100.0, potencia_kw=1.0, A_equipo=0.9), 1e-3, 100.0, ECO)
    assert r["eta"] > 0 and r["eta_relativa"] >= CT.ETA_MIN_REL - 1e-12 and r["C_op"] >= 0


def test_la_curva_de_la_ficha_cambia_el_costo_de_operar():
    base = dict(n=1, capacidad=300.0, precio_usd=300.0, potencia_kw=30.0, A_equipo=0.97)
    suave = CT.costo_total_opcion(dict(base, a_curva=0.0), REQ, HORAS, ECO)
    fuerte = CT.costo_total_opcion(dict(base, a_curva=1.5), REQ, HORAS, ECO)
    assert suave["eta_relativa"] == 1.0 and fuerte["eta_relativa"] < 1.0 and fuerte["C_op"] > suave["C_op"]
    pts = [(100, 0.6), (200, 0.8), (300, 0.9), (400, 0.8)]
    ficha = CT.costo_total_opcion(dict(base, puntos_eta=pts), REQ, HORAS, ECO)
    assert 0 < ficha["eta"] <= 0.9 + 1e-9 and "ficha" in " ".join(f["fuente"] for f in ficha["fuentes"] if f["concepto"] == "Curva de eficiencia")


# ---------------------------------------------------------------- candidatos y mejor opción
def _planta_vacia():
    return D.planta_vacia(dict(titulo="V", enunciado="diseñar", producto="X", rubro="pellet",
                               demanda=dict(periodo="mes", unidad="t", valores=[1], fuente="Supuesto"), precios=[]))


def test_planta_vacia_y_equipo_inexistente_dan_lista_vacia_con_aviso():
    pl = _planta_vacia()
    r = CT.candidatos_con_avisos(pl, "A1", buscar_en_linea=False)
    assert r["candidatos"] == [] and r["avisos"] and CT.candidatos_etapa(pl, "A1", buscar_en_linea=False) == []
    assert CT.mejor_opcion(pl, "A1", buscar_en_linea=False) is None
    assert CT.candidatos_etapa(None, "A1") == [] and CT.mejor_opcion(None, "A1") is None
    assert CT.mejor_opcion(pellet.crear(), "NO_EXISTE", buscar_en_linea=False) is None


CLAVES_CONTRATO = {"id", "modelo", "fabricante", "n", "k", "capacidad", "unidad", "precio_usd", "origen", "C_inv", "C_op", "C_inef", "C", "A",
                   "eta_operacion", "url", "fuente"}


def test_candidatos_ordenados_por_c_con_las_claves_del_contrato():
    pl = pellet.crear()
    cands = CT.candidatos_etapa(pl, "A1", buscar_en_linea=False)
    assert cands and all(CLAVES_CONTRATO <= set(c) for c in cands)
    cs = [c["C"] for c in cands]
    assert cs == sorted(cs)
    assert all(c["origen"] in ("Tavily", "Respaldo", "Williams") for c in cands)
    assert all(c["C"] == pytest.approx(c["C_inv"] + c["C_op"] + c["C_inef"]) and 0 < c["A"] <= 1 and 0 < c["eta_operacion"] <= 1 for c in cands)
    assert all(c["n"] in (c["k"], c["k"] + 1) for c in cands) and any(c["n"] == c["k"] + 1 for c in cands)
    mejor = CT.mejor_opcion(pl, "A1", buscar_en_linea=False)
    assert mejor["id"] == cands[0]["id"] and mejor["C"] == min(cs)
    req = next(r for r in S.requerimientos(pl) if r["equipo"] == "A1")
    assert all(c["k"] * c["capacidad"] >= req["requerida"] - 1e-9 for c in cands)


def test_candidatos_coinciden_con_seleccionar_y_se_pueden_aplicar():
    pl = pellet.crear()
    cands = CT.candidatos_etapa(pl, "A1", buscar_en_linea=False)
    e = next(x for x in S.seleccionar(pl, CAT)["etapas"] if x["equipo"] == "A1")
    por = {(a["modelo"], a["n"]): a for a in e["alternativas"]}
    for c in cands:
        if (c["modelo"], c["n"]) in por:                       # mismo catálogo: mismas cifras
            assert c["C_clp"] == pytest.approx(por[(c["modelo"], c["n"])]["C_clp"])
    assert S.aplicar(pl, {"A1": cands[0]}) == 1 and pl.equipos["A1"].v("unidades") == cands[0]["n"]


def test_candidatos_con_el_modulo_de_referencia_de_e2(monkeypatch):
    llamadas = []

    def candidatos(tipo, capacidad_requerida, unidad, en_linea=True, secretos=None):
        llamadas.append((tipo, round(capacidad_requerida, 3), unidad, en_linea))
        return [dict(modelo="Pelletizadora X", fabricante="Fab SA", capacidad=3.0, unidad=unidad, precio_usd=50000.0, origen="Tavily", url="https://x.test/a",
                     fuente="Fab SA, consultado el 14-11-2026", mtbf_h=400.0, mttr_h=8.0, potencia_kw=90.0),
                dict(modelo="Pelletizadora Y", capacidad=6.0, unidad=unidad, precio_usd=None, origen="Williams"),
                dict(modelo="Malo", capacidad=None), dict(modelo="Otra unidad", capacidad=5.0, unidad="kg/h", precio_usd=1.0)]
    modulo = types.ModuleType("pat_sim.datos.referencia_equipos"); modulo.candidatos = candidatos
    monkeypatch.setitem(sys.modules, "pat_sim.datos.referencia_equipos", modulo)
    import pat_sim.datos as PD
    monkeypatch.setattr(PD, "referencia_equipos", modulo, raising=False)
    pl = pellet.crear()
    r = CT.candidatos_con_avisos(pl, "A1", buscar_en_linea=False)
    assert r["origen_candidatos"] == "referencia_equipos" and llamadas == [("pelletizadora", 5.155, "t/h", False)]
    modelos = {c["modelo"] for c in r["candidatos"]}
    assert modelos == {"Pelletizadora X", "Pelletizadora Y"}                                 # sin capacidad o en otra unidad: descartadas
    x = next(c for c in r["candidatos"] if c["modelo"] == "Pelletizadora X" and c["n"] == 2)
    assert x["origen"] == "Tavily" and x["url"] == "https://x.test/a" and x["fabricante"] == "Fab SA" and x["precio_usd"] == pytest.approx(50000.0)
    assert x["potencia_unidad_kw"] == 90.0 and x["mtbf_h"] == 400.0
    y = next(c for c in r["candidatos"] if c["modelo"] == "Pelletizadora Y")
    assert y["origen"] == "Williams" and y["precio_usd"] > 0                                   # sin precio: Williams con la referencia de costeo
    assert CT.mejor_opcion(pl, "A1", buscar_en_linea=False)["C"] == min(c["C"] for c in r["candidatos"])


def test_si_el_modulo_de_referencia_falla_se_usa_el_catalogo(monkeypatch):
    def candidatos(*a, **k):
        raise RuntimeError("sin red")
    modulo = types.ModuleType("pat_sim.datos.referencia_equipos"); modulo.candidatos = candidatos
    monkeypatch.setitem(sys.modules, "pat_sim.datos.referencia_equipos", modulo)
    import pat_sim.datos as PD
    monkeypatch.setattr(PD, "referencia_equipos", modulo, raising=False)
    r = CT.candidatos_con_avisos(pellet.crear(), "A1", buscar_en_linea=True)
    assert r["origen_candidatos"] == "catálogo comercial" and r["candidatos"] and any("respaldo" in a for a in r["avisos"])


# ---------------------------------------------------------------- integración en seleccion.py
def test_seleccionar_elige_por_c_y_conserva_las_claves_de_siempre():
    for m in (agrozzi, pellet):
        pl = m.crear(); r = S.seleccionar(pl, CAT)
        for e in r["etapas"]:
            base = [a for a in e["alternativas"] if not a["redundante"]]
            assert e["mejor"]["C_clp"] == min(a["C_clp"] for a in base)
            recomendada = e["recomendada"]
            con = next((a for a in e["alternativas"] if a["redundante"] and a["modelo"] == e["mejor"]["modelo"]), None)
            if con is not None:
                assert recomendada["C_clp"] == pytest.approx(min(e["mejor"]["C_clp"], con["C_clp"]))     # la reserva conviene solo si baja C
            for a in e["alternativas"]:
                assert {"total_clp", "anual_clp", "ineficiencia_clp", "A_etapa", "etiqueta", "total_con_energia_clp"} <= set(a)
                assert {"C_inv", "C_op", "C_inef", "C", "C_clp", "A", "eta"} <= set(a)
                assert a["C_clp"] == pytest.approx(a["anual_clp"] + a["C_op_clp"] + a["ineficiencia_clp"])
                assert a["C_clp"] == pytest.approx(a["total_clp"] + a["costo_energia_clp"]) and a["total_con_energia_clp"] == pytest.approx(a["C_clp"])
                assert a["C_inv_clp"] == pytest.approx(a["anual_clp"]) and a["C_inef_clp"] == pytest.approx(a["ineficiencia_clp"])
                assert a["A"] <= a["A_etapa"] + 1e-12 and 0 < a["eta"] <= 1


def test_la_redundancia_se_recomienda_solo_si_baja_c():
    pl = agrozzi.crear(); r = S.seleccionar(pl, CAT)
    for e in r["etapas"]:
        d = e["redundancia"]
        if d is None:
            continue
        base = e["mejor"]; con = next(a for a in e["alternativas"] if a["redundante"] and a["modelo"] == base["modelo"])
        assert d["recomendar"] == (con["C_clp"] < base["C_clp"])
        assert d["neto_clp"] == pytest.approx(base["C_clp"] - con["C_clp"])


def test_la_sintesis_automatica_usa_el_mismo_criterio():
    pl = pellet.crear(); r = S.seleccionar(pl, CAT)
    et = {e["equipo"]: e for e in r["etapas"]}
    assert all(SI._costo_etapa(e) == pytest.approx(e["recomendada"]["C_clp"]) for e in et.values())
    assert SI._costo_etapa(None) == math.inf


def test_seleccionar_con_planta_vacia_no_falla():
    r = S.seleccionar(_planta_vacia(), CAT)
    assert r["etapas"] == [] and S.analizar_linea([])["cuello"] is None
