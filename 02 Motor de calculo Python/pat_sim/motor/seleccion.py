"""Selección de equipos comerciales después del diseño teórico (PAT 135, tarea T14, 05-11-2026).

Lo pide el profesor Torres en su correo del 04-11-2026 (01 Requisitos y diseno/Correo_profesor_Torres_04nov2026_proceso_iterativo.md):
no existen equipos del tamaño justo, así que se eligen alternativas comerciales, eventualmente varias en paralelo que sumen al
menos la capacidad; cada equipo trae su confiabilidad, que da la disponibilidad; con esa selección se vuelve al flujo para la
teoría de restricciones y el costo de ineficiencia total, que dice si hacen falta redundancias.

Método (PAT 135)
- Capacidad requerida de cada equipo: la carga que resolvió el balance, en la magnitud con que motor/costeo.py costea su tipo
  (t/h de carga, kg/h de agua evaporada o kW térmicos). El catálogo comercial está en la base (datos/mantenedor.py, tabla
  catalogo_comercial, editable en el mantenedor con la clave del profesor).
- Alternativas por modelo del tipo: k = ⌈requerida / capacidad del modelo⌉ unidades iguales en paralelo (k = 1 es «un equipo más
  grande») y la misma con una unidad más (n = k + 1, redundancia).
- Disponibilidad de una unidad A = MTBF/(MTBF + MTTR). Etapa con n en paralelo y k necesarias (k de n, binomial):
  A_etapa = Σ_{i=k..n} C(n, i)·A^i·(1 − A)^(n−i). Línea en serie: A_línea = Π A_etapa (unidades independientes).
- Capacidad efectiva esperada: instalada × A = n·c·A; con la demanda D, la capacidad útil esperada es E[mín(i·c, D)] con i
  binomial (n, A). Teoría de restricciones con la capacidad efectiva referida al producto: el cuello de botella es la etapa
  de menor capacidad efectiva.
- Costo de ineficiencia total por año = producción perdida esperada (D − E[mín(i·c, D)]) × margen + capacidad ociosa esperada
  E[máx(mín(i, k)·c − D, 0)] × margen × fracción de ociosidad (la unidad de reserva espera detenida), las dos en t de producto
  por las horas de operación del año.
- Costo anualizado de una unidad: precio de catálogo actualizado con el CEPCI (costeo.actualizar) y, si el catálogo no trae
  precio, la referencia de costeo.py escalada con Williams; por el factor de instalación de costos.py y el factor de
  recuperación de capital con la tasa y los años de Economía. Se recomienda la redundancia cuando el ahorro de ineficiencia
  supera el costo anualizado de la unidad adicional.
- Aplicar la selección deja en el equipo el modelo, las unidades (n y k), MTBF y MTTR de una unidad y la capacidad instalada
  total en «capacidad» (t/h de carga). El balance no cambia: la capacidad no limita el balance (motor/equipos.capacidad_param),
  así que las cifras de energía del Excel de Agrozzi (requisito R9) siguen iguales. La Línea (motor/linea_fluida.py) usa el
  MTBF y el MTTR del equipo y, con n unidades, los de una etapa equivalente con la misma capacidad esperada.
Supuestos con justificación en SUPUESTOS. Sin fuente segura, las cifras del catálogo de partida son Supuesto (ver mantenedor).
"""
from __future__ import annotations
import math
from datetime import date
from . import costeo as CO, costos
from .operacion import Supuesto

N_MAX = 10                       # unidades en paralelo como máximo por modelo
_SD = "sin dato de la planta ni fuente segura"
SUPUESTOS = {s.clave: s for s in [
    Supuesto("independencia", "Fallas de las unidades", 0.0, "—",
             "Independientes y con la misma disponibilidad (modelo binomial k de n); sin fallas de causa común ni reparación "
             "compartida; " + _SD),
    Supuesto("horas", "Horas de operación al año sin caldera con horas", 7200.0, "h/año",
             "300 días de 24 h cuando la planta no trae sus horas de temporada (caldera o generador con horas); " + _SD),
    Supuesto("frac_ocioso", "Costo de la capacidad ociosa", 0.25, "fracción del margen por t",
             "El mismo de motor/mc_economico.py: costos fijos de la capacidad sin uso como una cuarta parte del margen; " + _SD),
    Supuesto("reserva", "Unidades de reserva", 0.0, "—",
             "Con n = k + 1 operan k unidades y la de reserva queda detenida en espera hasta que otra falla: no suma capacidad "
             "ociosa ni costo de ociosidad (su costo es la anualidad de la inversión); " + _SD),
    Supuesto("serie", "Línea en serie", 0.0, "—",
             "La línea se detiene si una etapa no tiene las k unidades necesarias (sin pulmones entre etapas); la pestaña Línea "
             "simula los pulmones"),
]}


