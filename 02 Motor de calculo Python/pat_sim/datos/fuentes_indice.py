"""Lee el índice de fuentes del Capítulo 1 (00_INDICE_FUENTES_v3.md) y arma fuentes_capitulo1.csv para la base de datos."""
from __future__ import annotations
import csv, re
from datetime import datetime
from pathlib import Path

FECHA_INDICE_V3 = "2026-09-24"     # fecha de la v3 del índice (24 de septiembre de 2026)
CAMPOS = ["cita", "archivo", "doi", "url", "fecha_consulta", "nota", "sha1"]

# Fuentes que usa el simulador (parámetros del catálogo y economía) y que están en la carpeta pero no en las 45 filas de la v3.
# La fecha de consulta es la de descarga del archivo (fecha de modificación) cuando se arma el CSV con la carpeta a mano.
EXTRAS = [
    ("CFT (2024a). ART3MIS Longrun MVR evaporator at Empresas Carozzi, 5-ago-2024.", "CFT_2024a_ART3MIS_Carozzi_pagina.html",
     "https://www.cft-group.com/art3mis-longrun-mvr-evaporator-at-empresas-carozzi/", "Fabricante de los evaporadores: concentraciones y rendimiento"),
    ("CFT (2024b). Tomato processing plants, 9-dic-2024.", "CFT_2024b_Plantas_tomate_pagina.html",
     "https://www.cft-group.com/tomato-processing-plants/", "Fabricante: plantas de tomate"),
    ("CFT (s. f.). Evaporators.", "CFT_sf_Evaporadores_pagina.html",
     "https://www.cft-group.com/technology/evaporators/", "Fabricante: página de evaporadores y del Apollo"),
    ("Engineering ToolBox (2003). Higher Calorific Values of Common Fuels.", "EngineeringToolBox_2003_HHV_combustibles_pagina.html",
     "https://www.engineeringtoolbox.com/fuels-higher-calorific-values-d_169.html", "Poder calorífico superior e inferior del metano"),
    ("Engineering ToolBox (2003). Combustion of Fuels, CO2 Emission.", "EngineeringToolBox_2003_CO2_combustion_pagina.html",
     "https://www.engineeringtoolbox.com/co2-emission-fuels-d_1085.html", "Emisión específica de CO2 del metano"),
    ("Engineering ToolBox (2003). Aire necesario y gases de combustión de los combustibles.", "EngineeringToolBox_2003_aire_y_humos_pagina.html",
     "https://www.engineeringtoolbox.com/fuels-air-flue-gas-d_170.html", "Balance de combustión de la caldera"),
    ("Engineering ToolBox (2003). Exceso de aire y eficiencia de combustión.", "EngineeringToolBox_2003_exceso_de_aire_pagina.html",
     "https://www.engineeringtoolbox.com/fuels-combustion-efficiency-d_167.html", "Exceso de aire del gas natural"),
    ("CNE (2026c). Reporte mensual sector energético, septiembre de 2026, p. 12.", "CNE_2026_RMensual_sep.pdf",
     None, "Henry Hub de agosto de 2026: 2,77 US$/MMBtu"),
    ("Banco Central de Chile (2026). Indicadores diarios, 26 de octubre de 2026.", "BCCh_2026_Indicadores_26oct.pdf",
     None, "Dólar observado: 990,35 $/US$"),
    ("Bakar, y otros (2016). Applied Energy, 162, 1259–1271.", "Bakar_2016.pdf",
     None, "Aproximación mínima de temperatura en recuperación de calor"),
]


def _fecha_archivo(carpeta: Path | None, nombre: str) -> str | None:
    if carpeta is None or not (carpeta / nombre).exists():
        return None
    return datetime.fromtimestamp((carpeta / nombre).stat().st_mtime).date().isoformat()


def leer_indice(ruta: str | Path) -> list[dict]:
    """Filas con 5 celdas cuyo primer campo es un archivo entre acentos graves (las 45 de la v3)."""
    filas = []
    for linea in Path(ruta).read_text(encoding="utf-8").splitlines():
        if not linea.startswith("| `"):
            continue
        c = [x.strip() for x in linea.strip().strip("|").split("|")]
        if len(c) != 5:
            continue
        archivo = c[0].strip("` "); cita = c[2]
        doi = re.search(r"https?://doi\.org/(\S+)", cita)
        url = re.search(r"https?://\S+", cita)
        filas.append(dict(cita=cita, archivo=archivo,
                          doi=doi.group(1).rstrip(".,;") if doi else None,
                          url=url.group(0).rstrip(".,;") if url else None,
                          fecha_consulta=FECHA_INDICE_V3, nota=c[3], sha1=c[4].strip("` ")))
    return filas


def armar_csv(ruta_indice: str | Path, destino: str | Path, carpeta_fuentes: str | Path | None = None) -> int:
    filas = leer_indice(ruta_indice)
    carpeta = Path(carpeta_fuentes) if carpeta_fuentes else Path(ruta_indice).parent
    conocidos = {f["archivo"] for f in filas}
    for cita, archivo, url, nota in EXTRAS:
        if archivo not in conocidos:
            filas.append(dict(cita=cita, archivo=archivo, doi=None, url=url,
                              fecha_consulta=_fecha_archivo(carpeta, archivo), nota=nota, sha1=""))
    with open(destino, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CAMPOS); w.writeheader()
        for r in filas:
            w.writerow({k: ("" if r.get(k) is None else r[k]) for k in CAMPOS})
    return len(filas)
