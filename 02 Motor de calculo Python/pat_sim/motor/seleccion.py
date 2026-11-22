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
PAT 139 (14-11-2026): el criterio de elección es el costo anual total del profesor Torres, C = C_inv + C_op + C_inef (motor/costo_total.py):
C_inv es la anualidad de la inversión (anual_clp); C_op, la energía con la curva de eficiencia del equipo más el mantenimiento; C_inef,
(1 − A_sist)·producción anual·margen, con A con el mantenimiento preventivo: A = 1 − ((1 − R) + t_MP). Las alternativas traen las
claves nuevas C_inv, C_op, C_inef, C (US$/año), sus _clp, A, A_equipo y eta. Compatibilidad: ineficiencia_clp es ahora C_inef; total_clp
es C sin la energía (anualidad + C_inef + mantenimiento); total_con_energia_clp y C_clp son C; A_etapa sigue siendo el k de n sin
mantenimiento preventivo (el de la pantalla de selección). costo_perdida_clp y costo_ociosa_clp quedan como referencia de la capacidad
esperada y no entran en C.

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
    from . import costo_total as CT
    return dict(margen=mg, fuente_margen=f_mg, horas=float(h), fuente_horas=f_h, tasa=float(economia.get("tasa", 0.10)),
                anios=float(economia.get("anios", 20)), dolar=float(economia.get("dolar", costos.DOLAR)),
                frac_ocioso=SUPUESTOS["frac_ocioso"].valor, f_inst=float(f_inst), cepci_hoy=float(cepci_hoy), plan=plan, avisos=avisos,
                precio_kwh=float(economia["precio_kwh"]) if _num(economia.get("precio_kwh")) is not None else PRECIO_KWH,
                t_mp=float(economia["t_mp_frac"]) if _num(economia.get("t_mp_frac")) is not None else CT.T_MP,
                mantencion_pct=float(economia["mantencion_pct"]) if _num(economia.get("mantencion_pct")) is not None else None)


# ---------------------------------------------------------------- catálogo y alternativas
def filas_catalogo(req: dict, catalogo: list[dict]) -> list[dict]:
    """Modelos del tipo del equipo en su unidad; si no hay, los genéricos en t/h de carga (y se marca)."""
    filas = [f for f in catalogo if f["tipo"] == req["tipo_catalogo"] and (f.get("unidad") or "") == req["unidad"]]
    if filas:
        return filas
    return [dict(f, _generico=True) for f in catalogo if f["tipo"] == "generico"]


def filas_equipo(req: dict, catalogo: list[dict], extra: list[dict] | None = None, solo: bool = False) -> list[dict]:
    """Modelos que se consideran para un equipo: los del catálogo (filas_catalogo) y las máquinas de fichas (extra); con solo y
    extra, únicamente las de las fichas. PAT 136, T23."""
    extra = list(extra or [])
    filas = filas_catalogo(req, catalogo)
    if extra:
        filas = extra if solo else extra + filas
    return filas


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


def _potencia_unidad(fila: dict, req: dict, ref: dict | None = None) -> tuple[float | None, str]:
    """Potencia (kW, a plena carga) de una unidad y su fuente: la de la ficha si la trae; si no, la potencia eléctrica del equipo de la
    planta escalada con la capacidad (Supuesto «potencia_escala»). (None, "") si no hay dato."""
    ref = ref or {}
    if _num(fila.get("potencia_kw")):
        return float(fila["potencia_kw"]), "Ficha: " + str(fila.get("fuente_potencia") or "potencia de la ficha")
    if ref.get("potencia_kw"):
        base = req["carga_t_h"] if fila.get("_generico") else req["requerida"]
        razon = float(fila["capacidad"]) / base if base else 1.0
        return ref["potencia_kw"] * razon ** SUPUESTOS["potencia_escala"].valor, "Supuesto: " + SUPUESTOS["potencia_escala"].justificacion
    return None, ""


