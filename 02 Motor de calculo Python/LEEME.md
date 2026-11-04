# Motor de cálculo del simulador PAT (v0.2.0, fase 6, 29-10-2026)

Paquete `pat_sim`: balances de materia y energía por equipo, recuperación de calor y economía.
Los equipos se dibujan con la ISO 10628 y la instrumentación con ISA-5.1; cada lazo tiene su diagrama según la estructura de ISA-5.4.

## Cómo probarlo

```
pip install -r requirements.txt
python -m pytest -q tests
```

Las pruebas de test_agrozzi.py comparan la aplicación con el modelo de la planta basada en Agrozzi (results.json y fuel.json, iguales al Modelo_PAT_Agrozzi_v2.xlsx): balance de materia, energía, siete corrientes, cascada (9.073,8 kW), pinch (9.722,9 kW), alternativa 2, gas, 18 sensibilidades, 2 aproximaciones mínimas, guardar y cargar, y símbolos.

## Estructura

| Carpeta | Qué hace |
|:---|:---|
| pat_sim/motor | resumen.py (recuperación y gas de cualquier planta), corrientes, propiedades del agua (IAPWS-IF97), equipos, planta (orden topológico y especificaciones de diseño), recuperación, economía y diagrama |
| pat_sim/simbolos | iso10628.py (48 símbolos, categoría de la Tabla C.1 y letra del Anexo D), isa51.py (letras, burbujas, señales), isa54.py (diagrama de lazo) |
| pat_sim/catalogos | tomate.py (10 equipos), servicios.py (caldera a gas), biomasa.py (12 equipos de pellet, chip y leña, fase 6), registro.py (todos los tipos por rubro; guardar y cargar en JSON) |
| pat_sim/datos | bd.py (SQLite), fuentes_indice.py, fuentes_capitulo1.csv (55 fuentes) y fuentes_biomasa.csv (30 fuentes de la fase 6) |
| pat_sim/escenarios | agrozzi.py (planta basada en Agrozzi); pellet.py, chip.py y lena.py (escenarios base de biomasa); biomasa_comun.py |
| tests | Pruebas contra el modelo del Capítulo 1 |

## Uso mínimo

```python
from pat_sim.escenarios import agrozzi
pl = agrozzi.crear(TcMVR=85)          # cualquier parámetro de model.py
r = agrozzi.resumen(pl)
print(r["cascada"], r["cobertura_cascada"])
```

## Fase 6: biomasa (pellet, chip de madera y leña)

La biomasa es una corriente de tipo «biomasa»: m es el caudal húmedo y s la materia seca, así que la humedad en base húmeda es 1 − s/m. Equipos (catalogos/biomasa.py): recepción, secador rotatorio, secador de banda, secador de leña, astilladora, molino de martillos, pelletizadora, enfriador de pellet, criba, procesadora de leña (sierra y partidora), ensacado o acopio con verificación de norma, y generador de calor a biomasa.

- Secador: materia seca constante y balance de energía con referencia en agua líquida a 0 °C. El calor para llevar el aire de secado del ambiente a la temperatura de entrada es el **sumidero** del mapa de recuperación y la demanda del generador. El escape (aire húmedo) es el **calor residual**: sensible hasta el punto de rocío y condensación lineal hasta la temperatura de condensación.
- Equipos mecánicos: electricidad = energía específica × carga; una fracción calienta el producto.
- Pelletizadora y enfriador: el pellet sale de la prensa a 90 °C y se enfría a ambiente + 5 °C; ese calor sale con el aire del enfriador (otro calor residual).
- Ensacado o acopio: humedad y poder calorífico inferior en base húmeda (ISO 18125) contra ENplus A1, ISO 17225-4 o la NCh2907 (leña seca bajo 25 % en base seca); avisa si no cumple.
- Generador a biomasa: el resumen entrega la biomasa combustible (t, m³ estéreo, MWh) y el CO2 biogénico que desplaza cada alternativa, en lugar del gas natural.
- Cambios en el núcleo: planta.py reparte la demanda de calderas y generadores por puerto «vapor» o «calor» y suma el aire de secado al cierre de masa; propiedades.py agrega la presión y la temperatura de saturación (punto de rocío); resumen.py reconoce el generador a biomasa. Agrozzi da las mismas cifras.

