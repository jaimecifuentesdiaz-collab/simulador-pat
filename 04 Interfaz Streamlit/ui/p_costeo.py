"""Pantalla Costeo de la planta (PAT 135, tarea T7.1, 04-11-2026): lista completa de equipos con su precio (internet con
Tavily, último precio guardado o bibliografía), escalamiento de Williams, actualización con el CEPCI e inversión total que se
lleva a Economía. Indicación 1 del profesor Torres en la reunión del 04-11-2026. Motor: pat_sim/motor/costeo.py y
pat_sim/datos/precios_web.py."""
from __future__ import annotations
import streamlit as st
from pat_sim.motor import costeo as CT, costos
from pat_sim.datos import precios_web as PW
from . import comun as C


def _alternativa(pl):
    """PAT 135: la misma alternativa de recuperación que evalúa Economía (la elegida o la ganadora del multicriterio)."""
    try:
        from . import p_alternativas as PA
        r = C.resumen_actual()
        if r.get("sin_sumidero"):
            return None, None
        X = PA.alternativas_sesion(pl, r)
        return X, PA.elegida(X)
    except Exception:
        return None, None


def _tam(v, u, d=1):
    if v is None:
        return "—"
    if u == "mm":
        return f"DN {int(round(v))} ({CT.pulgadas(int(round(v)))}\")"
    return f"{C.fmt(v, d)} {u.replace('m2', 'm²')}"


def _ayuda():
    with st.expander("? Cómo se hace el costeo, para qué y por qué"):
        st.markdown(C.esc(
            "**Cómo.** La lista sale de la planta resuelta: equipos de la línea, recuperadores de calor de la alternativa que evalúa "
            "Economía, caldera o generador a biomasa, una bomba por línea de líquido (potencia de la red hidráulica), una válvula por "
            "lazo de control (Cv por ISA-75.01) y las cañerías por diámetro nominal (largo del layout o 30 m por línea, Supuesto). "
            "El precio viene de internet (Tavily), del último precio guardado o de una correlación de bibliografía. Si el tamaño "
            "encontrado no es el requerido se escala con Williams, C2 = C1·(S2/S1)^n, y si el precio es de otro año se actualiza "
            "con el CEPCI, C = C_año·(CEPCI_hoy/CEPCI_año). La planta instalada es el costo de los equipos por el factor "
            f"{C.fmt(costos.F_INSTALACION, 1)} de motor/costos.py.\n\n"
            "**Para qué.** Es la inversión que entra a la evaluación económica (VAN y TIR).\n\n"
            "**Por qué.** Los precios de equipos industriales casi nunca se publican: se combina lo que hay en internet con "
            "bibliografía, se deja la fuente, la fecha y la URL de cada cifra y se marca su origen. Las referencias marcadas "
            "Supuesto son órdenes de magnitud que se reemplazan con la búsqueda o con el PDF «estimación de costo de planta» del profesor."))


