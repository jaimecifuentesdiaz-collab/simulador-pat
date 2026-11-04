# Interfaz Streamlit del simulador PAT (fase 5; rubros de biomasa en la fase 6, 29-10-2026)

`app.py` abre el simulador en el navegador (Streamlit 1.65, Python 3.12). Lee y guarda en `03 Base de datos\simulador_pat.db` y calcula con el paquete `pat_sim` de `02 Motor de calculo Python`.

## Cómo abrirlo

1. Una sola vez: doble clic en `07 Instaladores y entorno\Instalar entorno PAT.bat`. Instala Python 3.12 (winget), crea el entorno en `%LOCALAPPDATA%\PAT_simulador\venv`, instala `requirements.txt`, corre las pruebas y deja el acceso directo **Simulador PAT** en el Escritorio. El registro queda en `instalacion_log.txt`.
2. Después: doble clic en el acceso directo **Simulador PAT** (o en `Abrir simulador PAT.bat`). Abre `http://localhost:8501` en Chrome.

El entorno queda fuera de OneDrive a propósito: miles de archivos de librerías no se sincronizan.

## Pestañas

| Pestaña | Qué hace |
|:---|:---|
| Escenario | Rubro (pasta de tomate, pellet, chip de madera, leña), proyectos y versiones guardadas, crear proyecto; el escenario base del rubro elegido con sus parámetros de partida y, para la biomasa, sus cifras de control (producto, poder calorífico, calor de secado, cascada) |
| Diseño | Simulador de planta interactivo (PAT 128): arrastrar equipos del catálogo, moverlos, conectarlos de puerto a puerto, editar capacidad, estado, repartos y parámetros con recálculo inmediato; flujos animados, capacidad efectiva, recurso crítico y acumulación (teoría de restricciones), diagnóstico, pistas, secuencia sugerida, curva de desempeño, variables de planta, vista por etapas y exportación SVG, PNG, JPG y Mermaid. Debajo: tabla de corrientes, balance por equipo con capacidad efectiva, formulario con todos los parámetros y PFD ISO 10628 con instrumentos ISA-5.1. PAT 134: catálogo «Instrumentación ISA-5.1 y ISA-5.4» (16 burbujas por tipo y ubicación, elementos primarios, válvulas con actuador y elementos de lazo), letras validadas en Propiedades, líneas de señal por tipo, casilla «Instrumentos» y aviso «Mínimo …» de los parámetros acotados |
| Operación | (PAT 130) Turnos de 8 h como el simulador del profesor: meta de utilización, compra de materia prima, mantenimiento (ninguno, preventivo en el equipo crítico, correctivo), inventario de materia prima y de producto conforme, producción limitada por la restricción, demanda variable, fallas, alertas y causas especiales con semilla reproducible, desgaste del estado de cada equipo; en el tomate, el tomate que espera en el patio se pierde y se cuenta el gas que la cascada evita en cada turno. Tabla de supuestos con su justificación |
| Calidad SPC | (PAT 130) Laboratorio virtual con resultado diferido (1 o 2 turnos), especificaciones con su fuente (pasta: °Brix, temperatura de esterilización, pH, consistencia Bostwick y mohos Howard; pellet: ENplus A1; chip y leña: su norma), acciones correctivas que son parámetros de la planta, carta de individuos con rango móvil, regla de 8 puntos a un lado, Cp, Cpk, Pp y Ppk |
| Instrumentación | Lazos ISA-5.1 con validación de letras, símbolos por ubicación, líneas de señal, diagrama de lazo con la estructura de ISA-5.4; desde PAT 134 incluye lo agregado en el lienzo y elige el diagrama por número de lazo |
| Balances | Cierre de masa, sólidos y energía por equipo y detalle de energía |
| Recuperación de calor | Mapa de corrientes, cascada, pinch, solo condensados, bomba de calor; deslizadores de aproximación mínima, temperatura final y COP; sensibilidad |
| Economía | Tomate: gas desplazado y CO2 por temporada, valor con Henry Hub (2,77 US$/MMBtu, CNE sep-2026) y dólar (990,35 $/US$, BCCh 26-10-2026), VAN, TIR, inversión máxima con VAN cero, equilibrio de la bomba de calor. Biomasa: biomasa combustible desplazada (t, m³ estéreo, MWh), CO2 biogénico, valor con 6.750 $/m³ estéreo (INFOR, jun-2025), VAN, TIR y sensibilidad al precio |
| Evaluación | (PAT 130) Nombre del estudiante (fija la semilla), cuatro justificaciones escritas, puntaje automático oculto hasta finalizar: los 85 puntos del profesor (diseño 15, restricciones 20, economía 15, calidad 20, operación 15) más 15 de recuperación de calor; descarga del informe (HTML) y del proyecto (JSON), importación y reinicio de la práctica |
| Informe | Descarga del informe en HTML y de los datos en JSON |

La barra lateral guarda la planta actual como una versión nueva del proyecto y registra su corrida.

## Cifras de control (planta basada en Agrozzi, igual que Modelo_PAT_Agrozzi_v2.xlsx)

Sumidero 15.956,0 kW; cascada 9.073,8 kW (56,9 %); pinch 9.722,9 kW; solo condensados 6.621,9 kW; gas que desplaza la cascada 73.747 MMBtu y 3.855 t de CO2; ahorro 202,3 MM$ por temporada al Henry Hub.

## Supuestos y límites

