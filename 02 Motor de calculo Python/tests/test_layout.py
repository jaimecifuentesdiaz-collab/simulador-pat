"""Pruebas del layout de planta (PAT 135, T7.3): dimensiones, gancho a internet, geometría, flujos, CRAFT, modelo de lenguaje
con respuesta simulada (sin red), longitudes de cañería y dibujos SVG. Valores recalculados a mano."""
import io, json, os, sys
import pytest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from pat_sim.motor import layout as LY
from pat_sim.escenarios import agrozzi, pellet, chip, lena


@pytest.fixture(scope="module")
def pl():
    return agrozzi.crear().resolver()


def _dims(*lados):
    return {k: dict(largo=L, ancho=W, alto=H) for k, (L, W, H) in lados}


class _Eq:                                    # equipo mínimo para probar sin planta
    def __init__(self, simbolo, carga=None, nombre="Equipo"):
        self.simbolo = simbolo; self.nombre = nombre; self.tipo = "prueba"; self.params = {}
        self.resultado = type("R", (), dict(detalle=dict(carga_t_h=carga) if carga else {}, servicios={}))()


def test_familia_por_simbolo_y_prefijo(pl):
    assert LY.familia(pl.equipos["W2"]) == "evaporador" and LY.familia(pl.equipos["D1"]) == "caldera"
    assert LY.familia(_Eq("bomba_centrifuga")) == "bomba" and LY.familia(_Eq("valvula_control")) == "valvula"
    assert LY.familia(_Eq("bomba_vacio")) == "maquina_rotativa" and LY.familia(_Eq("desconocido")) == "general"


def test_tamano_carga_calor_y_potencia(pl):
    assert LY.tamano(pl.equipos["F1"])[1] == pytest.approx(pl.equipos["F1"].resultado.detalle["carga_t_h"])
    var, q, u = LY.tamano(pl.equipos["W1"]); assert var == "Q_kW" and u == "kW" and q == pytest.approx(pl.equipos["W1"].resultado.detalle["Q_kW"])
    var, mw, u = LY.tamano(pl.equipos["D1"]); assert u == "MW" and mw == pytest.approx(pl.equipos["D1"].resultado.detalle["Q_vapor_kW"] / 1000)
    assert LY.tamano(_Eq("tolva"))[1] is None


def test_dimensiones_escala_y_override():
    d = LY.dimensiones(_Eq("tolva", 200.0))           # 2 veces la referencia de 100 t/h: lados × 2^(1/3)
    k = 2 ** (1 / 3)
    assert d["largo"] == pytest.approx(8 * k) and d["ancho"] == pytest.approx(5 * k) and d["alto"] == pytest.approx(4 * k)
    assert d["categoria"] == "Supuesto" and d["tamano"] == 200.0
    d0 = LY.dimensiones(_Eq("tolva"))                  # sin tamaño: la referencia
    assert d0["largo"] == pytest.approx(8) and d0["tamano"] is None
    d1 = LY.dimensiones(_Eq("tolva", 1e6))             # el factor se topa en 2,5
    assert d1["largo"] == pytest.approx(8 * 2.5 ** (1 / 3))
    o = LY.dimensiones(_Eq("tolva", 100.0), dict(largo=3, alto=2, fuente="https://fabricante.cl/tolva"))
    assert o["largo"] == 3 and o["ancho"] == pytest.approx(5) and o["alto"] == 2 and o["categoria"] == "Internet"
    assert LY.dimensiones(_Eq("tolva"), (1, 1, 1))["categoria"] == "Usuario"


def test_dimensiones_planta_en_los_cuatro_rubros():
    for m in (agrozzi, pellet, chip, lena):
        p = m.crear().resolver(); d = LY.dimensiones_planta(p, {"B1": (2, 2, 2)})
        assert set(d) == set(p.equipos) and d["B1"]["largo"] == 2
        assert all(v["largo"] >= v["ancho"] > 0 and v["alto"] > 0 for k, v in d.items() if k != "B1")


def test_dimensiones_desde_texto():
    d = LY.dimensiones_desde_texto("Dimensions 2400 x 1200 x 1800 mm")
    assert d == dict(largo=pytest.approx(2.4), ancho=pytest.approx(1.2), alto=pytest.approx(1.8))
    assert LY.dimensiones_desde_texto("6,5 m × 2 × 3 m")["largo"] == pytest.approx(6.5)
    assert LY.dimensiones_desde_texto("sin medidas") is None