def referencia_potencia(pl, equipo: str) -> dict:
    """Solo la potencia eléctrica (kW) del equipo de la planta y su fuente (referencias_equipo sin la huella): base de la energía de C_op
    de las unidades sin ficha con potencia."""
    from . import layout as LY
    eq = pl.equipos.get(equipo) if pl is not None else None
    out = dict(potencia_kw=None, fuente_pot="")
    if eq is None:
        return out
    try:
        P, f = LY.potencia_electrica(eq)
    except Exception:
        P, f = None, ""
    if P:
        out.update(potencia_kw=float(P), fuente_pot=f)
    return out


def evaluar(req: dict, fila: dict, n: int, k: int, P: dict, precio: dict | None = None, ref: dict | None = None) -> dict:
    """Una alternativa: n unidades del modelo de la fila, k necesarias. Disponibilidad, capacidades y costo anual total del profesor
    C = C_inv + C_op + C_inef (motor/costo_total.costo_total_opcion). ref: potencia eléctrica del equipo de la planta
    (referencia_potencia), para la energía de las unidades sin ficha con potencia; sin ella y sin ficha, C_op es solo el mantenimiento."""
    from . import linea_fluida as LF, costo_total as CT
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
    # costo anual total del profesor (PAT 139)
    S = D if fila.get("_generico") else req["requerida"]
    Pu, f_pot = _potencia_unidad(fila, req, ref)
    opc = dict(modelo=fila["modelo"], tipo=req["tipo"], n=n, k=k, capacidad=c, precio_usd=precio["precio_usd"], potencia_kw=Pu,
               mtbf_h=mtbf, mttr_h=mttr, t_mp_frac=P.get("t_mp"), produccion_anual=D * fp * P["horas"], q_peak=_num(fila.get("q_peak")),
               eta_max=_num(fila.get("eta_max")), a_curva=_num(fila.get("a_curva")), puntos_eta=fila.get("puntos_eta"))
    econ = dict(tasa=P["tasa"], anios=P["anios"], dolar=P["dolar"], f_inst=P["f_inst"], precio_kwh=P.get("precio_kwh"),
                mantencion_pct=P.get("mantencion_pct"), valor_unitario_usd=P["margen"] / P["dolar"], fuente_valor=P.get("fuente_margen") or "")
    ct = CT.costo_total_opcion(opc, S, P["horas"], econ)
    dd = ct["detalle"]; dolar = P["dolar"]
    c_mant, c_en = dd["mantenimiento_usd"] * dolar, dd["energia_usd"] * dolar
    return dict(equipo=req["equipo"], modelo=fila["modelo"], tipo_catalogo=fila["tipo"], capacidad_modelo=c, unidad=fila.get("unidad") or req["unidad"],
                n=int(n), k=int(k), redundante=n > k, instalada=n * c, instalada_t_h=n * c_tph, capacidad_modelo_t_h=c_tph,
                mtbf_h=float(mtbf), mttr_h=float(mttr), fuente_confiabilidad=f_conf, A_unidad=A, A_etapa=k_de_n(A, n, k),
                cap_esperada_t_h=capacidad_esperada(c_tph, n, A), cap_util_t_h=util, cap_ociosa_t_h=ocio, factor_producto=fp,
                cap_esperada_producto=capacidad_esperada(c_tph, n, A) * fp, perdida_t_anio=perdida_t, ociosa_t_anio=ociosa_t,
                costo_perdida_clp=c_perd, costo_ociosa_clp=c_ocio, ineficiencia_clp=ct["C_inef_clp"], precio_unitario_usd=precio["precio_usd"],
                fuente_precio=precio["fuente"], anio_precio=precio["anio"], inversion_clp=inv, anual_clp=anual,
                total_clp=anual + c_mant + ct["C_inef_clp"], categoria=fila.get("categoria") or "Supuesto", generico=bool(fila.get("_generico")),
                etiqueta=(f"{n} × {fila['modelo']}" + (f" ({k} de {n}, con redundancia)" if n > k else "")),
                # PAT 139: criterio C = C_inv + C_op + C_inef (US$/año y en pesos)
                C_inv=ct["C_inv"], C_op=ct["C_op"], C_inef=ct["C_inef"], C=ct["C"], C_inv_clp=ct["C_inv_clp"], C_op_clp=ct["C_op_clp"],
                C_inef_clp=ct["C_inef_clp"], C_clp=ct["C_clp"], A=ct["A"], A_equipo=ct["A_equipo"], eta=ct["eta"], eta_relativa=ct["eta_relativa"],
                factor_eta=dd["factor_eta"], q_unidad=ct["q_unidad"], mantenimiento_clp=c_mant, costo_energia_clp=c_en,
                energia_kwh_anio=dd["energia_kwh_anio"] if Pu else None, potencia_unidad_kw=Pu, fuente_potencia=f_pot,
                total_con_energia_clp=ct["C_clp"], fuentes_costo=ct["fuentes"], avisos_costo=ct["avisos"],
                detalle_costo=dd)                  # PAT 140 c: base de cálculo de C para la ficha comparativa de 3 opciones


