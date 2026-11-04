"""Alternativas de recuperación de calor, comparación multicriterio y aproximación mínima óptima (PAT 133, mejoras 1, 2 y 4).

Lleva a la aplicación el cálculo de los Capítulos 2 a 4 (Capitulos 2 a 4 Agrozzi/scripts/calc_cap234.py) para cualquier
planta del simulador:
- A1: solo las corrientes sensibles (condensados), cada una en su etapa.
- A2: cascada en serie con todas las corrientes.
- A3: colector común de las corrientes sensibles más las latentes (alcanza el objetivo pinch en Agrozzi).
- A4: bomba de calor que cubre todo el sumidero.
Área de cada etapa con LMTD y U bajo, medio y alto; inversión con la correlación de Shamoushaki et al. (2021) actualizada
con el PPI (motor/costos.py); evaluación después de impuesto como en el Capítulo 4; suma ponderada con normalización por
rango y barrido de pesos como en el Capítulo 3. El ΔTmin óptimo minimiza el costo total anual (capital anualizado más
operación y combustible remanente), como el supertargeting de Aspen Energy Analyzer (Linnhoff y Ahmad, 1990, en Kemp, 2007).
"""
from __future__ import annotations
import math
from . import recuperacion as rec, economia as eco, costos

# U en W/m2K (bajo, medio, alto)
U_LIQ = (500.0, 850.0, 1200.0)       # líquido contra tomate (Amon et al., 2015, Tabla 1, p. 528)
U_COND = (625.6, 840.0, 910.9)       # vapor que condensa contra pulpa de tomate (Sangrame et al., 2000, p. 205)
U_GAS = (25.0, 50.0, 100.0)          # Supuesto: gas de escape contra aire o sólido, orden de magnitud de Incropera et al. (2007, Tabla 11.2)
IMPUESTO = 0.27                      # primera categoría, régimen general (DL 824, art. 20)
VIDA = 15                            # años, maquinarias y equipos (SII, Res. Ex. 43/2002, n.o 15)
OM_HX = 0.02                         # fracción de la inversión por año (Supuesto del Capítulo 4)
HP_OM_FIJO, HP_OM_VAR = 2494.0, 3.60 # EUR/MW/año y EUR/MWh (Danish Energy Agency, 2026, hoja 2.a)
PMM_LIBRES = 84.004                  # $/kWh, precio medio de mercado de clientes libres (CNE, 7-08-2026)
NOMBRES = {"A1": "Condensados por separado", "A2": "Cascada en serie", "A3": "Colector común de condensados",
           "A4": "Bomba de calor"}
CRITERIOS = (("cob", "Cobertura del sumidero", True), ("p_eq", "Precio de equilibrio del combustible", False),
             ("equipos", "Número de equipos", False))


def _lmtd(a, b):
    a = max(a, 1e-6); b = max(b, 1e-6)
    return a if abs(a - b) < 1e-9 else (a - b) / math.log(a / b)


def _contexto(pl, r):
    from .resumen import _caldera, _horas
    snk = next(s for s in pl.sumideros() if s.equipo == r["sumidero"]["equipo"])
    cal = _caldera(pl)
    return snk, cal, _horas(pl), getattr(cal, "combustible", "gas") if cal is not None else None


def etapas(filas, corr, biomasa=False):
    """Área y costo de cada etapa de una cascada (filas de rec.cascada)."""
    out = []
    for f in filas:
        if f["Q_kW"] < 1e-6:
            continue
        s = corr[f["corriente"]]; Q = f["Q_kW"]
        if s[3] is None:
            Thi = Tho = s[1]; U = U_COND; tipo = "condensación"
        else:
            Thi = s[1]; Tho = s[1] - Q / s[3]; U = U_GAS if biomasa else U_LIQ; tipo = "gas" if biomasa else "líquido"
        L = _lmtd(Thi - f["T_sale"], Tho - f["T_entra"]); UA = Q / L
        A = [UA * 1000 / u for u in U]
        out.append(dict(corriente=f["corriente"], tipo=tipo, Q=Q, Tc_in=f["T_entra"], Tc_out=f["T_sale"], Th_in=Thi, Th_out=Tho,
                        LMTD=L, A_bajoU=A[0], A_medio=A[1], A_altoU=A[2]))
    return out


