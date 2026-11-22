# Base de datos del simulador PAT (fase 4; actualizada en la fase 6, 29-10-2026, y en PAT 138, 13-11-2026)

Archivo: `simulador_pat.db` (SQLite, biblioteca estándar de Python). Módulo: `02 Motor de calculo Python\pat_sim\datos\bd.py`.
Se reconstruye con `python construir_bd.py` (lee el índice v3 de `PAT\Fuentes\Capitulo 1 2.0`). Ojo: reconstruir reemplaza la base y con ella los proyectos guardados desde la interfaz; antes deja un respaldo con fecha (`simulador_pat_respaldo_AAAAMMDD_HHMMSS.db`). La interfaz crea y precarga la base sola si no existe, y al abrir una base anterior le agrega las tablas que le falten (modo curso, mantenedor, tablas genéricas y proyectos del usuario) sin tocar lo que ya tiene. En pellet, chip y leña, las cifras de biomasa de cada corrida quedan en `resumen_json` (las columnas de gas quedan vacías). El esquema completo está en `esquema.sql`.

PAT 144 b (20-11-2026): la versión en la nube (cuentas con rol, proyectos, versiones, actividad y asignaciones en Supabase, con reglas RLS) está en la carpeta `supabase`, con sus `.sql` numerados y su `LEAME.md`. Sin sesión en la nube la aplicación sigue usando esta base.

## Tablas de bd.py

| Tabla | Qué guarda |
|:---|:---|
| proyectos | Plantas de ejemplo y proyectos guardados antes de PAT 138: nombre, rubro, descripción, fecha de creación y de modificación |
| versiones | Cada versión de esos proyectos: número correlativo, la planta completa en JSON (equipos con sus parámetros, conexiones, especificaciones de diseño, instrumentos ISA-5.1 y la semilla del escenario), nota y fecha |
| corridas | Resultado de cada cálculo de una versión: cobertura de la cascada, calor de la cascada y del pinch (kW), gas base y gas que desplaza la cascada (MMBtu) y el resumen completo en JSON |
| fuentes | Las 45 fuentes del índice v3 del Capítulo 1, 10 que usa el simulador (CFT, Engineering ToolBox, CNE, Banco Central, Bakar) y 30 de la biomasa (fuentes_biomasa.csv): cita, archivo, DOI, enlace, fecha de consulta, nota y huella sha1 |
| parametros_catalogo | Parámetros por defecto de cada tipo de equipo: valor, unidad, categoría, fuente y justificación del supuesto, mínimo y máximo |
| proyectos_usuario | PAT 138: proyectos de cada persona (ver abajo) |
| proyectos_usuario_versiones | PAT 138: historial de cada «Guardar» de esos proyectos |

Además, la base recibe al abrirse las tablas del modo curso (curso, estudiantes, entregas), del mantenedor (`pat_sim\datos\mantenedor.py`: símbolos, catálogo de equipos, parámetros, desafíos, estados del material, precedencia, catálogo comercial) y las genéricas de la herramienta docente (`pat_sim\datos\genericos.py`: tipos de planta, equipos, operaciones, modelos comerciales con historial de precios, tipos de demanda, compatibilidad, cursos, usuarios y asignaciones).

Contenido del archivo entregado: 4 proyectos con su versión 1 y su corrida («Planta basada en Agrozzi» y los escenarios base de pellet, chip de madera y leña), 85 fuentes y 303 parámetros de catálogo. No trae proyectos de usuarios: sus dos tablas se crean solas la primera vez que la aplicación abre el archivo. La precarga solo agrega: el 29-10-2026 se aplicó sobre la base existente, sin perder versiones guardadas.

## Proyectos del usuario (PAT 138, 13-11-2026)

Cada proyecto se llama «Proyecto de <persona> <n>»: persona es el nombre escrito en la pantalla Desafío o, con acceso controlado, el usuario con sesión; n es el siguiente número de esa persona (uno más que el mayor que ya usa). Sin nombre queda «Proyecto <n>». El nombre se puede cambiar antes de guardar y no se repite (sin distinguir mayúsculas ni espacios de más): si se repite, la interfaz avisa y ofrece sobrescribir ese proyecto (queda como su versión más nueva) o usar el siguiente número. No hay límite de cantidad (las pruebas guardan 200).

Tabla `proyectos_usuario` (una fila por proyecto, con la copia de su última versión):

