"""Catálogo de 10 tipos de planta y 10 tipos de demanda para la herramienta docente (PAT 136, tarea T20).

Responde a los puntos 2 y 3 de los comentarios del profesor Torres del 13-11-2026: «10 tipos de plantas y 10 tipos de
demandas», combinables, para que el docente reparta una combinación distinta a cada estudiante.

Cada tipo de planta trae:
- id, nombre, producto, materia prima, unidad en que se mide la producción y región de Chile donde existe el rubro.
- La cadena de operaciones unitarias en orden. Cada operación tiene su función de proceso (FUNCIONES), el tipo de equipo del
  registro (catalogos/registro.TIPOS) que la representa, el símbolo y la familia de la ISO 10628 con la letra código del
  Anexo D (se toman de simbolos/iso10628.SIMBOLOS para no repetirlos), y el estado del material que entra y que sale. Con
  eso otro equipo arma la precedencia (motor/precedencia.py) y la planta automática.
- Los servicios (vapor, gas, electricidad y agua), la demanda por defecto, una producción de referencia y sus referencias.

Los cuatro rubros que ya existen (tomate, pellet, chip y leña) se enlazan a su escenario (escenarios/<modulo>.crear) sin
cambiarlo y usan los mismos códigos de estado y los mismos tipos de equipo que la semilla de datos/mantenedor.py. PAT 143 b: el
agar agar tiene su escenario (escenarios/agar.py) con los equipos de catalogos/agar.py, que se declaran «equivalentes» de cada
operación (tienen la misma fila de precedencia, pero la planta automática sigue usando el tipo de la operación). Los otros cinco
no tienen escenario calculado todavía: crear_escenario() devuelve None y la interfaz muestra un aviso.

Los 10 tipos de demanda son los que define el equipo T21 en motor/demanda.py; aquí se guardan solo como texto (id, nombre y
lógica agrícola, de mercado o mixta), sin importar ese módulo. La compatibilidad planta × demanda tiene tres niveles:
2 = natural (la demanda propia del rubro), 1 = adaptable (tiene sentido con la justificación que se indica) y 0 = sin sentido.

Fuentes: lo que no tiene fuente segura va como «Supuesto» con su justificación. Las cadenas nuevas siguen los documentos
citados en REFERENCIAS cuando se pudieron revisar (13-11-2026); el resto es Supuesto del equipo T20 para revisar.
"""
from __future__ import annotations
import importlib

from ..simbolos import iso10628 as ISO

# ---------------------------------------------------------------------------------------------------------------- funciones
# PAT 136: funciones de proceso (taxonomía para el catálogo y la síntesis automática de la tarea T22)
FUNCIONES = {
    "recepcion": "Recepción y pesaje",
    "lavado": "Lavado y selección",
    "reduccion_tamano": "Reducción de tamaño",
    "separacion_solido_liquido": "Separación sólido-líquido",
    "separacion_mecanica": "Separación mecánica y clasificación",
    "tratamiento_termico": "Tratamiento térmico",
    "reaccion": "Reacción, extracción o fermentación",
    "concentracion": "Concentración por evaporación",
    "secado": "Secado",
    "enfriamiento": "Enfriamiento",
    "mezcla": "Mezcla y acondicionamiento",
    "conformado": "Conformado (pelletizado)",
    "transporte": "Transporte y manejo de materiales",
    "envasado": "Envasado, ensacado o despacho",
    "generacion_calor": "Generación de calor o vapor (servicio)",
}

# Símbolo ISO 10628 de cada tipo de equipo con modelo propio (el mismo atributo «simbolo» de su clase en catalogos/).
# Los tipos genéricos «iso_<símbolo>» se resuelven solos. La prueba test_genericos revisa que coincidan con registro.TIPOS.
SIMBOLO_PROPIO = {
    "alimentacion_tomate": "tolva", "recepcion_seleccion": "criba", "trituradora": "trituradora", "hot_break": "intercambiador_tubular",
    "refinadora": "tamiz", "evaporador_mvr": "evaporador_mvr", "evaporador_multiefecto": "evaporador_multiefecto",
    "esterilizador": "intercambiador_tubular", "enfriamiento_flash": "recipiente", "llenadora_aseptica": "maquina_acabado",
    "alimentacion_biomasa": "tolva", "secador_biomasa": "secador_tambor", "secador_banda": "secador_banda", "secador_lena": "secador",
    "astilladora": "astilladora", "molino_martillos": "molino_martillos", "pelletizadora": "pelletizadora",
    "enfriador_pellet": "enfriador_contracorriente", "criba_biomasa": "criba", "sierra_lena": "sierra",
    "despacho_biomasa": "maquina_acabado", "caldera_gas": "caldera", "caldera_biomasa": "horno",
    # PAT 143 b: equipos del agar agar (catalogos/agar.py)
    "alimentacion_alga": "tolva", "lavado_alga": "recipiente_agitado", "tratamiento_alcalino_agar": "reactor",
    "lavado_neutralizacion_agar": "recipiente_agitado", "extractor_agar": "camisa", "filtro_prensa_agar": "filtro_prensa",
    "gelificador_agar": "intercambiador_placas", "prensa_gel_agar": "filtro", "secador_agar": "secador_banda",
    "molino_agar": "molino_martillos", "envasado_agar": "maquina_acabado",
}

LOGICAS = {"agricola": "Empujada por la oferta agrícola o de la materia prima",
           "mercado": "Tirada por el mercado",
           "mixta": "Mixta: oferta de materia prima y mercado a la vez"}
NIVELES = {2: "Natural", 1: "Adaptable", 0: "Sin sentido"}
SERVICIOS = ("vapor", "gas", "electricidad", "agua")


def simbolo_de(tipo_equipo: str) -> str:
    """Símbolo ISO 10628 del tipo de equipo («iso_bomba» → «bomba»; los propios, según SIMBOLO_PROPIO)."""
    if tipo_equipo.startswith("iso_"):
        return tipo_equipo[4:]
    return SIMBOLO_PROPIO.get(tipo_equipo, "equipo_general")


def familia_de(tipo_equipo: str) -> tuple[int, str, str]:
    """(categoría de la Tabla C.1, nombre de la familia, letra código del Anexo D) del tipo de equipo."""
    _nom, cat, letra, _dib = ISO.SIMBOLOS.get(simbolo_de(tipo_equipo), ISO.SIMBOLOS["equipo_general"])
    return cat, ISO.CATEGORIAS.get(cat, ""), letra


