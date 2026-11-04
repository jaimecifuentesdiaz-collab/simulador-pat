"""Diagrama de lazo de un instrumento con la estructura de ISA-5.4 (Instrument Loop Diagrams).

ISA-5.4 es una norma pagada que no está en la carpeta del proyecto; este diagrama sigue la estructura que
describe públicamente ISA (https://isa.org/standards-and-publications/isa-standards/isa-5-standard): el lazo se
dibuja en columnas por ubicación (campo, caja de conexiones, sala de control), con la etiqueta de cada
instrumento según ISA-5.1, los bornes de conexión y el tipo de señal. Es un diagrama de lazo simplificado.
"""
from __future__ import annotations
from . import isa51


def lazo_svg(letras: str, numero: str, descripcion: str = "", equipo: str = "", ubicacion: str = "dcs",
             caja: str = "JB-1", senal: str = "4-20 mA") -> str:
    v = letras[0].upper(); info = isa51.interpretar(letras)
    W, H = 900, 380; col = [(20, "Campo"), (330, "Caja de conexiones"), (560, "Sala de control")]
    o = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" font-family="Arial">',
         '<rect width="100%" height="100%" fill="#fff"/>']
    for i, (x, nm) in enumerate(col):
        w = (col[i + 1][0] if i + 1 < len(col) else W - 20) - x - 10
        o.append(f'<rect x="{x}" y="40" width="{w}" height="270" fill="none" stroke="#999"/><text x="{x + w / 2}" y="58" font-size="13" text-anchor="middle" font-weight="bold">{nm}</text>')
    o.append(f'<text x="20" y="26" font-size="15" font-weight="bold">Diagrama de lazo {isa51.tag(letras, numero)}: {descripcion or info["descripcion"]}</text>')
    # campo: elemento primario, transmisor, convertidor y elemento final
    o.append(isa51.burbuja(v + "E", numero, 70, 120, "campo")); o.append(isa51.burbuja(v + "T", numero, 170, 120, "campo"))
    o.append(isa51.linea(86, 120, 154, 120, "capilar" if v == "T" else "proceso"))
    o.append(isa51.burbuja(v + "Y", numero, 170, 240, "campo"))
    o.append(f'<path d="M60 250 L80 260 L60 270 Z M100 250 L80 260 L100 270 Z" fill="#fff" stroke="#111"/><path d="M80 260 V235" stroke="#111"/><path d="M68 235 A12 10 0 0 1 92 235 Z" fill="#fff" stroke="#111"/>')
    o.append(f'<text x="80" y="290" font-size="10" text-anchor="middle">{v}V-{numero}</text>')
    o.append(isa51.linea(154, 240, 92, 240, "neumatica"))
    if equipo: o.append(f'<text x="40" y="160" font-size="10">Equipo {equipo}</text>')
    # caja de conexiones con bornes
    o.append(f'<rect x="400" y="95" width="90" height="170" fill="#fafafa" stroke="#111"/><text x="445" y="88" font-size="11" text-anchor="middle">{caja}</text>')
    for j, (yy, b) in enumerate([(115, "1 +"), (130, "2 −"), (235, "3 +"), (250, "4 −")]):
        o.append(f'<circle cx="420" cy="{yy}" r="3" fill="#fff" stroke="#111"/><circle cx="470" cy="{yy}" r="3" fill="#fff" stroke="#111"/><text x="445" y="{yy + 4}" font-size="9" text-anchor="middle">{b}</text>')
    o.append(isa51.linea(186, 115, 417, 115, "electrica")); o.append(isa51.linea(186, 128, 417, 130, "electrica"))
    o.append(isa51.linea(186, 240, 417, 235, "electrica")); o.append(isa51.linea(186, 246, 417, 250, "electrica"))
    # sala de control: controlador
    o.append(isa51.burbuja(letras, numero, 720, 180, ubicacion, r=22))
    o.append(isa51.linea(473, 115, 690, 170, "electrica")); o.append(isa51.linea(473, 250, 690, 192, "electrica"))
    o.append(f'<text x="560" y="140" font-size="10">Entrada {senal}</text><text x="560" y="232" font-size="10">Salida {senal}</text>')
    o.append(f'<text x="20" y="335" font-size="10" fill="#444">Señales según ISA-5.1, Tabla 15: eléctrica en trazo discontinuo, neumática con doble barra. '
             f'Etiquetas: {v}E elemento primario, {v}T transmisor, {letras} controlador, {v}Y convertidor I/P, {v}V válvula de control.</text>')
    o.append('<text x="20" y="352" font-size="10" fill="#444">Estructura de diagrama de lazo según ISA-5.4 (norma no disponible en la carpeta del proyecto; diagrama simplificado).</text>')
    o.append('</svg>')
    return "".join(o)
