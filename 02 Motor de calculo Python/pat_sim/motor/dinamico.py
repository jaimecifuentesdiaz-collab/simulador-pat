"""Modo dinámico simplificado (PAT 133, mejora 20): integración explícita (Euler hacia adelante) con paso de tiempo declarado.

1) Arranque y parada del calentamiento que es el sumidero del mapa: el hot break en el tomate y el aire de secado en la
   biomasa. Se modela como un sistema de primer orden con la masa térmica del equipo (Supuesto declarado):
       C·dT/dt = Q(t) − K·(T − T0)
   con K = CP del sumidero (kW/K), T0 = temperatura de entrada del sumidero y C = masa de acero × calor específico del acero
   más la retención de producto (CP × tiempo de residencia). En el estado estacionario Q = K·(Tsp − T0), que es justo el
   calor del sumidero que calcula el motor. El calor lo regula un control con prealimentación y acción proporcional,
   Q = Q_est + g·K·(Tsp − T), limitado entre 0 y f·Q_est (capacidad de la válvula de vapor o del hogar). En la parada se
   corta el calor y la alimentación sigue pasando, de modo que el equipo se enfría con su constante de tiempo.
   El calor recuperable sigue a las fuentes del mapa: en el tomate los evaporadores entran en régimen después del hot break
   (retardo de primer orden τ_f, Supuesto); en la biomasa el escape sigue al propio secador (τ_f = 0). Su valor
   estacionario es la cascada en serie del motor, y solo se usa la parte que el calentamiento pide en cada instante.
2) Secado por cargas de la biomasa: periodo de velocidad constante y periodo de velocidad decreciente lineal entre la
   humedad crítica y la de equilibrio (Mujumdar, 2014), integrado con el mismo método y contrastado con la solución exacta.

Unidades: tiempo en minutos en las series, energía en kWh, potencia en kW, humedad en base seca (kg agua/kg seca)."""
from __future__ import annotations
import math
from .propiedades import latente

# PAT 133: calor específico del acero (Incropera et al., 2007, Tabla A.1, a 300 K)
CP_ACERO_INOX = 0.477      # kJ/kg·K, acero inoxidable AISI 304
CP_ACERO_CARBONO = 0.434   # kJ/kg·K, acero al carbono simple
FUENTE_ACERO = "Incropera et al. (2007, Tabla A.1, 300 K): AISI 304, 477 J/kg·K; acero al carbono simple, 434 J/kg·K"

# Supuestos declarados de cada rubro (no hay placa de los equipos ni visita a la planta)
SUPUESTOS = {
    "tomate": dict(
        masa_acero_t=12.0, cp_acero=CP_ACERO_INOX, residencia_min=3.0, tau_fuentes_min=15.0, ganancia=4.0, sobrecapacidad=1.25,
        justificacion=dict(
            masa_acero_t="Supuesto: orden de magnitud de un calentador tubular con su estanque de recirculación para unas 220 t/h; sin placa del equipo",
            cp_acero=FUENTE_ACERO + " (equipo de acero inoxidable)",
            residencia_min="Supuesto: retención de producto de unos minutos en los tubos y el estanque del hot break",
            tau_fuentes_min="Supuesto: los evaporadores reciben el producto después del hot break y tardan en entregar sus condensados",
            ganancia="Supuesto: ganancia proporcional del control de temperatura (TIC-101) sobre la prealimentación",
            sobrecapacidad="Supuesto: la válvula de vapor entrega hasta 25 % más que el consumo estacionario")),
    "biomasa": dict(
        masa_acero_t=25.0, cp_acero=CP_ACERO_CARBONO, residencia_min=0.0, tau_fuentes_min=0.0, ganancia=4.0, sobrecapacidad=1.25,
        justificacion=dict(
            masa_acero_t="Supuesto: tambor o cámara de secado y ductos del generador de aire caliente; sin placa del equipo",
            cp_acero=FUENTE_ACERO + " (equipo de acero al carbono)",
            residencia_min="El medio que se calienta es aire: su retención es despreciable frente a la del acero",
            tau_fuentes_min="El escape sale del propio secador: sigue su temperatura sin retardo",
            ganancia="Supuesto: ganancia proporcional del control de temperatura del aire (TIC-101) sobre la prealimentación",
            sobrecapacidad="Supuesto: el hogar entrega hasta 25 % más que la demanda estacionaria")),
}


