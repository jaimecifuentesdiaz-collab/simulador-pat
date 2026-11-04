"""Propiedades del agua y del vapor (IAPWS-IF97, paquete iapws) y constantes del modelo."""
from functools import lru_cache
from iapws import IAPWS97

CPW = 4.18  # kJ/kg·K, agua líquida (Tabla de vapor; mismo valor del Modelo_PAT_Agrozzi)


@lru_cache(maxsize=4096)
def sat(T: float) -> tuple[float, float]:
    """Entalpías del líquido y del vapor saturados a T (°C), en kJ/kg."""
    l = IAPWS97(T=T + 273.15, x=0)
    v = IAPWS97(T=T + 273.15, x=1)
    return l.h, v.h


def latente(T: float) -> float:
    hf, hg = sat(T)
    return hg - hf


@lru_cache(maxsize=1024)
def trabajo_isentropico(T_vapor: float, T_sat_descarga: float) -> float:
    """Trabajo isentrópico (kJ/kg) para comprimir vapor saturado a T_vapor hasta la presión de saturación de T_sat_descarga."""
    v1 = IAPWS97(T=T_vapor + 273.15, x=1)
    P2 = IAPWS97(T=T_sat_descarga + 273.15, x=1).P
    v2s = IAPWS97(P=P2, s=v1.s)
    return v2s.h - v1.h


@lru_cache(maxsize=4096)
def psat_kPa(T: float) -> float:
    """Presión de saturación del agua a T (°C), en kPa (IAPWS-IF97, región 4)."""
    return IAPWS97(T=T + 273.15, x=0).P * 1000


def tsat_C(P_kPa: float) -> float:
    """Temperatura de saturación (°C) a la presión parcial P_kPa (bisección sobre psat_kPa; sirve para el punto de rocío)."""
    lo, hi = 0.01, 200.0
    if P_kPa <= psat_kPa(lo):
        return lo
    for _ in range(80):
        mid = (lo + hi) / 2
        if psat_kPa(mid) < P_kPa: lo = mid
        else: hi = mid
    return (lo + hi) / 2


# ---------------------------------------------------------------- PAT 133 (mejora 9): propiedades de la pasta según °Brix y T
import math as _math

FUENTES_PASTA = {
    "cp": "Choi y Okos (1986), ecuaciones de cp por componente (agua, carbohidrato, proteína, grasa, fibra y ceniza)",
    "densidad": "Choi y Okos (1986), densidad por componente y regla de mezcla de volúmenes",
    "reologia": "Supuesto: ley de potencia ajustada al orden de magnitud de la pasta que usa la calculadora de tuberías "
                "(Steffe, 1996: K de 10 a 20 Pa·sⁿ y n cercano a 0,35 a 0,40); falta una fuente con la tabla por °Brix",
    "agua": "Choi y Okos (1986) para la densidad del agua; ecuación de Vogel con constantes de uso común para su viscosidad (Supuesto)",
}

# Choi y Okos (1986): cp en kJ/kg·K y densidad en kg/m³, T en °C (válidas de −40 a 150 °C)
_CP_CO = {"agua": (4.1762, -9.0864e-5, 5.4731e-6), "carbohidrato": (1.5488, 1.9625e-3, -5.9399e-6),
          "proteina": (2.0082, 1.2089e-3, -1.3129e-6), "grasa": (1.9842, 1.4733e-3, -4.8008e-6),
          "fibra": (1.8459, 1.8306e-3, -4.6509e-6), "ceniza": (1.0926, 1.8896e-3, -3.6817e-6)}
_RHO_CO = {"agua": (997.18, 3.1439e-3, -3.7574e-3), "carbohidrato": (1599.1, -0.31046, 0.0),
           "proteina": (1329.9, -0.5184, 0.0), "grasa": (925.59, -0.41757, 0.0),
           "fibra": (1311.5, -0.36589, 0.0), "ceniza": (2423.8, -0.28063, 0.0)}