def alternativas(req: dict, filas: list[dict], P: dict, n_max: int = N_MAX, redundancia: bool = True, ref: dict | None = None) -> list[dict]:
    """Por cada modelo: k = ⌈requerida/capacidad⌉ unidades (k = 1, un equipo más grande) y, si redundancia, k + 1. Ordenadas por el
    criterio del profesor: primero las sin reserva y, dentro de cada grupo, por menor C."""
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
            out.append(evaluar(req, f, n, k, P, precio, ref))
    return sorted(out, key=lambda a: (a["redundante"], a["C_clp"]))


def decidir_redundancia(base: dict, con: dict) -> dict:
    """Compara el ahorro de C_inef de agregar una unidad con el aumento de C_inv + C_op (anualidad, mantenimiento y energía): la unidad
    de reserva conviene si baja C = C_inv + C_op + C_inef."""
    ahorro = base["ineficiencia_clp"] - con["ineficiencia_clp"]
    costo = (con["anual_clp"] + (con.get("C_op_clp") or 0.0)) - (base["anual_clp"] + (base.get("C_op_clp") or 0.0))
    return dict(modelo=base["modelo"], n=base["n"], n_red=con["n"], ahorro_clp=ahorro, costo_clp=costo, neto_clp=ahorro - costo,
                recomendar=ahorro > costo, A_sin=base["A_etapa"], A_con=con["A_etapa"])


def seleccionar(pl, catalogo: list[dict] | None = None, economia: dict | None = None, desafio: dict | None = None,
                n_max: int = N_MAX, bd=None, f_inst: float = costos.F_INSTALACION, cepci_hoy: float = CO.CEPCI_HOY,
                fichas: dict | None = None, solo_fichas=()) -> dict:
    """Alternativas de cada equipo, la recomendada (menor costo anual total C = C_inv + C_op + C_inef, del profesor Torres) y la
    decisión de redundancia de su modelo. catalogo: filas de la tabla catalogo_comercial (por omisión, desde la base o la semilla).
    PAT 136, T23 (retrocompatible): fichas = {equipo: [filas con el formato del catálogo]} suma máquinas reales (motor/fichas.py,
    ficha_a_fila_catalogo) a las del catálogo; los equipos de solo_fichas usan únicamente esas (si tienen)."""
    if catalogo is None:
        from ..datos import mantenedor as M
        catalogo = M.catalogo_comercial(bd)
    P = parametros(pl, economia, desafio, f_inst, cepci_hoy)
    etapas, avisos = [], list(P["avisos"])
    for req in requerimientos(pl):
        extra = list((fichas or {}).get(req["equipo"]) or [])
        filas = filas_equipo(req, catalogo, extra, req["equipo"] in set(solo_fichas))
        alts = alternativas(req, filas, P, n_max, True, referencia_potencia(pl, req["equipo"]))
        e = dict(req, alternativas=alts, generico=bool(filas and all(f.get("_generico") for f in filas)), mejor=None, recomendada=None,
                 redundancia=None, n_fichas=len(extra))
        base = [a for a in alts if not a["redundante"]]
        if not base:
            avisos.append(f"{req['equipo']}: el catálogo no tiene modelos que sumen la capacidad con {n_max} unidades o menos.")
            etapas.append(e); continue
        if e["generico"]:
            avisos.append(f"{req['equipo']}: sin tamaños propios en el catálogo; se usan los genéricos en t/h de carga.")
        mejor = min(base, key=lambda a: a["C_clp"])
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