def supuestos(pl) -> dict:
    return dict(SUPUESTOS["tomate" if pl.rubro == "tomate" else "biomasa"])


def _sumidero(pl, r: dict | None):
    if r is None:
        from .resumen import resumen_planta
        r = resumen_planta(pl)
    if r.get("sin_sumidero"):
        raise ValueError("La planta no tiene un sumidero de calor: no hay calentamiento que simular")
    return r, r["sumidero"]


def primer_orden(C_kJ_K: float, K_kW_K: float, T0: float, Tsp: float, dt_s: float, t_parada_s: float, t_fin_s: float,
                 ganancia: float = 4.0, sobrecapacidad: float = 1.25, Q_recuperable: float = 0.0, tau_fuentes_s: float = 0.0) -> dict:
    """Integra C·dT/dt = Q − K·(T − T0) con Euler explícito. Devuelve las series (t en s) y las integrales con la misma regla
    del rectángulo por la izquierda que usa el método, de modo que el balance de energía integrado cierra."""
    if C_kJ_K <= 0 or K_kW_K <= 0:
        raise ValueError("La masa térmica y el CP del sumidero deben ser positivos")
    if dt_s <= 0:
        raise ValueError("El paso de tiempo debe ser positivo")
    lam = K_kW_K * (1 + max(ganancia, 0.0)) / C_kJ_K
    if dt_s * lam >= 1.0:
        raise ValueError("Paso de tiempo demasiado grande para el método explícito: use menos de " + f"{1 / lam:.1f}".replace(".", ",") + " s")
    if tau_fuentes_s > 0 and dt_s >= tau_fuentes_s:
        raise ValueError("El paso de tiempo debe ser menor que el retardo de las fuentes")
    Qest = K_kW_K * (Tsp - T0); Qmax = sobrecapacidad * Qest
    n = int(math.ceil(t_fin_s / dt_s))
    T = T0; yf = 0.0
    S = dict(t=[], T=[], y=[], Q=[], Q_util=[], Q_rec_disp=[], Q_rec=[], Q_ext=[])
    E = dict(Q=0.0, util=0.0, rec=0.0, ext=0.0)
    for k in range(n + 1):
        t = k * dt_s
        Q = 0.0 if t >= t_parada_s else min(max(Qest + ganancia * K_kW_K * (Tsp - T), 0.0), Qmax)
        Qu = K_kW_K * (T - T0)
        y = (T - T0) / (Tsp - T0) if Tsp != T0 else 1.0
        disp = Q_recuperable * max(yf, 0.0); rec = min(disp, Q)
        for c, v in (("t", t), ("T", T), ("y", y), ("Q", Q), ("Q_util", Qu), ("Q_rec_disp", disp), ("Q_rec", rec), ("Q_ext", Q - rec)):
            S[c].append(v)
        if k == n:
            break
        E["Q"] += Q * dt_s; E["util"] += Qu * dt_s; E["rec"] += rec * dt_s; E["ext"] += (Q - rec) * dt_s
        T = T + dt_s * (Q - Qu) / C_kJ_K
        yf = y if tau_fuentes_s <= 0 else yf + dt_s * (y - yf) / tau_fuentes_s
    return dict(series=S, integrales_kJ=E, Q_estacionario=Qest, Q_max=Qmax, tau_s=C_kJ_K / K_kW_K, lam=lam)


