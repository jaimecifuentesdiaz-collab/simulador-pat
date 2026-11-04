"""Resumen genérico de recuperación de calor y gas para cualquier planta del simulador.

Es la versión sin nombres fijos de escenarios.agrozzi.resumen: toma la temperatura mínima de aproximación y la
temperatura final del residual de pl.globales, elige el sumidero (por defecto el de mayor calor) y la caldera que
exista en la planta. Para la planta basada en Agrozzi entrega las mismas cifras que agrozzi.resumen (hay una prueba).
"""
from __future__ import annotations
from . import recuperacion as rec, economia as eco

# Fuentes de la bomba de calor del Capítulo 1 (el condensado del último efecto y el vapor del flash, en ese orden)
FUENTES_BOMBA_AGROZZI = ("F3", "F2", "F1c")
T_FUENTE_BOMBA_MAX = 60.0   # °C; para otras plantas: corrientes que ceden calor a esta temperatura o menos, las latentes primero


def _horas(pl) -> float | None:
    for e in pl.equipos.values():
        if hasattr(e, "horas"):
            return float(e.horas())
    h = pl.globales.get("horas_temporada")
    return float(h) if h else None


def _caldera(pl):
    return next((e for e in pl.equipos.values() if e.tipo.startswith("caldera")), None)


def resumen_planta(pl, cop: float = 2.0, sumidero: str | None = None, fuentes_bomba: list[str] | None = None) -> dict:
    g = pl.globales; dT = float(g.get("dT_min", 5.0)); Tfin = float(g.get("T_final_residual", 30.0))
    h = _horas(pl); cal = _caldera(pl)
    out = dict(horas=h, dT_min=dT, T_final=Tfin, cop=cop, avisos=list(pl.avisos),
               servicios=dict(vapor_kW=pl.servicio_total("vapor_kW"), electricidad_kW=pl.servicio_total("electricidad_kW"),
                              vapor_kgh=pl.servicio_total("vapor_kgh"), calor_kW=pl.servicio_total("calor_kW")), sin_sumidero=False)
    snks = pl.sumideros()
    if not snks:
        out["sin_sumidero"] = True
        return out
    cand = [s for s in snks if sumidero is None or s.equipo == sumidero] or snks
    snk = max(cand, key=lambda s: s.Q)
    m = rec.mapa(pl.residuales(), snk, dT, Tfin)
    casc, filas = rec.cascada(m); tg, qh, pin = rec.pinch(m)
    cond = rec.mapa(pl.residuales(), snk, dT, Tfin, incluir=[s[0] for s in m.corrientes if s[3] is not None])
    alt2, _ = rec.cascada(cond)
    nombres = [s[0] for s in m.corrientes]
    if fuentes_bomba is None:
        fuentes_bomba = [n for n in FUENTES_BOMBA_AGROZZI if n in nombres]
        if not fuentes_bomba:
            baja = [s for s in m.corrientes if s[1] <= T_FUENTE_BOMBA_MAX]
            fuentes_bomba = [s[0] for s in sorted(baja, key=lambda s: (0 if s[3] is None else 1, -s[1]))]
    hs = {s[0]: s for s in m.corrientes}
    hp = rec.bomba_calor(snk.Q, cop, [hs[n] for n in fuentes_bomba if n in hs])
    out.update(
        sumidero=dict(nombre=snk.nombre, equipo=snk.equipo, T_in=snk.T_in, T_out=snk.T_out, CP=snk.CP, Q=snk.Q),
        Qsumidero=snk.Q, oferta=m.oferta, corrientes={s[0]: list(s) for s in m.corrientes},
        cascada=casc, cascada_filas=filas, cobertura_cascada=casc / snk.Q if snk.Q else 0.0,
        pinch=tg, cobertura_pinch=tg / snk.Q if snk.Q else 0.0, Q_externo_min=qh, T_pinch=pin,
        alt2=alt2, cobertura_alt2=alt2 / snk.Q if snk.Q else 0.0, bomba_calor=hp, fuentes_bomba=fuentes_bomba,
    )
    if cal is not None and cal.resultado is not None and getattr(cal, "combustible", "gas") == "biomasa":
        # generador de calor a biomasa (pellet, chip, leña): biomasa combustible que desplaza cada alternativa
        out["combustible"] = "biomasa"
        out["calor_generador_kW"] = cal.resultado.detalle.get("Q_calor_kW")
        out["combustible_kgh"] = cal.resultado.detalle.get("combustible_kgh")
        if h:
            out["biomasa_base"] = cal.consumo(snk.Q, h); out["biomasa_cascada"] = cal.consumo(casc, h)
            out["biomasa_pinch"] = cal.consumo(tg, h); out["biomasa_alt2"] = cal.consumo(alt2, h)
            out["biomasa_remanente_cascada"] = {k: out["biomasa_base"][k] - out["biomasa_cascada"][k] for k in out["biomasa_base"]}
        return out
    if cal is not None and cal.resultado is not None:
        out["combustible"] = "gas"
        out["vapor_caldera_kW"] = cal.resultado.detalle.get("Q_vapor_kW")
        out["gas_caldera_kgh"] = cal.resultado.detalle.get("gas_kgh")
        out["eta_pcs"] = cal.eta_pcs
        if h:
            out["gas_base"] = eco.gas(snk.Q, h, cal); out["gas_cascada"] = eco.gas(casc, h, cal)
            out["gas_pinch"] = eco.gas(tg, h, cal); out["gas_alt2"] = eco.gas(alt2, h, cal)
            # gas_cascada, gas_pinch y gas_alt2 son el gas que cada alternativa DESPLAZA (el gas de ese calor, como en
            # COMBUSTIBLE!C22:G23 del Excel); la brecha remanente es lo que la caldera sigue quemando con la cascada.
            out["gas_desplazado_cascada"] = out["gas_cascada"]
            out["gas_remanente_cascada"] = {k: out["gas_base"][k] - out["gas_cascada"][k] for k in out["gas_base"]}
    return out
