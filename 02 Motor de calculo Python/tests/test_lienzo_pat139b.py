"""PAT 139b (pedido de Jaime y del profesor Torres, 14-11-2026): n unidades en paralelo dibujadas como n símbolos (datos que el
motor manda al lienzo) y curva característica de eficiencia de la línea η(producción) con su punto de operación, su punto de diseño
y la zona de buen rendimiento (motor/lienzo.curva_eficiencia_linea)."""
import json
import pytest
from pat_sim.motor import lienzo as LZ, seleccion as S, sintesis as SI, costo_total as CT
from pat_sim.motor.planta import Planta
from pat_sim.escenarios import agrozzi

CAT = {"todos": dict(nombre="Todos", equipos=[])}


def _tomate():
    pl = SI.armar_planta("tomate")
    sel = S.seleccionar(pl)
    S.aplicar(pl, {e["equipo"]: e["recomendada"] for e in sel["etapas"] if e["recomendada"]})
    return pl


# ---------------------------------------------------------------- n unidades en paralelo
@pytest.mark.parametrize("n,k,dib,resto,col,fil,res", [(1, 1, 1, 0, 1, 1, 0), (2, 1, 2, 0, 1, 2, 1), (3, 3, 3, 0, 1, 3, 0),
                                                        (4, 3, 4, 0, 2, 2, 1), (6, 4, 6, 0, 2, 3, 2), (9, 8, 6, 3, 2, 3, 0),
                                                        (10, 5, 6, 4, 2, 3, 1)])
def test_dibujo_paralelo_tope_columnas_y_reserva(n, k, dib, resto, col, fil, res):
    d = LZ.dibujo_paralelo(n, k)
    assert (d["n"], d["k"], d["n_dibujados"], d["n_resto"], d["columnas"], d["filas"]) == (n, k, dib, resto, col, fil)
    assert d["n_reserva"] == n - k and d["n_reserva_dibujadas"] == res and d["n_dibujados"] <= LZ.TOPE_PARALELO == 6


def test_dibujo_paralelo_datos_raros_no_fallan():
    assert LZ.dibujo_paralelo(None)["n"] == 1 and LZ.dibujo_paralelo(0)["n_dibujados"] == 1
    assert LZ.dibujo_paralelo(3, 9)["k"] == 3 and LZ.dibujo_paralelo(3, "x")["k"] == 3


def test_la_vista_real_manda_n_por_etapa_al_lienzo():
    pl = _tomate()
    d = LZ.datos_lienzo(pl, pl, None, CAT, vista="real")
    con = {k: v for k, v in d["real"]["equipos"].items() if v["seleccion"]}
    assert con and any(v["n"] > 1 for v in con.values())
    for v in con.values():
        assert v["dibujo"] == LZ.dibujo_paralelo(v["n"], v["k"]) and v["dibujo"]["n_dibujados"] == min(v["n"], 6)
    json.dumps(d)


def test_diseno_no_cambia_sin_capa_real():
    pl = agrozzi.crear(); pl.resolver()
    d = LZ.datos_lienzo(pl, pl, None, CAT)
    assert "real" not in d and d["vista"] == "ficticia"


# ---------------------------------------------------------------- curva de eficiencia de la línea
def test_curva_de_eficiencia_con_punto_de_operacion_y_de_diseno():
    pl = agrozzi.crear(); pl.resolver()
    c = LZ.curva_eficiencia_linea(pl, pl)
    assert c is not None and len(c["x"]) == len(c["eta_linea"]) == len(c["eta_critico"]) == 41
    assert c["x"][0] == 0 and c["x"][-1] == pytest.approx(c["capacidad_linea"]) and c["x"] == sorted(c["x"])
    assert all(0 < v <= 1 for v in c["eta_linea"])
    op, dis = c["operacion"], c["diseno"]
    assert op["produccion"] == pytest.approx(min(c["produccion_plan"], c["capacidad_linea"]), abs=1e-3)
    assert dis["eta_linea"] >= max(c["eta_linea"]) - 1e-9 and dis["eta_linea"] >= op["eta_linea"] - 1e-12     # el diseño es el máximo
    crit = next(e for e in c["etapas"] if e["id"] == c["critico"])
    assert op["eta_critico"] == pytest.approx(CT.eta_relativa(op["carga_rel_critico"], 1.0))
    assert crit["eta"] == c["eta_critico"]
    lo, hi = c["zona"]
    assert 0 < lo < hi <= c["capacidad_linea"] + 1e-9
    assert "ANSI/HI 9.6.3" in c["fuente_zona"] and "https://" in c["fuente_zona"] and "Supuesto" in c["fuente"]
    assert LZ.datos_lienzo(pl, pl, None, CAT)["curva_eficiencia"]["operacion"] == op


def test_la_eficiencia_de_la_linea_es_la_media_armonica_ponderada():
    pl = agrozzi.crear(); pl.resolver()
    c = LZ.curva_eficiencia_linea(pl, pl)
    i = 20
    w = {e["id"]: e["peso_kW"] for e in c["etapas"]}
    esperado = sum(w.values()) / sum(w[e["id"]] / e["eta"][i] for e in c["etapas"])
    assert c["eta_linea"][i] == pytest.approx(esperado, rel=1e-3)


def test_sobredimensionar_baja_la_eficiencia_en_operacion():
    """Con más capacidad instalada para la misma producción, la carga por unidad baja y la línea opera más lejos de su diseño."""
    pl = agrozzi.crear(); pl.resolver()
    base = LZ.curva_eficiencia_linea(pl, pl)["operacion"]["eta_linea"]
    for eq in pl.equipos.values():
        if "capacidad" in eq.params and eq.params["capacidad"].valor:
            eq.set("capacidad", float(eq.params["capacidad"].valor) * 3)
    pl.resolver()
    assert LZ.curva_eficiencia_linea(pl, pl)["operacion"]["eta_linea"] < base


def test_curva_con_unidades_en_paralelo_usa_la_carga_por_unidad():
    pl = _tomate()
    c = LZ.curva_eficiencia_linea(pl, pl)
    for e in c["etapas"]:
        act = S.seleccion_actual(pl.equipos[e["id"]])
        if act:
            assert (e["n"], e["k"]) == (act["n"], act["k"])
            assert e["q_diseno_t_h"] == pytest.approx(pl.equipos[e["id"]].capacidad_efectiva() / act["n"])


def test_planta_vacia_o_sin_resolver_no_tiene_curva():
    assert LZ.curva_eficiencia_linea(Planta("vacía"), None) is None
    pl = Planta("vacía")
    assert LZ.datos_lienzo(pl, None, "vacía", CAT)["curva_eficiencia"] is None
