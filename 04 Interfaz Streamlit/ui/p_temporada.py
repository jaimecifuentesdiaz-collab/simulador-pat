"""Pestaña Temporada (PAT 133, mejoras 6 y 7): llegada de materia prima por día, cola de camiones en el patio frente a la
capacidad de recepción (simulación de eventos discretos, Kingman y ley de Little) y programa de producción de la temporada
(Gantt) con arranque, limpiezas, paradas programadas y parada final. Funciona en los cuatro rubros."""
from __future__ import annotations
import pandas as pd
import streamlit as st
from pat_sim.motor import temporada as TM
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

MATERIA = {"tomate": "tomate", "pellet": "aserrín", "chip": "rollizos", "lena": "trozas"}
BASES = {"recepcion": "Primer equipo de la línea (capacidad de partida)", "linea": "Recurso crítico de la línea"}


def _parametros(pl) -> dict:
    """Formulario de parámetros; los valores quedan en st.session_state.temporada, uno por rubro."""
    ss = st.session_state; sp = TM.supuestos(pl); todos = ss.setdefault("temporada", {})
    P = todos.get(pl.rubro)
    if P is None:
        P = todos[pl.rubro] = dict(semilla=1, camion=sp["camion"], cv=sp["cv_servicio"], umbral=sp["umbral"], tasa=100 * sp["tasa"],
                                   base="recepcion", con_programa=True, arranque=sp["arranque"], cip_cada=sp["cip_cada"], cip_dur=sp["cip_dur"],
                                   parada_cada=sp["parada_cada"], parada_dur=sp["parada_dur"], parada_final=sp["parada_final"],
                                   pico=sp.get("pico", 0.5), ancho=sp.get("ancho", 0.25))
    tom = pl.rubro == "tomate"
    with st.form(f"tem_form_{pl.rubro}"):
        st.markdown("##### Llegada de materia prima y recepción")
        a, b, c, d = st.columns(4)
        sem = a.number_input("Semilla", 0, 10 ** 6, int(P["semilla"]), 1, key=f"tem_sem_{pl.rubro}",
                             help="La misma semilla entrega la misma temporada (random.Random(semilla)).")
        cam = b.number_input(f"Carga de un camión de {MATERIA.get(pl.rubro, 'materia prima')} (t)", 1.0, 60.0, float(P["camion"]), 1.0,
                             key=f"tem_cam_{pl.rubro}")
        cv = c.number_input("Variación de la descarga (coeficiente de variación)", 0.0, 2.0, float(P["cv"]), 0.05, key=f"tem_cv_{pl.rubro}")
        base = d.selectbox("Capacidad de recepción", list(BASES), index=list(BASES).index(P["base"]), format_func=BASES.get, key=f"tem_base_{pl.rubro}")
        if tom:
            a, b, c, d = st.columns(4)
            pico = a.number_input("Peak de cosecha (fracción de la temporada)", 0.0, 1.0, float(P["pico"]), 0.05, key="tem_pico")
            ancho = b.number_input("Ancho de la campana (fracción de la temporada)", 0.05, 2.0, float(P["ancho"]), 0.05, key="tem_ancho")
            umbral = c.number_input("Espera sin pérdida (h)", 0.0, 72.0, float(P["umbral"]), 1.0, key="tem_umbral")
            tasa = d.number_input("Pérdida sobre esa espera (% por h)", 0.0, 10.0, float(P["tasa"]), 0.05, format="%.3f", key="tem_tasa")
        else:
            pico, ancho, umbral, tasa = P["pico"], P["ancho"], P["umbral"], P["tasa"]
        st.markdown("##### Programa de producción")
        a, b, c, d = st.columns(4)
        arr = a.number_input("Arranque (h)", 0.0, 240.0, float(P["arranque"]), 1.0, key=f"tem_arr_{pl.rubro}")
        cc = b.number_input("Limpieza cada (h de producción)", 0.0, 2000.0, float(P["cip_cada"]), 12.0, key=f"tem_cc_{pl.rubro}",
                            help="Con 0 no se programan limpiezas.")
        cd = c.number_input("Duración de la limpieza (h)", 0.0, 48.0, float(P["cip_dur"]), 1.0, key=f"tem_cd_{pl.rubro}")
        pf = d.number_input("Parada final (h)", 0.0, 240.0, float(P["parada_final"]), 1.0, key=f"tem_pf_{pl.rubro}")
        a, b, c = st.columns(3)
        pc = a.number_input("Parada programada cada (días)", 0.0, 366.0, float(P["parada_cada"]), 1.0, key=f"tem_pc_{pl.rubro}",
                            help="Con 0 no se programan paradas.")
        pd_ = b.number_input("Duración de la parada programada (h)", 0.0, 240.0, float(P["parada_dur"]), 1.0, key=f"tem_pd_{pl.rubro}")
        cp = c.checkbox("La recepción solo atiende en las horas de producción del programa", value=bool(P["con_programa"]), key=f"tem_cp_{pl.rubro}")
        if st.form_submit_button("Simular la temporada", type="primary"):
            P.update(semilla=int(sem), camion=cam, cv=cv, base=base, pico=pico, ancho=ancho, umbral=umbral, tasa=tasa, arranque=arr,
                     cip_cada=cc, cip_dur=cd, parada_final=pf, parada_cada=pc, parada_dur=pd_, con_programa=cp)
    return P


