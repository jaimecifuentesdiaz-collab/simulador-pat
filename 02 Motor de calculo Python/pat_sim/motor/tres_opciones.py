"""Tres opciones de instalación por etapa y su ficha comparativa (PAT 140 c, pedido de Jaime del 16-11-2026).

Pedido: en Planta real cada etapa muestra siempre 3 opciones de instalación (por ejemplo 3 unidades, 2 unidades y 1 unidad) y, al
pinchar la etapa, la ficha las compara en 3 columnas con los resultados del equipo, la selección comercial, la eficiencia en operación,
el costo total y la curva η(q)/η_max de cada una, para escoger la que más conviene instalar.

Regla de las 3 opciones (decisión de PAT 140 c, documentada en Cambios_PAT140c_16nov2026.md):
1. A los candidatos de siempre (costo_total.candidatos_con_avisos: equipos reales de Tavily y de la base de respaldo, con n = k y
   n = k + 1, y la estimación de Williams del tamaño justo) se agregan las divisiones de la etapa en k = 1, 2 y 3 unidades iguales que
   operan todas (n = k). Cada división usa el equipo real (base de respaldo o Tavily) más cercano por arriba a la capacidad por unidad
   necesaria, requerida / k, dentro de +20 % (el mismo criterio «calza» de datos/referencia_equipos.py); si no hay, la estimación de
   Williams de ese tamaño, marcada como estimada (origen «Williams»).
2. De todos ellos se toma, para cada número de unidades n, la opción de menor C = C_inv + C_op + C_inef, y de esas las 3 de menor C:
   así las 3 opciones tienen siempre n distinto. Se muestran ordenadas por n (de menos a más unidades); ninguna se marca como la que
   conviene: en la ficha cada fila resalta su valor más conveniente y el estudiante decide.
3. Las demás opciones no se pierden: quedan en la tabla «Elegir por etapa» (todas, ordenables por cualquier columna).

Los equipos auxiliares (motor/eleccion_auxiliares.py) usan elegir_tres y comparativa con sus propios candidatos.
No usa Streamlit.
"""
from __future__ import annotations
import math

from . import costo_total as CT, seleccion as SEL

N_OPCIONES = 3
DIVISIONES = (1, 2, 3)                 # k unidades iguales que operan todas (n = k)
CALZA = 0.20                           # mismo criterio que datos/referencia_equipos.CALZA (±20 %)
REGLA = ("Tres opciones de distinto número de unidades n: para cada n la de menor C = C_inv + C_op + C_inef y, de esas, las 3 de menor C. "
         "Además de los candidatos reales se prueban las divisiones de la etapa en 1, 2 y 3 unidades iguales con el equipo real más "
         "cercano a la capacidad por unidad (hasta 20 % más grande) o, si no hay, la estimación de Williams de ese tamaño. Ordenadas por n; "
         "las demás quedan en la tabla «Elegir por etapa».")


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _f(v, d=1) -> str:
    """Número con formato chileno (punto de miles y coma decimal)."""
    if v is None:
        return "sin dato"
    return f"{float(v):,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _pct(v, d=1) -> str:
    return "sin dato" if v is None else _f(100.0 * float(v), d) + " %"


def _usd(v) -> str:
    return "sin dato" if v is None else "US$ " + _f(v, 0)


# ---------------------------------------------------------------- elección de las 3
def elegir_tres(cands: list[dict], m: int = N_OPCIONES) -> list[dict]:
    """De una lista de candidatos (cada uno con n y C), para cada n el de menor C y, de esos, los m de menor C; devueltos ordenados por n
    (y C). Candidatos sin n o sin C quedan fuera. Lista vacía si no hay."""
    por_n: dict[int, dict] = {}
    for c in sorted((c for c in cands or [] if _num(c.get("C")) is not None and _num(c.get("n"))),
                    key=lambda c: (float(c["C"]), str(c.get("id")))):
        por_n.setdefault(int(c["n"]), c)
    mejores = sorted(por_n.values(), key=lambda c: float(c["C"]))[:max(0, int(m))]
    return sorted(mejores, key=lambda c: (int(c["n"]), float(c["C"])))