Escenarios base (cifras de control en 06 Documentacion para el informe\Fase6_catalogo_biomasa.md):

| Escenario | Producto | Calor de secado | Cascada | Electricidad |
|:---|:---:|:---:|:---:|:---:|
| Pellet (5 t/h, planta tipo de Thek y Obernberger, 2009) | 5 t/h al 10 % | 5.862 kW (4,09 MJ/kg de agua) | 1.709,9 kW (29,2 %) | 132,5 kWh/t |
| Chip de madera (rollizos de pino radiata) | 10 t/h al 25 % | 7.514 kW | 1.549,1 kW (20,6 %) | 23,2 kWh/t |
| Leña seca de eucalipto | 2 t/h al 18 % | 2.708 kW | 848,8 kW (31,3 %) | 70,1 kWh/t |

## Pendiente

- Hecho en PAT 121: fase 4 (base SQLite en `03 Base de datos`) y fase 5 (interfaz en `04 Interfaz Streamlit`); ahora son 45 pruebas.
- Hecho en PAT 122: fase 6 (catálogos, escenarios y fuentes de biomasa); 65 pruebas del motor y la base de datos (20 de biomasa).
- Hecho en PAT 123: fase 7 (Capítulos 2, 3 y 4 con la planta basada en Agrozzi); 67 pruebas.
- Hecho en PAT 125: revisión independiente; correcciones de la interfaz (deslizadores y rubro), del secador de biomasa (el escape sigue la temperatura final de los residuales) y de los LEEME.

## Fase 7 (PAT 123, 29-10-2026)

- `pat_sim/motor/costos.py`: inversión de orden de magnitud de intercambiadores (Shamoushaki et al., 2021, actualizada con el índice PCU332410332410 del BLS, factor de instalación 2,5) y de bombas de calor (Danish Energy Agency, 2026), con fuente y fecha en el encabezado. Resuelve el pendiente de la inversión del Capítulo 1.
- `tests/test_costos.py`: 2 pruebas nuevas; con ellas pasan 67 (registro en `05 Pruebas y capturas/Pruebas_fase7_29oct2026.txt`).
- Los Capítulos 2 a 4 se calcularon con este motor: `PAT/Capitulos 2 a 4 Agrozzi/scripts/calc_cap234.py`.

## Fase 8 (PAT 124, 29-10-2026)

- Sin cambios en el motor. Se corrieron otra vez las 67 pruebas (pasan) y la interfaz con el banco sin internet (siete pestañas sin errores con las cuatro plantas): `05 Pruebas y capturas/Pruebas_fase8_29oct2026.txt`.
- El Capítulo 5 (`PAT/Capitulo 5 Aplicacion`) documenta la aplicación con cifras calculadas por este motor.


## Operación por turnos, calidad y evaluación (PAT 130, 02-11-2026)

- `motor/operacion.py`: `Operacion` (estado de la práctica, se guarda en JSON), `linea` (producción planificada y real, materia prima por tonelada, equipo crítico), `correr_turno` (runShift del profesor), `tomar_muestra` y `entregar_muestras` (sampleLab y deliverLab), `spc` y `grafico_control` (drawSPC, con rango móvil), `evaluar` y `finalizar` (grade). Todas las cifras didácticas están en `SUPUESTOS` con su justificación; los números aleatorios dependen solo de la semilla (FNV-1a del nombre, como el profesor) y del turno.
- `catalogos/calidad.py`: variables de calidad por rubro con la media tomada de la planta resuelta, la fuente del límite y las acciones correctivas.
- `tests/test_operacion.py`: 15 pruebas (reproducibilidad, balance de materia prima, desgaste y mantenimiento, restricción, laboratorio diferido, especificaciones, SPC, gas por turno, evaluación de 100 puntos, JSON).

## PAT 131 (02-11-2026)

`escenarios/chip.py` y `escenarios/lena.py`: la humedad máxima del acopio citaba la fuente de ENplus aunque la norma fuera otra; ahora cita Alakangas et al. (2015), ISO 17225-4 M25, y Superintendencia del Medio Ambiente (2018), NCh2907. Los valores no cambian; 91 pruebas pasan (`05 Pruebas y capturas\Pruebas_PAT131_total_02nov2026.txt`). Se ve en el simulador al reiniciarlo.
