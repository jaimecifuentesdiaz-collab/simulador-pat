"""Diagrama de flujo de proceso de la planta con símbolos ISO 10628 e instrumentos ISA-5.1 (SVG).

PAT 134: los instrumentos van en la posición que tienen en el lienzo de Diseño (o junto a su equipo, como antes), con su
símbolo (burbuja, elemento primario, válvula o elemento de lazo ISA-5.4) y con las líneas de señal dibujadas en el lienzo, cada
una con el trazo de su tipo (isa51.linea). Un instrumento sin líneas propias mantiene la línea eléctrica a su equipo."""
from __future__ import annotations
from ..simbolos import iso10628, isa51
from .corrientes import TIPOS

TAM = 64


def _fmt(v, d=1):
    return f"{v:,.{d}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def planta_svg(pl, instrumentos=True, numeros=True, tabla=True) -> str:
    from .instrumentacion import posiciones, ident, clave_corriente
    eqs = pl.equipos
    pos_ins = posiciones(pl, TAM) if instrumentos else {}
    W = max([e.x for e in eqs.values()] + [x - 100 for x, _, _ in pos_ins.values()]) + 220
    Hd = max([e.y for e in eqs.values()] + [y - 80 for _, y, _ in pos_ins.values()]) + 170
    medios = {}
    filas = [c for c in pl.conexiones if c.nombre] if tabla else []
    Ht = Hd + (40 + 16 * (len(filas) + 1) if filas else 0)
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{Ht}" viewBox="0 0 {W} {Ht}" font-family="Arial">',
         '<rect width="100%" height="100%" fill="#fff"/>']
    o.append('<defs>' + ''.join(f'<marker id="fl_{k}" markerUnits="userSpaceOnUse" markerWidth="11" markerHeight="10" refX="10" refY="5" orient="auto"><path d="M0 0 L11 5 L0 10 Z" fill="{v[1]}"/></marker>' for k, v in TIPOS.items()) + '</defs>')
    cen = lambda e: (e.x + TAM / 2, e.y + TAM / 2)
    for c in pl.conexiones:
        a, b = eqs[c.origen], eqs[c.destino]; tipo = pl.tipo_conexion(c); col, grosor = TIPOS[tipo][1], TIPOS[tipo][2]
        serv = pl.es_servicio(c)
        if serv:
            x1 = a.x + TAM / 2; x2 = b.x + TAM / 2; yr = b.y + TAM + 40
            y1 = a.y + TAM if yr > a.y + TAM else a.y; y2 = b.y + TAM
            path = f"M{x1} {y1} V{yr} H{x2} V{y2 + 2}"; mx, my = (x1 + x2) / 2, yr
        else:
            ya, yb = a.y + TAM / 2, b.y + TAM / 2
            if b.x > a.x + 10:
                x1, x2 = a.x + TAM, b.x
                path = f"M{x1} {ya} H{x2 - 2}" if abs(ya - yb) < 1 else f"M{x1} {ya} H{x1 + 20} V{yb} H{x2 - 2}"
                mx, my = (x1 + x2) / 2 if abs(ya - yb) < 1 else x1 + 20, ya - 14
            elif b.x < a.x - 10:
                x1, x2 = a.x, b.x + TAM
                path = f"M{x1} {ya} H{x2 + 2}" if abs(ya - yb) < 1 else f"M{x1} {ya} H{x1 - 20} V{yb} H{x2 + 2}"
                mx, my = (x1 + x2) / 2 if abs(ya - yb) < 1 else x1 - 20, ya - 14
            else:
                x1 = a.x + TAM; xr = x1 + 26; x2 = b.x + TAM
                path = f"M{x1} {ya} H{xr} V{yb} H{x2 + 2}"; mx, my = xr + 12, (ya + yb) / 2
        medios[clave_corriente(c)] = (mx, my)
        dash = ' stroke-dasharray="8 4"' if tipo == "vapor" else ""
        o.append(f'<path d="{path}" fill="none" stroke="{col}" stroke-width="{grosor}"{dash} marker-end="url(#fl_{tipo})"/>')
        if numeros and c.nombre:
            o.append(f'<path d="M{mx} {my - 8} L{mx + 9} {my} L{mx} {my + 8} L{mx - 9} {my} Z" fill="#fff" stroke="{col}"/><text x="{mx}" y="{my + 3.5}" font-size="9" text-anchor="middle">{c.nombre}</text>')
    for e in eqs.values():
        o.append(iso10628.svg(e.simbolo, e.x, e.y, TAM))
        o.append(f'<text x="{e.x + TAM / 2}" y="{e.y + TAM + 14}" font-size="11" font-weight="bold" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="4">{e.id}</text>')
        o.append(f'<text x="{e.x + TAM / 2}" y="{e.y + TAM + 27}" font-size="10" text-anchor="middle" paint-order="stroke" stroke="#fff" stroke-width="4">{e.nombre}</text>')
    if instrumentos:
        import math
        R = 15

        def borde_eq(e, x, y):          # punto del borde del símbolo del equipo en dirección al instrumento
            cx, cy = e.x + TAM / 2, e.y + TAM / 2; dx, dy = x - cx, y - cy
            if abs(dx) < 1e-9 and abs(dy) < 1e-9: return cx, cy - TAM / 2
            f = (TAM / 2) / max(abs(dx), abs(dy)); return cx + dx * f, cy + dy * f

        def recorte(x1, y1, x2, y2, r):  # acorta el tramo r unidades desde (x1, y1)
            L = math.hypot(x2 - x1, y2 - y1) or 1; return x1 + (x2 - x1) * r / L, y1 + (y2 - y1) * r / L
        lineas, simbolos = [], []
        for ins in pl.instrumentos:
            k = ident(ins); x, y, _ = pos_ins[k]
            propias = [s for s in ins.conexiones if isinstance(s, dict)]
            if not propias and ins.equipo in eqs:            # como antes: línea eléctrica al equipo
                e = eqs[ins.equipo]; bx, by = borde_eq(e, x, y); ax, ay = recorte(x, y, bx, by, R)
                lineas.append(isa51.linea(round(ax, 1), round(ay, 1), round(bx, 1), round(by, 1), "electrica"))
            for s in propias:
                t, de = s.get("tipo"), s.get("destino")
                if t == "equipo" and de in eqs:
                    bx, by = borde_eq(eqs[de], x, y)
                elif t == "corriente" and de in medios:
                    bx, by = medios[de]
                elif t == "instrumento" and de in pos_ins:
                    bx, by = recorte(pos_ins[de][0], pos_ins[de][1], x, y, R)
                else:
                    continue
                ax, ay = recorte(x, y, bx, by, R)
                lineas.append(isa51.linea(round(ax, 1), round(ay, 1), round(bx, 1), round(by, 1), s.get("senal") or "electrica"))
            simbolos.append(isa51.simbolo_svg(ins.simbolo, ins.letras, ins.numero, x, y, ins.ubicacion, r=R))
        o += lineas + simbolos
    if filas and pl.resuelta:
        y0 = Hd + 20
        cols = [("Corriente", 20), ("De", 90), ("A", 150), ("Tipo", 210), ("kg/h", 330), ("°C", 420), ("°Brix", 480)]
        o.append(f'<text x="20" y="{y0}" font-size="12" font-weight="bold">Tabla de corrientes</text>')
        for nm, x in cols: o.append(f'<text x="{x}" y="{y0 + 16}" font-size="10" font-weight="bold">{nm}</text>')
        for i, c in enumerate(filas):
            yy = y0 + 32 + 16 * i
            s = pl.salidas.get((c.origen, c.puerto_origen))
            if s is None and pl.es_servicio(c):
                vals = [c.nombre, c.origen, c.destino, pl.tipo_conexion(c), _fmt(eqs[c.destino].resultado.servicios.get("vapor_kW", 0)) + " kW", "", ""]
            else:
                s = s.fraccion(c.reparto / 100)
                vals = [c.nombre, c.origen, c.destino, pl.tipo_conexion(c), _fmt(s.m), _fmt(s.T, 2), _fmt(s.brix, 2) if s.s else "—"]
            for (nm, x), v in zip(cols, vals): o.append(f'<text x="{x}" y="{yy}" font-size="10">{v}</text>')
    o.append('</svg>')
    return "".join(o)