- No hay inversión en el Capítulo 1: el campo parte en 0 y la pantalla entrega la inversión máxima que da VAN cero. El VAN y la TIR dependen de la inversión que se ingrese.
- Los campos numéricos de Streamlit muestran el punto decimal según el navegador; las tablas y las cifras calculadas usan el formato chileno.
- ISA-5.1-2024 e ISA-5.4 son pagadas: se usa el tutorial de Carballo y Romero (2011) y la estructura pública de ISA-5.4; el diagrama de lazo es simplificado.
- Rubros de biomasa (fase 6): la tabla de corrientes muestra la humedad en base húmeda en lugar del °Brix; en Recuperación de calor la cuarta cifra es la oferta de calor residual (no hay vapor latente aparte). El CO2 de la biomasa es biogénico y no suma al inventario nacional (IPCC, 2006).

## Pruebas

`python -m pytest -q tests` en esta carpeta (8 pruebas de la interfaz con el probador de Streamlit: 5 de la fase 5 y 3 de los rubros de biomasa) y en `02 Motor de calculo Python` (67 pruebas del motor y la base de datos). El 29-10-2026 la interfaz se ejercitó con el banco sin internet (05 Pruebas y capturas): siete pestañas sin errores con las cuatro plantas; el instalador corre las 67 pruebas del motor y las 8 de la interfaz con el probador real. En la revisión del 29-10-2026 (PAT 125) las 75 pasaron con los paquetes verdaderos (Streamlit 1.65.0, iapws 1.5.4).

## Simulador de planta de la pestaña Diseño (PAT 128, 02-11-2026)

Ingeniería inversa del «Diseño libre» del simulador del profesor (`00 Referencia del profesor`), con la mejora del PAT.

| Función del simulador del profesor | En esta aplicación |
|:---|:---|
| Catálogo con clic para agregar, unidades múltiples | Catálogo por rubro con símbolos ISO 10628; arrastrar al lienzo o clic; identificador automático por letra ISO |
| Conexiones de puertos con reparto en %, lista con × | Igual (formulario y lista) y además arrastrando de puerto a puerto, con rechazo de tipos incompatibles y de ciclos |
| Secuencia sugerida | Conecta entradas libres con el equipo anterior y el vapor o calor con la caldera, sin borrar lo existente |
| Diagrama arrastrable y vista Mermaid | Lienzo con zoom, desplazamiento y flujos animados; vista por etapas; exporta SVG, PNG, JPG y Mermaid |
| Capacidad efectiva = nominal × estado; equipo restrictivo en dorado, sobrecarga en rojo | Igual, con el flujo limitado aguas abajo, la acumulación en t/h y la producción real frente a la planificada |
| Propiedades: capacidad, CAPEX, kWh/t, estado | Igual (costo y consumo específico opcionales) más todos los parámetros del proceso con su fuente |
| Curva de desempeño didáctica | Curva del equipo (carga frente a capacidad efectiva) y curva de capacidad de la línea, calculadas |
| Variables de planta | Alimentación planificada, especificaciones de diseño (°Brix, producción) y variables del calor residual |
| Diagnóstico y pistas | Reglas equivalentes más el balance de energía, servicios térmicos y recuperación de calor |
| Sin balance de energía ni fuentes | Balance de materia y energía, vapor, electricidad, calor recuperable y cada cifra con su fuente |

Archivos: `ui/lienzo.py` (envoltura del componente), `ui/componentes/lienzo_planta/index.html` (HTML, CSS y JavaScript sin internet),
`pat_sim/motor/lienzo.py` (eventos, resolución tolerante y teoría de restricciones; pruebas en `tests/test_lienzo.py`).
Después de cambiar el código hay que cerrar la ventana negra y abrir de nuevo «Simulador PAT».


## Operación, Calidad SPC y Evaluación (PAT 130, 02-11-2026)

Completan las seis pestañas del simulador del profesor (Escenario, Diseño libre, Operación, Calidad SPC, Economía y Evaluación). Se leyeron antes sus funciones `runShift`, `sampleLab`, `deliverLab`, `drawSPC` y `grade`. El motor está en `pat_sim/motor/operacion.py` (turnos, laboratorio, SPC, evaluación y la tabla `SUPUESTOS`) y las variables de calidad en `pat_sim/catalogos/calidad.py`.

| Qué agrega el PAT al profesor | Cómo |
|:---|:---|
| La capacidad del turno sale de la planta | Producción real de la teoría de restricciones de Diseño (capacidad nominal × estado); el desgaste y el mantenimiento cambian lo que se produce y se ven en el lienzo |
| La calidad sale del balance | El °Brix es el de la corriente al llenado; la temperatura de esterilización es la consigna TIC-401; la consistencia depende del hot break y los mohos del descarte en la selección. Las acciones correctivas son esos parámetros: cambian también el vapor, el gas y la recuperación de calor |
| Límites con fuente | Esterilización sobre 103 °C (DIA de Agrozzi), pH hasta 4,5 (Reglamento CEE 1764/86), mohos Howard hasta 50 % (CODEX STAN 57-1981), ENplus A1 (European Pellet Council, 2022), ISO 17225-4 y NCh2907 |
| Hallazgo didáctico | Los escenarios base dejan la media justo en un límite (esterilización en 103 °C, humedad del pellet en 10 % y del chip en 25 %): la mitad del producto queda fuera. La pestaña lo avisa y el estudiante debe centrar el proceso |
| Carta de control correcta para datos individuales | Límites con el rango móvil medio / 1,128 (Montgomery, 2020) y regla de ocho puntos seguidos a un lado; el profesor usa la desviación de la muestra y solo puntos fuera de 3σ |
| Energía por turno | Gas evitado por la cascada (MMBtu, CO2 y pesos al precio de Economía) o biomasa evitada |
| Evaluación | Se suman 15 puntos de recuperación de calor a los 85 del profesor |

Pruebas: `tests/test_operacion.py` (15 pruebas del motor) y, en la interfaz, `test_diez_pestanas_sin_errores` y `test_operacion_calidad_y_evaluacion`.
