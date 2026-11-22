"""Plano de disposición en planta detallado (PAT 140, pedido del 19-11-2026: «layout más profesional con el tamaño de las máquinas,
flujos y tuberías, que se vea a detalle»).

No recalcula nada del layout (motor/layout.py): toma sus posiciones, dimensiones, corrientes, red eléctrica y sala eléctrica y arma
un modelo de dibujo en metros (x al este, y al norte) con:
1. Equipos a escala con su símbolo de vista superior según la forma (layout.forma): estanques, tolvas, evaporadores con un cuerpo por
   efecto, intercambiadores de carcasa con cabezales, bandas con rodillos, bombas con motor, calderas con quemador, llenadora con
   cabezales, trituradora y refinadora con su motor, y la zona de mantención punteada alrededor.
2. Cañerías, ductos y transportadores con ancho a escala según el DN, flecha de sentido, código de línea (corriente, DN y fluido) y
   color por servicio; recorrido ortogonal que rodea los equipos (búsqueda A* en una grilla de 0,5 m por los pasillos). Las bombas de
   línea que no están en el diagrama (P-1xx de Equipos auxiliares) van sobre su cañería con dos válvulas de bloqueo y una de retención.
3. Bandeja eléctrica desde la sala eléctrica (CCM) por los pasillos, con tramos compartidos.
4. Edificio: nave con muros, grilla de columnas con ejes (1, 2, 3 y A, B) y cotas, portones y puertas, pasillo peatonal y de grúa
   horquilla, sala de calderas, oficinas y baños, bodega de producto terminado, patio de camiones, estacionamientos, garita y cerco.
Los largos de cañería y de cable del costeo siguen saliendo de motor/layout.py (rack y bandeja); el recorrido dibujado es solo gráfico.

Salidas: fragmentos SVG para el componente del plano (ui/componentes/layout_planta), SVG completo para descargar (vista de plano en
blanco y negro tipo CAD o vista a color) y primitivas en metros que la lámina (motor/lamina.py) pasa a PDF y DXF por capas.
"""
from __future__ import annotations
import datetime
import heapq
import json
import math
from . import layout as LY
from .formato import escribir

# ------------------------------------------------------------------------------------------- supuestos del plano (PAT 140)
MURO_M = 0.25            # m; Supuesto: muro perimetral de hormigón armado o albañilería de 25 cm
TABIQUE_M = 0.15         # m; Supuesto: tabique de salas interiores (calderas, oficinas)
VANO_M = 6.0             # m; Supuesto: distancia entre marcos de una nave de acero (vano usual de 6 m)
LUZ_MAX_M = 36.0         # m; Supuesto: luz libre máxima de un marco de alma llena sin columnas interiores
COLUMNA_M = 0.40         # m; Supuesto: perfil de columna de 40 cm de lado
PASILLO_GRUA_M = 3.5     # m; pasillo de trabajo de una grúa horquilla contrapesada, 3,2 a 3,5 m (Mecalux, manual de almacenaje)
PORTON_CAMION_M = 5.0    # m; Supuesto: portón de recepción para un camión de 2,6 m de ancho con holgura
PORTON_GRUA_M = 3.5      # m; Supuesto: portón de grúa horquilla igual al pasillo
PUERTA_M = 1.0           # m; Supuesto: puerta peatonal y de salas
OFICINA_L, OFICINA_F = 16.0, 8.0      # m; Supuesto: oficinas, baños y vestidores para una dotación de un turno
BODEGA_F = 12.0          # m; Supuesto: fondo de la bodega de producto terminado (del orden de dos días de producción en pallets)
PATIO_F = 20.0           # m; Supuesto: fondo del patio de maniobra de camiones de 16,5 m (algo más que el largo del camión)
ESTAC_A, ESTAC_L = 2.5, 5.0           # m; estacionamiento de 2,5 x 5,0 m (OGUC, art. 2.4.2)
N_ESTAC = 10             # Supuesto: estacionamientos de la dotación administrativa
CERCO_M = 3.0            # m; Supuesto: franja libre entre las construcciones y el cerco perimetral
ACCESO_M = 8.0           # m; Supuesto: portón de acceso al predio para dos camiones
MANT_FRAC = 0.5          # Supuesto: zona de mantención = mitad del pasillo mínimo (dos zonas vecinas se tocan sin quitar pasillo)
CELDA_M = 0.5            # m; grilla del ruteo de cañerías y bandeja (igual al ajuste del arrastre)
V_VAPOR, RHO_VAPOR = 30.0, 5.15       # m/s y kg/m³; Supuesto: vapor saturado a 10 bar abs (IAPWS-IF97) a 30 m/s (rango 25 a 40 m/s)
H_ETIQ = 0.45            # m; alto del texto del código de los equipos
H_LINEA = 0.32           # m; alto del texto del código de línea

SUPUESTOS = (
    ("Zona de mantención", "Mitad del pasillo mínimo alrededor de cada equipo; en los intercambiadores de carcasa, además, el largo "
     "del haz en el extremo del cabezal para retirarlo (práctica de diseño de cañerías: espacio libre en ambos extremos)."),
    ("Nave", "Muro de 25 cm, marcos de acero cada 6 m y luz libre hasta 36 m; la nave envuelve los equipos con sus zonas de "
     "mantención, un pasillo peatonal perimetral igual al pasillo mínimo y un pasillo de grúa horquilla de 3,5 m (Mecalux, 3,2 a "
     "3,5 m para grúa contrapesada)."),
    ("Anexos", "Oficinas, baños y vestidores de 16 x 8 m; bodega de producto terminado de 12 m de fondo; patio de camiones de 20 m; "
     "10 estacionamientos de 2,5 x 5,0 m (OGUC, art. 2.4.2); cerco a 3 m de las construcciones."),
    ("Cañerías", "Recorrido gráfico ortogonal por los pasillos; el largo del costeo sigue siendo el del rack (motor/layout.py). DN "
     "de líquidos desde la red hidráulica; DN del vapor con 30 m/s y 5,15 kg/m³ (vapor saturado a 10 bar abs)."),
)

SERVICIOS = {   # servicio: (nombre en la leyenda, color de la vista a color, abreviatura del código de línea)
    "producto": ("Producto", "#1b7a5a", "PR"), "agua": ("Agua", "#2e86c1", "AG"), "vapor": ("Vapor", "#c0392b", "VA"),
    "condensado": ("Condensado", "#6c3fa0", "CO"), "aire": ("Aire y gases calientes", "#d9822b", "AI"),
    "electricidad": ("Electricidad (bandeja)", "#c9a10a", "EL"),
}
_SRV_TIPO = {"producto": "producto", "subproducto": "producto", "biomasa": "producto", "agua": "agua", "vapor": "vapor",
             "condensado": "condensado", "aire": "aire", "gas": "aire", "humos": "aire", "calor": "aire", "electricidad": "electricidad"}

CAPAS = ("SITIO", "EDIFICIO", "PASILLOS", "EJES", "MANTENCION", "EQUIPOS", "CANERIAS", "ELECTRICO", "TEXTOS", "COTAS")
GRUPOS = {   # interruptores de la interfaz: grupo -> capas
    "edificio": ("SITIO", "EDIFICIO", "PASILLOS"), "equipos": ("EQUIPOS", "TEXTOS"), "mantencion": ("MANTENCION",),
    "canerias": ("CANERIAS",), "electrico": ("ELECTRICO",), "cotas": ("COTAS", "EJES"),
}
NOMBRE_GRUPO = {"edificio": "Edificio", "equipos": "Equipos", "mantencion": "Zonas de mantención", "canerias": "Cañerías",
                "electrico": "Electricidad", "cotas": "Cotas"}


def _f(v, d=1):
    return escribir(v, d)


def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


# ------------------------------------------------------------------------------------------- primitivas en metros
class _P:
    """Lista de primitivas en metros. e: estilo de línea; f: relleno; s: servicio (color)."""

    def __init__(self, capa="EQUIPOS"):
        self.capa = capa
        self.p: list[dict] = []

    def poli(self, pts, e="media", f=None, cerr=False, s=None, capa=None, **kw):
        self.p.append(dict(k="poly", capa=capa or self.capa, e=e, f=f, s=s, cerr=cerr, pts=[(float(a), float(b)) for a, b in pts], **kw))

    def linea(self, x1, y1, x2, y2, e="fina", **kw):
        self.poli([(x1, y1), (x2, y2)], e, **kw)

    def rect(self, x0, y0, x1, y1, e="media", f=None, **kw):
        self.poli([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], e, f, True, **kw)

    def circ(self, cx, cy, r, e="media", f=None, capa=None, s=None):
        self.p.append(dict(k="circ", capa=capa or self.capa, e=e, f=f, s=s, c=(float(cx), float(cy)), r=float(r)))

    def texto(self, x, y, s, h, anc="c", rot=0, capa=None, neg=False):
        if str(s):
            self.p.append(dict(k="text", capa=capa or "TEXTOS", x=float(x), y=float(y), s=str(s), h=float(h), anc=anc, rot=rot, neg=neg))

    def tubo(self, pts, w, s, capa="CANERIAS", **kw):
        self.p.append(dict(k="tubo", capa=capa, e="tubo", f=None, s=s, w=float(w), pts=[(float(a), float(b)) for a, b in pts], **kw))


def _arco(cx, cy, r, a0, a1, n=10):
    return [(cx + r * math.cos(math.radians(a0 + (a1 - a0) * i / n)), cy + r * math.sin(math.radians(a0 + (a1 - a0) * i / n)))
            for i in range(n + 1)]


def _cilindro(P, x0, x1, yc, r, e="gruesa", f="eq"):
    """Recipiente horizontal en planta: rectángulo con cabezales semielípticos en los extremos."""
    a = min(r * 0.55, (x1 - x0) / 4)
    pts = [(x0 + a, yc - r), (x1 - a, yc - r)]
    pts += [(x1 - a + a * math.cos(math.radians(t)), yc + r * math.sin(math.radians(t))) for t in range(-90, 91, 15)]
    pts += [(x0 + a, yc + r)]
    pts += [(x0 + a + a * math.cos(math.radians(t)), yc + r * math.sin(math.radians(t))) for t in range(90, 271, 15)]
    P.poli(pts, e, f, True)
    P.linea(x0 + a, yc - r, x0 + a, yc + r, "fina"); P.linea(x1 - a, yc - r, x1 - a, yc + r, "fina")


def _motor(P, x0, x1, y0, y1):
    """Motor eléctrico en planta: carcasa con aletas y tapa del ventilador."""
    P.rect(x0, y0, x1, y1, "media", "eq")
    L = x1 - x0
    for i in range(1, 4):
        P.linea(x0 + L * (0.15 + 0.2 * i), y0, x0 + L * (0.15 + 0.2 * i), y1, "fina")
    P.rect(x1, y0 + (y1 - y0) * 0.2, x1 + L * 0.12, y1 - (y1 - y0) * 0.2, "fina", "eq")


def _diag(P, x0, y0, x1, y1, ix0, iy0, ix1, iy1):
    for (a, b), (c, d) in (((x0, y0), (ix0, iy0)), ((x1, y0), (ix1, iy0)), ((x1, y1), (ix1, iy1)), ((x0, y1), (ix0, iy1))):
        P.linea(a, b, c, d, "fina")


