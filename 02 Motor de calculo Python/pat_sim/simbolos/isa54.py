"""Diagrama de lazo de un instrumento con la estructura de ISA-5.4 (Instrument Loop Diagrams).

ISA-5.4 es una norma pagada que no está en la carpeta del proyecto; este diagrama sigue la estructura que
describe públicamente ISA (https://isa.org/standards-and-publications/isa-standards/isa-5-standard): el lazo se
dibuja en columnas por ubicación (campo, caja de conexiones, sala de control), con la etiqueta de cada
instrumento según ISA-5.1, los bornes de conexión y el tipo de señal. Es un diagrama de lazo simplificado.
PAT 142: rotula la información mínima de ISA-5.4 de las diapositivas del curso (p. 32): la descripción del lazo en el título
(requisito 2), las relaciones con otros lazos (requisito 3), las fuentes de alimentación (requisito 6, p. 26), la acción en falla
del elemento final (requisito 7, p. 23), la acción del controlador (p. 28) y su consigna (p. 27). Sin esos datos, el diagrama
queda como antes.
"""
from __future__ import annotations
from . import isa51


def _e(t) -> str:
    """PAT 142: texto escapado para el SVG."""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def lazo_svg(letras: str, numero: str, descripcion: str = "", equipo: str = "", ubicacion: str = "dcs",
             caja: str = "JB-1", senal: str = "4-20 mA", accion_falla: str = "", alimentacion: dict | None = None, accion: str = "",
             consigna: str = "", relaciones: list | None = None, final: str = "") -> str:
    """PAT 142: alimentacion {"transmisor", "controlador", "convertidor"}: fuente de cada uno; relaciones: textos «cascada con el
    lazo 102 (TIC-101 → TIC-102)»; final: etiqueta del elemento final si no es la V del lazo."""
    v = letras[0].upper(); info = isa51.interpretar(letras)
    alimentacion = {k: x for k, x in (alimentacion or {}).items() if x}; relaciones = [r for r in (relaciones or []) if r]
    W, H = 900, 380 + (18 * (len(relaciones) + 1) if relaciones else 0); col = [(20, "Campo"), (330, "Caja de conexiones"), (560, "Sala de control")]
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
    o.append(f'<text x="80" y="290" font-size="10" text-anchor="middle">{_e(final) if final else f"{v}V-{numero}"}</text>')
    if accion_falla:                           # PAT 142: acción en falla junto al actuador (ISA p. 23)
        o.append(f'<text x="104" y="232" font-size="10" font-weight="bold">{_e(accion_falla)}</text>')
    if alimentacion.get("transmisor"):         # PAT 142: fuentes de alimentación (ISA p. 26)
        o.append(f'<text x="170" y="96" font-size="9" text-anchor="middle" fill="#7a3d00">{_e(alimentacion["transmisor"])}</text>')
    if alimentacion.get("convertidor"):
        o.append(f'<text x="170" y="272" font-size="9" text-anchor="middle" fill="#7a3d00">{_e(alimentacion["convertidor"])}</text>')
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
    if accion:                                 # PAT 142: sentido de acción (ISA p. 28) y consigna (p. 27) del controlador
        o.append(f'<text x="752" y="176" font-size="10">Acción {_e(accion)}</text>')
    if consigna:
        o.append(f'<text x="752" y="190" font-size="10">Consigna {_e(consigna)}</text>')
    if alimentacion.get("controlador"):
        o.append(f'<text x="720" y="222" font-size="9" text-anchor="middle" fill="#7a3d00">{_e(alimentacion["controlador"])}</text>')
    o.append(isa51.linea(473, 115, 690, 170, "electrica")); o.append(isa51.linea(473, 250, 690, 192, "electrica"))
    o.append(f'<text x="560" y="140" font-size="10">Entrada {senal}</text><text x="560" y="232" font-size="10">Salida {senal}</text>')
    o.append(f'<text x="20" y="335" font-size="10" fill="#444">Señales según ISA-5.1, Tabla 15: eléctrica en trazo discontinuo, neumática con doble barra. '
             f'Etiquetas: {v}E elemento primario, {v}T transmisor, {letras} controlador, {v}Y convertidor I/P, {v}V válvula de control.</text>')
    o.append('<text x="20" y="352" font-size="10" fill="#444">Estructura de diagrama de lazo según ISA-5.4 (norma no disponible en la carpeta del proyecto; diagrama simplificado).</text>')
    if relaciones:                             # PAT 142: interrelación con otros lazos (ISA p. 32, requisito 3)
        o.append('<text x="20" y="374" font-size="11" font-weight="bold">Relación con otros lazos</text>')
        for j, r in enumerate(relaciones):
            o.append(f'<text x="30" y="{392 + 18 * j}" font-size="10">{_e(r)}</text>')
    o.append('</svg>')
    return "".join(o)