def _valor(Q_kW, h, cal, comb, precio, dolar):
    """Ahorro por temporada (MM$) y cantidad de combustible desplazado (MMBtu o m3 estéreo)."""
    if comb == "biomasa":
        c = cal.consumo(Q_kW, h); return c["m3"] * precio / 1e6, c["m3"]
    g = eco.gas(Q_kW, h, cal); return eco.valor_gas(g["MMBtu"], precio, dolar), g["MMBtu"]


def evaluar(I, cantidad, precio, om, tasa, anios=VIDA, dolar=costos.DOLAR, biomasa=False, extra_costo=0.0, impuesto=IMPUESTO, vida_dep=VIDA):
    """Flujo después de impuesto con depreciación lineal y sin valor de desecho (Capítulo 4)."""
    S = cantidad * precio / 1e6 if biomasa else cantidad * precio * dolar / 1e6
    dep = I / vida_dep
    flujos = [-I] + [(S - om - extra_costo - (dep if i <= vida_dep else 0)) * (1 - impuesto) + (dep if i <= vida_dep else 0)
                     for i in range(1, anios + 1)]
    neto = flujos[1] if len(flujos) > 1 else 0.0
    return dict(S=S, VAN=eco.van(flujos, tasa), TIR=eco.tir(flujos), recuperacion=I / neto if neto > 0 else None, flujos=flujos)


def precio_equilibrio(I, cantidad, om, tasa, anios=VIDA, dolar=costos.DOLAR, biomasa=False, extra_costo=0.0):
    """Precio del combustible con VAN cero (US$/MMBtu en gas, $/m3 estéreo en biomasa)."""
    if cantidad <= 0:
        return None
    lo, hi = 0.0, 1e6 if biomasa else 500.0
    for _ in range(100):
        mid = (lo + hi) / 2
        if evaluar(I, cantidad, mid, om, tasa, anios, dolar, biomasa, extra_costo)["VAN"] > 0: hi = mid
        else: lo = mid
    return (lo + hi) / 2


def alternativas(pl, r, precio: float, dolar: float = costos.DOLAR, tasa: float = 0.10, anios: int = VIDA, dT: float | None = None,
                 cop: float | None = None, pesos=(1 / 3, 1 / 3, 1 / 3), con_bomba: bool = True) -> dict:
    """Las cuatro alternativas con área, inversión, evaluación y puntaje. precio: US$/MMBtu (gas) o $/m3 estéreo (biomasa)."""
    snk, cal, h, comb = _contexto(pl, r)
    bio = comb == "biomasa"
    dT = float(r["dT_min"] if dT is None else dT); Tf = float(r["T_final"]); cop = float(r.get("cop", 2.0) if cop is None else cop)
    m = rec.mapa(pl.residuales(), snk, dT, Tf); hs = {s[0]: s for s in m.corrientes}
    sens = [s for s in m.corrientes if s[3] is not None]
    alts = {}
    cond = rec.Mapa(sens, snk, dT, Tf); q1, f1 = rec.cascada(cond) if sens else (0.0, [])
    q2, f2 = rec.cascada(m)
    corr3 = dict(hs); m3 = m; extra3 = 0
    if len(sens) > 1:
        CPm = sum(s[3] for s in sens); Qm = sum(s[4] for s in sens); Tm = Tf + Qm / CPm
        corr3["FC"] = ("FC", Tm, Tf, CPm, Qm)
        m3 = rec.Mapa([s for s in m.corrientes if s[3] is None] + [corr3["FC"]], snk, dT, Tf); extra3 = 1
    q3, f3 = rec.cascada(m3)
    for k, q, f, corr, extra in (("A1", q1, f1, hs, 0), ("A2", q2, f2, hs, 0), ("A3", q3, f3, corr3, extra3)):
        et = etapas(f, corr, bio)
        inv = {n: costos.inversion_hx_mmclp([e[c] for e in et], dolar=dolar) for n, c in
               (("min", "A_altoU"), ("medio", "A_medio"), ("max", "A_bajoU"))}
        ahorro, cant = _valor(q, h, cal, comb, precio, dolar) if h else (0.0, 0.0)
        om = OM_HX * inv["medio"]
        alts[k] = dict(nombre=NOMBRES[k], Q=q, cob=q / snk.Q if snk.Q else 0.0, etapas=et, n_hx=len(et), equipos=len(et) + extra,
                       area_medio=sum(e["A_medio"] for e in et), inv=inv, om=om, ahorro=ahorro, cantidad=cant, extra_costo=0.0)
    if con_bomba and h:
        hp = rec.bomba_calor(snk.Q, cop, [hs[n] for n in r.get("fuentes_bomba", []) if n in hs])
        inv = {n: costos.inversion_bomba_calor_mmclp(snk.Q, i) for i, n in enumerate(("min", "medio", "max"))}
        Eel = hp["electricidad_kW"] * h / 1000
        om = (HP_OM_FIJO * snk.Q / 1000 + HP_OM_VAR * snk.Q * h / 1000) * costos.EURO / 1e6
        ahorro, cant = _valor(snk.Q, h, cal, comb, precio, dolar)
        alts["A4"] = dict(nombre=NOMBRES["A4"], Q=snk.Q, cob=1.0, etapas=[], n_hx=0, equipos=2 + len(hp["fuentes"]), area_medio=0.0,
                          inv=inv, om=om, ahorro=ahorro, cantidad=cant, elec_MWh=Eel, extra_costo=Eel * 1000 * PMM_LIBRES / 1e6)
    for a in alts.values():
        I = a["inv"]["medio"]
        a["ev"] = evaluar(I, a["cantidad"], precio, a["om"], tasa, anios, dolar, bio, a["extra_costo"])
        a["p_eq"] = precio_equilibrio(I, a["cantidad"], a["om"], tasa, anios, dolar, bio, a["extra_costo"])
    cands = [k for k, a in alts.items() if a["Q"] > 1e-6 and a["p_eq"] is not None]
    pt = puntajes(alts, cands, pesos)
    return dict(alts=alts, candidatos=cands, puntajes=pt, ganador=max(pt, key=pt.get) if pt else None,
                barrido=barrido(alts, cands), biomasa=bio, dT=dT, Qsumidero=snk.Q, unidad_precio="$/m³ estéreo" if bio else "US$/MMBtu")