def arranque_parada(pl, r: dict | None = None, dt_s: float | None = None, t_parada_min: float | None = None, t_fin_min: float | None = None,
                    **cambios) -> dict:
    """Arranque en frío (el equipo parte a la temperatura de entrada del sumidero), operación hasta el estacionario y parada.
    cambios: masa_acero_t, cp_acero, residencia_min, tau_fuentes_min, ganancia, sobrecapacidad (los supuestos del rubro)."""
    r, s = _sumidero(pl, r)
    sp = supuestos(pl); just = sp.pop("justificacion")
    for k, v in cambios.items():
        if k not in sp:
            raise KeyError(f"Supuesto desconocido: {k}")
        sp[k] = float(v)
    K = float(s["CP"]); T0 = float(s["T_in"]); Tsp = float(s["T_out"])
    C = sp["masa_acero_t"] * 1000 * sp["cp_acero"] + K * sp["residencia_min"] * 60
    tau = C / K
    dt = float(dt_s) if dt_s else tau / (1 + sp["ganancia"]) / 100           # paso declarado: 1 % de la constante de lazo cerrado
    tp = float(t_parada_min) * 60 if t_parada_min is not None else max(12 * tau, 8 * sp["tau_fuentes_min"] * 60)
    tf = float(t_fin_min) * 60 if t_fin_min is not None else tp + 8 * tau
    if tp > tf:
        raise ValueError("La parada debe ocurrir antes del final de la simulación")
    Qcasc = float(r.get("cascada") or 0.0)
    o = primer_orden(C, K, T0, Tsp, dt, tp, tf, sp["ganancia"], sp["sobrecapacidad"], Qcasc, sp["tau_fuentes_min"] * 60)
    S = o["series"]; Ei = o["integrales_kJ"]
    # tiempo para llegar al 95 % del cambio de temperatura
    i95 = next((i for i, y in enumerate(S["y"]) if y >= 0.95 and S["t"][i] < tp), None)
    t95 = S["t"][i95] if i95 is not None else None
    a95 = sum(S["Q"][i] for i in range(i95)) * dt if i95 else 0.0
    rec95 = sum(S["Q_rec"][i] for i in range(i95)) * dt if i95 else 0.0
    alm95 = C * (S["T"][i95] - T0) if i95 is not None else 0.0
    ip = min(int(round(tp / dt)), len(S["t"]) - 1)
    alm_parada = C * (S["T"][ip] - S["T"][-1])
    cierre = Ei["Q"] - Ei["util"] - C * (S["T"][-1] - S["T"][0])
    eq = pl.equipos.get(s["equipo"])
    return dict(
        equipo=s["equipo"], nombre=s["nombre"], nombre_equipo=eq.nombre if eq else s["equipo"], rubro=pl.rubro,
        dt_s=dt, t_parada_min=tp / 60, t_fin_min=tf / 60, C_kJ_K=C, K_kW_K=K, T0=T0, Tsp=Tsp, tau_min=tau / 60,
        tau_lazo_min=tau / (1 + sp["ganancia"]) / 60, supuestos=sp, justificacion=just,
        Q_estacionario=o["Q_estacionario"], Q_max=o["Q_max"], cascada=Qcasc,
        t95_min=None if t95 is None else t95 / 60,
        energia_arranque_kWh=a95 / 3600, energia_masa_kWh=alm95 / 3600, energia_producto_fuera_kWh=(a95 - alm95) / 3600,
        recuperado_arranque_kWh=rec95 / 3600, energia_parada_kWh=alm_parada / 3600,
        estado_final=dict(T=S["T"][ip], Q=S["Q"][ip - 1] if ip else S["Q"][0], Q_rec=S["Q_rec"][ip - 1] if ip else 0.0),
        balance=dict(calor_kWh=Ei["Q"] / 3600, producto_kWh=Ei["util"] / 3600, acumulado_kWh=C * (S["T"][-1] - S["T"][0]) / 3600,
                     cierre_kWh=cierre / 3600, recuperado_kWh=Ei["rec"] / 3600, externo_kWh=Ei["ext"] / 3600),
        series=dict(t_min=[t / 60 for t in S["t"]], T=S["T"], fraccion=S["y"], Q=S["Q"], Q_rec_disp=S["Q_rec_disp"], Q_rec=S["Q_rec"], Q_ext=S["Q_ext"]),
    )


# ------------------------------------------------------------------------------------------------ secado por cargas
def bs(M_bh: float) -> float:
    return M_bh / (1 - M_bh)


def bh(X_bs: float) -> float:
    return X_bs / (1 + X_bs)


