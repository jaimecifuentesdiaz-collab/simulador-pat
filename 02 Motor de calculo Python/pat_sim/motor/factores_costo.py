"""Sistemas de costeo con factores de literatura (PAT 136, tarea T24, 13-11-2026): punto 11 de los comentarios del profesor
Torres del 13-11-2026 (01 Requisitos y diseno/Comentarios_profesor_Torres_13nov2026.md).

Pasa del costo de los equipos comprados (motor/costeo.py) a la inversión de la planta con cinco métodos seleccionables:

- factor_unico: el factor 2,5 de motor/costos.py (1/0,40, fracción de equipo de la Danish Energy Agency, 2026; Supuesto). Es el
  método por defecto y deja todas las cifras de costeo.py como estaban.
- lang: un solo factor por tipo de planta (sólidos, sólidos y fluidos, fluidos), Lang (1947, 1948).
- hand: un factor por tipo de equipo, Hand (1958), con los valores de Brown (2006), Tabla 3.2.
- modulo_desnudo: Guthrie (1969) en la forma de Turton et al.: C_BM = Cp0·F_BM con F_BM = B1 + B2·FM·FP, costo de módulo total
  C_TM = 1,18·ΣC_BM y planta nueva C_GR = C_TM + 0,50·ΣC_BM0.
- desglose: ítem por ítem como porcentaje del costo de los equipos entregados, Peters y Timmerhaus (1991), Tabla 17.

Además, la mantención anual y los otros costos fijos de operación (suministros, seguros e impuestos territoriales) como
porcentaje de la inversión de capital fijo, con sus rangos de literatura (operacion_fija).

Cada factor lleva su fuente (autor, año, edición, tabla o página) y su categoría: «Literatura» si se verificó en el libro o en un
apunte que reproduce la tabla, «Literatura (transcrita; cotejar)» si se tomó de una transcripción que cita el libro y falta
cotejar la página, y «Supuesto» con su justificación si no se pudo verificar. La lista FUENTES_FACTORES reúne las fuentes con su
link e ISBN o DOI.

Las cañerías y el cable eléctrico de la lista de equipos (motor/costeo.py) son materiales a granel: los métodos lang, hand,
modulo_desnudo y desglose ya incluyen cañerías y sistema eléctrico en sus factores, por lo que esos ítems quedan fuera de la base
para no contarlos dos veces (se informan aparte). El factor_unico los mantiene en la base, como hasta ahora.
"""
from __future__ import annotations
import math

from . import costos