# ---------------------------------------------------------------- confiabilidad
def disponibilidad(mtbf: float, mttr: float) -> float:
    """A = MTBF/(MTBF + MTTR)."""
    mtbf, mttr = float(mtbf), float(mttr)
    if mtbf <= 0 or mttr < 0:
        raise ValueError("MTBF debe ser positivo y MTTR no negativo.")
    return mtbf / (mtbf + mttr)


def prob_disponibles(n: int, A: float) -> list[float]:
    """P(i unidades disponibles), i = 0..n, binomial (n, A)."""
    n = int(n)
    if n < 0 or not 0 <= A <= 1:
        raise ValueError("n debe ser ≥ 0 y A estar entre 0 y 1.")
    return [math.comb(n, i) * A ** i * (1 - A) ** (n - i) for i in range(n + 1)]


def k_de_n(A: float, n: int, k: int) -> float:
    """Disponibilidad de una etapa que necesita k de sus n unidades: P(i ≥ k)."""
    if k > n:
        return 0.0
    if k <= 0:
        return 1.0
    return float(sum(prob_disponibles(n, A)[k:]))


def serie(disponibilidades) -> float:
    """Etapas en serie: producto de las disponibilidades."""
    out = 1.0
    for a in disponibilidades:
        out *= float(a)
    return out


def capacidad_esperada(c: float, n: int, A: float) -> float:
    """Capacidad disponible esperada: n·c·A."""
    return float(n) * float(c) * float(A)


def capacidad_util(c: float, n: int, A: float, D: float) -> float:
    """E[mín(i·c, D)]: capacidad esperada limitada por la demanda D."""
    return float(sum(p * min(i * c, D) for i, p in enumerate(prob_disponibles(n, A))))


def capacidad_ociosa(c: float, n: int, A: float, D: float, k: int | None = None) -> float:
    """E[máx(mín(i, k)·c − D, 0)]: capacidad en operación que no se usa. Con k, a lo más k unidades operan y las de reserva
    quedan detenidas en espera (Supuesto «reserva»); sin k, todas las disponibles operan."""
    k = n if k is None else int(k)
    return float(sum(p * max(min(i, k) * c - D, 0.0) for i, p in enumerate(prob_disponibles(n, A))))


def crf(tasa: float, anios: float) -> float:
    """Factor de recuperación de capital i(1+i)^N/((1+i)^N − 1); con tasa 0, 1/N."""
    tasa, anios = float(tasa), float(anios)
    if anios <= 0:
        raise ValueError("Los años de evaluación deben ser positivos.")
    if abs(tasa) < 1e-12:
        return 1.0 / anios
    f = (1 + tasa) ** anios
    return tasa * f / (f - 1)