def simbolo(forma: str, L: float, W: float, efectos: int = 1) -> list[dict]:
    """Primitivas del símbolo de vista superior en coordenadas locales (centro en 0; x a lo largo del largo L, y a lo ancho W)."""
    P = _P("EQUIPOS")
    hx, hy, m = L / 2, W / 2, min(L, W)
    if forma == "tolva":
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        o = 0.08 * m; s = 0.14 * m
        P.rect(-hx + o, -hy + o, hx - o, hy - o, "fina")
        P.rect(-s, -s, s, s, "media")
        _diag(P, -hx + o, -hy + o, hx - o, hy - o, -s, -s, s, s)
    elif forma == "estanque":
        r = m / 2 * 0.94
        P.circ(0, 0, r, "gruesa", "eq"); P.circ(0, 0, r * 0.12, "fina")
        P.circ(r * 0.55, r * 0.35, r * 0.14, "fina")
        for a in (45, 135, 225, 315):
            cx, cy = r * 0.92 * math.cos(math.radians(a)), r * 0.92 * math.sin(math.radians(a)); q = r * 0.06
            P.rect(cx - q, cy - q, cx + q, cy + q, "fina", "eq")
        P.linea(hx * 0.94, 0, hx, 0, "media"); P.linea(-hx * 0.94, 0, -hx, 0, "media")
    elif forma in ("banda", "transportador"):
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        b = 0.36 * W; e0 = min(0.18 * L, 0.6)
        P.rect(-hx + e0, -b, hx - e0, b, "fina")
        n = max(2, int((L - 2 * e0) / 0.6))
        for i in range(1, n):
            x = -hx + e0 + (L - 2 * e0) * i / n
            P.linea(x, -b, x, b, "fina")
        for x in (-hx + e0 * 0.5, hx - e0 * 0.5):
            P.rect(x - e0 * 0.3, -b * 1.05, x + e0 * 0.3, b * 1.05, "media", "eq")
        if forma == "banda":
            ml = min(0.9, L * 0.15)
            _motor(P, hx - e0 - ml, hx - e0 - ml * 0.12, 0.38 * W, 0.49 * W)
    elif forma == "refinadora":
        P.rect(-hx, -hy, hx, hy, "fina")
        x1 = hx - 0.28 * L
        _cilindro(P, -hx + 0.04 * L, x1, 0, 0.34 * W)
        P.rect(x1, -0.06 * W, x1 + 0.05 * L, 0.06 * W, "fina", "eq")
        _motor(P, x1 + 0.05 * L, hx - 0.06 * L, -0.24 * W, 0.24 * W)
        s = 0.18 * W; cx = -hx + 0.18 * L
        P.rect(cx - s, -s, cx + s, s, "media", "eq"); _diag(P, cx - s, -s, cx + s, s, cx - s * 0.3, -s * 0.3, cx + s * 0.3, s * 0.3)
        P.rect(-hx + 0.3 * L, -0.42 * W, x1 - 0.05 * L, -0.34 * W, "oculta")
    elif forma == "ciclon":
        r = m / 2 * 0.9
        P.circ(0, 0, r, "gruesa", "eq"); P.circ(0, 0, r * 0.4, "media")
        P.rect(-hx, r * 0.55, 0, r * 0.95, "media", "eq")
    elif forma in ("molienda", "sierra"):
        P.rect(-hx, -hy, hx, hy, "fina")
        bx1 = -hx + 0.58 * L
        P.rect(-hx + 0.04 * L, -0.42 * W, bx1, 0.42 * W, "gruesa", "eq")
        if forma == "sierra":
            P.circ((-hx + 0.04 * L + bx1) / 2, 0, min(0.36 * W, (bx1 + hx - 0.04 * L) * 0.45), "media"); P.linea(-hx + 0.04 * L, 0, bx1, 0, "fina")
        else:
            cx = (-hx + 0.04 * L + bx1) / 2; s = 0.3 * W
            P.rect(cx - s, -s, cx + s, s, "media"); _diag(P, cx - s, -s, cx + s, s, cx - s * 0.35, -s * 0.35, cx + s * 0.35, s * 0.35)
        _motor(P, bx1 + 0.08 * L, hx - 0.08 * L, -0.25 * W, 0.25 * W)
        P.rect(bx1 - 0.06 * L, 0.3 * W, hx - 0.12 * L, 0.46 * W, "fina")
    elif forma == "intercambiador":
        r = 0.32 * W; x0 = -hx + 0.14 * L
        _cilindro(P, x0, hx - 0.02 * L, 0, r)
        P.rect(-hx + 0.01 * L, -r * 1.08, x0, r * 1.08, "gruesa", "eq")
        P.linea(x0 - 0.02 * L, -r * 1.2, x0 - 0.02 * L, r * 1.2, "media")
        for t in (0.3, 0.75):
            x = -hx + t * L
            P.rect(x - 0.025 * L, -hy * 0.9, x + 0.025 * L, hy * 0.9, "fina")
        for t in (0.22, 0.85):
            x = -hx + t * L
            P.rect(x - 0.02 * L, r, x + 0.02 * L, r + 0.12 * W, "fina", "eq")
    elif forma == "intercambiador_placas":
        P.rect(-hx, -hy, hx, hy, "fina")
        P.rect(-hx + 0.05 * L, -0.4 * W, -hx + 0.12 * L, 0.4 * W, "gruesa", "eq")
        P.rect(hx - 0.3 * L, -0.4 * W, hx - 0.24 * L, 0.4 * W, "gruesa", "eq")
        x0, x1 = -hx + 0.12 * L, hx - 0.3 * L
        P.rect(x0, -0.34 * W, x1, 0.34 * W, "media", "eq")
        n = max(4, int((x1 - x0) / 0.08))
        for i in range(1, min(n, 40)):
            x = x0 + (x1 - x0) * i / min(n, 40)
            P.linea(x, -0.34 * W, x, 0.34 * W, "fina")
        for y in (-0.42 * W, 0.42 * W):
            P.linea(-hx + 0.05 * L, y, hx - 0.04 * L, y, "fina")
    elif forma in ("evaporador", "evaporador_mvr"):
        P.rect(-hx, -hy, hx, hy, "oculta")               # estructura y plataforma
        n = max(1, int(efectos))
        zona = 0.66 * L
        r = min(0.4 * W, zona / (2 * n) * 0.86)
        xs = [-hx + zona * (i + 0.5) / n for i in range(n)]
        for i, x in enumerate(xs):
            P.circ(x, -0.08 * W, r, "gruesa", "eq"); P.circ(x, -0.08 * W, r * 0.18, "fina")
            rs = r * 0.55                                   # separador de vapor de cada efecto
            P.circ(x, hy - rs * 1.1, rs, "media", "eq")
            P.linea(x, -0.08 * W + r, x, hy - rs * 2.1, "fina")
            if i:
                P.linea(xs[i - 1] + r, -0.08 * W, x - r, -0.08 * W, "fina")
        x0 = -hx + zona + 0.03 * L
        if forma == "evaporador_mvr":                      # compresor de recompresión mecánica con su motor
            rc = min(0.22 * W, 0.08 * L)
            P.circ(x0 + rc, 0.05 * W, rc, "gruesa", "eq")
            _motor(P, x0 + 2 * rc + 0.02 * L, hx - 0.05 * L, 0.05 * W - rc * 0.6, 0.05 * W + rc * 0.6)
            _cilindro(P, x0, hx - 0.03 * L, -0.34 * W, 0.08 * W, "media")    # condensador de purga
        else:                                              # condensador de superficie al final de la batería
            _cilindro(P, x0, hx - 0.03 * L, -0.2 * W, 0.16 * W)
            P.poli([(x0, 0.22 * W), (x0 + 0.14 * L, 0.3 * W), (x0, 0.38 * W)], "media", "eq", True)   # termocompresor
    elif forma == "caldera":
        P.rect(-hx, -hy, hx, hy, "fina")
        r = 0.36 * W; x0 = -hx + 0.2 * L
        _cilindro(P, x0, hx - 0.12 * L, 0, r)
        P.rect(-hx + 0.04 * L, -0.2 * W, x0, 0.2 * W, "gruesa", "eq")       # quemador
        P.circ(-hx + 0.1 * L, 0.32 * W, 0.1 * W, "media", "eq")              # ventilador del quemador
        rch = min(0.1 * W, 0.05 * L)
        P.circ(hx - 0.06 * L, 0, rch, "media", "eq")                          # chimenea
        P.linea(hx - 0.12 * L, 0, hx - 0.06 * L - rch, 0, "fina")
        P.linea(x0 + 0.1 * L, r * 0.75, hx - 0.2 * L, r * 0.75, "fina")      # colector de vapor
    elif forma == "hogar":
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        o = 0.12 * m
        P.rect(-hx + o, -hy + o, hx - o, hy - o, "media")
        n = max(3, int((L - 2 * o) / 0.5))
        for i in range(1, min(n, 30)):
            x = -hx + o + (L - 2 * o) * i / min(n, 30)
            P.linea(x, -hy + 1.5 * o, x, hy - 1.5 * o, "fina")
        P.circ(hx - o * 0.8, hy - o * 0.8, o * 0.6, "media", "eq")
    elif forma == "secador_rotatorio":
        P.rect(-hx, -hy, hx, hy, "fina")
        P.rect(-0.38 * L, -0.3 * W, 0.38 * L, 0.3 * W, "gruesa", "eq")
        for x in (-0.2 * L, 0.2 * L):
            P.rect(x - 0.015 * L, -0.36 * W, x + 0.015 * L, 0.36 * W, "media", "eq")
        P.rect(0.05 * L, -0.38 * W, 0.08 * L, 0.38 * W, "media")
        _motor(P, 0.0, 0.08 * L, 0.38 * W, 0.48 * W)
        P.rect(-hx + 0.01 * L, -0.4 * W, -0.38 * L, 0.4 * W, "media", "eq")
        P.rect(0.38 * L, -0.4 * W, hx - 0.01 * L, 0.4 * W, "media", "eq")
    elif forma == "secador_banda":
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        P.rect(-hx + 0.3, -0.3 * W, hx - 0.3, 0.3 * W, "fina")
        n = max(2, int(round(L / 5)))
        for i in range(1, n):
            x = -hx + L * i / n
            P.linea(x, -hy, x, hy, "media")
        for i in range(n):
            P.circ(-hx + L * (i + 0.5) / n, 0.4 * W, min(0.08 * W, L / n * 0.2), "fina", "eq")
    elif forma == "secador_camara":
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        o = 0.1 * m
        P.rect(-hx + o, -hy + o, hx - o, hy - o, "media")
        n = max(0, int((L - 2 * o - 1.0) / 1.3))
        for i in range(n):
            x0 = -hx + o + 0.2 + i * 1.3
            if x0 + 1.1 < hx - o:
                P.rect(x0, -hy + 2 * o, x0 + 1.1, hy - 2 * o, "fina")
        P.poli(_arco(hx, hy - o, W / 2 - o, 180, 270, 8), "fina")
        P.poli(_arco(hx, -hy + o, W / 2 - o, 90, 180, 8), "fina")
    elif forma == "llenadora":
        P.rect(-hx, -hy, hx, hy, "fina")
        P.rect(-0.3 * L, -0.4 * W, 0.3 * L, 0.4 * W, "gruesa", "eq")
        n = 4
        for i in range(n):
            P.circ(-0.3 * L + 0.6 * L * (i + 0.5) / n, 0.08 * W, min(0.11 * W, 0.06 * L), "media", "eq")
        for x0, x1 in ((-hx + 0.02 * L, -0.3 * L), (0.3 * L, hx - 0.02 * L)):
            P.rect(x0, -0.22 * W, x1, 0.12 * W, "media", "eq")
            for i in range(1, 4):
                P.linea(x0 + (x1 - x0) * i / 4, -0.22 * W, x0 + (x1 - x0) * i / 4, 0.12 * W, "fina")
        P.rect(-0.12 * L, -0.38 * W, 0.12 * L, -0.24 * W, "fina")                 # tablero de mando
    elif forma == "acopio":
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        paso = max(0.6, m / 5)
        k = -L - W
        while k < L + W:
            seg = _recortar_diag(k, hx, hy)
            if seg:
                P.linea(*seg, "fina")
            k += paso
        P.poli(_arco(0, 0, min(hx, hy) * 0.8, 0, 360, 24), "media")
    elif forma == "pelletizadora":
        P.rect(-hx, -hy, hx, hy, "fina")
        rd = min(0.38 * W, 0.27 * L)
        P.circ(-0.22 * L, 0, rd, "gruesa", "eq"); P.circ(-0.22 * L, 0, rd * 0.52, "fina")
        P.rect(0.0, -0.3 * W, 0.18 * L, 0.3 * W, "media", "eq")
        _motor(P, 0.2 * L, hx - 0.06 * L, -0.24 * W, 0.24 * W)
    elif forma == "enfriador":
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        s = 0.12 * m
        P.circ(0, 0, m * 0.38, "media"); P.rect(-s, -s, s, s, "media")
        _diag(P, -hx, -hy, hx, hy, -s, -s, s, s)
    elif forma == "bomba":
        P.rect(-hx, -hy, hx, hy, "fina")
        P.circ(-hx + 0.22 * L, 0, min(0.42 * W, 0.21 * L), "gruesa", "eq")
        P.rect(-hx + 0.4 * L, -0.12 * W, -hx + 0.48 * L, 0.12 * W, "fina", "eq")
        _motor(P, -hx + 0.48 * L, hx - 0.08 * L, -0.34 * W, 0.34 * W)
    elif forma == "valvula":
        P.poli([(-hx, -hy), (0, 0), (-hx, hy)], "gruesa", "eq", True); P.poli([(hx, -hy), (0, 0), (hx, hy)], "gruesa", "eq", True)
    elif forma == "maquina_rotativa":
        P.rect(-hx, -hy, hx, hy, "fina")
        P.circ(-hx + 0.3 * L, 0, min(0.44 * W, 0.28 * L), "gruesa", "eq")
        _motor(P, -hx + 0.58 * L, hx - 0.06 * L, -0.3 * W, 0.3 * W)
    elif forma == "columna":
        P.circ(0, 0, m / 2 * 0.92, "gruesa", "eq"); P.circ(0, 0, m / 2 * 0.7, "fina")
        P.linea(-m * 0.1, 0, m * 0.1, 0, "fina"); P.linea(0, -m * 0.1, 0, m * 0.1, "fina")
    else:
        P.rect(-hx, -hy, hx, hy, "gruesa", "eq")
        o = 0.1 * m
        P.rect(-hx + o, -hy + o, hx - o, hy - o, "fina")
        P.linea(-hx + o, 0, hx - o, 0, "fina"); P.linea(0, -hy + o, 0, hy - o, "fina")
    return P.p


