"""Elección de equipos por costo total (PAT 139, comentarios del profesor Torres del 14-11-2026).

Criterio del profesor (hoja manuscrita, 14-11-2026): se elige la opción de menor costo anual total

    C = C_inv + C_op + C_inef

- C_inv: precio de compra del conjunto (n equipos) por el factor de instalación vigente (motor/costos.py), anualizado con el factor
  de recuperación de capital CRF con la tasa y los años de Economía (motor/seleccion.crf).
- C_op = potencia · (η_max / η(q)) · horas · precio de la energía + mantenimiento. η(q) es la curva característica del equipo
  (eficiencia en función de la producción, con máximo en su punto de diseño): operar lejos del peak sube el costo de operar.
  El mantenimiento es la fracción del capital fijo que ya usa el proyecto (motor/factores_costo.py, MANTENCION_PCT).
- C_inef = (1 − A_sist) · producción anual · valor unitario: producción perdida por indisponibilidad de la etapa. El valor unitario
  es el margen de contribución que ya usa motor/seleccion.py (margen()).

Disponibilidad de un equipo (profesor): A = 1 − ((1 − R) + t_MP), con (1 − R) = MTTR/(MTBF + MTTR) la fracción del tiempo en falla
y t_MP la fracción del tiempo en mantenimiento preventivo. Etapa con n iguales de los que se necesitan k: A_etapa = k de n
(binomial, seleccion.k_de_n). Sistema en serie: producto (seleccion.serie).

Todo se calcula en US$ por año (el precio de los candidatos viene en US$); las claves terminadas en _clp son los mismos valores en
pesos con el dólar de Economía. Con economia["dolar"] = 1 las dos monedas coinciden (útil para validar con el ejemplo del profesor).

Funciones del contrato E1: disponibilidad_equipo, curva_eficiencia, eta_relativa, costo_total_opcion, candidatos_etapa y
mejor_opcion. Los candidatos se piden a datos/referencia_equipos.candidatos (equipo E2); si ese módulo no existe todavía, se usa el
catálogo comercial de motor/seleccion.py, de modo que todo funciona con y sin él.

Supuestos con justificación en SUPUESTOS. Cada cifra sin fuente segura va marcada «Supuesto».
"""
from __future__ import annotations
import math
from datetime import date
from . import seleccion as SEL, costeo as CO, costos, factores_costo as FC, linea_fluida as LF
from .operacion import Supuesto

FUENTE_HOJA = "Disponibilidad del equipo"
URL_BEP = "https://fluidflowinfo.com/centrifugal-pump-performance-curve-explained"
URL_DECK = "https://www.pumpsandsystems.com/sites/default/files/webinars/2018/0426/EfficientPumpSelectionandControl.pdf"

