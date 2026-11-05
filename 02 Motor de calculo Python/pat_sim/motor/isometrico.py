"""Vista isométrica del layout al estilo Anatomy (PAT 135, tarea T15; pedido del profesor Torres del 04-11-2026).

Qué hace: dibuja en SVG la planta del layout (motor/layout.py) en proyección isométrica de 30°, con los equipos como sólidos
(prismas para equipos rectangulares; cilindros verticales para estanques, evaporadores y columnas; cilindros horizontales para
intercambiadores, secadores rotatorios y calderas) con sombreado de cuatro tonos (superior, izquierda, derecha y contorno), las
cañerías como tubos con el color de su tipo de corriente (el mismo de la leyenda de Diseño, motor/corrientes.py), el rack de
cañerías, la sala eléctrica (CCM), la bandeja eléctrica y los alimentadores. El orden de dibujo es el algoritmo del pintor: lo
más lejano primero, con un orden parcial entre cajas separadas por un eje (ordenamiento topológico).

Cámara (convención PAT 135): x al este, y al norte, z hacia arriba. La cámara gira en 4 orientaciones alrededor del centro de la
planta: 0° desde el sureste, 90° desde el noreste, 180° desde el noroeste y 270° desde el suroeste. En coordenadas de cámara
(a, b) el observador queda hacia +a, +b y arriba; pantalla: sx = (b − a)·cos 30°, sy = (a + b)·sen 30° − z (y hacia abajo).
La cara +a se ve a la izquierda y la +b a la derecha.

Relación con Anatomy (skill de Claude, https://github.com/wheresryan22/anatomy, v1.1.0): se usa la misma cámara isométrica y el
sombreado de cuatro tonos, pero calculado al instante desde el layout, porque Anatomy necesita un agente y minutos por figura.
Gancho: si la tabla simbolos del mantenedor trae un SVG con norma «ISO-ISOMETRICO» para el símbolo, el tipo o la familia del
equipo (figuras hechas después con Anatomy), se usa esa figura en vez del sólido genérico, ajustada a la caja proyectada.
"""
from __future__ import annotations
import heapq
import json
import math
import re
from . import layout as LY
from .corrientes import TIPOS as TIPOS_CORRIENTE

COS30 = math.cos(math.radians(30))
SIN30 = 0.5
NORMA_FIGURAS = "ISO-ISOMETRICO"
VISTAS = {0: "Vista desde el sureste", 90: "Vista desde el noreste", 180: "Vista desde el noroeste", 270: "Vista desde el suroeste"}
R_TUBO_M = 0.15        # m; Supuesto de dibujo: radio aparente de los tubos (no es el diámetro de cálculo)
SEP_RACK_M = 0.3       # m; Supuesto de dibujo: separación vertical entre las cañerías que comparten el rack (cuatro niveles)
ANCHO_RACK_M = 1.2     # m; Supuesto de dibujo: ancho de la viga del rack
ANCHO_BANDEJA_M = 0.4  # m; Supuesto de dibujo: ancho de la bandeja portaconductores
PASO_POSTE_M = 6.0     # m; Supuesto de dibujo: distancia entre postes del rack
COLOR_CCM = "#e8c547"
COLOR_RACK = "#8d99a3"
COLOR_BANDEJA = "#d4ac0d"   # «Energía eléctrica» de la leyenda de Diseño
FORMA_FAMILIA = {"evaporador": "cilindro_v", "recipiente": "cilindro_v", "columna": "cilindro_v", "enfriador": "cilindro_v",
                 "intercambiador": "cilindro_h", "secador_rotatorio": "cilindro_h", "caldera": "cilindro_h"}
COLOR_FAMILIA = {"tolva": "#a9b98e", "separador": "#9fb4c8", "molienda": "#b5a48e", "intercambiador": "#9cc3cf", "evaporador": "#b9cbd6",
                 "recipiente": "#a8c6d8", "acabado": "#b9b2cf", "caldera": "#cf9f84", "hogar": "#c98f78", "secador_rotatorio": "#d0b781",
                 "secador_banda": "#d0b781", "secador_camara": "#d0b781", "pelletizadora": "#b5a48e", "enfriador": "#a8c6d8",
                 "bomba": "#7fa6c4", "valvula": "#8fa1ad", "transportador": "#a9b98e", "maquina_rotativa": "#9fb0bb", "columna": "#b9cbd6",
                 "general": "#b4c3cb"}


