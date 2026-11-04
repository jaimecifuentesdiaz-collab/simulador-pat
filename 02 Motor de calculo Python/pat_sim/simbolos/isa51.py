"""Identificación y símbolos de instrumentos según ISA-5.1.

Fuente: Carballo, J. y Romero, D. (2011). Tutorial norma ISA S5.1 y diagramas P&ID. Universidad Tecnológica de Bolívar
(PROCESOS 2 DESCARGA\\0062398 (1).pdf): Tabla 3 (letras de identificación, p. 18), Tabla 4 (símbolos de dispositivos, p. 20),
Tabla 15 (líneas de conexión, p. 34) y Tabla 17 (elementos finales de control, p. 37). La norma ISA-5.1-2024 es pagada.
"""
from __future__ import annotations
import re

PRIMERA_LETRA = {  # variable medida o de inicio
    "A": "Análisis", "B": "Llama, combustión", "C": "Conductividad (a elección del usuario)", "D": "Densidad",
    "E": "Tensión eléctrica", "F": "Caudal", "G": "Calibre, dimensión", "H": "Manual", "I": "Corriente eléctrica",
    "J": "Potencia", "K": "Tiempo", "L": "Nivel", "M": "Humedad", "N": "A elección del usuario", "O": "A elección del usuario",
    "P": "Presión, vacío", "Q": "Cantidad", "R": "Radiación", "S": "Velocidad, frecuencia", "T": "Temperatura",
    "U": "Multivariable", "V": "Vibración", "W": "Peso, fuerza", "X": "Sin clasificar", "Y": "Evento, estado", "Z": "Posición",
}
MODIFICADORES = {"D": "Diferencial", "F": "Relación (fracción)", "Q": "Totalizador", "J": "Exploración"}
LETRAS_SUCESIVAS = {  # lectura pasiva o función de salida
    "A": "Alarma", "B": "A elección del usuario", "C": "Controlador", "E": "Elemento primario (sensor)", "G": "Visor, indicador local",
    "H": "Alto", "I": "Indicador", "K": "Estación de control", "L": "Bajo, luz piloto", "M": "Medio", "N": "A elección del usuario",
    "O": "Orificio, restricción", "P": "Punto de prueba", "R": "Registrador", "S": "Interruptor", "T": "Transmisor",
    "V": "Válvula, compuerta, actuador", "W": "Pozo, vaina", "X": "Sin clasificar", "Y": "Relé, convertidor, cálculo", "Z": "Elemento final no clasificado",
}
UBICACIONES = {  # Tabla 4
    "campo": "Montado en campo", "panel": "Panel principal (sala de control), accesible al operador",
    "panel_auxiliar": "Panel auxiliar, accesible al operador", "detras_panel": "Detrás del panel, no accesible al operador",
    "dcs": "Sistema de control distribuido (función compartida en pantalla)", "plc": "Controlador lógico programable", "computador": "Función de computador",
}
SENALES = {  # Tabla 15: patrón de trazo SVG
    "proceso": ("Conexión a proceso o suministro", "", ""), "electrica": ("Señal eléctrica", "6 3", ""),
    "neumatica": ("Señal neumática", "", "neumatica"), "datos": ("Enlace de datos o software", "", "datos"),
    "capilar": ("Tubo capilar", "", "capilar"), "hidraulica": ("Señal hidráulica", "", "hidraulica"),
    # PAT 134: señal electromagnética o sónica guiada, trazo sinusoidal (ISA-5.1, líneas de instrumento; sin número de tabla)
    "electromagnetica": ("Señal electromagnética o sónica (guiada)", "", "electromagnetica"),
}


def _x(t) -> str:
    """Escapa el texto para el SVG (las letras y la descripción las escribe el usuario en el lienzo)."""
    return str(t).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def interpretar(letras: str) -> dict:
    """Interpreta un código de identificación funcional, por ejemplo 'TIC' → temperatura, indicador, controlador."""
    t = letras.strip().upper()
    if not re.fullmatch(r"[A-Z]{1,5}", t):
        raise ValueError("La identificación debe tener de 1 a 5 letras")
    var = PRIMERA_LETRA.get(t[0]); resto = t[1:]; mod = None
    if len(resto) > 1 and resto[0] in MODIFICADORES:   # modificador de la primera letra (PDIC, FQI)
        mod, resto = MODIFICADORES[resto[0]], resto[1:]
    funciones = [LETRAS_SUCESIVAS.get(c, "?") for c in resto]
    if "?" in funciones:
        raise ValueError(f"Letra sucesiva no válida en {t}")
    return dict(letras=t, variable=var, modificador=mod, funciones=funciones,
                descripcion=" ".join([var or ""] + ([mod.lower()] if mod else []) + [f.lower() for f in funciones]).strip())


