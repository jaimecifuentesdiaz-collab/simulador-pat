"""Exportación del balance a Excel (.xlsx) y del informe listo para imprimir o guardar como PDF (PAT 133, mejora 18).

El .xlsx se arma sin dependencias externas: un archivo zip con el XML de SpreadsheetML (ECMA-376) escrito a mano, porque
openpyxl no está en el entorno de la aplicación. Los totales, las coberturas, el calor sensible del mapa y el calor de cada
etapa de la cascada son fórmulas de Excel que referencian las celdas de datos; cada fórmula trae además el valor que calculó
el motor, así el archivo se ve bien aunque el programa que lo abra no recalcule (al abrirlo, Excel recalcula todo). Las
fórmulas se guardan con los nombres del formato (SUM, SUMIF), que Excel en español muestra como SUMA y SUMAR.SI.
Estilos: texto a la izquierda, números al centro, dinero a la derecha y encabezados en negrita; sin paneles inmovilizados."""
from __future__ import annotations
import io, math, re, zipfile
from datetime import datetime
from xml.sax.saxutils import escape

# PAT 133: índices de los estilos de celda (cellXfs de styles.xml)
(TXT, ENC_TXT, ENC_NUM, ENC_CLP, NUM0, NUM1, NUM2, PCT, CLP, TIT, NOTA,
 TOT_TXT, TOT_NUM1, TOT_PCT, TOT_CLP, MON2) = range(16)

_NS = 'xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"'

