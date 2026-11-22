"""Equipos reales de referencia por tipo (PAT 139, equipo E2, 14-11-2026; punto 3 de los comentarios del profesor Torres).
Ampliada el 16-11-2026: precios puntuales de equipos de 4 tipos (caldera, evaporador multiefecto, MVR y esterilizador; las filas nuevas
llevan fecha_consulta 2026-11-16) y MTBF y MTTR de literatura genérica (bomba, esterilizador, llenadora; MTTR de caldera).

Cada fila es un equipo real leído de la página de un fabricante, distribuidor o mercado en línea el 14-11-2026, con su URL exacta.
Lo que la página no dice queda en None («sin dato»): no se inventó ningún valor. Reglas:

- punto: «minimo», «medio» y «maximo» son los tres puntos del tipo (el más chico que se encontró, uno intermedio y el más grande);
  «adicional» son equipos extra que se guardan con sus datos pero no cuentan entre los tres.
- precio_puntual = 1 solo si la página ata UN precio a UN modelo con su capacidad y el precio es creíble. Si la página da un rango para
  toda una serie (lo usual en Made-in-China), el precio queda en precio_texto y precio_usd en None. Si da una cifra que no es creíble
  (la misma en tamaños distintos o más barata en un equipo mayor), precio_usd guarda lo que dice la página pero precio_puntual = 0 y la
  razón va en «nota». Con precio_puntual = 0 el precio no se usa como precio del candidato (se estima con Williams y se marca).
- usar_en_ajuste = 1 solo si el precio es puntual y comparable con los demás puntos del tipo. Se pone 0 en precio puntual de otra clase
  (por ejemplo las bombas Alfa Laval, una serie premium con precio por kW diez veces mayor que el de la serie ATO).
- capacidad y unidad son la unidad de trabajo del tipo (UNIDAD_TIPO, la misma de motor/costeo.py): se calculan desde cap_original y
  unidad_original con convertir() y la conversión queda escrita en nota_conversion.
- MTBF y MTTR: ninguna página de fabricante o vendedor los publica. Los valores numéricos que hay (mtbf_h, mttr_h) son de literatura
  genérica (otro equipo, otra planta o derivados de los datos del artículo), no del fabricante, y confiabilidad_texto dice la fuente
  completa y la salvedad. Donde no se encontró fuente abierta con cifras queda «sin dato». confiabilidad_texto guarda además lo que la
  página dice de confiabilidad (garantía, vida de diseño, afirmaciones del proveedor, que no están verificadas).
- Los proveedores de Made-in-China.com figuran en la página como «Manufacturer/Factory & Trading Company»: pueden ser comercializadores.
"""
from __future__ import annotations

FECHA = "2026-11-14"
FECHA2 = "2026-11-16"          # filas nuevas de la ampliación del 16-11-2026
ANIO = 2026
MC = "Proveedor de Made-in-China.com (la página lo lista como fabricante y comercializador)"
RM = "revelationmachinery.com (Revelation Machinery, vendedor de equipo industrial usado)"

# unidad de trabajo de cada tipo: la de motor/costeo.py (_LINEA) y, en los auxiliares, la magnitud de su costeo
UNIDAD_TIPO = {
    "recepcion_seleccion": "t/h", "trituradora": "t/h", "hot_break": "kW", "refinadora": "t/h", "evaporador_mvr": "kg/h",
    "evaporador_multiefecto": "kg/h", "esterilizador": "kW", "enfriamiento_flash": "t/h", "llenadora_aseptica": "t/h",
    "caldera_gas": "kW", "bomba_centrifuga": "kW", "intercambiador": "m2", "torre_enfriamiento": "m3/h", "estanque_pulmon": "m3",
}
NOMBRE_TIPO = {
    "recepcion_seleccion": "Lavado y selección de tomate", "trituradora": "Trituradora de tomate",
    "hot_break": "Hot break (inactivación enzimática)", "refinadora": "Refinadora (despulpadora)",
    "evaporador_mvr": "Evaporador MVR", "evaporador_multiefecto": "Evaporador de múltiple efecto",
    "esterilizador": "Esterilizador tubular", "enfriamiento_flash": "Enfriamiento flash al vacío",
    "llenadora_aseptica": "Llenadora aséptica", "caldera_gas": "Caldera a gas (vapor)",
    "bomba_centrifuga": "Bomba centrífuga sanitaria", "intercambiador": "Intercambiador de tubo y carcasa",
    "torre_enfriamiento": "Torre de enfriamiento", "estanque_pulmon": "Estanque pulmón de acero inoxidable",
}
# clave de motor/costeo.py (EXPONENTES, REFERENCIAS) de cada tipo; sin clave propia se usa «generico» (n = 0,6 Supuesto)
CLAVE_COSTEO = {
    "recepcion_seleccion": "lavado_seleccion", "trituradora": "trituradora", "hot_break": "hot_break", "refinadora": "refinadora",
    "evaporador_mvr": "evaporador_mvr", "evaporador_multiefecto": "evaporador_multiefecto", "esterilizador": "esterilizador",
    "enfriamiento_flash": "enfriamiento_flash", "llenadora_aseptica": "llenadora_aseptica", "caldera_gas": "caldera_gas",
    "bomba_centrifuga": "bomba_centrifuga", "intercambiador": "intercambiador", "torre_enfriamiento": "torre_enfriamiento",
    "estanque_pulmon": "estanque_pulmon",
}


def _f(tipo, punto, fabricante, modelo, cap, ud, url, **kw):
    """Fila con todos los campos; lo no dado queda en None (sin dato)."""
    base = dict(tipo=tipo, punto=punto, fabricante=fabricante, modelo=modelo, cap_original=cap, unidad_original=ud, url=url,
                nombre_pagina=None, proveedor=None, precio_texto=None, precio_usd=None, moneda="US$", precio_puntual=0,
                usar_en_ajuste=0, anio_precio=ANIO, fecha_consulta=FECHA, potencia_kw=None, largo_m=None, ancho_m=None,
                alto_m=None, peso_kg=None, material=None, garantia_meses=None, plazo_entrega_semanas=None, mtbf_h=None,
                mttr_h=None, confiabilidad_texto=None, categoria="Internet", nota=None)
    base.update(kw)
    return base


_SIN_MTBF = "MTBF y MTTR: sin dato (la página no los publica)"
_ATO = "https://www.ato.com/1-1-2-hp-sanitary-centrifugal-pump"
_SIN_FAB = "MTBF y MTTR del fabricante: sin dato (la página no los publica). "
_LIT_BOMBA = ("MTBF de literatura genérica, no del fabricante (consultada el 2026-11-16): 2,5 años x 8.760 h = 21.900 h de promedio en "
              "bombas de proceso ANSI/ASME B73.1 (Budris, WaterWorld, año no dado; citado por Reliable, «Pump Reliability and MTBF "
              "Statistics», 2026-07-03, https://reliamag.com/topics/guides/pump-reliability-mtbf-statistics); Bloch (Pump User's "
              "Handbook, año no dado) da 3 a 10 años en refinerías. Contraste: tasa de falla en marcha de 5,0E-05 por hora (MTBF "
              "20.000 h) en Cadwallader (2015), INL/CON-15-34097, https://inldigitallibrary.inl.gov/sites/sti/sti/6760037.pdf. "
              "MTTR: sin dato.")
_LIT_ESTER = ("MTBF y MTTR de literatura genérica, no del fabricante (consultada el 2026-11-16): autoclave (retort) de una fábrica de "
              "conservas, MTBF 18,3 días (x 24 h = 439,2 h) y MTTR 30 min (0,5 h), tabla 2, p. 391, Savsar y Çiçek (2021), Avrupa "
              "Bilim ve Teknoloji Dergisi, número especial 29, https://dergipark.org.tr/en/download/article-file/2126133. Es un "
              "esterilizador por lotes, no tubular, y el artículo no define las horas por día: se asumen 24 h (Supuesto).")
