"""Símbolos gráficos de equipos según la ISO 10628 (UNE-EN ISO 10628:2001, Tabla C.1, serie básica) y letras código del Anexo D.

Cada símbolo se dibuja en SVG dentro de una caja de 60 × 60 (la cuadrícula M de la norma es de 2,5 mm;
aquí 1 módulo = 5 unidades). Se pueden girar o escalar sin cambiar su significado (Tabla C.1, C.3).
Fuente: PROCESOS 2 DESCARGA\\norma-iso-10628-para_diagramas_de_procesos.pdf, pp. 23 a 66.
"""
from __future__ import annotations

LETRAS_EQUIPO = {  # Anexo D.2
    "A": "Equipo o máquina no clasificado en otro grupo", "B": "Recipiente, depósito, tolva, silo", "C": "Reactor químico",
    "D": "Generador de vapor, generador de gas, horno", "F": "Filtro, tamiz, separador", "G": "Engranaje",
    "H": "Elevador, transportador, medio de transporte", "K": "Columna", "M": "Motor eléctrico", "P": "Bomba",
    "R": "Agitador, mezclador, amasadora", "S": "Centrifugadora", "T": "Secador", "V": "Compresor, bomba de vacío, soplante, ventilador",
    "W": "Intercambiador de calor", "X": "Alimentación y distribución, equipamiento especial", "Y": "Transmisión, motor no eléctrico",
    "Z": "Trituradora, amoladora",
}
LETRAS_VALVULA = {"B": "Llave de paso", "F": "Filtro en tubería, purgador", "H": "Válvula de control", "K": "Purgador de vapor",
                  "R": "Válvula de retención", "S": "Válvula o accesorio de seguridad", "V": "Válvula, general"}  # Anexo D.3
CATEGORIAS = {1: "Recipientes y depósitos", 2: "Recipientes y columnas con equipamiento interior", 3: "Calefacción y refrigeración",
              4: "Intercambiadores de calor, generadores de vapor, hornos", 5: "Filtros", 6: "Cribas, tamices", 7: "Separadores",
              8: "Centrifugadoras", 9: "Secadores", 10: "Trituradoras, amoladoras", 11: "Agitadores", 12: "Mezcladores, amasadoras",
              13: "Máquinas de proceso de transformación y de acabado", 14: "Bombas de líquido", 15: "Compresores, bombas de vacío, soplantes, ventiladores",
              16: "Elevadores, transportadores", 17: "Básculas", 18: "Dosificadores, alimentadores, distribución", 19: "Motores, transmisiones",
              20: "Equipamientos varios", 21: "Válvulas de paso", 22: "Válvulas de retención", 23: "Válvulas de control", 24: "Válvulas de seguridad"}

S = 'fill="#fff" stroke="#111" stroke-width="1.6"'
L = 'fill="none" stroke="#111" stroke-width="1.6"'
D = 'fill="none" stroke="#111" stroke-width="1.2" stroke-dasharray="4 3"'