# ---------------------------------------------------------------- fuentes
FUENTES_FACTORES = [
    dict(clave="ptw1991", referencia="Peters, M. S. y Timmerhaus, K. D. (1991). Plant Design and Economics for Chemical Engineers, "
                                     "4.a ed. McGraw-Hill, Nueva York. Capítulo 6: Tabla 17 (p. 183), Tabla 18 (p. 184), Tabla 25 (p. 203), "
                                     "pp. 204 y 205",
         archivo="Peters_1991_PlantDesign4ed.pdf", isbn="0-07-049613-7", doi="",
         url="https://enajafi.profile.semnan.ac.ir/downloads/file/3031", verificado="Tablas y páginas leídas en el PDF del libro (13-11-2026)"),
    dict(clave="ptw2003", referencia="Peters, M. S., Timmerhaus, K. D. y West, R. E. (2003). Plant Design and Economics for Chemical "
                                     "Engineers, 5.a ed. McGraw-Hill, Nueva York. Capítulo 6, Tabla 6-9 (factores sobre equipos entregados)",
         archivo="Peters_2003_PlantDesign5ed.pdf", isbn="0-07-239266-5", doi="",
         url="https://highered.mheducation.com/sites/0072392665/student_view0/chapter6/chapter_outline.html",
         verificado="Solo el número de tabla y los factores de Lang de la 5.a ed. (4,0; 4,3; 5,0) en un apunte universitario; "
                    "los porcentajes de la Tabla 6-9 no se pudieron leer: la aplicación usa la 4.a ed."),
    dict(clave="brown2006", referencia="Brown, T. (2006). Engineering Economics and Economic Design for Process Engineers. CRC Press, "
                                       "Boca Ratón. Tabla 3.1 (p. 49), Tabla 3.2 (p. 50), p. 81 y Tabla 4.8 (p. 83)",
         archivo="Brown_2006_EngineeringEconomics.pdf", isbn="978-1-4200-0810-4 (libro electrónico)", doi="",
         url="https://nibmehub.com/opac-service/pdf/read/Engineering%20Economics%20and%20Economic%20Design%20for%20Process%20Engineers.pdf",
         verificado="Tablas y páginas leídas en el PDF del libro (13-11-2026)"),
    dict(clave="hand1958", referencia="Hand, W. E. (1958). From flow sheet to cost estimate. Petroleum Refiner, 37(9)",
         archivo="Hand_1958_FlowSheetCostEstimate.pdf", isbn="", doi="",
         url="https://caf-corporation.com/insights/rest-in-peace-hand-factors-1958-2026",
         verificado="Artículo original no disponible; valores tomados de Brown (2006), Tabla 3.2, que cita a Brown (2000), "
                    "Hydrocarbon Processing, octubre de 2000, pp. 93 a 100"),
    dict(clave="lang1947", referencia="Lang, H. J. (1947). Cost relationships in preliminary cost estimation. Chemical Engineering; "
                                      "y Lang, H. J. (1948), artículos sobre estimación preliminar en Chemical Engineering",
         archivo="Lang_1947_CostRelationships.pdf", isbn="", doi="", url="",
         verificado="Artículo original no disponible; factores originales 3,10; 3,63 y 4,74 leídos en Brown (2006), Tabla 3.1, y en "
                    "un apunte del capítulo 5 de Turton et al. (2003)"),
    dict(clave="smith2005", referencia="Smith, R. (2005). Chemical Process Design and Integration. John Wiley & Sons, Chichester. "
                                       "Sección 2.2, Tablas 2.2 a 2.7 (pp. 19 a 21), y sección 2.5 (p. 28)",
         archivo="Smith_2005_ChemicalProcessDesign.pdf", isbn="0-471-48681-7", doi="",
         url="https://fenix.ciencias.ulisboa.pt/downloadFile/1970462275930926/Process Economics in R Smith_ Chemical Process  Design and Integration_ John Wiley and Sons 2005.pdf",
         verificado="Capítulo 2 leído en PDF (13-11-2026); páginas tomadas de los encabezados del texto extraído"),
    dict(clave="turton2003", referencia="Turton, R., Bailie, R. C., Whiting, W. B. y Shaeiwitz, J. A. (2003). Analysis, Synthesis, and "
                                        "Design of Chemical Processes, 2.a ed. Prentice Hall, Upper Saddle River. Capítulo 5, ec. 5.15 y 5.16, "
                                        "ec. A.4 y ejemplo ilustrativo del intercambiador de 100 m²",
         archivo="Turton_2003_AnalysisSynthesisDesign2ed.pdf", isbn="978-0-13-064792-4", doi="",
         url="https://web1.eng.famu.fsu.edu/~palanki/design/lectures/Lecture18/lec18d.pdf",
         verificado="Ecuaciones leídas en el resumen de símbolos del curso ECH 4604 (FAMU-FSU, 2003) y ejemplo leído en las "
                    "láminas del capítulo 5 (slideshare.net/slideshow/chapter-5-17550956)"),
    dict(clave="turton2018", referencia="Turton, R., Shaeiwitz, J. A., Bhattacharyya, D. y Whiting, W. B. (2018). Analysis, Synthesis, "
                                        "and Design of Chemical Processes, 5.a ed. Prentice Hall, Boston. Apéndice A (Tablas A.1 a A.4 y "
                                        "sección A.3.1)",
         archivo="Turton_2018_AnalysisSynthesisDesign5ed.pdf", isbn="978-0-13-417740-3", doi="",
         url="https://github.com/weepctxb/ChemEngDPpy/blob/master/capex.py",
         verificado="Constantes B1, B2, FM y C1 a C3 tomadas de la transcripción ChemEngDPpy (capex.py), que cita la 5.a ed.; "
                    "cotejar con el Apéndice A del libro"),
    dict(clave="guthrie1969", referencia="Guthrie, K. M. (1969). Data and techniques for preliminary capital cost estimating. "
                                         "Chemical Engineering, 76(6), 114 a 142",
         archivo="Guthrie_1969_CapitalCostEstimating.pdf", isbn="", doi="",
         url="https://ocw.unican.es/pluginfile.php/2992/course/section/2870/topic_5.3.pdf",
         verificado="Factor de módulo de hornos de proceso (2,27 bajo 200.000 US$) leído en el apunte OCW de la Universidad de "
                    "Cantabria (Viguri y Cifrian, tema 5.3); volumen y páginas del artículo según la cita habitual, cotejar"),
    dict(clave="karberz", referencia="Kar, I. y Berz, M. Cost Estimation in Plant Construction. Vulkan Verlag, Essen. Tabla 4.1 (p. 20)",
         archivo="Kar_Berz_CostEstimation.pdf", isbn="978-3-8343-3495-4", doi="",
         url="https://www.autofachmann.de/media/pdf/20/02/38/Seiten-aus-Kar_Berz_CostEstimation_150dpi-RGB.pdf",
         verificado="Extracto del editor leído (13-11-2026): confirma los factores de Hand de columnas, intercambiadores, "
                    "recipientes, bombas, compresores, hornos e instrumentación; año de edición no informado en el extracto"),
    dict(clave="dea2026", referencia="Danish Energy Agency (2026). Technology Data for Industrial Process Heat, hoja 2.a "
                                     "(motor/costos.py)",
         archivo="", isbn="", doi="", url="", verificado="Fuente ya usada en la aplicación (PAT 123)"),
]
FUENTE = {f["clave"]: f for f in FUENTES_FACTORES}

LIT, LIT_T, SUP = "Literatura", "Literatura (transcrita; cotejar)", "Supuesto"

# ---------------------------------------------------------------- tipos de planta
TIPOS_PLANTA = {"solidos": "Planta de sólidos", "mixta": "Planta de sólidos y fluidos", "fluidos": "Planta de fluidos"}

