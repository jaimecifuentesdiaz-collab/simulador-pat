"""Layout de planta (PAT 135, tarea T7.3; indicación 3 de la reunión con el profesor Torres del 04-11-2026).

Qué hace:
1. Dimensiones de cada equipo (largo, ancho y alto en m) en función de su tamaño (carga en t/h, calor en kW o potencia
   de la caldera en MW), con reemplazo por dimensiones traídas de internet o escritas por el usuario (dimensiones(eq, override)).
   Gancho opcional al cliente de Tavily de otro equipo (pat_sim.datos.precios_web), que puede no existir.
2. Propuesta automática de posiciones: con clave de un modelo de lenguaje se arma el prompt y se lee la respuesta JSON
   (API de mensajes de Anthropic por urllib); sin clave, o si falla, algoritmo propio de intercambio por pares tipo CRAFT.
3. Elevaciones frontal y lateral izquierda, corte y plano en planta como SVG, con cotas.
4. Longitud de cada corriente: recorrido ortogonal entre puertos con subida y bajada al rack de cañerías, más accesorios.
5. Red eléctrica (PAT 135, T15): sala eléctrica o CCM ubicada junto al centro de carga ponderado por potencia, un alimentador
   por equipo con potencia eléctrica por bandeja, corriente, sección por capacidad de corriente y caída de tensión.

Convenciones (PAT 135): coordenadas en metros, x hacia el este, y hacia el norte, z hacia arriba; posiciones[id] = [x, y, rot]
con (x, y) el centro de la huella del equipo y rot en grados (0, 90, 180 o 270, antihorario). Con rot 0 el largo va según x.

Fuentes del método de layout:
- CRAFT: Armour, G. C. y Buffa, E. S. (1963). A heuristic algorithm and simulation approach to relative location of
  facilities. Management Science, 9(2), 294-309. Intercambio por pares que minimiza Σ flujo × distancia entre centroides.
- SLP: Muther, R. (1973). Systematic Layout Planning, 2.ª ed. Cahners Books. Relaciones entre actividades según el flujo.
- Simplificación propia (Supuesto): los equipos se ordenan en una secuencia que se reparte en filas en zigzag separadas
  por pasillos (codificación por bandas), así toda propuesta cumple la no superposición por construcción; el intercambio
  por pares de CRAFT se hace sobre esa secuencia con distancia rectilínea.
"""
from __future__ import annotations
import json
import math
import re
import urllib.request
from .formato import escribir

# ------------------------------------------------------------------------------------------- supuestos (PAT 135)
PASILLO_M = 1.5        # m; Supuesto pedido en la tarea: pasillo libre entre huellas de equipos para tránsito y mantención
H_RACK_M = 5.0         # m; Supuesto: altura del rack de cañerías, que deja paso libre a una grúa horquilla y a la mantención
ACCESORIOS = 0.20      # fracción; Supuesto: margen por codos, válvulas, liras de dilatación y desvíos sobre el recorrido trazado
RAZON_MAX = 3.0        # Supuesto: la planta no supera una razón largo/ancho de 3 (edificio compacto, fija el ancho de banda)
KW_POR_TH_VAPOR = 2257 / 3.6   # kW por t/h de vapor: calor latente del agua a 100 °C, 2.257 kJ/kg (tablas de vapor IAPWS-IF97)
ESCALA_MIN, ESCALA_MAX = 0.4, 2.5   # Supuesto: tope del factor de escala para no salir del rango de las dimensiones de partida
DIM_MIN = 0.3          # m; ningún lado menor que esto

URL_API = "https://api.anthropic.com/v1/messages"
VERSION_API = "2023-06-01"
MODELO_LLM = "claude-sonnet-5-5"   # PAT 135: modelo vigente a noviembre de 2026; configurable en la interfaz o con ANTHROPIC_MODEL

FUENTE_CRAFT = "Armour y Buffa (1963), Management Science 9(2), 294-309 (CRAFT); Muther (1973), Systematic Layout Planning"
_JUST_GEOM = ("Supuesto: dimensiones de partida del orden de catálogos de fabricantes para ese tamaño (sin fuente segura); "
              "escalan con semejanza geométrica: volumen proporcional al tamaño, lados con exponente 1/3")
_JUST_PLANO = ("Supuesto: equipo extendido en planta (cinta o banda): la superficie crece con el tamaño, largo y ancho con "
               "exponente 1/2 y alto fijo")

