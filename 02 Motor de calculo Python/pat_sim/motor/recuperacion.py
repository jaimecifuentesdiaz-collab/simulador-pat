"""Recuperación de calor: mapa de corrientes, cascada en serie y objetivo pinch (tabla del problema de
Linnhoff y Flower, 1978, citada en Klemeš et al., 2018). Mismo algoritmo que model.py del modelo Agrozzi."""
from __future__ import annotations
import itertools
from dataclasses import dataclass
from .corrientes import Residual
from .equipos import Sumidero


@dataclass
class Mapa:
    corrientes: list[tuple]   # (nombre, T_in, T_out, CP, Q); CP None = latente a T_in
    sumidero: Sumidero
    dT: float
    T_final: float

    @property
    def oferta(self) -> float:
        return sum(s[4] for s in self.corrientes)


def mapa(residuales: list[Residual], sumidero: Sumidero, dT=5.0, T_final=30.0, incluir: list[str] | None = None) -> Mapa:
    st = []
    for r in residuales:
        if incluir is not None and r.nombre not in incluir:
            continue
        if r.CP is None:
            st.append((r.nombre, float(r.T_in), None, None, float(r.Q)))
        else:
            To = r.T_out if r.T_out is not None else T_final
            st.append((r.nombre, float(r.T_in), float(To), float(r.CP), float(r.CP * (r.T_in - To))))
    return Mapa(st, sumidero, dT, T_final)


def _etapa(Tc, s, CPc, dT):
    nm, Ti, To, CP, Qav = s
    if CP is None:
        return max(0, min(Qav, CPc * (Ti - dT - Tc)))
    return max(min(CP * (Ti - max(To, Tc + dT)), CPc * (Ti - dT - Tc)), 0)


def orden_por_defecto(st, dT):
    """Por techo térmico creciente; a igual techo, primero los condensados y los de mayor CP."""
    return [s[0] for s in sorted(st, key=lambda s: (s[1] - dT, 0 if s[3] is not None else 1, -(s[3] or 0)))]


def cascada(m: Mapa, orden: list[str] | None = None):
    """Cascada en serie: el tomate pasa por una etapa de intercambio por corriente. Devuelve (kW, filas)."""
    snk = m.sumidero; Tc = snk.T_in; CPc = snk.CP
    hs = {s[0]: s for s in m.corrientes}; orden = orden or orden_por_defecto(m.corrientes, m.dT)
    filas = []; tot = 0.0
    for k in orden:
        Q = _etapa(Tc, hs[k], CPc, m.dT); Q = min(Q, CPc * (snk.T_out - Tc)); Tn = Tc + Q / CPc
        filas.append(dict(corriente=k, Q_kW=Q, T_entra=Tc, T_sale=Tn)); tot += Q; Tc = Tn
    return tot, filas


def mejor_cascada(m: Mapa):
    best = (0.0, None)
    for perm in itertools.permutations([s[0] for s in m.corrientes]):
        t, f = cascada(m, list(perm))
        if t > best[0] + 1e-6: best = (t, f)
    return best


def pinch(m: Mapa):
    """Objetivo de recuperación (kW), calor externo mínimo (kW) y temperatura(s) de pinch (°C)."""
    snk = m.sumidero; dT = m.dT; hot = m.corrientes
    pts = {snk.T_in + dT / 2, snk.T_out + dT / 2}
    for s in hot:
        pts.add(s[1] - dT / 2)
        if s[3] is not None: pts.add(s[2] - dT / 2)
    pts = sorted(pts, reverse=True); cum = 0.0; flujos = [(pts[0], 0.0)]
    for a, b in zip(pts[:-1], pts[1:]):
        q = 0.0
        for s in hot:
            if s[3] is None: continue
            q += s[3] * max(0, min(a, s[1] - dT / 2) - max(b, s[2] - dT / 2))
        q -= snk.CP * max(0, min(a, snk.T_out + dT / 2) - max(b, snk.T_in + dT / 2))
        cum += q; flujos.append((b, cum))
        for s in hot:
            if s[3] is None and abs(s[1] - dT / 2 - b) < 1e-9:
                cum += s[4]; flujos.append((b - 1e-9, cum))
    mn = min(f for _, f in flujos); Qh = max(0.0, -mn)
    pin = sorted(set(round(t + dT / 2, 3) for t, f in flujos if abs(f - mn) < 1e-6))
    return snk.Q - Qh, Qh, pin


def bomba_calor(Q_sumidero: float, cop: float, corrientes_frias: list[tuple]) -> dict:
    """Bomba de calor que cubre todo el sumidero: electricidad = Q/COP y calor de baja = Q(1 − 1/COP),
    tomado de las corrientes en el orden dado."""
    elec = Q_sumidero / cop; pide = Q_sumidero - elec; usado = []
    for s in corrientes_frias:
        if pide <= 1e-9: break
        q = min(pide, s[4]); usado.append((s[0], q)); pide -= q
    return dict(electricidad_kW=elec, calor_baja_kW=Q_sumidero - elec, fuentes=usado, falta_kW=max(0.0, pide))
