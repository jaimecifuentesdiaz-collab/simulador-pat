"""Pestaña Calculadoras (PAT 132): herramientas de estimación sacadas por ingeniería inversa de simuladores de procesos
(DWSIM, CheCalc, Aspen Energy Analyzer, PinCH, SuperPro Designer, Engineering ToolBox, Simul8). Se abren con los datos de la
planta actual cuando existen y cada una cita su fuente."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import calculadoras as K
from pat_sim.motor import propiedades as PR
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

PCI = {"Gas natural": 48.0, "Diésel (gas oil)": 43.0, "Gas licuado (GLP)": 47.3}      # MJ/kg, IPCC (2006), Vol. 2, Cap. 1, Tabla 1.2


def _f(x, d=1):
    return "—" if x is None else C.fmt(x, d)


def _fuente(clave):
    C.ayuda(f"Fuente: {K.FUENTES[clave]}.")   # PAT 134: ayuda «?»


def _n(col, et, v, paso=1.0, f="%.2f", key=None, **kw):
    return col.number_input(et, value=float(v), step=float(paso), format=f, key=key, **kw)


def _equipo(pl, pref):
    return next((e for e in pl.equipos.values() if e.tipo.startswith(pref) and e.resultado is not None), None)


def mostrar():
    pl = C.planta(); ss = st.session_state
    if ss.get("k_planta") != pl.nombre:            # otra planta: las calculadoras vuelven a partir de sus datos
        for k in [k for k in ss.keys() if str(k).startswith("k_")]:
            ss.pop(k, None)
        ss["k_planta"] = pl.nombre
    C.ayuda("Herramientas de estimación de los simuladores de procesos comerciales y libres, para revisar a mano lo que "   # PAT 134
            "calcula el motor o dimensionar una mejora. Parten con los datos de la planta actual cuando existen; cambie cualquier valor.",
            "Calculadoras de ingeniería", 3)
    t = st.tabs(["Intercambiador", "Pinch", "Vapor y evaporador", "Caldera y CO2", "Secador", "Letalidad", "Bombas y tuberías",
                 "Costo de equipos", "OEE y colas", "Propiedades según °Brix"])
    for tab, fn in zip(t, (_hx, _pinch, _evap, _caldera, _secador, _letalidad, _tuberia, _costos, _oee, _brix)):
        with tab:
            try:
                fn(pl)
            except ValueError as e:
                st.error(str(e))


def _horas_planta(pl) -> float:
    """PAT 135: horas de operación del primer equipo que las declara; 8.000 h (supuesto) si la planta está vacía."""
    for e in pl.equipos.values():
        if hasattr(e, "horas"):
            return float(e.horas())
    return 8000.0


def _hx(pl):
    snk = pl.sumideros()[0] if pl.resuelta and pl.sumideros() else None
    res = sorted([r for r in (pl.residuales() if pl.resuelta else []) if r.CP], key=lambda r: -r.Q)
    cp0 = 3.98 if pl.rubro == "tomate" else 1.01
    C.ayuda("Dimensiona un intercambiador por LMTD (contracorriente y tubos y carcasa 1-2) y entrega su efectividad y NTU, como DWSIM y CheCalc.")   # PAT 134
    a, b, c = st.columns(3)
    cp = _n(a, "cp del fluido frío (kJ/kg·K)", cp0, 0.01, key="k_hx_cp")
    m = _n(a, "Caudal del fluido frío (kg/s)", (snk.CP / cp0) if snk else 10.0, 0.1, key="k_hx_m")
    Tci = _n(b, "Entrada del frío (°C)", snk.T_in if snk else 25.0, 1.0, "%.1f", key="k_hx_tci")
    Tco = _n(b, "Salida del frío (°C)", min(snk.T_out, snk.T_in + 10) if snk else 70.0, 1.0, "%.1f", key="k_hx_tco")
    Thi = _n(c, "Entrada del caliente (°C)", res[0].T_in if res else 95.0, 1.0, "%.1f", key="k_hx_thi")
    CPh = _n(c, "CP del caliente (kW/K)", res[0].CP if res else 50.0, 1.0, key="k_hx_cph")
    U = _n(a, "U global (W/m²·K)", 1500.0, 50.0, "%.0f", key="k_hx_U", help="Placas líquido-líquido 1.500 a 4.000; tubos y carcasa 300 a 1.500 (Incropera et al., 2007)")
    Q = m * cp * (Tco - Tci); Tho = Thi - Q / CPh if CPh else Thi
    st.caption(f"Del balance: Q = {_f(Q, 0)} kW y el caliente sale a {_f(Tho)} °C" + (f" (corriente {res[0].nombre} de la planta)" if res else ""))
    r = K.intercambiador(m, cp, Tci, Tco, Thi, Tho, U)
    x = st.columns(5)
    x[0].metric("LMTD", _f(r["LMTD"]) + " °C"); x[1].metric("Área en contracorriente", _f(r["A_contracorriente_m2"]) + " m²")
    x[2].metric("Factor F (1-2)", _f(r["F_12"], 2)); x[3].metric("Efectividad", C.pct(r["efectividad"])); x[4].metric("NTU", _f(r["NTU"], 2))
    for a_ in r["avisos"]:
        st.warning(a_)
    _fuente("intercambiador")


def _pinch(pl):
    C.ayuda("Tabla del problema, curvas compuestas y metas de servicios (Aspen Energy Analyzer, PinCH). Caliente: entrada mayor que salida. "   # PAT 134
            "Un calor latente se escribe como una corriente que baja 1 °C con CP igual a su calor.")
    filas = []
    if pl.resuelta:
        Tf = float(pl.globales.get("T_final_residual", 30.0))
        for r in pl.residuales():
            if r.CP:
                filas.append(dict(Corriente=r.nombre, Entrada=float(r.T_in), Salida=float(r.T_out if r.T_out is not None else Tf), CP=float(r.CP)))
            else:
                filas.append(dict(Corriente=r.nombre, Entrada=float(r.T_in), Salida=float(r.T_in) - 1.0, CP=float(r.Q)))
        for s in pl.sumideros():
            filas.append(dict(Corriente=s.nombre, Entrada=float(s.T_in), Salida=float(s.T_out), CP=float(s.CP)))
    if not filas:
        filas = [dict(Corriente="1", Entrada=20.0, Salida=135.0, CP=2.0), dict(Corriente="2", Entrada=170.0, Salida=60.0, CP=3.0),
                 dict(Corriente="3", Entrada=80.0, Salida=140.0, CP=4.0), dict(Corriente="4", Entrada=150.0, Salida=30.0, CP=1.5)]
    df0 = pd.DataFrame(filas)
    AT.tabla("k_pinch_editor", "Corrientes del problema")   # PAT 134: «?» de la tabla
    df = st.data_editor(df0, num_rows="dynamic", key="k_pinch_tabla", width="stretch")
    df = df0 if df is None else df
    dT = st.number_input("ΔTmin (°C)", value=float(pl.globales.get("dT_min", 10.0)), step=0.5, key="k_pinch_dT")
    r = K.tabla_problema([(str(f.Corriente), float(f.Entrada), float(f.Salida), float(f.CP)) for f in df.itertuples() if pd.notna(f.CP)], dT)
    x = st.columns(4)
    x[0].metric("Servicio caliente mínimo", _f(r["QH_min"], 0) + " kW"); x[1].metric("Servicio frío mínimo", _f(r["QC_min"], 0) + " kW")
    x[2].metric("Calor recuperable", _f(r["recuperado"], 0) + " kW")
    x[3].metric("Pinch (caliente / frío)", "sin pinch" if r["T_pinch_desplazada"] is None else f"{_f(r['T_pinch_caliente'])} / {_f(r['T_pinch_fria'])} °C")
    cc, cf = r["compuestas"]["caliente"], r["compuestas"]["fria"]
    if cc and cf:
        Hs = sorted({h for h, _ in cc + cf})
        def interp(p, h):
            for (h0, t0), (h1, t1) in zip(p, p[1:]):
                if h0 - 1e-9 <= h <= h1 + 1e-9:
                    return t0 if h1 == h0 else t0 + (t1 - t0) * (h - h0) / (h1 - h0)
            return None
        st.line_chart(pd.DataFrame({"Calor (kW)": Hs, "Compuesta caliente": [interp(cc, h) for h in Hs],
                                    "Compuesta fría": [interp(cf, h) for h in Hs]}), x="Calor (kW)", y_label="Temperatura (°C)")
    AT.tabla("k_pinch_intervalos", "Tabla del problema")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(r["intervalos"], [("T_alta", "T alta desplazada (°C)", "num", 1), ("T_baja", "T baja desplazada (°C)", "num", 1),
                                      ("CP_calientes", "Σ CP calientes (kW/K)", "num", 2), ("CP_frias", "Σ CP frías (kW/K)", "num", 2),
                                      ("dH", "Balance del intervalo (kW)", "num", 1), ("cascada_corregida", "Cascada corregida (kW)", "num", 1)])
    _fuente("pinch")


def _evap(pl):
    a, b, c = st.columns(3)
    T = _n(a, "Temperatura de saturación (°C)", 100.0, 1.0, "%.1f", key="k_vap_T", min_value=1.0, max_value=370.0)
    v = K.vapor_saturado(T)
    a.metric("Presión", _f(v["p_kPa"]) + " kPa"); b.metric("hf / hg", f"{_f(v['hf'], 1)} / {_f(v['hg'], 1)} kJ/kg"); c.metric("Calor latente", _f(v["hfg"], 1) + " kJ/kg")
    _fuente("vapor")
    st.markdown("##### Evaporador: agua evaporada, vapor por economía y alternativa MVR")
    w2 = pl.equipos.get("W2") if pl.rubro == "tomate" else None
    F0 = w2.resultado.detalle.get("carga_t_h") if w2 is not None and w2.resultado else 50.0
    p = getattr(pl, "_p", {}) or {}
    a, b, c = st.columns(3)
    F = _n(a, "Alimentación (t/h)", F0, 1.0, key="k_ev_F")
    xF = _n(a, "Sólidos de entrada (fracción)", p.get("xF", 0.05), 0.01, "%.3f", key="k_ev_xF")
    xP = _n(b, "Sólidos de salida (fracción)", p.get("xP", 0.28), 0.01, "%.3f", key="k_ev_xP")
    n = int(b.number_input("Efectos", 1, 7, int(p.get("N", 3)), key="k_ev_n"))
    fe = _n(c, "Economía por efecto", 0.85, 0.05, key="k_ev_fe", help="E ≈ 0,8 a 0,9 por efecto (Singh y Heldman, 2014)")
    eta = _n(c, "Rendimiento isentrópico del MVR", p.get("etaMVR", 0.75), 0.01, key="k_ev_eta")
    r = K.evaporador(F, xF, xP, n, fe, p.get("TbMVR", 70.0), p.get("TcMVR", 75.0), eta)
    x = st.columns(4)
    x[0].metric("Agua evaporada", _f(r["agua_t_h"], 2) + " t/h"); x[1].metric("Vapor vivo", _f(r["vapor_t_h"], 2) + " t/h", f"economía {_f(r['economia'], 2)}", delta_color="off")
    x[2].metric("Potencia MVR", _f(r["mvr_kW"], 0) + " kW", f"{_f(r['mvr_kWh_t'], 1)} kWh por t de agua", delta_color="off")
    x[3].metric("Producto", _f(r["producto_t_h"], 2) + " t/h")
    _fuente("evaporador")


def _caldera(pl):
    p = getattr(pl, "_p", {}) or {}
    d1 = _equipo(pl, "caldera")
    Ts0 = float(p.get("Ts", 184.1))
    q0 = (d1.resultado.detalle.get("Q_vapor_kW") or 0) if d1 is not None else 0
    v0 = q0 * 3.6 / (PR.sat(Ts0)[1] - PR.sat(80.0)[0]) if q0 else 10.0
    a, b, c = st.columns(3)
    comb = a.selectbox("Combustible", list(PCI) + ["Madera y astilla (biogénico)"], index=0 if pl.rubro == "tomate" else 3, key="k_cal_comb")
    if comb in PCI:
        pci = _n(a, "PCI (MJ/kg)", PCI[comb], 0.1, key=f"k_cal_pci_{comb}")
    else:
        pci = K.pci_humedo(_n(a, "PCI en base seca (MJ/kg)", 19.0, 0.1, key="k_cal_pcis"), _n(a, "Humedad (base húmeda)", 0.40, 0.01, key="k_cal_w"))
        a.caption(f"PCI en base húmeda: {_f(pci, 2)} MJ/kg")
    vap = _n(b, "Vapor producido (t/h)", v0, 0.5, key="k_cal_v")
    Ts = _n(b, "Temperatura del vapor saturado (°C)", Ts0, 1.0, "%.1f", key="k_cal_Ts")
    Tw = _n(b, "Agua de alimentación (°C)", 80.0, 1.0, "%.1f", key="k_cal_Tw")
    eta = _n(c, "Rendimiento de la caldera (PCI)", 0.85 if comb in PCI else 0.78, 0.01, key="k_cal_eta", help="0,80 a 0,90 con gas y 0,70 a 0,85 con biomasa (Van Loo y Koppejan, 2008)")
    precio = _n(c, "Precio del combustible ($ por GJ)", 0.0, 100.0, "%.0f", key="k_cal_precio")
    horas = _n(c, "Horas de operación al año", _horas_planta(pl), 100.0, "%.0f", key="k_cal_h")
    f_co2 = K.FACTOR_CO2_KG_TJ[comb]
    r = K.caldera(vap, Ts, Tw, eta, pci, precio, f_co2)
    x = st.columns(4)
    x[0].metric("Calor al vapor", _f(r["Q_kW"], 0) + " kW"); x[1].metric("Combustible", _f(r["combustible_kgh"], 0) + " kg/h")
    x[2].metric("Costo del vapor (combustible)", "$" + _f(r["costo_por_t_vapor"], 0) + " por t"); x[3].metric("Presión del vapor", _f(r["p_vapor_kPa"], 0) + " kPa")
    C.ayuda(f"Factor del combustible: {C.fmt(f_co2, 0)} kg CO2 por TJ (IPCC, 2006, Vol. 2, Cap. 2, Tabla 2.2). "   # PAT 134
            "El CO2 de la biomasa se informa aparte y no suma al total.", "Emisiones de CO2 (alcances 1 y 2)", 5)
    a, b = st.columns(2)
    kwh = _n(a, "Electricidad al año (MWh)", pl.servicio_total("electricidad_kW") * horas / 1000 if pl.resuelta else 0.0, 10.0, "%.0f", key="k_em_kwh")
    fr = _n(b, "Factor de emisión de la red (t CO2e por MWh)", K.FACTOR_RED_SEN, 0.01, "%.4f", key="k_em_red",   # PAT 133, mejora 11
            help=K.FUENTE_FACTOR_RED)
    e = K.emisiones(r["combustible_GJ_h"] * horas, f_co2, kwh * 1000, fr, biogenico=comb not in PCI)
    x = st.columns(3)
    x[0].metric("Alcance 1", _f(e["alcance1_t"], 0) + " t CO2/año"); x[1].metric("Alcance 2", _f(e["alcance2_t"], 0) + " t CO2/año")
    x[2].metric("CO2 biogénico (informativo)", _f(e["biogenico_t"], 0) + " t/año")
    _fuente("caldera")


def _secador(pl):
    s = _equipo(pl, "secador")
    d = s.resultado.detalle if s is not None else {}
    a, b = st.columns(2)
    m = _n(a, "Biomasa húmeda que entra (t/h)", d.get("carga_t_h") or 3.0, 0.1, key="k_sec_m")
    w0 = _n(a, "Humedad de entrada (base húmeda)", float((getattr(pl, "_p", None) or {}).get("M0", 0.50)), 0.01, key="k_sec_w0")
    w1 = _n(b, "Humedad de salida (base húmeda)", float(s.v("humedad_salida")) if s is not None and "humedad_salida" in s.params else 0.10, 0.01, key="k_sec_w1")
    q = _n(b, "Consumo específico (MJ por kg de agua)", d.get("consumo_MJ_kg_agua") or 3.2, 0.1, key="k_sec_q", help="2,8 a 4,0 en un tambor rotatorio (Mujumdar, 2014)")
    r = K.secador(m, w0, w1, q)
    x = st.columns(4)
    x[0].metric("Agua removida", _f(r["agua_t_h"], 3) + " t/h"); x[1].metric("Producto seco", _f(r["producto_t_h"], 3) + " t/h")
    x[2].metric("Calor de secado", _f(r["Q_kW"], 0) + " kW"); x[3].metric("Mínimo teórico (latente)", _f(r["Q_minimo_kW"], 0) + " kW")
    _fuente("secador")


def _letalidad(pl):
    w5 = pl.equipos.get("W5")
    T0 = float(w5.v("T_salida")) if w5 is not None and "T_salida" in w5.params else 110.0
    a, b, c = st.columns(3)
    T = _n(a, "Temperatura de mantención (°C)", T0, 0.5, "%.1f", key="k_let_T")
    tm = _n(a, "Tiempo de mantención (min)", 3.0, 0.5, "%.1f", key="k_let_t")
    Tr = _n(b, "Temperatura de referencia (°C)", 121.1, 0.1, "%.1f", key="k_let_Tr", help="121,1 °C y z = 10 °C dan el F0; en alimentos ácidos use la del microorganismo objetivo")
    z = _n(b, "Valor z (°C)", 10.0, 0.5, "%.1f", key="k_let_z")
    D = _n(c, "D a la referencia (min, opcional)", 0.0, 0.1, "%.2f", key="k_let_D")
    r = K.letalidad([(0.0, T), (tm, T)], Tr, z, D or None)
    x = st.columns(2)
    x[0].metric("Letalidad F", _f(r["F_min"], 3) + " min"); x[1].metric("Reducciones decimales", _f(r["reducciones"], 2))
    _fuente("letalidad")


def _tuberia(pl):
    a, b, c = st.columns(3)
    Q = _n(a, "Caudal (m³/h)", 50.0, 1.0, key="k_tub_Q"); D = _n(a, "Diámetro interno (mm)", 100.0, 5.0, "%.0f", key="k_tub_D")
    L = _n(a, "Largo equivalente (m)", 100.0, 10.0, "%.0f", key="k_tub_L"); dz = _n(b, "Altura a vencer (m)", 0.0, 1.0, "%.1f", key="k_tub_dz")
    rho = _n(b, "Densidad (kg/m³)", 1000.0, 10.0, "%.0f", key="k_tub_rho"); eta = _n(b, "Rendimiento de la bomba", 0.65, 0.01, key="k_tub_eta")
    pasta = c.checkbox("Fluido de ley de potencia (pasta de tomate)", value=False, key="k_tub_pasta")
    if pasta:
        Kc = _n(c, "Índice de consistencia K (Pa·sⁿ)", 15.0, 1.0, "%.1f", key="k_tub_K", help="10 a 20 en pasta de tomate (Steffe, 1996)")
        n = _n(c, "Índice de flujo n", 0.35, 0.01, key="k_tub_n"); mu = 0.001
    else:
        Kc = n = None; mu = _n(c, "Viscosidad (Pa·s)", 0.001, 0.0005, "%.4f", key="k_tub_mu")
    rug = _n(c, "Rugosidad (mm)", 0.045, 0.005, "%.3f", key="k_tub_rug")
    r = K.tuberia(Q, D, L, rho, mu, rug, Kc, n, eta, dz)
    x = st.columns(5)
    x[0].metric("Velocidad", _f(r["v"], 2) + " m/s"); x[1].metric("Reynolds", _f(r["Re"], 0), r["regimen"], delta_color="off")
    x[2].metric("Factor de fricción", _f(r["f"], 4)); x[3].metric("Pérdida de carga", _f(r["dp_kPa"], 1) + " kPa")
    x[4].metric("Potencia de la bomba", _f(r["potencia_kW"], 2) + " kW", f"altura {_f(r['H_m'], 1)} m", delta_color="off")
    _fuente("tuberia")
    _red_hidraulica(pl)


def _brix(pl):
    from . import s_brix                     # PAT 133, mejora 9
    s_brix.mostrar()


def _red_hidraulica(pl):
    from . import s_hidraulica               # PAT 133, mejora 8
    s_hidraulica.mostrar(pl)


def _costos(pl):
    a, b, c = st.columns(3)
    C1 = _n(a, "Costo conocido del equipo ($)", 1.2e6, 1e5, "%.0f", key="k_cos_C1"); S1 = _n(a, "Tamaño conocido", 20.0, 1.0, key="k_cos_S1")
    S2 = _n(a, "Tamaño nuevo", 40.0, 1.0, key="k_cos_S2")
    e = _n(b, "Exponente de escala", 0.6, 0.05, key="k_cos_n", help="0,6 por defecto, entre 0,4 y 0,8 según el equipo (Williams, 1947)")
    I1 = _n(b, "Índice CEPCI del costo conocido", 397.0, 1.0, "%.1f", key="k_cos_I1", help="397 corresponde a 2001, la base de Turton et al. (2018)")
    I2 = _n(b, "Índice CEPCI actual", K.CEPCI_ACTUAL, 1.0, "%.1f", key="k_cos_I2", help=K.FUENTE_CEPCI)
    tipo = c.selectbox("Tipo de planta (factor de Lang)", list(K.LANG), index=2, key="k_cos_lang")
    r = K.costo_escalado(C1, S1, S2, e, I1, I2, K.LANG[tipo])
    x = st.columns(3)
    x[0].metric("Equipo escalado", "$" + _f(r["equipo"], 0)); x[1].metric("Planta completa (Lang)", "$" + _f(r["planta"], 0), f"factor {_f(K.LANG[tipo], 2)}", delta_color="off")
    x[2].metric("Factores tamaño × índice", f"{_f(r['factor_tamano'], 3)} × {_f(r['factor_indice'], 3)}")
    _fuente("costos")


def _oee(pl):
    st.markdown("##### OEE (efectividad global del equipo)")
    a, b, c = st.columns(3)
    tp = _n(a, "Tiempo planificado (h)", 24.0, 1.0, "%.1f", key="k_oee_tp"); to = _n(a, "Tiempo operado (h)", 22.0, 0.5, "%.1f", key="k_oee_to")
    cap = _n(b, "Capacidad ideal (t/h)", 2.0, 0.1, key="k_oee_cap"); pr = _n(b, "Producido (t)", 38.0, 1.0, "%.1f", key="k_oee_pr")
    bu = _n(c, "Producto conforme (t)", 37.0, 1.0, "%.1f", key="k_oee_bu")
    r = K.oee(tp, to, cap, pr, bu)
    x = st.columns(4)
    x[0].metric("Disponibilidad", C.pct(r["disponibilidad"])); x[1].metric("Rendimiento", C.pct(r["rendimiento"]))
    x[2].metric("Calidad", C.pct(r["calidad"])); x[3].metric("OEE", C.pct(r["oee"]), "clase mundial 85 % (Nakajima, 1988)", delta_color="off")
    st.markdown("##### Variabilidad: espera ante el cuello de botella (Kingman) y ley de Little")
    u0 = 0.85
    try:
        from pat_sim.motor import lienzo as LZ
        tr = LZ.restricciones(pl, LZ.resolver_parcial(pl)[0]) if pl.resuelta else None
        if tr and tr.get("restrictivo"):
            u0 = min(0.99, tr["equipos"][tr["restrictivo"]]["util_demanda"]); st.caption(f"Utilización de partida: la del recurso crítico {tr['restrictivo']}")
    except Exception:
        pass
    a, b, c = st.columns(3)
    u = _n(a, "Utilización del equipo", u0, 0.01, "%.2f", key="k_kin_u", min_value=0.01, max_value=0.99)
    ca = _n(b, "Variabilidad de las llegadas (cv)", 1.0, 0.1, key="k_kin_ca"); cs = _n(b, "Variabilidad del proceso (cv)", 1.0, 0.1, key="k_kin_cs")
    te = _n(c, "Tiempo de proceso por lote (h)", 1.0, 0.1, key="k_kin_te"); lam = _n(c, "Llegadas por hora (lotes o t)", 1.0, 0.1, key="k_kin_lam")
    w = K.kingman(u, ca, cs, te)
    x = st.columns(2)
    x[0].metric("Espera en cola", _f(w, 2) + " h"); x[1].metric("Inventario en espera (Little)", _f(K.little(lam, w), 2))
    us = [0.5, 0.6, 0.7, 0.8, 0.85, 0.9, 0.95]
    st.line_chart(pd.DataFrame({"Utilización (%)": [100 * v for v in us], "Espera en cola (h)": [K.kingman(v, ca, cs, te) for v in us]}),
                  x="Utilización (%)", y_label="Espera en cola (h)")
    C.ayuda("Por eso no conviene cargar el recurso crítico al 100 %: la espera crece sin límite al acercarse a la capacidad.")   # PAT 134
    _fuente("oee")