# ---------------------------------------------------------------- Lang
# Factor × costo de los equipos = inversión de capital fijo (o total, según el juego elegido).
LANG = {
    "original": dict(nombre="Lang original (1947, 1948)", solidos=3.10, mixta=3.63, fluidos=4.74, categoria=LIT,
                     fuente="Lang (1947, 1948), factores originales sobre el costo de los equipos, según Brown (2006), Tabla 3.1, p. 49; "
                            "los mismos en Turton et al. (2003), 2.a ed., cap. 5"),
    "brown_nueva": dict(nombre="Brown, planta nueva en sitio nuevo", solidos=3.2, mixta=3.5, fluidos=4.5, categoria=LIT,
                        fuente="Brown (2006), Tabla 3.1, p. 49, columna planta nueva en sitio nuevo"),
    "ptw_capital_fijo": dict(nombre="Peters y Timmerhaus, capital fijo", solidos=3.9, mixta=4.1, fluidos=4.8, categoria=LIT,
                             fuente="Peters y Timmerhaus (1991), 4.a ed., Tabla 18, p. 184: inversión de capital fijo sobre el costo "
                                    "de los equipos entregados; incluye terreno y honorarios del contratista"),
    "ptw_capital_total": dict(nombre="Peters y Timmerhaus, capital total", solidos=4.6, mixta=4.9, fluidos=5.7, categoria=LIT,
                              fuente="Peters y Timmerhaus (1991), 4.a ed., Tabla 18, p. 184: inversión de capital total (con capital "
                                     "de trabajo) sobre el costo de los equipos entregados"),
}

# ---------------------------------------------------------------- Hand
# clase → (factor, nombre, fuente, categoría). Equipos de acero al carbono (Brown, 2006, Tabla 3.2).
_F_BROWN = "Hand (1958), según Brown (2006), Tabla 3.2, p. 50"
HAND = {
    "columna": (4.0, "Columnas de fraccionamiento", _F_BROWN, LIT),
    "recipiente": (4.0, "Recipientes a presión y estanques", _F_BROWN, LIT),
    "intercambiador": (3.5, "Intercambiadores de calor", _F_BROWN + "; también para placas de acero inoxidable", LIT),
    "horno": (2.0, "Hornos y calentadores a fuego directo", _F_BROWN, LIT),
    "bomba": (4.0, "Bombas", _F_BROWN, LIT),
    "compresor": (2.5, "Compresores", _F_BROWN, LIT),
    "instrumento": (4.0, "Instrumentos", _F_BROWN + "; 400 % en Kar y Berz, Tabla 4.1, p. 20", LIT),
    "otros": (2.5, "Otros equipos", _F_BROWN, LIT),
}

# ---------------------------------------------------------------- desglose por ítems (Peters y Timmerhaus, 1991, Tabla 17)
# (clave, nombre, % sólidos, % sólidos y fluidos, % fluidos, grupo) sobre el costo de los equipos entregados (= 100).
# La tabla corresponde a ampliaciones mayores de plantas en un sitio existente (encabezado de la Tabla 17).
_F_T17 = "Peters y Timmerhaus (1991), 4.a ed., Tabla 17, p. 183"
DESGLOSE_PTW = [
    ("instalacion", "Instalación de los equipos", 45, 39, 47, "directo"),
    ("instrumentacion", "Instrumentación y control (instalados)", 9, 13, 18, "directo"),
    ("canerias", "Cañerías (instaladas)", 16, 31, 66, "directo"),
    ("electrico", "Sistema eléctrico (instalado)", 10, 10, 11, "directo"),
    ("edificios", "Edificios (con sus servicios)", 25, 29, 18, "directo"),
    ("terreno_mejoras", "Mejoras del terreno", 13, 10, 10, "directo"),
    ("servicios", "Instalaciones de servicio (instaladas)", 40, 55, 70, "directo"),
    ("terreno", "Terreno (si se compra)", 6, 6, 6, "directo"),
    ("ingenieria", "Ingeniería y supervisión", 33, 32, 33, "indirecto"),
    ("construccion", "Gastos de construcción", 39, 34, 41, "indirecto"),
    ("contratista", "Honorarios del contratista (cerca de 5 % de los costos directos e indirectos)", 17, 18, 21, "indirecto"),
    ("contingencias", "Contingencias (cerca de 10 % de los costos directos e indirectos)", 34, 36, 42, "indirecto"),
]
CAPITAL_TRABAJO_PTW = dict(solidos=68, mixta=74, fluidos=86)     # Tabla 17: cerca de 15 % de la inversión de capital total

# ---------------------------------------------------------------- módulo desnudo (Guthrie, Turton)
F_TM = 1.18          # C_TM = 1,18·ΣC_BM: 15 % de contingencias y 3 % de honorarios (Turton et al., 2003, ec. 5.15)
F_GR = 0.50          # C_GR = C_TM + 0,50·ΣC_BM0: instalaciones auxiliares de una planta nueva (Turton et al., 2003, ec. 5.16)
FUENTE_TM = "Turton et al. (2003), 2.a ed., ec. 5.15 (C_TM = 1,18·ΣC_BM) y ec. 5.16 (C_GR = C_TM + 0,50·ΣC_BM0)"
MATERIALES = {"carbono": "Acero al carbono", "inoxidable": "Acero inoxidable"}
_F_T18 = "Turton et al. (2018), 5.a ed., Apéndice A, Tablas A.2 y A.4 y sección A.3.1, transcritas en ChemEngDPpy (capex.py)"
_F_EJ = ("Turton et al. (2003), 2.a ed., ejemplo ilustrativo del cap. 5 (intercambiador de tubo y carcasa de 100 m², 2001): "
         "Cp0 = 25 kUS$, C_BM0 = 82,3 kUS$, inoxidable a 1 bar 154 kUS$ y acero al carbono a 100 bar 98,1 kUS$")
