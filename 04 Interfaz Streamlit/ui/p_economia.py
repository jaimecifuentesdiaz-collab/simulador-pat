"""Pestaña Economía: gas natural desplazado, CO2 evitado, valorización con Henry Hub y dólar, VAN y TIR."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import economia as eco
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla
from . import p_alternativas as PA
from . import s_riesgo, s_optimizacion   # PAT 133, mejoras 5 y 10     # PAT 133, mejora 2: inversión y ahorro de la alternativa elegida


def _alternativa(pl, r):
    """PAT 133: alternativa que se evalúa (la ganadora del multicriterio o la elegida en Alternativas) y su inversión estimada."""
    try:
        X = PA.alternativas_sesion(pl, r); k = PA.elegida(X); return k, X["alts"][k]
    except Exception:
        return None, None


def _inversion(E, alt) -> float:
    """Con la casilla marcada, la inversión parte con la estimada de la alternativa (Shamoushaki et al., 2021, o DEA, 2026)."""
    return round(float(alt["inv"]["medio"]), 1) if (alt is not None and E.get("inv_auto", True)) else float(E["inversion"])


def _riesgo(pl, r, E, inv_eval):
    """PAT 133: tornado, Monte Carlo y optimización con la inversión que se está evaluando."""
    k, alt = _alternativa(pl, r)
    r2 = dict(r)
    if alt is not None and r.get("horas"):     # el riesgo se calcula con el combustible que desplaza la alternativa evaluada
        from pat_sim.motor.resumen import _caldera
        cal = _caldera(pl)
        if "gas_desplazado_cascada" in r:
            r2["gas_desplazado_cascada"] = eco.gas(alt["Q"], r["horas"], cal)
        elif "biomasa_cascada" in r:
            r2["biomasa_cascada"] = cal.consumo(alt["Q"], r["horas"])
    s_riesgo.mostrar(pl, r2, dict(E, inversion=inv_eval), titulo=f"Riesgo del VAN de {k}" if alt is not None else None)
    # la optimización recalcula la cascada en serie sobre copias de la planta: se evalúa con la inversión estimada de la cascada (A2)
    try:
        inv_casc = PA.alternativas_sesion(pl, r)["alts"]["A2"]["inv"]["medio"] if E.get("inv_auto", True) else inv_eval
    except Exception:
        inv_casc = inv_eval
    s_optimizacion.mostrar(pl, r, dict(E, inversion=inv_casc))


def _partir_de_base(ss) -> None:
    """PAT 135, sin valores fijos: la primera vez en la sesión, los parámetros económicos de partida salen del mantenedor
    (con respaldo a los valores de comun.py). El precio del gas usa la clave del gas natural industrial en Chile; si no hay
    un valor con fuente segura en la base, queda el Henry Hub como «Supuesto: Henry Hub, revisar»."""
    if ss.get("_eco_desde_base"):
        return
    ss._eco_desde_base = True
    E = ss.economia
    try:
        from pat_sim.datos import mantenedor as M
        bd = C.obtener_bd()
        gas_chile = M.parametro(M.CLAVE_GAS_CHILE, None, bd=bd)
        E["precio_gas"] = gas_chile if gas_chile is not None else M.parametro("henry_hub", C.HENRY_HUB, bd=bd)
        E["gas_supuesto"] = gas_chile is None
        E["dolar"] = M.parametro("dolar", C.DOLAR, bd=bd)
        E["tasa"] = M.parametro("tasa_descuento", E["tasa"], bd=bd)
        E["anios"] = int(M.parametro("anios_evaluacion", E["anios"], bd=bd))
        E["precio_biomasa"] = M.parametro("precio_biomasa", C.PRECIO_BIOMASA, bd=bd)
        E["cepci"] = M.parametro("cepci", None, bd=bd)
    except Exception:                                    # sin base, quedan los valores de comun.py
        E["gas_supuesto"] = True


def mostrar():
    ss = st.session_state; pl = C.planta()
    _partir_de_base(ss); E = ss.economia
    st.subheader("Economía")
    if not pl.equipos:       # PAT 135: planta vacía (desafío en blanco)
        st.info("La planta está vacía: agregue equipos en Diseño.")
        return
    if not C.exigir_resuelta():
        return
    r = C.resumen_actual()
    if "biomasa_base" in r:
        mostrar_biomasa(r)
        return
    if "gas_base" not in r:
        st.warning("La planta no tiene una caldera con horas de operación declaradas: no se puede calcular el gas desplazado.")
        return
    k_alt, alt = _alternativa(pl, r)
    C.ayuda(C.esc(f"Henry Hub: {C.fmt(C.HENRY_HUB, 2)} US$/MMBtu, {C.FUENTE_HH}. Dólar: {C.fmt(C.DOLAR, 2)} $/US$, {C.FUENTE_DOLAR}. "   # PAT 134: ayuda «?»
                  f"La planta quema gas natural licuado regasificado, que se modela como metano (Engineering ToolBox, 2003; poder calorífico superior)."),
            "Precios y supuestos")
    _escenario_gas(E)                                         # PAT 135: Henry Hub, importación o precio industrial del mantenedor
    with st.form("form_eco"):
        a, b, c = st.columns(3)
        pg = a.number_input(C.esc("Precio del gas (US$/MMBtu)"), 0.0, 100.0, float(E["precio_gas"]), 0.1,
                            help=C.esc(f"Por defecto, el Henry Hub de agosto de 2026: {C.fmt(C.HENRY_HUB, 2)} US$/MMBtu ({C.FUENTE_HH}). Es un piso: no incluye licuefacción, transporte ni regasificación."
                                 + (" Supuesto: Henry Hub, revisar. Agregue el parámetro precio_gas_industrial_chile en el Mantenedor con su fuente." if E.get("gas_supuesto", True) else "")))
        dl = b.number_input(C.esc("Dólar observado ($/US$)"), 1.0, 5000.0, float(E["dolar"]), 1.0, help=C.FUENTE_DOLAR)
        tasa = c.number_input("Tasa de descuento (%)", 0.0, 50.0, E["tasa"] * 100, 0.5) / 100
        d, e, f = st.columns(3)
        inv = d.number_input(C.esc("Inversión (MM$)"), 0.0, 1e7, _inversion(E, alt), 10.0, help=C.esc("Parte con la inversión estimada de la alternativa evaluada; desmarque la casilla para escribir otra. Con 0 se muestra la inversión máxima que da VAN cero."))
        cos = e.number_input(C.esc("Costo anual de operación y mantención (MM$)"), 0.0, 1e6, float(E["costo_anual"]), 1.0)
        an = f.number_input("Horizonte (años)", 1, 50, int(E["anios"]))
        auto = st.checkbox("Usar la inversión estimada de la alternativa evaluada", value=bool(E.get("inv_auto", True)), key="eco_inv_auto",
                           disabled=alt is None)
        if st.form_submit_button("Aplicar", type="primary"):
            E.update(precio_gas=pg, dolar=dl, tasa=tasa, inversion=inv, costo_anual=cos, anios=int(an), inv_auto=auto)

    casos = [("Caso base: todo el sumidero con caldera", r["gas_base"]), ("Ahorro de la cascada en serie (alternativa 1)", r["gas_cascada"]),
             ("Ahorro con el objetivo pinch", r["gas_pinch"]), ("Ahorro de solo los condensados (alternativa 2)", r["gas_alt2"]),
             ("Brecha remanente con la cascada", r["gas_remanente_cascada"])]
    filas = [dict(caso=n, mwh=g["gas_MWh"], m3=g["m3"], co2=g["co2_t"], mm=g["MMBtu"], v_hh=eco.valor_gas(g["MMBtu"], C.HENRY_HUB, E["dolar"]),
                  v=eco.valor_gas(g["MMBtu"], E["precio_gas"], E["dolar"])) for n, g in casos]
    for f, (n, _g) in zip(filas, casos):
        f["caso"] = n
    AT.tabla("eco_gas", "Gas natural y emisiones por temporada", 4, hh=C.FUENTE_HH)   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("caso", "Caso", "txt", 0), ("mwh", "Gas (MWh PCS)", "num", 0), ("m3", "Gas (m³)", "num", 0), ("co2", "CO2 (t)", "num", 0),
                            ("mm", "Gas (MMBtu)", "num", 0), ("v_hh", "Al Henry Hub (MM$)", "clp", 1), ("v", "Al precio elegido (MM$)", "clp", 1)])
    des = r["gas_desplazado_cascada"]; nom = "la cascada"
    if alt is not None:                       # PAT 133: el ahorro es el de la alternativa evaluada
        from pat_sim.motor.resumen import _caldera
        des = eco.gas(alt["Q"], r["horas"], _caldera(pl)); nom = f"{k_alt} ({alt['nombre'].lower()})"
        st.info(C.esc(f"Se evalúa {nom}: {C.fmt(alt['Q'], 0)} kW recuperados e inversión estimada de ${C.fmt(alt['inv']['medio'], 1)} MM "
                      f"(rango ${C.fmt(alt['inv']['min'], 1)} a ${C.fmt(alt['inv']['max'], 1)} MM). Se cambia en la pestaña Alternativas."))
    ahorro = eco.valor_gas(des["MMBtu"], E["precio_gas"], E["dolar"])
    inv_eval = _inversion(E, alt)
    a, b, c = st.columns(3)
    a.metric("Gas desplazado por " + nom, C.fmt(des["MMBtu"], 0) + " MMBtu")
    b.metric("CO2 evitado por temporada", C.fmt(des["co2_t"], 0) + " t")
    c.metric("Ahorro por temporada", C.esc("$" + C.fmt(ahorro, 1) + " MM"))

    neto = ahorro - E["costo_anual"]
    ev = eco.evaluacion(inv_eval, ahorro, E["costo_anual"], E["anios"], E["tasa"])
    fa = sum(1 / (1 + E["tasa"]) ** i for i in range(1, E["anios"] + 1))
    C.ayuda("Un ciclo de operación por año (una temporada). La TIR se calcula con la inversión ingresada; si es 0 no está definida.",   # PAT 134
            "Evaluación económica")
    d, e, f, g = st.columns(4)
    d.metric("VAN", C.esc("$" + C.fmt(ev["VAN"], 1) + " MM"))
    e.metric("TIR", C.pct(ev["TIR"]) if ev["TIR"] is not None else "—")
    f.metric("Recuperación", (C.fmt(ev["recuperacion_anios"], 1) + " años") if ev["recuperacion_anios"] else "—")
    g.metric("Inversión máxima con VAN cero", C.esc("$" + C.fmt(neto * fa, 1) + " MM"))

    st.markdown("#### Sensibilidad al precio del gas")
    precios = [x / 2 for x in range(2, 61)]
    df = pd.DataFrame({"Ahorro de la cascada (MM$ por temporada)": [eco.valor_gas(des["MMBtu"], p, E["dolar"]) for p in precios]}, index=precios)
    st.line_chart(df, x_label="Precio del gas (US$/MMBtu)", y_label="MM$ por temporada")

    AT.tabla("eco_bomba", "Bomba de calor frente a la cascada", 4, pmm=C.FUENTE_PMM,   # PAT 134: «?» de la tabla
             antes=f"COP {C.fmt(ss.cop, 1)} de la pestaña Recuperación de calor.")
    filas = []
    for n, p in C.PMM:
        filas.append(dict(n=n, p=p, eq=eco.equilibrio_bomba_calor(r["cobertura_cascada"], r["eta_pcs"], ss.cop, p, E["dolar"])))
    C.mostrar_tabla(filas, [("n", "Precio de la electricidad", "txt", 0), ("p", "$/kWh", "num", 2), ("eq", "Precio del gas sobre el cual conviene la bomba (US$/MMBtu)", "num", 1)])
    _riesgo(pl, r, E, inv_eval)


def mostrar_biomasa(r):
    """Rubros pellet, chip y leña: el generador de calor quema biomasa; la recuperación desplaza ese combustible."""
    ss = st.session_state; E = ss.economia; E.setdefault("precio_biomasa", C.PRECIO_BIOMASA)
    pl = C.planta(); k_alt, alt = _alternativa(pl, r)
    C.ayuda(C.esc(f"Biomasa: {C.fmt(C.PRECIO_BIOMASA, 0)} $/m³ estéreo, {C.FUENTE_BIOMASA}. El volumen sale de la densidad a granel del combustible "   # PAT 134
                  "(parámetro del generador de calor). El CO2 de la biomasa es biogénico: se informa aparte y no suma al inventario nacional "
                  "(IPCC, 2006, vol. 2, sec. 2.3.3.4)."), "Precios y supuestos")
    with st.form("form_eco_bio"):
        a, b, c = st.columns(3)
        pb = a.number_input(C.esc("Precio de la biomasa combustible ($/m³ estéreo)"), 0.0, 1e6, float(E["precio_biomasa"]), 250.0,
                            help=C.esc(f"Por defecto, astilla de pino con corteza puesta en planta: {C.fmt(C.PRECIO_BIOMASA, 0)} $/m³ estéreo sin IVA ({C.FUENTE_BIOMASA})."))
        tasa = b.number_input("Tasa de descuento (%)", 0.0, 50.0, E["tasa"] * 100, 0.5) / 100
        an = c.number_input("Horizonte (años)", 1, 50, int(E["anios"]))
        d, e = st.columns(2)
        inv = d.number_input(C.esc("Inversión (MM$)"), 0.0, 1e7, _inversion(E, alt), 10.0, help=C.esc("Parte con la inversión estimada de la alternativa evaluada; desmarque la casilla para escribir otra. Con 0 se muestra la inversión máxima que da VAN cero."))
        cos = e.number_input(C.esc("Costo anual de operación y mantención (MM$)"), 0.0, 1e6, float(E["costo_anual"]), 1.0)
        auto = st.checkbox("Usar la inversión estimada de la alternativa evaluada", value=bool(E.get("inv_auto", True)), key="eco_inv_auto_b",
                           disabled=alt is None)
        if st.form_submit_button("Aplicar", type="primary"):
            E.update(precio_biomasa=pb, tasa=tasa, inversion=inv, costo_anual=cos, anios=int(an), inv_auto=auto)
    precio = E["precio_biomasa"]
    casos = [("Caso base: todo el sumidero con el generador", r["biomasa_base"]), ("Ahorro de la cascada en serie", r["biomasa_cascada"]),
             ("Ahorro con el objetivo pinch", r["biomasa_pinch"]), ("Brecha remanente con la cascada", r["biomasa_remanente_cascada"])]
    filas = [dict(caso=n, mwh=g["MWh_pci"], t=g["t"], ts=g["t_seca"], m3=g["m3"], co2=g["co2_biogenico_t"], v=g["m3"] * precio / 1e6) for n, g in casos]
    AT.tabla("eco_biomasa", "Biomasa combustible y emisiones por año", 4, bio=C.FUENTE_BIOMASA)   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("caso", "Caso", "txt", 0), ("mwh", "Biomasa (MWh PCI)", "num", 0), ("t", "Biomasa húmeda (t)", "num", 0),
                            ("ts", "Biomasa seca (t)", "num", 0), ("m3", "Volumen (m³ estéreo)", "num", 0), ("co2", "CO2 biogénico (t)", "num", 0),
                            ("v", "Valor (MM$)", "clp", 1)])
    des = r["biomasa_cascada"]; nom = "la cascada"
    if alt is not None:                       # PAT 133: el ahorro es el de la alternativa evaluada
        from pat_sim.motor.resumen import _caldera
        des = _caldera(pl).consumo(alt["Q"], r["horas"]); nom = f"{k_alt} ({alt['nombre'].lower()})"
        st.info(C.esc(f"Se evalúa {nom}: {C.fmt(alt['Q'], 0)} kW recuperados e inversión estimada de ${C.fmt(alt['inv']['medio'], 1)} MM. "
                      "Se cambia en la pestaña Alternativas."))
    ahorro = des["m3"] * precio / 1e6
    inv_eval = _inversion(E, alt)
    a, b, c = st.columns(3)
    a.metric("Biomasa desplazada por " + nom, C.fmt(des["t"], 0) + " t por año")
    b.metric("CO2 biogénico evitado", C.fmt(des["co2_biogenico_t"], 0) + " t por año")
    c.metric("Ahorro por año", C.esc("$" + C.fmt(ahorro, 1) + " MM"))
    neto = ahorro - E["costo_anual"]
    ev = eco.evaluacion(inv_eval, ahorro, E["costo_anual"], E["anios"], E["tasa"])
    fa = sum(1 / (1 + E["tasa"]) ** i for i in range(1, E["anios"] + 1))
    st.markdown("#### Evaluación económica")
    d, e, f, g = st.columns(4)
    d.metric("VAN", C.esc("$" + C.fmt(ev["VAN"], 1) + " MM"))
    e.metric("TIR", C.pct(ev["TIR"]) if ev["TIR"] is not None else "—")
    f.metric("Recuperación", (C.fmt(ev["recuperacion_anios"], 1) + " años") if ev["recuperacion_anios"] else "—")
    g.metric("Inversión máxima con VAN cero", C.esc("$" + C.fmt(neto * fa, 1) + " MM"))
    st.markdown("#### Sensibilidad al precio de la biomasa")
    precios = [x * 500.0 for x in range(0, 41)]
    df = pd.DataFrame({"Ahorro de la cascada (MM$ por año)": [des["m3"] * p_ / 1e6 for p_ in precios]}, index=precios)
    st.line_chart(df, x_label="Precio de la biomasa ($/m³ estéreo)", y_label="MM$ por año")
    _riesgo(pl, r, E, inv_eval)

def _escenarios_gas() -> list:
    """PAT 135: escenarios de precio del gas leídos del mantenedor (los mismos del modelo de los Capítulos 2 a 4)."""
    out = []
    try:
        from pat_sim.datos import mantenedor as M
        bd = C.obtener_bd()
        hh = M.parametro("henry_hub", C.HENRY_HUB, bd=bd)
        out.append((f"Henry Hub ({C.fmt(hh, 2)} US$/MMBtu)", hh))
        imp = M.parametro(M.CLAVE_GAS_IMPORTACION, None, bd=bd)
        if imp is not None:
            out.append((f"Importación FOB ({C.fmt(imp, 2)} US$/MMBtu)", imp))
        ind = M.parametro(M.CLAVE_GAS_CHILE, None, bd=bd)
        if ind is not None:
            out.append((f"Industrial en Chile ({C.fmt(ind, 2)} US$/MMBtu)", ind))
    except Exception:
        out = [(f"Henry Hub ({C.fmt(C.HENRY_HUB, 2)} US$/MMBtu)", C.HENRY_HUB)]
    return out


def _escenario_gas(E: dict):
    """PAT 135: al cambiar el escenario se reemplaza el precio del gas del formulario; después se puede editar a mano."""
    esc = _escenarios_gas()
    if len(esc) < 2:
        return
    nombres = [n for n, _ in esc]
    inicial = len(nombres) - 1 if nombres[-1].startswith("Industrial") else 0   # si existe el precio industrial, parte con él
    elegido = st.radio(C.esc("Escenario de precio del gas"), nombres, index=inicial, horizontal=True, key="eco_esc_gas",
                       help=C.esc("Henry Hub es la referencia de Estados Unidos que la CNE usa para el GNL importado (piso). "
                                  "Importación FOB es el precio de importación del modelo de los Capítulos 2 a 4. "
                                  "El profesor puede editar estos valores o agregar el precio industrial en el Mantenedor."))
    if st.session_state.get("_eco_esc_gas_previo") != elegido:
        st.session_state["_eco_esc_gas_previo"] = elegido
        E["precio_gas"] = dict(esc)[elegido]
        E["gas_supuesto"] = False
