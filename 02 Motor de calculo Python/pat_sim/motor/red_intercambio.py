"""Diseño de la red de intercambiadores desde el pinch (PAT 133, mejora 3, 02-11-2026).

Método de diseño del pinch de Linnhoff y Hindmarsh (1983), explicado en Kemp (2007, cap. 4). El problema se divide en el
pinch (temperatura de rec.pinch) y cada lado se diseña por separado, partiendo desde el pinch hacia afuera:
- no se transfiere calor a través del pinch: no hay servicio frío arriba ni servicio caliente abajo;
- regla de CP en el pinch: arriba, CP caliente <= CP frío en cada apareamiento que toca el pinch; abajo, CP caliente >= CP
  frío; si no se cumple con el sumidero entero, el sumidero se divide en ramas en paralelo (división de corrientes);
- tick-off: cada apareamiento se hace tan grande como se pueda, hasta agotar una de las dos corrientes.
El número de equipos se compara con el mínimo de Euler por lado del pinch (corrientes + servicios - 1).
Área de cada equipo con LMTD en contracorriente y U de partida (las mismas cifras de Capitulos 2 a 4 Agrozzi/scripts/calc_cap234.py).

Mapa (motor/recuperacion.py): corrientes calientes (nombre, T_in, T_out, CP, Q), CP None = latente a T_in, y un solo
sumidero frío con T_in, T_out y CP.
"""
from __future__ import annotations
import html as _html
import itertools
import math
from . import recuperacion as rec

# Coeficientes globales U de partida (W/m²K), valores centrales del Capítulo 4
U_LIQUIDO = 850.0        # líquido contra tomate (Amon et al., 2015, Tabla 1, p. 528)
U_CONDENSACION = 840.0   # vapor que condensa contra pulpa de tomate (Sangrame et al., 2000, p. 205)
U_GAS = 50.0             # Supuesto (el mismo de motor/optimizacion.py y motor/alternativas.py): escape húmedo o aire contra
                         # aire de secado en los rubros de biomasa, orden de magnitud de los equipos gas a gas (Incropera et al.,
                         # 2007, Tabla 11.2); se debe reemplazar por el dato del fabricante
FUENTES = ("Método: Linnhoff y Hindmarsh (1983); Kemp (2007), cap. 4 (reglas del *pinch*, regla de CP, *tick-off* y mínimo de Euler).",
           "U de partida: líquido contra tomate 850 W/m²K (Amon et al., 2015, Tabla 1, p. 528); vapor que condensa contra pulpa "
           "840 W/m²K (Sangrame et al., 2000, p. 205); gas contra aire 50 W/m²K en biomasa (Supuesto, orden de magnitud de "
           "Incropera et al., 2007, Tabla 11.2).")
TOL_Q = 1e-6     # kW
TOL_T = 2e-3     # °C; rec.pinch entrega la temperatura de pinch redondeada a tres decimales


def lmtd(a: float, b: float) -> float:
    """Diferencia media logarítmica de temperatura (contracorriente) con las diferencias de los dos extremos."""
    a = max(a, 1e-9); b = max(b, 1e-9)
    return a if abs(a - b) < 1e-9 else (a - b) / math.log(a / b)


def _snap(T, cands):
    c = min(cands, key=lambda x: abs(x - T)) if cands else T
    return c if abs(c - T) <= TOL_T else T


def _clamp(x, lo, hi):
    return max(lo, min(hi, x))