# Supuesto: los sólidos de la pasta se tratan como carbohidratos (azúcares y ácidos dominan los sólidos solubles) y los
# sólidos totales se igualan al °Brix; el usuario puede pasar otra composición de los sólidos (fracciones que suman 1)
COMPOSICION_SOLIDOS_PASTA = {"carbohidrato": 1.0}
# Supuesto (reología): K = K30·(°Brix/30)^b·exp(Ea/R·(1/T − 1/T0)) y n lineal en el °Brix, con T0 = 32 °C
REO_K30 = 18.0       # Pa·sⁿ a 30 °Brix y 32 °C, dentro de 10 a 20 Pa·sⁿ (Steffe, 1996, citado en la calculadora de tuberías)
REO_B = 2.7          # exponente de la concentración; Supuesto que lleva K a cerca de 0,2 Pa·sⁿ en un jugo de 5 a 6 °Brix
REO_EA = 10000.0     # J/mol, energía de activación del flujo; Supuesto de orden de magnitud para purés de fruta
REO_T0 = 32.0        # °C
GAMMA_REF = 50.0     # 1/s, tasa de corte de referencia para la viscosidad aparente (Supuesto: flujo en tubería)


def _poli(c, T):
    return c[0] + c[1] * T + c[2] * T * T


def _fracciones_pasta(brix: float, composicion: dict | None) -> dict:
    x = max(0.0, min(float(brix), 100.0)) / 100
    comp = composicion or COMPOSICION_SOLIDOS_PASTA; tot = sum(comp.values()) or 1.0
    fr = {"agua": 1 - x}
    for k, v in comp.items():
        if k not in _CP_CO:
            raise KeyError(f"Componente desconocido {k}; use {', '.join(_CP_CO)}")
        fr[k] = fr.get(k, 0.0) + x * v / tot
    return fr


def cp_choi_okos(T: float, fracciones: dict) -> float:
    """cp de un alimento (kJ/kg·K) como suma ponderada por masa de los cp de sus componentes (Choi y Okos, 1986)."""
    return sum(f * _poli(_CP_CO[k], T) for k, f in fracciones.items())


def densidad_choi_okos(T: float, fracciones: dict) -> float:
    """Densidad (kg/m³): 1/ρ = Σ xᵢ/ρᵢ (Choi y Okos, 1986)."""
    return 1.0 / sum(f / _poli(_RHO_CO[k], T) for k, f in fracciones.items() if f > 0)


def cp_pasta(brix: float, T: float, composicion: dict | None = None) -> float:
    """cp del jugo o la pasta de tomate (kJ/kg·K) según °Brix y T (°C), por composición agua y sólidos (Choi y Okos, 1986)."""
    return cp_choi_okos(T, _fracciones_pasta(brix, composicion))


def densidad_pasta(brix: float, T: float, composicion: dict | None = None) -> float:
    """Densidad del jugo o la pasta (kg/m³) según °Brix y T (Choi y Okos, 1986)."""
    return densidad_choi_okos(T, _fracciones_pasta(brix, composicion))


def densidad_agua(T: float) -> float:
    return _poli(_RHO_CO["agua"], T)


def viscosidad_agua(T: float) -> float:
    """Viscosidad del agua líquida (Pa·s), ecuación de Vogel μ = A·10^(B/(T − C)) con A = 2,414e-5 Pa·s, B = 247,8 K y C = 140 K
    (Supuesto: constantes de uso común; da 0,89 mPa·s a 25 °C)."""
    return 2.414e-5 * 10 ** (247.8 / (T + 273.15 - 140.0))


def reologia_pasta(brix: float, T: float) -> tuple[float, float]:
    """Índice de consistencia K (Pa·sⁿ) e índice de flujo n de la ley de potencia del concentrado de tomate (Supuesto declarado
    en FUENTES_PASTA["reologia"]). Válido como estimación entre 4 y 40 °Brix y entre 20 y 100 °C."""
    b = max(1.0, float(brix))
    n = max(0.25, min(0.65, 0.60 - 0.0075 * (b - 5.0)))
    K = REO_K30 * (b / 30.0) ** REO_B * _math.exp(REO_EA / 8.314 * (1 / (T + 273.15) - 1 / (REO_T0 + 273.15)))
    return K, n


def viscosidad_aparente_pasta(brix: float, T: float, gamma: float = GAMMA_REF) -> float:
    """Viscosidad aparente μa = K·γ̇^(n − 1) (Pa·s) a la tasa de corte γ̇ (1/s)."""
    K, n = reologia_pasta(brix, T)
    return K * float(gamma) ** (n - 1)


def propiedades_pasta(brix: float, T: float, gamma: float = GAMMA_REF, composicion: dict | None = None) -> dict:
    K, n = reologia_pasta(brix, T)
    return dict(brix=brix, T=T, cp=cp_pasta(brix, T, composicion), densidad=densidad_pasta(brix, T, composicion), K=K, n=n,
                gamma=gamma, mu_aparente=K * gamma ** (n - 1), cp_modelo_lineal=CPW - (CPW - 1.5) * brix / 100)
