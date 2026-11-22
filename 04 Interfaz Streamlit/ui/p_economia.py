"""Pestaña Economía: gas natural desplazado, CO2 evitado, valorización con Henry Hub y dólar, VAN y TIR.
PAT 142 (pedido de Jaime del 19-11-2026): flujo de caja con impuestos, con la inversión que trae la internación de Costeo, el IVA
pagado y recuperado como crédito fiscal, la depreciación tributaria, el impuesto de primera categoría y la banda de error de la
clase de estimación (motor: pat_sim/motor/internacion.py). Claves «eco_fc_»."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import economia as eco, internacion as INT
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
    # PAT 140: el Henry Hub y el dólar, con sus fuentes, ya están en el «?» de cada campo del formulario de abajo
    C.ayuda(C.esc("La planta quema gas natural licuado regasificado, que se modela como metano (Engineering ToolBox, 2003; poder calorífico superior)."),   # PAT 134: ayuda «?»
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
        inv = d.number_input(C.esc("Inversión (M$)"), 0.0, 1e7, _inversion(E, alt), 10.0, help=C.esc("Parte con la inversión estimada de la alternativa evaluada; desmarque la casilla para escribir otra. Con 0 se muestra la inversión máxima que da VAN cero."))
        cos = e.number_input(C.esc("Costo anual de operación y mantención (M$)"), 0.0, 1e6, float(E["costo_anual"]), 1.0)
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
                            ("mm", "Gas (MMBtu)", "num", 0), ("v_hh", "Al Henry Hub (M$)", "clp", 1), ("v", "Al precio elegido (M$)", "clp", 1)])
    des = r["gas_desplazado_cascada"]; nom = "la cascada"
    if alt is not None:                       # PAT 133: el ahorro es el de la alternativa evaluada
        from pat_sim.motor.resumen import _caldera
        des = eco.gas(alt["Q"], r["horas"], _caldera(pl)); nom = f"{k_alt} ({alt['nombre'].lower()})"
        st.info(C.esc(f"Se evalúa {nom}: {C.fmt(alt['Q'], 0)} kW recuperados e inversión estimada de ${C.fmt(alt['inv']['medio'], 1)} M "
                      f"(rango ${C.fmt(alt['inv']['min'], 1)} a ${C.fmt(alt['inv']['max'], 1)} M). Se cambia en la pestaña Alternativas."))
    ahorro = eco.valor_gas(des["MMBtu"], E["precio_gas"], E["dolar"])
    inv_eval = _inversion(E, alt)
    a, b, c = st.columns(3)
    a.metric("Gas desplazado por " + nom, C.fmt(des["MMBtu"], 0) + " MMBtu")
    b.metric("CO2 evitado por temporada", C.fmt(des["co2_t"], 0) + " t")
    c.metric("Ahorro por temporada", C.esc("$" + C.fmt(ahorro, 1) + " M"))

    neto = ahorro - E["costo_anual"]
    ev = eco.evaluacion(inv_eval, ahorro, E["costo_anual"], E["anios"], E["tasa"])
    fa = sum(1 / (1 + E["tasa"]) ** i for i in range(1, E["anios"] + 1))
    C.ayuda("Un ciclo de operación por año (una temporada). La TIR se calcula con la inversión ingresada; si es 0 no está definida.",   # PAT 134
            "Evaluación económica")
    d, e, f, g = st.columns(4)
    d.metric("VAN", C.esc("$" + C.fmt(ev["VAN"], 1) + " M"))
    e.metric("TIR", C.pct(ev["TIR"]) if ev["TIR"] is not None else "—")
    f.metric("Recuperación", (C.fmt(ev["recuperacion_anios"], 1) + " años") if ev["recuperacion_anios"] else "—")
    g.metric("Inversión máxima con VAN cero", C.esc("$" + C.fmt(neto * fa, 1) + " M"))
    _flujo_impuestos(E, inv_eval, ahorro, "fc")          # PAT 142

    st.markdown("#### Sensibilidad al precio del gas")
    precios = [x / 2 for x in range(2, 61)]
    df = pd.DataFrame({"Ahorro de la cascada (M$ por temporada)": [eco.valor_gas(des["MMBtu"], p, E["dolar"]) for p in precios]}, index=precios)
    st.line_chart(df, x_label="Precio del gas (US$/MMBtu)", y_label="M$ por temporada")

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
    # PAT 140: el precio de la biomasa, con su fuente, ya está en el «?» del campo del formulario de abajo
    C.ayuda(C.esc("El volumen de la biomasa sale de la densidad a granel del combustible "   # PAT 134
                  "(parámetro del generador de calor). El CO2 de la biomasa es biogénico: se informa aparte y no suma al inventario nacional "
                  "(IPCC, 2006, vol. 2, sec. 2.3.3.4)."), "Precios y supuestos")
    with st.form("form_eco_bio"):
        a, b, c = st.columns(3)
        pb = a.number_input(C.esc("Precio de la biomasa combustible ($/m³ estéreo)"), 0.0, 1e6, float(E["precio_biomasa"]), 250.0,
                            help=C.esc(f"Por defecto, astilla de pino con corteza puesta en planta: {C.fmt(C.PRECIO_BIOMASA, 0)} $/m³ estéreo sin IVA ({C.FUENTE_BIOMASA})."))
        tasa = b.number_input("Tasa de descuento (%)", 0.0, 50.0, E["tasa"] * 100, 0.5) / 100
        an = c.number_input("Horizonte (años)", 1, 50, int(E["anios"]))
        d, e = st.columns(2)
        inv = d.number_input(C.esc("Inversión (M$)"), 0.0, 1e7, _inversion(E, alt), 10.0, help=C.esc("Parte con la inversión estimada de la alternativa evaluada; desmarque la casilla para escribir otra. Con 0 se muestra la inversión máxima que da VAN cero."))
        cos = e.number_input(C.esc("Costo anual de operación y mantención (M$)"), 0.0, 1e6, float(E["costo_anual"]), 1.0)
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
                            ("v", "Valor (M$)", "clp", 1)])
    des = r["biomasa_cascada"]; nom = "la cascada"
    if alt is not None:                       # PAT 133: el ahorro es el de la alternativa evaluada
        from pat_sim.motor.resumen import _caldera
        des = _caldera(pl).consumo(alt["Q"], r["horas"]); nom = f"{k_alt} ({alt['nombre'].lower()})"
        st.info(C.esc(f"Se evalúa {nom}: {C.fmt(alt['Q'], 0)} kW recuperados e inversión estimada de ${C.fmt(alt['inv']['medio'], 1)} M. "
                      "Se cambia en la pestaña Alternativas."))
    ahorro = des["m3"] * precio / 1e6
    inv_eval = _inversion(E, alt)
    a, b, c = st.columns(3)
    a.metric("Biomasa desplazada por " + nom, C.fmt(des["t"], 0) + " t por año")
    b.metric("CO2 biogénico evitado", C.fmt(des["co2_biogenico_t"], 0) + " t por año")
    c.metric("Ahorro por año", C.esc("$" + C.fmt(ahorro, 1) + " M"))
    neto = ahorro - E["costo_anual"]
    ev = eco.evaluacion(inv_eval, ahorro, E["costo_anual"], E["anios"], E["tasa"])
    fa = sum(1 / (1 + E["tasa"]) ** i for i in range(1, E["anios"] + 1))
    st.markdown("#### Evaluación económica")
    d, e, f, g = st.columns(4)
    d.metric("VAN", C.esc("$" + C.fmt(ev["VAN"], 1) + " M"))
    e.metric("TIR", C.pct(ev["TIR"]) if ev["TIR"] is not None else "—")
    f.metric("Recuperación", (C.fmt(ev["recuperacion_anios"], 1) + " años") if ev["recuperacion_anios"] else "—")
    g.metric("Inversión máxima con VAN cero", C.esc("$" + C.fmt(neto * fa, 1) + " M"))
    _flujo_impuestos(E, inv_eval, ahorro, "fcb")         # PAT 142
    st.markdown("#### Sensibilidad al precio de la biomasa")
    precios = [x * 500.0 for x in range(0, 41)]
    df = pd.DataFrame({"Ahorro de la cascada (M$ por año)": [des["m3"] * p_ / 1e6 for p_ in precios]}, index=precios)
    st.line_chart(df, x_label="Precio de la biomasa ($/m³ estéreo)", y_label="M$ por año")
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
                                  "Importación FOB es el precio de importación del modelo económico de la planta basada en Agrozzi. "
                                  "El docente puede editar estos valores o agregar el precio industrial en el Mantenedor."))
    if st.session_state.get("_eco_esc_gas_previo") != elegido:
        st.session_state["_eco_esc_gas_previo"] = elegido
        E["precio_gas"] = dict(esc)[elegido]
        E["gas_supuesto"] = False


# ---------------------------------------------------------------- PAT 142: flujo de caja con impuestos e internación
_MODOS_RENTA = {"ley": "Gradual de la Ley 21.850", "fija": "Tasa fija"}


def _flujo_impuestos(E: dict, inv_eval: float, ahorro: float, pre: str):
    """Flujo de caja anual con IVA, depreciación e impuesto de primera categoría (motor/internacion.flujo_caja), con la inversión
    que se evalúa arriba (que trae la internación si se llevó desde Costeo con la internación sumada)."""
    o = INT.opciones_flujo(E)
    C.ayuda(C.esc(
        "Flujo anual del proyecto en millones de pesos. Año 0: inversión (equipos, internación, instalación y terreno) e IVA de la "
        "inversión, que se paga y se recupera como crédito fiscal (D.L. 825, art. 23 N.º 1): en el año 0 si la empresa ya opera, en "
        "el año 1 si es un proyecto nuevo (art. 27 bis). Años 1 a n: ahorro menos costo de operación menos depreciación da la "
        "utilidad antes de impuesto; el impuesto de primera categoría se calcula sobre ella y la depreciación se suma de vuelta "
        "porque no es salida de caja. El IVA de la inversión se toma como 19 % de la inversión sin terreno, porque equipos, "
        "internación, montaje y servicios pagan IVA. Los derechos de aduana no se recuperan: quedan en el activo y se deprecian. "
        f"{INT.FUENTE_RENTA}. {INT.JUST_VIDA}. {INT.JUST_DESECHO}. {INT.JUST_PERDIDA}."), "Flujo de caja con impuestos")
    with st.form(f"eco_{pre}_form"):
        a, b, c, d = st.columns(4)
        modo = a.radio("Impuesto de primera categoría", list(_MODOS_RENTA), format_func=lambda k: _MODOS_RENTA[k],
                       index=0 if o["tasa_renta_modo"] == "ley" else 1, key=f"eco_{pre}_modo", help=C.esc(INT.FUENTE_RENTA))
        tasa_f = b.number_input("Tasa fija (%)", 0.0, 60.0, float(o["tasa_renta"]) * 100, 0.5, key=f"eco_{pre}_tasa",
                                help="Solo con «Tasa fija». Por defecto 27 %, la tasa general antes de la gradualidad de la Ley 21.850.")
        reg = c.selectbox("Depreciación", list(INT.VIDA), index=list(INT.VIDA).index(o["regimen_dep"]), key=f"eco_{pre}_dep",
                          format_func=lambda k: f"{k.capitalize()} ({INT.VIDA[k][0]} años)",
                          help=C.esc(" ".join(f"{v[1]}." for v in INT.VIDA.values()) + " " + INT.JUST_VIDA + "."))
        caso = d.selectbox("Recuperación del IVA", list(INT.CASOS_IVA), index=list(INT.CASOS_IVA).index(o["caso_iva"]), key=f"eco_{pre}_iva",
                           format_func=lambda k: "Año 0, empresa en operación" if k == "A" else "Año 1, proyecto nuevo",
                           help=C.esc(" ".join(f"{k}: {v}." for k, v in INT.CASOS_IVA.items())))
        e, f, g, h = st.columns(4)
        anio = e.number_input("Año de la inversión", 2020, 2100, int(o["anio_inversion"]), 1, key=f"eco_{pre}_anio", format="%d", help=INT.JUST_ANIO + ".")
        otras = f.checkbox("Empresa con utilidades", value=bool(o["otras_utilidades"]), key=f"eco_{pre}_otras", help=INT.JUST_PERDIDA + ".")
        desecho = g.checkbox("Valor de desecho contable", value=bool(o["valor_desecho"]), key=f"eco_{pre}_desecho", help=INT.JUST_DESECHO + ".")
        claves = list(INT.CLASES)
        clase = h.selectbox("Clase de estimación", claves, index=claves.index(o["clase_estimacion"]), key=f"eco_{pre}_clase",
                            format_func=lambda k: f"{INT.CLASES[k][0]} (± {C.fmt(INT.CLASES[k][2] * 100, 0)} %)", help=C.esc(INT.FUENTE_CLASES + "."))
        if st.form_submit_button("Aplicar"):
            E.update(tasa_renta_modo=modo, tasa_renta=float(tasa_f) / 100, regimen_dep=reg, caso_iva=caso, anio_inversion=int(anio),
                     otras_utilidades=bool(otras), valor_desecho=bool(desecho), clase_estimacion=clase)
    r = INT.flujo_desde_economia(E, inv_eval, ahorro)
    k = st.columns(4)
    k[0].metric("VAN con impuestos", C.esc("$" + C.fmt(r["VAN"], 1) + " M"))
    k[1].metric("TIR con impuestos", C.pct(r["TIR"]) if r["TIR"] is not None else "—")
    k[2].metric("Recuperación con impuestos", (C.fmt(r["recuperacion_anios"], 1) + " años") if r["recuperacion_anios"] else "—")
    bd = r["banda"]
    k[3].metric(f"VAN con la banda de ± {C.fmt(bd['error_max'] * 100, 0)} %", C.esc(f"${C.fmt(r['VAN_banda'][0], 1)} M"),
                C.esc(f"a ${C.fmt(r['VAN_banda'][1], 1)} M"), delta_color="off", help=C.esc(f"VAN con la inversión de ${C.fmt(bd['alto'], 1)} M y de ${C.fmt(bd['bajo'], 1)} M, clase {bd['nombre'].lower()} ({INT.FUENTE_CLASES})."))
    partes = [f"IVA de la inversión: ${C.fmt(r['iva'], 1)} M, recuperado en el año {r['anio_recuperacion_iva']}",
              f"depreciación {o['regimen_dep']} en {r['vida_util']} años"]
    if r["desde_costeo"] and r["internacion"] > 0:
        partes.insert(0, f"la inversión incluye ${C.fmt(r['internacion'], 1)} M de internación"
                         + (f" (derechos de aduana ${C.fmt(float(E.get('arancel_m') or 0.0), 1)} M)" if E.get("arancel_m") else ""))
    elif not r["desde_costeo"]:
        partes.insert(0, "la inversión no viene de Costeo: para sumar la internación, márquela en Costeo y lleve la inversión")
    if r["terreno"] > 0:
        partes.append(f"terreno de ${C.fmt(r['terreno'], 1)} M sin depreciar ni IVA")
    st.caption(C.esc("; ".join(partes)[:1].upper() + "; ".join(partes)[1:] + "."))
    filas = [dict(f, anio_txt=f"{f['anio']} ({f['anio_calendario']})", tr=f["tasa_renta"] if f["anio"] > 0 else None) for f in r["filas"]]
    with st.expander("Flujo de caja por año (M$)"):
        C.mostrar_tabla(filas, [("anio_txt", "Año", "cen", 0), ("ahorro", "Ahorro", "mm", 1), ("costo", "Operación y mantención", "mm", 1),
                                ("depreciacion", "Depreciación", "mm", 1), ("uai", "Utilidad antes de impuesto", "mm", 1),
                                ("tr", "Tasa de impuesto", "pct", 1), ("impuesto", "Impuesto", "mm", 1), ("inversion", "Inversión", "mm", 1),
                                ("iva_pagado", "IVA pagado", "mm", 1), ("iva_recuperado", "IVA recuperado", "mm", 1),
                                ("valor_desecho", "Valor de desecho", "mm", 1), ("flujo", "Flujo neto", "mm", 1),
                                ("flujo_desc", "Flujo descontado", "mm", 1), ("acumulado", "Flujo acumulado", "mm", 1)])
