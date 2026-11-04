"""Utilidades comunes de la interfaz: rutas, formato chileno, tablas con alineación del informe y estado de la sesión."""
from __future__ import annotations
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]                 # …\Aplicacion simulador
MOTOR = RAIZ / "02 Motor de calculo Python"
if str(MOTOR) not in sys.path:
    sys.path.insert(0, str(MOTOR))

import html as _html
import streamlit as st
from pat_sim.datos.bd import BaseDatos, NOMBRE_AGROZZI
from pat_sim.escenarios import agrozzi

# Cifras y fuentes de la economía (Modelo_PAT_Agrozzi_v2.xlsx, hoja COMBUSTIBLE)
HENRY_HUB = 2.77            # US$/MMBtu, agosto de 2026
FUENTE_HH = "CNE (2026c), Reporte mensual sector energético, septiembre de 2026, p. 12"
DOLAR = 990.35              # $/US$, 26-10-2026
FUENTE_DOLAR = "Banco Central de Chile (2026), indicadores diarios, 26-10-2026"
PMM = (("Clientes libres", 84.004), ("SEN", 93.417), ("Licitaciones de largo plazo", 108.81))
FUENTE_PMM = "CNE (2026b), Precio medio de mercado, 7-08-2026"
# Biomasa combustible de los rubros pellet, chip y leña (astilla de pino con corteza puesta en planta, sin IVA)
PRECIO_BIOMASA = 6750.0     # $/m³ estéreo, punto medio de 6.000 a 7.500
FUENTE_BIOMASA = "INFOR (Pardo, 2025), Boletín de precios forestales N.° 193, junio de 2025, pp. 12-13"


def fmt(v, d: int = 1) -> str:
    """Formato chileno: miles con punto y decimales con coma."""
    if v is None:
        return "—"
    try:
        v = float(v)
    except (TypeError, ValueError):
        return str(v)
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def esc(t: str) -> str:
    """Escapa el signo $ para que Streamlit no lo lea como fórmula."""
    return t.replace("$", "\\$")


def pct(v, d: int = 1) -> str:
    return "—" if v is None else fmt(100 * float(v), d) + " %"


def clp(v, d: int = 1) -> str:
    return "—" if v is None else "$" + fmt(v, d)


def tabla(filas: list[dict], cols: list[tuple], clase: str = "pat") -> str:
    """Tabla HTML con el estilo del informe: texto a la izquierda, números al centro y plata a la derecha.
    cols: (clave, título, tipo, decimales) con tipo 'txt', 'cen' (texto ya formateado de un número, al centro), 'num', 'clp', 'mm' (millones de pesos, a la derecha) o 'pct'."""
    h = [f'<div class="tabla-desliz"><table class="{clase}"><thead><tr>']
    for _, tit, tipo, _d in cols:
        al = {"txt": "left", "cen": "center", "num": "center", "pct": "center", "clp": "right", "mm": "right"}[tipo]
        h.append(f'<th style="text-align:{al}">{_html.escape(tit)}</th>')
    h.append("</tr></thead><tbody>")
    for f in filas:
        h.append("<tr>")
        for k, _tit, tipo, d in cols:
            v = f.get(k)
            if tipo in ("txt", "cen"):
                s, al = _html.escape("" if v is None else str(v)), "left" if tipo == "txt" else "center"
            elif tipo == "num":
                s, al = fmt(v, d), "center"
            elif tipo == "pct":
                s, al = pct(v, d), "center"
            elif tipo == "mm":
                s, al = fmt(v, d), "right"
            else:
                s, al = clp(v, d), "right"
            h.append(f'<td style="text-align:{al}">{s}</td>')
        h.append("</tr>")
    h.append("</tbody></table></div>")
    return "".join(h)