def mostrar():
    pl = C.planta()
    st.subheader("Temporada: llegada de materia prima y programa de producción")
    if not C.exigir_resuelta():
        return
    P = _parametros(pl)
    try:
        r = C.resumen_actual()
    except Exception:
        r = None
    try:
        pr = TM.programa_temporada(pl, arranque_h=P["arranque"], cip_cada_h=P["cip_cada"], cip_duracion_h=P["cip_dur"],
                                   parada_cada_d=P["parada_cada"], parada_duracion_h=P["parada_dur"], parada_final_h=P["parada_final"], resumen=r)
        ll = TM.llegadas_temporada(pl, semilla=P["semilla"], camion_t=P["camion"], cv_servicio=P["cv"], pico=P["pico"], ancho=P["ancho"],
                                   umbral_h=P["umbral"], tasa_h=P["tasa"] / 100, base=P["base"], programa=pr if P["con_programa"] else None,
                                   dist_descarga=st.session_state.get("distribuciones", {}).get("descarga_h"))
    except ValueError as e:
        st.warning(f"No se pudo simular la temporada: {e}")
        return
    _dd = st.session_state.get("distribuciones", {}).get("descarga_h")
    if _dd:                                      # PAT 134: tiempo de descarga ajustado en Datos de entrada
        st.info(C.esc(f"Tiempo de descarga con la distribución ajustada `{_dd['expresion']}` ({_dd.get('origen', 'Datos de entrada')}): "
                      "reemplaza la variación de la descarga y la capacidad de recepción del formulario. Se quita en Datos de entrada."))
    for a in ll["avisos"]:
        st.warning(a)

    C.ayuda(C.esc(f"Capacidad: {ll['origen_capacidad']}. Simulación de eventos discretos con random.Random({P['semilla']}): cada camión "   # PAT 134: ayuda «?»
                  "llega al azar dentro de las horas de operación y se descarga en orden de llegada. Kingman (Hopp y Spearman, 2008) y "
                  "Little (1961), como la calculadora de la pestaña Calculadoras."), "Cola de camiones en el patio")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Camiones de la temporada", C.fmt(ll["camiones"], 0), f"{C.fmt(ll['carga_camion_t'], 1)} t cada uno", delta_color="off")
    m2.metric("Capacidad de recepción", C.fmt(ll["capacidad_t_h"], 1) + " t/h", "utilización media " + C.pct(ll["utilizacion_media"]), delta_color="off")
    m3.metric("Espera media simulada", C.fmt(ll["espera_media_h"], 2) + " h", "máxima " + C.fmt(ll["espera_max_h"], 1) + " h", delta_color="off")
    m4.metric("Espera media de Kingman", "—" if ll["espera_kingman_h"] is None else C.fmt(ll["espera_kingman_h"], 2) + " h",
              "ca = 1; cs = " + C.fmt(ll["parametros"]["cv_servicio"], 2), delta_color="off")
    n1, n2, n3, n4 = st.columns(4)
    L = ll["little"]
    n1.metric("Camiones en espera (L)", C.fmt(L["L_integrada"], 2), "promedio de la temporada", delta_color="off")
    n2.metric("λ·W (ley de Little)", C.fmt(L["L_little"], 2), f"λ = {C.fmt(L['lambda_por_h'], 2)} camiones/h", delta_color="off")
    n3.metric("Materia prima degradada", C.fmt(ll["total_degradado_t"], 1) + " t",
              C.pct(ll["total_degradado_t"] / ll["total_llegada_t"] if ll["total_llegada_t"] else 0, 2) + " de lo que llega", delta_color="off")
    n4.metric("En el patio al cierre", C.fmt(max(0.0, ll["cola_final_t"]), 1) + " t", delta_color="off")

    D = ll["dias"]
    df = pd.DataFrame([dict(dia=x["dia"], **{"Llegada (t)": x["llegada_t"], "Procesado (t)": x["procesado_t"], "En cola al cierre del día (t)": x["cola_t"]})
                       for x in D]).set_index("dia")
    st.line_chart(df, x_label="Día de la temporada", y_label="Materia prima (t)")
    dq = pd.DataFrame([dict(dia=x["dia"], **{"Camiones en espera, promedio": x["camiones_espera_prom"], "Camiones en espera, máximo": x["camiones_espera_max"]})
                       for x in D]).set_index("dia")
    st.line_chart(dq, x_label="Día de la temporada", y_label="Camiones")

    with st.expander("Tabla por día"):
        paso = 1 if len(D) <= 90 else 7
        filas = [x for x in D if (x["dia"] - 1) % paso == 0 or x["dia"] == len(D)]
        AT.tabla("tem_dia", "Llegadas, cola y espera por día")   # PAT 134: «?» de la tabla
        C.mostrar_tabla(filas, [("dia", "Día", "num", 0), ("camiones", "Camiones", "num", 0), ("llegada_t", "Llegada (t)", "num", 1),
                                ("procesado_t", "Procesado (t)", "num", 1), ("cola_t", "En cola (t)", "num", 1), ("degradado_t", "Degradado (t)", "num", 2),
                                ("camiones_espera_prom", "Camiones en espera, promedio", "num", 2), ("camiones_espera_max", "Camiones en espera, máximo", "num", 0),
                                ("espera_media_h", "Espera media (h)", "num", 2), ("kingman_h", "Kingman (h)", "num", 2)])
        if paso > 1:
            st.caption("Se muestra un día de cada siete; los gráficos tienen todos los días.")

    st.markdown("#### Programa de producción")
    h = pr["horas_por_tipo"]
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("Horas efectivas", C.fmt(pr["horas_efectivas"], 0) + " h", "de " + C.fmt(pr["horas_diseno"], 0) + " h de diseño", delta_color="off")
    k2.metric("Disponibilidad del programa", C.pct(pr["disponibilidad"]), delta_color="off")
    k3.metric("Producción de la temporada", "—" if pr["produccion_programa_t"] is None else C.fmt(pr["produccion_programa_t"], 0) + " t",
              None if pr["produccion_perdida_t"] is None else "−" + C.fmt(pr["produccion_perdida_t"], 0) + " t frente al diseño", delta_color="off")
    k4.metric("Calor recuperable perdido en las paradas", C.fmt(pr["calor_no_recuperado_MWh"], 0) + " MWh",
              "cascada de " + C.fmt(pr["cascada_kW"], 0) + " kW", delta_color="off")
    if not pr["alcanza"] and pr["capacidad_linea_t_h"]:
        st.warning(f"Con {C.fmt(pr['horas_efectivas'], 0)} h efectivas la línea tendría que recibir {C.fmt(pr['ritmo_necesario_t_h'], 1)} t/h, "
                   f"sobre su capacidad de {C.fmt(pr['capacidad_linea_t_h'], 1)} t/h: quedan "
                   f"{C.fmt(pr['produccion_no_alcanzada_t'] or 0, 0)} t de producto sin hacer o hay que alargar la temporada.")
    st.html(TM.svg_como_img(TM.gantt_svg(pr)))
    cnr = pr["calor_no_recuperado_por_tipo_MWh"]
    filas = [dict(t=TM.NOMBRE_TIPO[k], n=sum(1 for b in pr["barras"] if b["tipo"] == k), h=h[k], q=cnr.get(k)) for k, _n, _c in TM.TIPOS if h[k] > 0]
    AT.tabla("tem_programa", "Horas y calor no aprovechado por actividad")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("t", "Actividad", "txt", 0), ("n", "Barras", "num", 0), ("h", "Horas", "num", 0), ("q", "Calor recuperable no aprovechado (MWh)", "num", 0)])
    comb = pr["combustible_no_evitado"]
    if comb.get("combustible") == "gas":
        st.caption(f"En las horas detenidas la cascada no evita {C.fmt(comb['MMBtu'], 0)} MMBtu de gas natural ({C.fmt(comb['co2_t'], 0)} t de CO2), "
                   "proporcional a las horas de la temporada.")
    elif comb.get("combustible") == "biomasa":
        st.caption(f"En las horas detenidas la cascada no desplaza {C.fmt(comb['t'], 0)} t de biomasa combustible ({C.fmt(comb['m3'], 0)} m³ estéreo).")
    with st.expander("Supuestos de la temporada"):
        AT.tabla("tem_supuestos", "Supuestos")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=s.nombre, v=s.valor, u=s.unidad, j=s.justificacion) for s in TM.SUPUESTOS.get(pl.rubro, TM.SUPUESTOS["pellet"])],
                        [("n", "Supuesto", "txt", 0), ("v", "Valor", "num", 3), ("u", "Unidad", "txt", 0), ("j", "Justificación", "txt", 0)])