# familia → B1, B2, FM por material, constantes de presión (C1, C2, C3, Pmín, Pmáx en barg) o None, fuente y categoría.
# Las familias «directas» tienen el F_BM tabulado (B2 = 0 o B1 = 0).
TURTON_BM = {
    "hx_tubo_carcasa": dict(nombre="Intercambiador de tubo y carcasa", B1=1.63, B2=1.66, FM=dict(carbono=1.0, inoxidable=2.73),
                            fp=(0.03881, -0.11272, 0.08183, 5.0, 140.0), categoria=LIT,
                            fuente=_F_EJ + "; de ahí B1 + B2 = 3,29 y FM inoxidable = 2,73. Constantes de presión: " + _F_T18),
    "hx_doble_tubo": dict(nombre="Intercambiador de doble tubo", B1=1.74, B2=1.55, FM=dict(carbono=1.0, inoxidable=2.73),
                          fp=(0.6072, -0.9120, 0.3327, 40.0, 100.0), categoria=LIT_T,
                          fuente=_F_T18 + "; FM del tubo y carcasa (ChemEngDPpy da 2,9 para inoxidable)"),
    "bomba_centrifuga": dict(nombre="Bomba centrífuga", B1=1.89, B2=1.35, FM=dict(carbono=1.6, inoxidable=2.3),
                             fp=(-0.3935, 0.3957, -0.00226, 10.0, 100.0), categoria=LIT_T,
                             fuente=_F_T18 + "; FM sobre hierro fundido = 1,0"),
    "recipiente_vertical": dict(nombre="Recipiente vertical", B1=2.25, B2=1.82, FM=dict(carbono=1.0, inoxidable=3.1), fp=None,
                                categoria=LIT_T, fuente=_F_T18 + "; FP = 1 a baja presión (Supuesto: la ecuación de presión de "
                                                                  "recipientes necesita el diámetro y el espesor)"),
    "compresor": dict(nombre="Compresor centrífugo", B1=0.0, B2=2.8, FM=dict(carbono=1.0, inoxidable=5.8 / 2.8), fp=None,
                      categoria=LIT_T, fuente=_F_T18 + ": F_BM = 2,8 en acero al carbono y 5,8 en inoxidable"),
    "horno": dict(nombre="Horno o caldera", B1=2.27, B2=0.0, FM=dict(carbono=1.0, inoxidable=1.0), fp=None, categoria=LIT_T,
                  fuente="Guthrie (1969), factor de módulo de hornos de proceso bajo 200.000 US$ (2,27), según el apunte OCW de la "
                         "Universidad de Cantabria, tema 5.3"),
    "maquinaria": dict(nombre="Maquinaria de proceso armada", B1=1.38, B2=0.0, FM=dict(carbono=1.0, inoxidable=1.0), fp=None,
                       categoria=SUP,
                       fuente="Supuesto: F_BM = 1,38 de los mezcladores de Turton (transcrito en ChemEngDPpy), usado para la "
                              "maquinaria de alimentos y de biomasa que se vende armada sobre su base y sin F_BM verificado; "
                              "cotejar con la tabla de factores directos del Apéndice A de Turton et al. (2018)"),
}