def test_buscar_dimensiones_web_con_cliente_simulado():
    class ConDim:
        @staticmethod
        def buscar_dimensiones(nombre, tipo, tam, unidad):
            return dict(largo=4, ancho=2, alto=3, fuente="https://ejemplo.cl")
    class ConBuscar:
        @staticmethod
        def buscar(consulta):
            return {"results": [{"content": "nada"}, {"content": "Size 3000 x 1500 x 2000 mm", "url": "https://f.cl/p"}]}
    class Falla:
        @staticmethod
        def buscar(consulta):
            raise RuntimeError("sin red")
    e = _Eq("tolva", 50.0, "Tolva")
    assert LY.buscar_dimensiones_web(e, ConDim)["largo"] == 4
    r = LY.buscar_dimensiones_web(e, ConBuscar)
    assert r["largo"] == pytest.approx(3) and r["fuente"] == "https://f.cl/p"
    assert LY.dimensiones(e, r)["categoria"] == "Internet"
    assert LY.buscar_dimensiones_web(e, Falla) is None
    LY.buscar_dimensiones_web(e)                     # sin el módulo de otro equipo devuelve None; con él, un dict o None


def test_huella_con_rotacion():
    d = dict(largo=4, ancho=2, alto=1)
    assert LY.huella([10, 5, 0], d) == (8, 4, 12, 6)
    assert LY.huella([10, 5, 90], d) == (9, 3, 11, 7) and LY.huella([10, 5, 450], d) == (9, 3, 11, 7)


def test_superposiciones_con_pasillo():
    dims = _dims(("a", (4, 2, 1)), ("b", (4, 2, 1)))
    assert LY.superposiciones({"a": [0, 0, 0], "b": [5.5, 0, 0]}, dims) == []          # separación 1,5 m: cumple
    assert LY.superposiciones({"a": [0, 0, 0], "b": [5.0, 0, 0]}, dims) == [("a", "b")]  # 1,0 m: no cumple
    assert LY.superposiciones({"a": [0, 0, 0], "b": [0, 3.4, 0]}, dims) == [("a", "b")]
    assert LY.superposiciones({"a": [0, 0, 0], "b": [5.0, 0, 0]}, dims, pasillo=1.0) == []


def test_puerto_gira_con_el_equipo():
    d = dict(largo=4, ancho=2, alto=6)
    assert LY.puerto([10, 5, 0], d, "sale") == pytest.approx((12, 5, 3))
    assert LY.puerto([10, 5, 0], d, "entra") == pytest.approx((8, 5, 3))
    assert LY.puerto([10, 5, 90], d, "sale") == pytest.approx((10, 7, 3))
    assert LY.puerto([10, 5, 0], d, "servicio") == pytest.approx((10, 6, 3))


def test_id_corriente_y_flujos(pl):
    fl = {f["id"]: f for f in LY.flujos(pl)}
    assert len(fl) == len(pl.conexiones) and LY.id_corriente(pl.conexiones[0]) == "1"
    assert fl["1"]["peso"] == pytest.approx(pl.salidas[("B1", "producto")].m / 1000) and fl["1"]["medio"] == "cañería"
    q = pl.equipos["W1"].resultado.servicios["vapor_kW"]
    assert fl["V1"]["servicio"] and fl["V1"]["peso"] == pytest.approx(q / LY.KW_POR_TH_VAPOR)
    fb = {f["id"]: f for f in LY.flujos(pellet.crear().resolver())}
    assert fb["1"]["medio"] == "transportador" and fb["Q1"]["medio"] == "ducto"


def test_costo_flujo_distancia():
    fl = [dict(origen="a", destino="b", peso=2.0), dict(origen="b", destino="c", peso=1.0)]
    assert LY.costo_flujo_distancia({"a": [0, 0, 0], "b": [3, 4, 0], "c": [3, 0, 0]}, fl) == pytest.approx(2 * 7 + 4)