# ---------------------------------------------------------------- divisiones de la etapa en k unidades
def _reales(req: dict, filas: list[dict]) -> list[dict]:
    """Filas de equipos reales (base de respaldo o Tavily) con precio, en la unidad de la etapa."""
    out = []
    for f in filas or []:
        c, p = _num(f.get("capacidad")), _num(f.get("precio_usd"))
        if f.get("_generico") or not c or c <= 0 or not p or p <= 0:
            continue
        if (f.get("unidad") or req["unidad"]) != req["unidad"] or f.get("origen") not in ("Respaldo", "Tavily"):
            continue
        out.append(f)
    return out


def _fila_williams(req: dict, cap: float, k: int) -> tuple[dict, list[str]]:
    """Fila de un equipo hipotético de capacidad cap (unidad de la etapa) con el precio de Williams de datos/referencia_equipos
    (regresión con los equipos reales del tipo); sin ese módulo o sin precio, la correlación de costeo.py (seleccion.precio_unitario)."""
    from datetime import date
    precio, fuente, avisos, nombre = None, "", [], f"{cap:g}"
    try:
        from ..datos import referencia_equipos as RE
        nombre = RE._cg(cap)
        cap_tipo = RE.convertir(req["tipo"], cap, req["unidad"], RE.UNIDAD_TIPO.get(req["tipo"], req["unidad"])) or cap
        w = RE.precio_williams(req["tipo"], cap_tipo)
        precio, fuente, avisos = _num(w.get("precio_usd")), w.get("fuente") or "", list(w.get("avisos") or [])
    except Exception as e:                       # sin el módulo o sin referencias: queda la correlación de costeo.py
        avisos.append(f"Sin el ajuste de Williams de la base de respaldo ({type(e).__name__}): se usa la correlación de costeo.py.")
    fab = ("sin dato (equipo hipotético del tamaño justo)" if k == 1
           else f"sin dato (equipo hipotético, la etapa dividida en {k} unidades iguales)")
    fila = dict(tipo=req["tipo_catalogo"], modelo=f"Equipo de {nombre} {req['unidad']} (índice de Williams)", fabricante=fab, capacidad=float(cap),
                unidad=req["unidad"], mtbf_h=None, mttr_h=None, fuente_confiabilidad="", precio_usd=precio,
                anio_precio=date.today().year, fuente_precio=("Precio estimado con " + fuente) if fuente else "",
                fuente_capacidad="Capacidad por unidad = requerida / k (PAT 140 c)", categoria="Supuesto", url="", origen="Williams",
                potencia_kw=None, fuente_potencia="", q_peak=None, eta_max=None, puntos_eta=None, fecha="")
    return fila, avisos