# ---------------------------------------------------------------- familias de los ítems de costeo (claves de motor/costeo.py)
# clave → (clase de Hand, familia de Turton, fase para el tipo de planta, nota de la asignación)
# fase: «fluido», «solido», «servicio» (no cuenta para el tipo de planta) o «granel» (cañerías y cable: ya en los factores).
_AS = "Asignación de T24 (Supuesto): "
FAMILIAS = {
    "intercambiador": ("intercambiador", "hx_tubo_carcasa", "fluido", ""),
    "bomba_centrifuga": ("bomba", "bomba_centrifuga", "fluido", ""),
    "caldera_gas": ("horno", "horno", "servicio", ""),
    "generador_biomasa": ("horno", "horno", "servicio", ""),
    "bomba_calor": ("compresor", "compresor", "servicio", _AS + "el costo de una bomba de calor lo domina su compresor"),
    "valvula_control": ("instrumento", "maquinaria", "servicio", _AS + "la válvula de control es parte de la instrumentación"),
    "caneria": (None, None, "granel", "Material a granel: incluido en los factores de cañerías"),
    "cable_electrico": (None, None, "granel", "Material a granel: incluido en los factores del sistema eléctrico"),
    "hot_break": ("intercambiador", "hx_tubo_carcasa", "fluido", _AS + "calentador tubular con recirculación"),
    "esterilizador": ("intercambiador", "hx_doble_tubo", "fluido", _AS + "esterilizador de tubo en tubo"),
    "evaporador_mvr": ("intercambiador", "hx_tubo_carcasa", "fluido", _AS + "el evaporador es un equipo de transferencia de calor"),
    "evaporador_multiefecto": ("intercambiador", "hx_tubo_carcasa", "fluido", _AS + "el evaporador es un equipo de transferencia de calor"),
    "enfriamiento_flash": ("recipiente", "recipiente_vertical", "fluido", _AS + "estanque de vacío vertical"),
    "refinadora": ("otros", "maquinaria", "fluido", _AS + "maquinaria que trabaja la pulpa"),
    "llenadora_aseptica": ("otros", "maquinaria", "fluido", _AS + "maquinaria que llena producto líquido"),
    "recepcion_tomate": ("otros", "maquinaria", "solido", ""),
    "lavado_seleccion": ("otros", "maquinaria", "solido", ""),
    "trituradora": ("otros", "maquinaria", "solido", ""),
    "recepcion_biomasa": ("otros", "maquinaria", "solido", ""),
    "secador_rotatorio": ("otros", "maquinaria", "solido", ""),
    "secador_banda": ("otros", "maquinaria", "solido", ""),
    "secador_lena": ("otros", "maquinaria", "solido", ""),
    "molino_martillos": ("otros", "maquinaria", "solido", ""),
    "astilladora": ("otros", "maquinaria", "solido", ""),
    "pelletizadora": ("otros", "maquinaria", "solido", ""),
    "enfriador_pellet": ("otros", "maquinaria", "solido", ""),
    "criba": ("otros", "maquinaria", "solido", ""),
    "sierra_lena": ("otros", "maquinaria", "solido", ""),
    "ensacado_acopio": ("otros", "maquinaria", "solido", ""),
    "generico": ("otros", "maquinaria", "solido", "Equipo sin referencia propia (Supuesto)"),
    # PAT 143 b: agar agar
    "recepcion_alga": ("otros", "maquinaria", "solido", ""),
    "estanque_lavado_alga": ("recipiente", "recipiente_vertical", "fluido", _AS + "estanque agitado"),
    "reactor_alcalino_agar": ("recipiente", "recipiente_vertical", "fluido", _AS + "estanque agitado con camisa"),
    "estanque_neutralizacion_agar": ("recipiente", "recipiente_vertical", "fluido", _AS + "estanque agitado"),
    "extractor_agar": ("recipiente", "recipiente_vertical", "fluido", _AS + "estanque agitado con camisa de vapor"),
    "filtro_prensa_agar": ("otros", "maquinaria", "fluido", _AS + "maquinaria que filtra el extracto líquido"),
    "enfriador_extracto_agar": ("intercambiador", "hx_tubo_carcasa", "fluido", _AS + "intercambiador de placas tratado como de tubo y carcasa"),
    "prensa_gel_agar": ("otros", "maquinaria", "solido", ""),
}
CLAVES_RECUPERACION = ("intercambiador", "bomba_calor")      # las mismas de recuperacion_usd en motor/costeo.py

# ---------------------------------------------------------------- operación: mantención y costos fijos (% del capital fijo)
# clave → (valor por defecto en %, rango (mín, máx) en %, base, fuente, categoría)
OM = {
    "mantencion": (6.0, (2.0, 11.0), "capital fijo",
                   "Peters y Timmerhaus (1991), 4.a ed., Tabla 25, p. 203: 2 a 6 % en procesos simples, 5 a 9 % en procesos "
                   "promedio y 7 a 11 % en procesos complejos, en promedio cerca de 6 %; Brown (2006), p. 81 y Tabla 4.8, p. 83: 2 a "
                   "10 %, 6 % para estudios; Smith (2005), sección 2.5, p. 28: cerca de 6 %", LIT),
    "suministros": (15.0, (10.0, 20.0), "mantención",
                    "Peters y Timmerhaus (1991), 4.a ed., p. 204: cerca de 15 % del costo de mantención y reparaciones "
                    "(rango 10 a 20 %: Supuesto alrededor del valor citado)", LIT),
    "seguros": (1.0, (0.4, 1.0), "capital fijo",
                "Peters y Timmerhaus (1991), 4.a ed., p. 205: cerca de 1 % de la inversión de capital fijo "
                "(mínimo del rango: Supuesto)", LIT),
    "impuestos": (1.0, (1.0, 4.0), "capital fijo",
                  "Peters y Timmerhaus (1991), 4.a ed., p. 205: 1 a 2 % en zonas menos pobladas y 2 a 4 % en zonas muy "
                  "pobladas; Supuesto: Curicó como zona menos poblada, extremo bajo", LIT),
}
OM_NOMBRES = dict(mantencion="Mantención y reparaciones", suministros="Suministros de operación", seguros="Seguros",
                  impuestos="Impuestos territoriales")
MANTENCION_PCT = OM["mantencion"][0]
MANTENCION_POR_PROCESO = {"simple": (2.0, 6.0), "promedio": (5.0, 9.0), "complejo": (7.0, 11.0)}   # Peters y Timmerhaus (1991), Tabla 25

# ---------------------------------------------------------------- métodos
METODOS = {
    "factor_unico": dict(nombre="Factor único", fuente="Factor 2,5 = 1/0,40, fracción de equipo de la Danish Energy Agency "
                                                       "(2026), hoja 2.a (motor/costos.py); Supuesto", categoria=SUP),
    "lang": dict(nombre="Lang (por tipo de planta)", fuente=LANG["original"]["fuente"], categoria=LIT),
    "hand": dict(nombre="Hand (por tipo de equipo)", fuente=_F_BROWN, categoria=LIT),
    "modulo_desnudo": dict(nombre="Módulo desnudo (Guthrie, Turton)", fuente=FUENTE_TM + "; F_BM = B1 + B2·FM·FP (ec. A.4)",
                           categoria=LIT),
    "desglose": dict(nombre="Desglose por ítems (Peters y Timmerhaus)", fuente=_F_T17, categoria=LIT),
}