def _recortar_diag(k, hx, hy):
    """Segmento de la recta y = x + k dentro del rectángulo [-hx, hx] x [-hy, hy] (rayado a 45°)."""
    pts = []
    for x in (-hx, hx):
        y = x + k
        if -hy - 1e-9 <= y <= hy + 1e-9:
            pts.append((x, y))
    for y in (-hy, hy):
        x = y - k
        if -hx - 1e-9 <= x <= hx + 1e-9:
            pts.append((x, y))
    pts = sorted(set((round(a, 6), round(b, 6)) for a, b in pts))
    if len(pts) < 2:
        return None
    (a, b), (c, d) = pts[0], pts[-1]
    return (a, b, c, d) if abs(a - c) + abs(b - d) > 1e-6 else None


def simbolo_ccm(L: float, W: float) -> list[dict]:
    """Sala eléctrica en coordenadas locales: muros, puerta y fila de celdas del CCM junto al muro de atrás (y+)."""
    P = _P("ELECTRICO")
    hx, hy, t = L / 2, W / 2, TABIQUE_M
    P.rect(-hx, -hy, hx, hy, "media", "sala_el")
    pw = min(PUERTA_M, L * 0.3)
    for x0, x1 in ((-hx, -pw / 2), (pw / 2, hx)):            # muro de adelante con la puerta al centro
        P.rect(x0, -hy, x1, -hy + t, "muro", "muro")
    P.rect(-hx, hy - t, hx, hy, "muro", "muro"); P.rect(-hx, -hy, -hx + t, hy, "muro", "muro"); P.rect(hx - t, -hy, hx, hy, "muro", "muro")
    P.linea(-pw / 2, -hy + t, -pw / 2, -hy + t + pw, "media")
    P.poli(_arco(-pw / 2, -hy + t, pw, 90, 0, 8), "fina")
    n = max(2, int((L - 2 * t - 0.6) / 0.8))
    x0 = -n * 0.8 / 2
    for i in range(n):
        P.rect(x0 + i * 0.8, hy - t - 0.6, x0 + (i + 1) * 0.8, hy - t, "media", "celda")
        P.linea(x0 + i * 0.8 + 0.4, hy - t - 0.6, x0 + i * 0.8 + 0.4, hy - t - 0.45, "fina")
    return P.p


def zona_mantencion(forma: str, L: float, W: float, margen: float) -> list[dict]:
    """Zona de servicio punteada (local): margen alrededor de la huella; en intercambiadores de carcasa, más el retiro del haz."""
    P = _P("MANTENCION")
    P.rect(-L / 2 - margen, -W / 2 - margen, L / 2 + margen, W / 2 + margen, "mant")
    if forma == "intercambiador":
        haz = 0.84 * L
        P.rect(-L / 2 - margen - haz, -0.3 * W, -L / 2 - margen, 0.3 * W, "mant")
    return P.p


def _transformar(prims: list[dict], x: float, y: float, rot: float) -> list[dict]:
    """Primitivas locales a coordenadas del plano (giro antihorario en grados y traslación)."""
    c, s = round(math.cos(math.radians(rot)), 9), round(math.sin(math.radians(rot)), 9)
    T = lambda a, b: (x + a * c - b * s, y + a * s + b * c)
    out = []
    for q in prims:
        q2 = dict(q)
        if "pts" in q:
            q2["pts"] = [T(a, b) for a, b in q["pts"]]
        if "c" in q:
            q2["c"] = T(*q["c"])
        if q["k"] == "text":
            q2["x"], q2["y"] = T(q["x"], q["y"])
        out.append(q2)
    return out


# ------------------------------------------------------------------------------------------- ruteo ortogonal (A*)
class _Grilla:
    """Grilla de celdas de CELDA_M para el ruteo. bloq: celdas ocupadas por equipos; uso: cuántas líneas pasan por cada celda."""
    DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))

    def __init__(self, x0, y0, x1, y1, paso=CELDA_M):
        self.x0, self.y0, self.paso = x0, y0, paso
        self.nx = max(2, int(math.ceil((x1 - x0) / paso)) + 1)
        self.ny = max(2, int(math.ceil((y1 - y0) / paso)) + 1)
        self.bloq = bytearray(self.nx * self.ny)
        self.uso = [0] * (self.nx * self.ny)

    def ij(self, x, y):
        return (min(self.nx - 1, max(0, int(round((x - self.x0) / self.paso)))), min(self.ny - 1, max(0, int(round((y - self.y0) / self.paso)))))

    def xy(self, i, j):
        return (self.x0 + i * self.paso, self.y0 + j * self.paso)

    def bloquear(self, x0, y0, x1, y1):
        i0, j0 = self.ij(x0, y0); i1, j1 = self.ij(x1, y1)
        for j in range(j0, j1 + 1):
            for i in range(i0, i1 + 1):
                self.bloq[j * self.nx + i] = 1

    def libre(self, i, j):
        return 0 <= i < self.nx and 0 <= j < self.ny and not self.bloq[j * self.nx + i]

    def ruta(self, a, da, b, giro=4.0, pen_uso=2.5, premio=None, max_exp=60000):
        """Camino de celdas de a (con dirección inicial da) a b; costo 1 por celda, giro por cada cambio de dirección y pen_uso por
        cada línea que ya pasa por la celda (premio < 1 en vez de pen_uso: se prefiere compartir, como en una bandeja)."""
        nx = self.nx
        ia, ja = a; ib, jb = b
        INF = float("inf")
        g = {}
        h = lambda i, j: abs(i - ib) + abs(j - jb)
        cola = [(h(ia, ja), 0.0, ia, ja, da)]
        g[(ia, ja, da)] = 0.0
        padre = {}
        exp = 0
        while cola:
            _, gc, i, j, d = heapq.heappop(cola)
            if (i, j) == (ib, jb):
                camino = [(i, j)]; k = (i, j, d)
                while k in padre:
                    k = padre[k]; camino.append((k[0], k[1]))
                return camino[::-1]
            if gc > g.get((i, j, d), INF):
                continue
            exp += 1
            if exp > max_exp:
                return None
            for nd, (di, dj) in enumerate(self.DIRS):
                if d is not None and nd == (d + 2) % 4:
                    continue
                ni, nj = i + di, j + dj
                if not (0 <= ni < nx and 0 <= nj < self.ny):
                    continue
                idx = nj * nx + ni
                if self.bloq[idx] and (ni, nj) != (ib, jb):
                    continue
                u = self.uso[idx]
                paso = (premio if (premio is not None and u) else 1.0) + (0.0 if premio is not None else pen_uso * u)
                c = gc + paso + (giro if (d is not None and nd != d) else 0.0)
                k = (ni, nj, nd)
                if c < g.get(k, INF):
                    g[k] = c; padre[k] = (i, j, d)
                    heapq.heappush(cola, (c + h(ni, nj), c, ni, nj, nd))
        return None

    def marcar(self, celdas):
        for i, j in celdas:
            self.uso[j * self.nx + i] += 1


def _simplificar(pts):
    """Quita puntos repetidos y colineales de un recorrido ortogonal."""
    out = []
    for p in pts:
        p = (round(p[0], 4), round(p[1], 4))
        if out and abs(out[-1][0] - p[0]) + abs(out[-1][1] - p[1]) < 1e-6:
            continue
        out.append(p)
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 1e-6 and abs(b[0] - c[0]) < 1e-6) or (abs(a[1] - b[1]) < 1e-6 and abs(b[1] - c[1]) < 1e-6):
            out.pop(i)
        else:
            i += 1
    return out


def _ortogonalizar(pts):
    """Inserta un quiebre donde dos puntos seguidos no están alineados (une la boquilla con el centro de la celda)."""
    out = [pts[0]]
    for p in pts[1:]:
        q = out[-1]
        if abs(q[0] - p[0]) > 1e-6 and abs(q[1] - p[1]) > 1e-6:
            out.append((p[0], q[1]))
        out.append(p)
    return out


def _normal(rot, lado):
    """Normal hacia afuera de la cara del puerto (sale: x+ local, entra: x- local, servicio: y+ local) girada con el equipo."""
    lx, ly = {"sale": (1, 0), "entra": (-1, 0), "servicio": (0, 1)}[lado]
    c, s = round(math.cos(math.radians(rot))), round(math.sin(math.radians(rot)))
    return (lx * c - ly * s, lx * s + ly * c)


def _salida(G, p, n):
    """Primera celda libre caminando desde el puerto p según la normal n; devuelve (celda, dirección inicial)."""
    d = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}[(int(n[0]), int(n[1]))]
    for k in range(1, 14):
        i, j = G.ij(p[0] + n[0] * k * G.paso, p[1] + n[1] * k * G.paso)
        if G.libre(i, j):
            return (i, j), d
    return G.ij(p[0], p[1]), d