def opciones_division(req: dict, filas: list[dict], P: dict, ref: dict | None = None, ks=DIVISIONES) -> tuple[list[dict], list[str]]:
    """Opciones «la etapa en k unidades iguales» (n = k) para cada k de ks: el equipo real más cercano por arriba a requerida / k dentro de
    +20 % o, si no hay, la estimación de Williams de ese tamaño. Cada opción tiene los mismos campos que costo_total.candidatos_etapa
    (se aplica igual con seleccion.aplicar) más division = k y estimada (precio o equipo estimado). Devuelve (opciones, avisos)."""
    out, avisos = [], []
    S = _num(req.get("requerida"))
    if not S or S <= 0:
        return [], ["La etapa no tiene capacidad requerida positiva."]
    reales = _reales(req, filas)
    for k in ks:
        k = int(k)
        if k < 1:
            continue
        q = S / k
        cerca = [f for f in reales if q * (1 - 1e-9) <= float(f["capacidad"]) <= q * (1 + CALZA)]
        if cerca:
            fila, estimada = min(cerca, key=lambda f: (float(f["capacidad"]), float(f["precio_usd"]))), False
        else:
            fila, av = _fila_williams(req, q, k)
            avisos += av
            estimada = True
        try:
            a = SEL.evaluar(req, fila, k, k, P, None, ref)
        except Exception as e:                   # una división mala no bota la etapa
            avisos.append(f"No se pudo evaluar la división en {k} unidades ({type(e).__name__}: {e}).")
            continue
        org = fila.get("origen") or "Williams"
        out.append(dict(a, id=f"{req['equipo']}|{fila['modelo']}|{k}", fabricante=fila.get("fabricante") or "", capacidad=a["capacidad_modelo"],
                        precio_usd=a["precio_unitario_usd"], origen=org, eta_operacion=a["eta"], url=fila.get("url") or "",
                        fuente=a.get("fuente_precio") or "", origen_precio=("Williams" if estimada else org), division=k,
                        estimada=bool(estimada or org == "Williams")))
    return out, list(dict.fromkeys(avisos))


def candidatos_tres(pl, equipo_id: str, economia: dict | None = None, buscar_en_linea: bool = True, **kw) -> dict:
    """Candidatos de la etapa (costo_total.candidatos_con_avisos) más las divisiones en 1, 2 y 3 unidades, sin repetir id y ordenados por
    C, y las 3 opciones de distinto n (elegir_tres). Devuelve {candidatos, tres, avisos, requerimiento, parametros}. Planta vacía o etapa
    inexistente: listas vacías y el aviso, sin fallar."""
    res = CT.candidatos_con_avisos(pl, equipo_id, economia, buscar_en_linea, **kw)
    req = res.get("requerimiento")
    if req is None:
        return dict(res, candidatos=[], tres=[])
    P = res.get("parametros") or SEL.parametros(pl, economia)
    gen, av = opciones_division(req, res.get("filas") or [], P, res.get("ref_potencia"))
    vistos, todos = set(), []
    for c in list(res["candidatos"]) + gen:
        if c["id"] not in vistos:
            vistos.add(c["id"]); todos.append(c)
    todos.sort(key=lambda c: (c["C"], c["n"]))
    tres = elegir_tres(todos)
    avisos = list(res.get("avisos") or []) + av
    if len({c["n"] for c in tres}) < N_OPCIONES:
        avisos.append(f"Solo hay {len(tres)} opciones de distinto número de unidades para esta etapa.")
    return dict(res, candidatos=todos, tres=tres, avisos=list(dict.fromkeys(avisos)), parametros=P)


# ---------------------------------------------------------------- resultados de la etapa en la planta resuelta
def restricciones(pl):
    """Teoría de restricciones de la planta (motor/lienzo.restricciones), una sola vez para todas las fichas. None si falla."""
    try:
        from . import lienzo as LZ
        return LZ.restricciones(pl, pl)
    except Exception:
        return None


_SIN = object()


def resultados_etapa(pl, equipo_id: str, tr=_SIN) -> dict | None:
    """Lo que la ficha muestra en «Resultados del equipo» y que no depende de la opción: carga demandada (t/h, teoría de restricciones
    de motor/lienzo.py), procesada y salida actuales, estado (fracción de la capacidad nominal) y cierre de energía (kW). None sin el
    equipo resuelto."""
    eq = getattr(pl, "equipos", {}).get(equipo_id) if pl is not None else None
    if eq is None or eq.resultado is None:
        return None
    r = eq.resultado
    carga = _num(r.detalle.get("carga_t_h"))
    out = dict(demanda=carga, procesado=carga, sale=None, estado=1.0, cierre_kW=None)
    if tr is _SIN:
        tr = restricciones(pl)
    v = (tr or {}).get("equipos", {}).get(equipo_id)
    if v:
        out.update(demanda=_num(v.get("demanda")), procesado=_num(v.get("procesado")))
    try:
        from .lienzo import TIPOS_SERVICIO
        ss = [getattr(pl, "salidas", {}).get((equipo_id, p.nombre)) for p in eq.salidas if p.tipo not in TIPOS_SERVICIO]
        out["sale"] = _num(sum(x.m for x in ss if x is not None) / 1000.0)
    except Exception:
        out["sale"] = None
    if "estado" in eq.params and eq.params["estado"].valor is not None:
        out["estado"] = max(0.15, min(1.0, float(eq.params["estado"].valor)))
    try:
        out["cierre_kW"] = _num(r.cierre_energia())
    except Exception:
        out["cierre_kW"] = None
    return out


