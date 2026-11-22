"""Lámina de ingeniería del layout (PAT 136, tarea T19; comentario 1 del profesor Torres del 13-11-2026).

Convierte el layout que ya calcula motor/layout.py (posiciones, dimensiones, corrientes, bandeja y sala eléctrica) en un plano
con formato de lámina: marco, marcas de centrado, zonas de referencia, cajetín, escala normalizada, ejes de grilla con burbujas,
cotas, barra de escala, norte y lista de equipos. No recalcula nada del layout: solo lo dibuja.

Salidas: SVG (pantalla), PDF (reportlab) y DXF (ezdxf, en capas, unidades en metros).

Normas y verificación (búsqueda web del 13-11-2026):
- ISO 5457:1999 (formatos y presentación de hojas): A3 = 297 x 420 mm y A1 = 594 x 841 mm; margen izquierdo de 20 mm (incluye el
  marco, sirve para archivar) y 10 mm en los otros lados; marco de línea continua de 0,7 mm; cuatro marcas de centrado de 0,7 mm que
  parten en el borde de la hoja y entran 10 mm del marco; referencia por zonas de 50 mm medidas desde los ejes de simetría (las
  diferencias se suman a las zonas de borde): letras mayúsculas de arriba abajo (sin I ni O) y números de izquierda a derecha, texto
  de 3,5 mm, líneas de 0,35 mm; A3 con 8 x 6 zonas y A1 con 16 x 12; cajetín en la esquina inferior derecha del marco (fuente:
  texto de ISO 5457:1999 en cdn.standards.iteh.ai, muestra pública).
- ISO 7200:2004 (campos de datos del cajetín): campos obligatorios propietario legal, número de identificación, fecha de emisión,
  número de hoja, título, persona que aprueba, creador y tipo de documento; opcionales índice de revisión, número de hojas, estado,
  tamaño de papel y otros; ancho total del cajetín de 180 mm (fuente: texto de ISO 7200:2004 en cdn.standards.iteh.ai).
- ISO 5455 (escalas): 1:50, 1:100, 1:200 y 1:500 están en la serie recomendada; 1:1000 se usa solo de respaldo (conocimiento propio,
  no se abrió el texto de la norma).
- ISO 129-1 (acotado) e ISO 128 (tipos de línea): líneas de cota finas continuas con extremos de flecha o trazo oblicuo, líneas de
  referencia que sobrepasan la de cota, texto sobre la línea de cota; continua gruesa para contornos visibles, fina para cotas,
  trazos para aristas ocultas y punto y raya para ejes (conocimiento propio, no se abrió el texto de las normas).
Supuesto: el espesor de 0,5 mm para la línea gruesa, 0,35 mm para la media y 0,25 mm para la fina (grupo 0,5 de ISO 128), las
longitudes de trazo y la altura de texto de 2,5 mm en A3 y 3,5 mm en A1; el módulo de la grilla de columnas (se elige entre 2, 5, 10,
20, 50 y 100 m según la escala) y su origen en (0; 0); la distribución de los campos del cajetín dentro de los 180 mm.

Coordenadas: la lámina se arma en mm de papel con origen en la esquina inferior izquierda e y hacia arriba. El plano en planta usa
x al este e y al norte (norte hacia arriba de la hoja). En el DXF todo se pasa a metros de modelo (mm de papel x escala / 1000), de modo
que al imprimir a la escala indicada la hoja sale a tamaño real.
"""
from __future__ import annotations
import datetime
import io
import math
from . import layout as LY
from . import plano_detalle as PD
from .formato import escribir

# ------------------------------------------------------------------------------------------- constantes
FORMATOS = {"A3": (420.0, 297.0), "A1": (841.0, 594.0)}      # mm, apaisados (ISO 5457 / ISO 216)
ZONAS = {"A3": (8, 6), "A1": (16, 12)}                       # zonas de referencia: lado largo y lado corto (ISO 5457)
ESCALAS = (50, 100, 200, 500)                                # ISO 5455
ESCALA_RESPALDO = 1000                                       # solo si no cabe en 1:500 (con aviso)
MARGEN_IZQ, MARGEN = 20.0, 10.0                              # mm (ISO 5457)
ANCHO_CAJETIN = 180.0                                        # mm (ISO 7200, apartado 6)
ANCHO_TABLA = 168.0                                          # mm; Supuesto: 12 mm menos que el cajetín para no pisar la marca de centrado
INSET = 11.0                                                 # mm; Supuesto: contenido a más de 10 mm del marco, fuera de las marcas de centrado
MODULOS_GRILLA = (2.0, 5.0, 10.0, 20.0, 50.0, 100.0)         # m; Supuesto
LETRAS_EJES = "ABCDEFGHJKLMNPQRSTUVWXYZ"                     # sin I ni O, como en las zonas de ISO 5457
AUTOR = "(nombre del estudiante)"   # PAT 140: sin nombre fijo; la pantalla pasa el nombre escrito en Desafío si lo hay
REVISOR = "Docente del curso"
INSTITUCION = "Universidad de Talca"
UNIDAD = "m"
PROYECCION = "Vista en planta; método de proyección del primer diedro (ISO E)"
TIPO_DOCUMENTO = "Plano de disposición general (layout)"
CAMPOS_CAJETIN = ("titulo", "proyecto", "autor", "revisor", "institucion", "fecha", "escala", "numero_plano", "revision", "unidad",
                  "proyeccion", "formato", "hoja", "tipo_documento")
CAPAS = {   # capa: (color en pantalla y PDF, color ACI del DXF)
    "EQUIPOS": ("#000000", 7), "CANERIAS": ("#1f4e8c", 5), "ELECTRICO": ("#a06a00", 30), "COTAS": ("#1b6b3a", 3),
    "TEXTOS": ("#000000", 7), "MARCO": ("#000000", 7), "EJES": ("#b0302a", 1),
    # PAT 140 (plano detallado): edificio, sitio, pasillos y zonas de mantención en capas propias
    "EDIFICIO": ("#000000", 7), "SITIO": ("#5f5f5f", 8), "PASILLOS": ("#5f5f5f", 8), "MANTENCION": ("#6f6f6f", 9)}
COLOR_PLANO = "#000000"     # PAT 140: vista de plano en blanco y negro (tipo CAD)
ACI_SERVICIO = {"producto": 3, "agua": 4, "vapor": 1, "condensado": 6, "aire": 30, "electricidad": 2}
# tipo de línea: (espesor mm, trazo en mm o None, tipo DXF)
TIPOS_LINEA = {
    "marco": (0.70, None), "gruesa": (0.50, None), "media": (0.35, None), "fina": (0.25, None),
    "trazos": (0.35, (3.0, 1.0)),                                   # ISO 128 tipo 02, aristas ocultas (cañerías)
    "puntoraya": (0.25, (9.0, 1.5, 0.5, 1.5)),                      # ISO 128 tipo 04, ejes
    "bandeja": (0.35, (9.0, 1.5, 0.5, 1.5, 0.5, 1.5)),              # ISO 128 tipo 05, trazo largo con dos puntos (bandeja eléctrica)
    "muy_fina": (0.18, None),                                       # PAT 140: detalles de los símbolos
    "pasillo": (0.25, (6.0, 3.0)),                                  # PAT 140: demarcación de pasillos en el piso
}
_ALFABETO_CAP = 0.72     # altura de mayúscula de Helvetica / tamaño de fuente