SUPUESTOS = {s.clave: s for s in [
    Supuesto("t_mp", "Fracción del tiempo en mantenimiento preventivo", 0.02, "fracción del tiempo",
             "Supuesto: una parada preventiva programada de 12 h al mes, cerca de 144 h al año, es decir 2 % de las 7.200 h de operación. "
             "La fórmula A = 1 − ((1 − R) + t_MP) no fija el valor de t_MP, y la carpeta del proyecto no "
             "trae una fuente para t_MP; se reemplaza con el plan de mantenimiento del fabricante o de la planta"),
    Supuesto("a_curva", "Caída de la eficiencia fuera del peak (coeficiente a de la parábola)", 0.6, "—",
             "Supuesto: η(q) = η_max·(1 − a·(q/q_peak − 1)²) con a = 0,6, es decir 15 % menos de eficiencia a la mitad del caudal de diseño "
             "(η = 0,85·η_max) y 40 % menos en vacío. Cualitativamente, la eficiencia cae al bajar el caudal bajo el punto de mejor eficiencia "
             f"(Pumps and Systems, 2018, «Efficient pump selection and control», {URL_DECK}, consultado el 14-11-2026: «As flow reduces so does "
             f"pump efficiency!»; fluidflowinfo, {URL_BEP}, consultado el 14-11-2026: operar cerca del punto de mejor eficiencia minimiza el costo "
             "de energía y el desgaste). Ninguna de las dos fuentes da un coeficiente: el 0,6 es de partida y se reemplaza con los puntos (q, η) de la "
             "ficha del equipo (ajustar_curva)"),
    Supuesto("eta_min_rel", "Eficiencia mínima relativa de la curva", 0.30, "fracción de η_max",
             "Supuesto: piso de la curva para que η nunca sea cero ni negativa lejos del peak (en vacío o en sobrecarga); un equipo con menos de "
             "30 % de su eficiencia máxima opera fuera de su rango estable y se descarta por otras vías (capacidad mínima del fabricante)"),
    Supuesto("q_peak", "Punto de diseño del equipo (donde η es máxima)", 1.0, "fracción de la capacidad nominal",
             "Supuesto: la eficiencia máxima está en la capacidad nominal de la ficha; con puntos (q, η) de la ficha el peak sale del ajuste"),
    Supuesto("reparto", "Reparto de la carga entre las unidades", 1.0, "—",
             "Las k unidades que operan comparten la producción requerida por igual; la unidad de reserva (n = k + 1) espera detenida y no "
             "consume (el mismo Supuesto «reserva» de motor/seleccion.py)"),
]}
T_MP = SUPUESTOS["t_mp"].valor
A_CURVA = SUPUESTOS["a_curva"].valor
ETA_MIN_REL = SUPUESTOS["eta_min_rel"].valor


def _num(x):
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


# ---------------------------------------------------------------- disponibilidad
def disponibilidad_equipo(mtbf_h, mttr_h, t_mp_frac=None) -> float:
    """A = 1 − ((1 − R) + t_MP) con (1 − R) = MTTR/(MTBF + MTTR) (hoja manuscrita del profesor Torres, 14-11-2026). Acotada a [0, 1].
    t_mp_frac = None toma el Supuesto «t_mp» (2 %). MTBF faltante o no positivo, MTTR negativo o t_MP negativo: ValueError."""
    mtbf, mttr = _num(mtbf_h), _num(mttr_h)
    if mtbf is None or mttr is None:
        raise ValueError("Falta el MTBF o el MTTR del equipo.")
    t = T_MP if t_mp_frac is None else _num(t_mp_frac)
    if t is None or t < 0:
        raise ValueError("La fracción de mantenimiento preventivo debe ser un número no negativo.")
    R = SEL.disponibilidad(mtbf, mttr)                 # R = MTBF/(MTBF + MTTR); valida MTBF > 0 y MTTR ≥ 0
    return float(min(1.0, max(0.0, 1.0 - ((1.0 - R) + t))))


