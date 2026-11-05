"""Pruebas del servidor MCP (PAT 135). Sin el paquete mcp: se instala un sustituto mínimo de FastMCP que registra las
herramientas con su decorador, y cada herramienta se llama como función normal."""
import importlib.util
import json
import os
import sys
import tempfile
import types
from pathlib import Path
import pytest

RAIZ = Path(__file__).resolve().parents[2]
RUTA = RAIZ / "09 Servidor MCP" / "servidor_mcp_pat.py"


class FastMCPSustituto:
    """Sustituto mínimo de mcp.server.fastmcp.FastMCP: guarda las funciones decoradas con @tool()."""
    def __init__(self, nombre="x", *a, **k):
        self.nombre = nombre; self.herramientas = {}

    def tool(self, *a, **k):
        def deco(f):
            self.herramientas[f.__name__] = f
            return f
        return deco

    def run(self, *a, **k):
        pass


def _cargar():
    for nombre in ("mcp", "mcp.server", "mcp.server.fastmcp"):
        sys.modules.pop(nombre, None)
    m1, m2, m3 = types.ModuleType("mcp"), types.ModuleType("mcp.server"), types.ModuleType("mcp.server.fastmcp")
    m3.FastMCP = FastMCPSustituto; m1.server = m2; m2.fastmcp = m3
    sys.modules.update({"mcp": m1, "mcp.server": m2, "mcp.server.fastmcp": m3})
    esp = importlib.util.spec_from_file_location("servidor_mcp_pat_prueba", RUTA)
    mod = importlib.util.module_from_spec(esp); esp.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def S():
    d = tempfile.mkdtemp(prefix="pat_mcp_")
    anterior = os.environ.get("PAT_SIM_DB")
    os.environ["PAT_SIM_DB"] = str(Path(d) / "prueba.db")
    mod = _cargar()
    yield mod
    if anterior is None:
        os.environ.pop("PAT_SIM_DB", None)
    else:
        os.environ["PAT_SIM_DB"] = anterior


def _t(S, nombre, **kw):
    r = S.mcp.herramientas[nombre](**kw)
    json.dumps(r, allow_nan=False)            # debe ser JSON puro
    return r


def test_registra_las_doce_herramientas(S):
    esperadas = {"listar_escenarios", "crear_planta", "listar_equipos", "cambiar_parametro", "resolver", "recuperacion_calor",
                 "evaluar_economia", "costear", "montecarlo_economico", "proponer_layout", "guardar_version", "cargar_version",
                 "listar_desafios"}
    assert esperadas <= set(S.mcp.herramientas)
    assert all((f.__doc__ or "").strip() for f in S.mcp.herramientas.values())


def test_listar_escenarios(S):
    r = _t(S, "listar_escenarios")
    assert {e["rubro"] for e in r["escenarios"]} == {"agrozzi", "pellet", "chip", "lena"}
    assert all(e["n_equipos"] > 3 for e in r["escenarios"])


def test_crear_planta_y_rubro_invalido(S):
    r = _t(S, "crear_planta", rubro="pellet")
    assert r["planta_id"] in S._PLANTAS and r["n_equipos"] > 3
    with pytest.raises(ValueError):
        S.mcp.herramientas["crear_planta"](rubro="cobre")
    with pytest.raises(ValueError):
        S.mcp.herramientas["resolver"](planta_id="P999")


def test_listar_equipos_y_cambiar_parametro(S):
    pid = _t(S, "crear_planta", rubro="agrozzi")["planta_id"]
    eqs = _t(S, "listar_equipos", planta_id=pid)["equipos"]
    assert any(e["id"] == "W1" for e in eqs)
    w1 = next(e for e in eqs if e["id"] == "W1")
    clave = next(p["clave"] for p in w1["parametros"] if p["clave"] == "T_salida")
    r = _t(S, "cambiar_parametro", planta_id=pid, equipo="W1", parametro=clave, valor=94.0)
    assert r["ahora"] == 94.0 and r["resuelta"] is False and S._PLANTAS[pid].equipos["W1"].v("T_salida") == 94.0
    with pytest.raises(ValueError):
        S.mcp.herramientas["cambiar_parametro"](planta_id=pid, equipo="ZZ", parametro="x", valor=1)
    with pytest.raises(KeyError):
        S.mcp.herramientas["cambiar_parametro"](planta_id=pid, equipo="W1", parametro="no_existe", valor=1)