def _txt(v, d=1) -> str:
    return escribir(v, d)


def _ancho(texto: str, h: float) -> float:
    """Ancho en mm de un texto de altura de mayúscula h (Helvetica). Con reportlab se mide; si no, 0,55 em por carácter."""
    em = h / _ALFABETO_CAP
    try:
        from reportlab.pdfbase.pdfmetrics import stringWidth
        return stringWidth(texto, "Helvetica", em)
    except Exception:
        return 0.55 * em * len(texto)


def _ajustar(texto: str, w: float, hmax: float, hmin: float, max_lineas: int, alto_disp: float) -> tuple[list[str], float]:
    """Ajusta el texto a w mm: primero una línea (reduciendo la altura hasta 2,6 mm o hmin), luego varias líneas que quepan en alto_disp
    mm; si no alcanza, corta con «...»."""
    texto = str(texto)
    h = hmax
    h1 = max(hmin, min(hmax, 2.6))
    while h >= h1 - 1e-9:
        if _ancho(texto, h) <= w and h * 1.3 <= alto_disp + 1e-9:
            return [texto], h
        h -= 0.25
    h = hmax
    while max_lineas > 1:
        lineas, actual = [], ""
        for pal in texto.split():
            prueba = (actual + " " + pal).strip()
            if _ancho(prueba, h) <= w or not actual:
                actual = prueba
            else:
                lineas.append(actual); actual = pal
        lineas.append(actual)
        if all(_ancho(x, h) <= w for x in lineas) and len(lineas) <= max_lineas and len(lineas) * h * 1.3 <= alto_disp + 1e-9:
            return lineas, h
        if h - 0.25 < hmin:
            break
        h -= 0.25
    h = hmin
    s = texto
    while len(s) > 1 and _ancho(s + "...", h) > w:
        s = s[:-1]
    return [s.rstrip() + "..." if s != texto else s], h


class _Dib:
    """Lista de primitivas en mm de papel (y hacia arriba)."""

    def __init__(self):
        self.prims: list[dict] = []

    def linea(self, capa, tl, x1, y1, x2, y2):
        self.prims.append(dict(k="poly", capa=capa, tl=tl, pts=[(x1, y1), (x2, y2)], cerrada=False))

    def poli(self, capa, tl, pts, cerrada=False):
        self.prims.append(dict(k="poly", capa=capa, tl=tl, pts=[(float(a), float(b)) for a, b in pts], cerrada=cerrada))

    def rect(self, capa, tl, x0, y0, x1, y1):
        self.poli(capa, tl, [(x0, y0), (x1, y0), (x1, y1), (x0, y1)], True)

    def circulo(self, capa, tl, cx, cy, r):
        self.prims.append(dict(k="circle", capa=capa, tl=tl, c=(cx, cy), r=r))

    def texto(self, capa, x, y, s, h, anc="l", rot=0):
        if s != "":
            self.prims.append(dict(k="text", capa=capa, x=x, y=y, s=str(s), h=h, anc=anc, rot=rot))

    def solido(self, capa, pts):
        self.prims.append(dict(k="solid", capa=capa, pts=[(float(a), float(b)) for a, b in pts]))


# ------------------------------------------------------------------------------------------- cajetín
def cajetin(titulo: str = "Plano de disposición general en planta", proyecto: str = "PAT 136", escala: str = "1:100", formato: str = "A3",
            fecha: str | None = None, numero_plano: str = "PAT136-LAY-001", revision: str = "A", hoja: str = "1/1",
            autor: str | None = None) -> dict:
    """Campos del cajetín según ISO 7200:2004. Propietario legal = institución; creador = autor (el nombre escrito en Desafío o
    «(nombre del estudiante)»); persona que aprueba = revisor."""
    if fecha is None:
        fecha = datetime.date.today().strftime("%d-%m-%Y")
    autor = " ".join(str(autor or "").split()) or AUTOR
    return dict(titulo=titulo, proyecto=proyecto, autor=autor, revisor=REVISOR, institucion=INSTITUCION, fecha=fecha, escala=escala,
                numero_plano=numero_plano, revision=revision, unidad=UNIDAD, proyeccion=PROYECCION, formato=formato, hoja=hoja,
                tipo_documento=TIPO_DOCUMENTO)


_FILAS_CAJETIN = (   # (alto mm, [(etiqueta, campo, ancho mm)])
    (14.0, [("Título", "titulo", 110.0), ("Número de plano", "numero_plano", 40.0), ("Revisión", "revision", 30.0)]),
    (14.0, [("Proyecto", "proyecto", 110.0), ("Escala", "escala", 40.0), ("Formato", "formato", 30.0)]),
    (12.0, [("Autor (creador)", "autor", 60.0), ("Revisor (aprueba)", "revisor", 60.0), ("Fecha de emisión", "fecha", 30.0), ("Hoja", "hoja", 30.0)]),
    (12.0, [("Institución (propietario legal)", "institucion", 90.0), ("Tipo de documento", "tipo_documento", 90.0)]),
    (10.0, [("Unidad de las cotas", "unidad", 40.0), ("Método de proyección", "proyeccion", 140.0)]),
)
ALTO_CAJETIN = sum(f[0] for f in _FILAS_CAJETIN)


def _dibujar_cajetin(d: _Dib, campos: dict, x1: float, y0: float) -> float:
    """Dibuja el cajetín con su esquina inferior derecha en (x1, y0); devuelve la x de su borde izquierdo."""
    xi = x1 - ANCHO_CAJETIN
    y = y0 + ALTO_CAJETIN
    for alto, celdas in _FILAS_CAJETIN:
        x = xi
        for etiqueta, campo, w in celdas:
            d.rect("MARCO", "media", x, y - alto, x + w, y)
            d.texto("TEXTOS", x + 1.2, y - 2.9, etiqueta, 1.8)
            lineas, h = _ajustar(campos.get(campo, ""), w - 2.4, 3.5, 1.8, 2, alto - 4.2)
            hb = len(lineas) * h * 1.3
            yb = y - 4.2 - (alto - 4.2 - hb) / 2 - h * 1.05          # primera línea base, centrada en el espacio bajo la etiqueta
            for i, ln in enumerate(lineas):
                d.texto("TEXTOS", x + 1.2, yb - i * h * 1.3, ln, h)
            x += w
        y -= alto
    d.rect("MARCO", "marco", xi, y0, x1, y0 + ALTO_CAJETIN)
    return xi