def puntajes(alts, cands, pesos) -> dict:
    """Suma ponderada con normalización por rango (Capítulo 3)."""
    out = {k: 0.0 for k in cands}
    for (c, _n, alto), w in zip(CRITERIOS, pesos):
        vals = [alts[k][c] for k in cands]
        if not vals:
            continue
        lo, hi = min(vals), max(vals)
        for k in cands:
            x = 1.0 if hi == lo else (alts[k][c] - lo) / (hi - lo)
            out[k] += w * (x if alto else 1 - x)
    return out


def barrido(alts, cands, paso: float = 0.01) -> dict:
    """Fracción de las combinaciones de pesos (paso 0,01, suma 1) en que gana cada alternativa."""
    gana = {k: 0 for k in cands}; n = 0; N = int(round(1 / paso))
    if not cands:
        return gana
    for i in range(N + 1):
        for j in range(N + 1 - i):
            s = puntajes(alts, cands, (i / N, j / N, (N - i - j) / N)); gana[max(s, key=s.get)] += 1; n += 1
    return {k: v / n for k, v in gana.items()}


def crf(tasa: float, anios: int) -> float:
    """Factor de recuperación del capital."""
    return 1 / anios if tasa == 0 else tasa * (1 + tasa) ** anios / ((1 + tasa) ** anios - 1)


def dTmin_optimo(pl, r, precio: float, dolar: float = costos.DOLAR, tasa: float = 0.10, anios: int = VIDA, alternativa: str = "A3",
                 dTs=None) -> dict:
    """Costo total anual (MM$ por temporada) de la alternativa para cada ΔTmin: capital anualizado + operación y mantención
    + combustible que la caldera sigue quemando. El óptimo es el ΔTmin de menor costo total."""
    dTs = list(dTs or [x / 2 for x in range(2, 41)])
    snk, cal, h, comb = _contexto(pl, r)
    base, _ = _valor(snk.Q, h, cal, comb, precio, dolar) if h else (0.0, 0.0)
    f = crf(tasa, anios); filas = []
    for d in dTs:
        a = alternativas(pl, r, precio, dolar, tasa, anios, dT=d, con_bomba=False)["alts"].get(alternativa)
        cap = a["inv"]["medio"] * f; rem = base - a["ahorro"]
        filas.append(dict(dT=d, Q=a["Q"], area=a["area_medio"], capital=cap, om=a["om"], combustible=rem, total=cap + a["om"] + rem))
    mejor = min(filas, key=lambda x: x["total"])
    return dict(filas=filas, optimo=mejor, crf=f, base=base)
