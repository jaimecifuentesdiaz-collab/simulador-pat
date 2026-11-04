"""Sección «Ajuste de distribuciones (como ExpertFit)» de la pestaña Datos de entrada (PAT 134).

Como ExpertFit de FlexSim: se entregan datos medidos, se ajustan siete distribuciones por máxima verosimilitud, se ordenan
por la calidad del ajuste (chi-cuadrado, Kolmogorov-Smirnov y Anderson-Darling; Law, 2015, cap. 6), se compara el histograma
con la densidad y la elegida se usa en Temporada (tiempo de descarga de un camión) u Operación (duración de las fallas).
El motor está en pat_sim/motor/ajuste.py; la elegida queda en st.session_state.distribuciones["descarga_h" | "falla_h"]."""
from __future__ import annotations
import base64
import streamlit as st
from pat_sim.motor import ajuste as AJ
from . import comun as C
from . import ayudas_tablas as AT   # PAT 134: «?» de cada tabla

FUENTES = {"ejemplo": "Serie de ejemplo del rubro (Supuesto)", "pegar": "Pegar valores", "csv": "Subir un CSV",
           "medidos": "Datos medidos (Excel de ida y vuelta)"}
DESTINO = {"descarga_h": "Temporada (tiempo de descarga)", "falla_h": "Operación (duración de fallas)"}


def _img(svg: str) -> str:
    return ('<img alt="Histograma con la distribución ajustada" style="width:100%;height:auto" src="data:image/svg+xml;base64,'
            + base64.b64encode(svg.encode("utf-8")).decode("ascii") + '">')


def _datos(pl) -> tuple:
    """Fuente elegida: (valores, nombre de la serie, nota, serie sugerida para el destino)."""
    ss = st.session_state; medidos = ss.get("datos_medidos") or {}
    fuentes = [k for k in FUENTES if k != "medidos" or medidos]
    a, b = st.columns([2, 3])
    fu = a.radio("Fuente de los datos", fuentes, format_func=FUENTES.get, key="aj_fuente",
                 index=fuentes.index("medidos") if medidos and "aj_fuente" not in ss else 0)
    if fu == "ejemplo":
        se = b.selectbox("Serie de ejemplo", list(AJ.SERIES), format_func=AJ.SERIES.get, key="aj_serie_ej")
        ej = AJ.ejemplo(pl.rubro, se)
        return ej["valores"], AJ.SERIES[se], "Supuesto: " + ej["supuesto"].justificacion, se
    if fu == "pegar":
        tx = b.text_area("Valores (uno por línea o separados por punto y coma o tabulación; coma decimal)", key="aj_texto", height=150,
                         help="Se puede pegar una columna copiada desde Excel.")
        return (AJ.leer_valores(tx) if tx and tx.strip() else None), "Valores pegados", "", None
    if fu == "csv":
        f = b.file_uploader("Archivo CSV (separador punto y coma, tabulación o coma)", type=["csv", "txt"], key="aj_csv")
        if f is None:
            return None, "CSV", "", None
        crudo = f.getvalue()
        try:
            tx = crudo.decode("utf-8-sig")
        except UnicodeDecodeError:
            tx = crudo.decode("latin-1")
        cols = AJ.leer_csv(tx)
        col = b.selectbox("Columna", list(cols), key="aj_col")
        return cols[col], f"{f.name}, columna {col}", "", None
    se = b.selectbox("Serie medida", list(medidos), key="aj_serie_med")
    return [float(v) for v in medidos[se]], se, "Datos medidos cargados en la sesión", None


def _usadas():
    ss = st.session_state; dists = ss.setdefault("distribuciones", {})
    for clave, nombre in DESTINO.items():
        d = dists.get(clave)
        if not d:
            continue
        a, b = st.columns([5, 1])
        a.markdown(f"En uso en {nombre}: `{d['expresion']}` (media {C.fmt(d['media'], 3)} h, desviación {C.fmt(d['desviacion'], 3)} h; "
                   f"{C.esc(str(d.get('origen', 'sin origen')))}).")
        if b.button("Quitar", key=f"aj_quitar_{clave}", width="stretch"):
            dists.pop(clave, None); st.rerun()