# ------------------------------------------------------------------------------------------- marco y zonas (ISO 5457)
def _dibujar_marco(d: _Dib, W: float, H: float, formato: str):
    fx0, fy0, fx1, fy1 = MARGEN_IZQ, MARGEN, W - MARGEN, H - MARGEN
    d.rect("MARCO", "marco", fx0, fy0, fx1, fy1)
    # marcas de centrado: parten en el borde de la hoja y entran 10 mm del marco
    d.linea("MARCO", "marco", 0, H / 2, fx0 + 10, H / 2)
    d.linea("MARCO", "marco", W, H / 2, fx1 - 10, H / 2)
    d.linea("MARCO", "marco", W / 2, 0, W / 2, fy0 + 10)
    d.linea("MARCO", "marco", W / 2, H, W / 2, fy1 - 10)
    nl, nc = ZONAS[formato]
    cx, cy = W / 2, H / 2

    def limites(centro, n, largo):
        b = [centro + 50.0 * j for j in range(-(n // 2 - 1), n // 2)]
        return [0.0] + b + [largo]
    bx, by = limites(cx, nl, W), limites(cy, nc, H)
    for x in bx[1:-1]:           # divisiones verticales: números arriba y abajo
        d.linea("MARCO", "fina", x, fy1, x, H); d.linea("MARCO", "fina", x, 0, x, fy0)
    for y in by[1:-1]:           # divisiones horizontales: letras a izquierda y derecha
        d.linea("MARCO", "fina", 0, y, fx0, y); d.linea("MARCO", "fina", fx1, y, W, y)
    for i in range(nl):
        xm = (bx[i] + bx[i + 1]) / 2
        d.texto("MARCO", xm, H - 7.2, str(i + 1), 3.5, "c"); d.texto("MARCO", xm, 3.7, str(i + 1), 3.5, "c")
    for j in range(nc):
        ym = (by[nc - j - 1] + by[nc - j]) / 2 - 1.25           # A arriba
        d.texto("MARCO", 10.0, ym, LETRAS_EJES[j], 3.5, "c"); d.texto("MARCO", W - 5.0, ym, LETRAS_EJES[j], 3.5, "c")
    # designación del formato en el lado derecho del margen inferior
    d.texto("MARCO", fx1, 3.7, formato, 3.5, "r")
    return fx0, fy0, fx1, fy1


# ------------------------------------------------------------------------------------------- geometría del layout
def _extension(lay: dict, plano: dict | None = None) -> dict | None:
    """Huellas de los equipos (y de la sala eléctrica) en m y extensión del dibujo, o None si la planta está vacía.
    PAT 140: la extensión es la del sitio del plano detallado (nave, anexos, patio y cerco perimetral)."""
    pos, dims = (lay or {}).get("posiciones") or {}, (lay or {}).get("dims") or {}
    huellas = {k: LY.huella(p, dims[k]) for k, p in pos.items() if k in dims}
    red = (lay or {}).get("red") or {}
    ccm = None
    if huellas and red.get("ccm") and red.get("ccm_dim"):
        ccm = LY.huella(red["ccm"], red["ccm_dim"])
    if not huellas:
        return None
    plano = plano if (plano and not plano.get("vacio")) else PD.construir(lay)
    x0, y0, x1, y1 = plano["sitio"]
    return dict(huellas=huellas, ccm=ccm, x0=x0, y0=y0, x1=x1, y1=y1, plano=plano)


def _altura_texto(formato: str) -> float:
    return 2.5 if formato == "A3" else 3.5


def _modulo(f: float, r_burbuja: float) -> float:
    """Menor módulo de grilla (m) cuyo espaciamiento en papel deja espacio a las burbujas."""
    for m in MODULOS_GRILLA:
        if m * f >= 1.5 * (2 * r_burbuja + 4):
            return m
    return MODULOS_GRILLA[-1]


def _geom_hoja(formato: str) -> dict:
    W, H = FORMATOS[formato]
    th = _altura_texto(formato)
    fila = th * 2.0
    strip = INSET + 5 * fila + 4
    px0, px1 = MARGEN_IZQ + INSET, W - MARGEN - ANCHO_CAJETIN - 5
    py0, py1 = MARGEN + strip, H - MARGEN - INSET
    paso = th * 2.6
    return dict(W=W, H=H, th=th, fila=fila, strip=strip, px0=px0, px1=px1, py0=py0, py1=py1, paso=paso,
                ml=14.0, mt=14.0, mr=3.6 * paso + 4, mb=3.6 * paso + 4, r_burbuja=4.0 if formato == "A3" else 5.0)


def _caja_grilla(ext: dict, escala: int, g: dict) -> dict:
    f = 1000.0 / escala
    M = _modulo(f, g["r_burbuja"])
    gx0, gx1 = math.floor(ext["x0"] / M + 1e-9) * M, math.ceil(ext["x1"] / M - 1e-9) * M
    gy0, gy1 = math.floor(ext["y0"] / M + 1e-9) * M, math.ceil(ext["y1"] / M - 1e-9) * M
    if gx1 - gx0 < M:
        gx1 = gx0 + M
    if gy1 - gy0 < M:
        gy1 = gy0 + M
    need_w = (gx1 - gx0) * f + g["ml"] + g["mr"]
    need_h = (gy1 - gy0) * f + g["mt"] + g["mb"]
    cabe = need_w <= g["px1"] - g["px0"] + 1e-9 and need_h <= g["py1"] - g["py0"] + 1e-9
    return dict(f=f, M=M, gx0=gx0, gx1=gx1, gy0=gy0, gy1=gy1, need_w=need_w, need_h=need_h, cabe=cabe)


def escala_automatica(lay: dict, formato: str = "A3", plano: dict | None = None) -> tuple[int, bool]:
    """Menor denominador de la serie ISO 5455 (1:50, 1:100, 1:200, 1:500) con que la planta cabe en el área útil de la lámina.
    Devuelve (denominador, cabe); si ni 1:500 sirve, usa 1:1000 de respaldo."""
    ext = _extension(lay, plano)
    if ext is None:
        return 100, True
    g = _geom_hoja(formato)
    for e in ESCALAS:
        if _caja_grilla(ext, e, g)["cabe"]:
            return e, True
    return ESCALA_RESPALDO, _caja_grilla(ext, ESCALA_RESPALDO, g)["cabe"]


# ------------------------------------------------------------------------------------------- cotas (ISO 129-1)
def _trazo45(d, capa, x, y, t=1.4):
    d.linea(capa, "media", x - t, y - t, x + t, y + t)


def _flecha(d, capa, x, y, dx, dy, L=3.0, a=0.5):
    """Flecha rellena con la punta en (x, y) y la cola hacia (-dx, -dy) (unitario)."""
    bx, by = x - dx * L, y - dy * L
    d.solido(capa, [(x, y), (bx - dy * a, by + dx * a), (bx + dy * a, by - dx * a), (bx + dy * a, by - dx * a)])


def _cota_h(d, x1, x2, y, texto, th, ext_desde=None, flechas=False):
    """Cota horizontal: línea fina con trazos oblicuos o flechas, líneas de referencia y texto sobre la línea."""
    if ext_desde is not None:
        for x in (x1, x2):
            d.linea("COTAS", "fina", x, ext_desde - 1.0, x, y - 2.0)
    d.linea("COTAS", "fina", x1, y, x2, y)
    if flechas:
        _flecha(d, "COTAS", x1, y, -1, 0); _flecha(d, "COTAS", x2, y, 1, 0)
    else:
        _trazo45(d, "COTAS", x1, y); _trazo45(d, "COTAS", x2, y)
    if texto and _ancho(texto, th) + 1.0 <= abs(x2 - x1):
        d.texto("COTAS", (x1 + x2) / 2, y + 1.0, texto, th, "c")
        return True
    return not texto


def _cota_v(d, y1, y2, x, texto, th, ext_desde=None, flechas=False):
    """Cota vertical (texto girado 90°, a la izquierda de la línea)."""
    if ext_desde is not None:
        for y in (y1, y2):
            d.linea("COTAS", "fina", ext_desde + 1.0, y, x + 2.0, y)
    d.linea("COTAS", "fina", x, y1, x, y2)
    if flechas:
        _flecha(d, "COTAS", x, y1, 0, -1); _flecha(d, "COTAS", x, y2, 0, 1)
    else:
        _trazo45(d, "COTAS", x, y1); _trazo45(d, "COTAS", x, y2)
    if texto and _ancho(texto, th) + 1.0 <= abs(y2 - y1):
        d.texto("COTAS", x - 1.0, (y1 + y2) / 2 - _ancho(texto, th) / 2, texto, th, "l", 90)
        return True
    return not texto


def _agrupar(valores: list[float], tol: float = 0.05) -> list[float]:
    out: list[float] = []
    for v in sorted(valores):
        if not out or v - out[-1] > tol:
            out.append(v)
    return out


# ------------------------------------------------------------------------------------------- generación de la lámina
def generar_lamina(lay: dict | None, nombres: dict | None = None, formato: str = "A3", escala: int | str | None = None,
                   proyecto: str = "PAT 136", titulo: str = "Plano de disposición general en planta", fecha: str | None = None,
                   numero_plano: str = "PAT136-LAY-001", revision: str = "A", plano: dict | None = None, modo: str = "plano",
                   capas: set | None = None, autor: str | None = None) -> dict:
    """Arma la lámina del layout. lay es el dict de motor.layout.estado_layout (posiciones, dims, filas, red); nombres, {tag: nombre}.
    escala: None o «auto» (la elige escala_automatica) o un denominador de la serie ISO 5455. Devuelve el modelo con las primitivas
    (en mm de papel), el cajetín, los avisos y los datos de la lista de equipos. Planta vacía: lámina con marco y cajetín y un aviso."""
    formato = formato if formato in FORMATOS else "A3"
    avisos: list[str] = []
    if lay and (lay.get("posiciones") or {}) and (plano is None or plano.get("vacio")):
        plano = PD.construir(lay, nombres, proyecto=proyecto)                       # PAT 140: plano detallado
    ext = _extension(lay, plano)
    g = _geom_hoja(formato)
    W, H, th = g["W"], g["H"], g["th"]
    d = _Dib()
    fx0, fy0, fx1, fy1 = _dibujar_marco(d, W, H, formato)

    E = 100
    cabe = True
    if ext is not None:
        auto, cabe_auto = escala_automatica(lay, formato, plano)
        pedida = None
        if escala not in (None, "auto", "Automática", ""):
            try:
                pedida = int(str(escala).replace("1:", "").strip())
            except ValueError:
                avisos.append(f"Escala «{escala}» no válida; se usa la automática.")
        if pedida is not None and pedida not in ESCALAS + (ESCALA_RESPALDO,):
            avisos.append(f"La escala 1:{pedida} no está en la serie 1:50, 1:100, 1:200 y 1:500 (ISO 5455); se usa la automática.")
            pedida = None
        if pedida is not None and not _caja_grilla(ext, pedida, g)["cabe"]:
            avisos.append(f"La planta no cabe en {formato} a 1:{pedida}; se usa 1:{auto}.")
            pedida = None
        E = pedida or auto
        cabe = _caja_grilla(ext, E, g)["cabe"]
        if not cabe:
            avisos.append(f"La planta no cabe en {formato} ni a 1:{E}; use un formato mayor.")
        elif E == ESCALA_RESPALDO:
            avisos.append("La planta solo cabe a 1:1000, fuera de la serie 1:50 a 1:500; conviene un formato mayor.")
    else:
        avisos.append("La planta está vacía: no hay equipos que dibujar. Agregue equipos en Diseño y proponga el layout.")

    campos = cajetin(titulo, proyecto, f"1:{E}" if ext is not None else "Sin escala", formato, fecha, numero_plano, revision, autor=autor)
    cajx0 = _dibujar_cajetin(d, campos, fx1, fy0)
    lista = []
    if ext is None:
        d.texto("TEXTOS", (g["px0"] + g["px1"]) / 2, (g["py0"] + g["py1"]) / 2, "Planta vacía: sin equipos", th * 1.4, "c")
        return _modelo(d, formato, E, campos, avisos, lista, None, cabe, modo)

    cg = _caja_grilla(ext, E, g)
    f, M = cg["f"], cg["M"]
    # el recuadro de la grilla se centra en el área útil
    ancho_g, alto_g = (cg["gx1"] - cg["gx0"]) * f, (cg["gy1"] - cg["gy0"]) * f
    area_x0, area_x1 = g["px0"] + g["ml"], g["px1"] - g["mr"]
    area_y0, area_y1 = g["py0"] + g["mb"], g["py1"] - g["mt"]
    ox = area_x0 + (area_x1 - area_x0 - ancho_g) / 2
    oy = area_y0 + (area_y1 - area_y0 - alto_g) / 2

    def X(x):
        return ox + (x - cg["gx0"]) * f

    def Y(y):
        return oy + (y - cg["gy0"]) * f

    # --- ejes de grilla de columnas con burbujas: números en x (arriba) y letras en y (izquierda)
    r = g["r_burbuja"]
    pd_ = ext["plano"]
    # PAT 140: los ejes son los de las columnas de la nave (marcos cada 6 m); si a esta escala quedan muy juntos para las
    # burbujas, se rotula uno de cada n
    paso_e = max(1, int(math.ceil((2 * r + 1.0) / max(1e-9, PD.VANO_M * f))))
    xs = pd_["ejes_x"][::paso_e] if pd_["ejes_x"][-1] in pd_["ejes_x"][::paso_e] else pd_["ejes_x"][::paso_e] + [pd_["ejes_x"][-1]]
    ys = pd_["ejes_y"]

    def letra(i):
        n = len(LETRAS_EJES)
        return LETRAS_EJES[i] if i < n else LETRAS_EJES[i // n - 1] + LETRAS_EJES[i % n]
    for x in xs:
        i = pd_["ejes_x"].index(x)
        d.linea("EJES", "puntoraya", X(x), Y(cg["gy0"]) - 3.0, X(x), Y(cg["gy1"]) + 5.0)
        d.circulo("EJES", "fina", X(x), Y(cg["gy1"]) + 5.0 + r, r)
        d.texto("EJES", X(x), Y(cg["gy1"]) + 5.0 + r - th * 0.36, str(i + 1), th, "c")
    for j, y in enumerate(ys):
        d.linea("EJES", "puntoraya", X(cg["gx0"]) - 5.0, Y(y), X(cg["gx1"]) + 3.0, Y(y))
        d.circulo("EJES", "fina", X(cg["gx0"]) - 5.0 - r, Y(y), r)
        d.texto("EJES", X(cg["gx0"]) - 5.0 - r, Y(y) - th * 0.36, letra(j), th, "c")

    # --- PAT 140: plano detallado (sitio, edificio, pasillos, zonas de mantención, símbolos, cañerías y bandeja) en mm de papel
    textos_detalle = _dibujar_detalle(d, pd_, X, Y, f, modo, capas)
    # --- equipos (contorno grueso), eje de centro y tag
    def caja(capa, tag, h):
        x0, y0, x1, y1 = X(h[0]), Y(h[1]), X(h[2]), Y(h[3])       # PAT 140: el contorno ya va en el símbolo del equipo
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        d.linea("EJES", "fina", cx - 1.2, cy, cx + 1.2, cy); d.linea("EJES", "fina", cx, cy - 1.2, cx, cy + 1.2)
        w, hh = x1 - x0, y1 - y0
        ht = th
        while ht > 1.8 and _ancho(tag, ht) + 1.0 > w:
            ht -= 0.25
        if _ancho(tag, ht) + 1.0 <= w and ht + 1.0 <= hh:
            d.texto("TEXTOS", cx, cy + 1.2, tag, ht, "c")
        elif _ancho(tag, th) + 1.0 <= hh and th + 1.0 <= w:
            d.texto("TEXTOS", cx - 1.2, cy - _ancho(tag, th) / 2, tag, th, "l", 90)
        else:
            d.texto("TEXTOS", cx, y1 + 1.0, tag, min(th, 2.2), "c")
    if capas is None or "EQUIPOS" in capas:
        for k, h in ext["huellas"].items():
            caja("EQUIPOS", k, h)
        if ext["ccm"]:
            caja("ELECTRICO", LY.ID_CCM, ext["ccm"])
    _textos_sin_choque(d, textos_detalle)

    # --- cotas: tres niveles abajo (ejes de equipos, entre ejes de grilla, total) y a la derecha
    xb = Y(cg["gy0"])
    lv = [xb - 1.4 * g["paso"], xb - 2.5 * g["paso"], xb - 3.6 * g["paso"]]
    ex = [h[0] for h in ext["huellas"].values()] + [h[2] for h in ext["huellas"].values()]
    cx_eq = _agrupar([(h[0] + h[2]) / 2 for h in list(ext["huellas"].values()) + ([ext["ccm"]] if ext["ccm"] else [])])
    cy_eq = _agrupar([(h[1] + h[3]) / 2 for h in list(ext["huellas"].values()) + ([ext["ccm"]] if ext["ccm"] else [])])
    omitidas = 0
    for a, b in zip(cx_eq, cx_eq[1:]):
        omitidas += not _cota_h(d, X(a), X(b), lv[0], _txt(b - a, 1), th, ext_desde=Y(ext["y0"]))
    for a, b in zip(xs, xs[1:]):
        _cota_h(d, X(a), X(b), lv[1], _txt(b - a, 1 if M != int(M) else 0), th, ext_desde=Y(cg["gy0"]))
    _cota_h(d, X(ext["x0"]), X(ext["x1"]), lv[2], _txt(ext["x1"] - ext["x0"], 1), th, ext_desde=Y(ext["y0"]), flechas=True)
    xr = X(cg["gx1"])
    lh = [xr + 1.4 * g["paso"], xr + 2.5 * g["paso"], xr + 3.6 * g["paso"]]
    for a, b in zip(cy_eq, cy_eq[1:]):
        omitidas += not _cota_v(d, Y(a), Y(b), lh[0], _txt(b - a, 1), th, ext_desde=X(ext["x1"]))
    for a, b in zip(ys, ys[1:]):
        _cota_v(d, Y(a), Y(b), lh[1], _txt(b - a, 1 if M != int(M) else 0), th, ext_desde=X(cg["gx1"]))
    _cota_v(d, Y(ext["y0"]), Y(ext["y1"]), lh[2], _txt(ext["y1"] - ext["y0"], 1), th, ext_desde=X(ext["x1"]), flechas=True)
    if omitidas:
        avisos.append(f"{omitidas} cotas entre ejes de equipos no caben a esta escala; las coordenadas de cada eje están en la lista de equipos.")

    # --- franja inferior: barra de escala, leyenda de tipos de línea, norte y notas
    ys0 = fy0 + INSET
    notas = ("Cotas en m; x al este, y al norte", "Línea: corriente-DN-servicio")
    tope = 60.0 if formato == "A3" else 100.0
    col2 = max(tope + 14.0, max(_ancho(t, th) for t in notas) + 6.0)
    _barra_escala(d, g["px0"], ys0 + 3 * g["fila"], f, th, formato)
    for i, t in enumerate(notas):
        d.texto("TEXTOS", g["px0"], ys0 + 1.0 + i * g["fila"], t, th)
    fin = _leyenda(d, g["px0"] + col2, ys0 + 5 * g["fila"] - g["fila"] * 0.7, g, th)
    _norte(d, min(fin + 12.0, g["px1"] - 8.0), ys0 + 9.0, th)

    # --- lista de equipos
    lista = _lista_equipos(lay, nombres or {}, ext)
    av = _dibujar_tabla(d, lista, cajx0, fx1, fy0 + ALTO_CAJETIN + 4.0, fy1 - INSET, g)
    avisos += av
    avisos += [a for a in pd_.get("avisos", []) if a not in avisos]
    return _modelo(d, formato, E, campos, avisos, lista, dict(cg, ox=ox, oy=oy, xs=xs, ys=ys), cabe, modo)


def _modelo(d: _Dib, formato, E, campos, avisos, lista, grilla, cabe, modo="plano") -> dict:
    W, H = FORMATOS[formato]
    return dict(formato=formato, ancho_mm=W, alto_mm=H, escala=E, escala_txt=f"1:{E}", cajetin=campos, prims=d.prims, avisos=avisos, modo=modo,
                equipos=lista, grilla=grilla, cabe=cabe, vacia=grilla is None,
                marco=(MARGEN_IZQ, MARGEN, W - MARGEN, H - MARGEN))


def _barra_escala(d, x, y, f, th, formato):
    """Barra de escala gráfica: tramos alternados, rótulos 0, mitad y total en m."""
    tope = 60.0 if formato == "A3" else 100.0
    for N in (200, 100, 50, 20, 10, 5, 2, 1, 0.5):
        if N * f <= tope:
            break
    n = 4
    L = N * f
    d.texto("TEXTOS", x, y + 5.5, f"Escala gráfica ({_txt(N, 0 if N == int(N) else 1)} m)", th)
    for i in range(n):
        x0 = x + i * L / n
        d.rect("COTAS", "fina", x0, y, x0 + L / n, y + 1.8)
        if i % 2 == 0:
            d.solido("COTAS", [(x0, y), (x0 + L / n, y), (x0 + L / n, y + 1.8), (x0, y + 1.8)])
    for frac, rot in ((0, "0"), (0.5, _txt(N / 2, 0 if (N / 2) == int(N / 2) else 1)), (1, _txt(N, 0 if N == int(N) else 1) + " m")):
        d.texto("COTAS", x + frac * L, y - th - 0.8, rot, th, "c" if frac < 1 else "c")


def _leyenda(d, x, ytop, g, th):
    items = (("EQUIPOS", "gruesa", "Equipos (contorno visible)"), ("CANERIAS", "fina", "Cañerías (doble línea a escala del DN)"),
             ("ELECTRICO", "bandeja", "Bandeja eléctrica"), ("MANTENCION", "trazos", "Zona de mantención"),
             ("EJES", "puntoraya", "Ejes de columnas"))
    fin = x
    for i, (capa, tl, txt) in enumerate(items):
        y = ytop - i * g["fila"]
        d.linea(capa, tl, x, y + th * 0.36, x + 18.0, y + th * 0.36)
        d.texto("TEXTOS", x + 21.0, y, txt, th)
        fin = max(fin, x + 21.0 + _ancho(txt, th))
    return fin


def _norte(d, cx, cy, th):
    d.circulo("COTAS", "fina", cx, cy, 6.0)
    d.solido("COTAS", [(cx, cy + 6.0), (cx - 2.2, cy - 3.0), (cx, cy - 1.2), (cx + 2.2, cy - 3.0)])
    d.texto("COTAS", cx, cy + 7.5, "N", th * 1.2, "c")


# ------------------------------------------------------------------------------------------- lista de equipos
_COLS = (("Tag", 16.0, "l"), ("Nombre", 58.0, "l"), ("Largo", 19.0, "r"), ("Ancho", 19.0, "r"), ("Alto", 19.0, "r"),
         ("X", 19.0, "r"), ("Y", 18.0, "r"))


def _lista_equipos(lay: dict, nombres: dict, ext: dict) -> list[dict]:
    out = []
    for k, h in ext["huellas"].items():
        dm = lay["dims"][k]
        out.append(dict(tag=k, nombre=str(nombres.get(k, k)), largo=dm["largo"], ancho=dm["ancho"], alto=dm["alto"],
                        x=(h[0] + h[2]) / 2, y=(h[1] + h[3]) / 2))
    if ext["ccm"]:
        dc = (lay.get("red") or {}).get("ccm_dim") or {}
        h = ext["ccm"]
        out.append(dict(tag=LY.ID_CCM, nombre="Sala eléctrica (CCM)", largo=dc.get("largo", 0.0), ancho=dc.get("ancho", 0.0),
                        alto=dc.get("alto", 0.0), x=(h[0] + h[2]) / 2, y=(h[1] + h[3]) / 2))
    return out


def _dibujar_tabla(d: _Dib, lista: list[dict], xi: float, fx1: float, y_base: float, y_tope: float, g: dict) -> list[str]:
    """Tabla de tags, nombre y dimensiones sobre el cajetín, ajustada al alto disponible (reduce la fila; si no cabe, avisa)."""
    th = g["th"]
    avisos = []
    n = len(lista)
    disp = y_tope - y_base
    fila = th * 2.0
    min_fila, min_th = th * 1.45, max(1.8, th * 0.72)
    filas_tot = n + 2                                  # título de la tabla y encabezado
    while filas_tot * fila > disp and fila > min_fila + 1e-9:
        fila -= 0.1
    hh = max(min_th, min(th, fila / 2.0))
    cabe_n = int(disp // fila) - 2
    mostrar = lista
    if cabe_n < n:
        mostrar = lista[:max(0, cabe_n - 1)]
        avisos.append(f"La lista de equipos no cabe completa en la lámina: se muestran {len(mostrar)} de {n}; use un formato mayor.")
    total_filas = len(mostrar) + 2 + (1 if cabe_n < n else 0)
    ytop = y_base + total_filas * fila
    xs = [xi]
    for _, w, _a in _COLS:
        xs.append(xs[-1] + w)
    d.texto("TEXTOS", xi, ytop - fila * 0.72, "Lista de equipos (dimensiones y coordenadas del centro, en m)", th * 1.1)
    y = ytop - fila
    d.rect("MARCO", "media", xi, y - fila, xs[-1], y)
    for (nom, w, al), x0 in zip(_COLS, xs):
        _celda(d, nom, x0, w, y - fila, fila, al, hh, True)
    y -= fila
    for e in mostrar:
        vals = [e["tag"], e["nombre"], _txt(e["largo"], 1), _txt(e["ancho"], 1), _txt(e["alto"], 1), _txt(e["x"], 1), _txt(e["y"], 1)]
        d.rect("MARCO", "fina", xi, y - fila, xs[-1], y)
        for (nom, w, al), x0, v in zip(_COLS, xs, vals):
            _celda(d, v, x0, w, y - fila, fila, al, hh, False)
        y -= fila
    if cabe_n < n:
        d.rect("MARCO", "fina", xi, y - fila, xs[-1], y)
        d.texto("TEXTOS", xi + 1.2, y - fila / 2 - hh * 0.36, f"... y {n - len(mostrar)} equipos más (ver pantalla)", hh)
        y -= fila
    for x0 in xs:
        d.linea("MARCO", "fina", x0, y, x0, ytop - fila)
    return avisos


def _celda(d, texto, x0, w, y0, fila, alin, h, enc):
    lineas, hh = _ajustar(texto, w - 2.0, h, 1.6, 1, fila)
    t = lineas[0]
    yb = y0 + (fila - hh * 0.72) / 2
    if alin == "r":
        d.texto("TEXTOS", x0 + w - 1.0, yb, t, hh, "r")
    else:
        d.texto("TEXTOS", x0 + 1.0, yb, t, hh, "l")


# ------------------------------------------------------------------------------------------- control de calidad
def _caja_texto(p: dict) -> tuple[float, float, float, float]:
    w, h = _ancho(p["s"], p["h"]), p["h"]
    x, y = p["x"], p["y"]
    if p["anc"] == "c":
        x0, x1 = x - w / 2, x + w / 2
    elif p["anc"] == "r":
        x0, x1 = x - w, x
    else:
        x0, x1 = x, x + w
    if p.get("rot", 0) == 90:                      # texto girado 90° antihorario: crece hacia +y y la altura va hacia -x
        return (x - h, y + (x0 - x), x, y + (x1 - x))
    return (x0, y, x1, y + h)


def fuera_del_marco(modelo: dict, tol: float = 0.05) -> list[dict]:
    """Primitivas que no son del marco y se salen del recuadro de la hoja (ISO 5457)."""
    x0, y0, x1, y1 = modelo["marco"]
    malos = []
    for p in modelo["prims"]:
        if p["capa"] == "MARCO":
            continue
        if p["k"] == "text":
            bx0, by0, bx1, by1 = _caja_texto(p)
        elif p["k"] == "circle":
            bx0, by0, bx1, by1 = p["c"][0] - p["r"], p["c"][1] - p["r"], p["c"][0] + p["r"], p["c"][1] + p["r"]
        else:
            bx0, by0 = min(q[0] for q in p["pts"]), min(q[1] for q in p["pts"])
            bx1, by1 = max(q[0] for q in p["pts"]), max(q[1] for q in p["pts"])
        if bx0 < x0 - tol or by0 < y0 - tol or bx1 > x1 + tol or by1 > y1 + tol:
            malos.append(p)
    return malos


def textos_superpuestos(modelo: dict, holgura: float = 0.0) -> list[tuple[str, str]]:
    """Pares de textos cuyas cajas se cruzan (excluye el marco y las zonas de referencia)."""
    ts = [(p, _caja_texto(p)) for p in modelo["prims"] if p["k"] == "text" and p["capa"] != "MARCO"]
    out = []
    for i, (a, A) in enumerate(ts):
        for b, B in ts[i + 1:]:
            if A[0] < B[2] - holgura and B[0] < A[2] - holgura and A[1] < B[3] - holgura and B[1] < A[3] - holgura:
                out.append((a["s"], b["s"]))
    return out


# ------------------------------------------------------------------------------------------- salidas
def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def a_svg(m: dict) -> str:
    """SVG de la lámina completa (mm de papel, y hacia abajo en pantalla)."""
    W, H = m["ancho_mm"], m["alto_mm"]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:g} {H:g}" width="{W:g}mm" height="{H:g}mm" '
         f'font-family="Helvetica, Arial, sans-serif">', f'<rect x="0" y="0" width="{W:g}" height="{H:g}" fill="#ffffff"/>']
    for p in m["prims"]:
        col = _color(m, p)
        if p["k"] == "poly":
            w, dash = TIPOS_LINEA[p["tl"]]
            pts = " ".join(f"{x:.2f},{H - y:.2f}" for x, y in p["pts"])
            da = f' stroke-dasharray="{" ".join(f"{v:g}" for v in dash)}"' if dash else ""
            tag = "polygon" if p["cerrada"] else "polyline"
            o.append(f'<{tag} points="{pts}" fill="none" stroke="{col}" stroke-width="{w:g}"{da} stroke-linejoin="miter"/>')
        elif p["k"] == "circle":
            w, _ = TIPOS_LINEA[p["tl"]]
            o.append(f'<circle cx="{p["c"][0]:.2f}" cy="{H - p["c"][1]:.2f}" r="{p["r"]:.2f}" fill="none" stroke="{col}" stroke-width="{w:g}"/>')
        elif p["k"] == "solid":
            pts = " ".join(f"{x:.2f},{H - y:.2f}" for x, y in p["pts"])
            o.append(f'<polygon points="{pts}" fill="{col}" stroke="none"/>')
        elif p["k"] == "text":
            anc = {"l": "start", "c": "middle", "r": "end"}[p["anc"]]
            em = p["h"] / _ALFABETO_CAP
            x, y = p["x"], H - p["y"]
            rot = f' transform="rotate({-p["rot"]} {x:.2f} {y:.2f})"' if p.get("rot") else ""
            o.append(f'<text x="{x:.2f}" y="{y:.2f}" font-size="{em:.2f}" text-anchor="{anc}" fill="{col}"{rot}>{_esc(p["s"])}</text>')
    o.append("</svg>")
    return "\n".join(o)


def a_pdf(m: dict) -> bytes:
    """PDF de una página con el tamaño de la lámina (reportlab)."""
    from reportlab.pdfgen import canvas
    from reportlab.lib.units import mm
    from reportlab.lib.colors import HexColor
    buf = io.BytesIO()
    W, H = m["ancho_mm"], m["alto_mm"]
    c = canvas.Canvas(buf, pagesize=(W * mm, H * mm))
    c.setTitle(f"{m['cajetin']['titulo']} - {m['cajetin']['numero_plano']}")
    c.setAuthor(m["cajetin"]["autor"]); c.setSubject(m["cajetin"]["proyecto"]); c.setCreator("pat_sim (PAT 136)")
    for p in m["prims"]:
        col = HexColor(_color(m, p))
        if p["k"] in ("poly", "circle"):
            w, dash = TIPOS_LINEA[p["tl"]]
            c.setStrokeColor(col); c.setLineWidth(w * mm); c.setLineCap(0); c.setLineJoin(0)
            c.setDash([v * mm for v in dash], 0) if dash else c.setDash([], 0)
            if p["k"] == "circle":
                c.circle(p["c"][0] * mm, p["c"][1] * mm, p["r"] * mm, stroke=1, fill=0)
            else:
                t = c.beginPath(); t.moveTo(p["pts"][0][0] * mm, p["pts"][0][1] * mm)
                for x, y in p["pts"][1:]:
                    t.lineTo(x * mm, y * mm)
                if p["cerrada"]:
                    t.close()
                c.drawPath(t, stroke=1, fill=0)
        elif p["k"] == "solid":
            c.setFillColor(col); c.setDash([], 0)
            t = c.beginPath(); t.moveTo(p["pts"][0][0] * mm, p["pts"][0][1] * mm)
            for x, y in p["pts"][1:]:
                t.lineTo(x * mm, y * mm)
            t.close(); c.drawPath(t, stroke=0, fill=1)
        elif p["k"] == "text":
            c.saveState(); c.setFillColor(col); c.setFont("Helvetica", p["h"] / _ALFABETO_CAP * mm)
            c.translate(p["x"] * mm, p["y"] * mm); c.rotate(p.get("rot", 0))
            {"l": c.drawString, "c": c.drawCentredString, "r": c.drawRightString}[p["anc"]](0, 0, p["s"])
            c.restoreState()
    c.showPage(); c.save()
    return buf.getvalue()


def a_dxf(m: dict) -> tuple[bytes | None, str]:
    """DXF de la lámina en capas y en metros de modelo (mm de papel x escala / 1000). Devuelve (bytes, «») o (None, aviso) si
    ezdxf no está instalado: la app no se rompe, solo no ofrece el DXF."""
    try:
        import ezdxf
        from ezdxf.enums import TextEntityAlignment
    except ImportError:
        return None, ("Falta la biblioteca ezdxf para generar el DXF: instálela con «pip install ezdxf» (está en requirements.txt) "
                      "y reinicie la aplicación. El PDF y el SVG se pueden descargar igual.")
    k = m["escala"] / 1000.0                       # m de modelo por mm de papel
    doc = ezdxf.new("R2010", setup=True)
    doc.units = 6                                  # INSUNITS = metros
    doc.header["$MEASUREMENT"] = 1
    for nombre, (_hex, aci) in CAPAS.items():
        doc.layers.add(nombre, color=aci)
    for nombre, (_w, dash) in TIPOS_LINEA.items():
        if not dash:
            continue
        pat = [sum(abs(v) for v in _alt(dash)) * k] + [v * k for v in _alt(dash)]
        try:
            doc.linetypes.add("PAT136_" + nombre.upper(), pattern=pat, description=f"PAT 136 {nombre}")
        except Exception:
            pass
    msp = doc.modelspace()
    for p in m["prims"]:
        at = dict(layer=p["capa"])
        if p.get("aci") and (m.get("modo") == "color" or p.get("color_fijo")):
            at["color"] = int(p["aci"])
        if p["k"] in ("poly", "circle"):
            w, dash = TIPOS_LINEA[p["tl"]]
            at["lineweight"] = int(round(w * 100))
            if dash:
                at["linetype"] = "PAT136_" + p["tl"].upper()
        if p["k"] == "poly":
            msp.add_lwpolyline([(x * k, y * k) for x, y in p["pts"]], close=p["cerrada"], dxfattribs=at)
        elif p["k"] == "circle":
            msp.add_circle((p["c"][0] * k, p["c"][1] * k), p["r"] * k, dxfattribs=at)
        elif p["k"] == "solid":
            q = [(x * k, y * k) for x, y in p["pts"]]
            while len(q) < 4:
                q.append(q[-1])
            msp.add_solid([q[0], q[1], q[3], q[2]], dxfattribs=at)    # PAT 140: el SOLID de DXF lleva los dos últimos vértices invertidos
        elif p["k"] == "text":
            t = msp.add_text(p["s"], height=p["h"] * k, rotation=p.get("rot", 0), dxfattribs=at)
            t.set_placement((p["x"] * k, p["y"] * k), align={"l": TextEntityAlignment.LEFT, "c": TextEntityAlignment.CENTER,
                                                              "r": TextEntityAlignment.RIGHT}[p["anc"]])
    doc.header["$LWDISPLAY"] = 1
    s = io.StringIO()
    doc.write(s)
    return s.getvalue().encode("utf-8"), ""


def _alt(dash):
    """Trazo ISO (largo, hueco, largo, hueco, ...) a patrón DXF: positivo = trazo, negativo = hueco, 0 = punto."""
    out = []
    for i, v in enumerate(dash):
        out.append((-1 if i % 2 else 1) * (0.0 if (i % 2 == 0 and v <= 0.5) else v))
    return out


# ------------------------------------------------------------------------------------------- PAT 140: plano detallado en la lámina
_TL = {"muro": "fina", "gruesa": "gruesa", "media": "media", "fina": "muy_fina", "mant": "trazos", "oculta": "trazos", "eje": "puntoraya",
       "bandeja": "bandeja", "pasillo": "pasillo", "cota": "fina"}
_CAPA_TXT = {"SITIO": "SITIO", "EDIFICIO": "EDIFICIO", "PASILLOS": "PASILLOS", "CANERIAS": "CANERIAS", "ELECTRICO": "ELECTRICO"}


def _color(m: dict, p: dict) -> str:
    """Color de la primitiva: en la vista de plano, negro (o gris en sitio, pasillos y mantención); a color, el del servicio o la capa."""
    if m.get("modo") == "color" or (p.get("color_fijo") and p.get("col")):   # PAT 140 i: los códigos de línea, siempre a color
        return p.get("col") or CAPAS[p["capa"]][0]
    return COLOR_PLANO if p["capa"] not in ("SITIO", "PASILLOS", "MANTENCION") else CAPAS[p["capa"]][0]


def _desplazar(pts, dist):
    """Polilínea ortogonal desplazada dist hacia la izquierda del sentido de avance (para la doble línea de las cañerías)."""
    if len(pts) < 2:
        return pts
    segs = []
    for a, b in zip(pts, pts[1:]):
        L = math.hypot(b[0] - a[0], b[1] - a[1]) or 1.0
        nx, ny = -(b[1] - a[1]) / L, (b[0] - a[0]) / L
        segs.append(((a[0] + nx * dist, a[1] + ny * dist), (b[0] + nx * dist, b[1] + ny * dist)))
    out = [segs[0][0]]
    for (a1, b1), (a2, b2) in zip(segs, segs[1:]):
        if abs(b1[0] - a1[0]) < 1e-9:          # tramo vertical seguido de horizontal (o al revés): esquina en (x de uno, y del otro)
            out.append((a1[0], a2[1]))
        elif abs(b1[1] - a1[1]) < 1e-9:
            out.append((a2[0], a1[1]))
        else:
            out.append(b1)
    out.append(segs[-1][1])
    return out


def _dibujar_detalle(d: _Dib, plano: dict, X, Y, f: float, modo: str, capas: set | None) -> list:
    """Pasa las primitivas del plano detallado (motor/plano_detalle.py) a mm de papel. Las cotas y los ejes los dibuja la lámina;
    los textos se devuelven para ponerlos al final, solo si miden 1,6 mm o más y no chocan con otro texto."""
    capas_ok = set(PD.CAPAS) - {"COTAS", "EJES", "TEXTOS"}
    if capas is not None:
        capas_ok &= set(capas)
    textos = []
    color = modo == "color"
    for q in PD.primitivas_mundo(plano, capas_ok):
        capa = q["capa"]
        col = None
        if color and q.get("s"):
            col = PD.SERVICIOS.get(q["s"], (None, None))[1]
        aci = ACI_SERVICIO.get(q.get("s")) if q.get("s") else None
        if q["k"] == "text":
            if q["h"] * f >= 1.6 and capa in _CAPA_TXT:
                textos.append(dict(q, _x=X(q["x"]), _y=Y(q["y"]), _h=q["h"] * f))
            continue
        if q["k"] == "circ":
            d.circulo(capa, _TL.get(q.get("e"), "fina"), X(q["c"][0]), Y(q["c"][1]), q["r"] * f)
        elif q["k"] == "tubo":
            pts = q["pts"]
            for s in (1, -1):
                d.poli(capa, "fina", [(X(a), Y(b)) for a, b in _desplazar(pts, s * q["w"] / 2)])
                if col or aci:
                    d.prims[-1].update(col=col, aci=aci)
        elif q["k"] == "poly":
            pts = [(X(a), Y(b)) for a, b in q["pts"]]
            if q.get("f") in ("muro", "cerco", "flecha") and q.get("cerr") and len(pts) in (3, 4):
                d.solido(capa, pts)
            else:
                d.poli(capa, _TL.get(q.get("e"), "fina"), pts, bool(q.get("cerr")))
        else:
            continue
        if col or aci:
            d.prims[-1].update(col=col, aci=aci)
    return textos


def _textos_sin_choque(d: _Dib, textos: list) -> None:
    """Agrega los textos del plano detallado que no chocan con los ya puestos (el control de calidad exige cero superposiciones)."""
    cajas = [_caja_texto(p) for p in d.prims if p["k"] == "text" and p["capa"] != "MARCO"]
    for q in textos:
        p = dict(k="text", capa=_CAPA_TXT[q["capa"]], x=q["_x"], y=q["_y"], s=q["s"], h=q["_h"], anc=q.get("anc", "c"), rot=q.get("rot", 0))
        if q.get("srv") in PD.SERVICIOS:                    # PAT 140 i: código de línea con el color de su servicio
            p.update(col=PD.SERVICIOS[q["srv"]][1], aci=ACI_SERVICIO.get(q["srv"]), color_fijo=True)
        c = _caja_texto(p)
        if any(c[0] < b[2] and b[0] < c[2] and c[1] < b[3] and b[1] < c[3] for b in cajas):
            continue
        cajas.append(c)
        d.prims.append(p)
