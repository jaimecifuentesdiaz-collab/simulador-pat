"""Simulador de plantas PAT (fase 5; Operación, Calidad SPC y Evaluación desde PAT 130): interfaz Streamlit sobre el motor pat_sim y la base SQLite.

Ejecutar:  streamlit run app.py   (o con el acceso directo «Simulador PAT» del Escritorio)
"""
from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import streamlit as st

st.set_page_config(page_title="Simulador PAT", page_icon="🏭", layout="wide", initial_sidebar_state="expanded")

from ui import comun as C                                   # noqa: E402  (agrega el motor al path)
from ui import p_escenario, p_diseno, p_operacion, p_calidad, p_instrumentacion, p_balances, p_calor, p_alternativas, p_economia, p_calculadoras, p_evaluacion, p_informe   # noqa: E402
from ui import p_temporada, p_dinamico, p_curso   # noqa: E402  (PAT 133, mejoras 6, 7, 16 y 20)
from ui import p_tablero, p_datos_entrada, p_linea, p_experimentos   # noqa: E402  (PAT 134: tableros, ajuste de distribuciones y Excel como FlexSim)
from pat_sim.motor.resumen import resumen_planta             # noqa: E402
import importlib, os, ui                                     # noqa: E402


def _recargar_interfaz():
    """PAT 130: si un archivo de ui/ cambió con el simulador abierto y Streamlit no lo notó (archivos editados desde otra
    máquina sobre OneDrive), se recargan los módulos de la interfaz para no tener que reiniciar: primero los que usan
    los demás (comun, lienzo, p_operacion) y después las pestañas. El motor no se recarga porque la planta de la sesión
    usa sus clases."""
    vistos = ui.__dict__.setdefault("_pat_mtimes", {})
    mods = {n: sys.modules[n] for n in sys.modules if n.startswith("ui.") and getattr(sys.modules[n], "__file__", None)}
    actual = {n: os.path.getmtime(m.__file__) for n, m in mods.items() if os.path.exists(m.__file__)}
    primera = not vistos
    cambio = any(vistos.get(n, 0) < t for n, t in actual.items() if n in vistos)
    if primera or cambio:
        base = ["ui.comun", "ui.lienzo", "ui.p_operacion"]
        for n in [x for x in base if x in actual] + sorted(x for x in actual if x not in base):
            importlib.reload(mods[n])
    vistos.update(actual)


_recargar_interfaz()

st.html(C.ESTILO)
C.iniciar_estado()
bd = C.obtener_bd(); ss = st.session_state; pl = C.planta()

# PAT 134: la barra lateral es el índice de pantallas (antes eran pestañas arriba). Lo que tenía la barra lateral pasó
# a Escenario (proyecto, versión, base y coma decimal, ui/s_proyecto.py) y a Curso (itinerario, ui/s_itinerario.py).
# Solo se ejecuta la pantalla elegida, así cada cambio de pantalla es más rápido. Con el sustituto de Streamlit del banco
# de pruebas o con PAT_TODAS_LAS_PAGINAS=1 (probador AppTest) se ejecutan todas, como antes con las pestañas.
GRUPOS = [
    # PAT 135: Recuperación de calor y Alternativas pasan al grupo Planta (apuntes de la reunión del 04-11-2026).
    ("Planta", [("Escenario", p_escenario), ("Diseño", p_diseno), ("Instrumentación", p_instrumentacion), ("Balances", p_balances),
                ("Recuperación de calor", p_calor), ("Alternativas", p_alternativas)]),
    ("Energía y economía", [("Economía", p_economia)]),
    ("Operación", [("Operación", p_operacion), ("Calidad SPC", p_calidad), ("Temporada", p_temporada), ("Dinámica", p_dinamico),
                   ("Línea", p_linea)]),
    ("Análisis como FlexSim", [("Experimentos", p_experimentos), ("Tableros", p_tablero), ("Datos de entrada", p_datos_entrada)]),
    ("Herramientas y curso", [("Calculadoras", p_calculadoras), ("Evaluación", p_evaluacion), ("Curso", p_curso), ("Informe", p_informe)]),
]
PAGINAS = {n: m for _, g in GRUPOS for n, m in g}
GRUPO_DE = {n: gr for gr, g in GRUPOS for n, _ in g}


def _estilo_indice() -> str:
    """CSS del índice: sin los círculos del selector, la pantalla elegida resaltada y el nombre de cada grupo arriba de su
    primera pantalla (con ::before, porque el selector de Streamlit no admite encabezados). PAT 134 (04-11-2026): pantallas
    a 1,1 rem y grupos a 0,85 rem en gris y negrita suave, en una línea con la barra de 18,75 rem que trae Streamlit 1.65."""
    reglas, k = [], 1
    for grupo, g in GRUPOS:
        reglas.append(f'section[data-testid="stSidebar"] [role="radiogroup"] > div:nth-child({k})::before{{content:"{grupo}";}}')
        k += len(g)
    r = 'section[data-testid="stSidebar"] [role="radiogroup"]'
    return f"""<style>
{r}{{gap:0;width:100%}}
{r} > div{{display:flex;flex-direction:column;width:100%}}
{r} > div::before{{font-size:0.85rem;font-weight:600;letter-spacing:0.03em;color:#6b6b6b;margin:14px 0 4px 2px;pointer-events:none;white-space:nowrap}}
{r} label{{width:100%;margin:0;padding:6px 10px;border-radius:6px;cursor:pointer}}
{r} label [data-testid="stMarkdownContainer"]{{font-size:1.1rem;line-height:1.3;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}}
{r} label p{{white-space:nowrap}}
{r} label > span:first-child{{display:none !important}}
{r} label > div > div:first-child:not(:last-child){{display:none !important}}
{r} label > div{{padding-left:0 !important;margin-left:0 !important}}
{r} label:hover{{background:rgba(27,122,90,0.08)}}
{r} label:has(input:checked){{background:rgba(27,122,90,0.16);box-shadow:inset 3px 0 0 #1b7a5a}}
{r} label:has(input:checked) p{{font-weight:600;color:#1b7a5a}}
""" + "\n".join(reglas) + "\n</style>"


st.html(_estilo_indice())
TODAS = hasattr(st, "REG") or os.environ.get("PAT_TODAS_LAS_PAGINAS") == "1"

if ss.get("pagina") not in PAGINAS:                           # al abrir: la de la dirección (?p=) o Escenario
    try:
        _p = st.query_params.get("p")
    except Exception:
        _p = None
    ss.pagina = _p if _p in PAGINAS else "Escenario"

with st.sidebar:
    st.markdown("### Simulador PAT")
    st.radio("Pantallas", list(PAGINAS), key="pagina", label_visibility="collapsed")
    if pl.avisos:
        st.warning(f"{len(pl.avisos)} aviso(s) del cálculo; véalos en Diseño.")
try:
    st.query_params["p"] = ss.pagina                          # la dirección recuerda la pantalla al recargar
except Exception:
    pass


def _correr(nombre, modulo):
    try:
        modulo.mostrar()
    except Exception as e:                                    # un error en una pantalla no tumba las demás
        st.error(f"Error en la pantalla {nombre}: {e}")
        st.exception(e)


if TODAS:
    for nombre, modulo in PAGINAS.items():
        _correr(nombre, modulo)
else:
    _correr(ss.pagina, PAGINAS[ss.pagina])