def test_ancho_banda_y_colocar_secuencia():
    dims = _dims(("a", (4, 2, 1)), ("b", (4, 2, 1)), ("c", (4, 2, 1)))
    assert LY.ancho_banda(dims) == pytest.approx((3 * 3 * 5.5 * 3.5) ** 0.5)
    pos = LY.colocar_secuencia(["a", "b", "c"], dims, 1.5, banda=10)
    assert pos["a"] == [3.5, 2.5, 0] and pos["b"] == [9.0, 2.5, 0]       # fila 1 de oeste a este
    assert pos["c"] == [9.5, 6.0, 0]                                     # fila 2 de vuelta, desde el este
    assert LY.superposiciones(pos, dims) == []


def test_secuencia_inicial_deja_la_caldera_al_final(pl):
    s = LY.secuencia_inicial(pl)
    assert s[0] == "B1" and s[-1] == "D1" and sorted(s) == sorted(pl.equipos)


def test_craft_no_empeora_y_no_superpone():
    for m in (agrozzi, pellet, chip, lena):
        p = m.crear().resolver(); dims = LY.dimensiones_planta(p); r = LY.craft(p, dims)
        assert r["costo"] <= r["costo_inicial"] + 1e-9 and set(r["posiciones"]) == set(p.equipos)
        assert LY.superposiciones(r["posiciones"], dims) == [] and "Armour" in r["fuente"]
        assert all(v[0] > 0 and v[1] > 0 for v in r["posiciones"].values())


def test_prompt_layout(pl):
    dims = LY.dimensiones_planta(pl); t = LY.prompt_layout(pl, dims)
    assert '"posiciones"' in t and "W2" in t and "1.5 m" in t and "CRAFT" in t


def test_parsear_respuesta_llm():
    ids = ["a", "b"]
    assert LY.parsear_respuesta_llm('```json\n{"posiciones": {"a": [1, 2, 95], "b": {"x": 3, "y": 4}}}\n```', ids) == {"a": [1.0, 2.0, 90], "b": [3.0, 4.0, 0]}
    assert LY.parsear_respuesta_llm('Aquí va: [{"id": "a", "x": 1, "y": 1}, {"id": "b", "x": 5, "y": 1, "rot": 180}]'.replace("[", '{"posiciones": [').replace("]", "]}"), ids)["b"] == [5.0, 1.0, 180]
    with pytest.raises(ValueError):
        LY.parsear_respuesta_llm('{"posiciones": {"a": [1, 2]}}', ids)
    with pytest.raises(ValueError):
        LY.parsear_respuesta_llm("no sé", ids)
    with pytest.raises(ValueError):
        LY.parsear_respuesta_llm('{"posiciones": {"a": ["x", 2], "b": [1, 1]}}', ids)


class _Resp(io.BytesIO):
    pass


def _abrir_simulado(texto, registro=None):
    def abrir(req, timeout=None):
        if registro is not None:
            registro.append(req)
        return _Resp(json.dumps({"type": "message", "content": [{"type": "text", "text": texto}]}).encode("utf-8"))
    return abrir


def test_llamar_llm_con_respuesta_simulada():
    reg = []
    assert LY.llamar_llm("hola", "clave-falsa", "modelo-x", _abrir_simulado("respuesta", reg)) == "respuesta"
    req = reg[0]; cuerpo = json.loads(req.data.decode("utf-8"))
    assert req.full_url == LY.URL_API and req.get_header("X-api-key") == "clave-falsa"
    assert req.get_header("Anthropic-version") == LY.VERSION_API and cuerpo["model"] == "modelo-x"
    err = lambda req, timeout=None: _Resp(json.dumps({"type": "error", "error": {"message": "clave inválida"}}).encode())
    with pytest.raises(RuntimeError):
        LY.llamar_llm("hola", "x", None, err)


def test_proponer_layout_llm_simulado_y_respaldo(pl):
    dims = LY.dimensiones_planta(pl)
    base = LY.craft(pl, dims)["posiciones"]
    r = LY.proponer_layout(pl, dims, clave="k", abrir=_abrir_simulado(json.dumps({"posiciones": base})))
    assert r["metodo"].startswith("Modelo de lenguaje") and r["posiciones"] == {k: [float(v[0]), float(v[1]), 0] for k, v in base.items()}
    malo = {k: [10, 10, 0] for k in dims}                      # todos encima: se descarta y se usa CRAFT
    r2 = LY.proponer_layout(pl, dims, clave="k", abrir=_abrir_simulado(json.dumps({"posiciones": malo})))
    assert "CRAFT" in r2["metodo"] and r2["avisos"] and LY.superposiciones(r2["posiciones"], dims) == []
    r3 = LY.proponer_layout(pl, dims)                          # sin clave
    assert "CRAFT" in r3["metodo"] and not r3["avisos"]