# ---------------------------------------------------------------------------------------------------------------- referencias
REFERENCIAS = {
    "agrozzi": "Planta basada en Agrozzi (escenarios/agrozzi.py): DIA 2025 y su Adenda (expediente SEIA), fabricante de los evaporadores (CFT) y Modelo_PAT_Agrozzi_v2.xlsx",
    "pellet": "escenarios/pellet.py: Thek y Obernberger (2009, Tabla I), planta tipo de 5 t/h de pellet; parámetros de catalogos/biomasa.py",
    "chip": "escenarios/chip.py: humedad de rollizos de Visser et al. (2014); parámetros de catalogos/biomasa.py",
    "lena": "escenarios/lena.py: leña seca según la NCh2907; parámetros de catalogos/biomasa.py",
    "mantenedor": "datos/mantenedor.py (PAT 135): estados del material y precedencia de los cuatro rubros, Supuesto del orden de la línea de cada escenario",
    "agar": ("escenarios/agar.py (PAT 143 b): 602 t de agar al año en 330 días de 24 h; parámetros con fuente en catalogos/agar.py "
             "(McHugh, 2003; Armisen y Galatas, 1987; Belattmania et al., 2021; Correa Rivas, 2020; Escalante y Noriega, 2019)"),
    "mchugh": ("McHugh, D. J. (2003). A guide to the seaweed industry. FAO Fisheries Technical Paper 441, sección 3.1.1 «Food grade agar». "
               "https://www.fao.org/4/y4765e/y4765e06.htm (consulta 13-11-2026): lavado, tratamiento alcalino de Gracilaria con NaOH al "
               "2 a 5 % a 85 a 90 °C por cerca de 1 h, extracción con agua a 95 a 100 °C por 2 a 4 h, filtración con filtro prensa, gel de "
               "cerca de 1 % de agar, prensado del gel (sinéresis) hasta cerca de 20 % de agar, secado con aire caliente y molienda a 80 a 100 mesh"),
    "fao_harina": ("FAO (1986). The production of fish meal and oil. FAO Fisheries Technical Paper 142, secciones 3.1.1 a 3.1.8 y 3.2.1. "
                   "https://www.fao.org/3/X6899E/X6899E00.htm (consulta 13-11-2026): cocción, prensado, separación del licor de prensa, "
                   "pulido del aceite, evaporación del agua de cola, secado y molienda"),
    "tetrapak": ("Tetra Pak. Dairy Processing Handbook, capítulo 19 «Milk and whey powder». "
                 "https://dairyprocessinghandbook.tetrapak.com/chapter/milk-and-whey-powder (consulta 13-11-2026): estandarización, "
                 "pasteurización de la leche para leche entera en polvo a 75 °C por 15 s, evaporación, homogeneización del concentrado de "
                 "leche entera, secado por pulverización y lecho fluido, tamizado"),
    "alfalaval": ("Supuesto por revisar: cadena típica de jugo concentrado de manzana (molienda, prensado, despectinizado enzimático, "
                  "ultrafiltración, evaporación con recuperación de aromas). Documento sugerido para contrastarla, no revisado por el "
                  "equipo T20: Alfa Laval, folleto «Juicy apples», https://www.alfalaval.ca/globalassets/documents/industries/"
                  "food-dairy-and-beverage/beverage/fruits-and-vegetable-processing/juicy-apples.pdf"),
    "sup_ciruela": ("Supuesto del equipo T20: cadena típica de ciruela deshidratada (recepción, lavado, secado en túnel de aire caliente, "
                    "calibrado, hidratación y pasteurización con vapor, envasado). No hay documento revisado en la carpeta del proyecto"),
    "sup_vino": ("Supuesto del equipo T20: cadena típica de vino a granel (despalillado y molienda, fermentación alcohólica, descube y "
                 "prensado, maloláctica en tintos, clarificación, estabilización tartárica en frío, despacho en estanques o *flexitank*). "
                 "No hay documento revisado en la carpeta del proyecto"),
    "sup_produccion": ("Supuesto didáctico (PAT 136): orden de magnitud de una planta mediana del rubro, para que el estudiante tenga un "
                       "tamaño de partida; no es el dato de una planta real y se reemplaza con la demanda que asigne el docente"),
    "demanda_t21": "Tipos de demanda definidos por el equipo T21 en motor/demanda.py (PAT 136)",
    "sup_compat": ("Supuesto del equipo T20 (PAT 136): criterio de ingeniería sobre si la lógica de la demanda corresponde a la materia "
                   "prima, a la perecibilidad y al mercado del producto; el docente la cambia en la base"),
}


# ---------------------------------------------------------------------------------------------------------------- plantas
def _op(codigo, nombre, funcion, tipo, entrada, salida, opcional=False, servicios=(), nota="", alternativas=(), rama="",
        equivalentes=()):
    """Operación unitaria. entrada: código de estado, tupla de códigos o "" (la primera). servicios: claves de SERVICIOS.
    equivalentes (PAT 143 b): tipos con modelo propio que hacen la misma operación en el escenario del rubro; llevan la misma fila
    de precedencia, pero la planta automática no los compara como alternativas."""
    return dict(codigo=codigo, nombre=nombre, funcion=funcion, tipo_equipo=tipo,
                entrada=tuple(entrada) if isinstance(entrada, (tuple, list)) else ((entrada,) if entrada else ()),
                salida=salida, opcional=bool(opcional), servicios=tuple(servicios), nota=nota,
                alternativas=tuple(alternativas), rama=rama, equivalentes=tuple(equivalentes))


def _srv(vapor="", gas="", electricidad="", agua=""):
    """Servicios de la planta: {servicio: {usa, uso}}. Texto vacío = no lo usa."""
    return {k: dict(usa=bool(v), uso=v) for k, v in (("vapor", vapor), ("gas", gas), ("electricidad", electricidad), ("agua", agua))}


_APROX = "Tipo de equipo aproximado: el registro no tiene todavía uno propio para este producto (se usa el más parecido)"

