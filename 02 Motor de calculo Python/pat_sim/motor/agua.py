"""Agua recuperable de los condensados (PAT 133, mejora 12).

Estima los m³ por temporada de agua que la planta puede reutilizar en vez de captar: el condensado de la evaporación y del
vapor que ya está en el mapa de residuales (corrientes sensibles «Condensado…» y latentes de vapor que se condensa) y, en la
biomasa, el agua que se condensa del escape del secador cuando se enfría bajo su punto de rocío.

Masa de cada corriente:
- residual sensible de condensado: m = CP·3600/cp del agua (kg/h);
- residual latente de vapor: m = Q·3600/λ(T) (kg/h), salvo que el mismo equipo tenga un condensado a la misma temperatura
  (es el mismo agua, por ejemplo F3 y F1c del evaporador de tres efectos);
- escape del secador: agua evaporada menos la que el aire puede llevar saturado a la temperatura de enfriamiento.
El calor excedente de los MVR (fuera del mapa) no suma agua: su masa ya está en el condensado del MVR.
Referencia de la reutilización de condensados en la pasta de tomate: Amon et al. (2015).
"""
from __future__ import annotations
from .propiedades import CPW, latente, psat_kPa

P_ATM = 101.325             # kPa (el mismo valor de catalogos/biomasa.py)
RHO_AGUA_CAPTADA = 1000.0   # kg/m³; Supuesto: el agua captada se mide a temperatura ambiente, donde su densidad es cercana a 1.000 kg/m³
FUENTE = "Amon, Maulhardt, Wong, Kazama y Simmons (2015), Appl. Therm. Eng., 78, 525-532"


def _horas(pl, r=None) -> float | None:
    if isinstance(r, dict) and r.get("horas"):
        return float(r["horas"])
    for e in pl.equipos.values():
        if hasattr(e, "horas"):
            return float(e.horas())
    h = pl.globales.get("horas_temporada")
    return float(h) if h else None


def _es_secador(eq) -> bool:
    d = eq.resultado.detalle if eq.resultado else {}
    return "T_rocio" in d and "aire_kgh" in d and "agua_evaporada_kgh" in d


def agua_escape_secador(E_kgh: float, aire_kgh: float, T_rocio: float, T_enfriado: float) -> float:
    """Agua (kg/h) que se condensa del escape al enfriarlo hasta T_enfriado: la evaporada menos la que lleva el aire saturado."""
    if aire_kgh <= 0 or T_enfriado >= T_rocio:
        return 0.0
    ps = psat_kPa(T_enfriado); Ys = 0.622 * ps / (P_ATM - ps)
    return max(E_kgh - aire_kgh * Ys, 0.0)


def agua_recuperada(pl, r: dict | None = None, T_escape: float | None = None) -> dict:
    """Filas por corriente (kg/h y m³ por temporada) y el total. r: resumen de la planta (se usan sus horas, si trae);
    T_escape: temperatura hasta la que se enfría el escape de los secadores (None = la T_condensacion de cada secador)."""
    if not pl.resuelta:
        raise ValueError("Resuelva la planta antes de estimar el agua recuperable")
    h = _horas(pl, r); filas = []; avisos = []
    if h is None:
        avisos.append("La planta no declara horas de temporada: el total se informa solo en kg/h")
    secadores = {k for k, e in pl.equipos.items() if _es_secador(e)}
    res = [x for x in pl.residuales(solo_mapa=False) if x.equipo not in secadores]
    for x in res:
        d = (x.descripcion or "").lower()
        if x.CP is not None and "condensado" in d:
            m = x.CP * 3600 / CPW; tipo = "Condensado (sensible)"; nota = "m = CP·3.600/cp del agua"; cuenta = True
        elif x.CP is None and "vapor" in d and x.en_mapa:
            gemelo = next((y for y in res if y is not x and y.equipo == x.equipo and y.CP is not None
                           and "condensado" in (y.descripcion or "").lower() and abs(y.T_in - x.T_in) < 0.05), None)
            m = x.Q * 3600 / latente(x.T_in); tipo = "Vapor que se condensa (latente)"
            cuenta = gemelo is None
            nota = "m = Q·3.600/λ(T)" if cuenta else f"Es el mismo agua del condensado {gemelo.nombre}: no se suma"
        else:
            continue
        filas.append(dict(corriente=x.nombre, equipo=x.equipo, tipo=tipo, T=x.T_in, m_kgh=m, cuenta=cuenta, nota=nota,
                          m3_temporada=m * h / RHO_AGUA_CAPTADA if (h and cuenta) else (0.0 if h else None)))
    for k in sorted(secadores):
        eq = pl.equipos[k]; dd = eq.resultado.detalle
        Tc = float(T_escape) if T_escape is not None else float(eq.v("T_condensacion")) if "T_condensacion" in eq.params else 30.0
        Td = float(dd["T_rocio"]); m = agua_escape_secador(float(dd["agua_evaporada_kgh"]), float(dd["aire_kgh"]), Td, Tc)
        nota = (f"Enfriado de {Td:.1f} a {Tc:.1f} °C, bajo el punto de rocío" if m > 0 else
                f"El punto de rocío ({Td:.1f} °C) no supera la temperatura de enfriamiento ({Tc:.1f} °C): no condensa").replace(".", ",")
        filas.append(dict(corriente=f"Escape del secador {k}", equipo=k, tipo="Agua condensada del escape", T=Td, m_kgh=m, cuenta=True,
                          nota=nota, m3_temporada=m * h / RHO_AGUA_CAPTADA if h else None))
    kgh = sum(f["m_kgh"] for f in filas if f["cuenta"])
    if not filas:
        avisos.append("La planta no tiene condensados en el mapa de residuales ni escapes de secador")
    return dict(filas=filas, total_kgh=kgh, total_m3_h=kgh / RHO_AGUA_CAPTADA, horas=h,
                total_m3_temporada=kgh * h / RHO_AGUA_CAPTADA if h else None, avisos=avisos, fuente=FUENTE)