# ------------------------------------------------------------------------------------------- cámara y proyección
def camara(x: float, y: float, rot: int = 0, cx: float = 0.0, cy: float = 0.0) -> tuple[float, float]:
    """Coordenadas de cámara (a, b) del punto (x, y) para la orientación rot (0, 90, 180 o 270) alrededor de (cx, cy)."""
    r = int(round(float(rot or 0) / 90.0)) % 4
    u, v = x - cx, y - cy
    for _ in range(r):                    # girar el mundo −90° por cada paso de cámara: (u, v) → (v, −u)
        u, v = v, -u
    return -v, u                          # rot 0: a = −y (sur hacia el observador), b = x (este hacia el observador)


def proyectar(a: float, b: float, z: float) -> tuple[float, float]:
    """Proyección isométrica de 30°: sx = (b − a)·cos 30°, sy = (a + b)·sen 30° − z (pantalla con y hacia abajo)."""
    return (b - a) * COS30, (a + b) * SIN30 - z


def caja_camara(h: tuple, z1: float, z2: float, rot: int, cx: float, cy: float) -> tuple:
    """Caja (a1, a2, b1, b2, z1, z2) en coordenadas de cámara de una huella (xmin, ymin, xmax, ymax)."""
    pts = [camara(x, y, rot, cx, cy) for x in (h[0], h[2]) for y in (h[1], h[3])]
    return (min(p[0] for p in pts), max(p[0] for p in pts), min(p[1] for p in pts), max(p[1] for p in pts), z1, z2)


# ------------------------------------------------------------------------------------------- colores
def _rgb(c: str) -> tuple[int, int, int]:
    c = c.lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def mezcla(c1: str, c2: str, t: float) -> str:
    """Color entre c1 (t = 0) y c2 (t = 1), en hexadecimal."""
    a, b = _rgb(c1), _rgb(c2)
    return "#" + "".join(f"{round(x + (y - x) * t):02x}" for x, y in zip(a, b))


def tonos(base: str) -> dict:
    """Sombreado de cuatro tonos al estilo Anatomy: superior (luz de arriba), izquierda (base), derecha (sombra) y contorno."""
    return dict(superior=mezcla(base, "#ffffff", 0.45), izquierda=base, derecha=mezcla(base, "#000000", 0.25),
                contorno=mezcla(base, "#000000", 0.6))


def forma(familia: str) -> str:
    """Sólido genérico de la familia de dimensiones: prisma, cilindro_v o cilindro_h."""
    return FORMA_FAMILIA.get(familia, "prisma")


# ------------------------------------------------------------------------------------------- algoritmo del pintor
def _antes(A: tuple, B: tuple, eps: float = 1e-6) -> bool:
    """A va detrás de B (se pinta antes) si un eje los separa con A del lado lejano (a, b menores) o abajo (z menor)."""
    return A[1] <= B[0] + eps or A[3] <= B[2] + eps or A[5] <= B[4] + eps


def _bbox_pantalla(c: tuple) -> tuple[float, float, float, float]:
    ps = [proyectar(a, b, z) for a in c[0:2] for b in c[2:4] for z in c[4:6]]
    return (min(p[0] for p in ps), min(p[1] for p in ps), max(p[0] for p in ps), max(p[1] for p in ps))


def orden_pintor(items: list[dict]) -> list[dict]:
    """Ordena los ítems (cada uno con «caja» en coordenadas de cámara) de atrás hacia adelante: orden parcial entre los que se
    traslapan en pantalla (_antes en un solo sentido) y, entre los libres, primero el de menor a + b y menor z (más lejano).
    Si hay un ciclo, se rompe con el más lejano."""
    n = len(items)
    bb = [_bbox_pantalla(it["caja"]) for it in items]
    sig = [[] for _ in range(n)]; grado = [0] * n
    for i in range(n):
        for j in range(i + 1, n):
            p, q = bb[i], bb[j]
            if p[2] <= q[0] or q[2] <= p[0] or p[3] <= q[1] or q[3] <= p[1]:
                continue
            ij, ji = _antes(items[i]["caja"], items[j]["caja"]), _antes(items[j]["caja"], items[i]["caja"])
            if ij and not ji:
                sig[i].append(j); grado[j] += 1
            elif ji and not ij:
                sig[j].append(i); grado[i] += 1

    def clave(i):
        c = items[i]["caja"]
        return ((c[0] + c[1]) / 2 + (c[2] + c[3]) / 2, (c[4] + c[5]) / 2, i)
    listos = [clave(i) for i in range(n) if grado[i] == 0]
    heapq.heapify(listos)
    hecho = [False] * n; out = []
    while len(out) < n:
        if not listos:                                    # ciclo: el más lejano de los que faltan
            i = min((k for k in range(n) if not hecho[k]), key=clave)
            grado[i] = 0; heapq.heappush(listos, clave(i))
        i = heapq.heappop(listos)[2]
        if hecho[i]:
            continue
        hecho[i] = True; out.append(items[i])
        for j in sig[i]:
            grado[j] -= 1
            if grado[j] == 0 and not hecho[j]:
                heapq.heappush(listos, clave(j))
    return out


