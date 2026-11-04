"""PAT 134 (04-11-2026, pedido de Jaime): un «?» en cada tabla de la aplicación, junto a su título, con tres partes cortas:
cómo se hace (de dónde salen los datos y cómo se calcula cada columna, con la fuente que ya cita el código), para qué sirve
y por qué importa en el proyecto (recuperación de calor en la planta de pasta de tomate y en los rubros de biomasa).
Las fuentes son solo las que ya están en el motor o en los supuestos; donde no hay, se explica el cálculo sin cita.
Uso: AT.tabla("clave", "Título", nivel, dg=columna, antes="nota previa", **valores para el texto)."""
from __future__ import annotations
from . import comun as C


def _t(como: str, para: str, por: str) -> str:
    return f"**Cómo se hace.** {como}\n\n**Para qué sirve.** {para}\n\n**Por qué importa.** {por}"


TEXTOS = {
    # ------------------------------------------------------------------------------------------------ Escenario
    "esc_proyectos": _t(
        "Lista de los proyectos de la base de datos SQLite local de la aplicación: nombre, rubro, número de versiones guardadas y fecha "
        "de la última modificación. Cada «Guardar» agrega una versión; aquí no se calcula nada.",
        "Elegir y recuperar una versión anterior de la planta con los selectores de abajo.",
        "El estudio compara la planta basada en Agrozzi con sus variantes y con los rubros de biomasa; guardar versiones deja la traza "
        "de cada caso evaluado y permite volver a la planta base del Capítulo 1."),
    "dp_cambios": _t(
        "Una fila por cada fila de la plantilla CSV que trae valor. «Antes» es el valor actual del parámetro con su categoría "
        "(Supuesto, literatura o fabricante) y «Medido» el valor leído con coma decimal; unidad, fuente, fecha y nota son las que usted "
        "escribió. Es una vista previa sobre una copia: la planta de la sesión no cambia hasta presionar «Aplicar».",
        "Revisar qué parámetros cambian y en cuánto antes de aplicarlos.",
        "Cada cifra del informe debe tener fuente y fecha; reemplazar supuestos por datos de placa o medidos baja la incertidumbre del "
        "calor recuperable y del ahorro de combustible, tanto en la planta de tomate como en la de biomasa."),
    "dp_rechazos": _t(
        "Filas de la plantilla que la validación no pudo aplicar, con el motivo que entrega el motor (motor/datos_planta.py): por ejemplo, "
        "un equipo o parámetro que no existe en la planta, un valor que no se lee como número o una fila repetida.",
        "Corregir esas filas en el CSV y volver a subirlo.",
        "Un dato medido que no entra deja el parámetro como Supuesto; conviene corregirlo para que el balance y la recuperación de calor "
        "usen el dato real."),
    "dp_medidos": _t(
        "Parámetros de la planta actual que tienen la categoría «Medido»: valor, unidad y la fuente con su fecha que se registraron al "
        "aplicarlos (desde la plantilla o desde el Excel de ida y vuelta).",
        "Ver de un vistazo qué datos de la planta ya no son supuestos.",
        "Separa lo medido de lo supuesto, como exige el informe del PAT: las conclusiones sobre el calor recuperable pesan más cuando "
        "descansan en datos medidos."),
    # ------------------------------------------------------------------------------------------------ Diseño
    "dis_corrientes": _t(
        "Una fila por conexión del diagrama, con el resultado del balance de la planta resuelta: caudal (kg/h) y temperatura de la "
        "corriente de salida del equipo de origen multiplicados por el reparto; °Brix en el jugo y la pasta, humedad en base húmeda en la "
        "biomasa (100 × (1 − fracción seca)) y, en las corrientes de servicio, el calor o vapor que consume el equipo de destino (kW).",
        "Leer el estado de cada corriente como en la tabla de corrientes de un diagrama de flujo ISO 10628; es la misma tabla del informe.",
        "Las corrientes calientes de esta tabla son la oferta de calor residual, y la corriente que se calienta, el sumidero; de ellas sale "
        "todo el cálculo de recuperación de calor en el tomate y en la biomasa."),
    "dis_capacidad": _t(
        "Por equipo: entrada y salida de proceso (t/h) del balance; capacidad nominal y estado son parámetros del equipo; capacidad efectiva = "
        "nominal × estado; procesado = mínimo entre la carga y la capacidad efectiva; utilización = carga / capacidad efectiva; acumulación = "
        "lo que llega sobre la capacidad efectiva; cierre de energía = energía que entra − energía que sale (kW). Como la tabla «Balance por "
        "equipo» del simulador del profesor.",
        "Encontrar el recurso crítico (mayor utilización) y las sobrecargas según la teoría de restricciones.",
        "El calor residual solo se recupera si la línea produce: un cuello de botella baja las horas y la carga efectiva, y con ellas el gas "
        "o la biomasa que la recuperación puede desplazar."),
    # ------------------------------------------------------------------------------------------------ Instrumentación
    "ins_lazos": _t(
        "Una fila por instrumento de la planta: identificación ISA-5.1 (letras y número), símbolo y ubicación (Carballo y Romero, 2011, "
        "Tablas 3, 4, 15 y 17), equipo, la lectura de las letras que arma el motor, la descripción, el parámetro del equipo que gobierna, el "
        "elemento final y las líneas de señal dibujadas en el lienzo.",
        "Revisar la lista de lazos del diagrama de cañerías e instrumentación sin abrir el lienzo.",
        "Los lazos de temperatura de los intercambiadores de recuperación y del calentamiento definen qué se puede controlar cuando el calor "
        "residual varía; sin ellos la recuperación no es operable."),
    "ins_senales": _t(
        "Líneas de señal del lazo elegido, tomadas del lienzo: instrumento de origen, tipo de señal según ISA-5.1, destino y parámetro del "
        "equipo que mueve la señal.",
        "Revisar que el lazo esté completo: medición, controlador y elemento final conectados.",
        "Un lazo cerrado sobre el calentamiento permite usar primero el calor recuperado y completar con la caldera o el generador solo lo "
        "que falta."),
    "ins_primera": _t(
        "Tabla de primeras letras de ISA-5.1 tal como la guarda el motor (pat_sim/normas/isa51): letra y variable medida (Carballo y Romero, "
        "2011).",
        "Leer o armar la identificación de un instrumento, por ejemplo la T de TIC.",
        "Nombrar bien los instrumentos de temperatura, presión y caudal deja el diagrama de la recuperación de calor legible para la planta."),
    "ins_sucesivas": _t(
        "Tabla de letras sucesivas de ISA-5.1 guardada en el motor: letra y función (indicador, controlador, transmisor y otras) (Carballo y "
        "Romero, 2011).",
        "Completar la identificación después de la primera letra.",
        "Distingue un instrumento que solo indica de uno que controla, clave para saber qué lazos actúan sobre el calor recuperado."),
    # ------------------------------------------------------------------------------------------------ Balances
    "bal_cierre": _t(
        "Para cada equipo, el motor suma la masa, los sólidos y la energía de todas sus entradas y salidas resueltas. Cierre = entra − sale; "
        "el estado es «Cierra» si los tres cierres quedan bajo la tolerancia elegida. Los sólidos del tomate entero no se modelan (el °Brix se "
        "fija en el jugo, a la salida de la refinadora); por eso esas celdas aparecen con una raya.",
        "Comprobar que el modelo conserva masa, sólidos y energía en cada equipo antes de usar sus números.",
        "La recuperación de calor se calcula con las corrientes de este balance: si un equipo no cierra, el calor residual y el ahorro de gas "
        "o de biomasa quedan mal estimados."),
    "bal_entra": _t(
        "Términos de energía que entran al equipo elegido (kW), tal como los entrega su cálculo en el motor: corrientes de proceso, vapor, "
        "combustible o electricidad.",
        "Ver de dónde viene la energía del equipo y cuánto aporta cada término.",
        "Muestra cuánto calor externo consume el equipo, que es lo que la recuperación puede reemplazar."),
    "bal_sale": _t(
        "Términos de energía que salen del equipo elegido (kW): productos, condensados, vahos, escapes y pérdidas, según su cálculo en el motor.",
        "Ver a dónde se va la energía y cuál es el calor que sale sin uso.",
        "Las salidas calientes que no se aprovechan son la oferta de calor residual del proyecto."),
    # ------------------------------------------------------------------------------------------------ Recuperación de calor
    "cal_mapa": _t(
        "Corrientes residuales calientes del balance de la propia planta (Capítulo 1). Calor sensible: Q = CP × (T de cesión − T final), con "
        "la T final de la pestaña; calor latente: Q es el calor de condensación a la T de cesión, sin CP.",
        "Reunir la oferta de calor residual que puede ir al sumidero.",
        "Es el punto de partida del proyecto: cuánto calor y a qué temperatura hay para precalentar el tomate o el aire de secado de la biomasa."),
    "cal_cascada": _t(
        "El sumidero pasa en serie por una etapa de intercambio por corriente, ordenadas por temperatura creciente (a igual techo, primero los "
        "condensados). Cada etapa: Q = mínimo entre el calor que cede la corriente sin bajar de T del sumidero + ΔTmin y CP del sumidero × "
        "(T de la corriente − ΔTmin − T de entrada); T de salida = T de entrada + Q / CP del sumidero (motor/recuperacion.py, mismo algoritmo "
        "del modelo Agrozzi).",
        "Ver cuánto aporta cada corriente y a qué temperatura queda el sumidero después de cada etapa.",
        "La cascada es la alternativa de recuperación que evalúa Economía por defecto; su calor fija el gas o la biomasa que se deja de quemar."),
    "cal_red": _t(
        "Red diseñada desde el *pinch* hacia afuera, sin pasar calor a través de él, con la regla de CP y el *tick-off* (Linnhoff y Hindmarsh, "
        "1983; Kemp, 2007, cap. 4). Por intercambiador: calor (kW), tramo del sumidero, temperaturas del lado caliente, LMTD, U de partida y "
        "área A = Q / (U × LMTD), en contracorriente pura y sin ensuciamiento. U: 850 W/m²K líquido contra tomate (Amon et al., 2015) y "
        "840 W/m²K vapor contra pulpa (Sangrame et al., 2000); en biomasa, 50 W/m²K gas contra aire (Supuesto).",
        "Pasar de la meta de energía del *pinch* a equipos concretos con su tamaño.",
        "El área de cada intercambiador define la inversión; es el puente entre el calor que se puede recuperar y lo que cuesta recuperarlo."),
    "cal_cop": _t(
        "Para cada COP de 1,5 a 5,0: electricidad de la bomba = calor del sumidero / COP y calor de baja temperatura que toma = calor del "
        "sumidero − electricidad.",
        "Ver cuánta electricidad pide una bomba de calor que cubra todo el sumidero y cuánto calor residual de baja temperatura necesita.",
        "La bomba de calor es la alternativa que cubre el 100 % del sumidero; se paga con electricidad en vez de gas o biomasa, y su "
        "conveniencia depende del COP."),
    "cal_agua": _t(
        "Masa de agua de cada corriente: con el CP o el calor latente del mapa de residuales y, en la biomasa, el agua que condensa el escape "
        "del secador bajo su punto de rocío. Agua por temporada = kg/h × horas de operación / 1.000 kg/m³ (densidad, Supuesto). Fuente: {fuente}.",
        "Estimar el agua que se puede reutilizar en lavado, limpieza o caldera, previo tratamiento.",
        "El condensado de la evaporación es agua del propio tomate; recuperar su calor y además su agua suma un beneficio al proyecto "
        "(Amon et al., 2015, analizan esa reutilización en una planta de pasta de tomate)."),
    # ------------------------------------------------------------------------------------------------ Alternativas
    "alt_comparacion": _t(
        "Las cuatro alternativas del Capítulo 3 con el balance actual. Calor (kW) y cobertura = calor / sumidero; equipos; área con U medio; "
        "inversión de Shamoushaki et al. (2021) actualizada con el PPI de septiembre de 2026 y factor de instalación 2,5 (Danish Energy Agency, "
        "2026), y bomba de calor a 1,20 MEUR por MW (Danish Energy Agency, 2026); U de Amon et al. (2015) y Sangrame et al. (2000){u_bio}. "
        "Precio de equilibrio: precio del combustible con VAN cero; VAN al precio de Economía después de impuesto (27 %) con depreciación lineal "
        "en 15 años (SII, Res. Ex. 43/2002), como en el Capítulo 4. Puntaje: suma ponderada con normalización por rango de cobertura, precio de "
        "equilibrio y equipos; «gana en el barrido» = % de las combinaciones de pesos (paso 0,01) en que la alternativa queda primera.",
        "Elegir la alternativa que evalúa la pestaña Economía con un criterio declarado y ver qué tan robusta es esa elección.",
        "Es la decisión central del proyecto: cuál forma de recuperar calor conviene en la planta de tomate o en la de biomasa."),
    "alt_etapas": _t(
        "Etapas de intercambio de la alternativa elegida: corriente, tipo, calor (kW), temperaturas de entrada y salida del lado frío y del "
        "caliente, LMTD = (ΔT1 − ΔT2) / ln(ΔT1 / ΔT2) y área media A = Q / (U × LMTD).",
        "Ver qué intercambiadores forman la alternativa y su tamaño.",
        "El área de cada etapa es la base de la inversión de la alternativa y, con ella, de su VAN."),
    # ------------------------------------------------------------------------------------------------ Economía
    "eco_gas": _t(
        "Para cada caso, el calor (kW) × horas de la temporada / eficiencia de la caldera (base PCS) da el gas en MWh; kg = kWh × 3,6 / PCS; "
        "m³ = kg / densidad; CO2 = kg × factor de emisión por kg; MMBtu = kWh / 293,071. Valor = MMBtu × precio (US$/MMBtu) × dólar / 10⁶, al "
        "Henry Hub ({hh}) y al precio elegido. Gas modelado como metano (Engineering ToolBox, 2003).",
        "Comparar el gas del caso base con el que ahorra cada forma de recuperar calor y con la brecha que queda.",
        "El ahorro de gas y el CO2 evitado son el beneficio que paga la inversión en recuperación de calor en la planta de pasta de tomate."),
    "eco_bomba": _t(
        "Para cada precio de la electricidad ({pmm}): precio del gas sobre el cual la bomba de calor que cubre todo el sumidero conviene más que "
        "la cascada = precio de la electricidad × eficiencia PCS / (COP × (1 − cobertura de la cascada)) × 293,071 / dólar. COP de la pestaña "
        "Recuperación de calor.",
        "Saber con qué precio del gas la bomba de calor le gana a la cascada.",
        "Muestra la frontera entre recuperar calor directo y electrificar el calentamiento, según los precios de la energía en Chile."),
    "eco_biomasa": _t(
        "Para cada caso, el calor (kW) × horas del año / eficiencia del generador da la biomasa en MWh PCI; masa húmeda = kWh × 3,6 / PCI húmedo; "
        "masa seca = húmeda × (1 − humedad); volumen = masa / densidad a granel; CO2 biogénico = masa seca × carbono × 44/12; valor = m³ × "
        "precio de la biomasa / 10⁶ ({bio}). El CO2 biogénico se informa aparte (IPCC, 2006, vol. 2, sec. 2.3.3.4).",
        "Comparar la biomasa del caso base con la que ahorra la recuperación y con la brecha que queda.",
        "En los rubros pellet, chip y leña el combustible es la biomasa: su ahorro es el beneficio que paga la recuperación de calor."),
    "rg_tornado": _t(
        "Cada supuesto (precio del combustible, dólar, tasa, inversión y fracción de recuperación) se lleva a su valor bajo y alto con los demás "
        "en el valor de la sesión y se recalcula el VAN de la cascada; amplitud = |VAN alto − VAN bajo|. Rangos en el «?» del Tornado "
        "(Capítulo 4, sección 4.7.7, y Supuestos declarados).",
        "Leer en números el gráfico de tornado y ordenar los supuestos por su efecto en el VAN.",
        "Indica qué dato conviene precisar primero para decidir la inversión en recuperación de calor."),
    "rg_percentiles": _t(
        "Percentiles 5, 50 y 95 de los VAN de todas las simulaciones de Monte Carlo, con los supuestos muestreados de distribuciones "
        "triangulares (mínimo y máximo del tornado y moda en el valor de la sesión).",
        "Dar el rango probable del VAN y no solo un valor.",
        "La decisión de inversión en recuperación de calor se toma con riesgo: un percentil 5 negativo avisa que el proyecto puede no pagarse."),
    "opt_curva": _t(
        "Valor del objetivo en cada punto de la grilla de la variable elegida, más el refinamiento por sección dorada alrededor del mejor punto; "
        "cada punto resuelve una copia de la planta.",
        "Ver la forma de la curva y qué tan plano es el óptimo.",
        "Muestra cuánto se gana o se pierde de calor recuperado o de VAN al mover una variable de diseño de la recuperación."),
    # ------------------------------------------------------------------------------------------------ Operación y Calidad
    "op_turnos": _t(
        "Un turno por fila, el más reciente arriba. La producción sale de la capacidad del turno (estado del equipo crítico, fallas y "
        "mantenimiento), la fracción conforme del laboratorio, las ventas = mínimo entre el producto conforme disponible y la demanda, y el "
        "faltante = demanda − ventas. El combustible evitado es el calor de la cascada × horas del turno, a la producción de ese turno.",
        "Seguir la operación turno a turno, como en el simulador del profesor.",
        "Une la operación con la energía: la recuperación de calor solo ahorra gas o biomasa en las horas en que la planta produce."),
    "op_estado": _t(
        "Estado de cada equipo (1 = buen estado), que baja entre 0,002 y 0,004 por turno hasta 0,65 y sube con el mantenimiento del equipo "
        "crítico; utilización = carga / (capacidad nominal × estado).",
        "Decidir dónde hacer mantenimiento.",
        "El desgaste baja la capacidad efectiva y las horas productivas, y con ellas el calor que se puede recuperar."),
    "op_supuestos": _t(
        "Supuestos de la operación y del laboratorio guardados en el motor (motor/operacion.py), cada uno con su valor, unidad y justificación.",
        "Saber con qué datos trabaja la operación por turnos.",
        "Declara qué cifras son supuestos didácticos y cuáles vienen de una fuente, como exige el informe."),
    "cal_lab": _t(
        "Último resultado de cada ensayo recibido del laboratorio virtual, la especificación de la variable y su estado (dentro o fuera). La "
        "fuente de cada límite está en la tabla «Variables de calidad» al final de la pestaña.",
        "Ver de inmediato si el producto cumple y qué acción correctiva usar.",
        "Las acciones correctivas son parámetros de la planta: corregir la calidad cambia también el vapor, el gas y la recuperación de calor."),
    "cal_variables": _t(
        "Por variable de calidad: media de la planta, desviación estándar de la variabilidad común multiplicada por el factor de desgaste del "
        "equipo de control y % dentro de especificación = probabilidad normal entre los límites. Especificación, categoría y fuente del límite "
        "y origen de la media vienen del motor.",
        "Ver qué variables tienen poco margen frente a su especificación.",
        "La calidad no se puede sacrificar por energía: una recuperación de calor que cambie temperaturas de proceso debe mantener el producto "
        "dentro de especificación."),
    # ------------------------------------------------------------------------------------------------ Temporada y Dinámica
    "tem_dia": _t(
        "Un día por fila (uno de cada siete si la temporada pasa de 90 días) de la simulación de eventos discretos: camiones y toneladas que "
        "llegan, procesado, cola al cierre, materia prima degradada sobre el umbral de espera, camiones en espera promedio y máximo, espera "
        "media simulada y espera de Kingman, W = (ca² + cs²)/2 × u/(1 − u) × te (Hopp y Spearman, 2008).",
        "Ver los días de congestión en el patio y comparar la simulación con la fórmula.",
        "Si la recepción no da abasto, la planta trabaja menos horas a plena carga y se recupera menos calor."),
    "tem_programa": _t(
        "Por actividad del programa (producción, arranque, limpieza CIP, paradas): número de barras del Gantt, horas y calor recuperable no "
        "aprovechado = calor de la cascada × horas detenidas.",
        "Ver cuánto tiempo de la temporada no se produce y cuánto calor se pierde por eso.",
        "Las horas efectivas fijan el ahorro anual de gas o biomasa; las paradas lo reducen."),
    "tem_supuestos": _t(
        "Supuestos de la temporada del rubro guardados en el motor (motor/temporada.py), con valor, unidad y justificación.",
        "Saber con qué datos se simulan la llegada de materia prima y el programa.",
        "Declara qué cifras son supuestos y por qué, como exige el informe."),
    "din_balance": _t(
        "Integrales en el tiempo de la simulación (kWh): calor entregado, calor que sale con el producto, calor acumulado en el acero y cierre "
        "= entregado − producto − acumulado; el calor entregado se reparte entre lo cubierto con recuperación y el externo (caldera o generador).",
        "Comprobar que el modelo dinámico conserva la energía y ver cuánto calor externo pide el arranque.",
        "En el arranque el calor residual todavía no está disponible: esa energía extra se paga con gas o biomasa y reduce el ahorro real."),
    "din_supuestos": _t(
        "Supuestos del modelo dinámico (masa de acero, retención, retardo de las fuentes, ganancia y capacidad máxima) con su valor y la "
        "justificación guardada en motor/dinamico.py.",
        "Saber qué datos del equipo usa la simulación.",
        "Todos son supuestos declarados: conviene reemplazarlos por datos de la planta antes de sacar conclusiones del arranque."),
    # ------------------------------------------------------------------------------------------------ Línea
    "ln_fallas": _t(
        "Una fila por equipo: si falla, distribución y media del tiempo entre fallas (MTBF) y de reparación (MTTR) en horas, y la base del reloj "
        "(tiempo ocupado o calendario, Law, 2015, cap. 14). El tiempo hasta la falla se cuenta desde que el equipo volvió a operar. Valores de "
        "partida: Supuesto PAT 134 por tipo de equipo (ver supuestos).",
        "Cargar las fallas de cada equipo para la simulación por *ticks*.",
        "Las fallas detienen la línea y con ella las corrientes calientes: el calor recuperable baja en la misma proporción."),
    "ln_tanques": _t(
        "Un tanque pulmón entre dos equipos, con su capacidad y nivel inicial en toneladas. Capacidad 0 anula el tanque: el equipo de antes "
        "entrega directo al siguiente en el mismo *tick*.",
        "Probar cuánto pulmón hace falta para que una falla no detenga toda la línea.",
        "Un pulmón mantiene operando los equipos que entregan calor residual mientras otro está en falla."),
    "ln_resultado": _t(
        "Por equipo: tasa máxima y carga de diseño (t/h), utilización, horas en cada estado (operando, bloqueado por falta de espacio aguas "
        "abajo, esperando por falta de entrada, en falla, en mantenimiento y detenido programado), número de fallas, disponibilidad = horas "
        "planificadas sin falla ni mantenimiento / horas planificadas y la teórica MTBF / (MTBF + MTTR).",
        "Encontrar qué equipo frena la línea y por qué.",
        "Las horas de operación reales fijan cuánto calor residual hay de verdad y cuánto combustible se desplaza."),
    "ln_supuestos": _t(
        "Supuestos de la simulación de la línea (motor/linea_fluida.py) con valor, unidad y justificación.",
        "Saber con qué datos se simuló.",
        "Declara qué cifras son supuestos, como exige el informe."),
    "ln_fallas_usadas": _t(
        "Expresión de las distribuciones de falla y reparación que usó la corrida, el reloj de falla y su origen (formulario o Datos de "
        "entrada). Gamma y lognormal con coeficiente de variación 0,5 y uniforme de 0,5 a 1,5 veces la media cuando solo se da la media "
        "(Supuesto PAT 134).",
        "Dejar registro exacto de las fallas simuladas.",
        "Permite repetir la corrida y justificar la disponibilidad que se usa para el calor recuperable."),
    "ln_tanques_usados": _t(
        "Capacidad y nivel inicial de cada tanque pulmón en la corrida y su origen, o «anulado» si su capacidad es 0.",
        "Dejar registro de los pulmones simulados.",
        "Permite repetir la corrida y comparar configuraciones de la línea."),
    # ------------------------------------------------------------------------------------------------ Experimentos
    "ex_variables": _t(
        "Variables que el modelo elegido deja cambiar, con unidad, valor por defecto (el de la planta) y rango permitido, según motor/experimentador.py.",
        "Saber qué se puede mover en los escenarios y en el optimizador.",
        "Son las palancas de operación que cambian la producción y, con ella, el calor que se recupera."),
    "ex_medidas": _t(
        "Medidas de desempeño que entrega cada réplica del modelo, con su unidad y si mayor o menor es mejor.",
        "Elegir qué comparar entre escenarios y qué optimizar.",
        "Incluyen las medidas de producción y energía con que se juzga cada escenario del proyecto."),
    "ex_escenarios": _t(
        "Una fila por escenario y una columna por variable; una celda vacía toma el valor por defecto. Cada escenario se corre con las mismas "
        "réplicas y semillas (números aleatorios comunes, Law, 2015, cap. 10).",
        "Armar los casos que se quieren comparar, como el *Experimenter* de FlexSim.",
        "Permite comparar con justicia cambios de operación que afectan la producción y el calor recuperable."),
    "ex_resultados": _t(
        "Por medida y escenario: media de las réplicas, intervalo de confianza al 95 % = media ± t × desviación / √n con la t de Student, "
        "desviación estándar muestral, mínimo y máximo (Law, 2015, cap. 9).",
        "Comparar escenarios con su incertidumbre y no solo con un promedio.",
        "Una diferencia de producción o de energía que cae dentro del intervalo no justifica un cambio en la planta."),
    "ex_opt_vars": _t(
        "Las variables marcadas se buscan entre su mínimo y máximo con el paso indicado; las no marcadas quedan en su valor por defecto. El "
        "rango de partida es ±25 % del valor por defecto dentro de los límites del modelo.",
        "Definir el espacio de búsqueda del optimizador.",
        "Acota la búsqueda a cambios de operación realistas para la planta."),
    "ex_opt_restr": _t(
        "Cada fila es una restricción sobre la media de las réplicas de una medida (mayor o igual, menor o igual) con su valor; un candidato que "
        "no la cumple queda como no factible.",
        "Exigir mínimos o máximos, por ejemplo de producción, mientras se optimiza otra medida.",
        "Evita optimizar la energía a costa de la producción o de la calidad."),
    "ex_candidatos": _t(
        "Candidatos ordenados por la media del objetivo entre sus réplicas, con su intervalo de confianza al 95 % (t de Student), los valores de "
        "las variables, si es factible y qué restricciones no cumple. Se muestran los 50 primeros.",
        "Ver la mejor configuración y cuán cerca quedan las siguientes.",
        "Si varias configuraciones tienen intervalos que se traslapan, conviene elegir la más simple de operar."),
    # ------------------------------------------------------------------------------------------------ Datos de entrada
    "aj_tabla": _t(
        "Siete distribuciones ajustadas por máxima verosimilitud a los datos, ordenadas por Anderson-Darling (A²), con chi-cuadrado en "
        "intervalos equiprobables y Kolmogorov-Smirnov (D) (Law, 2015, cap. 6); «pasa» compara cada estadístico con su valor crítico al 5 % y al "
        "10 %. La expresión es la que se escribe en FlexSim.",
        "Elegir la distribución de los tiempos de descarga o de la duración de las fallas.",
        "Tiempos bien ajustados hacen creíbles la cola de camiones y la disponibilidad, que fijan las horas de operación y el calor recuperable."),
    "aj_supuestos": _t(
        "Supuestos del ajuste guardados en motor/ajuste.py, con su justificación.",
        "Saber qué decisiones de método hay detrás de la tabla de ajuste.",
        "Declara los supuestos, como exige el informe."),
    "xl_cambios": _t(
        "Una fila por celda del Excel subido que difiere de la planta: destino (planta, temporada, economía o datos medidos), hoja y fila, "
        "equipo o tabla, parámetro, valor antes y después, unidad y nota de la validación (motor/libro_planta.py).",
        "Revisar los cambios antes de aplicarlos, como el *Excel Import/Export* de FlexSim.",
        "Permite cargar datos de la planta en lote con trazabilidad de qué cambió en el balance y en la economía."),
    # ------------------------------------------------------------------------------------------------ Calculadoras
    "k_pinch_editor": _t(
        "Corrientes de la planta resuelta (residuales calientes y sumidero) o un ejemplo si no hay planta. Caliente si la entrada es mayor que la "
        "salida; un calor latente se escribe como una corriente que baja 1 °C con CP igual a su calor. Se pueden agregar o editar filas.",
        "Armar el problema del *pinch* a mano o revisar el de la planta.",
        "Con estas corrientes se calcula cuánto calor se puede recuperar como máximo en el tomate o en la biomasa."),
    "k_pinch_intervalos": _t(
        "Tabla del problema (Linnhoff y Hindmarsh, 1983; Kemp, 2007): temperaturas desplazadas ΔTmin/2 (calientes bajan, frías suben), Σ CP de "
        "las corrientes presentes en cada intervalo, balance del intervalo = (Σ CP calientes − Σ CP frías) × (T alta − T baja) y cascada "
        "corregida = calor acumulado + servicio caliente mínimo; donde la cascada corregida vale cero está el *pinch*.",
        "Obtener las metas de servicio caliente y frío y la temperatura de *pinch*.",
        "Es la meta de energía con que se compara la cascada en serie y las demás alternativas de recuperación."),
    "k_brix": _t(
        "Para concentraciones de 5 a 36 °Brix a la temperatura elegida: cp y densidad por composición de Choi y Okos (1986), con los sólidos "
        "tratados como carbohidratos (Supuesto); K y n de la ley de potencia y viscosidad aparente μ = K × γ^(n − 1) a la tasa de corte elegida "
        "(Supuesto declarado en motor/propiedades.py).",
        "Consultar las propiedades del jugo y la pasta en cada etapa de concentración.",
        "El cp fija el calor que absorbe el tomate al precalentarse y la viscosidad el bombeo y el coeficiente de transferencia de los "
        "intercambiadores de recuperación."),
    "k_hidraulica": _t(
        "Por línea de líquido: caudal (m³/h) del balance; diámetro por la velocidad de diseño; Reynolds y régimen; pérdida de carga con Swamee "
        "y Jain (1976) en agua y Steffe (1996) en la pasta; altura = pérdida / (ρ g) + altura a vencer; potencia = caudal × presión total / "
        "rendimiento. Diámetro, largo, altura y rugosidad del acero inoxidable sanitario son Supuestos declarados en motor/hidraulica.py y la "
        "reología de la pasta, en motor/propiedades.py.",
        "Estimar la potencia de bombeo de la planta y la línea con mayor pérdida.",
        "Un intercambiador de recuperación agrega pérdida de carga: la electricidad extra de bombeo se descuenta del ahorro de combustible."),
    # ------------------------------------------------------------------------------------------------ Evaluación y Curso
    "ev_puntaje": _t(
        "Puntos de cada criterio de la evaluación automática al finalizar (motor/operacion.py), con su máximo y el total sobre 100. Usa "
        "indicadores de actividad y logros; no interpreta el contenido de las justificaciones.",
        "Ver el resultado de la práctica por criterio.",
        "Incluye 15 puntos por recuperación de calor, el aporte del PAT al simulador del profesor."),
    "ev_criterios": _t(
        "Criterios de la evaluación con sus puntos en esta aplicación, el peso que tienen en el simulador del profesor y cómo se mide cada uno.",
        "Saber de antemano qué se evalúa.",
        "Muestra que la recuperación de calor, que no existe en el simulador del profesor, se evalúa aquí como criterio propio."),
    "cur_variante": _t(
        "Cada parámetro de su variante sale del identificador con SHA-256: un número estable entre 0 y 1 que se lleva al rango del curso y se "
        "redondea al paso declarado (motor/curso.py). La fuente de cada rango es la de la columna Fuente.",
        "Saber con qué datos trabaja su caso.",
        "Cada estudiante resuelve una planta distinta pero comparable, con la recuperación de calor medida sobre sus propios datos."),
    "cur_profesor": _t(
        "Una fila por estudiante inscrito: número de entregas, último y mejor puntaje y fecha de la última entrega, leídos de la base de datos "
        "local con la clave del profesor.",
        "Seguir las entregas del curso y exportarlas a CSV.",
        "Permite usar el simulador y su módulo de recuperación de calor como actividad evaluada del curso."),
    # ------------------------------------------------------------------------------------------------ Informe (vista previa y archivo)
    "inf_equipos": _t(
        "Equipos de la planta con su identificador, nombre, tipo y la categoría y letra de su símbolo según ISO 10628.",
        "Inventario de equipos del informe.",
        "Identifica los equipos que generan calor residual y los que lo reciben."),
    "inf_parametros": _t(
        "Todos los parámetros de cada equipo con su valor, unidad, categoría (Supuesto, literatura, fabricante o medido) y fuente, tal como "
        "están en la planta.",
        "Dejar en el informe la fuente de cada cifra de partida.",
        "Cada resultado de recuperación de calor descansa en estos datos; sin su fuente no se puede defender."),
    "inf_corrientes": _t(
        "La misma tabla de corrientes de la pestaña Diseño: caudal y temperatura de la corriente de salida × reparto, °Brix o humedad y el calor "
        "de las corrientes de servicio.",
        "Documentar el balance de la planta.",
        "Contiene la oferta de calor residual y el sumidero del proyecto."),
    "inf_cierres": _t(
        "Cierre por equipo = entra − sale de masa, sólidos y energía, como en la pestaña Balances.",
        "Probar en el informe que el balance cierra.",
        "Un balance que cierra respalda el calor recuperable que se informa."),
    "inf_instrumentos": _t(
        "Lazos de instrumentación con su identificación ISA-5.1, equipo, descripción y elemento final.",
        "Documentar el control de la planta.",
        "Muestra cómo se controlan las temperaturas cuando se integra la recuperación de calor."),
    "inf_recuperacion": _t(
        "Calor del sumidero, de la cascada en serie, del objetivo *pinch* y, en el tomate, de solo los condensados (kW), con su cobertura = "
        "calor / sumidero, como en la pestaña Recuperación de calor.",
        "Resumir el potencial de recuperación.",
        "Es el resultado técnico central del proyecto."),
    "inf_economia": _t(
        "Gas desplazado por la cascada (MMBtu) = calor × horas / eficiencia PCS / 293,071; CO2 evitado con el factor de la caldera; ahorro = "
        "MMBtu × precio × dólar / 10⁶, con las fuentes del precio y del dólar que se citan abajo.",
        "Resumir el beneficio económico y ambiental.",
        "Es lo que paga la inversión en recuperación de calor en la planta de pasta de tomate."),
    "inf_economia_bio": _t(
        "Biomasa del caso base y desplazada por la cascada (t y m³ estéreo) = calor × horas / eficiencia / PCI húmedo y densidad a granel; CO2 "
        "biogénico = masa seca × carbono × 44/12; ahorro = m³ × precio / 10⁶, con la fuente del precio citada abajo.",
        "Resumir el beneficio en los rubros de biomasa.",
        "Es lo que paga la inversión en recuperación de calor con generador a biomasa."),
}


def texto(clave: str, antes: str | None = None, **kw) -> str:
    t = TEXTOS[clave]
    if kw:
        t = t.format(**kw)
    return (antes.strip() + "\n\n" + t) if antes else t


def tabla(clave: str, titulo: str, nivel: int = 5, dg=None, antes: str | None = None, **kw):
    """Título de la tabla con su «?» (C.ayuda) y las tres partes del texto."""
    C.ayuda(texto(clave, antes, **kw), titulo, nivel, dg=dg)


def html(clave: str, titulo: str, nivel: int = 2, **kw) -> str:
    """Igual que tabla(), pero como HTML para el informe descargable."""
    return C.ayuda_html(texto(clave, None, **kw), titulo, nivel)