def familia(clave: str) -> dict:
    """Clase de Hand, familia de Turton, fase y nota de un ítem de costeo (sin dato: «otros», maquinaria, sólido)."""
    h, t, fase, nota = FAMILIAS.get(clave, FAMILIAS["generico"])
    return dict(hand=h, turton=t, fase=fase, nota=nota)


def _clave(f: dict) -> str:
    """Clave de costeo de una fila (las filas de costeo.costear la traen; si no, se busca por el nombre del tipo)."""
    if f.get("clave"):
        return f["clave"]
    from .costeo import REFERENCIAS
    return next((k for k, r in REFERENCIAS.items() if r["nombre"] == f.get("tipo")), "generico")


def tipo_planta(filas: list[dict], tipo: str | None = None) -> dict:
    """Tipo de planta para Lang y el desglose. Con tipo dado, se respeta. Si no, regla de T24 (Supuesto): fracción del costo de
    equipos de fluidos sobre equipos de proceso (sin servicios ni granel) ≥ 0,7 → fluidos; ≤ 0,3 → sólidos; si no, mixta."""
    fl = so = 0.0
    for f in filas:
        fase = familia(_clave(f))["fase"]
        c = float(f.get("costo_usd") or 0.0)
        if fase == "fluido":
            fl += c
        elif fase == "solido":
            so += c
    frac = fl / (fl + so) if fl + so > 0 else None
    if tipo in TIPOS_PLANTA:
        return dict(tipo=tipo, nombre=TIPOS_PLANTA[tipo], frac_fluidos=frac, justificacion="Elegido por el usuario")
    if frac is None:
        t = "mixta"
    else:
        t = "fluidos" if frac >= 0.7 else ("solidos" if frac <= 0.3 else "mixta")
    j = ("Supuesto de T24: " + (f"{frac * 100:.0f} % del costo de los equipos de proceso maneja fluidos".replace(".", ",")
                                 if frac is not None else "sin equipos de proceso") +
         " (≥ 70 % fluidos, ≤ 30 % sólidos, entre ambos mixta)")
    return dict(tipo=t, nombre=TIPOS_PLANTA[t], frac_fluidos=frac, justificacion=j)


def factor_presion(familia_turton: str, P_barg: float = 0.0) -> tuple[float, str]:
    """FP de Turton: log10 FP = C1 + C2·log10 P + C3·(log10 P)², P en barg; bajo el rango, 1; sobre el rango, el del máximo."""
    fam = TURTON_BM.get(familia_turton)
    if fam is None or fam.get("fp") is None or not P_barg or P_barg <= 0:
        return 1.0, ""
    C1, C2, C3, lo, hi = fam["fp"]
    if P_barg < lo:
        return 1.0, f"{P_barg:g} barg bajo el rango de la correlación ({lo:g} barg): FP = 1".replace(".", ",")
    nota = ""
    P = P_barg
    if P > hi:
        P, nota = hi, f"{P_barg:g} barg sobre el rango ({hi:g} barg): FP del máximo".replace(".", ",")
    lp = math.log10(P)
    return max(1.0, 10 ** (C1 + C2 * lp + C3 * lp * lp)), nota


def f_bm(familia_turton: str, material: str = "inoxidable", P_barg: float = 0.0, precio_en_material: bool = True) -> dict:
    """F_BM = B1 + B2·FM·FP y su factor sobre el precio de la aplicación. Si el precio ya es del material elegido
    (precio_en_material), Cp0 = Cp/(FM·FP) y C_BM = Cp·(B1 + B2·FM·FP)/(FM·FP); si es de acero al carbono, C_BM = Cp·F_BM."""
    fam = TURTON_BM.get(familia_turton) or TURTON_BM["maquinaria"]
    FM = float(fam["FM"].get(material, fam["FM"].get("inoxidable", 1.0)))
    FP, nota = factor_presion(familia_turton, P_barg)
    F = fam["B1"] + fam["B2"] * FM * FP
    F0 = fam["B1"] + fam["B2"]
    if fam["B2"] == 0.0:                         # F_BM tabulado sin material ni presión
        FM, FP = 1.0, 1.0
    elif fam["B1"] == 0.0:                       # compresores: F_BM = B2·FM (Turton) con FM relativo al acero al carbono
        FP = 1.0; F = fam["B2"] * FM
    div = FM * FP if precio_en_material else 1.0
    return dict(familia=familia_turton, nombre=fam["nombre"], B1=fam["B1"], B2=fam["B2"], FM=FM, FP=FP, F_BM=F, F_BM0=F0,
                cp0_sobre_cp=1.0 / div, factor_sobre_precio=F / div, factor0_sobre_precio=F0 / div, fuente=fam["fuente"],
                categoria=fam["categoria"], nota=nota)


def _total(filas):
    return float(sum(float(f.get("costo_usd") or 0.0) for f in filas))


