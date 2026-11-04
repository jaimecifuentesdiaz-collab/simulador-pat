"""Herramientas de cálculo de apoyo (PAT 132), sacadas por ingeniería inversa de simuladores de procesos y de planta:
DWSIM y CheCalc (intercambiadores), Aspen Energy Analyzer y PinCH (tabla problema del pinch), tablas de vapor (IAPWS-IF97),
SuperPro Designer (evaporadores, caldera, utilidades, costos y emisiones), Engineering ToolBox (bombas y tuberías) y
Simul8/FlexSim (OEE, ley de Little y variabilidad). Cada función devuelve un diccionario con sus resultados y avisos.
Las fuentes de cada ecuación están en FUENTES (APA 7) y en el Capítulo 5."""
from __future__ import annotations
import math
from .propiedades import sat, psat_kPa, trabajo_isentropico

FUENTES = {
    "intercambiador": "Incropera et al. (2007); Bowman, Mueller y Nagle (1940)",
    "pinch": "Linnhoff y Hindmarsh (1983); Kemp (2007)",
    "vapor": "Wagner et al. (2000), IAPWS-IF97",
    "evaporador": "Singh y Heldman (2014)",
    "caldera": "Van Loo y Koppejan (2008); IPCC (2006)",
    "emisiones": "IPCC (2006), Vol. 2, Cap. 2, Tablas 2.2 a 2.5",
    "secador": "Mujumdar (2014)",
    "letalidad": "Holdsworth y Simpson (2016); Singh y Heldman (2014)",
    "tuberia": "Swamee y Jain (1976); Steffe (1996)",
    "costos": "Williams (1947); Lang (1948); Turton et al. (2018)",
    "oee": "Nakajima (1988); Little (1961); Hopp y Spearman (2008)",
}
# Factores de emisión por defecto de la combustión estacionaria (IPCC, 2006, Vol. 2, Cap. 2, Tabla 2.2), kg de CO2 por TJ (PCI)
FACTOR_CO2_KG_TJ = {"Gas natural": 56100.0, "Diésel (gas oil)": 74100.0, "Gas licuado (GLP)": 63100.0, "Madera y astilla (biogénico)": 112000.0}
# PAT 133, mejora 11: valores de partida citables con su fecha
FACTOR_RED_SEN = 0.2384     # t CO2e/MWh, Sistema Eléctrico Nacional 2023 (Coordinador Eléctrico Nacional, 11-01-2024); mismo de los Capítulos 2 a 4
FUENTE_FACTOR_RED = ("0,2384 t CO2e/MWh: factor de emisión del Sistema Eléctrico Nacional de 2023, Coordinador Eléctrico Nacional, "
                     "publicado el 11-01-2024 (el mismo de los Capítulos 2 a 4). Reemplácelo por el del año vigente cuando se publique")
CEPCI_ACTUAL = 797.9        # promedio anual 2023 (Chemical Engineering, 25-03-2024); 2024 y 2025 solo con suscripción
FUENTE_CEPCI = ("797,9: promedio anual 2023 del CEPCI (Chemical Engineering, 25-03-2024, de acceso libre). El promedio 2025 subió 1,6 % sobre "
                "el de 2024 (Chemical Engineering, 02-04-2026), pero sus valores solo se publican con suscripción")
LANG = {"Sólidos": 3.10, "Sólidos y fluidos": 3.63, "Fluidos": 4.74}          # Lang (1948), por tipo de planta


# ---------------------------------------------------------------- intercambiadores
def lmtd(dT1: float, dT2: float) -> float:
    if dT1 <= 0 or dT2 <= 0:
        raise ValueError("Las diferencias de temperatura en los extremos deben ser positivas (se cruzan las temperaturas)")
    return dT1 if abs(dT1 - dT2) < 1e-9 else (dT1 - dT2) / math.log(dT1 / dT2)


def factor_F_12(Thi, Tho, Tci, Tco) -> float | None:
    """Factor de corrección F de un intercambiador de tubos y carcasa 1-2 (Bowman et al., 1940). None si no es factible."""
    R = (Thi - Tho) / (Tco - Tci); P = (Tco - Tci) / (Thi - Tci); S = math.sqrt(R * R + 1)
    try:
        if abs(R - 1) < 1e-6:
            num = S * P / (1 - P); den = math.log((2 - P * (2 - S)) / (2 - P * (2 + S)))
            return num / den
        num = S * math.log((1 - P) / (1 - P * R))
        den = (R - 1) * math.log((2 - P * (R + 1 - S)) / (2 - P * (R + 1 + S)))
        F = num / den
        return F if 0 < F <= 1.0001 else None
    except (ValueError, ZeroDivisionError):
        return None