ESTILO = """
<style>
/* PAT 134 (04-11-2026): letra más grande donde hay espacio, con la jerarquía título > subtítulo > texto > notas.
   Streamlit fija el tamaño en el contenedor de cada markdown (texto 1rem; etiquetas, captions y pestañas 0,875rem). */
[data-testid="stMarkdown"] [data-testid="stMarkdownContainer"],
[data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"]{font-size:1.0625rem}
[data-testid="stCaptionContainer"]{font-size:0.92rem}
[data-testid="stWidgetLabel"] [data-testid="stMarkdownContainer"]{font-size:0.95rem}
[data-testid="stCheckbox"] [data-testid="stWidgetLabel"] [data-testid="stMarkdownContainer"]{font-size:0.95rem;line-height:1.35}
[data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"]{font-size:0.9rem}
[data-testid="stMetricDelta"], [data-testid="stMetricDelta"] [data-testid="stMarkdownContainer"]{font-size:0.9rem}
[data-testid="stTabs"] button[role="tab"] [data-testid="stMarkdownContainer"]{font-size:1rem}
[data-testid="stExpander"] summary [data-testid="stMarkdownContainer"]{font-size:1.0625rem}
table.pat{border-collapse:collapse;font-size:0.95rem;margin:0.3rem 0 0.8rem 0;width:100%}
table.pat th{background:#eef3f0;border-bottom:2px solid #1b7a5a;padding:5px 8px;font-weight:600;line-height:1.25}
table.pat td{border-bottom:1px solid #e3e3e3;padding:4px 8px;line-height:1.35}
div.contenedor-svg{overflow:auto;border:1px solid #ddd;border-radius:6px;background:#fff}
.nota{color:#5a5a5a;font-size:0.9rem}
div.tabla-desliz{overflow-x:auto;-webkit-overflow-scrolling:touch}
/* PAT 134: ayudas desplegables «?» (C.ayuda): clic despliega, otro clic oculta, sin JavaScript */
details.ayuda{margin:0 0 0.35rem 0;padding:0}
details.ayuda > summary{list-style:none;cursor:pointer;display:flex;align-items:center;gap:0.45rem;width:fit-content;max-width:100%;outline:none}
details.ayuda > summary::-webkit-details-marker{display:none}
details.ayuda > summary::marker{content:""}
details.ayuda span.q{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;width:18px;height:18px;flex:0 0 18px;
  border:1.5px solid #9a9a9a;border-radius:50%;color:#7a7a7a;background:#fff;font:700 11px/1 "Source Sans Pro",sans-serif;user-select:none;
  transition:color .15s,border-color .15s,background .15s}
details.ayuda > summary:hover span.q{border-color:#1b7a5a;color:#1b7a5a}
details.ayuda[open] > summary span.q{border-color:#1b7a5a;background:#1b7a5a;color:#fff}
details.ayuda > summary :is(h2,h3,h4,h5,h6){margin:0;padding:0.35rem 0 0.25rem 0;font-weight:600;line-height:1.25}
details.ayuda > summary h2{font-size:2.25rem} details.ayuda > summary h3{font-size:1.75rem}
details.ayuda > summary h4{font-size:1.5rem} details.ayuda > summary h5{font-size:1.25rem} details.ayuda > summary h6{font-size:1rem}
details.ayuda div.ayuda-txt{background:#f3f7f5;border:1px solid #dde8e2;border-left:3px solid #1b7a5a;border-radius:6px;
  padding:7px 11px;margin:4px 0 2px 0;font-size:0.95rem;color:#3d3d3d;line-height:1.5;width:100%;box-sizing:border-box}
details.ayuda div.ayuda-txt p{margin:0 0 0.35rem 0}
details.ayuda div.ayuda-txt ul, details.ayuda div.ayuda-txt ol{margin:0.15rem 0 0.35rem 1.2rem;padding:0}
details.ayuda div.ayuda-txt > :last-child{margin-bottom:0}
details.ayuda div.ayuda-txt code{font-size:0.88rem;background:#e8eeea;padding:0 3px;border-radius:3px}
/* PAT 133, mejora 21: vista para celular */
@media (max-width: 640px){
  .block-container{padding:0.6rem 0.5rem 2rem 0.5rem !important}
  div[data-baseweb="tab-list"]{overflow-x:auto;flex-wrap:nowrap;scrollbar-width:thin}
  button[role="tab"]{white-space:nowrap;padding:0 0.45rem}
  table.pat{font-size:0.8rem}
  [data-testid="stMarkdown"] [data-testid="stMarkdownContainer"], [data-testid="stAlertContainer"] [data-testid="stMarkdownContainer"]{font-size:1rem}
  [data-testid="stCaptionContainer"]{font-size:0.86rem}
  [data-testid="stTabs"] button[role="tab"] [data-testid="stMarkdownContainer"]{font-size:0.9rem}
  details.ayuda div.ayuda-txt{font-size:0.88rem}
  table.pat th, table.pat td{padding:2px 4px}
  div[data-testid="stMetricValue"]{font-size:1.15rem}
  div[data-testid="stMetricLabel"], [data-testid="stMetricLabel"] [data-testid="stMarkdownContainer"]{font-size:0.8rem}
  h3{font-size:1.15rem}
  details.ayuda > summary h3{font-size:1.15rem} details.ayuda > summary h4{font-size:1.05rem}
  div.contenedor-svg{max-height:70vh}
}
</style>
"""


