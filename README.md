# Simulador PAT: diseño asistido de ingeniería básica

Proyecto de Aplicación Tecnológica de Jaime Andrés Cifuentes Díaz, Ingeniería Civil Industrial, Universidad de Talca, campus Curicó. Profesor: Carlos Torres Fuchslocher.

Aplicación en Python y Streamlit para diseñar una planta a partir de un desafío (producto, demanda y precios de venta): balances, recuperación de calor, instrumentación ISA, costeo con índice de Williams y CEPCI, layout con elevaciones, evaluación económica y Montecarlo de confiabilidad y demanda. Caso base: planta de pasta de tomate basada en Agrozzi (Teno, Región del Maule), y plantas de pellet, chip y leña.

## Ejecutar en el computador
```
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Publicar en Streamlit Community Cloud
1. Subir este repositorio a GitHub.
2. En https://share.streamlit.io elegir el repositorio, rama `main`, archivo `streamlit_app.py` y Python 3.12.
3. En *Advanced settings* > *Secrets* pegar el contenido de `.streamlit/secrets.toml.ejemplo` con las claves reales.

La base SQLite incluida es la semilla: en la nube se reinicia cuando la aplicación se reinicia. Los datos permanentes irán en Supabase.

## Publicar en Hugging Face Spaces con acceso controlado (PAT 138)
1. Crear un espacio con la plantilla Docker (Hugging Face ya no ofrece Streamlit como SDK propio) y subirle `hf_space/Dockerfile` y `hf_space/README.md`. El espacio baja el código de la rama `hf` de este repositorio.
2. En *Settings* > *Variables and secrets* agregar los secretos `PROFESOR_CLAVE_SHA256` (SHA-256 de la clave del profesor) y `PAT_USUARIOS` (una línea por usuario: `usuario;rol;clave;nombre`, rol docente o estudiante).
3. La imagen fija `PAT_ACCESO=usuarios`: la aplicación pide usuario y clave antes de abrir. Sin `PROFESOR_CLAVE_SHA256`, la clave por defecto del profesor no abre la aplicación publicada.

El espacio gratuito no guarda la base entre reinicios: los usuarios permanentes van en `PAT_USUARIOS`.