_PLANTAS = [
    dict(id="tomate", nombre="Pasta de tomate", producto="Pasta de tomate concentrada (30 °Brix) en envase aséptico",
         materia_prima="Tomate industrial fresco", unidad="t de tomate fresco procesado por temporada", region="Maule (Teno)",
         rubro="tomate", escenario="agrozzi", demanda_defecto="agricola_tomate",
         produccion=dict(valor=450000.0, unidad="t de tomate por temporada de 76 días", fuente=REFERENCIAS["agrozzi"]),
         servicios=_srv(vapor="Hot break, evaporador de múltiple efecto y esterilizador (calderas a gas natural)",
                        gas="Calderas de vapor", electricidad="Compresores de los evaporadores MVR, bombas y motores",
                        agua="Lavado del tomate, condensado y enfriamiento"),
         referencias=("agrozzi", "mantenedor"),
         operaciones=[
             _op("recepcion", "Recepción de tomate", "recepcion", "alimentacion_tomate", "", "tomate_fresco"),
             _op("lavado", "Lavado y selección", "lavado", "recepcion_seleccion", "tomate_fresco", "tomate_lavado", servicios=("agua",)),
             _op("trituracion", "Trituración", "reduccion_tamano", "trituradora", "tomate_lavado", "tomate_triturado", servicios=("electricidad",)),
             _op("hot_break", "Calentamiento de inactivación enzimática (*hot break*)", "tratamiento_termico", "hot_break",
                 "tomate_triturado", "jugo_caliente", servicios=("vapor",)),
             _op("refinado", "Extracción y refinado", "separacion_mecanica", "refinadora", "jugo_caliente", "jugo_refinado", servicios=("electricidad",)),
             _op("evaporacion_mvr", "Preconcentración en evaporadores MVR (dos en serie)", "concentracion", "evaporador_mvr",
                 ("jugo_refinado", "pasta_concentrada"), "pasta_concentrada", servicios=("electricidad",)),
             _op("evaporacion_tvr", "Concentración final en evaporador de múltiple efecto (TVR)", "concentracion", "evaporador_multiefecto",
                 ("jugo_refinado", "pasta_concentrada"), "pasta_concentrada", servicios=("vapor", "agua")),
             _op("esterilizacion", "Esterilización", "tratamiento_termico", "esterilizador", "pasta_concentrada", "pasta_esteril", servicios=("vapor",)),
             _op("enfriamiento", "Enfriamiento *flash* al vacío", "enfriamiento", "enfriamiento_flash", "pasta_esteril", "pasta_enfriada",
                 opcional=True, nota="Opcional según la semilla del mantenedor: el esterilizador puede enfriar en su propia sección"),
             _op("llenado", "Llenado aséptico", "envasado", "llenadora_aseptica", "pasta_enfriada", "pasta_envasada"),
         ],
         equipos_servicio=("caldera_gas",)),
    dict(id="pellet", nombre="Pellet de madera", producto="Pellet de madera ENplus A1 (ISO 17225-2) ensacado",
         materia_prima="Aserrín verde de pino radiata", unidad="t de pellet al año", region="Biobío y Ñuble",
         rubro="pellet", escenario="pellet", demanda_defecto="mercado_estacional_invierno",
         produccion=dict(valor=39600.0, unidad="t de pellet al año (5 t/h, 24 h, 330 días)", fuente=REFERENCIAS["pellet"]),
         servicios=_srv(electricidad="Molino, pelletizadora (113,9 kWh/t en la planta tipo de Thek y Obernberger, 2009) y ventiladores",
                        agua="Acondicionamiento del aserrín molido, cuando se usa"),
         referencias=("pellet", "mantenedor"),
         operaciones=[
             _op("recepcion", "Recepción de aserrín verde", "recepcion", "alimentacion_biomasa", "", "biomasa_humeda"),
             _op("secado", "Secado en tambor rotatorio", "secado", "secador_biomasa", "biomasa_humeda", "biomasa_seca",
                 alternativas=("secador_banda", "secador_lena")),
             _op("molienda", "Molienda", "reduccion_tamano", "molino_martillos", "biomasa_seca", "biomasa_molida", servicios=("electricidad",)),
             _op("pelletizado", "Pelletizado", "conformado", "pelletizadora", "biomasa_molida", "pellet_caliente", servicios=("electricidad",)),
             _op("enfriamiento", "Enfriamiento en contracorriente", "enfriamiento", "enfriador_pellet", "pellet_caliente", "pellet_enfriado",
                 servicios=("electricidad",)),
             _op("cribado", "Cribado de finos", "separacion_mecanica", "criba_biomasa", "pellet_enfriado", "pellet_cribado", opcional=True),
             _op("ensacado", "Ensacado", "envasado", "despacho_biomasa", "pellet_cribado", "pellet_ensacado"),
         ],
         equipos_servicio=("caldera_biomasa",)),
    dict(id="chip", nombre="Chip de madera", producto="Astilla seca (ISO 17225-4, clase M25) a granel",
         materia_prima="Rollizos verdes de pino radiata", unidad="t de chip seco al año", region="Biobío, Ñuble y La Araucanía",
         rubro="chip", escenario="chip", demanda_defecto="mercado_constante",
         produccion=dict(valor=48000.0, unidad="t de chip seco al año (10 t/h, 16 h, 300 días)", fuente=REFERENCIAS["chip"]),
         servicios=_srv(electricidad="Astilladora, criba, ventiladores del secador y cintas"),
         referencias=("chip", "mantenedor"),
         operaciones=[
             _op("recepcion", "Recepción de rollizos", "recepcion", "alimentacion_biomasa", "", "rollizo_verde"),
             _op("astillado", "Astillado", "reduccion_tamano", "astilladora", "rollizo_verde", "astilla_verde", servicios=("electricidad",)),
             _op("cribado", "Cribado de astillas", "separacion_mecanica", "criba_biomasa", "astilla_verde", "astilla_cribada", opcional=True),
             _op("secado", "Secado en secador de banda", "secado", "secador_banda", "astilla_cribada", "astilla_seca",
                 alternativas=("secador_biomasa", "secador_lena")),
             _op("acopio", "Acopio y despacho", "envasado", "despacho_biomasa", "astilla_seca", "chip_acopiado"),
         ],
         equipos_servicio=("caldera_biomasa",)),
    dict(id="lena", nombre="Leña seca", producto="Leña seca de eucalipto (NCh2907) trozada y partida",
         materia_prima="Trozas verdes de eucalipto", unidad="t de leña seca al año", region="Maule, Biobío y La Araucanía",
         rubro="lena", escenario="lena", demanda_defecto="mercado_estacional_invierno",
         produccion=dict(valor=14400.0, unidad="t de leña seca al año (2 t/h, 24 h, 300 días)", fuente=REFERENCIAS["lena"]),
         servicios=_srv(electricidad="Procesadora de leña y ventiladores del secador"),
         referencias=("lena", "mantenedor"),
         operaciones=[
             _op("recepcion", "Recepción de trozas", "recepcion", "alimentacion_biomasa", "", "trozas_verdes"),
             _op("trozado", "Trozado y partido", "reduccion_tamano", "sierra_lena", "trozas_verdes", "lena_partida", servicios=("electricidad",)),
             _op("secado", "Secado en cámara", "secado", "secador_lena", "lena_partida", "lena_seca", opcional=True,
                 nota="Opcional según la semilla del mantenedor: la leña también se seca al aire en el acopio",
                 alternativas=("secador_biomasa", "secador_banda")),
             _op("acopio", "Acopio y despacho", "envasado", "despacho_biomasa", "lena_seca", "lena_acopiada"),
         ],
         equipos_servicio=("caldera_biomasa",)),
    # ------------------------------------------------------------------------------------------------ rubros nuevos (PAT 136)
    dict(id="agar", nombre="Agar agar", producto="Agar agar en polvo, grado alimentario",
         materia_prima="Alga roja Gracilaria seca", unidad="t de agar al año", region="Los Lagos y Biobío",
         rubro="agar", escenario="agar", demanda_defecto="mercado_agar",
         produccion=dict(valor=602.0, unidad="t de agar al año",
                         fuente="Supuesto ilustrativo del desafío de ejemplo de datos/mantenedor.py (desafio_agar, 602 t al año con peak en invierno)"),
         servicios=_srv(vapor="Tratamiento alcalino y extracción con agua caliente", gas="Caldera y aire caliente del secador",
                        electricidad="Agitadores, filtro prensa, prensa del gel, molino y ventiladores",
                        agua="Lavado del alga, extracción y enfriamiento del gel"),
         referencias=("mchugh", "agar"),
         estados=[("alga_seca", "alga seca recibida", "recepción"), ("alga_lavada", "alga lavada", "lavado"),
                  ("alga_tratada", "alga tratada con álcali", "tratamiento alcalino"), ("extracto_caliente", "extracto caliente de agar", "extracción"),
                  ("extracto_filtrado", "extracto filtrado", "filtración"), ("gel_agar", "gel de agar", "gelificación"),
                  ("gel_prensado", "gel prensado", "prensado del gel"), ("agar_seco", "agar seco en escamas", "secado"),
                  ("agar_molido", "agar en polvo", "molienda"), ("agar_envasado", "agar envasado", "envasado")],
         operaciones=[
             _op("recepcion", "Recepción y pesaje del alga", "recepcion", "iso_bascula", "", "alga_seca", equivalentes=("alimentacion_alga",)),
             _op("lavado", "Lavado del alga", "lavado", "iso_recipiente_agitado", "alga_seca", "alga_lavada", servicios=("agua", "electricidad"),
                 equivalentes=("lavado_alga",)),
             _op("alcali", "Tratamiento alcalino (NaOH al 2 a 5 %, 85 a 90 °C, cerca de 1 h)", "reaccion", "iso_reactor", "alga_lavada", "alga_tratada",
                 servicios=("vapor", "agua"), equivalentes=("tratamiento_alcalino_agar",)),
             _op("extraccion", "Extracción con agua caliente (95 a 100 °C, 2 a 4 h)", "reaccion", "iso_camisa", "alga_tratada", "extracto_caliente",
                 servicios=("vapor", "agua"), equivalentes=("extractor_agar",),
                 nota="En el escenario base el alga pasa antes por el lavado y neutralización, que no cambia su estado (no lleva fila de precedencia)"),
             _op("filtracion", "Filtración en caliente con filtro prensa", "separacion_solido_liquido", "iso_filtro_prensa", "extracto_caliente",
                 "extracto_filtrado", servicios=("electricidad",), equivalentes=("filtro_prensa_agar",)),
             _op("gelificacion", "Enfriamiento y gelificación", "enfriamiento", "iso_intercambiador_placas", "extracto_filtrado", "gel_agar",
                 servicios=("agua",), equivalentes=("gelificador_agar",)),
             _op("prensado", "Prensado del gel (sinéresis)", "separacion_solido_liquido", "iso_filtro", "gel_agar", "gel_prensado",
                 servicios=("electricidad",), nota="McHugh (2003) describe también el congelado y descongelado como alternativa",
                 equivalentes=("prensa_gel_agar",)),
             _op("secado", "Secado con aire caliente", "secado", "secador_banda", "gel_prensado", "agar_seco", servicios=("gas", "electricidad"),
                 nota=_APROX + ": el secador de banda de catalogos/biomasa.py", equivalentes=("secador_agar",)),
             _op("molienda", "Molienda a 80 a 100 mesh", "reduccion_tamano", "iso_molino_bolas", "agar_seco", "agar_molido", servicios=("electricidad",),
                 equivalentes=("molino_agar",)),
             _op("envasado", "Envasado del polvo", "envasado", "iso_dosificador_rotativo", "agar_molido", "agar_envasado",
                 equivalentes=("envasado_agar",)),
         ],
         equipos_servicio=("caldera_gas",)),
    dict(id="jugo_manzana", nombre="Jugo concentrado de manzana", producto="Jugo concentrado clarificado de manzana (cerca de 70 °Brix) en tambores asépticos",
         materia_prima="Manzana de calidad industrial (descarte de exportación)", unidad="t de manzana procesada por temporada",
         region="Maule (Curicó y Talca) y O'Higgins", rubro="jugo_manzana", escenario=None, demanda_defecto="agricola_fruta",
         produccion=dict(valor=60000.0, unidad="t de manzana por temporada", fuente=REFERENCIAS["sup_produccion"]),
         servicios=_srv(vapor="Evaporador con recuperación de aromas y pasteurización", gas="Calderas de vapor",
                        electricidad="Molino, prensas, ultrafiltración y bombas", agua="Lavado de la fruta, limpieza y enfriamiento"),
         referencias=("alfalaval",),
         estados=[("manzana_fresca", "manzana fresca", "recepción"), ("manzana_lavada", "manzana lavada y seleccionada", "lavado"),
                  ("pulpa_manzana", "pulpa de manzana molida", "molienda"), ("jugo_crudo", "jugo crudo", "prensado"),
                  ("jugo_despectinizado", "jugo despectinizado", "tratamiento enzimático"), ("jugo_clarificado", "jugo clarificado", "ultrafiltración"),
                  ("jugo_concentrado", "jugo concentrado", "evaporación"), ("concentrado_frio", "concentrado pasteurizado y frío", "pasteurización y enfriamiento"),
                  ("concentrado_envasado", "concentrado envasado", "llenado aséptico")],
         operaciones=[
             _op("recepcion", "Recepción y pesaje de la fruta", "recepcion", "iso_bascula", "", "manzana_fresca"),
             _op("lavado", "Lavado por flotación y selección", "lavado", "iso_deposito", "manzana_fresca", "manzana_lavada", servicios=("agua",)),
             _op("molienda", "Molienda", "reduccion_tamano", "trituradora", "manzana_lavada", "pulpa_manzana", servicios=("electricidad",)),
             _op("prensado", "Prensado de la pulpa", "separacion_solido_liquido", "iso_filtro_prensa", "pulpa_manzana", "jugo_crudo",
                 servicios=("electricidad",)),
             _op("enzimatico", "Despectinizado enzimático", "reaccion", "iso_recipiente_agitado", "jugo_crudo", "jugo_despectinizado",
                 servicios=("vapor", "electricidad")),
             _op("ultrafiltracion", "Clarificación por ultrafiltración", "separacion_solido_liquido", "iso_filtro", "jugo_despectinizado",
                 "jugo_clarificado", servicios=("electricidad",)),
             _op("evaporacion", "Evaporación con recuperación de aromas", "concentracion", "evaporador_multiefecto", "jugo_clarificado",
                 "jugo_concentrado", servicios=("vapor", "agua"), alternativas=("evaporador_mvr",)),
             _op("pasteurizacion", "Pasteurización y enfriamiento del concentrado", "tratamiento_termico", "iso_intercambiador_placas",
                 "jugo_concentrado", "concentrado_frio", servicios=("vapor", "agua")),
             _op("llenado", "Llenado aséptico en tambores", "envasado", "llenadora_aseptica", "concentrado_frio", "concentrado_envasado",
                 nota=_APROX + ": la llenadora aséptica de catalogos/tomate.py"),
         ],
         equipos_servicio=("caldera_gas",)),
    dict(id="leche_polvo", nombre="Leche en polvo", producto="Leche entera en polvo en sacos multicapa",
         materia_prima="Leche cruda de vaca", unidad="m³ de leche recibida al año", region="Los Ríos y Los Lagos",
         rubro="leche_polvo", escenario=None, demanda_defecto="mixta_oferta_mercado",
         produccion=dict(valor=150000.0, unidad="m³ de leche al año", fuente=REFERENCIAS["sup_produccion"]),
         servicios=_srv(vapor="Pasteurización, evaporador y calentamiento del aire de secado", gas="Calderas y quemadores del aire de secado",
                        electricidad="Compresor MVR, homogeneizador, ventiladores del secador", agua="Limpieza en sitio (CIP) y enfriamiento"),
         referencias=("tetrapak",),
         estados=[("leche_cruda", "leche cruda", "recepción"), ("leche_estandarizada", "leche estandarizada", "estandarización"),
                  ("leche_pasteurizada", "leche pasteurizada", "pasteurización"), ("leche_concentrada", "leche concentrada", "evaporación"),
                  ("concentrado_homogeneizado", "concentrado homogeneizado", "homogeneización"), ("polvo_humedo", "polvo a la salida de la cámara", "secado por pulverización"),
                  ("leche_polvo", "leche en polvo", "lecho fluido y separación"), ("leche_polvo_envasada", "leche en polvo envasada", "envasado")],
         operaciones=[
             _op("recepcion", "Recepción en estanques silo", "recepcion", "iso_deposito", "", "leche_cruda", servicios=("agua",)),
             _op("estandarizacion", "Estandarización por centrifugación", "separacion_mecanica", "iso_centrifuga", "leche_cruda", "leche_estandarizada",
                 servicios=("electricidad",)),
             _op("pasteurizacion", "Pasteurización (75 °C por 15 s en leche entera)", "tratamiento_termico", "iso_intercambiador_placas",
                 "leche_estandarizada", "leche_pasteurizada", servicios=("vapor", "agua")),
             _op("evaporacion", "Evaporación", "concentracion", "evaporador_mvr", "leche_pasteurizada", "leche_concentrada",
                 servicios=("electricidad", "vapor"), alternativas=("evaporador_multiefecto",)),
             _op("homogeneizacion", "Homogeneización del concentrado", "mezcla", "iso_bomba_desplazamiento", "leche_concentrada",
                 "concentrado_homogeneizado", opcional=True, servicios=("electricidad",),
                 nota="Solo en leche entera (Tetra Pak, cap. 19); el homogeneizador es una bomba de pistones a alta presión"),
             _op("secado", "Secado por pulverización", "secado", "iso_secador_pulverizacion", "concentrado_homogeneizado", "polvo_humedo",
                 servicios=("vapor", "gas", "electricidad")),
             _op("lecho_fluido", "Secado final y enfriamiento en lecho fluido, con ciclones", "separacion_mecanica", "iso_ciclon", "polvo_humedo",
                 "leche_polvo", servicios=("electricidad",), nota=_APROX + ": el registro no tiene lecho fluido; se usa el ciclón"),
             _op("envasado", "Tamizado y envasado en sacos", "envasado", "iso_dosificador_rotativo", "leche_polvo", "leche_polvo_envasada"),
         ],
         equipos_servicio=("caldera_gas",)),
    dict(id="harina_pescado", nombre="Harina y aceite de pescado", producto="Harina de pescado (y aceite como coproducto)",
         materia_prima="Pescado pelágico entero (jurel, anchoveta, sardina) o desechos de planta", unidad="t de pescado procesado al año",
         region="Biobío (Coronel y Talcahuano), Arica y Parinacota, Antofagasta", rubro="harina_pescado", escenario=None,
         demanda_defecto="contrato_industrial",
         produccion=dict(valor=120000.0, unidad="t de pescado al año", fuente=REFERENCIAS["sup_produccion"]),
         servicios=_srv(vapor="Cocedor, evaporador de agua de cola y secador", gas="Calderas de vapor (o petróleo)",
                        electricidad="Prensa, decantador, centrífugas y molino", agua="Condensadores y limpieza"),
         referencias=("fao_harina",),
         estados=[("pescado_fresco", "pescado fresco", "recepción"), ("pescado_cocido", "pescado cocido", "cocción"),
                  ("torta_prensa", "torta de prensa", "prensado"), ("licor_prensa", "licor de prensa", "prensado (rama del licor)"),
                  ("agua_cola", "agua de cola con aceite", "decantación"), ("agua_cola_desaceitada", "agua de cola sin aceite", "centrifugación"),
                  ("agua_cola_concentrada", "agua de cola concentrada", "evaporación"), ("torta_integral", "torta integral", "mezcla"),
                  ("harina_seca", "harina seca", "secado"), ("harina_molida", "harina molida", "molienda"), ("harina_ensacada", "harina ensacada", "ensacado")],
         operaciones=[
             _op("recepcion", "Recepción y pesaje del pescado", "recepcion", "iso_bascula", "", "pescado_fresco"),
             _op("coccion", "Cocción en cocedor con camisa de vapor", "tratamiento_termico", "iso_camisa", "pescado_fresco", "pescado_cocido",
                 servicios=("vapor",)),
             _op("prensado", "Prensado (sale la torta y el licor de prensa)", "separacion_solido_liquido", "iso_filtro_prensa", "pescado_cocido",
                 "torta_prensa", servicios=("electricidad",)),
             _op("decantacion", "Separación de sólidos del licor de prensa", "separacion_solido_liquido", "iso_decantador", "licor_prensa",
                 "agua_cola", servicios=("electricidad",), rama="licor de prensa"),
             _op("centrifugacion", "Separación y pulido del aceite", "separacion_mecanica", "iso_centrifuga", "agua_cola", "agua_cola_desaceitada",
                 servicios=("electricidad",), rama="licor de prensa", nota="El aceite de pescado sale como coproducto"),
             _op("evaporacion", "Evaporación del agua de cola", "concentracion", "evaporador_multiefecto", "agua_cola_desaceitada",
                 "agua_cola_concentrada", servicios=("vapor", "agua"), rama="licor de prensa"),
             _op("mezcla", "Mezcla de la torta con el concentrado", "mezcla", "iso_mezclador", ("torta_prensa", "agua_cola_concentrada"),
                 "torta_integral", servicios=("electricidad",)),
             _op("secado", "Secado en tambor rotatorio", "secado", "secador_biomasa", "torta_integral", "harina_seca", servicios=("vapor", "electricidad"),
                 nota=_APROX + ": el secador rotatorio de catalogos/biomasa.py"),
             _op("molienda", "Enfriamiento y molienda", "reduccion_tamano", "molino_martillos", "harina_seca", "harina_molida", servicios=("electricidad",)),
             _op("ensacado", "Ensacado", "envasado", "iso_dosificador_rotativo", "harina_molida", "harina_ensacada"),
         ],
         equipos_servicio=("caldera_gas",)),
    dict(id="ciruela_deshidratada", nombre="Ciruela deshidratada", producto="Ciruela deshidratada tipo D'Agen, calibrada y envasada",
         materia_prima="Ciruela fresca D'Agen", unidad="t de ciruela fresca por temporada", region="O'Higgins y Maule",
         rubro="ciruela_deshidratada", escenario=None, demanda_defecto="exportacion_ventana",
         produccion=dict(valor=12000.0, unidad="t de ciruela fresca por temporada", fuente=REFERENCIAS["sup_produccion"]),
         servicios=_srv(vapor="Hidratación y pasteurización antes de envasar", gas="Quemadores del aire de los túneles",
                        electricidad="Ventiladores de los túneles, cintas y calibradora", agua="Lavado de la fruta"),
         referencias=("sup_ciruela",),
         estados=[("ciruela_fresca", "ciruela fresca", "recepción"), ("ciruela_lavada", "ciruela lavada", "lavado"),
                  ("ciruela_en_bandejas", "ciruela en bandejas", "carga de bandejas"), ("ciruela_seca", "ciruela seca", "secado"),
                  ("ciruela_calibrada", "ciruela calibrada", "calibrado"), ("ciruela_hidratada", "ciruela hidratada y pasteurizada", "hidratación"),
                  ("ciruela_envasada", "ciruela envasada", "envasado")],
         operaciones=[
             _op("recepcion", "Recepción y pesaje de la fruta", "recepcion", "iso_bascula", "", "ciruela_fresca"),
             _op("lavado", "Lavado", "lavado", "iso_deposito", "ciruela_fresca", "ciruela_lavada", servicios=("agua",)),
             _op("bandejas", "Carga en bandejas y carros", "transporte", "iso_transportador_cinta", "ciruela_lavada", "ciruela_en_bandejas",
                 servicios=("electricidad",)),
             _op("secado", "Secado en túnel de aire caliente", "secado", "secador_banda", "ciruela_en_bandejas", "ciruela_seca",
                 servicios=("gas", "electricidad"), nota=_APROX + ": el secador de banda de catalogos/biomasa.py"),
             _op("calibrado", "Calibrado y selección", "separacion_mecanica", "recepcion_seleccion", "ciruela_seca", "ciruela_calibrada",
                 nota=_APROX + ": la selección de catalogos/tomate.py (con descarte)"),
             _op("hidratacion", "Hidratación y pasteurización con vapor", "tratamiento_termico", "iso_intercambiador_general", "ciruela_calibrada",
                 "ciruela_hidratada", servicios=("vapor",)),
             _op("envasado", "Envasado", "envasado", "iso_dosificador_rotativo", "ciruela_hidratada", "ciruela_envasada"),
         ],
         equipos_servicio=("caldera_gas",)),
    dict(id="vino_granel", nombre="Vino a granel", producto="Vino tinto a granel despachado en estanques o *flexitank*",
         materia_prima="Uva vinífera", unidad="t de uva por vendimia", region="Maule, O'Higgins y Ñuble",
         rubro="vino_granel", escenario=None, demanda_defecto="mixta_oferta_mercado",
         produccion=dict(valor=20000.0, unidad="t de uva por vendimia", fuente=REFERENCIAS["sup_produccion"]),
         servicios=_srv(electricidad="Refrigeración de la fermentación y de la estabilización, bombas y prensas",
                        agua="Limpieza de cubas, agua de enfriamiento"),
         referencias=("sup_vino",),
         estados=[("uva_fresca", "uva fresca", "recepción"), ("uva_molida", "uva despalillada y molida", "despalillado y molienda"),
                  ("vino_nuevo", "vino nuevo con orujo", "fermentación alcohólica"), ("vino_descubado", "vino descubado y prensado", "descube y prensado"),
                  ("vino_malolactico", "vino con maloláctica terminada", "fermentación maloláctica"), ("vino_clarificado", "vino clarificado", "clarificación"),
                  ("vino_estabilizado", "vino estabilizado en frío", "estabilización tartárica"), ("vino_despachado", "vino despachado a granel", "despacho")],
         operaciones=[
             _op("recepcion", "Recepción y pesaje de la uva", "recepcion", "iso_bascula", "", "uva_fresca"),
             _op("molienda", "Despalillado y molienda", "reduccion_tamano", "trituradora", "uva_fresca", "uva_molida", servicios=("electricidad",)),
             _op("fermentacion", "Fermentación alcohólica en cubas", "reaccion", "iso_reactor", "uva_molida", "vino_nuevo",
                 servicios=("electricidad", "agua")),
             _op("prensado", "Descube y prensado del orujo", "separacion_solido_liquido", "iso_filtro_prensa", "vino_nuevo", "vino_descubado",
                 servicios=("electricidad",)),
             _op("malolactica", "Fermentación maloláctica", "reaccion", "iso_deposito", "vino_descubado", "vino_malolactico", opcional=True,
                 nota="Opcional: habitual en tintos, no en todos los blancos"),
             _op("clarificacion", "Clarificación y filtración", "separacion_solido_liquido", "iso_filtro", "vino_malolactico", "vino_clarificado",
                 servicios=("electricidad",), alternativas=("iso_centrifuga",)),
             _op("estabilizacion", "Estabilización tartárica en frío", "enfriamiento", "iso_intercambiador_placas", "vino_clarificado",
                 "vino_estabilizado", servicios=("electricidad",)),
             _op("despacho", "Almacenamiento y despacho a granel", "envasado", "iso_bomba_desplazamiento", "vino_estabilizado", "vino_despachado",
                 servicios=("electricidad",), nota=_APROX + ": bomba de desplazamiento al estanque o *flexitank*"),
         ],
         equipos_servicio=()),
]

