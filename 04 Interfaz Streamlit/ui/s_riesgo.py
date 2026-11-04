"""Sección Riesgo de la pestaña Economía (mejora 5, PAT 133): tornado y Monte Carlo del VAN de la cascada.
Funciona en el tomate (gas natural) y en pellet, chip y leña (biomasa)."""
from __future__ import annotations
import html as _html
import pandas as pd
import streamlit as st
from pat_sim.motor import riesgo as R
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

UNIDADES = dict(precio=None, dolar="$/US$", inversion="MM$", tasa="%", fraccion="")
DEC = dict(precio=2, dolar=2, inversion=1, tasa=1, fraccion=2)


def mm(v) -> str:
    """Millones de pesos con el signo antes del $: −$95,1 MM."""
    return C.esc(("−" if v < 0 else "") + "$" + C.fmt(abs(v), 1) + " MM")


def _valor(clave, v, comb):
    if clave == "tasa":
        return C.pct(v, 1)
    if clave == "precio":
        return C.fmt(v, 2 if comb == "gas" else 0) + (" US$/MMBtu" if comb == "gas" else " $/m³ estéreo")
    u = UNIDADES.get(clave) or ""
    return C.fmt(v, DEC.get(clave, 2)) + (" " + u if u else "")


def tornado_svg(filas: list, ancho: int = 760) -> str:
    """Gráfico de tornado en SVG: una barra horizontal por supuesto, del VAN con el valor bajo al VAN con el valor alto."""
    if not filas:
        return ""
    alto_f = 30; mi = 230; md = 30; arriba = 30; alto = arriba + alto_f * len(filas) + 34
    v0 = filas[0]["van_base"]
    lo = min(min(f["van_min"] for f in filas), v0); hi = max(max(f["van_max"] for f in filas), v0)
    if hi - lo < 1e-9:
        hi = lo + 1.0
    pad = 0.05 * (hi - lo); lo -= pad; hi += pad
    x = lambda v: mi + (v - lo) / (hi - lo) * (ancho - mi - md)
    h = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho}" height="{alto}" viewBox="0 0 {ancho} {alto}" font-family="sans-serif" font-size="12">',
         f'<rect width="{ancho}" height="{alto}" fill="#ffffff"/>']
    for i, f in enumerate(filas):
        y = arriba + i * alto_f
        h.append(f'<text x="{mi - 8}" y="{y + 19}" text-anchor="end" fill="#222">{_html.escape(f["nombre"])}</text>')
        # tramo bajo el VAN base en rojo y sobre él en verde
        a, b = x(f["van_min"]), x(f["van_max"]); xb = x(v0)
        if a < xb:
            h.append(f'<rect x="{a:.1f}" y="{y + 6}" width="{max(xb - a, 0.5):.1f}" height="{alto_f - 12}" fill="#c0504d"/>')
        if b > xb:
            h.append(f'<rect x="{xb:.1f}" y="{y + 6}" width="{max(b - xb, 0.5):.1f}" height="{alto_f - 12}" fill="#1b7a5a"/>')
    xb = x(v0); yb = arriba + alto_f * len(filas)
    h.append(f'<line x1="{xb:.1f}" y1="{arriba - 6}" x2="{xb:.1f}" y2="{yb + 4}" stroke="#333" stroke-width="1.5"/>')
    h.append(f'<text x="{xb:.1f}" y="{arriba - 12}" text-anchor="middle" fill="#333">VAN base {C.fmt(v0, 0)} MM$</text>')
    h.append(f'<line x1="{mi}" y1="{yb + 4}" x2="{ancho - md}" y2="{yb + 4}" stroke="#999"/>')
    for k in range(5):
        v = lo + (hi - lo) * k / 4; xx = x(v)
        h.append(f'<line x1="{xx:.1f}" y1="{yb + 4}" x2="{xx:.1f}" y2="{yb + 9}" stroke="#999"/>')
        h.append(f'<text x="{xx:.1f}" y="{yb + 22}" text-anchor="middle" fill="#555">{C.fmt(v, 0)}</text>')
    h.append(f'<text x="{(mi + ancho - md) / 2:.1f}" y="{alto - 2}" text-anchor="middle" fill="#555">VAN (MM$)</text>')
    h.append("</svg>")
    return "".join(h)


