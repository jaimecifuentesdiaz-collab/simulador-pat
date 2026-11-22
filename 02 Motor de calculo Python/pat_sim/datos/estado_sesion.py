"""Estado de la sesión que se guarda con cada proyecto del usuario (PAT 138, pedido de Jaime del 13-11-2026).

La planta va aparte (planta_json). Aquí está lo demás que hace falta para retomar el trabajo como se dejó: el desafío (con la
variante de tomate, la distribución de la llegada y la serie de demanda), la economía, el COP, la temporada, los datos medidos,
las distribuciones ajustadas, el layout, el costeo, los equipos auxiliares, los parámetros de Línea y del riesgo económico, las
fichas de Planta real, los pesos de Alternativas, los tableros, el experimento y las etapas del flujo de diseño.

Solo se guardan valores que vuelven idénticos desde JSON (se comprueba ida y vuelta); lo que no, se omite y queda anotado en
_meta.omitidas. No se guardan los valores de botones ni de campos de carga de archivos (Streamlit no deja fijarlos) ni objetos
de la sesión (la operación por turnos, el historial del lienzo). Funciones sin Streamlit: reciben la sesión como diccionario.
"""
from __future__ import annotations
import hashlib, json, math
from datetime import datetime

FORMATO = 1
# claves de la sesión que se guardan con el proyecto
CLAVES = ("desafio", "economia", "cop", "temporada", "datos_medidos", "distribuciones", "layout", "costeo", "costeo_param",
          "auxiliares", "ln_parametros", "mce_parametros", "sel_fichas", "alt_pesos", "tableros", "experimento",
          "flujo_registro", "flujo_etapa", "persona_nombre")
PREFIJOS = ("sel_usar_",)          # fichas elegidas en Planta real, una clave por rubro y equipo
# resultados que valen para una versión de la planta: si estaban al día al guardar, se ponen al día con la planta cargada
CON_VERSION = {"costeo": "version", "layout": "pl_version"}
# lo que cuenta para «cambios sin guardar»: lo que el usuario fija a mano. No entran los resultados que las pantallas recalculan
# solas, la etapa del flujo ni los parámetros que una pantalla deja con su valor por omisión al abrirse (pesos de Alternativas,
# parámetros de Línea, del riesgo económico y del costeo, fichas de Planta real): abrir una pantalla no es un cambio.
CLAVES_HUELLA = ("desafio", "economia", "cop", "temporada", "datos_medidos", "distribuciones", "persona_nombre")