# ---------------------------------------------------------------------------------------------------------------- demandas
_DEMANDAS = [
    dict(id="agricola_tomate", nombre="Oferta agrícola del tomate industrial", logica="agricola",
         descripcion="La planta procesa lo que llega del campo: superficie contratada, rendimiento, curva de cosecha de la temporada y perecibilidad del tomate."),
    dict(id="agricola_fruta", nombre="Oferta agrícola de fruta", logica="agricola",
         descripcion="Cosecha de fruta (manzana, ciruela, uva) con su curva de temporada; la fruta es perecible y la planta debe absorber el peak."),
    dict(id="mercado_agar", nombre="Mercado del agar agar", logica="mercado",
         descripcion="Demanda del mercado de hidrocoloides pronosticada con series de tiempo; el producto se guarda y la capacidad se decide con inventario."),
    dict(id="mercado_estacional_invierno", nombre="Mercado estacional con peak en invierno", logica="mercado",
         descripcion="Demanda con estacionalidad marcada y máximo en los meses fríos (calefacción); obliga a decidir entre capacidad e inventario."),
    dict(id="mercado_constante", nombre="Mercado constante", logica="mercado",
         descripcion="Demanda pareja durante el año con variación aleatoria pequeña; sirve de caso base para comparar."),
    dict(id="mercado_tendencia_creciente", nombre="Mercado con tendencia creciente", logica="mercado",
         descripcion="Demanda que crece año a año; plantea la estrategia de capacidad (adelantarse, seguir o esperar la demanda)."),
    dict(id="contrato_industrial", nombre="Contrato industrial", logica="mercado",
         descripcion="Entregas comprometidas con un cliente industrial (volumen y calendario fijos, con multa por atraso)."),
    dict(id="exportacion_ventana", nombre="Exportación con ventana de embarque", logica="mercado",
         descripcion="Embarques concentrados en una ventana comercial del mercado de destino; la planta produce antes y acumula."),
    dict(id="mercado_impulsos", nombre="Mercado por pedidos grandes (impulsos)", logica="mercado",
         descripcion="Demanda intermitente: pocos pedidos grandes en fechas inciertas (licitaciones, compras puntuales)."),
    dict(id="mixta_oferta_mercado", nombre="Mixta: oferta de materia prima y mercado", logica="mixta",
         descripcion="La materia prima llega con estacionalidad propia y el mercado pide otra; se calza con inventario de producto o de materia prima."),
]
for _d in _DEMANDAS:
    _d.update(modulo="motor/demanda.py (equipo T21)", fuente=REFERENCIAS["demanda_t21"])