def _plan_arriba(arriba, sub, Tc0, Tout, CPc, dT, Tph):
    """Arriba del pinch: ramas paralelas (corrientes de sub) desde la temperatura fría del pinch Tc0, con CP de rama
    proporcional al mínimo que pide cada una (regla de CP), y luego las demás en serie, cada una lo más grande posible."""
    par = []; ser = []; Tc = Tc0
    if sub:
        hs = [arriba[i] for i in sub]; mins = []
        for h in hs:
            den = h["Ti"] - dT - Tc0
            if den <= 1e-9:
                return None
            mins.append(h["Qa"] / den)
        Qp = sum(h["Qa"] for h in hs)
        if sum(mins) > CPc * (1 + 1e-9) or Qp > CPc * (Tout - Tc0) + 1e-6:
            return None
        cpb = [CPc] if len(hs) == 1 else [CPc * mi / sum(mins) for mi in mins]
        for h, cb in zip(hs, cpb):
            Q = h["Qa"]; Tho = h["Ti"] if h["latente"] else h["Ti"] - Q / h["CP"]
            if Tho - Tc0 < dT - 1e-6:
                return None
            par.append((h, Q, h["Ti"], Tho, Tc0, Tc0 + Q / cb, cb))
        Tc = Tc0 + Qp / CPc
    resto = sorted((arriba[i] for i in range(len(arriba)) if i not in sub),
                   key=lambda h: (h["Ti"] if h["latente"] else max(h["To"], Tph), h["Ti"]))
    for h in resto:
        lo = h["Ti"] if h["latente"] else max(h["To"], Tph)
        if lo - Tc < dT - 1e-9 or Tout - Tc <= 1e-9:
            continue
        if h["latente"]:
            Q = min(h["Qa"], CPc * (h["Ti"] - dT - Tc), CPc * (Tout - Tc))
        else:
            Q = min(h["Qa"], CPc * (Tout - Tc))
            if h["CP"] > CPc:
                Q = min(Q, (lo - Tc - dT) / (1 / CPc - 1 / h["CP"]))
        if Q <= TOL_Q:
            continue
        Thi = h["Ti"] if h["latente"] else lo + Q / h["CP"]
        ser.append((h, Q, Thi, lo, Tc, Tc + Q / CPc, CPc)); Tc += Q / CPc
    return sum(x[1] for x in par) + sum(x[1] for x in ser), par, ser, Tc


def objetivo_pinch(m: rec.Mapa):
    """rec.pinch con un punto auxiliar de CP 0 sobre todo el mapa (PAT 133). rec.pinch empieza la cascada en la temperatura
    más alta y no suma el calor latente que está justo en ese punto; el punto auxiliar no cambia ningún otro flujo."""
    tope = max([float(s[1]) for s in m.corrientes] + [float(m.sumidero.T_out) + m.dT]) + 1.0
    aux = rec.Mapa(list(m.corrientes) + [("_aux", tope, tope - 1.0, 0.0, 0.0)], m.sumidero, m.dT, m.T_final)
    obj, qh, pins = rec.pinch(aux)
    pins = [p for p in pins if p < tope - 1e-6] or [min(tope - 1.0, max(float(s[1]) for s in m.corrientes) if m.corrientes else tope)]
    return obj, qh, pins