@pytest.mark.parametrize("rubro", ["agrozzi", "pellet", "chip", "lena"])
def test_resolver_y_recuperacion_en_los_cuatro_rubros(S, rubro):
    pid = _t(S, "crear_planta", rubro=rubro)["planta_id"]
    r = _t(S, "resolver", planta_id=pid)
    assert r["produccion"]["alimentacion_t_h"] > 0 and r["utilizaciones"]
    assert r["cuello_de_botella"]["utilizacion"] == max(u["utilizacion"] for u in r["utilizaciones"])
    c = _t(S, "recuperacion_calor", planta_id=pid)
    assert c["Qsumidero"] > 0 and 0 <= c["cobertura_cascada"] <= 1.0001 and c["combustible"] in ("gas", "biomasa")


def test_cambiar_parametro_cambia_el_resultado(S):
    pid = _t(S, "crear_planta", rubro="agrozzi")["planta_id"]
    a = _t(S, "resolver", planta_id=pid)["servicios"]["vapor_kW"]
    _t(S, "cambiar_parametro", planta_id=pid, equipo="W1", parametro="T_salida", valor=80.0)
    assert _t(S, "resolver", planta_id=pid)["servicios"]["vapor_kW"] != pytest.approx(a)


@pytest.mark.parametrize("rubro", ["agrozzi", "pellet"])
def test_evaluar_economia(S, rubro):
    pid = _t(S, "crear_planta", rubro=rubro)["planta_id"]
    r = _t(S, "evaluar_economia", planta_id=pid, precio_gas=2.77, dolar=990.35, tasa=0.10, anios=10, inversion=500.0)
    assert r["ahorro_anual_MM"] > 0 and len(r["flujos_MM"]) == 11
    assert r["VAN_MM"] == pytest.approx(sum(f / 1.1 ** i for i, f in enumerate(r["flujos_MM"])), rel=1e-6)
    r0 = _t(S, "evaluar_economia", planta_id=pid, precio_gas=2.77, dolar=990.35, tasa=0.10, anios=10, inversion=0.0)
    assert r0["VAN_MM"] == pytest.approx(0.0, abs=1e-6) and r0["avisos"]


def test_costear_sin_internet(S):
    pid = _t(S, "crear_planta", rubro="chip")["planta_id"]
    r = _t(S, "costear", planta_id=pid)
    assert r["filas"] and r["totales"]["total_usd"] > 0 and r["n_bibliografia"] == len(r["filas"])


def test_montecarlo_economico(S):
    pid = _t(S, "crear_planta", rubro="pellet")["planta_id"]
    r = _t(S, "montecarlo_economico", planta_id=pid, n=50)
    assert r["n"] == 50 and set(r["estrategias"]) == {"seguimiento", "un_nivel", "dos_niveles"}
    assert all(0 <= v["prob_negativo"] <= 1 and v["p5"] <= v["p95"] for v in r["estrategias"].values())


@pytest.mark.parametrize("rubro", ["agrozzi", "lena"])
def test_proponer_layout(S, rubro):
    pid = _t(S, "crear_planta", rubro=rubro)["planta_id"]
    r = _t(S, "proponer_layout", planta_id=pid)
    assert set(r["posiciones"]) == set(S._PLANTAS[pid].equipos) and r["superposiciones"] == [] and r["costo"] >= 0
    assert "lenguaje" not in r["metodo"].lower()      # algoritmo propio, sin modelo de lenguaje


def test_guardar_y_cargar_version(S):
    pid = _t(S, "crear_planta", rubro="agrozzi")["planta_id"]
    _t(S, "cambiar_parametro", planta_id=pid, equipo="W1", parametro="T_salida", valor=93.0)
    g = _t(S, "guardar_version", planta_id=pid, proyecto="Prueba MCP", nota="prueba")
    assert g["numero"] == 1
    g2 = _t(S, "guardar_version", planta_id=pid, proyecto="Prueba MCP")
    assert g2["numero"] == 2 and g2["proyecto_id"] == g["proyecto_id"]
    c = _t(S, "cargar_version", version_id=g["version_id"])
    assert S._PLANTAS[c["planta_id"]].equipos["W1"].v("T_salida") == 93.0
    r1 = _t(S, "resolver", planta_id=pid)["produccion"]; r2 = _t(S, "resolver", planta_id=c["planta_id"])["produccion"]
    assert r1["alimentacion_t_h"] == pytest.approx(r2["alimentacion_t_h"])


def test_listar_desafios(S):
    r = _t(S, "listar_desafios")
    assert len(r["desafios"]) >= 1 and all("titulo" in d for d in r["desafios"])
    assert len(_t(S, "listar_desafios", solo_activos=True)["desafios"]) <= len(r["desafios"])