def _normal(v):
    """Tuplas a listas y números de numpy a números de Python, para comparar con lo que vuelve de JSON."""
    if isinstance(v, dict):
        return {k: _normal(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_normal(x) for x in v]
    if hasattr(v, "item") and not isinstance(v, (str, bytes)):
        try:
            return v.item()
        except Exception:
            return v
    return v


def _igual(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_igual(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_igual(x, y) for x, y in zip(a, b))
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b
    return type(a) is type(b) and a == b if not (isinstance(a, (int, float)) and isinstance(b, (int, float))) else a == b


def _por_json(v):
    """(True, valor tal como vuelve de JSON) si v sobrevive la ida y vuelta sin cambiar; si no, (False, None)."""
    try:
        n = _normal(v)
        t = json.dumps(n, ensure_ascii=False, allow_nan=True)
        back = json.loads(t)
    except (TypeError, ValueError, OverflowError, RecursionError):
        return False, None
    return (True, back) if _igual(n, back) else (False, None)


_INT = "__claves_enteras__"


def _codificar(v):
    """Diccionarios con claves enteras (por ejemplo el registro de etapas del flujo, {1: …, 2: …}) a una forma que JSON
    conserva: {"__claves_enteras__": {"1": …}}."""
    if isinstance(v, dict):
        if v and all(isinstance(k, int) and not isinstance(k, bool) for k in v):
            return {_INT: {str(k): _codificar(x) for k, x in v.items()}}
        return {k: _codificar(x) for k, x in v.items()}
    if isinstance(v, (list, tuple)):
        return [_codificar(x) for x in v]
    return v


def _decodificar(v):
    if isinstance(v, dict):
        if set(v) == {_INT} and isinstance(v[_INT], dict):
            return {int(k): _decodificar(x) for k, x in v[_INT].items()}
        return {k: _decodificar(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_decodificar(x) for x in v]
    return v


def claves_de(ss) -> list[str]:
    return [k for k in CLAVES if k in ss] + sorted(k for k in ss.keys() if isinstance(k, str) and k.startswith(PREFIJOS))


def capturar(ss, version_planta: int | None = None) -> dict:
    """Estado guardable de la sesión ss (st.session_state o un diccionario). version_planta: la de C.version_planta(), para saber
    qué resultados (costeo, layout) estaban al día con la planta."""
    estado, omitidas, tuplas, vigentes, codificadas = {}, [], [], [], []
    for k in claves_de(ss):
        v = ss[k]
        if v is None:
            continue
        ok, back = _por_json(v)
        if not ok:
            c = _codificar(v)
            ok, back = _por_json(c)
            if ok and _igual(_normal(_decodificar(back)), _normal(v)):
                codificadas.append(k)
            else:
                omitidas.append(k)
                continue
        estado[k] = back
        if isinstance(v, tuple):
            tuplas.append(k)
        campo = CON_VERSION.get(k)
        if campo and isinstance(v, dict) and version_planta is not None and v.get(campo) == version_planta:
            vigentes.append(k)
    estado["_meta"] = dict(formato=FORMATO, fecha=datetime.now().isoformat(timespec="seconds"), omitidas=omitidas,
                           tuplas=tuplas, vigentes=vigentes, codificadas=codificadas)
    return estado


def restaurar(ss, estado: dict, version_planta: int | None = None, defectos: dict | None = None) -> list[str]:
    """Deja en ss el estado guardado: borra las claves guardables que el proyecto no trae (para que no queden las del trabajo
    anterior), pone las del proyecto, devuelve las tuplas y pone al día con version_planta los resultados que lo estaban al
    guardar. defectos: valores para las claves que el proyecto no trae y la sesión necesita (economía y COP).
    Devuelve las claves restauradas."""
    estado = dict(estado or {}); meta = estado.pop("_meta", None) or {}
    for k in claves_de(ss):
        if k not in estado:
            del ss[k]
    for k, v in (defectos or {}).items():
        if k not in estado:
            ss[k] = json.loads(json.dumps(v))
    puestas = []
    for k, v in estado.items():
        if k in CLAVES or (isinstance(k, str) and k.startswith(PREFIJOS)):
            if k in (meta.get("codificadas") or []):
                v = _decodificar(v)
            ss[k] = tuple(v) if k in (meta.get("tuplas") or []) and isinstance(v, list) else v
            puestas.append(k)
    for k in meta.get("vigentes") or []:
        campo = CON_VERSION.get(k)
        if campo and isinstance(ss.get(k), dict) and version_planta is not None:
            ss[k][campo] = version_planta
    return puestas


def foto(ss) -> dict:
    """Lo que el usuario fija a mano fuera de la planta (CLAVES_HUELLA), tal como vuelve de JSON, para avisar «cambios sin
    guardar». Vacío es lo mismo que no tenerlo."""
    d = {}
    for k in CLAVES_HUELLA:
        v = ss[k] if k in ss else None
        if v is None or (isinstance(v, (str, dict, list, tuple)) and not v):
            continue
        ok, back = _por_json(v)
        d[k] = back if ok else repr(v)
    return d


def cambio(antes, ahora) -> bool:
    """True si ahora difiere de antes. Una entrada nueva de un diccionario que no estaba al guardar no cuenta (las pantallas
    completan valores por omisión al abrirse, como la alternativa elegida en Alternativas); un valor distinto o uno que
    desapareció, sí."""
    if isinstance(antes, dict) and isinstance(ahora, dict):
        return any(k not in ahora or cambio(v, ahora[k]) for k, v in antes.items())
    return not _igual(_normal(antes), _normal(ahora))


def huella(ss) -> str:
    """Huella (sha1) de foto(ss)."""
    t = json.dumps(foto(ss), ensure_ascii=False, sort_keys=True, allow_nan=True, default=str)
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def huella_planta(pl) -> str:
    """Huella del contenido de la planta (equipos, parámetros, conexiones, instrumentos y _p)."""
    from .bd import a_json, planta_completa_a_dict
    try:
        t = a_json(planta_completa_a_dict(pl))
    except Exception:
        t = repr((getattr(pl, "nombre", ""), len(getattr(pl, "equipos", {}) or {}), len(getattr(pl, "conexiones", []) or [])))
    return hashlib.sha1(t.encode("utf-8")).hexdigest()


def resumen(pl, estado: dict | None = None, cop: float = 2.0) -> dict:
    """Cifras clave para la lista de proyectos: tipo de planta, variante y distribución del tomate, equipos, capacidad de
    diseño, kW recuperados por la cascada, inversión y VAN de la cascada (si hay inversión en Economía). Cada cifra que no se
    pueda calcular queda en None."""
    estado = estado or {}
    des = estado.get("desafio") or {}
    p = getattr(pl, "_p", None) if isinstance(getattr(pl, "_p", None), dict) else {}
    out = dict(planta=getattr(pl, "nombre", ""), rubro=getattr(pl, "rubro", ""), tipo_planta=None, variante_tomate=None,
               distribucion_tomate=None, equipos=len(getattr(pl, "equipos", {}) or {}), resuelta=bool(getattr(pl, "resuelta", False)),
               capacidad_t_h=None, kw_recuperados=None, inversion_m=None, van_m=None, desafio=des.get("titulo"))
    try:
        from ..motor import sintesis as SI
        out["tipo_planta"] = SI.tipo_de(pl)
        out["variante_tomate"] = SI.variante_de(pl) or des.get("variante_tomate")
        inf = SI.informe(pl) or {}
        out["capacidad_t_h"] = (inf.get("dimensionamiento") or {}).get("materia_prima_diseno_t_h")
        out["distribucion_tomate"] = inf.get("distribucion_tomate") or des.get("distribucion_tomate")
    except Exception:
        pass
    if out["tipo_planta"] is None:
        out["tipo_planta"] = p.get("tipo_planta") or out["rubro"]
    if out["capacidad_t_h"] is None:
        try:
            caps = [e.params["capacidad"].valor for e in pl.equipos.values() if "capacidad" in e.params and e.params["capacidad"].valor]
            out["capacidad_t_h"] = float(max(caps)) if caps else None
        except Exception:
            pass
    if not out["resuelta"] or not out["equipos"]:
        return out
    try:
        from ..motor.resumen import resumen_planta
        r = resumen_planta(pl, cop=cop)
        if r.get("cascada") is not None:
            out["kw_recuperados"] = float(r["cascada"])
        E = estado.get("economia") or {}
        inv = float(E.get("inversion") or 0.0)
        out["inversion_m"] = inv or None
        if inv > 0 and "gas_desplazado_cascada" in r:
            from ..motor import economia as eco
            ahorro = eco.valor_gas(r["gas_desplazado_cascada"]["MMBtu"], E["precio_gas"], E["dolar"])
            out["van_m"] = float(eco.evaluacion(inv, ahorro, float(E.get("costo_anual") or 0.0), int(E["anios"]), float(E["tasa"]))["VAN"])
    except Exception:
        pass
    return out