def intercambiador(m_frio_kgs, cp_frio, Tci, Tco, Thi, Tho, U_Wm2K, F_min=0.75) -> dict:
    """Dimensiona por LMTD: Q = U·A·F·LMTD en contracorriente y en tubos y carcasa 1-2; además ε y NTU."""
    if Tco <= Tci or Thi <= Tho:
        raise ValueError("El fluido frío debe calentarse y el caliente enfriarse")
    Q = m_frio_kgs * cp_frio * (Tco - Tci)                     # kW
    Cc = Q / (Tco - Tci); Ch = Q / (Thi - Tho)
    dT = lmtd(Thi - Tco, Tho - Tci)
    A = Q * 1000 / (U_Wm2K * dT)
    Cmin, Cmax = min(Cc, Ch), max(Cc, Ch); Cr = Cmin / Cmax
    ntu = U_Wm2K * A / 1000 / Cmin
    eps = Q / (Cmin * (Thi - Tci))
    F = factor_F_12(Thi, Tho, Tci, Tco)
    avisos = []
    if F is None or F < F_min:
        avisos.append(f"Con una carcasa 1-2 el factor F queda {'sin solución' if F is None else f'en {F:.2f}'.replace('.', ',')}, bajo el mínimo de "
                      f"{F_min:.2f}".replace(".", ",") + ": use contracorriente pura (placas) o varias carcasas en serie")
    return dict(Q_kW=Q, CP_frio_kWK=Cc, CP_caliente_kWK=Ch, LMTD=dT, A_contracorriente_m2=A, F_12=F,
                A_12_m2=A / F if F else None, NTU=ntu, efectividad=eps, Cr=Cr, avisos=avisos)


# ---------------------------------------------------------------- pinch (tabla problema)
def tabla_problema(corrientes: list[tuple], dTmin: float) -> dict:
    """corrientes = [(nombre, T_entrada, T_salida, CP kW/K)]. Caliente si T_entrada > T_salida.
    Temperaturas desplazadas en ΔTmin/2, balance por intervalo y cascada (Linnhoff y Hindmarsh, 1983)."""
    est = []
    for n, a, b, cp in corrientes:
        if cp <= 0 or a == b:
            continue
        cal = a > b; d = -dTmin / 2 if cal else dTmin / 2
        est.append((n, a + d, b + d, cp, cal))
    if not est:
        raise ValueError("Ingrese al menos una corriente con CP positivo y temperaturas distintas")
    Ts = sorted({t for e in est for t in (e[1], e[2])}, reverse=True)
    filas, R, acum = [], 0.0, [0.0]
    for hi, lo in zip(Ts, Ts[1:]):
        sc = sum(e[3] for e in est if e[4] and min(e[1], e[2]) <= lo and max(e[1], e[2]) >= hi)
        sf = sum(e[3] for e in est if not e[4] and min(e[1], e[2]) <= lo and max(e[1], e[2]) >= hi)
        dH = (sc - sf) * (hi - lo); R += dH; acum.append(R)
        filas.append(dict(T_alta=hi, T_baja=lo, CP_calientes=sc, CP_frias=sf, dH=dH, cascada=R))
    QH = max(0.0, -min(acum)); QC = acum[-1] + QH
    corr = [a + QH for a in acum]
    i = min(range(len(corr)), key=lambda k: corr[k])
    pinch = Ts[i] if corr[i] < 1e-6 and 0 < QH + QC else None
    for f, c in zip(filas, corr[1:]):
        f["cascada_corregida"] = c
    gcc = [(T, c) for T, c in zip(Ts, corr)]                   # gran curva compuesta: T desplazada vs calor neto
    return dict(QH_min=QH, QC_min=QC, T_pinch_desplazada=pinch,
                T_pinch_caliente=None if pinch is None else pinch + dTmin / 2,
                T_pinch_fria=None if pinch is None else pinch - dTmin / 2,
                recuperado=sum(e[3] * abs(e[1] - e[2]) for e in est if e[4]) - QC, intervalos=filas, gran_curva=gcc,
                compuestas=dict(caliente=_compuesta([e for e in est if e[4]], dTmin / 2, 0.0),
                                fria=_compuesta([e for e in est if not e[4]], -dTmin / 2, QC)))