# ---------------------------------------------------------------- ficha comparativa
def _conveniente(vals: list, criterio: str | None) -> list[bool]:
    """Marca en cada fila los valores más convenientes: «min», «max» o «cien» (más cerca de 100 %). Sin criterio, con menos de 2
    valores o con todos iguales: ninguno."""
    nums = [_num(v) for v in vals]
    ok = [v for v in nums if v is not None]
    if not criterio or len(ok) < 2 or max(ok) - min(ok) <= 1e-9 * max(1.0, abs(max(ok))):
        return [False] * len(vals)
    if criterio == "cien":
        dist = [None if v is None else abs(v - 1.0) for v in nums]
        b = min(d for d in dist if d is not None)
        return [d is not None and abs(d - b) <= 1e-9 for d in dist]
    b = min(ok) if criterio == "min" else max(ok)
    return [v is not None and abs(v - b) <= 1e-9 * max(1.0, abs(b)) for v in nums]


def _fila(etq: str, textos: list[str], nums: list | None = None, criterio: str | None = None, ayuda: str = "", info: str = "") -> dict:
    """info: texto del ⓘ de la fila (para qué y por qué, con las cifras vigentes y su fuente); vacío = sin ⓘ."""
    return dict(etq=etq, valores=textos, conveniente=_conveniente(nums or [None] * len(textos), criterio), criterio=criterio or "", ayuda=ayuda,
                info=info)