_LIT_LLEN = ("MTBF y MTTR de literatura genérica, no del fabricante (consultada el 2026-11-16): llenadora y selladora de latas de una "
             "fábrica de conservas, MTBF 5,5 días (x 24 h = 132 h) y MTTR 60 min (1 h), tabla 2, p. 391, Savsar y Çiçek (2021), "
             "Avrupa Bilim ve Teknoloji Dergisi, número especial 29, https://dergipark.org.tr/en/download/article-file/2126133. No es "
             "aséptica ni de pasta, y se asumen 24 h por día (Supuesto). Contraste: línea de llenado de cerveza en botella, MTBF de "
             "1.212,46 min (20,2 h) y MTTR mensual de 26,7 a 36,8 con promedio de 30,6 (unidad no rotulada en la tabla; si son "
             "minutos, 0,5 h), Zeng, Shao y Hao (2021), Tehnički vjesnik 28(2), 689-697, https://hrcak.srce.hr/file/371967.")
_LIT_CALD = ("MTTR de literatura genérica, no del fabricante (consultada el 2026-11-16): 2,06 h (123,75 min), calculado con los 8 eventos "
             "de la caldera Miura E1-2000GU a gas (2.000 kg/h) de una planta automotriz en 28 días de operación: 6 fallas de encendido "
             "de 15 min, una fuga de tubo de 720 min y un filtro de 180 min (990 min en total, tablas 1 y 2), Kavindra y Surahmanto "
             "(2026), Journal of Engineering and Applied Technology 7(1), 33-43, "
             "https://journal.uny.ac.id/index.php/jeatech/article/download/102648/26125/293077. Muestra chica y el artículo no calcula "
             "MTTR. MTBF: sin dato (no se deriva de las 148 h de operación de ese artículo porque mezcla paradas menores).")
_LKH_HOJA = "https://assets.alfalaval.com/documents/p35de4bfa/alfa-laval-lkh-product-leaflet-en-gb.pdf"
_CSI = "https://store.csidesigns.com/en/product/"
_LKH_CONF = (f"Hoja del fabricante ({_LKH_HOJA}): garantía extendida de 3 años en piezas sin desgaste con repuestos originales y "
             "«Maximized uptime and reduced maintenance costs»; vida útil e intervalos de mantención: sin dato. " + _SIN_FAB + _LIT_BOMBA)