def mostrar():
    pl = C.planta(); ss = st.session_state
    ss.setdefault("distribuciones", {})
    C.ayuda("Se ajustan siete distribuciones por máxima verosimilitud y se ordenan por la prueba de Anderson-Darling; se comparan con "   # PAT 134: ayuda «?»
            "chi-cuadrado (intervalos equiprobables) y Kolmogorov-Smirnov, al 5 % y al 10 % (Law, 2015, cap. 6). Si ninguna pasa, se "
            "propone la empírica lineal por tramos.", "Ajuste de distribuciones (como ExpertFit)", 5)
    _usadas()
    try:
        valores, serie, nota, sugerida = _datos(pl)
    except ValueError as e:
        st.warning(f"No se pudieron leer los datos: {e}"); return
    if not valores:
        st.info("Ingrese los valores medidos para ajustar las distribuciones."); return
    try:
        r = AJ.ajustar(valores)
    except ValueError as e:
        st.warning(f"No se puede ajustar: {e}"); return
    if nota:
        C.ayuda(C.esc(nota))   # PAT 134
    rs = r["resumen"]
    m = st.columns(4)
    m[0].metric("Datos", C.fmt(rs["n"], 0))
    m[1].metric("Media", C.fmt(rs["media"], 3), "desviación " + C.fmt(rs["desviacion"], 3), delta_color="off")
    m[2].metric("Mínimo y máximo", f"{C.fmt(rs['minimo'], 3)} a {C.fmt(rs['maximo'], 3)}")
    m[3].metric("Mejor ajuste", r["mejor"]["etiqueta"], r["mejor"]["expresion"], delta_color="off")
    for a in r["avisos"]:
        st.warning(a)
    si = lambda v: "Sí" if v else "No"
    filas = [dict(x, chi=x["chi2"]["estadistico"], ks=x["ks"]["estadistico"], ad=x["ad"]["estadistico"], p5=si(x["pasa_5"]), p10=si(x["pasa_10"]))
             for x in r["lista"]]
    AT.tabla("aj_tabla", "Distribuciones ajustadas")   # PAT 134: «?» de la tabla
    C.mostrar_tabla(filas, [("rango", "Lugar", "num", 0), ("etiqueta", "Distribución", "txt", 0), ("parametros", "Parámetros", "txt", 0),
                            ("expresion", "Expresión (FlexSim)", "txt", 0), ("chi", f"Chi-cuadrado (k = {r['k_chi2']})", "num", 2),
                            ("ks", "Kolmogorov-Smirnov (D)", "num", 4), ("ad", "Anderson-Darling (A²)", "num", 3),
                            ("p5", "Pasa al 5 %", "txt", 0), ("p10", "Pasa al 10 %", "txt", 0)])
    x0 = r["lista"][0] if r["lista"] else None
    if x0:
        C.ayuda(C.esc(f"{r['criterio']} Valores críticos al 5 %: chi-cuadrado {C.fmt(x0['chi2']['critico_5'], 2)} con {x0['chi2']['gl']} grados "   # PAT 134
                      f"de libertad; K-S ajustado {C.fmt(AJ.KS_CRITICO[0.05], 3)} y A² {C.fmt(AJ.AD_CRITICO[0.05], 3)}. {r['nota']}"))
    opciones = [x["nombre"] for x in r["lista"]] + ["empirica"]
    por_nombre = {x["nombre"]: x["dist"] for x in r["lista"]}; por_nombre["empirica"] = r["empirica"]
    if ss.get("aj_dist") not in opciones:          # la distribución elegida antes no se ajustó con estos datos
        ss.pop("aj_dist", None)
    a, b = st.columns([2, 1])
    elegida = a.selectbox("Distribución para el gráfico y la simulación", opciones, index=opciones.index(r["mejor"]["nombre"]),
                          format_func=lambda n: AJ.ETIQUETA[n] + (" (recomendada)" if n == r["mejor"]["nombre"] else ""), key="aj_dist")
    k = b.number_input("Clases del histograma", 3, 60, AJ.histograma(valores)["k"], 1, key="aj_k")
    d = por_nombre.get(elegida, r["mejor"])
    st.html(_img(AJ.grafico_svg(valores, d, int(k), titulo=f"{serie}: histograma y {d['etiqueta'].lower()}")))
    st.markdown(f"Expresión para FlexSim: `{d['expresion']}`; media {C.fmt(AJ.media(d), 3)} y desviación {C.fmt(AJ.desviacion(d), 3)}.")
    C.ayuda((C.esc(d["nota"]) + "\n\n" if d.get("nota") else "")   # PAT 134
            + "Los valores deben estar en horas: el tiempo de descarga es el de un camión con la carga media de la pestaña Temporada "
            "y la duración de falla es la detención correctiva dentro de un turno de 8 h.")
    if sugerida:
        st.caption(f"Esta serie de ejemplo corresponde a {DESTINO[sugerida]}.")
    guardar = dict(d, origen=f"{serie}, {len(valores)} datos, rubro {pl.rubro}", rubro=pl.rubro)
    c1, c2 = st.columns(2)
    if c1.button("Usar en Temporada (tiempo de descarga)", key="aj_usar_descarga", width="stretch", type="primary" if sugerida == "descarga_h" else "secondary"):
        ss.distribuciones["descarga_h"] = guardar; st.rerun()
    if c2.button("Usar en Operación (duración de fallas)", key="aj_usar_falla", width="stretch", type="primary" if sugerida == "falla_h" else "secondary"):
        ss.distribuciones["falla_h"] = guardar; st.rerun()
    with st.expander("Supuestos del ajuste"):
        AT.tabla("aj_supuestos", "Supuestos")   # PAT 134: «?» de la tabla
        C.mostrar_tabla([dict(n=s.nombre, j=s.justificacion) for s in AJ.SUPUESTOS],
                        [("n", "Supuesto", "txt", 0), ("j", "Justificación", "txt", 0)])