# Compatibilidad: por demanda, {planta: (nivel, justificación)}. Lo que no aparece es nivel 0 con la razón de SIN_SENTIDO.
_N, _A = 2, 1
_GUARDA = "el producto es estable y se guarda, así que una demanda de mercado se cubre con inventario"
_COMPAT = {
    "agricola_tomate": {"tomate": (_N, "Es la demanda del rubro: la planta basada en Agrozzi procesa la cosecha de tomate industrial de la temporada")},
    "agricola_fruta": {
        "jugo_manzana": (_N, "La manzana industrial llega con la cosecha y es perecible: la planta sigue la oferta"),
        "ciruela_deshidratada": (_N, "La ciruela se cosecha en pocas semanas y debe secarse fresca"),
        "vino_granel": (_N, "La vendimia fija el calendario de la bodega"),
        "tomate": (_A, "El tomate también es un fruto de temporada; cambia la curva de cosecha respecto de la del tomate industrial"),
        "agar": (_A, "La cosecha de Gracilaria en praderas también es estacional y se modela como oferta"),
    },
    "mercado_agar": {
        "agar": (_N, "Es la demanda del rubro: el agar se vende a la industria de alimentos y se pronostica con series de tiempo"),
        "leche_polvo": (_A, "Ingrediente industrial que se guarda y se vende por pronóstico, igual que el agar"),
        "harina_pescado": (_A, "Ingrediente industrial que se guarda y se vende por pronóstico, igual que el agar"),
        "jugo_manzana": (_A, "El concentrado es un ingrediente que se guarda y se vende por pronóstico"),
    },
    "mercado_estacional_invierno": {
        "pellet": (_N, "Combustible de calefacción: la venta se concentra en invierno"),
        "lena": (_N, "Combustible de calefacción: la venta se concentra en invierno"),
        "chip": (_A, "Parte del chip va a calderas de calefacción; peak de invierno menos marcado que el del pellet"),
        "agar": (_A, "El desafío de ejemplo del mantenedor usa una demanda de agar con peak en invierno"),
    },
    "mercado_constante": {
        "chip": (_N, "Abastece calderas industriales que operan todo el año"),
        **{p: (_A, "Caso base: " + _GUARDA) for p in ("tomate", "pellet", "agar", "jugo_manzana", "leche_polvo", "harina_pescado",
                                                      "ciruela_deshidratada", "vino_granel")},
        "lena": (_A, "Caso base de comparación; en la realidad la venta de leña es estacional"),
    },
    "mercado_tendencia_creciente": {
        "pellet": (_N, "Mercado en crecimiento por el reemplazo de la leña húmeda en calefacción"),
        **{p: (_A, "Sirve para decidir la estrategia de capacidad; " + _GUARDA) for p in ("tomate", "chip", "lena", "agar", "jugo_manzana",
                                                                                          "leche_polvo", "harina_pescado", "ciruela_deshidratada", "vino_granel")},
    },
    "contrato_industrial": {
        "harina_pescado": (_N, "La harina se vende con contratos a fabricantes de alimento para la salmonicultura"),
        "chip": (_A, "Contrato de suministro con una caldera industrial o una planta de celulosa"),
        "leche_polvo": (_A, "Contrato con la industria de alimentos"),
        "jugo_manzana": (_A, "Contrato con embotelladoras de jugos y bebidas"),
        "tomate": (_A, "La pasta se vende a la industria de salsas con entregas comprometidas"),
        "pellet": (_A, "Contrato con calderas de edificios o industrias"),
        "agar": (_A, "Contrato con un cliente industrial de alimentos"),
        "ciruela_deshidratada": (_A, "Contrato con un importador"),
        "vino_granel": (_A, "Contrato con un embotellador en el destino"),
    },
    "exportacion_ventana": {
        "ciruela_deshidratada": (_N, "Producto de exportación con embarques por temporada comercial del destino"),
        "vino_granel": (_A, "El vino a granel se exporta en embarques"),
        "jugo_manzana": (_A, "El concentrado se exporta casi entero"),
        "tomate": (_A, "Parte de la pasta se exporta"),
        "agar": (_A, "El agar chileno se exporta"),
        "harina_pescado": (_A, "Parte de la harina se exporta"),
        "leche_polvo": (_A, "Parte de la leche en polvo se exporta"),
        "chip": (_A, "Existe exportación de astilla por puerto"),
    },
    "mercado_impulsos": {
        "agar": (_N, "Pocos clientes industriales con pedidos grandes y espaciados"),
        "vino_granel": (_A, "Las compras de vino a granel son puntuales y grandes"),
        **{p: (_A, "Pedidos grandes y espaciados de clientes industriales; " + _GUARDA) for p in ("tomate", "pellet", "chip", "jugo_manzana",
                                                                                                  "leche_polvo", "harina_pescado", "ciruela_deshidratada")},
    },
    "mixta_oferta_mercado": {
        "leche_polvo": (_N, "La recepción de leche es estacional (peak en primavera) y el mercado pide parejo: se calza con inventario de polvo"),
        "vino_granel": (_N, "La vendimia llega en otoño y el vino se vende durante el año"),
        "harina_pescado": (_A, "Los desembarques dependen de cuotas y vedas; el mercado pide con otro calendario"),
        "jugo_manzana": (_A, "La fruta llega en temporada y el concentrado se vende todo el año"),
        "ciruela_deshidratada": (_A, "La fruta llega en temporada y la ciruela seca se vende todo el año"),
        "tomate": (_A, "La cosecha llega en temporada y la pasta se vende todo el año"),
        "agar": (_A, "La cosecha de algas es estacional y el mercado pide con otro calendario"),
        "pellet": (_A, "El aserrín llega con la producción de los aserraderos y el pellet se vende en invierno"),
        "chip": (_A, "Los rollizos llegan según la cosecha forestal y el chip se vende a las calderas"),
        "lena": (_A, "La leña verde se corta en verano y se vende en invierno"),
    },
}
SIN_SENTIDO = {
    "agricola_tomate": "La curva de cosecha del tomate industrial no corresponde a la materia prima de esta planta",
    "agricola_fruta": "La materia prima de esta planta no es fruta cosechada en temporada",
    "mercado_agar": "La serie del mercado del agar no representa el mercado de este producto",
    "mercado_estacional_invierno": "El producto no se usa para calefacción: su venta no tiene peak en invierno",
    "contrato_industrial": "El producto se vende al detalle a hogares, sin contratos industriales",
    "exportacion_ventana": "El producto se vende en el mercado interno; no hay ventana de exportación",
    "mercado_impulsos": "El producto se vende al detalle en muchas compras chicas, no en pedidos grandes",
}