# ================================================================== PAT 136, T23: planta real, combinaciones de máquinas
# Punto 10 de los comentarios del profesor Torres (13-11-2026): para cada equipo de la planta se comparan combinaciones de máquinas
# reales (una grande contra n chicas, con o sin unidad de reserva) en costo, disponibilidad (k de n), espacio (área de planta) y
# energía (potencia). Las máquinas vienen de fichas (motor/fichas.py: Tavily o el catálogo Supuesto de 99 modelos).
SUPUESTOS.update({s.clave: s for s in [
    Supuesto("area_escala", "Exponente de cada dimensión de un equipo con su capacidad", 1.0 / 3.0, "—",
             "Semejanza geométrica: largo, ancho y alto crecen con la capacidad elevada a 1/3, el mismo exponente de las familias de "
             "motor/layout.py; sin ficha con dimensiones, la huella de una unidad parte de la del equipo de la planta"),
    Supuesto("pasillo_unidad", "Pasillo que se suma a cada lado de la huella de una unidad", 1.5, "m",
             "El pasillo libre de motor/layout.py (PASILLO_M) para tránsito y mantención, una vez por dimensión de cada unidad"),
    Supuesto("potencia_escala", "Exponente de la potencia instalada de una unidad con su capacidad", 1.0, "—",
             "Potencia proporcional a la capacidad, sin economías de escala; sin ficha con potencia, la de una unidad parte de la "
             "potencia eléctrica del equipo de la planta (motor/layout.potencia_electrica)"),
    Supuesto("carga_parcial", "Consumo eléctrico con carga parcial", 1.0, "—",
             "El consumo de las unidades en operación es proporcional a la carga que reciben (sin consumo en vacío); la unidad de "
             "reserva espera detenida y no consume"),
    Supuesto("precio_kwh", "Precio de la electricidad", 84.004, "$/kWh",
             "CNE (2026b), Precio medio de mercado, clientes libres, 7-08-2026 (el mismo de la pantalla Economía); se cambia en la interfaz"),
]})
PRECIO_KWH = SUPUESTOS["precio_kwh"].valor


def referencias_equipo(pl, equipo: str) -> dict:
    """Huella (largo y ancho en m) y potencia eléctrica (kW) del equipo de la planta, con su fuente: la base para estimar el espacio
    y la energía de máquinas sin ficha. None en lo que la planta no tiene."""
    from . import layout as LY
    eq = pl.equipos.get(equipo)
    out = dict(largo=None, ancho=None, area_m2=None, potencia_kw=None, fuente_dim="", fuente_pot="")
    if eq is None:
        return out
    try:
        d = LY.dimensiones(eq)
        out.update(largo=float(d["largo"]), ancho=float(d["ancho"]), area_m2=float(d["largo"]) * float(d["ancho"]),
                   fuente_dim=f"Layout: {d.get('categoria', 'Supuesto')}, {d.get('fuente', '')}"[:300])
    except Exception:
        pass
    P, f = LY.potencia_electrica(eq)
    if P:
        out.update(potencia_kw=float(P), fuente_pot=f)
    return out


def _fila_de(filas: list[dict], modelo: str) -> dict:
    return next((f for f in filas if f.get("modelo") == modelo), {})