def tag(letras: str, numero: str, sufijo: str = "") -> str:
    return f"{letras.upper()}-{numero}{sufijo}"


def burbuja(letras: str, numero: str, x: float, y: float, ubicacion: str = "campo", r: float = 16, funcion: str | None = None) -> str:
    """Burbuja del instrumento centrada en (x, y), según su ubicación (Tabla 4).

    PAT 134: con «funcion» (discreto, compartido, computador o plc) la forma sale del tipo de instrumento y la raya
    horizontal de la ubicación (campo, panel, panel_auxiliar o detras_panel), para las 16 combinaciones de la Tabla 4.
    Sin «funcion» se mantiene la lectura anterior, en que dcs, plc y computador van en el panel principal."""
    if funcion in FUNCIONES:
        forma = {"discreto": "campo", "compartido": "dcs", "computador": "computador", "plc": "plc"}[funcion]
        lugar = ubicacion if ubicacion in LUGARES else "campo"
    else:
        forma, lugar = ubicacion, ubicacion
    S = 'fill="#fff" stroke="#111" stroke-width="1.3"'
    try:
        lectura = interpretar(letras)["descripcion"]
    except ValueError:
        lectura = "letras no válidas"
    g = [f'<g><title>{_x(tag(letras, numero))}: {_x(lectura)} · {_x(UBICACIONES.get(lugar, ""))}</title>']
    ubicacion = forma
    if ubicacion == "dcs":
        g.append(f'<rect x="{x - r}" y="{y - r}" width="{2 * r}" height="{2 * r}" {S}/><circle cx="{x}" cy="{y}" r="{r}" {S}/>')
    elif ubicacion == "plc":
        g.append(f'<rect x="{x - r}" y="{y - r}" width="{2 * r}" height="{2 * r}" {S}/><path d="M{x} {y - r} L{x + r} {y} L{x} {y + r} L{x - r} {y} Z" {S}/>')
    elif ubicacion == "computador":
        h = r * 0.87
        g.append(f'<path d="M{x - r} {y} L{x - r / 2} {y - h} H{x + r / 2} L{x + r} {y} L{x + r / 2} {y + h} H{x - r / 2} Z" {S}/>')
    else:
        g.append(f'<circle cx="{x}" cy="{y}" r="{r}" {S}/>')
    if funcion in FUNCIONES:
        ubicacion = lugar
    if ubicacion in ("panel", "dcs", "plc", "computador"):
        g.append(f'<path d="M{x - r} {y} H{x + r}" stroke="#111" stroke-width="1.1"/>')
    elif ubicacion == "panel_auxiliar":
        g.append(f'<path d="M{x - r} {y - 1.5} H{x + r} M{x - r} {y + 1.5} H{x + r}" stroke="#111" stroke-width="1"/>')
    elif ubicacion == "detras_panel":
        g.append(f'<path d="M{x - r} {y} H{x + r}" stroke="#111" stroke-width="1" stroke-dasharray="3 2"/>')
    fs = 9 if len(letras) > 3 else 10
    g.append(f'<text x="{x}" y="{y - 3}" font-size="{fs}" text-anchor="middle" font-family="Arial">{_x(letras.upper())}</text>')
    g.append(f'<text x="{x}" y="{y + 10}" font-size="9" text-anchor="middle" font-family="Arial">{_x(numero)}</text></g>')
    return "".join(g)