# ---------------------------------------------------------------- PAT 134: ayudas desplegables «?» (pedido de Jaime, 04-11-2026)
import re as _re
_COLOR_MD = {"red": "#d43a2c", "orange": "#e0891a", "green": "#2e9e5b", "blue": "#1f6fb2", "violet": "#7b3fb0",
             "gray": "#6b6b6b", "grey": "#6b6b6b"}


def _md_linea(t: str) -> str:
    """Markdown simple de una línea a HTML: `código`, [enlace](url), :red[…] y demás colores, **negrita** y *cursiva*;
    el resto se escapa. Es lo que usan las ayudas de la interfaz."""
    t = t.replace("\\$", "$")
    codigos = []

    def _cod(m):
        codigos.append("<code>" + _html.escape(m.group(1), quote=False) + "</code>")
        return f"\x00{len(codigos) - 1}\x00"
    t = _re.sub(r"`([^`]+)`", _cod, t)
    t = _html.escape(t, quote=False)
    t = _re.sub(r"\[([^\]]+)\]\((https?://[^)\s]+)\)", r'<a href="\2" target="_blank" rel="noopener">\1</a>', t)
    for _ in range(2):                         # colores con negrita o cursiva adentro
        t = _re.sub(r":(red|orange|green|blue|violet|gray|grey)\[([^\[\]]*)\]",
                    lambda m: f'<span style="color:{_COLOR_MD[m.group(1)]}">{m.group(2)}</span>', t)
    t = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", t)
    t = _re.sub(r"(?<![*\w])\*(?!\s)(.+?)(?<!\s)\*(?![*\w])", r"<i>\1</i>", t)
    t = _re.sub(r"(?<![\w])_(?!\s)([^_]+?)(?<!\s)_(?![\w])", r"<i>\1</i>", t)
    return _re.sub("\x00(\\d+)\x00", lambda m: codigos[int(m.group(1))], t)


def md_html(texto: str) -> str:
    """Convertidor mínimo de markdown a HTML para las ayudas: párrafos (línea en blanco), listas con «- » o «1. »,
    salto de línea con dos espacios al final y el markdown de línea de _md_linea."""
    bloques, lista, tipo, parr = [], [], None, []

    def _cerrar_parr():
        if parr:
            bloques.append("<p>" + " ".join(parr) + "</p>"); parr.clear()

    def _cerrar_lista():
        nonlocal tipo
        if lista:
            bloques.append(f"<{tipo}>" + "".join(f"<li>{x}</li>" for x in lista) + f"</{tipo}>"); lista.clear()
        tipo = None
    for crudo in str(texto).split("\n"):
        lin = crudo.strip()
        m_ul = _re.match(r"^[-*•] +(.*)$", lin); m_ol = _re.match(r"^\d+[.)] +(.*)$", lin)
        if not lin:
            _cerrar_parr(); _cerrar_lista()
        elif m_ul or m_ol:
            _cerrar_parr()
            t = "ul" if m_ul else "ol"
            if tipo and tipo != t:
                _cerrar_lista()
            tipo = t; lista.append(_md_linea((m_ul or m_ol).group(1)))
        elif lista and crudo[:1] in (" ", "\t"):
            lista[-1] += " " + _md_linea(lin)      # continuación de un ítem
        else:
            _cerrar_lista()
            parr.append(_md_linea(lin) + ("<br>" if crudo.endswith("  ") else ""))
    _cerrar_parr(); _cerrar_lista()
    return "".join(bloques)


