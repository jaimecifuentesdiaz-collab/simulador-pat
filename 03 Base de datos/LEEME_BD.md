# Base de datos del simulador PAT (fase 4; actualizada en la fase 6, 29-10-2026)

Archivo: `simulador_pat.db` (SQLite, biblioteca estándar de Python). Módulo: `02 Motor de calculo Python\pat_sim\datos\bd.py`.
Se reconstruye con `python construir_bd.py` (lee el índice v3 de `PAT\Fuentes\Capitulo 1 2.0`). Ojo: reconstruir reemplaza la base y con ella las versiones guardadas desde la interfaz; antes deja un respaldo con fecha (`simulador_pat_respaldo_AAAAMMDD_HHMMSS.db`). La interfaz crea y precarga la base sola si no existe. En pellet, chip y leña, las cifras de biomasa de cada corrida quedan en `resumen_json` (las columnas de gas quedan vacías).

## Tablas

| Tabla | Qué guarda |
|:---|:---|
| proyectos | Nombre, rubro, descripción, fecha de creación y de modificación |
| versiones | Cada versión de un proyecto: número correlativo, la planta completa en JSON (equipos con sus parámetros, conexiones, especificaciones de diseño, instrumentos ISA-5.1 y la semilla del escenario), nota y fecha |
| corridas | Resultado de cada cálculo de una versión: cobertura de la cascada, calor de la cascada y del pinch (kW), gas base y gas que desplaza la cascada (MMBtu) y el resumen completo en JSON |
| fuentes | Las 45 fuentes del índice v3 del Capítulo 1, 10 que usa el simulador (CFT, Engineering ToolBox, CNE, Banco Central, Bakar) y 30 de la biomasa (fuentes_biomasa.csv): cita, archivo, DOI, enlace, fecha de consulta, nota y huella sha1 |
| parametros_catalogo | Parámetros por defecto de cada tipo de equipo: valor, unidad, categoría, fuente y justificación del supuesto, mínimo y máximo |

Contenido de la precarga: 4 proyectos con su versión 1 y su corrida («Planta basada en Agrozzi» y los escenarios base de pellet, chip de madera y leña), 85 fuentes y 112 parámetros de catálogo. La precarga solo agrega: el 29-10-2026 se aplicó sobre la base existente, sin perder versiones guardadas.

## Uso desde Python

```python
import sys; sys.path.insert(0, r"…\02 Motor de calculo Python")
from pat_sim.datos.bd import BaseDatos
from pat_sim.motor.resumen import resumen_planta
bd = BaseDatos(); bd.precargar()
pid = bd.obtener_proyecto("Planta basada en Agrozzi")["id"]
pl = bd.cargar_version(bd.ultima_version(pid))     # planta resuelta
v = bd.guardar_version(pid, pl, "nota"); bd.guardar_corrida(v["id"], resumen_planta(pl))
```

## Pruebas

`python -m pytest -q tests` en `02 Motor de calculo Python`: 67 pruebas (29 del motor, 11 de la base de datos, 5 del resumen genérico, 20 de biomasa y 2 de costos). La prueba de ida y vuelta guarda la planta de Agrozzi, la carga y vuelve a obtener la cascada de 9.073,8 kW, el pinch de 9.722,9 kW y el gas del Capítulo 1.

## SharePoint de la UTAL

Queda como extensión futura: exige que TI de la UTAL registre la aplicación. El acceso está concentrado en la clase `BaseDatos`; para cambiar de SQLite a SharePoint bastaría una clase con los mismos métodos (guardar_version, cargar_version, guardar_corrida, listar_fuentes).