def test_completar_posiciones():
    dims = _dims(("a", (4, 2, 1)), ("b", (2, 2, 1)), ("c", (2, 1, 1)))
    pos = LY.completar_posiciones({"a": [3.5, 2.5, 0], "z": [0, 0, 0]}, dims)
    assert "z" not in pos and pos["b"] == [5.5 + 1.5 + 1, 1.5 + 1, 0] and LY.superposiciones(pos, dims) == []


def test_diametros_desde_la_red_hidraulica(pl):
    D = LY.diametros(pl)
    assert D[("F2", "W2")] > 0 and ("D1", "W1") not in D
    assert LY.diametros(object()) == {}


def test_longitud_tramo_a_mano():
    t = LY.longitud_tramo((0, 0, 1), (10, 4, 2), h_rack=5, accesorios=0.2)
    assert t["horizontal"] == 14 and t["vertical"] == 7 and t["total"] == pytest.approx(21 * 1.2) and t["accesorios"] == pytest.approx(4.2)
    assert LY.longitud_tramo((0, 0, 1), (10, 4, 2), por_rack=False, accesorios=0)["total"] == pytest.approx(15)


def test_longitudes_y_longitudes_m(pl):
    dims = LY.dimensiones_planta(pl); pos = LY.craft(pl, dims)["posiciones"]
    filas = LY.longitudes(pl, pos, dims)
    assert len(filas) == len(pl.conexiones)
    f6 = next(f for f in filas if f["id"] == "6")
    p1 = LY.puerto(pos["F2"], dims["F2"], "sale"); p2 = LY.puerto(pos["W2"], dims["W2"], "entra")
    assert f6["total"] == pytest.approx(LY.longitud_tramo(p1, p2)["total"]) and f6["D_mm"] > 0
    assert next(f for f in filas if f["id"] == "V1")["D_mm"] is None
    lm = LY.longitudes_m(filas)
    assert set(lm) == {f["id"] for f in filas} and lm["6"] == round(f6["total"], 2)


def test_elevaciones_corte_y_plano_svg(pl):
    dims = LY.dimensiones_planta(pl); pos = LY.craft(pl, dims)["posiciones"]
    fr = LY.elevacion_svg(pos, dims, "frontal"); la = LY.elevacion_svg(pos, dims, "lateral")
    assert fr.startswith("<svg") and "desde el sur" in fr and "W2" in fr and "rack +5,00" in fr
    assert "desde el oeste" in la and la.count("<rect") > len(dims)
    yc = LY.corte_y_por_defecto(pos, dims)
    assert yc == pytest.approx(pos["W2"][1])                       # el equipo más alto es el evaporador W2
    co = LY.corte_svg(pos, dims)
    assert "url(#rayado)" in co and "Corte A-A" in co
    pla = LY.plano_svg(pos, dims, LY.flujos(pl), {k: e.nombre for k, e in pl.equipos.items()}, yc)
    assert ">N</text>" in pla and "10 m" in pla and "Hot break" in pla
    assert "sin equipos" in LY.elevacion_svg({}, {}) and LY.corte_y_por_defecto({}, {}) == 0.0


def test_estado_layout_en_los_cuatro_rubros():
    for m in (agrozzi, pellet, chip, lena):
        p = m.crear().resolver(); lay = LY.estado_layout(p)
        assert set(lay["posiciones"]) == set(p.equipos) and lay["superposiciones"] == []
        assert set(lay["longitudes_m"]) == {LY.id_corriente(c) for c in p.conexiones}
        assert all(v > 0 for v in lay["longitudes_m"].values()) and lay["propuesta"] == lay["posiciones"]
        lay2 = LY.estado_layout(p, dict(posiciones={"B1": [100, 100, 90]}))
        assert lay2["posiciones"]["B1"] == [100, 100, 90] and set(lay2["posiciones"]) == set(p.equipos)


