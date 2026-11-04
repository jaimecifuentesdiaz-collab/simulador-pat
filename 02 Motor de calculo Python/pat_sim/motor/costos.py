"""Inversión de orden de magnitud de intercambiadores y bombas de calor (fase 7, PAT 123, 29-10-2026).

Fuentes (cada parámetro con su fecha):
- Correlación de tubo y carcasa en US$ de 2020, válida de 1 a 3.500 m²: Shamoushaki et al. (2021), Energies 14(9), 2665,
  ecuación 4 y Tabla 6. https://doi.org/10.3390/en14092665
- Actualización 2020 → sep-2026: índice de precios al productor PCU332410332410 (BLS, vía FRED, act. 15-10-2026):
  promedio 2020 = 191,183; septiembre de 2026 = 343,598.
- Factor de instalación 2,5 = 1 / 0,40, fracción de equipo de la Danish Energy Agency (2026), hoja 2.a (supuesto).
- Bomba de calor hasta 125 °C: 1,20 (0,90 a 1,50) MEUR de 2025 por MW térmico, Danish Energy Agency (2026), hoja 2.a.
- Dólar 990,35 $/US$ y euro 1.108,39 $/EUR del 26-10-2026 (Banco Central de Chile).
Los Capítulos 2 a 4 usan estas mismas cifras (Capitulos 2 a 4 Agrozzi/scripts/calc_cap234.py)."""
from __future__ import annotations
import math

SHAMOUSHAKI_TYC = dict(a=-0.06395, b=947.2, c=227.9)
PPI_2020 = (191.1 * 2 + 191.2 * 10) / 12
PPI_SEP_2026 = 343.598
F_INSTALACION = 2.5
DOLAR = 990.35
EURO = 1108.39
BOMBA_CALOR_MEUR_MW = (0.90, 1.20, 1.50)


def costo_equipo_usd2020(area_m2: float) -> float:
    """Costo de un intercambiador de tubo y carcasa (US$ de 2020)."""
    A = max(area_m2, 1.0); s = SHAMOUSHAKI_TYC
    return math.log(A) + s["a"] * A * A + s["b"] * A + s["c"]


A_MAX_CORRELACION = 3500.0   # m2, límite de validez de la correlación (Shamoushaki et al., 2021, Tabla 6)


def costo_equipo_partido_usd2020(area_m2: float) -> float:
    """PAT 133: sobre 3.500 m2 la etapa se reparte en unidades iguales en paralelo dentro del rango de la correlación
    (bajo 3.500 m2 da lo mismo que costo_equipo_usd2020)."""
    n = max(1, math.ceil(area_m2 / A_MAX_CORRELACION))
    return n * costo_equipo_usd2020(area_m2 / n)


def inversion_hx_mmclp(areas_m2: list[float], ppi=PPI_SEP_2026, f_inst=F_INSTALACION, dolar=DOLAR) -> float:
    """Inversión instalada en millones de pesos para un conjunto de intercambiadores."""
    return sum(costo_equipo_partido_usd2020(a) for a in areas_m2) * ppi / PPI_2020 * f_inst * dolar / 1e6


def inversion_bomba_calor_mmclp(Q_kW: float, caso: int = 1, euro=EURO) -> float:
    """caso 0, 1, 2 = bajo, central, alto."""
    return BOMBA_CALOR_MEUR_MW[caso] * Q_kW / 1000 * euro