# ---------------------------------------------------------------- curva de eficiencia
def ajustar_curva(puntos, q_peak=None, eta_max=None) -> dict:
    """Ajusta η(q) = η_max·(1 − a·(q/q_peak − 1)²) a los puntos (q, η) de una ficha.
    - 3 o más puntos con q distintos y curvatura negativa: cuadrática por mínimos cuadrados; q_peak y η_max salen del vértice.
    - Si no, q_peak y η_max son los dados o los del mejor punto, y a sale por mínimos cuadrados de un parámetro (con un solo punto
      queda el Supuesto «a_curva»).
    Devuelve {q_peak, eta_max, a, r2, n_puntos, metodo}. Sin puntos válidos: ValueError."""
    pts = []
    for p in puntos or []:
        try:
            q, e = float(p[0]), float(p[1])
        except (TypeError, ValueError, IndexError, KeyError):
            continue
        if math.isfinite(q) and math.isfinite(e) and q >= 0 and e > 0:
            pts.append((q, e))
    if not pts:
        raise ValueError("La curva de eficiencia necesita al menos un punto (q, η) con q ≥ 0 y η > 0.")
    qs, es = [p[0] for p in pts], [p[1] for p in pts]

    def _r2(qp, em, a):
        pred = [em * (1.0 - a * (q / qp - 1.0) ** 2) for q in qs]
        sst = sum((e - sum(es) / len(es)) ** 2 for e in es)
        sse = sum((e - p) ** 2 for e, p in zip(es, pred))
        return 1.0 if sst <= 1e-18 else 1.0 - sse / sst

    if q_peak is None and eta_max is None and len(pts) >= 3 and len(set(qs)) >= 3:
        import numpy as np
        c2, c1, c0 = np.polyfit(qs, es, 2)
        if c2 < 0:
            qp = -c1 / (2.0 * c2); em = c0 - c1 ** 2 / (4.0 * c2)
            if qp > 0 and em > 0:
                a = float(-c2 * qp ** 2 / em)
                return dict(q_peak=float(qp), eta_max=float(em), a=a, r2=float(_r2(qp, em, a)), n_puntos=len(pts),
                            metodo="Cuadrática por mínimos cuadrados con el vértice como peak")
    i = max(range(len(pts)), key=lambda j: es[j])
    qp = float(q_peak) if _num(q_peak) and float(q_peak) > 0 else qs[i]
    em = float(eta_max) if _num(eta_max) and float(eta_max) > 0 else es[i]
    if qp <= 0:
        qp = max(qs) or 1.0
    u2 = [(q / qp - 1.0) ** 2 for q in qs]
    den = em * sum(u ** 2 for u in u2)
    if den > 1e-12:
        a = max(0.0, sum((em - e) * u for e, u in zip(es, u2)) / den)
        metodo = "Peak dado o el del mejor punto; a por mínimos cuadrados"
    else:
        a, metodo = A_CURVA, "Un solo punto en el peak: a = Supuesto"
    return dict(q_peak=qp, eta_max=em, a=float(a), r2=float(_r2(qp, em, a)), n_puntos=len(pts), metodo=metodo)


def _curva(q, q_peak, eta_max, a, eta_min, puntos):
    """(η, η_max, a, q_peak) con la forma parabólica acotada a [η_min, η_max]; con puntos, los parámetros salen del ajuste."""
    if puntos:
        aj = ajustar_curva(puntos)
        q_peak, eta_max, a = aj["q_peak"], aj["eta_max"], aj["a"]
    eta_max = 1.0 if eta_max is None else float(eta_max)
    qp = _num(q_peak)
    if qp is None or qp <= 0 or eta_max <= 0:
        raise ValueError("q_peak y η_max deben ser positivos.")
    a = A_CURVA if a is None else max(0.0, float(a))
    piso = ETA_MIN_REL * eta_max if eta_min is None else min(max(float(eta_min), 0.0), eta_max)
    piso = max(piso, 1e-9 * eta_max)                        # η nunca es cero ni negativa
    qq = max(0.0, _num(q) or 0.0)
    eta = eta_max * (1.0 - a * (qq / qp - 1.0) ** 2)
    return float(min(eta_max, max(piso, eta))), eta_max, a, qp


def curva_eficiencia(q, q_peak, eta_max=1.0, a=None, eta_min=None, puntos=None) -> float:
    """η(q) = η_max·(1 − a·(q/q_peak − 1)²), acotada a [η_min, η_max] (nunca negativa). a por omisión: Supuesto «a_curva» (0,6);
    η_min por omisión: 30 % de η_max. Con puntos [(q, η), …] de la ficha, la curva se ajusta a ellos (ajustar_curva) y q_peak, η_max y a
    del argumento no se usan. q < 0 se toma como 0."""
    return _curva(q, q_peak, eta_max, a, eta_min, puntos)[0]