# ------------------------------------------------------------------------------------------- red eléctrica (PAT 135, T15)
class _P:                                     # parámetro mínimo con .valor
    def __init__(self, v):
        self.valor = v


def test_potencia_electrica_resultado_detalle_y_parametro():
    e = _Eq("bomba_centrifuga"); e.resultado.servicios = dict(electricidad_kW=12.5)
    assert LY.potencia_electrica(e) == (12.5, "Resultado del equipo (servicio de electricidad)")
    e2 = _Eq("bomba_centrifuga"); e2.resultado.detalle = dict(W_kW=3.0)
    assert LY.potencia_electrica(e2)[0] == 3.0 and "punto de operación" in LY.potencia_electrica(e2)[1]
    e3 = _Eq("molino_martillos"); e3.params = {"potencia_kW": _P(45)}
    assert LY.potencia_electrica(e3) == (45.0, "Parámetro potencia_kW del equipo")
    assert LY.potencia_electrica(_Eq("tolva")) == (None, "")          # sin potencia: no lleva alimentador


def test_cargas_electricas_y_centro_de_carga(pl):
    dims = LY.dimensiones_planta(pl); pos = LY.craft(pl, dims)["posiciones"]
    cs = LY.cargas_electricas(pl, pos, dims)
    eqs = {c["equipo"] for c in cs}
    assert {"W2", "W3"} <= eqs and "B1" not in eqs                    # solo los equipos con potencia
    from pat_sim.motor.hidraulica import red_hidraulica
    n_bombas = sum(1 for ln in red_hidraulica(pl)["lineas"] if ln["bomba_diagrama"] is None and ln["potencia_kW"] > 0)
    assert len(cs) == 2 + n_bombas and all(c["id"] == "AL-" + c["equipo"] for c in cs)
    assert {c["equipo"] for c in LY.cargas_electricas(pl, pos, dims, bombas_linea=False)} == {"W2", "W3"}
    c = LY.centro_de_carga([dict(P_kW=1, x=0, y=0), dict(P_kW=3, x=4, y=8)])
    assert c == pytest.approx((3.0, 6.0)) and LY.centro_de_carga([]) is None


def test_posicion_ccm_libre_y_cercana():
    dims = _dims(("a", (4, 2, 1)))
    p = LY.posicion_ccm({"a": [10, 10, 0]}, dims, [dict(P_kW=1, x=10, y=10)])
    d = dict(dims, CCM=dict(LY.CCM_DIM))
    assert LY.superposiciones({"a": [10, 10, 0], "CCM": p}, d) == []
    assert abs(p[0] - 10) + abs(p[1] - 10) == pytest.approx(4.5)       # 1 + 1,5 + 2 m al norte o al sur
    q = LY.posicion_ccm({"a": [10, 10, 0]}, dims, [])                  # sin cargas: junto al centro de la planta
    assert LY.superposiciones({"a": [10, 10, 0], "CCM": q}, d) == []


def test_corriente_resistencia_y_caida_a_mano():
    assert LY.corriente_A(100, 380, 0.85) == pytest.approx(100000 / (3 ** 0.5 * 380 * 0.85))
    assert LY.resistencia_ohm_m(10, 20) == pytest.approx(0.0017241)
    assert LY.resistencia_ohm_m(10, 90) == pytest.approx(0.017241 * (1 + 0.00393 * 70) / 10)
    R = 0.017241 * (1 + 0.00393 * 70) / 10; X = 0.08e-3; sen = (1 - 0.85 ** 2) ** 0.5
    dU, pct = LY.caida_tension(100, 50, 10, 380, 0.85)
    assert dU == pytest.approx(3 ** 0.5 * 100 * 50 * (R * 0.85 + X * sen)) and pct == pytest.approx(100 * dU / 380)
    assert LY.caida_tension(100, 50, 10, paralelos=2)[0] == pytest.approx(dU / 2)