ESTILOS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
<numFmts count="3"><numFmt numFmtId="164" formatCode="#,##0.0"/><numFmt numFmtId="165" formatCode="&quot;$&quot;#,##0"/><numFmt numFmtId="166" formatCode="0.0%"/></numFmts>
<fonts count="4"><font><sz val="11"/><name val="Calibri"/></font><font><b/><sz val="11"/><name val="Calibri"/></font>
<font><b/><sz val="13"/><name val="Calibri"/></font><font><i/><sz val="9"/><color rgb="FF5A5A5A"/><name val="Calibri"/></font></fonts>
<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>
<borders count="2"><border><left/><right/><top/><bottom/><diagonal/></border><border><left/><right/><top/><bottom style="thin"><color rgb="FF1B7A5A"/></bottom><diagonal/></border></borders>
<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>
<cellXfs count="16">
<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="left" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="center" vertical="center" wrapText="1"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="1" xfId="0" applyFont="1" applyBorder="1" applyAlignment="1"><alignment horizontal="right" vertical="center" wrapText="1"/></xf>
<xf numFmtId="3" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="164" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="166" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="165" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
<xf numFmtId="0" fontId="2" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left"/></xf>
<xf numFmtId="0" fontId="3" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left" vertical="top"/></xf>
<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1"><alignment horizontal="left" vertical="top" wrapText="1"/></xf>
<xf numFmtId="164" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="166" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1" applyAlignment="1"><alignment horizontal="center" vertical="top"/></xf>
<xf numFmtId="165" fontId="1" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyFont="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
<xf numFmtId="4" fontId="0" fillId="0" borderId="0" xfId="0" applyNumberFormat="1" applyAlignment="1"><alignment horizontal="right" vertical="top"/></xf>
</cellXfs>
<cellStyles count="1"><cellStyle name="Normal" xfId="0" builtinId="0"/></cellStyles>
</styleSheet>"""


def columna(n: int) -> str:
    """Letra de la columna n (1 = A)."""
    s = ""
    while n:
        n, r = divmod(n - 1, 26); s = chr(65 + r) + s
    return s


def celda(fila: int, col: int, fija: bool = False) -> str:
    return f"${columna(col)}${fila}" if fija else f"{columna(col)}{fila}"


def _cl(v, d: int = 1) -> str:
    """Cifra con coma decimal (formato chileno) para las notas de texto; sin decimales si es entera."""
    if v is None:
        return "—"
    v = float(v); d = 0 if v == int(v) else d
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _numero(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(float(v))


class Hoja:
    """Hoja de cálculo mínima: celdas con valor, estilo y fórmula opcional (con su valor ya calculado)."""

    def __init__(self, nombre: str, anchos: list[float]):
        self.nombre = nombre[:31]; self.anchos = anchos; self.celdas: dict[tuple[int, int], tuple] = {}

    def poner(self, fila, col, valor=None, estilo=TXT, formula: str | None = None):
        self.celdas[(fila, col)] = (valor, estilo, formula)

    def fila(self, fila, valores: list, estilos: list):
        for j, (v, e) in enumerate(zip(valores, estilos), start=1):
            self.poner(fila, j, v, e)

    def formulas(self) -> list[str]:
        return [f for (_v, _e, f) in self.celdas.values() if f]

    def xml(self) -> str:
        filas = {}
        for (f, c) in sorted(self.celdas):
            filas.setdefault(f, []).append(c)
        h = [f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet {_NS}>',
             # PAT 133: vista simple, sin <pane>: nunca paneles inmovilizados
             '<sheetViews><sheetView workbookViewId="0"/></sheetViews><sheetFormatPr defaultRowHeight="15"/><cols>']
        for j, a in enumerate(self.anchos, start=1):
            h.append(f'<col min="{j}" max="{j}" width="{a}" customWidth="1"/>')
        h.append("</cols><sheetData>")
        for f in sorted(filas):
            h.append(f'<row r="{f}">')
            for c in filas[f]:
                v, e, fo = self.celdas[(f, c)]; ref = celda(f, c)
                if fo:
                    val = f"<v>{float(v)!r}</v>" if _numero(v) else ""
                    h.append(f'<c r="{ref}" s="{e}"><f>{escape(fo)}</f>{val}</c>')
                elif isinstance(v, str):
                    h.append(f'<c r="{ref}" s="{e}" t="inlineStr"><is><t xml:space="preserve">{escape(v)}</t></is></c>')
                elif _numero(v):
                    h.append(f'<c r="{ref}" s="{e}"><v>{float(v)!r}</v></c>')
                else:
                    h.append(f'<c r="{ref}" s="{e}"/>')
            h.append("</row>")
        h.append('</sheetData><pageMargins left="0.7" right="0.7" top="0.75" bottom="0.75" header="0.3" footer="0.3"/>'
                 '<pageSetup paperSize="1" orientation="landscape"/></worksheet>')
        return "".join(h)


def libro_xlsx(hojas: list[Hoja]) -> bytes:
    """Empaqueta las hojas en un .xlsx (zip con el XML de SpreadsheetML)."""
    tipos = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
             '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>'
             '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
             '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>']
    rels_libro = ['<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">']
    hs = []
    for i, h in enumerate(hojas, start=1):
        tipos.append(f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>')
        rels_libro.append(f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>')
        hs.append(f'<sheet name="{escape(h.nombre, {chr(34): "&quot;"})}" sheetId="{i}" r:id="rId{i}"/>')
    n = len(hojas) + 1
    rels_libro.append(f'<Relationship Id="rId{n}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>')
    tipos.append("</Types>")
    libro = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook {_NS}><bookViews><workbookView/></bookViews>'
             f'<sheets>{"".join(hs)}</sheets><calcPr calcId="191029" fullCalcOnLoad="1"/></workbook>')
    raiz = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>')
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", "".join(tipos)); z.writestr("_rels/.rels", raiz)
        z.writestr("xl/workbook.xml", libro); z.writestr("xl/_rels/workbook.xml.rels", "".join(rels_libro))
        z.writestr("xl/styles.xml", ESTILOS)
        for i, h in enumerate(hojas, start=1):
            z.writestr(f"xl/worksheets/sheet{i}.xml", h.xml())
    return buf.getvalue()


# ------------------------------------------------------------------------------------------------ hoja de corrientes
SERVICIO = "Calor de servicio"
ENTALPIA = "Entalpía sobre 0 °C"


def filas_corrientes(pl) -> list[dict]:
    """Corrientes de la planta resuelta: número, origen, destino, tipo, caudal, temperatura y calor (mismo criterio de la
    tabla de corrientes de la pestaña Diseño: en los servicios, el calor que pide el equipo de destino)."""
    from .corrientes import TIPOS
    out = []
    for c in pl.conexiones:
        tipo = pl.tipo_conexion(c)
        f = dict(n=c.nombre or "", de=f"{c.origen} · {pl.equipos[c.origen].nombre}", a=f"{c.destino} · {pl.equipos[c.destino].nombre}",
                 tipo=TIPOS.get(tipo, (tipo,))[0], m=None, T=None, q=None, base="")
        if pl.es_servicio(c):
            r = pl.equipos[c.destino].resultado
            f.update(q=(r.servicios.get(c.puerto_origen + "_kW") if r else None), base=SERVICIO)
        else:
            s = pl.salidas.get((c.origen, c.puerto_origen))
            if s is not None:
                s = s.fraccion(c.reparto / 100)
                f.update(m=s.m, T=s.T, q=s.H(), base=ENTALPIA)
        out.append(f)
    return out


def _hoja_corrientes(pl, hoy: str) -> Hoja:
    h = Hoja("Corrientes", [8, 34, 34, 24, 15, 11, 15, 22])
    h.poner(1, 1, f"Corrientes de la planta: {pl.nombre}", TIT)
    h.poner(2, 1, f"Fuente: balance de materia y energía del motor pat_sim (simulador PAT), generado el {hoy}. "
                  "Entalpía con referencia en agua líquida a 0 °C (IAPWS-IF97 para el vapor).", NOTA)
    h.fila(4, ["N.º", "De", "A", "Tipo", "Caudal (kg/h)", "T (°C)", "Calor (kW)", "Base del calor"],
           [ENC_TXT, ENC_TXT, ENC_TXT, ENC_TXT, ENC_NUM, ENC_NUM, ENC_NUM, ENC_TXT])
    filas = filas_corrientes(pl); i0 = 5
    for i, f in enumerate(filas):
        h.fila(i0 + i, [f["n"], f["de"], f["a"], f["tipo"], f["m"], f["T"], f["q"], f["base"]], [TXT, TXT, TXT, TXT, NUM0, NUM1, NUM1, TXT])
    i1 = i0 + max(len(filas), 1) - 1; t = i1 + 2
    tot = sum(f["q"] or 0.0 for f in filas if f["base"] == SERVICIO)
    h.poner(t, 1, "Calor de servicio total (kW)", TOT_TXT)
    h.poner(t, 7, tot, TOT_NUM1, f'SUMIF({celda(i0, 8)}:{celda(i1, 8)},"{SERVICIO}",{celda(i0, 7)}:{celda(i1, 7)})')
    return h


# ------------------------------------------------------------------------------------------------ hoja de recuperación
def _hoja_recuperacion(pl, r: dict, economia: dict | None, hoy: str) -> Hoja:
    h = Hoja("Recuperación", [46, 17, 17, 17, 18])
    h.poner(1, 1, f"Recuperación de calor: {pl.nombre}", TIT)
    h.poner(2, 1, f"Fuente: mapa de corrientes, cascada en serie y pinch del motor pat_sim (Linnhoff y Flower, 1978, citado en "
                  f"Klemeš et al., 2018), generado el {hoy}. Aproximación mínima {_cl(r.get('dT_min'))} °C; temperatura final "
                  f"{_cl(r.get('T_final'))} °C.", NOTA)
    if r.get("sin_sumidero") or "cascada" not in r:
        h.poner(4, 1, "La planta no tiene un sumidero de calor: no hay recuperación que calcular.", TXT)
        return h
    s = r["sumidero"]
    # sumidero: el calor es fórmula de CP y temperaturas
    h.fila(4, ["Sumidero", "T entrada (°C)", "T salida (°C)", "CP (kW/K)", "Calor (kW)"], [ENC_TXT, ENC_NUM, ENC_NUM, ENC_NUM, ENC_NUM])
    fs = 5
    h.fila(fs, [f"{s['nombre']} ({s['equipo']})", s["T_in"], s["T_out"], s["CP"]], [TXT, NUM1, NUM1, NUM2])
    QS = celda(fs, 5, True); CPS = celda(fs, 4, True)
    h.poner(fs, 5, r["Qsumidero"], NUM1, f"{celda(fs, 4)}*({celda(fs, 3)}-{celda(fs, 2)})")
    # mapa de corrientes calientes: el calor sensible es fórmula; el latente es dato
    f = fs + 2
    h.poner(f, 1, "Mapa de corrientes calientes", TOT_TXT); f += 1
    h.fila(f, ["Corriente", "T de cesión (°C)", "T final (°C)", "CP (kW/K)", "Calor (kW)"], [ENC_TXT, ENC_NUM, ENC_NUM, ENC_NUM, ENC_NUM]); f += 1
    m0 = f
    for nombre, v in r["corrientes"].items():
        latente = v[3] is None
        h.fila(f, [nombre + (" (latente)" if latente else ""), v[1], None if latente else v[2], None if latente else v[3]], [TXT, NUM1, NUM1, NUM2])
        if latente:
            h.poner(f, 5, v[4], NUM1)
        else:
            h.poner(f, 5, v[4], NUM1, f"{celda(f, 4)}*({celda(f, 2)}-{celda(f, 3)})")
        f += 1
    m1 = f - 1
    h.poner(f, 1, "Oferta total del mapa (kW)", TOT_TXT)
    h.poner(f, 5, r["oferta"], TOT_NUM1, f"SUM({celda(m0, 5)}:{celda(m1, 5)})"); f += 2
    # cascada en serie: la temperatura de entrada de cada etapa es la de salida de la anterior y el calor es CP × ΔT
    h.poner(f, 1, "Cascada en serie (una etapa de intercambio por corriente)", TOT_TXT); f += 1
    h.fila(f, ["Etapa (corriente que cede calor)", "Sumidero entra (°C)", "Sumidero sale (°C)", "", "Calor de la etapa (kW)"],
           [ENC_TXT, ENC_NUM, ENC_NUM, ENC_NUM, ENC_NUM]); f += 1
    c0 = f
    for k, e in enumerate(r["cascada_filas"]):
        h.poner(f, 1, e["corriente"], TXT)
        h.poner(f, 2, e["T_entra"], NUM2, celda(fs, 2) if k == 0 else celda(f - 1, 3))
        h.poner(f, 3, e["T_sale"], NUM2)
        h.poner(f, 5, e["Q_kW"], NUM1, f"{CPS}*({celda(f, 3)}-{celda(f, 2)})")
        f += 1
    c1 = f - 1
    TC = celda(f, 5)
    h.poner(f, 1, "Cascada en serie: total (kW)", TOT_TXT)
    h.poner(f, 5, r["cascada"], TOT_NUM1, f"SUM({celda(c0, 5)}:{celda(c1, 5)})" if c1 >= c0 else "0"); f += 2
    # alternativas y coberturas (fórmulas de división sobre el calor del sumidero)
    h.poner(f, 1, "Alternativas y cobertura del sumidero", TOT_TXT); f += 1
    h.fila(f, ["Concepto", "Calor (kW)", "Cobertura del sumidero"], [ENC_TXT, ENC_NUM, ENC_NUM]); f += 1
    h.poner(f, 1, "Cascada en serie", TXT); h.poner(f, 2, r["cascada"], NUM1, TC)
    h.poner(f, 3, r["cobertura_cascada"], PCT, f"{celda(f, 2)}/{QS}"); f += 1
    h.poner(f, 1, "Objetivo pinch", TXT); h.poner(f, 2, r["pinch"], NUM1)
    h.poner(f, 3, r["cobertura_pinch"], PCT, f"{celda(f, 2)}/{QS}"); f += 1
    if r.get("combustible") != "biomasa":
        h.poner(f, 1, "Solo condensados (alternativa 2)", TXT); h.poner(f, 2, r["alt2"], NUM1)
        h.poner(f, 3, r["cobertura_alt2"], PCT, f"{celda(f, 2)}/{QS}"); f += 1
    h.poner(f, 1, "Calor externo mínimo (pinch)", TXT); h.poner(f, 2, r["Q_externo_min"], NUM1); f += 1
    h.poner(f, 1, "Calor que la caldera sigue entregando con la cascada", TXT)
    h.poner(f, 2, r["Qsumidero"] - r["cascada"], NUM1, f"{QS}-{TC}")
    h.poner(f, 3, 1 - r["cobertura_cascada"], PCT, f"{celda(f, 2)}/{QS}"); f += 2
    # economía de la cascada (dinero a la derecha)
    if economia and "gas_desplazado_cascada" in r:
        h.poner(f, 1, "Economía de la cascada", TOT_TXT); f += 1
        h.fila(f, ["Concepto", "Valor"], [ENC_TXT, ENC_CLP]); f += 1
        g = f
        h.poner(f, 1, "Gas desplazado por la cascada (MMBtu por temporada)", TXT); h.poner(f, 2, r["gas_desplazado_cascada"]["MMBtu"], NUM1); f += 1
        h.poner(f, 1, "Precio del gas (US$/MMBtu)", TXT); h.poner(f, 2, float(economia["precio_gas"]), MON2); f += 1
        h.poner(f, 1, "Dólar ($/US$)", TXT); h.poner(f, 2, float(economia["dolar"]), MON2); f += 1
        ah = r["gas_desplazado_cascada"]["MMBtu"] * float(economia["precio_gas"]) * float(economia["dolar"])
        h.poner(f, 1, "Ahorro por temporada ($)", TOT_TXT)
        h.poner(f, 2, ah, TOT_CLP, f"{celda(g, 2)}*{celda(g + 1, 2)}*{celda(g + 2, 2)}"); f += 1
        h.poner(f, 1, "Precio del gas y dólar: los de la pestaña Economía (fuente y fecha en el informe HTML).", NOTA)
    elif economia and "biomasa_cascada" in r:
        h.poner(f, 1, "Economía de la cascada (biomasa combustible)", TOT_TXT); f += 1
        h.fila(f, ["Concepto", "Valor"], [ENC_TXT, ENC_CLP]); f += 1
        g = f; precio = float(economia.get("precio_biomasa") or 0.0)
        h.poner(f, 1, "Biomasa desplazada por la cascada (m³ estéreo por año)", TXT); h.poner(f, 2, r["biomasa_cascada"]["m3"], NUM1); f += 1
        h.poner(f, 1, "Precio de la biomasa ($/m³ estéreo)", TXT); h.poner(f, 2, precio, CLP); f += 1
        h.poner(f, 1, "Ahorro por año ($)", TOT_TXT)
        h.poner(f, 2, r["biomasa_cascada"]["m3"] * precio, TOT_CLP, f"{celda(g, 2)}*{celda(g + 1, 2)}"); f += 1
        h.poner(f, 1, "Precio de la biomasa: el de la pestaña Economía (fuente y fecha en el informe HTML).", NOTA)
    return h


def balance_xlsx(pl, r: dict, economia: dict | None = None, fecha: str | None = None) -> bytes:
    """Balance de la planta resuelta en un .xlsx con dos hojas: «Corrientes» (caudal, temperatura y calor) y «Recuperación»
    (sumidero, mapa, cascada, alternativas y, si se entrega la economía de la sesión, el ahorro). r: resumen_planta(pl)."""
    if not pl.resuelta:
        raise ValueError("La planta no está resuelta: no hay balance que exportar")
    hoy = fecha or datetime.now().strftime("%d-%m-%Y")
    return libro_xlsx([_hoja_corrientes(pl, hoy), _hoja_recuperacion(pl, r, economia, hoy)])


# ------------------------------------------------------------------------------------------------ informe para imprimir
ESTILO_IMPRESION = """
<style>
.barra-imprimir{margin:12px 0 18px 0}
.barra-imprimir button{background:#1b7a5a;color:#fff;border:0;border-radius:6px;padding:8px 16px;font-size:0.95rem;cursor:pointer}
@media print{
  @page{size:letter;margin:18mm 15mm}
  body{max-width:none;margin:0;padding:0;font-size:10pt}
  .barra-imprimir{display:none}
  h2{break-after:avoid;page-break-after:avoid}
  h2.salto{break-before:page;page-break-before:always}
  table{page-break-inside:auto}
  tr{break-inside:avoid;page-break-inside:avoid}
  thead{display:table-header-group}
  div.contenedor-svg{overflow:visible;border:0}
  div.contenedor-svg svg{max-width:100%;height:auto}
}
</style>
"""
BOTON_IMPRIMIR = ('<div class="barra-imprimir"><button type="button" onclick="window.print()">Imprimir o guardar como PDF</button></div>')
SECCIONES_CON_SALTO = ("Parámetros y su fuente", "Diagrama de flujo", "Tabla de corrientes", "Recuperación de calor", "Economía")


def informe_imprimible(doc: str) -> str:
    """Agrega al informe HTML los estilos de impresión (tamaño carta, saltos de página antes de las secciones largas,
    encabezados de tabla repetidos) y un botón «Imprimir o guardar como PDF» que llama a window.print()."""
    if "</head>" in doc:
        doc = doc.replace("</head>", ESTILO_IMPRESION + "</head>", 1)
    else:
        doc = ESTILO_IMPRESION + doc
    m = re.search(r"<body[^>]*>", doc)
    doc = doc[:m.end()] + BOTON_IMPRIMIR + doc[m.end():] if m else BOTON_IMPRIMIR + doc
    for s in SECCIONES_CON_SALTO:
        doc = doc.replace(f"<h2>{s}", f'<h2 class="salto">{s}')
    return doc