def eta_relativa(q, q_peak, a=None, eta_min_rel=None, puntos=None) -> float:
    """η(q)/η_max, entre η_min_rel (30 % por omisión) y 1. El costo de operar sube con η_max/η = 1/eta_relativa."""
    em = ajustar_curva(puntos)["eta_max"] if puntos else 1.0
    eta, em, _a, _qp = _curva(q, q_peak, 1.0, a, None if eta_min_rel is None else float(eta_min_rel) * em, puntos)
    return float(eta / em)


# ---------------------------------------------------------------- Williams con las referencias
def exponente_williams(puntos) -> dict:
    """Exponente n de C = C1·(S/S1)^n por regresión log-log de puntos (tamaño, precio) de referencia. Con 2 puntos pasa por ambos.
    Devuelve {n, C1, S1, r2, n_puntos}; con menos de 2 tamaños distintos, n = 0,6 (regla de los seis décimos, Supuesto)."""
    pts = sorted({(float(s), float(c)) for s, c in puntos if _num(s) and _num(c) and float(s) > 0 and float(c) > 0})
    S1 = pts[0][0] if pts else 1.0
    if len({p[0] for p in pts}) < 2:
        return dict(n=CO.N_SEIS_DECIMOS, C1=pts[0][1] if pts else None, S1=S1, r2=None, n_puntos=len(pts))
    import numpy as np
    x = np.log([p[0] for p in pts]); y = np.log([p[1] for p in pts])
    n, b = np.polyfit(x, y, 1)
    pred = n * x + b
    sst = float(((y - y.mean()) ** 2).sum()); sse = float(((y - pred) ** 2).sum())
    return dict(n=float(n), C1=float(math.exp(b + n * math.log(S1))), S1=S1, r2=1.0 if sst <= 1e-18 else 1.0 - sse / sst, n_puntos=len(pts))


# ---------------------------------------------------------------- una opción
def _economia(economia: dict | None, rubro: str | None = None) -> dict:
    e = dict(economia or {})
    dolar = _num(e.get("dolar")) or costos.DOLAR
    if _num(e.get("valor_unitario_usd")) is not None:
        valor = float(e["valor_unitario_usd"])
        f_valor = e.get("fuente_valor") or "Economía: valor unitario dado (US$ por unidad de producción)"
    else:
        m, f_valor = SEL.margen(e.get("rubro") or rubro or "tomate", e)
        valor = m / dolar
    return dict(tasa=_num(e.get("tasa")) if _num(e.get("tasa")) is not None else 0.10,
                anios=_num(e.get("anios")) or 20.0, dolar=dolar, f_inst=_num(e.get("f_inst")) or costos.F_INSTALACION,
                precio_kwh=_num(e.get("precio_kwh")) if _num(e.get("precio_kwh")) is not None else SEL.PRECIO_KWH,
                mantencion_pct=_num(e.get("mantencion_pct")) if _num(e.get("mantencion_pct")) is not None else FC.MANTENCION_PCT,
                valor_unitario_usd=valor, fuente_valor=f_valor)