def test_seleccionar_seccion_capacidad_caida_y_paralelos():
    s = LY.seleccionar_seccion(100, 10)                 # diseño 125 A: 25 mm² (149 A)
    assert s["seccion_mm2"] == 25 and s["paralelos"] == 1 and s["criterio"] == "capacidad de corriente" and s["cumple"]
    s2 = LY.seleccionar_seccion(100, 300)               # 300 m: la caída obliga a 120 mm²
    assert s2["seccion_mm2"] == 120 and s2["criterio"] == "caída de tensión" and s2["dU_pct"] <= 3.0
    s3 = LY.seleccionar_seccion(1600, 10)               # diseño 2.000 A: tres de 300 mm² (3 × 741 A)
    assert s3["paralelos"] == 3 and s3["seccion_mm2"] == 300 and s3["capacidad_A"] == 3 * 741


def test_ruta_y_largo_de_cable_a_mano():
    r = LY.ruta_cable((0, 0, 0), (10, 4, 0), 4.0, 2.3, 0.5)
    assert r[0] == (0, 0, 2.3) and r[-1] == (10, 4, 0.5) and r[2] == (10, 0, 4.0)
    lg = LY.largo_cable(r, 0.15)
    assert lg["horizontal"] == pytest.approx(14) and lg["vertical"] == pytest.approx(1.7 + 3.5)
    assert lg["total"] == pytest.approx(19.2 * 1.15) and lg["holgura"] == pytest.approx(19.2 * 0.15)


def test_red_electrica_en_los_cuatro_rubros():
    for m in (agrozzi, pellet, chip, lena):
        p = m.crear().resolver(); dims = LY.dimensiones_planta(p); pos = LY.craft(p, dims)["posiciones"]
        r = LY.red_electrica(p, pos, dims)
        assert r["cables"] and r["cerca_ccm"] == [] and set(r["cables_m"]) == {c["id"] for c in r["cables"]}
        assert r["P_total_kW"] == pytest.approx(sum(c["P_kW"] for c in r["cables"]))
        assert all(c["dU_pct"] <= 3.0 and c["capacidad_A"] >= c["I_diseno_A"] for c in r["cables"])
        assert LY.superposiciones(dict(pos, CCM=r["ccm"]), dict(dims, CCM=r["ccm_dim"])) == []
        r2 = LY.red_electrica(p, pos, dims, ccm=[1, 2, 90])            # el usuario movió la sala eléctrica
        assert r2["ccm"] == [1.0, 2.0, 90] and r2["ccm_propuesta"] == r["ccm"]
    pa = agrozzi.crear().resolver(); d = LY.dimensiones_planta(pa); po = LY.craft(pa, d)["posiciones"]
    ra = LY.red_electrica(pa, po, d)
    assert any("media tensión" in a for a in ra["avisos"])             # W2 de 1 MW: aviso


def test_cables_m():
    assert LY.cables_m([dict(id="AL-A", total=12.345), dict(id="AL-B", total=1.0)]) == {"AL-A": 12.35, "AL-B": 1.0}


def test_dibujos_con_red_electrica(pl):
    lay = LY.estado_layout(pl)
    fr = LY.elevacion_svg(lay["posiciones"], lay["dims"], "frontal", red=lay["red"])
    la = LY.elevacion_svg(lay["posiciones"], lay["dims"], "lateral", red=lay["red"])
    assert "bandeja eléctrica +4,00" in fr and ">CCM</text>" in fr and 'stroke-dasharray="2 3"' in la
    pla = LY.plano_svg(lay["posiciones"], lay["dims"], lay["filas"], red=lay["red"])
    assert ">CCM</text>" in pla and pla.count("<polyline") == len(lay["cables"])
    assert "bandeja" not in LY.elevacion_svg(lay["posiciones"], lay["dims"], "frontal")   # sin red, como antes


def test_estado_layout_con_red_electrica(pl):
    lay = LY.estado_layout(pl)
    assert lay["ccm"] == lay["red"]["ccm_propuesta"] and set(lay["cables_m"]) == {c["id"] for c in lay["cables"]}
    lay2 = LY.estado_layout(pl, dict(lay, ccm=[2, 3, 0], tension=400.0, bombas_linea=False))
    assert lay2["ccm"] == [2.0, 3.0, 0] and set(lay2["cables_m"]) == {"AL-W2", "AL-W3"}
    assert all(c["U_V"] == 400.0 for c in lay2["cables"])