def _pv(eq, clave):
    p = eq.params.get(clave)
    if p is None or p.valor is None or isinstance(p.valor, bool):
        return None
    try:
        v = float(p.valor)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def fallas_equivalentes(eq):
    """(MTBF, MTTR, nota) que usa la Línea para un equipo con selección aplicada; None si no tiene MTBF y MTTR propios.
    Con n > 1 unidades, la Línea simula la etapa como un equipo que se detiene entero: se le da una disponibilidad equivalente
    A_eq = E[mín(i·c, D)] / mín(n·c, D), con el MTTR de una unidad y MTBF = MTTR·A_eq/(1 − A_eq)."""
    mt, mr = _pv(eq, "mtbf_h"), _pv(eq, "mttr_h")
    if mt is None or mr is None or mt <= 0 or mr < 0:
        return None
    modelo = str(eq.params["modelo"].valor or "modelo elegido") if "modelo" in eq.params else "modelo elegido"
    n = int(_pv(eq, "unidades") or 1)
    if n <= 1:
        return mt, mr, f"Selección de equipos: {modelo}"
    A = disponibilidad(mt, mr)
    cap = eq.capacidad_efectiva() or 0.0
    carga = None
    if eq.resultado is not None:
        try:
            carga = float(eq.resultado.detalle.get("carga_t_h") or 0) or None
        except (TypeError, ValueError):
            carga = None
    c = cap / n if cap else 1.0
    D = carga or n * c
    base = min(n * c, D)
    frac = capacidad_util(c, n, A, D) / base if base > 0 else A
    nota = f"Selección de equipos: {n} × {modelo}, etapa equivalente (A = {frac:.4f})".replace(".", ",")
    if frac >= 1 - 1e-12:
        return mt, 0.0, nota
    return mr * frac / (1 - frac), mr, nota


# ---------------------------------------------------------------- capacidad requerida
def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def _excluido(eq) -> bool:
    return eq.tipo.startswith(("caldera", "generador", "alimentacion"))


def requerimientos(pl) -> list[dict]:
    """Equipos de la planta resuelta con capacidad nominal declarable y carga: la capacidad requerida en la magnitud del
    catálogo (la de costeo._LINEA) y su conversión a t/h de carga. Sin magnitud propia, t/h de carga («generico»)."""
    if not getattr(pl, "resuelta", False):
        return []
    out = []
    for k, eq in pl.equipos.items():
        if "capacidad" not in eq.params or eq.resultado is None or _excluido(eq):
            continue
        carga = _num(eq.resultado.detalle.get("carga_t_h"))
        if not carga or carga <= 0:
            continue
        tipo_cat, clave, magnitud, unidad, S = "generico", "generico", "Capacidad", "t/h", carga
        if eq.tipo in CO._LINEA:
            clave, _n, _q, magnitud, unidad, det, _s, _c = CO._LINEA[eq.tipo]
            S = _num(eq.resultado.detalle.get(det)) if det != "carga_t_h" else carga
            tipo_cat = eq.tipo
            if not S or S <= 0:
                tipo_cat, magnitud, unidad, S = eq.tipo, "Capacidad", "t/h", carga
        out.append(dict(equipo=k, nombre=eq.nombre, tipo=eq.tipo, tipo_catalogo=tipo_cat, clave_costeo=clave, magnitud=magnitud,
                        unidad=unidad, requerida=float(S), carga_t_h=float(carga), tph_por_unidad=float(carga) / float(S),
                        actual=seleccion_actual(eq)))
    return out


def seleccion_actual(eq) -> dict | None:
    """Selección aplicada en el equipo (modelo, n, k, MTBF, MTTR y capacidad en t/h) o None."""
    n = _pv(eq, "unidades")
    modelo = str(eq.params["modelo"].valor or "") if "modelo" in eq.params else ""
    if not n or not modelo:
        return None
    return dict(modelo=modelo, n=int(n), k=int(_pv(eq, "unidades_requeridas") or n), mtbf_h=_pv(eq, "mtbf_h"), mttr_h=_pv(eq, "mttr_h"),
                capacidad_t_h=_pv(eq, "capacidad"))


# ---------------------------------------------------------------- parámetros económicos
def margen(rubro: str, economia: dict | None = None, desafio: dict | None = None) -> tuple[float, str]:
    """Margen de contribución ($/t de producto) y su fuente: economia["margen"] si existe; si no, el Supuesto de
    motor/mc_economico.py del rubro, acotado al precio de venta del desafío (el margen no puede superar el precio)."""
    from . import mc_economico as MC
    economia = economia or {}
    if _num(economia.get("margen")):
        return float(economia["margen"]), "Economía (margen de la sesión)"
    m = MC.margen_defecto(rubro); fuente = f"Supuesto de motor/mc_economico.py ({MC.SUPUESTOS['margen'].justificacion})"
    dolar = _num(economia.get("dolar")) or costos.DOLAR
    for p in (desafio or {}).get("precios") or []:
        f_mon = {"US$": dolar, "$": 1.0, "€": costos.EURO}.get(p.get("moneda"))
        f_uni = {"t": 1.0, "kg": 1000.0}.get(p.get("unidad"))
        v = _num(p.get("precio"))
        if f_mon and f_uni and v:
            precio = v * f_mon * f_uni
            if precio < m:
                return precio, f"Precio de venta del desafío ({p.get('producto', '')}), cota del margen; {p.get('fuente', '')}".strip()
            break
    return m, fuente