def _compuesta(est, desplaz, H0):
    """Puntos (H acumulado kW, T real °C) de una curva compuesta; la fría parte en QC_min para mostrar el traslape."""
    if not est:
        return []
    Ts = sorted({t for e in est for t in (e[1], e[2])}); H = H0; pts = [(H, Ts[0] + desplaz)]
    for lo, hi in zip(Ts, Ts[1:]):
        H += sum(e[3] for e in est if min(e[1], e[2]) <= lo and max(e[1], e[2]) >= hi) * (hi - lo)
        pts.append((H, hi + desplaz))
    return pts


# ---------------------------------------------------------------- vapor y evaporadores
def vapor_saturado(T: float) -> dict:
    hf, hg = sat(T)
    return dict(T=T, p_kPa=psat_kPa(T), hf=hf, hg=hg, hfg=hg - hf)


def evaporador(F_t_h, xF, xP, efectos=3, factor_economia=0.85, T_ebullicion=70.0, T_condensacion=75.0, eta_mvr=0.75) -> dict:
    """Agua evaporada, vapor vivo con la economía E ≈ factor × n efectos y, como alternativa, potencia de un MVR."""
    if not 0 < xF < xP < 1:
        raise ValueError("Los sólidos deben cumplir 0 < x de entrada < x de salida < 1")
    mw = F_t_h * (1 - xF / xP); E = factor_economia * efectos
    w = trabajo_isentropico(T_ebullicion, T_condensacion) / eta_mvr        # kJ por kg de agua
    return dict(agua_t_h=mw, producto_t_h=F_t_h - mw, economia=E, vapor_t_h=mw / E,
                mvr_kJ_kg=w, mvr_kW=w * mw / 3.6, mvr_kWh_t=w / 3.6, latente_kJ_kg=sat(T_ebullicion)[1] - sat(T_ebullicion)[0])


# ---------------------------------------------------------------- caldera, combustible y emisiones
def pci_humedo(pci_seco_MJkg: float, humedad_bh: float) -> float:
    """PCI en base húmeda: PCI_seco·(1 − w) − 2,443·w (MJ/kg), calor latente del agua a 25 °C."""
    return pci_seco_MJkg * (1 - humedad_bh) - 2.443 * humedad_bh


def caldera(vapor_t_h, T_vapor, T_agua, eta, PCI_MJkg, precio_comb_por_GJ=0.0, factor_co2_kg_TJ=56100.0) -> dict:
    """Método directo: Q = m_v·(h_g − h_agua); combustible = Q/(η·PCI); costo del vapor y CO2 del alcance 1."""
    hg = sat(T_vapor)[1]; hw = sat(T_agua)[0]
    Q = vapor_t_h * 1000 / 3600 * (hg - hw)                  # kW
    GJh = Q * 3.6 / 1000 / eta
    return dict(Q_kW=Q, h_vapor=hg, h_agua=hw, p_vapor_kPa=psat_kPa(T_vapor), combustible_kgh=GJh * 1000 / PCI_MJkg,
                combustible_GJ_h=GJh, costo_por_t_vapor=GJh * precio_comb_por_GJ / vapor_t_h if vapor_t_h else 0.0,
                co2_kgh=GJh / 1000 * factor_co2_kg_TJ)


def emisiones(GJ_combustible_anual, factor_kg_TJ, kWh_anual=0.0, factor_red_t_MWh=0.0, biogenico=False) -> dict:
    """Alcance 1 = energía del combustible × factor (IPCC, 2006); alcance 2 = electricidad × factor de la red.
    El CO2 de la biomasa se informa aparte (biogénico) y no suma al total."""
    a1 = GJ_combustible_anual / 1000 * factor_kg_TJ / 1000     # t
    a2 = kWh_anual / 1000 * factor_red_t_MWh
    return dict(alcance1_t=0.0 if biogenico else a1, biogenico_t=a1 if biogenico else 0.0, alcance2_t=a2,
                total_t=(0.0 if biogenico else a1) + a2)