def linea(x1, y1, x2, y2, tipo: str = "electrica") -> str:
    """Línea de señal según la Tabla 15."""
    nm, dash, deco = SENALES.get(tipo, SENALES["electrica"])
    s = f'<path d="M{x1} {y1} L{x2} {y2}" stroke="#111" stroke-width="1" fill="none"' + (f' stroke-dasharray="{dash}"' if dash else "") + "/>"
    if deco:
        import math
        L = math.hypot(x2 - x1, y2 - y1) or 1; ux, uy = (x2 - x1) / L, (y2 - y1) / L; nx, ny = -uy, ux
        for t in (0.3, 0.7):
            cx, cy = x1 + (x2 - x1) * t, y1 + (y2 - y1) * t
            if deco == "neumatica":
                for o in (-2.5, 2.5):
                    px, py = cx + ux * o, cy + uy * o
                    s += f'<path d="M{px - nx * 4 + ux * 2} {py - ny * 4 + uy * 2} L{px + nx * 4 - ux * 2} {py + ny * 4 - uy * 2}" stroke="#111" stroke-width="1"/>'
            elif deco == "datos":
                s += f'<circle cx="{cx}" cy="{cy}" r="2.5" fill="#fff" stroke="#111"/>'
            elif deco == "capilar":
                s += f'<path d="M{cx - 3} {cy - 3} L{cx + 3} {cy + 3} M{cx + 3} {cy - 3} L{cx - 3} {cy + 3}" stroke="#111"/>'
            elif deco == "hidraulica":       # PAT 134: marca en L (raya perpendicular con un pie a lo largo de la línea)
                s += f'<path d="M{cx - nx * 4} {cy - ny * 4} L{cx + nx * 4} {cy + ny * 4} L{cx + nx * 4 + ux * 4} {cy + ny * 4 + uy * 4}" stroke="#111" fill="none"/>'
    if deco == "electromagnetica":            # PAT 134: la línea entera es una onda sinusoidal
        s = f'<path d="{_onda(x1, y1, x2, y2)}" stroke="#111" stroke-width="1" fill="none"/>'
    return s


def _onda(x1, y1, x2, y2, paso: float = 10.0, amp: float = 3.5) -> str:
    """Trazo sinusoidal entre dos puntos (medias ondas de largo «paso»), para la señal electromagnética o sónica."""
    import math
    L = math.hypot(x2 - x1, y2 - y1)
    if L < 1e-9:
        return f"M{x1} {y1}"
    ux, uy = (x2 - x1) / L, (y2 - y1) / L; nx, ny = -uy, ux
    n = max(1, int(round(L / paso))); h = L / n; d = [f"M{x1:.1f} {y1:.1f}"]
    for i in range(n):
        a = h * (i + 0.5); b = h * (i + 1); sg = 1 if i % 2 == 0 else -1
        cx, cy = x1 + ux * a + nx * amp * 2 * sg, y1 + uy * a + ny * amp * 2 * sg
        d.append(f"Q{cx:.1f} {cy:.1f} {x1 + ux * b:.1f} {y1 + uy * b:.1f}")
    return " ".join(d)


# ---------------------------------------------------------------- PAT 134: catálogo de símbolos para el lienzo de Diseño
# Tipo de instrumento (forma de la burbuja) y ubicación (raya horizontal) de la Tabla 4: 4 × 4 combinaciones.
FUNCIONES = {"discreto": "Instrumento discreto", "compartido": "Pantalla compartida o control compartido (DCS)",
             "computador": "Función de computador", "plc": "Controlador lógico programable (PLC)"}
LUGARES = {"campo": "Montado en campo", "panel": "Panel principal, accesible al operador",
           "panel_auxiliar": "Panel auxiliar, accesible al operador", "detras_panel": "Detrás del panel, no accesible al operador"}

_F4 = "ISA-5.1 (Carballo y Romero, 2011, Tabla 4)"
_F17 = "ISA-5.1, elementos finales de control (Carballo y Romero, 2011, Tabla 17)"
_FG = "ISA-5.1, símbolos generales de instrumentos (sin número de tabla)"
_F54 = "Estructura de ISA-5.4, diagrama de lazo (norma pagada; símbolo simplificado)"