def parametros(pl, economia: dict | None = None, desafio: dict | None = None, f_inst: float = costos.F_INSTALACION,
               cepci_hoy: float = CO.CEPCI_HOY) -> dict:
    """Margen, horas, tasa, años, dólar, fracción de ociosidad, factor de instalación y producto por t de carga de cada equipo."""
    from .resumen import _horas
    from . import lienzo as LZ
    economia = economia or {}
    if desafio is None:
        p = getattr(pl, "_p", None)
        desafio = p.get("desafio") if isinstance(p, dict) else None
    mg, f_mg = margen(pl.rubro, economia, desafio)
    h = _horas(pl)
    f_h = "Horas de la temporada de la planta (caldera o generador)" if h else "Supuesto: " + SUPUESTOS["horas"].justificacion
    h = h or SUPUESTOS["horas"].valor
    plan, avisos = None, []
    try:
        tr = LZ.restricciones(pl, pl) if pl.resuelta else None
        plan = _num(tr["produccion_plan"]) if tr else None
    except Exception:
        plan = None
    if not plan:
        avisos.append("La planta no tiene un producto final identificado: la producción se mide en t de carga de cada equipo.")
    return dict(margen=mg, fuente_margen=f_mg, horas=float(h), fuente_horas=f_h, tasa=float(economia.get("tasa", 0.10)),
                anios=float(economia.get("anios", 20)), dolar=float(economia.get("dolar", costos.DOLAR)),
                frac_ocioso=SUPUESTOS["frac_ocioso"].valor, f_inst=float(f_inst), cepci_hoy=float(cepci_hoy), plan=plan, avisos=avisos)


# ---------------------------------------------------------------- catálogo y alternativas
def filas_catalogo(req: dict, catalogo: list[dict]) -> list[dict]:
    """Modelos del tipo del equipo en su unidad; si no hay, los genéricos en t/h de carga (y se marca)."""
    filas = [f for f in catalogo if f["tipo"] == req["tipo_catalogo"] and (f.get("unidad") or "") == req["unidad"]]
    if filas:
        return filas
    return [dict(f, _generico=True) for f in catalogo if f["tipo"] == "generico"]


def precio_unitario(fila: dict, clave_costeo: str, cepci_hoy: float = CO.CEPCI_HOY) -> dict:
    """Precio de una unidad en US$ de hoy: el del catálogo actualizado con el CEPCI de su año o, sin precio, la referencia de
    costeo.py escalada con Williams al tamaño del modelo."""
    S = float(fila["capacidad"])
    if _num(fila.get("precio_usd")):
        C, anio, fuente = float(fila["precio_usd"]), fila.get("anio_precio"), fila.get("fuente_precio") or ""
        cref = CO.cepci_de(anio)
    else:
        clave = "generico" if fila.get("_generico") else clave_costeo
        p = CO.precio_bibliografia(clave, S)
        n = CO.exponente(clave)[0]
        C = p["precio_usd"] if p.get("exacto") else CO.williams(p["precio_usd"], p["tamano"], S, n)
        anio, cref = p["anio"], p["cepci_ref"]
        fuente = f"{p['fuente']}, escalado con Williams (n = {n:g})".replace(".", ",")
    C_hoy, fc = CO.actualizar(C, cref, cepci_hoy)
    return dict(precio_usd=float(C_hoy), precio_ref_usd=float(C), anio=anio, factor_cepci=float(fc), fuente=fuente)


