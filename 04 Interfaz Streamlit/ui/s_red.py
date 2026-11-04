"""Sección Red de intercambiadores desde el pinch (PAT 133, mejora 3). Va en la pestaña Recuperación de calor, después de
la sección Pinch: ui/p_calor.py llama s_red.mostrar(pl, r) con la planta y el resumen de la sesión."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import red_intercambio as RI
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla


def _tramo(a) -> str:
    rama = "" if a["rama"] is None else f" (rama de {C.pct(a['fraccion'], 0)} del flujo)"
    return f"{C.fmt(a['Tc_in'], 1)} → {C.fmt(a['Tc_out'], 1)} °C{rama}"


def mostrar(pl, r):
    st.markdown("#### Red de intercambiadores desde el *pinch*")
    if r.get("sin_sumidero"):
        return
    try:
        red = RI.disenar_red_planta(pl, r)
    except Exception as e:          # la red no debe botar la pestaña
        st.warning(f"No se pudo diseñar la red de intercambiadores: {e}")
        return
    if red is None:
        return
    s = red["sumidero"]
    C.ayuda(f"Se divide el problema en el *pinch* ({C.fmt(red['T_pinch_caliente'], 2)} °C del lado caliente y "   # PAT 134: ayuda «?»
            f"{C.fmt(red['T_pinch_fria'], 2)} °C del lado frío) y se diseña cada lado desde el *pinch* hacia afuera: sin "
            f"transferir calor a través del *pinch*, con la regla de CP en los apareamientos que lo tocan (el sumidero "
            f"{C.esc(s['nombre'])} se divide en ramas en paralelo cuando hace falta) y con el *tick-off*, que hace cada "
            "intercambiador tan grande como se pueda.")
    m1, m2, m3, m4 = st.columns(4)
    eq = red["equipos"]; eu = red["euler"]
    m1.metric("Calor recuperado por la red", C.fmt(red["Q_recuperado"], 1) + " kW",
              ("alcanza el objetivo" if red["alcanza_objetivo"] else "bajo el objetivo") + f" de {C.fmt(red['objetivo_kW'], 1)} kW", delta_color="off")
    m2.metric("Equipos de la red", C.fmt(eq["total"], 0),
              f"{eq['recuperacion']} de recuperación, {eq['calentadores']} de servicio caliente y {eq['enfriadores']} de servicio frío", delta_color="off")
    m3.metric("Mínimo de Euler (por lado del *pinch*)", C.fmt(eu["total"], 0), f"{eu['arriba']} arriba y {eu['abajo']} abajo", delta_color="off")
    m4.metric("Área total de recuperación", C.fmt(red["area_total_m2"], 1) + " m²", "con U de partida", delta_color="off")

    filas = [dict(id=a["id"], lado="Arriba" if a["lado"] == "arriba" else "Abajo", n=a["corriente"], tipo=a["tipo"].capitalize(),
                  tramo=_tramo(a), Q=a["Q_kW"], Th=f"{C.fmt(a['Th_in'], 1)} → {C.fmt(a['Th_out'], 1)}",
                  LMTD=a["LMTD"], U=a["U"], A=a["A_m2"]) for a in red["apareamientos"]]
    AT.tabla("cal_red", "Intercambiadores de la red")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("id", "Equipo", "txt", 0), ("lado", "Lado", "txt", 0), ("n", "Corriente caliente", "txt", 0),
                            ("tipo", "Tipo", "txt", 0), ("tramo", "Tramo del sumidero", "txt", 0), ("Q", "Calor (kW)", "num", 1),
                            ("Th", "Caliente entra → sale (°C)", "cen", 0), ("LMTD", "LMTD (°C)", "num", 2),
                            ("U", "U (W/m²K)", "num", 0), ("A", "Área (m²)", "num", 1)])
    sc = "; ".join(f"{C.fmt(c['Q_kW'], 1)} kW de {C.fmt(c['Tc_in'], 1)} a {C.fmt(c['Tc_out'], 1)} °C" for c in red["calentadores"]) or "ninguno"
    sf = ", ".join(f"{e['corriente']} ({C.fmt(e['Q_kW'], 1)} kW)" for e in red["enfriadores"]) or "ninguno"
    st.markdown(f"Servicio caliente que queda (caldera o generador): **{C.fmt(red['servicio_caliente_kW'], 1)} kW** ({sc}). "
                f"Calor residual que no se usa (servicio frío): **{C.fmt(red['servicio_frio_kW'], 1)} kW**: {C.esc(sf)}.")
    C.ayuda(f"El mínimo de Euler cuenta corrientes más servicios menos uno en cada lado del *pinch*; sin dividir en el "   # PAT 134
            f"*pinch* serían {red['euler_sin_dividir']} equipos, pero esa red no alcanzaría el objetivo. "
            "Si la red tiene más equipos que el mínimo, hay lazos que se pueden romper a cambio de algo de calor.")
    for a in red["avisos"]:
        st.warning(a)
    st.html('<div class="contenedor-svg">' + RI.diagrama_rejilla_svg(red) + "</div>")
    C.ayuda(" ".join(RI.FUENTES) + " Área en contracorriente pura, sin factor de corrección F ni ensuciamiento.")   # PAT 134