def costo_total_opcion(opcion: dict, requerida: float, horas: float, economia: dict | None = None) -> dict:
    """Costo anual total C = C_inv + C_op + C_inef de una opción: n equipos iguales de los que k son necesarios para la producción
    requerida (misma unidad que la capacidad).

    opcion: n, capacidad (de un equipo), precio_usd (de un equipo, sin instalación) obligatorios; k (por omisión ⌈requerida/capacidad⌉),
    potencia_kw (de un equipo a plena carga; sin ella, la energía no entra), mtbf_h y mttr_h (sin ellos se usa el Supuesto por tipo de
    motor/linea_fluida.py y se avisa), A_equipo (disponibilidad dada; manda sobre MTBF y MTTR), t_mp_frac, q_peak (por omisión la capacidad),
    eta_max (por omisión 1: η relativa), a_curva, puntos_eta (puntos (q, η) de la ficha), produccion_anual (por omisión requerida·horas·
    factor_producto), factor_producto, tipo, modelo.
    economia: tasa, anios, dolar, f_inst, precio_kwh ($/kWh), mantencion_pct, valor_unitario_usd o margen ($ por unidad de producción).
    Devuelve C_inv, C_op, C_inef, C (US$/año) y sus *_clp, A (de la etapa, k de n), A_equipo, k, n, q_unidad, eta, eta_relativa, detalle,
    fuentes y avisos. Requerida 0: sin pérdida por indisponibilidad (A = 1) y sin energía; n = 0: sin equipos (C = 0, A = 0 si algo se
    requiere)."""
    avisos, fuentes = [], []
    E = _economia(economia, opcion.get("rubro"))
    h = _num(horas)
    if h is None or h <= 0:
        h = SEL.SUPUESTOS["horas"].valor
        avisos.append("Sin horas de operación: se usa el Supuesto de 7.200 h al año.")
    S = max(0.0, _num(requerida) or 0.0)
    n = max(0, int(round(_num(opcion.get("n")) or 0)))
    c = _num(opcion.get("capacidad"))
    precio = _num(opcion.get("precio_usd"))
    if n > 0 and (c is None or c <= 0):
        raise ValueError("La opción necesita la capacidad de un equipo (capacidad > 0).")
    if n > 0 and (precio is None or precio < 0):
        raise ValueError("La opción necesita el precio de un equipo en US$ (precio_usd ≥ 0).")
    c = c or 0.0; precio = precio or 0.0
    kmin = int(math.ceil(S / c - 1e-9)) if (S > 0 and c > 0) else 0
    k = kmin if opcion.get("k") is None else int(opcion["k"])
    if k < kmin:
        avisos.append(f"k = {k} no alcanza la capacidad requerida: se usa k = {kmin} (⌈requerida / capacidad⌉).")
        k = kmin
    if n < k:
        avisos.append(f"La opción tiene {n} equipos y necesita {k}: no alcanza la producción requerida (A = 0).")

    # disponibilidad: equipo y etapa
    t_mp = T_MP if opcion.get("t_mp_frac") is None else float(opcion["t_mp_frac"])
    f_disp = f"{FUENTE_HOJA}: A = 1 − ((1 − R) + t_MP)"
    mtbf, mttr = _num(opcion.get("mtbf_h")), _num(opcion.get("mttr_h"))
    if _num(opcion.get("A_equipo")) is not None:
        A_eq = min(1.0, max(0.0, float(opcion["A_equipo"])))
        f_disp = "Disponibilidad del equipo dada por la opción (ficha o docente)"
    else:
        if mtbf is None or mttr is None or mtbf <= 0 or mttr < 0:
            cat = LF.categoria(str(opcion.get("tipo") or ""))
            mtbf, mttr = LF.FALLAS_TIPO[cat]
            avisos.append(f"El equipo no trae MTBF y MTTR: se usa el Supuesto PAT 134 de motor/linea_fluida.py ({cat}: MTBF {mtbf:g} h, MTTR {mttr:g} h).")
            f_disp += f"; MTBF y MTTR: Supuesto PAT 134 (FALLAS_TIPO, {cat})"
        A_eq = disponibilidad_equipo(mtbf, mttr, t_mp)
        if opcion.get("t_mp_frac") is None:
            f_disp += f"; t_MP = {T_MP:.0%}: Supuesto («t_mp» de motor/costo_total.py)".replace(".", ",")
    A = SEL.k_de_n(A_eq, n, k) if n > 0 else (0.0 if S > 0 else 1.0)
    fuentes.append(dict(concepto="Disponibilidad", fuente=f_disp + "; etapa k de n (binomial)"))

    # carga por equipo y curva de eficiencia
    q_u = (S / k) if k > 0 else 0.0
    q_peak = _num(opcion.get("q_peak")) or c or 1.0
    eta, eta_max, a, qp = _curva(q_u, q_peak, _num(opcion.get("eta_max")) or 1.0, _num(opcion.get("a_curva")), None, opcion.get("puntos_eta"))
    factor_eta = eta_max / eta
    f_curva = ("Puntos (q, η) de la ficha, ajuste parabólico" if opcion.get("puntos_eta")
               else "Supuesto: " + SUPUESTOS["a_curva"].justificacion)
    fuentes.append(dict(concepto="Curva de eficiencia", fuente=f"Curva parabólica con η máxima en el punto de diseño; {f_curva}"))

    # C_inv
    inversion = precio * n * E["f_inst"]
    crf = SEL.crf(E["tasa"], E["anios"])
    C_inv = inversion * crf
    fuentes.append(dict(concepto="C_inv", fuente=f"Precio de la opción × n × factor de instalación ({E['f_inst']:g}, motor/costos.py) × CRF "
                                                f"(tasa {E['tasa']:.1%}, {E['anios']:g} años, Economía)".replace(".", ",")))

    # C_op
    P_u = _num(opcion.get("potencia_kw"))
    carga = min(1.0, q_u / c) if c > 0 else 0.0
    if P_u is None or P_u <= 0:
        kw_op, kwh_ref = 0.0, 0.0
        if n > 0:
            avisos.append("Sin potencia del equipo: la energía no entra en C_op (solo el mantenimiento).")
    else:
        kw_op = k * P_u * carga                      # potencia con la eficiencia máxima, proporcional a la carga (Supuesto «carga_parcial»)
        kwh_ref = kw_op * h
    kwh = kwh_ref * factor_eta
    c_energia = kwh * E["precio_kwh"] / E["dolar"]
    c_mant = inversion * E["mantencion_pct"] / 100.0
    C_op = c_energia + c_mant
    fuentes.append(dict(concepto="C_op", fuente=f"Energía: potencia × η_max/η(q) × horas × precio (Economía, {E['precio_kwh']:g} $/kWh); mantenimiento: "
                                                f"{E['mantencion_pct']:g} % del capital fijo ({FC.OM['mantencion'][3][:90]}…)".replace(".", ",")))

    # C_inef
    prod = _num(opcion.get("produccion_anual"))
    if prod is None:
        prod = S * h * (_num(opcion.get("factor_producto")) or 1.0)
    C_inef = (1.0 - A) * prod * E["valor_unitario_usd"]
    fuentes.append(dict(concepto="C_inef", fuente=f"(1 − A_sist) × producción anual × valor unitario; {E['fuente_valor']}"))

    C = C_inv + C_op + C_inef
    d = E["dolar"]
    detalle = dict(inversion_usd=inversion, precio_unitario_usd=precio, f_inst=E["f_inst"], crf=crf, tasa=E["tasa"], anios=E["anios"],
                   horas=h, requerida=S, capacidad_unidad=c, carga_fraccion=carga, q_peak=qp, a_curva=a, eta_max=eta_max,
                   factor_eta=factor_eta, potencia_unidad_kw=P_u, potencia_operando_kw=kw_op, energia_kwh_anio=kwh,
                   energia_kwh_anio_sin_curva=kwh_ref, energia_usd=c_energia, mantenimiento_usd=c_mant, mantencion_pct=E["mantencion_pct"],
                   precio_kwh_clp=E["precio_kwh"], produccion_anual=prod, valor_unitario_usd=E["valor_unitario_usd"],
                   perdida_fraccion=1.0 - A, t_mp=t_mp, mtbf_h=mtbf, mttr_h=mttr, dolar=d, fuente_valor=E["fuente_valor"])
    return dict(C_inv=C_inv, C_op=C_op, C_inef=C_inef, C=C, C_inv_clp=C_inv * d, C_op_clp=C_op * d, C_inef_clp=C_inef * d, C_clp=C * d,
                A=float(A), A_equipo=float(A_eq), k=k, n=n, q_unidad=q_u, eta=eta, eta_relativa=eta / eta_max, moneda="US$/año",
                detalle=detalle, fuentes=fuentes, avisos=avisos)