def evaluar(req: dict, fila: dict, n: int, k: int, P: dict, precio: dict | None = None) -> dict:
    """Una alternativa: n unidades del modelo de la fila, k necesarias. Disponibilidad, capacidades, costos e ineficiencia."""
    from . import linea_fluida as LF
    c = float(fila["capacidad"])
    if fila.get("_generico"):
        c_tph = c                                  # el genérico está en t/h de carga
    else:
        c_tph = c * req["tph_por_unidad"]
    mtbf, mttr = _num(fila.get("mtbf_h")), _num(fila.get("mttr_h"))
    f_conf = fila.get("fuente_confiabilidad") or ""
    if mtbf is None or mttr is None:
        cat = LF.categoria(req["tipo"]); mtbf, mttr = LF.FALLAS_TIPO[cat]
        f_conf = f"Supuesto PAT 134 de motor/linea_fluida.py (FALLAS_TIPO, {cat}): el modelo no trae MTBF y MTTR"
    A = disponibilidad(mtbf, mttr)
    D = req["carga_t_h"]
    fp = (P["plan"] / D) if P.get("plan") else 1.0       # t de producto por t de carga de este equipo
    util = capacidad_util(c_tph, n, A, D); ocio = capacidad_ociosa(c_tph, n, A, D, k)
    perdida_t = max(0.0, D - util) * fp * P["horas"]; ociosa_t = ocio * fp * P["horas"]
    c_perd = perdida_t * P["margen"]; c_ocio = ociosa_t * P["margen"] * P["frac_ocioso"]
    precio = precio or precio_unitario(fila, req["clave_costeo"], P["cepci_hoy"])
    inv = n * precio["precio_usd"] * P["f_inst"] * P["dolar"]
    anual = inv * crf(P["tasa"], P["anios"])
    return dict(equipo=req["equipo"], modelo=fila["modelo"], tipo_catalogo=fila["tipo"], capacidad_modelo=c, unidad=fila.get("unidad") or req["unidad"],
                n=int(n), k=int(k), redundante=n > k, instalada=n * c, instalada_t_h=n * c_tph, capacidad_modelo_t_h=c_tph,
                mtbf_h=float(mtbf), mttr_h=float(mttr), fuente_confiabilidad=f_conf, A_unidad=A, A_etapa=k_de_n(A, n, k),
                cap_esperada_t_h=capacidad_esperada(c_tph, n, A), cap_util_t_h=util, cap_ociosa_t_h=ocio, factor_producto=fp,
                cap_esperada_producto=capacidad_esperada(c_tph, n, A) * fp, perdida_t_anio=perdida_t, ociosa_t_anio=ociosa_t,
                costo_perdida_clp=c_perd, costo_ociosa_clp=c_ocio, ineficiencia_clp=c_perd + c_ocio, precio_unitario_usd=precio["precio_usd"],
                fuente_precio=precio["fuente"], anio_precio=precio["anio"], inversion_clp=inv, anual_clp=anual,
                total_clp=anual + c_perd + c_ocio, categoria=fila.get("categoria") or "Supuesto", generico=bool(fila.get("_generico")),
                etiqueta=(f"{n} × {fila['modelo']}" + (f" ({k} de {n}, con redundancia)" if n > k else "")))


def alternativas(req: dict, filas: list[dict], P: dict, n_max: int = N_MAX, redundancia: bool = True) -> list[dict]:
    """Por cada modelo: k = ⌈requerida/capacidad⌉ unidades (k = 1, un equipo más grande) y, si redundancia, k + 1."""
    out = []
    for f in filas:
        c = _num(f.get("capacidad"))
        if not c or c <= 0:
            continue
        S = req["carga_t_h"] if f.get("_generico") else req["requerida"]
        k = max(1, math.ceil(S / c - 1e-9))
        if k > n_max:
            continue
        precio = precio_unitario(f, req["clave_costeo"], P["cepci_hoy"])
        for n in ((k, k + 1) if redundancia else (k,)):
            out.append(evaluar(req, f, n, k, P, precio))
    return sorted(out, key=lambda a: (a["redundante"], a["total_clp"]))


def decidir_redundancia(base: dict, con: dict) -> dict:
    """Compara el ahorro de ineficiencia de agregar una unidad con su costo anualizado."""
    ahorro = base["ineficiencia_clp"] - con["ineficiencia_clp"]
    costo = con["anual_clp"] - base["anual_clp"]
    return dict(modelo=base["modelo"], n=base["n"], n_red=con["n"], ahorro_clp=ahorro, costo_clp=costo, neto_clp=ahorro - costo,
                recomendar=ahorro > costo, A_sin=base["A_etapa"], A_con=con["A_etapa"])