def ayuda_html(texto: str, titulo: str | None = None, nivel: int = 4) -> str:
    """HTML de una ayuda: <details> con el «?» en el resumen (a la derecha del título si lo hay) y el texto en una caja."""
    q = '<span class="q" title="Ayuda: clic para ver u ocultar">?</span>'
    if titulo:
        n = min(6, max(2, int(nivel)))
        resumen = f"<h{n}>{_md_linea(titulo)}</h{n}>{q}"
    else:
        resumen = q
    return f'<details class="ayuda"><summary>{resumen}</summary><div class="ayuda-txt">{md_html(texto)}</div></details>'


def ayuda(texto: str, titulo: str | None = None, nivel: int = 4, dg=None):
    """PAT 134: descripción pequeña (cómo leer, cómo se usa, de dónde sale una cifra, supuestos) oculta detrás de un «?»
    en un círculo. Con título, dibuja el título (h4, o el nivel pedido) con el «?» a su derecha; sin título, solo el «?».
    Clic despliega el texto ahí mismo y otro clic lo oculta. dg: columna o contenedor donde dibujarla (por omisión, st)."""
    (dg if dg is not None else st).html(ayuda_html(texto, titulo, nivel))


def mostrar_tabla(filas, cols):
    st.html(tabla(filas, cols))


@st.cache_resource(show_spinner="Abriendo la base de datos…")
def obtener_bd() -> BaseDatos:
    b = BaseDatos()
    b.precargar()
    return b


def iniciar_estado():
    """Carga en la sesión la última versión de la planta basada en Agrozzi (o la crea si no hay base)."""
    ss = st.session_state
    if "pl" in ss:
        return
    bd = obtener_bd()
    p = bd.obtener_proyecto(NOMBRE_AGROZZI)
    try:
        vid = bd.ultima_version(p["id"]) if p else None
        ss.pl = con_capacidades(bd.cargar_version(vid)) if vid else agrozzi.crear()
        ss.pid, ss.vid = (p["id"], vid) if p else (None, None)
    except Exception:
        ss.pl = agrozzi.crear(); ss.pid = ss.vid = None
    ss.cop = 2.0
    ss.economia = dict(precio_gas=HENRY_HUB, dolar=DOLAR, inversion=0.0, costo_anual=0.0, anios=20, tasa=0.10, precio_biomasa=PRECIO_BIOMASA)


def con_capacidades(pl):
    """PAT 132: una versión guardada antes de las capacidades de partida (o sin ninguna) recibe las del escenario base,
    para que la vista de teoría de restricciones muestre la utilización con su semáforo desde el inicio."""
    from pat_sim.escenarios import capacidades as CAP
    if pl.resuelta and not any(e.params["capacidad"].valor for e in pl.equipos.values() if "capacidad" in e.params):
        CAP.aplicar(pl)
    try:                                       # PAT 133, mejora 19: repone las marcas «Medido» de los datos de planta
        from pat_sim.motor.datos_planta import restaurar_medidos
        restaurar_medidos(pl)
    except Exception:
        pass
    return pl


def planta():
    return st.session_state.pl


def resolver(pl=None) -> bool:
    """Resuelve la planta y muestra el error en español si no se puede. Devuelve True si quedó resuelta."""
    pl = pl or planta()
    try:
        pl.resolver()
        st.session_state.error_resolucion = None
        return True
    except Exception as e:                    # error de la planta (falta alimentación, ciclo, parámetro)
        pl.resuelta = False
        st.session_state.error_resolucion = str(e)
        st.error(f"No se pudo resolver la planta: {e}")
        return False


def exigir_resuelta() -> bool:
    pl = planta()
    if not pl.resuelta:
        motivo = st.session_state.get("error_resolucion")
        st.warning("La planta no está resuelta. Revise la pestaña Diseño: cada equipo debe tener su alimentación."
                   + (f" Motivo: {motivo}" if motivo else ""))
        return False
    return True


def resumen_actual():
    """Resumen de recuperación de calor de la planta actual con el COP de la sesión (se recalcula en cada ejecución)."""
    from pat_sim.motor.resumen import resumen_planta
    return resumen_planta(planta(), cop=st.session_state.cop)