# id: (nombre, categoría Tabla C.1, letra Anexo D, dibujo en caja 60x60)
SIMBOLOS: dict[str, tuple[str, int, str, str]] = {
    "recipiente": ("Recipiente, general", 1, "B", f'<rect x="15" y="3" width="30" height="54" rx="15" {S}/>'),
    "deposito": ("Depósito abierto", 1, "B", f'<path d="M8 15 V52 H52 V15" {L}/><path d="M8 52 H52" {L}/>'),
    "tolva": ("Tolva, silo", 1, "B", f'<path d="M10 5 H50 V32 L34 54 H26 L10 32 Z" {S}/>'),
    "almacenamiento_granel": ("Almacenamiento a granel, montón", 20, "A", f'<path d="M4 50 L30 14 L56 50 Z" {S}/><path d="M2 52 H58" {L}/>'),
    "recipiente_agitado": ("Recipiente con agitador", 11, "R", f'<rect x="13" y="6" width="34" height="50" rx="12" {S}/><path d="M30 0 V42 M22 42 H38 M22 38 V46 M38 38 V46" {L}/>'),
    "intercambiador_general": ("Intercambiador de calor, general", 4, "W", f'<circle cx="30" cy="30" r="22" {S}/><path d="M8 30 L16 30 L21 20 L27 40 L33 20 L39 40 L44 30 L52 30" {L}/>'),
    "intercambiador_tubular": ("Intercambiador de calor de haz tubular", 4, "W", f'<rect x="6" y="18" width="48" height="24" rx="10" {S}/><path d="M14 24 H46 M14 30 H46 M14 36 H46" {L}/><path d="M14 18 V42 M46 18 V42" {L}/>'),
    "intercambiador_placas": ("Intercambiador de calor (placas)", 4, "W", f'<rect x="10" y="10" width="40" height="40" {S}/><path d="M10 10 L50 50 M50 10 L10 50" {L}/>'),
    "condensador": ("Condensador (intercambiador de calor)", 4, "W", f'<circle cx="30" cy="30" r="22" {S}/><path d="M16 22 L30 30 L16 38" {L}/><path d="M30 8 V52" {D}/>'),
    "evaporador_pelicula": ("Evaporador de película", 4, "W", f'<path d="M18 4 H42 V44 L30 56 L18 44 Z" {S}/><path d="M24 10 V40 M30 10 V40 M36 10 V40" {L}/>'),
    "evaporador_mvr": ("Evaporador de película con recompresión mecánica de vapor", 4, "W",
                       f'<path d="M10 10 H32 V46 L21 56 L10 46 Z" {S}/><path d="M16 16 V40 M21 16 V40 M26 16 V40" {L}/>'
                       f'<circle cx="46" cy="20" r="11" {S}/><path d="M38 13 L54 17 M38 27 L54 23" {L}/><path d="M32 18 H35" {L}/>'),
    "evaporador_multiefecto": ("Evaporador de múltiple efecto", 4, "W",
                               ''.join(f'<path d="M{x} 8 H{x + 16} V44 L{x + 8} 54 L{x} 44 Z" {S}/><path d="M{x + 5} 14 V38 M{x + 11} 14 V38" {L}/>' for x in (2, 22, 42))),
    "caldera": ("Caldera de vapor (generador de vapor)", 4, "D", f'<path d="M10 56 V24 A20 20 0 0 1 50 24 V56 Z" {S}/><path d="M18 46 L24 36 L30 46 L36 36 L42 46" {L}/>'),
    "horno": ("Horno, general", 4, "D", f'<path d="M18 4 H42 L54 16 V44 L42 56 H18 L6 44 V16 Z" {S}/><rect x="20" y="20" width="20" height="20" {L}/>'),
    "quemador": ("Sistema de encendido, quemador", 4, "D", f'<path d="M14 50 V34 L30 18 L46 34 V50 Z" {S}/><path d="M30 26 C24 34 36 38 30 46" {L}/>'),
    "chimenea": ("Chimenea", 20, "A", f'<path d="M22 56 L26 4 H34 L38 56 Z" {S}/>'),
    "filtro": ("Filtro, general", 5, "F", f'<rect x="10" y="6" width="40" height="48" {S}/><path d="M10 30 H50" {D}/>'),
    "criba": ("Dispositivo de cribado", 6, "F", f'<path d="M12 6 H48 V40 L30 56 L12 40 Z" {S}/><path d="M12 12 L48 40" {D}/>'),
    "tamiz": ("Criba, general", 6, "F", f'<path d="M4 30 L14 16 H46 L56 30 L46 44 H14 Z" {S}/><path d="M30 16 V44" {L}/>'),
    "ciclon": ("Ciclón (separador)", 7, "F", f'<path d="M14 4 H46 V24 L34 54 H26 L14 24 Z" {S}/><path d="M24 4 V16 H36 V4" {L}/>'),
    "centrifuga": ("Centrifugadora", 8, "S", f'<rect x="8" y="14" width="44" height="32" rx="4" {S}/><path d="M16 30 A14 10 0 1 0 44 30 A14 10 0 1 0 16 30" {L}/>'),
    "secador": ("Secador, general", 9, "T", f'<path d="M14 4 H46 L54 14 V56 H6 V14 Z" {S}/>'),
    "secador_tambor": ("Secador rotatorio (tambor)", 9, "T", f'<g transform="rotate(-10 30 30)"><rect x="4" y="18" width="52" height="24" rx="6" {S}/><path d="M16 15 V45 M44 15 V45" {L}/></g>'),
    "secador_banda": ("Secador de banda", 9, "T", f'<path d="M14 4 H46 L54 14 V56 H6 V14 Z" {S}/><path d="M12 34 H48" {L}/><circle cx="14" cy="34" r="3" {S}/><circle cx="46" cy="34" r="3" {S}/>'),
    "trituradora": ("Trituradora, general", 10, "Z", f'<path d="M6 10 H54 L44 50 H16 Z" {S}/><path d="M20 18 L40 42 M40 18 L20 42" {L}/>'),
    "molino_martillos": ("Trituradora de martillos (molino)", 10, "Z", f'<path d="M6 10 H54 L44 50 H16 Z" {S}/><circle cx="30" cy="28" r="9" {L}/><path d="M30 19 V37 M21 28 H39" {L}/>'),
    "astilladora": ("Trituradora de disco (astilladora)", 10, "Z", f'<path d="M6 10 H54 L44 50 H16 Z" {S}/><circle cx="30" cy="28" r="10" {L}/><path d="M22 22 L38 34 M22 34 L38 22" {L}/>'),
    "sierra": ("Máquina de corte (sierra para leña)", 13, "A", f'<rect x="6" y="18" width="48" height="26" {S}/><circle cx="30" cy="31" r="10" {L}/><path d="M30 21 L32 25 M38 24 L35 28 M40 31 L36 31 M22 38 L25 35" {L}/>'),
    "mezclador": ("Mezclador", 12, "R", f'<rect x="6" y="16" width="48" height="28" {S}/><path d="M10 30 C16 18 22 42 28 30 C34 18 40 42 46 30 L50 30" {L}/>'),
    "maquina_acabado": ("Máquina de acabado (llenadora, ensacadora)", 13, "A", f'<rect x="6" y="6" width="48" height="30" {S}/><path d="M22 36 L26 44 H34 L38 36" {L}/><rect x="22" y="44" width="16" height="12" {S}/>'),
    "pelletizadora": ("Máquina de transformación: pelletizadora de matriz anular", 13, "A", f'<rect x="6" y="8" width="48" height="44" {S}/><circle cx="30" cy="30" r="15" {L}/><circle cx="30" cy="30" r="7" {L}/>' + ''.join(f'<circle cx="{30 + 11 * c}" cy="{30 + 11 * s}" r="1.4" fill="#111"/>' for c, s in ((1, 0), (-1, 0), (0, 1), (0, -1), (.7, .7), (-.7, .7), (.7, -.7), (-.7, -.7)))),
    "enfriador_contracorriente": ("Enfriador de contracorriente (de pellet)", 9, "T", f'<path d="M12 4 H48 V40 L36 56 H24 L12 40 Z" {S}/><path d="M18 46 H42" {L}/><path d="M6 30 H12 M48 18 H54" {L}/>'),
    "bomba": ("Bomba, general", 14, "P", f'<circle cx="30" cy="30" r="20" {S}/><path d="M14 18 L46 30 L14 42" {L}/>'),
    "compresor": ("Compresor, general", 15, "V", f'<circle cx="30" cy="30" r="20" {S}/><path d="M14 18 L46 24 M14 42 L46 36" {L}/>'),
    "ventilador": ("Ventilador", 15, "V", f'<circle cx="30" cy="30" r="20" {S}/><path d="M30 30 L30 14 Q38 18 30 30 Q46 34 36 40 L30 30 Q22 42 16 34 Z" {L}/>'),
    "eyector": ("Compresor eyector (termocompresor)", 15, "V", f'<path d="M4 22 H20 L30 28 V32 L20 38 H4 Z M30 28 H40 L56 20 V40 L40 32 H30" {S}/><path d="M30 10 V28" {L}/>'),
    "bomba_vacio": ("Bomba de vacío", 15, "V", f'<circle cx="30" cy="30" r="20" {S}/><path d="M14 24 L46 18 M14 36 L46 42" {L}/>'),
    "transportador_cinta": ("Cinta transportadora", 16, "H", f'<circle cx="12" cy="30" r="7" {S}/><circle cx="48" cy="30" r="7" {S}/><path d="M12 23 H48 M12 37 H48" {L}/>'),
    "transportador_tornillo": ("Transportador de tornillo sin fin", 16, "H", f'<rect x="4" y="18" width="52" height="24" {S}/><path d="M8 30 L14 22 L20 38 L26 22 L32 38 L38 22 L44 38 L50 22 L54 30" {L}/>'),
    "elevador_cangilones": ("Elevador de cangilones", 16, "H", f'<rect x="20" y="2" width="20" height="56" rx="10" {S}/><path d="M25 12 V48 M35 12 V48" {L}/><path d="M35 20 h4 M35 30 h4 M35 40 h4" {L}/>'),
    "bascula": ("Báscula", 17, "A", f'<path d="M10 40 H50 L30 18 Z" {S}/><path d="M6 46 H54" {L}/>'),
    "dosificador_rotativo": ("Alimentador de válvula rotativa", 18, "X", f'<rect x="10" y="10" width="40" height="40" {S}/><circle cx="30" cy="30" r="14" {L}/><path d="M16 30 H44 M30 16 V44" {L}/>'),
    "motor": ("Motor eléctrico", 19, "M", f'<circle cx="30" cy="30" r="18" {S}/><text x="30" y="36" font-size="18" text-anchor="middle" font-family="Arial">M</text>'),
    "valvula": ("Válvula, general", 21, "V", f'<path d="M10 20 L30 30 L10 40 Z M50 20 L30 30 L50 40 Z" {S}/>'),
    "valvula_retencion": ("Válvula de retención", 22, "R", f'<path d="M10 20 L30 30 L10 40 Z" {S}/><path d="M50 20 L30 30 L50 40 Z" fill="#111" stroke="#111"/>'),
    "valvula_control": ("Válvula de control", 23, "H", f'<path d="M10 30 L30 40 L10 50 Z M50 30 L30 40 L50 50 Z" {S}/><path d="M30 40 V20" {L}/><path d="M18 20 A12 10 0 0 1 42 20 Z" {S}/>'),
    "valvula_seguridad": ("Válvula de seguridad", 24, "S", f'<path d="M20 40 L30 30 L40 40 Z M20 20 L30 30 L20 40" {S}/><path d="M30 30 V6 M26 8 L34 12 L26 16 L34 20" {L}/>'),
    "equipo_general": ("Equipo o máquina, general", 20, "A", f'<rect x="6" y="12" width="48" height="36" rx="3" {S}/>'),
    # PAT 132: símbolos de la serie básica que completan las 24 categorías de la Tabla C.1 (opción «Todos los equipos»)
    "recipiente_presion": ("Recipiente a presión (fondos abombados)", 1, "B", f'<rect x="15" y="3" width="30" height="54" rx="15" {S}/><path d="M15 12 H45 M15 48 H45" {L}/>'),
    "tanque_esferico": ("Recipiente esférico", 1, "B", f'<circle cx="30" cy="28" r="22" {S}/><path d="M16 46 L12 58 M44 46 L48 58" {L}/>'),
    "gasometro": ("Gasómetro", 1, "B", f'<rect x="8" y="22" width="44" height="34" {S}/><path d="M14 22 V10 H46 V22" {L}/>'),
    "columna": ("Columna, general", 2, "K", f'<rect x="20" y="2" width="20" height="56" rx="10" {S}/>'),
    "columna_platos": ("Columna de platos", 2, "K", f'<rect x="20" y="2" width="20" height="56" rx="10" {S}/><path d="M20 18 H40 M20 26 H40 M20 34 H40 M20 42 H40" {L}/>'),
    "columna_relleno": ("Columna de relleno", 2, "K", f'<rect x="20" y="2" width="20" height="56" rx="10" {S}/><path d="M20 16 L40 44 M40 16 L20 44 M20 16 H40 M20 44 H40" {L}/>'),
    "reactor": ("Reactor, recipiente con equipamiento interior", 2, "C", f'<rect x="14" y="4" width="32" height="52" rx="12" {S}/><path d="M18 20 H42 M18 40 H42" {D}/>'),
    "camisa": ("Recipiente con camisa de calefacción o refrigeración", 3, "W", f'<rect x="16" y="8" width="28" height="46" rx="10" {S}/><path d="M12 18 V46 A14 10 0 0 0 48 46 V18" {L}/>'),
    "serpentin": ("Serpentín de calefacción o refrigeración", 3, "W", f'<rect x="12" y="6" width="36" height="48" rx="10" {S}/><path d="M18 20 Q30 26 42 20 Q30 32 18 30 Q30 38 42 32 Q30 44 18 40" {L}/>'),
    "aeroenfriador": ("Intercambiador enfriado por aire (aeroenfriador)", 4, "W", f'<rect x="6" y="22" width="48" height="16" {S}/><circle cx="30" cy="48" r="8" {S}/><path d="M22 48 H38" {L}/>'),
    "torre_enfriamiento": ("Torre de enfriamiento", 4, "W", f'<path d="M14 56 L20 6 H40 L46 56 Z" {S}/><path d="M18 30 H42" {D}/>'),
    "filtro_prensa": ("Filtro prensa", 5, "F", f'<rect x="4" y="16" width="52" height="28" {S}/><path d="M12 16 V44 M20 16 V44 M28 16 V44 M36 16 V44 M44 16 V44" {L}/>'),
    "filtro_mangas": ("Filtro de mangas (gases)", 5, "F", f'<path d="M10 4 H50 V38 L34 56 H26 L10 38 Z" {S}/><path d="M20 8 V32 M30 8 V32 M40 8 V32" {L}/>'),
    "separador_gotas": ("Separador de gotas", 7, "F", f'<rect x="15" y="3" width="30" height="54" rx="15" {S}/><path d="M15 22 H45" {D}/>'),
    "decantador": ("Separador por gravedad (decantador)", 7, "F", f'<rect x="4" y="16" width="52" height="28" rx="12" {S}/><path d="M36 22 V44" {L}/>'),
    "secador_pulverizacion": ("Secador por pulverización", 9, "T", f'<path d="M10 4 H50 V34 L30 56 L10 34 Z" {S}/><path d="M24 10 L30 18 L36 10" {L}/>'),
    "molino_bolas": ("Molino de bolas (tambor)", 10, "Z", f'<rect x="4" y="16" width="52" height="28" rx="6" {S}/><circle cx="20" cy="30" r="4" {S}/><circle cx="32" cy="34" r="4" {S}/><circle cx="42" cy="26" r="4" {S}/>'),
    "molino_rodillos": ("Trituradora de rodillos", 10, "Z", f'<path d="M6 10 H54 L44 50 H16 Z" {S}/><circle cx="23" cy="28" r="8" {S}/><circle cx="37" cy="28" r="8" {S}/>'),
    "extrusora": ("Extrusora", 13, "A", f'<rect x="4" y="22" width="44" height="16" {S}/><path d="M48 24 L56 30 L48 36 M8 30 Q14 22 20 30 Q26 38 32 30 Q38 22 44 30" {L}/>'),
    "bomba_centrifuga": ("Bomba centrífuga", 14, "P", f'<circle cx="30" cy="30" r="20" {S}/><path d="M30 10 H52" {L}/>'),
    "bomba_desplazamiento": ("Bomba de desplazamiento positivo", 14, "P", f'<circle cx="30" cy="30" r="20" {S}/><path d="M18 30 H42 M24 22 L18 30 L24 38" {L}/>'),
    "bomba_tornillo": ("Bomba de tornillo", 14, "P", f'<rect x="6" y="20" width="48" height="20" rx="4" {S}/><path d="M10 30 Q16 22 22 30 Q28 38 34 30 Q40 22 46 30" {L}/>'),
    "soplante": ("Soplante", 15, "V", f'<circle cx="30" cy="30" r="20" {S}/><path d="M14 22 L46 30 L14 38" {L}/><path d="M30 10 H50" {L}/>'),
    "transporte_neumatico": ("Transportador neumático", 16, "H", f'<path d="M4 40 H40 V14 H56" {L}/><path d="M4 34 H34 V8 H56" {L}/>'),
    "turbina": ("Turbina", 19, "Y", f'<path d="M12 20 L48 8 V52 L12 40 Z" {S}/>'),
    "valvula_mariposa": ("Válvula de mariposa", 21, "V", f'<path d="M10 20 L30 30 L10 40 Z M50 20 L30 30 L50 40 Z" {S}/><path d="M30 18 V42" {L}/>'),
    "valvula_bola": ("Válvula de bola", 21, "V", f'<path d="M10 20 L30 30 L10 40 Z M50 20 L30 30 L50 40 Z" {S}/><circle cx="30" cy="30" r="5" fill="#111"/>'),
    "valvula_tres_vias": ("Válvula de tres vías", 21, "V", f'<path d="M8 22 L30 30 L8 38 Z M52 22 L30 30 L52 38 Z M22 56 L30 30 L38 56 Z" {S}/>'),
}