# ---------------------------------------------------------------------------------------------------------------- consultas
def _completar(p: dict) -> dict:
    p = dict(p)
    ops = []
    for i, o in enumerate(p["operaciones"], start=1):
        o = dict(o); o["orden"] = i
        cat, fam, letra = familia_de(o["tipo_equipo"])
        o.update(simbolo=simbolo_de(o["tipo_equipo"]), familia=cat, familia_nombre=fam, letra=letra,
                 funcion_nombre=FUNCIONES[o["funcion"]])
        ops.append(o)
    p["operaciones"] = ops
    p["referencias_texto"] = [REFERENCIAS[r] for r in p["referencias"]]
    if p["escenario"]:
        p["escenario_funcion"] = f"pat_sim.escenarios.{p['escenario']}.crear"
    return p


PLANTAS = {p["id"]: _completar(p) for p in _PLANTAS}
DEMANDAS = {d["id"]: dict(d) for d in _DEMANDAS}
IDS_PLANTAS = tuple(PLANTAS)
IDS_DEMANDAS = tuple(DEMANDAS)
EXISTENTES = tuple(i for i, p in PLANTAS.items() if p["escenario"])     # tomate, pellet, chip, leña y agar (PAT 143 b)


def planta(planta_id: str) -> dict:
    if planta_id not in PLANTAS:
        raise KeyError(f"No existe el tipo de planta «{planta_id}». Use uno de: {', '.join(IDS_PLANTAS)}")
    return PLANTAS[planta_id]