# familia: (variable de tamaño, tamaño de referencia, (largo, ancho, alto) en m a ese tamaño, exponentes, justificación)
FAMILIAS = {
    "tolva": ("carga", 100.0, (8.0, 5.0, 4.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "separador": ("carga", 50.0, (4.0, 2.0, 2.5), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "molienda": ("carga", 50.0, (3.0, 2.0, 2.5), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "intercambiador": ("Q_kW", 5000.0, (6.0, 1.5, 2.5), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "evaporador": ("carga", 100.0, (10.0, 6.0, 15.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "recipiente": ("carga", 50.0, (3.0, 3.0, 6.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "acabado": ("carga", 20.0, (6.0, 3.0, 3.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "caldera": ("MW", 10.0, (8.0, 3.5, 4.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "hogar": ("MW", 5.0, (8.0, 4.0, 6.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "secador_rotatorio": ("carga", 10.0, (20.0, 4.0, 5.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "secador_banda": ("carga", 10.0, (30.0, 5.0, 4.0), (1 / 2, 1 / 2, 0.0), _JUST_PLANO),
    "secador_camara": ("carga", 5.0, (12.0, 3.0, 3.0), (1 / 2, 1 / 2, 0.0), _JUST_PLANO),
    "pelletizadora": ("carga", 5.0, (3.0, 2.0, 3.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "enfriador": ("carga", 5.0, (2.5, 2.5, 5.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "bomba": ("carga", 50.0, (1.2, 0.5, 0.6), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "valvula": ("carga", 50.0, (0.6, 0.4, 0.4), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "transportador": ("carga", 20.0, (10.0, 1.0, 1.5), (0.0, 1 / 2, 0.0), _JUST_PLANO),
    "maquina_rotativa": ("carga", 20.0, (2.0, 1.2, 1.5), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "columna": ("carga", 20.0, (3.0, 3.0, 12.0), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
    "general": ("carga", 20.0, (3.0, 2.0, 2.5), (1 / 3, 1 / 3, 1 / 3), _JUST_GEOM),
}
_POR_SIMBOLO = {
    "tolva": "tolva", "almacenamiento_granel": "tolva",
    "criba": "separador", "tamiz": "separador", "filtro": "separador", "filtro_prensa": "separador", "filtro_mangas": "separador",
    "ciclon": "separador", "centrifuga": "separador",
    "trituradora": "molienda", "molino_martillos": "molienda", "astilladora": "molienda", "molino_bolas": "molienda",
    "molino_rodillos": "molienda", "sierra": "molienda", "mezclador": "molienda",
    "intercambiador_tubular": "intercambiador", "intercambiador_general": "intercambiador", "intercambiador_placas": "intercambiador",
    "condensador": "intercambiador", "aeroenfriador": "intercambiador", "camisa": "intercambiador", "serpentin": "intercambiador",
    "evaporador_mvr": "evaporador", "evaporador_multiefecto": "evaporador", "evaporador_pelicula": "evaporador",
    "recipiente": "recipiente", "deposito": "recipiente", "recipiente_agitado": "recipiente", "recipiente_presion": "recipiente",
    "tanque_esferico": "recipiente", "gasometro": "recipiente", "decantador": "recipiente", "separador_gotas": "recipiente",
    "maquina_acabado": "acabado", "extrusora": "acabado", "bascula": "acabado", "dosificador_rotativo": "maquina_rotativa",
    "caldera": "caldera", "horno": "hogar", "quemador": "hogar", "chimenea": "columna",
    "secador_tambor": "secador_rotatorio", "secador_banda": "secador_banda", "secador": "secador_camara",
    "secador_pulverizacion": "columna", "pelletizadora": "pelletizadora", "enfriador_contracorriente": "enfriador",
    "transportador_cinta": "transportador", "transportador_tornillo": "transportador", "elevador_cangilones": "transportador",
    "transporte_neumatico": "transportador",
    "compresor": "maquina_rotativa", "ventilador": "maquina_rotativa", "soplante": "maquina_rotativa", "eyector": "maquina_rotativa",
    "bomba_vacio": "maquina_rotativa", "motor": "maquina_rotativa", "turbina": "maquina_rotativa",
    "columna": "columna", "columna_platos": "columna", "columna_relleno": "columna", "reactor": "columna",
    "torre_enfriamiento": "columna",
}
_UNIDAD = {"carga": "t/h", "Q_kW": "kW", "MW": "MW"}


def familia(eq) -> str:
    """Familia de dimensiones de un equipo, según su símbolo ISO 10628 (bombas y válvulas por prefijo)."""
    s = str(getattr(eq, "simbolo", "") or "")
    if s.startswith("bomba") and s != "bomba_vacio":
        return "bomba"
    if s.startswith("valvula"):
        return "valvula"
    return _POR_SIMBOLO.get(s, "general")


def _num(v):
    try:
        v = float(v)
        return v if math.isfinite(v) and v > 0 else None
    except (TypeError, ValueError):
        return None


def tamano(eq) -> tuple[str, float | None, str]:
    """(variable, valor, unidad) del tamaño que fija las dimensiones: carga (t/h), calor (kW) o potencia de caldera (MW).
    Sin resultado ni capacidad declarada el valor es None (se usa el tamaño de referencia de la familia)."""
    var = FAMILIAS[familia(eq)][0]
    r = getattr(eq, "resultado", None)
    det = (r.detalle if r is not None else {}) or {}
    serv = (r.servicios if r is not None else {}) or {}
    if var == "MW":
        q = _num(det.get("Q_vapor_kW")) or _num(det.get("Q_calor_kW"))
        return var, (q / 1000 if q else None), _UNIDAD[var]
    if var == "Q_kW":
        q = _num(det.get("Q_kW")) or _num(serv.get("vapor_kW")) or _num(serv.get("calor_kW"))
        return var, q, _UNIDAD[var]
    v = _num(det.get("carga_t_h"))
    if v is None and "capacidad" in getattr(eq, "params", {}):
        v = _num(eq.params["capacidad"].valor)
    return var, v, _UNIDAD[var]


def dimensiones(eq, override=None) -> dict:
    """Largo, ancho y alto (m) del equipo según su familia y tamaño. override: dict con largo, ancho o alto (los que vengan)
    y fuente (por ejemplo el enlace de la página de un fabricante traída con Tavily), o tupla (largo, ancho, alto)."""
    fam = familia(eq)
    var, S0, (L0, W0, H0), (eL, eW, eH), just = FAMILIAS[fam]
    _, S, unidad = tamano(eq)
    f = max(ESCALA_MIN, min(ESCALA_MAX, (S / S0) if S else 1.0))
    d = dict(largo=max(DIM_MIN, L0 * f ** eL), ancho=max(DIM_MIN, W0 * f ** eW), alto=max(DIM_MIN, H0 * f ** eH),
             familia=fam, variable=var, tamano=S, unidad=unidad, categoria="Supuesto", fuente=just)
    if d["ancho"] > d["largo"]:
        d["largo"], d["ancho"] = d["ancho"], d["largo"]
    if override:
        if isinstance(override, (list, tuple)):
            override = dict(zip(("largo", "ancho", "alto"), override))
        cambio = False
        for k in ("largo", "ancho", "alto"):
            v = _num(override.get(k))
            if v is not None:
                d[k] = v; cambio = True
        if cambio:
            fuente = str(override.get("fuente") or "")
            d["categoria"] = "Internet" if fuente.startswith("http") or override.get("web") else "Usuario"
            d["fuente"] = fuente or "Dimensión escrita por el usuario"
    return d


def dimensiones_planta(pl, overrides: dict | None = None) -> dict:
    """Dimensiones de todos los equipos de la planta: {id: dict de dimensiones(eq, overrides.get(id))}."""
    ov = overrides or {}
    return {k: dimensiones(e, ov.get(k)) for k, e in pl.equipos.items()}


# ------------------------------------------------------------------------------------------- gancho a internet
_PATRON_DIM = re.compile(r"(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*[x×X*]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)?\s*[x×X*]\s*(\d+(?:[.,]\d+)?)\s*(mm|cm|m)\b")
_A_M = {"mm": 0.001, "cm": 0.01, "m": 1.0}


def dimensiones_desde_texto(texto: str) -> dict | None:
    """Primeras dimensiones «L x A x H unidad» de un texto (por ejemplo el resumen de una página de fabricante), en m.
    La unidad del último número vale para los que no traen la suya. None si no hay."""
    m = _PATRON_DIM.search(str(texto or ""))
    if not m:
        return None
    u_fin = m.group(6)
    vals = []
    for i in (1, 3, 5):
        u = m.group(i + 1) or u_fin
        vals.append(float(m.group(i).replace(",", ".")) * _A_M[u])
    return dict(largo=vals[0], ancho=vals[1], alto=vals[2])


def buscar_dimensiones_web(eq, buscador=None) -> dict | None:
    """Gancho opcional al cliente de Tavily (pat_sim.datos.precios_web, de otro equipo; puede no existir). Si el módulo tiene
    buscar_dimensiones(nombre, tipo, tamano, unidad) se usa su dict; si solo tiene buscar(consulta) se leen las dimensiones del
    texto de los resultados. Devuelve un override para dimensiones() con fuente (enlace), o None si no hay módulo ni dato."""
    mod = buscador
    if mod is None:
        try:
            from ..datos import precios_web as mod          # noqa: F401
        except Exception:
            return None
    _, S, unidad = tamano(eq)
    nombre = getattr(eq, "nombre", "") or getattr(eq, "nombre_tipo", "")
    try:
        if hasattr(mod, "buscar_dimensiones"):
            r = mod.buscar_dimensiones(nombre, getattr(eq, "tipo", ""), S, unidad)
            if isinstance(r, dict) and any(_num(r.get(k)) for k in ("largo", "ancho", "alto")):
                return dict(r, web=True)
            return None
        if hasattr(mod, "buscar"):
            consulta = f"{nombre} dimensions length width height {escribir(S, 0) + ' ' + unidad if S else ''}".strip()
            res = mod.buscar(consulta)
            items = res.get("results", []) if isinstance(res, dict) else (res or [])
            for it in items:
                txt = it.get("content", "") if isinstance(it, dict) else str(it)
                d = dimensiones_desde_texto(txt)
                if d:
                    d.update(fuente=(it.get("url", "") if isinstance(it, dict) else "") or "Búsqueda en internet", web=True)
                    return d
    except Exception:
        return None
    return None


# ------------------------------------------------------------------------------------------- geometría
def _rot(r) -> int:
    return int(round(float(r or 0) / 90.0)) % 4 * 90


def huella(pos, dim) -> tuple[float, float, float, float]:
    """(xmin, ymin, xmax, ymax) de la huella del equipo con su rotación."""
    x, y, r = float(pos[0]), float(pos[1]), _rot(pos[2] if len(pos) > 2 else 0)
    L, W = (dim["largo"], dim["ancho"]) if r in (0, 180) else (dim["ancho"], dim["largo"])
    return (x - L / 2, y - W / 2, x + L / 2, y + W / 2)


def superposiciones(posiciones: dict, dims: dict, pasillo: float = PASILLO_M, tol: float = 1e-6) -> list[tuple[str, str]]:
    """Pares de equipos cuyas huellas se tocan o quedan a menos del pasillo (el pasillo se cuenta entre huellas)."""
    ids = [k for k in posiciones if k in dims]
    hs = {k: huella(posiciones[k], dims[k]) for k in ids}
    malos = []
    for i, a in enumerate(ids):
        for b in ids[i + 1:]:
            A, B = hs[a], hs[b]
            sep_x = max(B[0] - A[2], A[0] - B[2]); sep_y = max(B[1] - A[3], A[1] - B[3])
            if max(sep_x, sep_y) < pasillo - tol:
                malos.append((a, b))
    return malos


def puerto(pos, dim, lado: str) -> tuple[float, float, float]:
    """Coordenadas (x, y, z) de un puerto: «sale» en el lado derecho local (x+), «entra» en el izquierdo (x−) y «servicio» en la
    cara de atrás (y+), girados con el equipo. Altura de la boquilla: mitad del alto (Supuesto, boquilla a media altura)."""
    x, y, r = float(pos[0]), float(pos[1]), _rot(pos[2] if len(pos) > 2 else 0)
    lx, ly = {"sale": (dim["largo"] / 2, 0.0), "entra": (-dim["largo"] / 2, 0.0), "servicio": (0.0, dim["ancho"] / 2)}[lado]
    c, s = round(math.cos(math.radians(r))), round(math.sin(math.radians(r)))
    return (x + lx * c - ly * s, y + lx * s + ly * c, dim["alto"] / 2)


# ------------------------------------------------------------------------------------------- corrientes y flujos
def id_corriente(c) -> str:
    """Identificador de la corriente: su número de diagrama o «origen-destino»."""
    return str(c.nombre) if c.nombre else f"{c.origen}-{c.destino}"


def _medio(pl, c, tipo) -> str:
    cor = (getattr(pl, "salidas", None) or {}).get((c.origen, c.puerto_origen)) if getattr(pl, "resuelta", False) else None
    if tipo == "electricidad":
        return "cable"
    if (cor is not None and cor.fase == "solido") or tipo == "biomasa":
        return "transportador"
    if tipo in ("calor", "humos", "aire"):
        return "ducto"
    return "cañería"


def flujos(pl) -> list[dict]:
    """Corrientes entre equipos con su peso para el layout (t/h). Proceso: caudal de la corriente × reparto. Servicios de vapor o
    calor: kW que pide el destino ÷ 627 kW por t/h de vapor (calor latente a 100 °C). Sin planta resuelta, peso 1."""
    out = []
    salidas = getattr(pl, "salidas", None) or {}
    for c in pl.conexiones:
        if c.origen not in pl.equipos or c.destino not in pl.equipos:
            continue
        tipo = pl.tipo_conexion(c); serv = pl.es_servicio(c); peso = None
        if pl.resuelta:
            if serv:
                r = pl.equipos[c.destino].resultado
                kw = (r.servicios.get(c.puerto_origen + "_kW", 0.0) if r is not None else 0.0) * c.reparto / 100
                peso = float(kw) / KW_POR_TH_VAPOR if kw else None
            elif (c.origen, c.puerto_origen) in salidas:
                peso = salidas[(c.origen, c.puerto_origen)].m * c.reparto / 100 / 1000
        out.append(dict(id=id_corriente(c), origen=c.origen, destino=c.destino, tipo=tipo, servicio=serv,
                        medio=_medio(pl, c, tipo), peso=max(0.1, float(peso)) if peso else 1.0))
    return out


def costo_flujo_distancia(posiciones: dict, fl: list[dict]) -> float:
    """Σ peso × distancia rectilínea entre centros de los equipos conectados (función objetivo de CRAFT)."""
    t = 0.0
    for f in fl:
        a, b = posiciones.get(f["origen"]), posiciones.get(f["destino"])
        if a is not None and b is not None:
            t += f["peso"] * (abs(a[0] - b[0]) + abs(a[1] - b[1]))
    return t


# ------------------------------------------------------------------------------------------- algoritmo propio (CRAFT)
def ancho_banda(dims: dict, pasillo: float = PASILLO_M, razon: float = RAZON_MAX) -> float:
    """Largo máximo de una fila: el que deja la planta con razón largo/ancho ≤ razón para el área con pasillos (Supuesto)."""
    area = sum((d["largo"] + pasillo) * (d["ancho"] + pasillo) for d in dims.values())
    return max(math.sqrt(razon * area), max((d["largo"] for d in dims.values()), default=1.0))


def colocar_secuencia(seq: list[str], dims: dict, pasillo: float = PASILLO_M, banda: float | None = None) -> dict:
    """Reparte la secuencia en filas en zigzag (la fila par de oeste a este, la impar de vuelta) con pasillos entre equipos,
    entre filas y en el perímetro. Sin superposición por construcción. Devuelve {id: [x, y, 0]}."""
    banda = banda or ancho_banda(dims, pasillo)
    filas, fila, ocup = [], [], 0.0
    for k in seq:
        L = dims[k]["largo"]
        if fila and ocup + pasillo + L > banda + 1e-9:
            filas.append(fila); fila, ocup = [], 0.0
        ocup += (pasillo if fila else 0.0) + L; fila.append(k)
    if fila:
        filas.append(fila)
    pos, y0 = {}, pasillo
    for i, f in enumerate(filas):
        prof = max(dims[k]["ancho"] for k in f)
        largo_fila = sum(dims[k]["largo"] for k in f) + pasillo * (len(f) - 1)
        x = pasillo if i % 2 == 0 else pasillo + banda
        for k in f:
            L = dims[k]["largo"]
            if i % 2 == 0:
                pos[k] = [x + L / 2, y0 + prof / 2, 0]; x += L + pasillo
            else:
                pos[k] = [x - L / 2, y0 + prof / 2, 0]; x -= L + pasillo
        y0 += prof + pasillo
        del largo_fila
    return pos


def secuencia_inicial(pl) -> list[str]:
    """Orden del proceso (topológico) para partir: así los equipos vecinos en la línea quedan juntos (relación A de Muther)."""
    try:
        orden = pl.orden()
    except Exception:
        orden = list(pl.equipos)
    proc = [k for k in orden if not str(pl.equipos[k].tipo).startswith("caldera")]
    return proc + [k for k in orden if k not in proc]


def craft(pl, dims: dict, pasillo: float = PASILLO_M, fl: list[dict] | None = None, max_iter: int = 200) -> dict:
    """Intercambio por pares (CRAFT, Armour y Buffa, 1963) sobre la secuencia de filas: en cada vuelta se prueba intercambiar
    cada par de equipos y se aplica el intercambio que más baja Σ flujo × distancia rectilínea; termina cuando ninguno mejora."""
    fl = flujos(pl) if fl is None else fl
    seq = [k for k in secuencia_inicial(pl) if k in dims]
    banda = ancho_banda(dims, pasillo)
    pos = colocar_secuencia(seq, dims, pasillo, banda); costo = costo_flujo_distancia(pos, fl)
    costo0, it = costo, 0
    while it < max_iter:
        it += 1; mejor = None
        for i in range(len(seq)):
            for j in range(i + 1, len(seq)):
                s2 = seq[:]; s2[i], s2[j] = s2[j], s2[i]
                p2 = colocar_secuencia(s2, dims, pasillo, banda); c2 = costo_flujo_distancia(p2, fl)
                if c2 < costo - 1e-9 and (mejor is None or c2 < mejor[0]):
                    mejor = (c2, s2, p2)
        if mejor is None:
            break
        costo, seq, pos = mejor
    return dict(posiciones=pos, costo=costo, costo_inicial=costo0, iteraciones=it, secuencia=seq,
                metodo="Algoritmo propio: intercambio por pares tipo CRAFT", fuente=FUENTE_CRAFT)


# ------------------------------------------------------------------------------------------- modelo de lenguaje
def prompt_layout(pl, dims: dict, pasillo: float = PASILLO_M, fl: list[dict] | None = None) -> str:
    """Prompt para que un modelo de lenguaje proponga las posiciones. Pide solo JSON."""
    fl = flujos(pl) if fl is None else fl
    eqs = [dict(id=k, nombre=pl.equipos[k].nombre, largo_m=round(d["largo"], 2), ancho_m=round(d["ancho"], 2), alto_m=round(d["alto"], 2))
           for k, d in dims.items()]
    cor = [dict(origen=f["origen"], destino=f["destino"], tipo=f["tipo"], peso_t_h=round(f["peso"], 3)) for f in fl]
    return ("Eres ingeniero de proyectos de plantas de proceso. Propón el layout en planta de esta planta "
            f"({pl.nombre}). Coordenadas en metros: x hacia el este, y hacia el norte; (x, y) es el centro de la huella; rot en "
            "grados (0, 90, 180 o 270, antihorario; con 0 el largo va según x).\n"
            f"Restricciones: las huellas no se superponen y entre dos huellas queda un pasillo libre de al menos {pasillo} m; "
            f"todas las coordenadas positivas con {pasillo} m de pasillo perimetral; planta compacta.\n"
            "Objetivo: minimizar la suma de peso × distancia rectilínea entre los equipos conectados (método CRAFT), con el "
            "orden del proceso de oeste a este y las calderas o generadores de calor junto a sus consumidores.\n"
            f"Equipos: {json.dumps(eqs, ensure_ascii=False)}\n"
            f"Corrientes: {json.dumps(cor, ensure_ascii=False)}\n"
            'Responde solo con JSON, sin texto antes ni después: {"posiciones": {"ID": [x, y, rot], ...}, "justificacion": "una frase"}')


def parsear_respuesta_llm(texto: str, ids) -> dict:
    """Lee las posiciones del JSON que respondió el modelo (acepta bloque de código, {"posiciones": {id: [x, y, rot]}} o lista
    de {id, x, y, rot}). Lanza ValueError si falta un equipo o un valor no es número."""
    t = str(texto or "").strip()
    t = re.sub(r"^```(?:json)?\s*|\s*```$", "", t)
    a, b = t.find("{"), t.rfind("}")
    if a < 0 or b <= a:
        raise ValueError("La respuesta no trae JSON")
    try:
        obj = json.loads(t[a:b + 1])
    except json.JSONDecodeError as e:
        raise ValueError(f"JSON inválido en la respuesta: {e}") from e
    p = obj.get("posiciones", obj) if isinstance(obj, dict) else obj
    if isinstance(p, list):
        p = {str(x.get("id")): [x.get("x"), x.get("y"), x.get("rot", 0)] for x in p if isinstance(x, dict)}
    if not isinstance(p, dict):
        raise ValueError("La respuesta no trae posiciones")
    out = {}
    for k in ids:
        v = p.get(k)
        if v is None:
            raise ValueError(f"La respuesta no trae la posición de {k}")
        if isinstance(v, dict):
            v = [v.get("x"), v.get("y"), v.get("rot", 0)]
        try:
            x, y = float(v[0]), float(v[1]); r = _rot(v[2] if len(v) > 2 else 0)
        except (TypeError, ValueError, IndexError) as e:
            raise ValueError(f"Posición no numérica de {k}") from e
        if not (math.isfinite(x) and math.isfinite(y)):
            raise ValueError(f"Posición no numérica de {k}")
        out[k] = [x, y, r]
    return out


def llamar_llm(prompt: str, clave: str, modelo: str | None = None, abrir=None, timeout: float = 60.0, max_tokens: int = 4096) -> str:
    """Llama a la API de mensajes de Anthropic con urllib y devuelve el texto de la respuesta. abrir: función tipo urlopen
    (se reemplaza en las pruebas por una respuesta simulada)."""
    cuerpo = json.dumps(dict(model=modelo or MODELO_LLM, max_tokens=max_tokens,
                             messages=[dict(role="user", content=prompt)])).encode("utf-8")
    req = urllib.request.Request(URL_API, data=cuerpo, method="POST",
                                 headers={"x-api-key": clave, "anthropic-version": VERSION_API, "content-type": "application/json"})
    r = (abrir or urllib.request.urlopen)(req, timeout=timeout)
    try:
        datos = json.loads(r.read().decode("utf-8"))
    finally:
        if hasattr(r, "close"):
            r.close()
    if isinstance(datos, dict) and datos.get("type") == "error":
        raise RuntimeError(str(datos.get("error", {}).get("message", "error de la API")))
    return "".join(b.get("text", "") for b in datos.get("content", []) if isinstance(b, dict) and b.get("type") == "text")


def proponer_layout(pl, dims: dict | None = None, pasillo: float = PASILLO_M, clave: str | None = None, modelo: str | None = None,
                    abrir=None) -> dict:
    """Propuesta automática. Con clave: modelo de lenguaje (si su propuesta no respeta el pasillo, se descarta). Sin clave o si
    falla: algoritmo propio tipo CRAFT. Devuelve posiciones, método, costo Σ flujo × distancia y avisos."""
    dims = dims or dimensiones_planta(pl)
    fl = flujos(pl); avisos = []
    if clave:
        try:
            txt = llamar_llm(prompt_layout(pl, dims, pasillo, fl), clave, modelo, abrir)
            pos = parsear_respuesta_llm(txt, list(dims))
            malos = superposiciones(pos, dims, pasillo)
            if malos:
                raise ValueError("superpone " + ", ".join(f"{a} con {b}" for a, b in malos[:4]))
            return dict(posiciones=pos, costo=costo_flujo_distancia(pos, fl), metodo=f"Modelo de lenguaje ({modelo or MODELO_LLM})",
                        fuente="Propuesta del modelo de lenguaje, revisada contra superposición y pasillo", avisos=avisos)
        except Exception as e:
            avisos.append(f"La propuesta del modelo de lenguaje no se pudo usar ({e}); se usó el algoritmo propio")
    r = craft(pl, dims, pasillo, fl)
    r["avisos"] = avisos
    return r


def completar_posiciones(posiciones: dict, dims: dict, pasillo: float = PASILLO_M) -> dict:
    """Deja solo los equipos que existen y pone los nuevos al este de lo ya ubicado, en columna, sin superposición."""
    pos = {k: list(v) for k, v in (posiciones or {}).items() if k in dims}
    faltan = [k for k in dims if k not in pos]
    if not faltan:
        return pos
    x0 = max((huella(pos[k], dims[k])[2] for k in pos), default=0.0) + pasillo
    y = pasillo
    ancho = max(dims[k]["largo"] for k in faltan)
    for k in faltan:
        pos[k] = [x0 + ancho / 2, y + dims[k]["ancho"] / 2, 0]; y += dims[k]["ancho"] + pasillo
    return pos


# ------------------------------------------------------------------------------------------- longitudes de cañería
def diametros(pl) -> dict:
    """Diámetro interno (mm) de las líneas de líquido desde hidraulica.red_hidraulica, por (origen, destino); vacío si no se puede."""
    try:
        from .hidraulica import red_hidraulica
        return {(f["origen"], f["destino"]): f["D_mm"] for f in red_hidraulica(pl)["lineas"]}
    except Exception:
        return {}


def longitud_tramo(p1, p2, h_rack: float = H_RACK_M, accesorios: float = ACCESORIOS, por_rack: bool = True) -> dict:
    """Recorrido ortogonal entre dos puertos (x, y, z): horizontal |Δx| + |Δy|; vertical: subida y bajada al rack (|h − z1| +
    |h − z2|) o, sin rack (transportadores), |z1 − z2|; total = (horizontal + vertical) × (1 + accesorios)."""
    hor = abs(p1[0] - p2[0]) + abs(p1[1] - p2[1])
    ver = (abs(h_rack - p1[2]) + abs(h_rack - p2[2])) if por_rack else abs(p1[2] - p2[2])
    return dict(horizontal=hor, vertical=ver, accesorios=(hor + ver) * accesorios, total=(hor + ver) * (1 + accesorios))


def longitudes(pl, posiciones: dict, dims: dict, h_rack: float = H_RACK_M, accesorios: float = ACCESORIOS) -> list[dict]:
    """Una fila por corriente: medio (cañería, ducto, transportador o cable), diámetro si hay, tramos y largo total (m)."""
    D = diametros(pl); filas = []
    for f in flujos(pl):
        a, b = posiciones.get(f["origen"]), posiciones.get(f["destino"])
        if a is None or b is None:
            continue
        p1 = puerto(a, dims[f["origen"]], "sale")
        p2 = puerto(b, dims[f["destino"]], "servicio" if f["servicio"] else "entra")
        t = longitud_tramo(p1, p2, h_rack, accesorios, por_rack=f["medio"] != "transportador")
        filas.append(dict(f, D_mm=D.get((f["origen"], f["destino"])) if f["medio"] == "cañería" else None, **t))
    return filas


def longitudes_m(filas: list[dict]) -> dict:
    """{id de corriente: largo total en m} para st.session_state["layout"]["longitudes_m"] (lo usa el costeo)."""
    return {f["id"]: round(f["total"], 2) for f in filas}


# ------------------------------------------------------------------------------------------- red eléctrica (PAT 135, T15)
# Pedido del profesor Torres (04-11-2026): layout preliminar con piping y alimentaciones eléctricas. Un CCM (centro de control
# de motores) en una sala eléctrica alimenta a cada equipo con potencia eléctrica por un alimentador propio que va por bandeja.
TENSION_V = 380.0      # V entre fases, trifásico 50 Hz; Supuesto: tensión nominal habitual de baja tensión industrial en Chile
FP = 0.85              # Supuesto: factor de potencia de motores de inducción a plena carga, sin compensación
H_BANDEJA_M = 4.0      # m; Supuesto: bandeja portaconductores 1 m bajo el rack de cañerías, separada de las líneas calientes
HOLGURA_CABLE = 0.15   # fracción; Supuesto: subidas a tableros, curvas de la bandeja, colas de conexión y holgura de tendido
Z_BORNES_M = 0.5       # m; Supuesto: caja de bornes del motor del equipo a 0,5 m del piso
Z_SALIDA_CCM_M = 2.3   # m; Supuesto: salida de cables por arriba de las celdas del CCM (alto típico de celdas, 2,3 m)
FACTOR_DISENO = 1.25   # Supuesto: corriente de diseño del alimentador = 125 % de la nominal (margen de arranque y ampliación)
DU_MAX_PCT = 3.0       # %; Supuesto: caída de tensión máxima en el alimentador (criterio usual de 3 % en alimentadores)
RHO_CU_20 = 0.017241   # Ω·mm²/m; resistividad del cobre recocido a 20 °C (IEC 60028, patrón internacional del cobre recocido)
ALFA_CU = 0.00393      # 1/K; coeficiente de temperatura de la resistencia del cobre recocido a 20 °C (IEC 60028)
T_CONDUCTOR_C = 90.0   # °C; Supuesto: conductor XLPE a su temperatura máxima de servicio (caso más desfavorable)
X_CABLE_OHM_KM = 0.08  # Ω/km; Supuesto: reactancia típica de un cable multipolar de baja tensión
P_MEDIA_TENSION_KW = 250.0   # kW; Supuesto: sobre esta potencia un motor se suele alimentar en media tensión (se avisa)
CCM_DIM = dict(largo=6.0, ancho=4.0, alto=3.5)   # m; Supuesto: sala eléctrica con una fila de celdas y pasillo de operación
ID_CCM = "CCM"
# (sección mm², capacidad A): cobre, aislación XLPE, cable multipolar en bandeja perforada, 30 °C
SECCIONES = ((2.5, 36), (4, 49), (6, 63), (10, 86), (16, 115), (25, 149), (35, 185), (50, 225), (70, 289), (95, 352),
             (120, 410), (150, 473), (185, 542), (240, 641), (300, 741))
FUENTE_SECCIONES = ("Supuesto: capacidades del orden de IEC 60364-5-52, tabla B.52.12, método E (cable multipolar de cobre XLPE "
                    "en bandeja perforada, 30 °C, tres conductores cargados); verificar con la tabla del fabricante del cable")
FUENTE_TENSION = ("Supuesto: 380 V trifásico 50 Hz, tensión de baja tensión industrial habitual en Chile; factor de potencia 0,85; "
                  "caída de tensión máxima 3 % en el alimentador (criterio usual; verificar con el pliego técnico vigente de la SEC)")


def potencia_electrica(eq) -> tuple[float | None, str]:
    """Potencia eléctrica (kW) del equipo y de dónde sale: servicio electricidad_kW del resultado, W_kW del detalle (bombas) o
    parámetro potencia_kW o potencia (kW). (None, "") si no tiene: ese equipo no lleva alimentador."""
    r = getattr(eq, "resultado", None)
    serv = (getattr(r, "servicios", None) or {}) if r is not None else {}
    det = (getattr(r, "detalle", None) or {}) if r is not None else {}
    v = _num(serv.get("electricidad_kW"))
    if v:
        return v, "Resultado del equipo (servicio de electricidad)"
    v = _num(det.get("W_kW"))
    if v:
        return v, "Resultado del equipo (potencia en el punto de operación)"
    ps = getattr(eq, "params", {}) or {}
    for k in ("potencia_kW", "potencia"):
        if k in ps:
            v = _num(getattr(ps[k], "valor", ps[k]))
            if v:
                return v, f"Parámetro {k} del equipo"
    return None, ""


def cargas_electricas(pl, posiciones: dict, dims: dict, bombas_linea: bool = True) -> list[dict]:
    """Una carga por equipo con potencia eléctrica, en el centro de su huella. Con bombas_linea, también las bombas de las líneas
    de líquido que no tienen bomba dibujada en el diagrama (las mismas P-1xx que agrega el costeo), junto a la salida del origen."""
    out = []
    for k, eq in pl.equipos.items():
        if k not in posiciones or k not in dims:
            continue
        P, fuente = potencia_electrica(eq)
        if P:
            out.append(dict(id=f"AL-{k}", equipo=k, nombre=getattr(eq, "nombre", k), P_kW=P, fuente_P=fuente,
                            x=float(posiciones[k][0]), y=float(posiciones[k][1])))
    if bombas_linea:
        try:
            from .hidraulica import red_hidraulica
            lineas = red_hidraulica(pl)["lineas"]
        except Exception:
            lineas = []
        for i, ln in enumerate(lineas, 1):
            o = ln["origen"]
            if ln.get("bomba_diagrama") is None and _num(ln.get("potencia_kW")) and o in posiciones and o in dims:
                x, y, _ = puerto(posiciones[o], dims[o], "sale")
                out.append(dict(id=f"AL-P-{100 + i}", equipo=f"P-{100 + i}", nombre=f"Bomba de la línea {ln['linea']}",
                                P_kW=float(ln["potencia_kW"]), fuente_P="Red hidráulica (motor/hidraulica.py)", x=x, y=y))
    return out


def centro_de_carga(cargas: list[dict]) -> tuple[float, float] | None:
    """Centro de carga: promedio de las posiciones ponderado por la potencia (kW). None sin cargas."""
    P = sum(c["P_kW"] for c in cargas)
    if P <= 0:
        return None
    return (sum(c["P_kW"] * c["x"] for c in cargas) / P, sum(c["P_kW"] * c["y"] for c in cargas) / P)


def posicion_ccm(posiciones: dict, dims: dict, cargas: list[dict], pasillo: float = PASILLO_M, dim_ccm: dict | None = None,
                 paso: float = 0.5, max_anillos: int = 400) -> list[float]:
    """Posición propuesta de la sala eléctrica: el punto libre más cercano al centro de carga (sin cargas, el centro de la planta),
    buscado en anillos de una grilla de paso m; libre = a pasillo o más de toda huella y con coordenadas positivas."""
    dc = dim_ccm or CCM_DIM
    hs = [huella(p, dims[k]) for k, p in posiciones.items() if k in dims]
    c = centro_de_carga(cargas)
    if c is None:
        c = ((min(h[0] for h in hs) + max(h[2] for h in hs)) / 2, (min(h[1] for h in hs) + max(h[3] for h in hs)) / 2) if hs else (0.0, 0.0)
    L2, W2 = dc["largo"] / 2, dc["ancho"] / 2

    def libre(x, y):
        if x - L2 < pasillo - 1e-9 or y - W2 < pasillo - 1e-9:
            return False
        for h in hs:
            if max(h[0] - (x + L2), (x - L2) - h[2], h[1] - (y + W2), (y - W2) - h[3]) < pasillo - 1e-6:
                return False
        return True
    x0, y0 = round(c[0] / paso) * paso, round(c[1] / paso) * paso
    for r in range(max_anillos + 1):
        cand = [(i, j) for i in range(-r, r + 1) for j in range(-r, r + 1) if max(abs(i), abs(j)) == r]
        cand.sort(key=lambda t: (x0 + t[0] * paso - c[0]) ** 2 + (y0 + t[1] * paso - c[1]) ** 2)
        for i, j in cand:
            x, y = x0 + i * paso, y0 + j * paso
            if libre(x, y):
                return [x, y, 0]
    xmax = max((h[2] for h in hs), default=0.0)
    return [xmax + pasillo + L2, pasillo + W2, 0]


def corriente_A(P_kW: float, U_V: float = TENSION_V, fp: float = FP) -> float:
    """Corriente de línea trifásica: I = P / (√3 · U · cos φ), con P en W."""
    return float(P_kW) * 1000 / (math.sqrt(3) * U_V * fp)


def resistencia_ohm_m(seccion_mm2: float, T_C: float = T_CONDUCTOR_C) -> float:
    """Resistencia del conductor de cobre (Ω/m): ρ20 · (1 + α (T − 20)) / S."""
    return RHO_CU_20 * (1 + ALFA_CU * (T_C - 20)) / seccion_mm2


def caida_tension(I_A: float, L_m: float, seccion_mm2: float, U_V: float = TENSION_V, fp: float = FP, paralelos: int = 1,
                  x_ohm_km: float = X_CABLE_OHM_KM) -> tuple[float, float]:
    """Caída de tensión trifásica (V y % de U): ΔU = √3 · I · L · (R cos φ + X sen φ) / n, con n conductores en paralelo."""
    R = resistencia_ohm_m(seccion_mm2); X = x_ohm_km / 1000
    sen = math.sqrt(max(0.0, 1 - fp ** 2))
    dU = math.sqrt(3) * I_A * L_m * (R * fp + X * sen) / max(1, int(paralelos))
    return dU, 100 * dU / U_V


def seleccionar_seccion(I_A: float, L_m: float, U_V: float = TENSION_V, fp: float = FP, du_max: float = DU_MAX_PCT,
                        factor: float = FACTOR_DISENO) -> dict:
    """Sección del alimentador: la menor de la tabla cuya capacidad cubre la corriente de diseño (factor × I) y cuya caída de
    tensión no pasa de du_max. Si ni la mayor sección alcanza, se ponen conductores en paralelo."""
    Id = I_A * factor
    n0 = n = max(1, math.ceil(Id / SECCIONES[-1][1]))
    while True:
        aptas = [(S, cap) for S, cap in SECCIONES if cap * n >= Id - 1e-9]
        for S, cap in aptas:
            dU, pct = caida_tension(I_A, L_m, S, U_V, fp, n)
            if pct <= du_max + 1e-9:
                crit = "capacidad de corriente" if (n == n0 and S == aptas[0][0]) else "caída de tensión"
                return dict(I_diseno_A=Id, seccion_mm2=S, capacidad_A=cap * n, paralelos=n, dU_V=dU, dU_pct=pct, cumple=True, criterio=crit)
        if n >= 12:
            S, cap = SECCIONES[-1]; dU, pct = caida_tension(I_A, L_m, S, U_V, fp, n)
            return dict(I_diseno_A=Id, seccion_mm2=S, capacidad_A=cap * n, paralelos=n, dU_V=dU, dU_pct=pct, cumple=False, criterio="tope")
        n += 1


def ruta_cable(p_ccm, p_eq, h_bandeja: float = H_BANDEJA_M, z_salida: float = Z_SALIDA_CCM_M, z_bornes: float = Z_BORNES_M) -> list:
    """Recorrido ortogonal del alimentador (x, y, z): sube del CCM a la bandeja, va según x y después según y, y baja al equipo."""
    xc, yc = float(p_ccm[0]), float(p_ccm[1]); xe, ye = float(p_eq[0]), float(p_eq[1])
    return [(xc, yc, z_salida), (xc, yc, h_bandeja), (xe, yc, h_bandeja), (xe, ye, h_bandeja), (xe, ye, z_bornes)]


def largo_cable(ruta: list, holgura: float = HOLGURA_CABLE) -> dict:
    """Largo del recorrido: horizontal (|Δx| + |Δy|), vertical (subida y bajada) y holgura; total = (H + V) × (1 + holgura)."""
    hor = sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(ruta, ruta[1:]))
    ver = sum(abs(b[2] - a[2]) for a, b in zip(ruta, ruta[1:]))
    return dict(horizontal=hor, vertical=ver, holgura=(hor + ver) * holgura, total=(hor + ver) * (1 + holgura))


def red_electrica(pl, posiciones: dict, dims: dict, ccm=None, h_bandeja: float = H_BANDEJA_M, holgura: float = HOLGURA_CABLE,
                  U_V: float = TENSION_V, fp: float = FP, du_max: float = DU_MAX_PCT, bombas_linea: bool = True,
                  pasillo: float = PASILLO_M, dim_ccm: dict | None = None) -> dict:
    """Red eléctrica del layout: posición del CCM (la dada o la propuesta junto al centro de carga), un alimentador por carga con
    recorrido, largo, corriente, sección y caída de tensión, el detalle por cable y {alimentador: m} para el costeo."""
    dc = dict(dim_ccm or CCM_DIM)
    cargas = cargas_electricas(pl, posiciones, dims, bombas_linea)
    propuesta = posicion_ccm(posiciones, dims, cargas, pasillo, dc)
    pos_ccm = [float(ccm[0]), float(ccm[1]), _rot(ccm[2] if len(ccm) > 2 else 0)] if ccm else propuesta
    cables, avisos = [], []
    for c in cargas:
        ruta = ruta_cable(pos_ccm, (c["x"], c["y"]), h_bandeja)
        lg = largo_cable(ruta, holgura)
        I = corriente_A(c["P_kW"], U_V, fp)
        sel = seleccionar_seccion(I, lg["total"], U_V, fp, du_max)
        cables.append(dict(c, U_V=U_V, fp=fp, I_A=I, ruta=ruta, **lg, **sel,
                           conductor=(f"{sel['paralelos']} × " if sel["paralelos"] > 1 else "") + f"3 × {escribir(sel['seccion_mm2'], 0 if float(sel['seccion_mm2']).is_integer() else 1)} mm² Cu XLPE"))
        if c["P_kW"] > P_MEDIA_TENSION_KW:
            avisos.append(f"{c['equipo']}: {escribir(c['P_kW'], 0)} kW; sobre {escribir(P_MEDIA_TENSION_KW, 0)} kW se suele alimentar en media "
                          f"tensión; aquí se calcula en {escribir(U_V, 0)} V con " + (f"{sel['paralelos']} conductores por fase en paralelo" if sel["paralelos"] > 1
                          else "un conductor por fase") + " (Supuesto)")
        if not sel["cumple"]:
            avisos.append(f"{c['id']}: ni con {sel['paralelos']} conductores de {escribir(sel['seccion_mm2'], 0)} mm² la caída baja de {escribir(du_max, 1)} %")
    hs_ccm = huella(pos_ccm, dc)
    cerca = [k for k, p in posiciones.items() if k in dims and
             max(huella(p, dims[k])[0] - hs_ccm[2], hs_ccm[0] - huella(p, dims[k])[2],
                 huella(p, dims[k])[1] - hs_ccm[3], hs_ccm[1] - huella(p, dims[k])[3]) < pasillo - 1e-6]
    if cerca:
        avisos.append("La sala eléctrica queda a menos del pasillo de " + ", ".join(cerca))
    P = sum(c["P_kW"] for c in cargas)
    return dict(ccm=pos_ccm, ccm_propuesta=propuesta, ccm_dim=dc, cables=cables, cables_m=cables_m(cables), P_total_kW=P,
                I_total_A=corriente_A(P, U_V, fp) if P else 0.0, largo_total_m=sum(c["total"] for c in cables), avisos=avisos,
                cerca_ccm=cerca, centro=centro_de_carga(cargas), h_bandeja=h_bandeja,
                supuestos=dict(U_V=U_V, fp=fp, h_bandeja=h_bandeja, holgura=holgura, du_max=du_max, factor=FACTOR_DISENO,
                               fuente_tension=FUENTE_TENSION, fuente_secciones=FUENTE_SECCIONES))


def cables_m(cables: list[dict]) -> dict:
    """{alimentador: largo total en m} para st.session_state["layout"]["cables_m"] (lo puede usar el costeo)."""
    return {c["id"]: round(c["total"], 2) for c in cables}


# ------------------------------------------------------------------------------------------- dibujos SVG
_COLOR = {"producto": "#1b7a5a", "subproducto": "#7a5a1b", "vapor": "#c0392b", "condensado": "#2e6db4", "agua": "#2e86c1",
          "gas": "#8e44ad", "aire": "#5dade2", "humos": "#7f8c8d", "electricidad": "#d4ac0d", "calor": "#e67e22", "biomasa": "#6e8b3d"}


COLOR_CABLE = _COLOR["electricidad"]   # PAT 135 (T15): mismo color de «Energía eléctrica» en la leyenda de Diseño


def _f(v, d=1):
    return escribir(v, d)


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _cota_h(x1, x2, y, texto, s=""):
    """Cota horizontal con flechas y texto centrado."""
    return (f'<g stroke="#34495e" fill="#34495e" font-size="11" {s}><line x1="{x1:.1f}" y1="{y:.1f}" x2="{x2:.1f}" y2="{y:.1f}" '
            f'marker-start="url(#fl)" marker-end="url(#fl)"/><line x1="{x1:.1f}" y1="{y - 6:.1f}" x2="{x1:.1f}" y2="{y + 6:.1f}"/>'
            f'<line x1="{x2:.1f}" y1="{y - 6:.1f}" x2="{x2:.1f}" y2="{y + 6:.1f}"/>'
            f'<text x="{(x1 + x2) / 2:.1f}" y="{y - 4:.1f}" text-anchor="middle" stroke="none">{texto}</text></g>')


def _cota_v(x, y1, y2, texto):
    return (f'<g stroke="#34495e" fill="#34495e" font-size="10"><line x1="{x:.1f}" y1="{y1:.1f}" x2="{x:.1f}" y2="{y2:.1f}" '
            f'marker-start="url(#fl)" marker-end="url(#fl)"/><text x="{x + 3:.1f}" y="{(y1 + y2) / 2 + 3:.1f}" stroke="none">{texto}</text></g>')


_DEFS = ('<defs><marker id="fl" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto-start-reverse" markerUnits="userSpaceOnUse">'
         '<path d="M0 1 L8 4 L0 7 Z"/></marker><pattern id="rayado" width="6" height="6" patternUnits="userSpaceOnUse" '
         'patternTransform="rotate(45)"><line x1="0" y1="0" x2="0" y2="6" stroke="#7b8c95" stroke-width="1.2"/></pattern></defs>')


def _vista(items, titulo, eje_txt, h_rack, ancho_px=900, notas="", cables=None, h_bandeja=None):
    """items: (u1, u2, alto, id, estilo) con u en m a lo largo de la vista; estilo 'cerca', 'lejos', 'corte' o 'electrico'
    (sala eléctrica). PAT 135 (T15): cables = recorridos [(u, z), ...] de los alimentadores y h_bandeja, la bandeja eléctrica."""
    if not items:
        return f'<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60"><text x="10" y="30">{_esc(titulo)}: sin equipos</text></svg>'
    cables = cables or []
    us = [p[0] for c in cables for p in c]
    umin = min([i[0] for i in items] + us); umax = max([i[1] for i in items] + us)
    zmax = max(max(i[2] for i in items), h_rack, h_bandeja or 0.0) + 1.0
    mx, mt, mb = 60, 50, 70
    der = 130                                               # PAT 135 (T15): espacio para los rótulos del rack y de la bandeja
    s = min((ancho_px - 2 * mx - der) / max(umax - umin, 1.0), 380 / zmax)
    W = 2 * mx + der + (umax - umin) * s; Hs = mt + zmax * s + mb
    X = lambda u: mx + (u - umin) * s
    Z = lambda z: mt + (zmax - z) * s
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{Hs:.0f}" viewBox="0 0 {W:.0f} {Hs:.0f}" font-family="Arial">',
         '<rect width="100%" height="100%" fill="#fff"/>', _DEFS,
         f'<text x="{mx}" y="22" font-size="15" font-weight="bold" fill="#173243">{_esc(titulo)}</text>',
         f'<text x="{mx}" y="38" font-size="11" fill="#5b7280">{_esc(eje_txt)}</text>']
    # rack de cañerías
    o.append(f'<line x1="{X(umin) - 20:.1f}" y1="{Z(h_rack):.1f}" x2="{X(umax) + 20:.1f}" y2="{Z(h_rack):.1f}" stroke="#c98c31" '
             f'stroke-width="2" stroke-dasharray="8 5"/><text x="{X(umax) + 22:.1f}" y="{Z(h_rack) + 4:.1f}" font-size="10" '
             f'fill="#c98c31">rack +{_f(h_rack, 2)}</text>')
    if h_bandeja:
        o.append(f'<line x1="{X(umin) - 20:.1f}" y1="{Z(h_bandeja):.1f}" x2="{X(umax) + 20:.1f}" y2="{Z(h_bandeja):.1f}" stroke="{COLOR_CABLE}" '
                 f'stroke-width="2" stroke-dasharray="3 3"/><text x="{X(umax) + 22:.1f}" y="{Z(h_bandeja) + 4:.1f}" font-size="10" '
                 f'fill="{COLOR_CABLE}">bandeja eléctrica +{_f(h_bandeja, 2)}</text>')
    orden = sorted(items, key=lambda i: {"lejos": 0, "cerca": 1, "electrico": 1, "corte": 2}[i[4]])   # estable: lo lejano primero
    for u1, u2, h, k, est in orden:
        fill = {"lejos": "#eef3f5", "cerca": "#dcebe6", "corte": "url(#rayado)", "electrico": "#f8eec4"}[est]
        stroke = {"lejos": "#9aaab2", "cerca": "#1b7a5a", "corte": "#173243", "electrico": COLOR_CABLE}[est]
        o.append(f'<rect x="{X(u1):.1f}" y="{Z(h):.1f}" width="{(u2 - u1) * s:.1f}" height="{h * s:.1f}" fill="{fill}" '
                 f'stroke="{stroke}" stroke-width="{2 if est != "lejos" else 1}"/>')
        if est != "lejos":
            o.append(f'<text x="{(X(u1) + X(u2)) / 2:.1f}" y="{Z(h) - 4:.1f}" font-size="11" text-anchor="middle" fill="#173243" '
                     f'font-weight="bold">{_esc(k)}</text>')
            o.append(_cota_v(X(u2) + 4, Z(h), Z(0), _f(h, 1)))
    for c in cables:                                        # PAT 135 (T15): alimentadores punteados
        pts = " ".join(f"{X(u):.1f},{Z(z):.1f}" for u, z in c)
        o.append(f'<polyline points="{pts}" fill="none" stroke="{COLOR_CABLE}" stroke-width="1.6" stroke-dasharray="2 3"/>')
    # piso, nivel y cota total
    o.append(f'<line x1="{X(umin) - 30:.1f}" y1="{Z(0):.1f}" x2="{X(umax) + 30:.1f}" y2="{Z(0):.1f}" stroke="#173243" stroke-width="2.5"/>')
    o.append(f'<text x="{X(umin) - 30:.1f}" y="{Z(0) + 14:.1f}" font-size="10" fill="#173243">±0,00</text>')
    o.append(_cota_h(X(umin), X(umax), Z(0) + 32, f"{_f(umax - umin, 1)} m"))
    if notas:
        o.append(f'<text x="{mx}" y="{Hs - 8:.0f}" font-size="10" fill="#5b7280">{_esc(notas)}</text>')
    o.append("</svg>")
    return "".join(o)


def elevacion_svg(posiciones: dict, dims: dict, vista: str = "frontal", h_rack: float = H_RACK_M, red: dict | None = None) -> str:
    """Elevación frontal (observador al sur mirando al norte: eje x) o lateral izquierda (observador al oeste mirando al este:
    eje y, el norte a la izquierda). Los equipos más cercanos al observador se dibujan delante; cotas de alto y largo total.
    PAT 135 (T15): con red (de red_electrica) se dibujan la sala eléctrica, la bandeja y los alimentadores punteados."""
    items = []
    for k, p in posiciones.items():
        if k not in dims:
            continue
        x1, y1, x2, y2 = huella(p, dims[k])
        if vista == "frontal":
            items.append((x1, x2, dims[k]["alto"], k, "cerca", y1))
        else:
            items.append((-y2, -y1, dims[k]["alto"], k, "cerca", x1))
    cables, hb = [], None
    if red and red.get("ccm"):                              # PAT 135 (T15): la sala eléctrica entra al orden por profundidad
        x1, y1, x2, y2 = huella(red["ccm"], red["ccm_dim"])
        items.append(((x1, x2, red["ccm_dim"]["alto"], ID_CCM, "cerca", y1) if vista == "frontal" else
                      (-y2, -y1, red["ccm_dim"]["alto"], ID_CCM, "cerca", x1)))
        cables = [[(p[0] if vista == "frontal" else -p[1], p[2]) for p in c["ruta"]] for c in red.get("cables", [])]
        hb = red.get("h_bandeja", H_BANDEJA_M)
    # profundidad: el que está más lejos va detrás y más claro si lo tapa otro más cercano
    items.sort(key=lambda i: -i[5])
    fin = []
    for i, it in enumerate(items):
        tapado = any(o[0] <= it[0] + 1e-6 and o[1] >= it[1] - 1e-6 and o[2] >= it[2] - 1e-6 for o in items[i + 1:])
        est = "lejos" if tapado else ("electrico" if it[3] == ID_CCM else "cerca")
        fin.append((it[0], it[1], it[2], it[3], est))
    if vista == "frontal":
        return _vista(fin, "Elevación frontal (vista desde el sur)", "Eje horizontal: oeste a la izquierda, este a la derecha; alturas en m", h_rack,
                      cables=cables, h_bandeja=hb)
    return _vista(fin, "Elevación lateral izquierda (vista desde el oeste)", "Eje horizontal: norte a la izquierda, sur a la derecha; alturas en m", h_rack,
                  cables=cables, h_bandeja=hb)


def corte_y_por_defecto(posiciones: dict, dims: dict) -> float:
    """Plano de corte A-A por defecto: el eje de la fila del equipo más alto (corta los evaporadores o el secador)."""
    if not posiciones:
        return 0.0
    k = max((k for k in posiciones if k in dims), key=lambda k: dims[k]["alto"])
    return float(posiciones[k][1])


def corte_svg(posiciones: dict, dims: dict, y_corte: float | None = None, h_rack: float = H_RACK_M) -> str:
    """Corte A-A por el plano vertical y = y_corte, mirando al norte: los equipos cortados van rayados; los que quedan detrás del
    plano, en contorno claro; los que quedan delante no se dibujan."""
    yc = corte_y_por_defecto(posiciones, dims) if y_corte is None else float(y_corte)
    items = []
    for k, p in posiciones.items():
        if k not in dims:
            continue
        x1, y1, x2, y2 = huella(p, dims[k])
        if y1 - 1e-9 <= yc <= y2 + 1e-9:
            items.append((x1, x2, dims[k]["alto"], k, "corte"))
        elif y1 > yc:
            items.append((x1, x2, dims[k]["alto"], k, "lejos"))
    return _vista(items, f"Corte A-A (plano y = {_f(yc, 1)} m, mirando al norte)",
                  "Rayado: equipo cortado por el plano; contorno claro: equipo detrás del plano", h_rack)


def plano_svg(posiciones: dict, dims: dict, fl: list[dict] | None = None, nombres: dict | None = None, y_corte: float | None = None,
              ancho_px: int = 900, red: dict | None = None) -> str:
    """Plano en planta para el informe (el mismo que dibuja el componente): cuadrícula de 1 m, rótulos, escala, norte y línea de corte.
    PAT 135 (T15): con red (de red_electrica) se dibujan la sala eléctrica y los alimentadores en líneas punteadas."""
    nombres = nombres or {}
    hs = {k: huella(p, dims[k]) for k, p in posiciones.items() if k in dims}
    h_ccm = huella(red["ccm"], red["ccm_dim"]) if red and red.get("ccm") else None
    if not hs:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="300" height="40"><text x="10" y="25">Sin equipos</text></svg>'
    X2 = max([h[2] for h in hs.values()] + ([h_ccm[2]] if h_ccm else [])) + PASILLO_M
    Y2 = max([h[3] for h in hs.values()] + ([h_ccm[3]] if h_ccm else [])) + PASILLO_M
    m = 40; s = (ancho_px - 2 * m) / max(X2, 1.0); W = ancho_px; H = 2 * m + Y2 * s + 30
    X = lambda x: m + x * s
    Y = lambda y: m + (Y2 - y) * s
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H:.0f}" viewBox="0 0 {W} {H:.0f}" font-family="Arial">',
         '<rect width="100%" height="100%" fill="#fff"/>', _DEFS]
    for i in range(int(math.floor(X2)) + 1):
        o.append(f'<line x1="{X(i):.1f}" y1="{Y(0):.1f}" x2="{X(i):.1f}" y2="{Y(Y2):.1f}" stroke="{"#c7d6dc" if i % 5 == 0 else "#edf2f4"}"/>')
    for j in range(int(math.floor(Y2)) + 1):
        o.append(f'<line x1="{X(0):.1f}" y1="{Y(j):.1f}" x2="{X(X2):.1f}" y2="{Y(j):.1f}" stroke="{"#c7d6dc" if j % 5 == 0 else "#edf2f4"}"/>')
    for f in fl or []:
        if f["origen"] in posiciones and f["destino"] in posiciones:
            a, b = posiciones[f["origen"]], posiciones[f["destino"]]
            raya = ' stroke-dasharray="6 4"' if f["servicio"] else ""
            o.append(f'<path d="M{X(a[0]):.1f} {Y(a[1]):.1f} H{X(b[0]):.1f} V{Y(b[1]):.1f}" fill="none" stroke="{_COLOR.get(f["tipo"], "#555")}" '
                     f'stroke-width="1.6"{raya} opacity="0.8"/>')
    for k, (x1, y1, x2, y2) in hs.items():
        o.append(f'<rect x="{X(x1):.1f}" y="{Y(y2):.1f}" width="{(x2 - x1) * s:.1f}" height="{(y2 - y1) * s:.1f}" fill="#dcebe6" stroke="#1b7a5a" stroke-width="1.5"/>')
        o.append(f'<text x="{X((x1 + x2) / 2):.1f}" y="{Y((y1 + y2) / 2):.1f}" font-size="11" text-anchor="middle" font-weight="bold" fill="#173243">{_esc(k)}</text>')
        o.append(f'<text x="{X((x1 + x2) / 2):.1f}" y="{Y((y1 + y2) / 2) + 12:.1f}" font-size="9" text-anchor="middle" fill="#3b5562">{_esc(str(nombres.get(k, ""))[:22])}</text>')
    if h_ccm:                                               # PAT 135 (T15): sala eléctrica y alimentadores
        for c in red.get("cables", []):
            pts = " ".join(f"{X(p[0]):.1f},{Y(p[1]):.1f}" for p in c["ruta"])
            o.append(f'<polyline points="{pts}" fill="none" stroke="{COLOR_CABLE}" stroke-width="1.8" stroke-dasharray="2 3"/>')
        x1, y1, x2, y2 = h_ccm
        o.append(f'<rect x="{X(x1):.1f}" y="{Y(y2):.1f}" width="{(x2 - x1) * s:.1f}" height="{(y2 - y1) * s:.1f}" fill="#f8eec4" '
                 f'stroke="{COLOR_CABLE}" stroke-width="1.8"/><text x="{X((x1 + x2) / 2):.1f}" y="{Y((y1 + y2) / 2) + 4:.1f}" '
                 f'font-size="11" text-anchor="middle" font-weight="bold" fill="#7d6608">{ID_CCM}</text>')
    if y_corte is not None:
        o.append(f'<line x1="{X(0):.1f}" y1="{Y(y_corte):.1f}" x2="{X(X2):.1f}" y2="{Y(y_corte):.1f}" stroke="#bd4b40" stroke-width="1.5" stroke-dasharray="12 4 2 4"/>'
                 f'<text x="{X(0) + 2:.1f}" y="{Y(y_corte) - 4:.1f}" font-size="11" fill="#bd4b40" font-weight="bold">A</text>'
                 f'<text x="{X(X2) - 10:.1f}" y="{Y(y_corte) - 4:.1f}" font-size="11" fill="#bd4b40" font-weight="bold">A</text>')
    # escala de 10 m y norte
    o.append(_cota_h(X(0), X(10), H - 22, "10 m"))
    o.append(f'<g transform="translate({W - 30},{m + 10})"><path d="M0 -14 L7 8 L0 3 L-7 8 Z" fill="#173243"/>'
             f'<text x="0" y="22" font-size="12" text-anchor="middle" font-weight="bold">N</text></g>')
    o.append("</svg>")
    return "".join(o)


def estado_layout(pl, layout: dict | None = None, overrides: dict | None = None, pasillo: float = PASILLO_M,
                  h_rack: float = H_RACK_M, accesorios: float = ACCESORIOS) -> dict:
    """Arma o actualiza el dict de st.session_state["layout"]: posiciones (completadas con los equipos nuevos), dims,
    longitudes_m, filas de longitudes y costo. Si no hay posiciones, parte con el algoritmo propio.
    PAT 135 (T15): también la red eléctrica (ccm, red, cables y cables_m) con los supuestos guardados en el mismo dict
    (h_bandeja, holgura_cable, tension, fp, du_max, bombas_linea); sin ccm se propone junto al centro de carga."""
    lay = dict(layout or {})
    dims = dimensiones_planta(pl, overrides if overrides is not None else lay.get("overrides"))
    if not lay.get("posiciones"):
        r = craft(pl, dims, pasillo)
        lay.update(posiciones=r["posiciones"], propuesta={k: list(v) for k, v in r["posiciones"].items()}, metodo=r["metodo"])
    lay["posiciones"] = completar_posiciones(lay["posiciones"], dims, pasillo)
    filas = longitudes(pl, lay["posiciones"], dims, h_rack, accesorios)
    lay.update(dims=dims, filas=filas, longitudes_m=longitudes_m(filas),
               costo=costo_flujo_distancia(lay["posiciones"], flujos(pl)),
               superposiciones=superposiciones(lay["posiciones"], dims, pasillo))
    red = red_electrica(pl, lay["posiciones"], dims, lay.get("ccm"), float(lay.get("h_bandeja", H_BANDEJA_M)),
                        float(lay.get("holgura_cable", HOLGURA_CABLE)), float(lay.get("tension", TENSION_V)), float(lay.get("fp", FP)),
                        float(lay.get("du_max", DU_MAX_PCT)), bool(lay.get("bombas_linea", True)), pasillo)
    lay.update(ccm=red["ccm"], red=red, cables=red["cables"], cables_m=red["cables_m"])
    return lay