def svg(simbolo: str, x: float = 0, y: float = 0, ancho: float = 60, alto: float | None = None) -> str:
    """Devuelve el símbolo como grupo SVG en (x, y) escalado a ancho × alto."""
    alto = alto or ancho
    nombre, cat, letra, dib = SIMBOLOS.get(simbolo, SIMBOLOS["equipo_general"])
    return f'<g transform="translate({x},{y}) scale({ancho / 60},{alto / 60})"><title>{nombre} (ISO 10628, categoría {cat}, letra {letra})</title>{dib}</g>'


def svg_suelto(simbolo: str, tam: int = 60) -> str:
    return f'<svg xmlns="http://www.w3.org/2000/svg" width="{tam}" height="{tam}" viewBox="0 0 60 60">{SIMBOLOS.get(simbolo, SIMBOLOS["equipo_general"])[3]}</svg>'


def lamina(cols: int = 6) -> str:
    """Lámina con todos los símbolos, su categoría y su letra código (para revisar y para el informe)."""
    items = list(SIMBOLOS.items()); w, h = 205, 120; rows = (len(items) + cols - 1) // cols
    out = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{cols * w}" height="{rows * h + 40}" viewBox="0 0 {cols * w} {rows * h + 40}" font-family="Arial">',
           '<rect width="100%" height="100%" fill="#fff"/>',
           f'<text x="10" y="24" font-size="15" font-weight="bold">Biblioteca de símbolos ISO 10628 (Tabla C.1, serie básica; letras código del Anexo D)</text>']
    for i, (k, (nm, cat, letra, _)) in enumerate(items):
        cx, cy = (i % cols) * w, 40 + (i // cols) * h
        out.append(f'<rect x="{cx + 4}" y="{cy + 2}" width="{w - 8}" height="{h - 6}" fill="none" stroke="#ccc"/>')
        out.append(svg(k, cx + w / 2 - 25, cy + 8, 50))
        words = nm.split(" "); line1 = ""; lines = []
        for wd in words:
            if len(line1) + len(wd) > 26: lines.append(line1); line1 = wd
            else: line1 = (line1 + " " + wd).strip()
        lines.append(line1)
        for j, ln in enumerate(lines[:3]):
            out.append(f'<text x="{cx + w / 2}" y="{cy + 72 + j * 12}" font-size="10" text-anchor="middle">{ln}</text>')
        out.append(f'<text x="{cx + w / 2}" y="{cy + h - 10}" font-size="10" text-anchor="middle" fill="#555">Cat. {cat} · letra {letra} · {k}</text>')
    out.append('</svg>')
    return "".join(out)