FILAS: list[dict] = [
    # ------------------------------------------------------------------ bomba centrífuga sanitaria (kW de motor)
    _f("bomba_centrifuga", "minimo", "ATO (marca del vendedor ato.com; la página no nombra fabricante)",
       "Sanitary Stainless Steel Centrifugal Pump 3/4 hp (sin número de modelo en la página)", 0.55, "kW", _ATO,
       proveedor="ato.com", precio_texto="US$ 471,53", precio_usd=471.53, precio_puntual=1, usar_en_ajuste=1,
       mtbf_h=21900.0, confiabilidad_texto=_SIN_FAB + _LIT_BOMBA, nota="Altura nominal 14 m. Material, peso y dimensiones: sin dato en esa fila de la página."),
    _f("bomba_centrifuga", "medio", "ATO (marca del vendedor ato.com; la página no nombra fabricante)", "ATO-50SF6-18-1.1", 1.1, "kW",
       _ATO, proveedor="ato.com", precio_texto="US$ 730,21", precio_usd=730.21, precio_puntual=1, usar_en_ajuste=1, peso_kg=24.0,
       material="Acero inoxidable 304", potencia_kw=1.1, mtbf_h=21900.0, confiabilidad_texto=_SIN_FAB + _LIT_BOMBA,
       nota="1,5 hp, caudal nominal 6 m3/h, diámetro de bocas 50-40 mm. Dimensiones: sin dato."),
    _f("bomba_centrifuga", "maximo", "ATO (marca del vendedor ato.com; la página no nombra fabricante)",
       "Sanitary Stainless Steel Centrifugal Pump 4 hp (sin número de modelo en la página)", 3.0, "kW", _ATO, proveedor="ato.com",
       precio_texto="US$ 1.011,84", precio_usd=1011.84, precio_puntual=1, usar_en_ajuste=1, material="Acero inoxidable 304",
       mtbf_h=21900.0, confiabilidad_texto=_SIN_FAB + _LIT_BOMBA, nota="Altura nominal 20 m. Peso y dimensiones: sin dato en esa fila."),
    _f("bomba_centrifuga", "adicional", "Alfa Laval", "LKH05A125F4ES-1.5LSB (LKH-5, 1,5 hp)", 1.5, "hp",
       _CSI + "pump-solutions-centrifugal-pumps/alfa-laval-lkh05-centrifugal-pump-and-motor-2-x-15-tri-clamp-316l-32ra-scsc-sin--LKH05A125F4ES-1%5E46%5E5LSB",
       proveedor="store.csidesigns.com", precio_texto="US$ 7.779,56 (el signo $ de la página se lee como dólar)", precio_usd=7779.56,
       precio_puntual=1, usar_en_ajuste=0, material="Acero inoxidable 316L, acabado 32 Ra, elastómero EPDM, sello SiC/SiC",
       mtbf_h=21900.0, confiabilidad_texto=_LKH_CONF,
       nota="Serie premium: no entra al ajuste porque su precio por kW es unas diez veces el de la serie ATO. Motor Baldor. "
            "Peso publicado 91 (sin unidad en la página)."),
    _f("bomba_centrifuga", "adicional", "Alfa Laval", "LKH10M155S2YS21AAN-7P5B36CBB (LKH-10, 7,5 hp)", 7.5, "hp",
       _CSI + "alfa-laval-pumps-centrifugal-pumps/alfa-laval-lkh10-centrifugal-pump-and-motor-25-x-2-tri-clamp-316l-32ra-csc-sing--LKH10M155S2YS21AAN-7P5B36CBB",
       proveedor="store.csidesigns.com", precio_texto="US$ 9.606,08", precio_usd=9606.08, precio_puntual=1, usar_en_ajuste=0,
       material="Acero inoxidable 316L, 32 Ra, sello mecánico FKM", mtbf_h=21900.0, confiabilidad_texto=_LKH_CONF,
       nota="Serie premium, motor Baldor, impulsor de 155 mm. Peso publicado 293,08 (sin unidad en la página)."),
    _f("bomba_centrifuga", "adicional", "Alfa Laval", "LKH20M140S2YS21AAN-7P5B36CBB (LKH-20, 7,5 hp)", 7.5, "hp",
       _CSI + "alfa-laval-pumps-centrifugal-pumps/alfa-laval-lkh20-centrifugal-pump-and-motor-25-x-2-tri-clamp-316l-32ra-csc-sing--LKH20M140S2YS21AAN-7P5B36CBB",
       proveedor="store.csidesigns.com", precio_texto="US$ 11.112,59", precio_usd=11112.59, precio_puntual=1, usar_en_ajuste=0,
       material="Acero inoxidable 316L", mtbf_h=21900.0, confiabilidad_texto=_LKH_CONF,
       nota="Serie premium, motor Baldor, impulsor de 140 mm. Peso publicado 301,46 (sin unidad en la página)."),

    # ------------------------------------------------------------------ caldera a gas (kW térmicos = t/h de vapor × 655,6 kW por t/h)
    _f("caldera_gas", "minimo", "Taikang Yinyu Boiler Manufacturing Co., Ltd.", "WNS0.5 (0,5 t/h de vapor)", 0.5, "t/h vapor",
       "https://tkyyboiler.en.made-in-china.com/product/RrpUOoiYOVcm/China-CE-Certified-10t-H-Wns-Model-Horizontal-Natural-Gas-Boiler-for-Food-Processing-Automatic-Fire-Tube-Water-Tube-Steam.html",
       nombre_pagina="CE Certified 10t/H Wns Model Horizontal Natural Gas Boiler for Food Processing", proveedor=MC,
       precio_texto="US$ 2.000-5.000 por equipo: rango de la página para toda la serie WNS0.5 a WNS20, no por modelo",
       largo_m=3.0, ancho_m=1.5, alto_m=1.81, peso_kg=3500.0, material="Placas de caldera Q245R y Q345R", garantia_meses=24.0,
       plazo_entrega_semanas=3.0,
       mttr_h=2.06, confiabilidad_texto="Vida de diseño de 16 a 26 años, eficiencia térmica >98 % (afirmaciones del proveedor). " + _SIN_FAB + _LIT_CALD,
       nota="Dimensiones y peso son los máximos de transporte (3000 x 1500 x 1810 mm, 3,5 t). Gas natural 35,7 Nm3/h. Plazo: 3 semanas "
            "es el de equipo a medida (15 días hábiles); en stock 1 a 5 días. El rango de precio no es creíble para los 20 t/h: no se usa."),
    _f("caldera_gas", "medio", "Taikang Yinyu Boiler Manufacturing Co., Ltd.", "WNS6 (6 t/h de vapor)", 6.0, "t/h vapor",
       "https://tkyyboiler.en.made-in-china.com/product/RrpUOoiYOVcm/China-CE-Certified-10t-H-Wns-Model-Horizontal-Natural-Gas-Boiler-for-Food-Processing-Automatic-Fire-Tube-Water-Tube-Steam.html",
       nombre_pagina="CE Certified 10t/H Wns Model Horizontal Natural Gas Boiler for Food Processing", proveedor=MC,
       precio_texto="US$ 2.000-5.000 por equipo: rango de la página para toda la serie, no por modelo",
       largo_m=6.455, ancho_m=2.435, alto_m=2.865, peso_kg=17500.0, material="Placas de caldera Q245R y Q345R", garantia_meses=24.0,
       plazo_entrega_semanas=3.0, mttr_h=2.06, confiabilidad_texto="Vida de diseño de 16 a 26 años (proveedor). " + _SIN_FAB + _LIT_CALD,
       nota="Máximos de transporte 6455 x 2435 x 2865 mm y 17,5 t. Gas natural 424,2 Nm3/h."),
    _f("caldera_gas", "maximo", "Taikang Yinyu Boiler Manufacturing Co., Ltd.", "WNS20 (20 t/h de vapor)", 20.0, "t/h vapor",
       "https://tkyyboiler.en.made-in-china.com/product/RrpUOoiYOVcm/China-CE-Certified-10t-H-Wns-Model-Horizontal-Natural-Gas-Boiler-for-Food-Processing-Automatic-Fire-Tube-Water-Tube-Steam.html",
       nombre_pagina="CE Certified 10t/H Wns Model Horizontal Natural Gas Boiler for Food Processing", proveedor=MC,
       precio_texto="US$ 2.000-5.000 por equipo: rango de la página para toda la serie, no por modelo",
       largo_m=8.2, ancho_m=3.65, alto_m=4.1, peso_kg=45500.0, material="Placas de caldera Q245R y Q345R", garantia_meses=24.0,
       plazo_entrega_semanas=3.0, mttr_h=2.06, confiabilidad_texto="Vida de diseño de 16 a 26 años (proveedor). " + _SIN_FAB + _LIT_CALD,
       nota="Máximos de transporte 8200 x 3650 x 4100 mm y 45,5 t. Gas natural 1.415,8 Nm3/h."),
    _f("caldera_gas", "adicional", "Jiangsu Soho Honry Import & Export Co., Ltd. (marca SUTEX)", "WNS1 (1 t/h de vapor)", 1.0, "t/h vapor",
       "https://js-sohohonry.en.made-in-china.com/product/wQTUrSBbgRcY/China-Wns-Natural-Gas-Fired-Fire-Tube-Steam-Boiler.html",
       nombre_pagina="Wns Natural Gas Fired Fire Tube Steam Boiler", proveedor=MC,
       precio_texto="US$ 20.000-200.000 por equipo: rango de la página para la serie WNS1 a WNS20, no por modelo",
       largo_m=3.9, ancho_m=2.02, alto_m=2.35, peso_kg=5700.0, garantia_meses=12.0, plazo_entrega_semanas=13.0,
       mttr_h=2.06, confiabilidad_texto="Garantía de 12 meses contra defectos. " + _SIN_FAB + _LIT_CALD,
       nota="Dimensiones de la pieza mayor. Los rendimientos térmicos de la tabla de la página pasan de 100 %: no se usan."),
    _f("caldera_gas", "adicional", "Jiangsu Soho Honry Import & Export Co., Ltd. (marca SUTEX)", "WNS20 (20 t/h de vapor)", 20.0, "t/h vapor",
       "https://js-sohohonry.en.made-in-china.com/product/wQTUrSBbgRcY/China-Wns-Natural-Gas-Fired-Fire-Tube-Steam-Boiler.html",
       nombre_pagina="Wns Natural Gas Fired Fire Tube Steam Boiler", proveedor=MC,
       precio_texto="US$ 20.000-200.000 por equipo: rango de la página para la serie WNS1 a WNS20, no por modelo",
       largo_m=8.6, ancho_m=3.46, alto_m=3.58, peso_kg=38300.0, garantia_meses=12.0, plazo_entrega_semanas=13.0,
       mttr_h=2.06, confiabilidad_texto="Garantía de 12 meses contra defectos. " + _SIN_FAB + _LIT_CALD, nota="Dimensiones de la pieza mayor. Plazo de 60 a 90 días."),

    # ------------------------------------------------------------------ torre de enfriamiento (m3/h de agua)
    _f("torre_enfriamiento", "minimo", "Dongguan Naser Machinery Co., Ltd.", "NCT-80H (80 RT)", 62.64, "m3/h",
       "https://naserland.en.made-in-china.com/product/vKomFzdylRWn/China-80rt-Round-Counter-Flow-Type-FRP-Cooling-Tower.html",
       nombre_pagina="80rt Round Counter Flow Type FRP Cooling Tower", proveedor=MC, precio_texto="US$ 3.700,00 por pieza",
       precio_usd=3700.0, precio_puntual=1, usar_en_ajuste=1, potencia_kw=1.5, largo_m=2.145, ancho_m=2.145, alto_m=2.18, peso_kg=290.0,
       material="Carcasa y cubeta de FRP, relleno de PP, aspas de aleación de aluminio", garantia_meses=12.0, plazo_entrega_semanas=2.0,
       confiabilidad_texto="Certificados CE y SGS, ISO 9001; carcasa de FRP con estabilizador UV; motor IP44 (proveedor). " + _SIN_MTBF,
       nota="Ancho y largo son el diámetro de la cubeta (2145 mm). Plazo de 10 días hábiles."),
    _f("torre_enfriamiento", "medio", "Hebei Shengrun FRP Co., Ltd.", "Round Cooling Tower 350 m3/h (sin número de modelo)", 350.0, "m3/h",
       "https://shengrunfrp.en.made-in-china.com/product/AQMrvBhYaopg/China-Fiber-Reinforced-Polymer-350m3-H-Water-Flow-7-5kw-Counter-Flow-Low-Noise-Round-Shape-Large-Cooling-Tower.html",
       nombre_pagina="Fiber-Reinforced Polymer 350m3/H Water Flow 7.5kw Counter Flow Low Noise Round Shape Large Cooling Tower",
       proveedor=MC, precio_texto="US$ 999,00 (1 a 99 piezas), US$ 950,00 (100 a 999), US$ 800,00 (1.000 o más)", precio_usd=999.0,
       precio_puntual=0, usar_en_ajuste=0, potencia_kw=7.5, material="FRP/GRP (la página también dice «Metal»)",
       confiabilidad_texto="Certificados RoHS, UR, ISO, CE, CCC (proveedor). " + _SIN_MTBF,
       nota="Precio no creíble: una torre de 350 m3/h a US$ 999 sale más barata que la de 62,64 m3/h (US$ 3.700), y la ficha mezcla "
            "texto de un depurador de gases. Se guarda con su precio pero no se usa en el ajuste."),
    _f("torre_enfriamiento", "maximo", "Newin (Guangdong) Machinery Co., Ltd.", "Counterflow Cooling Tower for 1200 M3/H Open Circuit System",
       1200.0, "m3/h",
       "https://newinmachine.en.made-in-china.com/product/iyYQcXvUgnhg/China-Square-Counterflow-FRP-Cooling-Tower-for-Power-Plant-300-Ton.html",
       nombre_pagina="Counterflow Cooling Tower for 1200 M3/H Open Circuit System (fila de un listado de 24 productos)", proveedor=MC,
       precio_texto="US$ 25.000", precio_usd=25000.0, precio_puntual=0, usar_en_ajuste=0, material="«Armour» (texto de la página, sin aclarar)",
       confiabilidad_texto=_SIN_MTBF,
       nota="El mismo precio de US$ 25.000 aparece en otras cinco filas del listado con capacidades distintas: probable precio de "
            "marcador. No se usa en el ajuste. Potencia, peso y dimensiones: sin dato."),
    _f("torre_enfriamiento", "adicional", "Newin (Guangdong) Machinery Co., Ltd.", "Nsh Series 800 Tons (800 m3/h nominales)", 800.0, "m3/h",
       "https://newinmachine.en.made-in-china.com/product/iyYQcXvUgnhg/China-Square-Counterflow-FRP-Cooling-Tower-for-Power-Plant-300-Ton.html",
       nombre_pagina="Newin Open Type Cooling Tower - Nsh Series 800 Tons", proveedor=MC,
       precio_texto="US$ 25.000-90.000 por pieza: rango de la fila, no un precio por modelo", potencia_kw=30.0, peso_kg=6520.0,
       garantia_meses=12.0, confiabilidad_texto=_SIN_MTBF,
       nota="Motor de 7,5 x 4 kW (4 motores). Peso neto 6.520 kg y en operación 13.300 kg. Dimensiones: sin dato."),

    # ------------------------------------------------------------------ intercambiador de tubo y carcasa (m2)
    _f("intercambiador", "minimo", "Sin dato (la página dice «Manufacturer: Not Specified»)", "Shell and Tube Heat Exchanger 7,85 sq ft (stock 8.BR-398.2)",
       7.85, "sq ft", "https://genemco.com/products/shell-and-tube-heat-exchanger-785-sq-ft", proveedor="genemco.com (equipo industrial, stock)",
       precio_texto="US$ 5.000 (antes US$ 5.500, «Save 9 %»)", precio_usd=5000.0, precio_puntual=0, usar_en_ajuste=0,
       largo_m=0.0889, ancho_m=0.0889, alto_m=3.353, material="Acero inoxidable 316 en el lado de tubos",
       confiabilidad_texto=_SIN_MTBF,
       nota="El precio de US$ 5.000 es idéntico en los tres intercambiadores del listado (7,85; 190,76 y 570,86 sq ft): precio de marcador, "
            "no se usa. Tubos de 1 in x 10 ft. Presión de diseño y condición (nuevo o usado): sin dato."),
    _f("intercambiador", "medio", "Sin dato (la página dice «Manufacturer: Not Specified»)", "Stainless Steel Shell and Tube Heat Exchanger 190,76 sq ft (stock NOI172)",
       190.76, "sq ft", "https://genemco.com/products/stainless-steel-shell-and-tube-heat-exchanger-19076-sq-ft-noi172",
       proveedor="genemco.com (equipo industrial, stock)", precio_texto="US$ 5.000 (antes US$ 5.500)", precio_usd=5000.0, precio_puntual=0,
       usar_en_ajuste=0, largo_m=3.454, ancho_m=0.965, alto_m=2.438, material="Acero inoxidable 316 (tubos)", confiabilidad_texto=_SIN_MTBF,
       nota="Mismo precio de marcador que los otros dos: no se usa. Medidas totales 136 x 38 x 96 in."),
    _f("intercambiador", "maximo", "Sin dato (la página dice «Manufacturer: Not Specified»)", "Stainless Steel Shell and Tube Heat Exchanger 570,86 sq ft (stock 35.343a)",
       570.86, "sq ft", "https://genemco.com/products/stainless-steel-shell-and-tube-heat-exchanger-57086-sq-ft-35343a",
       proveedor="genemco.com (equipo industrial, stock)", precio_texto="US$ 5.000 (antes US$ 5.500), «Sold out»", precio_usd=5000.0,
       precio_puntual=0, usar_en_ajuste=0, largo_m=1.511, ancho_m=1.194, alto_m=4.191, material="Acero inoxidable 316 (tubos)",
       confiabilidad_texto=_SIN_MTBF, nota="Mismo precio de marcador: no se usa. Medidas 4 ft 11,5 in x 3 ft 11 in x 13 ft 9 in."),
    _f("intercambiador", "adicional", "Shandong Tanglian Chemical Equipment Co., Ltd.", "10m2 Stainless Steel Condenser Heat Exchanger Factory Price",
       10.0, "m2", "https://m.madeinchina.com/mall/show-10m2-Stainless-Steel-Condenser-Heat-Exchanger-Factory-Price_781331.html",
       proveedor=MC, precio_texto="US$ 5.000 por pieza", precio_usd=5000.0, precio_puntual=1, usar_en_ajuste=1, material="Acero inoxidable",
       garantia_meses=12.0, confiabilidad_texto="Proveedor con auditoría SGS/BV y certificados ISO y SGS (la página). " + _SIN_MTBF,
       nota="Los 10 m2 salen solo del título: la ficha técnica no trae el área ni el modelo («heat exchanger»)."),

    # ------------------------------------------------------------------ trituradora de tomate (t/h)
    _f("trituradora", "minimo", "Henan Topp Machinery Co., Ltd.", "TPP-PS1", 1.0, "t/h",
       "https://toppmachine.en.made-in-china.com/product/RdGaFCpOlNYk/China-Fruit-Vegetable-Tomato-Crusher-Crushing-Machine-Pineapple-Crusher.html",
       nombre_pagina="Fruit Vegetable Tomato Crusher Crushing Machine Pineapple Crusher", proveedor=MC, precio_texto="US$ 860,00 por equipo",
       precio_usd=860.0, precio_puntual=1, usar_en_ajuste=1, potencia_kw=1.1, largo_m=0.45, ancho_m=0.40, alto_m=1.35, peso_kg=65.0,
       material="Acero inoxidable 304", garantia_meses=12.0, plazo_entrega_semanas=4.3,
       confiabilidad_texto="Certificados CE e ISO 9001, proveedor auditado por BV (la página). " + _SIN_MTBF,
       nota="Otro listado del mismo proveedor y modelo (HdPaTtzxvyrV) publica US$ 960: el precio varía entre listados. Plazo: un mes en temporada alta."),
    _f("trituradora", "medio", "Henan Topp Machinery Co., Ltd.", "TPP-PS5", 5.0, "t/h",
       "https://toppmachine.en.made-in-china.com/product/HdPaTtzxvyrV/China-Tomato-Crusher-Carrot-Crushing-Machine-Vegetable-Fruit-Crusher.html",
       nombre_pagina="Tomato Crusher Carrot Crushing Machine Vegetable Fruit Crusher", proveedor=MC,
       precio_texto="Sin dato para este modelo: el único precio de la página (US$ 960) es del TPP-PS1", potencia_kw=5.5, largo_m=0.55,
       ancho_m=0.47, alto_m=1.55, peso_kg=105.0, material="Acero inoxidable 304", garantia_meses=12.0, confiabilidad_texto=_SIN_MTBF,
       nota="Datos de la tabla de parámetros de la página."),
    _f("trituradora", "maximo", "Henan Topp Machinery Co., Ltd.", "TPP-PS10", 10.0, "t/h",
       "https://toppmachine.en.made-in-china.com/product/HdPaTtzxvyrV/China-Tomato-Crusher-Carrot-Crushing-Machine-Vegetable-Fruit-Crusher.html",
       nombre_pagina="Tomato Crusher Carrot Crushing Machine Vegetable Fruit Crusher", proveedor=MC,
       precio_texto="Sin dato para este modelo", potencia_kw=7.5, largo_m=0.70, ancho_m=0.60, alto_m=1.60, peso_kg=160.0,
       material="Acero inoxidable 304", garantia_meses=12.0, confiabilidad_texto=_SIN_MTBF,
       nota="La página da 7 a 10 t/h; se usa el extremo superior."),
    _f("trituradora", "adicional", "Shanghai Benyoud Machinery Group Co., Ltd.", "BYFC (FHJ-10, FHJ-15, FHJ-20)", 20.0, "t/h",
       "https://beyond-machinery.en.made-in-china.com/product/RZhGOFnJAsWu/China-Fruit-crusher-machine-industrial-stainless-steel-tomato-crusher-machine.html",
       nombre_pagina="Fruit crusher machine industrial stainless steel tomato crusher machine", proveedor=MC,
       precio_texto="US$ 25.000 por pieza (precio único del listado, no por modelo)", potencia_kw=37.0, largo_m=2.05, ancho_m=1.15,
       alto_m=1.65, material="Acero inoxidable 304 o 316L", garantia_meses=12.0, plazo_entrega_semanas=4.3, confiabilidad_texto=_SIN_MTBF,
       nota="Página contradictoria: capacidad «5-20TPH» en la ficha, «1-5 t/h» en la descripción y 10, 45 y 55 T/H en la tabla (con "
            "potencias de 37, 45 y 55 kW). Se toma 20 t/h; la potencia es la del FHJ-10."),

    # ------------------------------------------------------------------ refinadora o despulpadora (t/h)
    _f("refinadora", "minimo", "Antler Automation Equipment (Suzhou) Co., Ltd.", "DJJ-1", 500.0, "kg/h",
       "https://antlermachine.en.made-in-china.com/product/htYULRcVVgWp/China-Fruit-Seed-Separation-Equipment-Automatic-Tomato-Pulp-Machine.html",
       nombre_pagina="Fruit Seed Separation Equipment Automatic Tomato Pulp Machine", proveedor=MC, precio_texto="US$ 4.000,00 por equipo",
       precio_usd=4000.0, precio_puntual=1, usar_en_ajuste=1, potencia_kw=1.5, peso_kg=270.0, material="Acero inoxidable 304",
       garantia_meses=12.0, confiabilidad_texto="Certificados ISO 9001 y CE (la página). " + _SIN_MTBF,
       nota="La ficha lista 500 a 5.000 kg/h sin asignarlos a modelos; se usa el de la ficha básica (500 kg/h). La garantía es de 1 año en la "
            "ficha y de 2 años en las preguntas frecuentes. Peso 270 kg contra 150 kg de embalaje: dato dudoso."),
    _f("refinadora", "medio", "Zhengzhou Hento Machinery Co., Ltd.", "HT-DJ2-4.0 (doble canal)", 4.0, "t/h",
       "https://zzhento.en.made-in-china.com/product/IKMEVOxdkLhF/China-High-Efficiency-Fruit-Pulp-Machine-Tomato-Paste-Pulper-Mango-Pulping-Machine.html",
       nombre_pagina="High Efficiency Fruit Pulp Machine / Tomato Paste Pulper / Mango Pulping Machine", proveedor=MC,
       precio_texto="US$ 1.625 (1 a 9 equipos), US$ 1.500 (10 a 49), US$ 1.250 (50 o más): precio del listado, no por modelo",
       potencia_kw=7.5, largo_m=1.51, ancho_m=1.48, alto_m=1.53, material="Acero inoxidable 304 en las partes en contacto",
       garantia_meses=24.0, plazo_entrega_semanas=3.0,
       confiabilidad_texto="Proveedor auditado por SGS; «Every machine has to be tested before delivery» (proveedor). " + _SIN_MTBF,
       nota="Plazo de 15 días hábiles."),
    _f("refinadora", "maximo", "Zhengzhou Hento Machinery Co., Ltd.", "HT-DJ3-7.5 (triple canal)", 7.5, "t/h",
       "https://zzhento.en.made-in-china.com/product/IKMEVOxdkLhF/China-High-Efficiency-Fruit-Pulp-Machine-Tomato-Paste-Pulper-Mango-Pulping-Machine.html",
       nombre_pagina="High Efficiency Fruit Pulp Machine / Tomato Paste Pulper / Mango Pulping Machine", proveedor=MC,
       precio_texto="Mismo precio de listado que el modelo medio: no es del HT-DJ3-7.5", potencia_kw=18.5, largo_m=1.935, ancho_m=2.275,
       alto_m=1.70, material="Acero inoxidable 304 en las partes en contacto", garantia_meses=24.0, plazo_entrega_semanas=3.0,
       confiabilidad_texto=_SIN_MTBF, nota="Peso: sin dato (solo el bruto de embalaje del modelo menor)."),

    # ------------------------------------------------------------------ hot break (kW térmicos = t/h × 71,9 kW por t/h)
    _f("hot_break", "minimo", "Shanghai ChenFei Machinery Technology Co., Ltd.", "Customized (precalentador hot break, sin número de modelo)", 2.0, "t/h",
       "https://cfmachine.en.made-in-china.com/product/vygEdUkbMFhl/China-Tomato-Paste-Pre-Heater-Pre-heater-Equipment-Thermo-break-or-hot-break-.html",
       nombre_pagina="Tomato Paste Pre-Heater (Pre-heater Equipment, Thermo break or hot-break)", proveedor=MC,
       precio_texto="US$ 14.000,00 por pieza", precio_usd=14000.0, precio_puntual=1, usar_en_ajuste=1, potencia_kw=2.2, material="Acero inoxidable 304",
       confiabilidad_texto="Ingenieros disponibles para servicio en el exterior (proveedor). " + _SIN_MTBF,
       nota="Consumo de vapor, dimensiones, peso, garantía y plazo: sin dato (la ficha dice «Customized»). Faltan el tamaño medio y el máximo."),
    _f("hot_break", "adicional", "Manzini", "UHV-30 (hot break usado, inox)", None, "t/h",
       "https://www.machineseeker.nz/manzini-uhv-30/i-19256401", proveedor="machineseeker.nz, Lorquí (España)", precio_texto="«Call»: sin precio publicado",
       material="Acero inoxidable", confiabilidad_texto="Usado, «excelente» y «completamente funcional» (el vendedor). " + _SIN_MTBF,
       nota="Capacidad, año, potencia y medidas: sin dato en la página."),

    # ------------------------------------------------------------------ esterilizador tubular (kW térmicos = t/h × 44,5 kW por t/h)
    _f("esterilizador", "minimo", "Shanghai Benyoud Machinery Group Co., Ltd.", "TG-UHT-1.5", 1500.0, "L/h",
       "https://beyond-machinery.en.made-in-china.com/product/DCdQqlgcHxkE/China-tube-in-tube-sterilizer-for-tomato-paste-sterilizing.html",
       nombre_pagina="tube-in-tube sterilizer for tomato paste sterilizing", proveedor=MC,
       precio_texto="US$ 25.000 por pieza (precio único del listado para TG-UHT-1.5, 3 y 5, no por modelo)", largo_m=7.0, ancho_m=2.0,
       alto_m=2.0, peso_kg=1700.0, material="Acero inoxidable", plazo_entrega_semanas=13.0,
       mtbf_h=439.2, mttr_h=0.5, confiabilidad_texto="«The system is of high reliable»; control de temperatura de ±0,5 °C; proveedor auditado por SGS. " + _SIN_FAB + _LIT_ESTER,
       nota="Vapor 150 kg/h a 0,5 MPa. Potencia eléctrica y garantía: sin dato. Plazo de 1 a 3 meses."),
    _f("esterilizador", "medio", "Shanghai Benyoud Machinery Group Co., Ltd.", "TG-UHT-3", 3000.0, "L/h",
       "https://beyond-machinery.en.made-in-china.com/product/DCdQqlgcHxkE/China-tube-in-tube-sterilizer-for-tomato-paste-sterilizing.html",
       nombre_pagina="tube-in-tube sterilizer for tomato paste sterilizing", proveedor=MC,
       precio_texto="US$ 25.000 por pieza (precio único del listado, no por modelo)", largo_m=7.0, ancho_m=2.0, alto_m=2.0, peso_kg=2000.0,
       material="Acero inoxidable", plazo_entrega_semanas=13.0, mtbf_h=439.2, mttr_h=0.5, confiabilidad_texto=_SIN_FAB + _LIT_ESTER, nota="Vapor 210 kg/h a 0,5 MPa."),
    _f("esterilizador", "maximo", "Shanghai Benyoud Machinery Group Co., Ltd.", "TG-UHT-5", 5000.0, "L/h",
       "https://beyond-machinery.en.made-in-china.com/product/DCdQqlgcHxkE/China-tube-in-tube-sterilizer-for-tomato-paste-sterilizing.html",
       nombre_pagina="tube-in-tube sterilizer for tomato paste sterilizing", proveedor=MC,
       precio_texto="US$ 25.000 por pieza (precio único del listado, no por modelo)", largo_m=7.0, ancho_m=2.0, alto_m=2.2, peso_kg=2200.0,
       material="Acero inoxidable", plazo_entrega_semanas=13.0, mtbf_h=439.2, mttr_h=0.5, confiabilidad_texto=_SIN_FAB + _LIT_ESTER, nota="Vapor 280 kg/h a 0,5 MPa."),
    _f("esterilizador", "adicional", "Shanghai ChenFei Machinery Technology Co., Ltd.", "CFM-01 (esterilizador tubular UHT)", 2.0, "t/h",
       "https://cfmachine.en.made-in-china.com/product/mChQbaEoCdcy/China-Apple-Juice-Beverage-Stainless-Steel-Uht-Tube-Sterilizer.html",
       nombre_pagina="Apple Juice Beverage Stainless Steel Uht Tube Sterilizer", proveedor=MC,
       precio_texto="US$ 20.000-100.000 por pieza: rango del listado", potencia_kw=9.0, peso_kg=600.0, material="Acero inoxidable 304",
       garantia_meses=12.0, mtbf_h=439.2, mttr_h=0.5, confiabilidad_texto="Certificados CE e ISO 9001; «equipment stability relatively high» (proveedor). " + _SIN_FAB + _LIT_ESTER,
       nota="Potencia escrita como «9kw» bajo el rótulo «Power(W)»: dato dudoso."),

    # ------------------------------------------------------------------ evaporador de múltiple efecto (kg/h de agua evaporada)
    _f("evaporador_multiefecto", "minimo", "Zhejiang Shuangzi Intelligent Equipment Co., Ltd.", "SJM2-800 (doble efecto)", 600.0, "kg/h",
       "https://zjshuangzi.en.made-in-china.com/product/AfCUhGJDqPkq/China-New-Arrivals-2024-Products-Falling-Film-Evaporators-Double-Effect-Evaporator-for-Tomato-Paste-Making-Machine.html",
       nombre_pagina="Falling Film Evaporators Double Effect Evaporator for Tomato Paste Making Machine", proveedor=MC,
       precio_texto="US$ 20.000-50.000 por pieza: rango de la serie SJM2-800 a SJM2-2500, no por modelo", potencia_kw=18.0, largo_m=4.5,
       ancho_m=2.3, alto_m=7.1, material="Acero inoxidable SUS304 o SUS316L", garantia_meses=12.0, plazo_entrega_semanas=13.0,
       confiabilidad_texto="Auditoría TÜV Rheinland, certificados CE y ASME (la página). " + _SIN_MTBF,
       nota="Evaporación 600 kg/h y vapor 390 kg/h. Peso: sin dato (solo bruto de embalaje, 5.000 kg para la serie)."),
    _f("evaporador_multiefecto", "medio", "Beijing Meckey Engineering Co.", "MKFE-20", 20000.0, "kg/h",
       "https://cnmeckey.en.made-in-china.com/product/pXvJGWUggqRy/China-Multiple-Effect-Industrial-Falling-Film-Evaporator.html",
       nombre_pagina="Multiple Effect Industrial Falling Film Evaporator", proveedor=MC,
       precio_texto="US$ 100.000-650.000 por equipo: rango de la serie MKFE-3 a MKFE-60, no por modelo", garantia_meses=12.0,
       plazo_entrega_semanas=26.0, confiabilidad_texto="Certificado CE; auditoría SGS (la página). " + _SIN_MTBF,
       nota="Vapor 4.200 kg/h. Potencia, dimensiones, peso y material: sin dato. Plazo de 3 a 6 meses en temporada baja."),
    _f("evaporador_multiefecto", "maximo", "Beijing Meckey Engineering Co.", "MKFE-60", 60000.0, "kg/h",
       "https://cnmeckey.en.made-in-china.com/product/pXvJGWUggqRy/China-Multiple-Effect-Industrial-Falling-Film-Evaporator.html",
       nombre_pagina="Multiple Effect Industrial Falling Film Evaporator", proveedor=MC,
       precio_texto="US$ 100.000-650.000 por equipo: rango de la serie, no por modelo", garantia_meses=12.0, plazo_entrega_semanas=52.0,
       confiabilidad_texto="Certificado CE; auditoría SGS (la página). " + _SIN_MTBF,
       nota="Vapor 12.000 kg/h (0,2 kg de vapor por kg evaporado). Plazo de 6 a 12 meses en temporada alta."),

    # ------------------------------------------------------------------ evaporador MVR (kg/h)
    _f("evaporador_mvr", "minimo", "Qingdao Conqinphi Environmental Technology Group Co., Ltd.", "KJH-JUI-8410", 500.0, "kg/h",
       "https://mvrevaporator.en.made-in-china.com/product/KfHRDgUYvlre/China-Mvr-Evaporator-for-Fruit-Juice-Tomato-Paste-Concentrated.html",
       nombre_pagina="Mvr Evaporator for Fruit Juice Tomato Paste Concentrated", proveedor=MC,
       precio_texto="US$ 16.500-96.600 por pieza: rango del listado (un solo modelo, sin precio por configuración)",
       material="Titanio, acero inoxidable y acero al carbono", garantia_meses=12.0, plazo_entrega_semanas=14.3,
       confiabilidad_texto="«High degree of automation and excellent stability, but requires regular compressor maintenance» (proveedor). " + _SIN_MTBF,
       nota="La página da «Processing Capacity ≥0.5 t/H», que no es evaporación: se usa como cota inferior de 500 kg/h. Potencia «690kw/H» con "
            "unidad ambigua, no se usa. Plazo de entrega 100 días. Faltan el tamaño medio y el máximo."),

    # ------------------------------------------------------------------ lavado y selección (lavadora de burbujas de aire, t/h)
    _f("recepcion_seleccion", "minimo", "Zhengzhou Angtuo Machinery Equipment Co., Ltd.", "ATQP-2500", 500.0, "kg/h",
       "https://atmachine.en.made-in-china.com/product/HwDfqlrPnFUo/China-Air-Bubble-Washer-Tomato-Apple-Cleaning-Washer-Vegetable-Fruit-Washing-Machine.html",
       nombre_pagina="Air Bubble Washer Tomato Apple Cleaning Washer Vegetable Fruit Washing Machine", proveedor=MC,
       precio_texto="US$ 3.250 (1 a 4 equipos), US$ 2.880 (5 a 9), US$ 2.550 (10 o más): precio del listado, no por modelo",
       potencia_kw=3.75, largo_m=2.5, ancho_m=1.0, alto_m=1.3, peso_kg=250.0, material="Acero inoxidable SS304",
       garantia_meses=24.0, plazo_entrega_semanas=3.0, confiabilidad_texto=_SIN_MTBF,
       nota="Garantía de 2 años en la ficha y de 1 año en las preguntas frecuentes. Plazo de 15 días hábiles."),
    _f("recepcion_seleccion", "medio", "Zhengzhou Angtuo Machinery Equipment Co., Ltd.", "ATQP-5000", 1500.0, "kg/h",
       "https://atmachine.en.made-in-china.com/product/HwDfqlrPnFUo/China-Air-Bubble-Washer-Tomato-Apple-Cleaning-Washer-Vegetable-Fruit-Washing-Machine.html",
       nombre_pagina="Air Bubble Washer Tomato Apple Cleaning Washer Vegetable Fruit Washing Machine", proveedor=MC,
       precio_texto="Mismo precio de listado: no es del ATQP-5000", potencia_kw=5.1, largo_m=5.0, ancho_m=1.2, alto_m=1.3, peso_kg=500.0,
       material="Acero inoxidable SS304", garantia_meses=24.0, plazo_entrega_semanas=3.0, confiabilidad_texto=_SIN_MTBF),
    _f("recepcion_seleccion", "maximo", "Zhengzhou Angtuo Machinery Equipment Co., Ltd.", "ATQP-6000", 2000.0, "kg/h",
       "https://atmachine.en.made-in-china.com/product/HwDfqlrPnFUo/China-Air-Bubble-Washer-Tomato-Apple-Cleaning-Washer-Vegetable-Fruit-Washing-Machine.html",
       nombre_pagina="Air Bubble Washer Tomato Apple Cleaning Washer Vegetable Fruit Washing Machine", proveedor=MC,
       precio_texto="Mismo precio de listado: no es del ATQP-6000", potencia_kw=5.5, largo_m=6.0, ancho_m=1.2, alto_m=1.3, peso_kg=600.0,
       material="Acero inoxidable SS304", garantia_meses=24.0, plazo_entrega_semanas=3.0, confiabilidad_texto=_SIN_MTBF),
    _f("recepcion_seleccion", "adicional", "Qingdao Tune Machinery Co., Ltd.", "Industrial Vegetable Air Bubble Washing Machine (300 a 5.000 kg/h)",
       5000.0, "kg/h",
       "https://qdtune.en.made-in-china.com/product/kKsxpYXyhirJ/China-Industrial-Vegetable-Air-Bubble-Washing-Machine-Fruit-Washing-Machine-Tomato-Washing-Machine.html",
       nombre_pagina="Industrial Vegetable Air Bubble Washing Machine Fruit Washing Machine Tomato Washing Machine", proveedor=MC,
       precio_texto="US$ 3.000-20.000 por pieza: rango del listado", potencia_kw=1.5, largo_m=2.6, ancho_m=0.88, alto_m=1.0,
       material="Acero inoxidable 304", plazo_entrega_semanas=4.3, confiabilidad_texto=_SIN_MTBF,
       nota="La capacidad más grande de la ficha es 5.000 kg/h; potencia y medidas son las de la ficha básica."),

    # ------------------------------------------------------------------ estanque pulmón de acero inoxidable (m3)
    _f("estanque_pulmon", "minimo", "Wenzhou Xusheng Machinery Industry and Trading Co., Ltd.", "TANK027 (300 L, camisa doble)", 300.0, "L",
       "https://xushengvalves.en.made-in-china.com/product/cnmUKweOETkN/China-Stainless-Steel-Sanitary-Steam-Electrical-Heating-and-Cooling-Double-Jacket-Storage-Tank.html",
       nombre_pagina="300L SS304 Food Grade Stainless Steel Sanitary Steam Heating and Water Cooling Double Jacketed Storage Mixing Tank",
       proveedor=MC, precio_texto="US$ 3.000 (1 a 49 piezas), US$ 2.800 (50 a 99), US$ 2.100 (100 a 499), US$ 1.500 (500 o más)",
       precio_usd=3000.0, precio_puntual=1, usar_en_ajuste=1, largo_m=0.8, ancho_m=0.8, alto_m=1.195, material="Acero inoxidable SS304 o SS316L",
       garantia_meses=12.0, plazo_entrega_semanas=1.0, confiabilidad_texto="Garantía de un año, sin piezas de desgaste. " + _SIN_MTBF,
       nota="Diámetro 800 mm y altura 1.195 mm (tabla de 300 L). Peso bruto de embalaje 150 kg. La página es inconsistente (precio de la "
            "metaetiqueta US$ 1.500 y pedido mínimo 50); se toma el precio de 1 a 49 piezas."),
    _f("estanque_pulmon", "medio", "Guangzhou Ailusi Machinery Co., Ltd.", "Ast 1000 L (tanque de agua de acero inoxidable)", 1000.0, "L",
       "https://ailusi.en.made-in-china.com/product/omJpbaROahck/China-1000-Liter-to-5000-Liter-Stainless-Steel-Water-Storage-Tanks-with-Water-Filter-Vessels-for-Storing-Pure-Water.html",
       nombre_pagina="1000 Liter to 5000 Liter Stainless Steel Water Storage Tanks with Water Filter Vessels for Storing Pure Water",
       proveedor=MC, precio_texto="US$ 550-1.300 por equipo: rango del listado de 1.000 a 5.000 L, no por tamaño",
       material="Acero inoxidable SUS304 o SUS316L", garantia_meses=12.0, plazo_entrega_semanas=3.0, confiabilidad_texto=_SIN_MTBF,
       nota="Tanque de agua sin camisa. Plazo de 10 a 20 días en cantidades chicas."),
    _f("estanque_pulmon", "maximo", "Guangzhou Ailusi Machinery Co., Ltd.", "Ast 5000 L (tanque de agua de acero inoxidable)", 5000.0, "L",
       "https://ailusi.en.made-in-china.com/product/omJpbaROahck/China-1000-Liter-to-5000-Liter-Stainless-Steel-Water-Storage-Tanks-with-Water-Filter-Vessels-for-Storing-Pure-Water.html",
       nombre_pagina="1000 Liter to 5000 Liter Stainless Steel Water Storage Tanks with Water Filter Vessels for Storing Pure Water",
       proveedor=MC, precio_texto="US$ 550-1.300 por equipo: rango del listado, no por tamaño", material="Acero inoxidable SUS304 o SUS316L",
       garantia_meses=12.0, plazo_entrega_semanas=4.3, confiabilidad_texto=_SIN_MTBF,
       nota="Tamaño máximo del listado (5.000 L); la página dice que fabrica de 50 L a 20 t. Plazo de unos 30 días en cantidades grandes."),

    # ------------------------------------------------------------------ llenadora aséptica (t/h)
    _f("llenadora_aseptica", "minimo", "Manzini", "F-20 (llenadora aséptica usada)", 10000.0, "L/h",
       "https://maquinariatomasguillen.com/en/products/fillers-dosers/aseptic/s-s-manzini-f20-aseptic-filler", proveedor="maquinariatomasguillen.com",
       precio_texto="«Request a quote»: sin precio publicado", largo_m=4.2, alto_m=4.3, material="Acero inoxidable",
       mtbf_h=132.0, mttr_h=1.0, confiabilidad_texto="Usada, «excelente condición» (el vendedor). " + _SIN_FAB + _LIT_LLEN,
       nota="Ancho y peso: sin dato (la página trae 0 como relleno). Faltan el tamaño medio y el máximo, y todos los precios."),

    # ------------------------------------------------------------------ enfriamiento flash al vacío (t/h)
    _f("enfriamiento_flash", "minimo", "Wenzhou Longwan Wanyuan Food Machinery Factory", "WY-05 (desaireador al vacío, equipo afín)", 5.0, "t/h",
       "https://wanyuanqiye.en.made-in-china.com/product/HKZxYnXlaRhf/China-Fruit-Juice-Vacuum-Deaerator-Vacuum-Degasser.html",
       nombre_pagina="Fruit Juice Vacuum Deaerator Vacuum Degasser", proveedor=MC,
       precio_texto="US$ 1.600-3.500 por pieza: rango del listado (un solo modelo)", potencia_kw=5.5, largo_m=1.8, ancho_m=1.0, alto_m=2.5,
       material="Acero inoxidable SUS304 de 3 mm", plazo_entrega_semanas=13.0,
       confiabilidad_texto="Auditoría TÜV Rheinland, certificado CE (la página). " + _SIN_MTBF,
       nota="Es un desaireador al vacío, no un enfriador flash: se guarda como equipo afín. La ficha da 5 t/h en la tabla y 500 L/h en la "
            "descripción (contradicción). Vacío de 6,4 a 8,7 x 10^4 Pa. Faltan los otros dos tamaños."),

    # ------------------------------------------------------------------ ampliación del 16-11-2026 (fecha_consulta 2026-11-16)
    # caldera a gas usada, tres precios puntuales de Revelation Machinery (no entran al ajuste: edades de 2021, 2005 y 1965)
    _f("caldera_gas", "adicional", "Fulton Steam Solutions, Inc.", "FC80 (caldera vertical a gas, 800.000 BTU/h)", 234.457, "kW",
       "https://revelationmachinery.com/product/fulton-fc80-gas-fired-vertical-steam-boiler-system-800000-btu-hr-100-psi-2021-build-ul-certified/",
       proveedor=RM, precio_texto="US$ 79.900 (la página escribe $79,900.00 sin nombrar la moneda; se lee como dólar)", precio_usd=79900.0,
       precio_puntual=1, usar_en_ajuste=0, fecha_consulta=FECHA2, mttr_h=2.06,
       confiabilidad_texto=_SIN_FAB + _LIT_CALD,
       nota="Usada: la página la llama «late-model» y «still in place», año 2021. Caldera vertical de 800.000 BTU/h hasta 100 psi; "
            "800.000 BTU/h x 0,000293071 = 234,457 kW. La página no dice si son BTU/h de entrada o de salida ni da caudal de vapor. No "
            "entra al ajuste: precio de equipo usado de otra edad y tecnología que los otros dos de esta tabla."),
    _f("caldera_gas", "adicional", "Hurst", "Caldera de vapor de baja presión de 125 hp (2005)", 3.1298, "t/h vapor",
       "https://revelationmachinery.com/product/125-hp-hurst-low-pressure-steam-boiler-2005/",
       proveedor=RM, precio_texto="US$ 19.900 (la página escribe $19,900.00 sin nombrar la moneda; se lee como dólar)", precio_usd=19900.0,
       precio_puntual=1, usar_en_ajuste=0, fecha_consulta=FECHA2, largo_m=4.369, ancho_m=2.286, alto_m=2.388, mttr_h=2.06,
       confiabilidad_texto=_SIN_FAB + _LIT_CALD,
       nota="Usada, año 2005. Vapor de 6.900 lb/h x 0,453592 = 3.129,8 kg/h, que es la cifra explícita de la página; la misma página dice "
            "125 hp, que a 34,5 lb/h por hp serían unas 4.300 lb/h: inconsistencia sin resolver (con 125 hp la capacidad sería 1,96 t/h). "
            "Medidas 172 x 90 x 94 in (largo, ancho con accesorios, alto). No entra al ajuste: equipo usado de otra edad."),
    _f("caldera_gas", "adicional", "Orr & Sembower", "3HG (caldera pirotubular de 350 hp, 1965)", 3433.74, "kW",
       "https://revelationmachinery.com/product/350-hp-orr-sembower-3hg-natural-gas-boiler-1965/",
       proveedor=RM, precio_texto="US$ 17.900 (la página escribe $17,900.00 sin nombrar la moneda; se lee como dólar)", precio_usd=17900.0,
       precio_puntual=1, usar_en_ajuste=0, fecha_consulta=FECHA2, mttr_h=2.06,
       confiabilidad_texto=_SIN_FAB + _LIT_CALD,
       nota="Usada, año 1965, tres pasos, a gas natural. Capacidad de la página 11.716.250 BTU/h (350 hp): x 0,000293071 = 3.433,74 kW; "
            "no da caudal de vapor. Precio de equipo de 61 años: no es comparable con uno nuevo y no entra al ajuste."),
    # evaporador multiefecto usado de Revelation Machinery
    _f("evaporador_multiefecto", "adicional", "Buflovac / Hebeler", "12-04878 (doble efecto, película ascendente y descendente, 2017)",
       1877.8, "kg/h",
       "https://revelationmachinery.com/product/buflovac-hebeler-12-04878-double-effect-rising-falling-film-evaporator-system-2017-6500-lb-hr-316l-ss-food-protein-concentrator/",
       proveedor=RM, precio_texto="US$ 329.900 (la página escribe $329,900.00 sin nombrar la moneda; se lee como dólar)", precio_usd=329900.0,
       precio_puntual=1, usar_en_ajuste=0, fecha_consulta=FECHA2,
       material="316L en las piezas en contacto con el producto; 304L en servicios y estructura",
       confiabilidad_texto=_SIN_MTBF + ". Sin cifras de literatura abiertas para evaporadores de este tipo (consultado el 2026-11-16).",
       nota="Evaporación de 4.140 lb/h de agua x 0,453592 = 1.877,8 kg/h; alimentación 6.500 lb/h al 15 % de sólidos y concentrado de 2.360 lb/h "
            "al 41 %. Alimentación inversa. El único motor que da la página es la bomba de vacío de 7,5 hp (SIHI), sin potencia total. La "
            "página lo describe para suspensiones hidrolizadas y proteínas, no tomate; condición no dicha. No entra al ajuste: es un "
            "equipo de otro servicio y de reventa, distinto del catálogo nuevo del resto del tipo."),
    _f("evaporador_multiefecto", "adicional", "Thermohran Engineering Ltd. (Bulgaria)",
       "T215 (evaporador de pasta de tomate y puré de fruta, usado, 1998)", None, "kg/h",
       "https://www.machineseeker-india.com/thermohran+engineering+ltd.-t215/i-22171377",
       proveedor="machineseeker-india.com (vendedor sin nombre, Isperih, Bulgaria)",
       precio_texto="€ 125.000 (la página escribe «€1,25,000» con agrupación india de miles; precio fijo más IVA, EXW)", precio_usd=None,
       moneda="EUR", precio_puntual=0, usar_en_ajuste=0, fecha_consulta=FECHA2,
       confiabilidad_texto=_SIN_MTBF + ". Usado, «completamente funcional» y «excelente» (el vendedor); 6.000 h de operación.",
       nota="Capacidad de la línea: 150 t de tomate por 24 h y 1.000 kg/h de producto a 28-30 °Brix; la página no da la evaporación en "
            "kg/h, por eso la capacidad queda sin dato. Año 1998. El precio está en euros y no se convierte a dólares (sin tipo de cambio de la "
            "fecha), por eso no es precio puntual en US$."),
    # evaporador MVR
    _f("evaporador_mvr", "adicional", "Zhejiang Shuangzi Intelligent Equipment Co., Ltd.",
       "Full-Automatic Fall Film Honey MVR Evaporation System (1000 L/H)", 1000.0, "L/h",
       "https://www.madeinchina.com/mall/show-Full-Automatic-Fall-Film-Honey-Mvr-Evaporation-System_288879.html",
       nombre_pagina="Full-Automatic Fall Film Honey Mvr Evaporation System",
       proveedor="Proveedor de madeinchina.com (Zhejiang, China); la página no dice si es fabricante o comercializador",
       precio_texto="US$ 30.000 por pieza (precio único, pedido mínimo de 1)", precio_usd=30000.0, precio_puntual=1, usar_en_ajuste=1,
       fecha_consulta=FECHA2, material="Acero inoxidable", garantia_meses=12.0,
       confiabilidad_texto=_SIN_MTBF + ". Garantía de calidad de un año (la página). Sin cifras de literatura abiertas para MVR "
                           "(consultado el 2026-11-16).",
       nota="Capacidad 1000 L/h del nombre del modelo (a kg/h con densidad 1, Supuesto); la columna de evaporación de la ficha viene vacía. "
            "«25-35 kW para evaporar» sin unidad clara y «3000 kg» sin rótulo: no se usan. Es un sistema general: el título dice miel y la "
            "ficha no menciona tomate. Único punto con precio de este tipo: el ajuste usa el exponente de costeo.py."),
    # esterilizador tubular
    _f("esterilizador", "adicional", "Suzhou Ellison Packing Machinery Co., Ltd.", "UHT (esterilizador tubular de 6.000 L/h)", 6000.0, "L/h",
       "https://www.madeinchina.com/mall/show-Stainless-Steel-Tubular-Sterilizer-Machine-Fruit-Juice-Pasteurized-Machine-Uht-Sterilizer-Equipment_978489.html",
       nombre_pagina="Stainless Steel Tubular Sterilizer Machine/ Fruit Juice Pasteurized Machine / Uht Sterilizer Equipment",
       proveedor="Proveedor de madeinchina.com (Jiangsu, China); la página no dice si es fabricante o comercializador",
       precio_texto="US$ 11.000 por pieza (precio único, pedido mínimo de 1)", precio_usd=11000.0, precio_puntual=1, usar_en_ajuste=1,
       fecha_consulta=FECHA2, potencia_kw=10.2, material="Acero inoxidable SUS304/316",
       mtbf_h=439.2, mttr_h=0.5, confiabilidad_texto=_SIN_FAB + _LIT_ESTER,
       nota="La ficha dice 1000-10000 L/h; se usa el caudal de 6.000 L/h de la tabla técnica (para jugo de fruta). Vapor 420 kg/h a 4 bar o "
            "más; esterilización a 95-105 °C por 30 s. Modelo «UHT» sin número. Garantía y plazo: sin dato. Único punto con precio de "
            "este tipo: el ajuste usa el exponente de costeo.py."),
]