# ---------------------------------------------------------------- candidatos de una etapa
def _filas_respaldo(req: dict, catalogo: list[dict] | None = None, bd=None) -> list[dict]:
    """Catálogo comercial actual de motor/seleccion.py (modelos del tipo del equipo en su unidad; si no hay, los genéricos)."""
    if catalogo is None:
        from ..datos import mantenedor as M
        catalogo = M.catalogo_comercial(bd)
    return [dict(f, origen=f.get("origen") or ("Respaldo" if _num(f.get("precio_usd")) else "Williams")) for f in SEL.filas_catalogo(req, catalogo)]


def _fila_de_referencia(c: dict, req: dict) -> dict | None:
    """Pasa un candidato de datos/referencia_equipos.candidatos al formato de fila del catálogo de motor/seleccion.py."""
    cap = _num(c.get("capacidad"))
    if not cap or cap <= 0:
        return None
    unidad = c.get("unidad") or req["unidad"]
    if unidad != req["unidad"]:
        return None
    origen = c.get("origen") or ("Tavily" if c.get("url") else "Respaldo")
    fuente = c.get("fuente") or c.get("fuente_precio") or ""
    f = dict(tipo=req["tipo_catalogo"], modelo=str(c.get("modelo") or "Sin modelo"), fabricante=c.get("fabricante") or "", capacidad=cap,
             unidad=unidad, mtbf_h=_num(c.get("mtbf_h")), mttr_h=_num(c.get("mttr_h")),
             fuente_confiabilidad=c.get("fuente_confiabilidad") or "", precio_usd=_num(c.get("precio_usd")),
             anio_precio=c.get("anio_precio") or c.get("anio") or date.today().year, fuente_precio=fuente,
             fuente_capacidad=c.get("fuente_capacidad") or fuente, categoria=c.get("categoria") or ("Internet" if origen == "Tavily" else "Literatura"),
             url=c.get("url") or "", origen=origen, potencia_kw=_num(c.get("potencia_kw")), fuente_potencia=c.get("fuente_potencia") or fuente,
             largo_m=_num(c.get("largo_m")), ancho_m=_num(c.get("ancho_m")), alto_m=_num(c.get("alto_m")),
             fuente_dimensiones=c.get("fuente_dimensiones") or "", q_peak=_num(c.get("q_peak")), eta_max=_num(c.get("eta_max")),
             puntos_eta=c.get("puntos_eta"), fecha=c.get("fecha") or c.get("fecha_precio") or "")
    if f["precio_usd"] is not None and f["precio_usd"] <= 0:
        f["precio_usd"] = None
        f["origen"] = "Williams"
    if f["precio_usd"] is None:
        f["origen"] = "Williams"
    return f