def _elementos() -> dict:
    """Catálogo: clave → nombre, grupo, símbolo, ubicación, letras o código por defecto, si se valida con la tabla de
    letras de ISA-5.1 y fuente. Los elementos de ISA-5.4 (caja, regleta, fuente, tarjetas) llevan un código, no letras ISA-5.1."""
    E = {}
    g1 = "Burbujas ISA-5.1: tipo de instrumento y ubicación"
    letras_def = {"discreto": "TI", "compartido": "TIC", "computador": "TY", "plc": "TIC"}
    for f, nf in FUNCIONES.items():
        for u, nu in LUGARES.items():
            E[f"{f}_{u}"] = dict(nombre=f"{nf} · {nu.lower()}", grupo=g1, simbolo=f, ubicacion=u, letras=letras_def[f], isa51=True, fuente=_F4)
    g2 = "Elementos primarios ISA-5.1"
    for k, nm, l in [("placa_orificio", "Placa orificio (caudal)", "FE"), ("venturi", "Tubo venturi (caudal)", "FE"),
                     ("rotametro", "Rotámetro, medidor de área variable", "FI"), ("termopozo", "Termopozo o vaina", "TW"),
                     ("visor_nivel", "Visor de nivel", "LG")]:
        E[k] = dict(nombre=nm, grupo=g2, simbolo=k, ubicacion="campo", letras=l, isa51=True, fuente=_FG)
    g3 = "Elementos finales de control ISA-5.1"
    for k, nm, l, fu in [("valvula_diafragma", "Válvula de control, actuador neumático de diafragma", "TV", _F17),
                         ("valvula_piston", "Válvula de control, actuador neumático de pistón", "PV", _F17),
                         ("valvula_motor", "Válvula de control, actuador eléctrico (motor)", "FV", _F17),
                         ("valvula_solenoide", "Válvula de solenoide (todo o nada)", "XV", _F17),
                         ("valvula_manual", "Válvula manual", "HV", _FG),
                         ("valvula_alivio", "Válvula de alivio o seguridad de presión", "PSV", _FG)]:
        E[k] = dict(nombre=nm, grupo=g3, simbolo=k, ubicacion="campo", letras=l, isa51=True, fuente=fu)
    g4 = "Elementos del diagrama de lazo ISA-5.4"
    E["transmisor"] = dict(nombre="Transmisor (en campo)", grupo=g4, simbolo="discreto", ubicacion="campo", letras="TT", isa51=True, fuente=_F4)
    E["controlador"] = dict(nombre="Controlador (DCS, panel principal)", grupo=g4, simbolo="compartido", ubicacion="panel", letras="TIC", isa51=True, fuente=_F4)
    E["convertidor_ip"] = dict(nombre="Convertidor de corriente a presión (I/P)", grupo=g4, simbolo="convertidor", ubicacion="campo", letras="TY", isa51=True, fuente=_F4)
    for k, nm, c in [("caja_conexiones", "Caja de conexiones", "JB"), ("regleta_bornes", "Regleta de bornes", "TB"),
                     ("fuente_alimentacion", "Fuente de alimentación de 24 V c.c.", "PS"), ("tarjeta_ai", "Tarjeta de entrada analógica", "AI"),
                     ("tarjeta_ao", "Tarjeta de salida analógica", "AO"), ("tarjeta_di", "Tarjeta de entrada digital", "DI"),
                     ("tarjeta_do", "Tarjeta de salida digital", "DO")]:
        E[k] = dict(nombre=nm, grupo=g4, simbolo=k, ubicacion="detras_panel", letras=c, isa51=False, fuente=_F54)
    return E


ELEMENTOS = _elementos()
# símbolo → si sus letras se validan con la tabla de ISA-5.1 (los de ISA-5.4 llevan un código libre)
SIMBOLOS_ISA51 = {e["simbolo"] for e in ELEMENTOS.values() if e["isa51"]} | {""}
SIMBOLOS_ISA54 = {e["simbolo"] for e in ELEMENTOS.values() if not e["isa51"]}
NOMBRE_SIMBOLO = {"": "Burbuja de instrumento", "discreto": "Instrumento discreto", "compartido": "Pantalla compartida o control (DCS)",
                  "computador": "Función de computador", "plc": "Controlador lógico programable (PLC)",
                  **{e["simbolo"]: e["nombre"] for e in ELEMENTOS.values() if e["simbolo"] not in FUNCIONES}}


def valida_isa51(simbolo: str) -> bool:
    return (simbolo or "") in SIMBOLOS_ISA51


def validar_codigo(simbolo: str, letras: str) -> str:
    """Letras ISA-5.1 (validadas con la tabla de letras) o código de un elemento de ISA-5.4 (1 a 6 letras o cifras)."""
    t = str(letras or "").strip().upper()
    if valida_isa51(simbolo):
        interpretar(t)
        return t
    if not re.fullmatch(r"[A-Z0-9]{1,6}", t):
        raise ValueError("El código del elemento debe tener de 1 a 6 letras o cifras")
    return t