def mostrar():
    ss = st.session_state; pl = C.planta(); E = ss.economia
    st.subheader("Costeo de la planta")
    _ayuda()
    if not C.exigir_resuelta():
        return
    P = ss.setdefault("costeo_param", dict(cepci=CT.CEPCI_HOY, anio=CT.ANIO_CEPCI_HOY))
    with st.form("cst_form"):
        a, b, c = st.columns(3)
        cepci = a.number_input("CEPCI actual", 100.0, 5000.0, float(P["cepci"]), 0.1, key="cst_cepci",
                               help=C.esc(f"Por defecto 797,9, promedio anual 2023 ({CT.FUENTE_CEPCI_ANUAL}). El promedio 2025 subió 1,6 % "
                                          "sobre el de 2024 (Chemical Engineering, 02-04-2026), pero su valor solo se publica con suscripción."))
        anio = b.number_input("Año del CEPCI", 2000, 2100, int(P["anio"]), 1, key="cst_anio")
        dolar = c.number_input(C.esc("Dólar observado ($/US$)"), 1.0, 5000.0, float(E["dolar"]), 1.0, key="cst_dolar", help=C.FUENTE_DOLAR)
        if st.form_submit_button("Aplicar", type="primary"):
            P.update(cepci=float(cepci), anio=int(anio)); E["dolar"] = float(dolar)
    clave = PW.obtener_clave()
    buscar = st.button("Buscar precios en internet", key="cst_buscar", disabled=not clave,
                       help="Una búsqueda de Tavily por equipo (plan gratuito: 1.000 al mes). Cada precio queda guardado en la base con su fecha.")
    if not clave:
        st.caption("Sin clave de Tavily: se usan los precios guardados y la bibliografía. La clave va en `.streamlit/secrets.toml` "
                   "(TAVILY_API_KEY) o en la variable de entorno TAVILY_API_KEY.")
    X, k_alt = _alternativa(pl)
    lay = ss.get("layout") or {}
    longitudes = lay.get("longitudes_m") if isinstance(lay, dict) else None
    cables_m = lay.get("cables_m") if isinstance(lay, dict) else None   # PAT 135, T14: red eléctrica del layout (equipo S)
    try:
        bd = C.obtener_bd()
    except Exception:
        bd = None
    try:
        res = CT.costear(pl, cepci_hoy=float(P["cepci"]), anio_cepci=int(P["anio"]), dolar=float(E["dolar"]), bd=bd,
                         buscar=bool(buscar and clave), clave=clave, longitudes=longitudes, alternativa=k_alt, X=X,
                         cables_m=cables_m if isinstance(cables_m, dict) else None)
    except Exception as e:                    # el costeo nunca debe botar la aplicación
        st.error(f"No se pudo costear la planta: {e}")
        return
    t = res["totales"]
    ss["costeo"] = {"total_clp": t["total_clp"], "filas": res["filas"], "totales": t}
    if k_alt:
        st.caption(f"Recuperadores de la alternativa {k_alt}, la que evalúa Economía (se cambia en Alternativas).")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Equipos", C.esc("$" + C.fmt(t["equipos_clp"] / 1e6, 1) + " MM"), f"US$ {C.fmt(t['equipos_usd'] / 1e6, 2)} MM", delta_color="off")
    m2.metric(f"Instalación (factor {C.fmt(t['f_inst'], 1)})", C.esc("$" + C.fmt(t["instalacion_clp"] / 1e6, 1) + " MM"))
    m3.metric("Total planta", C.esc("$" + C.fmt(t["total_clp"] / 1e6, 1) + " MM"), f"US$ {C.fmt(t['total_usd'] / 1e6, 2)} MM", delta_color="off")
    m4.metric("Origen de los precios", f"{res['n_internet']} de internet", f"{res['n_bibliografia']} de bibliografía", delta_color="off")
    filas = [dict(f, nombre_txt=f"{f['equipo']} · {f['nombre']}", req=_tam(f["tamano"], f["unidad"]) + (f" × {C.fmt(f['cantidad'], 0)} m" if f["unidad"] in ("mm", "mm2") else "")
                  + (f" × {f['unidades']} unidades" if f.get("unidades") else ""),   # PAT 135, T14: unidades en paralelo
                  ref=_tam(f["tamano_ref"], f["unidad"]), anio_txt=str(f["anio"] or "—"), url_txt=f["url"] or "—") for f in res["filas"]]
    C.mostrar_tabla(filas, [("nombre_txt", "Equipo", "txt", 0), ("tipo", "Tipo", "txt", 0), ("req", "Tamaño requerido", "cen", 0),
                            ("ref", "Tamaño de referencia", "cen", 0), ("precio_ref_usd", "Precio de referencia (US$)", "clp", 0),
                            ("anio_txt", "Año", "cen", 0), ("n", "Williams n", "num", 2), ("factor_cepci", "Factor CEPCI", "num", 3),
                            ("costo_usd", "Costo actualizado (US$)", "clp", 0), ("costo_clp", "Costo actualizado ($)", "clp", 0),
                            ("fuente", "Fuente", "txt", 0), ("fecha", "Fecha", "txt", 0), ("url_txt", "URL", "txt", 0), ("origen", "Origen", "txt", 0)])
    notas = [f"{f['equipo']}: {f['nota']}" for f in res["filas"] if f.get("nota")] + res["avisos"]
    if notas:
        with st.expander(f"Notas y supuestos de cada fila ({len(notas)})"):
            st.markdown(C.esc("\n".join(f"- {n}" for n in notas)))
    st.markdown("#### Llevar a Economía")
    que = st.radio("Inversión que se lleva", ["Planta completa", "Solo recuperación de calor"], horizontal=True, key="cst_que",
                   help="Economía evalúa el ahorro de la recuperación de calor: para ese VAN corresponde la inversión de los recuperadores.")
    total = t["total_clp"] if que == "Planta completa" else t["recuperacion_clp"]
    st.caption(C.esc(f"Se escribirá ${C.fmt(total / 1e6, 1)} MM como inversión (MM$) y se desmarcará «Usar la inversión estimada de la alternativa evaluada»."))
    if st.button("Llevar a Economía", key="cst_llevar", type="primary"):
        E["inversion"] = round(total / 1e6, 1); E["inv_auto"] = False
        ss["eco_inv_auto"] = False; ss["eco_inv_auto_b"] = False      # las casillas de Economía muestran lo mismo
        ss["costeo"]["llevado_mmclp"] = E["inversion"]
        st.success(C.esc(f"Inversión de ${C.fmt(E['inversion'], 1)} MM llevada a Economía."))