| Columna | Qué guarda |
|:---|:---|
| id | Número interno |
| nombre | Nombre único (COLLATE NOCASE) |
| persona | Nombre de la persona del nombre automático |
| numero | n del nombre automático (vacío si el nombre es otro) |
| usuario | Usuario con sesión, si el acceso controlado está activo |
| nota | Última nota escrita al guardar |
| rubro, tipo_planta | Rubro de la planta y tipo de planta del catálogo de 10 plantas |
| creado, modificado | Fechas (AAAA-MM-DDTHH:MM:SS) |
| n_versiones | Cantidad de versiones del historial |
| planta_json | Planta completa (la misma serialización de `versiones`, más la categoría, fuente y justificación de los parámetros que difieren del catálogo, como la selección comercial y los datos medidos) |
| estado_json | Estado de la sesión para retomar el trabajo (`pat_sim\datos\estado_sesion.py`): desafío (variante de tomate, distribución de la llegada, serie de demanda y nombre), economía, COP, temporada, datos medidos, distribuciones ajustadas, layout, costeo, equipos auxiliares, parámetros de Línea, del riesgo económico y del costeo, fichas de Planta real, pesos de Alternativas, tableros, experimento, etapas del flujo de diseño y nombre de la persona |
| resumen_json | Cifras clave para la lista: planta, tipo de planta, variante y distribución del tomate, equipos, capacidad de diseño (t/h), kW recuperados por la cascada, inversión y VAN de la cascada (M$, solo si se ingresó una inversión en Economía) |

Tabla `proyectos_usuario_versiones`: id, proyecto_id, numero (1, 2, 3…), fecha, nota, planta_json, estado_json y resumen_json de cada «Guardar». Al eliminar un proyecto se borran sus versiones.

## Uso desde Python

```python
import sys; sys.path.insert(0, r"…\02 Motor de calculo Python")
from pat_sim.datos.bd import BaseDatos
from pat_sim.motor.resumen import resumen_planta
bd = BaseDatos(); bd.precargar()
pid = bd.obtener_proyecto("Planta basada en Agrozzi")["id"]
pl = bd.cargar_version(bd.ultima_version(pid))     # planta resuelta (tablas de la fase 4)
v = bd.guardar_version(pid, pl, "nota"); bd.guardar_corrida(v["id"], resumen_planta(pl))

# proyectos del usuario (PAT 138)
from pat_sim.datos import estado_sesion as ES
g = bd.guardar_proyecto_usuario(pl, persona="Ana Pérez", estado=ES.capturar({"cop": 2.0}), resumen=ES.resumen(pl))
# g = {"id": 1, "nombre": "Proyecto de Ana Pérez 1", "version": 1, "nuevo": True}
d = bd.cargar_proyecto_usuario(g["id"])           # {proyecto, version, planta, estado, resumen}; version=n para otra
bd.listar_proyectos_usuario(buscar="perez"); bd.renombrar_proyecto_usuario(g["id"], "Mi planta"); bd.eliminar_proyecto_usuario(g["id"])
```

## Pruebas

`python -m pytest -q tests` en `02 Motor de calculo Python`: 1.141 pruebas al 13-11-2026 (1.139 pasan; las 2 que fallan son ajenas a la base: `test_alternativas` busca un JSON que no está en la copia y `test_experimentador` falla con Python 3.13). De la base de datos: 11 en `test_bd.py`, 16 en `test_proyectos_usuario.py` y las de `test_genericos.py` y `test_almacen.py`. La prueba de ida y vuelta guarda la planta de Agrozzi, la carga y vuelve a obtener la cascada de 9.073,8 kW, el pinch de 9.722,9 kW, el hot break de 15.956,0 kW y el gas del Capítulo 1; la de PAT 138 hace lo mismo con un proyecto del usuario y con una planta ideal de tomate con llegada Weibull.

## SharePoint de la UTAL y Supabase

Quedan como extensión futura. SharePoint exige que TI de la UTAL registre la aplicación. En la versión publicada en internet (Streamlit Community Cloud o Hugging Face) la base vuelve a la original cuando el servidor se reinicia, con lo que se pierden los proyectos guardados ahí; guardarlos en Supabase (PostgreSQL) es la mejora prevista. El acceso está concentrado en la clase `BaseDatos`; para cambiar de SQLite a otra base bastaría una clase con los mismos métodos (guardar_proyecto_usuario, cargar_proyecto_usuario, listar_proyectos_usuario, guardar_version, cargar_version, guardar_corrida, listar_fuentes).

## Equipos reales de referencia (PAT 139, 14-11-2026)

Tabla `equipos_referencia` (módulo `pat_sim\datos\referencia_equipos.py`, datos en `referencia_equipos_datos.py`; sin tocar `bd.py`): equipos reales por tipo (el más chico que se encontró, uno medio y el más grande, más filas adicionales) con fabricante, modelo, capacidad, precio con su texto, fecha de consulta, URL, potencia, medidas, peso, material, garantía, plazo y lo que la página dice de confiabilidad; lo que la página no dice queda «sin dato». Se siembra sola e idempotente (INSERT OR IGNORE) la primera vez que se pide una referencia. Con ellos se ajusta el exponente n de Williams (regresión log-log) y se estima el precio del tamaño que falta. El mismo contenido está en `equipos_referencia_PAT139.csv` (UTF-8 con BOM, separador «;», coma decimal). `precio_puntual = 1` marca el precio que la página ata a un modelo con su capacidad; un rango de la serie o una cifra sospechosa queda solo como texto y no entra al ajuste.