def simbolo_svg(simbolo: str, letras: str, numero: str, x: float = 0, y: float = 0, ubicacion: str = "campo", r: float = 16) -> str:
    """Símbolo de un instrumento o elemento centrado en (x, y): burbuja según tipo y ubicación (Tabla 4), elemento primario,
    válvula con su actuador (Tabla 17) o elemento del diagrama de lazo de ISA-5.4. Para el lienzo y el diagrama de flujo."""
    simbolo = simbolo or ""
    if simbolo in ("", "discreto", "compartido", "computador", "plc"):
        return burbuja(letras, numero, x, y, ubicacion, r, simbolo or None)
    if simbolo == "convertidor":
        return burbuja(letras, numero, x, y, ubicacion, r, "discreto")[:-4] + \
            f'<text x="{x + r + 2}" y="{y - r + 4}" font-size="8" font-family="Arial">I/P</text></g>'
    S = 'fill="#fff" stroke="#111" stroke-width="1.2"'
    k = r / 16.0
    P = lambda d: f'<path d="{d}" {S} transform="translate({x} {y}) scale({k})"/>'
    T = lambda tx, ty, t, fs=8, extra="": f'<text x="{x + tx * k}" y="{y + ty * k}" font-size="{fs}" text-anchor="middle" font-family="Arial"{extra}>{_x(t)}</text>'
    et = tag(letras, numero) if str(numero or "") else str(letras).upper()
    etq = T(0, 30, et)
    nombre = NOMBRE_SIMBOLO.get(simbolo, simbolo)
    g = [f'<g><title>{_x(tag(letras, numero))}: {_x(nombre)}</title>']
    cuerpo = "M-14 2 L14 18 L14 2 L-14 18 Z"                  # cuerpo de la válvula (dos triángulos opuestos)
    if simbolo == "valvula_diafragma":
        g += [P(cuerpo), P("M0 10 V-4"), P("M-11 -4 A11 9 0 0 1 11 -4 Z"), etq]
    elif simbolo == "valvula_piston":
        g += [P(cuerpo), P("M0 10 V-5"), P("M-8 -16 H8 V-5 H-8 Z"), etq]
    elif simbolo == "valvula_motor":
        g += [P(cuerpo), P("M0 10 V-3"), f'<circle cx="{x}" cy="{y - 11 * k}" r="{8 * k}" {S}/>', T(0, -8, "M", 9), etq]
    elif simbolo == "valvula_solenoide":
        g += [P(cuerpo), P("M0 10 V-4"), P("M-7 -17 H7 V-4 H-7 Z"), T(0, -7.5, "S", 9), etq]
    elif simbolo == "valvula_manual":
        g += [P(cuerpo), P("M0 10 V-4 M-9 -4 H9"), etq]
    elif simbolo == "valvula_alivio":
        g += [P("M0 10 L14 3 L14 17 Z"), P("M0 10 L-7 24 L7 24 Z"), P("M0 10 V6 L-5 4 L5 1 L-5 -2 L5 -5 L-5 -8 L0 -10 V-14"), T(0, 34, et)]
    elif simbolo == "placa_orificio":
        g += [P("M-20 0 H20"), P("M-2.5 -10 V10 M2.5 -10 V10"), T(0, 22, et)]
    elif simbolo == "venturi":
        g += [P("M-20 -7 L-7 -3 H7 L20 -7 M-20 7 L-7 3 H7 L20 7"), T(0, 22, et)]
    elif simbolo == "rotametro":
        g += [P("M-4 13 L-8 -13 H8 L4 13 Z"), f'<circle cx="{x}" cy="{y + 2 * k}" r="{2.6 * k}" fill="#111"/>', T(0, 25, et)]
    elif simbolo == "termopozo":
        g += [P("M-16 -12 H16"), P("M-4 -12 V8 A4 4 0 0 0 4 8 V-12"), T(0, 24, et)]
    elif simbolo == "visor_nivel":
        g += [P("M-5 -16 H5 V16 H-5 Z"), P("M-5 -12 H-14 M-5 12 H-14"), P("M-3 2 H3 M-3 5 H3"), T(0, 28, et)]
    elif simbolo == "caja_conexiones":
        g += [P("M-16 -12 H16 V12 H-16 Z"), P("M-16 -12 L-10 -6 M16 -12 L10 -6 M-16 12 L-10 6 M16 12 L10 6"),
              T(0, -1, letras.upper(), 8.5, ' font-weight="bold"'), T(0, 8, numero, 7.5)]
    elif simbolo == "regleta_bornes":
        g += [P("M-20 -8 H20 V8 H-20 Z")] + [f'<circle cx="{x + c * k}" cy="{y}" r="{2.3 * k}" {S}/>' for c in (-14, -7, 0, 7, 14)] + [T(0, 20, et)]
    elif simbolo == "fuente_alimentacion":
        g += [P("M-16 -12 H16 V12 H-16 Z"), T(0, -1, "+  −", 9), T(0, 8, "24 V c.c.", 6), T(0, 24, et)]
    elif simbolo in ("tarjeta_ai", "tarjeta_ao", "tarjeta_di", "tarjeta_do"):
        g += [P("M-16 -12 H10 L16 -6 V12 H-16 Z"), P("M-16 -6 H-20 M-16 0 H-20 M-16 6 H-20"),
              T(0, 2, letras.upper(), 9, ' font-weight="bold"'), T(0, 24, et)]
    else:
        return burbuja(letras, numero, x, y, ubicacion, r, "discreto")
    g.append("</g>")
    return "".join(g)