def secado_cargas(X0: float, Xf: float, Xc: float, Xe: float, Nc: float, dt_h: float, masa_seca_kg: float = 1000.0,
                  T_bulbo: float = 50.0, t_max_h: float | None = None) -> dict:
    """Secado de una carga (Mujumdar, 2014): dX/dt = −Nc si X > Xc; dX/dt = −Nc·(X − Xe)/(Xc − Xe) si X ≤ Xc.
    X en base seca, Nc en kg de agua por kg seco y por hora. Integra con Euler explícito y entrega la solución exacta."""
    if not (Xe < Xf < X0):
        raise ValueError("Debe cumplirse humedad de equilibrio < humedad final < humedad inicial (base seca)")
    if Nc <= 0 or dt_h <= 0:
        raise ValueError("La velocidad de secado y el paso de tiempo deben ser positivos")
    if Xc <= Xe:
        raise ValueError("La humedad crítica debe ser mayor que la de equilibrio")
    if Xc < X0 and dt_h * Nc / (Xc - Xe) >= 1.0:
        raise ValueError("Paso de tiempo demasiado grande para el periodo decreciente")
    def vel(X):
        return Nc if X > Xc else Nc * (X - Xe) / (Xc - Xe)
    t1 = max(X0 - max(Xc, Xf), 0.0) / Nc
    t2 = (Xc - Xe) / Nc * math.log((min(Xc, X0) - Xe) / (Xf - Xe)) if Xf < Xc else 0.0
    t_max = t_max_h or 1.5 * (t1 + t2) + 10 * dt_h
    lam = latente(T_bulbo)                           # kJ/kg, a la temperatura de bulbo húmedo del periodo constante (IAPWS-IF97)
    S = dict(t_h=[], X=[], M_bh=[], velocidad=[], calor_kW=[]); X = X0; t = 0.0; agua = 0.0; t_fin = None
    while True:
        v = vel(X) if X > Xf else 0.0
        S["t_h"].append(t); S["X"].append(X); S["M_bh"].append(bh(X)); S["velocidad"].append(v)
        S["calor_kW"].append(v * masa_seca_kg * lam / 3600)
        if X <= Xf + 1e-12:
            t_fin = t; break
        if t >= t_max:
            break
        dX = min(v * dt_h, X - Xf) if X - v * dt_h < Xf else v * dt_h
        X -= dX; agua += dX * masa_seca_kg; t += dt_h
    return dict(series=S, t_constante_h=t1, t_decreciente_h=t2, t_exacto_h=t1 + t2, t_euler_h=t_fin,
                agua_kg=agua, energia_kWh=agua * lam / 3600, lam_kJ_kg=lam, X0=X0, Xf=Xf, Xc=Xc, Xe=Xe, Nc=Nc, dt_h=dt_h,
                masa_seca_kg=masa_seca_kg)


SUPUESTOS_CARGAS = dict(
    Xc=0.30, Xe=0.03, horas_carga=1.0,
    justificacion=dict(
        Xc="Supuesto: humedad crítica igual al punto de saturación de las fibras de la madera, cercano a 30 % en base seca (Glass y Zelinka, 2010, cap. 4)",
        Xe="Supuesto: humedad de equilibrio de la madera con aire caliente y seco; sin isoterma medida del material",
        horas_carga="Supuesto: una carga es la materia seca de una hora de alimentación de la planta",
        Nc="Derivado: toda la potencia útil del secador continuo del motor evapora agua en el periodo de velocidad constante"))


def secado_cargas_planta(pl, dt_h: float | None = None, **cambios) -> dict:
    """Secado por cargas con los datos del secador de la planta de biomasa resuelta (humedades, materia seca y calor útil)."""
    seca = [e for e in pl.equipos.values() if e.tipo.startswith("secador") and e.resultado is not None]
    if not seca:
        raise ValueError("La planta no tiene un secador de biomasa resuelto")
    e = seca[0]; d = e.resultado.detalle
    sp = dict(SUPUESTOS_CARGAS); just = sp.pop("justificacion")
    for k, v in cambios.items():
        if k not in sp:
            raise KeyError(f"Supuesto desconocido: {k}")
        sp[k] = float(v)
    carga_kgh = float(d["carga_t_h"]) * 1000
    X0 = bs(float(d["humedad_entrada"])); Xf = bs(float(d["humedad_salida"]))
    ms = carga_kgh * (1 - float(d["humedad_entrada"])) * sp["horas_carga"]
    Tb = float(e.v("T_producto"))
    Nc = float(d["Q_util_kW"]) * 3600 / latente(Tb) / ms
    dt = float(dt_h) if dt_h else min(0.005, 0.01 * (sp["Xc"] - sp["Xe"]) / Nc)
    o = secado_cargas(X0, Xf, sp["Xc"], sp["Xe"], Nc, dt, ms, Tb)
    o.update(equipo=e.id, nombre_equipo=e.nombre, supuestos=sp, justificacion=just,
             t_continuo_h=sp["horas_carga"], agua_continuo_kg=float(d["agua_evaporada_kgh"]) * sp["horas_carga"])
    return o