def demanda(demanda_id: str) -> dict:
    if demanda_id not in DEMANDAS:
        raise KeyError(f"No existe el tipo de demanda «{demanda_id}». Use uno de: {', '.join(IDS_DEMANDAS)}")
    return DEMANDAS[demanda_id]


def compatibilidad(planta_id: str, demanda_id: str) -> tuple[int, str]:
    """(nivel, justificación): 2 natural, 1 adaptable, 0 sin sentido."""
    planta(planta_id); demanda(demanda_id)
    r = _COMPAT.get(demanda_id, {}).get(planta_id)
    if r:
        return r
    return 0, SIN_SENTIDO.get(demanda_id, "Combinación sin sentido para este rubro") + " (" + REFERENCIAS["sup_compat"].split(":")[0] + ")"


def matriz_compatibilidad() -> list[dict]:
    """Las 100 combinaciones planta × demanda con su nivel y su justificación."""
    out = []
    for p in IDS_PLANTAS:
        for d in IDS_DEMANDAS:
            n, j = compatibilidad(p, d)
            out.append(dict(planta_id=p, demanda_id=d, nivel=n, nivel_nombre=NIVELES[n], justificacion=j, fuente=REFERENCIAS["sup_compat"]))
    return out


def combinaciones(minimo_nivel: int = 1) -> list[tuple[str, str]]:
    """Pares (planta, demanda) con nivel ≥ minimo_nivel, en el orden del catálogo. minimo_nivel=0 da las 100."""
    return [(f["planta_id"], f["demanda_id"]) for f in matriz_compatibilidad() if f["nivel"] >= minimo_nivel]