def info_costo(d: dict) -> dict:
    """PAT 140 e: textos del ⓘ de las filas de «Costo total» (para qué y por qué de cada ecuación), con las cifras vigentes tomadas del
    detalle del costo (costo_total.costo_total_opcion): las mismas que usa la base de cálculo. Sin detalle, sin textos."""
    if not d:
        return {}
    fv = str(d.get("fuente_valor") or "").strip().split(" (")[0].rstrip(" ,;.")
    fv = (fv[:1].lower() + fv[1:]) if fv else "margen de contribución del rubro (motor/seleccion.py, margen)"
    return {
        "Inversión instalada (n × precio × factor)": (
            f"Para qué: costo de comprar e instalar las n unidades de la opción. Por qué el factor: el precio de catálogo no incluye montaje, "
            f"fundaciones, cañerías, instrumentación ni obras; el factor de instalación ({_f(d.get('f_inst'), 2)}) lo lleva a costo instalado. "
            "Fuente: Supuesto de motor/costos.py (Danish Energy Agency, 2026, hoja 2.a)."),
        "C_inv (inversión anualizada)": (
            f"C_inv = inversión instalada × CRF, con CRF = i(1+i)^N / ((1+i)^N − 1); hoy tasa {_pct(d.get('tasa'), 1)} y {_f(d.get('anios'), 0)} años, "
            f"CRF {_f(d.get('crf'), 4)}. Para qué: pasar la inversión a US$ por año para sumarla con los costos de operación. Por qué: permite "
            "comparar opciones con distinta inversión en la misma base anual. Fuente: tasa y años de la pantalla Economía; fórmula en motor/seleccion.py (crf)."),
        "C_op (energía y mantenimiento)": (
            f"C_op = energía + mantenimiento. Energía = potencia × η_max/η × {_f(d.get('horas'), 0)} h/año de operación × {_f(d.get('precio_kwh_clp'), 3)} $/kWh, "
            f"pasado a US$ con el dólar {_f(d.get('dolar'), 2)} $/US$. Mantenimiento = {_f(d.get('mantencion_pct'), 1)} % de la inversión instalada al año. "
            "Para qué: costo anual de hacer funcionar la opción. Por qué η_max/η: fuera de su punto de diseño el equipo consume más energía por "
            "unidad procesada. Fuente: precio de la electricidad de la pantalla Economía (Supuesto «precio_kwh» de motor/seleccion.py, CNE 2026b); "
            "dólar de motor/costos.py; mantenimiento de motor/factores_costo.py (Peters y Timmerhaus, 1991, Tabla 25)."),
        "C_inef (producción perdida)": (
            f"C_inef = (1 − A) × producción anual × valor unitario (hoy US$ {_f(d.get('valor_unitario_usd'), 2)} por unidad). A es la disponibilidad "
            f"de la etapa con k de n unidades, calculada con el MTBF y el MTTR de cada unidad y el tiempo de mantenimiento preventivo t_MP "
            f"({_pct(d.get('t_mp'), 1)}). Para qué: valorizar la producción que se pierde cuando la etapa está detenida por fallas. Por qué: una "
            f"opción barata pero con baja disponibilidad puede salir más cara; es lo que hace que una unidad de reserva convenga. Fuente: "
            f"motor/costo_total.py (Supuesto «t_mp»); valor unitario: {fv}."),
        "C = C_inv + C_op + C_inef": (
            "Para qué: costo total anual de cada opción, el criterio para comparar las columnas (la más conveniente es la de menor C). Por qué: "
            "junta inversión, operación y pérdidas en una sola cifra anual. Fuente: motor/costo_total.py."),
    }


def _sin_referencias(t: str) -> str:
    """PAT 140 g (pedido de Jaime, 17-11-2026): los textos que ve el usuario no nombran el simulador de referencia del curso."""
    return (t.replace("orden de magnitud del simulador del profesor", "orden de magnitud de referencia")
             .replace("del simulador del profesor", "de referencia").replace("simulador del profesor", "simulador de referencia"))


def _supuesto_conf(c: dict) -> bool:
    f = str(c.get("fuente_confiabilidad") or "")
    if f.startswith("Supuesto"):
        return True
    return any("no trae MTBF" in str(a) for a in c.get("avisos_costo") or [])


def _origen(c: dict) -> str:
    org = c.get("origen") or "sin dato"
    if org == "Williams":
        return "Williams (estimado)"
    if c.get("estimada") or c.get("precio_estimado") or "estimado" in str(c.get("fuente") or "").lower():
        return f"{org} (precio estimado)"
    return org


def _curva(opciones: list[dict], S: float, puntos: int = 41) -> dict:
    """η/η_max de cada opción contra la producción de la etapa Q (misma escala para las 3): con k unidades en operación cada una
    procesa Q/k (Supuesto «reparto» de costo_total.py). Punto de operación en Q = requerida y punto de diseño donde cada unidad
    trabaja en su q_peak."""
    series, picos = [], []
    for c in opciones:
        d = c.get("detalle_costo") or {}
        k = max(1, int(c.get("k") or 1))
        q_op = _num(c.get("q_unidad")) or (S / k)
        qp = _num(d.get("q_peak")) or _num(c.get("capacidad")) or q_op or 1.0
        a = _num(d.get("a_curva"))
        escala = q_op / S if S > 0 else 1.0 / k          # carga por unidad por cada unidad de producción de la etapa
        series.append((c, qp, a, escala))
        picos.append(qp / escala if escala > 0 else S)
    xmax = min(3.0 * S, max([1.5 * S] + [1.15 * p for p in picos])) if S > 0 else 1.0
    xs = [xmax * i / (puntos - 1) for i in range(puntos)]
    out = []
    for (c, qp, a, escala), pico in zip(series, picos):
        eta = [round(CT.eta_relativa(x * escala, qp, a=a), 5) for x in xs]
        out.append(dict(id=c["id"], etq=c.get("etiqueta") or c.get("modelo"), eta=eta,
                        op=dict(x=round(S, 6), eta=round(CT.eta_relativa(S * escala, qp, a=a), 5)),
                        diseno_x=round(pico, 6) if pico <= xmax else None))
    return dict(x=[round(x, 6) for x in xs], series=out, y_min=0.25, y_max=1.02, a_supuesto=CT.A_CURVA,
                fuente=("Curva η(q) = η_max·(1 − a·(q/q_peak − 1)²) de motor/costo_total.py; a = 0,6 y q_peak = capacidad nominal de la ficha: "
                        "Supuestos «a_curva» y «q_peak» (sin puntos (q, η) de fabricante)."))