def operacion():
    """Estado de la operación por turnos (pestañas Operación, Calidad SPC y Evaluación). Se reinicia si cambia el rubro."""
    from pat_sim.motor.operacion import Operacion, semilla_texto
    ss = st.session_state; pl = planta()
    op = ss.get("op")
    if op is None or op.rubro != pl.rubro:
        nombre = (ss.get("ev_estudiante") or "").strip()
        ss.op = Operacion(rubro=pl.rubro, semilla=semilla_texto(nombre or "escenario"), estudiante=nombre)
        ss.pop("op_compra", None)
    return ss.op


def resumen_o_nada():
    try:
        return resumen_actual()
    except Exception:
        return None


# ---------------------------------------------------------------- PAT 133, mejora 21: campos numéricos con formato chileno
_NI_ORIG = None


def _numero_cl(dg, label, min_value=None, max_value=None, value="min", step=None, format=None, key=None, help=None,
               on_change=None, args=None, kwargs=None, **kw):
    """Reemplazo de st.number_input: campo de texto que muestra y lee coma decimal y punto de miles (1.234,5), con los
    mismos límites, paso y tipo (entero o decimal) que el campo original. Se desactiva con la opción de la barra lateral."""
    from pat_sim.motor import formato as FM
    ss = st.session_state
    if not ss.get("formato_cl", True) or _NI_ORIG is None:
        return _NI_ORIG(dg, label, min_value, max_value, value, step, format, key, help, on_change, args, kwargs, **kw)
    nums = [x for x in (value, min_value, max_value, step) if x is not None and x != "min"]
    entero = bool(nums) and all(isinstance(x, int) and not isinstance(x, bool) for x in nums)
    if value == "min":
        value = min_value if min_value is not None else 0
    d = FM.decimales(format, step, entero) if entero else max(FM.decimales(format, step, entero), FM.decimales_valor(value, 3))
    texto = "" if value is None else FM.escribir(value, d)
    extra = {k: v for k, v in kw.items() if k in ("placeholder", "disabled", "label_visibility", "width")}
    if on_change is not None:
        extra.update(on_change=on_change, args=args, kwargs=kwargs)
    if key is not None:
        tk, tv = f"{key}__cl", f"{key}__clv"
        if tk in ss and key in ss and tv in ss and ss[key] != ss[tv] and ss[key] is not None:
            ss[tk] = FM.escribir(ss[key], d)          # el programa cambió el valor por la sesión: se muestra el nuevo
        elif tk not in ss:
            ss[tk] = FM.escribir(ss[key], d) if key in ss and ss[key] is not None else texto
        t = dg.text_input(label, key=tk, help=help, **extra)
    else:
        t = dg.text_input(label, value=texto, help=help, **extra)
    if (t is None or not str(t).strip()) and value is None:
        return None
    try:
        x = FM.leer(t)
    except ValueError:
        dg.caption(f":red[«{t}» no es un número; se usa {texto}.]")
        x = float(value or 0)
    if min_value is not None and x < min_value:
        dg.caption(f":orange[Mínimo {FM.escribir(min_value, d)}.]"); x = float(min_value)
    if max_value is not None and x > max_value:
        dg.caption(f":orange[Máximo {FM.escribir(max_value, d)}.]"); x = float(max_value)
    x = int(round(x)) if entero else x
    if key is not None:
        ss[key] = x; ss[f"{key}__clv"] = x
    return x


def _activar_formato_cl():
    """Cambia st.number_input (y el de columnas, formularios y barra lateral) por el campo chileno, una sola vez."""
    global _NI_ORIG
    try:
        from streamlit.delta_generator import DeltaGenerator
    except Exception:                 # sustituto de Streamlit del banco de pruebas
        return
    if getattr(DeltaGenerator, "_pat_cl", False):
        _NI_ORIG = DeltaGenerator._pat_ni_orig
        return
    _NI_ORIG = DeltaGenerator.number_input
    DeltaGenerator._pat_ni_orig = _NI_ORIG
    DeltaGenerator.number_input = lambda self, *a, **k: _numero_cl(self, *a, **k)
    st.number_input = lambda *a, **k: _numero_cl(st._main, *a, **k)
    DeltaGenerator._pat_cl = True


_activar_formato_cl()