def candidatos_con_avisos(pl, equipo_id: str, economia: dict | None = None, buscar_en_linea: bool = True, catalogo: list[dict] | None = None,
                          bd=None, secretos=None) -> dict:
    """Como candidatos_etapa, pero devuelve {candidatos, avisos, requerimiento, origen_candidatos}. Planta vacía o sin ese equipo:
    lista vacía y el aviso, sin fallar. origen_candidatos: «referencia_equipos» (equipo E2) o «catálogo comercial» (respaldo)."""
    avisos = []
    req = next((r for r in SEL.requerimientos(pl) if r["equipo"] == equipo_id), None) if pl is not None else None
    if req is None:
        avisos.append("La planta no tiene resuelto ese equipo o no está en la planta: no hay etapa que elegir."
                      if pl is not None and getattr(pl, "equipos", None) else "La planta está vacía: no hay equipos que elegir.")
        return dict(candidatos=[], avisos=avisos, requerimiento=None, origen_candidatos="")
    filas, origen = [], "catálogo comercial"
    try:
        from ..datos import referencia_equipos as RE
    except Exception:
        RE = None
    if RE is not None:
        try:
            kw = dict(en_linea=bool(buscar_en_linea))
            if secretos is not None:
                kw["secretos"] = secretos
            res = RE.candidatos(req["tipo"], req["requerida"], req["unidad"], **kw)
            filas = [f for f in (_fila_de_referencia(c, req) for c in (res or [])) if f]
            if filas:
                origen = "referencia_equipos"
            else:
                avisos.append("referencia_equipos no entregó candidatos: se usa el catálogo comercial de respaldo.")
        except Exception as e:                            # E2 falla: el catálogo comercial sigue funcionando
            avisos.append(f"referencia_equipos no respondió ({type(e).__name__}): se usa el catálogo comercial de respaldo.")
            filas = []
    if not filas:
        filas = _filas_respaldo(req, catalogo, bd)
    if not filas:
        avisos.append("Sin modelos para este tipo de equipo.")
        return dict(candidatos=[], avisos=avisos, requerimiento=req, origen_candidatos=origen)
    P = SEL.parametros(pl, economia)
    ref = SEL.referencia_potencia(pl, equipo_id)
    alts = SEL.alternativas(req, filas, P, SEL.N_MAX, True, ref)
    por_modelo = {f["modelo"]: f for f in filas}
    out = []
    for a in alts:
        f = por_modelo.get(a["modelo"], {})
        out.append(dict(a, id=f"{equipo_id}|{a['modelo']}|{a['n']}", fabricante=f.get("fabricante") or "", capacidad=a["capacidad_modelo"],
                        precio_usd=a["precio_unitario_usd"], origen=f.get("origen") or ("Respaldo" if _num(f.get("precio_usd")) else "Williams"),
                        eta_operacion=a["eta"], url=f.get("url") or "", fuente=a.get("fuente_precio") or "",
                        origen_precio=("Williams" if not _num(f.get("precio_usd")) else f.get("origen") or "Respaldo")))
    out.sort(key=lambda a: (a["C"], a["n"]))
    avisos += list(P.get("avisos") or [])
    if not out:
        avisos.append(f"Ningún modelo suma la capacidad requerida con {SEL.N_MAX} unidades o menos.")
    # PAT 140 c: filas, parámetros y potencia de referencia, para armar las 3 opciones de distinto n (motor/tres_opciones.py)
    return dict(candidatos=out, avisos=avisos, requerimiento=req, origen_candidatos=origen, filas=filas, parametros=P, ref_potencia=ref)


def candidatos_etapa(pl, equipo_id: str, economia: dict | None = None, buscar_en_linea: bool = True, **kw) -> list[dict]:
    """Opciones (n = k, n = k + 1 de cada modelo) para un equipo de la planta, ordenadas por C (menor primero). Cada dict: id, modelo,
    fabricante, n, k, capacidad (de un equipo), unidad, precio_usd (de un equipo), origen («Tavily», «Respaldo» o «Williams»), C_inv,
    C_op, C_inef, C (US$/año; con sufijo _clp en pesos), A (de la etapa, k de n), eta_operacion, url y fuente, más todo lo que entrega
    seleccion.evaluar (por eso se puede aplicar con seleccion.aplicar). Planta vacía o equipo inexistente: lista vacía."""
    return candidatos_con_avisos(pl, equipo_id, economia, buscar_en_linea, **kw)["candidatos"]


def mejor_opcion(pl, equipo_id: str, economia: dict | None = None, buscar_en_linea: bool = True, **kw) -> dict | None:
    """La opción de menor C del equipo, o None si no hay candidatos (planta vacía, equipo sin catálogo)."""
    c = candidatos_etapa(pl, equipo_id, economia, buscar_en_linea, **kw)
    return c[0] if c else None