def comparativa(opciones: list[dict], etapa: dict, resultados: dict | None = None) -> dict:
    """Ficha comparativa de hasta 3 opciones (columnas) de una etapa o de un equipo auxiliar.
    etapa: equipo, nombre, requerida, unidad y, en la planta real, tph_por_unidad (t/h de carga por unidad de la etapa).
    resultados: resultados_etapa (solo planta real; sin él no va la sección «Resultados del equipo»).
    Devuelve {equipo, nombre, unidad, requerida, regla, opciones (encabezados), secciones (filas alineadas con un valor por opción y la
    marca «conveniente»), curva (η/η_max contra la producción de la etapa, misma escala) y base (base de cálculo de C)}."""
    ops = list(opciones or [])
    S = _num(etapa.get("requerida")) or 0.0
    u = etapa.get("unidad") or ""
    tph_u = _num(etapa.get("tph_por_unidad")) or 1.0
    cab = []
    for c in ops:
        cab.append(dict(id=c["id"], titulo=f"{c.get('n')} × {c.get('modelo')}", etiqueta=c.get("etiqueta") or c.get("modelo"),
                        fabricante=c.get("fabricante") or "sin dato", origen=_origen(c), url=c.get("url") or "",
                        fuente=str(c.get("fuente") or "sin dato")[:400], n=int(c.get("n") or 0), k=int(c.get("k") or 0)))
    secs = []
    det = [c.get("detalle_costo") or {} for c in ops]
    inst_tph = [(_num(c.get("instalada_t_h")) if _num(c.get("instalada_t_h")) is not None
                 else (_num(c.get("capacidad")) or 0.0) * int(c.get("n") or 0) * tph_u) for c in ops]
    # Resultados del equipo (planta real)
    if resultados:
        dem, proc0, sale0 = resultados.get("demanda"), resultados.get("procesado"), resultados.get("sale")
        est = resultados.get("estado") or 1.0
        efec = [x * est for x in inst_tph]
        proc = [None if dem is None else min(dem, e) for e in efec]
        sal = [None if (sale0 is None or not proc0 or p is None) else sale0 * p / proc0 for p in proc]
        util = [None if (dem is None or not e) else dem / e for e in efec]
        cie = resultados.get("cierre_kW")
        secs.append(dict(titulo="Resultados del equipo", filas=[
            _fila("Carga demandada", [_f(dem, 2) + " t/h"] * len(ops)),
            _fila("Carga procesada", [_f(p, 2) + " t/h" for p in proc], proc, "max"),
            _fila("Salida de proceso", [_f(s, 2) + " t/h" for s in sal], sal, "max"),
            _fila("Capacidad efectiva", [_f(e, 2) + " t/h" for e in efec], efec, None, "Capacidad instalada × estado del equipo"),
            _fila("Utilización", [_pct(x, 1) for x in util], util, None, "Carga demandada / capacidad efectiva"),
            _fila("Cierre de energía", [_f(cie, 3) + " kW"] * len(ops))],
            nota=("Con la opción instalada: capacidad efectiva = capacidad instalada × estado; procesada = mínimo entre la demanda y la "
                  "capacidad efectiva; la salida se escala con lo procesado. El balance de materia y energía no cambia.")))
    # Selección comercial
    def _cap(v):
        return "sin dato" if v is None else f"{_f(v, 2 if v < 100 else (1 if v < 1000 else 0))} {u}"

    mtbf_t, mttr_t, mtbf_n = [], [], []
    for c, d in zip(ops, det):
        mt, mr = _num(c.get("mtbf_h")) or _num(d.get("mtbf_h")), _num(c.get("mttr_h")) or _num(d.get("mttr_h"))
        sup = _supuesto_conf(c)
        mtbf_t.append(("sin dato; se usa " if sup else "") + _f(mt, 0) + " h" + (" (Supuesto)" if sup else ""))
        mttr_t.append(("sin dato; se usa " if sup else "") + _f(mr, 1) + " h" + (" (Supuesto)" if sup else ""))
        mtbf_n.append(mt)
    caps = [_num(c.get("capacidad")) for c in ops]
    insts = [None if v is None else v * int(c.get("n") or 0) for v, c in zip(caps, ops)]
    Au = [_num(c.get("A_equipo")) for c in ops]
    A = [_num(c.get("A")) for c in ops]
    secs.append(dict(titulo="Selección comercial", filas=[
        _fila("Modelo y fabricante", [f"{c.get('modelo')} · {c.get('fabricante') or 'sin dato'}" for c in ops]),
        _fila("Origen del dato", [_origen(c) for c in ops]),
        _fila("Unidades en paralelo (n)", [str(c.get("n")) for c in ops]),
        _fila("Necesarias (k)", [str(c.get("k")) for c in ops]),
        _fila("Capacidad por unidad", [_cap(v) for v in caps]),
        _fila("Capacidad instalada", [_cap(v) for v in insts]),
        _fila("MTBF de una unidad", mtbf_t, mtbf_n, "max"),
        _fila("MTTR de una unidad", mttr_t, [_num(c.get("mttr_h")) or _num(d.get("mttr_h")) for c, d in zip(ops, det)], "min"),
        _fila("Disponibilidad de una unidad", [_pct(v, 2) for v in Au], Au, "max", "A = 1 − (MTTR/(MTBF + MTTR) + t_MP)"),
        _fila("Disponibilidad de la etapa (k de n)", [_pct(v, 2) + f" ({c.get('k')} de {c.get('n')})" for v, c in zip(A, ops)], A, "max")],
        nota="Fuente de MTBF y MTTR: " + "; ".join(dict.fromkeys(_sin_referencias(str(c.get("fuente_confiabilidad") or "la ficha del equipo"))[:160] for c in ops)) + "."))
    # Eficiencia en operación
    qp = [_num(d.get("q_peak")) or _num(c.get("capacidad")) for c, d in zip(ops, det)]
    qu = [_num(c.get("q_unidad")) for c in ops]
    rel = [None if (q is None or not p) else q / p for q, p in zip(qu, qp)]
    er = [_num(c.get("eta_relativa")) if _num(c.get("eta_relativa")) is not None else _num(c.get("eta_operacion")) for c in ops]
    kw = [_num(d.get("potencia_operando_kw")) for d in det]
    kwh = [_num(d.get("energia_kwh_anio")) for d in det]
    secs.append(dict(titulo="Eficiencia en operación", filas=[
        _fila("Carga por unidad en operación", [("sin dato" if r is None else _pct(r, 1) + " del punto de diseño") for r in rel], rel, "cien"),
        _fila("Eficiencia relativa η/η_max", [_pct(v, 1) for v in er], er, "max"),
        _fila("Punto de diseño por unidad", [_cap(v) for v in qp]),
        _fila("Potencia en operación", [("sin dato" if (v is None or not d.get("potencia_unidad_kw")) else _f(v, 1) + " kW") for v, d in zip(kw, det)],
              [v if d.get("potencia_unidad_kw") else None for v, d in zip(kw, det)], "min"),
        _fila("Energía al año (con η)", [("sin dato" if (v is None or not d.get("potencia_unidad_kw")) else _f(v, 0) + " kWh/año") for v, d in zip(kwh, det)],
              [v if d.get("potencia_unidad_kw") else None for v, d in zip(kwh, det)], "min")],
        nota="Las k unidades en operación se reparten la carga (Supuesto «reparto»); la de reserva espera detenida."))
    # Costo total
    inv = [_num(d.get("inversion_usd")) for d in det]
    pu = [_num(c.get("precio_usd")) for c in ops]
    d0 = next((d for d in det if d), {})
    info = info_costo(d0)
    filas_c = [_fila("Precio de una unidad", [_usd(v) for v in pu], pu, None, "Unidades de distinto tamaño: se compara la inversión, no el precio"),
               _fila("Inversión instalada (n × precio × factor)", [_usd(v) for v in inv], inv, "min",
                     info=info.get("Inversión instalada (n × precio × factor)", ""))]
    for clave, etq in (("C_inv", "C_inv (inversión anualizada)"), ("C_op", "C_op (energía y mantenimiento)"),
                       ("C_inef", "C_inef (producción perdida)"), ("C", "C = C_inv + C_op + C_inef")):
        vals = [_num(c.get(clave)) for c in ops]
        filas_c.append(_fila(etq, [("sin dato" if v is None else _usd(v) + "/año") for v in vals], vals, "min", info=info.get(etq, "")))
    secs.append(dict(titulo="Costo total", filas=filas_c, nota="Fuente del precio: en el encabezado de cada columna."))
    base = ""
    if d0:
        base = (f"Base de cálculo (US$ por año): C_inv = n × precio × factor de instalación {_f(d0.get('f_inst'), 2)} × CRF {_f(d0.get('crf'), 4)} "
                f"(tasa {_pct(d0.get('tasa'), 1)} y {_f(d0.get('anios'), 0)} años de Economía); C_op = energía (potencia × η_max/η × "
                f"{_f(d0.get('horas'), 0)} h/año × {_f(d0.get('precio_kwh_clp'), 3)} $/kWh) + mantenimiento ({_f(d0.get('mantencion_pct'), 1)} % "
                f"de la inversión); C_inef = (1 − A) × producción anual × valor unitario (US$ {_f(d0.get('valor_unitario_usd'), 2)} por unidad). "
                f"Dólar {_f(d0.get('dolar'), 2)} $/US$. t_MP {_pct(d0.get('t_mp'), 1)} (Supuesto «t_mp»). Motor: motor/costo_total.py.")
    return dict(equipo=etapa.get("equipo"), nombre=etapa.get("nombre") or "", unidad=u, requerida=S, regla=REGLA, opciones=cab, secciones=secs,
                curva=_curva(ops, S) if ops and S > 0 else None, base=base)


def ficha_etapa(pl, equipo_id: str, tres: list[dict], req: dict | None = None, tr=_SIN) -> dict | None:
    """Ficha comparativa de las 3 opciones de una etapa de la planta real (comparativa con sus resultados_etapa). tr: restricciones(pl)
    ya calculadas (para no repetirlas en cada etapa)."""
    if not tres:
        return None
    if req is None:
        req = next((r for r in SEL.requerimientos(pl) if r["equipo"] == equipo_id), None)
    if req is None:
        return None
    return comparativa(tres, dict(equipo=equipo_id, nombre=req.get("nombre"), requerida=req["requerida"], unidad=req["unidad"],
                                  tph_por_unidad=req.get("tph_por_unidad")), resultados_etapa(pl, equipo_id, tr))
