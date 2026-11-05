# Servidor MCP del simulador PAT

Expone el motor `pat_sim` como servidor del *Model Context Protocol* (MCP), con el SDK oficial de Python (paquete `mcp`, clase `FastMCP`). Un agente puede así crear una planta, cambiar parámetros, resolver los balances, evaluar la economía y proponer el layout, usando los mismos cálculos de la aplicación Streamlit. Responde a la sección MCP del correo del profesor Torres del 04-11-2026.

## Herramientas

| Herramienta | Qué hace |
|:---|:---|
| `listar_escenarios` | Rubros disponibles: agrozzi, pellet, chip, lena |
| `crear_planta(rubro)` | Crea la planta y devuelve su `planta_id` (registro en memoria) |
| `listar_equipos(planta_id)` | Equipos y parámetros editables |
| `cambiar_parametro(planta_id, equipo, parametro, valor)` | Edita un parámetro |
| `resolver(planta_id)` | Producción, cuello de botella, utilizaciones, servicios y avisos |
| `recuperacion_calor(planta_id)` | Cascada, pinch, bomba de calor y combustible desplazado |
| `evaluar_economia(planta_id, precio_gas, dolar, tasa, anios, inversion)` | Ahorro, VAN, TIR y recuperación (MM$) |
| `costear(planta_id)` | Costo de equipos con la bibliografía, sin internet |
| `montecarlo_economico(planta_id, n)` | VAN con fallas y demanda variable, tres estrategias de capacidad |
| `proponer_layout(planta_id)` | Disposición con algoritmo propio, sin modelo de lenguaje |
| `guardar_version` y `cargar_version` | Versiones en la base SQLite (`03 Base de datos`) |
| `listar_desafios` | Desafíos del mantenedor |

Los ids de planta viven mientras el servidor esté corriendo; para conservar un diseño hay que usar `guardar_version`.

## Instalación y ejecución

1. Instalar el entorno del simulador con `07 Instaladores y entorno/Instalar entorno PAT.bat` (crea `%LOCALAPPDATA%\PAT_simulador\venv`).
2. Instalar el SDK: `%LOCALAPPDATA%\PAT_simulador\venv\Scripts\python.exe -m pip install -r requirements.txt` (el `.bat` lo hace solo si falta).
3. Correr por stdio: `python servidor_mcp_pat.py`. Normalmente no se corre a mano: lo lanza el cliente MCP. `Abrir servidor MCP PAT.bat` lo deja corriendo con el entorno correcto.

## Conectarlo a Claude Desktop o Claude Code

Claude Desktop: agregar el bloque a `claude_desktop_config.json` y reiniciar. Claude Code: el mismo bloque en un archivo `.mcp.json`, o con el comando `claude mcp add`. Ajustar las rutas a su computador.

```json
{
  "mcpServers": {
    "pat_sim": {
      "command": "C:\\Users\\jaime\\AppData\\Local\\PAT_simulador\\venv\\Scripts\\python.exe",
      "args": ["C:\\Users\\jaime\\OneDrive\\Escritorio\\PAT\\Aplicacion simulador\\09 Servidor MCP\\servidor_mcp_pat.py"]
    }
  }
}
```

## Conectarlo a un agente LangChain

Se usa el adaptador MCP de LangChain, revisar la documentación vigente para el nombre exacto del paquete y de las clases. La idea: el adaptador lanza este mismo comando por stdio (`command` y `args` como arriba), convierte cada herramienta MCP en una herramienta de LangChain y se la entrega al agente, que elige el modelo de lenguaje que se configure. No se escribe aquí el código para no inventar nombres.

## Por qué Anatomy no es un servidor MCP

Anatomy (https://github.com/wheresryan22/anatomy) es una *skill* de agente: un archivo `SKILL.md` con instrucciones que Claude Code, OpenCode o Codex cargan y siguen para dibujar figuras isométricas, y se invoca con `/anatomy <descripción>` dentro del agente. No expone herramientas con entradas y salidas definidas ni corre como proceso aparte, y necesita un agente que la ejecute. Un servidor MCP, en cambio, es un proceso que publica funciones llamables por cualquier cliente. Por eso el motor de cálculo va como MCP y las figuras como *skill* (decisión registrada en `01 Requisitos y diseno/Correo_profesor_Torres_04nov2026_proceso_iterativo.md`).

## Pruebas

`02 Motor de calculo Python/tests/test_servidor_mcp.py` usa un sustituto mínimo de `FastMCP` y llama cada herramienta como función normal, con una base SQLite temporal.

## Límites

- El costeo usa solo la bibliografía (sin precios de internet) y el layout solo el algoritmo propio.
- `evaluar_economia` y `montecarlo_economico` evalúan la cascada; el Montecarlo parte con precio de gas 2,77 US$/MMBtu, dólar 990,35, tasa 10 % y 20 años, supuestos de la aplicación.
- No se probó con el paquete `mcp` real (la máquina de pruebas no tiene internet): la interfaz usada es `FastMCP`, `@mcp.tool()` y `mcp.run()`.


## Versión probada
Probado el 05-11-2026 con el paquete oficial `mcp` 1.30.0 (cliente stdio real: 13 herramientas, *hot break* de Agrozzi 15.956,0 kW). La versión 2 de `mcp` renombró FastMCP a MCPServer, por eso requirements.txt fija `mcp>=1.0,<2`.