def seleccionar(pl, catalogo: list[dict] | None = None, economia: dict | None = None, desafio: dict | None = None,
                n_max: int = N_MAX, bd=None, f_inst: float = costos.F_INSTALACION, cepci_hoy: float = CO.CEPCI_HOY) -> dict:
    """Alternativas de cada equipo, la recomendada (menor costo anual total = anualidad + ineficiencia) y la decisión de
    redundancia de su modelo. catalogo: filas de la tabla catalogo_comercial (por omisión, desde la base o la semilla)."""
    if catalogo is None:
        from ..datos import mantenedor as M
        catalogo = M.catalogo_comercial(bd)
    P = parametros(pl, economia, desafio, f_inst, cepci_hoy)
    etapas, avisos = [], list(P["avisos"])
    for req in requerimientos(pl):
        filas = filas_catalogo(req, catalogo)
        alts = alternativas(req, filas, P, n_max)
        e = dict(req, alternativas=alts, generico=bool(filas and filas[0].get("_generico")), mejor=None, recomendada=None, redundancia=None)
        base = [a for a in alts if not a["redundante"]]
        if not base:
            avisos.append(f"{req['equipo']}: el catálogo no tiene modelos que sumen la capacidad con {n_max} unidades o menos.")
            etapas.append(e); continue
        if e["generico"]:
            avisos.append(f"{req['equipo']}: sin tamaños propios en el catálogo; se usan los genéricos en t/h de carga.")
        mejor = min(base, key=lambda a: a["total_clp"])
        con = next((a for a in alts if a["redundante"] and a["modelo"] == mejor["modelo"]), None)
        dec = decidir_redundancia(mejor, con) if con else None
        e.update(mejor=mejor, recomendada=con if dec and dec["recomendar"] else mejor, redundancia=dec)
        etapas.append(e)
    return dict(etapas=etapas, parametros=P, avisos=avisos)


def analizar_linea(elegidas: list[dict], plan: float | None = None) -> dict:
    """Teoría de restricciones con la capacidad efectiva esperada (referida al producto) y disponibilidad de la línea en serie.
    elegidas: alternativas (una por etapa) de evaluar()."""
    if not elegidas:
        return dict(etapas=[], cuello=None, A_linea=None, capacidad_linea=None, plan=plan)
    filas = []
    for a in elegidas:
        filas.append(dict(equipo=a["equipo"], modelo=a["modelo"], n=a["n"], k=a["k"], A_etapa=a["A_etapa"], instalada_producto=a["instalada_t_h"] * a["factor_producto"],
                          efectiva_producto=a["cap_esperada_producto"], util_producto=a["cap_util_t_h"] * a["factor_producto"],
                          ineficiencia_clp=a["ineficiencia_clp"]))
    cuello = min(filas, key=lambda f: f["efectiva_producto"])
    for f in filas:
        f["cuello"] = f is cuello
        f["utilizacion"] = (plan / f["efectiva_producto"]) if plan and f["efectiva_producto"] > 0 else None
    return dict(etapas=filas, cuello=cuello["equipo"], A_linea=serie(f["A_etapa"] for f in filas),
                capacidad_linea=cuello["efectiva_producto"], plan=plan,
                produccion_esperada=min([plan] + [f["util_producto"] for f in filas]) if plan else None,
                ineficiencia_clp=sum(f["ineficiencia_clp"] for f in filas))