# ------------------------------------------------------------------------------------------- recorridos
def ruta_tubo(p1, p2, z_rack: float = LY.H_RACK_M, por_rack: bool = True) -> list[tuple]:
    """Recorrido ortogonal de la cañería entre puertos (x, y, z): sube al rack, va según x y después según y, y baja. Sin rack
    (transportadores) va a la altura de la salida y baja o sube al final."""
    x1, y1, z1 = (float(v) for v in p1); x2, y2, z2 = (float(v) for v in p2)
    z = z_rack if por_rack else z1
    pts = [(x1, y1, z1), (x1, y1, z), (x2, y1, z), (x2, y2, z), (x2, y2, z2)]
    out = [pts[0]]
    for p in pts[1:]:
        if max(abs(p[k] - out[-1][k]) for k in range(3)) > 1e-9:
            out.append(p)
    return out


def _convexa(pts: list[tuple]) -> list[tuple]:
    """Envolvente convexa (cadena monótona de Andrew)."""
    p = sorted(set((round(x, 3), round(y, 3)) for x, y in pts))
    if len(p) <= 2:
        return p
    cruz = lambda o, a, b: (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    lo, hi = [], []
    for q in p:
        while len(lo) >= 2 and cruz(lo[-2], lo[-1], q) <= 0:
            lo.pop()
        lo.append(q)
    for q in reversed(p):
        while len(hi) >= 2 and cruz(hi[-2], hi[-1], q) <= 0:
            hi.pop()
        hi.append(q)
    return lo[:-1] + hi[:-1]


# ------------------------------------------------------------------------------------------- sólidos (SVG)
def _pol(pts, fill, stroke, sw=1.0, extra="") -> str:
    return (f'<polygon points="{" ".join(f"{x:.1f},{y:.1f}" for x, y in pts)}" fill="{fill}" stroke="{stroke}" '
            f'stroke-width="{sw}" stroke-linejoin="round"{extra}/>')


def prisma(P, caja: tuple, t: dict) -> str:
    """Prisma: cara superior, cara +a (izquierda) y cara +b (derecha) con sus tonos; contorno oscuro."""
    a1, a2, b1, b2, z1, z2 = caja
    sup = [P(a1, b1, z2), P(a2, b1, z2), P(a2, b2, z2), P(a1, b2, z2)]
    izq = [P(a2, b1, z1), P(a2, b2, z1), P(a2, b2, z2), P(a2, b1, z2)]
    der = [P(a1, b2, z1), P(a2, b2, z1), P(a2, b2, z2), P(a1, b2, z2)]
    return (_pol(izq, t["izquierda"], t["contorno"]) + _pol(der, t["derecha"], t["contorno"]) + _pol(sup, t["superior"], t["contorno"]))


def recortar_x(pol: list[tuple], xc: float, izquierda: bool = True) -> list[tuple]:
    """Recorte de un polígono convexo por la recta vertical x = xc (Sutherland y Hodgman, 1974): mitad izquierda o derecha."""
    dentro = (lambda p: p[0] <= xc + 1e-9) if izquierda else (lambda p: p[0] >= xc - 1e-9)
    out = []
    for i, q in enumerate(pol):
        p = pol[i - 1]
        if dentro(q):
            if not dentro(p) and q[0] != p[0]:
                out.append((xc, p[1] + (q[1] - p[1]) * (xc - p[0]) / (q[0] - p[0])))
            out.append(q)
        elif dentro(p) and q[0] != p[0]:
            out.append((xc, p[1] + (q[1] - p[1]) * (xc - p[0]) / (q[0] - p[0])))
    return out


def cilindro_v(P, caja: tuple, t: dict, n: int = 40) -> str:
    """Cilindro vertical de sección elíptica inscrita en la caja (toca las cuatro caras, donde están los puertos): manto partido
    en mitad izquierda y derecha con sus tonos, tapa superior con el tono superior y contorno."""
    a1, a2, b1, b2, z1, z2 = caja
    ra, rb = (a2 - a1) / 2, (b2 - b1) / 2; ac, bc = (a1 + a2) / 2, (b1 + b2) / 2
    ang = [2 * math.pi * i / n for i in range(n)]
    arriba = [P(ac + ra * math.cos(q), bc + rb * math.sin(q), z2) for q in ang]
    abajo = [P(ac + ra * math.cos(q), bc + rb * math.sin(q), z1) for q in ang]
    cuerpo = _convexa(arriba + abajo)
    xc = P(ac, bc, z2)[0]
    return (_pol(recortar_x(cuerpo, xc, True), t["izquierda"], "none", 0) + _pol(recortar_x(cuerpo, xc, False), t["derecha"], "none", 0)
            + _pol(cuerpo, "none", t["contorno"]) + _pol(arriba, t["superior"], t["contorno"]))


def cilindro_h(P, caja: tuple, t: dict, n: int = 32) -> str:
    """Cilindro horizontal según el lado largo de la caja, sobre dos silletas: manto (tono del costado visible), franja superior
    (tono superior), tapa cercana (tono de esa cara) y contorno."""
    a1, a2, b1, b2, z1, z2 = caja
    eje_a = (a2 - a1) >= (b2 - b1)
    corto = (b2 - b1) if eje_a else (a2 - a1)
    r = min(corto, z2 - z1) / 2; zc = z2 - r
    ac, bc = (a1 + a2) / 2, (b1 + b2) / 2
    ang = [2 * math.pi * i / n for i in range(n)]

    def aro(u):
        if eje_a:
            return [(u, bc + r * math.cos(q), zc + r * math.sin(q)) for q in ang]
        return [(ac + r * math.cos(q), u, zc + r * math.sin(q)) for q in ang]
    e1, e2 = (aro(a1), aro(a2)) if eje_a else (aro(b1), aro(b2))
    pr = lambda pts: [P(*p) for p in pts]
    o = []
    if zc - r > z1 + 1e-6:                                 # silletas al 20 % y al 80 % del largo
        for f in (0.2, 0.8):
            if eje_a:
                u = a1 + f * (a2 - a1); cj = (u - 0.15, u + 0.15, bc - 0.8 * r, bc + 0.8 * r, z1, zc)
            else:
                u = b1 + f * (b2 - b1); cj = (ac - 0.8 * r, ac + 0.8 * r, u - 0.15, u + 0.15, z1, zc)
            o.append(prisma(P, cj, tonos("#7f8c8d")))
    cuerpo = _convexa(pr(e1 + e2))
    arriba = _convexa(pr([p for p in e1 + e2 if p[2] >= zc - 1e-9]))
    lado, tapa_t = ("derecha", "izquierda") if eje_a else ("izquierda", "derecha")
    o.append(_pol(cuerpo, t[lado], t["contorno"]))
    o.append(_pol(arriba, t["superior"], "none", 0))
    o.append(_pol(pr(e2), t[tapa_t], t["contorno"]))
    o.append(_pol(cuerpo, "none", t["contorno"]))
    return "".join(o)


def tubo(P, pts: list[tuple], color: str, ancho: float, raya: str = "") -> str:
    """Tubo: contorno oscuro, cuerpo del color de la corriente y brillo claro desplazado hacia arriba (sensación de volumen)."""
    xy = [P(*p) for p in pts]
    s = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    s2 = " ".join(f"{x:.1f},{y - ancho * 0.22:.1f}" for x, y in xy)
    base = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    return (f'<polyline points="{s}" {base} stroke="{mezcla(color, "#000000", 0.55)}" stroke-width="{ancho + 2:.1f}"{raya}/>'
            f'<polyline points="{s}" {base} stroke="{color}" stroke-width="{ancho:.1f}"{raya}/>'
            f'<polyline points="{s2}" {base} stroke="{mezcla(color, "#ffffff", 0.55)}" stroke-width="{max(1.0, ancho * 0.3):.1f}" opacity="0.8"{raya}/>')


# ------------------------------------------------------------------------------------------- figuras de Anatomy (gancho)
def _limpiar_svg(svg: str) -> str:
    s = re.sub(r"<\?xml[^>]*\?>|<!DOCTYPE[^>]*>|<!--.*?-->", "", str(svg or ""), flags=re.S)
    s = re.sub(r"<script\b.*?</script\s*>", "", s, flags=re.S | re.I)
    s = re.sub(r"\son\w+\s*=\s*(\"[^\"]*\"|'[^']*')", "", s, flags=re.I)
    return s.strip()


def figura_incrustada(svg: str, x: float, y: float, w: float, h: float) -> str:
    """Pone un SVG externo (figura isométrica del mantenedor) dentro del rectángulo (x, y, w, h), apoyado abajo y centrado. Quita
    scripts y atributos de eventos. Si la figura no trae viewBox se arma con su width y height. Vacío si no es SVG."""
    s = _limpiar_svg(svg)
    m = re.search(r"<svg\b([^>]*)>", s, flags=re.I)
    if not m:
        return ""
    attrs = m.group(1)
    vb = re.search(r'viewBox\s*=\s*["\']([^"\']+)["\']', attrs)
    if vb:
        caja = vb.group(1)
    else:
        num = lambda k: re.search(rf'\b{k}\s*=\s*["\']?\s*([\d.]+)', attrs)
        W, H = num("width"), num("height")
        caja = f"0 0 {W.group(1) if W else 100} {H.group(1) if H else 100}"
    resto = re.sub(r'\s(?:width|height|x|y|viewBox|preserveAspectRatio)\s*=\s*("[^"]*"|\'[^\']*\')', "", attrs)
    nueva = (f'<svg{resto} x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" viewBox="{caja}" '
             f'preserveAspectRatio="xMidYMax meet">')
    return s[:m.start()] + nueva + s[m.end():]


def figuras_isometricas(mant=None) -> dict:
    """{código: svg} de las figuras isométricas guardadas en la tabla simbolos del mantenedor con norma «ISO-ISOMETRICO».
    mant: objeto con listar_simbolos(norma) (pat_sim.datos.mantenedor.Mantenedor). Vacío si no hay mantenedor o falla."""
    if mant is None:
        return {}
    try:
        return {str(f["codigo"]): f["svg"] for f in mant.listar_simbolos(NORMA_FIGURAS) if f.get("svg") and "<svg" in f["svg"].lower()}
    except Exception:
        return {}


# ------------------------------------------------------------------------------------------- escena
def _esc(s) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def escena(posiciones: dict, dims: dict, corrientes: list | None = None, red: dict | None = None, rot: int = 0,
           h_rack: float = LY.H_RACK_M, nombres: dict | None = None, codigos: dict | None = None, figuras: dict | None = None) -> dict:
    """Ítems 3D de la escena en coordenadas de cámara, ya ordenados por el pintor. Cada ítem: clase (eq, ccm, co, rack, ba, ca),
    id, caja, y lo necesario para dibujarlo. codigos: {id: [símbolo, tipo, familia]} para buscar la figura del mantenedor."""
    nombres = nombres or {}; codigos = codigos or {}; figuras = figuras or {}
    hs = {k: LY.huella(p, dims[k]) for k, p in posiciones.items() if k in dims}
    todos = list(hs.values()) + ([LY.huella(red["ccm"], red["ccm_dim"])] if red and red.get("ccm") else [])
    cx = (min((h[0] for h in todos), default=0) + max((h[2] for h in todos), default=0)) / 2
    cy = (min((h[1] for h in todos), default=0) + max((h[3] for h in todos), default=0)) / 2
    cam = lambda x, y: camara(x, y, rot, cx, cy)
    items = []
    for k, h in hs.items():
        fam = dims[k].get("familia") or "general"
        fig = next((figuras[c] for c in (codigos.get(k) or []) if c and c in figuras), None)
        items.append(dict(clase="eq", id=k, nombre=nombres.get(k, ""), forma=forma(fam), color=COLOR_FAMILIA.get(fam, COLOR_FAMILIA["general"]),
                          caja=caja_camara(h, 0.0, float(dims[k]["alto"]), rot, cx, cy), figura=fig))
    if red and red.get("ccm"):
        items.append(dict(clase="ccm", id=LY.ID_CCM, nombre="Sala eléctrica (CCM)", forma="prisma", color=COLOR_CCM, figura=None,
                          caja=caja_camara(LY.huella(red["ccm"], red["ccm_dim"]), 0.0, float(red["ccm_dim"]["alto"]), rot, cx, cy)))

    def seg_caja(p, q, ancho=0.0, z1=None, z2=None):
        a1, b1 = cam(p[0], p[1]); a2, b2 = cam(q[0], q[1])
        A1, A2, B1, B2 = min(a1, a2), max(a1, a2), min(b1, b2), max(b1, b2)
        if ancho:
            if A2 - A1 < 1e-9:
                A1, A2 = A1 - ancho / 2, A2 + ancho / 2
            if B2 - B1 < 1e-9:
                B1, B2 = B1 - ancho / 2, B2 + ancho / 2
        return (A1, A2, B1, B2, min(p[2], q[2]) if z1 is None else z1, max(p[2], q[2]) if z2 is None else z2)
    vigas, postes = {}, {}
    for i, f in enumerate(corrientes or []):
        o, d = f["origen"], f["destino"]
        if o not in posiciones or d not in posiciones or o not in dims or d not in dims:
            continue
        p1 = LY.puerto(posiciones[o], dims[o], "sale")
        p2 = LY.puerto(posiciones[d], dims[d], "servicio" if f.get("servicio") else "entra")
        por_rack = f.get("medio") != "transportador"
        ruta = ruta_tubo(p1, p2, h_rack + SEP_RACK_M * (i % 4), por_rack)
        color = TIPOS_CORRIENTE.get(f.get("tipo"), ("", "#555555"))[1]
        for p, q in zip(ruta, ruta[1:]):
            items.append(dict(clase="co", id=str(f["id"]), o=o, d=d, color=color, pts=[cam(p[0], p[1]) + (p[2],), cam(q[0], q[1]) + (q[2],)],
                              servicio=bool(f.get("servicio")),
                              caja=seg_caja(p, q)))
            if por_rack and abs(p[2] - q[2]) < 1e-9:
                kv = tuple(round(v, 1) for v in (p[0], p[1], q[0], q[1]))
                vigas.setdefault(kv, (p, q))
                for e in (p, q):
                    postes.setdefault((round(e[0], 1), round(e[1], 1)), e)
                L = abs(q[0] - p[0]) + abs(q[1] - p[1]); n = int(L // PASO_POSTE_M)
                for j in range(1, n + 1):
                    t = j * PASO_POSTE_M / L
                    e = (p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t, p[2])
                    postes.setdefault((round(e[0], 1), round(e[1], 1)), e)
    zv1, zv2 = h_rack - 0.3, h_rack - 0.12
    for p, q in vigas.values():
        items.append(dict(clase="rack", id="rack", color=COLOR_RACK, caja=seg_caja(p, q, ANCHO_RACK_M, zv1, zv2)))
    for e in postes.values():
        a, b = cam(e[0], e[1])
        items.append(dict(clase="rack", id="rack", color=COLOR_RACK, caja=(a - 0.12, a + 0.12, b - 0.12, b + 0.12, 0.0, zv1)))
    if red:
        hb = float(red.get("h_bandeja", LY.H_BANDEJA_M)); tramos = {}
        for c in red.get("cables", []):
            r_ = c["ruta"]
            for p, q in zip(r_, r_[1:]):
                if abs(p[2] - q[2]) < 1e-9 and max(abs(p[0] - q[0]), abs(p[1] - q[1])) > 1e-9:
                    tramos.setdefault(tuple(round(v, 1) for v in (p[0], p[1], q[0], q[1])), (p, q))
                if max(abs(p[0] - q[0]), abs(p[1] - q[1]), abs(p[2] - q[2])) > 1e-9:
                    items.append(dict(clase="ca", id=c["id"], o=LY.ID_CCM, d=c["equipo"], equipo=c["equipo"], color=COLOR_BANDEJA, pts=[cam(p[0], p[1]) + (p[2] + 0.03,), cam(q[0], q[1]) + (q[2] + 0.03,)],
                                      caja=seg_caja(p, q)))
        for p, q in tramos.values():
            items.append(dict(clase="ba", id="bandeja", color=COLOR_BANDEJA, caja=seg_caja(p, q, ANCHO_BANDEJA_M, hb - 0.1, hb)))
    return dict(items=orden_pintor(items), rot=rot, centro=(cx, cy), titulo=VISTAS.get(int(rot) % 360, ""))


def _norte(rot: int) -> tuple[float, float]:
    """Dirección en pantalla (unitaria) del norte para la orientación rot."""
    a0, b0 = camara(0, 0, rot); a1, b1 = camara(0, 1, rot)
    sx, sy = proyectar(a1 - a0, b1 - b0, 0)
    n = math.hypot(sx, sy) or 1.0
    return sx / n, sy / n


def isometrico_svg(posiciones: dict, dims: dict, corrientes: list | None = None, red: dict | None = None, rot: int = 0,
                   h_rack: float = LY.H_RACK_M, nombres: dict | None = None, codigos: dict | None = None, figuras: dict | None = None,
                   ancho_px: int = 1100, titulo: str = "Vista isométrica") -> str:
    """SVG autónomo de la vista isométrica en la orientación rot, con título, rótulos, norte y leyenda. Cada pieza lleva clase y
    data-id (equipos), data-c, data-o y data-d (cañerías y alimentadores) para la interacción en el navegador."""
    esc_ = escena(posiciones, dims, corrientes, red, rot, h_rack, nombres, codigos, figuras)
    items = esc_["items"]
    if not items:
        return '<svg xmlns="http://www.w3.org/2000/svg" width="400" height="60"><text x="10" y="30">Vista isométrica: sin equipos</text></svg>'
    pts = []
    for it in items:
        c = it["caja"]
        pts += [proyectar(a, b, z) for a in c[0:2] for b in c[2:4] for z in c[4:6]]
    x0, x1 = min(p[0] for p in pts), max(p[0] for p in pts); y0, y1 = min(p[1] for p in pts), max(p[1] for p in pts)
    S = max(3.0, min(40.0, (ancho_px - 80) / max(x1 - x0, 1.0)))
    top, mx = 64, 40
    W = ancho_px; Hs = top + 14 + (y1 - y0) * S + 56
    P = lambda a, b, z: (mx + (proyectar(a, b, z)[0] - x0) * S, top + 14 + (proyectar(a, b, z)[1] - y0) * S)
    ancho_tubo = max(2.5, min(9.0, 2 * R_TUBO_M * S))
    o = []
    tipos_usados = []
    for it in items:
        cl = it["clase"]
        if cl in ("eq", "ccm"):
            t = tonos(it["color"])
            if it.get("figura"):
                c = it["caja"]; ps = [P(a, b, z) for a in c[0:2] for b in c[2:4] for z in c[4:6]]
                xa, xb = min(p[0] for p in ps), max(p[0] for p in ps); ya, yb = min(p[1] for p in ps), max(p[1] for p in ps)
                cuerpo = figura_incrustada(it["figura"], xa, ya, xb - xa, yb - ya) or prisma(P, it["caja"], t)
            elif it["forma"] == "cilindro_v":
                cuerpo = cilindro_v(P, it["caja"], t)
            elif it["forma"] == "cilindro_h":
                cuerpo = cilindro_h(P, it["caja"], t)
            else:
                cuerpo = prisma(P, it["caja"], t)
            o.append(f'<g class="it {cl}" data-id="{_esc(it["id"])}">{cuerpo}</g>')
        elif cl == "co":
            raya = ' stroke-dasharray="6 4"' if it.get("servicio") else ""
            o.append(f'<g class="it co" data-c="{_esc(it["id"])}" data-o="{_esc(it["o"])}" data-d="{_esc(it["d"])}">'
                     f'{tubo(P, it["pts"], it["color"], ancho_tubo, raya)}</g>')
        elif cl == "ca":
            xy = " ".join(f"{x:.1f},{y:.1f}" for x, y in (P(*p) for p in it["pts"]))
            o.append(f'<g class="it ca" data-c="{_esc(it["id"])}" data-o="{_esc(it["o"])}" data-d="{_esc(it["equipo"])}">'
                     f'<polyline points="{xy}" fill="none" stroke="#7d6608" stroke-width="1.6" stroke-dasharray="3 3"/></g>')
        else:
            o.append(f'<g class="{cl}">{prisma(P, it["caja"], tonos(it["color"]))}</g>')
        if cl == "co":
            tp = next((k for k, v in TIPOS_CORRIENTE.items() if v[1] == it["color"]), None)
            if tp and tp not in tipos_usados:
                tipos_usados.append(tp)
    # rótulos encima de todo
    rot_ = []
    for it in items:
        if it["clase"] not in ("eq", "ccm"):
            continue
        a1, a2, b1, b2, z1, z2 = it["caja"]
        x, y = P((a1 + a2) / 2, (b1 + b2) / 2, z2)
        rot_.append(f'<g class="rot" data-id="{_esc(it["id"])}"><text x="{x:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-size="12" '
                    f'font-weight="bold" fill="#173243" stroke="#ffffff" stroke-width="3" paint-order="stroke">{_esc(it["id"])}</text>'
                    + (f'<text x="{x:.1f}" y="{y + 5:.1f}" text-anchor="middle" font-size="9.5" fill="#3b5562" stroke="#ffffff" '
                       f'stroke-width="2.5" paint-order="stroke">{_esc(str(it.get("nombre") or "")[:24])}</text>' if it.get("nombre") else "") + "</g>")
    # norte y leyenda
    nx, ny = _norte(rot)
    bx, by = W - 46, 40
    norte = (f'<g transform="translate({bx},{by})"><circle r="18" fill="#ffffff" stroke="#c7d6dc"/>'
             f'<line x1="{-nx * 12:.1f}" y1="{-ny * 12:.1f}" x2="{nx * 12:.1f}" y2="{ny * 12:.1f}" stroke="#173243" stroke-width="2" marker-end="url(#iso_fl)"/>'
             f'<text x="{nx * 25:.1f}" y="{ny * 25 + 4:.1f}" font-size="12" font-weight="bold" text-anchor="middle" fill="#173243">N</text></g>')
    ley = [(TIPOS_CORRIENTE[k][1], TIPOS_CORRIENTE[k][0], "tubo") for k in tipos_usados]
    ley.append((COLOR_RACK, "Rack de cañerías", "caja"))
    if red and red.get("ccm"):
        ley += [(COLOR_CCM, "Sala eléctrica (CCM)", "caja"), (COLOR_BANDEJA, "Bandeja eléctrica y alimentadores", "caja")]
    lx, lo = mx, []
    for col, txt, kind in ley:
        lo.append((f'<line x1="{lx}" y1="{Hs - 18}" x2="{lx + 18}" y2="{Hs - 18}" stroke="{col}" stroke-width="5" stroke-linecap="round"/>' if kind == "tubo"
                   else f'<rect x="{lx}" y="{Hs - 24}" width="18" height="11" fill="{col}" stroke="{mezcla(col, "#000000", 0.5)}"/>')
                  + f'<text x="{lx + 23}" y="{Hs - 14}" font-size="11" fill="#173243">{_esc(txt)}</text>')
        lx += 30 + 6.2 * len(txt)
    defs = ('<defs><marker id="iso_fl" markerWidth="8" markerHeight="8" refX="4" refY="4" orient="auto" markerUnits="userSpaceOnUse">'
            '<path d="M0 1 L8 4 L0 7 Z" fill="#173243"/></marker></defs>')
    cab = (f'<text x="{mx}" y="24" font-size="16" font-weight="bold" fill="#173243">{_esc(titulo)}: {_esc(esc_["titulo"].lower())}</text>'
           f'<text x="{mx}" y="42" font-size="11" fill="#5b7280">Proyección isométrica de 30°; sombreado de cuatro tonos; cañerías con el '
           f'color de su tipo de corriente; rack a +{LY._f(h_rack, 1)} m</text>')
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W:.0f}" height="{Hs:.0f}" viewBox="0 0 {W:.0f} {Hs:.0f}" font-family="Arial" '
            f'data-rot="{int(rot) % 360}">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>{defs}{cab}<g class="escena">{"".join(o)}</g><g class="rotulos">{"".join(rot_)}</g>'
            f'{norte}{"".join(lo)}</svg>')