def crear_escenario(planta_id: str, **kw):
    """Planta calculada del escenario enlazado (los cuatro rubros de antes y el agar). None si el tipo no tiene escenario."""
    p = planta(planta_id)
    if not p["escenario"]:
        return None
    mod = importlib.import_module(f"..escenarios.{p['escenario']}", __package__)
    return mod.crear(**kw)


def estados_material(planta_id: str) -> list[dict]:
    """Filas como las de la tabla estados_material del mantenedor (rubro, orden, código, nombre, etapa, fuente).
    Los cuatro rubros existentes las toman de la semilla del mantenedor; los nuevos, de su lista «estados»."""
    p = planta(planta_id)
    if "estados" not in p:
        from ..datos.mantenedor import semilla_estados
        return [e for e in semilla_estados() if e["rubro"] == p["rubro"]]
    fuente = "; ".join(p["referencias_texto"])
    return [dict(rubro=p["rubro"], orden=i, codigo=c, nombre=n, etapa=e, fuente=fuente) for i, (c, n, e) in enumerate(p["estados"], start=1)]


def precedencia(planta_id: str) -> list[dict]:
    """Filas como las de la tabla precedencia del mantenedor (rubro, tipo, acepta, entrega, opcional, fuente), una por operación."""
    p = planta(planta_id)
    fuente = "; ".join(p["referencias_texto"])
    return [dict(rubro=p["rubro"], tipo=o["tipo_equipo"], acepta=", ".join(o["entrada"]), entrega=o["salida"], opcional=o["opcional"],
                 fuente=(o["nota"] + "; " if o["nota"] else "") + fuente) for o in p["operaciones"]]


def tabla_precedencia(planta_id: str) -> dict:
    """{estados, precedencia, libre} listo para motor/precedencia.Precedencia.desde()."""
    return dict(estados=estados_material(planta_id), precedencia=precedencia(planta_id), libre=False)