def _recto_libre(p1, n1, p2, n2, obstaculos):
    """True si las dos boquillas se miran en la misma recta y el tramo entre ellas no toca otro equipo."""
    if n1[0] != -n2[0] or n1[1] != -n2[1]:
        return False
    if n1[1] == 0 and abs(p1[1] - p2[1]) < 1e-6 and (p2[0] - p1[0]) * n1[0] > 0:
        caja = (min(p1[0], p2[0]) + 0.05, p1[1] - 0.2, max(p1[0], p2[0]) - 0.05, p1[1] + 0.2)
    elif n1[0] == 0 and abs(p1[0] - p2[0]) < 1e-6 and (p2[1] - p1[1]) * n1[1] > 0:
        caja = (p1[0] - 0.2, min(p1[1], p2[1]) + 0.05, p1[0] + 0.2, max(p1[1], p2[1]) - 0.05)
    else:
        return False
    return not any(_cruza(caja, h) for h in obstaculos)


def _recorrer(G, p1, n1, p2, n2, obstaculos=(), **kw):
    if _recto_libre(p1, n1, p2, n2, obstaculos):
        return [p1, p2], []
    a, da = _salida(G, p1, n1)
    b, _ = _salida(G, p2, n2)
    celdas = G.ruta(a, da, b, **kw)
    if not celdas:
        return _simplificar([p1, (p2[0], p1[1]), p2]), []
    pts = [p1] + [G.xy(i, j) for i, j in celdas] + [p2]
    return _simplificar(_ortogonalizar(pts)), celdas


def _largo(pts):
    return sum(abs(b[0] - a[0]) + abs(b[1] - a[1]) for a, b in zip(pts, pts[1:]))


def _punto_a(pts, dist):
    """Punto y dirección unitaria a la distancia dist medida sobre el recorrido."""
    acum = 0.0
    for a, b in zip(pts, pts[1:]):
        L = abs(b[0] - a[0]) + abs(b[1] - a[1])
        if L <= 1e-9:
            continue
        if acum + L >= dist:
            t = (dist - acum) / L
            return (a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t), ((b[0] - a[0]) / L, (b[1] - a[1]) / L)
        acum += L
    a, b = pts[-2], pts[-1]; L = max(1e-9, abs(b[0] - a[0]) + abs(b[1] - a[1]))
    return b, ((b[0] - a[0]) / L, (b[1] - a[1]) / L)


# ------------------------------------------------------------------------------------------- diámetros y servicios
def servicio(tipo: str) -> str:
    return _SRV_TIPO.get(str(tipo), "producto")


def dn_de(fila: dict) -> int | None:
    """DN de la línea: líquidos con el diámetro de la red hidráulica; vapor por velocidad (Supuesto); el resto sin DN."""
    try:
        from .costeo import diametro_nominal
    except Exception:
        return None
    D = fila.get("D_mm")
    if D:
        return int(diametro_nominal(float(D)))
    if fila.get("tipo") == "vapor" and fila.get("peso"):
        m = float(fila["peso"]) * 1000 / 3600
        D = math.sqrt(4 * m / (RHO_VAPOR * V_VAPOR * math.pi)) * 1000
        return int(diametro_nominal(D))
    return None


def ancho_linea(fila: dict, dn: int | None) -> float:
    """Ancho dibujado (m): diámetro exterior aproximado (DN × 1,1, mínimo 0,15 m; vapor con 0,1 m de aislación); cinta 0,8 m; ducto 0,6 m."""
    if fila.get("medio") == "transportador":
        return 0.8
    if fila.get("medio") == "ducto":
        return 0.6
    w = max(0.15, (dn or 80) / 1000 * 1.1)
    return w + (0.1 if fila.get("tipo") in ("vapor", "condensado") else 0.0)


# ------------------------------------------------------------------------------------------- edificio
def _muro_con_vanos(P, lado, a0, a1, fijo, t, vanos, capa="EDIFICIO", f="muro"):
    """Muro recto con vanos [(centro, ancho)] a lo largo de a (x para lados N y S, y para W y E)."""
    cortes = sorted((c - w / 2, c + w / 2) for c, w in vanos)
    tramos, ini = [], a0
    for v0, v1 in cortes:
        if v0 > ini:
            tramos.append((ini, v0))
        ini = max(ini, v1)
    if ini < a1:
        tramos.append((ini, a1))
    for u0, u1 in tramos:
        if lado in ("N", "S"):
            P.rect(u0, fijo - t / 2, u1, fijo + t / 2, "muro", f, capa=capa)
        else:
            P.rect(fijo - t / 2, u0, fijo + t / 2, u1, "muro", f, capa=capa)


def _puerta(P, lado, c, fijo, w, t, hacia, capa="EDIFICIO"):
    """Puerta abatible de una hoja: hoja y arco de giro hacia el lado «hacia» (+1 o -1 en la normal del muro)."""
    if lado in ("N", "S"):
        y = fijo + hacia * t / 2
        P.linea(c - w / 2, y, c - w / 2, y + hacia * w, "media", capa=capa)
        P.poli(_arco(c - w / 2, y, w, 90 if hacia > 0 else -90, 0, 8), "fina", capa=capa)
    else:
        x = fijo + hacia * t / 2
        P.linea(x, c - w / 2, x + hacia * w, c - w / 2, "media", capa=capa)
        P.poli(_arco(x, c - w / 2, w, 0 if hacia > 0 else 180, 90, 8), "fina", capa=capa)


def _porton(P, lado, c, fijo, w, t, capa="EDIFICIO"):
    """Portón corredero o enrollable: línea de trazos en el vano y guías en los extremos."""
    if lado in ("N", "S"):
        P.linea(c - w / 2, fijo, c + w / 2, fijo, "oculta", capa=capa)
        for x in (c - w / 2, c + w / 2):
            P.rect(x - 0.08, fijo - t * 0.7, x + 0.08, fijo + t * 0.7, "media", "muro", capa=capa)
    else:
        P.linea(fijo, c - w / 2, fijo, c + w / 2, "oculta", capa=capa)
        for y in (c - w / 2, c + w / 2):
            P.rect(fijo - t * 0.7, y - 0.08, fijo + t * 0.7, y + 0.08, "media", "muro", capa=capa)


def _flecha_doble(P, x0, y0, x1, y1, capa, e="fina"):
    P.linea(x0, y0, x1, y1, e, capa=capa)
    L = math.hypot(x1 - x0, y1 - y0) or 1.0
    ux, uy = (x1 - x0) / L, (y1 - y0) / L
    for (px, py, sx) in ((x1, y1, 1), (x0, y0, -1)):
        bx, by = px - sx * ux * 0.6, py - sx * uy * 0.6
        P.poli([(px, py), (bx - uy * 0.2, by + ux * 0.2), (bx + uy * 0.2, by - ux * 0.2)], "fina", "flecha", True, capa=capa)


def _cota(P, x0, y0, x1, y1, texto, h=0.5, capa="COTAS"):
    """Cota con trazos oblicuos; texto sobre la línea (o a la izquierda si es vertical)."""
    P.linea(x0, y0, x1, y1, "cota", capa=capa)
    for x, y in ((x0, y0), (x1, y1)):
        P.linea(x - 0.25, y - 0.25, x + 0.25, y + 0.25, "media", capa=capa)
    if abs(y1 - y0) < 1e-9:
        P.texto((x0 + x1) / 2, y0 + 0.2, texto, h, "c", capa=capa)
    else:
        P.texto(x0 - 0.2, (y0 + y1) / 2, texto, h, "c", 90, capa=capa)


def _union(cajas):
    cajas = [c for c in cajas if c]
    return (min(c[0] for c in cajas), min(c[1] for c in cajas), max(c[2] for c in cajas), max(c[3] for c in cajas)) if cajas else None


def _cruza(a, b, tol=0.0):
    return a[0] < b[2] - tol and b[0] < a[2] - tol and a[1] < b[3] - tol and b[1] < a[3] - tol


# ------------------------------------------------------------------------------------------- modelo completo
_CACHE: dict = {}


def construir(lay: dict | None, nombres: dict | None = None, pl=None, proyecto: str = "", autor: str = "",
              fecha: str | None = None) -> dict:
    """Modelo del plano detallado en metros. lay: dict de layout.estado_layout; pl (opcional): planta resuelta, para las bombas de
    línea de Equipos auxiliares. Planta vacía: modelo vacío con aviso (no falla)."""
    nombres = nombres or {}
    lay = lay or {}
    pos, dims = lay.get("posiciones") or {}, lay.get("dims") or {}
    red = lay.get("red") or {}
    fecha = fecha or datetime.date.today().strftime("%d-%m-%Y")
    cajetin = dict(proyecto=proyecto or "Planta", titulo="Plano de disposición en planta", fecha=fecha, autor=autor or "")
    ids = [k for k in pos if k in dims]
    if not ids:
        return dict(vacio=True, equipos=[], ccm=None, mundo=[], ext=(0.0, 0.0, 10.0, 10.0), lineas=[], bombas=[], ejes_x=[], ejes_y=[],
                    nave=None, avisos=["La planta está vacía: no hay equipos que dibujar."], cajetin=cajetin, leyenda=_leyenda([]),
                    supuestos=SUPUESTOS)
    bombas = _bombas_linea(pl)
    clave = json.dumps([{k: pos[k] for k in ids}, {k: [dims[k].get(c) for c in ("largo", "ancho", "forma", "efectos")] for k in ids},
                        red.get("ccm"), red.get("ccm_dim"), [(f.get("id"), f.get("origen"), f.get("destino"), f.get("tipo"), f.get("medio"),
                                                              f.get("D_mm"), f.get("servicio"), f.get("peso")) for f in lay.get("filas") or []],
                        [(c.get("id"), c.get("equipo"), c.get("x"), c.get("y")) for c in red.get("cables") or []],
                        float(lay.get("pasillo", LY.PASILLO_M)), bombas, sorted(nombres.items())], default=str)
    if clave in _CACHE:
        m = _CACHE[clave]
        return dict(m, cajetin=cajetin)
    m = _construir(lay, ids, pos, dims, red, nombres, bombas)
    m["cajetin"] = cajetin
    if len(_CACHE) > 12:
        _CACHE.clear()
    _CACHE[clave] = m
    return m


def _bombas_linea(pl) -> list:
    """Bombas de línea que no están en el diagrama (P-1xx), de Equipos auxiliares: [(id, origen, destino, línea)]."""
    if pl is None or not getattr(pl, "resuelta", False):
        return []
    try:
        from . import auxiliares as AX
        return [(f["id"], f["origen"], f["destino"], str(f["linea"])) for f in AX.bombas(pl)["filas"] if not f["en_diagrama"]]
    except Exception:
        return []


