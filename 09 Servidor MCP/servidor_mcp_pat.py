"""Servidor MCP del motor pat_sim (PAT 135, 05-11-2026).

Expone el motor de ingeniería básica de planta como herramientas del Model Context Protocol (MCP), para que un agente
(Claude Desktop, Claude Code o un agente LangChain) diseñe con la aplicación. Usa el SDK oficial de Python (paquete mcp,
FastMCP) y habla por stdio: python servidor_mcp_pat.py

Las plantas viven en un registro en memoria (id de texto). Todas las herramientas devuelven datos JSON serializables.
Nada de lo que hace requiere internet ni un modelo de lenguaje: el costeo usa la bibliografía y el layout el algoritmo propio.
"""
from __future__ import annotations
import itertools
import math
import sys
from pathlib import Path

# PAT 135: el motor está en la carpeta hermana «02 Motor de calculo Python» (paquete pat_sim)
RAIZ = Path(__file__).resolve().parents[1]
MOTOR = RAIZ / "02 Motor de calculo Python"
if str(MOTOR) not in sys.path:
    sys.path.insert(0, str(MOTOR))

from mcp.server.fastmcp import FastMCP   # noqa: E402

from pat_sim.escenarios import agrozzi, pellet, chip, lena   # noqa: E402
from pat_sim.motor import resumen as RES, economia as ECO, riesgo as RIESGO, costeo as COSTEO   # noqa: E402
from pat_sim.motor import mc_economico as MC, layout as LY, temporada as TM   # noqa: E402

mcp = FastMCP("pat_sim")

ESCENARIOS = {"agrozzi": agrozzi, "pellet": pellet, "chip": chip, "lena": lena}
_PLANTAS: dict = {}                      # PAT 135: registro en memoria, id -> Planta
_CONTADOR = itertools.count(1)