def mostrar(pl, r, E, titulo=None):
    """pl: planta; r: resumen de la planta (C.resumen_actual()); E: st.session_state.economia."""
    ss = st.session_state
    st.markdown("#### " + (titulo or "Riesgo del VAN de la cascada"))
    s = R.supuestos(r, E)
    if s is None:
        st.info("La planta no tiene una caldera o un generador de calor con horas de operación: no hay VAN que evaluar.")
        return
    comb = s["combustible"]
    for a in s["avisos"]:
        st.info(C.esc(a))
    filas = R.tornado(s["base"], s["rangos"], s["fn"])
    if comb == "gas":
        fuente_precio = (f"precio del gas de {C.fmt(R.GAS_MIN, 2)} US$/MMBtu, Henry Hub de agosto de 2026 ({C.FUENTE_HH}), a "
                         f"{C.fmt(R.GAS_MAX, 0)} US$/MMBtu (Supuesto, techo del rango de sensibilidad del Capítulo 4); dólar ±10 % (Supuesto)")
    else:
        fuente_precio = (f"precio de la biomasa de {C.fmt(R.BIOMASA_MIN, 0)} a {C.fmt(R.BIOMASA_MAX, 0)} $/m³ estéreo ({C.FUENTE_BIOMASA}); "
                         "sin dólar, porque el precio ya está en pesos")
    C.ayuda(C.esc("Cada supuesto se lleva a su mínimo y a su máximo con los demás en el valor de la sesión.\n\n"   # PAT 134: ayuda «?»
                  "Rangos: " + fuente_precio + "; tasa de 6 a 14 % y inversión ±30 % (Capítulo 4, sección 4.7.7); fracción de recuperación, "
                  "calor efectivamente recuperado sobre el de diseño, de 0,8 a 1,0 (Supuesto: ensuciamiento, paradas y control). "
                  "Si el valor de la sesión cae fuera de un rango, el rango se ensancha hasta contenerlo. Costo anual y horizonte fijos."),
            "Tornado", 5)
    st.image(tornado_svg(filas), width="stretch")
    tab = [dict(n=f["nombre"], bajo=_valor(f["clave"], f["valor_bajo"], comb), alto=_valor(f["clave"], f["valor_alto"], comb),
                vb=f["van_bajo"], va=f["van_alto"], amp=f["amplitud"]) for f in filas]
    AT.tabla("rg_tornado", "Valores del tornado")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(tab, [("n", "Supuesto", "txt", 0), ("bajo", "Valor bajo", "cen", 0), ("alto", "Valor alto", "cen", 0),
                          ("vb", "VAN con el bajo (MM$)", "mm", 1), ("va", "VAN con el alto (MM$)", "mm", 1), ("amp", "Amplitud (MM$)", "mm", 1)])

    C.ayuda("Cada supuesto se muestrea de una distribución triangular con mínimo y máximo del tornado y moda en el valor de la sesión.",   # PAT 134
            "Monte Carlo", 5)
    a, b = st.columns(2)
    n = int(a.number_input("Número de simulaciones", 100, 20000, 2000, 100, key="rg_n"))
    semilla = int(b.number_input("Semilla", 0, 10**9, 133, 1, key="rg_semilla", help="Con la misma semilla se repiten exactamente los resultados."))
    llave = (pl.rubro, comb, round(s["desplazado"], 6), tuple(sorted(s["base"].items())), n, semilla)
    if st.button("Simular", type="primary", key="rg_simular"):
        with st.spinner("Simulando…"):
            ss["rg_resultado"] = (llave, R.monte_carlo(s["base"], s["distribuciones"], s["fn"], n=n, semilla=semilla))
    guardado = ss.get("rg_resultado")
    if not guardado or guardado[0] != llave:
        st.caption("Presione Simular para correr el Monte Carlo con los supuestos actuales.")
        return
    mc = guardado[1]
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("VAN medio", mm(mc["media"]))
    m2.metric("Desviación estándar", mm(mc["desviacion"]))
    m3.metric("Percentiles 5 y 95", C.esc(C.fmt(mc["p5"], 0) + " a " + C.fmt(mc["p95"], 0) + " MM$"))
    m4.metric("Probabilidad de VAN positivo", C.pct(mc["prob_positivo"]))
    clases = R.histograma(mc["valores"], 30)
    df = pd.DataFrame({"Simulaciones": [c for _a, _b, c in clases]}, index=[round((a_ + b_) / 2, 1) for a_, b_, _c in clases])
    st.bar_chart(df, x_label="VAN (MM$, marca de clase)", y_label="Simulaciones")
    AT.tabla("rg_percentiles", "Percentiles del VAN")   # PAT 134: «?» de la tabla
    C.mostrar_tabla([dict(n="Percentil 5", v=mc["p5"]), dict(n="Mediana (percentil 50)", v=mc["p50"]), dict(n="Percentil 95", v=mc["p95"])],
                    [("n", "Estadístico", "txt", 0), ("v", "VAN (MM$)", "mm", 1)])
    st.caption(f"{C.fmt(mc['n'], 0)} simulaciones con la semilla {mc['semilla']}.")
    C.ayuda("random.Random de Python, reproducible con la misma semilla. "   # PAT 134
            "Los supuestos se muestrean independientes entre sí; no se modelan correlaciones entre el precio y el dólar.")