def aplicar(metodo: str, filas: list[dict], f_inst: float = costos.F_INSTALACION, tipo: str | None = None,
            lang_fuente: str = "original", material: str = "inoxidable", P_barg: float = 0.0, precio_en_material: bool = True,
            ampliacion: bool = False, incluir_terreno: bool = True, entrega_pct: float = 0.0) -> dict:
    """Inversión de la planta con el método elegido sobre las filas de costeo (costo_usd de cada equipo comprado).
    Devuelve base_usd (equipos que entran a la base), excluidos_usd (granel ya incluido en los factores), total_usd,
    factor_efectivo, recuperacion_usd (recuperadores con su parte de la inversión), desglose (ítems con su fuente) y
    por_equipo (factor e instalado de cada fila). entrega_pct: flete hasta la planta sobre el precio (Supuesto, 0 por defecto:
    los precios de la aplicación se toman como puestos en planta)."""
    if metodo not in METODOS:
        raise ValueError(f"Método de costeo desconocido: {metodo}")
    M = METODOS[metodo]
    avisos, desglose, por_eq = [], [], []
    tp = tipo_planta(filas, tipo)
    if metodo == "factor_unico":                 # exactamente lo de costeo.costear (base con cañerías y cable)
        base = _total(filas)
        rec = float(sum(float(f.get("costo_usd") or 0) for f in filas if _clave(f) in CLAVES_RECUPERACION))
        for f in filas:
            c = float(f.get("costo_usd") or 0)
            por_eq.append(dict(equipo=f.get("equipo"), nombre=f.get("nombre"), clave=_clave(f), costo_usd=c, factor=f_inst,
                               instalado_usd=c * f_inst, fuente=M["fuente"]))
        desglose = [dict(item="Equipos", porcentaje=100.0, usd=base, fuente="Costeo de la planta"),
                    dict(item=f"Instalación y resto de la planta (factor {f_inst:g} − 1)".replace(".", ","),
                         porcentaje=(f_inst - 1) * 100, usd=base * (f_inst - 1), fuente=M["fuente"])]
        return dict(metodo=metodo, nombre=M["nombre"], fuente=M["fuente"], categoria=M["categoria"], tipo_planta=tp,
                    base_usd=base, excluidos_usd=0.0, total_usd=base * f_inst, factor_efectivo=f_inst,
                    recuperacion_usd=rec * f_inst, desglose=desglose, por_equipo=por_eq, avisos=avisos)
    granel = [f for f in filas if familia(_clave(f))["fase"] == "granel"]
    equipos = [f for f in filas if familia(_clave(f))["fase"] != "granel"]
    excl = _total(granel)
    if granel:
        avisos.append("Cañerías y cable eléctrico de la lista (US$ " + f"{excl:,.0f}".replace(",", ".") + ") quedan fuera de la "
                      "base: el método ya los incluye en sus factores")
    ent = 1.0 + max(float(entrega_pct or 0.0), 0.0) / 100.0
    if entrega_pct:
        avisos.append(f"Flete hasta la planta de {entrega_pct:g} % sobre el precio (Supuesto del usuario)".replace(".", ","))
    base = _total(equipos) * ent
    k = tp["tipo"]
    if metodo in ("lang", "desglose"):
        if metodo == "lang":
            L = LANG.get(lang_fuente) or LANG["original"]
            fac = float(L[k]); fuente = L["fuente"]
            desglose = [dict(item="Equipos" + (" entregados" if entrega_pct else ""), porcentaje=100.0, usd=base, fuente="Costeo de la planta"),
                        dict(item=f"Resto de la planta ({tp['nombre'].lower()}, factor {fac:g})".replace(".", ","),
                             porcentaje=(fac - 1) * 100, usd=base * (fac - 1), fuente=fuente)]
        else:
            col = {"solidos": 2, "mixta": 3, "fluidos": 4}[k]
            fuente = _F_T17
            desglose = [dict(item="Equipos" + (" entregados" if entrega_pct else ""), porcentaje=100.0, usd=base, grupo="directo",
                             fuente="Costeo de la planta")]
            for fila in DESGLOSE_PTW:
                if fila[0] == "terreno" and not incluir_terreno:
                    continue
                p = float(fila[col])
                desglose.append(dict(item=fila[1], clave=fila[0], porcentaje=p, usd=base * p / 100, grupo=fila[5], fuente=_F_T17))
            fac = sum(d["porcentaje"] for d in desglose) / 100.0
            if not incluir_terreno:
                avisos.append("Sin terreno: se resta el 6 % de la Tabla 17")
        fac_precio = fac * ent
        for f in filas:
            c = float(f.get("costo_usd") or 0); g = familia(_clave(f))["fase"] == "granel"
            por_eq.append(dict(equipo=f.get("equipo"), nombre=f.get("nombre"), clave=_clave(f), costo_usd=c, factor=0.0 if g else fac_precio,
                               instalado_usd=0.0 if g else c * fac_precio, fuente=fuente))
        total = base * fac
    elif metodo == "hand":
        total = 0.0; por_clase = {}
        for f in filas:
            c = float(f.get("costo_usd") or 0); fam = familia(_clave(f))
            if fam["hand"] is None:
                por_eq.append(dict(equipo=f.get("equipo"), nombre=f.get("nombre"), clave=_clave(f), costo_usd=c, factor=0.0,
                                   instalado_usd=0.0, fuente=fam["nota"]))
                continue
            h = HAND[fam["hand"]]; inst = c * ent * h[0]; total += inst
            pc = por_clase.setdefault(fam["hand"], dict(item=h[1], factor=h[0], equipos_usd=0.0, usd=0.0, fuente=h[2]))
            pc["equipos_usd"] += c * ent; pc["usd"] += inst
            por_eq.append(dict(equipo=f.get("equipo"), nombre=f.get("nombre"), clave=_clave(f), costo_usd=c, factor=h[0] * ent,
                               instalado_usd=inst, clase=h[1], fuente=h[2] + (f". {fam['nota']}" if fam["nota"] else "")))
        desglose = sorted(por_clase.values(), key=lambda d: -d["usd"])
        avisos.append("Hand entrega el costo de la planta dentro de los límites de batería, con factores para equipos de acero "
                      "al carbono (Brown, 2006, Tabla 3.2); no incluye instalaciones fuera de esos límites")
    else:                                         # módulo desnudo
        s_bm = s_bm0 = 0.0; por_fam = {}
        for f in filas:
            c = float(f.get("costo_usd") or 0); fam = familia(_clave(f))
            if fam["turton"] is None:
                por_eq.append(dict(equipo=f.get("equipo"), nombre=f.get("nombre"), clave=_clave(f), costo_usd=c, factor=0.0,
                                   instalado_usd=0.0, fuente=fam["nota"]))
                continue
            b = f_bm(fam["turton"], material, P_barg, precio_en_material)
            cbm = c * ent * b["factor_sobre_precio"]; cbm0 = c * ent * b["factor0_sobre_precio"]
            s_bm += cbm; s_bm0 += cbm0
            inst = F_TM * cbm + (0.0 if ampliacion else F_GR * cbm0)
            pf = por_fam.setdefault(fam["turton"], dict(item=b["nombre"], F_BM=b["F_BM"], FM=b["FM"], FP=b["FP"],
                                                        factor=b["factor_sobre_precio"], equipos_usd=0.0, usd=0.0,
                                                        fuente=b["fuente"], categoria=b["categoria"]))
            pf["equipos_usd"] += c * ent; pf["usd"] += cbm
            if b["nota"]:
                avisos.append(f"{f.get('equipo')}: {b['nota']}")
            por_eq.append(dict(equipo=f.get("equipo"), nombre=f.get("nombre"), clave=_clave(f), costo_usd=c,
                               factor=inst / c if c else 0.0, instalado_usd=inst, F_BM=b["F_BM"], FM=b["FM"], FP=b["FP"],
                               C_BM=cbm, fuente=b["fuente"] + (f". {fam['nota']}" if fam["nota"] else "")))
        desglose = sorted(por_fam.values(), key=lambda d: -d["usd"])
        desglose.append(dict(item="Contingencias y honorarios (18 % de ΣC_BM)", factor=F_TM - 1, usd=(F_TM - 1) * s_bm, fuente=FUENTE_TM))
        if not ampliacion:
            desglose.append(dict(item="Instalaciones auxiliares de planta nueva (50 % de ΣC_BM0)", factor=F_GR, usd=F_GR * s_bm0,
                                 fuente=FUENTE_TM))
        total = F_TM * s_bm + (0.0 if ampliacion else F_GR * s_bm0)
        fuente = METODOS[metodo]["fuente"]
        avisos.append(f"Material {MATERIALES.get(material, material).lower()}; los precios "
                      + ("ya son de ese material (Cp0 = Cp/(FM·FP))" if precio_en_material else "se toman como de acero al carbono (Cp0 = Cp)"))
    rec = float(sum(p["instalado_usd"] for p in por_eq if p["clave"] in CLAVES_RECUPERACION))
    return dict(metodo=metodo, nombre=M["nombre"], fuente=M["fuente"], categoria=M["categoria"], tipo_planta=tp, base_usd=base,
                excluidos_usd=excl, total_usd=float(total), factor_efectivo=(total / base if base > 0 else 0.0),
                recuperacion_usd=rec, desglose=desglose, por_equipo=por_eq, avisos=avisos)


