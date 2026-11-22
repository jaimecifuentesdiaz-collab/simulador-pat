"""Tabla única de reemplazos de textos visibles (PAT 140g, 17-11-2026).

La aplicación es una herramienta de diseño de plantas para estudiantes y docentes: sus textos visibles no remiten a un
informe, a una memoria ni a una persona en particular. Esta tabla la usan el código (los textos ya quedaron reescritos con
ella) y el script «03 Base de datos/limpiar_textos_PAT140g.py», que limpia los textos ya sembrados en una base existente,
para que el código y la base digan lo mismo.

REEMPLAZOS va en orden: primero las frases largas y después las genéricas. Cada reemplazo es idempotente (el texto nuevo
no contiene el antiguo), así que aplicar la tabla dos veces da el mismo resultado.
"""
from __future__ import annotations

REF = "simulador didáctico de referencia"

REEMPLAZOS: list[tuple[str, str]] = [
    # ---------------------------------------------------------------- costo anual total y disponibilidad
    ("Hoja manuscrita del profesor Torres, 14-11-2026", "Disponibilidad del equipo"),
    ("La hoja del profesor (14-11-2026) define la fórmula A = 1 − ((1 − R) + t_MP) pero no da el valor",
     "La fórmula A = 1 − ((1 − R) + t_MP) no fija el valor de t_MP"),
    ("Disponibilidad del equipo dada por la opción (ficha o profesor)", "Disponibilidad del equipo dada por la opción (ficha o docente)"),
    ("Forma de la hoja del profesor (η máxima en el punto de diseño)", "Curva parabólica con η máxima en el punto de diseño"),
    ("C = C_inv + C_op + C_inef del profesor Torres", "C = C_inv + C_op + C_inef"),
    (", hoja del profesor Torres", ""),
    # ---------------------------------------------------------------- simulador SCORM de referencia
    ("orden de magnitud del simulador del profesor", "orden de magnitud didáctico"),
    ("Orden de magnitud del simulador del profesor", "Orden de magnitud didáctico"),
    ("(Scorm_pellet_profesor.html, ", "(SCORM de pellet, "),
    ("de Scorm_pellet_profesor.html", "del simulador SCORM de pellet"),
    ("Scorm_pellet_profesor.html", "simulador SCORM de pellet"),
    ("en el profesor la causa especial", f"en el {REF} la causa especial"),
    ("El profesor usa 12,5 t", f"El {REF} usa 12,5 t"),
    ("El profesor parte con 65 t", f"El {REF} parte con 65 t"),
    ("El profesor limita la conformidad", f"El {REF} limita la conformidad"),
    ("el profesor revisa solo los puntos", f"el {REF} revisa solo los puntos"),
    ("qualityMean del profesor", f"qualityMean del {REF}"),
    ("el aporte del PAT al simulador del profesor", f"el aporte de esta aplicación al {REF}"),
    ("simulador del profesor", REF),
    ("Simulador del profesor", "Simulador didáctico de referencia"),
    # ---------------------------------------------------------------- rol de quien usa Docente, Curso o Mantenedor
    ("clave del profesor del Mantenedor", "clave docente del Mantenedor"),
    ("Clave del profesor", "Clave del docente"),
    ("clave del profesor", "clave del docente"),
    ("Acceso de profesor:", "Acceso de docente:"),
    ("Opción del profesor", "Opción del docente"),
    ("El profesor puede editar", "El docente puede editar"),
    ("El profesor lo reemplaza", "El docente lo reemplaza"),
    ("el profesor lo ajusta", "el docente lo ajusta"),
    ("le indicó su profesor", "le indicó su docente"),
    ("función reservada al profesor:", "función reservada al docente:"),
    ("#### Profesor", "#### Docente"),
    # ---------------------------------------------------------------- pedidos y fechas de reunión en las ayudas
    ("El profesor Torres pidió (04-11-2026) llevar a la evaluación económica", "Lleva a la evaluación económica"),
    ("El profesor Torres pidió vistas de elevación del *layout* (04-11-2026); en ingeniería básica muestran si",
     "Las vistas de elevación del *layout* muestran, en ingeniería básica, si"),
    ("El profesor Torres pidió vistas isométricas interactivas del *layout* definido (04-11-2026): se ve",
     "Con las vistas isométricas interactivas del *layout* definido se ve"),
    ("El profesor Torres pidió un *layout* preliminar con *piping* y alimentaciones eléctricas (04-11-2026).",
     "El *layout* preliminar incluye *piping* y alimentaciones eléctricas."),
    ("El profesor Torres pidió un plano con dibujo profesional de ingeniería (13-11-2026):",
     "El plano sale con dibujo profesional de ingeniería:"),
    (" (PAT 136, punto 4 de los comentarios del profesor)", " (PAT 136)"),
    # ---------------------------------------------------------------- capítulos e informe del proyecto
    ("Capítulo 1 del PAT y escenarios/agrozzi.py: DIA 2025", "Planta basada en Agrozzi (escenarios/agrozzi.py): DIA 2025"),
    (" (Capítulo 1 del PAT y escenarios/agrozzi.py)", " (escenarios/agrozzi.py)"),
    ("La planta del PAT: Agrozzi en Teno, con las cifras del Capítulo 1.",
     "La planta de referencia: Agrozzi en Teno, con las cifras de Modelo_PAT_Agrozzi_v2.xlsx."),
    ("El modelo del PAT: pasta hot break", "El modelo de referencia: pasta hot break"),
    ("Informe 1, Tabla 25", "Supuesto de partida del modelo de la planta basada en Agrozzi"),
    ("Modelo_PAT_Capitulos2a4_Agrozzi_v1.xlsx, hoja PARAMETROS", "Modelo económico de la planta basada en Agrozzi (v1), hoja PARAMETROS"),
    ("residuales del Capítulo 1", "residuales de la planta basada en Agrozzi"),
    ("30 °Brix del Capítulo 1", "30 °Brix de la planta basada en Agrozzi"),
    ("basada en Agrozzi del Capítulo 1", "basada en Agrozzi"),
    ("Línea base del Capítulo 1 (", "Línea base de la planta basada en Agrozzi ("),
    ("Línea de pasta de tomate del Capítulo 1 (", "Línea de pasta de tomate de la planta basada en Agrozzi ("),
    ("como en el Capítulo 1 y en Modelo_PAT_Agrozzi_v2.xlsx", "como en Modelo_PAT_Agrozzi_v2.xlsx"),
    ("Cifras del Capítulo 1: Modelo_PAT_Agrozzi_v2.xlsx", "Cifras de la planta basada en Agrozzi: Modelo_PAT_Agrozzi_v2.xlsx"),
    ("Modelo_PAT_Agrozzi_v2.xlsx (Capítulo 1).", "Modelo_PAT_Agrozzi_v2.xlsx."),
    ("la planta base del Capítulo 1", "la planta base"),
    ("del balance de la propia planta (Capítulo 1)", "del balance de la propia planta"),
    ("(450.000 t en 76 días, Capítulo 1)", "(450.000 t en 76 días)"),
    (" (el mismo de los Capítulos 2 a 4)", ""),
    ("del modelo de los Capítulos 2 a 4", "del modelo económico de la planta basada en Agrozzi"),
    ("Las cuatro alternativas del Capítulo 3 con el balance actual", "Las cuatro alternativas de recuperación de calor con el balance actual"),
    ("Las mismas cuatro alternativas y el mismo método del Capítulo 3:", "Las cuatro alternativas y el método de comparación:"),
    ("(SII, Res. Ex. 43/2002), como en el Capítulo 4.", "(SII, Res. Ex. 43/2002)."),
    ("(Capítulo 4, sección 4.7.7, y Supuestos declarados)", "(Supuestos declarados)"),
    ("(Capítulo 4, sección 4.7.7)", "(Supuestos de sensibilidad)"),
    ("techo del rango de sensibilidad del Capítulo 4", "techo del rango de sensibilidad"),
    ("con U medio (Capítulo 4) y", "con U medio y"),
    ("Cada cifra del informe debe tener fuente y fecha", "Cada cifra de un informe técnico debe tener fuente y fecha"),
    ("como exige el informe del PAT:", "como exige un informe técnico:"),
    ("como exige el informe.", "como exige un informe técnico."),
    # ---------------------------------------------------------------- costeo
    ("o con el PDF «estimación de costo de planta» del profesor", "o con una cotización"),
    ("o con el PDF del profesor", "o de una cotización"),
]


def neutralizar(texto):
    """Aplica REEMPLAZOS en orden. Devuelve el mismo objeto si no es texto."""
    if not isinstance(texto, str):
        return texto
    for viejo, nuevo in REEMPLAZOS:
        if viejo in texto:
            texto = texto.replace(viejo, nuevo)
    return texto


def _revisar_idempotencia() -> list[str]:
    """Reemplazos cuyo texto nuevo vuelve a contener un texto antiguo de la tabla (deben ser cero)."""
    malos = []
    for _v, nuevo in REEMPLAZOS:
        if neutralizar(nuevo) != nuevo:
            malos.append(nuevo)
    return malos