def disenar_red(m: rec.Mapa, biomasa: bool = False, U: dict | None = None) -> dict:
    """Red de intercambiadores de máxima recuperación (MER) para el mapa m con su ΔTmin. Devuelve un diccionario con los
    apareamientos, los servicios que quedan, el número de equipos y el mínimo de Euler, y el área de cada equipo."""
    U = dict(dict(liquido=U_LIQUIDO, condensacion=U_CONDENSACION, gas=U_GAS), **(U or {}))
    snk = m.sumidero; dT = float(m.dT); Tin = float(snk.T_in); Tout = float(snk.T_out); CPc = float(snk.CP)
    objetivo, Qh_min, pins = objetivo_pinch(m)
    o_rec = rec.pinch(m)[0]
    cands = [float(s[1]) for s in m.corrientes] + [float(s[2]) for s in m.corrientes if s[3] is not None] + [Tin + dT, Tout + dT]
    Tph = _snap(float(max(pins)), cands); Tpc = Tph - dT
    avisos = []
    if abs(o_rec - objetivo) > 1e-3:
        avisos.append(f"El objetivo *pinch* del resumen ({o_rec:.1f} kW) no cuenta el calor latente de la corriente más caliente; "
                      f"aquí se usa el objetivo corregido de {objetivo:.1f} kW.")
    if len(pins) > 1:
        avisos.append("Hay más de una temperatura de *pinch* (" + ", ".join(f"{p:.2f}" for p in pins) + " °C); se divide en la más alta.")
    H = []
    for s in m.corrientes:
        nm, Ti, To, CP, Q = s[0], float(s[1]), s[2], s[3], float(s[4])
        lat = CP is None
        h = dict(nombre=nm, Ti=Ti, To=Ti if lat else float(To), CP=None if lat else float(CP), Q=Q, latente=lat)
        if lat:
            h["Qa"] = Q if Ti > Tph + TOL_T else 0.0
            h["Qb"] = Q - h["Qa"]
        else:
            h["Qa"] = h["CP"] * max(0.0, Ti - max(h["To"], Tph))
            h["Qb"] = h["CP"] * max(0.0, min(Ti, Tph) - h["To"])
        h["usado"] = 0.0
        H.append(h)
    Tc_pinch = _clamp(Tpc, Tin, Tout)
    tipo_de = lambda h: "gas" if biomasa else ("condensacion" if h["latente"] else "liquido")
    nombres_tipo = dict(gas="gas", condensacion="condensación", liquido="líquido")
    ap = []

    def agregar(lado, h, Q, Thi, Tho, Tci, Tco, CPb, rama=None, grupo=None, toca=False):
        t = tipo_de(h); dt1 = Thi - Tco; dt2 = Tho - Tci; L = lmtd(dt1, dt2); u = U[t]
        ap.append(dict(id=f"E{len(ap) + 1}", lado=lado, corriente=h["nombre"], tipo=nombres_tipo[t], Q_kW=Q,
                       CP_caliente=h["CP"], Th_in=Thi, Th_out=Tho, Tc_in=Tci, Tc_out=Tco, CP_frio=CPb, fraccion=CPb / CPc,
                       rama=rama, grupo=grupo, toca_pinch=toca, dT_caliente=dt1, dT_fria=dt2, LMTD=L, U=u,
                       A_m2=Q * 1000.0 / (u * L)))
        h["usado"] += Q

    # ---------- arriba del pinch: ramas en paralelo desde el pinch (regla de CP) y luego serie hacia arriba ----------
    # Se prueban los subconjuntos de corrientes que van en ramas paralelas en el pinch; las demás se ponen en serie
    # después de la mezcla, de la más fría a la más caliente. Se elige el de mayor calor y, a igual calor, el de menos ramas.
    arriba = [h for h in H if h["Qa"] > TOL_Q]
    need_a = CPc * (Tout - Tc_pinch); Tmix = Tc_pinch
    if arriba and need_a > TOL_Q:
        mejor = None
        for k in range(len(arriba) + 1):
            for sub in itertools.combinations(range(len(arriba)), k):
                plan = _plan_arriba(arriba, sub, Tc_pinch, Tout, CPc, dT, Tph)
                if plan is None:
                    continue
                if mejor is None or plan[0] > mejor[0] + 1e-6 or (abs(plan[0] - mejor[0]) <= 1e-6 and len(plan[1]) < len(mejor[1])):
                    mejor = plan
        if mejor is not None:
            Qtot, par, ser, Tmix = mejor
            for j_, (h, Q, Thi, Tho, Tci, Tco, cb) in enumerate(par):
                agregar("arriba", h, Q, Thi, Tho, Tci, Tco, cb, rama=j_ if len(par) > 1 else None,
                        grupo="arriba" if len(par) > 1 else None, toca=(not h["latente"]) and Tho <= Tph + TOL_T)
            for h, Q, Thi, Tho, Tci, Tco, cb in ser:
                agregar("arriba", h, Q, Thi, Tho, Tci, Tco, cb, toca=(not h["latente"]) and Tho <= Tph + TOL_T)
    resto_arriba = sum(h["Qa"] for h in H) - sum(a["Q_kW"] for a in ap)
    if resto_arriba > 1e-3:
        avisos.append(f"Quedan {resto_arriba:.1f} kW de calor arriba del *pinch* sin usar: irían a servicio frío arriba del *pinch*.")

    # ---------- abajo del pinch: apareamiento en el pinch con la regla de CP y luego tick-off hacia el frío ----------
    top = {}
    for h in H:
        if h["Qb"] > TOL_Q:
            top[h["nombre"]] = h["Ti"] if h["latente"] else min(h["Ti"], Tph)
    rem_b = {h["nombre"]: h["Qb"] for h in H}
    Tc_top = _clamp(Tpc, Tin, Tout)
    toca_frio = Tin + TOL_T < Tpc <= Tout + TOL_T
    if toca_frio and CPc * (Tc_top - Tin) > TOL_Q:
        lat = [h for h in H if h["latente"] and h["Qb"] > TOL_Q and abs(h["Ti"] - Tph) <= TOL_T]
        sen = [h for h in H if not h["latente"] and h["Qb"] > TOL_Q and h["Ti"] >= Tph - TOL_T]
        need = CPc * (Tc_top - Tin)
        if lat:          # el calor latente en el pinch tiene CP infinito: cumple la regla de CP
            h = max(lat, key=lambda x: x["Qb"]); Q = min(h["Qb"], need)
            agregar("abajo", h, Q, h["Ti"], h["Ti"], Tc_top - Q / CPc, Tc_top, CPc, toca=True)
            rem_b[h["nombre"]] -= Q; Tc_top -= Q / CPc
        elif [h for h in sen if h["CP"] >= CPc * (1 - 1e-12)]:
            h = max(sen, key=lambda x: x["CP"]); Q = min(h["Qb"], need)
            agregar("abajo", h, Q, Tph, Tph - Q / h["CP"], Tc_top - Q / CPc, Tc_top, CPc, toca=True)
            rem_b[h["nombre"]] -= Q; top[h["nombre"]] = Tph - Q / h["CP"]; Tc_top -= Q / CPc
        elif sen and sum(h["CP"] for h in sen) >= CPc * (1 - 1e-12):
            sc = sum(h["CP"] for h in sen); cpb = [CPc * h["CP"] / sc for h in sen]   # cada rama con CP <= CP caliente
            T_div = max([Tin] + [Tc_top - h["Qb"] / cb for h, cb in zip(sen, cpb)])
            for j, (h, cb) in enumerate(zip(sen, cpb)):
                Q = cb * (Tc_top - T_div)
                if Q <= TOL_Q: continue
                agregar("abajo", h, Q, Tph, Tph - Q / h["CP"], T_div, Tc_top, cb, rama=j, grupo="abajo", toca=True)
                rem_b[h["nombre"]] -= Q; top[h["nombre"]] = Tph - Q / h["CP"]
            Tc_top = T_div
        elif sen:
            avisos.append("Abajo del *pinch* ninguna corriente cumple la regla de CP; se sigue con el tick-off.")
    while CPc * (Tc_top - Tin) > TOL_Q:
        need = CPc * (Tc_top - Tin); mejor = None
        for h in H:
            n = h["nombre"]
            if rem_b[n] <= TOL_Q or n not in top or top[n] - Tc_top < dT - 1e-9: continue
            if h["latente"]:
                Q = min(rem_b[n], need)
            else:
                Q = min(rem_b[n], need, h["CP"] * (top[n] - h["To"]))
                if h["CP"] < CPc: Q = min(Q, (top[n] - Tc_top - dT) / (1 / h["CP"] - 1 / CPc))
            if Q > TOL_Q and (mejor is None or Q > mejor[1] + 1e-9):
                mejor = (h, Q)
        if mejor is None: break
        h, Q = mejor; n = h["nombre"]
        Tho = h["Ti"] if h["latente"] else top[n] - Q / h["CP"]
        agregar("abajo", h, Q, top[n], Tho, Tc_top - Q / CPc, Tc_top, CPc)
        rem_b[n] -= Q; top[n] = Tho; Tc_top -= Q / CPc
    def_abajo = CPc * (Tc_top - Tin)
    if def_abajo > 1e-3:
        avisos.append(f"Abajo del *pinch* faltan {def_abajo:.1f} kW: un servicio caliente abajo del *pinch* rompe la regla.")

    # ---------- servicios, número de equipos y mínimo de Euler ----------
    Qrec = sum(a["Q_kW"] for a in ap)
    calentadores = []
    if Tout - Tmix > 1e-9 and CPc * (Tout - Tmix) > TOL_Q:
        calentadores.append(dict(id="SC", lado="arriba", Q_kW=CPc * (Tout - Tmix), Tc_in=Tmix, Tc_out=Tout))
    if def_abajo > TOL_Q:
        calentadores.append(dict(id="SC2", lado="abajo", Q_kW=def_abajo, Tc_in=Tin, Tc_out=Tc_top))
    enfriadores = []
    for h in H:
        r_ = h["Q"] - h["usado"]
        if r_ > 1e-3:
            Ti_e = h["Ti"] if h["latente"] else h["To"] + r_ / h["CP"]
            enfriadores.append(dict(id="SF", corriente=h["nombre"], Q_kW=r_, Th_in=Ti_e, Th_out=h["To"],
                                    lado="arriba" if h["Qa"] - sum(a["Q_kW"] for a in ap if a["corriente"] == h["nombre"] and a["lado"] == "arriba") > 1e-3 else "abajo"))
    Qa_frio = CPc * (Tout - Tc_pinch); Qb_frio = CPc * (_clamp(Tpc, Tin, Tout) - Tin)
    n_a = sum(1 for h in H if h["Qa"] > 1e-3) + (Qa_frio > 1e-3) + any(c["lado"] == "arriba" for c in calentadores) + any(e["lado"] == "arriba" for e in enfriadores)
    n_b = sum(1 for h in H if h["Qb"] > 1e-3) + (Qb_frio > 1e-3) + any(e["lado"] == "abajo" for e in enfriadores) + any(c["lado"] == "abajo" for c in calentadores)
    euler = dict(arriba=max(0, n_a - 1), abajo=max(0, n_b - 1))
    euler["total"] = euler["arriba"] + euler["abajo"]
    n_glob = sum(1 for h in H if h["Q"] > 1e-3) + 1 + (Qh_min > 1e-3) + (m.oferta - objetivo > 1e-3)
    eq = dict(recuperacion=len(ap), calentadores=len(calentadores), enfriadores=len(enfriadores),
              arriba=sum(1 for a in ap if a["lado"] == "arriba") + sum(1 for c in calentadores if c["lado"] == "arriba") + sum(1 for e in enfriadores if e["lado"] == "arriba"),
              abajo=sum(1 for a in ap if a["lado"] == "abajo") + sum(1 for c in calentadores if c["lado"] == "abajo") + sum(1 for e in enfriadores if e["lado"] == "abajo"))
    eq["total"] = eq["recuperacion"] + eq["calentadores"] + eq["enfriadores"]
    alcanza = Qrec >= objetivo - max(1e-3, 1e-6 * objetivo)
    if not alcanza:
        avisos.append(f"La red recupera {Qrec:.1f} kW, bajo el objetivo *pinch* de {objetivo:.1f} kW.")
    return dict(dT_min=dT, T_pinch_caliente=Tph, T_pinch_fria=Tpc, T_pinch=list(pins), objetivo_kW=objetivo,
                Q_externo_min=Qh_min, Q_recuperado=Qrec, alcanza_objetivo=alcanza, brecha_kW=objetivo - Qrec,
                sumidero=dict(nombre=snk.nombre, equipo=snk.equipo, T_in=Tin, T_out=Tout, CP=CPc, Q=snk.Q),
                corrientes=[dict(nombre=h["nombre"], Ti=h["Ti"], To=h["To"], CP=h["CP"], Q=h["Q"], latente=h["latente"],
                                 Q_arriba=h["Qa"], Q_abajo=h["Qb"]) for h in H],
                apareamientos=ap, calentadores=calentadores, enfriadores=enfriadores, T_mezcla_arriba=Tmix,
                servicio_caliente_kW=sum(c["Q_kW"] for c in calentadores), servicio_frio_kW=sum(e["Q_kW"] for e in enfriadores),
                equipos=eq, euler=euler, euler_sin_dividir=max(0, n_glob - 1), area_total_m2=sum(a["A_m2"] for a in ap),
                biomasa=biomasa, avisos=avisos, fuentes=list(FUENTES))