def operacion_fija(inversion: float, mantencion_pct: float | None = None, suministros_pct: float | None = None,
                   seguros_pct: float | None = None, impuestos_pct: float | None = None) -> dict:
    """Costos fijos anuales de operación sobre la inversión de capital fijo (en la misma moneda que la inversión):
    mantención, suministros (sobre la mantención), seguros e impuestos territoriales. Cada fila con su rango y fuente."""
    v = dict(mantencion=mantencion_pct, suministros=suministros_pct, seguros=seguros_pct, impuestos=impuestos_pct)
    inv = max(float(inversion or 0.0), 0.0)
    filas, mant = [], 0.0
    for k in ("mantencion", "suministros", "seguros", "impuestos"):
        d, rango, base_txt, fuente, cat = OM[k]
        pct = float(d if v[k] is None else v[k])
        base = mant if base_txt == "mantención" else inv
        monto = base * pct / 100.0
        if k == "mantencion":
            mant = monto
        fuera = not (rango[0] - 1e-9 <= pct <= rango[1] + 1e-9)
        filas.append(dict(clave=k, item=OM_NOMBRES[k], pct=pct, base=base_txt, rango=rango, monto=monto,
                          fuente=fuente if v[k] is None or abs(pct - d) < 1e-12 else
                          "Usuario (" + f"{pct:g}".replace(".", ",") + " %); literatura: " + fuente,
                          categoria=cat if v[k] is None or abs(pct - d) < 1e-12 else "Usuario", fuera_de_rango=fuera))
    return dict(filas=filas, mantencion=mant, total=float(sum(f["monto"] for f in filas)), inversion=inv)