# ---------------------------------------------------------------- secador y letalidad
def secador(m_humedo_t_h, w_entrada, w_salida, q_MJ_kg_agua=3.2) -> dict:
    if not 0 <= w_salida < w_entrada < 1:
        raise ValueError("La humedad de salida debe ser menor que la de entrada (base húmeda)")
    seco = m_humedo_t_h * (1 - w_entrada); prod = seco / (1 - w_salida); agua = m_humedo_t_h - prod
    return dict(seco_t_h=seco, producto_t_h=prod, agua_t_h=agua, Q_kW=agua * 1000 * q_MJ_kg_agua / 3.6,
                Q_minimo_kW=agua * 1000 * 2.443 / 3.6)


def letalidad(perfil: list[tuple], T_ref=121.1, z=10.0, D_ref: float | None = None) -> dict:
    """perfil = [(t_min, T °C)] en orden; F = Σ 10^((T − T_ref)/z)·Δt por trapecios. Con D_ref, reducciones decimales F/D."""
    F = 0.0
    for (t0, T0), (t1, T1) in zip(perfil, perfil[1:]):
        F += (10 ** ((T0 - T_ref) / z) + 10 ** ((T1 - T_ref) / z)) / 2 * (t1 - t0)
    return dict(F_min=F, reducciones=F / D_ref if D_ref else None)


# ---------------------------------------------------------------- hidráulica
def tuberia(Q_m3h, D_mm, L_m, rho=1000.0, mu_Pas=0.001, rug_mm=0.045, K=None, n=None, eta_bomba=0.65, dz_m=0.0) -> dict:
    """Δp por Darcy-Weisbach. Newtoniano: Swamee-Jain (turbulento) o 64/Re (laminar). Ley de potencia (pasta):
    Reynolds de Metzner-Reed y f = 64/Re_MR en laminar (Steffe, 1996). Potencia de la bomba = ρ·g·Q·H/η."""
    D = D_mm / 1000; A = math.pi * D * D / 4; Qs = Q_m3h / 3600; v = Qs / A
    if K and n:
        Re = rho * v ** (2 - n) * D ** n / (K * 8 ** (n - 1) * ((3 * n + 1) / (4 * n)) ** n)
    else:
        Re = rho * v * D / mu_Pas
    if Re < 2100:
        f = 64 / Re; reg = "laminar"
    else:
        f = 0.25 / math.log10(rug_mm / 1000 / (3.7 * D) + 5.74 / Re ** 0.9) ** 2; reg = "turbulento"
        if K and n:
            reg = "turbulento (Swamee-Jain es aproximado para la ley de potencia)"
    dp = f * L_m / D * rho * v * v / 2
    H = dp / (rho * 9.81) + dz_m
    return dict(v=v, Re=Re, f=f, regimen=reg, dp_kPa=dp / 1000, H_m=H, potencia_kW=rho * 9.81 * Qs * H / eta_bomba / 1000)


# ---------------------------------------------------------------- costos de equipos
def costo_escalado(C1, S1, S2, exponente=0.6, I1=1.0, I2=1.0, f_lang=None) -> dict:
    """Regla de los seis décimos con índice de costos: C2 = C1·(S2/S1)^n·(I2/I1); planta = f_Lang·C2."""
    C2 = C1 * (S2 / S1) ** exponente * (I2 / I1)
    return dict(equipo=C2, planta=C2 * f_lang if f_lang else None, factor_tamano=(S2 / S1) ** exponente, factor_indice=I2 / I1)


# ---------------------------------------------------------------- OEE y variabilidad
def oee(tiempo_planificado_h, tiempo_operado_h, capacidad_ideal_t_h, producido_t, bueno_t) -> dict:
    A = tiempo_operado_h / tiempo_planificado_h
    P = producido_t / (capacidad_ideal_t_h * tiempo_operado_h)
    Q = bueno_t / producido_t if producido_t else 0.0
    return dict(disponibilidad=A, rendimiento=P, calidad=Q, oee=A * P * Q)


def kingman(utilizacion, ca=1.0, cs=1.0, te_h=1.0) -> float:
    """Espera en cola (h) de Kingman: [(ca² + cs²)/2]·[u/(1 − u)]·te; tiende a infinito cuando u → 1."""
    if utilizacion >= 1:
        return math.inf
    return (ca * ca + cs * cs) / 2 * utilizacion / (1 - utilizacion) * te_h


def little(llegada_por_h, espera_h) -> float:
    """Inventario en proceso (WIP) = λ·W (Little, 1961)."""
    return llegada_por_h * espera_h