def disenar_red_planta(pl, r: dict | None = None) -> dict | None:
    """Red de la planta con el sumidero y las globales del resumen (motor/resumen.py). None si no hay sumidero."""
    from .resumen import resumen_planta
    r = r or resumen_planta(pl)
    if r.get("sin_sumidero"):
        return None
    s = r["sumidero"]
    snk = next((x for x in pl.sumideros() if x.equipo == s["equipo"] and x.nombre == s["nombre"]), None) or \
        next(x for x in pl.sumideros() if x.equipo == s["equipo"])
    m = rec.mapa(pl.residuales(), snk, r["dT_min"], r["T_final"])
    return disenar_red(m, biomasa=r.get("combustible") == "biomasa")


# ---------------------------------------------------------------- diagrama de rejilla (grid diagram)
_C = dict(cal="#9c3d2e", fri="#2f5f8a", pinch="#7a7a7a", txt="#333333", borde="#333333", sc="#f1dcd5", sf="#dce6ef", fondo="#ffffff")


def _f(v, d=1):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def diagrama_rejilla_svg(red: dict) -> str:
    """Diagrama de rejilla: corrientes calientes arriba (de izquierda a derecha), sumidero abajo (de derecha a izquierda),
    línea vertical del pinch y un par de círculos unidos por cada intercambiador, con su calor en kW."""
    e = _html.escape
    H = red["corrientes"]; ap = red["apareamientos"]; s = red["sumidero"]
    arr = [a for a in ap if a["lado"] == "arriba"]; aba = [a for a in ap if a["lado"] == "abajo"]
    sc_a = [c for c in red["calentadores"] if c["lado"] == "arriba"]; sc_b = [c for c in red["calentadores"] if c["lado"] == "abajo"]
    largo = max([len(f"{h['nombre']} · {_f(h['Ti'], 1)} °C") for h in H] + [len(f"{s['nombre']} ({s['equipo']}) · {_f(s['T_out'], 1)} °C")])
    W = 78; X0 = 40 + 6.3 * largo; fila = 42; Y0 = 60
    cols = []                                    # (tipo, objeto) de izquierda a derecha
    cols += [("sc", c) for c in sc_a]
    cols += [("ap", a) for a in reversed(arr)]
    n_izq = len(cols)
    cols += [("ap", a) for a in aba]
    cols += [("sc", c) for c in sc_b]
    if red["enfriadores"]:
        cols.append(("sf", None))
    xs = [X0 + W * (i + 0.5) + (W * 0.6 if i >= n_izq else 0) for i in range(len(cols))]
    x_pinch = X0 + W * n_izq + W * 0.3
    x_ini = X0 - 20; x_fin = X0 + W * len(cols) + W * 0.6 + 20
    yh = {h["nombre"]: Y0 + i * fila for i, h in enumerate(H)}
    yc = Y0 + len(H) * fila + 18
    n_ramas = max([a["rama"] + 1 for a in ap if a["rama"] is not None] + [1])
    alto = yc + (n_ramas - 1) * 24 + 84
    ancho = max(x_fin + 70, 720)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho:.0f}" height="{alto:.0f}" viewBox="0 0 {ancho:.0f} {alto:.0f}" '
         f'font-family="Segoe UI, Arial, sans-serif" font-size="11" style="background:{_C["fondo"]}">',
         '<defs>'
         f'<marker id="fc" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{_C["cal"]}"/></marker>'
         f'<marker id="ff" markerWidth="8" markerHeight="8" refX="7" refY="4" orient="auto"><path d="M0,0 L8,4 L0,8 z" fill="{_C["fri"]}"/></marker>'
         '</defs>']
    # línea del pinch
    o.append(f'<line x1="{x_pinch:.1f}" y1="22" x2="{x_pinch:.1f}" y2="{alto - 40:.1f}" stroke="{_C["pinch"]}" stroke-width="1.5" stroke-dasharray="6,4"/>')
    o.append(f'<text x="{x_pinch - 3:.1f}" y="16" text-anchor="end" font-style="italic" fill="{_C["txt"]}">Pinch</text>')
    o.append(f'<text x="{x_pinch + 3:.1f}" y="16" text-anchor="start" fill="{_C["txt"]}">'
             f'{_f(red["T_pinch_caliente"], 2)} / {_f(red["T_pinch_fria"], 2)} °C</text>')
    gr = f'fill="{_C["pinch"]}" font-size="10"'
    o.append(f'<text x="{x_pinch - 8:.1f}" y="34" text-anchor="end" font-style="italic" {gr}>pinch</text>')
    o.append(f'<text x="{x_pinch - 36:.1f}" y="34" text-anchor="end" {gr}>arriba del</text>')
    o.append(f'<text x="{x_pinch + 8:.1f}" y="34" text-anchor="start" {gr}>abajo del</text>')
    o.append(f'<text x="{x_pinch + 56:.1f}" y="34" text-anchor="start" font-style="italic" {gr}>pinch</text>')
    # corrientes calientes
    for h in H:
        y = yh[h["nombre"]]
        xa = x_ini if h["Q_arriba"] > 1e-3 else x_pinch + 4
        xb = x_fin if h["Q_abajo"] > 1e-3 else x_pinch - 4
        o.append(f'<line x1="{xa:.1f}" y1="{y}" x2="{xb:.1f}" y2="{y}" stroke="{_C["cal"]}" stroke-width="2.2" marker-end="url(#fc)"/>')
        tipo = "latente" if h["latente"] else "CP " + _f(h["CP"], 1)
        if xa > x_ini:     # corriente que nace en el pinch: guía punteada desde la etiqueta
            o.append(f'<line x1="{x_ini:.1f}" y1="{y}" x2="{xa:.1f}" y2="{y}" stroke="#c9c9c9" stroke-width="1" stroke-dasharray="2,4"/>')
        o.append(f'<text x="{x_ini - 6:.1f}" y="{y - 3}" text-anchor="end" fill="{_C["txt"]}">{e(h["nombre"])} · {_f(h["Ti"], 1)} °C</text>')
        o.append(f'<text x="{x_ini - 6:.1f}" y="{y + 10}" text-anchor="end" fill="{_C["pinch"]}" font-size="9.5">{tipo} · {_f(h["Q"], 0)} kW</text>')
        o.append(f'<text x="{xb + 10:.1f}" y="{y + 4}" fill="{_C["txt"]}">{_f(h["To"], 1)} °C</text>')
    # sumidero y ramas
    xa_c = x_ini if s["T_out"] > red["T_pinch_fria"] + 1e-6 else x_pinch - 4
    xb_c = x_fin if red["T_pinch_fria"] > s["T_in"] + 1e-6 else x_pinch + 4
    o.append(f'<line x1="{xb_c:.1f}" y1="{yc}" x2="{xa_c:.1f}" y2="{yc}" stroke="{_C["fri"]}" stroke-width="2.4" marker-end="url(#ff)"/>')
    o.append(f'<text x="{x_ini - 6:.1f}" y="{yc - 3}" text-anchor="end" fill="{_C["txt"]}">{e(s["nombre"])} ({e(s["equipo"])}) · {_f(s["T_out"], 1)} °C</text>')
    o.append(f'<text x="{x_ini - 6:.1f}" y="{yc + 10}" text-anchor="end" fill="{_C["pinch"]}" font-size="9.5">CP {_f(s["CP"], 1)} · {_f(s["Q"], 0)} kW</text>')
    o.append(f'<text x="{xb_c + 6:.1f}" y="{yc + 4}" fill="{_C["txt"]}">{_f(s["T_in"], 1)} °C</text>')
    for g in ("arriba", "abajo"):
        idx = [i for i, (t, a) in enumerate(cols) if t == "ap" and a["grupo"] == g]
        if not idx: continue
        x1 = xs[min(idx)] - W * 0.42; x2 = xs[max(idx)] + W * 0.42
        for j in range(1, n_ramas):
            if not any(cols[i][1]["rama"] == j for i in idx): continue
            yr = yc + 24 * j
            o.append(f'<path d="M{x2:.1f},{yc} L{x2:.1f},{yr} L{x1:.1f},{yr} L{x1:.1f},{yc}" fill="none" stroke="{_C["fri"]}" stroke-width="1.6"/>')
    def circulo(x, y, txt, fill):
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="11" fill="{fill}" stroke="{_C["borde"]}" stroke-width="1.3"/>')
        o.append(f'<text x="{x:.1f}" y="{y + 3.5:.1f}" text-anchor="middle" font-size="9" fill="{_C["txt"]}">{e(txt)}</text>')
    for (t, a), x in zip(cols, xs):
        if t == "ap":
            y1 = yh[a["corriente"]]; y2 = yc + 24 * (a["rama"] or 0)
            o.append(f'<line x1="{x:.1f}" y1="{y1}" x2="{x:.1f}" y2="{y2}" stroke="{_C["borde"]}" stroke-width="1.2"/>')
            circulo(x, y1, a["id"], "#ffffff"); circulo(x, y2, a["id"], "#ffffff")
            o.append(f'<text x="{x:.1f}" y="{y1 - 15}" text-anchor="middle" fill="{_C["txt"]}" font-size="10">{_f(a["Q_kW"], 0)} kW</text>')
        elif t == "sc":
            circulo(x, yc, "SC", _C["sc"])
            o.append(f'<text x="{x:.1f}" y="{yc - 16}" text-anchor="middle" fill="{_C["txt"]}" font-size="10">{_f(a["Q_kW"], 0)} kW</text>')
        else:
            for en in red["enfriadores"]:
                y = yh[en["corriente"]]
                circulo(x, y, "SF", _C["sf"])
                o.append(f'<text x="{x:.1f}" y="{y - 15}" text-anchor="middle" fill="{_C["txt"]}" font-size="10">{_f(en["Q_kW"], 0)} kW</text>')
    o.append(f'<text x="12" y="{alto - 26:.1f}" fill="{_C["pinch"]}" font-size="10">E: intercambiador de recuperación (kW sobre el círculo) · '
             'SC: servicio caliente (caldera o generador) · SF: servicio frío (descarga del residual)</text>')
    o.append(f'<text x="12" y="{alto - 12:.1f}" fill="{_C["pinch"]}" font-size="10">ΔTmin {_f(red["dT_min"], 1)} °C · '
             'las ramas bajo el sumidero son divisiones en paralelo · posiciones no a escala de temperatura</text>')
    o.append("</svg>")
    return "".join(o)
