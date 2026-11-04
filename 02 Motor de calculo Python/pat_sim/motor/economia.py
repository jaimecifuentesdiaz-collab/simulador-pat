"""Gas natural desplazado, CO2 evitado, valorización y evaluación económica (VAN, TIR)."""
from __future__ import annotations

K_MMBTU = 293.071  # kWh por MMBtu


def gas(Q_kW: float, horas: float, caldera) -> dict:
    """Gas que la caldera quema para entregar Q_kW durante 'horas' (misma fórmula que fuel.py)."""
    eta = caldera.eta_pcs; HHV = float(caldera.v("HHV"))
    fuel_kWh = Q_kW * horas / eta; kg = fuel_kWh * 3.6 / HHV
    return dict(gas_MWh=fuel_kWh / 1000, kg=kg, m3=kg / float(caldera.v("densidad")),
                co2_t=kg * float(caldera.v("co2_kg_kg")) / 1000, MMBtu=fuel_kWh / K_MMBTU)


def valor_gas(MMBtu: float, precio_usd_mmbtu: float, dolar_clp: float) -> float:
    """Millones de pesos."""
    return MMBtu * precio_usd_mmbtu * dolar_clp / 1e6


def equilibrio_bomba_calor(cobertura_cascada: float, eta_pcs: float, cop: float, precio_elec_clp_kwh: float, dolar_clp: float) -> float:
    """Precio del gas (US$/MMBtu) sobre el cual la bomba de calor (que cubre todo el sumidero) conviene más que la cascada."""
    if cobertura_cascada >= 1:
        return None
    return (precio_elec_clp_kwh * eta_pcs / (cop * (1 - cobertura_cascada))) * K_MMBTU / dolar_clp


def van(flujos: list[float], tasa: float) -> float:
    return sum(f / (1 + tasa) ** i for i, f in enumerate(flujos))


def tir(flujos: list[float]) -> float | None:
    f = lambda r: van(flujos, r)
    lo, hi = -0.95, 10.0
    if f(lo) * f(hi) > 0: return None
    for _ in range(200):
        mid = (lo + hi) / 2
        if f(lo) * f(mid) <= 0: hi = mid
        else: lo = mid
    return (lo + hi) / 2


def evaluacion(inversion: float, ahorro_anual: float, costo_anual: float, anios: int, tasa: float) -> dict:
    flujos = [-inversion] + [ahorro_anual - costo_anual] * anios
    neto = ahorro_anual - costo_anual
    return dict(flujos=flujos, VAN=van(flujos, tasa), TIR=tir(flujos), recuperacion_anios=inversion / neto if neto > 0 else None)