def enriquecer(a: dict, fila: dict, req: dict, P: dict, ref: dict | None = None, precio_kwh: float = PRECIO_KWH) -> dict:
    """Agrega a una alternativa de evaluar() el espacio (área de planta de las n unidades con pasillo) y la energía (potencia de las
    k unidades en operación y su costo anual). La ficha manda; sin ficha, se escala la huella y la potencia del equipo de la planta."""
    ref = ref or {}
    s_esc = SUPUESTOS["area_escala"].valor; pas = SUPUESTOS["pasillo_unidad"].valor
    c = float(a["capacidad_modelo"]); base_req = req["carga_t_h"] if fila.get("_generico") else req["requerida"]
    razon = c / base_req if base_req else 1.0       # tamaño de la unidad relativo al que pide el equipo de la planta
    L, W, f_dim = None, None, ""
    if _num(fila.get("largo_m")) and _num(fila.get("ancho_m")):
        L, W, f_dim = float(fila["largo_m"]), float(fila["ancho_m"]), "Ficha: " + str(fila.get("fuente_dimensiones") or "dimensiones de la ficha")
    elif ref.get("largo") and ref.get("ancho"):
        L, W = ref["largo"] * razon ** s_esc, ref["ancho"] * razon ** s_esc
        f_dim = "Supuesto: " + SUPUESTOS["area_escala"].justificacion
    area_u = (L + pas) * (W + pas) if L is not None else None
    Pu, f_pot = None, ""
    if _num(fila.get("potencia_kw")):
        Pu, f_pot = float(fila["potencia_kw"]), "Ficha: " + str(fila.get("fuente_potencia") or "potencia de la ficha")
    elif ref.get("potencia_kw"):
        Pu = ref["potencia_kw"] * razon ** SUPUESTOS["potencia_escala"].valor
        f_pot = "Supuesto: " + SUPUESTOS["potencia_escala"].justificacion
    D = req["carga_t_h"]
    carga = min(1.0, D / (a["k"] * a["capacidad_modelo_t_h"])) if a["k"] * a["capacidad_modelo_t_h"] > 0 else 1.0
    kw = a["k"] * Pu * carga if Pu is not None else None
    # PAT 139: la energía lleva el factor η_max/η(q) de la curva del equipo (costo_total); el costo de la energía ya es parte de C_op
    kwh = kw * P["horas"] * a.get("factor_eta", 1.0) if kw is not None else None
    c_en = kwh * precio_kwh if kwh is not None else 0.0
    a.update(area_unidad_m2=area_u, area_total_m2=(a["n"] * area_u) if area_u is not None else None, fuente_area=f_dim,
             potencia_unidad_kw=Pu, potencia_instalada_kw=(a["n"] * Pu) if Pu is not None else None,
             potencia_operando_kw=kw, energia_kwh_anio=kwh, costo_energia_clp=c_en, fuente_potencia=f_pot,
             total_con_energia_clp=a["total_clp"] + c_en,
             garantia_meses=_num(fila.get("garantia_meses")), plazo_entrega_semanas=_num(fila.get("plazo_entrega_semanas")),
             peso_kg=_num(fila.get("peso_kg")), material=fila.get("material") or "", url=fila.get("url") or "")
    # con el precio de la electricidad pedido, C_op y C = C_inv + C_op + C_inef se recalculan (la energía es parte de C_op)
    d = P["dolar"]
    a.update(C_op_clp=a["mantenimiento_clp"] + c_en, C_clp=a["anual_clp"] + a["mantenimiento_clp"] + c_en + a["ineficiencia_clp"])
    a.update(C_op=a["C_op_clp"] / d, C=a["C_clp"] / d)
    return a


def recomendar(alts: list[dict], area_max: float | None = None, disp_min: float | None = None) -> dict:
    """Combinación de menor costo anual total (anualidad + ineficiencia + energía) que cumple el área máxima y la disponibilidad
    mínima de la etapa, si se piden. Devuelve {recomendada, candidatas, motivo}. Sin candidatas, recomendada es None y el motivo lo dice.
    Una combinación sin dato de área no se descarta por un área máxima (se avisa)."""
    cand = []
    for a in alts:
        if area_max is not None and a.get("area_total_m2") is not None and a["area_total_m2"] > area_max + 1e-9:
            continue
        if disp_min is not None and a["A_etapa"] < disp_min - 1e-12:
            continue
        cand.append(a)
    if not cand:
        return dict(recomendada=None, candidatas=[], motivo="Ninguna combinación cumple el área máxima y la disponibilidad mínima pedidas.")
    mejor = min(cand, key=lambda a: a["total_con_energia_clp"])
    motivo = (f"{mejor['etiqueta']}: menor costo anual total (anualidad, ineficiencia y energía) entre {len(cand)} combinaciones"
              + (" que cumplen las restricciones" if (area_max is not None or disp_min is not None) else "") + ".")
    return dict(recomendada=mejor, candidatas=cand, motivo=motivo)