def vistas_isometricas(posiciones: dict, dims: dict, corrientes: list | None = None, red: dict | None = None, **k) -> dict:
    """Las cuatro orientaciones de la cámara: {"0": svg, "90": svg, "180": svg, "270": svg}."""
    return {str(r): isometrico_svg(posiciones, dims, corrientes, red, r, **k) for r in (0, 90, 180, 270)}


def datos_interaccion(posiciones: dict, dims: dict, corrientes: list | None = None, red: dict | None = None,
                      nombres: dict | None = None) -> dict:
    """Datos que muestra el navegador al pasar el mouse: equipos (dimensiones, posición, potencia, conexiones), cañerías y
    alimentadores. Todo serializable a JSON."""
    nombres = nombres or {}
    cab = {c["equipo"]: c for c in (red or {}).get("cables", [])}
    eqs = {}
    for k, p in posiciones.items():
        if k not in dims:
            continue
        d = dims[k]; c = cab.get(k)
        eqs[k] = dict(nombre=nombres.get(k, ""), familia=d.get("familia", ""), largo=d["largo"], ancho=d["ancho"], alto=d["alto"],
                      x=float(p[0]), y=float(p[1]), rot=int(p[2] if len(p) > 2 else 0),
                      P_kW=c["P_kW"] if c else None, alimentador=c["id"] if c else None, conductor=c["conductor"] if c else None,
                      conexiones=[str(f["id"]) for f in (corrientes or []) if k in (f["origen"], f["destino"])])
    if red and red.get("ccm"):
        eqs[LY.ID_CCM] = dict(nombre="Sala eléctrica (CCM)", familia="electrica", largo=red["ccm_dim"]["largo"], ancho=red["ccm_dim"]["ancho"],
                              alto=red["ccm_dim"]["alto"], x=red["ccm"][0], y=red["ccm"][1], rot=int(red["ccm"][2]),
                              P_kW=red.get("P_total_kW"), alimentador=None, conductor=None,
                              conexiones=[c["id"] for c in red.get("cables", [])])
    cors = {str(f["id"]): dict(origen=f["origen"], destino=f["destino"], tipo=f.get("tipo", ""),
                               tipo_txt=TIPOS_CORRIENTE.get(f.get("tipo"), (f.get("tipo", ""),))[0], medio=f.get("medio", ""),
                               largo_m=f.get("total"), D_mm=f.get("D_mm")) for f in (corrientes or [])}
    cabs = {c["id"]: dict(origen=LY.ID_CCM, destino=c["equipo"], nombre=c["nombre"], P_kW=c["P_kW"], I_A=c["I_A"], conductor=c["conductor"],
                          largo_m=c["total"], dU_pct=c["dU_pct"]) for c in (red or {}).get("cables", [])}
    return json.loads(json.dumps(dict(equipos=eqs, corrientes=cors, cables=cabs), default=float))