# ---------------------------------------------------------------- aplicar a la planta
def aplicar(pl, elecciones: dict) -> int:
    """Deja la selección en cada equipo: modelo, unidades (n y k), MTBF y MTTR de una unidad y capacidad instalada total
    (t/h de carga). elecciones: {equipo: alternativa de evaluar()}. No resuelve de nuevo: el balance no cambia."""
    hoy = date.today().isoformat(); n_ok = 0
    for eid, a in elecciones.items():
        eq = pl.equipos.get(eid)
        if eq is None or a is None or "unidades" not in eq.params:
            continue
        cat = a.get("categoria") or "Supuesto"
        f = f"Selección de equipos (PAT 135, {hoy}): {a['etiqueta']}; catálogo comercial ({cat})"
        eq.set("modelo", a["modelo"], categoria=cat, fuente=f)
        eq.set("unidades", int(a["n"]), categoria=cat, fuente=f)
        eq.set("unidades_requeridas", int(a["k"]), categoria=cat, fuente=f)
        eq.set("mtbf_h", float(a["mtbf_h"]), categoria=cat, fuente=a.get("fuente_confiabilidad") or f)
        eq.set("mttr_h", float(a["mttr_h"]), categoria=cat, fuente=a.get("fuente_confiabilidad") or f)
        inst = f"{a['instalada']:g} {a['unidad']}".replace(".", ",")
        eq.set("capacidad", float(a["instalada_t_h"]), categoria=cat, fuente=f"{f}; {inst} instalados",
               justificacion="Capacidad instalada total del modelo comercial elegido, en t/h de carga; no limita el balance")
        n_ok += 1
    return n_ok


def quitar(pl, ids=None) -> int:
    """Borra la selección de los equipos (la capacidad queda como estaba)."""
    n = 0
    for k, eq in pl.equipos.items():
        if (ids is None or k in ids) and "unidades" in eq.params and seleccion_actual(eq):
            eq.set("modelo", ""); [eq.set(c, None) for c in ("unidades", "unidades_requeridas", "mtbf_h", "mttr_h")]; n += 1
    return n


def elegida_actual(etapa: dict) -> dict | None:
    """La alternativa que coincide con la selección aplicada en el equipo (modelo y n), si existe."""
    act = etapa.get("actual")
    if not act:
        return None
    return next((a for a in etapa["alternativas"] if a["modelo"] == act["modelo"] and a["n"] == act["n"]), None)


# ---------------------------------------------------------------- gancho para traer más tamaños con Tavily
def tamanos_web(tipo: str, clave: str | None, consulta: str | None = None, dolar: float = costos.DOLAR, euro: float = costos.EURO,
                _abrir=None) -> list[dict]:
    """Candidatos a modelos comerciales desde internet (Tavily, datos/precios_web.py): capacidad y precio leídos de cada página,
    con su URL y fecha, categoría «Internet» y sin MTBF ni MTTR (la página no los trae; la selección usa el Supuesto por tipo).
    No guarda nada: el profesor los revisa y los guarda en el mantenedor. Sin clave o sin red, lista vacía."""
    from ..datos import precios_web as PW
    if not clave:
        return []
    if tipo in CO._LINEA:
        _k, nombre, q, magnitud, unidad, _d, _s, _c = CO._LINEA[tipo]
    else:
        nombre, q, magnitud, unidad = "Equipo genérico", CO.REFERENCIAS["generico"]["consulta"], "Capacidad", "t/h"
    consulta = consulta or q.format(s="").replace("  ", " ").strip() + " models capacity"
    try:
        resp = PW.buscar_tavily(consulta, clave, _abrir=_abrir)
    except Exception:
        return []
    res = resp.get("results") or []
    cand = PW._candidatos([(f"{r.get('title', '')}. {r.get('content', '')}", r.get("title", "") or "Tavily", r.get("url", "")) for r in res],
                          unidad, dolar, euro)
    hoy = date.today()
    out = []
    for c in cand:
        if not c.get("tamano"):
            continue
        out.append(dict(tipo=tipo, modelo=f"{nombre} {c['tamano']:g} {unidad} ({c['fuente'][:40]})", magnitud=magnitud, capacidad=float(c["tamano"]),
                        unidad=unidad, fuente_capacidad=f"{c['fuente']}, consultado el {hoy.isoformat()}", mtbf_h=None, mttr_h=None,
                        fuente_confiabilidad="", precio_usd=float(c["precio_usd"]), anio_precio=hoy.year,
                        fuente_precio=f"{c['fuente']}, consultado el {hoy.isoformat()} (Tavily)", largo_m=None, ancho_m=None, alto_m=None,
                        fuente_dimensiones="Sin dato en la página", categoria="Internet", url=c.get("url", "")))
    return out