def grande_contra_chicas(alts: list[dict]) -> dict:
    """Compara la mejor combinación de una máquina grande (k = 1) con la mejor de varias chicas (k ≥ 2), ambas sin reserva, en los
    cuatro criterios. Devuelve {grande, chicas, filas, ganadores}; si falta alguno de los dos grupos, ese lado es None."""
    base = [a for a in alts if not a["redundante"]]
    g = [a for a in base if a["k"] == 1]; ch = [a for a in base if a["k"] >= 2]
    grande = min(g, key=lambda a: a["total_con_energia_clp"]) if g else None
    chicas = min(ch, key=lambda a: a["total_con_energia_clp"]) if ch else None
    filas, ganadores = [], {}
    if grande and chicas:
        crit = [("costo", "Inversión instalada ($)", "inversion_clp", False), ("disp", "Disponibilidad de la etapa", "A_etapa", True),
                ("area", "Espacio: área de planta (m²)", "area_total_m2", False), ("energia", "Energía: potencia en operación (kW)", "potencia_operando_kw", False),
                ("total", "Costo anual total ($/año)", "total_con_energia_clp", False)]
        for k, nombre, campo, mayor in crit:
            vg, vc = grande.get(campo), chicas.get(campo)
            if vg is None or vc is None:
                gan = "sin dato"
            elif abs(vg - vc) <= 1e-9 * max(1.0, abs(vg)):
                gan = "empate"
            else:
                gan = "grande" if ((vg > vc) if mayor else (vg < vc)) else "chicas"
            filas.append(dict(clave=k, criterio=nombre, grande=vg, chicas=vc, ganador=gan))
            ganadores[k] = gan
    return dict(grande=grande, chicas=chicas, filas=filas, ganadores=ganadores)


def comparar_combinaciones(req: dict, filas: list[dict], P: dict, ref: dict | None = None, n_max: int = N_MAX, redundancia: bool = True,
                           area_max: float | None = None, disp_min: float | None = None, precio_kwh: float = PRECIO_KWH) -> dict:
    """Combinaciones de máquinas (una grande contra n chicas, con y sin unidad de reserva) para un equipo de la planta, con costo,
    disponibilidad k de n, espacio y energía. filas: modelos en el formato del catálogo (de fichas.ficha_a_fila_catalogo o del
    mantenedor). Devuelve {alternativas, recomendacion, grande_chicas, mejores (por criterio), avisos}."""
    alts = alternativas(req, filas, P, n_max, redundancia, ref)
    for a in alts:
        enriquecer(a, _fila_de(filas, a["modelo"]), req, P, ref, precio_kwh)
    alts.sort(key=lambda a: a["total_con_energia_clp"])
    avisos = []
    if not alts:
        avisos.append("Ninguna máquina suma la capacidad requerida con el máximo de unidades permitido.")
    if alts and all(a["potencia_operando_kw"] is None for a in alts):
        avisos.append("Sin potencia en las fichas ni en el equipo de la planta: la energía no entra en el costo.")
    if alts and all(a["area_total_m2"] is None for a in alts):
        avisos.append("Sin dimensiones en las fichas ni en el layout: no se puede comparar el espacio.")
    mejores = {}
    for clave, campo, mayor in (("costo", "inversion_clp", False), ("disponibilidad", "A_etapa", True), ("espacio", "area_total_m2", False),
                                ("energia", "potencia_operando_kw", False), ("total", "total_con_energia_clp", False)):
        con = [a for a in alts if a.get(campo) is not None]
        if con:
            mejores[clave] = (max if mayor else min)(con, key=lambda a: a[campo])
    return dict(alternativas=alts, recomendacion=recomendar(alts, area_max, disp_min), grande_chicas=grande_contra_chicas(alts),
                mejores=mejores, avisos=avisos)