# ---------------------------------------------------------------- utilidades
def _json(x):
    """Convierte a tipos JSON puros: numpy a número, tuplas a listas, inf y nan a None."""
    if isinstance(x, dict):
        return {str(k): _json(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [_json(v) for v in x]
    if hasattr(x, "tolist") and not isinstance(x, (str, bytes)):
        return _json(x.tolist())
    if isinstance(x, bool) or x is None or isinstance(x, str):
        return x
    if isinstance(x, int):
        return x
    if isinstance(x, float):
        return x if math.isfinite(x) else None
    return str(x)


def _planta(planta_id: str):
    pl = _PLANTAS.get(str(planta_id))
    if pl is None:
        raise ValueError(f"No existe la planta «{planta_id}». Cree una con crear_planta; las vigentes son: {sorted(_PLANTAS) or 'ninguna'}")
    return pl


def _resuelta(pl):
    if not pl.resuelta:
        pl.resolver()
    return pl


def _registrar(pl) -> str:
    pid = f"P{next(_CONTADOR)}"
    _PLANTAS[pid] = pl
    return pid


def _bd():
    from pat_sim.datos.bd import BaseDatos
    return BaseDatos()       # respeta PAT_SIM_DB


# ---------------------------------------------------------------- herramientas
@mcp.tool()
def listar_escenarios() -> dict:
    """Lista los rubros que se pueden crear con crear_planta (agrozzi, pellet, chip, lena) con el nombre y la cantidad de equipos de cada uno."""
    out = []
    for rubro, mod in ESCENARIOS.items():
        pl = mod.crear()
        out.append(dict(rubro=rubro, nombre=pl.nombre, rubro_interno=pl.rubro, n_equipos=len(pl.equipos)))
    return _json(dict(escenarios=out))


@mcp.tool()
def crear_planta(rubro: str) -> dict:
    """Crea una planta de partida y la guarda en el registro en memoria. rubro: agrozzi, pellet, chip o lena. Devuelve el id de la planta (planta_id) para las demás herramientas."""
    clave = str(rubro).strip().lower().replace("leña", "lena")
    if clave not in ESCENARIOS:
        raise ValueError(f"Rubro desconocido «{rubro}». Use uno de: {', '.join(ESCENARIOS)}")
    pl = ESCENARIOS[clave].crear()
    pid = _registrar(pl)
    return _json(dict(planta_id=pid, rubro=clave, nombre=pl.nombre, n_equipos=len(pl.equipos)))


@mcp.tool()
def listar_equipos(planta_id: str) -> dict:
    """Lista los equipos de la planta con su tipo y los parámetros editables (clave, valor, unidad). Sirve para elegir qué mandar a cambiar_parametro."""
    pl = _planta(planta_id)
    eqs = []
    for e in pl.equipos.values():
        eqs.append(dict(id=e.id, nombre=e.nombre, tipo=e.tipo,
                        parametros=[dict(clave=k, nombre=p.nombre, valor=p.valor, unidad=p.unidad) for k, p in e.params.items()]))
    return _json(dict(planta_id=str(planta_id), equipos=eqs))


@mcp.tool()
def cambiar_parametro(planta_id: str, equipo: str, parametro: str, valor: float) -> dict:
    """Cambia un parámetro de un equipo (por ejemplo equipo W1, parametro T_salida, valor 95). La planta queda sin resolver: llame a resolver para ver el efecto."""
    pl = _planta(planta_id)
    if equipo not in pl.equipos:
        raise ValueError(f"La planta no tiene el equipo «{equipo}». Equipos: {', '.join(pl.equipos)}")
    eq = pl.equipos[equipo]
    antes = eq.params[parametro].valor if parametro in eq.params else None
    eq.set(parametro, float(valor))
    pl.resuelta = False
    return _json(dict(planta_id=str(planta_id), equipo=equipo, parametro=parametro, antes=antes, ahora=float(valor), resuelta=False))


@mcp.tool()
def resolver(planta_id: str) -> dict:
    """Resuelve los balances de la planta y entrega un resumen: producción de la temporada, capacidad de la línea, cuello de botella (equipo con mayor utilización), utilizaciones, servicios y avisos."""
    pl = _planta(planta_id)
    pl.resolver()
    r = RES.resumen_planta(pl)
    util = pl.utilizaciones()
    d = TM.datos_planta(pl)
    cuello = util[0] if util else None
    return _json(dict(planta_id=str(planta_id), nombre=pl.nombre, rubro=pl.rubro,
                      produccion=dict(alimentacion_t_h=d["carga"], dias=d["D"], horas_dia=d["H"], alimentacion_temporada_t=d["total"],
                                      capacidad_linea_t_h=TM.capacidad_linea(pl)),
                      cuello_de_botella=cuello, utilizaciones=util, servicios=r["servicios"], horas=r["horas"],
                      avisos=list(pl.avisos)))


@mcp.tool()
def recuperacion_calor(planta_id: str) -> dict:
    """Recuperación de calor de la planta: calor del sumidero, cobertura de la cascada, del pinch y de la bomba de calor, y el combustible (gas o biomasa) que cada alternativa desplaza."""
    pl = _resuelta(_planta(planta_id))
    r = RES.resumen_planta(pl)
    if r.get("sin_sumidero"):
        return _json(dict(planta_id=str(planta_id), sin_sumidero=True, avisos=r["avisos"]))
    claves = ("sumidero", "Qsumidero", "oferta", "cascada", "cobertura_cascada", "pinch", "cobertura_pinch", "T_pinch", "Q_externo_min",
              "alt2", "cobertura_alt2", "bomba_calor", "fuentes_bomba", "combustible", "horas", "dT_min", "T_final", "cop",
              "gas_base", "gas_cascada", "gas_pinch", "gas_alt2", "gas_remanente_cascada", "calor_generador_kW", "combustible_kgh",
              "biomasa_base", "biomasa_cascada", "biomasa_pinch", "biomasa_alt2", "biomasa_remanente_cascada", "avisos")
    return _json(dict(planta_id=str(planta_id), **{k: r[k] for k in claves if k in r}))


def _economia(pl, precio_gas, dolar, tasa, anios, inversion, costo_anual=0.0, precio_biomasa=6750.0):
    r = RES.resumen_planta(_resuelta(pl))
    E = dict(precio_gas=float(precio_gas), dolar=float(dolar), inversion=float(inversion), costo_anual=float(costo_anual),
             anios=int(anios), tasa=float(tasa), precio_biomasa=float(precio_biomasa))
    return r, E


@mcp.tool()
def evaluar_economia(planta_id: str, precio_gas: float, dolar: float, tasa: float, anios: int, inversion: float,
                     costo_anual: float = 0.0, precio_biomasa: float = 6750.0) -> dict:
    """Evaluación económica de la recuperación de calor por cascada: ahorro anual, VAN, TIR y recuperación. precio_gas en US$/MMBtu, dolar en $/US$, tasa como fracción (0.10), anios, inversion y costo_anual en millones de pesos (MM$). En plantas a biomasa se usa precio_biomasa en $/m3 estéreo. Con inversion 0 se usa la inversión máxima con VAN cero."""
    pl = _planta(planta_id)
    r, E = _economia(pl, precio_gas, dolar, tasa, anios, inversion, costo_anual, precio_biomasa)
    s = RIESGO.supuestos(r, E)
    if s is None:
        raise ValueError("La planta no tiene caldera o generador con horas declaradas: no hay ahorro que evaluar.")
    ev = RIESGO.evaluacion_cascada(s["base"], s["desplazado"], s["combustible"])
    ahorro = RIESGO.ahorro_anual(s["base"], s["desplazado"], s["combustible"])
    return _json(dict(planta_id=str(planta_id), combustible=s["combustible"], desplazado=s["desplazado"], ahorro_anual_MM=ahorro,
                      inversion_MM=s["base"]["inversion"], costo_anual_MM=s["base"]["costo_anual"], VAN_MM=ev["VAN"], TIR=ev["TIR"],
                      recuperacion_anios=ev["recuperacion_anios"], flujos_MM=ev["flujos"], avisos=s["avisos"]))


@mcp.tool()
def costear(planta_id: str) -> dict:
    """Costo de los equipos y de la planta (Williams, CEPCI, factor de instalación) usando solo la bibliografía, sin internet. Devuelve el costo por equipo y los totales en US$ y $."""
    pl = _resuelta(_planta(planta_id))
    c = COSTEO.costear(pl, buscar=False)
    filas = [{k: f.get(k) for k in ("equipo", "nombre", "tipo", "tamano", "unidad", "cantidad", "costo_usd", "costo_clp", "origen", "fuente")}
             for f in c["filas"]]
    return _json(dict(planta_id=str(planta_id), filas=filas, totales=c["totales"], avisos=c["avisos"], cepci_hoy=c["cepci_hoy"],
                      dolar=c["dolar"], n_bibliografia=c["n_bibliografia"]))


@mcp.tool()
def montecarlo_economico(planta_id: str, n: int = 500) -> dict:
    """Simulación de Montecarlo del VAN con fallas de los equipos y demanda variable, para las estrategias de capacidad seguimiento, un nivel y dos niveles. n es la cantidad de réplicas (entre 10 y 20000). Entrega media, percentiles 5, 50 y 95, probabilidad de VAN negativo, déficit y exceso."""
    pl = _planta(planta_id)
    n = max(10, min(int(n), 20000))
    r, E = _economia(pl, 2.77, 990.35, 0.10, 20, 0.0)
    ctx = MC.contexto(pl, r, E)
    if ctx is None:
        raise ValueError("La planta no tiene caldera o generador con horas declaradas: no hay ahorro que simular.")
    res = MC.simular(ctx, n=n)
    est = {}
    for k, v in res["estrategias"].items():
        est[k] = {c: v[c] for c in ("nombre", "media", "desviacion", "p5", "p50", "p95", "prob_negativo", "deficit_t", "exceso_t",
                                    "produccion_t", "demanda_t", "servicio")}
    return _json(dict(planta_id=str(planta_id), n=res["n"], anios=res["anios"], periodos=res["periodos"], alcance=res["alcance"],
                      inversion_MM=res["inversion"], estrategias=est, avisos=ctx["avisos"]))


@mcp.tool()
def proponer_layout(planta_id: str) -> dict:
    """Propone la disposición en planta de los equipos con el algoritmo propio (tipo CRAFT, sin modelo de lenguaje): posiciones x e y, costo flujo por distancia, método y superposiciones detectadas."""
    pl = _resuelta(_planta(planta_id))
    dims = LY.dimensiones_planta(pl)
    p = LY.proponer_layout(pl, dims)
    return _json(dict(planta_id=str(planta_id), metodo=p["metodo"], costo=p["costo"], posiciones=p["posiciones"],
                      superposiciones=LY.superposiciones(p["posiciones"], dims), avisos=p.get("avisos", [])))


@mcp.tool()
def guardar_version(planta_id: str, proyecto: str = "", nota: str = "") -> dict:
    """Guarda la planta como una versión nueva de un proyecto de la base SQLite (la crea si no existe). Si proyecto va vacío usa «MCP» más el nombre de la planta. Devuelve proyecto_id, version_id y número de versión."""
    pl = _planta(planta_id)
    bd = _bd()
    nombre = (proyecto or "").strip() or f"MCP {pl.nombre}"
    p = bd.obtener_proyecto(nombre)
    pid = p["id"] if p else bd.crear_proyecto(nombre, pl.rubro, "Creado desde el servidor MCP")
    v = bd.guardar_version(pid, pl, nota)
    return _json(dict(planta_id=str(planta_id), proyecto=nombre, proyecto_id=pid, version_id=v["id"], numero=v["numero"]))


@mcp.tool()
def cargar_version(version_id: int) -> dict:
    """Carga una versión guardada de la base SQLite, la resuelve y la registra como planta nueva. Devuelve el planta_id nuevo."""
    pl = _bd().cargar_version(int(version_id))
    pid = _registrar(pl)
    return _json(dict(planta_id=pid, version_id=int(version_id), rubro=pl.rubro, nombre=pl.nombre, n_equipos=len(pl.equipos)))


@mcp.tool()
def listar_desafios(solo_activos: bool = False) -> dict:
    """Lista los desafíos de diseño del mantenedor (título, enunciado, producto, rubro, demanda y precios)."""
    from pat_sim.datos import mantenedor as M
    bd = _bd()
    M.sembrar(bd)
    return _json(dict(desafios=M.mantenedor(bd).listar_desafios(bool(solo_activos))))


if __name__ == "__main__":
    mcp.run()      # transporte stdio por defecto