def _construir(lay, ids, pos, dims, red, nombres, bombas) -> dict:
    pas = float(lay.get("pasillo", LY.PASILLO_M))
    mant = max(0.3, pas * MANT_FRAC)
    avisos = []
    W = _P("EDIFICIO")                                     # todo lo que va en coordenadas del plano
    huellas = {k: LY.huella(pos[k], dims[k]) for k in ids}
    equipos = []
    for k in ids:
        d = dims[k]; p = pos[k]; rot = LY._rot(p[2] if len(p) > 2 else 0)
        fo = d.get("forma") or "general"
        nombre = str(nombres.get(k, k))
        corto = nombre if len(nombre) <= 24 else nombre[:23].rstrip() + "…"
        equipos.append(dict(id=k, nombre=nombre, corto=corto, forma=fo, largo=d["largo"], ancho=d["ancho"], alto=d["alto"],
                            x=float(p[0]), y=float(p[1]), rot=rot, prims=simbolo(fo, d["largo"], d["ancho"], d.get("efectos", 1)),
                            mant=zona_mantencion(fo, d["largo"], d["ancho"], mant), huella=huellas[k]))
    ccm = None
    if red.get("ccm") and red.get("ccm_dim"):
        dc = red["ccm_dim"]; p = red["ccm"]
        h = LY.huella(p, dc)
        ccm = dict(id=LY.ID_CCM, nombre="Sala eléctrica", corto="Sala eléctrica", forma="ccm", largo=dc["largo"], ancho=dc["ancho"],
                   alto=dc["alto"], x=float(p[0]), y=float(p[1]), rot=LY._rot(p[2] if len(p) > 2 else 0),
                   prims=simbolo_ccm(dc["largo"], dc["ancho"]), mant=[], huella=h, electrico=True)

    # --- nave: envuelve equipos con su zona de mantención, la sala eléctrica y los pasillos
    zonas = [(h[0] - mant, h[1] - mant, h[2] + mant, h[3] + mant) for h in huellas.values()] + ([ccm["huella"]] if ccm else [])
    Pz = _union(zonas)
    t = MURO_M
    ix0, ix1 = Pz[0] - pas, Pz[2] + pas
    iy0, iy1 = Pz[1] - PASILLO_GRUA_M - pas, Pz[3] + pas
    Lx = ix1 - ix0 + t
    nx = max(2, int(math.ceil(Lx / VANO_M - 1e-9)))
    ax0 = ix0 - t / 2 - (nx * VANO_M - Lx) / 2
    ejes_x = [ax0 + i * VANO_M for i in range(nx + 1)]
    Ly = iy1 - iy0 + t
    Ly2 = float(math.ceil(Ly - 1e-9))
    ay0 = iy0 - t / 2
    nl = max(1, int(math.ceil(Ly2 / LUZ_MAX_M - 1e-9)))
    ejes_y = [ay0 + Ly2 * j / nl for j in range(nl + 1)]
    X0, X1, Y0, Y1 = ejes_x[0], ejes_x[-1], ejes_y[0], ejes_y[-1]
    Lh = X1 - X0
    nave = (X0 - t / 2, Y0 - t / 2, X1 + t / 2, Y1 + t / 2)
    # anexos al sur: oficinas al oeste, bodega al este y portón de recepción entre ambos
    of_l = min(OFICINA_L, 0.3 * Lh); bo_l = min(max(12.0, 0.3 * Lh), 0.35 * Lh)
    of = (nave[0], nave[1] - OFICINA_F, nave[0] + of_l, nave[1])
    bo = (nave[2] - bo_l, nave[1] - BODEGA_F, nave[2], nave[1])
    rec = next((k for k in ids if dims[k].get("familia") == "tolva"), None) or min(ids, key=lambda k: pos[k][0])
    hueco0, hueco1 = of[2] + 0.5, bo[0] - 0.5
    wp = max(2.5, min(PORTON_CAMION_M, hueco1 - hueco0 - 1.0))
    xp = min(max(pos[rec][0], hueco0 + wp / 2 + 0.5), hueco1 - wp / 2 - 0.5)
    # pisos (para la vista a color) y muros de la nave
    S = _P("SITIO")
    patio = (nave[0], min(of[1], bo[1]) - PATIO_F, nave[2], min(of[1], bo[1]))
    cerco = (nave[0] - CERCO_M, patio[1] - CERCO_M, nave[2] + CERCO_M, nave[3] + CERCO_M)
    S.rect(*cerco, e="fina", f="terreno")
    S.rect(*patio, e="fina", f="calle")
    S.rect(of[2], of[1], bo[0], nave[1], e="fina", f="calle")              # acceso pavimentado frente al portón
    W.rect(*nave, e="fina", f="piso")
    vanos_s = [(xp, wp), ((bo[0] + bo[2]) / 2, PORTON_GRUA_M), ((of[0] + of[2]) / 2, PUERTA_M)]
    vanos_n = [(X0 + Lh * 0.25, PUERTA_M), (X0 + Lh * 0.75, PUERTA_M)]       # salidas de emergencia
    _muro_con_vanos(W, "S", nave[0], nave[2], Y0, t, vanos_s)
    _muro_con_vanos(W, "N", nave[0], nave[2], Y1, t, vanos_n)
    _muro_con_vanos(W, "W", nave[1], nave[3], X0, t, [])
    _muro_con_vanos(W, "E", nave[1], nave[3], X1, t, [])
    _porton(W, "S", xp, Y0, wp, t)
    _porton(W, "S", (bo[0] + bo[2]) / 2, Y0, PORTON_GRUA_M, t)
    _puerta(W, "S", (of[0] + of[2]) / 2, Y0, PUERTA_M, t, -1)
    for c in (X0 + Lh * 0.25, X0 + Lh * 0.75):
        _puerta(W, "N", c, Y1, PUERTA_M, t, +1)
    # columnas: en cada eje x sobre los ejes y; en los frontones, pilares cada 6 m o menos
    cols = []
    for x in ejes_x:
        for j, y in enumerate(ejes_y):
            cols.append((x, y, j in (0, len(ejes_y) - 1)))
    for x in (X0, X1):
        for y0_, y1_ in zip(ejes_y, ejes_y[1:]):
            n = int(math.ceil((y1_ - y0_) / VANO_M - 1e-9))
            for i in range(1, n):
                cols.append((x, y0_ + (y1_ - y0_) * i / n, True))
    omitidas = 0
    for x, y, borde in cols:
        q = COLUMNA_M / 2
        cj = (x - q, y - q, x + q, y + q)
        if not borde and any(_cruza(cj, (h[0] - 0.3, h[1] - 0.3, h[2] + 0.3, h[3] + 0.3)) for h in huellas.values()):
            omitidas += 1; continue
        W.rect(*cj, e="muro", f="muro")
    if omitidas:
        avisos.append(f"{omitidas} columnas interiores caen sobre equipos y no se dibujan: requieren viga de transferencia o mover el equipo.")
    # oficinas y baños
    W.rect(*of, e="fina", f="oficina")
    _muro_con_vanos(W, "S", of[0], of[2], of[1] + t / 2, t, [((of[0] + of[2]) * 0.5, PUERTA_M * 1.2)])
    _muro_con_vanos(W, "W", of[1], of[3], of[0] + t / 2, t, [])
    _muro_con_vanos(W, "E", of[1], of[3], of[2] - t / 2, t, [])
    xb = of[0] + (of[2] - of[0]) * 0.62
    _muro_con_vanos(W, "E", of[1] + t, of[3] - t, xb, TABIQUE_M, [((of[1] + of[3]) / 2, PUERTA_M * 0.9)], f="muro")
    _puerta(W, "S", (of[0] + of[2]) * 0.5, of[1] + t / 2, PUERTA_M * 1.2, t, +1)
    for i in range(3):                                         # artefactos sanitarios
        cx = xb + 0.8 + i * 1.1
        if cx + 0.4 < of[2] - t:
            W.rect(cx - 0.35, of[3] - t - 1.4, cx + 0.35, of[3] - t - 0.2, "fina", "eq")
    W.texto((of[0] + xb) / 2, (of[1] + of[3]) / 2, "Oficinas", 0.7, capa="EDIFICIO")
    W.texto((xb + of[2]) / 2, (of[1] + of[3]) / 2 - 0.6, "Baños y vestidores", 0.5, capa="EDIFICIO")
    # bodega de producto terminado con portón de despacho
    W.rect(*bo, e="fina", f="bodega")
    _muro_con_vanos(W, "S", bo[0], bo[2], bo[1] + t / 2, t, [((bo[0] + bo[2]) / 2, PORTON_GRUA_M + 0.5)])
    _muro_con_vanos(W, "W", bo[1], bo[3], bo[0] + t / 2, t, [])
    _muro_con_vanos(W, "E", bo[1], bo[3], bo[2] - t / 2, t, [])
    _porton(W, "S", (bo[0] + bo[2]) / 2, bo[1] + t / 2, PORTON_GRUA_M + 0.5, t)
    for i in range(int((bo[2] - bo[0] - 2) // 1.4)):         # posiciones de pallets
        x = bo[0] + 1.0 + i * 1.4
        for y in (bo[3] - t - 1.6, bo[1] + t + 3.2):
            if x + 1.2 < bo[2] - 1.0:
                W.rect(x, y - 1.0, x + 1.2, y, "fina", None)
    W.texto((bo[0] + bo[2]) / 2, (bo[1] + bo[3]) / 2, "Bodega de producto terminado", 0.6, capa="EDIFICIO")
    # sala de calderas: tabique alrededor de las calderas y hogares con un pasillo libre
    calderas = [k for k in ids if dims[k].get("familia") in ("caldera", "hogar")]
    if calderas:
        sc = _union([huellas[k] for k in calderas])
        for marg in (pas, mant):
            sc2 = (sc[0] - marg, sc[1] - marg, sc[2] + marg, sc[3] + marg)
            if not any(_cruza(sc2, huellas[k]) for k in ids if k not in calderas) and not (ccm and _cruza(sc2, ccm["huella"])):
                break
        else:
            avisos.append("La sala de calderas toca otros equipos: separe las calderas del proceso.")
        W.rect(*sc2, e="fina", f="calderas")
        cx = (sc2[0] + sc2[2]) / 2
        hacia_centro = -1 if (sc2[1] + sc2[3]) / 2 > (Y0 + Y1) / 2 else 1
        yp = sc2[1] if hacia_centro < 0 else sc2[3]
        _muro_con_vanos(W, "S", sc2[0], sc2[2], sc2[1], TABIQUE_M, [(cx, PUERTA_M * 1.4)] if hacia_centro < 0 else [])
        _muro_con_vanos(W, "N", sc2[0], sc2[2], sc2[3], TABIQUE_M, [(cx, PUERTA_M * 1.4)] if hacia_centro > 0 else [])
        _muro_con_vanos(W, "W", sc2[1], sc2[3], sc2[0], TABIQUE_M, [])
        _muro_con_vanos(W, "E", sc2[1], sc2[3], sc2[2], TABIQUE_M, [])
        _puerta(W, "S" if hacia_centro < 0 else "N", cx, yp, PUERTA_M * 1.4, TABIQUE_M, hacia_centro)
        W.texto(sc2[0] + 0.3, sc2[3] - 0.25 - 0.55, "Sala de calderas", 0.55, "l", capa="EDIFICIO")
    # pasillos marcados en el piso
    Pa = _P("PASILLOS")
    jx0, jx1, jy0, jy1 = X0 + t / 2, X1 - t / 2, Y0 + t / 2, Y1 - t / 2
    Pa.rect(jx0 + pas, jy0 + pas + PASILLO_GRUA_M, jx1 - pas, jy1 - pas, "pasillo")
    Pa.linea(jx0 + pas, jy0 + pas, jx1 - pas, jy0 + pas, "pasillo")
    Pa.linea(jx0 + pas, jy0 + pas, jx0 + pas, jy0 + pas + PASILLO_GRUA_M, "pasillo")
    Pa.linea(jx1 - pas, jy0 + pas, jx1 - pas, jy0 + pas + PASILLO_GRUA_M, "pasillo")
    yg = jy0 + pas + PASILLO_GRUA_M / 2
    _flecha_doble(Pa, jx0 + pas + 1.0, yg - 0.45, jx0 + pas + 5.0, yg - 0.45, "PASILLOS")
    Pa.texto(jx0 + pas + 5.6, yg - 0.62, f"Pasillo de grúa horquilla {_f(PASILLO_GRUA_M, 1)} m", 0.45, "l", capa="PASILLOS")
    Pa.texto(jx0 + pas / 2, (jy0 + jy1) / 2, f"Pasillo peatonal {_f(pas, 1)} m", 0.4, "c", 90, capa="PASILLOS")
    # sitio: patio, estacionamientos, acceso, garita y cerco
    n_est = int(min(N_ESTAC, max(2, (patio[2] - patio[0]) * 0.45 // ESTAC_A)))
    for i in range(n_est):
        x = patio[0] + 1.0 + i * ESTAC_A
        S.rect(x, patio[1] + 0.5, x + ESTAC_A, patio[1] + 0.5 + ESTAC_L, "fina", "estac")
    S.texto(patio[0] + 1.0 + n_est * ESTAC_A / 2, patio[1] + 0.5 + ESTAC_L + 0.4, f"Estacionamientos ({n_est})", 0.55, capa="SITIO")
    S.texto((patio[0] + patio[2]) / 2, patio[1] + PATIO_F * 0.55, "Patio de camiones", 0.9, capa="SITIO")
    ct = (xp - 1.3, nave[1] - 2.0 - 16.5, xp + 1.3, nave[1] - 2.0)       # camión de 16,5 m frente al portón de recepción
    if ct[1] > patio[1] + 0.5:
        _camion(S, xp, ct[3], ct[1])
    xa = patio[2] - ACCESO_M / 2 - 4.0
    _muro_con_vanos(S, "S", cerco[0], cerco[2], cerco[1], 0.06, [(xa, ACCESO_M)], f="cerco")
    _muro_con_vanos(S, "N", cerco[0], cerco[2], cerco[3], 0.06, [], f="cerco")
    _muro_con_vanos(S, "W", cerco[1], cerco[3], cerco[0], 0.06, [], f="cerco")
    _muro_con_vanos(S, "E", cerco[1], cerco[3], cerco[2], 0.06, [], f="cerco")
    for x in (xa - ACCESO_M / 2, xa + ACCESO_M / 2):
        S.linea(x, cerco[1], x + (ACCESO_M / 2 if x < xa else -ACCESO_M / 2) * 0.9, cerco[1] + ACCESO_M / 2 * 0.43, "fina")
    S.texto(xa, cerco[1] - 1.0, "Acceso", 0.6, capa="SITIO")
    S.rect(xa + ACCESO_M / 2 + 0.8, cerco[1] + 0.8, xa + ACCESO_M / 2 + 3.8, cerco[1] + 3.8, "media", "oficina")
    S.texto(xa + ACCESO_M / 2 + 2.3, cerco[1] + 2.1, "Garita", 0.45, capa="SITIO")
    S.texto(cerco[0] + 0.3, cerco[1] - 1.0, "Cerco perimetral", 0.45, "l", capa="SITIO")
    W.texto(xp, Y0 + t / 2 + 0.5, "Portón de recepción", 0.45, capa="EDIFICIO")
    W.texto(jx1 - pas - 0.3, jy1 - pas - 0.9, "Nave de proceso", 0.75, "r", capa="EDIFICIO")

    # --- ejes de columnas con burbujas y cotas
    E = _P("EJES"); C = _P("COTAS")
    rb = 0.9
    for i, x in enumerate(ejes_x):
        E.linea(x, Y0 - 2.0, x, Y1 + 3.0, "eje")
        E.circ(x, Y1 + 3.0 + rb, rb, "fina", "burbuja"); E.texto(x, Y1 + 3.0 + rb - 0.3, str(i + 1), 0.8, capa="EJES")
    letras = "ABCDEFGHJKLMNPQRSTUVWXYZ"
    for j, y in enumerate(ejes_y):
        E.linea(X0 - 3.0, y, X1 + 2.0, y, "eje")
        E.circ(X0 - 3.0 - rb, y, rb, "fina", "burbuja"); E.texto(X0 - 3.0 - rb, y - 0.3, letras[j % len(letras)], 0.8, capa="EJES")
    yc = Y1 + 3.0 + 2 * rb + 1.2
    for a, b in (zip(ejes_x, ejes_x[1:]) if len(ejes_x) > 2 else ()):
        _cota(C, a, yc, b, yc, _f(b - a, 1))
    _cota(C, X0, yc + 1.4, X1, yc + 1.4, _f(X1 - X0, 1))
    xc = X0 - 3.0 - 2 * rb - 1.2
    for a, b in (zip(ejes_y, ejes_y[1:]) if len(ejes_y) > 2 else ()):
        _cota(C, xc, a, xc, b, _f(b - a, 1))
    _cota(C, xc - 1.4, Y0, xc - 1.4, Y1, _f(Y1 - Y0, 1))
    _cota(C, cerco[0], cerco[1] - 2.6, cerco[2], cerco[1] - 2.6, _f(cerco[2] - cerco[0], 1))

    # --- cañerías: ruteo ortogonal por los pasillos
    G = _Grilla(math.floor(jx0 / CELDA_M) * CELDA_M, math.floor(jy0 / CELDA_M) * CELDA_M, jx1, jy1)
    for h in huellas.values():
        G.bloquear(h[0] - 0.25, h[1] - 0.25, h[2] + 0.25, h[3] + 0.25)
    if ccm:
        h = ccm["huella"]; G.bloquear(h[0] - 0.25, h[1] - 0.25, h[2] + 0.25, h[3] + 0.25)
    Cn = _P("CANERIAS")
    lineas, etiquetas = [], []
    ocupado = [h for h in huellas.values()] + ([ccm["huella"]] if ccm else [])
    textos_edif = [_caja_txt(q) for q in W.p + Pa.p if q["k"] == "text"]
    ocupado += _poner_etiquetas(equipos + ([ccm] if ccm else []), ocupado + textos_edif) + textos_edif
    filas = sorted(lay.get("filas") or [], key=lambda f: -(f.get("D_mm") or 0))
    for f in filas:
        o, dd = f.get("origen"), f.get("destino")
        if o not in huellas or dd not in huellas:
            continue
        lado2 = "servicio" if f.get("servicio") else "entra"
        p1 = LY.puerto(pos[o], dims[o], "sale"); p2 = LY.puerto(pos[dd], dims[dd], lado2)
        n1 = _normal(LY._rot(pos[o][2] if len(pos[o]) > 2 else 0), "sale")
        n2 = _normal(LY._rot(pos[dd][2] if len(pos[dd]) > 2 else 0), lado2)
        pts, celdas = _recorrer(G, (p1[0], p1[1]), n1, (p2[0], p2[1]), n2, [huellas[k] for k in huellas if k not in (o, dd)])
        G.marcar(celdas)
        srv = servicio(f.get("tipo")); dn = dn_de(f); w = ancho_linea(f, dn)
        abbr = "CT" if f.get("medio") == "transportador" else ("DU" if f.get("medio") == "ducto" else SERVICIOS[srv][2])
        codigo = f"{f['id']}-" + (f"DN{dn}-" if dn else "") + abbr
        Cn.tubo(pts, w, srv, eq=f"{o} {dd}", linea=str(f["id"]), medio=f.get("medio"))
        lineas.append(dict(id=str(f["id"]), origen=o, destino=dd, srv=srv, dn=dn, ancho=w, pts=pts, codigo=codigo, medio=f.get("medio"),
                           largo_dibujo=_largo(pts)))
        # flecha y código en el tramo más largo
        segs = sorted(zip(pts, pts[1:]), key=lambda s: -(abs(s[1][0] - s[0][0]) + abs(s[1][1] - s[0][1])))
        if segs:
            a, b = segs[0]; L = abs(b[0] - a[0]) + abs(b[1] - a[1])
            if L > 0.8:
                ux, uy = (b[0] - a[0]) / L, (b[1] - a[1]) / L
                mx, my = (a[0] + b[0]) / 2, (a[1] + b[1]) / 2
                ta = max(0.45, w * 1.3)
                Cn.poli([(mx + ux * ta / 2, my + uy * ta / 2), (mx - ux * ta / 2 - uy * ta * 0.45, my - uy * ta / 2 + ux * ta * 0.45),
                         (mx - ux * ta / 2 + uy * ta * 0.45, my - uy * ta / 2 - ux * ta * 0.45)], "fina", "flecha", True, s=srv,
                        eq=f"{o} {dd}")
                _etiqueta_linea(Cn, codigo, a, b, w, etiquetas, ocupado, f"{o} {dd}", srv)
    # bombas de línea (P-1xx) con válvulas de bloqueo y retención sobre su cañería
    pos_bombas = {}
    for pid, o, dd, ln in bombas:
        li = next((x for x in lineas if x["origen"] == o and x["destino"] == dd), None)
        if li is None or len(li["pts"]) < 2:
            continue
        L = li["largo_dibujo"]
        if L < 2.0:
            continue
        dp = min(2.2, L * 0.35)
        (bx, by), (ux, uy) = _punto_a(li["pts"], dp)
        Cn.circ(bx, by, 0.32, "gruesa", "eq", s="producto")
        nx_, ny_ = -uy, ux
        mx_, my_ = bx + nx_ * 0.62, by + ny_ * 0.62
        Cn.poli([(mx_ - ux * 0.22 - nx_ * 0.28, my_ - uy * 0.22 - ny_ * 0.28), (mx_ + ux * 0.22 - nx_ * 0.28, my_ + uy * 0.22 - ny_ * 0.28),
                 (mx_ + ux * 0.22 + nx_ * 0.28, my_ + uy * 0.22 + ny_ * 0.28), (mx_ - ux * 0.22 + nx_ * 0.28, my_ - uy * 0.22 + ny_ * 0.28)],
                "media", "eq", True)
        Cn.texto(bx + nx_ * 1.25, by + ny_ * 1.25 - 0.12, pid, 0.32, "c", capa="CANERIAS")
        pos_bombas[pid] = (bx, by)
        for dv, tipo_v in ((dp - 0.75, "bloqueo"), (dp + 0.75, "bloqueo"), (dp + 1.35, "retencion")):
            if 0.3 < dv < L - 0.3:
                (vx, vy), (vx_u, vy_u) = _punto_a(li["pts"], dv)
                _valvula(Cn, vx, vy, vx_u, vy_u, tipo_v)
    # --- bandeja eléctrica: del CCM a cada carga, compartiendo tramos
    El = _P("ELECTRICO")
    if ccm:
        sal = LY.puerto([ccm["x"], ccm["y"], ccm["rot"]], dict(largo=ccm["largo"], ancho=ccm["ancho"], alto=ccm["alto"]), "servicio")
        nsal = _normal(ccm["rot"], "servicio")
        G.uso = [0] * (G.nx * G.ny)
        aristas, bajadas = set(), []
        for c in red.get("cables") or []:
            k = c.get("equipo")
            if k in huellas:
                pe = LY.puerto(pos[k], dims[k], "servicio"); ne = _normal(LY._rot(pos[k][2] if len(pos[k]) > 2 else 0), "servicio")
                destino = (pe[0], pe[1])
            elif k in pos_bombas:
                destino = pos_bombas[k]; ne = None
            else:
                continue
            a, da = _salida(G, (sal[0], sal[1]), nsal)
            b = _salida(G, destino, ne)[0] if ne else G.ij(*destino)
            celdas = G.ruta(a, da, b, giro=2.0, premio=0.25)
            if not celdas:
                continue
            for u, v in zip(celdas, celdas[1:]):
                aristas.add(tuple(sorted((u, v))))
            G.marcar(set(celdas))
            bajadas.append((G.xy(*celdas[-1]), destino))
            bajadas.append(((sal[0], sal[1]), G.xy(*celdas[0])))
        for s0, s1 in _fusionar(aristas, G):
            El.linea(*s0, *s1, "bandeja")
        for (ax_, ay_), (bx_, by_) in bajadas:
            for seg in zip(_ortogonalizar([(ax_, ay_), (bx_, by_)]), _ortogonalizar([(ax_, ay_), (bx_, by_)])[1:]):
                El.linea(*seg[0], *seg[1], "bandeja")
            El.circ(bx_, by_, 0.12, "fina", "flecha", s="electricidad")
    mundo = S.p + W.p + Pa.p + E.p + Cn.p + El.p + C.p
    ext = _union([cerco, (X0 - 3.0 - 2 * rb - 4.5, Y0, X1, yc + 2.4), (cerco[0], cerco[1] - 3.4, cerco[2], cerco[1])])
    usados = {x["srv"] for x in lineas} | ({"electricidad"} if ccm and red.get("cables") else set())
    ext_nave = (X0 - 3.0 - 2 * rb - 4.5, min(of[1], bo[1]) - 1.5, X1 + 3.0, yc + 2.4)    # nave y anexos con ejes y cotas
    return dict(vacio=False, equipos=equipos, ccm=ccm, mundo=mundo, ext=ext, ext_nave=ext_nave, sitio=cerco, nave=nave, ejes_x=ejes_x, ejes_y=ejes_y,
                lineas=lineas, bombas=[dict(id=k, x=v[0], y=v[1]) for k, v in pos_bombas.items()], avisos=avisos,
                leyenda=_leyenda(usados), supuestos=SUPUESTOS, mant=mant, recepcion=rec)


def _camion(P, xc, y_frente, y_cola):
    """Camión articulado visto desde arriba, retrocediendo hacia el portón: semirremolque con ejes y tracto con cabina."""
    a = 1.25
    P.rect(xc - a, y_frente - 13.6, xc + a, y_frente, "media", "camion")
    for y in (y_frente - 12.2, y_frente - 11.0, y_frente - 9.8):
        P.rect(xc - a - 0.12, y - 0.45, xc - a + 0.18, y + 0.45, "fina", "muro"); P.rect(xc + a - 0.18, y - 0.45, xc + a + 0.12, y + 0.45, "fina", "muro")
    P.linea(xc - a, y_frente - 0.4, xc + a, y_frente - 0.4, "fina")
    yt = y_frente - 13.9
    P.rect(xc - a * 0.95, yt - 2.6, xc + a * 0.95, yt, "media", "camion")
    P.rect(xc - a * 0.95, y_cola, xc + a * 0.95, yt - 2.6 + 0.0, "media", "camion")
    P.linea(xc - a * 0.8, y_cola + 0.6, xc + a * 0.8, y_cola + 0.6, "fina")


def _valvula(P, x, y, ux, uy, tipo):
    """Válvula sobre la línea: corbatín (bloqueo) o corbatín con una mitad rellena (retención)."""
    nx_, ny_ = -uy, ux; a, b = 0.28, 0.2
    izq = [(x, y), (x - ux * a + nx_ * b, y - uy * a + ny_ * b), (x - ux * a - nx_ * b, y - uy * a - ny_ * b)]
    der = [(x, y), (x + ux * a + nx_ * b, y + uy * a + ny_ * b), (x + ux * a - nx_ * b, y + uy * a - ny_ * b)]
    P.poli(izq, "media", "eq", True)
    P.poli(der, "media", "flecha" if tipo == "retencion" else "eq", True)


def _etiqueta_linea(P, texto, a, b, w, puestas, ocupado, eq, srv=None):
    """Código de línea junto al tramo, sin tapar equipos ni otros códigos; si no cabe en ninguna posición se omite.
    PAT 140 i: el texto lleva el servicio (clave srv) para escribirse con el color del servicio en las dos vistas."""
    L = abs(b[0] - a[0]) + abs(b[1] - a[1])
    largo_txt = len(texto) * H_LINEA * 0.58
    if L < largo_txt + 0.6:
        return
    horizontal = abs(b[1] - a[1]) < 1e-9
    for t in (0.5, 0.3, 0.7, 0.18, 0.82):
        for lado in (1, -1):
            mx, my = a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
            off = w / 2 + 0.12
            if horizontal:
                caja = (mx - largo_txt / 2, my + lado * off - (H_LINEA if lado < 0 else 0), mx + largo_txt / 2,
                        my + lado * off + (H_LINEA if lado > 0 else 0))
            else:
                caja = (mx + lado * off - (H_LINEA if lado < 0 else 0), my - largo_txt / 2, mx + lado * off + (H_LINEA if lado > 0 else 0),
                        my + largo_txt / 2)
            if any(_cruza(caja, c) for c in puestas) or any(_cruza(caja, c) for c in ocupado):
                continue
            puestas.append(caja)
            if horizontal:
                P.texto(mx, caja[1] + H_LINEA * 0.12, texto, H_LINEA, "c", capa="CANERIAS")
            else:
                P.texto(caja[2] - H_LINEA * 0.12, my, texto, H_LINEA, "c", 90, capa="CANERIAS")
            P.p[-1]["eq"] = eq
            if srv in SERVICIOS:
                P.p[-1]["srv"] = srv
            return


def _fusionar(aristas, G):
    """Une las aristas de celda de la bandeja en tramos rectos máximos."""
    hor, ver = {}, {}
    for (i1, j1), (i2, j2) in aristas:
        if j1 == j2:
            hor.setdefault(j1, []).append(min(i1, i2))
        else:
            ver.setdefault(i1, []).append(min(j1, j2))
    out = []
    for j, xs in hor.items():
        xs = sorted(set(xs)); ini = prev = xs[0]
        for i in xs[1:] + [None]:
            if i is None or i != prev + 1:
                out.append((G.xy(ini, j), G.xy(prev + 1, j)))
                ini = i
            prev = i if i is not None else prev
    for i, ys in ver.items():
        ys = sorted(set(ys)); ini = prev = ys[0]
        for j in ys[1:] + [None]:
            if j is None or j != prev + 1:
                out.append((G.xy(i, ini), G.xy(i, prev + 1)))
                ini = j
            prev = j if j is not None else prev
    return out


def _leyenda(usados) -> list[dict]:
    """Leyenda de servicios: los seis pedidos siempre (producto, agua, vapor, condensado, aire y electricidad)."""
    return [dict(srv=k, nombre=v[0], color=v[1], abreviatura=v[2], presente=k in usados) for k, v in SERVICIOS.items()]


def primitivas_mundo(m: dict, capas: set | None = None) -> list[dict]:
    """Todas las primitivas en coordenadas del plano (equipos y sala eléctrica transformados), en orden de dibujo, solo de las capas
    pedidas (None = todas). Las etiquetas de los equipos van en la capa TEXTOS."""
    capas = set(CAPAS) if capas is None else set(capas)
    if m.get("vacio"):
        return []
    out = [q for q in m["mundo"] if q["capa"] in ("SITIO", "EDIFICIO", "PASILLOS", "EJES")]
    for e in m["equipos"]:
        out += _transformar(e["mant"], e["x"], e["y"], e["rot"])
    for e in m["equipos"] + ([m["ccm"]] if m.get("ccm") else []):
        out += _transformar(e["prims"], e["x"], e["y"], e["rot"])
    out += [q for q in m["mundo"] if q["capa"] in ("CANERIAS", "ELECTRICO")]
    out += [q for q in m["mundo"] if q["capa"] == "COTAS"]
    out += etiquetas_equipos(m)
    return [q for q in out if q["capa"] in capas]


def etiquetas_equipos(m: dict) -> list[dict]:
    """Código y nombre corto de cada equipo junto a su huella (abajo o arriba, en la franja de mantención, sin tapar el dibujo)."""
    return [dict(k="text", capa="TEXTOS", x=e["etq"][0], y=e["etq"][1], s=e["etq"][3], h=e["etq"][2], anc="c", rot=0, id=e["id"])
            for e in m["equipos"] + ([m["ccm"]] if m.get("ccm") else []) if e.get("etq")]


def _ancho_txt(s, h):
    return len(str(s)) * h * 0.64


def _caja_txt(q):
    w = _ancho_txt(q["s"], q["h"])
    x0 = q["x"] - (w / 2 if q.get("anc", "c") == "c" else (w if q.get("anc") == "r" else 0))
    if q.get("rot") == 90:
        return (q["x"] - q["h"], q["y"] - w / 2, q["x"] + 0.1, q["y"] + w / 2)
    return (x0, q["y"] - 0.1, x0 + w, q["y"] + q["h"])


def _poner_etiquetas(equipos, ocupado):
    """Etiqueta de cada equipo: debajo de la huella; si choca con otra, arriba; si sigue chocando, más chica o solo el código."""
    puestas = []
    for e in sorted(equipos, key=lambda e: (-e["huella"][1], e["huella"][0])):
        h = e["huella"]
        hecho = False
        for txt, alto in ((f"{e['id']} {e['corto']}", H_ETIQ), (f"{e['id']} {e['corto']}", H_ETIQ * 0.75), (e["id"], H_ETIQ)):
            for y in (h[1] - 0.12 - alto, h[3] + 0.12):
                q = dict(s=txt, h=alto, x=e["x"], y=y, anc="c")
                c = _caja_txt(q)
                if not any(_cruza(c, o) for o in puestas) and not any(_cruza(c, o) for o in ocupado if o is not h):
                    e["etq"] = (e["x"], y, alto, txt); puestas.append(c); hecho = True
                    break
            if hecho:
                break
        if not hecho:
            e["etq"] = (e["x"], h[1] - 0.12 - H_ETIQ, H_ETIQ, e["id"]); puestas.append(_caja_txt(dict(s=e["id"], h=H_ETIQ, x=e["x"], y=h[1] - 0.12 - H_ETIQ)))
    return puestas


# ------------------------------------------------------------------------------------------- SVG
_PX = {"muro": 0.6, "gruesa": 1.7, "media": 1.05, "fina": 0.6, "mant": 0.8, "oculta": 0.9, "eje": 0.6, "bandeja": 1.7,
       "pasillo": 0.9, "cota": 0.6}
_DASH = {"mant": "0.3 0.22", "oculta": "0.5 0.25", "eje": "1.6 0.4 0.2 0.4", "bandeja": "0.7 0.25 0.12 0.25", "pasillo": "0.9 0.5"}
_TRAZO_PLANO = {"SITIO": "#555", "EDIFICIO": "#111", "PASILLOS": "#555", "EJES": "#444", "MANTENCION": "#6a6a6a", "EQUIPOS": "#111",
                "CANERIAS": "#111", "ELECTRICO": "#111", "TEXTOS": "#111", "COTAS": "#222"}
_TRAZO_COLOR = {"SITIO": "#8b979d", "EDIFICIO": "#3e4d55", "PASILLOS": "#c99a2e", "EJES": "#b0302a", "MANTENCION": "#7d97a1",
                "EQUIPOS": "#1f4f43", "CANERIAS": "#1f4f43", "ELECTRICO": "#8a6d00", "TEXTOS": "#17303d", "COTAS": "#34495e"}
_RELLENO_COLOR = {"eq": "#e4efe9", "muro": "#4b5a62", "piso": "#ffffff", "terreno": "#eef2ea", "calle": "#dfe3e5", "oficina": "#eaf0f6",
                  "bodega": "#f2efe6", "calderas": "#fbebe7", "sala_el": "#fbf2cf", "celda": "#f1d978", "estac": "#dfe3e5",
                  "camion": "#ffffff", "cerco": "#5b6b73", "flecha": "#1f4f43", "burbuja": "#ffffff"}
_RELLENO_PLANO = {"muro": "#262626", "cerco": "#262626", "flecha": "#111", "celda": "#d9d9d9"}


def css(modo: str = "plano", u: float | None = None, raiz: str = "svg") -> str:
    """Hoja de estilo del plano. u = metros por píxel para escribir los anchos de línea como número (SVG para descargar); sin u,
    los anchos usan la variable --u que el componente actualiza con el zoom (el trazo se ve igual a cualquier escala)."""
    color = modo == "color"
    W = (lambda px: f"{px * u:.4f}") if u else (lambda px: f"calc({px} * var(--u, 0.1))")
    r = [f"{raiz} .t{{font-family:'Source Sans Pro','Segoe UI',Arial,sans-serif;paint-order:stroke;stroke:#fff;stroke-linejoin:round}}"]
    for capa in CAPAS:
        col = (_TRAZO_COLOR if color else _TRAZO_PLANO)[capa]
        r.append(f"{raiz} .k-{capa}{{stroke:{col};fill:none}} {raiz} .t.k-{capa}{{fill:{col};stroke:#fff}}")
    for e, px in _PX.items():
        r.append(f"{raiz} .e-{e}{{stroke-width:{W(px)}" + (f";stroke-dasharray:{_DASH[e]}" if e in _DASH else "") + "}")
    for f, col in _RELLENO_COLOR.items():
        r.append(f"{raiz} .f-{f}{{fill:{col if color else _RELLENO_PLANO.get(f, '#fff')}}}")
    if not color:
        r.append(f"{raiz} .f-terreno,{raiz} .f-calle,{raiz} .f-piso{{fill:#fff}}")
    r.append(f"{raiz} .e-muro{{stroke-width:{W(0.5)}}} {raiz} .tubo-int{{stroke:#fff;fill:none}} {raiz} .tubo{{fill:none;stroke-linejoin:miter}}")
    for k, (_n, col, _a) in SERVICIOS.items():
        if color:
            r.append(f"{raiz} .tubo.s-{k}{{stroke:{col}}} {raiz} .f-flecha.s-{k}{{fill:{col};stroke:{col}}} {raiz} .k-ELECTRICO.e-bandeja{{stroke:{SERVICIOS['electricidad'][1]}}}")
        else:
            r.append(f"{raiz} .tubo.s-{k}{{stroke:#111}}")
    for k, (_n, col, _a) in SERVICIOS.items():           # PAT 140 i: el código de cada línea va con el color de su servicio en las dos vistas
        r.append(f"{raiz} .t.k-CANERIAS.s-{k}{{fill:{col}}}")
    r.append(f"{raiz} .tubo-int{{display:{'none' if color else 'inline'}}} {raiz} .ancho .tubo-int{{display:inline}}")
    r.append(f"{raiz} .e-tubo-borde{{stroke-width:0}}")
    return "\n".join(r)


def _clase(q) -> str:
    c = [f"k-{q['capa']}", f"e-{q.get('e', 'fina')}"]
    if q.get("f"):
        c.append(f"f-{q['f']}")
    if q.get("s"):
        c.append(f"s-{q['s']}")
    return " ".join(c)


def _pts(pts) -> str:
    return " ".join(f"{a:.3f},{-b:.3f}" for a, b in pts)


def svg_primitivas(prims: list[dict]) -> str:
    """Primitivas a elementos SVG con y hacia abajo (y_svg = -y) y clases de estilo."""
    o = []
    for q in prims:
        extra = f' data-eq="{_esc(q["eq"])}"' if q.get("eq") else ""
        if q["k"] == "poly":
            tag = "polygon" if q.get("cerr") else "polyline"
            o.append(f'<{tag} class="{_clase(q)}" points="{_pts(q["pts"])}"{extra}/>')
        elif q["k"] == "circ":
            o.append(f'<circle class="{_clase(q)}" cx="{q["c"][0]:.3f}" cy="{-q["c"][1]:.3f}" r="{q["r"]:.3f}"{extra}/>')
        elif q["k"] == "tubo":
            d = _pts(q["pts"])
            ancho = ' class="ancho"' if q.get("medio") in ("transportador", "ducto") else ""
            o.append(f'<g{ancho}{extra} data-linea="{_esc(q.get("linea", ""))}"><polyline class="tubo s-{q["s"]}" points="{d}" stroke-width="{q["w"]:.3f}"/>'
                     f'<polyline class="tubo-int" points="{d}" stroke-width="{q["w"] * (0.72 if ancho else 0.55):.3f}"/></g>')
        elif q["k"] == "text":
            anc = {"l": "start", "c": "middle", "r": "end"}[q.get("anc", "c")]
            rot = f' transform="rotate({-q["rot"]} {q["x"]:.3f} {-q["y"]:.3f})"' if q.get("rot") else ""
            srv = f' s-{q["srv"]}' if q.get("srv") in SERVICIOS else ""      # PAT 140 i: código de línea con el color del servicio
            o.append(f'<text class="t k-{q["capa"]}{srv}" x="{q["x"]:.3f}" y="{-q["y"]:.3f}" font-size="{q["h"] / 0.72:.3f}" '
                     f'stroke-width="{q["h"] * 0.28:.3f}" text-anchor="{anc}"{rot}{extra}>{_esc(q["s"])}</text>')
    return "".join(o)


def fragmentos(m: dict) -> dict:
    """Datos para el componente: SVG por capa del mundo y SVG local de cada equipo (símbolo y zona de mantención)."""
    capas = {c: svg_primitivas([q for q in m.get("mundo", []) if q["capa"] == c]) for c in CAPAS}
    eqs = []
    for e in m.get("equipos", []) + ([m["ccm"]] if m.get("ccm") else []):
        et = e.get("etq") or (e["x"], e["huella"][1] - 0.12 - H_ETIQ, H_ETIQ, e["id"])
        eqs.append(dict(id=e["id"], svg=svg_primitivas(e["prims"]), mant=svg_primitivas(e["mant"]),
                        etiqueta=dict(s=et[3], dx=et[0] - e["x"], dy=et[1] - e["y"], h=et[2])))
    return dict(capas=capas, simbolos=eqs, ext=list(m["ext"]), ext_nave=list(m.get("ext_nave") or m["ext"]), h_etiqueta=H_ETIQ)


def a_svg(m: dict, modo: str = "plano", capas: set | None = None, ancho_px: int = 1400, y_corte: float | None = None) -> str:
    """Plano completo para descargar: dibujo a escala con estilo de la vista elegida, leyenda de servicios, escala gráfica, norte y
    rótulo (proyecto, título, fecha y autor). Planta vacía: SVG con un aviso."""
    caj = m.get("cajetin") or {}
    if m.get("vacio"):
        return ('<svg xmlns="http://www.w3.org/2000/svg" width="420" height="60"><text x="10" y="35" font-family="Arial" font-size="14">'
                'Planta vacía: agregue equipos en Diseño.</text></svg>')
    x0, y0, x1, y1 = m["ext"]
    x0 -= 1.0; y0 -= 1.0; x1 += 1.0; y1 += 1.0
    s = (ancho_px - 40) / (x1 - x0)
    alto_dib = (y1 - y0) * s
    pie = 120
    H = alto_dib + 40 + pie
    u = 1.0 / s
    prims = primitivas_mundo(m, capas)
    if y_corte is not None and (capas is None or "COTAS" in capas):
        P = _P("COTAS")
        P.linea(m["nave"][0] - 2, y_corte, m["nave"][2] + 2, y_corte, "eje")
        P.texto(m["nave"][0] - 2.6, y_corte - 0.35, "A", 1.0); P.texto(m["nave"][2] + 2.6, y_corte - 0.35, "A", 1.0)
        for q in P.p:
            q["capa"] = "COTAS"
        prims += P.p
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{ancho_px}" height="{H:.0f}" viewBox="0 0 {ancho_px} {H:.0f}" '
         f'font-family="Arial, Helvetica, sans-serif">',
         f"<style>{css(modo, u, 'svg.dib')}</style>",
         f'<rect width="100%" height="100%" fill="#ffffff"/>',
         f'<svg class="dib" x="20" y="20" width="{ancho_px - 40}" height="{alto_dib:.1f}" viewBox="{x0:.3f} {-y1:.3f} {x1 - x0:.3f} {y1 - y0:.3f}">',
         svg_primitivas(prims), "</svg>"]
    # pie: leyenda, escala, norte y rótulo
    yp = alto_dib + 40
    color = modo == "color"
    o.append(f'<line x1="20" y1="{yp:.1f}" x2="{ancho_px - 20}" y2="{yp:.1f}" stroke="#222" stroke-width="1"/>')
    xl = 24
    for i, it in enumerate(m["leyenda"]):
        cx = xl + (i % 3) * 210; cy = yp + 22 + (i // 3) * 22
        col = it["color"]                                    # PAT 140 i: la muestra va con el color del servicio también en la vista de plano
        da = ' stroke-dasharray="6 3 2 3"' if it["srv"] == "electricidad" else ""
        o.append(f'<line x1="{cx}" y1="{cy}" x2="{cx + 34}" y2="{cy}" stroke="{col}" stroke-width="4"{da}/>')
        o.append(f'<text x="{cx + 42}" y="{cy + 4}" font-size="12" fill="#222">{_esc(it["nombre"])} ({it["abreviatura"]})</text>')
    o.append(f'<text x="{xl}" y="{yp + 82}" font-size="11" fill="#444">Código de línea: corriente-DN-servicio (CT cinta, DU ducto). '
             f'Punteado fino: zona de mantención. Cotas en m.</text>')
    # escala gráfica de 10 m
    L10 = 10 * s
    xe = 680; ye = yp + 30
    for i in range(5):
        o.append(f'<rect x="{xe + i * L10 / 5:.1f}" y="{ye}" width="{L10 / 5:.1f}" height="6" fill="{"#222" if i % 2 == 0 else "#fff"}" stroke="#222" stroke-width="0.8"/>')
    o.append(f'<text x="{xe}" y="{ye + 22}" font-size="11">0</text><text x="{xe + L10:.1f}" y="{ye + 22}" font-size="11" text-anchor="middle">10 m</text>')
    o.append(f'<text x="{xe}" y="{ye - 8}" font-size="11" fill="#444">Escala gráfica</text>')
    xn = xe + L10 + 60
    o.append(f'<g transform="translate({xn:.1f},{yp + 45})"><circle r="20" fill="none" stroke="#222"/><path d="M0 -17 L7 10 L0 4 L-7 10 Z" fill="#222"/>'
             f'<text y="-24" font-size="13" font-weight="bold" text-anchor="middle">N</text></g>')
    xr = ancho_px - 20 - 360
    filas = (("Proyecto", caj.get("proyecto", "")), ("Título", caj.get("titulo", "")), ("Fecha", caj.get("fecha", "")),
             ("Autor", caj.get("autor", "")))
    o.append(f'<rect x="{xr}" y="{yp + 8}" width="360" height="{len(filas) * 24}" fill="none" stroke="#222"/>')
    for i, (et, v) in enumerate(filas):
        yy = yp + 8 + i * 24
        if i:
            o.append(f'<line x1="{xr}" y1="{yy}" x2="{xr + 360}" y2="{yy}" stroke="#222" stroke-width="0.6"/>')
        o.append(f'<text x="{xr + 6}" y="{yy + 16}" font-size="10" fill="#555">{et}</text>'
                 f'<text x="{xr + 70}" y="{yy + 16}" font-size="{min(13.0, 282 / max(1, len(str(v)) * 0.55)):.1f}" fill="#111">{_esc(v)}</text>')
    o.append("</svg>")
    return "".join(o)
